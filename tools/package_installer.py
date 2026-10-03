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
with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
    archive.writestr('ComfyUI-Easy-Install-AMD.bat', bat.replace('\n', '\r\n').encode('utf-8'))
with zipfile.ZipFile(destination) as archive:
    assert archive.testzip() is None
    assert archive.namelist() == ['ComfyUI-Easy-Install-AMD.bat']
print(f'{destination}\nOne installer file; {destination.stat().st_size:,} bytes; source revision {revision}')
