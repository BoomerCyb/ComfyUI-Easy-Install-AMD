import argparse
import ctypes
from datetime import datetime
from pathlib import Path
import re
import shutil
import subprocess
import sys
import winreg

ROOT = Path(__file__).resolve().parent.parent


def gpu_registry():
    gpus = []
    pci = r'SYSTEM\CurrentControlSet\Enum\PCI'
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, pci) as devices:
        for i in range(winreg.QueryInfoKey(devices)[0]):
            device = winreg.EnumKey(devices, i)
            if 'VEN_1002' not in device.upper():
                continue
            with winreg.OpenKey(devices, device) as instances:
                for j in range(winreg.QueryInfoKey(instances)[0]):
                    instance = winreg.EnumKey(instances, j)
                    with winreg.OpenKey(instances, instance) as key:
                        try:
                            driver = winreg.QueryValueEx(key, 'Driver')[0]
                            if not driver.lower().startswith('{4d36e968-e325-11ce-bfc1-08002be10318}'):
                                continue
                            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 'SYSTEM\\CurrentControlSet\\Control\\Class\\' + driver) as cls:
                                name = winreg.QueryValueEx(cls, 'DriverDesc')[0]
                            gpus.append({'name': name, 'pnp_id': 'PCI\\' + device + '\\' + instance})
                        except FileNotFoundError:
                            continue
    return gpus


def browser_version():
    import win32api
    for exe in ('chrome.exe', 'msedge.exe'):
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, 'SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\' + exe) as key:
                    path = winreg.QueryValue(key, None)
                info = win32api.GetFileVersionInfo(path, '\\')
                hi, lo = info['FileVersionMS'], info['FileVersionLS']
                return f'{hi >> 16}.{hi & 65535}.{lo >> 16}.{lo & 65535}'
            except (OSError, win32api.error):
                continue
    return '148.0.0.0'


def pagefile():
    import win32com.client
    import pythoncom
    pythoncom.CoInitialize()
    try:
        wmi = win32com.client.GetObject('winmgmts:')
        usage = list(wmi.ExecQuery('SELECT AllocatedBaseSize FROM Win32_PageFileUsage'))
        settings = list(wmi.ExecQuery('SELECT MaximumSize FROM Win32_PageFileSetting'))
        current = sum(int(p.AllocatedBaseSize) for p in usage)
        maximum = sum(int(p.MaximumSize) for p in settings)
        return f'{maximum} MB (current: {current} MB)' if maximum else f'Auto (current: {current} MB)'
    finally:
        pythoncom.CoUninitialize()


