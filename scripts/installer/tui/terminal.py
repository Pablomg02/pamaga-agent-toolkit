"""Raw terminal I/O: alternate screen, raw mode and key decoding.

This is the only module that touches the real terminal. `Terminal` is a
context manager: it enters the alternate screen, hides the cursor and sets
raw mode, and restores all of it on normal exit, on an exception, on Ctrl-C
(which arrives as a key in raw mode) and on SIGTERM. `read_key` returns
normalised key names, `size` measures the window and `draw` paints a frame.

Key decoding lives in the pure function `decode(bytes) -> list[str]`, which
`read_key` uses; a lone ESC waits `ESCAPE_TIMEOUT` for the rest of a split
sequence before it is reported as `esc`.

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import atexit
import os
import select
import shutil
import signal
import sys
import threading
import time
from collections import deque
from typing import Deque, IO, List, Optional, Sequence, Tuple

try:  # POSIX only
    import termios
    import tty
except ImportError:  # pragma: no cover - Windows
    termios = None
    tty = None

ESCAPE_TIMEOUT = 0.03
READ_SIZE = 64
DEFAULT_SIZE = (80, 24)

KEY_NAMES = frozenset({
    "up", "down", "left", "right", "pgup", "pgdn", "home", "end",
    "enter", "esc", "tab", "backspace", "space", "delete", "ctrl-c",
})

# Longest sequences first: prefixes are checked in order.
_SEQUENCES: Tuple[Tuple[bytes, str], ...] = (
    (b"\x1b[1~", "home"),
    (b"\x1b[3~", "delete"),
    (b"\x1b[4~", "end"),
    (b"\x1b[5~", "pgup"),
    (b"\x1b[6~", "pgdn"),
    (b"\x1b[A", "up"),
    (b"\x1b[B", "down"),
    (b"\x1b[C", "right"),
    (b"\x1b[D", "left"),
    (b"\x1b[H", "home"),
    (b"\x1b[F", "end"),
    (b"\x1bOA", "up"),
    (b"\x1bOB", "down"),
    (b"\x1bOC", "right"),
    (b"\x1bOD", "left"),
    (b"\x1bOH", "home"),
    (b"\x1bOF", "end"),
)

_SINGLE_KEYS = {
    0x03: "ctrl-c",
    0x08: "backspace",
    0x09: "tab",
    0x0A: "enter",
    0x0D: "enter",
    0x20: "space",
    0x7F: "backspace",
}

_WINDOWS_SPECIAL = {
    "H": "up",
    "P": "down",
    "K": "left",
    "M": "right",
    "I": "pgup",
    "Q": "pgdn",
    "G": "home",
    "O": "end",
    "S": "delete",
}


def _utf8_char(data: bytes, index: int) -> Tuple[str, int]:
    byte = data[index]
    if byte >= 0xF0:
        size = 4
    elif byte >= 0xE0:
        size = 3
    elif byte >= 0xC0:
        size = 2
    else:
        size = 1
    try:
        return data[index:index + size].decode("utf-8"), size
    except UnicodeDecodeError:
        return "\ufffd", 1


def decode(data: bytes) -> List[str]:
    """Normalised key names for a chunk of terminal input.

    Complete escape sequences (arrows, `PgUp`/`PgDn`, `Home`/`End`) become
    their names, `\\r`/`\\n` is `enter`, `\\x7f`/`\\x08` is `backspace`,
    `\\x03` is `ctrl-c`, a space is `space` and other printable bytes are
    returned as characters. Two keys in one chunk yield two entries.

    An escape sequence split across reads is completed by `read_key`, which
    waits `ESCAPE_TIMEOUT`; `decode` itself maps an ESC that does not start a
    complete sequence to `esc` plus the following bytes decoded normally.
    """
    keys: List[str] = []
    index = 0
    while index < len(data):
        byte = data[index]
        if byte == 0x1B:
            for sequence, name in _SEQUENCES:
                if data.startswith(sequence, index):
                    keys.append(name)
                    index += len(sequence)
                    break
            else:
                keys.append("esc")
                index += 1
        elif byte == 0x0D and index + 1 < len(data) and data[index + 1] == 0x0A:
            keys.append("enter")
            index += 2
        elif byte in _SINGLE_KEYS:
            keys.append(_SINGLE_KEYS[byte])
            index += 1
        elif 0x20 <= byte < 0x7F:
            keys.append(chr(byte))
            index += 1
        elif byte >= 0x80:
            char, size = _utf8_char(data, index)
            keys.append(char)
            index += size
        else:
            index += 1  # unknown control byte: ignore
    return keys


def decode_windows(chars: str) -> List[str]:
    """Normalised keys for `msvcrt` input, where specials arrive as two chars.

    The prefixes are `\\x00` and `\\xe0`; `H P K M I Q G O S` map to the
    arrow, paging, home/end and delete keys.
    """
    keys: List[str] = []
    index = 0
    while index < len(chars):
        char = chars[index]
        if char in ("\x00", "\xe0"):
            if index + 1 >= len(chars):
                index += 1  # the second half has not arrived yet
                continue
            name = _WINDOWS_SPECIAL.get(chars[index + 1])
            if name:
                keys.append(name)
            index += 2
        elif char == "\r":
            keys.append("enter")
            index += 1
        elif char == "\x1b":
            keys.append("esc")
            index += 1
        elif char == "\t":
            keys.append("tab")
            index += 1
        elif char in ("\x08", "\x7f"):
            keys.append("backspace")
            index += 1
        elif char == " ":
            keys.append("space")
            index += 1
        elif char == "\x03":
            keys.append("ctrl-c")
            index += 1
        elif char.isprintable():
            keys.append(char)
            index += 1
        else:
            index += 1
    return keys


def _is_prefix(chunk: bytes) -> bool:
    """True when `chunk` could still grow into a known escape sequence."""
    return any(sequence.startswith(chunk) and len(chunk) < len(sequence) for sequence, _ in _SEQUENCES)


def _split(data: bytes) -> Tuple[bytes, bytes]:
    """Split a read buffer into decodable bytes and a trailing partial sequence."""
    for index, byte in enumerate(data):
        if byte == 0x1B and _is_prefix(data[index:]):
            return data[:index], data[index:]
    return data, b""


class Terminal:
    """Context manager around the real terminal.

    `fd` defaults to standard input and `stream` to standard output, so the
    normal use is `with Terminal() as term:`. Tests pass a pty file descriptor
    and a fake stream.
    """

    def __init__(self, fd: Optional[int] = None, stream: Optional[IO[str]] = None) -> None:
        self._fd = sys.stdin.fileno() if fd is None else fd
        self._stream = stream
        self._saved = None
        self._win_mode = None
        self._active = False
        self._keys: Deque[str] = deque()
        self._buffer = b""
        self._last_frame: Optional[Tuple[str, ...]] = None
        self._atexit = None
        self._old_sigterm = None

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> "Terminal":
        if self._active:
            return self
        self._keys.clear()
        self._buffer = b""
        self._last_frame = None
        self._active = True
        self._atexit = self.restore
        atexit.register(self._atexit)
        if os.name == "posix":
            self._enter_posix()
            self._install_signal_handler()
        else:  # pragma: no cover - Windows
            self._enter_windows()
        self._write("\x1b[?1049h\x1b[?25l")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.restore()
        return False

    def restore(self) -> None:
        """Leave the alternate screen, show the cursor and reset raw mode.

        Safe to call more than once and from an `atexit` handler or a signal
        handler: it never raises.
        """
        if not self._active:
            return
        self._active = False
        self._write("\x1b[?25h\x1b[?1049l")
        if termios is not None and self._saved is not None:
            try:
                termios.tcsetattr(self._fd, termios.TCSANOW, self._saved)
            except (termios.error, OSError, ValueError):
                pass
            self._saved = None
        if self._win_mode is not None:  # pragma: no cover - Windows
            self._restore_windows()
        if self._atexit is not None:
            try:
                atexit.unregister(self._atexit)
            except Exception:
                pass
            self._atexit = None
        if self._old_sigterm is not None:
            try:
                signal.signal(signal.SIGTERM, self._old_sigterm)
            except (ValueError, OSError):
                pass
            self._old_sigterm = None

    # -- platform setup ----------------------------------------------------

    def _enter_posix(self) -> None:
        if termios is None or tty is None:
            return
        try:
            self._saved = termios.tcgetattr(self._fd)
            # TCSANOW, not setraw's default TCSAFLUSH: a key typed while the
            # installer was starting must not be thrown away. Not TCSADRAIN
            # either: on macOS it waits for unread output, such as the echo
            # of that key, and can block forever.
            tty.setraw(self._fd, termios.TCSANOW)
        except (termios.error, OSError, ValueError):
            self._saved = None

    def _install_signal_handler(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            return
        try:
            self._old_sigterm = signal.signal(signal.SIGTERM, self._on_sigterm)
        except (ValueError, OSError):
            self._old_sigterm = None

    def _on_sigterm(self, signum, frame) -> None:
        previous = self._old_sigterm
        self.restore()
        try:
            signal.signal(signum, previous if callable(previous) else signal.SIG_DFL)
            os.kill(os.getpid(), signum)
        except (OSError, RuntimeError, ValueError):
            os._exit(128 + signum)

    def _enter_windows(self) -> None:  # pragma: no cover - Windows
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                self._win_mode = mode.value
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except Exception:
            self._win_mode = None
        try:
            self._output().reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass

    def _restore_windows(self) -> None:  # pragma: no cover - Windows
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            kernel32.SetConsoleMode(handle, self._win_mode)
        except Exception:
            pass
        self._win_mode = None

    def _output(self) -> IO[str]:
        return self._stream if self._stream is not None else sys.stdout

    def _write(self, text: str) -> bool:
        """Write to the output stream; never raises, so restore() is safe."""
        try:
            stream = self._output()
            stream.write(text)
            stream.flush()
            return True
        except (OSError, ValueError):
            return False

    # -- reading -----------------------------------------------------------

    def read_key(self, timeout: float = 0.1) -> Optional[str]:
        """The next key name, or None when `timeout` seconds pass without one."""
        if os.name != "posix":
            return self._read_key_windows(timeout)  # pragma: no cover - Windows
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            if self._keys:
                return self._keys.popleft()
            complete, partial = _split(self._buffer)
            if complete:
                self._buffer = partial
                keys = decode(complete)
                if keys:
                    self._keys.extend(keys[1:])
                    return keys[0]
                continue
            if partial:
                if self._read_more(ESCAPE_TIMEOUT):
                    continue
                # No byte followed within the grace period: the ESC is a key.
                keys = decode(self._buffer)
                self._buffer = b""
                if keys:
                    self._keys.extend(keys[1:])
                    return keys[0]
                continue
            remaining = deadline - time.monotonic()
            if remaining < 0:
                return None
            if not self._read_more(remaining):
                return None

    def _read_more(self, wait: float) -> bool:
        """Wait up to `wait` seconds for input; True when bytes were buffered."""
        try:
            ready = select.select([self._fd], [], [], max(0.0, wait))[0]
        except (OSError, ValueError):
            return False
        if not ready:
            return False
        try:
            data = os.read(self._fd, READ_SIZE)
        except OSError:
            return False
        if not data:
            return False  # end of input
        self._buffer += data
        return True

    def _read_key_windows(self, timeout: float) -> Optional[str]:  # pragma: no cover - Windows
        import msvcrt

        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            if self._keys:
                return self._keys.popleft()
            if self._buffer:
                if self._buffer.endswith(("\x00", "\xe0")):
                    if time.monotonic() >= deadline:
                        self._buffer = self._buffer[:-1]
                        continue
                    if msvcrt.kbhit():
                        self._buffer += msvcrt.getwch()
                    else:
                        time.sleep(0.005)
                    continue
                keys = decode_windows(self._buffer)
                self._buffer = ""
                if keys:
                    self._keys.extend(keys[1:])
                    return keys[0]
                continue
            if time.monotonic() >= deadline:
                return None
            if msvcrt.kbhit():
                self._buffer += msvcrt.getwch()
            else:
                time.sleep(0.01)

    # -- drawing -----------------------------------------------------------

    def size(self) -> os.terminal_size:
        """(columns, lines) of the terminal, with an 80x24 fallback."""
        try:
            columns, lines = os.get_terminal_size(self._fd)
            if columns > 0 and lines > 0:
                return os.terminal_size((columns, lines))
        except OSError:
            pass
        # Before 3.11 shutil returns 0x0 for a pty that was never sized
        # instead of the fallback.
        size = shutil.get_terminal_size(fallback=DEFAULT_SIZE)
        if size.columns > 0 and size.lines > 0:
            return size
        return os.terminal_size(DEFAULT_SIZE)

    def draw(self, lines: Sequence[str]) -> None:
        """Paint one frame, `\\x1b[H` + each line + `\\x1b[K`, then `\\x1b[J`.

        Written in one call, and only when the frame differs from the previous
        one. Lines are separated by `\\r\\n` because raw mode disables output
        post-processing; the last line has no newline, so a full-height frame
        never scrolls.
        """
        frame = tuple(lines)
        if frame == self._last_frame:
            return
        self._last_frame = frame
        body = "\r\n".join(line + "\x1b[K" for line in frame)
        self._write("\x1b[H" + body + "\x1b[J")
