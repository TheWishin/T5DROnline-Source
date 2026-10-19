"""Crash-safe file writes for the server's own files (certificate, key, host.json)."""
import os


def atomic_write(path, data, mode=0o644):
    """Write `data` (str or bytes) to `path` so that a crash or power cut at any moment leaves
    either the old file or the new one, never a truncated mix: a temporary file next to it,
    flushed to disk, then renamed over the old one (and the directory entry synced on POSIX)."""
    tmp = f"{path}.tmp{os.getpid()}"
    raw = data.encode("utf-8") if isinstance(data, str) else data
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), mode)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    if os.name != "nt":
        try:
            dfd = os.open(os.path.dirname(os.path.abspath(path)), os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass
