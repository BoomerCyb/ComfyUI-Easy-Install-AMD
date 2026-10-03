"""Native ComfyUI FLUX.2 Klein graph with packed Nunchaku AMD projections."""
import json
import torch
from safetensors import safe_open
if __package__:
    from .nunchaku_amd import AMDInt4Linear
    from .fp4 import AMDFP4Linear
    from .comfy_loader_flux import ParallelInput
else:
    from nunchaku_amd import AMDInt4Linear
    from fp4 import AMDFP4Linear
    from comfy_loader_flux import ParallelInput


class SplitOutput(torch.nn.Module):
    def __init__(self, attention, mlp, dim):
        super().__init__()
        self.attention, self.mlp, self.dim = attention, mlp, dim

    def forward(self, x):
        return self.attention(x[..., :self.dim]) + self.mlp(x[..., self.dim:])


def load_flux2(path, *, backend='triton', activation_bits=4):
    import comfy.model_management as management
    import comfy.model_patcher
    import comfy.ops
    import comfy.supported_models
    import comfy.utils
    if not torch.version.hip or not torch.cuda.is_available():
        raise RuntimeError('AMD ROCm is required')
    with safe_open(str(path), framework='pt', device='cpu') as checkpoint:
        metadata = checkpoint.metadata() or {}
        config = json.loads(metadata.get('config', '{}'))
        quant = json.loads(metadata.get('quantization_config', '{}'))
        if metadata.get('model_class') != 'NunchakuFlux2Transformer2DModel':
            raise ValueError('Expected a Nunchaku FLUX.2 checkpoint')
        weight = quant.get('weight', {})
        fp4 = weight.get('group_size') == 16
        if not fp4 and (weight.get('dtype'), weight.get('group_size')) != ('int4', 64):
            raise ValueError('Unsupported quantization')
        dim = config['num_attention_heads'] * config['attention_head_dim']
        unet = dict(image_model='flux2', in_channels=config['in_channels'],
                    out_channels=config.get('out_channels') or config['in_channels'], patch_size=1,
                    vec_in_dim=None, context_in_dim=config['joint_attention_dim'], hidden_size=dim,
                    mlp_ratio=config['mlp_ratio'], num_heads=config['num_attention_heads'],
                    depth=config['num_layers'], depth_single_blocks=config['num_single_layers'],
                    axes_dim=config['axes_dims_rope'], theta=config['rope_theta'], qkv_bias=False,
                    guidance_embed=config['guidance_embeds'], txt_ids_dims=[3], global_modulation=True,
                    mlp_silu_act=True, ops_bias=False, default_ref_method='index', ref_index_scale=10.0)
        model_config = comfy.supported_models.Flux2(unet)
        model_config.custom_operations = comfy.ops.manual_cast
        model_config.set_inference_dtype(torch.bfloat16, torch.bfloat16)
        model = model_config.get_model({}, device=torch.device('meta'))
        diffusion = model.diffusion_model
        keys, consumed, packed = set(checkpoint.keys()), set(), []

        def linear(prefix):
            names = {key for key in keys if key.startswith(prefix + '.')}
            state = {key[len(prefix)+1:]: checkpoint.get_tensor(key) for key in names}
            required = {'qweight', 'wscales', 'proj_down', 'proj_up', 'smooth_factor'}
            allowed = required | {'smooth_factor_orig', 'bias', 'wcscales', 'wtscale'}
            if not required <= state.keys() or state.keys() - allowed:
                raise ValueError(f'Unexpected projection fields: {prefix}: {state.keys()}')
            layer = (AMDFP4Linear if fp4 else AMDInt4Linear)(state, backend=backend, activation_bits=activation_bits)
            consumed.update(names)
            packed.append(layer)
            return layer

        for index, block in enumerate(diffusion.double_blocks):
            prefix = f'transformer_blocks.{index}'
            block.img_attn.qkv = linear(prefix + '.attn.to_qkv')
            block.txt_attn.qkv = linear(prefix + '.attn.to_added_qkv')
            block.img_attn.proj = linear(prefix + '.attn.to_out.0')
            block.txt_attn.proj = linear(prefix + '.attn.to_add_out')
            block.img_mlp[0] = linear(prefix + '.ff.linear_in')
            block.img_mlp[2] = linear(prefix + '.ff.linear_out')
            block.txt_mlp[0] = linear(prefix + '.ff_context.linear_in')
            block.txt_mlp[2] = linear(prefix + '.ff_context.linear_out')
        for index, block in enumerate(diffusion.single_blocks):
            prefix = f'single_transformer_blocks.{index}.attn'
            block.linear1 = ParallelInput(linear(prefix + '.qkv_proj'), linear(prefix + '.mlp_fc1'))
            block.linear2 = SplitOutput(linear(prefix + '.out_proj'), linear(prefix + '.mlp_fc2'), dim)
        mapping = comfy.utils.flux_to_diffusers(unet)
        backbone = {}
        for key in keys - consumed:
            target = mapping.get(key.replace('time_guidance_embed.', 'time_text_embed.'))
            if key.startswith(('double_stream_modulation_', 'single_stream_modulation.')):
                target = key.replace('.linear.', '.lin.')
            value = checkpoint.get_tensor(key)
            if isinstance(target, tuple):
                target, slices, transform = target
                if slices is not None:
                    raise ValueError(f'Unexpected sliced tensor {key}')
                value = transform(value)
            if not isinstance(target, str):
                raise ValueError(f'Unmapped FLUX.2 tensor {key}')
            backbone[target] = value
        missing, unexpected = diffusion.load_state_dict(backbone, strict=False, assign=True)
        expected = {name + '.' + field for name, module in diffusion.named_modules()
                    if isinstance(module, AMDInt4Linear) for field in module._buffers}
        if set(missing) != expected or unexpected:
            raise ValueError(f'FLUX.2 load mismatch: {set(missing)^expected}, {unexpected}')
        if any(value.is_meta for value in (*diffusion.parameters(), *diffusion.buffers())):
            raise ValueError('Uninitialized model tensor')
        model.eval().requires_grad_(False)
        resident = sum(t.numel()*t.element_size() for t in (*diffusion.parameters(), *diffusion.buffers()))
        cache = sum((m.proj_down.numel()+m.proj_up.numel()+m.smooth_factor.numel())*4 for m in packed)
        patcher = comfy.model_patcher.ModelPatcher(model, load_device=management.get_torch_device(),
                                                  offload_device=torch.device('cpu'), size=resident+cache)
        patcher.nunchaku_amd_info = dict(architecture='flux2', checkpoint=str(path), backend=backend,
                                       quantized_projections=len(packed), activation_bits=activation_bits,
                                       weight_format='fp4' if fp4 else 'int4', experimental=True)
        return patcher
