"""Decode Nunchaku E2M1 weights and FP8 scales inside a ROCm BF16 GEMM."""
import torch
import triton
import triton.language as tl


@triton.jit
def _fp4_gemm(X,W,S,C,T,Y,M:tl.constexpr,N:tl.constexpr,K:tl.constexpr,
              BM:tl.constexpr=16,BN:tl.constexpr=32,BK:tl.constexpr=64):
    rows=tl.program_id(0)*BM+tl.arange(0,BM)
    cols=tl.program_id(1)*BN+tl.arange(0,BN)
    kk=tl.arange(0,BK)
    nt=cols//128
    np=(cols%128)//16
    ns=(cols%16)//8
    nl=cols%8
    channel_offset=nt*128+np*16+(cols%8//2)*4+ns*2+cols%2
    channel=tl.load(C+channel_offset,mask=cols<N,other=0).to(tl.float32)
    tensor=tl.load(T).to(tl.float32)
    acc=tl.full((BM,BN),0,tl.float32)
    for group in range(K//BK):
        kin=group*BK+kk
        word=(((((nt[None,:]*(K//64)+group)*8+np[None,:])*8+nl[None,:])*4+(kk[:,None]%32)//8)*2+ns[None,:])*2+kk[:,None]//32
        bits=tl.load(W+word,mask=cols[None,:]<N,other=0)
        code=(bits>>((kk[:,None]%8)*4))&15
        magnitude=code&7
        value=tl.where(magnitude<4,magnitude.to(tl.float32)*.5,
                       tl.where(magnitude==4,2.,tl.where(magnitude==5,3.,tl.where(magnitude==6,4.,6.))))
        value=tl.where((code&8)!=0,-value,value)
        scale_offset=((nt[None,:]*(K//64)+kin[:,None]//64)*128+(cols%8)[None,:]*16+(cols%32//8)[None,:]*4+(cols%128//32)[None,:])*4+kin[:,None]%64//16
        # Read E4M3 bytes directly: this avoids unsupported fp8 masked-load
        # conversions on some Windows ROCm Triton builds.
        scale_bits=tl.load(S+scale_offset,mask=cols[None,:]<N,other=0).to(tl.int32)
        exponent=(scale_bits>>3)&15
        mantissa=scale_bits&7
        scales=tl.where(exponent==0,mantissa.to(tl.float32)/512,
                        (1+mantissa.to(tl.float32)/8)*tl.exp2(exponent.to(tl.float32)-7))
        scales=tl.where((scale_bits&128)!=0,-scales,scales)
        b=(value*scales*channel[None,:]*tensor).to(X.dtype.element_ty)
        a=tl.load(X+rows[:,None]*K+kin[None,:],mask=rows[:,None]<M,other=0)
        acc+=tl.dot(a,b)
    tl.store(Y+rows[:,None]*N+cols[None,:],acc,mask=(rows[:,None]<M)&(cols[None,:]<N))


def packed_fp4_linear(x,qweight,wscales,wcscales,wtscale):
    if not torch.version.hip or x.device.type != 'cuda':
        raise RuntimeError('ROCm GPU tensors required')
    n,k=qweight.shape[0],qweight.shape[1]*2
    if n%128 or k%128 or qweight.dtype != torch.int8 or wscales.shape != (k//16,n):
        raise ValueError('Expected aligned Nunchaku FP4 group-size-16 packing')
    flat=x.contiguous().reshape(-1,k)
    result=torch.empty((flat.shape[0],n),device=x.device,dtype=x.dtype)
    _fp4_gemm[(triton.cdiv(flat.shape[0],16),triton.cdiv(n,32))](
        flat,qweight.contiguous().view(torch.int32),wscales.contiguous().view(torch.uint8),wcscales.contiguous(),wtscale.contiguous(),
        result,flat.shape[0],n,k,num_warps=4)
    return result.reshape(*x.shape[:-1],n)
