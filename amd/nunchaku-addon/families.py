"""ComfyUI nodes for the additional packed AMD Nunchaku model families."""
import gc
import json
from pathlib import Path


def checkpoint_choices(word):
    import folder_paths
    names = [name for name in folder_paths.get_filename_list('diffusion_models')
             if word in name.lower() and ('svdq-int4' in name.lower() or 'svdq-fp4' in name.lower())]
    return names or [f'Install the {word} checkpoint from the Nunchaku add-on']


class NunchakuAMDFlux2Loader:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'checkpoint_name':(checkpoint_choices('flux.2'),),
                            'backend':(['triton','torch'],),'activation_bits':(['4','16'],)}}
    RETURN_TYPES = ('MODEL',)
    FUNCTION = 'load_model'
    CATEGORY = 'Nunchaku AMD/RX 9070 XT only'

    def load_model(self,checkpoint_name,backend,activation_bits):
        import folder_paths
        from . import ensure_gpu
        from .comfy_loader_flux2 import load_flux2
        ensure_gpu(backend)
        return (load_flux2(folder_paths.get_full_path_or_raise('diffusion_models',checkpoint_name),
                           backend=backend,activation_bits=int(activation_bits)),)


class NunchakuAMDSDXLLoader(NunchakuAMDFlux2Loader):
    @classmethod
    def INPUT_TYPES(cls):
        result = super().INPUT_TYPES()
        result['required']['checkpoint_name'] = (checkpoint_choices('sdxl'),)
        return result

    def load_model(self,checkpoint_name,backend,activation_bits):
        import folder_paths
        from . import ensure_gpu
        from .comfy_loader_sdxl import load_sdxl
        ensure_gpu(backend)
        return (load_sdxl(folder_paths.get_full_path_or_raise('diffusion_models',checkpoint_name),
                          backend=backend,activation_bits=int(activation_bits)),)


class NunchakuAMDT5Loader:
    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        names = folder_paths.get_filename_list('text_encoders')
        return {'required':{'t5_checkpoint':([name for name in names if 'awq-int4' in name and 't5' in name] or ['Install the AWQ T5 encoder'],),
                            'clip_l_checkpoint':([name for name in names if 'clip_l' in name] or ['clip_l.safetensors'],),
                            'backend':(['triton','torch'],)}}
    RETURN_TYPES = ('CLIP',)
    FUNCTION = 'load_clip'
    CATEGORY = 'Nunchaku AMD/RX 9070 XT only'

    def load_clip(self,t5_checkpoint,clip_l_checkpoint,backend):
        import folder_paths
        from . import ensure_gpu
        from .comfy_loader_t5 import load_flux_clip
        ensure_gpu(backend)
        return (load_flux_clip(folder_paths.get_full_path_or_raise('text_encoders',t5_checkpoint),
                               folder_paths.get_full_path_or_raise('text_encoders',clip_l_checkpoint),backend=backend),)


class NunchakuAMDSanaGenerate:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'checkpoint_name':(checkpoint_choices('sana'),),
                            'prompt':('STRING',{'multiline':True,'default':'A red ceramic teapot on a wooden table.'}),
                            'negative_prompt':('STRING',{'multiline':True,'default':''}),
                            'seed':('INT',{'default':123,'min':0,'max':2147483647}),
                            'width':('INT',{'default':512,'min':256,'max':2048,'step':32}),
                            'height':('INT',{'default':512,'min':256,'max':2048,'step':32}),
                            'steps':('INT',{'default':20,'min':1,'max':100}),
                            'guidance':('FLOAT',{'default':4.5,'min':1.0,'max':20.0}),
                            'backend':(['triton','torch'],),'activation_bits':(['4','16'],)}}
    RETURN_TYPES = ('IMAGE','STRING')
    RETURN_NAMES = ('images','report')
    FUNCTION = 'generate'
    CATEGORY = 'Nunchaku AMD/RX 9070 XT only'
    DESCRIPTION = 'Packed SANA pipeline. Install the SANA encoder/VAE bundle through the add-on.'

    def generate(self,checkpoint_name,prompt,negative_prompt,seed,width,height,steps,guidance,backend,activation_bits):
        import folder_paths
        import numpy as np
        import torch
        import comfy.model_management as management
        from diffusers import SanaPipeline
        from . import ensure_gpu
        from .sana import load_sana
        ensure_gpu(backend)
        management.unload_all_models()
        directory = Path(folder_paths.models_dir)/'nunchaku_pipelines/sana'
        if not (directory/'model_index.json').is_file():
            raise RuntimeError('Install the SANA pipeline bundle through Add-Ons/Nunchaku.bat')
        pipe = None
        try:
            with torch.inference_mode():
                model = load_sana(folder_paths.get_full_path_or_raise('diffusion_models',checkpoint_name),
                                  backend=backend,activation_bits=int(activation_bits))
                pipe = SanaPipeline.from_pretrained(directory,transformer=model,torch_dtype=torch.bfloat16,
                                                   variant='bf16',local_files_only=True).to(management.get_torch_device())
                output = pipe(prompt,negative_prompt=negative_prompt,height=height,width=width,
                              num_inference_steps=steps,guidance_scale=guidance,
                              generator=torch.Generator('cpu').manual_seed(seed)).images[0]
                image = torch.from_numpy(np.asarray(output).copy()).float().unsqueeze(0)/255
                return image,json.dumps(model.nunchaku_amd_info,indent=2)
        finally:
            del pipe
            gc.collect()
            management.soft_empty_cache()


