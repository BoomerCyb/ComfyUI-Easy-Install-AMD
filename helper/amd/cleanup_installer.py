"""Remove distribution files after a successful portable installation."""
from pathlib import Path
import zipfile


def cleanup(root):
    root = Path(root).resolve()
    if not (root/'.amd-installed').is_file() or not (root/'ComfyUI/main.py').is_file():
        raise RuntimeError('Installation is incomplete; setup files are retained.')
    documentation = root/'documentation'
    # Retain the supplied notices in documentation; preserve changed user files.
    for source in documentation.rglob('*'):
        if not source.is_file() or source.is_symlink():
            continue
        relative = source.relative_to(documentation)
        if relative.parts[0] not in ('README.md','LICENSE','docs'):
            continue
        target = root/relative
        if target.is_symlink() or not target.resolve().is_relative_to(root):
            continue
        if target.is_file() and target.read_bytes()==source.read_bytes():
            target.unlink()
    docs = root/'docs'
    if docs.is_dir() and not docs.is_symlink() and docs.resolve().is_relative_to(root):
        for directory in sorted(docs.rglob('*'),key=lambda p:len(p.parts),reverse=True):
            if directory.is_dir() and not directory.is_symlink() and directory.resolve().is_relative_to(root):
                try:
                    directory.rmdir()
                except OSError:
                    pass
        try:
            docs.rmdir()
        except OSError:
            print('Retaining docs: it contains additional or changed files.')
    helper = root/'Helper-CEI.zip'
    if helper.is_file() and not helper.is_symlink():
        with zipfile.ZipFile(helper) as archive:
            if 'amd/setup.py' not in archive.namelist():
                raise RuntimeError('Unrecognized helper archive; retaining it.')
        helper.unlink()
    print('Setup files removed. License notices remain in documentation/LICENSE.')


if __name__=='__main__':
    cleanup(Path(__file__).resolve().parent.parent)
