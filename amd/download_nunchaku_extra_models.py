"""Pinned model downloads for the tested AMD FLUX/Z-Image INT4 adapters."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import download_nunchaku_models as downloader

VAE = ('vae/ae.safetensors',335304388,
       'https://huggingface.co/Comfy-Org/z_image_turbo/resolve/6fc90a3b1b653e935a0d175e260736de25b84df5/split_files/vae/ae.safetensors?download=true')
SETS = {
    'zimage': [
        ('diffusion_models/nunchaku/svdq-int4_r128-z-image-turbo.safetensors',4011374152,
         'https://huggingface.co/nunchaku-tech/nunchaku-z-image-turbo/resolve/ca6bac69c3b0b2bdd31ca5196bf87c5f2a9eaedf/svdq-int4_r128-z-image-turbo.safetensors?download=true'),
        ('text_encoders/qwen_3_4b_fp8_mixed.safetensors',5631994051,
         'https://huggingface.co/Comfy-Org/z_image_turbo/resolve/6fc90a3b1b653e935a0d175e260736de25b84df5/split_files/text_encoders/qwen_3_4b_fp8_mixed.safetensors?download=true'),VAE],
    'flux': [
        ('diffusion_models/nunchaku/svdq-int4_r32-flux.1-schnell.safetensors',6747849760,
         'https://huggingface.co/nunchaku-tech/nunchaku-flux.1-schnell/resolve/b18e8e6333da55835f6ce16c04b13c543c0954b1/svdq-int4_r32-flux.1-schnell.safetensors?download=true'),
        ('text_encoders/clip_l.safetensors',246144152,
         'https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/753bc0d550cce75eb3c964eb1e43973b9391451a/clip_l.safetensors?download=true'),
        ('text_encoders/t5xxl_fp8_e4m3fn.safetensors',4893934904,
         'https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/753bc0d550cce75eb3c964eb1e43973b9391451a/t5xxl_fp8_e4m3fn.safetensors?download=true'),VAE],
}
SETS['zimage-fp4'] = [
    ('diffusion_models/nunchaku/svdq-fp4_r128-z-image-turbo.safetensors',4200179380,
     'https://huggingface.co/nunchaku-tech/nunchaku-z-image-turbo/resolve/ca6bac69c3b0b2bdd31ca5196bf87c5f2a9eaedf/svdq-fp4_r128-z-image-turbo.safetensors?download=true'),
    *SETS['zimage'][1:],
]

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('family',choices=SETS)
    downloader.MODELS = SETS[parser.parse_args().family]
    downloader.main()
