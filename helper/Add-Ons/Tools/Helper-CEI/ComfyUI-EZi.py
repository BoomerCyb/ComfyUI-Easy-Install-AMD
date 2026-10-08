APP_VERSION = "0.1.12-amd"

import sys
import os
import ctypes

try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

def _find_webview2_runtime_exe():
    import glob
    candidates = []
    for env_var in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData"):
        base = os.environ.get(env_var)
        if not base:
            continue
        candidates.extend(glob.glob(os.path.join(base, "Microsoft", "EdgeWebView", "Application", "*", "msedgewebview2.exe")))
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _check_webview2():
    registered = False
    try:
        import winreg
        keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
            (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        ]
        for hive, path in keys:
            try:
                winreg.OpenKey(hive, path)
                registered = True
                break
            except OSError:
                pass
    except Exception:
        pass
    exe_path = _find_webview2_runtime_exe()
    return registered, exe_path


_ezi_wv2_registered, _ezi_wv2_exe = _check_webview2()
_ezi_wv2_registered_but_exe_missing = _ezi_wv2_registered and not _ezi_wv2_exe

if not _ezi_wv2_registered:
    url = "https://developer.microsoft.com/en-us/microsoft-edge/webview2/"
    ctypes.windll.user32.MessageBoxW(
        0,
        "WebView2 Runtime was not found on this system.\n\n"
        "ComfyUI-EZi requires the Microsoft Edge WebView2 Runtime to run.\n\n"
        "Click OK to open the download page in your browser.",
        "ComfyUI-Easy-Install-AMD - WebView2 Runtime Missing",
        0x10
    )
    os.startfile(url)
    sys.exit(1)

try:
    import webview
    from webview.window import FixPoint
except ImportError:
    import sys, subprocess, os
    print("pywebview not found - attempting to install...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pywebview"])
    try:
        import webview
        from webview.window import FixPoint
    except ImportError:
        print("ERROR: pywebview could not be installed. Please run:")
        print("  pip install pywebview")
        sys.exit(1)

_EZI_TOP_RESIZE_GAP = 5
_ezi_bounds_fns = {}


_ezi_wv2_failure_reported = False

def _ezi_report_webview2_failure(exc):
    global _ezi_wv2_failure_reported
    if _ezi_wv2_failure_reported:
        return
    _ezi_wv2_failure_reported = True
    try:
        detail = f"\n\nDetails: {exc}" if exc else ""
        if _ezi_wv2_registered_but_exe_missing:
            reason = (
                "The Microsoft Edge WebView2 Runtime is registered as "
                "installed, but its files could not be found in any of the "
                "usual locations - most likely removed by a \"debloat\"/"
                "privacy tool, or blocked by antivirus."
            )
        else:
            reason = (
                "The Microsoft Edge WebView2 Runtime is installed, but "
                "something is preventing it from running - most commonly a "
                "Group Policy restriction, an AppLocker/Software "
                "Restriction Policy, or antivirus/endpoint-protection "
                "software blocking msedgewebview2.exe."
            )
        ctypes.windll.user32.MessageBoxW(
            0,
            "ComfyUI-EZi could not start its WebView2 window.\n\n" + reason +
            "\n\nCheck whether \"msedgewebview2.exe\" is allowed to run, and "
            "whether Microsoft Edge / Edge WebView2 is blocked for this "
            "user or on this machine." + detail,
            "ComfyUI-Easy-Install-AMD - WebView2 Blocked",
            0x10
        )
    except Exception:
        pass
    os._exit(1)


def _patch_pywebview_for_drag_regions():
    try:
        from webview.platforms import edgechromium as _edge
    except Exception:
        return
    if getattr(_edge.EdgeChrome, '_ezi_drag_region_patched', False):
        return
    _orig_on_webview_ready = _edge.EdgeChrome.on_webview_ready

    def _patched_on_webview_ready(self, sender, args):
        try:
            if getattr(args, 'IsSuccess', True):
                sender.CoreWebView2.Settings.IsNonClientRegionSupportEnabled = True
            else:
                _ezi_report_webview2_failure(getattr(args, 'InitializationException', None))
        except Exception:
            pass
        return _orig_on_webview_ready(self, sender, args)

    _edge.EdgeChrome.on_webview_ready = _patched_on_webview_ready
    _edge.EdgeChrome._ezi_drag_region_patched = True


_EZI_BAR_HEIGHT = 34


def _ezi_dpi_scale(hwnd=None, form=None):
    try:
        if hwnd is None and form is not None:
            hwnd = int(form.Handle.ToInt64())
        if hwnd:
            u = ctypes.windll.user32
            u.GetDpiForWindow.argtypes = [ctypes.c_void_p]
            u.GetDpiForWindow.restype = ctypes.c_uint
            dpi = u.GetDpiForWindow(ctypes.c_void_p(hwnd))
            if dpi:
                return dpi / 96.0
    except Exception:
        pass
    try:
        if form is not None:
            return max(1.0, float(form.DeviceDpi) / 96.0)
    except Exception:
        pass
    return 1.0
_EZI_WINDOW_REF = {"window": None, "shell_expanded": True, "comfy_webview": None, "rec_overlay": None,
                   "comfy_slide_progress": 1.0, "comfy_slide_gen": 0}


def _ezi_cubic_bezier(x1, y1, x2, y2):
    def _bez(a, b, u):
        return 3 * (1 - u) ** 2 * u * a + 3 * (1 - u) * u * u * b + u ** 3

    def _ease(x):
        if x <= 0.0:
            return 0.0
        if x >= 1.0:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(24):
            mid = (lo + hi) / 2.0
            if _bez(x1, x2, mid) < x:
                lo = mid
            else:
                hi = mid
        return _bez(y1, y2, (lo + hi) / 2.0)
    return _ease


def _make_clickthrough(hwnd):
    if not hwnd:
        return
    try:
        import ctypes.wintypes
        GWL_EXSTYLE       = -20
        WS_EX_LAYERED     = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_NOACTIVATE  = 0x08000000
        WS_EX_TOOLWINDOW  = 0x00000080

        user32 = ctypes.windll.user32
        is_64 = ctypes.sizeof(ctypes.c_void_p) == 8
        get_long = user32.GetWindowLongPtrW if is_64 else user32.GetWindowLongW
        set_long = user32.SetWindowLongPtrW if is_64 else user32.SetWindowLongW
        get_long.restype  = ctypes.c_void_p if is_64 else ctypes.c_long
        get_long.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
        set_long.restype  = ctypes.c_void_p if is_64 else ctypes.c_long
        set_long.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_void_p if is_64 else ctypes.c_long]

        want = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        cur = int(get_long(hwnd, GWL_EXSTYLE) or 0)
        new_style = cur | want
        set_long(hwnd, GWL_EXSTYLE, ctypes.c_void_p(new_style) if is_64 else new_style)
        SWP_NOMOVE = 0x0002; SWP_NOSIZE = 0x0001; SWP_NOZORDER = 0x0004; SWP_FRAMECHANGED = 0x0020
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
    except Exception:
        pass


def _patch_pywebview_top_gap():
    try:
        from webview.platforms import edgechromium as _edge
    except Exception:
        return
    if getattr(_edge.EdgeChrome, '_ezi_top_gap_patched', False):
        return
    _orig_init = _edge.EdgeChrome.__init__

    def _patched_init(self, form, window, cache_dir):
        _orig_init(self, form, window, cache_dir)
        if window is not _EZI_WINDOW_REF.get("window"):
            return
        try:
            import System.Windows.Forms as _WinForms
            self.webview.Dock   = getattr(_WinForms.DockStyle, 'None')
            self.webview.Anchor = _WinForms.AnchorStyles.Top | _WinForms.AnchorStyles.Left
            try:
                from System.Drawing import Color as _EziSysColor
                self.webview.DefaultBackgroundColor = _EziSysColor.Transparent
            except Exception:
                pass

            comfy_webview = None
            try:
                _WebView2Class = type(self.webview)
                comfy_webview = _WebView2Class()
                comfy_webview.Anchor = _WinForms.AnchorStyles.Top | _WinForms.AnchorStyles.Left
                try:
                    _comfy_userdata = os.path.join(CURRENT_SCRIPT_DIR, "EZi_cache")
                    os.makedirs(_comfy_userdata, exist_ok=True)
                    from Microsoft.Web.WebView2.WinForms import CoreWebView2CreationProperties as _EziCWV2CP
                    _cprops = _EziCWV2CP()
                    _cprops.UserDataFolder = _comfy_userdata
                    comfy_webview.CreationProperties = _cprops
                except Exception as _cache_err:
                    print("EZi_cache: could not set UserDataFolder:", _cache_err)
                form.Controls.Add(comfy_webview)
                comfy_webview.BringToFront()
                self.webview.BringToFront()
                _EZI_WINDOW_REF["comfy_webview"] = comfy_webview

                def _ezi_init_comfy_webview(sender=None, args=None):
                    try:
                        self.webview.CoreWebView2InitializationCompleted -= _ezi_init_comfy_webview
                    except Exception:
                        pass
                    try:
                        comfy_webview.EnsureCoreWebView2Async(None)
                    except Exception:
                        pass

                def _ezi_on_comfy_message(sender=None, args=None):
                    try:
                        raw = args.WebMessageAsJson
                    except Exception:
                        return
                    if not raw:
                        return
                    try:
                        parsed = json.loads(raw)
                    except Exception:
                        parsed = None
                    if isinstance(parsed, dict) and parsed.get("type") == "ezi_storage_save":
                        try:
                            api_ref = _EZI_WINDOW_REF.get("api")
                            if api_ref is not None:
                                api_ref.save_comfy_storage(json.dumps({
                                    "ls": parsed.get("ls", {}) or {},
                                    "ss": parsed.get("ss", {}) or {},
                                }))
                        except Exception:
                            pass
                        return
                    try:
                        self.webview.CoreWebView2.ExecuteScriptAsync(
                            "window.postMessage(" + raw + ", '*');"
                        )
                    except Exception:
                        pass

                def _ezi_on_comfy_ready(sender=None, args=None):
                    try:
                        ok = getattr(args, 'IsSuccess', True)
                        if not ok:
                            try:
                                exc = getattr(args, 'InitializationException', None)
                                detail = f"\n\nDetails: {exc}" if exc else ""
                                ctypes.windll.user32.MessageBoxW(
                                    0,
                                    "ComfyUI-EZi could not create the ComfyUI display "
                                    "window (a second WebView2 instance)." + detail,
                                    "ComfyUI-Easy-Install-AMD - ComfyUI Display Unavailable",
                                    0x30
                                )
                            except Exception:
                                pass
                            return
                        _EZI_WINDOW_REF["comfy_ready"] = True

                        try:
                            comfy_webview.CoreWebView2.Settings.UserAgent = CHROME_UA
                        except Exception:
                            pass

                        try:
                            comfy_webview.CoreWebView2.CallDevToolsProtocolMethodAsync(
                                "Network.clearBrowserCache", "{}"
                            )
                        except Exception:
                            pass

                        try:
                            _ezi_beforeunload_guard_js = (
                                "(function(){"
                                "try{"
                                "Object.defineProperty(window,'onbeforeunload',{"
                                "get:function(){return null;},"
                                "set:function(){},"
                                "configurable:true"
                                "});"
                                "var _ael=window.EventTarget.prototype.addEventListener;"
                                "window.EventTarget.prototype.addEventListener=function(type,fn,opts){"
                                "if(type==='beforeunload')return;"
                                "return _ael.call(this,type,fn,opts);"
                                "};"
                                "}catch(e){}"
                                "})();"
                            )
                            comfy_webview.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(
                                _ezi_beforeunload_guard_js
                            )
                        except Exception as _beforeunload_guard_err:
                            print("EZi: could not install beforeunload guard:", _beforeunload_guard_err)

                        try:
                            comfy_webview.CoreWebView2.WebMessageReceived += _ezi_on_comfy_message
                        except Exception:
                            pass

                        def _ezi_on_comfy_download_starting(s3=None, e3=None):
                            try:
                                op = getattr(e3, 'DownloadOperation', None)
                                uri = str(getattr(op, 'Uri', '') or '') if op else ''
                                try:
                                    e3.Cancel = True
                                except Exception:
                                    pass
                                if not uri:
                                    return
                                if not _ezi_claim_download(uri):
                                    return

                                suggested = os.path.basename(uri.split('?')[0]) or "download"
                                try:
                                    from urllib.parse import urlparse, parse_qs
                                    qs = parse_qs(urlparse(uri).query)
                                    if qs.get('filename'):
                                        suggested = qs['filename'][0]
                                except Exception:
                                    pass

                                def _do_comfy_download():
                                    api_ref = _EZI_WINDOW_REF.get("api")
                                    println = api_ref._print if api_ref is not None else None
                                    try:
                                        result = window.create_file_dialog(
                                            webview.SAVE_DIALOG,
                                            save_filename=suggested
                                        )
                                        path = result[0] if isinstance(result, (list, tuple)) else result
                                        if not path:
                                            return
                                        _ezi_download_with_progress(
                                            uri, path, println=println, label=suggested,
                                            headers={"User-Agent": "ComfyUI-EZi"}, timeout=120
                                        )
                                        if api_ref is not None:
                                            api_ref._println(f"\033[92m[Download] Saved to {path}\033[0m")
                                    except Exception as ex:
                                        if api_ref is not None:
                                            api_ref._println(f"\033[91m[Download] Error: {ex}\033[0m")

                                threading.Thread(target=_do_comfy_download, daemon=True).start()
                            except Exception as _ds_err:
                                pass

                        try:
                            comfy_webview.CoreWebView2.DownloadStarting += _ezi_on_comfy_download_starting
                        except Exception as _dl_wire_err:
                            pass

                        def _ezi_on_comfy_new_window(s4=None, e4=None):
                            try:
                                uri = str(getattr(e4, 'Uri', '') or '')
                            except Exception:
                                uri = ''
                            if _ezi_is_auth_popup(e4, uri):
                                return
                            try:
                                e4.Handled = True
                            except Exception:
                                pass

                            def _do_new_window():
                                try:
                                    if uri:
                                        if not _ezi_claim_download(uri):
                                            return
                                        import webbrowser
                                        opened = webbrowser.open(uri)
                                except Exception as _nw_err:
                                    pass

                            threading.Thread(target=_do_new_window, daemon=True).start()

                        try:
                            comfy_webview.CoreWebView2.NewWindowRequested += _ezi_on_comfy_new_window
                        except Exception as _nw_wire_err:
                            pass

                        def _ezi_comfy_nav_completed(sender2=None, args2=None):
                            try:
                                self.webview.CoreWebView2.ExecuteScriptAsync(
                                    "if (typeof comfy_webview_ready === 'function') comfy_webview_ready();"
                                )
                            except Exception:
                                pass


                        comfy_webview.CoreWebView2.NavigationCompleted += _ezi_comfy_nav_completed

                        pending_url = _EZI_WINDOW_REF.get("comfy_pending_url")
                        if pending_url:
                            comfy_webview.CoreWebView2.Navigate(pending_url)
                    except Exception:
                        pass

                comfy_webview.CoreWebView2InitializationCompleted += _ezi_on_comfy_ready
                try:
                    if self.webview.CoreWebView2 is not None:
                        comfy_webview.EnsureCoreWebView2Async(None)
                    else:
                        self.webview.CoreWebView2InitializationCompleted += _ezi_init_comfy_webview
                except Exception:
                    self.webview.CoreWebView2InitializationCompleted += _ezi_init_comfy_webview
            except Exception as _e:
                print("Could not create ComfyUI webview:", _e)
                comfy_webview = None

            def _ezi_apply_bounds(sender=None, args=None):
                try:
                    is_maximized = (form.WindowState == _WinForms.FormWindowState.Maximized)
                    gap = 0 if is_maximized else _EZI_TOP_RESIZE_GAP
                    target_w = max(0, form.ClientSize.Width)
                    full_h = max(0, form.ClientSize.Height - gap)
                    _sc = _ezi_dpi_scale(form=form)
                    bar_h = int(round(_EZI_BAR_HEIGHT * _sc))
                    expanded = _EZI_WINDOW_REF.get("shell_expanded", True)
                    if expanded is True:
                        shell_h = full_h
                    elif isinstance(expanded, (int, float)) and expanded > 0:
                        shell_h = min(int(round(expanded * _sc)), full_h)
                    elif comfy_webview is None:
                        shell_h = full_h
                    else:
                        shell_h = bar_h
                    if comfy_webview is not None:
                        ctop = gap + bar_h
                        _prog = _EZI_WINDOW_REF.get("comfy_slide_progress", 1.0)
                        comfy_x = int(round(target_w * (1.0 - _prog))) if _prog < 1.0 else 0
                        comfy_webview.SetBounds(comfy_x, ctop, target_w,
                                                max(0, form.ClientSize.Height - ctop))
                        self.webview.SetBounds(0, gap, target_w,
                                               max(bar_h, shell_h))
                        self.webview.BringToFront()
                    else:
                        self.webview.SetBounds(0, gap, target_w, shell_h)
                except Exception:
                    pass

            form.Resize += _ezi_apply_bounds
            self._ezi_apply_bounds = _ezi_apply_bounds
            _EZI_WINDOW_REF["apply_bounds"] = _ezi_apply_bounds
            _EZI_WINDOW_REF["winforms_form"] = form
            try:
                _ezi_bounds_fns[int(form.Handle.ToInt32())] = _ezi_apply_bounds
            except Exception:
                pass
            try:
                _EZI_WINDOW_REF["main_hwnd"] = int(form.Handle.ToInt64())
            except Exception:
                pass
            _ezi_apply_bounds()
        except Exception:
            pass

    _edge.EdgeChrome.__init__ = _patched_init
    _edge.EdgeChrome._ezi_top_gap_patched = True


import threading as _ezi_threading_early
_EZI_DL_LOCK = _ezi_threading_early.Lock()
_EZI_RECENT_DL_URIS = {}
_EZI_DL_DEDUP_WINDOW = 5.0


def _ezi_claim_download(uri):
    import time
    now = time.time()
    with _EZI_DL_LOCK:
        for k in list(_EZI_RECENT_DL_URIS.keys()):
            if now - _EZI_RECENT_DL_URIS[k] > _EZI_DL_DEDUP_WINDOW:
                del _EZI_RECENT_DL_URIS[k]
        last = _EZI_RECENT_DL_URIS.get(uri)
        if last is not None and (now - last) <= _EZI_DL_DEDUP_WINDOW:
            return False
        _EZI_RECENT_DL_URIS[uri] = now
        return True

_EZI_AUTH_URL_MARKERS = (
    'accounts.google.com',
    'github.com/login',
    'github.com/sessions',
    'login.microsoftonline.com',
    'login.live.com',
    'appleid.apple.com',
    'discord.com/oauth2',
    'discord.com/api/oauth2',
    '/__/auth/',
    '/oauth',
    '/authorize',
    '/api/auth/',
    'firebaseapp.com',
    'auth0.com',
    'clerk.accounts',
)


def _ezi_is_auth_popup(args, uri):
    try:
        low = (uri or '').lower()
        if any(m in low for m in _EZI_AUTH_URL_MARKERS):
            return True
    except Exception:
        pass
    try:
        feats = getattr(args, 'WindowFeatures', None)
        if feats is not None and bool(getattr(feats, 'HasSize', False)):
            return True
    except Exception:
        pass
    return False



def _ezi_format_bytes(n):
    n = float(n)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024.0:
            return f"{n:.1f}{unit}" if unit != 'B' else f"{int(n)}{unit}"
        n /= 1024.0
    return f"{n:.1f}TB"


def _ezi_download_with_progress(url, dest_path, println=None, label=None, headers=None, timeout=30):
    import urllib.request, time

    req = urllib.request.Request(url, headers=headers or {"User-Agent": "ComfyUI-EZi"})
    name = label or os.path.basename(dest_path) or "file"
    tmp_path = dest_path + ".part"
    chunk_size = 262144
    downloaded = 0
    start = time.time()
    last_print = 0.0

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            total = 0
            try:
                total = int(resp.headers.get("Content-Length") or 0)
            except Exception:
                total = 0

            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if println:
                        now = time.time()
                        if now - last_print >= 0.15:
                            last_print = now
                            elapsed = max(now - start, 0.001)
                            speed = downloaded / elapsed
                            speed_txt = f"{_ezi_format_bytes(speed)}/s"
                            if total > 0:
                                pct = min(downloaded / total * 100.0, 100.0)
                                bar_len = 24
                                filled = int(bar_len * downloaded / total)
                                bar = "█" * filled + " " * (bar_len - filled)
                                eta = (total - downloaded) / speed if speed > 0 else 0
                                line = (f"Downloading {name}: {pct:5.1f}%|{bar}| "
                                        f"{_ezi_format_bytes(downloaded)}/{_ezi_format_bytes(total)} "
                                        f"[{speed_txt}, ETA {int(eta)}s]")
                            else:
                                line = f"Downloading {name}: {_ezi_format_bytes(downloaded)} [{speed_txt}]"
                            println(line + "\r")

            if println:
                elapsed = max(time.time() - start, 0.001)
                speed_txt = f"{_ezi_format_bytes(downloaded / elapsed)}/s"
                if total > 0:
                    bar = "█" * 24
                    line = (f"Downloading {name}: 100.0%|{bar}| "
                            f"{_ezi_format_bytes(downloaded)}/{_ezi_format_bytes(total)} [{speed_txt}]")
                else:
                    line = f"Downloading {name}: {_ezi_format_bytes(downloaded)} [{speed_txt}]"
                println(line + "\n")

        os.replace(tmp_path, dest_path)
        return dest_path
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise


def _patch_pywebview_downloads():
    try:
        from webview.platforms import edgechromium as _edge
    except Exception as e:
        return
    if getattr(_edge.EdgeChrome, '_ezi_download_patched', False):
        return
    _orig_on_webview_ready = _edge.EdgeChrome.on_webview_ready

    def _patched_on_webview_ready(self, sender, args):
        try:
            if getattr(args, 'IsSuccess', True):
                core = sender.CoreWebView2

                def _on_download_starting(s, e):
                    try:
                        op = getattr(e, 'DownloadOperation', None)
                        uri = str(getattr(op, 'Uri', '') or '') if op else ''

                        try:
                            e.Cancel = True
                        except Exception as ce:
                            pass

                        if not uri:
                            return
                        if not _ezi_claim_download(uri):
                            return

                        suggested = os.path.basename(uri.split('?')[0]) or "download"
                        try:
                            from urllib.parse import urlparse, parse_qs
                            qs = parse_qs(urlparse(uri).query)
                            if qs.get('filename'):
                                suggested = qs['filename'][0]
                        except Exception as qe:
                            pass

                        def _manual_download():
                            api_ref = _EZI_WINDOW_REF.get("api")
                            println = api_ref._print if api_ref is not None else None
                            try:
                                w = getattr(self, 'window', None) or _EZI_WINDOW_REF.get("window")
                                if w is None:
                                    return
                                result = w.create_file_dialog(
                                    webview.SAVE_DIALOG,
                                    save_filename=suggested
                                )
                                path = result[0] if isinstance(result, (list, tuple)) else result
                                if not path:
                                    return

                                _ezi_download_with_progress(
                                    uri, path, println=println, label=suggested,
                                    headers={"User-Agent": "ComfyUI-EZi"}, timeout=120
                                )
                                if api_ref is not None:
                                    api_ref._println(f"\033[92m[Download] Saved to {path}\033[0m")
                            except Exception as ex:
                                if api_ref is not None:
                                    api_ref._println(f"\033[91m[Download] Error: {ex}\033[0m")

                        threading.Thread(target=_manual_download, daemon=True).start()
                    except Exception as ex:
                        pass

                try:
                    core.DownloadStarting += _on_download_starting
                except Exception as ex:
                    pass

                def _on_new_window(s5=None, e5=None):
                    try:
                        uri = str(getattr(e5, 'Uri', '') or '')
                    except Exception:
                        uri = ''
                    if _ezi_is_auth_popup(e5, uri):
                        return
                    try:
                        e5.Handled = True
                    except Exception:
                        pass

                    def _do_shell_new_window():
                        try:
                            if uri:
                                if not _ezi_claim_download(uri):
                                    return
                                import webbrowser
                                webbrowser.open(uri)
                        except Exception as _snw_err:
                            pass

                    threading.Thread(target=_do_shell_new_window, daemon=True).start()

                try:
                    core.NewWindowRequested += _on_new_window
                except Exception as ex:
                    pass
        except Exception as ex:
            pass
        return _orig_on_webview_ready(self, sender, args)

    _edge.EdgeChrome.on_webview_ready = _patched_on_webview_ready
    _edge.EdgeChrome._ezi_download_patched = True


_patch_pywebview_for_drag_regions()
_patch_pywebview_top_gap()
_patch_pywebview_downloads()

import subprocess
import threading
import json
import re
import codecs
import asyncio
import socket
import shlex
import base64
import time

try:
    from aiohttp import web, ClientSession, ClientTimeout, WSMsgType
except ImportError:
    print("aiohttp not found - install it or use ComfyUI's python_embeded")
    sys.exit(1)


CURRENT_SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))

_DEPR_MARK = '[DEPRECATION WARNING] Detected import of deprecated legacy API:'
_DEPR_HOLD_MAX = len(_DEPR_MARK) + 80
_LINE_TERM_RE = re.compile(r'[\r\n]')

_PTY_ROWS = 40
_winpty_lock = threading.Lock()
_winpty_state = {'tried_install': False}

def _import_winpty():
    try:
        from winpty import PtyProcess
        return PtyProcess, None
    except Exception as e:
        return None, e

def _ensure_winpty(log=None):
    PtyProcess, err = _import_winpty()
    if PtyProcess:
        return PtyProcess, None
    with _winpty_lock:
        PtyProcess, err = _import_winpty()
        if PtyProcess or _winpty_state['tried_install']:
            return PtyProcess, err
        _winpty_state['tried_install'] = True
        try:
            exe = sys.executable
            if os.path.basename(exe).lower() == 'pythonw.exe':
                cand = os.path.join(os.path.dirname(exe), 'python.exe')
                if os.path.isfile(cand):
                    exe = cand
            if log:
                log("\033[93m[Console] pywinpty not found - installing it (needed for live pip progress bars)...\033[0m")
            r = subprocess.run([exe, '-m', 'pip', 'install', 'pywinpty', '--only-binary=:all:',
                                '--no-warn-script-location', '--disable-pip-version-check'],
                               capture_output=True, timeout=180, creationflags=0x08000000)
            if r.returncode != 0:
                tail = (r.stdout + r.stderr).decode('utf-8', errors='replace').strip().splitlines()[-1:]
                return None, RuntimeError('pip install pywinpty failed: ' + (tail[0] if tail else r.returncode))
            import importlib
            importlib.invalidate_caches()
            PtyProcess, err = _import_winpty()
            if log:
                if PtyProcess:
                    log("\033[92m[Console] pywinpty installed - live progress bars enabled.\033[0m")
                else:
                    log(f"\033[93m[Console] pywinpty installed but cannot be loaded: {err}\033[0m")
            return PtyProcess, err
        except Exception as e:
            return None, e

def _spawn_pty(cmd, cwd, env, cols, log=None):
    PtyProcess, err = _ensure_winpty(log)
    if PtyProcess is None:
        return None, err
    try:
        return PtyProcess.spawn([str(c) for c in cmd], cwd=cwd,
                                env={k: str(v) for k, v in env.items()},
                                dimensions=(_PTY_ROWS, max(40, int(cols)))), None
    except Exception as e:
        return None, e

ROOT_DIR = os.path.normpath(os.path.join(CURRENT_SCRIPT_DIR, "..", "..", ".."))
os.environ["PIP_CONSTRAINT"] = os.path.join(ROOT_DIR, "amd", "amd-constraints.txt")
os.environ["UV_CONSTRAINT"] = os.environ["PIP_CONSTRAINT"]
sys.path.insert(0, os.path.join(ROOT_DIR, "amd"))

ICO_PATH = os.path.join(CURRENT_SCRIPT_DIR, "ComfyUI-EZi-Desktop.ico")
SETTINGS_PATH = os.path.join(CURRENT_SCRIPT_DIR, "ComfyUI-EZi.settings.json")

EZI_UA_TAG = "ComfyUI-EZi-Desktop"

def _get_browser_version():
    from windows_tools import browser_version
    return browser_version()

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    f"(KHTML, like Gecko) Chrome/{_get_browser_version()} Safari/537.36 {EZI_UA_TAG}/{APP_VERSION}"
)

_argv_rest = sys.argv[1:]
DEV_MODE = '--dev' in _argv_rest
_argv_rest = [a for a in _argv_rest if a != '--dev']
_bat_arg = _argv_rest[0] if _argv_rest else "Start ComfyUI.bat"
BAT_FILE = _bat_arg if os.path.isabs(_bat_arg) else os.path.join(ROOT_DIR, _bat_arg)
COMFY_PORT = 8188

COMFYUI_URL_RE = re.compile(
    r'To see the GUI go to:\s+https?://(?:127\.0\.0\.1|localhost|0\.0\.0\.0):(\d+)',
    re.IGNORECASE
)

def _setup_path():
    try:
        subprocess.run(['cmd', '/c', 'chcp', '65001'],
                       capture_output=True, creationflags=0x08000000)
    except Exception:
        pass
    windir = os.environ.get('windir', r'C:\Windows')
    localappdata = os.environ.get('LOCALAPPDATA', '')
    extra = []

    try:
        r = subprocess.run(
            ['cmd', '/c', 'where.exe', 'git.exe'],
            capture_output=True, timeout=5, creationflags=0x08000000
        )
        if r.returncode == 0:
            git_path = r.stdout.decode(errors='replace').strip().splitlines()[0]
            git_dir = os.path.dirname(git_path)
            if git_dir:
                extra.append(git_dir)
    except Exception:
        pass

    extra += [
        os.path.join(windir, 'System32'),

        os.path.join(localappdata, 'Microsoft', 'WindowsApps'),
    ]

    current = os.environ.get('PATH', '')
    additions = [p for p in extra if p and p.lower() not in current.lower()]
    if additions:
        os.environ['PATH'] = ';'.join(additions) + ';' + current

_setup_path()


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


_ATTN_BAT_FLAGS = {
    'start comfyui kitchenattention.bat': '--use-ck-attention',
    'start comfyui sageattention.bat':    '--use-sage-attention',
    'start comfyui flashattention.bat':   '--use-flash-attention',
}


def _required_attn_flag(bat_path):
    return _ATTN_BAT_FLAGS.get(os.path.basename(bat_path or '').lower())


def _ensure_attention_flags():
    for bat_lower, flag in _ATTN_BAT_FLAGS.items():
        try:
            bat_path = None
            if os.path.isdir(ROOT_DIR):
                for fn in os.listdir(ROOT_DIR):
                    if fn.lower() == bat_lower:
                        bat_path = os.path.join(ROOT_DIR, fn)
                        break
            if not bat_path or not os.path.isfile(bat_path):
                continue
            with open(bat_path, 'r', encoding='utf-8', errors='replace', newline='') as f:
                content = f.read()
            lines = content.splitlines(keepends=True)
            flag_re = re.compile(r'(?<![\w-])' + re.escape(flag) + r'(?![\w-])')
            i = 0
            while i < len(lines):
                j = i
                acc = lines[i].rstrip('\r\n')
                while acc.rstrip().endswith('^') and j + 1 < len(lines):
                    acc = acc.rstrip()[:-1] + ' ' + lines[j + 1].lstrip().rstrip('\r\n')
                    j += 1
                acc_s = acc.strip()
                if (acc_s and
                        not acc_s.startswith('::') and
                        not re.match(r'(?i)^rem(\s|$)', acc_s) and
                        re.search(r'python_embeded[/\\]python\.exe', acc_s, re.IGNORECASE) and
                        re.search(r'(?:ComfyUI[/\\]main|amd[/\\]runtime)\.py', acc_s, re.IGNORECASE)):
                    if flag_re.search(acc_s):
                        break
                    for k in range(i, j + 1):
                        new_line, n = re.subn(r'(?i)((?:main|runtime)\.py["\']?)',
                                              lambda m: m.group(1) + ' ' + flag,
                                              lines[k], count=1)
                        if n:
                            lines[k] = new_line
                            with open(bat_path, 'w', encoding='utf-8', newline='') as f:
                                f.write(''.join(lines))
                            break
                    break
                i = j + 1
        except Exception:
            pass


def _get_hwnd(window):
    _vp = ctypes.c_void_p
    try:
        if window is not None and window is _EZI_WINDOW_REF.get("window"):
            h = _EZI_WINDOW_REF.get("main_hwnd")
            if h and ctypes.windll.user32.IsWindow(h):
                return h
    except Exception:
        pass
    try:
        nh = window.native_handle
        if nh:
            return nh
    except Exception:
        pass
    try:
        user = ctypes.windll.user32
        current_pid = os.getpid()
        found = ctypes.c_void_p(0)

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, _vp, ctypes.POINTER(ctypes.c_long))

        def _enum_cb(hwnd, _lparam):
            pid = ctypes.c_ulong(0)
            user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == current_pid:
                if user.IsWindowVisible(hwnd) and user.GetParent(hwnd) == 0:
                    found.value = hwnd
                    return False
            return True

        user.EnumWindows(WNDENUMPROC(_enum_cb), 0)
        if found.value:
            return found.value
    except Exception:
        pass
    return None

def _set_window_icon(hwnd):
    if not hwnd or not os.path.exists(ICO_PATH):
        return
    try:
        ico = ctypes.windll.user32.LoadImageW(
            None, ICO_PATH, 1, 0, 0, 0x00000010 | 0x00000040
        )
        if ico:
            ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, ico)
            ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, ico)
    except Exception:
        pass


import ctypes.wintypes as _wt

