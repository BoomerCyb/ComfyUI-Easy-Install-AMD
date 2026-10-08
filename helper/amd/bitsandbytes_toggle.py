"""Keep bitsandbytes optional and preserve disabled files locally."""
import argparse
from pathlib import Path
import shutil
import sys
from bundles import BNB, pip, constraints
ROOT = Path(__file__).resolve().parent.parent

def toggle(root=ROOT, disable=False):
    site = root / 'python_embeded/Lib/site-packages'
    saved = root / 'amd/disabled-packages/bitsandbytes'
    active = site / 'bitsandbytes'
    has_saved = saved.exists() and any(saved.iterdir())
    if has_saved and active.exists() and not disable:
        # Our ROCm build is saved aside, so this one was installed meanwhile (e.g. the
        # CUDA build from PyPI by a node requirement). Replace it with the saved build.
        print('Replacing A Different Bitsandbytes Installed While The ROCm Build Was Disabled')
        pip(root / 'python_embeded/python.exe', 'uninstall', '-y', 'bitsandbytes', constrained=False)
        if active.exists():
            raise RuntimeError('Could Not Remove The Other Bitsandbytes; Inspect Site-Packages')
    if active.exists():
        if has_saved:
            raise RuntimeError('Saved Bitsandbytes Files Already Exist; Restore Or Inspect Them First')
        saved.mkdir(parents=True, exist_ok=True)
        paths = [active] + list(site.glob('bitsandbytes-*.dist-info')) + list(site.glob('bitsandbytes.libs'))
        moved = []
        try:
            for path in paths:
                target = saved / path.name
                path.rename(target)
                moved.append((path, target))
        except OSError:
            for path, target in reversed(moved):
                target.rename(path)
            raise
        print('Bitsandbytes Disabled')
    elif disable:
        print('Bitsandbytes Already Disabled')
    elif has_saved:
        paths = list(saved.iterdir())
        if any((site / p.name).exists() for p in paths):
            raise RuntimeError('Bitsandbytes Restore Destination Already Exists')
        moved = []
        try:
            for path in paths:
                target = site / path.name
                path.rename(target)
                moved.append((path, target))
        except OSError:
            for path, target in reversed(moved):
                target.rename(path)
            raise
        saved.rmdir()
        print('Bitsandbytes Enabled')
    else:
        pip(root / 'python_embeded/python.exe', 'install', '--no-deps', BNB, constrained=False)
        print('Bitsandbytes Installed And Enabled')
    constraints(root / 'python_embeded/python.exe', root / 'amd/amd-constraints.txt')
    print('Restart ComfyUI To Apply')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--disable', action='store_true')
    toggle(disable=parser.parse_args().disable)
