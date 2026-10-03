"""Read-only NF4 decoder for LTX's published encoder/connector dependencies.

Uses saved bitsandbytes codebooks and double-quantization scales. No CUDA
extension is imported. These are NF4 weight-only layers, not SVDQuant layers.
"""
import json
import math
import re
import torch
import torch.nn.functional as F
from safetensors import safe_open


class AMDNF4Linear(torch.nn.Module):
    def __init__(self,state,original):
        super().__init__()
        metadata = json.loads(bytes(state['quant_state.bitsandbytes__nf4'].tolist()).decode('utf-8'))
        if metadata.get('quant_type') != 'nf4' or tuple(metadata['shape']) != (original.out_features,original.in_features):
            raise ValueError('NF4 shape or type mismatch')
        self.in_features,self.out_features = original.in_features,original.out_features
        self.blocksize = metadata['blocksize']
        if self.blocksize <= 0:
            raise ValueError('Invalid NF4 block size')
        scales = state['absmax']
        if 'nested_absmax' in state:
            indices = torch.arange(scales.numel())//metadata['nested_blocksize']
            scales = state['nested_quant_map'][scales.long()].float()*state['nested_absmax'][indices].float()+metadata['nested_offset']
        scales = scales.float()
        packed = state['packed'].flatten()
        if packed.dtype != torch.uint8 or packed.numel() != math.ceil(self.in_features*self.out_features/2):
            raise ValueError('Invalid packed NF4 weight')
        if scales.numel() != math.ceil(self.in_features*self.out_features/self.blocksize) or not torch.isfinite(scales).all():
            raise ValueError('Invalid NF4 scales')
        code = state['quant_map'].float()
        if code.numel() != 16 or not torch.isfinite(code).all():
            raise ValueError('Invalid NF4 codebook')
        self.register_buffer('packed',packed)
        self.register_buffer('scales',scales)
        self.register_buffer('code',code)
        self.register_buffer('bias',state.get('bias'))

    def _apply(self,fn,recurse=True):
        scales,code = self.scales,self.code
        result = super()._apply(fn,recurse=recurse)
        self.scales = scales.to(device=self.packed.device)
        self.code = code.to(device=self.packed.device)
        return result

    def decode_rows(self,start,end,dtype):
        size = (end-start)*self.in_features
        offset = start*self.in_features
        if self.packed.device.type == 'cuda':
            if __package__:
                from .nf4_kernel import decode_nf4
            else:
                from nf4_kernel import decode_nf4
            return decode_nf4(self.packed,self.scales,self.code,offset,size,self.blocksize,dtype).reshape(end-start,self.in_features)
        positions = torch.arange(offset,offset+size,device=self.packed.device)
        words = self.packed[positions//2]
        indices = torch.where(positions%2==0,words>>4,words&15).long()
        return (self.code[indices]*self.scales[positions//self.blocksize]).reshape(end-start,self.in_features).to(dtype)

    def decode(self,dtype):
        return self.decode_rows(0,self.out_features,dtype)

    def forward(self,x):
        result = torch.empty((*x.shape[:-1],self.out_features),device=x.device,dtype=x.dtype)
        for start in range(0,self.out_features,256):
            end = min(start+256,self.out_features)
            result[...,start:end] = F.linear(x,self.decode_rows(start,end,x.dtype),None if self.bias is None else self.bias[start:end])
        return result


def load_nf4_into(model,path):
    with safe_open(str(path),framework='pt',device='cpu') as checkpoint:
        mapping = {}
        conversions = getattr(model,'_checkpoint_conversion_mapping',{})
        for original_key in checkpoint.keys():
            key = original_key
            for pattern,replacement in conversions.items():
                key = re.sub(pattern,replacement,key)
            if key in mapping:
                raise ValueError(f'Duplicate converted dependency key: {key}')
            mapping[key] = original_key
        get = lambda name: checkpoint.get_tensor(mapping[name])
        keys,consumed,count = set(mapping),set(),0
        for key in sorted(keys):
            suffix = '.weight.quant_state.bitsandbytes__nf4'
            if not key.endswith(suffix):
                continue
            prefix = key[:-len(suffix)]
            original = model.get_submodule(prefix)
            if not isinstance(original,torch.nn.Linear):
                raise ValueError(f'NF4 target is not a linear: {prefix}')
            names = {name for name in keys if name.startswith(prefix+'.weight.')}
            state = {name[len(prefix+'.weight.'):]:get(name) for name in names}
            state['packed'] = get(prefix+'.weight')
            names.add(prefix+'.weight')
            if prefix+'.bias' in keys:
                state['bias'] = get(prefix+'.bias')
                names.add(prefix+'.bias')
            layer = AMDNF4Linear(state,original)
            if '.' in prefix:
                parent,name = prefix.rsplit('.',1)
                setattr(model.get_submodule(parent),name,layer)
            else:
                setattr(model,prefix,layer)
            consumed.update(names)
            count += 1
        backbone = {key:get(key) for key in keys-consumed}
        missing,unexpected = model.load_state_dict(backbone,strict=False,assign=True)
        if hasattr(model,'tie_weights'):
            model.tie_weights()
        expected = {name+'.'+field for name,module in model.named_modules()
                    if isinstance(module,AMDNF4Linear) for field in module._buffers if module._buffers[field] is not None}
        # Transformers omits a tied LM head in safetensors; verify an actual tie.
        for name in set(missing)-expected:
            parameter = model.get_parameter(name)
            if parameter.is_meta or 'lm_head' not in name or parameter.data_ptr() != model.get_input_embeddings().weight.data_ptr():
                raise ValueError(f'Missing NF4 dependency tensor: {name}')
        if unexpected:
            raise ValueError(f'Unexpected NF4 dependency tensors: {unexpected}')
        # Meta construction also leaves deterministic, non-persistent buffers
        # empty. Recreate these from the architecture, never from random data.
        for module in model.modules():
            if hasattr(module,'rope_init_fn') and getattr(module,'inv_freq',None) is not None and module.inv_freq.is_meta:
                module.inv_freq,module.attention_scaling = module.rope_init_fn(module.config,torch.device('cpu'))
                module.original_inv_freq = module.inv_freq
            for name,value in list(module._buffers.items()):
                if value is None or not value.is_meta or name not in module._non_persistent_buffers_set:
                    continue
                if name == 'position_ids':
                    module._buffers[name] = torch.arange(value.numel(),dtype=value.dtype).reshape(value.shape)
                elif name == 'embed_scale' and hasattr(module,'embedding_dim'):
                    module._buffers[name] = torch.tensor(module.embedding_dim**.5,dtype=value.dtype)
        remaining = [name for name,t in list(model.named_parameters())+list(model.named_buffers()) if t.is_meta]
        if remaining:
            raise ValueError(f'Uninitialized NF4 dependency tensors: {remaining}')
    model.eval().requires_grad_(False)
    model.to(dtype=torch.bfloat16)
    model.nunchaku_amd_nf4_projections = count
    return model
