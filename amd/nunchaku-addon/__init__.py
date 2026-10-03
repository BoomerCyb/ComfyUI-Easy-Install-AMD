"""AMD Nunchaku model loaders for RX 9070 XT and diagnostic layer tests."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault('TRITON_CACHE_DIR', str(ROOT / '.cache/triton'))

_PROBED_GPUS = set()


def ensure_gpu(backend):
    import torch
    if not torch.version.hip or not torch.cuda.is_available():
        raise RuntimeError('ROCm PyTorch and an AMD GPU are required')
    device = torch.cuda.current_device()
    arch = torch.cuda.get_device_properties(device).gcnArchName
    key = (device, arch, backend)
    if key in _PROBED_GPUS:
        return
    name = torch.cuda.get_device_name(device)
    if not arch.startswith('gfx1201') or 'RX 9070 XT' not in name.upper():
        raise RuntimeError('Nunchaku AMD supports RX 9070 XT only. Selected GPU: '+name)
    _PROBED_GPUS.add(key)


class NunchakuAMDQwenLayerTest:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'backend': (['triton', 'torch'],),
            'tokens': ('INT', {'default': 37, 'min': 1, 'max': 256}),
            'activation_bits': (['4', '16'],),
            'test_seed': ('INT', {'default': 123, 'min': 0, 'max': 2147483647}),
        }}

    RETURN_TYPES = ('STRING',)
    RETURN_NAMES = ('test_report',)
    FUNCTION = 'test_layer'
    CATEGORY = 'Nunchaku AMD/RX 9070 XT only'
    OUTPUT_NODE = True
    DESCRIPTION = 'Tests one real Qwen-Image INT4 layer on AMD. Does not load a full model or generate an image.'

    def test_layer(self, backend, tokens, activation_bits, test_seed):
        import torch
        from safetensors.torch import load_file
        from .nunchaku_amd import AMDInt4Linear
        if not torch.version.hip or not torch.cuda.is_available():
            raise RuntimeError('Nunchaku AMD test requires ROCm PyTorch and an AMD GPU')
        if tokens < 1 or tokens > 256:
            raise ValueError('tokens must be between 1 and 256')
        device = torch.cuda.current_device()
        arch = torch.cuda.get_device_properties(device).gcnArchName
        with torch.inference_mode():
            state = {key: value.to(device=f'cuda:{device}') for key, value in
                     load_file(str(ROOT / 'fixtures/qwen-int4-layer.safetensors')).items()}
            generator = torch.Generator(device=f'cuda:{device}').manual_seed(test_seed)
            x = torch.randn(tokens, state['qweight'].shape[1] * 2,
                            dtype=torch.bfloat16, device=f'cuda:{device}', generator=generator)
            reference = AMDInt4Linear(state, backend='torch', activation_bits=int(activation_bits))(x)
            candidate = AMDInt4Linear(state, backend=backend, activation_bits=int(activation_bits))(x)
            torch.cuda.synchronize(device)
            if not torch.isfinite(candidate).all():
                raise RuntimeError('Layer produced nonfinite output')
            error = candidate.float() - reference.float()
            nrmse = (error.square().mean() / reference.float().square().mean().clamp_min(1e-12)).sqrt().item()
            if nrmse >= 0.003:
                raise RuntimeError(f'Layer comparison failed: normalized RMS error {nrmse}')
            receipt = json.loads((ROOT / 'fixtures/receipt.json').read_text(encoding='utf-8'))
            report = json.dumps({'status': 'PASS', 'gpu': torch.cuda.get_device_name(device),
                                 'architecture': arch, 'backend': backend, 'activation_bits': int(activation_bits),
                                 'layer': receipt['layer'], 'tokens': tokens, 'output_shape': list(candidate.shape),
                                 'normalized_rmse': nrmse, 'max_abs_error': error.abs().max().item(),
                                 'scope': 'Single Qwen INT4 layer comparison. Use the separate Qwen INT4 Loader workflow for generation.'}, indent=2)
        print('Nunchaku AMD layer test:', report, flush=True)
        return {'ui': {'text': [report]}, 'result': (report,)}


class NunchakuAMDQwenLoader:
    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        names = [name for name in folder_paths.get_filename_list('diffusion_models') if 'svdq-int4' in name.lower() and 'qwen' in name.lower()]
        return {'required': {'checkpoint_name': (names or ['Install the Qwen INT4 checkpoint through the Nunchaku add-on'],),
                             'backend': (['triton', 'torch'],), 'activation_bits': (['4', '16'],)}}

    RETURN_TYPES = ('MODEL',)
    RETURN_NAMES = ('model',)
    FUNCTION = 'load_model'
    CATEGORY = 'Nunchaku AMD/RX 9070 XT only'
    DESCRIPTION = 'Original Qwen-Image INT4 on AMD. Streams one block at a time. External LoRAs, attention patches and Qwen 2.1 are unsupported.'

    def load_model(self, checkpoint_name, backend, activation_bits):
        import folder_paths
        import torch
        from .comfy_loader import load_qwen
        ensure_gpu(backend)
        path = folder_paths.get_full_path_or_raise('diffusion_models', checkpoint_name)
        return (load_qwen(path, backend=backend, activation_bits=int(activation_bits)),)


class NunchakuAMDQwen21Loader(NunchakuAMDQwenLoader):
    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        names = [name for name in folder_paths.get_filename_list('diffusion_models') if 'qwen-image-2.1-int4' in name.lower()]
        return {'required': {'checkpoint_name': (names or ['Install the Qwen 2.1 Nunchaku INT4 checkpoint'],),
                             'backend': (['triton', 'torch'],), 'activation_bits': (['4', '16'],)}}
    DESCRIPTION = 'Qwen 2.1 Nunchaku signed INT4: 224 quantized projections, rank-128 SVD branches, AMD Triton. Use dedicated runtime Turbo adapter; standard LoRA merging is unsupported.'

    def load_model(self, checkpoint_name, backend, activation_bits):
        import folder_paths
        import torch
        from .comfy_loader21 import load_qwen21
        ensure_gpu(backend)
        return (load_qwen21(folder_paths.get_full_path_or_raise('diffusion_models', checkpoint_name),
                            backend=backend, activation_bits=int(activation_bits)),)


class NunchakuAMDQwen21EditEncode:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'clip': ('CLIP',), 'vae': ('VAE',), 'image': ('IMAGE',),
                             'prompt': ('STRING', {'multiline': True}),
                             'negative_prompt': ('STRING', {'multiline': True, 'default': ''}),
                             'resolution': ('INT', {'default':512,'min':32,'max':4096,'step':32})},
                'optional': {'image_2': ('IMAGE',), 'image_3': ('IMAGE',)}}
    RETURN_TYPES = ('CONDITIONING','CONDITIONING','LATENT')
    RETURN_NAMES = ('positive','negative','latent')
    FUNCTION = 'encode'
    CATEGORY = 'Nunchaku AMD/RX 9070 XT only'
    DESCRIPTION = 'Qwen 2.1 reference editing: encodes images through the vision encoder and VAE. Use the Qwen 2.1 INT4 loader.'

    def encode(self, clip, vae, image, prompt, negative_prompt, resolution, image_2=None, image_3=None):
        from comfy_extras.nodes_qwen import TextEncodeQwenImage21
        images = {name:value for name,value in (('image_1',image),('image_2',image_2),('image_3',image_3)) if value is not None}
        return tuple(TextEncodeQwenImage21.execute(clip,prompt,negative_prompt,vae=vae,
                                                   resolution=resolution,images=images).result)


class NunchakuAMDZImageLoader(NunchakuAMDQwenLoader):
    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        names = [name for name in folder_paths.get_filename_list('diffusion_models') if any(prefix in name.lower() for prefix in ('svdq-int4','svdq-fp4')) and 'z-image' in name.lower()]
        return {'required': {'checkpoint_name': (names or ['Install the Z-Image Turbo Nunchaku INT4 checkpoint'],),
                             'backend': (['triton','torch'],), 'activation_bits': (['4','16'],)}}
    DESCRIPTION = 'Z-Image Turbo INT4 or E2M1 FP4/FP8 scales: 136 packed projections and native ComfyUI attention. Software BF16 computation; tested on RX 9070 XT.'

    def load_model(self, checkpoint_name, backend, activation_bits):
        import folder_paths
        from .comfy_loader_zimage import load_zimage
        ensure_gpu(backend)
        return (load_zimage(folder_paths.get_full_path_or_raise('diffusion_models',checkpoint_name),
                            backend=backend,activation_bits=int(activation_bits)),)


class NunchakuAMDFluxLoader(NunchakuAMDQwenLoader):
    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        names = [name for name in folder_paths.get_filename_list('diffusion_models') if 'svdq-int4' in name.lower() and 'flux.1' in name.lower()]
        return {'required': {'checkpoint_name': (names or ['Install the FLUX.1 Schnell Nunchaku INT4 checkpoint'],),
                             'backend': (['triton','torch'],), 'activation_bits': (['4','16'],)}}
    DESCRIPTION = 'FLUX.1 signed INT4 and AWQ modulation. Schnell generation tested on RX 9070 XT; other variants are unverified.'

    def load_model(self, checkpoint_name, backend, activation_bits):
        import folder_paths
        from .comfy_loader_flux import load_flux
        ensure_gpu(backend)
        return (load_flux(folder_paths.get_full_path_or_raise('diffusion_models',checkpoint_name),
                          backend=backend,activation_bits=int(activation_bits)),)


from .turbo21 import NunchakuAMDQwen21TurboLoRA, NunchakuAMDQwen21TurboSigmas

NODE_CLASS_MAPPINGS = {'NunchakuAMDQwen21Loader': NunchakuAMDQwen21Loader,
                       'NunchakuAMDZImageLoader': NunchakuAMDZImageLoader,
                       'NunchakuAMDFluxLoader': NunchakuAMDFluxLoader,
                       'NunchakuAMDQwen21EditEncode': NunchakuAMDQwen21EditEncode,
                       'NunchakuAMDQwen21TurboLoRA': NunchakuAMDQwen21TurboLoRA,
                       'NunchakuAMDQwen21TurboSigmas': NunchakuAMDQwen21TurboSigmas,
                       'NunchakuAMDQwenLayerTest': NunchakuAMDQwenLayerTest,
                       'NunchakuAMDQwenLoader': NunchakuAMDQwenLoader}
NODE_DISPLAY_NAME_MAPPINGS = {'NunchakuAMDQwen21Loader': 'Nunchaku AMD — Qwen 2.1 INT4 Loader',
                              'NunchakuAMDZImageLoader': 'Nunchaku AMD — Z-Image Turbo INT4 / FP4 Loader',
                              'NunchakuAMDFluxLoader': 'Nunchaku AMD — FLUX.1 INT4 Loader',
                              'NunchakuAMDQwen21EditEncode': 'Nunchaku AMD — Qwen 2.1 Reference Edit',
                              'NunchakuAMDQwen21TurboLoRA': 'Nunchaku AMD — Qwen 2.1 Viggle Turbo',
                              'NunchakuAMDQwen21TurboSigmas': 'Nunchaku AMD — Qwen 2.1 Turbo Sigmas',
                              'NunchakuAMDQwenLayerTest': 'Nunchaku AMD — Qwen INT4 Layer Test',
                              'NunchakuAMDQwenLoader': 'Nunchaku AMD — Qwen INT4 Loader (RX 9070 XT only)'}
WEB_DIRECTORY = './web'

from .families import NODE_CLASS_MAPPINGS as FAMILY_NODES, NODE_DISPLAY_NAME_MAPPINGS as FAMILY_NAMES
NODE_CLASS_MAPPINGS.update(FAMILY_NODES)
NODE_DISPLAY_NAME_MAPPINGS.update(FAMILY_NAMES)
