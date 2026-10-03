"""Fetch original Qwen INT4 plus its matching encoder from pinned sources."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
MODELS = [
    ('diffusion_models/nunchaku/svdq-int4_r32-qwen-image.safetensors', 11521979944,
     'https://huggingface.co/nunchaku-ai/nunchaku-qwen-image/resolve/4d9f4f667ea571ab172e0ee29ac2c27b82a41a6b/svdq-int4_r32-qwen-image.safetensors?download=true'),
    ('text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors', 9384670680,
     'https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/7beb7b647f04469fbe64ba8adc2bb0d7e5e9f73f/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors?download=true'),
    ('vae/qwen_image_vae.safetensors', None,
     'https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/7beb7b647f04469fbe64ba8adc2bb0d7e5e9f73f/split_files/vae/qwen_image_vae.safetensors?download=true'),
]


def main():
    from safetensors import safe_open
    print(f'Model set needs about {sum(size or 0 for _, size, _ in MODELS)/1e9:.1f} GB when not already installed (plus any VAE with unspecified size).', flush=True)
    for relative, expected, url in MODELS:
        target = ROOT / 'ComfyUI/models' / relative
        if not target.resolve().is_relative_to(ROOT):
            raise ValueError('Model target is outside the installation root')
        if target.exists():
            if expected is not None and target.stat().st_size != expected:
                raise RuntimeError(f'Existing model has an unexpected size; preserving it: {target}')
            with safe_open(str(target), framework='pt') as model:
                if not list(model.keys()):
                    raise RuntimeError(f'Model contains no tensors: {target}')
            print('Already installed:', target, flush=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix('.safetensors.part')
        subprocess.run(['curl.exe', '-L', '--fail', '--retry', '3', '--continue-at', '-', '-o', str(partial), url], check=True)
        if expected is not None and partial.stat().st_size != expected:
            raise RuntimeError(f'Download size mismatch: {partial}')
        with safe_open(str(partial), framework='pt') as model:
            if not list(model.keys()):
                raise RuntimeError('Downloaded model contains no tensors')
        partial.rename(target)


if __name__ == '__main__':
    main()
