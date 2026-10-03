"""Stage portable helpers from the downloaded Git repository."""
import argparse
from pathlib import Path
import shutil


def stage(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or destination.is_relative_to(source):
        raise ValueError('Installation destination must be outside the source checkout')
    payload = source / 'helper-source/ComfyUI-Easy-Install'
    if not payload.is_dir() or not (source / 'amd/setup.py').is_file():
        raise ValueError('Incomplete installer source checkout')
    for base, prefix in ((payload, Path()), (source / 'amd', Path('amd'))):
        for path in base.rglob('*'):
            if not path.is_file() or any(part in ('__pycache__', '.cache', 'Getting Started') for part in path.relative_to(base).parts) or path.suffix in ('.pyc', '.log'):
                continue
            relative = prefix / path.relative_to(base)
            if not prefix.parts and relative.parts[0] == 'ComfyUI':
                relative = Path('preset-files') / relative
            target = destination / relative
            if not target.resolve().is_relative_to(destination):
                raise ValueError('Payload path escapes installation folder')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    for name in ('README.md', 'UPSTREAM.md', 'LICENSE', 'CHANGES.md'):
        target = destination / 'documentation' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
    for path in (source / 'vendor').iterdir():
        if path.is_file():
            target = destination / 'documentation/licenses' / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    print('Easy Install AMD helpers downloaded and staged.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    stage(Path(__file__).resolve().parent.parent, parser.parse_args().root)
