VERSION = '0.1.26-amd'

import glob
import os
import sys
import subprocess
import ctypes
import ctypes.wintypes as wt
import threading
import re
import shlex
import json
import math

import time
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT_DIR   = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
EZI_PY     = os.path.join(SCRIPT_DIR, 'ComfyUI-EZi.py')

def root(name):
    return os.path.join(ROOT_DIR, name)

ADDONS_DIR = root('Add-ons')

def attention_available(module):
    # Whether the package is installed. Importing it to find out loads PyTorch, which
    # can take longer than any timeout on a cold start and then reads as "missing".
    site = root('python_embeded/Lib/site-packages')
    return (os.path.isfile(os.path.join(site, module, '__init__.py'))
            and bool(glob.glob(os.path.join(glob.escape(site), module + '-*.dist-info'))))

HAS_SAGE  = attention_available('sageattention')
HAS_FLASH = attention_available('flash_attn')

HAS_DESK_SAGE  = HAS_SAGE and os.path.exists(root('Start ComfyUI SageAttention.bat'))
HAS_DESK_FLASH = HAS_FLASH and os.path.exists(root('Start ComfyUI FlashAttention.bat'))
HAS_DESK_KITCHEN = os.path.exists(root('Start ComfyUI KitchenAttention.bat'))
HAS_BROW_SAGE  = HAS_SAGE and os.path.exists(root('Start ComfyUI SageAttention.bat'))
HAS_BROW_FLASH = HAS_FLASH and os.path.exists(root('Start ComfyUI FlashAttention.bat'))
HAS_BROW_KITCHEN = os.path.exists(root('Start ComfyUI KitchenAttention.bat'))

HAS_UPD_COMFY      = os.path.exists(root('Update ComfyUI.bat'))
HAS_UPD_COMFY_NODE = os.path.exists(root('Update ComfyUI and Nodes.bat'))
HAS_UPD_EASY       = os.path.exists(root('Update Easy-Install.bat'))
HAS_UPD_COMFY_NIGHTLY = os.path.exists(root('Update ComfyUI Nightly.bat'))

INSTALL_SAGE_BAT  = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '..', 'SageAttention AMD.bat'))
INSTALL_FLASH_BAT = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '..', 'FlashAttention AMD.bat'))

def _get_dpi_scale():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    try:
        class _POINT(ctypes.Structure):
            _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]
        pt = _POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        MONITOR_DEFAULTTONEAREST = 2
        hmon = ctypes.windll.user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
        dpi_x = ctypes.c_uint(0)
        dpi_y = ctypes.c_uint(0)
        MDT_EFFECTIVE_DPI = 0
        ctypes.windll.shcore.GetDpiForMonitor(
            hmon, MDT_EFFECTIVE_DPI,
            ctypes.byref(dpi_x), ctypes.byref(dpi_y)
        )
        return max(0.5, dpi_x.value / 96.0)
    except Exception:
        try:
            hdc = ctypes.windll.user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
            ctypes.windll.user32.ReleaseDC(0, hdc)
            return max(0.5, dpi / 96.0)
        except Exception:
            return 1.0

UI_SCALE = _get_dpi_scale()

def sc(v):
    return int(round(v * UI_SCALE))

WS_POPUP         = 0x80000000
WS_VISIBLE       = 0x10000000
WS_CLIPCHILDREN  = 0x02000000
WS_EX_TOPMOST    = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_CHILD         = 0x40000000
BS_OWNERDRAW     = 0x0000000B
TTS_ALWAYSTIP    = 0x0001
TTS_NOPREFIX     = 0x0002
TTM_ADDTOOLW     = 0x0432
TTM_SETMAXTIPWIDTH = 0x0418
TTDT_AUTOPOP     = 2
TTM_SETDELAYTIME = 0x0403
WM_DESTROY       = 0x0002
WM_PAINT         = 0x000F
WM_ERASEBKGND    = 0x0014
WM_COMMAND       = 0x0111
WM_NCHITTEST     = 0x0084
WM_ACTIVATE      = 0x0006
WM_DRAWITEM      = 0x002B
WM_MOUSEMOVE     = 0x0200
WM_MOUSELEAVE    = 0x02A3
WM_CTLCOLORBTN   = 0x0135
WM_KILLFOCUS     = 0x0008
WM_LBUTTONDOWN   = 0x0201
HTCAPTION        = 2
IDC_ARROW        = 32512
CS_HREDRAW       = 0x0002
CS_VREDRAW       = 0x0001
SW_SHOW          = 5
PS_SOLID         = 0
PS_DASH          = 1
DT_LEFT          = 0x0000
DT_CENTER        = 0x0001
DT_VCENTER       = 0x0004
DT_SINGLELINE    = 0x0020
SRCCOPY          = 0x00CC0020
RDW_INVALIDATE   = 0x0001
RDW_UPDATENOW    = 0x0100
RDW_ALLCHILDREN  = 0x0080
RGN_DIFF         = 4

WIN_W, WIN_H = sc(672), sc(420)

user32   = ctypes.windll.user32
gdi32    = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

if sys.maxsize > 2**32:
    LRESULT = ctypes.c_int64
    WPARAM  = ctypes.c_uint64
    LPARAM  = ctypes.c_int64
else:
    LRESULT = ctypes.c_long
    WPARAM  = ctypes.c_uint
    LPARAM  = ctypes.c_long

WNDPROC       = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, WPARAM, LPARAM)
BTN_PROC_TYPE = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, WPARAM, LPARAM)

user32.DefWindowProcW.argtypes    = [wt.HWND, wt.UINT, WPARAM, LPARAM]
user32.DefWindowProcW.restype     = LRESULT
user32.CallWindowProcW.argtypes   = [WNDPROC, wt.HWND, wt.UINT, WPARAM, LPARAM]
user32.CallWindowProcW.restype    = LRESULT
user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype  = ctypes.c_void_p
user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_void_p]
user32.SetWindowLongPtrW.restype  = ctypes.c_void_p
user32.FillRect.argtypes          = [wt.HDC, ctypes.POINTER(wt.RECT), wt.HBRUSH]
user32.FillRect.restype           = ctypes.c_int
user32.GetDlgCtrlID.argtypes      = [wt.HWND]
user32.GetDlgCtrlID.restype       = ctypes.c_int
user32.SendMessageW.argtypes      = [wt.HWND, wt.UINT, WPARAM, LPARAM]
user32.SendMessageW.restype       = LRESULT
user32.GetDlgItem.argtypes        = [wt.HWND, ctypes.c_int]
user32.GetDlgItem.restype         = wt.HWND
user32.SetFocus.argtypes          = [wt.HWND]
user32.SetFocus.restype           = wt.HWND

class WNDCLASSEX(ctypes.Structure):
    _fields_ = [
        ('cbSize',        wt.UINT),
        ('style',         wt.UINT),
        ('lpfnWndProc',   WNDPROC),
        ('cbClsExtra',    ctypes.c_int),
        ('cbWndExtra',    ctypes.c_int),
        ('hInstance',     wt.HINSTANCE),
        ('hIcon',         wt.HICON),
        ('hCursor',       wt.HANDLE),
        ('hbrBackground', wt.HBRUSH),
        ('lpszMenuName',  wt.LPCWSTR),
        ('lpszClassName', wt.LPCWSTR),
        ('hIconSm',       wt.HICON),
    ]

class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ('hdc',         wt.HDC),
        ('fErase',      wt.BOOL),
        ('rcPaint',     wt.RECT),
        ('fRestore',    wt.BOOL),
        ('fIncUpdate',  wt.BOOL),
        ('rgbReserved', ctypes.c_byte * 32),
    ]

class LOGFONT(ctypes.Structure):
    _fields_ = [
        ('lfHeight',         ctypes.c_long),
        ('lfWidth',          ctypes.c_long),
        ('lfEscapement',     ctypes.c_long),
        ('lfOrientation',    ctypes.c_long),
        ('lfWeight',         ctypes.c_long),
        ('lfItalic',         ctypes.c_byte),
        ('lfUnderline',      ctypes.c_byte),
        ('lfStrikeOut',      ctypes.c_byte),
        ('lfCharSet',        ctypes.c_byte),
        ('lfOutPrecision',   ctypes.c_byte),
        ('lfClipPrecision',  ctypes.c_byte),
        ('lfQuality',        ctypes.c_byte),
        ('lfPitchAndFamily', ctypes.c_byte),
        ('lfFaceName',       ctypes.c_wchar * 32),
    ]

class DRAWITEMSTRUCT(ctypes.Structure):
    _fields_ = [
        ('CtlType',    wt.UINT),
        ('CtlID',      wt.UINT),
        ('itemID',     wt.UINT),
        ('itemAction', wt.UINT),
        ('itemState',  wt.UINT),
        ('_pad',       ctypes.c_uint),
        ('hwndItem',   wt.HWND),
        ('hDC',        wt.HDC),
        ('rcItem',     wt.RECT),
        ('itemData',   ctypes.c_size_t),
    ]

class TRACKMOUSEEVENT(ctypes.Structure):
    _pack_ = 8
    _fields_ = [
        ('cbSize',      wt.DWORD),
        ('dwFlags',     wt.DWORD),
        ('hwndTrack',   wt.HWND),
        ('dwHoverTime', wt.DWORD),
    ]

def make_font(size, weight=400, face='Segoe UI'):
    lf = LOGFONT()
    lf.lfHeight         = size
    lf.lfWeight         = weight
    lf.lfQuality        = 5
    lf.lfPitchAndFamily = 0x22
    lf.lfFaceName       = face
    return gdi32.CreateFontIndirectW(ctypes.byref(lf))

def make_solid_brush(c):
    return gdi32.CreateSolidBrush(c)

class POINT(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]

def calc_position():
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    x, y = pt.x + 16, pt.y + 16
    if x + WIN_W > sw: x = sw - WIN_W - 8
    if y + WIN_H > sh: y = sh - WIN_H - 8
    if x < 0: x = 8
    if y < 0: y = 8
    return x, y

ID_CLOSE      = 1
ID_VERSION    = 2
ID_EZI_DESK     = 10
ID_KITCHEN_DESK = 13
ID_SAGE_DESK    = 11
ID_FLASH_DESK   = 12
ID_EZI_BROW     = 20
ID_KITCHEN_BROW = 23
ID_SAGE_BROW    = 21
ID_FLASH_BROW   = 22

