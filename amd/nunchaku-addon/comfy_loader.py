"""Experimental ComfyUI MODEL loader for original Nunchaku Qwen-Image INT4."""
import json
from pathlib import Path
import torch
from safetensors import safe_open
if __package__:
    from .qwen_block import AMDQwenBlock
else:
    from qwen_block import AMDQwenBlock


class AMDStreamingBlock(AMDQwenBlock):
    """Keep checkpoint tensors in system RAM; stage only the active block."""
    def _apply(self, fn, recurse=True):
        # Parent model transfers must not put all 60 blocks into VRAM.
        return self

    @torch.inference_mode()
    def forward(self, hidden_states, *args, **kwargs):
        saved = [(module, dict(module._buffers)) for module in self.modules()]
        try:
            for module, buffers in saved:
                for name, value in buffers.items():
                    if value is not None:
                        module._buffers[name] = value.to(hidden_states.device)
            return super().forward(hidden_states, *args, **kwargs)
        finally:
            # Restore original CPU tensors instead of copying immutable weights
            # back over PCIe. This also rolls back a partially failed transfer.
            for module, buffers in saved:
                module._buffers.update(buffers)
                if hasattr(module, 'clear_runtime_cache'):
                    module.clear_runtime_cache()


def load_qwen(path, *, backend='triton', activation_bits=4):
    import comfy.model_management as management
    import comfy.model_patcher
    import comfy.ops
    import comfy.supported_models
    if not torch.version.hip or not torch.cuda.is_available():
        raise RuntimeError('ROCm PyTorch and an AMD GPU are required')
    path = Path(path)
    with safe_open(str(path), framework='pt', device='cpu') as checkpoint:
        metadata = checkpoint.metadata() or {}
        config = json.loads(metadata.get('config', '{}'))
        quant = json.loads(metadata.get('quantization_config', '{}'))
        if metadata.get('model_class') != 'NunchakuQwenImageTransformer2DModel':
            raise ValueError('Expected an original Nunchaku Qwen-Image checkpoint')
        if quant.get('weight', {}).get('dtype') != 'int4' or quant.get('weight', {}).get('group_size') != 64:
            raise ValueError('Only signed INT4 group-size-64 checkpoints are supported')
        if (config.get('num_attention_heads'), config.get('attention_head_dim'), config.get('joint_attention_dim')) != (24, 128, 3584):
            raise ValueError('This loader supports original Qwen-Image T2I, not Qwen-Image 2.1')
        unet = {name: config[name] for name in ('patch_size', 'in_channels', 'out_channels',
                'attention_head_dim', 'num_attention_heads', 'joint_attention_dim',
                'pooled_projection_dim', 'axes_dims_rope')}
        unet['num_layers'] = 0
        unet['image_model'] = 'qwen_image'
        model_config = comfy.supported_models.QwenImage(unet)
        model_config.custom_operations = comfy.ops.manual_cast
        model_config.set_inference_dtype(torch.bfloat16, torch.bfloat16)
        model = model_config.get_model({}, device=torch.device('meta'))
        diffusion = model.diffusion_model
        keys = list(checkpoint.keys())
        backbone = {key: checkpoint.get_tensor(key) for key in keys if not key.startswith('transformer_blocks.')}
        missing, unexpected = diffusion.load_state_dict(backbone, strict=False, assign=True)
        if missing or unexpected:
            raise ValueError(f'Backbone checkpoint mismatch: missing={missing}, unexpected={unexpected}')
        layers = int(config['num_layers'])
        blocks = []
        largest = 0
        for index in range(layers):
            prefix = f'transformer_blocks.{index}.'
            state = {key[len(prefix):]: checkpoint.get_tensor(key) for key in keys if key.startswith(prefix)}
            if not state:
                raise ValueError(f'Checkpoint is missing block {index}; single-layer fixtures are not complete models')
            largest = max(largest, sum(value.numel() * value.element_size() for value in state.values()))
            blocks.append(AMDStreamingBlock(state, backend=backend, activation_bits=activation_bits, heads=24))
        diffusion.transformer_blocks = torch.nn.ModuleList(blocks)
        model.model_config.unet_config['num_layers'] = layers
        model.eval().requires_grad_(False)
        backbone_size = sum(value.numel() * value.element_size() for value in backbone.values())
        # Account for the backbone, active block, dequantization tiles and scratch.
        effective_resident_size = backbone_size + largest * 2 + 256 * 1024**2
        patcher = comfy.model_patcher.ModelPatcher(model, load_device=management.get_torch_device(),
                                                  offload_device=torch.device('cpu'), size=effective_resident_size)
        patcher.nunchaku_amd_info = {'path': str(path), 'blocks': layers, 'backend': backend,
                                    'activation_bits': activation_bits, 'offload': 'one block at a time',
                                    'experimental': True}
        return patcher
