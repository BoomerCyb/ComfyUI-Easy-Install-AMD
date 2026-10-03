"""Native ComfyUI SDXL UNet with Nunchaku packed INT4 projections."""
import json
import torch
import torch.nn.functional as F
from safetensors import safe_open
if __package__:
    from .nunchaku_amd import AMDInt4Linear
else:
    from nunchaku_amd import AMDInt4Linear


class PackedSelfAttention(torch.nn.Module):
    def __init__(self, qkv, output, heads):
        super().__init__()
        self.qkv, self.to_out, self.heads = qkv, output, heads

    def forward(self, x, context=None, value=None, mask=None, transformer_options=None):
        if context is not None or value is not None:
            raise ValueError('Packed self-attention requires the original self-attention inputs')
        q, k, v = self.qkv(x).chunk(3, dim=-1)
        b, tokens, dim = q.shape
        q, k, v = [t.reshape(b, tokens, self.heads, dim//self.heads).transpose(1,2) for t in (q,k,v)]
        result = F.scaled_dot_product_attention(q,k,v,attn_mask=mask)
        return self.to_out(result.transpose(1,2).reshape(b,tokens,dim))


def load_sdxl(path, *, backend='triton', activation_bits=4):
    import comfy.model_detection
    import comfy.model_management as management
    import comfy.model_patcher
    import comfy.ops
    import comfy.utils
    if not torch.version.hip or not torch.cuda.is_available():
        raise RuntimeError('AMD ROCm is required')
    with safe_open(str(path), framework='pt', device='cpu') as checkpoint:
        metadata = checkpoint.metadata() or {}
        config = json.loads(metadata.get('config','{}'))
        quant = json.loads(metadata.get('quantization_config','{}'))
        if config.get('_class_name') != 'UNet2DConditionModel' or config.get('cross_attention_dim') != 2048:
            raise ValueError('Expected an SDXL Nunchaku checkpoint')
        if (quant.get('weight',{}).get('dtype'), quant.get('weight',{}).get('group_size')) != ('int4',64):
            raise ValueError('Expected signed INT4 group-size-64 weights')
        keys = set(checkpoint.keys())
        # Detection only needs tensor shapes and key names; avoid allocating a dense UNet.
        shapes = {key: torch.empty(checkpoint.get_slice(key).get_shape(),device='meta') for key in keys}
        model_config = comfy.model_detection.model_config_from_diffusers_unet(shapes)
        if model_config is None:
            raise ValueError('Unsupported SDXL architecture')
        model_config.custom_operations = comfy.ops.manual_cast
        model_config.set_inference_dtype(torch.bfloat16,torch.bfloat16)
        model = model_config.get_model({},device=torch.device('meta'))
        diffusion = model.diffusion_model
        mapping = comfy.utils.unet_to_diffusers(model_config.unet_config)
        consumed, packed = set(), []
        aliases = dict(lora_down='proj_down',lora_up='proj_up',smooth='smooth_factor',smooth_orig='smooth_factor_orig')

        def linear(prefix):
            names = {key for key in keys if key.startswith(prefix+'.')}
            state = {aliases.get(key[len(prefix)+1:],key[len(prefix)+1:]):checkpoint.get_tensor(key) for key in names}
            required = {'qweight','wscales','proj_down','proj_up','smooth_factor'}
            if not required <= state.keys() or state.keys()-required-{'smooth_factor_orig','bias'}:
                raise ValueError(f'Unexpected projection fields {prefix}')
            layer = AMDInt4Linear(state,backend=backend,activation_bits=activation_bits)
            consumed.update(names)
            packed.append(layer)
            return layer

        prefixes = sorted((key[:-8] for key in keys if key.endswith('.qweight')),
                          key=lambda prefix: (not prefix.endswith('.attn1.to_qkv'),prefix))
        for prefix in prefixes:
            if prefix+'.qweight' in consumed:
                continue
            if prefix.endswith('.attn1.to_qkv'):
                target = mapping[prefix.replace('.to_qkv','.to_q')+'.weight'].rsplit('.to_q.weight',1)[0]
                parent_name, child = target.rsplit('.',1)
                original = diffusion.get_submodule(target)
                output = torch.nn.Sequential(linear(prefix.rsplit('.',1)[0]+'.to_out.0'))
                setattr(diffusion.get_submodule(parent_name),child,PackedSelfAttention(linear(prefix),output,original.heads))
            else:
                target = mapping[prefix+'.weight'].rsplit('.weight',1)[0]
                parent_name, child = target.rsplit('.',1)
                setattr(diffusion.get_submodule(parent_name),child,linear(prefix))
        backbone = {}
        for key in keys-consumed:
            target = mapping.get(key)
            if target is None:
                raise ValueError(f'Unmapped SDXL tensor: {key}')
            backbone[target] = checkpoint.get_tensor(key)
        missing, unexpected = diffusion.load_state_dict(backbone,strict=False,assign=True)
        expected = {name+'.'+field for name,module in diffusion.named_modules()
                    if isinstance(module,AMDInt4Linear) for field in module._buffers}
        if set(missing) != expected or unexpected:
            raise ValueError(f'SDXL load mismatch: {set(missing)^expected}, {unexpected}')
        if any(value.is_meta for value in (*diffusion.parameters(),*diffusion.buffers())):
            raise ValueError('Uninitialized model tensor')
        model.eval().requires_grad_(False)
        resident = sum(t.numel()*t.element_size() for t in (*diffusion.parameters(),*diffusion.buffers()))
        cache = sum((m.proj_down.numel()+m.proj_up.numel()+m.smooth_factor.numel())*4 for m in packed)
        patcher = comfy.model_patcher.ModelPatcher(model,load_device=management.get_torch_device(),
                                                  offload_device=torch.device('cpu'),size=resident+cache)
        patcher.nunchaku_amd_info = dict(architecture='sdxl',checkpoint=str(path),backend=backend,
                                       quantized_projections=len(packed),activation_bits=activation_bits,experimental=True)
        return patcher