ID_UPD_COMFY      = 30
ID_UPD_COMFY_NODE = 31
ID_UPD_EASY       = 32

ID_FOLD_OUTPUT    = 41
ID_FOLD_INPUT     = 42
ID_FOLD_WORKFLOWS = 43
ID_FOLD_MODELS    = 44

ID_MODE_BROWSER   = 50
ID_MODE_HYBRID    = 51
ID_TRITON         = 45

ID_SC_EZI_DESK     = 110
ID_SC_SAGE_DESK    = 111
ID_SC_FLASH_DESK   = 112
ID_SC_KITCHEN_DESK = 113
ID_SC_EZI_BROW     = 120
ID_SC_SAGE_BROW    = 121
ID_SC_FLASH_BROW   = 122
ID_SC_KITCHEN_BROW = 123

ID_SC_UPD_COMFY  = 130

SHORTCUT_META = {
    ID_SC_EZI_DESK:     (ID_EZI_DESK,     'ComfyUI-EZi-Desktop.ico', 'ComfyUI-Easy-Install-AMD Desktop'),
    ID_SC_SAGE_DESK:    (ID_SAGE_DESK,    'ComfyUI-EZi-Desktop.ico', 'ComfyUI-Easy-Install-AMD SageAttention'),
    ID_SC_FLASH_DESK:   (ID_FLASH_DESK,   'ComfyUI-EZi-Desktop.ico', 'ComfyUI-Easy-Install-AMD FlashAttention'),
    ID_SC_KITCHEN_DESK: (ID_KITCHEN_DESK, 'ComfyUI-EZi-Desktop.ico', 'ComfyUI-Easy-Install-AMD KitchenAttention'),
    ID_SC_EZI_BROW:     (ID_EZI_BROW,     'ComfyUI-EZi.ico',         'ComfyUI-EZi'),
    ID_SC_SAGE_BROW:    (ID_SAGE_BROW,    'ComfyUI-Sage.ico',        'ComfyUI-SA'),
    ID_SC_FLASH_BROW:   (ID_FLASH_BROW,   'ComfyUI-Flash.ico',       'ComfyUI-FA'),
    ID_SC_KITCHEN_BROW: (ID_KITCHEN_BROW, 'ComfyUI-Kitchen.ico',     'ComfyUI-KA'),
}

ARROW_COLOR_CAT = {}
for _sc_id, _sc_meta in SHORTCUT_META.items():
    _main_id = _sc_meta[0]
    ARROW_COLOR_CAT[_sc_id] = (
        'desk' if _main_id in (ID_EZI_DESK, ID_SAGE_DESK, ID_FLASH_DESK, ID_KITCHEN_DESK) else 'brow'
    )

WM_APP_CLOSE = 0x8001

g_fonts          = {}
g_brushes        = {}
g_hover_btn      = None
g_gradient_memdc = None
g_gradient_bmp   = None
g_tooltip_hwnd   = None
g_creating_shortcut = False
g_hwnd           = None
g_adv            = False

class TOOLINFOW(ctypes.Structure):
    _fields_ = [
        ('cbSize',   wt.UINT),
        ('uFlags',   wt.UINT),
        ('hwnd',     wt.HWND),
        ('uId',      ctypes.c_size_t),
        ('rect',     wt.RECT),
        ('hinst',    wt.HINSTANCE),
        ('lpszText', wt.LPCWSTR),
        ('lParam',   ctypes.c_size_t),
        ('lpReserved', ctypes.c_void_p),
    ]

BTN_META = {
    ID_EZI_DESK:       ('ComfyUI EZi',     'desk'),
    ID_KITCHEN_DESK:   ('KitchenAttn',     'desk'),
    ID_SAGE_DESK:      ('SageAttn',        'desk'),
    ID_FLASH_DESK:     ('FlashAttn',       'desk'),
    ID_EZI_BROW:       ('ComfyUI EZi',     'brow'),
    ID_KITCHEN_BROW:   ('KitchenAttn',     'brow'),
    ID_SAGE_BROW:      ('SageAttn',        'brow'),
    ID_FLASH_BROW:     ('FlashAttn',       'brow'),
    ID_UPD_COMFY:      ('ComfyUI Stable',  'upd'),
    ID_SC_UPD_COMFY:   ('ComfyUI Latest',  'upd'),
    ID_UPD_COMFY_NODE: ('ComfyUI + Nodes', 'upd'),
    ID_UPD_EASY:       ('Easy-Install',    'upd'),
    ID_CLOSE:          ('\u2715',          'close'),
    ID_VERSION:        ('v' + VERSION,     'version'),
    ID_MODE_BROWSER:   ('BROWSER',         'modebrow'),
    ID_MODE_HYBRID:    ('HYBRID',          'modehyb'),
    ID_FOLD_OUTPUT:    ('Output',          'fld'),
    ID_FOLD_INPUT:     ('Input',           'fld'),
    ID_FOLD_WORKFLOWS: ('Workflows',       'fld'),
    ID_FOLD_MODELS:    ('Models',          'fld'),
}

INSTALL_BTN_STATE = {
    ID_SAGE_DESK:  lambda: not HAS_DESK_SAGE,
    ID_FLASH_DESK: lambda: not HAS_DESK_FLASH,
    ID_SAGE_BROW:  lambda: not HAS_BROW_SAGE,
    ID_FLASH_BROW: lambda: not HAS_BROW_FLASH,
}

def is_install_state(btn_id):
    fn = INSTALL_BTN_STATE.get(btn_id)
    return fn() if fn else False

DIMMED_BTN_STATE = {
    ID_UPD_COMFY:      lambda: not HAS_UPD_COMFY,
    ID_UPD_COMFY_NODE: lambda: not HAS_UPD_COMFY_NODE,
    ID_UPD_EASY:       lambda: not HAS_UPD_EASY,
    ID_SC_UPD_COMFY:   lambda: not HAS_UPD_COMFY_NIGHTLY,
    ID_KITCHEN_DESK:   lambda: not HAS_DESK_KITCHEN,
    ID_KITCHEN_BROW:   lambda: not HAS_BROW_KITCHEN,
}

def is_dimmed_state(btn_id):
    fn = DIMMED_BTN_STATE.get(btn_id)
    return fn() if fn else False

def get_brush(c):
    if c not in g_brushes:
        g_brushes[c] = make_solid_brush(c)
    return g_brushes[c]


def _find_bat_comfy_line(bat_content):
    lines = bat_content.splitlines()
    logical_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        while line.rstrip('\r').rstrip().endswith('^') and i + 1 < len(lines):
            line = line.rstrip('\r').rstrip()[:-1] + ' ' + lines[i + 1].lstrip()
            i += 1
        logical_lines.append(line)
        i += 1
    for line in logical_lines:
        stripped = line.strip()
        if stripped.startswith('::') or re.match(r'(?i)^rem(\s|$)', stripped):
            continue
        if (re.search(r'python_embeded[/\\]python\.exe', stripped, re.IGNORECASE) and
                re.search(r'(?:ComfyUI[/\\]main|amd[/\\]runtime)\.py', stripped, re.IGNORECASE)):
            return stripped
    return None


def _get_bat_file():
    bat_arg = sys.argv[1] if len(sys.argv) > 1 else 'Start ComfyUI.bat'
    return bat_arg if os.path.isabs(bat_arg) else os.path.join(ROOT_DIR, bat_arg)


def _get_comfy_user_dir():
    bat_file = _get_bat_file()
    user_dir = None
    if os.path.exists(bat_file):
        try:
            with open(bat_file, 'r', encoding='utf-8', errors='replace') as f:
                bat_content = f.read()
            m_env = re.search(r'(?i)set\s+"?COMFY_USER_DIR=([^"\n]+)"?', bat_content)
            if m_env:
                user_dir = m_env.group(1).strip().strip('"')
            else:
                comfy_line = _find_bat_comfy_line(bat_content)
                if comfy_line:
                    m = re.search(r'python_embeded[/\\]python\.exe["\'"]?\s+(.*)',
                                  comfy_line, re.IGNORECASE)
                    if m:
                        tokens = shlex.split(m.group(1).strip(), posix=False)
                        for i, tok in enumerate(tokens):
                            if tok == '--user-directory' and i + 1 < len(tokens):
                                user_dir = tokens[i + 1].strip('"\'')
                                break
        except Exception:
            pass
    if user_dir:
        if not os.path.isabs(user_dir):
            user_dir = os.path.normpath(os.path.join(ROOT_DIR, user_dir))
        return os.path.join(user_dir, 'default')
    return os.path.join(ROOT_DIR, 'ComfyUI', 'user', 'default')


def _resolve_output_dir():
    bat_file = _get_bat_file()
    output_dir = None
    try:
        if os.path.exists(bat_file):
            with open(bat_file, 'r', encoding='utf-8', errors='replace') as f:
                bat_content = f.read()
            m_env = re.search(r'(?i)set\s+"?COMFY_OUTPUT_DIR=([^"\n]+)"?', bat_content)
            if m_env:
                output_dir = m_env.group(1).strip().strip('"')
            m_arg = re.search(r'python_embeded[/\\]python\.exe["\'"]?\s+(.*)',
                              _find_bat_comfy_line(bat_content) or '', re.IGNORECASE)
            if m_arg:
                parsed = shlex.split(m_arg.group(1).strip(), posix=False)
                for idx, tok in enumerate(parsed):
                    if tok == '--output-directory' and idx + 1 < len(parsed):
                        output_dir = parsed[idx + 1].strip('"\'')
                        break
    except Exception:
        pass
    if not output_dir:
        output_dir = os.path.normpath(os.path.join(ROOT_DIR, 'ComfyUI', 'output'))
    output_dir = os.path.normpath(output_dir)
    return output_dir if os.path.isdir(output_dir) else None


