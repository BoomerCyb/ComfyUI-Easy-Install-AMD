"""Install the bundled experimental ComfyUI node without changing dependencies."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil


def install(root):
    root = Path(root).resolve()
    source = Path(__file__).resolve().parent / 'nunchaku-addon'
    target = root / 'ComfyUI/custom_nodes/ComfyUI-Nunchaku-AMD'
    workflows = root / 'ComfyUI/user/default/workflows'
    for path in (target, workflows):
        if not path.resolve().is_relative_to(root):
            raise RuntimeError('Add-on installation path is outside the installation root')
    if not (root / 'ComfyUI/main.py').is_file():
        raise RuntimeError('ComfyUI installation not found')
    if target.exists():
        backup = root / 'amd/nunchaku-backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        shutil.copytree(target, backup, ignore=shutil.ignore_patterns('__pycache__', '.cache'))
        print('Previous AMD add-on saved at:', backup)
    shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '.cache'))
    workflows.mkdir(parents=True, exist_ok=True)
    for workflow in source.glob('Nunchaku-AMD-*.json'):
        shutil.copy2(workflow, workflows / workflow.name)
    example = source / 'examples/nunchaku-amd-reference.png'
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
