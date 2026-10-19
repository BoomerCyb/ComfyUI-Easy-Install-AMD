import logging
import sys


class _LogFilter(logging.Filter):
    def filter(self, record):
        exc = record.exc_info[1] if record.exc_info else None
        if isinstance(exc, ConnectionResetError):
            return False
        msg = record.getMessage()
        if "_call_connection_lost" in msg:
            return False
        if record.levelno == logging.WARNING and msg.lstrip().startswith("[DEPRECATION WARNING]"):
            return False
        return True


class _StdoutFilter:
    _PREFIX = "[WARNING] [DEPRECATION WARNING]"

    def __init__(self, stream):
        self._stream = stream
        self._skip_newline = False

    def write(self, s):
        if isinstance(s, str):
            if self._skip_newline and s == "\n":
                self._skip_newline = False
                return len(s)
            self._skip_newline = False
            if s.lstrip().startswith(self._PREFIX):
                self._skip_newline = not s.endswith("\n")
                return len(s)
        return self._stream.write(s)

    def __getattr__(self, name):
        return getattr(self._stream, name)


_filter = _LogFilter()
logging.getLogger("asyncio").addFilter(_filter)
for _h in logging.getLogger().handlers:
    _h.addFilter(_filter)

if not isinstance(sys.stdout, _StdoutFilter):
    sys.stdout = _StdoutFilter(sys.stdout)

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}