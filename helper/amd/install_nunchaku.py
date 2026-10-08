"""Install the current public Nunchaku-AMD fork, preserving the previous copy."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import tempfile
import json

REPOSITORY = 'https://github.com/BoomerCyb/Nunchaku-AMD.git'
REVISION = 'c1ab591240c5753639a3e492279b4acf9b2376af'


def install(root):
    root = Path(root).resolve()
    target = root / 'ComfyUI/custom_nodes/ComfyUI-Nunchaku-AMD'
    workflows = root / 'ComfyUI/user/default/workflows'
    for path in (target, workflows):
        if not path.resolve().is_relative_to(root):
            raise RuntimeError('Add-on installation path is outside the installation root')
    if not (root / 'ComfyUI/main.py').is_file():
        raise RuntimeError('ComfyUI installation not found')
    staging = root / 'amd'
    if not staging.resolve().is_relative_to(root):
        raise RuntimeError('Download staging path is outside the installation root')
    staging.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='nunchaku-download-', dir=staging) as directory:
        source = Path(directory) / 'source'
        print('Downloading Nunchaku-AMD from:', REPOSITORY, flush=True)
        subprocess.run(['git', 'clone', '--depth', '1', REPOSITORY, str(source)], check=True)
        revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
        for required in ('__init__.py', 'nunchaku_amd.py', 'packed_kernel.py', 'NOTICE.txt', 'LICENSE', 'Nunchaku-AMD-Qwen-Image-2.1-Viggle-Turbo.json'):
            if not (source / required).is_file():
                raise RuntimeError('Incomplete Nunchaku repository: ' + required)
        backup = None
        if target.exists():
            backup = staging / 'nunchaku-backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            if not backup.resolve().is_relative_to(root):
                raise RuntimeError('Backup path is outside the installation root')
            backup.parent.mkdir(parents=True, exist_ok=True)
            target.rename(backup)
            print('Previous AMD add-on saved at:', backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            source.rename(target)
        except OSError:
            if backup is not None:
                backup.rename(target)
            raise
        (staging / 'nunchaku-install.json').write_text(json.dumps({'repository': REPOSITORY, 'revision': revision}, indent=2), encoding='utf-8')
    workflows.mkdir(parents=True, exist_ok=True)
    for workflow in target.glob('Nunchaku-AMD-*.json'):
        shutil.copy2(workflow, workflows / workflow.name)
    example = target / 'examples/nunchaku-amd-reference.png'
    if example.is_file():
        destination = root / 'ComfyUI/input' / example.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(example, destination)
    print('Nunchaku AMD nodes and Qwen, FLUX.1/2, SDXL, SANA, T5 and LTX2 workflows installed.')
    print('Restart ComfyUI, then open a Nunchaku-AMD workflow.')
    print('Qwen 2.1 Turbo uses its dedicated runtime adapter; standard LoRA merging is unsupported.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    install(parser.parse_args().root)