_MONITOR_DEFAULTTONEAREST = 2

class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", _wt.DWORD), ("rcMonitor", _wt.RECT),
                ("rcWork", _wt.RECT), ("dwFlags", _wt.DWORD)]

class EZI_WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [
        ("length",           ctypes.c_uint),
        ("flags",            ctypes.c_uint),
        ("showCmd",          ctypes.c_uint),
        ("ptMinPosition",    _wt.POINT),
        ("ptMaxPosition",    _wt.POINT),
        ("rcNormalPosition", _wt.RECT),
    ]

def _apply_captioned_frame_style(hwnd):
    if not hwnd:
        return
    try:
        import ctypes.wintypes
        GWL_STYLE      = -16
        WS_CAPTION     = 0x00C00000
        WS_SYSMENU     = 0x00080000
        WS_MINIMIZEBOX = 0x00020000
        WS_MAXIMIZEBOX = 0x00010000
        WS_THICKFRAME  = 0x00040000
        SWP_NOMOVE       = 0x0002
        SWP_NOSIZE       = 0x0001
        SWP_NOZORDER     = 0x0004
        SWP_FRAMECHANGED = 0x0020

        user32 = ctypes.windll.user32
        is_64 = ctypes.sizeof(ctypes.c_void_p) == 8
        get_long = user32.GetWindowLongPtrW if is_64 else user32.GetWindowLongW
        set_long = user32.SetWindowLongPtrW if is_64 else user32.SetWindowLongW
        get_long.restype  = ctypes.c_void_p if is_64 else ctypes.c_long
        get_long.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
        set_long.restype  = ctypes.c_void_p if is_64 else ctypes.c_long
        set_long.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_void_p if is_64 else ctypes.c_long]

        want = WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_THICKFRAME
        cur = int(get_long(hwnd, GWL_STYLE) or 0)
        if (cur & want) == want:
            return
        new_style = cur | want
        set_long(hwnd, GWL_STYLE, ctypes.c_void_p(new_style) if is_64 else new_style)
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
    except Exception:
        pass


_hidden_titlebar_hooks = {}

_last_normal_rect = {}
_win_size_state   = {}
_correcting_rect  = set()
_in_sizemove      = set()
_settings_ref     = {"obj": None}


def _get_rect_now(user32, hwnd_):
    import ctypes.wintypes as wt
    rc = wt.RECT()
    if user32.GetWindowRect(hwnd_, ctypes.byref(rc)):
        return [rc.left, rc.top, rc.right, rc.bottom]
    return None

def _snap_rect(hwnd_, rect, tag=""):
    try:
        user32 = ctypes.windll.user32
        l, t, r, b = rect
        w, h = r - l, b - t
        if w <= 50 or h <= 50:
            return
        before = _get_rect_now(user32, hwnd_)
        SWP_NOZORDER   = 0x0004
        SWP_NOACTIVATE = 0x0010
        user32.SetWindowPos(hwnd_, None, l, t, w, h, SWP_NOZORDER | SWP_NOACTIVATE)
        after = _get_rect_now(user32, hwnd_)
    except Exception as e:
        pass

def _schedule_reapply(hwnd_, rect):
    import threading as _th
    for delay in (0.05, 0.15, 0.35, 0.7, 1.2):
        _th.Timer(delay, lambda d=delay: _snap_rect(hwnd_, rect, tag=f"+{d}s")).start()

def _install_hidden_titlebar_hook(hwnd):
    if not hwnd or hwnd in _hidden_titlebar_hooks:
        return
    try:
        import ctypes.wintypes as wt

        GWLP_WNDPROC  = -4
        WM_NCCALCSIZE = 0x0083
        WM_NCACTIVATE = 0x0086
        WM_NCHITTEST  = 0x0084
        WM_GETMINMAXINFO = 0x0024
        WM_ACTIVATE   = 0x0006
        WM_SIZE       = 0x0005
        WM_DPICHANGED = 0x02E0
        WM_ENTERSIZEMOVE = 0x0231
        WM_EXITSIZEMOVE = 0x0232
        SIZE_RESTORED  = 0
        SIZE_MINIMIZED = 1
        SIZE_MAXIMIZED = 2
        MONITOR_DEFAULTTONEAREST = 2
        HTTOP      = 12
        HTTOPLEFT  = 13
        HTTOPRIGHT = 14
        SM_CXSIZEFRAME    = 32
        SM_CXPADDEDBORDER = 92

        user32 = ctypes.windll.user32

        class _NCCALCSIZE_PARAMS(ctypes.Structure):
            _fields_ = [('rgrc', wt.RECT * 3), ('lppos', ctypes.c_void_p)]

        class _MONITORINFO(ctypes.Structure):
            _fields_ = [
                ('cbSize',    ctypes.c_ulong),
                ('rcMonitor', wt.RECT),
                ('rcWork',    wt.RECT),
                ('dwFlags',   ctypes.c_ulong),
            ]

        class _MINMAXINFO(ctypes.Structure):
            _fields_ = [
                ('ptReserved',     wt.POINT),
                ('ptMaxSize',      wt.POINT),
                ('ptMaxPosition',  wt.POINT),
                ('ptMinTrackSize', wt.POINT),
                ('ptMaxTrackSize', wt.POINT),
            ]

        user32.SetWindowLongPtrW.restype  = ctypes.c_void_p
        user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_void_p]
        user32.CallWindowProcW.restype    = ctypes.c_ssize_t
        user32.CallWindowProcW.argtypes   = [ctypes.c_void_p, wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
        user32.DefWindowProcW.restype     = ctypes.c_ssize_t
        user32.DefWindowProcW.argtypes    = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
        user32.IsZoomed.argtypes          = [wt.HWND]
        user32.IsIconic.argtypes          = [wt.HWND]
        user32.MonitorFromWindow.restype  = ctypes.c_void_p
        user32.MonitorFromWindow.argtypes = [wt.HWND, ctypes.c_uint]
        user32.MonitorFromRect.restype    = ctypes.c_void_p
        user32.MonitorFromRect.argtypes   = [ctypes.POINTER(wt.RECT), ctypes.c_uint]
        user32.GetMonitorInfoW.argtypes   = [ctypes.c_void_p, ctypes.c_void_p]
        user32.GetWindowPlacement.argtypes = [wt.HWND, ctypes.POINTER(EZI_WINDOWPLACEMENT)]
        user32.SetWindowPlacement.argtypes = [wt.HWND, ctypes.POINTER(EZI_WINDOWPLACEMENT)]

        user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]

        def _ezi_resolve_target_monitor(hwnd_):
            try:
                rc = wt.RECT()
                stale_offscreen = False
                if user32.GetWindowRect(hwnd_, ctypes.byref(rc)):
                    if rc.left <= -20000 or rc.top <= -20000:
                        stale_offscreen = True
                if user32.IsIconic(hwnd_) or stale_offscreen:
                    wp = EZI_WINDOWPLACEMENT()
                    wp.length = ctypes.sizeof(EZI_WINDOWPLACEMENT)
                    if user32.GetWindowPlacement(hwnd_, ctypes.byref(wp)):
                        mon = user32.MonitorFromRect(ctypes.byref(wp.rcNormalPosition), MONITOR_DEFAULTTONEAREST)
                        if mon:
                            return mon
            except Exception:
                pass
            return user32.MonitorFromWindow(hwnd_, MONITOR_DEFAULTTONEAREST)

        WNDPROC_TYPE = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM)

        def _wndproc(hwnd_, msg, wparam, lparam):
            try:
                if msg == WM_GETMINMAXINFO:
                    try:
                        user32.CallWindowProcW(holder['orig'], hwnd_, msg, wparam, lparam)
                        mmi = ctypes.cast(lparam, ctypes.POINTER(_MINMAXINFO)).contents
                        mon = _ezi_resolve_target_monitor(hwnd_)
                        if mon:
                            mi = _MONITORINFO()
                            mi.cbSize = ctypes.sizeof(_MONITORINFO)
                            if user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
                                mmi.ptMaxPosition.x = mi.rcWork.left - mi.rcMonitor.left
                                mmi.ptMaxPosition.y = mi.rcWork.top - mi.rcMonitor.top
                                mmi.ptMaxSize.x = mi.rcWork.right - mi.rcWork.left
                                mmi.ptMaxSize.y = mi.rcWork.bottom - mi.rcWork.top
                    except Exception:
                        pass
                    return 0

                if msg == WM_NCCALCSIZE and wparam:
                    params = ctypes.cast(lparam, ctypes.POINTER(_NCCALCSIZE_PARAMS)).contents
                    if user32.IsZoomed(hwnd_):
                        mon = _ezi_resolve_target_monitor(hwnd_)
                        if mon:
                            mi = _MONITORINFO()
                            mi.cbSize = ctypes.sizeof(_MONITORINFO)
                            if user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
                                params.rgrc[0].left   = mi.rcWork.left
                                params.rgrc[0].top    = mi.rcWork.top
                                params.rgrc[0].right  = mi.rcWork.right
                                params.rgrc[0].bottom = mi.rcWork.bottom
                        return 0
                    original_top = params.rgrc[0].top
                    ret = user32.DefWindowProcW(hwnd_, msg, wparam, lparam)
                    params.rgrc[0].top = original_top
                    return ret

                if msg == WM_NCHITTEST:
                    try:
                        if not user32.IsZoomed(hwnd_) and not user32.IsIconic(hwnd_):
                            x = ctypes.c_short(lparam & 0xFFFF).value
                            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                            rc = wt.RECT()
                            if user32.GetWindowRect(hwnd_, ctypes.byref(rc)):
                                if rc.top <= y < rc.top + _EZI_TOP_RESIZE_GAP:
                                    h_margin = user32.GetSystemMetrics(SM_CXSIZEFRAME) + \
                                               user32.GetSystemMetrics(SM_CXPADDEDBORDER)
                                    if h_margin <= 0:
                                        h_margin = 8
                                    if x < rc.left + h_margin:
                                        return HTTOPLEFT
                                    elif x >= rc.right - h_margin:
                                        return HTTOPRIGHT
                                    else:
                                        return HTTOP
                    except Exception:
                        pass

                if msg == WM_NCACTIVATE:
                    _reapply_no_border(hwnd_)
                    return user32.DefWindowProcW(hwnd_, msg, wparam, lparam)

                if msg == WM_ACTIVATE:
                    _reapply_no_border(hwnd_)

                if msg == WM_ENTERSIZEMOVE:
                    _in_sizemove.add(hwnd_)

                if msg == WM_DPICHANGED:
                    try:
                        rc = ctypes.cast(lparam, ctypes.POINTER(wt.RECT)).contents
                        SWP_NOZORDER   = 0x0004
                        SWP_NOACTIVATE = 0x0010
                        user32.SetWindowPos(
                            hwnd_, None, rc.left, rc.top,
                            rc.right - rc.left, rc.bottom - rc.top,
                            SWP_NOZORDER | SWP_NOACTIVATE
                        )
                    except Exception:
                        pass
                    try:
                        fn = _ezi_bounds_fns.get(int(hwnd_))
                        if fn:
                            fn()
                        import threading as _th
                        for _delay in (0.05, 0.15, 0.35):
                            _th.Timer(_delay, lambda f=fn: f() if f else None).start()
                    except Exception:
                        pass

                if msg == WM_SIZE:
                    cur_state  = int(wparam)
                    prev_state = _win_size_state.get(hwnd_, SIZE_RESTORED)
                    _win_size_state[hwnd_] = cur_state

                    really_restored = (cur_state == SIZE_RESTORED
                                        and not user32.IsZoomed(hwnd_)
                                        and not user32.IsIconic(hwnd_))

                    if really_restored and prev_state in (SIZE_MAXIMIZED, SIZE_MINIMIZED) \
                            and hwnd_ not in _correcting_rect and hwnd_ not in _in_sizemove:
                        saved = _last_normal_rect.get(hwnd_)
                        if not saved:
                            try:
                                s_obj = _settings_ref.get("obj") or {}
                                wp = s_obj.get("window_placement") or {}
                                rc_data = wp.get("rcNormalPosition")
                                if rc_data and len(rc_data) == 4:
                                    saved = rc_data
                            except Exception:
                                saved = None
                        if saved:
                            l, t, r, b = saved
                            w, h = r - l, b - t
                            if w > 50 and h > 50:
                                def _deferred_restore_fix(target=(l, t, r, b), hh=hwnd_):
                                    try:
                                        if hh in _correcting_rect:
                                            return
                                        if user32.IsZoomed(hh) or user32.IsIconic(hh) \
                                                or hh in _in_sizemove:
                                            return
                                        rc2 = wt.RECT()
                                        if not user32.GetWindowRect(hh, ctypes.byref(rc2)):
                                            return
                                        cur = (rc2.left, rc2.top, rc2.right, rc2.bottom)
                                        if all(abs(cur[i] - target[i]) <= 3 for i in range(4)):
                                            return
                                        _correcting_rect.add(hh)
                                        try:
                                            wp_native = EZI_WINDOWPLACEMENT()
                                            wp_native.length = ctypes.sizeof(EZI_WINDOWPLACEMENT)
                                            wp_native.showCmd = 1
                                            wp_native.rcNormalPosition = wt.RECT(*target)
                                            user32.SetWindowPlacement(hh, ctypes.byref(wp_native))
                                        finally:
                                            _correcting_rect.discard(hh)
                                    except Exception:
                                        pass
                                import threading as _th
                                _th.Timer(0.1, _deferred_restore_fix).start()
                            try:
                                s_obj = _settings_ref.get("obj")
                                if s_obj is not None:
                                    wp2 = s_obj.get("window_placement")
                                    if not isinstance(wp2, dict):
                                        wp2 = {}
                                    wp2["rcNormalPosition"] = [l, t, r, b]
                                    wp2["showCmd"] = 1
                                    s_obj["window_placement"] = wp2
                                    _save_settings(s_obj)
                            except Exception:
                                pass
                    elif really_restored:
                        rc = wt.RECT()
                        if user32.GetWindowRect(hwnd_, ctypes.byref(rc)):
                            rect_now = [rc.left, rc.top, rc.right, rc.bottom]
                            _last_normal_rect[hwnd_] = rect_now
                            try:
                                s_obj = _settings_ref.get("obj")
                                if s_obj is not None:
                                    wp = s_obj.get("window_placement")
                                    if not isinstance(wp, dict):
                                        wp = {}
                                    wp["rcNormalPosition"] = rect_now
                                    wp["showCmd"] = 1
                                    s_obj["window_placement"] = wp
                            except Exception:
                                pass

                if msg == WM_EXITSIZEMOVE:
                    _in_sizemove.discard(hwnd_)
                    try:
                        if not user32.IsZoomed(hwnd_) and not user32.IsIconic(hwnd_) \
                                and hwnd_ not in _correcting_rect:
                            rc = wt.RECT()
                            if user32.GetWindowRect(hwnd_, ctypes.byref(rc)):
                                rect_now = [rc.left, rc.top, rc.right, rc.bottom]
                                _last_normal_rect[hwnd_] = rect_now
                                try:
                                    s_obj = _settings_ref.get("obj")
                                    if s_obj is not None:
                                        wp = s_obj.get("window_placement")
                                        if not isinstance(wp, dict):
                                            wp = {}
                                        wp["rcNormalPosition"] = rect_now
                                        wp["showCmd"] = 1
                                        s_obj["window_placement"] = wp
                                        _save_settings(s_obj)
                                except Exception:
                                    pass
                    except Exception:
                        pass
            except Exception:
                pass
            return user32.CallWindowProcW(holder['orig'], hwnd_, msg, wparam, lparam)

        holder = {'orig': None}
        ref = WNDPROC_TYPE(_wndproc)
        holder['orig'] = user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(ref, ctypes.c_void_p))
        _hidden_titlebar_hooks[hwnd] = {'ref': ref, 'orig': holder['orig']}
        _apply_win11_rounded_corners(hwnd)
    except Exception:
        pass

def _reapply_no_border(hwnd):
    if not hwnd:
        return
    try:
        dwmapi = ctypes.windll.dwmapi
        DWMWA_BORDER_COLOR = 34
        DWMWA_COLOR_DEFAULT = ctypes.c_int(-1)
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_BORDER_COLOR,
                                      ctypes.byref(DWMWA_COLOR_DEFAULT),
                                      ctypes.sizeof(DWMWA_COLOR_DEFAULT))
    except Exception:
        pass


def _apply_win11_rounded_corners(hwnd):
    if not hwnd:
        return
    try:
        dwmapi = ctypes.windll.dwmapi
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWC_ROUND = ctypes.c_int(2)
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                                      ctypes.byref(DWMWC_ROUND),
                                      ctypes.sizeof(DWMWC_ROUND))
    except Exception:
        pass


def _force_full_repaint(hwnd):
    if not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        RDW_INVALIDATE   = 0x0001
        RDW_ERASE        = 0x0004
        RDW_ALLCHILDREN  = 0x0080
        RDW_UPDATENOW    = 0x0100
        RDW_FRAME        = 0x0400
        user32.RedrawWindow(
            hwnd, None, None,
            RDW_INVALIDATE | RDW_ERASE | RDW_FRAME | RDW_ALLCHILDREN | RDW_UPDATENOW
        )
    except Exception:
        pass


def _suppress_dwm_border(hwnd):
    if not hwnd:
        return
    try:
        _reapply_no_border(hwnd)
        SWP_NOMOVE       = 0x0002
        SWP_NOSIZE       = 0x0001
        SWP_NOZORDER     = 0x0004
        SWP_NOACTIVATE   = 0x0010
        SWP_FRAMECHANGED = 0x0020
        ctypes.windll.user32.SetWindowPos(
            hwnd, None, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
        )
    except Exception:
        pass


import struct as _struct

def _guid_bytes(s):
    s = s.replace('{','').replace('}','').replace('-','')
    d1 = int(s[0:8],  16)
    d2 = int(s[8:12], 16)
    d3 = int(s[12:16],16)
    d4 = bytes(int(s[16+i*2:18+i*2],16) for i in range(8))
    return _struct.pack('<IHH', d1, d2, d3) + d4


_CLSID_TaskbarList = _guid_bytes('56FDF344-FD6D-11d0-958A-006097C9A090')
_IID_ITaskbarList3 = _guid_bytes('EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF')

_TBPF_NOPROGRESS    = 0
_TBPF_INDETERMINATE = 1
_TBPF_NORMAL        = 2
_TBPF_ERROR         = 4
_TBPF_PAUSED        = 8

_taskbar_com_obj  = None
_taskbar_com_lock = __import__('threading').Lock()

def _get_taskbar_obj():
    global _taskbar_com_obj
    if _taskbar_com_obj is not None:
        return _taskbar_com_obj
    with _taskbar_com_lock:
        if _taskbar_com_obj is not None:
            return _taskbar_com_obj
        try:
            ole32 = ctypes.windll.ole32
            ole32.CoInitializeEx(None, 0)
            clsid = ctypes.create_string_buffer(_CLSID_TaskbarList, 16)
            iid   = ctypes.create_string_buffer(_IID_ITaskbarList3,  16)
            obj   = ctypes.c_void_p()
            hr = ole32.CoCreateInstance(
                ctypes.byref(clsid), None, 1,
                ctypes.byref(iid), ctypes.byref(obj)
            )
            if hr != 0 or not obj:
                return None
            vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p))
            base = ctypes.cast(vtbl[0], ctypes.POINTER(ctypes.c_void_p))
            _F   = ctypes.WINFUNCTYPE
            _P   = ctypes.c_void_p
            _ULL = ctypes.c_ulonglong
            _INT = ctypes.c_int
            _LONG= ctypes.c_long
            hr2 = _F(_LONG, _P)(base[3])(obj)
            if hr2 != 0:
                return None
            _taskbar_com_obj = {
                'obj': obj,
                'MarkFullscreenWindow': _F(_LONG, _P, _P, _INT)(base[8]),
                'SetProgressValue': _F(_LONG, _P, _P, _ULL, _ULL)(base[9]),
                'SetProgressState': _F(_LONG, _P, _P, _INT)(base[10]),
            }
            return _taskbar_com_obj
        except Exception:
            return None

def _taskbar_mark_not_fullscreen(hwnd):
    if not hwnd:
        return
    try:
        tb = _get_taskbar_obj()
        if not tb:
            return
        tb['MarkFullscreenWindow'](tb['obj'], ctypes.c_void_p(hwnd), 0)
    except Exception:
        pass

def _taskbar_progress_ctypes(hwnd, value, maximum, state=2):
    if not hwnd:
        return
    try:
        tb = _get_taskbar_obj()
        if not tb:
            return
        hwnd_p = ctypes.c_void_p(hwnd)
        tb['SetProgressState'](tb['obj'], hwnd_p, state)
        if state == _TBPF_NORMAL and maximum > 0:
            tb['SetProgressValue'](tb['obj'], hwnd_p,
                                   ctypes.c_ulonglong(value),
                                   ctypes.c_ulonglong(maximum))
    except Exception:
        pass


def _get_desktop():
    try:
        import ctypes.wintypes
        buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(0, 0x0000, 0, 0, buf)
        path = buf.value
        if path and os.path.isdir(path):
            return path
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Desktop")

