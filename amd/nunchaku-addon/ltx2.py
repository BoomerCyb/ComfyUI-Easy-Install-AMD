"""Nunchaku Lite LTX2 packed projections with one CPU-staged block on AMD."""
import json
import torch
from safetensors import safe_open
if __package__:
    from .nunchaku_amd import AMDInt4Linear
    from .fp4 import AMDFP4Linear
else:
    from nunchaku_amd import AMDInt4Linear
    from fp4 import AMDFP4Linear


class StreamingBlock(torch.nn.Module):
    def __init__(self,block):
        super().__init__()
        self.block = block

    def _apply(self,fn,recurse=True):
        return self

    def forward(self,hidden_states,*args,**kwargs):
        saved = [(module,dict(module._buffers),dict(module._parameters)) for module in self.block.modules()]
        try:
            for module,buffers,parameters in saved:
                for name,value in buffers.items():
                    if value is not None:
                        module._buffers[name] = value.to(hidden_states.device)
                for name,value in parameters.items():
                    if value is not None:
                        module._parameters[name] = torch.nn.Parameter(value.to(hidden_states.device),requires_grad=False)
            return self.block(hidden_states,*args,**kwargs)
        finally:
            for module,buffers,parameters in saved:
                module._buffers.update(buffers)
                module._parameters.update(parameters)
                if hasattr(module,'clear_runtime_cache'):
                    module.clear_runtime_cache()


def load_ltx2(path,config,*,backend='triton',activation_bits=4,stream=True):
    from diffusers import LTX2VideoTransformer3DModel
    config = dict(config)
    config.pop('quantization_config',None)
    with torch.device('meta'):
        model = LTX2VideoTransformer3DModel.from_config(config)
    with safe_open(str(path),framework='pt',device='cpu') as checkpoint:
        metadata = checkpoint.metadata() or {}
        quant = json.loads(metadata.get('quantization_config','{}'))
        weight = quant.get('weight',{})
        fp4 = weight.get('group_size') == 16
        if not fp4 and (weight.get('dtype'),weight.get('group_size')) != ('int4',64):
            raise ValueError('Expected Nunchaku Lite group-64 INT4 or group-16 FP4')
        keys,consumed,projections = set(checkpoint.keys()),set(),0
        for key in sorted(keys):
            if not key.endswith('.qweight'):
                continue
            prefix = key[:-8]
            original = model.get_submodule(prefix)
            names = {name for name in keys if name.startswith(prefix+'.')}
            state = {name[len(prefix)+1:]:checkpoint.get_tensor(name) for name in names}
            required = {'qweight','wscales','proj_down','proj_up','smooth_factor'}
            if not required <= state.keys() or state.keys()-required-{'smooth_factor_orig','bias','wcscales','wtscale'}:
                raise ValueError(f'Unexpected LTX fields: {prefix}')
            if state['qweight'].shape != (original.out_features,original.in_features//2):
                raise ValueError(f'LTX packed projection shape mismatch: {prefix}')
            layer = (AMDFP4Linear if fp4 else AMDInt4Linear)(state,backend=backend,activation_bits=activation_bits)
            parent,name = prefix.rsplit('.',1)
            setattr(model.get_submodule(parent),name,layer)
            consumed.update(names)
            projections += 1
        backbone = {name:checkpoint.get_tensor(name) for name in keys-consumed}
        missing,unexpected = model.load_state_dict(backbone,strict=False,assign=True)
        expected = {name+'.'+field for name,module in model.named_modules()
                    if isinstance(module,AMDInt4Linear) for field in module._buffers}
        if set(missing) != expected or unexpected:
            raise ValueError(f'LTX load mismatch: {set(missing)^expected}, {unexpected}')
        if any(t.is_meta for t in (*model.parameters(),*model.buffers())):
            raise ValueError('Uninitialized LTX tensor')
    model.to(dtype=torch.bfloat16)
    model.eval().requires_grad_(False)
    if stream:
        model.transformer_blocks = torch.nn.ModuleList([StreamingBlock(block) for block in model.transformer_blocks])
    model.nunchaku_amd_info = dict(architecture='ltx2',blocks=len(model.transformer_blocks),
                                  quantized_projections=projections,backend=backend,activation_bits=activation_bits,
                                  offload='one block at a time' if stream else 'resident',experimental=True)
    return model
