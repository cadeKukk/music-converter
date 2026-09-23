#!/usr/bin/env python3
"""Start, stop, check, and configure login startup without third-party Python packages."""
import argparse
import hashlib
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import time

from runtime import APP, INBOX, acquire_lock, media_tools

STATE = INBOX / ".converter"
IDENTIFIER = "music-converter-" + hashlib.sha256(str(APP).encode()).hexdigest()[:12]


def running():
    lock = acquire_lock(STATE / "watcher.lock")
    if lock is None:
        return True
    lock.close()
    return False


def start():
    media_tools()
    if running():
        print("Converter is already running.")
        return
    interpreter = Path(sys.executable)
    if os.name == "nt" and interpreter.with_name("pythonw.exe").exists():
        interpreter = interpreter.with_name("pythonw.exe")
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    with (STATE / "service.log").open("ab") as log:
        child = subprocess.Popen([str(interpreter), "-X", "utf8", str(APP / "converter.py")],
                                 cwd=APP, stdin=subprocess.DEVNULL, stdout=log, stderr=log, **kwargs)
    for _ in range(50):
        if running():
            print("Running. Drop completed album folders into:", INBOX)
            print("Original FLACs are permanently deleted after MP3 verification.")
            return
        if child.poll() is not None:
            raise RuntimeError(f"Converter exited. See {STATE / 'service.log'}")
        time.sleep(.1)
    raise RuntimeError(f"Startup not confirmed. See {STATE / 'service.log'}")


def stop():
    if not running():
        print("Converter is already stopped.")
        return
    (STATE / "stop.request").touch()
    for _ in range(150):
        if not running():
            print("Converter stopped. Originals from interrupted conversions are kept.")
            return
        time.sleep(.1)
    raise RuntimeError("Stop requested; a large file copy may still be finishing. Run Status again shortly.")


def startup_path():
    if os.name == "nt":
        return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup" / (IDENTIFIER + ".lnk")
    if sys.platform == "darwin":
        return Path.home() / "Library/LaunchAgents" / ("local." + IDENTIFIER + ".plist")
    raise RuntimeError("Automatic login setup supports Windows and macOS. Use your desktop's startup manager on Linux.")


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def enable_login():
    media_tools()
    path = startup_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        interpreter = Path(sys.executable).with_name("pythonw.exe")
        if not interpreter.exists():
            interpreter = Path(sys.executable)
        args = subprocess.list2cmdline(["-X", "utf8", str(APP / "converter.py")])
        command = (
            "$shell = New-Object -ComObject WScript.Shell; "
            f"$link = $shell.CreateShortcut({ps_quote(path)}); "
            f"$link.TargetPath = {ps_quote(interpreter)}; "
            f"$link.Arguments = {ps_quote(args)}; "
            f"$link.WorkingDirectory = {ps_quote(APP)}; "
            "$link.WindowStyle = 7; $link.Save()"
        )
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command], check=True)
    else:
        config = {"Label": "local." + IDENTIFIER,
                  "ProgramArguments": [sys.executable, "-X", "utf8", str(APP / "converter.py")],
                  "WorkingDirectory": str(APP), "RunAtLoad": True,
                  "StandardOutPath": str(STATE / "service.log"),
                  "StandardErrorPath": str(STATE / "service.log")}
        STATE.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as stream:
            plistlib.dump(config, stream)
        # The current session uses the same ordinary Start path. macOS loads this at next login.
    start()
    print("Automatic startup enabled for your next login.")


def disable_login():
    path = startup_path()
    if sys.platform == "darwin":
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/local.{IDENTIFIER}"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    path.unlink(missing_ok=True)
    stop()
    print("Automatic startup disabled.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "status", "check", "enable-login", "disable-login"])
    args = parser.parse_args()
    try:
        if args.action == "check":
            print("Python:", sys.version.split()[0], sys.executable)
            return subprocess.call([sys.executable, str(APP / "converter.py"), "--check"])
        if args.action == "status":
            print("Converter is", "RUNNING" if running() else "STOPPED")
            print("Music inbox:", INBOX)
            print("Login startup:", "enabled" if startup_path().exists() else "disabled")
        elif args.action == "start":
            start()
        elif args.action == "stop":
            stop()
        elif args.action == "enable-login":
            enable_login()
        elif args.action == "disable-login":
            disable_login()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print("Error:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
