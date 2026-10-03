"""Read upstream Nunchaku INT4 packing directly inside a ROCm Triton GEMM."""
import torch
import os
import triton
import triton.language as tl


@triton.jit
def _gemm(X, W, S, Y, M: tl.constexpr, N: tl.constexpr, K: tl.constexpr,
          BM: tl.constexpr = 16, BN: tl.constexpr = 32, BK: tl.constexpr = 64):
    rows = tl.program_id(0) * BM + tl.arange(0, BM)
    cols = tl.program_id(1) * BN + tl.arange(0, BN)
    kk = tl.arange(0, BK)
    acc = tl.full((BM, BN), 0, tl.float32)
    nt = cols // 128
    np = (cols % 128) // 16
    ns = (cols % 16) // 8
    nl = cols % 8
    for group in range(K // BK):
        kin = group * BK + kk
        word = (((((nt[None, :] * (K // 64) + group) * 8 + np[None, :]) * 8 + nl[None, :]) * 4 + (kk[:, None] % 32) // 8) * 2 + ns[None, :]) * 2 + kk[:, None] // 32
        bits = tl.load(W + word, mask=cols[None, :] < N, other=0)
        q = (bits >> ((kk[:, None] % 8) * 4)) & 15
        q = tl.where(q >= 8, q - 16, q)
        scale_offset = (nt * (K // 64) + group) * 128 + np * 16 + (cols % 8 // 2) * 4 + ns * 2 + cols % 2
        scales = tl.load(S + scale_offset, mask=cols < N, other=0).to(tl.float32)
        b = (q.to(tl.float32) * scales[None, :]).to(X.dtype.element_ty)
        a = tl.load(X + rows[:, None] * K + kin[None, :], mask=rows[:, None] < M, other=0)
        acc += tl.dot(a, b)
    tl.store(Y + rows[:, None] * N + cols[None, :], acc, mask=(rows[:, None] < M) & (cols[None, :] < N))


def packed_linear(x, qweight, wscales):
    if not torch.version.hip or x.device.type != 'cuda':
        raise RuntimeError('This experimental kernel requires ROCm GPU tensors')
    n, half_k = qweight.shape
    k = half_k * 2
    if n % 128 or k % 128 or qweight.dtype != torch.int8 or wscales.numel() != n * (k // 64):
        raise ValueError('Expected upstream group-size-64 INT4 packing')
    flat = x.contiguous().reshape(-1, k)
    result = torch.empty((flat.shape[0], n), dtype=x.dtype, device=x.device)
    arch = torch.cuda.get_device_properties(x.device).gcnArchName
    default_tile = '64,64' if flat.shape[0] >= 64 and arch.startswith('gfx1201') else '16,32'
    bm,bn = tuple(map(int,os.environ.get('NUNCHAKU_GEMM_TILE',default_tile).split(',')))
    if (bm,bn) not in ((16,32),(64,64)):
        raise ValueError('Only validated GEMM tiles 16,32 and 64,64 are supported')
    _gemm[(triton.cdiv(flat.shape[0], bm), triton.cdiv(n, bn))](
        flat, qweight.contiguous().view(torch.int32), wscales.contiguous(), result,
        flat.shape[0], n, k, BM=bm,BN=bn,num_warps=4)
    return result.reshape(*x.shape[:-1], n)


@triton.jit
def _awq_gemm(X, W, S, Z, Y, M: tl.constexpr, N: tl.constexpr, K: tl.constexpr,
              BM: tl.constexpr = 16, BN: tl.constexpr = 32, BK: tl.constexpr = 64):
    rows = tl.program_id(0) * BM + tl.arange(0, BM)
    cols = tl.program_id(1) * BN + tl.arange(0, BN)
    kk = tl.arange(0, BK)
    acc = tl.full((BM, BN), 0, tl.float32)
    for group in range(K // BK):
        kin = group * BK + kk
        original_word = cols[None, :] * (K // 4) + (kin[:, None] // 32) * 8 + kin[:, None] % 8
        d = original_word % 16
        tmp = original_word // 16
        c = tmp % (K // 64)
        row4 = tmp // (K // 64)
        index16 = (row4 // 4) * K + (c * 4 + row4 % 4) * 16 + d
        word = tl.load(W + index16 // 2, mask=cols[None, :] < N, other=0)
        shift = index16 % 2 * 16 + kin[:, None] % 32 // 8 * 4
        q = (word >> shift) & 15
        scale = tl.load(S + group * N + cols, mask=cols < N, other=0).to(tl.float32)
        zero = tl.load(Z + group * N + cols, mask=cols < N, other=0).to(tl.float32)
        b = (q.to(tl.float32) * scale[None, :] + zero[None, :]).to(X.dtype.element_ty)
        a = tl.load(X + rows[:, None] * K + kin[None, :], mask=rows[:, None] < M, other=0)
        acc += tl.dot(a, b)
    tl.store(Y + rows[:, None] * N + cols[None, :], acc, mask=(rows[:, None] < M) & (cols[None, :] < N))


def packed_awq_linear(x, qweight, wscales, wzeros):
    if not torch.version.hip or x.device.type != 'cuda':
        raise RuntimeError('ROCm tensors required')
    n, k = qweight.shape[0] * 4, qweight.shape[1] * 2
    flat = x.contiguous().reshape(-1, k)
    result = torch.empty((flat.shape[0], n), dtype=x.dtype, device=x.device)
    _awq_gemm[(triton.cdiv(flat.shape[0], 16), triton.cdiv(n, 32))](
        flat, qweight.contiguous(), wscales.contiguous(), wzeros.contiguous(), result,
        flat.shape[0], n, k, num_warps=4)
    return result.reshape(*x.shape[:-1], n)