def _get_comfy_user_dir():
    user_dir = None
    if os.path.exists(BAT_FILE):
        try:
            with open(BAT_FILE, 'r', encoding='utf-8', errors='replace') as f:
                bat_content = f.read()
            m_env = re.search(r'(?i)set\s+"?COMFY_USER_DIR=([^"\n]+)"?', bat_content)
            if m_env:
                user_dir = m_env.group(1).strip().strip('"')
            else:
                comfy_line = _find_bat_comfy_line(bat_content)
                if comfy_line:
                    m = re.search(r'python_embeded[/\\]python\.exe["\']?\s+(.*)',
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


def _get_manager_config_path():
    user_dir_with_default = _get_comfy_user_dir()
    user_dir = os.path.dirname(user_dir_with_default)
    return os.path.join(user_dir, '__manager', 'config.ini')


def _get_comfy_current_theme():
    try:
        user_dir = _get_comfy_user_dir()
        settings_file = os.path.join(user_dir, 'comfy.settings.json')
        if os.path.exists(settings_file):
            with open(settings_file, 'r', encoding='utf-8', errors='replace') as f:
                data = json.load(f)
            palette_id = data.get('Comfy.ColorPalette', '')
            if not palette_id:
                palette_id = 'dark'
            return str(palette_id)
    except Exception:
        pass
    return ''


def _get_builtin_palettes_from_frontend():
    site_pkgs = os.path.join(ROOT_DIR, 'python_embeded', 'Lib', 'site-packages')
    if not os.path.isdir(site_pkgs):
        return {}

    pkg_dir = os.path.join(site_pkgs, 'comfyui_frontend_package')
    if not os.path.isdir(pkg_dir):
        import glob as _glob
        candidates = _glob.glob(os.path.join(site_pkgs, 'comfyui_frontend_package*'))
        pkg_dir = next((c for c in candidates if os.path.isdir(c) and 'dist-info' not in c), None)
        if not pkg_dir:
            return {}

    palettes_dir = os.path.join(pkg_dir, 'static', 'assets', 'palettes')
    if not os.path.isdir(palettes_dir):
        return {}

    palettes = {}
    try:
        for fname in os.listdir(palettes_dir):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(palettes_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    data = json.load(f)
                pid = data.get('id')
                colors = data.get('colors', {})
                if pid and colors:
                    palettes[pid] = colors
            except Exception:
                continue
    except Exception:
        return {}

    return palettes


_BUILTIN_PALETTES_CACHE = None

_COMMON_NODE_SLOT = {
    'CLIP': '#FFD500', 'CLIP_VISION': '#A8DADC', 'CLIP_VISION_OUTPUT': '#ad7452',
    'CONDITIONING': '#FFA931', 'CONTROL_NET': '#6EE7B7', 'IMAGE': '#64B5F6',
    'LATENT': '#FF9CF9', 'MASK': '#81C784', 'MODEL': '#B39DDB',
    'STYLE_MODEL': '#C2FFAE', 'VAE': '#FF6E6E', 'NOISE': '#B0B0B0',
    'GUIDER': '#66FFFF', 'SAMPLER': '#ECB4B4', 'SIGMAS': '#CDFFCD', 'TAESD': '#DCC274',
}

_FALLBACK_PALETTES = {
    'dark': {
        'node_slot': _COMMON_NODE_SLOT,
        'litegraph_base': {
            'CLEAR_BACKGROUND_COLOR': '#141414', 'NODE_TITLE_COLOR': '#999',
            'NODE_SELECTED_TITLE_COLOR': '#FFF', 'NODE_TEXT_COLOR': '#AAA',
            'NODE_TEXT_HIGHLIGHT_COLOR': '#FFF', 'NODE_DEFAULT_COLOR': '#333',
            'NODE_DEFAULT_BGCOLOR': '#353535', 'NODE_DEFAULT_BOXCOLOR': '#666',
            'NODE_DEFAULT_SHAPE': 2, 'NODE_BOX_OUTLINE_COLOR': '#FFF',
            'NODE_BYPASS_BGCOLOR': '#FF00FF', 'NODE_ERROR_COLOUR': '#E00',
            'DEFAULT_SHADOW_COLOR': 'rgba(0,0,0,0.5)', 'WIDGET_BGCOLOR': '#222',
            'WIDGET_OUTLINE_COLOR': '#666', 'WIDGET_TEXT_COLOR': '#DDD',
            'WIDGET_SECONDARY_TEXT_COLOR': '#999', 'WIDGET_DISABLED_TEXT_COLOR': '#666',
            'LINK_COLOR': '#9A9', 'EVENT_LINK_COLOR': '#A86', 'CONNECTING_LINK_COLOR': '#AFA',
            'BADGE_FG_COLOR': '#FFF', 'BADGE_BG_COLOR': '#0F1F0F',
        },
        'comfy_base': {
            'fg-color': '#fff', 'bg-color': '#202020', 'comfy-menu-bg': '#171718',
            'comfy-menu-secondary-bg': '#303030', 'comfy-input-bg': '#222',
            'input-text': '#ddd', 'descrip-text': '#999', 'drag-text': '#ccc',
            'error-text': '#ff4444', 'border-color': '#4e4e4e',
            'tr-even-bg-color': '#222', 'tr-odd-bg-color': '#353535',
            'content-bg': '#4e4e4e', 'content-fg': '#fff',
            'content-hover-bg': '#222', 'content-hover-fg': '#fff',
            'bar-shadow': 'rgba(16, 16, 16, 0.5) 0 0 0.5rem',
        },
    },
    'light': {
        'node_slot': _COMMON_NODE_SLOT,
        'litegraph_base': {
            'CLEAR_BACKGROUND_COLOR': '#e0e0e0', 'NODE_TITLE_COLOR': '#222',
            'NODE_SELECTED_TITLE_COLOR': '#000', 'NODE_TEXT_COLOR': '#333',
            'NODE_TEXT_HIGHLIGHT_COLOR': '#000', 'NODE_DEFAULT_COLOR': '#ccc',
            'NODE_DEFAULT_BGCOLOR': '#f5f5f5', 'NODE_DEFAULT_BOXCOLOR': '#999',
            'NODE_DEFAULT_SHAPE': 2, 'NODE_BOX_OUTLINE_COLOR': '#000',
            'NODE_BYPASS_BGCOLOR': '#FF00FF', 'NODE_ERROR_COLOUR': '#E00',
            'DEFAULT_SHADOW_COLOR': 'rgba(0,0,0,0.1)', 'WIDGET_BGCOLOR': '#e0e0e0',
            'WIDGET_OUTLINE_COLOR': '#999', 'WIDGET_TEXT_COLOR': '#333',
            'WIDGET_SECONDARY_TEXT_COLOR': '#666', 'WIDGET_DISABLED_TEXT_COLOR': '#999',
            'LINK_COLOR': '#4CAF50', 'EVENT_LINK_COLOR': '#FF9800', 'CONNECTING_LINK_COLOR': '#2196F3',
            'BADGE_FG_COLOR': '#000', 'BADGE_BG_COLOR': '#e0f0e0',
        },
        'comfy_base': {
            'fg-color': '#222', 'bg-color': '#e9e9e9', 'comfy-menu-bg': '#f5f5f5',
            'comfy-menu-secondary-bg': '#e0e0e0', 'comfy-input-bg': '#d0d0d0',
            'input-text': '#222', 'descrip-text': '#666', 'drag-text': '#888',
            'error-text': '#cc0000', 'border-color': '#bbb',
            'tr-even-bg-color': '#e5e5e5', 'tr-odd-bg-color': '#f0f0f0',
            'content-bg': '#bbb', 'content-fg': '#222',
            'content-hover-bg': '#d0d0d0', 'content-hover-fg': '#000',
            'bar-shadow': 'rgba(0, 0, 0, 0.1) 0 0 0.5rem',
        },
    },
    'solarized': {
        'node_slot': _COMMON_NODE_SLOT,
        'litegraph_base': {
            'CLEAR_BACKGROUND_COLOR': '#002b36', 'NODE_TITLE_COLOR': '#93a1a1',
            'NODE_SELECTED_TITLE_COLOR': '#fdf6e3', 'NODE_TEXT_COLOR': '#839496',
            'NODE_TEXT_HIGHLIGHT_COLOR': '#fdf6e3', 'NODE_DEFAULT_COLOR': '#073642',
            'NODE_DEFAULT_BGCOLOR': '#073642', 'NODE_DEFAULT_BOXCOLOR': '#586e75',
            'NODE_DEFAULT_SHAPE': 2, 'NODE_BOX_OUTLINE_COLOR': '#268bd2',
            'NODE_BYPASS_BGCOLOR': '#FF00FF', 'NODE_ERROR_COLOUR': '#dc322f',
            'DEFAULT_SHADOW_COLOR': 'rgba(0,0,0,0.5)', 'WIDGET_BGCOLOR': '#003847',
            'WIDGET_OUTLINE_COLOR': '#586e75', 'WIDGET_TEXT_COLOR': '#839496',
            'WIDGET_SECONDARY_TEXT_COLOR': '#657b83', 'WIDGET_DISABLED_TEXT_COLOR': '#586e75',
            'LINK_COLOR': '#2aa198', 'EVENT_LINK_COLOR': '#cb4b16', 'CONNECTING_LINK_COLOR': '#859900',
            'BADGE_FG_COLOR': '#fdf6e3', 'BADGE_BG_COLOR': '#073642',
        },
        'comfy_base': {
            'fg-color': '#839496', 'bg-color': '#002b36', 'comfy-menu-bg': '#073642',
            'comfy-menu-secondary-bg': '#003847', 'comfy-input-bg': '#003847',
            'input-text': '#839496', 'descrip-text': '#657b83', 'drag-text': '#586e75',
            'error-text': '#dc322f', 'border-color': '#0d525e',
            'tr-even-bg-color': '#003847', 'tr-odd-bg-color': '#073642',
            'content-bg': '#0d525e', 'content-fg': '#839496',
            'content-hover-bg': '#003847', 'content-hover-fg': '#93a1a1',
            'bar-shadow': 'rgba(0, 0, 0, 0.5) 0 0 0.5rem',
        },
    },
    'arc': {
        'node_slot': _COMMON_NODE_SLOT,
        'litegraph_base': {
            'CLEAR_BACKGROUND_COLOR': '#2f343f', 'NODE_TITLE_COLOR': '#d3dae3',
            'NODE_SELECTED_TITLE_COLOR': '#fff', 'NODE_TEXT_COLOR': '#d3dae3',
            'NODE_TEXT_HIGHLIGHT_COLOR': '#fff', 'NODE_DEFAULT_COLOR': '#383c4a',
            'NODE_DEFAULT_BGCOLOR': '#383c4a', 'NODE_DEFAULT_BOXCOLOR': '#4b5162',
            'NODE_DEFAULT_SHAPE': 2, 'NODE_BOX_OUTLINE_COLOR': '#5294e2',
            'NODE_BYPASS_BGCOLOR': '#FF00FF', 'NODE_ERROR_COLOUR': '#E00',
            'DEFAULT_SHADOW_COLOR': 'rgba(0,0,0,0.5)', 'WIDGET_BGCOLOR': '#404552',
            'WIDGET_OUTLINE_COLOR': '#4b5162', 'WIDGET_TEXT_COLOR': '#d3dae3',
            'WIDGET_SECONDARY_TEXT_COLOR': '#9c9fa8', 'WIDGET_DISABLED_TEXT_COLOR': '#666',
            'LINK_COLOR': '#5294e2', 'EVENT_LINK_COLOR': '#cba6f7', 'CONNECTING_LINK_COLOR': '#5294e2',
            'BADGE_FG_COLOR': '#d3dae3', 'BADGE_BG_COLOR': '#2f343f',
        },
        'comfy_base': {
            'fg-color': '#d3dae3', 'bg-color': '#2f343f', 'comfy-menu-bg': '#383c4a',
            'comfy-menu-secondary-bg': '#404552', 'comfy-input-bg': '#404552',
            'input-text': '#d3dae3', 'descrip-text': '#9c9fa8', 'drag-text': '#9c9fa8',
            'error-text': '#ff4444', 'border-color': '#4b5162',
            'tr-even-bg-color': '#404552', 'tr-odd-bg-color': '#383c4a',
            'content-bg': '#4b5162', 'content-fg': '#d3dae3',
            'content-hover-bg': '#404552', 'content-hover-fg': '#fff',
            'bar-shadow': 'rgba(0, 0, 0, 0.5) 0 0 0.5rem',
        },
    },
    'nord': {
        'node_slot': _COMMON_NODE_SLOT,
        'litegraph_base': {
            'CLEAR_BACKGROUND_COLOR': '#2e3440', 'NODE_TITLE_COLOR': '#d8dee9',
            'NODE_SELECTED_TITLE_COLOR': '#eceff4', 'NODE_TEXT_COLOR': '#d8dee9',
            'NODE_TEXT_HIGHLIGHT_COLOR': '#eceff4', 'NODE_DEFAULT_COLOR': '#3b4252',
            'NODE_DEFAULT_BGCOLOR': '#3b4252', 'NODE_DEFAULT_BOXCOLOR': '#4c566a',
            'NODE_DEFAULT_SHAPE': 2, 'NODE_BOX_OUTLINE_COLOR': '#88c0d0',
            'NODE_BYPASS_BGCOLOR': '#FF00FF', 'NODE_ERROR_COLOUR': '#bf616a',
            'DEFAULT_SHADOW_COLOR': 'rgba(0,0,0,0.5)', 'WIDGET_BGCOLOR': '#434c5e',
            'WIDGET_OUTLINE_COLOR': '#4c566a', 'WIDGET_TEXT_COLOR': '#d8dee9',
            'WIDGET_SECONDARY_TEXT_COLOR': '#81a1c1', 'WIDGET_DISABLED_TEXT_COLOR': '#4c566a',
            'LINK_COLOR': '#88c0d0', 'EVENT_LINK_COLOR': '#d08770', 'CONNECTING_LINK_COLOR': '#a3be8c',
            'BADGE_FG_COLOR': '#eceff4', 'BADGE_BG_COLOR': '#2e3440',
        },
        'comfy_base': {
            'fg-color': '#d8dee9', 'bg-color': '#2e3440', 'comfy-menu-bg': '#3b4252',
            'comfy-menu-secondary-bg': '#434c5e', 'comfy-input-bg': '#434c5e',
            'input-text': '#d8dee9', 'descrip-text': '#81a1c1', 'drag-text': '#81a1c1',
            'error-text': '#bf616a', 'border-color': '#4c566a',
            'tr-even-bg-color': '#434c5e', 'tr-odd-bg-color': '#3b4252',
            'content-bg': '#4c566a', 'content-fg': '#d8dee9',
            'content-hover-bg': '#434c5e', 'content-hover-fg': '#eceff4',
            'bar-shadow': 'rgba(0, 0, 0, 0.5) 0 0 0.5rem',
        },
    },
    'github': {
        'node_slot': _COMMON_NODE_SLOT,
        'litegraph_base': {
            'CLEAR_BACKGROUND_COLOR': '#0d1117', 'NODE_TITLE_COLOR': '#c9d1d9',
            'NODE_SELECTED_TITLE_COLOR': '#f0f6fc', 'NODE_TEXT_COLOR': '#c9d1d9',
            'NODE_TEXT_HIGHLIGHT_COLOR': '#f0f6fc', 'NODE_DEFAULT_COLOR': '#161b22',
            'NODE_DEFAULT_BGCOLOR': '#161b22', 'NODE_DEFAULT_BOXCOLOR': '#30363d',
            'NODE_DEFAULT_SHAPE': 2, 'NODE_BOX_OUTLINE_COLOR': '#388bfd',
            'NODE_BYPASS_BGCOLOR': '#FF00FF', 'NODE_ERROR_COLOUR': '#f85149',
            'DEFAULT_SHADOW_COLOR': 'rgba(0,0,0,0.5)', 'WIDGET_BGCOLOR': '#21262d',
            'WIDGET_OUTLINE_COLOR': '#30363d', 'WIDGET_TEXT_COLOR': '#c9d1d9',
            'WIDGET_SECONDARY_TEXT_COLOR': '#8b949e', 'WIDGET_DISABLED_TEXT_COLOR': '#484f58',
            'LINK_COLOR': '#3fb950', 'EVENT_LINK_COLOR': '#d29922', 'CONNECTING_LINK_COLOR': '#388bfd',
            'BADGE_FG_COLOR': '#f0f6fc', 'BADGE_BG_COLOR': '#0d1117',
        },
        'comfy_base': {
            'fg-color': '#c9d1d9', 'bg-color': '#0d1117', 'comfy-menu-bg': '#161b22',
            'comfy-menu-secondary-bg': '#21262d', 'comfy-input-bg': '#21262d',
            'input-text': '#c9d1d9', 'descrip-text': '#8b949e', 'drag-text': '#8b949e',
            'error-text': '#f85149', 'border-color': '#30363d',
            'tr-even-bg-color': '#21262d', 'tr-odd-bg-color': '#161b22',
            'content-bg': '#30363d', 'content-fg': '#c9d1d9',
            'content-hover-bg': '#21262d', 'content-hover-fg': '#f0f6fc',
            'bar-shadow': 'rgba(0, 0, 0, 0.5) 0 0 0.5rem',
        },
    },
}


def _get_builtin_palettes():
    global _BUILTIN_PALETTES_CACHE
    if _BUILTIN_PALETTES_CACHE is not None:
        return _BUILTIN_PALETTES_CACHE
    from_frontend = _get_builtin_palettes_from_frontend()
    if from_frontend:
        _BUILTIN_PALETTES_CACHE = from_frontend
        return _BUILTIN_PALETTES_CACHE
    _BUILTIN_PALETTES_CACHE = _FALLBACK_PALETTES
    return _BUILTIN_PALETTES_CACHE


def _get_comfy_theme_css_vars():
    try:
        user_dir = _get_comfy_user_dir()
        settings_file = os.path.join(user_dir, 'comfy.settings.json')
        if not os.path.exists(settings_file):
            return {}
        with open(settings_file, 'r', encoding='utf-8', errors='replace') as f:
            data = json.load(f)

        custom_palettes = data.get('Comfy.CustomColorPalettes', {})
        palette_id = data.get('Comfy.ColorPalette', '') or 'dark'

        colors = {}
        if palette_id in custom_palettes:
            colors = custom_palettes[palette_id].get('colors', {})
        else:
            colors = _get_builtin_palettes().get(palette_id, {})

        cb = colors.get('comfy_base', {})
        lg = colors.get('litegraph_base', {})

        def c(key, fallback=''):
            return cb.get(key, fallback) or fallback

        def lg_c(key, fallback=''):
            return lg.get(key, fallback) or fallback

        bg        = c('bg-color', '#202020')
        menu_bg   = c('comfy-menu-bg', bg)
        menu_bg2  = c('comfy-menu-secondary-bg', menu_bg)
        input_bg  = c('comfy-input-bg', bg)
        fg        = c('fg-color', '#cccccc')
        border    = c('border-color', '#444444')
        lg_bg     = lg_c('CLEAR_BACKGROUND_COLOR', bg)
        node_bg   = lg_c('NODE_DEFAULT_BGCOLOR', menu_bg)
        widget_bg = lg_c('WIDGET_BGCOLOR', input_bg)
        node_title = lg_c('NODE_TITLE_COLOR', fg)

        accent = lg_c('NODE_BOX_OUTLINE_COLOR', c('border-color', '#388bfd'))

        def _hex_luminance(hex_color):
            try:
                h = hex_color.lstrip('#')
                if len(h) == 3:
                    h = h[0]*2 + h[1]*2 + h[2]*2
                r, g, b = int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255
                def _lin(c): return c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4
                return 0.2126*_lin(r) + 0.7152*_lin(g) + 0.0722*_lin(b)
            except Exception:
                return 0.5

        def _blend(hex1, hex2, t=0.35):
            try:
                h1, h2 = hex1.lstrip('#'), hex2.lstrip('#')
                if len(h1) == 3: h1 = h1[0]*2 + h1[1]*2 + h1[2]*2
                if len(h2) == 3: h2 = h2[0]*2 + h2[1]*2 + h2[2]*2
                r1,g1,b1 = int(h1[0:2],16), int(h1[2:4],16), int(h1[4:6],16)
                r2,g2,b2 = int(h2[0:2],16), int(h2[2:4],16), int(h2[4:6],16)
                r = int(r1*(1-t) + r2*t)
                g = int(g1*(1-t) + g2*t)
                b = int(b1*(1-t) + b2*t)
                return '#{:02x}{:02x}{:02x}'.format(r,g,b)
            except Exception:
                return hex1

        accent_lum = _hex_luminance(accent)
        if accent_lum > 0.80 or accent_lum < 0.05:
            link_color = lg_c('LINK_COLOR', '')
            if link_color:
                link_lum = _hex_luminance(link_color)
                if 0.05 <= link_lum <= 0.80:
                    accent = link_color
                    accent_lum = link_lum

        # AMD edition uses red shell accents while retaining the canvas palette.
        accent = '#f05a5a'
        accent_lum = _hex_luminance(accent)
        if accent_lum >= 0.18:
            accent_bg       = _blend(accent, '#000000', 0.60)
            accent_bg_hover = _blend(accent, '#000000', 0.45)
        else:
            accent_bg       = _blend(accent, '#ffffff', 0.60)
            accent_bg_hover = _blend(accent, '#ffffff', 0.45)

        acc_bg_lum = _hex_luminance(accent_bg)
        text_on_accent = '#ffffff' if acc_bg_lum < 0.35 else '#111111'
        accent_hover   = _blend(accent, '#ffffff', 0.30)

        return {
            '--bg':               lg_bg,
            '--bar-bg':           menu_bg,
            '--border':           border,
            '--border2':          border,
            '--border3':          border,
            '--btn-bg':           node_bg,
            '--btn-bg2':          node_bg,
            '--input-bg':         input_bg,
            '--modal-bg':         menu_bg,
            '--hover-row':        lg_bg,
            '--text':             fg,
            '--text2':            node_title,
            '--text3':            fg,
            '--accent':           accent,
            '--accent-hover':     accent_hover,
            '--accent-bg':        accent_bg,
            '--accent-bg-hover':  accent_bg_hover,
            '--text-on-accent':   text_on_accent,
        }
    except Exception:
        return {}


def _load_settings():
    defaults = {
        "last_save_dir": _get_desktop(),
        "window_maximized": False,
        "window_placement": None,
        "show_tooltips": True,
        "hide_deprecation_warnings": True,
        "console_detached": False,
        "console_placement": None,
        "rec_fps": 30,
        "console_bg_image": "",
        "console_bg_fit": "fit",
        "console_bg_opacity": 0.12,
    }
    try:
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("_dpi_aware_version", 0) < 1:
                data["window_placement"] = None
                data["console_placement"] = None
                data["_dpi_aware_version"] = 1
                try:
                    tmp = SETTINGS_PATH + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    os.replace(tmp, SETTINGS_PATH)
                except Exception:
                    pass
            defaults.update(data)
    except Exception:
        pass
    return defaults

def _save_settings(settings):
    try:
        if not settings or not isinstance(settings, dict):
            return
        ALLOWED = ("last_save_dir", "window_maximized", "comfy_storage", "show_tooltips", "hide_deprecation_warnings", "window_placement", "custom_file_browser", "theme", "console_detached", "console_placement", "_dpi_aware_version", "rec_fps", "console_bg_image", "console_bg_fit", "console_bg_opacity", "console_bg_animate", "cached_comfy_stable_version", "pinned_packages", "proxy_port")
        existing = {}
        try:
            if os.path.exists(SETTINGS_PATH):
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if not isinstance(existing, dict):
                    existing = {}
        except Exception:
            pass
        merged = {}
        for k in ALLOWED:
            if k in settings:
                merged[k] = settings[k]
            elif k in existing:
                merged[k] = existing[k]
        if not merged:
            return
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
        os.replace(tmp, SETTINGS_PATH)
    except Exception:
        pass

def _get_save_dialog_type():
    try:
        return webview.FileDialog.SAVE
    except AttributeError:
        return webview.SAVE_DIALOG

SAVE_DIALOG_TYPE = _get_save_dialog_type()

SHELL_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ComfyUI-EZi-shell.html")

def _load_shell_html():
    try:
        with open(SHELL_HTML_PATH, "r", encoding="utf-8") as _f:
            return _f.read()
    except Exception as e:
        raise RuntimeError(
            f"Could not load {SHELL_HTML_PATH!r} - make sure it is next to ComfyUI-EZi.py. ({e})"
        )

SHELL_HTML = _load_shell_html()


def _load_ico_as_base64():
    ico_w, ico_h = 256, 256
    if not os.path.exists(ICO_PATH):
        return "", ico_w, ico_h
    try:
        from PIL import Image
        import io as _io
        with Image.open(ICO_PATH) as im:
            frames = []
            try:
                for _i in range(getattr(im, 'n_frames', 1)):
                    im.seek(_i)
                    frames.append((im.size[0] * im.size[1], im.copy()))
            except EOFError:
                pass
            best = max(frames, key=lambda x: x[0])[1] if frames else im
            ico_w, ico_h = best.size
            buf = _io.BytesIO()
            best.convert("RGBA").save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
        return f'url("data:image/png;base64,{b64}")', ico_w, ico_h
    except Exception:
        pass
    try:
        with open(ICO_PATH, "rb") as _f:
            b64 = base64.b64encode(_f.read()).decode()
        return f'url("data:image/x-icon;base64,{b64}")', ico_w, ico_h
    except Exception:
        return "", ico_w, ico_h

def _get_shell_html(settings=None):
    settings = settings or {}
    custom_bg  = settings.get("console_bg_image", "").strip()
    bg_fit     = settings.get("console_bg_fit", "fit")
    bg_opacity = settings.get("console_bg_opacity", 0.12)

    ico_opacity = str(round(float(bg_opacity), 4))
    ico_repeat  = "no-repeat"

    _ico_css, ico_w, ico_h = _load_ico_as_base64()
    if custom_bg and os.path.isfile(custom_bg):
        ext  = os.path.splitext(custom_bg)[1].lower().lstrip(".")
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "webp": "image/webp", "svg": "image/svg+xml"}.get(ext, "image/png")
        try:
            with open(custom_bg, "rb") as _f:
                b64 = base64.b64encode(_f.read()).decode()
            ico_css = f'url("data:{mime};base64,{b64}")'
        except Exception:
            ico_css = ""
        fit_map = {
            "fit":     ("contain",   "no-repeat"),
            "stretch": ("100% 100%", "no-repeat"),
            "tile":    ("auto",      "repeat"),
            "center":  ("auto",      "no-repeat"),
        }
        ico_size, ico_repeat = fit_map.get(bg_fit, ("contain", "no-repeat"))
        ico_pos = "inset: 0; width: auto; height: auto; transform: none;"
    elif _ico_css:
        ico_css  = _ico_css
        ico_size = f"{ico_w}px {ico_h}px"
        ico_pos  = (f"width: {ico_w}px; height: {ico_h}px;\n"
                    f"    top: 50%; left: 50%; transform: translate(-50%, -50%);")
    else:
        ico_css  = ""
        ico_size = "256px 256px"
        ico_pos  = "width: 256px; height: 256px;\n    top: 50%; left: 50%; transform: translate(-50%, -50%);"

    return (SHELL_HTML
            .replace("{ICO_BG}",      ico_css)
            .replace("{ICO_POS}",     ico_pos)
            .replace("{ICO_SIZE}",    ico_size)
            .replace("{ICO_REPEAT}",  ico_repeat)
            .replace("{ICO_OPACITY}", ico_opacity)
            .replace("{EZI_VERSION}", APP_VERSION))

_CONSOLE_ICON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M11 19h-6a2 2 0 0 1 -2 -2v-10a2 2 0 0 1 2 -2h14a2 2 0 0 1 2 2v4"/><path d="M14 15a1 1 0 0 1 1 -1h5a1 1 0 0 1 1 1v3a1 1 0 0 1 -1 1h-5a1 1 0 0 1 -1 -1l0 -3"/><path d="M7 9l4 4"/><path d="M7 12v-3h3"/></svg>'

_CONSOLE_PAGE_BODY = r"""<body>
<div id="bar"><button id="attach-btn" tabindex="-1" data-tip="Attach console back to the ComfyUI-EZi window" onmousedown="event.preventDefault()" onclick="attachConsole()">__ICON__</button><span id="status">ComfyUI Console</span></div>
<div id="panels">
  <div id="term-panel"></div>
  <div id="ico-bg"></div>
  <button id="term-jump" onmousedown="event.preventDefault()" onclick="jumpBottom()">&#x2193; Jump to latest</button>
</div>
<script>
const EZI_INIT = __INIT__;
const ansi = new AnsiUp();
const term = document.getElementById('term-panel');
let showingUI = false;
__EMU__
function applyTheme(theme, vars) {
  var root = document.documentElement;
  root.classList.remove('theme-pixaroma', 'theme-light', 'theme-comfyui');
  if (theme === 'pixaroma') root.classList.add('theme-pixaroma');
  else if (theme === 'light') root.classList.add('theme-light');
  else if (theme === 'comfyui') {
    var cssBody = Object.entries(vars || {}).map(function(kv) { return kv[0] + ':' + kv[1]; }).join(';');
    var el = document.getElementById('ezi-comfyui-theme-style');
    if (!el) { el = document.createElement('style'); el.id = 'ezi-comfyui-theme-style'; document.head.appendChild(el); }
    el.textContent = ':root.theme-comfyui{' + cssBody + '}';
    root.classList.add('theme-comfyui');
  }
}
applyTheme(EZI_INIT.theme, EZI_INIT.comfyThemeVars);
function attachConsole() { try { pywebview.api.attach_console(); } catch (e) {} }
function send_columns() {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  ctx.font = '12px Consolas, "Courier New", monospace';
  const charW = ctx.measureText('M').width || 7.2;
  const style = window.getComputedStyle(term);
  const padL = parseFloat(style.paddingLeft) || 0;
  const padR = parseFloat(style.paddingRight) || 0;
  const scrollbarW = Math.max(term.offsetWidth - term.clientWidth, 17);
  const usable = term.clientWidth - padL - padR - scrollbarW - 2;
  const cols = Math.floor(usable / charW);
  try { if (cols > 0) pywebview.api.set_columns(cols); } catch (e) {}
}
window.addEventListener('resize', send_columns);
(function waitForApi() {
  if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.set_columns) send_columns();
  else setTimeout(waitForApi, 50);
})();
eziLazyTip(document.getElementById('attach-btn'));
applyTooltips(EZI_INIT.tooltips !== false);
term.tabIndex = -1;
function _focusTerm() {
  var a = document.activeElement;
  if (!a || a === document.body || a.id === 'attach-btn') {
    try { if (a && a.blur) a.blur(); term.focus({ preventScroll: true }); } catch (e) {}
  }
}
window.addEventListener('focus', _focusTerm);
document.addEventListener('visibilitychange', _focusTerm);
_focusTerm();
</script>
</body>
</html>
"""

def _get_console_html(settings=None):
    html = _get_shell_html(settings)
    head = html[:html.index('</head>')]
    head = re.sub(r'<title>.*?</title>', '<title>ComfyUI Console</title>', head, count=1, flags=re.S)
    a = html.index('const T = {')
    b = html.index('\n})();', html.index('window.applyTooltips = function')) + len('\n})();')
    emu = html[a:b]
    theme = (settings or {}).get("theme", "dark")
    try:
        theme_vars = _get_comfy_theme_css_vars() if theme == "comfyui" else {}
    except Exception:
        theme_vars = {}
    init = json.dumps({"theme": theme, "comfyThemeVars": theme_vars,
                       "tooltips": bool((settings or {}).get("show_tooltips", True))}).replace('</', '<\\/')
    body = (_CONSOLE_PAGE_BODY.replace('__ICON__', _CONSOLE_ICON_SVG)
                              .replace('__INIT__', init)
                              .replace('__EMU__', emu))
    return head + '</head>\n' + body

async def make_proxy_app(comfy_port_holder, storage_holder, settings_holder=None, api_holder=None):
    async def handle_shell(request):
        s = settings_holder[0] if settings_holder else {}
        return web.Response(text=_get_shell_html(s), content_type='text/html', charset='utf-8')

    async def handle_console(request):
        s = settings_holder[0] if settings_holder else {}
        return web.Response(text=_get_console_html(s), content_type='text/html', charset='utf-8')
    
    async def handle_favicon(request):
        if os.path.isfile(ICO_PATH):
            try:
                with open(ICO_PATH, 'rb') as f:
                    data = f.read()
                return web.Response(body=data, content_type='image/x-icon',
                                    headers={'Cache-Control': 'public, max-age=86400'})
            except Exception:
                pass
        return web.Response(status=404)

    async def handle_any(request):
        comfy_port = comfy_port_holder[0]
        comfy_host = f"127.0.0.1:{comfy_port}"
        path_qs    = request.path_qs
        api_ref = api_holder[0] if api_holder else None
        
        if (request.headers.get('Upgrade', '').lower() == 'websocket'):
            ws_server = web.WebSocketResponse(max_msg_size=134217728); await ws_server.prepare(request)
            try:
                async with ClientSession() as session:
                    async with session.ws_connect(f"ws://{comfy_host}{path_qs}", max_msg_size=134217728) as ws_client:
                        async def fwd(src, dst):
                            try:
                                async for msg in src:
                                    try:
                                        if msg.type == WSMsgType.TEXT:
                                            if dst is ws_server:
                                                try:
                                                    d = json.loads(msg.data)
                                                    t = d.get('type')
                                                    if t == 'progress':
                                                        pd = d.get('data', {})
                                                        val = pd.get('value', 0)
                                                        mx  = pd.get('max', 1)
                                                        if mx > 0:
                                                            api_ref._tb_set(val, mx, 2)
                                                    elif t in ('execution_success', 'execution_error', 'execution_interrupted'):
                                                        api_ref._tb_set(0, 1, 0)
                                                except Exception:
                                                    pass
                                            await dst.send_str(msg.data)
                                        elif msg.type == WSMsgType.BINARY:
                                            await dst.send_bytes(msg.data)
                                        elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR, WSMsgType.CLOSING):
                                            break
                                    except (ConnectionResetError, OSError, asyncio.CancelledError):
                                        break
                                    except Exception:
                                        break
                            except (ConnectionResetError, OSError, asyncio.CancelledError):
                                pass
                            except Exception:
                                pass
                        await asyncio.gather(fwd(ws_server, ws_client), fwd(ws_client, ws_server), return_exceptions=True)
            except Exception:
                pass
            if not ws_server.closed:
                await ws_server.close()
            return ws_server

        try:
            async with ClientSession(timeout=ClientTimeout(total=120)) as session:
                fwd_hd = {k:v for k,v in request.headers.items() if k.lower() not in ('content-encoding','transfer-encoding','host','origin')}
                fwd_hd['Host'] = comfy_host
                # Requests from pages served by this proxy become same-origin requests to
                # ComfyUI. Any other Origin is passed through unchanged, so ComfyUI's
                # cross-site check still rejects requests sent by other websites.
                origin = request.headers.get('Origin')
                if origin is not None:
                    fwd_hd['Origin'] = f"http://{comfy_host}" if origin == f"http://{request.host}" else origin
                async with session.request(request.method, f"http://{comfy_host}{path_qs}", headers=fwd_hd, data=await request.read(), allow_redirects=False) as resp:
                    body = await resp.read()
                    resp_hd = {k: v for k, v in resp.headers.items() if k.lower() not in ('content-encoding', 'transfer-encoding', 'content-length')}
                    
                    is_ezi_webview = EZI_UA_TAG in request.headers.get('User-Agent', '')
                    if is_ezi_webview and request.path == '/' and 'text/html' in resp.headers.get('Content-Type', '').lower():
                        html = body.decode('utf-8', errors='replace')

                        stored_data = storage_holder[0]
                        try:
                            data_str = (json.dumps(stored_data).replace('</', '<\\/')
                                        if stored_data else 'null')
                            inject_js = f"""<script>
    (function() {{
        try {{
            var data = {data_str};
            if (data && data.ls) {{ Object.keys(data.ls).forEach(function(k) {{ try {{ if (localStorage.getItem(k) === null) localStorage.setItem(k, data.ls[k]); }} catch(e) {{}} }}); }}
            if (data && data.ss) {{ Object.keys(data.ss).forEach(function(k) {{ try {{ if (sessionStorage.getItem(k) === null) sessionStorage.setItem(k, data.ss[k]); }} catch(e) {{}} }}); }}
        }} catch(e) {{}}

        window._eziPostToShell = function(msg) {{
            try {{
                if (window.chrome && window.chrome.webview) {{
                    window.chrome.webview.postMessage(msg);
                    return;
                }}
            }} catch(e) {{}}
            try {{ window.parent.postMessage(msg, '*'); }} catch(e) {{}}
        }};

        try {{
            if (window.chrome && window.chrome.webview) {{
                window.chrome.webview.addEventListener('message', function(ev) {{
                    try {{ window.postMessage(ev.data, '*'); }} catch(e) {{}}
                }});
            }}
        }} catch(e) {{}}

        window.__eziFlushStorageNow = function() {{
            try {{
                var out = {{ ls: {{}}, ss: {{}} }};
                var ls = window.localStorage;
                for (var i = 0; i < ls.length; i++) {{
                    var k = ls.key(i);
                    if (k) out.ls[k] = ls.getItem(k);
                }}
                var ss = window.sessionStorage;
                for (var j = 0; j < ss.length; j++) {{
                    var sk = ss.key(j);
                    if (sk) out.ss[sk] = ss.getItem(sk);
                }}
                window._eziPostToShell({{ type: 'ezi_storage_save', ls: out.ls, ss: out.ss }});
            }} catch(e) {{}}
        }};
        window.addEventListener('pagehide', window.__eziFlushStorageNow);
        window.addEventListener('beforeunload', window.__eziFlushStorageNow);

        var _eziComfyReady = false;
        var _OrigWS = window.WebSocket;
        function _eziCheckMsg(data) {{
            if (_eziComfyReady) return;
            try {{
                var d = JSON.parse(data);
                if (d && d.type === 'status') {{
                    _eziComfyReady = true;
                    window._eziPostToShell({{ type: 'ezi_comfy_ready' }});
                }}
            }} catch(e) {{}}
        }}
        window.WebSocket = function(url, protocols) {{
            var ws = protocols ? new _OrigWS(url, protocols) : new _OrigWS(url);
            var _origAEL = ws.addEventListener.bind(ws);
            ws.addEventListener = function(type, fn, opts) {{
                if (type === 'message' && !_eziComfyReady) {{
                    return _origAEL('message', function(ev) {{ _eziCheckMsg(ev.data); return fn.apply(this, arguments); }}, opts);
                }}
                return _origAEL(type, fn, opts);
            }};
            var _onmsg = null;
            Object.defineProperty(ws, 'onmessage', {{
                get: function() {{ return _onmsg; }},
                set: function(fn) {{
                    _onmsg = fn ? function(ev) {{ _eziCheckMsg(ev.data); return fn.apply(this, arguments); }} : fn;
                }},
                configurable: true
            }});
            return ws;
        }};
        window.WebSocket.prototype = _OrigWS.prototype;
        window.WebSocket.CONNECTING = _OrigWS.CONNECTING;
        window.WebSocket.OPEN = _OrigWS.OPEN;
        window.WebSocket.CLOSING = _OrigWS.CLOSING;
        window.WebSocket.CLOSED = _OrigWS.CLOSED;

        var _origOpen = window.open;
        var _EZI_FAKE_AUTH_POPUP = false;
        window.open = function(url, target, features) {{
            if (_EZI_FAKE_AUTH_POPUP && url && (
                url.includes('accounts.google.com') ||
                url.includes('github.com/login') ||
                url.includes('/__/auth/') ||
                url.includes('/api/auth/signin')
            )) {{
                try {{
                    window._eziPostToShell({{ type: 'ezi_open_auth_popup', url: url }});
                }} catch(e) {{}}
                var fakeWin = {{
                    closed: false,
                    close: function() {{ this.closed = true; }},
                    focus: function() {{}},
                    postMessage: function() {{}}
                }};
                return fakeWin;
            }}
            return _origOpen.call(this, url, target, features);
        }};

        var _origConsoleError = console.error;
        console.error = function() {{
            var args = Array.from(arguments);
            var errStr = args.join(' ');
            if (errStr.includes('Firebase: Error (auth/popup') ||
                errStr.includes('Firebase: Error (auth/cancelled-popup-request')) {{
                return;
            }}
            return _origConsoleError.apply(console, args);
        }};

        window.addEventListener('unhandledrejection', function(event) {{
            if (event.reason && event.reason.code && event.reason.code.startsWith('auth/')) {{
                event.preventDefault();
            }}
        }});

        document.addEventListener('click', function(ev) {{
            var anyA = ev.target && ev.target.closest ? ev.target.closest('a') : null;
            if (!anyA) return;
            try {{
                window._eziPostToShell({{
                    type: 'ezi_debug_log',
                    msg: 'anchor click: href=' + anyA.href +
                         ' download=' + JSON.stringify(anyA.getAttribute('download')) +
                         ' target=' + JSON.stringify(anyA.getAttribute('target'))
                }});
            }} catch(e) {{}}
        }}, true);

        document.addEventListener('click', function(ev) {{
            var a = ev.target && ev.target.closest ? ev.target.closest('a[download]') : null;
            if (!a || !a.href) return;
            try {{
                ev.preventDefault();
                ev.stopPropagation();
                var filename = a.getAttribute('download') || 'download';

                if (a.href.startsWith('blob:')) {{
                    var xhr = new XMLHttpRequest();
                    xhr.open('GET', a.href, true);
                    xhr.responseType = 'blob';
                    xhr.onload = function(e) {{
                        if (this.status == 200) {{
                            var myBlob = this.response;
                            var isText = /^(text\\/|application\\/json|application\\/xml|image\\/svg\\+xml)/.test(myBlob.type) ||
                                         /\\.(json|txt|ya?ml|csv|svg)$/i.test(filename);
                            var reader = new FileReader();
                            reader.onload = function() {{
                                window._eziPostToShell({{
                                    type: 'ezi_save_blob',
                                    filename: filename,
                                    content: reader.result,
                                    isBase64: !isText
                                }});
                            }};
                            if (isText) {{
                                reader.readAsText(myBlob);
                            }} else {{
                                reader.readAsDataURL(myBlob);
                            }}
                        }}
                    }};
                    xhr.send();
                    return;
                }}

                var urlObj = new URL(a.href, window.location.origin);
                var relativeUrl = urlObj.pathname + urlObj.search;
                window._eziPostToShell({{ type: 'ezi_save_image', url: relativeUrl, filename: filename }});
            }} catch(e) {{ console.error("Download interceptor error:", e); }}
        }}, true);
    }})();
    </script>"""
                            idx = html.lower().find('<head>')
                            if idx != -1:
                                html = html[:idx+6] + inject_js + html[idx+6:]
                            else:
                                html = inject_js + html
                        except Exception:
                            pass

                        cmenu_js = """<script>
    (function() {
        function initCMenu() {
            if (document.getElementById('ezi-cmenu')) return;
            var m = document.createElement('div');
            m.id = 'ezi-cmenu';
            m.style.cssText = 'position:fixed;background:var(--comfy-menu-bg, #1e1e1e);border:1px solid var(--border-color, #444);border-radius:6px;padding:4px 0;z-index:9999999;display:none;font-size:12px;color:var(--input-text, #cccccc);box-shadow:0 6px 16px rgba(0,0,0,0.3);font-family:Segoe UI, Tahoma, Geneva, Verdana, sans-serif;min-width:220px;';
            document.body.appendChild(m);

            function addItem(txt, shortcut, fn, addSeparator) {
                if (addSeparator) {
                    var sep = document.createElement('div');
                    sep.style.cssText = 'height:1px;background-color:var(--border-color, #444);margin:4px 0;';
                    m.appendChild(sep);
                }
                var i = document.createElement('div');
                var textSpan = document.createElement('span');
                textSpan.innerText = txt;
                var shortcutSpan = document.createElement('span');
                shortcutSpan.innerText = shortcut;
                shortcutSpan.style.cssText = 'color:var(--descrip-text, #888);font-size:11px;float:right;margin-left:20px;';
                i.appendChild(textSpan);
                i.appendChild(shortcutSpan);
                i.style.cssText = 'padding:6px 24px 6px 12px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;clear:both;';
                
                i.onmouseover = function() { 
                    this.style.background='var(--comfy-menu-secondary-bg, #2a2a2a)'; 
                    this.style.color='var(--fg-color, #ffffff)'; 
                }; 
                i.onmouseout = function() { 
                    this.style.background=''; 
                    this.style.color='var(--input-text, #cccccc)'; 
                };
                i.onclick = function(e) { e.stopPropagation(); fn(); m.style.display='none'; };
                m.appendChild(i);
            }

            addItem('Undo', 'Ctrl+Z', function() {
                var el = m.tgt; el.focus(); document.execCommand('undo');
            });
            
            addItem('Redo', 'Ctrl+Y', function() {
                var el = m.tgt; el.focus(); document.execCommand('redo');
            }, true);

            addItem('Cut', 'Ctrl+X', function() {
                var el = m.tgt; 
                window._eziPostToShell({ type: 'ezi_clipboard_request', action: 'cut', text: el.value.substring(el.selectionStart, el.selectionEnd) });
                el.focus();
                document.execCommand('delete');
            }, true);

            addItem('Copy', 'Ctrl+C', function() {
                var el = m.tgt;
                window._eziPostToShell({ type: 'ezi_clipboard_request', action: 'copy', text: el.value.substring(el.selectionStart, el.selectionEnd) });
            });

            addItem('Paste', 'Ctrl+V', function() {
                var el = m.tgt;
                el.focus();
                window._eziPostToShell({ type: 'ezi_clipboard_request', action: 'paste' });
                window.addEventListener('message', function handler(ev) {
                    if (ev.data && ev.data.type === 'ezi_clipboard_response') {
                        window.removeEventListener('message', handler);
                        document.execCommand('insertText', false, ev.data.text);
                    }
                });
            });

            addItem('Delete', 'Del', function() {
                var el = m.tgt; el.focus(); document.execCommand('delete');
            }, true);

            addItem('Select All', 'Ctrl+A', function() {
                var el = m.tgt; el.focus(); el.select();
            });

            document.addEventListener('click', function() { m.style.display='none'; });
            document.addEventListener('contextmenu', function(e) {
                var t = e.target;
                if (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable) {
                    e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
                    t.focus(); m.tgt = t;
                    m.style.left = e.clientX + 'px'; m.style.top = e.clientY + 'px'; m.style.display = 'block';
                } else { m.style.display='none'; }
            }, true);
        }
        if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', initCMenu); } else { initCMenu(); }
    })();
    </script>
    <script>
    (function() {
        var seen = new WeakSet();
        function scheduleKill(el) {
            if (seen.has(el)) return;
            seen.add(el);
            setTimeout(function() {
                if (!document.body.contains(el)) return;
                el.remove();
            }, 8000);
        }
        function scan(node) {
            if (!node || node.nodeType !== 1) return;
            if (node.matches && node.matches('.p-tooltip')) scheduleKill(node);
            if (node.querySelectorAll) {
                node.querySelectorAll('.p-tooltip').forEach(scheduleKill);
            }
        }
        function initTooltipFix() {
            document.querySelectorAll('.p-tooltip').forEach(scheduleKill);
            var obs = new MutationObserver(function(muts) {
                muts.forEach(function(m) {
                    m.addedNodes.forEach(scan);
                });
            });
            obs.observe(document.body, { childList: true, subtree: true });
        }
        if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', initTooltipFix); } else { initTooltipFix(); }
    })();
    </script>"""
                        html = html.replace('</body>', cmenu_js + '</body>')

                        body = html.encode('utf-8')

                        _strip = {'etag', 'last-modified', 'cache-control', 'expires', 'age'}
                        resp_hd = {k: v for k, v in resp_hd.items() if k.lower() not in _strip}
                        resp_hd['Cache-Control'] = 'no-store, no-cache, must-revalidate'
                        resp_hd['Pragma'] = 'no-cache'
                        resp_hd['Expires'] = '0'

                    return web.Response(status=resp.status, headers=resp_hd, body=body)
        except: return web.Response(status=502)

    app = web.Application(client_max_size=1024*1024*1024)
    app.router.add_get('/__shell__', handle_shell)
    app.router.add_get('/__console__', handle_console)
    app.router.add_get('/favicon.ico', handle_favicon)
    app.router.add_route('*', '/{path_info:.*}', handle_any)
    return app

