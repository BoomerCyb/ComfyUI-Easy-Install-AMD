"""Install the tested Qwen 2.1 Nunchaku INT4 model set, including Turbo."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import download_nunchaku_models as downloader

downloader.MODELS = [
    ('diffusion_models/nunchaku/qwen-image-2.1-int4-r128.safetensors', 4655402112,
     'https://huggingface.co/mesmertech/Mesmer-Image-21-Nunchaku/resolve/868fc8b147de20f2c6e6835b694b2c4d9de9b5a6/qwen-image-2.1-int4-r128.safetensors?download=true'),
    ('text_encoders/qwen3vl_8b_int8_convrot.safetensors', 9350798360,
     'https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/cb504a4090723e43f17ad01cec0359490e2de613/text_encoders/qwen3vl_8b_int8_convrot.safetensors?download=true'),
    ('vae/qwen_image_2.1_vae_bf16.safetensors', 675509688,
     'https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/cb504a4090723e43f17ad01cec0359490e2de613/vae/qwen_image_2.1_vae_bf16.safetensors?download=true'),
    ('loras/qwen/Qwen-Image-2.1-viggle-turbo-v0.3-6step-lora-r128.safetensors', 679604800,
     'https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo/resolve/009a44a895ef85f7e643c80fdca9543795248867/Qwen-Image-2.1-viggle-turbo-v0.3-6step-lora-r128.safetensors?download=true'),
]

if __name__ == '__main__':
    print('Qwen 2.1 Nunchaku INT4 + encoder + VAE + Turbo: about 15.4 GB total if missing.')
    downloader.main()