def _resolve_input_dir():
    bat_file = _get_bat_file()
    try:
        if os.path.exists(bat_file):
            with open(bat_file, 'r', encoding='utf-8', errors='replace') as f:
                bat_content = f.read()
            m_env = re.search(r'(?i)set\s+"?COMFY_INPUT_DIR=([^"\n]+)"?', bat_content)
            if m_env:
                d = m_env.group(1).strip().strip('"')
                if not os.path.isabs(d):
                    d = os.path.normpath(os.path.join(ROOT_DIR, d))
                return d if os.path.isdir(d) else None
            comfy_line = _find_bat_comfy_line(bat_content)
            if comfy_line:
                m = re.search(r'python_embeded[/\\]python\.exe["\'"]?\s+(.*)',
                              comfy_line, re.IGNORECASE)
                if m:
                    tokens = shlex.split(m.group(1).strip(), posix=False)
                    for i, tok in enumerate(tokens):
                        if tok == '--input-directory' and i + 1 < len(tokens):
                            d = tokens[i + 1].strip('"\'')
                            if not os.path.isabs(d):
                                d = os.path.normpath(os.path.join(ROOT_DIR, d))
                            return d if os.path.isdir(d) else None
    except Exception:
        pass
    d = os.path.normpath(os.path.join(ROOT_DIR, 'ComfyUI', 'input'))
    return d if os.path.isdir(d) else None


def _resolve_workflows_dir():
    user_dir = _get_comfy_user_dir()
    d = os.path.join(user_dir, 'workflows')
    return d if os.path.isdir(d) else None