def _is_rect_on_active_monitor(left, top, right, bottom):
    try:
        import ctypes.wintypes as wt
        user32 = ctypes.windll.user32

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize",    wt.DWORD),
                        ("rcMonitor", wt.RECT),
                        ("rcWork",    wt.RECT),
                        ("dwFlags",   wt.DWORD)]

        monitors = []
        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            ctypes.c_void_p, ctypes.c_void_p,
            ctypes.POINTER(wt.RECT), ctypes.c_double
        )

        def _cb(hmon, hdc, lprect, lparam):
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
                r = info.rcWork
                monitors.append((r.left, r.top, r.right, r.bottom))
            return True

        user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_cb), 0)

        MIN_W, MIN_H = 100, 50
        for ml, mt, mr, mb in monitors:
            ol = max(left, ml)
            ot = max(top,  mt)
            or_ = min(right, mr)
            ob  = min(bottom, mb)
            if (or_ - ol) >= MIN_W and (ob - ot) >= MIN_H:
                return True
        return False
    except Exception:
        return True


class Api:
    _NO_WIN        = 0x08000000
    _NO_WIN_HIDDEN = 0x08000000 | 0x20000000
    PY_EXE         = os.path.join(ROOT_DIR, "python_embeded", "python.exe")
    COMFY_DIR      = os.path.join(ROOT_DIR, "ComfyUI")

    def get_addon_status(self):
        from importlib.metadata import distributions
        from pathlib import Path
        site = Path(ROOT_DIR) / 'python_embeded/Lib/site-packages'
        packages = {dist.metadata.get('Name', '').lower().replace('_', '-')
                    for dist in distributions(path=[str(site)])}
        comfy = Path(ROOT_DIR) / 'ComfyUI'
        addon = comfy / 'custom_nodes/ComfyUI-Nunchaku-AMD'
        linked = comfy / 'extra_model_paths.yaml'
        try:
            models_linked = linked.is_file() and 'base_path:' in linked.read_text(encoding='utf-8-sig')
        except OSError:
            models_linked = False
        status = {
            'pixelartistry watertight workflows.bat': (Path(ROOT_DIR) / 'amd/pixelartistry-workflows.json').is_file() and
                any((comfy / 'user/default/workflows/PixelArtistry').rglob('*.json')),
            'pixaroma workflows.bat': any((comfy / 'user/default/workflows/Pixaroma').rglob('*.json')),
            'flashattention.bat': 'flash-attn' in packages and bool({'aiter','amd-aiter'} & packages),
            'insightface.bat': {'insightface', 'facexlib', 'onnxruntime'}.issubset(packages),
            'nunchaku.bat': all((addon / name).is_file() for name in
                                ('__init__.py', 'nunchaku_amd.py', 'packed_kernel.py')),
            'sageattention-multi (v2.2.0 and v3).bat': 'sageattention' in packages,
        }
        group_file = Path(ROOT_DIR) / 'amd/wtivo-node-groups.json'
        if group_file.is_file():
            for group in json.loads(group_file.read_text(encoding='utf-8')).values():
                status[group['button']] = all((comfy / 'custom_nodes' / name / '__init__.py').is_file()
                                              for name in group['nodes'])
                if group['button'] == 'boomercyb wtivo amd nodes.bat':
                    try:
                        report = json.loads((Path(ROOT_DIR)/'amd/wtivo-boomercyb-installed.json').read_text())
                        status[group['button']] &= report.get('complete') is True and report.get('native_verified') is True
                    except (OSError, ValueError):
                        status[group['button']] = False
        return status

    def exit_app(self):
        self.save_window_state()
        self._confirm_close = True
        self._graceful_close()

    def restart_ezi(self):
        self.save_window_state()
        self._confirm_close = True

        try:
            self._kill_running_proc()
        except Exception:
            pass

        self._flush_state_to_disk()

        try:
            subprocess.Popen(
                [sys.executable] + sys.argv,
                cwd=os.getcwd(),
                creationflags=0x00000008,
            )
        except Exception as e:
            pass

        self._close_window()

    def restart_after_update(self):
        self._safe_eval("document.getElementById('modal-overlay').classList.remove('active');")
        self._safe_eval("switchToConsole()")
        self._updating = False
        self._restart_comfy()

    def read_clipboard(self):
        try:
            import ctypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            try:
                ctypes.windll.ole32.OleInitialize(None)
            except Exception:
                pass

            user32.OpenClipboard.argtypes = [ctypes.c_void_p]
            user32.OpenClipboard.restype = ctypes.c_int
            user32.GetClipboardData.argtypes = [ctypes.c_uint]
            user32.GetClipboardData.restype = ctypes.c_void_p
            kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalLock.restype = ctypes.c_void_p
            kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalUnlock.restype = ctypes.c_int
            user32.CloseClipboard.argtypes = []
            user32.CloseClipboard.restype = ctypes.c_int

            if not user32.OpenClipboard(0):
                return ""
            try:
                handle = user32.GetClipboardData(13)
                if not handle:
                    return ""
                ptr = kernel32.GlobalLock(handle)
                if not ptr:
                    return ""
                try:
                    return ctypes.c_wchar_p(ptr).value or ""
                finally:
                    kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
        except Exception:
            return ""

    def write_clipboard(self, text):
        try:
            import ctypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            try:
                ctypes.windll.ole32.OleInitialize(None)
            except Exception:
                pass

            user32.OpenClipboard.argtypes = [ctypes.c_void_p]
            user32.OpenClipboard.restype = ctypes.c_int
            user32.EmptyClipboard.argtypes = []
            user32.EmptyClipboard.restype = ctypes.c_int
            user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
            user32.SetClipboardData.restype = ctypes.c_void_p
            kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
            kernel32.GlobalAlloc.restype = ctypes.c_void_p
            kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalLock.restype = ctypes.c_void_p
            kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalUnlock.restype = ctypes.c_int
            kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
            kernel32.GlobalFree.restype = ctypes.c_void_p
            user32.CloseClipboard.argtypes = []
            user32.CloseClipboard.restype = ctypes.c_int

            if not user32.OpenClipboard(0):
                return
            user32.EmptyClipboard()
            
            try:
                buf = ctypes.create_unicode_buffer(text)
                size = ctypes.sizeof(buf)
                
                GMEM_MOVEABLE = 0x0002
                h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
                if not h_mem:
                    return
                
                ptr = kernel32.GlobalLock(h_mem)
                if not ptr:
                    kernel32.GlobalFree(h_mem)
                    return
                
                try:
                    ctypes.memmove(ptr, buf, size)
                finally:
                    kernel32.GlobalUnlock(h_mem)
                
                if not user32.SetClipboardData(13, h_mem):
                    kernel32.GlobalFree(h_mem)
            finally:
                user32.CloseClipboard()
        except Exception:
            pass

    def save_blob_data(self, filename, content, is_base64=False):
        threading.Thread(target=self._do_save_blob, args=(filename, content, is_base64), daemon=True).start()

    def _do_save_blob(self, filename, content, is_base64=False):
        if not self._window:
            return

        ext = os.path.splitext(filename)[1].lower()

        known_labels = {
            '.json': 'JSON Files',
            '.txt': 'Text Files',
            '.yaml': 'YAML Files',
            '.yml': 'YAML Files',
            '.png': 'PNG Image',
            '.jpg': 'JPEG Image',
            '.jpeg': 'JPEG Image',
            '.webp': 'WebP Image',
            '.gif': 'GIF Image',
            '.bmp': 'Bitmap Image',
            '.svg': 'SVG Image',
            '.mp4': 'MP4 Video',
            '.webm': 'WebM Video',
            '.mov': 'QuickTime Video',
            '.avi': 'AVI Video',
            '.mkv': 'Matroska Video',
            '.wav': 'WAV Audio',
            '.mp3': 'MP3 Audio',
            '.ogg': 'OGG Audio',
            '.flac': 'FLAC Audio',
            '.csv': 'CSV Files',
            '.zip': 'ZIP Archive',
            '.safetensors': 'SafeTensors Files',
        }

        if ext:
            label = known_labels.get(ext, f"{ext[1:].upper()} Files")
            file_types = (f"{label} (*{ext})", "All Files (*.*)")
        else:
            file_types = ("All Files (*.*)",)

        save_path = None
        try:
            with self._save_dialog_lock:
                result = self._window.create_file_dialog(
                    SAVE_DIALOG_TYPE,
                    directory=self._last_save_dir,
                    save_filename=filename,
                    file_types=file_types
                )
                if result:
                    save_path = result[0] if isinstance(result, (list, tuple)) else result
                    self._last_save_dir = os.path.dirname(save_path)
                    self._settings["last_save_dir"] = self._last_save_dir
                    _save_settings(self._settings)
        except Exception:
            pass

        if save_path:
            try:
                if is_base64:
                    if ',' in content:
                        content = content.split(',', 1)[1]
                    data = base64.b64decode(content)
                    with open(save_path, 'wb') as f:
                        f.write(data)
                else:
                    with open(save_path, 'w', encoding='utf-8') as f:
                        f.write(content)
            except Exception as e:
                self._println(f"[Save Blob] Error: {e}\n")

    def open_auth_popup(self, url):
        msg = (
            "Google sign-in doesn't work inside the desktop app - Google "
            "blocks embedded browsers for security. The desktop app uses a "
            "<b>Comfy API Key</b> instead.<br><br>"
            "<b>Step-by-step:</b><br>"
            "1. Click <i>Get a key in browser</i> below - your Comfy "
            "account page will open in your default browser.<br>"
            "2. Sign in there with Google (it only works in a real "
            "browser).<br>"
            "3. On the <i>API Keys</i> page, click <b>+ New API Key</b> "
            "(top-right).<br>"
            "4. Type any name you want (e.g. <i>Desktop EZi</i>), leave "
            "<i>Description</i> blank, then click <b>Generate</b>.<br>"
            "5. The key is shown <u>only once</u>. Click the <i>copy</i> "
            "icon on the right of the key field.<br>"
            "6. Come back here, paste the key into the field below and "
            "click <i>Apply</i>. That's it &mdash; the desktop app will "
            "fill ComfyUI's API Key dialog and sign you in "
            "automatically.<br><br>"
            "<input type='password' id='ezi-api-key' placeholder='Paste your API key here' "
            "style='width:100%;padding:8px;background:#111;color:#ccc;"
            "border:1px solid #555;border-radius:4px;font-family:monospace;"
            "box-sizing:border-box;margin-top:4px;'>"
        )
        safe_msg = json.dumps(msg)
        js = (
            "showModal('\\uD83D\\uDD11', 'Sign in with a Comfy API Key', " + safe_msg + ", ["
            "{ label: 'Cancel', cls: '', action: function(){} },"
            "{ label: 'Get a key in browser', cls: '', noClose: true, "
            "  action: function(){ try { pywebview.api.open_url('https://platform.comfy.org/profile/api-keys'); } catch(e){} } },"
            "{ label: 'Apply', cls: 'primary', "
            "  action: function(){"
            "    var el = document.getElementById('ezi-api-key');"
            "    var k = el && el.value ? el.value.trim() : '';"
            "    try { pywebview.api.apply_api_key(k); } catch(e){}"
            "  } }"
            "]);"
            "setTimeout(function(){"
            "  var el = document.getElementById('ezi-api-key');"
            "  if (el) el.focus();"
            "}, 50);"
        )
        try:
            self._safe_eval(js)
        except Exception:
            pass

    def apply_api_key(self, key):
        key = (key or '').strip()
        if not key:
            self._println("[Auth] No API key provided\n")
            return
        try:
            self.write_clipboard(key)
        except Exception as e:
            self._println(f"[Auth] clipboard write failed: {e}\n")

        key_js = json.dumps(key)
        auto_js = (
            "(function(){"
            "  try {"
            "    var iframe = document.getElementById('ui-frame');"
            "    var doc = iframe && iframe.contentDocument;"
            "    var win = iframe && iframe.contentWindow;"
            "    if (!doc || !win) return 'no-doc';"
            "    var KEY = " + key_js + ";"
            "    var clicked = false;"
            "    var cands = doc.querySelectorAll('button, [role=\"button\"], a');"
            "    for (var i = 0; i < cands.length; i++) {"
            "      var txt = (cands[i].textContent || '').trim();"
            "      if (txt === 'Comfy API Key' || txt.indexOf('Comfy API Key') !== -1) {"
            "        cands[i].click(); clicked = true; break;"
            "      }"
            "    }"
            "    function clickUseApiKey(){"
            "      var bs = doc.querySelectorAll('button');"
            "      for (var j = 0; j < bs.length; j++) {"
            "        var t = (bs[j].textContent || '').trim();"
            "        if (/API Key/i.test(t) && !/Comfy API Key/i.test(t)) { bs[j].click(); return true; }"
            "      }"
            "      return false;"
            "    }"
            "    function submitForm(input){"
            "      var form = input.closest('form');"
            "      if (!form) return false;"
            "      try { if (typeof form.requestSubmit === 'function') { form.requestSubmit(); return true; } } catch(e){}"
            "      var btn = form.querySelector('button[type=\"submit\"]');"
            "      try { form.dispatchEvent(new win.Event('submit', {bubbles: true, cancelable: true})); } catch(e){}"
            "      if (btn && !btn.disabled) { btn.click(); return true; }"
            "      return false;"
            "    }"
            "    var tries = 0;"
            "    function fill(){"
            "      tries++;"
            "      var input = doc.getElementById('comfy-org-api-key');"
            "      if (!input) {"
            "        if (tries === 5) { clickUseApiKey(); }"
            "        if (tries < 80) { setTimeout(fill, 100); return; }"
            "        return;"
            "      }"
            "      try { input.focus(); } catch(e){}"
            "      var setter = null;"
            "      try { setter = Object.getOwnPropertyDescriptor(win.HTMLInputElement.prototype, 'value').set; } catch(e){}"
            "      try {"
            "        if (setter) setter.call(input, ''); else input.value = '';"
            "        input.dispatchEvent(new win.Event('input', {bubbles: true}));"
            "      } catch(e){}"
            "      try {"
            "        if (setter) setter.call(input, KEY); else input.value = KEY;"
            "      } catch(e) { input.value = KEY; }"
            "      input.dispatchEvent(new win.Event('input', {bubbles: true}));"
            "      input.dispatchEvent(new win.Event('change', {bubbles: true}));"
            "      var submitTries = 0;"
            "      function trySubmit(){"
            "        submitTries++;"
            "        if (submitForm(input)) return;"
            "        try {"
            "          var ev = new win.KeyboardEvent('keydown', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true, cancelable:true});"
            "          input.dispatchEvent(ev);"
            "          var ev2 = new win.KeyboardEvent('keypress', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true, cancelable:true});"
            "          input.dispatchEvent(ev2);"
            "        } catch(e){}"
            "        if (submitTries < 10) setTimeout(trySubmit, 200);"
            "      }"
            "      setTimeout(trySubmit, 400);"
            "    }"
            "    setTimeout(fill, 300);"
            "    return clicked ? 'auto' : 'no-button';"
            "  } catch(e) { return 'err:' + String(e); }"
            "})();"
        )
        def _do():
            try:
                result = self._window.evaluate_js(auto_js)
                self._println(f"[Auth] API key auto-apply: {result}\n")
            except Exception as e:
                self._println(f"[Auth] auto-apply error: {e}\n")
        threading.Thread(target=_do, daemon=True).start()

    def __init__(self, proxy_port, comfy_port_holder, settings, storage_holder, settings_holder=None):
        self._window, self._proc = None, None
        self._settings = settings
        self._storage_holder = storage_holder
        self._settings_holder = settings_holder
        self._last_save_dir = settings.get("last_save_dir", os.path.expanduser("~"))
        self._save_dialog_lock = threading.Lock()
        self._url_found, self._started, self._js_ready = False, False, threading.Event()
        self._updating = False
        self._confirm_close = False
        self._ui_shown = False
        self._restarting = False
        self._run_id = 0
        self._out_buf, self._out_lock = [], threading.Lock()
        self._columns = 120
        self._depr_hold, self._depr_drop, self._depr_bol = '', False, True
        self._depr_blank, self._depr_hold_t = False, 0.0
        self._last_ch = '\n'
        self._console_win, self._console_hwnd = None, None
        self._console_allow_close, self._console_geo_timer = False, None
        self._pump_lock = threading.Lock()
        self._console_op_lock = threading.Lock()
        threading.Thread(target=self._console_pump, daemon=True).start()
        self._main_hwnd = None
        self._proxy_port, self._comfy_port_holder = proxy_port, comfy_port_holder
        self._tb_hwnd = None
        import queue as _tbq
        self._tb_queue = _tbq.Queue()
        threading.Thread(target=self._tb_worker_start, daemon=True).start()
        if sys.platform == "win32":
            hwnd = ctypes.WinDLL('kernel32').GetConsoleWindow()
            if hwnd: ctypes.WinDLL('user32').ShowWindow(hwnd, 0)
				
    def handle_comfyui_download(self, url, filename):
        threading.Thread(target=self._do_handle_download, args=(url, filename), daemon=True).start()

    def _do_handle_download(self, url, filename):
        import urllib.request
        port = self._comfy_port_holder[0]
        if not port:
            return

        full_url = f"http://127.0.0.1:{port}{url}"

        if not self._window:
            return

        ext = os.path.splitext(filename)[1].lower()
        if ext in ('.mp4', '.webm', '.avi', '.mov', '.mkv'):
            file_types = ("Video Files (*.mp4;*.webm;*.avi;*.mov;*.mkv)", "All Files (*.*)")
        elif ext in ('.wav', '.mp3', '.ogg', '.flac', '.aac'):
            file_types = ("Audio Files (*.wav;*.mp3;*.ogg;*.flac;*.aac)", "All Files (*.*)")
        elif ext in ('.gif',):
            file_types = ("GIF Image (*.gif)", "All Files (*.*)")
        else:
            file_types = ("Image Files (*.png;*.jpg;*.jpeg;*.webp)", "All Files (*.*)")

        save_path = None
        try:
            with self._save_dialog_lock:
                result = self._window.create_file_dialog(
                    SAVE_DIALOG_TYPE,
                    directory=self._last_save_dir,
                    save_filename=filename,
                    file_types=file_types
                )
                if result:
                    save_path = result[0] if isinstance(result, (list, tuple)) else result
                    self._last_save_dir = os.path.dirname(save_path)
                    self._settings["last_save_dir"] = self._last_save_dir
                    _save_settings(self._settings)
        except Exception:
            pass

        if not save_path:
            return

        try:
            _ezi_download_with_progress(
                full_url, save_path, println=self._print, label=filename, timeout=60
            )
            self._println(f"\033[92m[Save Media] Saved to {save_path}\033[0m")
        except Exception as e:
            self._println(f"\033[91m[Save Media] Error: {e}\033[0m")

    def confirm_close(self):
        if not self._updating:
            self.save_window_state()
        self._confirm_close = True
        self._graceful_close()

    def modal_response(self, result, action):
        if action == 'close':
            if result:
                if not self._updating:
                    self.save_window_state()
                self._confirm_close = True
                self._graceful_close()
        elif action == 'update':
            if result:
                bat = os.path.join(ROOT_DIR, 'Update ComfyUI.bat')
                threading.Thread(target=self._do_update, args=(bat,), daemon=True).start()

    def _flush_state_to_disk(self):
        try:
            cw = _EZI_WINDOW_REF.get("comfy_webview")
            if cw is not None and _EZI_WINDOW_REF.get("comfy_ready"):
                def _do_flush():
                    try:
                        cw.CoreWebView2.ExecuteScriptAsync(
                            "window.__eziFlushStorageNow && window.__eziFlushStorageNow();"
                        )
                    except Exception:
                        pass
                self._ui_invoke(_do_flush)
        except Exception:
            pass

        time.sleep(0.4)

    def _close_window(self):
        try:
            self._safe_eval("""
                (function() {
                    try {
                        var f = document.getElementById('ui-frame');
                        if (!f) return;
                        try {
                            var w = f.contentWindow;
                            if (w) w.onbeforeunload = null;
                        } catch(e2) {}
                        f.src = 'about:blank';
                    } catch(e) {}
                })();
            """)
        except Exception:
            pass

        def _delayed_destroy():
            time.sleep(0.4)
            if self._window:
                self._window.destroy()
        threading.Thread(target=_delayed_destroy, daemon=True).start()

    def _graceful_close(self):
        self._flush_state_to_disk()
        self._close_window()

    def set_window(self, w):
        self._window = w

    def minimize_window(self):
        try:
            if self._window:
                self._window.minimize()
        except Exception:
            pass

    def toggle_maximize_window(self):
        try:
            if not self._window:
                return
            if self._is_maximized():
                self._window.restore()
            else:
                self._window.maximize()
        except Exception:
            pass

    def close_window(self):
        try:
            if self._window:
                self._window.destroy()
        except Exception:
            pass

    def get_maximized_state(self):
        return self._is_maximized()

    def get_window_rect(self):
        try:
            w = self._window
            if not w:
                return None
            return {'x': w.x, 'y': w.y, 'w': w.width, 'h': w.height}
        except Exception:
            return None

    def move_window_to(self, x, y):
        try:
            if self._window:
                self._window.move(int(x), int(y))
        except Exception:
            pass

    def resize_window(self, width, height, fix_east=False, fix_south=False):
        try:
            if not self._window:
                return
            fp = FixPoint(0)
            if fix_east:
                fp |= FixPoint.EAST
            if fix_south:
                fp |= FixPoint.SOUTH
            self._window.resize(int(width), int(height), fp)
        except Exception:
            pass

    def set_window_rect(self, x, y, w, h):
        try:
            hwnd = self._main_hwnd or _get_hwnd(self._window)
            if not hwnd:
                return
            import ctypes.wintypes as wt
            user32 = ctypes.windll.user32
            try:
                scale = user32.GetDpiForWindow(hwnd) / 96.0
            except Exception:
                scale = 1.0
            if not scale:
                scale = 1.0
            px_x = int(round(x * scale))
            px_y = int(round(y * scale))
            px_w = int(round(w * scale))
            px_h = int(round(h * scale))
            SWP_NOZORDER   = 0x0004
            SWP_NOACTIVATE = 0x0010
            user32.SetWindowPos(hwnd, None, px_x, px_y, px_w, px_h, SWP_NOZORDER | SWP_NOACTIVATE)
        except Exception:
            pass

    def get_work_area(self):
        try:
            w = self._window
            if not w:
                return None
            hwnd = _get_hwnd(w)
            if not hwnd:
                return None

            import ctypes.wintypes
            user32 = ctypes.windll.user32
            MONITOR_DEFAULTTONEAREST = 2

            class _RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                            ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

            class _MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", _RECT),
                            ("rcWork", _RECT), ("dwFlags", ctypes.c_ulong)]

            hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
            mi = _MONITORINFO()
            mi.cbSize = ctypes.sizeof(_MONITORINFO)
            if not hmon or not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                return None

            try:
                scale = user32.GetDpiForWindow(hwnd) / 96.0
            except Exception:
                scale = 1.0
            if not scale:
                scale = 1.0

            rw = mi.rcWork
            return {
                'x': int(round(rw.left / scale)),
                'y': int(round(rw.top / scale)),
                'w': int(round((rw.right - rw.left) / scale)),
                'h': int(round((rw.bottom - rw.top) / scale)),
            }
        except Exception:
            return None

    def _tb_set(self, value, maximum, state=2):
        self._tb_queue.put_nowait((value, maximum, state))

    def _tb_worker_start(self):
        ctypes.windll.ole32.CoInitializeEx(None, 0)
        while True:
            try:
                value, maximum, state = self._tb_queue.get(timeout=2)
                if not self._tb_hwnd:
                    self._tb_hwnd = _get_hwnd(self._window)
                _taskbar_progress_ctypes(self._tb_hwnd, value, maximum, state)
            except Exception:
                pass

    def set_title(self, suffix: str = ""):
        if self._window:
            try:
                t = f'ComfyUI-EZi-Desktop  v{APP_VERSION}'
                self._window.set_title(t + (f' - {suffix}' if suffix else ''))
            except Exception:
                pass

    def js_ready(self, cols=0):
        try:
            if cols and int(cols) > 0:
                self._columns = max(40, int(cols))
        except Exception:
            pass
        self._js_ready.set()
        if not self._started:
            self._started = True
            threading.Thread(target=self._run, daemon=True).start()
            threading.Thread(target=self._check_update, daemon=True).start()
            threading.Thread(target=self._check_ezi_update, daemon=True).start()
            threading.Thread(target=self._port_monitor, daemon=True).start()

    def set_columns(self, cols):
        try:
            self._columns = max(40, int(cols))
        except Exception:
            pass

    def _hwnd_maximized(self, hwnd):
        try:
            if not hwnd:
                return False
            wp = EZI_WINDOWPLACEMENT()
            wp.length = ctypes.sizeof(EZI_WINDOWPLACEMENT)
            ctypes.windll.user32.GetWindowPlacement(hwnd, ctypes.byref(wp))
            return wp.showCmd == 3
        except Exception:
            return False

    def _is_maximized(self):
        try:
            import ctypes.wintypes as wt
            hwnd = _get_hwnd(self._window)
            if not hwnd:
                return False
            wp = EZI_WINDOWPLACEMENT()
            wp.length = ctypes.sizeof(EZI_WINDOWPLACEMENT)
            ctypes.windll.user32.GetWindowPlacement(hwnd, ctypes.byref(wp))
            return wp.showCmd == 3
        except Exception:
            return False

    def _get_columns(self):
        try:
            win = self._console_win or self._window
            if win:
                result = win.evaluate_js(
                    "(function(){"
                    "var canvas=document.createElement('canvas');"
                    "var ctx=canvas.getContext('2d');"
                    "ctx.font='12px Consolas,\"Courier New\",monospace';"
                    "var charW=ctx.measureText('M').width||7.2;"
                    "var t=document.getElementById('term-panel');"
                    "var style=window.getComputedStyle(t);"
                    "var padL=parseFloat(style.paddingLeft)||0;"
                    "var padR=parseFloat(style.paddingRight)||0;"
                    "var scrollbarW=Math.max(t.offsetWidth-t.clientWidth,17);"
                    "var usable=t.clientWidth-padL-padR-scrollbarW-2;"
                    "var cols=Math.floor(usable/charW);"
                    "return cols>0?cols:0;"
                    "})()"
                )
                if result and int(result) > 0:
                    cols = max(40, int(result))
                    if self._console_win is not None:
                        maxed = self._hwnd_maximized(self._console_hwnd)
                    else:
                        maxed = self._is_maximized()
                    if not maxed:
                        cols = min(cols, 80)
                    return cols
        except Exception:
            pass
        return self._columns

    def ui_shown(self):
        self._ui_shown = True

    def on_loaded(self):
        hwnd = _get_hwnd(self._window)
        if hwnd:
            self._main_hwnd = hwnd
            _apply_captioned_frame_style(hwnd)
            _install_hidden_titlebar_hook(hwnd)
            _suppress_dwm_border(hwnd)
            _taskbar_mark_not_fullscreen(hwnd)
        _set_window_icon(hwnd)

    def _kill_process_tree(self, root_pid):
        try:
            kernel = ctypes.windll.kernel32
            PROCESS_TERMINATE = 0x0001
            SYNCHRONIZE = 0x00100000
            TH32CS_SNAPPROCESS = 0x00000002

            class PROCESSENTRY32(ctypes.Structure):
                _fields_ = [
                    ("dwSize",              ctypes.c_uint32),
                    ("cntUsage",            ctypes.c_uint32),
                    ("th32ProcessID",       ctypes.c_uint32),
                    ("th32DefaultHeapID",   ctypes.POINTER(ctypes.c_ulong)),
                    ("th32ModuleID",        ctypes.c_uint32),
                    ("cntThreads",          ctypes.c_uint32),
                    ("th32ParentProcessID", ctypes.c_uint32),
                    ("pcPriClassBase",      ctypes.c_long),
                    ("dwFlags",             ctypes.c_uint32),
                    ("szExeFile",           ctypes.c_char * 260),
                ]

            def _kill(pid):
                snap = kernel.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
                if snap == ctypes.c_void_p(-1).value:
                    return
                children = []
                try:
                    entry = PROCESSENTRY32()
                    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
                    if kernel.Process32First(snap, ctypes.byref(entry)):
                        while True:
                            if entry.th32ParentProcessID == pid:
                                children.append(entry.th32ProcessID)
                            if not kernel.Process32Next(snap, ctypes.byref(entry)):
                                break
                finally:
                    kernel.CloseHandle(snap)
                for child_pid in children:
                    _kill(child_pid)
                h = kernel.OpenProcess(PROCESS_TERMINATE | SYNCHRONIZE, False, pid)
                if h:
                    kernel.TerminateProcess(h, 1)
                    result = kernel.WaitForSingleObject(h, 3000)
                    kernel.CloseHandle(h)
                    if result != 0:
                        try:
                            subprocess.run(
                                ['taskkill', '/F', '/T', '/PID', str(pid)],
                                capture_output=True, timeout=5,
                                creationflags=self._NO_WIN
                            )
                        except Exception:
                            pass

            _kill(root_pid)
        except Exception:
            pass

    def _kill_port_owner(self, port):
        try:
            iphlpapi = ctypes.windll.iphlpapi

            class MIB_TCPROW_OWNER_PID(ctypes.Structure):
                _fields_ = [
                    ('dwState',      ctypes.c_ulong),
                    ('dwLocalAddr',  ctypes.c_ulong),
                    ('dwLocalPort',  ctypes.c_ulong),
                    ('dwRemoteAddr', ctypes.c_ulong),
                    ('dwRemotePort', ctypes.c_ulong),
                    ('dwOwningPid',  ctypes.c_ulong),
                ]

            buf_size = ctypes.c_ulong(0)
            iphlpapi.GetExtendedTcpTable(None, ctypes.byref(buf_size), False, 2, 5, 0)
            buf = (ctypes.c_byte * buf_size.value)()
            if iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(buf_size), False, 2, 5, 0) == 0:
                count = ctypes.c_ulong.from_buffer(buf).value
                offset = ctypes.sizeof(ctypes.c_ulong)
                row_sz = ctypes.sizeof(MIB_TCPROW_OWNER_PID)
                for i in range(count):
                    row = MIB_TCPROW_OWNER_PID.from_buffer(buf, offset + i * row_sz)
                    local_port = ((row.dwLocalPort & 0xFF) << 8) | ((row.dwLocalPort >> 8) & 0xFF)
                    if local_port == port:
                        pid = row.dwOwningPid
                        if pid and pid != os.getpid():
                            try:
                                self._kill_process_tree(pid)
                            except Exception:
                                pass
        except Exception:
            pass

    def _kill_running_proc(self):
        port = self._comfy_port_holder[0]

        self._restarting = False

        started_own_proc = self._proc is not None

        if self._proc:
            try:
                self._kill_process_tree(self._proc.pid)
            except Exception:
                pass
            self._proc = None

        if port and started_own_proc:
            self._kill_port_owner(port)

        if port and started_own_proc:
            for i in range(80):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.2)
                        if s.connect_ex(('127.0.0.1', port)) != 0:
                            break
                except Exception:
                    break
                if i > 0 and i % 5 == 0:
                    self._kill_port_owner(port)
                time.sleep(0.1)

    def _port_monitor(self):
        import urllib.request as _ur

        def _http_alive(port):
            try:
                r = _ur.urlopen(f'http://127.0.0.1:{port}/system_stats', timeout=5)
                return r.status == 200
            except Exception:
                return False

        was_up = False
        down_count = 0
        restart_start_time = 0
        _SOCK_DOWN_THRESHOLD = 12

        while self._window:
            time.sleep(0.5)
            if self._updating:
                was_up = False
                down_count = 0
                continue
            port = self._comfy_port_holder[0]
            if not port:
                continue
            sock_up = False
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.5)
                    sock_up = s.connect_ex(('127.0.0.1', port)) == 0
            except Exception:
                pass
            if sock_up:
                down_count = 0
                if self._restarting:
                    if restart_start_time == 0:
                        restart_start_time = time.time()
                    if _http_alive(port):
                        self._restarting = False
                        restart_start_time = 0
                        self._url_found = True
                        was_up = True
                        self._safe_eval("set_dot_ready();")
                        self._navigate_comfy_webview(f'http://127.0.0.1:{self._proxy_port}/')
                    else:
                        if time.time() - restart_start_time > 15:
                            self._restarting = False
                            restart_start_time = 0
                            self._url_found = True
                            was_up = True
                            self._safe_eval("set_dot_ready();")
                            self._navigate_comfy_webview(f'http://127.0.0.1:{self._proxy_port}/')
                elif not was_up:
                    was_up = True
            else:
                if was_up and not self._restarting:
                    down_count += 1
                    if down_count >= _SOCK_DOWN_THRESHOLD:
                        if not _http_alive(port):
                            was_up = False
                            down_count = 0
                            self._restarting = True
                            self._url_found = False
                            restart_start_time = time.time()
                            self._println(f"\n\033[93m⚠  ComfyUI is restarting...\033[0m")
                            self._safe_eval("switchToConsole('Restarting...')")
                        else:
                            down_count = 0
                if self._restarting:
                    if restart_start_time > 0 and time.time() - restart_start_time > 300:
                        self._restarting = False
                        restart_start_time = 0
                        self._url_found = False
                        was_up = False
                        self._println(f"\n\033[91m⚠  Restart timed out. ComfyUI did not come back online.\033[0m")
                        self._safe_eval("switchToConsole('Stopped')")
    def _check_update(self):
        try:
            if not os.path.isdir(os.path.join(self.COMFY_DIR, '.git')):
                return
            self._println('\033[93mChecking for ComfyUI update...\033[0m')
            subprocess.run(['git', 'fetch', '--quiet', '--tags'], cwd=self.COMFY_DIR, capture_output=True, timeout=8, creationflags=self._NO_WIN)
            local = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=self.COMFY_DIR, capture_output=True, timeout=5, creationflags=self._NO_WIN
            ).stdout.strip().decode(errors='replace')
            for ref in ['origin/main', 'origin/master', 'origin/HEAD']:
                r = subprocess.run(
                    ['git', 'rev-parse', ref],
                    cwd=self.COMFY_DIR, capture_output=True, timeout=5, creationflags=self._NO_WIN
                )
                if r.returncode == 0:
                    remote = r.stdout.strip().decode(errors='replace')
                    break
            else:
                remote = ''
            all_tags = subprocess.run(
                ['git', 'tag', '--sort=-version:refname'],
                cwd=self.COMFY_DIR, capture_output=True, timeout=5, creationflags=self._NO_WIN
            ).stdout.decode(errors='replace').strip().splitlines()
            latest_tag = all_tags[0].strip() if all_tags else ''
            if latest_tag:
                head_r = subprocess.run(
                    ['git', 'rev-parse', 'HEAD'],
                    cwd=self.COMFY_DIR, capture_output=True, timeout=5, creationflags=self._NO_WIN
                )
                tag_r = subprocess.run(
                    ['git', 'rev-parse', f'{latest_tag}^{{}}'],
                    cwd=self.COMFY_DIR, capture_output=True, timeout=5, creationflags=self._NO_WIN
                )
                head_hash = head_r.stdout.strip().decode(errors='replace')
                tag_hash = tag_r.stdout.strip().decode(errors='replace')
                if head_hash and tag_hash and head_hash != tag_hash:
                    stable_tag = None
                    try:
                        import urllib.request as _ur, json as _json
                        req = _ur.Request(
                            'https://api.github.com/repos/Comfy-Org/ComfyUI/releases/latest',
                            headers={'User-Agent': EZI_UA_TAG}
                        )
                        with _ur.urlopen(req, timeout=8) as resp:
                            rel_data = _json.loads(resp.read())
                        stable_tag = rel_data.get('tag_name') or None
                    except Exception:
                        pass
                    is_stable = bool(stable_tag and latest_tag == stable_tag)
                    if stable_tag:
                        try:
                            import json as _json2
                            _cu_data = {}
                            if os.path.exists(SETTINGS_PATH):
                                with open(SETTINGS_PATH, 'r', encoding='utf-8') as _sf:
                                    _cu_data = _json2.loads(_sf.read())
                            _cu_data['cached_comfy_stable_version'] = stable_tag
                            _tmp = SETTINGS_PATH + '.tmp'
                            with open(_tmp, 'w', encoding='utf-8') as _sf:
                                _json2.dump(_cu_data, _sf, indent=2, ensure_ascii=False)
                            os.replace(_tmp, SETTINGS_PATH)
                        except Exception:
                            pass
                    elif not stable_tag:
                        try:
                            import json as _json2
                            if os.path.exists(SETTINGS_PATH):
                                with open(SETTINGS_PATH, 'r', encoding='utf-8') as _sf:
                                    _cu_data = _json2.loads(_sf.read())
                                _cached_stable = _cu_data.get('cached_comfy_stable_version') or None
                                is_stable = bool(_cached_stable and latest_tag == _cached_stable)
                        except Exception:
                            pass
                    self._safe_eval(f"show_update({json.dumps(latest_tag)}, {json.dumps(is_stable)})")
        except Exception:
            pass

    def _get_latest_ezi_tag(self):
        import urllib.request as _ur
        url = "https://github.com/Tavris1/ComfyUI-Easy-Install/releases/latest"
        req = _ur.Request(url, headers={"User-Agent": EZI_UA_TAG}, method="HEAD")
        with _ur.urlopen(req, timeout=8) as r:
            final_url = r.geturl()
        tag = final_url.rstrip("/").rsplit("/", 1)[-1].strip().lstrip("v")
        if tag:
            return tag
        raise ValueError(f"could not parse tag from redirect target: {final_url!r}")

    def _get_latest_ezi_tag_via_api(self):
        import urllib.request as _ur
        import json as _json
        url = "https://api.github.com/repos/Tavris1/ComfyUI-Easy-Install/releases/latest"
        req = _ur.Request(url, headers={"User-Agent": EZI_UA_TAG})
        with _ur.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
        return data.get("tag_name", "").strip().lstrip("v")

    def _check_ezi_update(self):
        return  # AMD helper releases are maintained separately.
        try:
            self._println('\033[95mChecking for Easy-Install update...\033[0m')
            try:
                tag = self._get_latest_ezi_tag()
            except Exception as e:
                self._println(f'\033[93mredirect-based check failed ({e!r}), falling back to api.github.com...\033[0m')
                tag = self._get_latest_ezi_tag_via_api()
            if not tag:
                self._println('\033[93mEasy-Install update check: could not determine latest tag\033[0m')
                return
            local_parts  = [int(x) for x in APP_VERSION.split(".") if x.isdigit()]
            remote_parts = [int(x) for x in tag.split(".")      if x.isdigit()]
            if remote_parts > local_parts:
                display = "v" + tag
                self._println(f'\033[95mEasy-Install update available: v{APP_VERSION} -> {display}\033[0m')
                self._safe_eval(f"show_ezi_update({json.dumps(display)})")
            else:
                self._println(f'\033[92mEasy-Install is up to date (v{APP_VERSION}, latest is v{tag})\033[0m')
        except Exception as e:
            self._println(f'\033[91mEasy-Install update check failed: {e!r}\033[0m')

    def run_update(self):
        bat = os.path.join(ROOT_DIR, 'Update ComfyUI.bat')
        if not os.path.exists(bat):
            self._safe_eval(f"show_update_missing({json.dumps(ROOT_DIR)})")
            return
        self._safe_eval("show_update_confirm()")

    def run_ezi_update(self):
        bat = os.path.join(ROOT_DIR, "Update Easy-Install.bat")
        if not os.path.exists(bat):
            self._safe_eval(f"show_update_missing({json.dumps(ROOT_DIR)})")
            return
        threading.Thread(target=self._do_run_bat, args=(bat,), daemon=True).start()

    def _do_update(self, bat):
        self._do_run_bat(bat, status_label='Updating...', hide_update_notice=True)

    def retry(self, cols=0):
        try:
            if cols and int(cols) > 0:
                self._columns = max(40, int(cols))
                os.environ['TQDM_NCOLS'] = str(self._columns)
        except Exception:
            pass
        self._restart_comfy(check_update=False)

    def _restart_comfy(self, check_update=True):
        self._started = False
        self._url_found = False
        self._ui_shown = False
        self._restarting = True
        self._run_id += 1
        threading.Thread(target=self._run, daemon=True).start()
        if check_update:
            threading.Thread(target=self._check_update, daemon=True).start()
            threading.Thread(target=self._check_ezi_update, daemon=True).start()

    def _resolve_output_dir(self):
        output_dir = None
        try:
            if os.path.exists(BAT_FILE):
                with open(BAT_FILE, 'r', encoding='utf-8', errors='replace') as f:
                    bat_content = f.read()
                m_env = re.search(
                    r'(?i)set\s+"?COMFY_OUTPUT_DIR=([^"\n]+)"?',
                    bat_content
                )
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

    def get_system_info(self):
        import shutil
        import glob
        from concurrent.futures import ThreadPoolExecutor

        def _ps(cmd, timeout=8):
            raise RuntimeError('Obsolete system information query')

        def _get_python():
            try:
                r = subprocess.run([self.PY_EXE, "--version"], capture_output=True, stdin=subprocess.DEVNULL, timeout=5, creationflags=self._NO_WIN)
                ver = r.stdout.decode(errors='replace').strip() or r.stderr.decode(errors='replace').strip()
                parts = ver.split()
                return parts[1] if len(parts) > 1 else ver
            except Exception:
                return 'N/A'

        def _get_torch():
            try:
                site = os.path.join(ROOT_DIR, 'python_embeded', 'Lib', 'site-packages')
                version_file = os.path.join(site, 'torch', 'version.py')
                with open(version_file, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                torch_m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
                cuda_m  = re.search(r'\bhip(?:\s*:\s*\S+)?\s*=\s*["\']([^"\']+)["\']', content)
                tv = torch_m.group(1) if torch_m else 'N/A'
                cv = cuda_m.group(1) if cuda_m else 'N/A'
                return tv, cv
            except Exception:
                pass
            try:
                r = subprocess.run(
                    [self.PY_EXE, "-c", "import torch; v=torch.__version__; cv=torch.version.hip or 'N/A'; print(v+'|'+cv)"],
                    capture_output=True, stdin=subprocess.DEVNULL, timeout=10, creationflags=self._NO_WIN
                )
                out = r.stdout.decode(errors='replace').strip()
                if '|' in out:
                    torch_v, cuda_v = out.split('|', 1)
                    return torch_v, cuda_v
            except Exception:
                pass
            return 'N/A', 'N/A'

        def _get_comfyui():
            try:
                import ast
                version_file = os.path.join(self.COMFY_DIR, 'comfyui_version.py')
                with open(version_file, encoding='utf-8') as version_source:
                    for statement in ast.parse(version_source.read()).body:
                        if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == '__version__' for target in statement.targets):
                            value = ast.literal_eval(statement.value)
                            if isinstance(value, str):
                                return value
            except (OSError, ValueError, SyntaxError):
                pass
            try:
                r = subprocess.run(
                    ['git', 'describe', '--tags', '--exact-match', 'HEAD'],
                    cwd=self.COMFY_DIR, capture_output=True, stdin=subprocess.DEVNULL, timeout=5, creationflags=self._NO_WIN
                )
                if r.returncode == 0:
                    return r.stdout.decode(errors='replace').strip()
                r2 = subprocess.run(
                    ['git', 'describe', '--tags', '--abbrev=0', 'HEAD'],
                    cwd=self.COMFY_DIR, capture_output=True, stdin=subprocess.DEVNULL, timeout=5, creationflags=self._NO_WIN
                )
                return r2.stdout.decode(errors='replace').strip() or 'N/A'
            except Exception:
                return 'N/A'

        def _get_frontend():
            try:
                import importlib.metadata as _im
                ver = _im.version('comfyui_frontend_package')
                if ver and ver != '0.1.0':
                    return ver
            except Exception:
                pass
            try:
                site = os.path.join(ROOT_DIR, 'python_embeded', 'Lib', 'site-packages')
                matches = sorted(glob.glob(
                    os.path.join(site, 'comfyui_frontend_package-*.dist-info', 'METADATA')
                ), reverse=True)
                for meta_path in matches:
                    with open(meta_path, 'r', encoding='utf-8', errors='replace') as f:
                        for line in f:
                            if line.startswith('Version:'):
                                ver = line.split(':', 1)[1].strip()
                                if ver and ver != '0.1.0':
                                    return ver
                            elif line.startswith('Name:') or (line.strip() == '' and line != line.lstrip()):
                                break
            except Exception:
                pass
            return 'N/A'

        def _get_rocm():
            from importlib.metadata import distributions
            site = os.path.join(ROOT_DIR, 'python_embeded', 'Lib', 'site-packages')
            versions = {dist.metadata.get('Name', '').lower().replace('_', '-'): dist.version
                        for dist in distributions(path=[site])}
            return versions.get('rocm-sdk-core') or versions.get('rocm') or 'N/A'

        def _get_amd_driver(gpu):
            import winreg
            display_key = r'SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}'
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, display_key) as adapters:
                    for index in range(winreg.QueryInfoKey(adapters)[0]):
                        child = winreg.EnumKey(adapters, index)
                        try:
                            with winreg.OpenKey(adapters, child) as adapter:
                                description = winreg.QueryValueEx(adapter, 'DriverDesc')[0]
                                if description.casefold() == gpu.casefold():
                                    return winreg.QueryValueEx(adapter, 'DriverVersion')[0]
                        except OSError:
                            continue
            except OSError:
                pass
            return 'N/A'

        def _get_ram():
            import psutil
            return str(round(psutil.virtual_memory().total / 1024**3)) + ' GB'

        def _get_pagefile():
            from windows_tools import pagefile
            return pagefile()

        def _get_gpu():
            try:
                import sys as _sys
                _sys.path.insert(0, os.path.join(ROOT_DIR, 'amd'))
                from runtime import configure
                _env, _arch = configure(ROOT_DIR)
                _code = "import torch; p=torch.cuda.get_device_properties(0); print(p.name+'|'+str(round(p.total_memory/1024**3))+' GB')"
                r = subprocess.run([self.PY_EXE, '-c', _code], env=_env, capture_output=True,
                                   timeout=30, creationflags=self._NO_WIN, check=True)
                gpu, vram = r.stdout.decode().strip().split('|')
                return gpu + ' (' + _arch + ')', vram, _get_amd_driver(gpu)
            except Exception:
                return 'AMD detection failed', 'N/A', 'N/A'

        def _get_long_paths():
            try:
                r = subprocess.run(
                    ['reg', 'query', r'HKLM\SYSTEM\CurrentControlSet\Control\FileSystem', '/v', 'LongPathsEnabled'],
                    capture_output=True, stdin=subprocess.DEVNULL, timeout=5, creationflags=self._NO_WIN
                )
                return '0x1' in r.stdout.decode(errors='replace')
            except Exception:
                return False

        info = {}
        with ThreadPoolExecutor(max_workers=8) as ex:
            f_python     = ex.submit(_get_python)
            f_torch      = ex.submit(_get_torch)
            f_rocm       = ex.submit(_get_rocm)
            f_comfyui    = ex.submit(_get_comfyui)
            f_frontend   = ex.submit(_get_frontend)
            f_ram        = ex.submit(_get_ram)
            f_pagefile   = ex.submit(_get_pagefile)
            f_gpu        = ex.submit(_get_gpu)
            f_long_paths = ex.submit(_get_long_paths)

            info['python']                    = f_python.result()
            info['torch'], info['hip']        = f_torch.result()
            info['rocm']                      = f_rocm.result()
            info['comfyui']                   = f_comfyui.result()
            info['frontend']                  = f_frontend.result()
            info['ram']                       = f_ram.result()
            info['pagefile']                  = f_pagefile.result()
            info['gpu'], info['vram'], info['driver'] = f_gpu.result()
            info['long_paths']                = f_long_paths.result()

        return info

    def get_cache_sizes(self):
        import shutil

        def _dir_size_mb(path):
            total = 0
            try:
                for dirpath, _dirnames, filenames in os.walk(path):
                    for f in filenames:
                        try:
                            total += os.path.getsize(os.path.join(dirpath, f))
                        except Exception:
                            pass
            except Exception:
                pass
            return total

        def _fmt(b):
            if b <= 0:
                return '0 MB'
            mb = b / (1024 * 1024)
            if mb >= 1024:
                return f'{mb/1024:.2f} GB'
            if mb < 0.1:
                return '0 MB'
            return f'{mb:.1f} MB'

        pip_size = 0
        try:
            r = subprocess.run(
                [self.PY_EXE, '-m', 'pip', 'cache', 'dir'],
                capture_output=True, stdin=subprocess.DEVNULL, timeout=10, creationflags=self._NO_WIN
            )
            pip_dir = r.stdout.decode(errors='replace').strip()
            if pip_dir and os.path.isdir(pip_dir):
                pip_size = _dir_size_mb(pip_dir)
        except Exception:
            pass

        uv_size = 0
        try:
            uv_exe = os.path.join(ROOT_DIR, 'python_embeded', 'Scripts', 'uv.exe')
            if not os.path.exists(uv_exe):
                import shutil as _sh
                uv_exe = _sh.which('uv') or ''
            if uv_exe:
                r = subprocess.run(
                    [uv_exe, 'cache', 'dir'],
                    capture_output=True, stdin=subprocess.DEVNULL, timeout=10, creationflags=self._NO_WIN
                )
                uv_dir = r.stdout.decode(errors='replace').strip()
                if uv_dir and os.path.isdir(uv_dir):
                    uv_size = _dir_size_mb(uv_dir)
        except Exception:
            pass

        return {'pip': _fmt(pip_size), 'uv': _fmt(uv_size)}

    def clear_cache(self, cache_type):
        import shutil as _sh

        def _fmt(b):
            if b <= 0:
                return '0 MB'
            mb = b / (1024 * 1024)
            if mb >= 1024:
                return f'{mb/1024:.2f} GB'
            if mb < 0.1:
                return '0 MB'
            return f'{mb:.1f} MB'

        if cache_type == 'pip':
            try:
                subprocess.run(
                    [self.PY_EXE, '-m', 'pip', 'cache', 'purge'],
                    capture_output=True, stdin=subprocess.DEVNULL, timeout=30, creationflags=self._NO_WIN
                )
            except Exception:
                pass
            size = 0
            try:
                r = subprocess.run(
                    [self.PY_EXE, '-m', 'pip', 'cache', 'dir'],
                    capture_output=True, stdin=subprocess.DEVNULL, timeout=10, creationflags=self._NO_WIN
                )
                pip_dir = r.stdout.decode(errors='replace').strip()
                if pip_dir and os.path.isdir(pip_dir):
                    for dp, _d, fs in os.walk(pip_dir):
                        for f in fs:
                            try:
                                size += os.path.getsize(os.path.join(dp, f))
                            except Exception:
                                pass
            except Exception:
                pass
            return {'size': _fmt(size)}

        if cache_type == 'uv':
            uv_exe = os.path.join(ROOT_DIR, 'python_embeded', 'Scripts', 'uv.exe')
            if not os.path.exists(uv_exe):
                uv_exe = _sh.which('uv') or ''
            if uv_exe:
                try:
                    r = subprocess.run(
                        [uv_exe, 'cache', 'dir'],
                        capture_output=True, stdin=subprocess.DEVNULL, timeout=10, creationflags=self._NO_WIN
                    )
                    uv_dir = r.stdout.decode(errors='replace').strip()
                except Exception:
                    uv_dir = ''

                try:
                    subprocess.run(
                        [uv_exe, 'cache', 'clean'],
                        capture_output=True, stdin=subprocess.DEVNULL, timeout=60, creationflags=self._NO_WIN
                    )
                except Exception:
                    pass

                if uv_dir and os.path.isdir(uv_dir):
                    try:
                        _sh.rmtree(uv_dir, ignore_errors=True)
                    except Exception:
                        pass

            size = 0
            try:
                if uv_exe and uv_dir and os.path.isdir(uv_dir):
                    for dp, _d, fs in os.walk(uv_dir):
                        for f in fs:
                            try:
                                size += os.path.getsize(os.path.join(dp, f))
                            except Exception:
                                pass
            except Exception:
                pass
            return {'size': _fmt(size)}

    def check_output_folder(self):
        path = self._resolve_output_dir()
        return path or ""

    def get_frontend_versions(self):
        import urllib.request as _ur, json as _json
        current = None
        try:
            import importlib.metadata as _im
            for _pkg in ('comfyui_frontend_package', 'comfyui-frontend-package'):
                try:
                    ver = _im.version(_pkg)
                    if ver and ver != '0.1.0':
                        current = ver
                        break
                except Exception:
                    continue
        except Exception:
            pass
        if not current:
            try:
                site = os.path.join(ROOT_DIR, 'python_embeded', 'Lib', 'site-packages')
                matches = sorted(glob.glob(
                    os.path.join(site, 'comfyui_frontend_package-*.dist-info', 'METADATA')
                ), reverse=True)
                for meta_path in matches:
                    with open(meta_path, 'r', encoding='utf-8', errors='replace') as _f:
                        for line in _f:
                            if line.startswith('Version:'):
                                ver = line.split(':', 1)[1].strip()
                                if ver and ver != '0.1.0':
                                    current = ver
                                break
                    if current:
                        break
            except Exception:
                pass
        try:
            with _ur.urlopen('https://pypi.org/pypi/comfyui-frontend-package/json', timeout=8) as r:
                data = _json.loads(r.read())
            all_versions = sorted(
                data.get('releases', {}).keys(),
                key=lambda v: [int(x) for x in v.replace('.post', '.').split('.') if x.isdigit()],
                reverse=True
            )
            versions = all_versions[:100]
            if current and current not in versions:
                versions.append(current)
                versions.sort(key=lambda v: [int(x) for x in v.replace('.post', '.').split('.') if x.isdigit()], reverse=True)
        except Exception:
            versions = [current] if current else []
        is_nightly = self.get_frontend_is_nightly()
        return {'current': current, 'versions': versions, 'isNightly': bool(is_nightly)}

    def get_frontend_is_nightly(self):
        import glob as _glob, re as _re

        site_pkgs = os.path.join(ROOT_DIR, 'python_embeded', 'Lib', 'site-packages')
        pkg_dir   = os.path.join(site_pkgs, 'comfyui_frontend_package')
        if not os.path.isdir(pkg_dir):
            candidates = _glob.glob(os.path.join(site_pkgs, 'comfyui_frontend_package*'))
            pkg_dir = next((c for c in candidates
                            if os.path.isdir(c) and 'dist-info' not in c), None)
        if not pkg_dir:
            return None

        assets_dir = os.path.join(pkg_dir, 'static', 'assets')
        if not os.path.isdir(assets_dir):
            return None

        patterns = [
            re.compile(r'__IS_NIGHTLY__\s*[=:]\s*(true|false)', re.IGNORECASE),
            re.compile(r'isNightly\s*=\s*(true|false)',           re.IGNORECASE),
        ]

        js_files = sorted(
            _glob.glob(os.path.join(assets_dir, 'index-*.js')),
            key=os.path.getsize, reverse=True
        )
        if not js_files:
            js_files = _glob.glob(os.path.join(assets_dir, '*.js'))

        for js_path in js_files[:3]:
            try:
                with open(js_path, 'r', encoding='utf-8', errors='replace') as f:
                    chunk_size = 256 * 1024
                    prev_tail  = ''
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        search_text = prev_tail + chunk
                        for pat in patterns:
                            m = pat.search(search_text)
                            if m:
                                return m.group(1).lower() == 'true'
                        prev_tail = chunk[-200:]
            except Exception:
                continue

        return None

    def get_comfyui_required_frontend(self, tag):
        import re as _re, urllib.request as _ur, base64 as _b64
        if not tag or tag == 'NIGHTLY':
            return None

        def _parse_fe_version(line):
            m = _re.search(r'==\s*([^\s,;#]+)', line)
            return m.group(1).strip() if m else None

        def _find_in_lines(lines):
            for line in lines:
                line = line.strip()
                if line.lower().startswith('comfyui-frontend-package'):
                    return _parse_fe_version(line)
            return None

        try:
            r = subprocess.run(
                ['git', 'show', f'tags/{tag}:requirements.txt'],
                cwd=self.COMFY_DIR, capture_output=True, timeout=5,
                creationflags=self._NO_WIN
            )
            if r.returncode == 0:
                result = _find_in_lines(r.stdout.decode(errors='replace').splitlines())
                if result is not None:
                    return result
                return None
        except Exception:
            pass

        try:
            url = (f'https://raw.githubusercontent.com/Comfy-Org/ComfyUI'
                   f'/{tag}/requirements.txt')
            req = _ur.Request(url, headers={'User-Agent': 'ComfyUI-EZi'})
            with _ur.urlopen(req, timeout=8) as resp:
                text = resp.read().decode('utf-8', errors='replace')
            result = _find_in_lines(text.splitlines())
            if result is not None:
                return result
            return None
        except Exception:
            pass

        try:
            current_tag = None
            r = subprocess.run(
                ['git', 'describe', '--tags', '--exact-match', 'HEAD'],
                cwd=self.COMFY_DIR, capture_output=True, timeout=3,
                creationflags=self._NO_WIN
            )
            if r.returncode == 0:
                current_tag = r.stdout.strip().decode(errors='replace')
            if current_tag and current_tag == tag:
                req_path = os.path.join(self.COMFY_DIR, 'requirements.txt')
                if os.path.exists(req_path):
                    with open(req_path, 'r', encoding='utf-8', errors='replace') as f:
                        return _find_in_lines(f)
        except Exception:
            pass

        return None

    def get_comfyui_versions(self):
        import urllib.request as _ur, json as _json

        def _ver_key(tag):
            t = tag.lstrip('v')
            parts = []
            for x in t.replace('-', '.').split('.'):
                try: parts.append(int(x))
                except ValueError: parts.append(0)
            return parts

        current = None
        is_stable = False
        try:
            r = subprocess.run(
                ['git', 'describe', '--tags', '--exact-match', 'HEAD'],
                cwd=self.COMFY_DIR, capture_output=True, timeout=5, creationflags=self._NO_WIN
            )
            if r.returncode == 0:
                current = r.stdout.strip().decode(errors='replace')
                is_stable = True
        except Exception:
            pass

        if not current:
            try:
                r2 = subprocess.run(
                    ['git', 'describe', '--tags', '--abbrev=0', 'HEAD'],
                    cwd=self.COMFY_DIR, capture_output=True, timeout=5, creationflags=self._NO_WIN
                )
                if r2.returncode == 0:
                    current = r2.stdout.strip().decode(errors='replace') or None
            except Exception:
                pass

        local_tags = []
        try:
            r = subprocess.run(
                ['git', 'tag', '--sort=-version:refname'],
                cwd=self.COMFY_DIR, capture_output=True, timeout=5, creationflags=self._NO_WIN
            )
            local_tags = [t.strip() for t in r.stdout.decode(errors='replace').strip().splitlines() if t.strip()]
        except Exception:
            pass

        remote_tags = []
        for page in (1, 2):
            try:
                req = _ur.Request(
                    f'https://api.github.com/repos/Comfy-Org/ComfyUI/tags?per_page=100&page={page}',
                    headers={'User-Agent': 'ComfyUI-EZi'}
                )
                with _ur.urlopen(req, timeout=8) as resp:
                    data = _json.loads(resp.read())
                batch = [t['name'] for t in data if t.get('name')]
                remote_tags.extend(batch)
                if len(batch) < 100:
                    break
            except Exception:
                break

        all_tags = list({t for t in (local_tags + remote_tags) if re.match(r'^v?\d+\.\d+', t)})
        all_tags.sort(key=_ver_key, reverse=True)
        all_tags = all_tags[:20]
        if current and current not in all_tags:
            all_tags.insert(0, current)
            all_tags = all_tags[:20]
        if not current:
            all_tags.insert(0, 'NIGHTLY')
            current = 'NIGHTLY'

        stable_version = None
        try:
            req = _ur.Request(
                'https://api.github.com/repos/Comfy-Org/ComfyUI/releases/latest',
                headers={'User-Agent': 'ComfyUI-EZi'}
            )
            with _ur.urlopen(req, timeout=8) as resp:
                rel_data = _json.loads(resp.read())
            stable_version = rel_data.get('tag_name') or None
            if stable_version:
                try:
                    _cached_data = {}
                    if os.path.exists(SETTINGS_PATH):
                        with open(SETTINGS_PATH, 'r', encoding='utf-8') as _sf:
                            _cached_data = _json.loads(_sf.read())
                    _cached_data['cached_comfy_stable_version'] = stable_version
                    _tmp = SETTINGS_PATH + '.tmp'
                    with open(_tmp, 'w', encoding='utf-8') as _sf:
                        _json.dump(_cached_data, _sf, indent=2, ensure_ascii=False)
                    os.replace(_tmp, SETTINGS_PATH)
                except Exception:
                    pass
        except Exception:
            try:
                if os.path.exists(SETTINGS_PATH):
                    with open(SETTINGS_PATH, 'r', encoding='utf-8') as _sf:
                        _cached_data = _json.loads(_sf.read())
                    stable_version = _cached_data.get('cached_comfy_stable_version') or None
            except Exception:
                pass

        return {'current': current, 'versions': all_tags, 'stableVersion': stable_version, 'isStable': bool(is_stable)}

    def set_comfyui_version(self, tag):
        self._println("ComfyUI release tags can remove ROCm fork changes. Use the ROCm updater; frontend switching remains available.")
        return
        threading.Thread(target=self._do_set_comfyui_version, args=(tag,), daemon=True).start()

    def _do_set_comfyui_version(self, tag):
        self._safe_eval("switchToConsole('Switching...')")
        self._println(f"\033[93m=== Switching ComfyUI to {tag} ===\033[0m")
        self._kill_running_proc()
        try:
            self._println("\033[93mFetching tags...\033[0m")
            subprocess.run(['git', 'fetch', '--tags', '--quiet'],
                           cwd=self.COMFY_DIR, capture_output=True, timeout=30, creationflags=self._NO_WIN)
            r = subprocess.run(['git', 'checkout', f'tags/{tag}'],
                               cwd=self.COMFY_DIR, capture_output=True, timeout=15, creationflags=self._NO_WIN)
            out = (r.stdout + r.stderr).decode(errors='replace').strip()
            if out:
                self._println(out)
            if r.returncode == 0:
                self._println(f"\033[92m=== Switched to {tag}. Restarting ComfyUI... ===\033[0m")
                self._safe_eval("switchToConsole()")
                self._restart_comfy()
                self._updating = False
            else:
                self._println(f"\033[91m=== Checkout failed (exit {r.returncode}) ===\033[0m")
        except Exception as e:
            self._println(f"\033[91mError: {e}\033[0m")

    def set_comfyui_version_then_frontend(self, tag, fe_version):
        self._println("ComfyUI release tags can remove ROCm fork changes. Use the ROCm updater; frontend switching remains available.")
        return
        threading.Thread(target=self._do_set_comfyui_version_then_frontend, args=(tag, fe_version), daemon=True).start()

    def _do_set_comfyui_version_then_frontend(self, tag, fe_version):
        self._safe_eval("switchToConsole('Switching...')")
        self._println(f"\033[93m=== Switching ComfyUI to {tag} + frontend {fe_version} ===\033[0m")
        self._kill_running_proc()
        try:
            self._println("\033[93mFetching tags...\033[0m")
            subprocess.run(['git', 'fetch', '--tags', '--quiet'],
                           cwd=self.COMFY_DIR, capture_output=True, timeout=30, creationflags=self._NO_WIN)
            r = subprocess.run(['git', 'checkout', f'tags/{tag}'],
                               cwd=self.COMFY_DIR, capture_output=True, timeout=15, creationflags=self._NO_WIN)
            out = (r.stdout + r.stderr).decode(errors='replace').strip()
            if out:
                self._println(out)
            if r.returncode != 0:
                self._println(f"\033[91m=== Checkout failed (exit {r.returncode}) ===\033[0m")
                return
            self._println(f"\033[92m=== Switched to {tag} ===\033[0m")
            if not fe_version:
                req_path = os.path.join(self.COMFY_DIR, 'requirements.txt')
                try:
                    with open(req_path, 'r', encoding='utf-8') as _f:
                        for _line in _f:
                            _line = _line.strip()
                            if _line.lower().startswith('comfyui-frontend-package'):
                                import re as _re
                                _m = _re.search(r'==\s*([^\s]+)', _line)
                                if _m:
                                    fe_version = _m.group(1)
                                break
                except Exception:
                    pass
            if fe_version:
                if not self._pip_install_frontend(fe_version):
                    self._println(f"\033[91m=== Frontend install failed ===\033[0m")
                    return
                self._println(f"\033[92m=== Installed frontend {fe_version}. Restarting ComfyUI... ===\033[0m")
            else:
                self._println(f"\033[93m=== No matching frontend version found, skipping. Restarting ComfyUI... ===\033[0m")
            self._safe_eval("switchToConsole()")
            self._restart_comfy()
            self._updating = False
        except Exception as e:
            self._println(f"\033[91mError: {e}\033[0m")

    def _pip_install_frontend(self, version):
        self._println(f"\033[93m=== Installing comfyui-frontend-package=={version} ===\033[0m")
        return self._stream_cmd(
            [self.PY_EXE, '-m', 'pip', 'install', f'comfyui-frontend-package=={version}',
             '--no-warn-script-location'],
            cwd=ROOT_DIR, use_pty=True) == 0

    def set_frontend_version(self, version):
        threading.Thread(target=self._do_set_frontend_version, args=(version,), daemon=True).start()

    def _do_set_frontend_version(self, version):
        self._safe_eval("switchToConsole('Installing...')")
        try:
            if self._pip_install_frontend(version):
                self._println(f"\033[92m=== Installed. Restarting ComfyUI... ===\033[0m")
                self._kill_running_proc()
                time.sleep(1)
                self._safe_eval("switchToConsole()")
                self._restart_comfy()
                self._updating = False
            else:
                self._println(f"\033[91m=== Installation failed ===\033[0m")
        except Exception as e:
            self._println(f"\033[91mError: {e}\033[0m")

    def run_bat(self, rel_path):
        if self._updating:
            return
        rel_clean = rel_path.lstrip('./\\').replace('\\\\', '\\')
        bat = os.path.normpath(os.path.join(ROOT_DIR, rel_clean))
        if not os.path.exists(bat):
            self._safe_eval(f"show_update_missing({json.dumps(os.path.dirname(bat))})")
            return
        if os.path.basename(bat) == 'Easy-Models-Linker.bat':
            self._updating = True
            threading.Thread(target=self._do_models_linker, daemon=True).start()
            return
        if os.path.basename(bat) == 'Easy-model2GGUF.bat':
            self._kill_running_proc()
            subprocess.Popen(['cmd.exe', '/c', bat], cwd=ROOT_DIR, creationflags=subprocess.CREATE_NEW_CONSOLE)
            return
        if os.path.basename(bat) in ('ROCm Bundle Manager.bat', 'Latest AMD Nightly.bat'):
            command = ['cmd.exe', '/c', os.path.join(ROOT_DIR, 'amd', 'bundle-menu.bat')]
            if os.path.basename(bat) == 'Latest AMD Nightly.bat':
                command.append('--latest')
            subprocess.Popen(command, cwd=ROOT_DIR, creationflags=subprocess.CREATE_NEW_CONSOLE)
            self._println('Bundle manager opened. ComfyUI remains running while you choose or prepare a bundle. Close EZi Desktop only when prompted to activate it.')
            return
        threading.Thread(target=self._do_run_bat, args=(bat,), daemon=True).start()

    def _do_models_linker(self):
        try:
            result = subprocess.run(
                [os.path.join(ROOT_DIR, 'python_embeded', 'python.exe'),
                 os.path.join(ROOT_DIR, 'amd', 'windows_tools.py'), 'models'],
                cwd=ROOT_DIR, creationflags=subprocess.CREATE_NEW_CONSOLE)
            if result.returncode == 2:
                self._println('Model folder selection cancelled.')
                return
            if result.returncode != 0:
                self._println('Model linking failed. ComfyUI is still running; see the linker error.')
                return
            self._println('Model paths saved. Restarting ComfyUI to load the linked folders...')
            self._safe_eval("switchToConsole('Loading linked models...')")
            self._kill_running_proc()
            self._restart_comfy(check_update=False)
        except Exception as e:
            self._println(f'Error linking models: {e}')
        finally:
            self._updating = False

    def _do_run_bat(self, bat, status_label=None, hide_update_notice=False):
        name = os.path.basename(bat)
        label = status_label or f'Running {name}...'
        self._updating = True
        self._safe_eval(f"switchToConsole({json.dumps(label)})")
        self._safe_eval("document.getElementById('update-notice').style.display='none';")
        self._println(f"\033[93m=== Stopping ComfyUI ===\033[0m")
        self._kill_running_proc()
        self._println(f"\033[93m=== Running {name} ===\033[0m")
        result = 1
        try:
            result = self._stream_cmd(
                ['cmd', '/c', 'chcp', '65001', '>', 'nul', '&&', bat, 'NoPause', '<', 'nul'],
                cwd=os.path.dirname(bat), use_pty=True, stdin_devnull=True)
        except Exception as e:
            self._println(f"\033[91mError running {name}: {e}\033[0m")
        
        if result:
            self._println(f"\033[91m=== {name} failed (exit {result}). See the error above and rerun after fixing it. ===\033[0m")
        else:
            self._println(f"\033[92m=== {name} completed successfully. ===\033[0m")
        
        if hide_update_notice:
            self._safe_eval("document.getElementById('update-notice').style.display='none';")

        is_wtivo_group = name.lower() in ('boomercyb wtivo amd nodes.bat','mostaadtech wtivo nodes.bat')
        if is_wtivo_group and result:
            self._println('ComfyUI remains stopped. Rerun the node add-on after resolving the error; restart follows a successful complete installation.')
            self._safe_eval("switchToConsole('Node installation failed — ComfyUI stopped')")
            self._updating = False
            return

        is_ezi_update = name.lower() == "update easy-install.bat"

        if is_ezi_update:
            self._println(f"\033[92mRestarting ComfyUI-EZi...\033[0m")
            time.sleep(1)
            self.restart_ezi()
        else:
            self._println(f"\033[92mRestarting ComfyUI...\033[0m")
            time.sleep(1)
            self._safe_eval("switchToConsole()")
            self._restart_comfy(check_update=not is_wtivo_group)
            self._updating = False

    def open_output_folder(self):
        path = self._resolve_output_dir()
        if not path:
            return
        try:
            custom_browser = self._settings.get("custom_file_browser", "").strip()
            if custom_browser and os.path.isfile(custom_browser):
                subprocess.Popen([custom_browser, path])
            else:
                subprocess.Popen(['explorer', path])
        except Exception as e:
            self._println(f"[Output] Could not open folder: {e}\n")

    def _open_folder_path(self, path):
        if not path or not os.path.isdir(path):
            return False
        try:
            custom_browser = self._settings.get("custom_file_browser", "").strip()
            if custom_browser and os.path.isfile(custom_browser):
                subprocess.Popen([custom_browser, path])
            else:
                subprocess.Popen(['explorer', path])
            return True
        except Exception as e:
            self._println(f"[Folder] Could not open folder: {e}\n")
            return False

    def _resolve_input_dir(self):
        try:
            if os.path.exists(BAT_FILE):
                with open(BAT_FILE, 'r', encoding='utf-8', errors='replace') as f:
                    bat_content = f.read()
                m_env = re.search(r'(?i)set\s+"?COMFY_INPUT_DIR=([^"\n]+)"?', bat_content)
                if m_env:
                    d = m_env.group(1).strip().strip('"')
                    if not os.path.isabs(d):
                        d = os.path.normpath(os.path.join(ROOT_DIR, d))
                    return d if os.path.isdir(d) else None
                comfy_line = _find_bat_comfy_line(bat_content)
                if comfy_line:
                    m = re.search(r'python_embeded[/\\]python\.exe["\']?\s+(.*)',
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

    def _resolve_workflows_dir(self):
        user_dir = _get_comfy_user_dir()
        d = os.path.join(user_dir, 'workflows')
        return d if os.path.isdir(d) else None

    def _resolve_models_dir(self):
        yaml_path = os.path.normpath(os.path.join(ROOT_DIR, 'ComfyUI', 'extra_model_paths.yaml'))
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
                            parent = os.path.normpath(os.path.join(base_path, first_component))

                        if os.path.isdir(parent):
                            parent_votes[parent] = parent_votes.get(parent, 0) + 1

                    if parent_votes:
                        best = max(parent_votes, key=lambda p: parent_votes[p])
                        return best

            except Exception:
                pass
        d = os.path.normpath(os.path.join(ROOT_DIR, 'ComfyUI', 'models'))
        return d if os.path.isdir(d) else None

    def open_sub_folder(self, folder_type):
        if folder_type == 'input':
            path = self._resolve_input_dir()
        elif folder_type == 'workflows':
            path = self._resolve_workflows_dir()
        elif folder_type == 'models':
            path = self._resolve_models_dir()
        else:
            return
        if not self._open_folder_path(path):
            self._println(f"[Folder] '{folder_type}' folder not found.\n")

    def browse_for_exe(self):
        try:
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=('Executable files (*.exe)', 'All files (*.*)')
            )
            if result and result[0]:
                return result[0]
        except Exception:
            pass
        return None

    def browse_for_folder(self):
        try:
            result = self._window.create_file_dialog(
                webview.FOLDER_DIALOG,
                allow_multiple=False
            )
            if result and result[0]:
                return result[0]
        except Exception:
            pass
        return None

    def browse_for_image(self):
        try:
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=('Image files (*.png;*.jpg;*.jpeg;*.webp;*.svg)', 'All files (*.*)')
            )
            if result and result[0]:
                return result[0]
        except Exception:
            pass
        return None

    def apply_console_bg(self):
        custom_bg  = self._settings.get("console_bg_image", "").strip()
        bg_fit     = self._settings.get("console_bg_fit", "fit")
        opacity    = float(self._settings.get("console_bg_opacity", 0.12))

        _ico_css, ico_w, ico_h = _load_ico_as_base64()

        if custom_bg and os.path.isfile(custom_bg):
            ext  = os.path.splitext(custom_bg)[1].lower().lstrip(".")
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "webp": "image/webp", "svg": "image/svg+xml"}.get(ext, "image/png")
            try:
                with open(custom_bg, "rb") as _f:
                    b64 = base64.b64encode(_f.read()).decode()
                css_url = f'url("data:{mime};base64,{b64}")'
            except Exception:
                css_url = ""
            fit_map = {
                "fit":     ("contain",   "no-repeat"),
                "stretch": ("100% 100%", "no-repeat"),
                "tile":    ("auto",      "repeat"),
                "center":  ("auto",      "no-repeat"),
            }
            bg_size, bg_repeat = fit_map.get(bg_fit, ("contain", "no-repeat"))
            js = f"""
(function(){{
    var el = document.getElementById('ico-bg');
    if (!el) return;
    el.style.backgroundImage    = {json.dumps(css_url)};
    el.style.backgroundSize     = {json.dumps(bg_size)};
    el.style.backgroundRepeat   = {json.dumps(bg_repeat)};
    el.style.backgroundPosition = 'center';
    el.style.opacity   = {opacity};
    el.style.inset     = '0';
    el.style.width     = 'auto';
    el.style.height    = 'auto';
    el.style.transform = 'none';
}})();
"""
        else:
            css_url = _ico_css
            bg_size = f"{ico_w}px {ico_h}px" if _ico_css else "256px 256px"

            js = (
                "(function(){{"
                "var el = document.getElementById('ico-bg');"
                "if (!el) return;"
                f"el.style.backgroundImage    = {json.dumps(css_url)};"
                f"el.style.backgroundSize     = {json.dumps(bg_size)};"
                "el.style.backgroundRepeat   = 'no-repeat';"
                "el.style.backgroundPosition = 'center';"
                f"el.style.opacity            = '{opacity}';"
                "el.style.inset              = 'unset';"
                f"el.style.width              = '{ico_w}px';"
                f"el.style.height             = '{ico_h}px';"
                "el.style.top                = '50%';"
                "el.style.left               = '50%';"
                "el.style.transform          = 'translate(-50%, -50%)';"
                "}})()"
            )
        self._safe_eval(js)
        win = self._console_win
        if win is not None:
            try:
                win.evaluate_js(js)
            except Exception:
                pass


    def get_startup_args(self):
        try:
            if not os.path.exists(BAT_FILE):
                return ""
            with open(BAT_FILE, 'r', encoding='utf-8', errors='replace') as f:
                bat_content = f.read()
            comfy_line = _find_bat_comfy_line(bat_content)
            if not comfy_line:
                return ""
            m = re.search(r'python_embeded[/\\]python\.exe["\'"]?\s+(.*)',
                          comfy_line, re.IGNORECASE)
            if not m:
                return ""
            tokens = shlex.split(m.group(1).strip(), posix=False)
            
            MANAGED_WITH_VAL = {
                '--input-directory', '--output-directory', '--user-directory',
            }
            MANAGED_FLAG = {'--windows-standalone-build'}
            _req_attn = _required_attn_flag(BAT_FILE)
            if _req_attn:
                MANAGED_FLAG = MANAGED_FLAG | {_req_attn}
            
            script_idx = None
            for idx, tok in enumerate(tokens):
                if re.search(r'(?:main|runtime)\.py', tok, re.IGNORECASE):
                    script_idx = idx
                    break
            if script_idx is None:
                return ""
            post = tokens[script_idx + 1:]
            extra = []
            i = 0
            while i < len(post):
                tok = post[i]
                if tok in MANAGED_WITH_VAL:
                    i += 2
                elif tok in MANAGED_FLAG:
                    i += 1
                else:
                    extra.append(tok)
                    i += 1
            return ' '.join(extra)
        except Exception:
            return ""

    def set_startup_args(self, args_str):
        bat_names = [
            'Start ComfyUI.bat',
            'Start ComfyUI SageAttention.bat',
            'Start ComfyUI FlashAttention.bat',
            'Start ComfyUI KitchenAttention.bat',
        ]
        args_str = (args_str or '').strip()

        MANAGED_WITH_VAL = {
            '--input-directory', '--output-directory', '--user-directory',
        }
        MANAGED_FLAG = {'--windows-standalone-build'}

        for bat_name in bat_names:
            bat_path = os.path.join(ROOT_DIR, bat_name)
            if not os.path.exists(bat_path):
                continue
            try:
                with open(bat_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                lines = content.splitlines(keepends=True)
                start_idx = end_idx = None
                logical_line = None
                i = 0
                while i < len(lines):
                    stripped = lines[i].rstrip('\r\n')
                    accumulated = stripped
                    j = i
                    while accumulated.rstrip().endswith('^') and j + 1 < len(lines):
                        accumulated = accumulated.rstrip()[:-1] + ' ' + lines[j + 1].lstrip().rstrip('\r\n')
                        j += 1
                    acc_s = accumulated.strip()
                    if (acc_s and
                            not acc_s.startswith('::') and
                            not re.match(r'(?i)^rem(\s|$)', acc_s) and
                            re.search(r'python_embeded[/\\]python\.exe', acc_s, re.IGNORECASE) and
                            re.search(r'(?:ComfyUI[/\\]main|amd[/\\]runtime)\.py', acc_s, re.IGNORECASE)):
                        start_idx = i
                        end_idx = j
                        logical_line = acc_s
                        break
                    i += 1
                if logical_line is None or start_idx is None:
                    continue
                m = re.search(r'(.*python_embeded[/\\]python\.exe["\'"]?)\s+(.*)',
                              logical_line, re.IGNORECASE | re.DOTALL)
                if not m:
                    continue
                py_prefix = m.group(1)
                rest = m.group(2).strip()
                tokens = shlex.split(rest, posix=False)
                script_idx = None
                for idx2, tok in enumerate(tokens):
                    if re.search(r'(?:main|runtime)\.py', tok, re.IGNORECASE):
                        script_idx = idx2
                        break
                if script_idx is None:
                    continue
                pre_script = tokens[:script_idx + 1]
                post_script = tokens[script_idx + 1:]
                _req_attn = _required_attn_flag(bat_path)
                _mflag = (MANAGED_FLAG | {_req_attn}) if _req_attn else MANAGED_FLAG
                kept_managed = []
                k = 0
                while k < len(post_script):
                    tok = post_script[k]
                    if tok in MANAGED_WITH_VAL:
                        kept_managed.append(tok)
                        if k + 1 < len(post_script):
                            kept_managed.append(post_script[k + 1])
                            k += 2
                        else:
                            k += 1
                    elif tok in _mflag:
                        kept_managed.append(tok)
                        k += 1
                    else:
                        k += 1
                
                if '--windows-standalone-build' not in kept_managed:
                    kept_managed.append('--windows-standalone-build')
                if _req_attn and _req_attn not in kept_managed:
                    kept_managed.append(_req_attn)

                new_extra = shlex.split(args_str, posix=False) if args_str else []
                _parsed = []
                _i2 = 0
                while _i2 < len(new_extra):
                    _tok = new_extra[_i2]
                    if _tok.startswith('-'):
                        if _i2 + 1 < len(new_extra) and not new_extra[_i2 + 1].startswith('-'):
                            _parsed.append((_tok, new_extra[_i2 + 1]))
                            _i2 += 2
                        else:
                            _parsed.append((_tok, None))
                            _i2 += 1
                    else:
                        _parsed.append((None, _tok))
                        _i2 += 1
                _managed_all = MANAGED_WITH_VAL | _mflag
                if _req_attn:
                    _managed_all = _managed_all | set(_ATTN_BAT_FLAGS.values())
                _seen_flags = set()
                _deduped = []
                for _flag, _val in reversed(_parsed):
                    if _flag is None:
                        _deduped.insert(0, (None, _val))
                        continue
                    if _flag in _managed_all:
                        continue
                    if _flag not in _seen_flags:
                        _seen_flags.add(_flag)
                        _deduped.insert(0, (_flag, _val))
                filtered_extra = []
                for _flag, _val in _deduped:
                    if _flag is not None:
                        filtered_extra.append(_flag)
                    if _val is not None:
                        filtered_extra.append(_val)
                rebuilt = kept_managed + filtered_extra
                new_cmd_parts = [py_prefix] + pre_script + rebuilt
                new_line = ' '.join(new_cmd_parts)
                orig_ending = '\r\n' if '\r\n' in lines[start_idx] else '\n'
                new_lines = (
                    lines[:start_idx] +
                    [new_line + orig_ending] +
                    lines[end_idx + 1:]
                )
                with open(bat_path, 'w', encoding='utf-8', newline='') as f:
                    f.write(''.join(new_lines))
            except Exception as e:
                self._println(f"[StartupArgs] Error updating {bat_name}: {e}\n")

        self._println("\n[StartupArgs] Restarting ComfyUI-EZi to apply new startup arguments...\n")
        
        self.restart_ezi()

    def get_custom_paths(self):
        paths = {'input': '', 'output': '', 'user': ''}
        try:
            if not os.path.exists(BAT_FILE):
                return json.dumps(paths)
            with open(BAT_FILE, 'r', encoding='utf-8', errors='replace') as f:
                bat_content = f.read()
            comfy_line = _find_bat_comfy_line(bat_content)
            if not comfy_line:
                return json.dumps(paths)
            m = re.search(r'python_embeded[/\\]python\.exe["\']?\s+(.*)',
                          comfy_line, re.IGNORECASE)
            if not m:
                return json.dumps(paths)
            tokens = shlex.split(m.group(1).strip(), posix=False)
            param_map = {
                '--input-directory':  'input',
                '--output-directory': 'output',
                '--user-directory':   'user',
            }
            i = 0
            while i < len(tokens):
                tok = tokens[i]
                if tok in param_map and i + 1 < len(tokens):
                    paths[param_map[tok]] = tokens[i + 1].strip('"\'')
                    i += 2
                else:
                    i += 1
        except Exception:
            pass
        return json.dumps(paths)

    def set_custom_paths(self, input_dir, output_dir, user_dir):
        bat_names = [
            'Start ComfyUI.bat',
            'Start ComfyUI SageAttention.bat',
            'Start ComfyUI FlashAttention.bat',
            'Start ComfyUI KitchenAttention.bat',
        ]
        new_vals = {
            '--input-directory':  input_dir.strip().strip('"'),
            '--output-directory': output_dir.strip().strip('"'),
            '--user-directory':   user_dir.strip().strip('"'),
        }

        for bat_name in bat_names:
            bat_path = os.path.join(ROOT_DIR, bat_name)
            if not os.path.exists(bat_path):
                continue
            try:
                with open(bat_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()

                lines = content.splitlines(keepends=True)

                i = 0
                start_idx = None
                end_idx = None
                logical_line = None

                while i < len(lines):
                    stripped = lines[i].rstrip('\r\n')
                    accumulated = stripped
                    j = i
                    while accumulated.rstrip().endswith('^') and j + 1 < len(lines):
                        accumulated = accumulated.rstrip()[:-1] + ' ' + lines[j + 1].lstrip().rstrip('\r\n')
                        j += 1

                    acc_s = accumulated.strip()
                    if (acc_s and
                            not acc_s.startswith('::') and
                            not re.match(r'(?i)^rem(\s|$)', acc_s) and
                            re.search(r'python_embeded[/\\]python\.exe', acc_s, re.IGNORECASE) and
                            re.search(r'(?:ComfyUI[/\\]main|amd[/\\]runtime)\.py', acc_s, re.IGNORECASE)):
                        start_idx = i
                        end_idx = j
                        logical_line = acc_s
                        break
                    i += 1

                if logical_line is None or start_idx is None:
                    continue

                m = re.search(r'(.*python_embeded[/\\]python\.exe["\']?)\s+(.*)',
                              logical_line, re.IGNORECASE | re.DOTALL)
                if not m:
                    continue
                py_prefix = m.group(1)
                rest = m.group(2).strip()

                tokens = shlex.split(rest, posix=False)

                script_idx = None
                for idx, tok in enumerate(tokens):
                    if re.search(r'(?:main|runtime)\.py', tok, re.IGNORECASE):
                        script_idx = idx
                        break

                if script_idx is None:
                    continue

                pre_script = tokens[:script_idx + 1]
                post_script = tokens[script_idx + 1:]

                SINGLE_VAL_PARAMS = {
                    '--input-directory', '--output-directory', '--user-directory',
                    '--port', '--tls-keyfile', '--tls-certfile', '--max-upload-size',
                    '--base-directory', '--temp-directory', '--cuda-device',
                    '--default-device', '--oneapi-device-selector', '--preview-size',
                    '--cache-lru', '--reserve-vram', '--vram-headroom',
                    '--default-hashing-function',
                    '--front-end-version', '--front-end-root', '--comfy-api-base',
                    '--database-url', '--models-directory', '--feature-flag',
                }
                rebuilt = []
                k = 0
                while k < len(post_script):
                    tok = post_script[k]
                    if tok in new_vals:
                        k += 2 if (k + 1 < len(post_script)) else 1
                    elif tok in SINGLE_VAL_PARAMS:
                        rebuilt.append(tok)
                        if k + 1 < len(post_script):
                            rebuilt.append(post_script[k + 1])
                            k += 2
                        else:
                            k += 1
                    else:
                        rebuilt.append(tok)
                        k += 1

                for param, val in new_vals.items():
                    if val:
                        rebuilt.extend([param, f'"{val}"'])

                new_cmd_parts = [py_prefix] + pre_script + rebuilt
                new_line = ' '.join(new_cmd_parts)

                orig_ending = '\r\n' if '\r\n' in lines[start_idx] else '\n'

                new_lines = (
                    lines[:start_idx] +
                    [new_line + orig_ending] +
                    lines[end_idx + 1:]
                )

                with open(bat_path, 'w', encoding='utf-8', newline='') as f:
                    f.write(''.join(new_lines))

            except Exception as e:
                self._println(f"[CustomPaths] Error updating {bat_name}: {e}\n")

        self._println("\n[CustomPaths] Restarting ComfyUI to apply new folder settings...\n")
        self._safe_eval("switchToConsole('Restarting...')")
        self._kill_running_proc()
        self._restart_comfy(check_update=False)

    def manager_config_exists(self):
        return os.path.exists(_get_manager_config_path())

    def get_security_level(self):
        try:
            config_path = _get_manager_config_path()
            if not os.path.exists(config_path):
                return 'weak'
            import configparser
            cfg = configparser.ConfigParser()
            cfg.read(config_path, encoding='utf-8')
            level = cfg.get('default', 'security_level', fallback='weak').strip()
            if level not in ('weak', 'normal-', 'normal', 'strong'):
                level = 'weak'
            return level
        except Exception:
            return 'weak'

    def set_security_level(self, level):
        if level not in ('weak', 'normal-', 'normal', 'strong'):
            return False
        try:
            config_path = _get_manager_config_path()
            if not os.path.exists(config_path):
                return False
            import configparser
            cfg = configparser.ConfigParser()
            cfg.read(config_path, encoding='utf-8')
            if not cfg.has_section('default'):
                cfg.add_section('default')
            cfg.set('default', 'security_level', level)
            tmp = config_path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                cfg.write(f)
            os.replace(tmp, config_path)
            self._println(f"\n[Manager] Security level set to '{level}'. Restarting ComfyUI...\n")
            self._safe_eval("switchToConsole('Restarting...')")
            self._kill_running_proc()
            self._restart_comfy(check_update=False)
            return True
        except Exception:
            return False

    def get_pinned_packages(self):
        try:
            if os.path.exists(SETTINGS_PATH):
                with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return json.dumps(data.get('pinned_packages') or [])
        except Exception:
            pass
        return json.dumps([])

    def set_pinned_packages(self, packages_json):
        try:
            packages = json.loads(packages_json)
            if not isinstance(packages, list):
                return False
            existing = {}
            try:
                if os.path.exists(SETTINGS_PATH):
                    with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
            except Exception:
                pass
            existing['pinned_packages'] = packages
            tmp = SETTINGS_PATH + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            os.replace(tmp, SETTINGS_PATH)
            if isinstance(self._settings, dict):
                self._settings['pinned_packages'] = packages
            return True
        except Exception:
            return False

    def check_pinned_packages(self, packages_json=None):
        try:
            packages = None
            if packages_json:
                try:
                    _p = json.loads(packages_json)
                    if isinstance(_p, list):
                        packages = [str(x) for x in _p]
                except Exception:
                    packages = None
            if packages is None:
                if os.path.exists(SETTINGS_PATH):
                    with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    packages = data.get('pinned_packages') or []
                else:
                    packages = []
            results = []
            for entry in packages:
                entry = entry.strip()
                if not entry:
                    continue
                if '==' in entry:
                    pkg, ver = entry.split('==', 1)
                    pkg = pkg.strip()
                    ver = ver.strip()
                else:
                    results.append({'pkg': entry, 'status': 'unknown'})
                    continue
                try:
                    r = subprocess.run(
                        [self.PY_EXE, '-c',
                         f'import importlib.metadata as _im; print(_im.version({pkg!r}))'],
                        capture_output=True, timeout=8,
                        creationflags=self._NO_WIN
                    )
                    if r.returncode == 0:
                        installed = r.stdout.decode(errors='replace').strip()
                        status = 'ok' if installed == ver else 'mismatch'
                        results.append({'pkg': entry, 'status': status, 'installed': installed})
                    else:
                        results.append({'pkg': entry, 'status': 'missing'})
                except Exception:
                    results.append({'pkg': entry, 'status': 'unknown'})
            return json.dumps(results)
        except Exception:
            return json.dumps([])

    def open_url(self, url):
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass

    def screenshot(self, x, y, w, h):
        threading.Thread(target=self._do_screenshot, args=(x, y, w, h), daemon=True).start()

    def start_recording(self, x, y, w, h, fps=15):
        threading.Thread(target=self._do_start_recording, args=(x, y, w, h, int(fps)), daemon=True).start()

    def stop_recording(self):
        if hasattr(self, '_rec_stop_event') and self._rec_stop_event:
            self._rec_stop_event.set()

    def _capture_frame_gdi(self, hwnd, x, y, w, h):
        ctx = self._make_gdi_capture_ctx(hwnd, x, y, w, h)
        if ctx is None:
            return None
        try:
            return ctx.capture()
        finally:
            ctx.release()

    def _make_gdi_capture_ctx(self, hwnd, x, y, w, h):
        import ctypes, ctypes.wintypes as wt
        gdi  = ctypes.windll.gdi32
        user = ctypes.windll.user32
        _vp  = ctypes.c_void_p

        gdi.CreateCompatibleDC.restype       = _vp
        gdi.CreateCompatibleDC.argtypes      = [_vp]
        gdi.CreateCompatibleBitmap.restype   = _vp
        gdi.CreateCompatibleBitmap.argtypes  = [_vp, ctypes.c_int, ctypes.c_int]
        gdi.SelectObject.restype             = _vp
        gdi.SelectObject.argtypes            = [_vp, _vp]
        gdi.DeleteObject.restype             = wt.BOOL
        gdi.DeleteObject.argtypes            = [_vp]
        gdi.DeleteDC.restype                 = wt.BOOL
        gdi.DeleteDC.argtypes                = [_vp]
        gdi.BitBlt.restype                   = wt.BOOL
        gdi.BitBlt.argtypes                  = [_vp, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                               ctypes.c_int, _vp, ctypes.c_int, ctypes.c_int, wt.DWORD]
        gdi.GetDIBits.restype                = ctypes.c_int
        gdi.GetDIBits.argtypes               = [_vp, _vp, wt.UINT, wt.UINT,
                                               ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
        user.GetDC.restype                   = _vp
        user.GetDC.argtypes                  = [_vp]
        user.ReleaseDC.restype               = ctypes.c_int
        user.ReleaseDC.argtypes              = [_vp, _vp]
        user.DrawIconEx.restype              = wt.BOOL
        user.DrawIconEx.argtypes             = [_vp, ctypes.c_int, ctypes.c_int, _vp,
                                               ctypes.c_int, ctypes.c_int, wt.UINT, _vp, wt.UINT]
        user.ClientToScreen.restype          = wt.BOOL
        user.ClientToScreen.argtypes         = [_vp, ctypes.c_void_p]
        user.GetCursorInfo.restype           = wt.BOOL
        user.GetIconInfo.restype             = wt.BOOL
        user.SetThreadDpiAwarenessContext.argtypes = [_vp]
        user.SetThreadDpiAwarenessContext.restype  = _vp
        user.GetDpiForWindow.argtypes        = [_vp]
        user.GetDpiForWindow.restype         = wt.UINT

        try:
            prev_ctx = None
            try:
                prev_ctx = user.SetThreadDpiAwarenessContext(_vp(-4))
            except Exception:
                pass

            dpr = 1.0
            try:
                dpi = user.GetDpiForWindow(_vp(hwnd))
                if dpi: dpr = dpi / 96.0
            except Exception:
                pass

            phys_x = max(0, int(round(x * dpr)))
            phys_y = max(0, int(round(y * dpr)))
            cap_w  = max(2, int(round(w * dpr)))
            cap_h  = max(2, int(round(h * dpr)))
            cap_w  = cap_w if cap_w % 2 == 0 else cap_w - 1
            cap_h  = cap_h if cap_h % 2 == 0 else cap_h - 1

            pt = wt.POINT(0, 0)
            user.ClientToScreen(_vp(hwnd), ctypes.byref(pt))
            src_x = pt.x + phys_x
            src_y = pt.y + phys_y

            hdc_screen = user.GetDC(None)
            hdc_mem    = gdi.CreateCompatibleDC(hdc_screen)
            hbm        = gdi.CreateCompatibleBitmap(hdc_screen, cap_w, cap_h)
            old_bm     = gdi.SelectObject(hdc_mem, hbm)

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [("biSize",wt.DWORD),("biWidth",wt.LONG),("biHeight",wt.LONG),
                            ("biPlanes",wt.WORD),("biBitCount",wt.WORD),("biCompression",wt.DWORD),
                            ("biSizeImage",wt.DWORD),("biXPelsPerMeter",wt.LONG),
                            ("biYPelsPerMeter",wt.LONG),("biClrUsed",wt.DWORD),("biClrImportant",wt.DWORD)]
            bih = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER),
                                   biWidth=cap_w, biHeight=-cap_h, biPlanes=1, biBitCount=32,
                                   biCompression=0)

            buf = (ctypes.c_char * (cap_w * cap_h * 4))()

            class CURSORINFO(ctypes.Structure):
                _fields_ = [("cbSize",wt.DWORD),("flags",wt.DWORD),
                            ("hCursor",_vp),("ptScreenPos",wt.POINT)]
            class ICONINFO(ctypes.Structure):
                _fields_ = [("fIcon",wt.BOOL),("xHotspot",wt.DWORD),("yHotspot",wt.DWORD),
                            ("hbmMask",_vp),("hbmColor",_vp)]
            ci = CURSORINFO()
            ci.cbSize = ctypes.sizeof(CURSORINFO)
            ii = ICONINFO()

            if prev_ctx is not None:
                try: user.SetThreadDpiAwarenessContext(prev_ctx)
                except Exception: pass

            class _Ctx:
                __slots__ = ('_gdi','_user','_vp','_hdc_screen','_hdc_mem','_hbm','_old_bm',
                             '_bih','_buf','_ci','_ii','cap_w','cap_h','src_x','src_y','size',
                             '_last_hcursor','_hotspot_x','_hotspot_y')
                def __init__(self_):
                    self_._gdi = gdi; self_._user = user; self_._vp = _vp
                    self_._hdc_screen = hdc_screen; self_._hdc_mem = hdc_mem
                    self_._hbm = hbm; self_._old_bm = old_bm
                    self_._bih = bih; self_._buf = buf
                    self_._ci = ci; self_._ii = ii
                    self_.cap_w = cap_w; self_.cap_h = cap_h
                    self_.src_x = src_x; self_.src_y = src_y
                    self_.size = (cap_w, cap_h)
                    self_._last_hcursor = None
                    self_._hotspot_x = 0
                    self_._hotspot_y = 0

                def capture(self_):
                    g = self_._gdi; u = self_._user; vp = self_._vp

                    self_._ci.cbSize = ctypes.sizeof(CURSORINFO)
                    cursor_visible = u.GetCursorInfo(ctypes.byref(self_._ci)) and self_._ci.flags == 1
                    cur_x = self_._ci.ptScreenPos.x - self_.src_x if cursor_visible else 0
                    cur_y = self_._ci.ptScreenPos.y - self_.src_y if cursor_visible else 0
                    h_cursor = vp(self_._ci.hCursor) if cursor_visible else None

                    g.BitBlt(self_._hdc_mem, 0, 0, self_.cap_w, self_.cap_h,
                             self_._hdc_screen, self_.src_x, self_.src_y, 0x00CC0020)

                    if cursor_visible and h_cursor:
                        if h_cursor != self_._last_hcursor:
                            if u.GetIconInfo(h_cursor, ctypes.byref(self_._ii)):
                                self_._hotspot_x = int(self_._ii.xHotspot)
                                self_._hotspot_y = int(self_._ii.yHotspot)
                                if self_._ii.hbmColor: g.DeleteObject(vp(self_._ii.hbmColor))
                                if self_._ii.hbmMask:  g.DeleteObject(vp(self_._ii.hbmMask))
                            self_._last_hcursor = h_cursor
                        try:
                            u.DrawIconEx(self_._hdc_mem,
                                         cur_x - self_._hotspot_x,
                                         cur_y - self_._hotspot_y,
                                         h_cursor, 0, 0, 0, None, 0x0003)
                        except Exception:
                            pass

                    g.GetDIBits(self_._hdc_mem, self_._hbm, 0, self_.cap_h,
                                self_._buf, ctypes.byref(self_._bih), 0)
                    return bytes(self_._buf)

                def release(self_):
                    try:
                        self_._gdi.SelectObject(self_._hdc_mem, self_._old_bm)
                        self_._gdi.DeleteObject(self_._hbm)
                        self_._gdi.DeleteDC(self_._hdc_mem)
                        self_._user.ReleaseDC(None, self_._hdc_screen)
                    except Exception:
                        pass

            return _Ctx()

        except Exception as e:
            self._println(f"[Record] GDI context error: {e}")
            return None

    def _do_start_recording(self, x, y, w, h, fps=15):
        import ctypes, ctypes.wintypes as wt
        FPS = max(1, min(60, int(fps)))
        self._rec_stop_event = threading.Event()

        try:
            from PIL import Image
        except ImportError:
            self._println("[Record] Error: Pillow is not installed.")
            self._safe_eval("stopRecording()")
            return

        hwnd = None
        for _attempt in range(10):
            hwnd = _get_hwnd(self._window) if self._window else None
            if hwnd:
                break
            time.sleep(0.3)
        if not hwnd:
            self._println("[Record] Error: could not find application window handle.")
            self._safe_eval("stopRecording()")
            return

        cap_ctx = self._make_gdi_capture_ctx(hwnd, x, y, w, h)
        if cap_ctx is None:
            self._println("[Record] Failed to create capture context.")
            self._safe_eval("stopRecording()")
            return

        fw, fh = cap_ctx.cap_w, cap_ctx.cap_h

        if fw < 16 or fh < 16:
            self._println(f"[Record] Region too small ({fw}x{fh}). Minimum is 16x16 pixels.")
            cap_ctx.release()
            self._safe_eval("stopRecording()")
            return

        self._safe_eval(f"showRecIndicator({x},{y},{w},{h})")

        try:
            _rc = wt.RECT()
            ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(_rc))
            _client_w = _rc.right - _rc.left
            _client_h = _rc.bottom - _rc.top
            _origin = wt.POINT(0, 0)
            ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(_origin))
            _phys_x = cap_ctx.src_x - _origin.x
            _phys_y = cap_ctx.src_y - _origin.y
        except Exception:
            _client_w = _client_h = 0
            _phys_x = _phys_y = 0
        _is_full_area = (_phys_x <= 8 and _phys_y <= 8 and _client_w and _client_h
                          and cap_ctx.cap_w >= _client_w - 8
                          and cap_ctx.cap_h >= _client_h - 24)
        if not _is_full_area:
            self._show_rec_overlay(cap_ctx)

        import shutil, subprocess as sp
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            for candidate in [
                os.path.join(ROOT_DIR, 'ffmpeg.exe'),
                os.path.join(ROOT_DIR, 'ffmpeg', 'ffmpeg.exe'),
                os.path.join(ROOT_DIR, 'ffmpeg', 'bin', 'ffmpeg.exe'),
                r'C:\ffmpeg\bin\ffmpeg.exe',
                r'C:\ffmpeg\ffmpeg.exe',
            ]:
                if os.path.isfile(candidate):
                    ffmpeg = candidate
                    break

        tmp_file = os.path.join(self._last_save_dir, f'_ezi_rec_tmp_{int(time.time())}.mp4')

        try:
          if ffmpeg:
            cmd = [
                ffmpeg, '-y',
                '-f', 'rawvideo',
                '-vcodec', 'rawvideo',
                '-s', f'{fw}x{fh}',
                '-pix_fmt', 'bgra',
                '-r', str(FPS),
                '-i', 'pipe:0',
                '-an',
                '-vcodec', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-r', str(FPS),
                tmp_file
            ]
            try:
                proc = sp.Popen(cmd, stdin=sp.PIPE, stdout=sp.DEVNULL, stderr=sp.DEVNULL,
                                creationflags=0x08000000)
            except Exception as e:
                self._println(f"[Record] ffmpeg launch failed: {e}")
                self._safe_eval("stopRecording()")
                return

            self._println(f"[Record] Recording started (ffmpeg, {fw}x{fh} @ {FPS}fps)...")
            interval = 1.0 / FPS

            import queue as _queue
            frame_queue = _queue.Queue(maxsize=4)
            write_exc = [None]

            def _writer():
                last_raw = None
                frames_sent = 0
                t_start_w = None
                try:
                    while True:
                        try:
                            item = frame_queue.get(timeout=1.0)
                        except _queue.Empty:
                            if self._rec_stop_event.is_set():
                                break
                            continue
                        if item is None:
                            break
                        raw, t_captured = item
                        if raw is not None:
                            last_raw = raw
                        if t_start_w is None:
                            t_start_w = t_captured
                        if last_raw is None:
                            continue
                        elapsed = t_captured - t_start_w
                        frames_due = max(frames_sent + 1, int(elapsed / interval) + 1)
                        try:
                            while frames_sent < frames_due:
                                proc.stdin.write(last_raw)
                                frames_sent += 1
                        except (BrokenPipeError, OSError):
                            break
                except Exception as e:
                    write_exc[0] = e
                finally:
                    try:
                        proc.stdin.close()
                    except Exception:
                        pass

            writer_thread = threading.Thread(target=_writer, daemon=True)
            writer_thread.start()

            try:
                t_start = time.time()
                frame_index = 0
                while not self._rec_stop_event.is_set():
                    next_slot = t_start + frame_index * interval
                    now = time.time()
                    wait = next_slot - now
                    if wait > 0:
                        self._rec_stop_event.wait(wait)
                    if self._rec_stop_event.is_set():
                        break
                    t_capture = time.time()
                    raw = cap_ctx.capture()
                    try:
                        frame_queue.put_nowait((raw, t_capture - t_start))
                    except _queue.Full:
                        pass
                    frame_index += 1
            finally:
                frame_queue.put(None)
                writer_thread.join(timeout=20)
                try:
                    proc.wait(timeout=15)
                except Exception:
                    try: proc.kill()
                    except Exception: pass

          else:
            self._println("[Record] ffmpeg not found - collecting frames (may use more RAM)...")
            frames = []
            timestamps = []
            interval = 1.0 / FPS
            t_start = time.time()
            frame_index = 0
            while not self._rec_stop_event.is_set():
                next_frame_time = t_start + frame_index * interval
                now = time.time()
                wait_before = next_frame_time - now
                if wait_before > 0:
                    self._rec_stop_event.wait(wait_before)
                if self._rec_stop_event.is_set():
                    break
                raw = cap_ctx.capture()
                if raw is not None:
                    frames.append(raw)
                    timestamps.append(time.time() - t_start)
                frame_index += 1
                elapsed_total = time.time() - t_start
                expected_index = int(elapsed_total / interval)
                if frame_index < expected_index:
                    frame_index = expected_index

            if not frames:
                self._println("[Record] No frames captured.")
                self._safe_eval("stopRecording()")
                return

            if len(timestamps) > 1:
                actual_fps = max(1.0, (len(timestamps) - 1) / (timestamps[-1] - timestamps[0]))
            else:
                actual_fps = float(FPS)
            encode_fps = max(1, round(actual_fps))

            written = False
            try:
                import cv2
                import numpy as np
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                out = cv2.VideoWriter(tmp_file, fourcc, encode_fps, (fw, fh))
                for raw in frames:
                    arr = np.frombuffer(raw, dtype=np.uint8).reshape((fh, fw, 3))
                    out.write(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))
                out.release()
                written = True
                self._println(f"[Record] Encoded with OpenCV ({encode_fps}fps actual).")
            except ImportError:
                pass
            except Exception as e:
                self._println(f"[Record] OpenCV error: {e}")

            if not written:
                try:
                    tmp_file = tmp_file.replace('.mp4', '.avi')
                    self._write_mjpeg_avi(tmp_file, frames, fw, fh, encode_fps)
                    written = True
                    self._println("[Record] Encoded as MJPEG AVI (ffmpeg not found).")
                except Exception as e:
                    self._println(f"[Record] AVI write error: {e}")

            if not written:
                self._println("[Record] Recording failed - install ffmpeg or opencv-python.")
                self._safe_eval("stopRecording()")
                return

        finally:
            cap_ctx.release()
            self._hide_rec_overlay()
            self._safe_eval("stopRecording()")

        self._println(f"[Record] Recording stopped. Saving...")

        default_name = os.path.basename(tmp_file).replace('_ezi_rec_tmp_', 'ComfyUI-EZi-recording-')
        if not default_name.endswith('.mp4') and not default_name.endswith('.avi'):
            default_name = f"ComfyUI-EZi-recording-{time.strftime('%Y%m%d_%H%M%S')}.mp4"
        else:
            ext = '.mp4' if tmp_file.endswith('.mp4') else '.avi'
            default_name = f"ComfyUI-EZi-recording-{time.strftime('%Y%m%d_%H%M%S')}{ext}"

        save_path = None
        if self._window and os.path.exists(tmp_file):
            try:
                ft = ("MP4 Video (*.mp4)", "All Files (*.*)") if tmp_file.endswith('.mp4') else ("AVI Video (*.avi)", "All Files (*.*)",)
                result = self._window.create_file_dialog(
                    SAVE_DIALOG_TYPE,
                    directory=self._last_save_dir,
                    save_filename=default_name,
                    file_types=ft
                )
                if result:
                    save_path = result[0] if isinstance(result, (list, tuple)) else result
                    self._last_save_dir = os.path.dirname(save_path)
                    self._settings["last_save_dir"] = self._last_save_dir
                    _save_settings(self._settings)
            except Exception:
                pass

        if save_path and os.path.exists(tmp_file):
            import shutil as _sh
            try:
                _sh.move(tmp_file, save_path)
                self._println(f"[Record] Saved: {save_path}")
            except Exception as e:
                self._println(f"[Record] Save error: {e}")
        elif os.path.exists(tmp_file):
            try: os.remove(tmp_file)
            except Exception: pass

    def _write_mjpeg_avi(self, path, frames_raw, w, h, fps):
        import io, struct
        from PIL import Image

        jpegs = []
        for raw in frames_raw:
            img = Image.frombytes('RGB', (w, h), raw)
            buf = io.BytesIO()
            img.save(buf, 'JPEG', quality=85)
            jpegs.append(buf.getvalue())

        def dw(n):  return struct.pack('<I', n)
        def dd(n):  return struct.pack('<i', n)
        def dw2(n): return struct.pack('<H', n)

        n = len(jpegs)
        us_per_frame = int(1_000_000 / fps)

        movi_data = b''
        idx1_data = b''
        offset = 4
        for jpg in jpegs:
            padded = jpg + (b'\x00' if len(jpg) % 2 else b'')
            chunk = b'00dc' + dw(len(jpg)) + padded
            idx1_data += b'00dc' + dw(0x10) + dw(offset) + dw(len(jpg))
            offset += len(chunk)
            movi_data += chunk

        movi_size = len(movi_data) + 4
        idx1_size = len(idx1_data)

        strh = (b'vids' + b'MJPG' + dw(0)*4 + dw(1) + dw(fps) +
                dw(0) + dw(n) + dw(0) + dw(int(w*h*3)) +
                dw2(w) + dw2(h))
        strf = (dw(40) + dd(w) + dd(h) + dw2(1) + dw2(24) +
                b'MJPG' + dw(w*h*3) + dd(0)*2 + dw(0)*2)

        strl = (b'LIST' + dw(4 + 8 + len(strh) + 8 + len(strf)) + b'strl' +
                b'strh' + dw(len(strh)) + strh +
                b'strf' + dw(len(strf)) + strf)

        avih = (dw(us_per_frame) + dw(int(w*h*3*fps)) + dw(0) + dw(0x10) +
                dw(n) + dw(0) + dw(1) + dw(0) + dw(w) + dw(h))
        hdrl = b'LIST' + dw(4 + 8 + len(avih) + len(strl)) + b'hdrl' + b'avih' + dw(len(avih)) + avih + strl

        movi_chunk = b'LIST' + dw(movi_size) + b'movi' + movi_data
        idx1_chunk = b'idx1' + dw(idx1_size) + idx1_data

        riff_data = hdrl + movi_chunk + idx1_chunk
        with open(path, 'wb') as f:
            f.write(b'RIFF' + dw(len(riff_data) + 4) + b'AVI ' + riff_data)

    def _do_screenshot(self, x, y, w, h):
        time.sleep(0.15)
        try:
            try:
                from PIL import Image
            except ImportError:
                self._println("[Screenshot] Error: Pillow is not installed.\n"
                            "Run: python_embeded\\python.exe -m pip install Pillow")
                return

            import ctypes, ctypes.wintypes as wt
            gdi  = ctypes.windll.gdi32
            user = ctypes.windll.user32

            _vp = ctypes.c_void_p
            user.GetDC.argtypes    = [_vp];           user.GetDC.restype    = _vp
            user.ReleaseDC.argtypes = [_vp, _vp]
            user.ClientToScreen.argtypes = [_vp, ctypes.POINTER(wt.POINT)]
            user.GetClientRect.argtypes  = [_vp, ctypes.c_void_p]
            user.GetDpiForWindow.argtypes = [_vp]; user.GetDpiForWindow.restype = wt.UINT
            gdi.CreateCompatibleDC.argtypes     = [_vp]; gdi.CreateCompatibleDC.restype     = _vp
            gdi.CreateCompatibleBitmap.argtypes = [_vp, ctypes.c_int, ctypes.c_int]
            gdi.CreateCompatibleBitmap.restype  = _vp
            gdi.SelectObject.argtypes = [_vp, _vp]; gdi.SelectObject.restype = _vp
            gdi.BitBlt.argtypes = [_vp,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,
                                   _vp,ctypes.c_int,ctypes.c_int,wt.DWORD]
            gdi.BitBlt.restype = wt.BOOL
            gdi.GetDIBits.argtypes = [_vp,_vp,wt.UINT,wt.UINT,ctypes.c_void_p,ctypes.c_void_p,wt.UINT]
            gdi.DeleteObject.argtypes = [_vp]
            gdi.DeleteDC.argtypes     = [_vp]

            hwnd = _get_hwnd(self._window) if self._window else None
            if not hwnd:
                self._println("[Screenshot] Error: No window handle found.")
                return

            prev_dpi_ctx = None
            try:
                user.SetThreadDpiAwarenessContext.argtypes = [_vp]
                user.SetThreadDpiAwarenessContext.restype  = _vp
                prev_dpi_ctx = user.SetThreadDpiAwarenessContext(_vp(-4))
            except Exception:
                pass

            try:
                dpr = 1.0
                try:
                    dpi = user.GetDpiForWindow(hwnd)
                    dpr = dpi / 96.0
                except Exception:
                    dpr = 1.0

                class RECT(ctypes.Structure):
                    _fields_ = [("left",ctypes.c_long),("top",ctypes.c_long),
                                 ("right",ctypes.c_long),("bottom",ctypes.c_long)]
                rc = RECT()
                user.GetClientRect(hwnd, ctypes.byref(rc))
                cap_w = max(1, rc.right)
                cap_h = max(1, rc.bottom)

                pt = wt.POINT(0, 0)
                user.ClientToScreen(hwnd, ctypes.byref(pt))

                hdc_screen = user.GetDC(_vp(0))
                hdc_mem    = gdi.CreateCompatibleDC(hdc_screen)
                hbm        = gdi.CreateCompatibleBitmap(hdc_screen, cap_w, cap_h)
                old_bm     = gdi.SelectObject(hdc_mem, hbm)

                gdi.BitBlt(hdc_mem, 0, 0, cap_w, cap_h,
                           hdc_screen, pt.x, pt.y, 0x00CC0020)

                class BITMAPINFOHEADER(ctypes.Structure):
                    _fields_ = [("biSize",wt.DWORD),("biWidth",wt.LONG),("biHeight",wt.LONG),
                                ("biPlanes",wt.WORD),("biBitCount",wt.WORD),("biCompression",wt.DWORD),
                                ("biSizeImage",wt.DWORD),("biXPelsPerMeter",wt.LONG),
                                ("biYPelsPerMeter",wt.LONG),("biClrUsed",wt.DWORD),("biClrImportant",wt.DWORD)]

                bih = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER),
                                       biWidth=cap_w, biHeight=-cap_h, biPlanes=1, biBitCount=32,
                                       biCompression=0)
                buf = (ctypes.c_char * (cap_w * cap_h * 4))()
                gdi.GetDIBits(hdc_mem, hbm, 0, cap_h, buf, ctypes.byref(bih), 0)

                gdi.SelectObject(hdc_mem, old_bm)
                gdi.DeleteObject(hbm)
                gdi.DeleteDC(hdc_mem)
                user.ReleaseDC(_vp(0), hdc_screen)

                full_img = Image.frombuffer("RGBA", (cap_w, cap_h), buf, "raw", "BGRA", 0, 1)

                px = max(0, int(round(x * dpr)))
                py = max(0, int(round(y * dpr)))
                pw = max(1, int(round(w * dpr)))
                ph = max(1, int(round(h * dpr)))
                img = full_img.crop((px, py, px + pw, py + ph))

            finally:
                if prev_dpi_ctx is not None:
                    try: user.SetThreadDpiAwarenessContext(prev_dpi_ctx)
                    except Exception: pass

            default_name = f"ComfyUI-EZi-screenshot-{time.strftime('%Y%m%d_%H%M%S')}.png"
            save_path = None
            if self._window:
                try:
                    result = self._window.create_file_dialog(
                        SAVE_DIALOG_TYPE,
                        directory=self._last_save_dir,
                        save_filename=default_name,
                        file_types=("PNG Image (*.png)", "All Files (*.*)")
                    )
                    if result:
                        save_path = result[0] if isinstance(result, (list, tuple)) else result
                        self._last_save_dir = os.path.dirname(save_path)
                        self._settings["last_save_dir"] = self._last_save_dir
                        _save_settings(self._settings)
                except Exception:
                    save_path = None

            if not save_path:
                try:
                    import ctypes.wintypes as wt
                    ctypes.windll.ole32.CoInitializeEx(None, 0x2)
                    class OPENFILENAME(ctypes.Structure):
                        _fields_ = [
                            ("lStructSize",wt.DWORD),("hwndOwner",wt.HWND),("hInstance",wt.HINSTANCE),
                            ("lpstrFilter",wt.LPCWSTR),("lpstrCustomFilter",wt.LPWSTR),
                            ("nMaxCustFilter",wt.DWORD),("nFilterIndex",wt.DWORD),
                            ("lpstrFile",wt.LPWSTR),("nMaxFile",wt.DWORD),
                            ("lpstrFileTitle",wt.LPWSTR),("nMaxFileTitle",wt.DWORD),
                            ("lpstrInitialDir",wt.LPCWSTR),("lpstrTitle",wt.LPCWSTR),
                            ("Flags",wt.DWORD),("nFileOffset",wt.WORD),("nFileExtension",wt.WORD),
                            ("lpstrDefExt",wt.LPCWSTR),("lCustData",wt.LPARAM),
                            ("lpfnHook",wt.LPVOID),("lpTemplateName",wt.LPCWSTR),
                            ("pvReserved",wt.LPVOID),("dwReserved",wt.DWORD),("FlagsEx",wt.DWORD)
                        ]
                    buf_path = ctypes.create_unicode_buffer(default_name, 1024)
                    ofn = OPENFILENAME()
                    ofn.lStructSize = ctypes.sizeof(OPENFILENAME)
                    ofn.hwndOwner   = hwnd if hwnd else None
                    ofn.lpstrFilter = "PNG Image\0*.png\0All Files\0*.*\0"
                    ofn.nFilterIndex = 1
                    ofn.lpstrFile   = buf_path
                    ofn.nMaxFile    = 1024
                    ofn.lpstrInitialDir = self._last_save_dir
                    ofn.lpstrTitle  = "Save Screenshot"
                    ofn.lpstrDefExt = "png"
                    ofn.Flags       = 0x00000002 | 0x00000800
                    if ctypes.windll.comdlg32.GetSaveFileNameW(ctypes.byref(ofn)):
                        save_path = buf_path.value
                        self._last_save_dir = os.path.dirname(save_path)
                        self._settings["last_save_dir"] = self._last_save_dir
                        _save_settings(self._settings)
                    ctypes.windll.ole32.CoUninitialize()
                except Exception:
                    pass

            if save_path:
                img.convert("RGB").save(save_path, "PNG")
        except Exception as e:
            self._println(f"Screenshot error: {e}")

    def save_window_state(self):
        if not self._window:
            return
        try:
            hwnd = self._main_hwnd or _get_hwnd(self._window)
            if not hwnd:
                return

            import ctypes.wintypes as wt
            user = ctypes.windll.user32

            if bool(user.IsIconic(hwnd)):
                return

            wp = EZI_WINDOWPLACEMENT()
            wp.length = ctypes.sizeof(EZI_WINDOWPLACEMENT)
            if not user.GetWindowPlacement(hwnd, ctypes.byref(wp)):
                return

            is_maximized = (wp.showCmd == 3)
            nr = wp.rcNormalPosition
            normal_rect = [nr.left, nr.top, nr.right, nr.bottom]

            w = normal_rect[2] - normal_rect[0]
            h = normal_rect[3] - normal_rect[1]
            if w < 50 or h < 50:
                return

            try:
                user.GetDpiForWindow.argtypes = [ctypes.c_void_p]
                user.GetDpiForWindow.restype  = wt.UINT
                saved_dpi = user.GetDpiForWindow(ctypes.c_void_p(hwnd))
            except Exception:
                saved_dpi = 96
            if not saved_dpi:
                saved_dpi = 96

            saved_state = {
                "showCmd":          3 if is_maximized else 1,
                "rcNormalPosition": normal_rect,
                "saved_dpi":        saved_dpi,
            }

            if is_maximized:
                rc = wt.RECT()
                if user.GetWindowRect(hwnd, ctypes.byref(rc)):
                    saved_state["maximized_rect"] = [rc.left, rc.top, rc.right, rc.bottom]

            if self._settings.get("window_placement") != saved_state:
                self._settings["window_placement"] = saved_state
                _save_settings(self._settings)
        except Exception:
            pass

        if self._console_win is not None and self._console_hwnd:
            self._save_console_placement(self._console_hwnd)

    def save_comfy_storage(self, storage_json):
        try:
            data = json.loads(storage_json)
            if not data or (isinstance(data.get("ls"), dict) and not data["ls"] and isinstance(data.get("ss"), dict) and not data["ss"]):
                return
            MAX_STORAGE_BYTES = 20 * 1024 * 1024
            try:
                if len(json.dumps(data)) > MAX_STORAGE_BYTES:
                    return
            except Exception:
                pass
            self._settings["comfy_storage"] = data
            self._storage_holder[0] = data
            _save_settings(self._settings)
        except Exception:
            pass

    def get_ui_settings(self):
        try:
            hide = self._settings.get("hide_deprecation_warnings", True)
            fb = self._settings.get("custom_file_browser", "")
            theme = self._settings.get("theme", "dark")
            comfy_theme = _get_comfy_current_theme()
            comfy_theme_vars = _get_comfy_theme_css_vars()
            comfy_settings_path = os.path.join(_get_comfy_user_dir(), 'comfy.settings.json')
            console_detached = self._settings.get("console_detached", False)
            custom_paths_json = self.get_custom_paths()
            custom_paths = json.loads(custom_paths_json) if custom_paths_json else {'input': '', 'output': '', 'user': ''}
            return json.dumps({
                "showTooltips": bool(self._settings.get("show_tooltips", True)),
                "hideDeprecationWarnings": hide,
                "customFileBrowser": fb,
                "theme": theme,
                "comfyTheme": comfy_theme,
                "comfyThemeVars": comfy_theme_vars,
                "comfySettingsPath": comfy_settings_path,
                "consoleDetached": console_detached,
                "customPaths": custom_paths,
                "recFps": self._settings.get("rec_fps", 15),
                "consoleBgImage":   self._settings.get("console_bg_image", ""),
                "consoleBgFit":     self._settings.get("console_bg_fit", "fit"),
                "consoleBgOpacity": self._settings.get("console_bg_opacity", 0.12),
                "consoleBgAnimate": self._settings.get("console_bg_animate", True),
            })
        except Exception as e:
            print(f"[EZi DEBUG] get_ui_settings ERROR: {e}", flush=True)
            return None

    def save_ui_settings(self, settings_json):
        try:
            if not settings_json or not isinstance(settings_json, str) or not settings_json.strip():
                return
            data = json.loads(settings_json)
            if not isinstance(data, dict) or not data:
                return
            if "showTooltips" in data:
                self._settings["show_tooltips"] = bool(data["showTooltips"])
                self._console_push_tooltips()
            if "hideDeprecationWarnings" in data:
                self._settings["hide_deprecation_warnings"] = bool(data["hideDeprecationWarnings"])
            if "customFileBrowser" in data:
                self._settings["custom_file_browser"] = str(data["customFileBrowser"]).strip()
            if "theme" in data and data["theme"] in ("dark", "pixaroma", "light", "comfyui"):
                self._settings["theme"] = data["theme"]
                self._console_push_theme()
            if "recFps" in data and int(data["recFps"]) in (15, 30, 60):
                self._settings["rec_fps"] = int(data["recFps"])
            if "consoleBgImage" in data:
                self._settings["console_bg_image"] = str(data["consoleBgImage"]).strip()
            if "consoleBgFit" in data and data["consoleBgFit"] in ("fit", "stretch", "tile", "center"):
                self._settings["console_bg_fit"] = data["consoleBgFit"]
            if "consoleBgOpacity" in data:
                try:
                    val = float(data["consoleBgOpacity"])
                    if 0.03 <= val <= 0.60:
                        self._settings["console_bg_opacity"] = val
                except (ValueError, TypeError):
                    pass
            if "consoleBgAnimate" in data:
                self._settings["console_bg_animate"] = bool(data["consoleBgAnimate"])

            if self._settings_holder is not None:
                self._settings_holder[0] = self._settings
            _save_settings(self._settings)
        except Exception:
            pass

    def get_comfy_storage(self):
        return self._settings.get("comfy_storage", None)

    def send_to_comfy(self, message_json):
        try:
            if not message_json or not isinstance(message_json, str):
                return
            cw = _EZI_WINDOW_REF.get("comfy_webview")
            if cw is None:
                return

            def _do_post():
                try:
                    cw.CoreWebView2.PostWebMessageAsJson(message_json)
                except Exception:
                    pass
            self._ui_invoke(_do_post)
        except Exception:
            pass

    def _console_title(self):
        return f"ComfyUI Console  [EZi v{APP_VERSION}]"

    def _create_console_window(self):
        kw = dict(url=f'http://127.0.0.1:{self._proxy_port}/__console__', js_api=self,
                  width=900, height=500, min_size=(420, 220), resizable=True,
                  hidden=True, frameless=False, background_color='#1e1e1e')
        try:
            return webview.create_window(self._console_title(), user_agent=CHROME_UA, **kw)
        except TypeError:
            return webview.create_window(self._console_title(), **kw)

    def _console_hwnd_of(self, win):
        try:
            h = ctypes.windll.user32.FindWindowW(None, self._console_title())
            if h:
                return int(h)
        except Exception:
            pass
        try:
            h = int(win.native.Handle.ToInt64())
            if h:
                return h
        except Exception:
            pass
        return None

    def _apply_console_placement(self, hwnd):
        if not hwnd:
            return False
        want_max = False
        try:
            user32 = ctypes.windll.user32
            pl = self._settings.get("console_placement")
            if pl and isinstance(pl, dict):
                x, y = pl.get("x", 100), pl.get("y", 100)
                cx, cy = pl.get("cx", 900), pl.get("cy", 500)
                if pl.get("showCmd", 1) == 3:
                    mr = pl.get("maximized_rect")
                    if mr and _is_rect_on_active_monitor(mr[0], mr[1], mr[2], mr[3]):
                        user32.MoveWindow(hwnd, x, y, cx, cy, False)
                    want_max = True
                elif _is_rect_on_active_monitor(x, y, x + cx, y + cy):
                    user32.MoveWindow(hwnd, x, y, cx, cy, True)
            try:
                dark = ctypes.c_int(0 if self._settings.get("theme", "dark") == "light" else 1)
                for attr in (20, 19):
                    if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(dark), ctypes.sizeof(dark)) == 0:
                        break
            except Exception:
                pass
            _set_window_icon(hwnd)
        except Exception:
            pass
        return want_max

    def _push_console_state(self, win, state):
        CH = 200000
        win.evaluate_js("tImportBegin()")
        for i in range(0, len(state), CH):
            win.evaluate_js("tImportPart(%s)" % json.dumps(state[i:i + CH]))
        return bool(win.evaluate_js("tImportEnd()"))

    def _focus_console_window(self):
        win = self._console_win
        if win is None:
            return
        try:
            hwnd = self._console_hwnd
            if hwnd:
                u32 = ctypes.windll.user32
                if u32.IsIconic(hwnd):
                    u32.ShowWindow(hwnd, 9)
                u32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _abort_console_window(self, win):
        if win is None:
            return
        self._console_allow_close = True
        try:
            win.destroy()
        except Exception:
            pass
        self._console_allow_close = False

    def _do_detach(self):
        if self._window is None:
            return False
        win = None
        with self._pump_lock:
            try:
                win = self._create_console_window()
                win.events.closing += self._on_console_closing
                for ev_name in ('moved', 'resized'):
                    ev = getattr(win.events, ev_name, None)
                    if ev is not None:
                        ev += self._on_console_geometry
                if not win.events.loaded.wait(30):
                    raise RuntimeError("the console window did not load")
                hwnd = self._console_hwnd_of(win)
                want_max = self._apply_console_placement(hwnd)
                state = self._window.evaluate_js("tExport()")
                if not state:
                    raise RuntimeError("could not read the console history")
                self._push_console_state(win, state)
                win.show()
                if hwnd:
                    try:
                        if want_max:
                            ctypes.windll.user32.ShowWindow(hwnd, 3)
                        ctypes.windll.user32.SetForegroundWindow(hwnd)
                    except Exception:
                        pass
                self._console_hwnd = hwnd
                self._console_win = win
                self._settings["console_detached"] = True
                _save_settings(self._settings)
            except Exception as e:
                self._console_win, self._console_hwnd = None, None
                self._abort_console_window(win)
                self._println(f"\033[91m[Console] Could not detach: {e}\033[0m")
                return False
        self._safe_eval("window.__eziConsoleDetachedUI && window.__eziConsoleDetachedUI(true)")
        return True

    def _do_attach(self):
        with self._pump_lock:
            win = self._console_win
            if win is None:
                return True
            state = None
            try:
                state = win.evaluate_js("tExport()")
            except Exception:
                pass
            if self._console_hwnd:
                self._save_console_placement(self._console_hwnd)
            if state and self._window is not None:
                try:
                    self._push_console_state(self._window, state)
                except Exception as e:
                    self._println(f"\033[91m[Console] History could not be moved back: {e}\033[0m")
            self._console_win, self._console_hwnd = None, None
            self._abort_console_window(win)
            self._settings["console_detached"] = False
            _save_settings(self._settings)
        self._safe_eval("window.__eziConsoleDetachedUI && window.__eziConsoleDetachedUI(false)")
        return True

    def _on_console_closing(self):
        if self._console_allow_close:
            return True
        threading.Thread(target=self.attach_console, daemon=True).start()
        return False

    def _on_console_geometry(self, *args):
        t = self._console_geo_timer
        if t is not None:
            t.cancel()
        t = threading.Timer(0.6, self._save_console_placement_now)
        t.daemon = True
        t.start()
        self._console_geo_timer = t

    def _save_console_placement_now(self):
        if self._console_win is not None and self._console_hwnd:
            self._save_console_placement(self._console_hwnd)

    def _console_push_theme(self):
        win = self._console_win
        if win is None:
            return
        try:
            theme = self._settings.get("theme", "dark")
            vars_ = _get_comfy_theme_css_vars() if theme == "comfyui" else {}
            win.evaluate_js(f"applyTheme({json.dumps(theme)}, {json.dumps(vars_)})")
        except Exception:
            pass

    def _console_push_tooltips(self):
        win = self._console_win
        if win is None:
            return
        try:
            win.evaluate_js(f"applyTooltips({json.dumps(bool(self._settings.get('show_tooltips', True)))})")
        except Exception:
            pass

    def _destroy_console_window(self):
        win = self._console_win
        if win is None:
            return
        self._console_win, self._console_hwnd = None, None
        self._abort_console_window(win)

    def detach_console(self):
        if self._console_win is not None:
            self._focus_console_window()
            self._safe_eval("window.__eziConsoleDetachedUI && window.__eziConsoleDetachedUI(true)")
            return True
        if not self._console_op_lock.acquire(blocking=False):
            return False
        try:
            return bool(self._do_detach())
        finally:
            self._console_op_lock.release()

    def attach_console(self):
        if self._console_win is None:
            self._safe_eval("window.__eziConsoleDetachedUI && window.__eziConsoleDetachedUI(false)")
            return True
        if not self._console_op_lock.acquire(blocking=False):
            return False
        try:
            return bool(self._do_attach())
        finally:
            self._console_op_lock.release()

    def _save_console_placement(self, hwnd):
        try:
            import ctypes.wintypes as wt
            user32 = ctypes.windll.user32

            is_maximized = bool(user32.IsZoomed(hwnd))
            if bool(user32.IsIconic(hwnd)):
                return

            rc = wt.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rc)):
                return
            placement = {
                "x":       rc.left,
                "y":       rc.top,
                "cx":      rc.right  - rc.left,
                "cy":      rc.bottom - rc.top,
                "showCmd": 3 if is_maximized else 1,
            }

            if is_maximized:
                placement["maximized_rect"] = [rc.left, rc.top, rc.right, rc.bottom]

            if self._settings.get("console_placement") != placement:
                self._settings["console_placement"] = placement
                _save_settings(self._settings)
        except Exception:
            pass

    def stop(self):
        try:
            self.save_window_state()
        except Exception:
            pass
        self._destroy_console_window()
        self._window = None
        self._kill_running_proc()

    def _run(self):
        try:
            if not os.path.isdir(os.path.join(ROOT_DIR, "python_embeded")):
                self._println(
                    f"\033[91m✖  Wrong script location!\033[0m\n"
                    f"\n"
                    f"ComfyUI-EZi.py must be placed three levels below the ComfyUI root:\n"
                    f"\033[93m  <ComfyUI Root>\\Add-Ons\\Tools\\Helper-CEI\\ComfyUI-EZi.py\033[0m\n"
                    f"\n"
                    f"Current location:\n"
                    f"\033[93m  {CURRENT_SCRIPT_DIR}\033[0m"
                )
                return
            main_path = None
            for loc in [os.path.join(ROOT_DIR, "main.py"), os.path.join(ROOT_DIR, "ComfyUI", "main.py")]:
                if os.path.exists(loc):
                    main_path = loc; break
            
            if not main_path:
                self._println("Error: main.py not found!"); return

            extra_args = []
            py_flags = ['-X', 'utf8=1']
            if not os.path.exists(BAT_FILE):
                bat_name = os.path.basename(BAT_FILE)
                self._safe_eval(f"show_bat_missing({json.dumps(bat_name)})")
            if os.path.exists(BAT_FILE):
                with open(BAT_FILE, 'r', encoding='utf-8', errors='replace') as f:
                    bat_content = f.read()

                ENV_TO_ARG = {
                    'COMFY_INPUT_DIR':  '--input-directory',
                    'COMFY_OUTPUT_DIR': '--output-directory',
                    'COMFY_USER_DIR':   '--user-directory',
                }
                env_dirs = {}
                for env_name, arg_name in ENV_TO_ARG.items():
                    m_env = re.search(
                        r'(?i)set\s+"?' + re.escape(env_name) + r'=([^"\n]+)"?',
                        bat_content
                    )
                    if m_env:
                        env_dirs[arg_name] = m_env.group(1).strip().strip('"')

                m = re.search(r'python_embeded[/\\]python\.exe["\']?\s+(.*)',
                              _find_bat_comfy_line(bat_content) or '', re.IGNORECASE)
                if m:
                    raw_str = m.group(1).strip()
                    parsed = shlex.split(raw_str, posix=False)

                    script_idx = None
                    for idx, token in enumerate(parsed):
                        if token.endswith('.py'):
                            script_idx = idx
                            break

                    if script_idx is not None:
                        pre_script = parsed[:script_idx]
                        post_script = parsed[script_idx + 1:]
                    else:
                        pre_script = []
                        post_script = parsed

                    PY_FLAGS_WITH_VALUE = {'-W', '-X'}
                    j = 0
                    while j < len(pre_script):
                        tok = pre_script[j]
                        if tok in PY_FLAGS_WITH_VALUE and j + 1 < len(pre_script):
                            py_flags.extend([tok, pre_script[j + 1]])
                            j += 2
                        elif tok.startswith('-'):
                            py_flags.append(tok)
                            j += 1
                        else:
                            j += 1

                    ARGS_SINGLE_VAL = {
                        '--port', '--tls-keyfile', '--tls-certfile',
                        '--max-upload-size', '--base-directory',
                        '--output-directory', '--temp-directory', '--input-directory',
                        '--cuda-device', '--default-device',
                        '--oneapi-device-selector',
                        '--preview-size', '--cache-lru',
                        '--reserve-vram', '--vram-headroom', '--default-hashing-function',
                        '--front-end-version', '--front-end-root',
                        '--user-directory', '--comfy-api-base', '--database-url',
                        '--models-directory', '--feature-flag',
                    }
                    ARGS_OPT_VAL = {
                        '--listen', '--enable-cors-header', '--directml',
                        '--preview-method', '--async-offload',
                    }
                    ARGS_MULTI_VAL = {
                        '--extra-model-paths-config', '--whitelist-custom-nodes',
                    }
                    ARGS_OPT_MULTI_VAL = {
                        '--fast', '--cache-ram', '--verbose',
                    }
                    i = 0
                    while i < len(post_script):
                        arg = post_script[i]
                        if arg in ARGS_SINGLE_VAL:
                            if i + 1 < len(post_script):
                                val = post_script[i + 1].strip('"\'')
                                extra_args.extend([arg, val])
                                env_dirs.pop(arg, None)
                                i += 2
                            else:
                                i += 1
                        elif arg in ARGS_OPT_VAL:
                            extra_args.append(arg)
                            if (i + 1 < len(post_script) and
                                    not post_script[i + 1].startswith('--')):
                                extra_args.append(post_script[i + 1].strip('"\''))
                                i += 2
                            else:
                                i += 1
                        elif arg in ARGS_MULTI_VAL:
                            extra_args.append(arg)
                            i += 1
                            while i < len(post_script) and not post_script[i].startswith('--'):
                                extra_args.append(post_script[i].strip('"\''))
                                i += 1
                        elif arg in ARGS_OPT_MULTI_VAL:
                            extra_args.append(arg)
                            i += 1
                            while i < len(post_script) and not post_script[i].startswith('--'):
                                extra_args.append(post_script[i].strip('"\''))
                                i += 1
                        elif arg.startswith('--'):
                            if 'auto-launch' not in arg:
                                extra_args.append(arg)
                            i += 1
                        else:
                            i += 1

                for arg_name, path_val in env_dirs.items():
                    extra_args.extend([arg_name, path_val])

            final_args = py_flags + [main_path] + extra_args + ["--disable-auto-launch"]

            target_port = self._comfy_port_holder[0]
            for arg_i, arg_v in enumerate(extra_args):
                if arg_v == '--port' and arg_i + 1 < len(extra_args):
                    try: target_port = int(extra_args[arg_i + 1])
                    except ValueError: pass

            def _port_busy(port):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
                    connection.settimeout(0.5)
                    return connection.connect_ex(('127.0.0.1', port)) == 0

            if _port_busy(target_port):
                self._println(
                    f"\033[93m⚠  Port {target_port} is already in use!\033[0m\n"
                    f"Another application is occupying this port.\n"
                    f"Please close it, then press \033[92mRetry\033[0m."
                )
                self._safe_eval("show_port_error()")
                return

            _cols = self._get_columns()
            cmd_display = os.path.relpath(self.PY_EXE, ROOT_DIR) + ' ' + ' '.join(final_args)
            self._println('\033[2m' + cmd_display + '\033[0m\n')
            my_run_id = self._run_id
            run_env = os.environ.copy()
            for _k in ("CUDA_PATH", "CUDA_HOME", "CUDA_BIN_PATH", "CUDNN_PATH", "CUDNN_HOME",
                       "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV"):
                run_env.pop(_k, None)
            for _k in [k for k in run_env if k.upper().startswith("CUDA_PATH_V")]:
                run_env.pop(_k, None)
            run_env |= {"PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "TQDM_NCOLS": str(_cols)}
            import sys as _sys
            _sys.path.insert(0, os.path.join(ROOT_DIR, 'amd'))
            from runtime import configure, startup_args
            run_env, gpu_arch = configure(ROOT_DIR, run_env)
            extra_args = startup_args(gpu_arch, extra_args)
            _comfy_args = repr([main_path] + extra_args + ["--disable-auto-launch"])
            _bootstrap = (
                "import sys, runpy, logging\n"
                "sys.stderr = sys.stdout\n"
                "_oe = logging.StreamHandler.emit\n"
                "def _pe(self, r):\n"
                "    self.stream = sys.stdout\n"
                "    _oe(self, r)\n"
                "logging.StreamHandler.emit = _pe\n"
                f"sys.argv = {_comfy_args}\n"
                f"runpy.run_path({main_path!r}, run_name='__main__')\n"
            )
            try:
                _pinned = self._settings.get('pinned_packages') or []
                if not _pinned:
                    try:
                        if os.path.exists(SETTINGS_PATH):
                            with open(SETTINGS_PATH, 'r', encoding='utf-8') as _sf:
                                _pinned = json.load(_sf).get('pinned_packages') or []
                    except Exception:
                        pass
                for _entry in _pinned:
                    _entry = _entry.strip()
                    if not _entry or '==' not in _entry:
                        continue
                    _pkg, _ver = _entry.split('==', 1)
                    _pkg, _ver = _pkg.strip(), _ver.strip()
                    _chk = subprocess.run(
                        [self.PY_EXE, '-c',
                         f'import sys, importlib.metadata as _im; v=_im.version({_pkg!r}); sys.exit(0 if v=={_ver!r} else 1)'],
                        capture_output=True, timeout=10, creationflags=self._NO_WIN,
                        env=run_env
                    )
                    if _chk.returncode != 0:
                        self._println(f'\033[93m[Pinned] {_pkg} version mismatch - reinstalling {_entry}...\033[0m')
                        _rc = self._stream_cmd(
                            [self.PY_EXE, '-I', '-m', 'pip', 'install',
                             '--force-reinstall', _entry,
                             '--no-deps', '--no-warn-script-location', '--no-cache-dir'],
                            env=run_env, use_pty=True)
                        if _rc == 0:
                            self._println(f'\033[92m[Pinned] {_entry} restored.\033[0m')
                        else:
                            self._println(f'\033[91m[Pinned] Failed to restore {_entry}.\033[0m')
            except Exception:
                pass

            self._proc = subprocess.Popen(
                [self.PY_EXE] + py_flags + ['-c', _bootstrap],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                cwd=ROOT_DIR, env=run_env,
                creationflags=0x08000000|0x00000200
            )
            dec = codecs.getincrementaldecoder('utf-8')(errors='replace')
            fd = self._proc.stdout.fileno()
            url_tail = ''
            while True:
                if self._run_id != my_run_id:
                    break
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                text = dec.decode(chunk)
                if not text:
                    continue
                self._print(text)
                url_tail += text
                m = None
                if '\n' in url_tail:
                    head, _, url_tail = url_tail.rpartition('\n')
                    m = COMFYUI_URL_RE.search(head)
                elif len(url_tail) > 8192:
                    url_tail = url_tail[-1024:]
                if m and not self._url_found and not self._restarting:
                    self._url_found = True
                    detected_port = int(m.group(1))
                    self._comfy_port_holder[0] = detected_port
                    self._safe_eval("set_dot_ready()")
                    def _wait_and_load(port, proxy_port):
                        import urllib.request as _ur
                        for _ in range(40):
                            try:
                                _ur.urlopen(f'http://127.0.0.1:{port}/system_stats', timeout=5)
                                self._navigate_comfy_webview(f'http://127.0.0.1:{proxy_port}/')
                                return
                            except Exception:
                                time.sleep(0.5)
                        self._navigate_comfy_webview(f'http://127.0.0.1:{proxy_port}/')
                    threading.Thread(target=_wait_and_load,
                                     args=(detected_port, self._proxy_port),
                                     daemon=True).start()
                elif m and self._restarting:
                    self._comfy_port_holder[0] = int(m.group(1))
            tail = dec.decode(b'', final=True)
            if tail:
                self._print(tail)
            self._ensure_nl()
        except Exception as e: self._println(f"Error: {str(e)}")

    def _depr_filter(self, text):
        if not self._settings.get('hide_deprecation_warnings', True):
            text = self._depr_hold + text
            self._depr_hold, self._depr_drop, self._depr_blank = '', False, False
            if text:
                self._depr_bol = text[-1] in '\r\n'
            return text
        if self._depr_hold == '\r' and self._depr_blank:
            text, self._depr_hold = '\r' + text, ''
        out, pos, n = [], 0, len(text)
        while pos < n:
            if self._depr_drop:
                nl = text.find('\n', pos)
                if nl < 0:
                    break
                pos, self._depr_drop, self._depr_bol, self._depr_blank = nl + 1, False, True, True
                continue
            if not self._depr_bol:
                m = _LINE_TERM_RE.search(text, pos)
                if not m:
                    out.append(text[pos:])
                    break
                out.append(text[pos:m.end()])
                pos, self._depr_bol = m.end(), True
                continue
            if self._depr_blank:
                c = text[pos]
                if c == '\n':
                    self._depr_blank = False
                    pos += 1
                    continue
                if c == '\r' and pos + 1 >= n:
                    self._depr_hold, self._depr_hold_t = '\r', time.monotonic()
                    break
                self._depr_blank = False
                if c == '\r' and text[pos + 1] == '\n':
                    pos += 2
                    continue
            m = _LINE_TERM_RE.search(text, pos)
            seg = text[pos:m.start()] if m else text[pos:]
            cand = self._depr_hold + seg
            if _DEPR_MARK in cand:
                self._depr_hold, self._depr_drop, self._depr_bol = '', True, False
                pos += len(seg)
                continue
            if m:
                out.append(cand + m.group())
                self._depr_hold = ''
                pos = m.end()
                continue
            if len(cand) >= _DEPR_HOLD_MAX:
                out.append(cand)
                self._depr_hold, self._depr_bol = '', False
            else:
                if not self._depr_hold:
                    self._depr_hold_t = time.monotonic()
                self._depr_hold = cand
            break
        return ''.join(out)

    def _depr_release(self, age=0.05):
        with self._out_lock:
            if self._depr_hold and time.monotonic() - self._depr_hold_t >= age:
                held, self._depr_hold, self._depr_bol, self._depr_blank = self._depr_hold, '', False, False
                self._sink(held)

    def _sink(self, text):
        if not text:
            return
        self._last_ch = text[-1]
        self._out_buf.append(text)

    def _print(self, text):
        if not text:
            return
        with self._out_lock:
            self._sink(self._depr_filter(text))

    def _println(self, text):
        if text.endswith('\n'):
            text = text[:-1]
        for line in text.split('\n'):
            self._print(line + '\n')

    def _ensure_nl(self):
        with self._out_lock:
            if self._depr_hold:
                held, self._depr_hold = self._depr_hold, ''
                self._sink(held)
            if self._last_ch != '\n':
                self._sink('\n')
            self._depr_bol = True

    def _ctl(self, seq):
        with self._out_lock:
            self._out_buf.append(seq)

    def _console_pump(self):
        CHUNK = 262144
        while True:
            time.sleep(0.03)
            self._depr_release()
            if not self._js_ready.is_set():
                continue
            with self._pump_lock:
                win = self._console_win or self._window
                if win is None:
                    continue
                with self._out_lock:
                    if not self._out_buf:
                        continue
                    data, self._out_buf = ''.join(self._out_buf), []
                for k in range(0, len(data), CHUNK):
                    try:
                        win.evaluate_js(f"add_to_console({json.dumps(data[k:k + CHUNK])})")
                    except Exception:
                        pass

    def _forward_pipe(self, proc):
        dec = codecs.getincrementaldecoder('utf-8')(errors='replace')
        fd = proc.stdout.fileno()
        while True:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            text = dec.decode(chunk)
            if text:
                self._print(text)
        tail = dec.decode(b'', final=True)
        if tail:
            self._print(tail)

    def _stream_cmd(self, cmd, cwd=None, env=None, use_pty=False, stdin_devnull=False):
        cmd = [str(c) for c in cmd]
        env = env if env is not None else os.environ.copy()
        if use_pty:
            cols = max(40, int(self._columns))
            pty, err = _spawn_pty(cmd, cwd, env, cols, log=self._println)
            if pty is None:
                self._println(f"\033[93m[Console] ConPTY unavailable ({err}) - live progress bars are disabled\033[0m")
            else:
                self._ensure_nl()
                self._ctl(f"\x1b]777;ezi-pty;start;{_PTY_ROWS};{cols}\x07")
                try:
                    while True:
                        try:
                            chunk = pty.read(4096)
                        except (EOFError, OSError):
                            break
                        if not chunk:
                            break
                        if isinstance(chunk, bytes):
                            chunk = chunk.decode('utf-8', errors='replace')
                        self._print(chunk)
                finally:
                    try:
                        pty.wait()
                    except Exception:
                        pass
                    self._ctl("\x1b]777;ezi-pty;end\x07")
                    with self._out_lock:
                        if self._depr_hold:
                            held, self._depr_hold = self._depr_hold, ''
                            self._sink(held)
                        self._last_ch, self._depr_bol, self._depr_drop, self._depr_blank = '\n', True, False, False
                return pty.exitstatus or 0
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                cwd=cwd, env=env,
                                stdin=subprocess.DEVNULL if stdin_devnull else None,
                                creationflags=self._NO_WIN)
        try:
            self._forward_pipe(proc)
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass
            proc.wait()
        self._ensure_nl()
        return proc.returncode or 0

    def _safe_eval(self, js):
        if self._window:
            try: self._window.evaluate_js(js)
            except: pass

    def _ui_invoke(self, action):
        try:
            form = _EZI_WINDOW_REF.get("winforms_form")
            if form is None:
                action()
                return
            if form.InvokeRequired:
                import System
                form.BeginInvoke(System.Action(action))
            else:
                action()
        except Exception:
            pass

    def _show_rec_overlay(self, cap_ctx):
        def _do():
            try:
                import System.Windows.Forms as _WinForms
                import System.Drawing as _Drawing

                self._hide_rec_overlay_now()

                sx, sy = cap_ctx.src_x, cap_ctx.src_y
                sw, sh = max(1, cap_ctx.cap_w), max(1, cap_ctx.cap_h)
                THICK = 3
                red = _Drawing.Color.FromArgb(255, 68, 68)

                def _make_strip(x, y, w, h):
                    f = _WinForms.Form()
                    f.AutoScaleMode  = getattr(_WinForms.AutoScaleMode, 'None')
                    f.FormBorderStyle = getattr(_WinForms.FormBorderStyle, 'None')
                    f.ShowInTaskbar   = False
                    f.StartPosition   = _WinForms.FormStartPosition.Manual
                    f.TopMost         = True
                    f.MinimumSize     = _Drawing.Size(0, 0)
                    f.BackColor       = red
                    f.Bounds          = _Drawing.Rectangle(x, y, max(1, w), max(1, h))
                    f.Show()
                    f.Bounds = _Drawing.Rectangle(x, y, max(1, w), max(1, h))
                    _make_clickthrough(f.Handle.ToInt64())
                    return f

                top    = _make_strip(sx - THICK, sy - THICK, sw + THICK * 2, THICK)
                bottom = _make_strip(sx - THICK, sy + sh,     sw + THICK * 2, THICK)
                left   = _make_strip(sx - THICK, sy,          THICK, sh)
                right  = _make_strip(sx + sw,    sy,          THICK, sh)

                stopf = _WinForms.Form()
                stopf.AutoScaleMode  = getattr(_WinForms.AutoScaleMode, 'None')
                stopf.FormBorderStyle = getattr(_WinForms.FormBorderStyle, 'None')
                stopf.ShowInTaskbar   = False
                stopf.StartPosition   = _WinForms.FormStartPosition.Manual
                stopf.TopMost         = True
                stopf.MinimumSize     = _Drawing.Size(0, 0)

                btn = _WinForms.Button()
                btn.Text      = "\u23F9 Stop REC"
                btn.FlatStyle = _WinForms.FlatStyle.Flat
                btn.FlatAppearance.BorderColor = red
                btn.BackColor = _Drawing.Color.FromArgb(0x6e, 0x20, 0x20)
                btn.ForeColor = _Drawing.Color.FromArgb(0xff, 0x88, 0x88)
                btn.Font      = _Drawing.Font("Consolas", 8.5, _Drawing.FontStyle.Bold)
                btn.AutoSize  = True
                btn.Click += lambda s, e: self.stop_recording()

                stopf.Controls.Add(btn)
                stopf.Show()
                stopf.ClientSize = btn.Size
                stopf.Location = _Drawing.Point(sx, max(0, sy - btn.Height - THICK - 2))

                _EZI_WINDOW_REF["rec_overlay"] = (top, bottom, left, right, stopf)
            except Exception as _e:
                self._println(f"[Record] overlay error: {_e}")
        self._ui_invoke(_do)

    def _hide_rec_overlay_now(self):
        pair = _EZI_WINDOW_REF.get("rec_overlay")
        _EZI_WINDOW_REF["rec_overlay"] = None
        if not pair:
            return
        for f in pair:
            try:
                f.Close()
                f.Dispose()
            except Exception:
                pass

    def _hide_rec_overlay(self):
        self._ui_invoke(self._hide_rec_overlay_now)

    def _navigate_comfy_webview(self, url):
        def _do():
            cw = _EZI_WINDOW_REF.get("comfy_webview")
            if cw is None:
                return
            if _EZI_WINDOW_REF.get("comfy_ready") and cw.CoreWebView2 is not None:
                cw.CoreWebView2.Navigate(url)
            else:
                _EZI_WINDOW_REF["comfy_pending_url"] = url
        self._ui_invoke(_do)

    def reload_comfy_view(self):
        def _do():
            cw = _EZI_WINDOW_REF.get("comfy_webview")
            if cw is not None and cw.CoreWebView2 is not None:
                cw.CoreWebView2.Reload()
        self._ui_invoke(_do)

    def set_shell_expanded(self, expanded):
        if isinstance(expanded, bool):
            _EZI_WINDOW_REF["shell_expanded"] = expanded
        elif isinstance(expanded, (int, float)) and expanded > 0:
            _EZI_WINDOW_REF["shell_expanded"] = expanded
        elif isinstance(expanded, str) and expanded.lower() == 'full':
            _EZI_WINDOW_REF["shell_expanded"] = True
        else:
            _EZI_WINDOW_REF["shell_expanded"] = False
        def _do():
            fn = _EZI_WINDOW_REF.get("apply_bounds")
            if fn:
                fn()
        self._ui_invoke(_do)

    def slide_comfy_in(self, duration_ms=300):
        ref = _EZI_WINDOW_REF
        try:
            if ref.get("comfy_webview") is None or not ref.get("apply_bounds"):
                return False
            dur = max(0.05, float(duration_ms) / 1000.0)
            ref["comfy_slide_gen"] = ref.get("comfy_slide_gen", 0) + 1
            gen = ref["comfy_slide_gen"]
            ease = _ezi_cubic_bezier(0.4, 0.0, 0.2, 1.0)

            def _apply(p):
                if ref.get("comfy_slide_gen") != gen:
                    return
                ref["comfy_slide_progress"] = p
                fn = ref.get("apply_bounds")
                if fn:
                    fn()

            parked = threading.Event()

            def _park():
                try:
                    _apply(0.0)
                finally:
                    parked.set()
            self._ui_invoke(_park)
            parked.wait(0.5)

            def _runner():
                t0 = time.perf_counter()
                pending = {"v": False}

                def _step():
                    try:
                        t = min(1.0, (time.perf_counter() - t0) / dur)
                        _apply(ease(t))
                    finally:
                        pending["v"] = False
                try:
                    while ref.get("comfy_slide_gen") == gen and (time.perf_counter() - t0) < dur:
                        if not pending["v"]:
                            pending["v"] = True
                            self._ui_invoke(_step)
                        time.sleep(0.004)
                finally:
                    self._ui_invoke(lambda: _apply(1.0))
            threading.Thread(target=_runner, daemon=True).start()
            return True
        except Exception:
            ref["comfy_slide_progress"] = 1.0
            try:
                fn = ref.get("apply_bounds")
                if fn:
                    self._ui_invoke(fn)
            except Exception:
                pass
            return False

