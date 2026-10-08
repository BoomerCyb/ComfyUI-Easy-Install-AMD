from pathlib import Path


def create_launcher_shortcuts(root):
    import win32com.client
    root = Path(root).resolve()
    helper = root / 'Add-Ons/Tools/Helper-CEI'
    launcher = helper / 'ComfyUI-EZi-Launcher.py'
    python = root / 'python_embeded/pythonw.exe'
    if not launcher.is_file() or not python.is_file():
        raise FileNotFoundError('EZi Launcher or portable Python is missing')
    shell = win32com.client.Dispatch('WScript.Shell')
    destinations = [root, Path(shell.SpecialFolders('Desktop'))]
    for destination in destinations:
        path = destination / 'ComfyUI-Easy-Install-AMD Launcher.lnk'
        shortcut = shell.CreateShortcut(str(path))
        shortcut.TargetPath = str(python)
        shortcut.Arguments = '"' + str(launcher) + '"'
        shortcut.WorkingDirectory = str(root)
        shortcut.IconLocation = str(helper / 'ComfyUI-EZi-Launcher.ico') + ',0'
        shortcut.Save()
        print('Created launcher shortcut:', path)


if __name__ == '__main__':
    create_launcher_shortcuts(Path(__file__).resolve().parent.parent)
