"""Nunchaku/TinyChat AWQ W4A16 packing on AMD; group-scaled affine weights."""
import torch


def unpack_awq(qweight):
    if qweight.dtype != torch.int32 or qweight.ndim != 2:
        raise ValueError('AWQ weights must be int32 packed matrices')
    n, k = qweight.shape[0] * 4, qweight.shape[1] * 2
    if k % 64:
        raise ValueError('AWQ input width must be divisible by 64')
    words = qweight.contiguous().view(torch.int16).reshape(n // 4, k // 64, 4, 16)
    words = words.permute(0, 2, 1, 3).reshape(-1, 8).to(torch.int32)
    shifts = torch.arange(4, device=qweight.device, dtype=torch.int32) * 4
    return ((words[:, None, :] >> shifts[None, :, None]) & 15).reshape(n, k)


class AMDAWQLinear(torch.nn.Module):
    def __init__(self, state, *, modulation=False, modulation_splits=6, backend='torch'):
        super().__init__()
        for name in ('qweight', 'wscales', 'wzeros', 'bias'):
            if name in state:
                self.register_buffer(name, state[name])
            else:
                setattr(self, name, None)
        self.modulation = modulation
        self.modulation_splits = modulation_splits
        self.backend = backend
        self.in_features = self.qweight.shape[1] * 2
        self.out_features = self.qweight.shape[0] * 4

    @torch.inference_mode()
    def forward(self, x):
        if x.shape[-1] != self.in_features:
            raise ValueError('Input width does not match the AWQ layer')
        n, k = self.out_features, self.in_features
        if self.backend == 'triton':
            if __package__:
                from .packed_kernel import packed_awq_linear
            else:
                from packed_kernel import packed_awq_linear
            result = packed_awq_linear(x, self.qweight, self.wscales, self.wzeros)
            if self.bias is not None:
                result = result + self.bias
            return (result.reshape(*result.shape[:-1], -1, self.modulation_splits).transpose(-1, -2).reshape(*result.shape[:-1], n)
                    if self.modulation else result)
        # This first implementation dequantizes output tiles through ROCm PyTorch.
        result = torch.empty((*x.shape[:-1], n), device=x.device, dtype=x.dtype)
        groups = k // 64
        if self.wscales.shape[0] < groups:
            raise ValueError('Expected group-size-64 AWQ scales')
        for start in range(0, n, 128):
            end = min(start + 128, n)
            q = unpack_awq(self.qweight[start // 4:end // 4]).reshape(end - start, groups, 64).float()
            scales = self.wscales[:groups, start:end].T.float().unsqueeze(-1)
            zeros = self.wzeros[:groups, start:end].T.float().unsqueeze(-1)
            dense = (q * scales + zeros).reshape(end - start, k).to(x.dtype)
            result[..., start:end] = x @ dense.T
        if self.bias is not None:
            result = result + self.bias
        if self.modulation:
            # The converter interleaves six modulation outputs and folds +1 into
            # the two scale biases. Restore contiguous outputs; our AMD block
            # uses those folded scale values directly.
            result = result.reshape(*result.shape[:-1], -1, self.modulation_splits).transpose(-1, -2).reshape(*result.shape[:-1], n)
        return result
