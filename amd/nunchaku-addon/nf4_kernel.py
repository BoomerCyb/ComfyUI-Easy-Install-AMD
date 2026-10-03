"""NF4 dependency-weight decoding on AMD, without bitsandbytes native code."""
import torch
import triton
import triton.language as tl


@triton.jit
def _decode(P,S,C,Y,OFFSET:tl.constexpr,SIZE:tl.constexpr,GROUP:tl.constexpr,BLOCK:tl.constexpr):
    local = tl.program_id(0)*BLOCK+tl.arange(0,BLOCK)
    absolute = local+OFFSET
    word = tl.load(P+absolute//2,mask=local<SIZE,other=0).to(tl.int32)
    nibble = tl.where(absolute%2==0,word>>4,word&15)
    value = tl.load(C+nibble)*tl.load(S+absolute//GROUP,mask=local<SIZE,other=0)
    tl.store(Y+local,value,mask=local<SIZE)


def decode_nf4(packed,scales,code,offset,size,group,dtype):
    if not torch.version.hip:
        raise RuntimeError('This decoder requires AMD ROCm')
    result = torch.empty(size,device=packed.device,dtype=dtype)
    _decode[(triton.cdiv(size,1024),)](packed,scales,code,result,offset,size,group,1024)
    return result
