"""ComfyUI adapter for published FLUX.1 Nunchaku signed INT4 checkpoints."""
import json
import torch
from safetensors import safe_open
if __package__:
    from .nunchaku_amd import AMDInt4Linear
    from .awq import AMDAWQLinear
else:
    from nunchaku_amd import AMDInt4Linear
    from awq import AMDAWQLinear


class FoldedModulation(torch.nn.Module):
    def __init__(self, packed, splits):
        super().__init__()
        self.packed, self.splits = packed, splits

    def forward(self, x):
        # Native ComfyUI adds one to scales. The AWQ converter already did so.
        parts = list(self.packed(x).chunk(self.splits, dim=-1))
        parts[1] = parts[1]-1
        if self.splits == 6:
            parts[4] = parts[4]-1
        return torch.cat(parts, dim=-1)


class ParallelInput(torch.nn.Module):
    def __init__(self, qkv, mlp):
        super().__init__()
        self.qkv, self.mlp = qkv, mlp

    def forward(self, x):
        return torch.cat((self.qkv(x), self.mlp(x)), dim=-1)


class ParallelOutput(torch.nn.Module):
    def __init__(self, attn, mlp):
        super().__init__()
        self.attn, self.mlp = attn, mlp

    def forward(self, x):
        return self.attn(x[...,:3072]) + self.mlp(x[...,3072:])


