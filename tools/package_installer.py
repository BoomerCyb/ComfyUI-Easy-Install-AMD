"""Package one Windows batch installer pinned to a published source commit."""
from pathlib import Path
import subprocess
import zipfile

root = Path(__file__).resolve().parent.parent
dist = root / 'dist'
dist.mkdir(exist_ok=True)
revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
bat = (root / 'ComfyUI-Easy-Install-AMD.bat').read_text(encoding='utf-8')
bat = bat.replace('set "AMD_SOURCE_REF=Windows"', f'set "AMD_SOURCE_REF={revision}"')
destination = dist / 'ComfyUI-Easy-Install-AMD.zip'
folder = Path('ComfyUI-Easy-Install-AMD')
with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
    archive.writestr(str(folder / 'ComfyUI-Easy-Install-AMD.bat'), bat.replace('\n', '\r\n').encode('utf-8'))
    for name in ('README.md', 'LICENSE', 'UPSTREAM.md', 'CHANGES.md'):
        archive.write(root / name, folder / name)
    for name in ('EASY-INSTALL-LICENSE', 'ROCM-LICENSE'):
        archive.write(root / 'vendor' / name, folder / 'licenses' / name)
with zipfile.ZipFile(destination) as archive:
    assert archive.testzip() is None
    assert len(archive.namelist()) == 7
    assert all(name.startswith('ComfyUI-Easy-Install-AMD/') for name in archive.namelist())
print(f'{destination}\nOne installer plus documentation/licenses; {destination.stat().st_size:,} bytes; source revision {revision}')
