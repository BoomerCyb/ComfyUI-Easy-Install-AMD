"""Load the published LTX pipeline dependencies through AMD NF4 layers."""
import json
from pathlib import Path
import torch
if __package__:
    from .nf4 import load_nf4_into
else:
    from nf4 import load_nf4_into


def load_pipeline(directory,transformer):
    from transformers import Gemma3Config,Gemma3ForConditionalGeneration
    from diffusers import LTX2Pipeline
    from diffusers.pipelines.ltx2.connectors import LTX2TextConnectors
    directory = Path(directory)
    config = json.loads((directory/'text_encoder/config.json').read_text())
    config.pop('quantization_config',None)
    encoder_config = Gemma3Config.from_dict(config)
    encoder_config._attn_implementation = 'sdpa'
    with torch.device('meta'):
        encoder = Gemma3ForConditionalGeneration(encoder_config)
    encoder = load_nf4_into(encoder,directory/'text_encoder/model.safetensors')
    config = json.loads((directory/'connectors/config.json').read_text())
    config.pop('quantization_config',None)
    with torch.device('meta'):
        connectors = LTX2TextConnectors.from_config(config)
    connectors = load_nf4_into(connectors,directory/'connectors/diffusion_pytorch_model.safetensors')
    pipe = LTX2Pipeline.from_pretrained(directory,transformer=transformer,text_encoder=encoder,
                                      connectors=connectors,torch_dtype=torch.bfloat16,local_files_only=True)
    # Each dependency moves to GPU only for its own stage; transformer blocks
    # additionally stream from CPU. Packed NF4 dependency weights stay packed.
    pipe.enable_model_cpu_offload(gpu_id=torch.cuda.current_device())
    return pipe
