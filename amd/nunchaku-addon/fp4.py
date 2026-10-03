"""Software E2M1/FP8-scale compatibility for Nunchaku NVFP4 weights on ROCm.

This uses BF16/FP16 matrix products, not NVIDIA NVFP4 instructions or ABI.
"""
import torch
if __package__:
    from .nunchaku_amd import AMDInt4Linear, unpack_weight, unpack_scales
else:
    from nunchaku_amd import AMDInt4Linear, unpack_weight, unpack_scales


def fp4_values(codes):
    lut = torch.tensor([0,.5,1,1.5,2,3,4,6],device=codes.device,dtype=torch.float32)
    values = lut[(codes & 7).long()]
    return torch.where((codes & 8) != 0,-values,values)


def unpack_fp4_scales(packed,n,k):
    if packed.numel() != n*(k//16):
        raise ValueError('Expected group-size-16 FP4 scales')
    return packed.reshape(n//128,k//64,1,8,4,4,4).permute(0,2,5,4,3,1,6).reshape(n,k//16)


def quantize_fp4_activation(x):
    grouped = x.float().reshape(*x.shape[:-1],-1,16)
    scales = (grouped.abs().amax(-1,keepdim=True)/6).clamp(max=448).to(torch.float8_e4m3fn).float()
    safe = torch.where(scales == 0,torch.ones_like(scales),scales)
    normalized = grouped.abs()/safe
    thresholds = torch.tensor([.25,.75,1.25,1.75,2.5,3.5,5],device=x.device)
    codes = torch.bucketize(normalized.contiguous(),thresholds)
    # Round exact halfway values to an even E2M1 mantissa.
    for index in (1,3,5):
        codes = torch.where(normalized == thresholds[index],index+1,codes)
    values = fp4_values(codes) * torch.sign(grouped)
    return (values*scales).reshape_as(x).to(x.dtype)


class AMDFP4Linear(AMDInt4Linear):
    def __init__(self,state,*,backend='triton',activation_bits=4):
        if backend not in ('torch','triton') or activation_bits not in (4,16):
            raise ValueError('Expected torch/triton and 4/16 activation bits')
        super().__init__({k:v for k,v in state.items() if k not in ('wcscales','wtscale')},
                         backend=backend,activation_bits=activation_bits)
        n,k = self.qweight.shape[0],self.qweight.shape[1]*2
        if self.wscales.dtype != torch.float8_e4m3fn or self.wscales.shape != (k//16,n):
            raise ValueError('Expected Nunchaku FP4 E2M1 with FP8 E4M3 group-size-16 scales')
        self.register_buffer('wtscale',state.get('wtscale',torch.ones(1,dtype=torch.bfloat16,device=self.qweight.device)))
        self.register_buffer('wcscales',state.get('wcscales',torch.ones(n,dtype=torch.bfloat16,device=self.qweight.device)))
        if self.wtscale.numel() != 1 or self.wcscales.numel() != n:
            raise ValueError('Unexpected FP4 tensor/channel scale shape')
        self.in_features,self.out_features=k,n

    def _apply(self,fn,recurse=True):
        # ComfyUI may cast model floats globally. FP8 scale bytes must retain
        # their storage format while following the packed weights' device.
        scales=self.wscales
        super()._apply(fn,recurse=recurse)
        self._buffers['wscales']=scales.to(device=self.qweight.device,dtype=torch.float8_e4m3fn)
        return self

    @torch.inference_mode()
    def forward(self,x):
        original=x
        factor,down,up,bias=self._prepare_runtime()
        if factor is not None:
            x=(x.float()/factor).to(x.dtype)
        if self.activation_bits == 4:
            x=quantize_fp4_activation(x)
        if self.backend == 'triton':
            if __package__:
                from .fp4_kernel import packed_fp4_linear
            else:
                from fp4_kernel import packed_fp4_linear
            result=packed_fp4_linear(x,self.qweight,self.wscales,self.wcscales,self.wtscale)
        else:
            n,k=self.out_features,self.in_features
            result=torch.empty((*x.shape[:-1],n),device=x.device,dtype=x.dtype)
            scales=self.wscales.reshape(n//128,-1)
            channel=unpack_scales(self.wcscales,n,64).reshape(-1).float()
            for start in range(0,n,128):
                q=fp4_values(unpack_weight(self.qweight[start:start+128]) & 15)
                s=unpack_fp4_scales(scales[start//128],128,k).float()
                dense=(q.reshape(128,k//16,16)*s[...,None]).reshape(128,k)
                dense=(dense*channel[start:start+128,None]*self.wtscale.float()).to(x.dtype)
                result[...,start:start+128]=x@dense.T
        if down is not None:
            result=(result.float()+(original.float()@down.T)@up.T).to(x.dtype)
        return result if bias is None else result+bias