def load_flux(path, *, backend='triton', activation_bits=4):
    import comfy.model_management as management
    import comfy.model_patcher
    import comfy.ops
    import comfy.supported_models
    import comfy.utils
    if not torch.version.hip or not torch.cuda.is_available():
        raise RuntimeError('ROCm PyTorch and an AMD GPU are required')
    if backend not in ('torch','triton') or activation_bits not in (4,16):
        raise ValueError('Expected torch/triton and 4/16 activation bits')
    with safe_open(str(path), framework='pt', device='cpu') as checkpoint:
        metadata = checkpoint.metadata() or {}
        config = json.loads(metadata.get('config','{}'))
        quant = json.loads(metadata.get('quantization_config','{}'))
        if metadata.get('model_class') != 'NunchakuFluxTransformer2dModel':
            raise ValueError('Expected a Nunchaku FLUX.1 checkpoint')
        if quant.get('weight',{}).get('dtype') != 'int4' or quant.get('weight',{}).get('group_size') != 64:
            raise ValueError('Only signed INT4 group-size-64 checkpoints are supported')
        if (config.get('num_layers'),config.get('num_single_layers'),config.get('num_attention_heads'),config.get('attention_head_dim')) != (19,38,24,128):
            raise ValueError('Unsupported FLUX architecture')
        guidance = config.get('guidance_embeds',False)
        unet = dict(image_model='flux', in_channels=16, out_channels=16, patch_size=2,
                    vec_in_dim=768, context_in_dim=4096, hidden_size=3072, mlp_ratio=4,
                    num_heads=24, depth=19, depth_single_blocks=38, axes_dim=[16,56,56],
                    theta=10000, qkv_bias=True, guidance_embed=guidance, txt_ids_dims=[0,1,2])
        model_config = (comfy.supported_models.Flux if guidance else comfy.supported_models.FluxSchnell)(unet)
        model_config.custom_operations = comfy.ops.manual_cast
        model_config.set_inference_dtype(torch.bfloat16,torch.bfloat16)
        model = model_config.get_model({},device=torch.device('meta'))
        diffusion = model.diffusion_model
        keys = set(checkpoint.keys())
        consumed = set()
        quantized = []

        def linear(prefix, splits=None, gelu=False):
            names = {key for key in keys if key.startswith(prefix+'.')}
            aliases = dict(lora_down='proj_down',lora_up='proj_up',smooth='smooth_factor',smooth_orig='smooth_factor_orig')
            state = {aliases.get(key[len(prefix)+1:],key[len(prefix)+1:]):checkpoint.get_tensor(key) for key in names}
            if splits:
                if set(state) != {'qweight','wscales','wzeros','bias'}:
                    raise ValueError(f'Unexpected AWQ fields: {prefix}')
                layer = FoldedModulation(AMDAWQLinear(state,modulation=True,modulation_splits=splits,backend=backend),splits)
            else:
                if set(state) != {'qweight','wscales','proj_down','proj_up','smooth_factor','smooth_factor_orig','bias'}:
                    raise ValueError(f'Unexpected INT4 fields: {prefix}: {sorted(state)}')
                layer = AMDInt4Linear(state,backend=backend,activation_bits=activation_bits,
                                      unsigned=gelu,activation_shift=.171875 if gelu else 0)
                quantized.append(layer)
            consumed.update(names)
            return layer

        for index, block in enumerate(diffusion.double_blocks):
            prefix = f'transformer_blocks.{index}'
            block.img_mod.lin = linear(prefix+'.norm1.linear',splits=6)
            block.txt_mod.lin = linear(prefix+'.norm1_context.linear',splits=6)
            block.img_attn.qkv = linear(prefix+'.qkv_proj')
            block.txt_attn.qkv = linear(prefix+'.qkv_proj_context')
            block.img_attn.proj = linear(prefix+'.out_proj')
            block.txt_attn.proj = linear(prefix+'.out_proj_context')
            block.img_mlp[0] = linear(prefix+'.mlp_fc1')
            block.img_mlp[2] = linear(prefix+'.mlp_fc2',gelu=True)
            block.txt_mlp[0] = linear(prefix+'.mlp_context_fc1')
            block.txt_mlp[2] = linear(prefix+'.mlp_context_fc2',gelu=True)
        for index, block in enumerate(diffusion.single_blocks):
            prefix = f'single_transformer_blocks.{index}'
            block.modulation.lin = linear(prefix+'.norm.linear',splits=3)
            block.linear1 = ParallelInput(linear(prefix+'.qkv_proj'),linear(prefix+'.mlp_fc1'))
            block.linear2 = ParallelOutput(linear(prefix+'.out_proj'),linear(prefix+'.mlp_fc2',gelu=True))
        mapping = comfy.utils.flux_to_diffusers(unet)
        backbone = {}
        for key in keys-consumed:
            # Legacy Nunchaku norms omit the attn component.
            normalized = key
            for field in ('norm_q','norm_k','norm_added_q','norm_added_k'):
                normalized = normalized.replace('.'+field+'.','.attn.'+field+'.')
            target = mapping.get(normalized)
            value = checkpoint.get_tensor(key)
            if isinstance(target,tuple):
                target, slices, transform = target
                if slices is not None:
                    raise ValueError(f'Unexpected sliced backbone: {key}')
                value = transform(value)
            if not isinstance(target,str):
                raise ValueError(f'Unmapped FLUX tensor: {key}')
            backbone[target] = value
        missing,unexpected = diffusion.load_state_dict(backbone,strict=False,assign=True)
        expected = {name+'.'+field for name,module in diffusion.named_modules()
                    if isinstance(module,(AMDInt4Linear,AMDAWQLinear)) for field in module._buffers}
        if set(missing) != expected or unexpected:
            raise ValueError(f'Checkpoint mismatch: {set(missing)^expected}, {unexpected}')
        if any(t.is_meta for t in (*diffusion.parameters(),*diffusion.buffers())):
            raise ValueError('Uninitialized model tensor')
        resident = sum(t.numel()*t.element_size() for t in (*diffusion.parameters(),*diffusion.buffers()))
        cache = sum((m.proj_down.numel()+m.proj_up.numel()+m.smooth_factor.numel())*4 for m in quantized)
        model.eval().requires_grad_(False)
        patcher = comfy.model_patcher.ModelPatcher(model,load_device=management.get_torch_device(),offload_device=torch.device('cpu'),size=resident+cache)
        patcher.nunchaku_amd_info = dict(path=str(path),architecture='flux1',blocks=57,
                                       quantized_projections=len(quantized),weight_bits=4,activation_bits=activation_bits,
                                       backend=backend,resident_bytes=resident,runtime_cache_bytes=cache,
                                       guidance_embed=guidance,experimental=True)
        return patcher