def _resolve_models_dir():
    yaml_path = os.path.normpath(
        os.path.join(ROOT_DIR, 'ComfyUI', 'extra_model_paths.yaml'))
    if os.path.exists(yaml_path):
        try:
            with open(yaml_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            base_path = None
            m_base = re.search(r'^\s+base_path\s*:\s*(.+)$', content, re.MULTILINE)
            if m_base:
                base_path = m_base.group(1).strip().strip('"\'').rstrip('/\\')
            if base_path:
                parent_votes = {}
                for line in content.splitlines():
                    stripped = line.strip()
                    if (not stripped or stripped.startswith('#')
                            or re.match(r'(?i)base_path\s*:', stripped)
                            or re.match(r'(?i)is_default\s*:', stripped)):
                        continue
                    m_kv = re.match(r'^(\s{2,})\S[^:]+:\s*(.+)$', line)
                    if not m_kv:
                        continue
                    raw_val = m_kv.group(2).strip().strip('"\'').rstrip('/\\')
                    if not raw_val:
                        continue
                    if os.path.isabs(raw_val):
                        parent = os.path.normpath(os.path.dirname(raw_val))
                    else:
                        first_component = raw_val.replace('/', '\\').split('\\')[0]
                        parent = os.path.normpath(
                            os.path.join(base_path, first_component))
                    if os.path.isdir(parent):
                        parent_votes[parent] = parent_votes.get(parent, 0) + 1
                if parent_votes:
                    return max(parent_votes, key=lambda p: parent_votes[p])
        except Exception:
            pass
    d = os.path.normpath(os.path.join(ROOT_DIR, 'ComfyUI', 'models'))
    return d if os.path.isdir(d) else None


def _load_custom_browser():
    settings_path = os.path.join(SCRIPT_DIR, 'ComfyUI-EZi.settings.json')
    try:
        if os.path.exists(settings_path):
            import json
            with open(settings_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            cb = data.get('custom_file_browser', '').strip()
            if cb and os.path.isfile(cb):
                return cb
    except Exception:
        pass
    return None


def _settings_path():
    return os.path.join(SCRIPT_DIR, 'ComfyUI-EZi.settings.json')


def _open_folder(path):
    if path and os.path.isdir(path):
        try:
            custom = _load_custom_browser()
            if custom:
                subprocess.Popen([custom, path])
            else:
                os.startfile(path)
        except Exception:
            pass


def open_folder_async(resolver):
    threading.Thread(target=lambda: _open_folder(resolver()), daemon=True).start()


def launch_ezi(adv=False):
    pythonw = os.path.join(ROOT_DIR, 'python_embeded', 'pythonw.exe')
    if not os.path.exists(pythonw):
        pythonw = re.sub(r'(?i)python\.exe$', 'pythonw.exe', sys.executable)
    cmd = [pythonw, EZI_PY]
    if adv:
        cmd.append('--advanced-console')
    subprocess.Popen(cmd, cwd=SCRIPT_DIR, creationflags=0x8)
    user32.PostMessageW(g_hwnd, WM_APP_CLOSE, 0, 0)


def launch_bat(name):
    bat = root(name)
    if os.path.exists(bat):
        subprocess.Popen([bat], cwd=ROOT_DIR,
                          creationflags=subprocess.CREATE_NEW_CONSOLE)
    user32.PostMessageW(g_hwnd, WM_APP_CLOSE, 0, 0)


def launch_ezi_with_bat(bat_name, adv=False):
    pythonw = os.path.join(ROOT_DIR, 'python_embeded', 'pythonw.exe')
    cmd = [pythonw, EZI_PY, bat_name]
    if adv:
        cmd.append('--advanced-console')
    subprocess.Popen(cmd, cwd=SCRIPT_DIR, creationflags=0x8)
    user32.PostMessageW(g_hwnd, WM_APP_CLOSE, 0, 0)


def launch_brow(name):
    if not g_adv:
        launch_bat(name)
    elif name == 'Start ComfyUI.bat':
        launch_ezi(adv=True)
    else:
        launch_ezi_with_bat(name, adv=True)


def install_addon(bat_path):
    if os.path.exists(bat_path):
        bat_dir = os.path.dirname(bat_path)
        subprocess.Popen([bat_path], cwd=bat_dir,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
    user32.PostMessageW(g_hwnd, WM_APP_CLOSE, 0, 0)


def triton_enabled():
    try:
        with open(root('Start ComfyUI.bat'), encoding='utf-8') as handle:
            args = handle.read()
        return '--enable-triton-backend' in args and '--disable-triton-backend' not in args
    except OSError:
        return False


def triton_label():
    return 'Triton: On' if triton_enabled() else 'Triton: Off'


def toggle_triton():
    try:
        result = subprocess.run(
            [root('python_embeded/python.exe'), root('amd/windows_tools.py'), 'triton'],
            cwd=ROOT_DIR, capture_output=True, text=True,
            timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as error:
        user32.MessageBoxW(g_hwnd, str(error), 'Triton Toggle Failed', 0x10)
        return
    message = (result.stdout + result.stderr).strip()
    if result.returncode:
        # Show the tool's own message (e.g. "ComfyUI is running"), not just the exit status.
        user32.MessageBoxW(g_hwnd, message[-1500:] or f'Exit code {result.returncode}', 'Triton Toggle Failed', 0x10)
        return
    spec = list(g_control_specs[ID_TRITON]); spec[4] = triton_label(); g_control_specs[ID_TRITON] = tuple(spec)
    user32.SetWindowTextW(g_controls[ID_TRITON], spec[4])
    user32.InvalidateRect(g_controls[ID_TRITON], None, False)
    user32.MessageBoxW(g_hwnd, message, 'Triton Backend', 0x40)


ACTIONS = {
    ID_TRITON:     lambda: toggle_triton(),
    ID_VERSION:    lambda: os.startfile('https://github.com/BoomerCyb/ComfyUI-Easy-Install-AMD'),
    ID_EZI_DESK:   lambda: launch_ezi(),
    ID_EZI_BROW:   lambda: launch_brow('Start ComfyUI.bat'),

    ID_KITCHEN_DESK: lambda: launch_ezi_with_bat('Start ComfyUI KitchenAttention.bat'),
    ID_KITCHEN_BROW: lambda: launch_brow('Start ComfyUI KitchenAttention.bat'),

    ID_SAGE_DESK:  (
        (lambda: launch_ezi_with_bat('Start ComfyUI SageAttention.bat'))
        if HAS_DESK_SAGE
        else (lambda: install_addon(INSTALL_SAGE_BAT))
    ),
    ID_FLASH_DESK: (
        (lambda: launch_ezi_with_bat('Start ComfyUI FlashAttention.bat'))
        if HAS_DESK_FLASH
        else (lambda: install_addon(INSTALL_FLASH_BAT))
    ),
    ID_SAGE_BROW:  (
        (lambda: launch_brow('Start ComfyUI SageAttention.bat'))
        if HAS_BROW_SAGE
        else (lambda: install_addon(INSTALL_SAGE_BAT))
    ),
    ID_FLASH_BROW: (
        (lambda: launch_brow('Start ComfyUI FlashAttention.bat'))
        if HAS_BROW_FLASH
        else (lambda: install_addon(INSTALL_FLASH_BAT))
    ),

    ID_UPD_COMFY:      lambda: launch_bat('Update ComfyUI.bat'),
    ID_UPD_COMFY_NODE: lambda: launch_bat('Update ComfyUI and Nodes.bat'),
    ID_UPD_EASY:       lambda: launch_bat('Update Easy-Install.bat'),
    ID_SC_UPD_COMFY:   lambda: launch_bat('Update ComfyUI Nightly.bat'),

    ID_FOLD_OUTPUT:    lambda: open_folder_async(_resolve_output_dir),
    ID_FOLD_INPUT:     lambda: open_folder_async(_resolve_input_dir),
    ID_FOLD_WORKFLOWS: lambda: open_folder_async(_resolve_workflows_dir),
    ID_FOLD_MODELS:    lambda: open_folder_async(_resolve_models_dir),
}


def create_shortcut(sc_btn_id):
    meta = SHORTCUT_META.get(sc_btn_id)
    if not meta:
        return
    main_id, ico_name, label = meta

    if main_id == ID_EZI_DESK:
        target   = sys.executable
        args     = '"{}"'.format(EZI_PY)
        work_dir = SCRIPT_DIR
    elif main_id in (ID_SAGE_DESK, ID_FLASH_DESK, ID_KITCHEN_DESK):
        pythonw  = os.path.join(ROOT_DIR, 'python_embeded', 'pythonw.exe')
        bat_map_desk = {
            ID_SAGE_DESK:    'Start ComfyUI SageAttention.bat',
            ID_FLASH_DESK:   'Start ComfyUI FlashAttention.bat',
            ID_KITCHEN_DESK: 'Start ComfyUI KitchenAttention.bat',
        }
        target   = pythonw
        args     = '"{}" "{}"'.format(EZI_PY, bat_map_desk[main_id])
        work_dir = SCRIPT_DIR
    else:
        bat_map = {
            ID_EZI_BROW:     'Start ComfyUI.bat',
            ID_SAGE_BROW:    'Start ComfyUI SageAttention.bat',
            ID_FLASH_BROW:   'Start ComfyUI FlashAttention.bat',
            ID_KITCHEN_BROW: 'Start ComfyUI KitchenAttention.bat',
        }
        if g_adv:
            if main_id == ID_EZI_BROW:
                target = sys.executable
                args   = '"{}" --advanced-console'.format(EZI_PY)
            else:
                target = os.path.join(ROOT_DIR, 'python_embeded', 'pythonw.exe')
                args   = '"{}" "{}" --advanced-console'.format(EZI_PY, bat_map[main_id])
            work_dir = SCRIPT_DIR
            label    = label + ' HYBRID'
        else:
            target   = os.path.join(ROOT_DIR, bat_map[main_id])
            args     = ''
            work_dir = ROOT_DIR

    ico_path = os.path.join(SCRIPT_DIR, ico_name)

    import win32com.client
    shell = win32com.client.Dispatch('WScript.Shell')
    desktop = shell.SpecialFolders('Desktop')
    shortcut = shell.CreateShortcut(os.path.join(desktop, label + '.lnk'))
    shortcut.TargetPath = target
    shortcut.Arguments = args
    shortcut.WorkingDirectory = work_dir
    shortcut.IconLocation = ico_path + ',0'
    shortcut.Save()
    user32.PostMessageW(g_hwnd, WM_APP_CLOSE, 0, 0)

LOGO_PNG = (
    'iVBORw0KGgoAAAANSUhEUgAAAMAAAADABAMAAACg8nE0AAAAMFBMVEWC382C382C382C382C382C382C382C382C382C382C382C382C'
    '382C382C382C380xhxc0AAAAEHRSTlMAESIzRFVmd4iZqrvM3e7/dpUBFQAABBdJREFUeNrtm01rE0EYxyeTxJRYTARvvayCCEVoPHhR'
    'L4JXNSi96EE/QvEsFPwE/Qi5eBDFWnr0El9yUarRm1ClB70JjUppqV3HQ7pNNjuzz3/myWi185zSZXZ++5v33c4IYRUnH726JjzGaaWU'
    '6vjLv6qUUkq1vAHe9gE7ngWUansC3EoAmxY3FSzSKpe7JJ60PPjZ9FsFviqhNgD0vBSRW0jfd7kBfv2bRfRz8POJF8CWE8BhrFNKeSrO'
    'mST/DU+ASgKY89Ui5vv5b3trcuU+oOmvUVfsC6hg2W2ui9dr4mBFqojk7GykSfPhpuHmG/c1F1cePDQVYnnQVdOxmdtqs3GH6EfZ0E6R'
    'k+b0rZxGro2d/KEpG7quspiTXtf2K3npt62E9bN8LfeGdmY+eIGuibC10YVRQLWRP0bYAoot07rTEJqFZH5sjHQ0ZT1mgXfsFlGVSB1n'
    'L1HzcisFKOMrChTQTAHmxg+o2NSYru9XFdQu+lUhY4d5iarl42uDIioSaX/oLjaImxpDdUCs7+IjuqvviFqI4PLcjAwT9F1sOBoe6Sxe'
    'XcgXobbv5ftwHRTFPnuFCoAACIADBijlzmN1KI91Z4BcgQj3FlwB8e1nCKDuXgcdaALquQPiq54NQAUGAFPg9AO2AgVgK5A9matAArgK'
    '9FjEVKABTAVgNOUpAACeAjIfsBQQAEsBmtE4ChCAo4DNyQwFDMBQAFcV7gogwF0BXRc5K5TAdPHZ9LvsxPKYAWJ1NfXn4bD4DYB9CKh7'
    'BpQWPAPORX4BxaWeX8D5ut9KLi55bkXuAhiAIYABGAIQgCMAATgCCIAlgACm6n4BhSXPo+lUwy+gsCz8ApgCJIArQAK4AhSALUAB2AIE'
    'gC9ALH6HBI5d2vv5tTu2z5pDAuef7v28KITY6tXHUESHtDXwuW3zyiOtN76oy1avPPZLxy9dq7c2a8CuAKwgHQVgBekqgCpIVwFUQToL'
    'gArSWQBUkO4CmIId4GXX+guGFSC+Yv8FwwqQyQ9QsAFosqMVJEcAUZAsAUBBsgQABckToBUkT4BWkNh2/ZyMOr3eWKZMY1HEzbrzqkKt'
    'IyXROUM/ZC15vG/ppzk6YMGfEkbyKrn/Izd88QqA/wwQiz+1r6I8mwwNjy0zOpVscJ1IrnTz99lZr7oN+yOlaTNmyy7/yeylYQMJ7xY3'
    'hWZTdURsB206nd4wFbLmAb4Ll7Nwpr3dM4pQFMjZDd0D7na0j5q73uOAac21N+n+pjgKZeDuxZy92S41kNleX1PuDamCbMeXFicnoIMF'
    'kfGgE3lyAjpYkG3kUjkWkv7kRWQ4uetQSIuwuvZQynOBniED2t88fCCF2FBt9J62roYKeQxn5JvTCU0mn3IAtulDhAgRIkSIECFChPh7'
    '8RvLWl3uOMlp8QAAAABJRU5ErkJggg=='
)

import base64
import tempfile
import zlib

P = ctypes.c_void_p
I = ctypes.c_int
U = ctypes.c_uint
F = ctypes.c_float

def _bind(lib, name, result, *args):
    fn = getattr(lib, name)
    fn.restype, fn.argtypes = result, list(args)
    return fn

for name, result, args in [
    ('CreateWindowExW', P, [U, wt.LPCWSTR, wt.LPCWSTR, U, I,I,I,I,P,P,P,P]),
    ('GetDC', P, [P]), ('ReleaseDC', I, [P,P]),
    ('BeginPaint', P, [P, ctypes.POINTER(PAINTSTRUCT)]),
    ('EndPaint', I, [P, ctypes.POINTER(PAINTSTRUCT)]),
    ('LoadCursorW', P, [P,P]), ('DestroyWindow', I, [P]),
    ('PostMessageW', I, [P,U,WPARAM,LPARAM]),
    ('InvalidateRect', I, [P,P,I]), ('GetClientRect', I, [P,ctypes.POINTER(wt.RECT)]),
    ('GetWindowRect', I, [P,ctypes.POINTER(wt.RECT)]),
    ('SetWindowTextW', I, [P,wt.LPCWSTR]), ('EnableWindow', I, [P,I]),
    ('SetWindowPos', I, [P,P,I,I,I,I,U]),
    ('IsWindowEnabled', I, [P]), ('GetFocus', P, []),
    ('ShowWindow', I, [P,I]), ('UpdateWindow', I, [P]),
    ('SetForegroundWindow', I, [P]), ('SetWindowRgn', I, [P,P,I]),
    ('TrackMouseEvent', I, [ctypes.POINTER(TRACKMOUSEEVENT)]),
    ('DrawTextW', I, [P,wt.LPCWSTR,I,ctypes.POINTER(wt.RECT),U]),
    ('CreatePopupMenu', P, []), ('AppendMenuW', I, [P,U,ctypes.c_size_t,wt.LPCWSTR]),
    ('TrackPopupMenu', U, [P,U,I,I,I,P,P]), ('DestroyMenu', I, [P]),
    ('IsDialogMessageW', I, [P,ctypes.POINTER(wt.MSG)]),
    ('GetNextDlgTabItem', P, [P,P,I]), ('GetKeyState', ctypes.c_short, [I]),
    ('MessageBoxW', I, [P,wt.LPCWSTR,wt.LPCWSTR,U]),
    ('GetMessageW', I, [ctypes.POINTER(wt.MSG),P,U,U]),
    ('TranslateMessage', I, [ctypes.POINTER(wt.MSG)]),
    ('DispatchMessageW', LRESULT, [ctypes.POINTER(wt.MSG)]),
    ('RegisterClassExW', wt.ATOM, [ctypes.POINTER(WNDCLASSEX)]),
    ('SetTimer', P, [P,P,U,P]), ('KillTimer', I, [P,P]),
]:
    _bind(user32, name, result, *args)
_bind(kernel32, 'GetModuleHandleW', P, wt.LPCWSTR)
for name, result, args in [
    ('CreateCompatibleDC', P, [P]), ('CreateCompatibleBitmap', P, [P,I,I]),
    ('SelectObject', P, [P,P]), ('DeleteObject', I, [P]), ('DeleteDC', I, [P]),
    ('CreateFontIndirectW', P, [ctypes.POINTER(LOGFONT)]),
    ('CreateSolidBrush', P, [U]), ('SetBkMode', I, [P,I]), ('SetTextColor', U, [P,U]),
    ('BitBlt', I, [P,I,I,I,I,P,I,I,U]),
    ('CreateRoundRectRgn', P, [I,I,I,I,I,I]),
]:
    _bind(gdi32, name, result, *args)

gp = ctypes.windll.gdiplus
class GPSTART(ctypes.Structure):
    _fields_ = [('version', U), ('callback', P), ('no_thread', I), ('no_codecs', I)]
class GPRECT(ctypes.Structure):
    _fields_ = [('x', F), ('y', F), ('width', F), ('height', F)]

for name, args in [
    ('GdiplusStartup', [ctypes.POINTER(P),ctypes.POINTER(GPSTART),P]),
    ('GdipCreateFromHDC', [P,ctypes.POINTER(P)]), ('GdipDeleteGraphics', [P]),
    ('GdipSetSmoothingMode', [P,I]), ('GdipSetInterpolationMode', [P,I]),
    ('GdipCreateSolidFill', [U,ctypes.POINTER(P)]), ('GdipDeleteBrush', [P]),
    ('GdipCreateLineBrushFromRect', [ctypes.POINTER(GPRECT),U,U,I,I,ctypes.POINTER(P)]),
    ('GdipCreatePen1', [U,F,I,ctypes.POINTER(P)]), ('GdipDeletePen', [P]),
    ('GdipCreatePath', [I,ctypes.POINTER(P)]), ('GdipDeletePath', [P]),
    ('GdipAddPathArc', [P,F,F,F,F,F,F]), ('GdipClosePathFigure', [P]),
    ('GdipAddPathLine', [P,F,F,F,F]),
    ('GdipAddPathBezier', [P,F,F,F,F,F,F,F,F]),
    ('GdipFillPath', [P,P,P]), ('GdipDrawPath', [P,P,P]),
    ('GdipFillRectangle', [P,P,F,F,F,F]),
    ('GdipDrawLine', [P,P,F,F,F,F]),
    ('GdipDrawEllipse', [P,P,F,F,F,F]), ('GdipFillEllipse', [P,P,F,F,F,F]),
    ('GdipLoadImageFromFile', [wt.LPCWSTR,ctypes.POINTER(P)]),
    ('GdipDrawImageRect', [P,P,F,F,F,F]), ('GdipDisposeImage', [P]), ('GdipSetLineWrapMode', [P,I]),
]:
    _bind(gp, name, I, *args)
_bind(gp, 'GdiplusShutdown', None, P)

def color(hexcode, alpha=255):
    return (alpha << 24) | int(hexcode.lstrip('#'), 16)

THEMES = {
    'dark': {
        'bg': '#0c0e12', 'bar-bg': '#161b22', 'border': '#21262d', 'border2': '#30363d', 'border3': '#484f58',
        'btn-bg': '#21262d', 'btn-bg2': '#2d333b', 'input-bg': '#0d1117', 'modal-bg': '#161b22',
        'hover-row': '#1c2128', 'text': '#cccccc', 'text2': '#8b949e', 'text3': '#e6edf3',
        'accent': '#388bfd', 'accent-hover': '#58a6ff', 'accent-bg': '#0d419d', 'accent-bg-hover': '#1158c7',
    },
    'pixaroma': {
        'bg': '#111111', 'bar-bg': '#1a1a1a', 'border': '#252525', 'border2': '#2e2e2e', 'border3': '#444444',
        'btn-bg': '#222222', 'btn-bg2': '#2a2a2a', 'input-bg': '#0d0d0d', 'modal-bg': '#1a1a1a',
        'hover-row': '#1f1f1f', 'text': '#cccccc', 'text2': '#888888', 'text3': '#e0e0e0',
        'accent': '#e8530a', 'accent-hover': '#ff7040', 'accent-bg': '#6e2200', 'accent-bg-hover': '#8a3000',
    },
    'aurora': {
        'bg': '#0b1926', 'bar-bg': '#102638', 'border': '#304659', 'border2': '#3b566f', 'border3': '#49758a',
        'btn-bg': '#22374b', 'btn-bg2': '#304b63', 'input-bg': '#09232d', 'modal-bg': '#122438',
        'hover-row': '#203649', 'text': '#edf3ff', 'text2': '#a1b3cc', 'text3': '#edf3ff',
        'accent': '#82dfcd', 'accent-hover': '#9be9d9', 'accent-bg': '#224c56', 'accent-bg-hover': '#2b616c',
    },
    'amd': {
        'bg': '#000000', 'bar-bg': '#121212', 'border': '#262626', 'border2': '#333333', 'border3': '#404040',
        'btn-bg': '#1a1a1a', 'btn-bg2': '#262626', 'input-bg': '#000000', 'modal-bg': '#0d0d0d',
        'hover-row': '#1c1c1c', 'text': '#e6e6e6', 'text2': '#a6a6a6', 'text3': '#ffffff',
        'accent': '#ed1c24', 'accent-hover': '#ff4d53', 'accent-bg': '#5c0b0e', 'accent-bg-hover': '#7a0f13',
    },
    'light': {
        'bg': '#f0f2f5', 'bar-bg': '#dde1e7', 'border': '#c8cdd5', 'border2': '#b0b7c0', 'border3': '#8a9199',
        'btn-bg': '#e2e6eb', 'btn-bg2': '#d0d5dc', 'input-bg': '#ffffff', 'modal-bg': '#ffffff',
        'hover-row': '#d8dce3', 'text': '#24292f', 'text2': '#57606a', 'text3': '#1c2026',
        'accent': '#0969da', 'accent-hover': '#0550ae', 'accent-bg': '#0969da', 'accent-bg-hover': '#0550ae',
    },
}

AURORA_EXACT = {
    'row_border': '#334d61', 'icon_bg': '#293e54', 'install': '#192d40', 'dark': '#09232d',
    'secondary': '#224c56', 'p1': '#94e4d3', 'p2': '#70d2c3', 'p_hover': '#9be9d9',
    'disabled': '#65768b', 'hover_stroke': '#7b9bb6', 'focus': '#e3f8f4', 'g1': '#153b4b', 'g2': '#45426b',
}

# AMD Red #ED1C24 on Black, with White text and Dark Gray #404040
AMD_EXACT = {
    'p1': '#ed1c24', 'p2': '#b5141a', 'p_hover': '#ff3d44', 'dark': '#ffffff', 'secondary': '#ffd6d7',
    'focus': '#ffffff', 'g1': '#3b0709', 'g2': '#1a1a1a', 'icon_bg': '#262626', 'row_border': '#333333',
}

def _hex_ok(value):
    m = re.fullmatch(r'#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})', str(value).strip())
    if not m: return None
    h = m.group(1)
    if len(h) == 3: h = ''.join(c*2 for c in h)
    return '#' + h.lower()

def _rgb(h):
    return tuple(int(h[i:i+2], 16) for i in (1, 3, 5))

def _lum(h):
    r, g, b = [c/255 for c in _rgb(h)]
    return 0.2126*r + 0.7152*g + 0.0722*b

def _mix(a, b, t):
    return '#%02x%02x%02x' % tuple(round(x + (y-x)*t) for x, y in zip(_rgb(a), _rgb(b)))

def _blend(a, b, t):
    ra, rb = _rgb(a), _rgb(b)
    return '#%02x%02x%02x' % tuple(int(x*(1-t) + y*t) for x, y in zip(ra, rb))

def _gamma_lum(h):
    def lin(c): return c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4
    r, g, b = [lin(c/255) for c in _rgb(h)]
    return 0.2126*r + 0.7152*g + 0.0722*b

def _builtin_palette(pid):
    site = os.path.join(ROOT_DIR, 'python_embeded', 'Lib', 'site-packages')
    try:
        for pkg in sorted(os.listdir(site)):
            if not pkg.startswith('comfyui_frontend_package') or 'dist-info' in pkg: continue
            pdir = os.path.join(site, pkg, 'static', 'assets', 'palettes')
            if not os.path.isdir(pdir): continue
            for fn in os.listdir(pdir):
                if not fn.endswith('.json'): continue
                try:
                    with open(os.path.join(pdir, fn), encoding='utf-8', errors='replace') as f: d = json.load(f)
                except (OSError, ValueError): continue
                if d.get('id') == pid and d.get('colors'): return d['colors']
    except OSError: pass
    return {}

def _comfy_theme_fallback():
    try:
        path = os.path.join(_get_comfy_user_dir(), 'comfy.settings.json')
        with open(path, encoding='utf-8', errors='replace') as f: data = json.load(f)
        pid = data.get('Comfy.ColorPalette', '') or 'dark'
        custom = data.get('Comfy.CustomColorPalettes', {})
        colors = custom[pid].get('colors', {}) if isinstance(custom, dict) and pid in custom else _builtin_palette(pid)
        cb, lg = colors.get('comfy_base', {}), colors.get('litegraph_base', {})
        def c(k, fb=''): return _hex_ok(cb.get(k, '')) or fb
        def l(k, fb=''): return _hex_ok(lg.get(k, '')) or fb
        bg = c('bg-color', '#202020')
        menu_bg = c('comfy-menu-bg', bg)
        input_bg = c('comfy-input-bg', bg)
        fg = c('fg-color', '#cccccc')
        border = c('border-color', '#444444')
        lg_bg = l('CLEAR_BACKGROUND_COLOR', bg)
        node_bg = l('NODE_DEFAULT_BGCOLOR', menu_bg)
        node_title = l('NODE_TITLE_COLOR', fg)
        accent = l('NODE_BOX_OUTLINE_COLOR', c('border-color', '#388bfd'))
        lum = _gamma_lum(accent)
        if lum > 0.80 or lum < 0.05:
            link = l('LINK_COLOR', '')
            if link and 0.05 <= _gamma_lum(link) <= 0.80:
                accent, lum = link, _gamma_lum(link)
        target = '#000000' if lum >= 0.18 else '#ffffff'
        return {
            'bg': lg_bg, 'bar-bg': menu_bg, 'border': border, 'border2': border, 'border3': border,
            'btn-bg': node_bg, 'btn-bg2': node_bg, 'input-bg': input_bg, 'modal-bg': menu_bg,
            'hover-row': lg_bg, 'text': fg, 'text2': node_title, 'text3': fg,
            'accent': accent, 'accent-hover': _blend(accent, '#ffffff', .30),
            'accent-bg': _blend(accent, target, .60), 'accent-bg-hover': _blend(accent, target, .45),
        }
    except (OSError, ValueError, AttributeError, KeyError, TypeError):
        return {}

def _load_theme():
    name, extra = 'amd', {}
    try:
        with open(_settings_path(), encoding='utf-8') as f: data = json.load(f)
        name = data.get('theme', 'amd')
        lt = data.get('launcher_theme', 'amd')
        if lt != 'follow':
            name = lt if lt in THEMES or lt == 'comfyui' else 'amd'
        if name == 'comfyui':
            saved = data.get('comfy_theme_vars') or data.get('comfyThemeVars')
            extra = saved if isinstance(saved, dict) and saved else _comfy_theme_fallback()
    except (OSError, ValueError, AttributeError): pass
    v = dict(THEMES.get(name, THEMES['amd']))
    for k, val in extra.items():
        h = _hex_ok(val)
        if h: v[str(k).lstrip('-')] = h
    return name, v

def _derive_theme(name, v):
    acc = v['accent']
    light_acc = _lum(acc) >= 0.35
    t = {
        'white': v['text3'], 'muted': v['text2'], 'mint': acc, 'border': v['border2'], 'border_outer': v['border3'],
        'sep': v['border'], 'bg': v['bg'], 'panel': v['bar-bg'], 'modal': v['modal-bg'], 'row': v['hover-row'],
        'row_border': v['border'], 'icon_bg': v['btn-bg'], 'btn': v['btn-bg'], 'btn_hover': v['btn-bg2'],
        'install': _mix(v['btn-bg'], v['bg'], .5),
        'dark': _mix(acc, '#000000', .85) if light_acc else '#ffffff',
        'secondary': _mix(acc, '#000000', .65) if light_acc else '#e6e6e6',
        'p1': _mix(acc, '#ffffff', .12), 'p2': _mix(acc, '#000000', .12), 'p_hover': _mix(acc, '#ffffff', .22),
        'disabled': _mix(v['text2'], v['bg'], .5), 'hover_stroke': _mix(v['border2'], v['text2'], .5),
        'focus': _mix(acc, '#ffffff', .8),
        'g1': _mix(v['bg'], acc, .18), 'g2': _mix(v['bg'], v['border3'], .45),
    }
    if name == 'aurora': t.update(AURORA_EXACT)
    if name == 'amd': t.update(AMD_EXACT)
    return t

def _tint_png(data, hexcolor):
    r, g, b = _rgb(hexcolor)
    out = bytearray(data[:8]); pos = 8
    while pos < len(data):
        n = int.from_bytes(data[pos:pos+4], 'big'); typ = data[pos+4:pos+8]; body = data[pos+8:pos+8+n]
        if typ == b'PLTE': body = bytes([r, g, b]) * (n // 3)
        out += n.to_bytes(4, 'big') + typ + body + (zlib.crc32(typ + body) & 0xffffffff).to_bytes(4, 'big')
        pos += 12 + n
    return bytes(out)

THEME_NAME, _THEME_VARS = _load_theme()
TC = _derive_theme(THEME_NAME, _THEME_VARS)
WHITE = color(TC['white'])
MUTED = color(TC['muted'])
MINT = color(TC['mint'])
BORDER = color(TC['border'])
DARK = color(TC['dark'])
g_mode = 'Desktop'
g_controls = {}
g_control_specs = {}
g_subclasses = []
g_tip_texts = []
g_scene_dc = None
g_scene_bitmap = None
g_scene_old = None
g_logo = P()
g_logo_path = None
g_token = P()
ID_MODE_DESKTOP = 52
ROW_IDS = [200, 201, 202, 203]
ROW_HIT_IDS = [220, 221, 222, 223]
SC_IDS = [210, 211, 212, 213]
ROW_NAMES = ['ComfyUI', 'Kitchen Attention', 'Sage Attention', 'Flash Attention']
ROW_ICONS = ['nodes', 'blocks', 'leaf', 'bolt']
UPDATE_DESCRIPTIONS = {
    ID_UPD_EASY: 'EZi and Add-ons',
    ID_UPD_COMFY: 'Latest stable release',
    ID_SC_UPD_COMFY: 'Latest development version',
    ID_UPD_COMFY_NODE: 'Stable + all custom nodes',
}
DESK_IDS = [ID_EZI_DESK, ID_KITCHEN_DESK, ID_SAGE_DESK, ID_FLASH_DESK]
BROW_IDS = [ID_EZI_BROW, ID_KITCHEN_BROW, ID_SAGE_BROW, ID_FLASH_BROW]

def source_id(index):
    return (DESK_IDS if g_mode == 'Desktop' else BROW_IDS)[index]

def available(bid):
    if is_dimmed_state(bid):
        return False
    if is_install_state(bid):
        installer = INSTALL_SAGE_BAT if bid in (ID_SAGE_DESK, ID_SAGE_BROW) else INSTALL_FLASH_BAT
        return os.path.isfile(installer)
    return True

def graphics(hdc):
    g = P()
    gp.GdipCreateFromHDC(hdc, ctypes.byref(g))
    gp.GdipSetSmoothingMode(g, 4)
    gp.GdipSetInterpolationMode(g, 7)
    return g

def rounded(g, x,y,w,h, fill, stroke=None, radius=10):
    path = P()
    gp.GdipCreatePath(0, ctypes.byref(path))
    r = min(radius, w/2, h/2)
    x,y,w,h,r = (value*UI_SCALE for value in (x,y,w,h,r))
    for xx, yy, angle in [(x,y,180), (x+w-2*r,y,270), (x+w-2*r,y+h-2*r,0), (x,y+h-2*r,90)]:
        gp.GdipAddPathArc(path, xx,yy,2*r,2*r,angle,90)
    gp.GdipClosePathFigure(path)
    if fill is not None:
        brush = P()
        if isinstance(fill,tuple):
            rect=GPRECT(x,y,w,h)
            gp.GdipCreateLineBrushFromRect(ctypes.byref(rect),fill[0],fill[1],1,0,ctypes.byref(brush))
        else: gp.GdipCreateSolidFill(fill,ctypes.byref(brush))
        gp.GdipFillPath(g,brush,path)
        gp.GdipDeleteBrush(brush)
    if stroke is not None:
        pen = P()
        gp.GdipCreatePen1(stroke,max(1,UI_SCALE),2,ctypes.byref(pen))
        gp.GdipDrawPath(g,pen,path)
        gp.GdipDeletePen(pen)
    gp.GdipDeletePath(path)

def text_at(hdc, text, x,y,w,h, font='body', col=WHITE, center=False):
    old = gdi32.SelectObject(hdc,g_fonts[font])
    gdi32.SetBkMode(hdc,1)
    rgb = col & 0xffffff
    gdi32.SetTextColor(hdc, ((rgb & 255)<<16) | (rgb & 0xff00) | (rgb>>16))
    rc = wt.RECT(sc(x),sc(y),sc(x+w),sc(y+h))
    user32.DrawTextW(hdc,text,-1,ctypes.byref(rc),DT_VCENTER|DT_SINGLELINE|0x800|(DT_CENTER if center else DT_LEFT))
    gdi32.SelectObject(hdc,old)

def icon(g, kind, x,y,size=24, col=MUTED):
    pen, brush = P(), P()
    gp.GdipCreatePen1(col, max(1.4,(2.6 if kind=='update' else 1.7)*UI_SCALE*size/24),2,ctypes.byref(pen))
    gp.GdipCreateSolidFill(col,ctypes.byref(brush))
    def pt(a,b): return sc(x+a*size/24), sc(y+b*size/24)
    def line(a,b,c,d): gp.GdipDrawLine(g,pen,*pt(a,b),*pt(c,d))
    def circle(a,b,r,filled=False):
        xx,yy=pt(a-r,b-r)
        (gp.GdipFillEllipse if filled else gp.GdipDrawEllipse)(g,brush if filled else pen,xx,yy,sc(2*r*size/24),sc(2*r*size/24))
    def poly(points, fill=False):
        path=P(); gp.GdipCreatePath(0,ctypes.byref(path))
        for a,b in zip(points,points[1:]): gp.GdipAddPathLine(path,*pt(*a),*pt(*b))
        if fill: gp.GdipClosePathFigure(path); gp.GdipFillPath(g,brush,path)
        else: gp.GdipDrawPath(g,pen,path)
        gp.GdipDeletePath(path)
    if kind in ('nodes','hybrid'):
        line(12,5,4,19); line(4,19,20,19); line(20,19,12,5)
        for a,b in [(12,5),(4,19),(20,19)]: circle(a,b,3,kind=='nodes')
    elif kind=='desktop':
        rounded(g,x+size/12,y+size/12,size*5/6,size*.6,None,col,2)
        line(12,17,12,21); line(7,22,17,22)
    elif kind=='browser':
        circle(12,12,10); line(2,12,22,12)
        gp.GdipDrawEllipse(g,pen,*pt(8,2),sc(size/3),sc(size*5/6))
    elif kind=='folder':
        poly([(2,6),(8,6),(11,9),(22,9),(22,21),(2,21),(2,6)])
    elif kind=='shortcut':
        poly([(11,4),(21,4),(21,14)]); line(9,16,21,4)
        poly([(8,7),(3,7),(3,22),(18,22),(18,17)])
    elif kind=='chevron': poly([(6,9),(12,15),(18,9)])
    elif kind=='close': line(5,5,19,19); line(19,5,5,19)
    elif kind=='update':
        for a in (-165,15):
            path=P(); gp.GdipCreatePath(0,ctypes.byref(path))
            gp.GdipAddPathArc(path,*pt(4,4),sc(16*size/24),sc(16*size/24),a,120)
            gp.GdipDrawPath(g,pen,path); gp.GdipDeletePath(path)
        poly([(20.84,9.52),(20.2,3.8),(15.11,8.89)],True)
        poly([(3.16,14.48),(3.8,20.2),(8.89,15.11)],True)
    elif kind=='blocks':
        for a,b in [(3,2),(3,11),(12,11),(12,20),(21,20)]:
            rounded(g,x+a*size/28,y+b*size/28,size/4,size/4,col,None,1)
    elif kind=='bolt': poly([(14,1),(3,14),(11,14),(8,23),(22,9),(13,9)],True)
    elif kind=='leaf':
        for coords in [((11,22),(1,20),(0,10),(2,6),(9,9),(13,16),(11,22)),
                       ((12,22),(10,10),(16,4),(23,2),(24,13),(19,21),(12,22))]:
            path=P(); gp.GdipCreatePath(0,ctypes.byref(path))
            a,b,c,d,e,f,h=coords
            gp.GdipAddPathBezier(path,*pt(*a),*pt(*b),*pt(*c),*pt(*d))
            gp.GdipAddPathBezier(path,*pt(*d),*pt(*e),*pt(*f),*pt(*h))
            gp.GdipClosePathFigure(path); gp.GdipFillPath(g,brush,path); gp.GdipDeletePath(path)
    gp.GdipDeletePen(pen); gp.GdipDeleteBrush(brush)

def _load_mode():
    try:
        with open(_settings_path(),encoding='utf-8') as f: data=json.load(f)
        value=data.get('launcher_mode','Desktop')
        return value if value in ('Desktop','Browser','Hybrid') else 'Desktop'
    except (OSError, ValueError, AttributeError): return 'Desktop'

def _save_mode():
    try:
        try:
            with open(_settings_path(),encoding='utf-8') as f: data=json.load(f)
        except (OSError,ValueError): data={}
        if not isinstance(data,dict): data={}
        data['launcher_mode']=g_mode
        with open(_settings_path(),'w',encoding='utf-8') as f: json.dump(data,f,indent=4,ensure_ascii=False)
    except OSError: pass

def paint_scene():
    global g_scene_dc,g_scene_bitmap,g_scene_old
    if not g_scene_dc:
        dc=user32.GetDC(g_hwnd)
        g_scene_dc=gdi32.CreateCompatibleDC(dc)
        g_scene_bitmap=gdi32.CreateCompatibleBitmap(dc,WIN_W,WIN_H)
        g_scene_old=gdi32.SelectObject(g_scene_dc,g_scene_bitmap)
        user32.ReleaseDC(g_hwnd,dc)
    dc=g_scene_dc
    g=graphics(dc)
    shift=-(time.time()%5)/5*2*WIN_W
    for first,last,direction,rect in [(color(TC['g1']),color(TC['g2']),0,GPRECT(shift,0,WIN_W,WIN_H)),
                                       (color(TC['bg'],0),color(TC['bg']),1,GPRECT(0,0,WIN_W,WIN_H))]:
        brush=P()
        gp.GdipCreateLineBrushFromRect(ctypes.byref(rect),first,last,direction,0,ctypes.byref(brush))
        if direction==0: gp.GdipSetLineWrapMode(brush,1)
        gp.GdipFillRectangle(g,brush,0,0,WIN_W,WIN_H)
        gp.GdipDeleteBrush(brush)
    rounded(g,1,1,670,418,None,color(TC['border_outer']),16)
    rounded(g,12,52,412,308,color(TC['panel'],150),BORDER,12)
    rounded(g,436,52,224,308,color(TC['modal'],130),BORDER,12)
    if g_logo: gp.GdipDrawImageRect(g,g_logo,sc(22),sc(10),sc(30),sc(30))
    gp.GdipDeleteGraphics(g)
    text_at(dc,'ComfyUI EZi',64,8,153,34,'title')
    text_at(dc,'Launcher - AMD',195,10,150,30,'heading',MUTED)
    old=gdi32.SelectObject(dc,g_fonts['title']); rc=wt.RECT()
    user32.DrawTextW(dc,'Update',-1,ctypes.byref(rc),0x400|DT_SINGLELINE); gdi32.SelectObject(dc,old)
    ux=448+(200-(rc.right/UI_SCALE+28))/2
    g=graphics(dc); icon(g,'update',ux,69,20,WHITE); gp.GdipDeleteGraphics(g)
    text_at(dc,'Update',ux+28,64,170,30,'title')
    for n,name in enumerate(ROW_NAMES):
        y=108+n*62
        bid=source_id(n)
        missing=is_install_state(bid)
        status='Not installed' if missing else ('Unavailable' if not available(bid) else ('Default' if n==0 else 'Ready'))
        g=graphics(dc)
        rounded(g,22,y,392,54,color(TC['row'],155),color(TC['row_border']),10)
        rounded(g,32,y+11,32,32,color(TC['icon_bg'],190),None,10)
        icon(g,ROW_ICONS[n],38,y+17,20,MINT)
        rounded(g,80,y+36,6,6,MINT if status in ('Default','Ready') else MUTED,None,3)
        gp.GdipDeleteGraphics(g)
        text_at(dc,name,78,y+3,174,27,'heading')
        text_at(dc,status,92,y+29,160,20,'small',MINT)
    g=graphics(dc)
    rounded(g,22,367,628,1,color(TC['sep']),None,0)
    gp.GdipDeleteGraphics(g)

def draw_control(hdc,hw):
    bid=user32.GetDlgCtrlID(hw)
    spec=g_control_specs[bid]
    x,y,w,h,label,kind=spec
    gdi32.BitBlt(hdc,0,0,sc(w),sc(h),g_scene_dc,sc(x),sc(y),SRCCOPY)
    enabled=bool(user32.IsWindowEnabled(hw))
    hover=g_hover_btn==hw and enabled
    if kind=='row':
        if hover or user32.GetFocus()==hw:
            g=graphics(hdc)
            rounded(g,1,1,w-2,h-2,None,MINT if hover else WHITE,10)
            gp.GdipDeleteGraphics(g)
        return
    selected=(bid==ID_MODE_DESKTOP and g_mode=='Desktop' or bid==ID_MODE_BROWSER and g_mode=='Browser' or bid==ID_MODE_HYBRID and g_mode=='Hybrid')
    primary=selected or (bid in ROW_IDS and not is_install_state(source_id(ROW_IDS.index(bid))))
    col=WHITE if enabled else color(TC['disabled'])
    g=graphics(hdc)
    if kind not in ('close','version'):
        fill=(color(TC['p_hover']) if hover else (color(TC['p1']),color(TC['p2']))) if primary and enabled else (color(TC['btn_hover']) if hover else color(TC['btn'],200))
        stroke=MINT if primary and enabled else (color(TC['hover_stroke']) if hover else BORDER)
        if kind=='install': fill=color(TC['install'],180)
        rounded(g,1,1,w-2,h-2,fill,stroke,7)
        if primary and enabled: col=DARK
    if user32.GetFocus()==hw and not (primary and enabled): rounded(g,3,3,w-6,h-6,None,color(TC['focus']),5)
    if kind in ('desktop','browser','hybrid','folder'):
        icon(g,kind,10,(h-18)/2,18,col)
    elif kind in ('shortcut','close'):
        icon(g,kind,(w-20)/2,(h-20)/2,20,col)
    gp.GdipDeleteGraphics(g)
    if kind in ('shortcut','close'): return
    if kind=='update':
        text_at(hdc,label,8,5,w-16,25,'heading',col,True)
        secondary=color(TC['secondary']) if primary and enabled else (MINT if enabled else col)
        text_at(hdc,UPDATE_DESCRIPTIONS[bid],8,29,w-16,19,'small',secondary,True)
        return
    if kind in ('desktop','browser','hybrid','folder'): text_at(hdc,label,34,0,w-40,h,'body',col,True)
    else: text_at(hdc,label,0,0,w,h,'small' if kind=='version' else 'body',MINT if kind=='version' and enabled else col,True)

def add_tip(hw, text):
    buf=ctypes.create_unicode_buffer(text); g_tip_texts.append(buf)
    ti=TOOLINFOW(); ti.cbSize=ctypes.sizeof(ti); ti.uFlags=0x11
    ti.hwnd=g_hwnd; ti.uId=hw; ti.lpszText=ctypes.cast(buf,wt.LPWSTR)
    user32.SendMessageW(g_tooltip_hwnd,TTM_ADDTOOLW,0,ctypes.addressof(ti))

def create_control(bid,x,y,w,h,label,kind='button',tip=None):
    g_control_specs[bid]=(x,y,w,h,label,kind)
    style=WS_CHILD|WS_VISIBLE|BS_OWNERDRAW|0x04000000
    if kind!='row': style|=0x10000
    hw=user32.CreateWindowExW(0,'BUTTON',label,style,
        sc(x),sc(y),sc(w),sc(h),g_hwnd,bid,kernel32.GetModuleHandleW(None),None)
    if not hw: raise ctypes.WinError()
    g_controls[bid]=hw
    user32.SetWindowPos(hw,1 if kind=='row' else 0,0,0,0,0,0x1|0x2|0x10)
    orig=user32.GetWindowLongPtrW(hw,-4)
    @BTN_PROC_TYPE
    def proc(window,msg,wp,lp):
        global g_hover_btn
        if msg==WM_PAINT:
            ps=PAINTSTRUCT(); dc=user32.BeginPaint(window,ctypes.byref(ps))
            crc=wt.RECT(); user32.GetClientRect(window,ctypes.byref(crc))
            mdc=gdi32.CreateCompatibleDC(dc)
            mbmp=gdi32.CreateCompatibleBitmap(dc,crc.right,crc.bottom)
            mold=gdi32.SelectObject(mdc,mbmp)
            draw_control(mdc,window)
            gdi32.BitBlt(dc,0,0,crc.right,crc.bottom,mdc,0,0,SRCCOPY)
            gdi32.SelectObject(mdc,mold); gdi32.DeleteObject(mbmp); gdi32.DeleteDC(mdc)
            user32.EndPaint(window,ctypes.byref(ps)); return 0
        if msg==WM_ERASEBKGND: return 1
        if msg==WM_MOUSEMOVE and g_hover_btn!=window:
            prev=g_hover_btn; g_hover_btn=window
            if prev: user32.InvalidateRect(prev,None,False)
            user32.InvalidateRect(window,None,False)
            tme=TRACKMOUSEEVENT(ctypes.sizeof(TRACKMOUSEEVENT),2,window,0)
            user32.TrackMouseEvent(ctypes.byref(tme))
        elif msg==WM_MOUSELEAVE:
            if g_hover_btn==window: g_hover_btn=None
            user32.InvalidateRect(window,None,False)
        elif msg in (7,8): user32.InvalidateRect(window,None,False)
        elif msg==0x100 and wp==13:
            user32.PostMessageW(g_hwnd,WM_COMMAND,bid,0); return 0
        elif msg==0x100 and wp==27:
            user32.PostMessageW(g_hwnd,WM_APP_CLOSE,0,0); return 0
        return user32.CallWindowProcW(ctypes.cast(orig,WNDPROC),window,msg,wp,lp)
    g_subclasses.append(proc)
    user32.SetWindowLongPtrW(hw,-4,ctypes.cast(proc,P))
    if tip: add_tip(hw,tip)
    return hw

def refresh_controls():
    for n,bid in enumerate(ROW_IDS):
        sid=source_id(n)
        missing=is_install_state(sid)
        label='+ Install' if missing else 'Launch'
        spec=list(g_control_specs[bid]); spec[4]=label; spec[5]='install' if missing else 'button'; g_control_specs[bid]=tuple(spec)
        user32.SetWindowTextW(g_controls[bid],label+' '+ROW_NAMES[n]+' ('+g_mode+')')
        user32.EnableWindow(g_controls[bid],available(sid))
        user32.SetWindowTextW(g_controls[ROW_HIT_IDS[n]],label+' '+ROW_NAMES[n]+' ('+g_mode+')')
        user32.EnableWindow(g_controls[ROW_HIT_IDS[n]],available(sid))
        user32.EnableWindow(g_controls[SC_IDS[n]],available(sid) and not missing)
        user32.ShowWindow(g_controls[SC_IDS[n]],0 if missing else SW_SHOW)
    user32.EnableWindow(g_controls[ID_UPD_COMFY],available(ID_UPD_COMFY))
    user32.EnableWindow(g_controls[ID_SC_UPD_COMFY],available(ID_SC_UPD_COMFY))
    user32.EnableWindow(g_controls[ID_UPD_COMFY_NODE],available(ID_UPD_COMFY_NODE))
    user32.EnableWindow(g_controls[ID_UPD_EASY],available(ID_UPD_EASY))
    for bid,name in [(ID_MODE_DESKTOP,'Desktop'),(ID_MODE_BROWSER,'Browser'),(ID_MODE_HYBRID,'Hybrid')]:
        user32.SetWindowTextW(g_controls[bid],name+(' (selected)' if name==g_mode else ''))
    paint_scene()
    user32.InvalidateRect(g_hwnd,None,False)
    for hw in g_controls.values(): user32.InvalidateRect(hw,None,False)

def handle_command(bid):
    global g_mode,g_adv
    if bid==ID_CLOSE: user32.DestroyWindow(g_hwnd); return
    modes={ID_MODE_DESKTOP:'Desktop',ID_MODE_BROWSER:'Browser',ID_MODE_HYBRID:'Hybrid'}
    if bid in modes:
        g_mode=modes[bid]; g_adv=g_mode=='Hybrid'; _save_mode(); refresh_controls(); return
    if bid in ROW_IDS or bid in ROW_HIT_IDS:
        sid=source_id((ROW_IDS if bid in ROW_IDS else ROW_HIT_IDS).index(bid))
        if available(sid): ACTIONS[sid]()
        return
    if bid in SC_IDS:
        sid=source_id(SC_IDS.index(bid))
        if available(sid) and not is_install_state(sid): create_shortcut(sid+100)
        return
    if bid in ACTIONS and available(bid): ACTIONS[bid]()

@WNDPROC
def wnd_proc(hwnd,msg,wp,lp):
    if msg==WM_PAINT:
        ps=PAINTSTRUCT(); dc=user32.BeginPaint(hwnd,ctypes.byref(ps))
        if g_scene_dc: gdi32.BitBlt(dc,0,0,WIN_W,WIN_H,g_scene_dc,0,0,SRCCOPY)
        user32.EndPaint(hwnd,ctypes.byref(ps)); return 0
    if msg==WM_ERASEBKGND: return 1
    if msg==WM_DRAWITEM:
        dis=ctypes.cast(lp,ctypes.POINTER(DRAWITEMSTRUCT)).contents
        if dis.CtlID in g_control_specs: draw_control(dis.hDC,dis.hwndItem)
        return 1
    if msg==WM_COMMAND:
        try: handle_command(wp & 0xffff)
        except Exception as exc:
            user32.MessageBoxW(hwnd,str(exc),'ComfyUI EZi Launcher',0x10)
        return 0
    if msg==WM_NCHITTEST:
        rc=wt.RECT(); user32.GetWindowRect(hwnd,ctypes.byref(rc))
        x=ctypes.c_short(lp & 0xffff).value-rc.left
        y=ctypes.c_short((lp>>16)&0xffff).value-rc.top
        if 0<=y<sc(48) and 0<=x<sc(552): return HTCAPTION
    if msg==WM_APP_CLOSE: user32.DestroyWindow(hwnd); return 0
    if msg==0x100 and wp==27: user32.DestroyWindow(hwnd); return 0
    if msg==WM_ACTIVATE and (wp & 0xffff)==0:
        if not g_creating_shortcut: user32.DestroyWindow(hwnd)
        return 0
    if msg==0x0113:
        paint_scene()
        user32.InvalidateRect(hwnd,None,False)
        for hw in g_controls.values(): user32.InvalidateRect(hw,None,False)
        return 0
    if msg==WM_DESTROY:
        user32.KillTimer(hwnd,1)
        user32.PostQuitMessage(0); return 0
    return user32.DefWindowProcW(hwnd,msg,wp,lp)

def main():
    global g_hwnd,g_tooltip_hwnd,g_mode,g_adv,g_logo_path,WIN_W,WIN_H,UI_SCALE
    work=wt.RECT()
    user32.SystemParametersInfoW(0x30,0,ctypes.byref(work),0)
    if work.right>work.left:
        UI_SCALE=min(UI_SCALE,(work.right-work.left-32)/672,(work.bottom-work.top-32)/420)
    WIN_W,WIN_H=sc(672),sc(420)
    gp.GdiplusStartup(ctypes.byref(g_token),ctypes.byref(GPSTART(1,None,0,0)),None)
    try:
        with tempfile.NamedTemporaryFile(suffix='.png',delete=False) as f:
            g_logo_path=f.name; f.write(_tint_png(base64.b64decode(LOGO_PNG),TC['mint']))
        gp.GdipLoadImageFromFile(g_logo_path,ctypes.byref(g_logo))
        for name,size,weight in [('title',20,650),('heading',16,600),('body',14,600),('small',12,400)]:
            g_fonts[name]=make_font(sc(-size),weight)
        g_mode=_load_mode(); g_adv=g_mode=='Hybrid'
        wc=WNDCLASSEX(); wc.cbSize=ctypes.sizeof(wc); wc.style=CS_HREDRAW|CS_VREDRAW
        wc.lpfnWndProc=wnd_proc; wc.hInstance=kernel32.GetModuleHandleW(None)
        wc.hCursor=user32.LoadCursorW(None,IDC_ARROW); wc.lpszClassName='ComfyUI_EZi_Aurora'
        if not user32.RegisterClassExW(ctypes.byref(wc)): raise ctypes.WinError()
        x,y=calc_position()
        if work.right>work.left:
            x=max(work.left,min(x,work.right-WIN_W)); y=max(work.top,min(y,work.bottom-WIN_H))
        g_hwnd=user32.CreateWindowExW(WS_EX_TOPMOST|WS_EX_TOOLWINDOW,wc.lpszClassName,'ComfyUI-Easy-Install-AMD',
            WS_POPUP|WS_CLIPCHILDREN,x,y,WIN_W,WIN_H,None,None,wc.hInstance,None)
        if not g_hwnd: raise ctypes.WinError()
        user32.SetWindowRgn(g_hwnd,gdi32.CreateRoundRectRgn(0,0,WIN_W+1,WIN_H+1,sc(32),sc(32)),True)
        g_tooltip_hwnd=user32.CreateWindowExW(WS_EX_TOPMOST,'tooltips_class32',None,TTS_ALWAYSTIP|TTS_NOPREFIX,
            0,0,0,0,g_hwnd,None,wc.hInstance,None)
        user32.SendMessageW(g_tooltip_hwnd,TTM_SETMAXTIPWIDTH,0,sc(320))
        paint_scene()
        create_control(ID_VERSION,552,12,72,24,'v'+VERSION,'version','Open project page')
        create_control(ID_CLOSE,632,10,28,28,'Close','close')
        create_control(ID_TRITON,438,12,106,24,triton_label(),'button','Turn the Triton backend on or off')
        for bid,x,label,kind in [(ID_MODE_DESKTOP,22,'Desktop','desktop'),(ID_MODE_BROWSER,154,'Browser','browser'),(ID_MODE_HYBRID,286,'Hybrid','hybrid')]:
            create_control(bid,x,64,128,32,label,kind)
        for n,bid in enumerate(ROW_IDS):
            create_control(ROW_HIT_IDS[n],22,108+n*62,392,54,ROW_NAMES[n],'row')
            create_control(bid,266,119+n*62,94,32,'Launch')
            create_control(SC_IDS[n],368,119+n*62,34,32,'Create shortcut for '+ROW_NAMES[n],'shortcut','Create desktop shortcut for the selected mode')
        for n,(bid,label) in enumerate([(ID_UPD_EASY,'Easy-Install'),(ID_UPD_COMFY,'ComfyUI Stable'),
                                       (ID_SC_UPD_COMFY,'ComfyUI Latest'),(ID_UPD_COMFY_NODE,'ComfyUI + Nodes')]):
            hw=create_control(bid,448,108+n*62,200,54,label,'update')
            user32.SetWindowTextW(hw,label+' — '+UPDATE_DESCRIPTIONS[bid])
        for n,(bid,label) in enumerate([(ID_FOLD_OUTPUT,'Output'),(ID_FOLD_INPUT,'Input'),(ID_FOLD_WORKFLOWS,'Workflows'),(ID_FOLD_MODELS,'Models')]):
            create_control(bid,22+n*159,374,151,32,label,'folder','Open '+label+' folder')
        refresh_controls()
        user32.ShowWindow(g_hwnd,SW_SHOW)
        user32.UpdateWindow(g_hwnd); user32.SetForegroundWindow(g_hwnd)
        user32.SetTimer(g_hwnd,1,33,None)
        msg=wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg),None,0,0)>0:
            if msg.message==0x100 and msg.wParam==9:
                next_hw=user32.GetNextDlgTabItem(g_hwnd,user32.GetFocus(),bool(user32.GetKeyState(0x10)&0x8000))
                if next_hw: user32.SetFocus(next_hw)
                continue
            if msg.message==0x100 and msg.wParam==27:
                user32.DestroyWindow(g_hwnd)
                continue
            user32.TranslateMessage(ctypes.byref(msg)); user32.DispatchMessageW(ctypes.byref(msg))
    finally:
        if g_scene_dc:
            gdi32.SelectObject(g_scene_dc,g_scene_old); gdi32.DeleteObject(g_scene_bitmap); gdi32.DeleteDC(g_scene_dc)
        for font in g_fonts.values(): gdi32.DeleteObject(font)
        if g_logo: gp.GdipDisposeImage(g_logo)
        if g_logo_path:
            try: os.unlink(g_logo_path)
            except OSError: pass
        gp.GdiplusShutdown(g_token)

if __name__=='__main__': main()
