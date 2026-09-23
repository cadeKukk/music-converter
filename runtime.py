"""Small standard-library helpers shared by the converter and launchers."""
import os
from pathlib import Path
import shutil
import sys

APP = Path(__file__).resolve().parent
INBOX = APP / "Music Inbox"


def is_link(path):
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def acquire_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    stream.seek(0, os.SEEK_END)
    if stream.tell() == 0:
        stream.write(b"0")
        stream.flush()
    stream.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        stream.close()
        return None
    return stream


def media_tools():
    """Prefer optional local tools, then PATH, then standard Homebrew locations."""
    suffix = ".exe" if os.name == "nt" else ""
    for directory in (APP / "tools", APP / "tools/bin"):
        ffmpeg, ffprobe = directory / ("ffmpeg" + suffix), directory / ("ffprobe" + suffix)
        if ffmpeg.is_file() and ffprobe.is_file():
            return str(ffmpeg), str(ffprobe)
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg and ffprobe:
        return ffmpeg, ffprobe
    if sys.platform == "darwin":
        for directory in (Path("/opt/homebrew/bin"), Path("/usr/local/bin")):
            if (directory / "ffmpeg").is_file() and (directory / "ffprobe").is_file():
                return str(directory / "ffmpeg"), str(directory / "ffprobe")
    raise RuntimeError("FFmpeg and FFprobe are missing. Follow docs/WINDOWS.md or docs/MAC.md, then reopen the launcher.")
