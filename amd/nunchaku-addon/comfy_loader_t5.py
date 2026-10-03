"""Nunchaku TinyChat AWQ T5-XXL in the native ComfyUI FLUX CLIP interface."""
import json
import torch
from safetensors import safe_open
if __package__:
    from .awq import AMDAWQLinear
else:
    from awq import AMDAWQLinear


def load_t5(path, *, backend='triton'):
    import comfy.ops
    from comfy.text_encoders.t5 import T5
    with safe_open(str(path), framework='pt',device='cpu') as checkpoint:
        metadata = checkpoint.metadata() or {}
        if metadata.get('model_class') != 'NunchakuT5EncoderModel':
            raise ValueError('Expected the Nunchaku AWQ T5 encoder')
        config = json.loads(metadata['config'])
        if config.get('dense_act_fn') == 'gelu_new':
            config['dense_act_fn'] = 'gelu_pytorch_tanh'
        model = T5(config,torch.bfloat16,torch.device('meta'),comfy.ops.manual_cast)
        keys, consumed = set(checkpoint.keys()), set()
        projections = 0
        for key in sorted(keys):
            if not key.endswith('.qweight'):
                continue
            prefix = key[:-8]
            original = model.get_submodule(prefix)
            qweight = checkpoint.get_tensor(key)
            if qweight.dtype != torch.int16:
                raise ValueError('Expected TinyChat int16 packing')
            scales = checkpoint.get_tensor(prefix+'.scales')
            zeros = checkpoint.get_tensor(prefix+'.scaled_zeros')
            groups = original.in_features//128
            if qweight.shape != (original.out_features//4,original.in_features) or scales.shape[1] != original.out_features:
                raise ValueError(f'AWQ shape mismatch: {prefix}')
            # Replication preserves group-128 quantization with the group-64 kernel.
            state = dict(qweight=qweight.contiguous().view(torch.int32),
                         wscales=scales[:groups].repeat_interleave(2,dim=0),
                         wzeros=zeros[:groups].repeat_interleave(2,dim=0))
            layer = AMDAWQLinear(state,backend=backend)
            parent, name = prefix.rsplit('.',1)
            setattr(model.get_submodule(parent),name,layer)
            consumed.update((key,prefix+'.scales',prefix+'.scaled_zeros'))
            projections += 1
        state = {key:checkpoint.get_tensor(key) for key in keys-consumed}
        # Transformers ties encoder.embed_tokens to shared; native ComfyUI has only shared.
        if 'encoder.embed_tokens.weight' in state:
            if 'shared.weight' not in state:
                state['shared.weight'] = state['encoder.embed_tokens.weight']
            elif not torch.equal(state['shared.weight'],state['encoder.embed_tokens.weight']):
                raise ValueError('Tied T5 embeddings disagree')
            state.pop('encoder.embed_tokens.weight')
        missing,unexpected = model.load_state_dict(state,strict=False,assign=True)
        expected = {name+'.'+field for name,module in model.named_modules()
                    if isinstance(module,AMDAWQLinear) for field in module._buffers}
        if set(missing) != expected or unexpected:
            raise ValueError(f'T5 load mismatch: {set(missing)^expected}, {unexpected}')
        if any(t.is_meta for t in (*model.parameters(),*model.buffers())):
            raise ValueError('Uninitialized T5 tensor')
        model.eval().requires_grad_(False)
        model.nunchaku_amd_info = dict(architecture='t5-xxl',quantized_projections=projections,
                                      weight_bits=4,activation_bits=16,group_size=128,backend=backend,experimental=True)
        return model


def load_flux_clip(t5_path, clip_l_path, *, backend='triton'):
    import comfy.sd
    import comfy.utils
    import comfy.sd1_clip
    from comfy.text_encoders.flux import FluxClipModel,FluxTokenizer
    from comfy.text_encoders.sd3_clip import T5XXLModel
    from comfy.supported_models_base import ClipTarget
    packed = load_t5(t5_path,backend=backend)

    class PackedFluxClip(FluxClipModel):
        def __init__(self,device='cpu',dtype=None,model_options=None):
            torch.nn.Module.__init__(self)
            options = model_options or {}
            self.clip_l = comfy.sd1_clip.SDClipModel(device='cpu',dtype=torch.bfloat16,
                                                    return_projected_pooled=False,model_options=options)
            self.t5xxl = T5XXLModel(device='meta',dtype=torch.bfloat16,model_options=options)
            self.t5xxl.transformer = packed
            self.dtypes = {torch.bfloat16}

    target = ClipTarget(FluxTokenizer,PackedFluxClip)
    clip = comfy.sd.CLIP(target,model_options={'initial_device':torch.device('cpu'),'dtype':torch.bfloat16},disable_dynamic=True)
    state = comfy.utils.load_torch_file(str(clip_l_path))
    missing,unexpected = clip.cond_stage_model.clip_l.load_sd(state)
    unexpected = [name for name in unexpected if name != 'text_model.embeddings.position_ids']
    missing = [name for name in missing if name not in ('text_projection.weight','logit_scale')]
    if missing or unexpected:
        raise ValueError(f'CLIP-L mismatch: {missing}, {unexpected}')
    return clip
