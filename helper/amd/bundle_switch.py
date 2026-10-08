import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
PTH = 'python312.zip\n.\nLib\nLib/site-packages\n../ComfyUI\n../amd\n..\nimport site\n'


def controller(root):
    import psutil
    active = root / 'python_embeded'
    target = root / '.bundle-controller'
    target.mkdir(exist_ok=True)
    for pattern in ('python.exe', '*.dll', '*.pyd', 'python312.zip'):
        for path in active.glob(pattern):
            shutil.copy2(path, target / path.name)
    shutil.copytree(Path(psutil.__file__).parent, target / 'psutil', dirs_exist_ok=True)
    (target / 'python312._pth').write_text('python312.zip\n.\n../amd\nimport site\n', encoding='ascii')


def activate(root):
    import psutil
    root = root.resolve()
    pending = root / 'amd/pending-bundle.txt'
    name = pending.read_text(encoding='ascii').strip()
    if not re.fullmatch(r'\d{8}-\d{6}', name):
        raise ValueError('Invalid bundle name')
    bundle = root / 'bundles' / name
    active = root / 'python_embeded'
    stage = root / 'python_bundle_stage'
    backup = root / 'bundles' / datetime.now().strftime('%Y%m%d-%H%M%S')
    for path in (bundle, active, stage, backup):
        if not path.resolve().is_relative_to(root):
            raise ValueError('Bundle path escapes this installation')
    data = json.loads((bundle / 'bundle.json').read_text(encoding='utf-8'))
    if not data.get('verified'):
        raise ValueError('Missing GPU verification receipt')
    input('Close EZi Desktop and all Python processes for this installation, then press Enter to switch: ')
    for process in psutil.process_iter(['exe']):
        try:
            exe = process.info['exe']
            if exe and Path(exe).resolve().is_relative_to(active.resolve()):
                raise RuntimeError('Python is still running in the active bundle. Close it before switching.')
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if backup.exists() or stage.exists():
        raise RuntimeError('Backup collision or an earlier staged switch exists; inspect before retrying.')
    shutil.copytree(bundle / 'python_embeded', stage)
    (stage / 'python312._pth').write_text(PTH, encoding='ascii')
    backup.mkdir()
    shutil.copy2(root / 'amd/active-bundle.json', backup / 'bundle.json')
    shutil.copy2(root / 'amd/amd-constraints.txt', backup / 'amd-constraints.txt')
    active.rename(backup / 'python_embeded')
    try:
        stage.rename(active)
        shutil.copy2(bundle / 'bundle.json', root / 'amd/active-bundle.json')
        shutil.copy2(bundle / 'amd-constraints.txt', root / 'amd/amd-constraints.txt')
    except OSError:
        if active.exists():
            active.rename(stage)
        (backup / 'python_embeded').rename(active)
        shutil.copy2(backup / 'bundle.json', root / 'amd/active-bundle.json')
        shutil.copy2(backup / 'amd-constraints.txt', root / 'amd/amd-constraints.txt')
        raise
    pending.unlink()
    print('Bundle switched. Previous environment saved for rollback. Restart EZi Desktop.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare-controller', action='store_true')
    parser.add_argument('--activate', action='store_true')
    args = parser.parse_args()
    controller(ROOT) if args.prepare_controller else activate(ROOT)
