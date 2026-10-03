"""Runtime Viggle adapters and six-step schedule for the AMD INT4 Qwen 2.1 model."""
import json
import math
import torch
import torch.nn.functional as F


def with_turbo_branches(branches, executor, *args, **kwargs):
    model = executor.class_obj
    hooks = []
    try:
        for name, pair in branches.items():
            down, up = (value.to(device=args[0].device, dtype=args[0].dtype) for value in pair)
            def add_branch(module, inputs, output, down=down, up=up):
                return output + F.linear(F.linear(inputs[0], down), up)
            hooks.append(model.get_submodule(name).register_forward_hook(add_branch))
        return executor(*args, **kwargs)
    finally:
        for hook in hooks:
            hook.remove()


class NunchakuAMDQwen21TurboLoRA:
    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        names = [name for name in folder_paths.get_filename_list('loras') if 'viggle' in name.lower() and 'v0.3-6step' in name.lower()]
        return {'required': {'model': ('MODEL',), 'lora_name': (names or ['Install Viggle v0.3 six-step LoRA'],),
                             'strength': ('FLOAT', {'default': 1.0, 'min': 0.0, 'max': 2.0, 'step': .05})}}
    RETURN_TYPES = ('MODEL',)
    FUNCTION = 'load'
    CATEGORY = 'Nunchaku AMD/Experimental'
    DESCRIPTION = 'Adds Viggle v0.3 Turbo as runtime branches on the Qwen 2.1 Nunchaku INT4 model; keeps INT4 weights compressed.'

    def load(self, model, lora_name, strength):
        import comfy.patcher_extension
        import comfy.utils
        import folder_paths
        from .nunchaku_amd import AMDInt4Linear
        if getattr(model, 'nunchaku_amd_info', {}).get('architecture') != 'qwen_image21':
            raise ValueError('Use the Nunchaku AMD Qwen 2.1 INT4 loader')
        sd, metadata = comfy.utils.load_torch_file(folder_paths.get_full_path_or_raise('loras', lora_name), return_metadata=True)
        config = json.loads((metadata or {}).get('lora_adapter_metadata', '{}'))
        scale = strength * config.get('transformer.lora_alpha', 1) / config.get('transformer.r', 1)
        branches = {name.removeprefix('transformer.').removesuffix('.lora_A.weight'):
                    (value, sd[name.replace('lora_A', 'lora_B')] * scale)
                    for name, value in sd.items() if name.endswith('.lora_A.weight')}
        if not branches:
            raise ValueError('No compatible LoRA branches found')
        for name, (down, up) in branches.items():
            layer = model.model.diffusion_model.get_submodule(name)
            # The adapter also targets boundary linears such as shared modulation;
            # those stay BF16 in the Nunchaku checkpoint itself.
            if not isinstance(layer, (AMDInt4Linear, torch.nn.Linear)) or down.shape[1] != layer.in_features or up.shape[0] != layer.out_features or down.shape[0] != up.shape[1]:
                raise ValueError(f'LoRA branch does not match the INT4 model: {name}')
        cloned = model.clone()
        cloned.nunchaku_amd_info = dict(model.nunchaku_amd_info, turbo_lora=lora_name, turbo_strength=strength)
        cloned.add_wrapper_with_key(comfy.patcher_extension.WrappersMP.DIFFUSION_MODEL, 'amd_qwen21_viggle',
                                    lambda executor, *args, **kwargs: with_turbo_branches(branches, executor, *args, **kwargs))
        return (cloned,)


class NunchakuAMDQwen21TurboSigmas:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'latent': ('LATENT',)}}
    RETURN_TYPES = ('SIGMAS',)
    FUNCTION = 'get_sigmas'
    CATEGORY = 'Nunchaku AMD/Experimental'
    DESCRIPTION = 'Viggle v0.3 six-step schedule with resolution-dependent shift. Use Euler and CFG 1.'

    def get_sigmas(self, latent):
        ratio = latent.get('downscale_ratio_spacial', 16) / 16
        samples = latent['samples']
        tokens = round(samples.shape[-2] * ratio) * round(samples.shape[-1] * ratio)
        mu = .5 + .4 * (tokens - 256) / (8192 - 256)
        raw = torch.tensor([1, .9375, .875, .75, .5, .25], dtype=torch.float64)
        shifted = math.exp(mu) / (math.exp(mu) + 1 / raw - 1)
        return (torch.cat((shifted, shifted.new_zeros(1))).float(),)