if __name__ == '__main__':
    def find_free_port(preferred=None):
        try:
            preferred = int(preferred) if preferred else None
        except (TypeError, ValueError):
            preferred = None
        if preferred and 1024 <= preferred <= 65535 and preferred != COMFY_PORT:
            try:
                with socket.socket() as s:
                    s.bind(('127.0.0.1', preferred))
                return preferred
            except OSError:
                pass
        with socket.socket() as s: s.bind(('', 0)); return s.getsockname()[1]

    _autorun_bat = os.path.normpath(os.path.join(CURRENT_SCRIPT_DIR, "..", "AutoRun.bat"))
    try:
        if os.path.isfile(_autorun_bat):
            os.remove(_autorun_bat)
    except Exception:
        pass

    _ensure_attention_flags()

    settings = _load_settings()
    settings["_dpi_aware_version"] = 1
    _settings_ref["obj"] = settings
    p_port = find_free_port(settings.get("proxy_port"))
    if settings.get("proxy_port") != p_port:
        settings["proxy_port"] = p_port
        _save_settings(settings)
    c_port_h = [COMFY_PORT]
    storage_holder = [settings.get("comfy_storage")]
    settings_holder = [settings]

    _proxy_ready = threading.Event()
    _api_holder = [None]

    loop = asyncio.new_event_loop()
    def start_proxy():
        asyncio.set_event_loop(loop)
        async def _run():
            app = await make_proxy_app(c_port_h, storage_holder, settings_holder, _api_holder)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, '127.0.0.1', p_port)
            await site.start()
            _proxy_ready.set()
            await asyncio.Event().wait()
        loop.run_until_complete(_run())

    threading.Thread(target=start_proxy, daemon=True).start()
    _proxy_ready.wait(timeout=10)

    def _clear_webview2_cache():
        try:
            import shutil
            base = os.environ.get('LOCALAPPDATA', '')
            temp = os.environ.get('TEMP', '')
            candidates = [
                os.path.join(base, 'pywebview', 'EBWebView'),
                os.path.join(temp, 'pywebview', 'EBWebView'),
            ]
            for path in candidates:
                if os.path.isdir(path):
                    try:
                        shutil.rmtree(path, ignore_errors=True)
                    except Exception:
                        pass
        except Exception:
            pass
    _clear_webview2_cache()

    api = Api(p_port, c_port_h, settings, storage_holder, settings_holder)
    _api_holder[0] = api
    _EZI_WINDOW_REF["api"] = api

    import atexit
    atexit.register(api._kill_running_proc)

    try:
        window = webview.create_window(
            f'ComfyUI EZi Desktop - AMD  v{APP_VERSION}',
            url=f'http://127.0.0.1:{p_port}/__shell__',
            js_api=api,
            user_agent=CHROME_UA,
            frameless=False,
            resizable=True,
            background_color='#1e1e1e',
        )
    except TypeError:
        window = webview.create_window(
            f'ComfyUI EZi Desktop - AMD  v{APP_VERSION}',
            url=f'http://127.0.0.1:{p_port}/__shell__',
            js_api=api,
            frameless=False,
            resizable=True,
            background_color='#1e1e1e',
        )
    api.set_window(window)
    _EZI_WINDOW_REF["window"] = window
    window.events.loaded += api.on_loaded
    window.events.closed  += api.stop

    def _titlebar_push_max_state(is_max):
        try:
            window.evaluate_js(
                "window.__eziSetMaxState && window.__eziSetMaxState(%s)"
                % ('true' if is_max else 'false')
            )
        except Exception:
            pass
    def _ezi_reapply_bounds_for(hwnd):
        try:
            fn = _ezi_bounds_fns.get(int(hwnd)) if hwnd else None
            if fn:
                fn()
        except Exception:
            pass

    def _on_maximized():
        _titlebar_push_max_state(True)
        hwnd = _get_hwnd(window)
        _taskbar_mark_not_fullscreen(hwnd)
        _ezi_reapply_bounds_for(hwnd)
        _force_full_repaint(hwnd)
        import threading as _th
        for _delay in (0.05, 0.15, 0.35):
            _th.Timer(_delay, lambda h=hwnd: (_ezi_reapply_bounds_for(h), _force_full_repaint(h))).start()
    def _on_restored():
        _titlebar_push_max_state(False)
        hwnd = _get_hwnd(window)
        _ezi_reapply_bounds_for(hwnd)
    window.events.maximized += _on_maximized
    window.events.restored  += _on_restored

    def _on_closing():
        if api._confirm_close:
            return True
        # Ask in every case; while an install or update runs, warn that closing
        # interrupts it and can leave the environment half-installed.
        busy = 'true' if api._updating else 'false'
        def _ask():
            try:
                u32 = ctypes.windll.user32
                hwnd = _get_hwnd(window)
                if hwnd:
                    try:
                        if u32.IsIconic(hwnd):
                            u32.ShowWindow(hwnd, 9)
                        u32.SetForegroundWindow(hwnd)
                        u32.BringWindowToTop(hwnd)
                    except Exception:
                        pass
                api._window.evaluate_js(f"show_close_confirm({busy});")
                time.sleep(0.08)
                if hwnd:
                    try:
                        u32.SetForegroundWindow(hwnd)
                    except Exception:
                        pass
            except Exception:
                api._confirm_close = True
                try:
                    api._window.destroy()
                except Exception:
                    pass
        threading.Thread(target=_ask, daemon=True).start()
        return False
    window.events.closing += _on_closing

    def _restore_on_shown():
        try:
            hwnd = _get_hwnd(window)
            if not hwnd:
                threading.Timer(0.3, _restore_on_shown).start()
                return

            wp_data = settings.get("window_placement")
            if not wp_data or not isinstance(wp_data, dict):
                return

            import ctypes.wintypes as wt
            user = ctypes.windll.user32

            prev_dpi_ctx = None
            try:
                prev_dpi_ctx = user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
            except Exception:
                pass

            try:
                wp = EZI_WINDOWPLACEMENT()
                wp.length = ctypes.sizeof(EZI_WINDOWPLACEMENT)

                show_cmd = wp_data.get("showCmd", 1)
                rc_data  = wp_data.get("rcNormalPosition")
                if not rc_data or len(rc_data) != 4:
                    return

                saved_dpi = wp_data.get("saved_dpi", 96) or 96
                current_dpi = 96
                try:
                    user.GetDpiForWindow.argtypes = [ctypes.c_void_p]
                    user.GetDpiForWindow.restype  = wt.UINT
                    current_dpi = user.GetDpiForWindow(ctypes.c_void_p(hwnd)) or 96
                except Exception:
                    pass

                if saved_dpi != current_dpi:
                    scale = current_dpi / saved_dpi
                    def _scale_rect(r):
                        left  = int(round(r[0] * scale))
                        top   = int(round(r[1] * scale))
                        right = int(round(left + (r[2] - r[0]) * scale))
                        bottom= int(round(top  + (r[3] - r[1]) * scale))
                        return [left, top, right, bottom]
                    rc_data = _scale_rect(rc_data)
                    mx_rect = wp_data.get("maximized_rect")
                    if mx_rect:
                        mx_rect = _scale_rect(mx_rect)
                    else:
                        mx_rect = None
                else:
                    mx_rect = wp_data.get("maximized_rect")

                def _primary_monitor_center_rect(w=1100, h=700):
                    try:
                        sw = user.GetSystemMetrics(0)
                        sh = user.GetSystemMetrics(1)
                        x = max(0, (sw - w) // 2)
                        y = max(0, (sh - h) // 2)
                        return [x, y, x + w, y + h]
                    except Exception:
                        return [100, 100, 1200, 800]

                if show_cmd == 3:
                    check_rect = mx_rect if mx_rect else rc_data
                    if not _is_rect_on_active_monitor(check_rect[0], check_rect[1], check_rect[2], check_rect[3]):
                        fallback = _primary_monitor_center_rect()
                        wp.showCmd = 1
                        wp.rcNormalPosition = wt.RECT(fallback[0], fallback[1], fallback[2], fallback[3])
                    else:
                        wp.showCmd = 3
                        wp.rcNormalPosition = wt.RECT(rc_data[0], rc_data[1], rc_data[2], rc_data[3])
                else:
                    if not _is_rect_on_active_monitor(rc_data[0], rc_data[1], rc_data[2], rc_data[3]):
                        fallback = _primary_monitor_center_rect()
                        wp.showCmd = 1
                        wp.rcNormalPosition = wt.RECT(fallback[0], fallback[1], fallback[2], fallback[3])
                    else:
                        wp.showCmd = 1
                        wp.rcNormalPosition = wt.RECT(rc_data[0], rc_data[1], rc_data[2], rc_data[3])

                user.SetWindowPlacement(hwnd, ctypes.byref(wp))
                def _reapply():
                    try:
                        user.SetWindowPlacement(hwnd, ctypes.byref(wp))
                    except Exception:
                        pass
                threading.Timer(0.25, _reapply).start()
            finally:
                if prev_dpi_ctx is not None:
                    try:
                        user.SetThreadDpiAwarenessContext(prev_dpi_ctx)
                    except Exception:
                        pass
        except Exception:
            pass

    window.events.shown += _restore_on_shown

    try:
        try:
            webview.start(user_agent=CHROME_UA, debug=DEV_MODE)
        except TypeError:
            webview.start(debug=DEV_MODE)
    except Exception as _start_err:
        _err_text = f"{type(_start_err).__module__}.{type(_start_err).__name__}: {_start_err}".lower()
        if any(tok in _err_text for tok in (
            "webview2", "corewebview2", "0x80070002", "0x8007007e", "0x80004005"
        )):
            _ezi_report_webview2_failure(_start_err)
        else:
            raise
