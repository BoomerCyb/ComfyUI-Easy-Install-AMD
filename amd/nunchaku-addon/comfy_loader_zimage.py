"""Load the published Nunchaku Z-Image signed INT4 layout into ComfyUI."""
import json
import torch
from safetensors import safe_open
if __package__:
    from .nunchaku_amd import AMDInt4Linear
    from .fp4 import AMDFP4Linear
else:
    from nunchaku_amd import AMDInt4Linear
    from fp4 import AMDFP4Linear


class PackedSwiGLU(torch.nn.Module):
    def __init__(self, proj, out):
        super().__init__()
        self.proj, self.out = proj, out

    def forward(self, x):
        hidden, gate = self.proj(x).chunk(2, dim=-1)
        return self.out(hidden * torch.nn.functional.silu(gate))


def load_zimage(path, *, backend='triton', activation_bits=4):
    import comfy.model_management as management
    import comfy.model_patcher
    import comfy.ops
    import comfy.supported_models
    import comfy.utils
    if not torch.version.hip or not torch.cuda.is_available():
        raise RuntimeError('ROCm PyTorch and an AMD GPU are required')
    if backend not in ('torch', 'triton') or activation_bits not in (4, 16):
        raise ValueError('Expected torch/triton and 4/16 activation bits')
    with safe_open(str(path), framework='pt', device='cpu') as checkpoint:
        metadata = checkpoint.metadata() or {}
        config = json.loads(metadata.get('config', '{}'))
        quant = json.loads(metadata.get('quantization_config','{}'))
        weight_config = quant.get('weight',{})
        precision = weight_config.get('dtype')
        if (precision,weight_config.get('group_size')) not in (('int4',64),('fp4_e2m1_all',16)):
            raise ValueError('Only signed INT4/64 or E2M1 FP4/16 checkpoints are supported')
        fp4 = precision == 'fp4_e2m1_all'
        if metadata.get('model_class') != 'NunchakuZImageTransformer2DModel':
            raise ValueError('Expected a Nunchaku Z-Image checkpoint')
        if (config.get('dim'), config.get('n_layers'), config.get('n_refiner_layers'), config.get('cap_feat_dim')) != (3840, 30, 2, 2560):
            raise ValueError('Unsupported Z-Image architecture')
        unet = dict(image_model='lumina2', patch_size=2, in_channels=16, dim=3840,
                    n_layers=30, n_refiner_layers=2, n_heads=30, n_kv_heads=30,
                    multiple_of=256, ffn_dim_multiplier=8/3, norm_eps=1e-5,
                    qk_norm=True, cap_feat_dim=2560, axes_dims=[32,48,48],
                    axes_lens=[1536,512,512], rope_theta=256, z_image_modulation=True,
                    time_scale=1000, pad_tokens_multiple=32)
        model_config = comfy.supported_models.ZImage(unet)
        model_config.custom_operations = comfy.ops.manual_cast
        model_config.set_inference_dtype(torch.bfloat16, torch.bfloat16)
        model = model_config.get_model({}, device=torch.device('meta'))
        diffusion = model.diffusion_model
        keys = set(checkpoint.keys())
        consumed = set()
        quantized = []

        def linear(prefix):
            names = {key for key in keys if key.startswith(prefix+'.')}
            state = {key[len(prefix)+1:]: checkpoint.get_tensor(key) for key in names}
            required = {'qweight','wscales','proj_down','proj_up','smooth_factor','smooth_factor_orig'}
            extras = {'wcscales','wtscale'} if fp4 else set()
            if set(state)-extras != required or (fp4 and not set(state)&extras):
                raise ValueError(f'Unsupported quantization fields: {prefix}: {sorted(state)}')
            if state['qweight'].dtype != torch.int8:
                raise ValueError('Expected packed four-bit weights in int8 storage')
            layer = (AMDFP4Linear if fp4 else AMDInt4Linear)(state, backend=backend, activation_bits=activation_bits)
            layer.in_features = state['qweight'].shape[1]*2
            layer.out_features = state['qweight'].shape[0]
            consumed.update(names)
            quantized.append(layer)
            return layer

        for group, count in (('layers',30), ('noise_refiner',2), ('context_refiner',2)):
            for index in range(count):
                prefix = f'{group}.{index}'
                block = diffusion.get_submodule(prefix)
                block.attention.qkv = linear(prefix+'.attention.to_qkv')
                block.attention.out = linear(prefix+'.attention.to_out.0')
                block.feed_forward = PackedSwiGLU(linear(prefix+'.feed_forward.net.0.proj'),
                                                 linear(prefix+'.feed_forward.net.2'))
        mapping = comfy.utils.z_image_to_diffusers(unet)
        backbone = {}
        for key in keys-consumed:
            target = mapping.get(key)
            if not isinstance(target, str):
                raise ValueError(f'Unmapped Z-Image tensor: {key}')
            backbone[target] = checkpoint.get_tensor(key)
        missing, unexpected = diffusion.load_state_dict(backbone, strict=False, assign=True)
        expected = {name+'.'+field for name, module in diffusion.named_modules()
                    if isinstance(module, AMDInt4Linear)
                    for field in module._buffers}
        if set(missing) != expected or unexpected:
            raise ValueError(f'Checkpoint mismatch: {set(missing)^expected}, {unexpected}')
        if any(t.is_meta for t in (*diffusion.parameters(), *diffusion.buffers())):
            raise ValueError('Uninitialized model tensor')
        resident = sum(t.numel()*t.element_size() for t in (*diffusion.parameters(), *diffusion.buffers()))
        cache = sum((m.proj_down.numel()+m.proj_up.numel()+m.smooth_factor.numel())*4 for m in quantized)
        model.eval().requires_grad_(False)
        patcher = comfy.model_patcher.ModelPatcher(model, load_device=management.get_torch_device(),
                                                  offload_device=torch.device('cpu'), size=resident+cache)
        patcher.nunchaku_amd_info = dict(path=str(path), architecture='z_image', blocks=34,
                                      quantized_projections=136, weight_bits=4, activation_bits=activation_bits,
                                      backend=backend, resident_bytes=resident, runtime_cache_bytes=cache,
                                      precision='fp4_e2m1_fp8_scales' if fp4 else 'int4',
                                      experimental=True)
        return patcher
