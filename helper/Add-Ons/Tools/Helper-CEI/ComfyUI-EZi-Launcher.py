VERSION = '0.1.14-amd'

import os
import sys
import subprocess
import ctypes
import ctypes.wintypes as wt
import threading
import re
import shlex

import time
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT_DIR   = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
EZI_PY     = os.path.join(SCRIPT_DIR, 'ComfyUI-EZi.py')

def root(name):
    return os.path.join(ROOT_DIR, name)

ADDONS_DIR = root('Add-ons')

def attention_available(module):
    python = root('python_embeded/python.exe')
    if not os.path.isfile(python):
        return False
    try:
        result = subprocess.run(
            [python, '-c', 'import ' + module], cwd=ROOT_DIR,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False

HAS_SAGE = True
HAS_FLASH = True
ATTENTION_CHECK_PENDING = True
ATTENTION_CHECK_RESULTS = None

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

# Pixaroma theme
C_BG            = 0x111111
C_TITLEBAR      = 0x1A1A1A
C_BORDER        = 0x252525
C_FOOTER_BG     = 0x161616

C_ORANGE = 0x4467F6
C_GREEN  = 0x5A5AF0
C_BLUE   = 0xF49145

C_DP_BG         = 0x222222
C_DP_BORDER     = 0x0A53E8
C_DP_TEXT       = 0x0A53E8
C_DPH_BG        = 0x00226E
C_DPH_BORDER    = 0x4070FF
C_DPH_TEXT      = 0x4070FF

C_DP_INST_BORDER = 0x18488A
C_DP_INST_TEXT   = 0x18488A

C_BP_BG         = 0x222222
C_BP_BORDER     = 0x5A5AF0
C_BP_TEXT       = 0x5A5AF0
C_BPH_BG        = 0x242460
C_BPH_BORDER    = 0x8B8BFF
C_BPH_TEXT      = 0x8B8BFF

C_BP_INST_BORDER = 0x323284
C_BP_INST_TEXT   = 0x323284

C_UP_BG         = 0x222222
C_UP_BORDER     = 0xD08020
C_UP_TEXT       = 0xD08020
C_UPH_BG        = 0x281800
C_UPH_BORDER    = 0xFFB050
C_UPH_TEXT      = 0xFFB050

C_UP_DIM_BORDER = 0x724611
C_UP_DIM_TEXT   = 0x724611

C_FLD_BG        = 0x1E1E1E
C_FLD_BORDER    = 0x2A2A2A
C_FLD_TEXT      = C_DP_BORDER
C_FLDH_BG       = 0x00226E
C_FLDH_BORDER   = 0x0A53E8
C_FLDH_TEXT     = 0x0A53E8

C_VER_TEXT      = 0xAAAAAA

# Layout
WIN_W           = sc(520)
SEP_X           = sc(180)
SEP2_X          = sc(350)
TITLE_H         = sc(36)
STRIPE_H        = sc(2)
SEC_TOP_PAD     = sc(12)
SEC_LABEL_H     = sc(22)
SEC_LABEL_PAD   = 0
CONTENT_TOP     = TITLE_H + STRIPE_H + SEC_TOP_PAD + SEC_LABEL_H + SEC_LABEL_PAD
BTN_H           = sc(36)
BTN_GAP         = sc(6)
FOOTER_H        = sc(44)
FOOTER_BTN_H    = sc(28)
BOT_PAD         = sc(8)
ARROW_W         = sc(22)
ARROW_GAP       = sc(2)
WIN_BORDER_W    = max(1, sc(1))

WIN_H = CONTENT_TOP + (5 * BTN_H) + (4 * BTN_GAP) + BOT_PAD + FOOTER_H

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
WM_APP_ATTENTION_READY = 0x8002
WM_TIMER = 0x0113
ATTENTION_TIMER = 73

g_fonts          = {}
g_brushes        = {}
g_hover_btn      = None
g_gradient_memdc = None
g_gradient_bmp   = None
g_tooltip_hwnd   = None
g_creating_shortcut = False
g_hwnd           = None

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

def triton_enabled():
    try:
        with open(root('Start ComfyUI.bat'), encoding='utf-8') as handle:
            args = handle.read()
        return '--enable-triton-backend' in args and '--disable-triton-backend' not in args
    except OSError:
        return False


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
    BTN_META[ID_TRITON] = ('Triton: On' if triton_enabled() else 'Triton: Off', 'desk')
    user32.RedrawWindow(g_hwnd, None, None,
                        RDW_INVALIDATE | RDW_UPDATENOW | RDW_ALLCHILDREN)
    user32.MessageBoxW(g_hwnd, message, 'Triton Backend', 0x40)


BTN_META = {
    ID_TRITON: ('Triton: On' if triton_enabled() else 'Triton: Off', 'desk'),
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


def btn_default_bg(btn_id):
    if btn_id in (ID_TRITON, ID_EZI_DESK,  ID_KITCHEN_DESK, ID_SAGE_DESK,  ID_FLASH_DESK,
                  ID_SC_EZI_DESK, ID_SC_SAGE_DESK, ID_SC_FLASH_DESK, ID_SC_KITCHEN_DESK):
        if btn_id in INSTALL_BTN_STATE and is_install_state(btn_id):
            return C_BG
        if is_dimmed_state(btn_id):
            return C_BG
        return C_DP_BG
    if btn_id in (ID_EZI_BROW,  ID_KITCHEN_BROW, ID_SAGE_BROW,  ID_FLASH_BROW,
                  ID_SC_EZI_BROW, ID_SC_SAGE_BROW, ID_SC_FLASH_BROW, ID_SC_KITCHEN_BROW):
        if btn_id in INSTALL_BTN_STATE and is_install_state(btn_id):
            return C_BG
        if is_dimmed_state(btn_id):
            return C_BG
        return C_BP_BG
    if btn_id in (ID_UPD_COMFY, ID_SC_UPD_COMFY, ID_UPD_COMFY_NODE, ID_UPD_EASY):
        return C_UP_BG
    if btn_id in (ID_FOLD_OUTPUT, ID_FOLD_INPUT, ID_FOLD_WORKFLOWS, ID_FOLD_MODELS):
        return C_FLD_BG
    return C_BG


def check_attention_background():
    global ATTENTION_CHECK_RESULTS
    ATTENTION_CHECK_RESULTS = (attention_available('sageattention'), attention_available('flash_attn'))
    user32.PostMessageW(g_hwnd, WM_APP_ATTENTION_READY, 0, 0)


def apply_attention_results():
    global HAS_SAGE, HAS_FLASH, HAS_DESK_SAGE, HAS_BROW_SAGE, HAS_DESK_FLASH, HAS_BROW_FLASH, ATTENTION_CHECK_PENDING
    HAS_SAGE, HAS_FLASH = ATTENTION_CHECK_RESULTS
    HAS_DESK_SAGE = HAS_BROW_SAGE = HAS_SAGE and os.path.isfile(root('Start ComfyUI SageAttention.bat'))
    HAS_DESK_FLASH = HAS_BROW_FLASH = HAS_FLASH and os.path.isfile(root('Start ComfyUI FlashAttention.bat'))
    ATTENTION_CHECK_PENDING = False
    user32.KillTimer(g_hwnd, ATTENTION_TIMER)
    for button, available, bat, installer, desktop in (
        (ID_SAGE_DESK, HAS_DESK_SAGE, 'Start ComfyUI SageAttention.bat', INSTALL_SAGE_BAT, True),
        (ID_SAGE_BROW, HAS_BROW_SAGE, 'Start ComfyUI SageAttention.bat', INSTALL_SAGE_BAT, False),
        (ID_FLASH_DESK, HAS_DESK_FLASH, 'Start ComfyUI FlashAttention.bat', INSTALL_FLASH_BAT, True),
        (ID_FLASH_BROW, HAS_BROW_FLASH, 'Start ComfyUI FlashAttention.bat', INSTALL_FLASH_BAT, False)):
        ACTIONS[button] = (lambda bat=bat: launch_ezi_with_bat(bat)) if available and desktop else (lambda bat=bat: launch_bat(bat)) if available else (lambda installer=installer: install_addon(installer))
    user32.RedrawWindow(g_hwnd, None, None, RDW_INVALIDATE | RDW_UPDATENOW | RDW_ALLCHILDREN)


def launch_ezi():
    pythonw = os.path.join(ROOT_DIR, 'python_embeded', 'pythonw.exe')
    if not os.path.exists(pythonw):
        pythonw = re.sub(r'(?i)python\.exe$', 'pythonw.exe', sys.executable)
    subprocess.Popen([pythonw, EZI_PY], cwd=SCRIPT_DIR, creationflags=0x8)
    user32.PostMessageW(g_hwnd, WM_APP_CLOSE, 0, 0)


def launch_bat(name):
    bat = root(name)
    if os.path.exists(bat):
        subprocess.Popen([bat], cwd=ROOT_DIR,
                          creationflags=subprocess.CREATE_NEW_CONSOLE)
    user32.PostMessageW(g_hwnd, WM_APP_CLOSE, 0, 0)


def launch_ezi_with_bat(bat_name):
    pythonw = os.path.join(ROOT_DIR, 'python_embeded', 'pythonw.exe')
    subprocess.Popen([pythonw, EZI_PY, bat_name], cwd=SCRIPT_DIR, creationflags=0x8)
    user32.PostMessageW(g_hwnd, WM_APP_CLOSE, 0, 0)


def install_addon(bat_path):
    if os.path.exists(bat_path):
        bat_dir = os.path.dirname(bat_path)
        subprocess.Popen([bat_path], cwd=bat_dir,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
    user32.PostMessageW(g_hwnd, WM_APP_CLOSE, 0, 0)


ACTIONS = {
    ID_TRITON: toggle_triton,
    ID_VERSION:    lambda: os.startfile('https://github.com/Tavris1/ComfyUI-Easy-Install'),
    ID_EZI_DESK:   lambda: launch_ezi(),
    ID_EZI_BROW:   lambda: launch_bat('Start ComfyUI.bat'),

    ID_KITCHEN_DESK: lambda: launch_ezi_with_bat('Start ComfyUI KitchenAttention.bat'),
    ID_KITCHEN_BROW: lambda: launch_bat('Start ComfyUI KitchenAttention.bat'),

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
        (lambda: launch_bat('Start ComfyUI SageAttention.bat'))
        if HAS_BROW_SAGE
        else (lambda: install_addon(INSTALL_SAGE_BAT))
    ),
    ID_FLASH_BROW: (
        (lambda: launch_bat('Start ComfyUI FlashAttention.bat'))
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


def _rgb(c):
    return (c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF)


def _to_col(r, g, b):
    return (b << 16) | (g << 8) | r


def _lerp(a, b, s):
    return int(a + (b - a) * s)


def _lerp_col(c1, c2, s):
    r1, g1, b1 = _rgb(c1)
    r2, g2, b2 = _rgb(c2)
    return _to_col(_lerp(r1, r2, s), _lerp(g1, g2, s), _lerp(b1, b2, s))


def _gradient_col(t):
    sep1 = SEP_X  / float(WIN_W)
    sep2 = SEP2_X / float(WIN_W)
    fade = 0.05

    if t <= sep1 - fade:
        return C_DP_BORDER
    if t < sep1 + fade:
        s = (t - (sep1 - fade)) / (2 * fade)
        return _lerp_col(C_DP_BORDER, C_BP_BORDER, s)
    if t <= sep2 - fade:
        return C_BP_BORDER
    if t < sep2 + fade:
        s = (t - (sep2 - fade)) / (2 * fade)
        return _lerp_col(C_BP_BORDER, C_UP_BORDER, s)
    return C_UP_BORDER


def create_gradient_cache():
    global g_gradient_memdc, g_gradient_bmp
    hdc_screen       = user32.GetDC(0)

    g_gradient_memdc = gdi32.CreateCompatibleDC(hdc_screen)
    g_gradient_bmp   = gdi32.CreateCompatibleBitmap(hdc_screen, WIN_W, STRIPE_H)
    gdi32.SelectObject(g_gradient_memdc, g_gradient_bmp)
    for i in range(WIN_W):
        t   = i / (WIN_W - 1)
        col = _gradient_col(t)
        pen = gdi32.CreatePen(PS_SOLID, 1, col)
        old = gdi32.SelectObject(g_gradient_memdc, pen)
        gdi32.MoveToEx(g_gradient_memdc, i, 0, None)
        gdi32.LineTo(g_gradient_memdc, i, STRIPE_H)
        gdi32.SelectObject(g_gradient_memdc, old)
        gdi32.DeleteObject(pen)

    user32.ReleaseDC(0, hdc_screen)


def draw_arrow_button(hdc, hw, rc):
    sc_id  = user32.GetDlgCtrlID(hw)
    cat    = ARROW_COLOR_CAT.get(sc_id)
    if not cat:
        return
    hovered = (hw == g_hover_btn)
    dimmed  = is_dimmed_state(sc_id)

    if dimmed:
        bg       = C_UP_BG
        border   = C_UP_DIM_BORDER
        text_col = C_UP_DIM_TEXT
    elif cat == 'desk':
        bg       = C_DPH_BG     if hovered else C_DP_BG
        border   = C_DPH_BORDER if hovered else C_DP_BORDER
        text_col = C_DPH_TEXT   if hovered else C_DP_TEXT
    elif cat == 'upd':
        bg       = C_UPH_BG     if hovered else C_UP_BG
        border   = C_UPH_BORDER if hovered else C_UP_BORDER
        text_col = C_UPH_TEXT   if hovered else C_UP_TEXT
    else:
        bg       = C_BPH_BG     if hovered else C_BP_BG
        border   = C_BPH_BORDER if hovered else C_BP_BORDER
        text_col = C_BPH_TEXT   if hovered else C_BP_TEXT

    if rc.right <= rc.left or rc.bottom <= rc.top:
        return

    user32.FillRect(hdc, ctypes.byref(rc), get_brush(bg))

    pen = gdi32.CreatePen(PS_SOLID, 1, border)
    op  = gdi32.SelectObject(hdc, pen)
    ob  = gdi32.SelectObject(hdc, gdi32.GetStockObject(5))
    gdi32.RoundRect(hdc, rc.left, rc.top, rc.right, rc.bottom, sc(7), sc(7))
    gdi32.SelectObject(hdc, op)
    gdi32.SelectObject(hdc, ob)
    gdi32.DeleteObject(pen)

    old_font = gdi32.SelectObject(hdc, g_fonts['arrow'])
    gdi32.SetBkMode(hdc, 1)
    gdi32.SetTextColor(hdc, text_col)
    glyph = 'N' if cat == 'upd' else '\u2197'
    user32.DrawTextW(hdc, glyph, -1, ctypes.byref(rc),
                     DT_CENTER | DT_VCENTER | DT_SINGLELINE)
    gdi32.SelectObject(hdc, old_font)


def draw_triton_gradient(hdc, rc, label, hovered):
    # Reuse the title stripe's column-aligned colors and transition points.
    gdi32.SaveDC.argtypes = [wt.HDC]
    gdi32.SaveDC.restype = ctypes.c_int
    gdi32.RestoreDC.argtypes = [wt.HDC, ctypes.c_int]
    gdi32.SelectClipRgn.argtypes = [wt.HDC, wt.HANDLE]
    saved = gdi32.SaveDC(hdc)
    region = gdi32.CreateRoundRectRgn(rc.left, rc.top, rc.right, rc.bottom, sc(7), sc(7))
    gdi32.SelectClipRgn(hdc, region)
    for x in range(rc.left, rc.right):
        color = _gradient_col((sc(8) + x) / float(WIN_W))
        column = wt.RECT(x, rc.top, x + 1, rc.bottom)
        brush = gdi32.CreateSolidBrush(_lerp_col(C_BG, color, .25 if hovered else .13))
        user32.FillRect(hdc, ctypes.byref(column), brush)
        gdi32.DeleteObject(brush)
        edge_brush = gdi32.CreateSolidBrush(color)
        for edge in (wt.RECT(x, rc.top, x + 1, rc.top + sc(1)),
                     wt.RECT(x, rc.bottom - sc(1), x + 1, rc.bottom)):
            user32.FillRect(hdc, ctypes.byref(edge), edge_brush)
        gdi32.DeleteObject(edge_brush)
    # Draw a complete rounded border using the difference between two regions.
    thickness = max(1, sc(1))
    outer = gdi32.CreateRoundRectRgn(rc.left, rc.top, rc.right + 1, rc.bottom + 1, sc(7), sc(7))
    inner = gdi32.CreateRoundRectRgn(rc.left + thickness, rc.top + thickness,
                                   rc.right + 1 - thickness, rc.bottom + 1 - thickness, sc(7), sc(7))
    ring = gdi32.CreateRectRgn(0, 0, 0, 0)
    gdi32.CombineRgn(ring, outer, inner, RGN_DIFF)
    gdi32.SelectClipRgn(hdc, ring)
    for x in range(rc.left, rc.right):
        color = _gradient_col((sc(8) + x) / float(WIN_W))
        brush = gdi32.CreateSolidBrush(_lerp_col(color, 0xFFFFFF, .15) if hovered else color)
        column = wt.RECT(x, rc.top, x + 1, rc.bottom)
        user32.FillRect(hdc, ctypes.byref(column), brush)
        gdi32.DeleteObject(brush)
    for border_region in (outer, inner, ring):
        gdi32.DeleteObject(border_region)
    gdi32.RestoreDC(hdc, saved)
    gdi32.DeleteObject(region)
    old_font = gdi32.SelectObject(hdc, g_fonts['btn_pri'])
    gdi32.SetBkMode(hdc, 1)
    gdi32.SetTextColor(hdc, C_BPH_TEXT if hovered else C_BP_TEXT)
    user32.DrawTextW(hdc, label, -1, ctypes.byref(rc), DT_CENTER | DT_VCENTER | DT_SINGLELINE)
    gdi32.SelectObject(hdc, old_font)


def draw_button(hdc, hw, rc):
    btn_id = user32.GetDlgCtrlID(hw)
    meta   = BTN_META.get(btn_id)
    if not meta:
        return
    label, btn_type = meta
    if ATTENTION_CHECK_PENDING and btn_id in (ID_SAGE_DESK, ID_SAGE_BROW, ID_FLASH_DESK, ID_FLASH_BROW):
        label += ": Checking..."
    hovered = (hw == g_hover_btn)
    install = is_install_state(btn_id)
    if btn_id == ID_TRITON:
        draw_triton_gradient(hdc, rc, label, hovered)
        return
    pen_style = PS_SOLID
    font = g_fonts['btn_pri']

    if btn_type == 'version':
        hovered  = (hw == g_hover_btn)
        text_col = C_DP_BORDER if hovered else C_VER_TEXT
        if rc.right <= rc.left or rc.bottom <= rc.top:
            return
        user32.FillRect(hdc, ctypes.byref(rc), get_brush(C_TITLEBAR))
        old_font = gdi32.SelectObject(hdc, g_fonts['footer'])
        gdi32.SetBkMode(hdc, 1)
        gdi32.SetTextColor(hdc, text_col)
        user32.DrawTextW(hdc, label, -1, ctypes.byref(rc),
                         DT_LEFT | DT_VCENTER | DT_SINGLELINE)
        gdi32.SelectObject(hdc, old_font)
        return

    if btn_type == 'close':
        bg       = 0x2A2A2A      if hovered else C_BG
        border   = 0x2A2A2A      if hovered else 0x2A1015
        text_col = 0x4070FF      if hovered else 0x666666
        font     = g_fonts['close']
    elif btn_type == 'fld':
        bg       = C_FLDH_BG     if hovered else C_FLD_BG
        border   = C_FLDH_BORDER if hovered else C_FLD_BORDER
        text_col = C_FLDH_TEXT   if hovered else C_FLD_TEXT
        font     = g_fonts['footer']
    elif btn_type == 'upd':
        if is_dimmed_state(btn_id):
            bg       = C_UP_BG
            border   = C_UP_DIM_BORDER
            text_col = C_UP_DIM_TEXT
            font     = g_fonts['btn_pri']
        else:
            bg       = C_UPH_BG     if hovered else C_UP_BG
            border   = C_UPH_BORDER if hovered else C_UP_BORDER
            text_col = C_UPH_TEXT   if hovered else C_UP_TEXT
            font     = g_fonts['btn_pri']
    elif btn_type == 'desk':
        if is_dimmed_state(btn_id):
            bg       = C_BG
            border   = C_DP_INST_BORDER
            text_col = C_DP_INST_TEXT
            font     = g_fonts['btn_pri']
        elif install:
            label    = '+ Install ' + label
            bg       = C_BG
            border   = C_DPH_BORDER  if hovered else C_DP_INST_BORDER
            text_col = C_DPH_TEXT    if hovered else C_DP_INST_TEXT
            font     = g_fonts['btn_install']
        else:
            bg       = C_DPH_BG     if hovered else C_DP_BG
            border   = C_DPH_BORDER if hovered else C_DP_BORDER
            text_col = C_DPH_TEXT   if hovered else C_DP_TEXT
            font     = g_fonts['btn_pri']
    elif btn_type == 'brow':
        if is_dimmed_state(btn_id):
            bg       = C_BG
            border   = C_BP_INST_BORDER
            text_col = C_BP_INST_TEXT
            font     = g_fonts['btn_pri']
        elif install:
            label    = '+ Install ' + label
            bg       = C_BG
            border   = C_BPH_BORDER  if hovered else C_BP_INST_BORDER
            text_col = C_BPH_TEXT    if hovered else C_BP_INST_TEXT
            font     = g_fonts['btn_install']
        else:
            bg       = C_BPH_BG     if hovered else C_BP_BG
            border   = C_BPH_BORDER if hovered else C_BP_BORDER
            text_col = C_BPH_TEXT   if hovered else C_BP_TEXT
            font     = g_fonts['btn_pri']
    else:
        bg = C_BG
        border = 0x2A2A2A
        text_col = 0x888888

    if rc.right <= rc.left or rc.bottom <= rc.top:
        return

    user32.FillRect(hdc, ctypes.byref(rc), get_brush(bg))

    pen = gdi32.CreatePen(pen_style, 1, border)
    op  = gdi32.SelectObject(hdc, pen)
    ob  = gdi32.SelectObject(hdc, gdi32.GetStockObject(5))
    gdi32.RoundRect(hdc, rc.left, rc.top, rc.right, rc.bottom, sc(7), sc(7))
    gdi32.SelectObject(hdc, op)
    gdi32.SelectObject(hdc, ob)
    gdi32.DeleteObject(pen)

    old_font = gdi32.SelectObject(hdc, font)
    gdi32.SetBkMode(hdc, 1)
    gdi32.SetTextColor(hdc, text_col)
    if ATTENTION_CHECK_PENDING and btn_id in (ID_SAGE_DESK, ID_SAGE_BROW, ID_FLASH_DESK, ID_FLASH_BROW):
        size = wt.SIZE()
        gdi32.GetTextExtentPoint32W(hdc, label, len(label), ctypes.byref(size))
        width = rc.right - rc.left
        span = width + size.cx + sc(16)
        offset = int(time.monotonic() * sc(55)) % span
        x = rc.right - offset
        moving = wt.RECT(x, rc.top, x + size.cx + sc(4), rc.bottom)
        gdi32.SaveDC.argtypes = [wt.HDC]
        gdi32.SaveDC.restype = ctypes.c_int
        gdi32.RestoreDC.argtypes = [wt.HDC, ctypes.c_int]
        gdi32.IntersectClipRect.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        saved_dc = gdi32.SaveDC(hdc)
        gdi32.IntersectClipRect(hdc, rc.left + sc(4), rc.top + sc(2), rc.right - sc(4), rc.bottom - sc(2))
        user32.DrawTextW(hdc, label, -1, ctypes.byref(moving), DT_LEFT | DT_VCENTER | DT_SINGLELINE)
        gdi32.RestoreDC(hdc, saved_dc)
    else:
        user32.DrawTextW(hdc, label, -1, ctypes.byref(rc), DT_CENTER | DT_VCENTER | DT_SINGLELINE)
    gdi32.SelectObject(hdc, old_font)


_subclass_procs = []


def make_btn_subclass(hwnd_btn, is_arrow=False):
    orig = user32.GetWindowLongPtrW(hwnd_btn, -4)

    @BTN_PROC_TYPE
    def sub_proc(hw, msg, wp, lp):
        global g_hover_btn
        if msg == WM_PAINT:
            ps  = PAINTSTRUCT()
            hdc = user32.BeginPaint(hw, ctypes.byref(ps))
            rc  = wt.RECT()
            user32.GetClientRect(hw, ctypes.byref(rc))
            if is_arrow:
                draw_arrow_button(hdc, hw, rc)
            else:
                draw_button(hdc, hw, rc)
            user32.EndPaint(hw, ctypes.byref(ps))
            return 0

        if msg == WM_ERASEBKGND:
            return 1

        if msg == WM_MOUSEMOVE:
            if g_hover_btn != hw:
                prev        = g_hover_btn
                g_hover_btn = hw
                if prev:
                    user32.InvalidateRect(prev, None, False)
                user32.InvalidateRect(hw, None, False)
                tme = TRACKMOUSEEVENT(
                    ctypes.sizeof(TRACKMOUSEEVENT), 0x00000002, hw, 0)
                user32.TrackMouseEvent(ctypes.byref(tme))

        elif msg == WM_MOUSELEAVE:
            if g_hover_btn == hw:
                g_hover_btn = None
                user32.InvalidateRect(hw, None, False)

        orig_proc = ctypes.cast(orig, BTN_PROC_TYPE)
        return user32.CallWindowProcW(orig_proc, hw, msg, wp, lp)

    _subclass_procs.append((orig, sub_proc))
    user32.SetWindowLongPtrW(hwnd_btn, -4,
                             ctypes.cast(sub_proc, ctypes.c_void_p))


def create_tooltip_window(parent):
    global g_tooltip_hwnd
    hinstance = kernel32.GetModuleHandleW(None)
    g_tooltip_hwnd = user32.CreateWindowExW(
        WS_EX_TOPMOST,
        'tooltips_class32', None,
        TTS_ALWAYSTIP | TTS_NOPREFIX,
        0, 0, 0, 0,
        parent, None, hinstance, None,
    )
    user32.SendMessageW(g_tooltip_hwnd, TTM_SETDELAYTIME, TTDT_AUTOPOP, 5000)
    user32.SendMessageW(g_tooltip_hwnd, TTM_SETMAXTIPWIDTH, 0, 300)


def add_tooltip(hwnd_btn, text):
    if not g_tooltip_hwnd:
        return
    ti = TOOLINFOW()
    ti.cbSize   = ctypes.sizeof(TOOLINFOW)
    ti.uFlags   = 0x0011
    ti.hwnd     = hwnd_btn
    ti.uId      = hwnd_btn
    ti.lpszText = text

    SendMsg = ctypes.WINFUNCTYPE(
        ctypes.c_void_p,
        wt.HWND, wt.UINT, ctypes.c_void_p, ctypes.c_void_p
    )(ctypes.cast(user32.SendMessageW, ctypes.c_void_p).value)
    SendMsg(g_tooltip_hwnd, TTM_ADDTOOLW, None, ctypes.byref(ti))


BTN_TIPS = {
    ID_SC_EZI_DESK:     'Create Desktop shortcut\nComfyUI-Easy-Install-AMD Desktop',
    ID_SC_SAGE_DESK:    'Create Desktop shortcut\nComfyUI-Easy-Install-AMD SageAttention',
    ID_SC_FLASH_DESK:   'Create Desktop shortcut\nComfyUI-Easy-Install-AMD FlashAttention',
    ID_SC_KITCHEN_DESK: 'Create Desktop shortcut\nComfyUI-Easy-Install-AMD KitchenAttention',
    ID_SC_EZI_BROW:     'Create Desktop shortcut\nComfyUI-EZi',
    ID_SC_SAGE_BROW:    'Create Desktop shortcut\nComfyUI-SA',
    ID_SC_FLASH_BROW:   'Create Desktop shortcut\nComfyUI-FA',
    ID_SC_KITCHEN_BROW: 'Create Desktop shortcut\nComfyUI-KA',
    ID_SC_UPD_COMFY:    'Update to the latest/nightly version',
    ID_UPD_COMFY:       'Update to stable version',
}


def create_button(parent, btn_id, x, y, w, h, is_arrow=False):
    ex_style = WS_EX_NOACTIVATE if is_arrow else 0
    hwnd_btn = user32.CreateWindowExW(
        ex_style, 'BUTTON', '',
        WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
        x, y, w, h,
        parent, btn_id,
        kernel32.GetModuleHandleW(None), None,
    )
    make_btn_subclass(hwnd_btn, is_arrow=is_arrow)
    tip = BTN_TIPS.get(btn_id)
    if tip:
        add_tooltip(hwnd_btn, tip)
    return hwnd_btn


# Main Window
@WNDPROC
def wnd_proc(hwnd, msg, wp, lp):
    global g_hwnd, g_hover_btn

    if msg == WM_DESTROY:
        for br  in g_brushes.values(): gdi32.DeleteObject(br)
        for fnt in g_fonts.values():   gdi32.DeleteObject(fnt)
        if g_gradient_bmp:   gdi32.DeleteObject(g_gradient_bmp)
        if g_gradient_memdc: gdi32.DeleteDC(g_gradient_memdc)
        user32.PostQuitMessage(0)
        return 0

    if msg == WM_PAINT:
        ps  = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))

        user32.FillRect(hdc, ctypes.byref(wt.RECT(0, 0, WIN_W, WIN_H)),
                        get_brush(C_BG))

        user32.FillRect(hdc, ctypes.byref(wt.RECT(0, 0, WIN_W, TITLE_H)),
                        get_brush(C_TITLEBAR))
        
        old_font = gdi32.SelectObject(hdc, g_fonts['title'])
        gdi32.SetBkMode(hdc, 1)
        gdi32.SetTextColor(hdc, C_BP_BORDER)
        title_cx = (SEP_X + SEP2_X) // 2
        title_rc = wt.RECT(title_cx - WIN_W // 2, 0,
                           title_cx + WIN_W // 2, TITLE_H)
        user32.DrawTextW(hdc, 'ComfyUI EZi Launcher - AMD', -1,
                         ctypes.byref(title_rc),
                         DT_CENTER | DT_VCENTER | DT_SINGLELINE)
        gdi32.SelectObject(hdc, old_font)

        if g_gradient_memdc:
            gdi32.BitBlt(hdc, 0, TITLE_H, WIN_W, STRIPE_H,
                         g_gradient_memdc, 0, 0, SRCCOPY)
                         
        old_font = gdi32.SelectObject(hdc, g_fonts['sec_title'])
        gdi32.SetBkMode(hdc, 1)
        gdi32.SetTextColor(hdc, C_DP_BORDER)
        user32.DrawTextW(hdc, '-- Desktop --', -1,
                         ctypes.byref(wt.RECT(sc(12), CONTENT_TOP - SEC_LABEL_H,
                                              sc(175), CONTENT_TOP)),
                         DT_CENTER | DT_SINGLELINE)
        gdi32.SetTextColor(hdc, C_BP_BORDER)
        user32.DrawTextW(hdc, '-- Browser --', -1,
                         ctypes.byref(wt.RECT(sc(188), CONTENT_TOP - SEC_LABEL_H,
                                              sc(350), CONTENT_TOP)),
                         DT_CENTER | DT_SINGLELINE)
        gdi32.SetTextColor(hdc, C_UP_BORDER)
        user32.DrawTextW(hdc, '-- Update --', -1,
                         ctypes.byref(wt.RECT(sc(355), CONTENT_TOP - SEC_LABEL_H,
                                              WIN_W - sc(8), CONTENT_TOP)),
                         DT_CENTER | DT_SINGLELINE)
        gdi32.SelectObject(hdc, old_font)
        
        user32.FillRect(hdc,
                        ctypes.byref(wt.RECT(0, WIN_H - FOOTER_H, WIN_W, WIN_H)),
                        get_brush(C_FOOTER_BG))

        BORDER_W = WIN_BORDER_W
        outer_rgn = gdi32.CreateRoundRectRgn(0, 0, WIN_W + 1, WIN_H + 1, sc(24), sc(24))
        inner_rgn = gdi32.CreateRoundRectRgn(
            BORDER_W, BORDER_W, WIN_W + 1 - BORDER_W, WIN_H + 1 - BORDER_W,
            max(0, sc(24) - BORDER_W), max(0, sc(24) - BORDER_W)
        )
        ring_rgn = gdi32.CreateRectRgn(0, 0, 0, 0)
        gdi32.CombineRgn(ring_rgn, outer_rgn, inner_rgn, RGN_DIFF)
        gdi32.SelectClipRgn(hdc, ring_rgn)
        if g_gradient_memdc:
            gdi32.StretchBlt(hdc, 0, 0, WIN_W, WIN_H,
                             g_gradient_memdc, 0, 0, WIN_W, STRIPE_H, SRCCOPY)
        else:
            user32.FillRect(hdc, ctypes.byref(wt.RECT(0, 0, WIN_W, WIN_H)),
                            get_brush(C_BP_BORDER))
        gdi32.SelectClipRgn(hdc, None)
        gdi32.DeleteObject(outer_rgn)
        gdi32.DeleteObject(inner_rgn)
        gdi32.DeleteObject(ring_rgn)

        user32.EndPaint(hwnd, ctypes.byref(ps))
        return 0

    if msg == WM_ERASEBKGND:
        return 1

    if msg == WM_DRAWITEM:
        dis = ctypes.cast(ctypes.c_void_p(lp),
                          ctypes.POINTER(DRAWITEMSTRUCT)).contents
        if dis.CtlID in ARROW_COLOR_CAT:
            draw_arrow_button(dis.hDC, dis.hwndItem, dis.rcItem)
        else:
            draw_button(dis.hDC, dis.hwndItem, dis.rcItem)
        return 1

    if msg == WM_CTLCOLORBTN:
        hw     = ctypes.cast(ctypes.c_void_p(lp), wt.HWND)
        btn_id = user32.GetDlgCtrlID(hw)
        bg     = btn_default_bg(btn_id)
        gdi32.SetBkColor(wt.HDC(wp), bg)
        return ctypes.cast(get_brush(bg), ctypes.c_void_p).value

    if msg == WM_TIMER and wp == ATTENTION_TIMER:
        if ATTENTION_CHECK_PENDING:
            for button in (ID_SAGE_DESK, ID_SAGE_BROW, ID_FLASH_DESK, ID_FLASH_BROW):
                child = user32.GetDlgItem(hwnd, button)
                user32.InvalidateRect(child, None, False)
        return 0

    if msg == WM_APP_ATTENTION_READY:
        apply_attention_results()
        return 0

    if msg == WM_COMMAND:
        btn_id = wp & 0xFFFF
        if ATTENTION_CHECK_PENDING and btn_id in (ID_SAGE_DESK, ID_SAGE_BROW, ID_FLASH_DESK, ID_FLASH_BROW, ID_SC_SAGE_DESK, ID_SC_SAGE_BROW, ID_SC_FLASH_DESK, ID_SC_FLASH_BROW):
            return 0
        if btn_id == ID_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if btn_id in SHORTCUT_META:
            main_id = SHORTCUT_META[btn_id][0]
            if main_id in INSTALL_BTN_STATE and is_install_state(main_id):
                return 0
            create_shortcut(btn_id)
            return 0
        action = ACTIONS.get(btn_id)
        if action:
            if is_dimmed_state(btn_id):
                return 0
            action()
            return 0

    if msg == WM_NCHITTEST:
        x  = ctypes.c_short(lp & 0xFFFF).value
        y  = ctypes.c_short((lp >> 16) & 0xFFFF).value
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        lx, ly = x - rc.left, y - rc.top
        if 0 <= ly < TITLE_H and 0 <= lx < WIN_W - sc(30):
            return HTCAPTION
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    if msg == WM_APP_CLOSE:
        user32.DestroyWindow(hwnd)
        return 0

    if msg == WM_ACTIVATE:
        if (wp & 0xFFFF) == 0:
            if g_creating_shortcut:
                return 0
            user32.DestroyWindow(hwnd)
        return 0

    return user32.DefWindowProcW(hwnd, msg, wp, lp)


# Main
def main():
    global g_hwnd

    if sys.platform != 'win32':
        sys.exit(1)

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    hinstance = kernel32.GetModuleHandleW(None)

    g_fonts['title']        = make_font(sc(-15), 600)
    g_fonts['sec_title']    = make_font(sc(-12), 700)
    g_fonts['btn_pri']      = make_font(sc(-16), 700)
    g_fonts['btn_install']  = make_font(sc(-13), 500)
    g_fonts['btn_sec']      = make_font(sc(-14), 500)
    g_fonts['footer']       = make_font(sc(-12), 500)
    g_fonts['close']        = make_font(sc(-12), 600)
    g_fonts['arrow']        = make_font(sc(-14), 600)

    CLASS_NAME = 'ComfyUI_EZi_Launcher'

    wc = WNDCLASSEX()
    wc.cbSize        = ctypes.sizeof(WNDCLASSEX)
    wc.style         = CS_HREDRAW | CS_VREDRAW
    wc.lpfnWndProc   = wnd_proc
    wc.hInstance     = hinstance
    wc.hCursor       = user32.LoadCursorW(None, IDC_ARROW)
    wc.hbrBackground = make_solid_brush(C_BG)
    wc.lpszClassName = CLASS_NAME

    if not user32.RegisterClassExW(ctypes.byref(wc)):
        raise ctypes.WinError()

    x, y = calc_position()

    g_hwnd = user32.CreateWindowExW(
        WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
        CLASS_NAME, 'ComfyUI-Easy-Install-AMD',
        WS_POPUP | WS_VISIBLE | WS_CLIPCHILDREN,
        x, y, WIN_W, WIN_H,
        None, None, hinstance, None,
    )
    if not g_hwnd:
        raise ctypes.WinError()

    rgn = gdi32.CreateRoundRectRgn(0, 0, WIN_W + 1, WIN_H + 1, sc(24), sc(24))
    user32.SetWindowRgn(g_hwnd, rgn, True)

    create_gradient_cache()
    create_tooltip_window(g_hwnd)

    PAD     = sc(8)
    BTN_W   = SEP_X - PAD * 2
    MAIN_W  = BTN_W - ARROW_W - ARROW_GAP

    bw      = SEP2_X - SEP_X - PAD * 2
    MAIN_BW = bw - ARROW_W - ARROW_GAP

    upd_w   = WIN_W - SEP2_X - PAD * 2

    close_sz = sc(22)
    close_x  = WIN_W - sc(28)
    close_y  = (TITLE_H - close_sz) // 2
    create_button(g_hwnd, ID_CLOSE, close_x, close_y, close_sz, close_sz)

    ver_label = 'v' + VERSION
    hdc_tmp   = user32.GetDC(g_hwnd)
    old_f     = gdi32.SelectObject(hdc_tmp, g_fonts['footer'])
    ver_size  = wt.SIZE()
    gdi32.GetTextExtentPoint32W(hdc_tmp, ver_label, len(ver_label), ctypes.byref(ver_size))
    gdi32.SelectObject(hdc_tmp, old_f)
    user32.ReleaseDC(g_hwnd, hdc_tmp)
    ver_w = ver_size.cx + sc(6)
    ver_h = TITLE_H - WIN_BORDER_W
    create_button(g_hwnd, ID_VERSION, sc(12), WIN_BORDER_W, ver_w, ver_h)

    y_d = CONTENT_TOP

    create_button(g_hwnd, ID_EZI_DESK, PAD, y_d, MAIN_W, BTN_H)
    create_button(g_hwnd, ID_SC_EZI_DESK,
                  PAD + MAIN_W + ARROW_GAP, y_d, ARROW_W, BTN_H, is_arrow=True)
    y_d += BTN_H + BTN_GAP

    if HAS_DESK_KITCHEN:
        create_button(g_hwnd, ID_KITCHEN_DESK, PAD, y_d, MAIN_W, BTN_H)
        create_button(g_hwnd, ID_SC_KITCHEN_DESK,
                      PAD + MAIN_W + ARROW_GAP, y_d, ARROW_W, BTN_H, is_arrow=True)
    else:
        create_button(g_hwnd, ID_KITCHEN_DESK, PAD, y_d, BTN_W, BTN_H)
    y_d += BTN_H + BTN_GAP

    if HAS_DESK_SAGE:
        create_button(g_hwnd, ID_SAGE_DESK, PAD, y_d, MAIN_W, BTN_H)
        create_button(g_hwnd, ID_SC_SAGE_DESK,
                      PAD + MAIN_W + ARROW_GAP, y_d, ARROW_W, BTN_H, is_arrow=True)
    else:
        create_button(g_hwnd, ID_SAGE_DESK, PAD, y_d, BTN_W, BTN_H)
    y_d += BTN_H + BTN_GAP

    if HAS_DESK_FLASH:
        create_button(g_hwnd, ID_FLASH_DESK, PAD, y_d, MAIN_W, BTN_H)
        create_button(g_hwnd, ID_SC_FLASH_DESK,
                      PAD + MAIN_W + ARROW_GAP, y_d, ARROW_W, BTN_H, is_arrow=True)
    else:
        create_button(g_hwnd, ID_FLASH_DESK, PAD, y_d, BTN_W, BTN_H)

    y_b = CONTENT_TOP
    bx  = SEP_X + PAD

    create_button(g_hwnd, ID_EZI_BROW, bx, y_b, MAIN_BW, BTN_H)
    create_button(g_hwnd, ID_SC_EZI_BROW,
                  bx + MAIN_BW + ARROW_GAP, y_b, ARROW_W, BTN_H, is_arrow=True)
    y_b += BTN_H + BTN_GAP

    if HAS_BROW_KITCHEN:
        create_button(g_hwnd, ID_KITCHEN_BROW, bx, y_b, MAIN_BW, BTN_H)
        create_button(g_hwnd, ID_SC_KITCHEN_BROW,
                      bx + MAIN_BW + ARROW_GAP, y_b, ARROW_W, BTN_H, is_arrow=True)
    else:
        create_button(g_hwnd, ID_KITCHEN_BROW, bx, y_b, bw, BTN_H)
    y_b += BTN_H + BTN_GAP

    if HAS_BROW_SAGE:
        create_button(g_hwnd, ID_SAGE_BROW, bx, y_b, MAIN_BW, BTN_H)
        create_button(g_hwnd, ID_SC_SAGE_BROW,
                      bx + MAIN_BW + ARROW_GAP, y_b, ARROW_W, BTN_H, is_arrow=True)
    else:
        create_button(g_hwnd, ID_SAGE_BROW, bx, y_b, bw, BTN_H)
    y_b += BTN_H + BTN_GAP

    if HAS_BROW_FLASH:
        create_button(g_hwnd, ID_FLASH_BROW, bx, y_b, MAIN_BW, BTN_H)
        create_button(g_hwnd, ID_SC_FLASH_BROW,
                      bx + MAIN_BW + ARROW_GAP, y_b, ARROW_W, BTN_H, is_arrow=True)
    else:
        create_button(g_hwnd, ID_FLASH_BROW, bx, y_b, bw, BTN_H)

    y_u = CONTENT_TOP
    ux  = SEP2_X + PAD

    create_button(g_hwnd, ID_UPD_EASY,       ux, y_u, upd_w, BTN_H)
    y_u += BTN_H + BTN_GAP
    create_button(g_hwnd, ID_UPD_COMFY,      ux, y_u, upd_w, BTN_H)
    y_u += BTN_H + BTN_GAP
    create_button(g_hwnd, ID_SC_UPD_COMFY,   ux, y_u, upd_w, BTN_H)
    y_u += BTN_H + BTN_GAP
    create_button(g_hwnd, ID_UPD_COMFY_NODE, ux, y_u, upd_w, BTN_H)

    fld_pad   = 8
    fld_gap   = 4
    fld_total = WIN_W - fld_pad * 2
    fld_w     = (fld_total - 3 * fld_gap) // 4
    create_button(g_hwnd, ID_TRITON, PAD, CONTENT_TOP + 4 * (BTN_H + BTN_GAP), WIN_W - 2 * PAD, BTN_H)
    fld_y     = WIN_H - FOOTER_H + (FOOTER_H - FOOTER_BTN_H) // 2

    fx = fld_pad
    create_button(g_hwnd, ID_FOLD_OUTPUT,    fx, fld_y, fld_w, FOOTER_BTN_H)
    fx += fld_w + fld_gap
    create_button(g_hwnd, ID_FOLD_INPUT,     fx, fld_y, fld_w, FOOTER_BTN_H)
    fx += fld_w + fld_gap
    create_button(g_hwnd, ID_FOLD_WORKFLOWS, fx, fld_y, fld_w, FOOTER_BTN_H)
    fx += fld_w + fld_gap
    last_w = WIN_W - fld_pad - fx
    create_button(g_hwnd, ID_FOLD_MODELS,    fx, fld_y, last_w, FOOTER_BTN_H)

    user32.ShowWindow(g_hwnd, SW_SHOW)
    user32.UpdateWindow(g_hwnd)
    user32.SetForegroundWindow(g_hwnd)
    user32.SetTimer(g_hwnd, ATTENTION_TIMER, 50, None)
    threading.Thread(target=check_attention_background, daemon=True).start()

    user32.RedrawWindow(g_hwnd, None, None,
                        RDW_INVALIDATE | RDW_UPDATENOW | RDW_ALLCHILDREN)

    msg = wt.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

if __name__ == '__main__':
    main()