def models():
    import win32com.client
    folder = win32com.client.Dispatch('Shell.Application').BrowseForFolder(0, 'Select your existing MODELS folder', 0x51, 17)
    if folder is None:
        return 2
    path = Path(folder.Self.Path).resolve()
    yaml = ROOT / 'ComfyUI/extra_model_paths.yaml'
    if yaml.exists():
        shutil.copy2(yaml, yaml.with_name('extra_model_paths.' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.bak'))
    # JSON string quoting is also valid YAML and handles Windows path characters.
    import json
    lines = ['comfyui:', '    base_path: ' + json.dumps(str(path)), '    is_default: true']
    for child in sorted(path.iterdir()):
        if child.is_dir():
            lines.append('    ' + json.dumps(child.name.lower()) + ': ' + json.dumps(child.name))
    yaml.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Models linked:', path)


def toggle():
    paths = sorted(ROOT.glob('Start ComfyUI*.bat'))
    disable = '--disable-dynamic-vram' not in (ROOT / 'Start ComfyUI.bat').read_text(encoding='utf-8')
    for path in paths:
        text = path.read_text(encoding='utf-8')
        text = re.sub(r'\s+--(?:enable|disable)-dynamic-vram', '', text)
        text = re.sub(r'(?m)^(.*python_embeded\\python\.exe.*amd\\runtime\.py[^\n]*)$',
                      lambda m: m[1] + (' --disable-dynamic-vram' if disable else ' --enable-dynamic-vram'), text)
        path.write_text(text, encoding='utf-8')
    print('Dynamic VRAM disabled' if disable else 'Dynamic VRAM enabled')


def triton():
    paths = sorted(ROOT.glob('Start ComfyUI*.bat'))
    primary = ROOT / 'Start ComfyUI.bat'
    current = primary.read_text(encoding='utf-8')
    enabled = '--enable-triton-backend' in current and '--disable-triton-backend' not in current
    flag = '--disable-triton-backend' if enabled else '--enable-triton-backend'
    for path in paths:
        text = path.read_text(encoding='utf-8')
        text = re.sub(r'\s+--(?:enable|disable)-triton-backend\b', '', text)
        text = re.sub(r'(?m)^(.*python_embeded\\python\.exe.*(?:amd\\runtime|ComfyUI\\main)\.py[^\n]*)$',
                      lambda m: m[1].rstrip('\r') + ' ' + flag, text)
        path.write_text(text, encoding='utf-8')
    print('Triton Backend Disabled' if enabled else 'Triton Backend Enabled')
    print('Restart ComfyUI To Apply. Triton Remains Installed For Custom Nodes.')


def gguf():
    import win32ui
    dialog = win32ui.CreateFileDialog(1, None, None, 0x1000, 'Model files|*.safetensors;*.pth;*.pt|All files|*.*||')
    if dialog.DoModal() != 1:
        return
    source = Path(dialog.GetPathName())
    choices = ['Q8_0', 'Q6_K', 'Q5_K_M', 'Q5_K_S', 'Q5_1', 'Q5_0', 'Q4_K_M', 'Q4_K_S', 'Q4_1', 'Q4_0', 'Q3_K_M', 'Q3_K_S', 'Q2_K']
    print('Quantization:', ', '.join(choices))
    method = input('Method [Q4_K_M]: ').strip().upper() or 'Q4_K_M'
    if method not in choices:
        raise ValueError('Invalid quantization method')
    tools = ROOT / 'ComfyUI/custom_nodes/ComfyUI-GGUF/tools'
    subprocess.run([sys.executable, str(tools / 'convert.py'), '--src', str(source)], check=True)
    intermediate = next((source.with_name(source.stem + '-' + dtype + '.gguf') for dtype in ('BF16', 'FP16')
                         if source.with_name(source.stem + '-' + dtype + '.gguf').exists()), None)
    if intermediate is None:
        raise RuntimeError('Converter did not produce a BF16/FP16 GGUF file')
    output = source.with_name(source.stem + '-' + method + '.gguf')
    subprocess.run([str(ROOT / 'Add-Ons/Tools/llama.cpp/llama-quantize.exe'), str(intermediate), str(output), method], check=True)
    if list(source.parent.glob('fix_5d_tensors_*.safetensors')):
        fixed = output.with_name(output.stem + '-fixed.gguf')
        subprocess.run([sys.executable, str(tools / 'fix_5d_tensors.py'), '--src', str(output), '--dst', str(fixed), '--overwrite'], check=True)
        fixed.replace(output)
    print('Created:', output)


def longpaths():
    if not ctypes.windll.shell32.IsUserAnAdmin():
        result = ctypes.windll.shell32.ShellExecuteW(None, 'runas', sys.executable,
            subprocess.list2cmdline([str(Path(__file__).resolve()), 'longpaths']), str(ROOT), 1)
        if result <= 32:
            raise RuntimeError('Administrator access was declined or unavailable')
        return
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\FileSystem', 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, 'LongPathsEnabled', 0, winreg.REG_DWORD, 1)
    print('Long paths enabled. Restart Windows for all applications to see the change.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['models', 'toggle', 'triton', 'gguf', 'longpaths'])
    action = parser.parse_args().action
    raise SystemExit(globals()[action]())
