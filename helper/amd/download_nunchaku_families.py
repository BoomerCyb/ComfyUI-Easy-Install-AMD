"""Pinned, resumable model/component downloads for the AMD family add-on."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def main(family):
    if family in ('all','sana','ltx2'):
        from importlib.metadata import version,PackageNotFoundError
        from packaging.version import Version
        requirements = []
        for name,minimum in (('diffusers','0.39.0'),('accelerate','1.0')):
            try:
                installed = Version(version(name))
            except PackageNotFoundError:
                installed = Version('0')
            if installed < Version(minimum):
                requirements.append(name+'>='+minimum)
        if requirements:
            subprocess.run([sys.executable,'-m','pip','install',*requirements],check=True)
    catalog = json.loads((Path(__file__).parent/'nunchaku-families-downloads.json').read_text())
    entries = [item for key,items in catalog.items() if family in ('all',key) for item in items]
    entries = list({item['path']:item for item in entries}.values())
    print(f'Download set: {family}; {sum(item["size"] for item in entries)/1e9:.1f} GB if missing.',flush=True)
    for item in entries:
        target = ROOT/'ComfyUI/models'/item['path']
        if not target.resolve().is_relative_to(ROOT):
            raise ValueError('Download target escapes the installation')
        if target.exists():
            if target.stat().st_size != item['size']:
                raise RuntimeError(f'Existing file size differs; preserving it: {target}')
            print('Already installed:',target,flush=True)
            continue
        target.parent.mkdir(parents=True,exist_ok=True)
        partial = target.with_suffix(target.suffix+'.part')
        subprocess.run(['curl.exe','-fL','--retry','3','-C','-','-o',str(partial),item['url']],check=True)
        if partial.stat().st_size != item['size']:
            raise RuntimeError(f'Download size differs: {target}')
        if target.suffix == '.safetensors':
            from safetensors import safe_open
            with safe_open(str(partial),framework='pt') as checkpoint:
                if not list(checkpoint.keys()):
                    raise RuntimeError('Downloaded safetensors file is empty')
        elif target.suffix == '.json':
            json.loads(partial.read_text(encoding='utf-8'))
        partial.replace(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('family',choices=('all','flux2','sdxl','sana','t5','ltx2'))
    main(parser.parse_args().family)
