"""Qwen 2.1 Nunchaku SVDQ INT4 checkpoint loader for the AMD Triton backend."""
import json
from pathlib import Path
import re
import torch
from safetensors import safe_open
if __package__:
    from .nunchaku_amd import AMDInt4Linear
else:
    from nunchaku_amd import AMDInt4Linear

FORMAT = 'qwen21-nunchaku-svdq-int4-v1'
PATTERN = re.compile(r'transformer_blocks\.(\d+)\.(attn\.(to_q|to_k|to_v|to_out\.0)|img_mlp\.(proj|gate_layer|out))')


def load_qwen21(path, *, backend='triton', activation_bits=4):
    import comfy.model_management as management
    import comfy.model_patcher
    import comfy.ops
    import comfy.supported_models
    if not torch.version.hip or not torch.cuda.is_available():
        raise RuntimeError('ROCm PyTorch and an AMD GPU are required')
    if backend not in ('torch', 'triton') or activation_bits not in (4, 16):
        raise ValueError('Expected torch/triton backend and 4/16 activation bits')
    path = Path(path)
    with safe_open(str(path), framework='pt', device='cpu') as checkpoint:
        meta = checkpoint.metadata() or {}
        config = json.loads(meta.get('config', '{}'))
        manifest = json.loads(meta.get('manifest', '{}'))
        layers = manifest.get('layers', {})
        if manifest.get('backend_format') != FORMAT or manifest.get('complete') is not True:
            raise ValueError('Expected Mesmer Qwen 2.1 Nunchaku signed INT4 v1; BF16/INT8/NVFP4 files are unsupported here')
        if len(layers) != 224 or any(not PATTERN.fullmatch(name) for name in layers):
            raise ValueError('Expected exactly 224 Qwen 2.1 Nunchaku projection layers')
        if (config.get('num_layers'), config.get('num_attention_heads'), config.get('attention_head_dim'), config.get('context_in_dim')) != (32, 32, 128, 4096):
            raise ValueError('Unexpected Qwen 2.1 architecture')
        unet = {key: config[key] for key in ('in_channels', 'out_channels', 'num_layers', 'attention_head_dim',
                 'num_attention_heads', 'context_in_dim', 'mlp_ratio', 'axes_dims_rope', 'eps')}
        unet.update(image_model='qwen_image21', fused_mlp=False)
        model_config = comfy.supported_models.QwenImage21(unet)
        model_config.custom_operations = comfy.ops.manual_cast
        model_config.set_inference_dtype(torch.bfloat16, torch.bfloat16)
        model = model_config.get_model({}, device=torch.device('meta'))
        diffusion = model.diffusion_model
        keys = list(checkpoint.keys())
        quant_keys = set()
        total_bytes = 0
        for name, info in layers.items():
            if info.get('precision') != 'int4' or info.get('rank') != 128 or info.get('bias'):
                raise ValueError(f'Unexpected INT4 layer contract: {name}')
            parent_name, _, child = name.rpartition('.')
            parent = diffusion.get_submodule(parent_name)
            original = parent.get_submodule(child)
            if (original.in_features, original.out_features) != (info['in_features'], info['out_features']):
                raise ValueError(f'Checkpoint dimension mismatch: {name}')
            prefix = name + '.'
            state = {key[len(prefix):]: checkpoint.get_tensor(key) for key in keys if key.startswith(prefix)}
            required = {'qweight', 'wscales', 'proj_down', 'proj_up', 'smooth_factor', 'smooth_factor_orig'}
            if set(state) != required:
                raise ValueError(f'Unexpected layer tensors: {name}: {sorted(state)}')
            n, k = info['out_features'], info['in_features']
            if state['qweight'].dtype != torch.int8 or state['qweight'].shape != (n, k//2) or state['wscales'].shape != (k//64, n):
                raise ValueError(f'Unexpected packed weight/scale shape: {name}')
            layer = AMDInt4Linear(state, backend=backend, activation_bits=activation_bits)
            layer.in_features, layer.out_features = k, n
            parent._modules[child] = layer
            quant_keys.update(key for key in keys if key.startswith(prefix))
            total_bytes += sum(value.numel()*value.element_size() for key,value in state.items() if key != 'smooth_factor_orig')
        backbone = {key: checkpoint.get_tensor(key) for key in keys if key not in quant_keys}
        missing, unexpected = diffusion.load_state_dict(backbone, strict=False, assign=True)
        expected_missing = {name+'.'+field for name in layers for field in ('qweight','wscales','proj_down','proj_up','smooth_factor')}
        if set(missing) != expected_missing or unexpected:
            raise ValueError(f'Checkpoint mismatch: unexpected={unexpected}, missing difference={set(missing)^expected_missing}')
        if any(tensor.is_meta for tensor in (*diffusion.parameters(), *diffusion.buffers())):
            raise ValueError('Uninitialized model tensor')
        total_bytes += sum(value.numel()*value.element_size() for value in backbone.values())
        runtime_cache_bytes = sum((module.proj_down.numel()+module.proj_up.numel()+module.smooth_factor.numel())*4
                                  for module in diffusion.modules() if isinstance(module, AMDInt4Linear))
        model.eval().requires_grad_(False)
        # Start with full prefix computation; cache quantized projections separately later.
        diffusion.prefix_cache_enabled = False
        patcher = comfy.model_patcher.ModelPatcher(model, load_device=management.get_torch_device(),
                                                  offload_device=torch.device('cpu'), size=total_bytes+runtime_cache_bytes)
        patcher.nunchaku_amd_info = {'path': str(path), 'architecture': 'qwen_image21', 'blocks': 32,
                                    'quantized_projections': 224, 'weight_bits': 4, 'activation_bits': activation_bits,
                                    'svd_rank': 128, 'backend': backend, 'resident_bytes': total_bytes,
                                    'runtime_cache_bytes': runtime_cache_bytes,
                                    'checkpoint_format': FORMAT, 'experimental': True}
        return patcher