class NunchakuAMDLTXGenerate(NunchakuAMDSanaGenerate):
    @classmethod
    def INPUT_TYPES(cls):
        result = super().INPUT_TYPES()
        required = result['required']
        required['checkpoint_name'] = (checkpoint_choices('ltx2'),)
        required['steps'] = ('INT',{'default':8,'min':1,'max':100})
        required['guidance'] = ('FLOAT',{'default':1.0,'min':1.0,'max':20.0})
        required['width'] = ('INT',{'default':256,'min':128,'max':1024,'step':32})
        required['height'] = ('INT',{'default':256,'min':128,'max':1024,'step':32})
        required['frames'] = ('INT',{'default':9,'min':9,'max':121,'step':8})
        required['fps'] = ('FLOAT',{'default':24.0,'min':1.0,'max':60.0})
        return result
    RETURN_TYPES = ('IMAGE','AUDIO','STRING')
    RETURN_NAMES = ('frames','audio','report')
    DESCRIPTION = 'Joint LTX2 video/audio through packed AMD projections and streamed transformer blocks.'

    def generate(self,checkpoint_name,prompt,negative_prompt,seed,width,height,steps,guidance,backend,activation_bits,frames,fps):
        import folder_paths
        import torch
        import comfy.model_management as management
        from . import ensure_gpu
        from .ltx2 import load_ltx2
        from .ltx_pipeline import load_pipeline
        ensure_gpu(backend)
        management.unload_all_models()
        directory = Path(folder_paths.models_dir)/'nunchaku_pipelines/ltx2'
        config = json.loads((Path(__file__).parent/'configs/ltx2.json').read_text())
        pipe = None
        try:
            with torch.inference_mode():
                model = load_ltx2(folder_paths.get_full_path_or_raise('diffusion_models',checkpoint_name),config,
                                  backend=backend,activation_bits=int(activation_bits))
                pipe = load_pipeline(directory,model)
                video,audio = pipe(prompt,negative_prompt=negative_prompt,height=height,width=width,num_frames=frames,
                                   frame_rate=fps,num_inference_steps=steps,guidance_scale=guidance,
                                   sigmas=[1.0,.99375,.9875,.98125,.975,.909375,.725,.421875] if steps==8 else None,
                                   generator=torch.Generator('cpu').manual_seed(seed),output_type='np',return_dict=False)
                images = torch.from_numpy(video[0].copy()).float()
                waveform = audio[0].float().cpu()
                if waveform.ndim == 1:
                    waveform = waveform[None]
                if not torch.isfinite(images).all() or not torch.isfinite(waveform).all():
                    raise RuntimeError('LTX produced non-finite output')
                return images,{'waveform':waveform[None],'sample_rate':pipe.vocoder.config.output_sampling_rate},json.dumps(model.nunchaku_amd_info,indent=2)
        finally:
            del pipe
            gc.collect()
            management.soft_empty_cache()


NODE_CLASS_MAPPINGS = {cls.__name__:cls for cls in (NunchakuAMDFlux2Loader,NunchakuAMDSDXLLoader,NunchakuAMDT5Loader,
                                                   NunchakuAMDSanaGenerate,NunchakuAMDLTXGenerate)}
NODE_DISPLAY_NAME_MAPPINGS = {'NunchakuAMDFlux2Loader':'Nunchaku AMD — FLUX.2 Klein Loader',
                              'NunchakuAMDSDXLLoader':'Nunchaku AMD — SDXL INT4 Loader',
                              'NunchakuAMDT5Loader':'Nunchaku AMD — T5 INT4 + CLIP-L',
                              'NunchakuAMDSanaGenerate':'Nunchaku AMD — SANA Generate',
                              'NunchakuAMDLTXGenerate':'Nunchaku AMD — LTX2 Video / Audio'}
