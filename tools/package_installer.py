from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent.parent
dist = root / 'dist'
dist.mkdir(exist_ok=True)
helper = dist / 'Helper-AMD.zip'
payload = root / 'helper-source/ComfyUI-Easy-Install'
with zipfile.ZipFile(helper, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(payload.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and 'Getting Started' not in path.parts and path.suffix != '.pyc':
            relative = path.relative_to(payload)
            if relative.parts[0] == 'ComfyUI':
                relative = Path('preset-files') / relative
            archive.write(path, relative)
    for path in sorted((root / 'amd').rglob('*')):
        if path.is_file() and not any(part in ('__pycache__', '.cache', 'nunchaku-backups', 'nunchaku-integration-backups') for part in path.parts) and path.suffix not in ('.pyc', '.log'):
            archive.write(path, path.relative_to(root))
    for name in ('README.md', 'UPSTREAM.md', 'LICENSE'):
        archive.write(root / name, Path('documentation') / name)
    for name in ('EASY-INSTALL-LICENSE', 'ROCM-LICENSE'):
        archive.write(root / 'vendor' / name, Path('documentation/licenses') / name)
with zipfile.ZipFile(helper) as archive:
    assert archive.testzip() is None
    names = archive.namelist()
    for required in ('amd/setup.py', 'amd/detect_gpu.py', 'amd/nodes.json', 'amd/shortcuts.py',
                     'ComfyUI-Easy-Install-AMD Launcher.bat',
                     'Add-Ons/Tools/Helper-CEI/ComfyUI-EZi-Launcher.py'):
        assert required in names, required
    assert not any(name.endswith('.ps1') or '/__pycache__/' in name for name in names)
    assert not any(name.startswith('ComfyUI/') for name in names)
    assert not any('/Getting Started/' in name for name in names)
    assert 'amd/nunchaku-addon/fixtures/qwen-int4-layer.safetensors' in names
    assert 'amd/nunchaku-addon/comfy_loader.py' in names
    assert 'amd/nunchaku-addon/Nunchaku-AMD-Qwen-Image.json' in names
    assert 'amd/nunchaku-addon/comfy_loader21.py' in names
    assert 'amd/nunchaku-addon/turbo21.py' in names
    assert 'amd/nunchaku-addon/comfy_loader_flux.py' in names
    assert 'amd/nunchaku-addon/comfy_loader_zimage.py' in names
    assert 'amd/nunchaku-addon/fp4.py' in names
    assert 'amd/nunchaku-addon/fp4_kernel.py' in names
    assert 'amd/nunchaku-addon/Nunchaku-AMD-Z-Image-Turbo-FP4.json' in names
    assert 'amd/download_nunchaku_extra_models.py' in names
    assert 'amd/nunchaku-addon/Nunchaku-AMD-FLUX.1-Schnell.json' in names
    assert 'amd/nunchaku-addon/Nunchaku-AMD-Z-Image-Turbo.json' in names
    assert 'amd/nunchaku-addon/Nunchaku-AMD-Qwen-Image-2.1-Viggle-Turbo-Edit.json' in names
    assert 'amd/nunchaku-addon/Nunchaku-AMD-Qwen-Image-2.1-Viggle-Turbo.json' in names
    assert not any(name.endswith('svdq-int4_r32-qwen-image.safetensors') for name in names)
    assert not any('/.cache/' in name for name in names)
    for module in ('families','comfy_loader_flux2','comfy_loader_sdxl','comfy_loader_t5','sana','ltx2','ltx_pipeline','nf4','nf4_kernel'):
        assert f'amd/nunchaku-addon/{module}.py' in names
    for family in ('FLUX.2-Klein','SDXL','FLUX.1-T5-INT4','SANA','LTX2'):
        assert f'amd/nunchaku-addon/Nunchaku-AMD-{family}.json' in names
    assert 'amd/download_nunchaku_families.py' in names
    assert 'amd/nunchaku-families-downloads.json' in names
    assert 'amd/bundle-presets.json' in names
    assert 'amd/nunchaku-addon/configs/ltx2.json' in names
readme = dist / 'README.txt'
readme.write_text('ComfyUI-Easy-Install-AMD\n\n'
    'Modified ComfyUI-Easy-Install / EZi Desktop edition for AMD GPUs.\n'
    'Original Easy Install by ivo / Tavris1.\n'
    'Includes the Easy Install logo, guided setup sections and EZi launcher flow.\n\n'
    'Extract all three files together into a new folder.\n'
    'Run ComfyUI-Easy-Install-AMD.bat as a normal user.\n'
    'Setup creates the ComfyUI-Easy-Install-AMD portable installation folder\n'
    'and the ComfyUI-Easy-Install-AMD Launcher desktop shortcut.\n\n'
    'Helper-AMD.zip contains the EZi Desktop/Launcher, workflows, helper scripts\n'
    'and license notices. Keep it beside the installer batch file.\n'
    'Only .bat and .py scripts are used; no PowerShell is required.\n\n'
    'This experimental build includes the build-backend, ONNX dependency and\n'
    'launcher fixes. Nunchaku AMD supports Qwen-Image, Qwen 2.1/Turbo/editing,\n'
    'FLUX.1, FLUX.2 Klein, Z-Image, SDXL, SANA, T5 and LTX2 video/audio.\n'
    'Each family has a tested checkpoint; other variants remain experimental.\n'
    'NVIDIA numerical parity is unverified. Z-Image FP4 uses software decoding.\n'
    'Model downloads are separate. Full GPU tests were run on RX 9070 XT.\n'
    'Some NVIDIA-only add-ons and conflicting audio dependencies are unavailable.\n', encoding='utf-8')
destination = dist / 'ComfyUI-Easy-Install-AMD.zip'
with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
    archive.write(root / 'ComfyUI-Easy-Install-AMD.bat', 'ComfyUI-Easy-Install-AMD.bat')
    archive.write(helper, 'Helper-AMD.zip')
    archive.write(readme, 'README.txt')
with zipfile.ZipFile(destination) as archive:
    assert archive.testzip() is None
    assert len(archive.namelist()) == 3
print(f'{destination}\n3 distribution files; {destination.stat().st_size:,} bytes; integrity verified')
