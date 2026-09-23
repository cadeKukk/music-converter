#!/usr/bin/env python3
"""Convert loose FLACs and create MP3 copies of dropped folder trees."""
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
from runtime import INBOX, acquire_lock, is_link, media_tools

STOP = False
CHILD = None
LOG = logging.getLogger("music-converter")
OUTPUT_FOLDER = "Converted MP3"
PROBE_CACHE = {}
STOP_FILE = None


def stop(_signum, _frame):
    global STOP
    STOP = True
    if CHILD is not None and CHILD.poll() is None:
        CHILD.terminate()


def signature(path):
    stat = path.stat()
    return stat.st_ino, stat.st_size, stat.st_mtime_ns


def prepare_directory(directory, root):
    """Create output directories without following links out of the drop folder."""
    current = root
    for component in directory.relative_to(root).parts:
        current = current / component
        if is_link(current):
            raise OSError(f"Output directory is a symbolic link: {current}")
        current.mkdir(exist_ok=True)


def output_directory(source_dir, folder, names):
    relative = source_dir.relative_to(folder)
    for ancestor in (relative, *relative.parents):
        if ancestor.as_posix() in names:
            return folder / OUTPUT_FOLDER / names[ancestor.as_posix()] / relative.relative_to(ancestor)
    return folder / OUTPUT_FOLDER / relative


def discover(folder, names):
    """Return source/target pairs, excluding generated output and hidden files."""
    jobs = []
    for entry in sorted(folder.iterdir()):
        if entry.name.startswith(".") or entry.name == OUTPUT_FOLDER or is_link(entry):
            continue
        if entry.is_file() and entry.suffix.lower() == ".flac":
            jobs.append((entry, entry.with_suffix(".mp3")))
        elif entry.is_dir():
            def report_error(error):
                LOG.error("Cannot read source folder: %s", error)
            for directory, dirs, files in os.walk(entry, followlinks=False, onerror=report_error):
                source_dir = Path(directory)
                dirs[:] = sorted(d for d in dirs if not d.startswith(".")
                                 and not is_link(source_dir / d))
                output_dir = output_directory(source_dir, folder, names)
                try:
                    prepare_directory(output_dir, folder)
                except OSError as exc:
                    LOG.error("Cannot create output folder: %s", exc)
                    dirs[:] = []
                    continue
                for name in sorted(files):
                    source = source_dir / name
                    if name.startswith(".") or is_link(source) or not source.is_file():
                        continue
                    target = output_dir / name
                    if source.suffix.lower() == ".flac":
                        target = target.with_suffix(".mp3")
                    jobs.append((source, target))
    # A FLAC conversion wins when an input folder also contains the same-name MP3.
    return sorted(jobs, key=lambda job: (job[0].suffix.lower() != ".flac", str(job[0])))


def publish(temporary, target):
    try:
        os.link(temporary, target)
        LOG.info("Created %s", target)
        return True
    except FileExistsError:
        LOG.info("Kept existing %s", target)
        return False


def copy_companion(source, target, expected):
    fd, temporary = tempfile.mkstemp(prefix=".copying-", dir=target.parent)
    os.close(fd)
    try:
        shutil.copy2(source, temporary)
        if not STOP and signature(source) == expected:
            publish(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def run_media(command):
    """Run a cancellable FFmpeg operation and surface decoding failures."""
    global CHILD
    with tempfile.TemporaryFile() as errors:
        try:
            CHILD = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
            while True:
                try:
                    output, _ = CHILD.communicate(timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    if STOP or (STOP_FILE is not None and STOP_FILE.exists()):
                        stop(None, None)
            if STOP:
                raise RuntimeError("Stopped; original FLAC kept")
            if CHILD.returncode:
                errors.seek(0, os.SEEK_END)
                errors.seek(max(0, errors.tell() - 6000))
                raise RuntimeError(errors.read().decode("utf-8", errors="replace").strip())
            return output.decode("utf-8", errors="replace")
        finally:
            CHILD = None


def probe(path, ffprobe):
    key = str(path), signature(path)
    if key not in PROBE_CACHE:
        result = run_media([ffprobe, "-v", "error", "-show_format", "-show_streams",
                            "-of", "json", str(path)])
        PROBE_CACHE[key] = json.loads(result)
    return PROBE_CACHE[key]


def decoded_audio(path, ffmpeg):
    result = run_media([ffmpeg, "-v", "error", "-nostdin", "-xerror", "-i", str(path),
                        "-map", "0:a:0", "-vn", "-ar", "44100", "-ac", "2",
                        "-c:a", "pcm_s16le", "-progress", "pipe:1", "-nostats",
                        "-f", "hash", "-hash", "sha256", "pipe:1"])
    duration = None
    digest = None
    for line in result.splitlines():
        if line.startswith("out_time_us="):
            try:
                duration = int(line.partition("=")[2]) / 1_000_000
            except ValueError:
                pass
        elif line.startswith("SHA256="):
            digest = line.partition("=")[2].strip()
    if duration is None or duration <= 0 or not digest:
        raise RuntimeError(f"No complete audio could be verified: {path.name}")
    return duration, digest


def validate_conversion(source, mp3, ffmpeg, ffprobe):
    original = probe(source, ffprobe)
    converted = probe(mp3, ffprobe)
    audio = [stream for stream in converted.get("streams", []) if stream.get("codec_type") == "audio"]
    if not audio or audio[0].get("codec_name") != "mp3":
        raise RuntimeError("Output is not an MP3; original kept")
    source_duration, _ = decoded_audio(source, ffmpeg)
    target_duration, target_digest = decoded_audio(mp3, ffmpeg)
    tolerance = max(.1, source_duration * .0001)
    if abs(source_duration - target_duration) > tolerance:
        raise RuntimeError("Audio durations differ; original kept")
    # A declared length also catches a truncated FLAC ending exactly on a frame boundary.
    declared = original.get("format", {}).get("duration")
    if declared and abs(float(declared) - source_duration) > tolerance:
        raise RuntimeError("FLAC appears incomplete; original kept")
    return target_digest


def convert(source, target, expected, ffmpeg, ffprobe):
    if is_link(source) or is_link(target):
        raise RuntimeError("Symbolic links are not converted or deleted")
    fd, temporary = tempfile.mkstemp(prefix=".converting-", suffix=".mp3", dir=target.parent)
    os.close(fd)
    try:
        LOG.info("Converting %s", source.name)
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                   "-xerror", "-i", str(source), "-map", "0:a:0", "-map", "0:v:0?",
                   "-map_metadata", "0", "-c:a", "libmp3lame", "-b:a", "320k",
                   "-ar", "44100", "-ac", "2", "-c:v", "mjpeg",
                   "-id3v2_version", "3", temporary]
        run_media(command)
        candidate_digest = validate_conversion(source, Path(temporary), ffmpeg, ffprobe)
        if signature(source) != expected:
            LOG.info("File changed during conversion; will retry: %s", source.name)
            return
        # An exclusive hard link publishes the complete output without overwriting anything.
        if not publish(temporary, target):
            if is_link(target) or not target.is_file():
                raise RuntimeError("Existing destination is not a regular file; original kept")
            before = signature(target)
            _, existing_digest = decoded_audio(target, ffmpeg)
            existing_info = probe(target, ffprobe)
            if not any(s.get("codec_name") == "mp3" for s in existing_info.get("streams", [])):
                raise RuntimeError("Existing destination is not an MP3; original kept")
            if existing_digest != candidate_digest or signature(target) != before:
                raise RuntimeError("Existing MP3 does not match a fresh conversion; original kept")
        if STOP or is_link(source) or signature(source) != expected:
            LOG.info("Source changed or stop requested; original kept: %s", source)
            return
        # Flush the verified output before deleting the source.
        with target.open("r+b") as stream:
            os.fsync(stream.fileno())
        source.unlink()
        LOG.info("Deleted verified original FLAC: %s", source)
    finally:
        Path(temporary).unlink(missing_ok=True)


def safe_name(value):
    value = re.sub(r'[\x00-\x1f/\\:*?"<>|]', "_", value)
    value = re.sub(r"\s+", " ", value).strip(" .") or "Unknown"
    while len(value.encode("utf-8")) > 230:
        value = value[:-1]
    return value


def album_name(files, fallback, ffprobe):
    tags = [{k.lower(): str(v).strip() for k, v in probe(p, ffprobe).get("format", {}).get("tags", {}).items()}
            for p in files]
    albums = {tag["album"] for tag in tags if tag.get("album")}
    if len(albums) > 1:
        return None  # A collection: name its individual album folders instead.
    album = next(iter(albums), fallback)
    artists = {tag.get("album_artist") or tag.get("albumartist") or tag.get("artist")
               for tag in tags}
    artists.discard(None)
    artist = next(iter(artists)) if len(artists) == 1 else "Various Artists" if artists else "Unknown Artist"
    years = []
    for tag in tags:
        for key in ("originaldate", "originalyear", "date", "year"):
            match = re.search(r"\b(\d{4})\b", tag.get(key, ""))
            if match:
                years.append(match.group(1))
                break
    year = max(sorted(set(years)), key=years.count) if years else "Unknown Year"
    return safe_name(f"({year}) - {album} - {artist}")


def save_names(state, names):
    temporary = state / "folder-names.json.tmp"
    temporary.write_text(json.dumps(names, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, state / "folder-names.json")


def finalize_folders(folder, names, state, ffprobe):
    """Rename completed album outputs and remember their destinations across restarts."""
    def finish(source):
        if STOP:
            return
        key = source.relative_to(folder).as_posix()
        target = output_directory(source, folder, names)
        if is_link(target) or not target.is_dir():
            return
        visible = []
        for directory, dirs, files in os.walk(source, followlinks=False):
            parent = Path(directory)
            dirs[:] = [d for d in dirs if not d.startswith(".") and not is_link(parent / d)]
            visible.extend(parent / f for f in files if not f.startswith(".") and not is_link(parent / f))
        # A failed, incomplete, or conflicting conversion keeps the folder pending.
        if any(p.suffix.lower() == ".flac" for p in visible):
            return
        if any(not (output_directory(p.parent, folder, names) / p.name).is_file() for p in visible):
            return
        mp3s = []
        for directory, dirs, files in os.walk(target, followlinks=False):
            parent = Path(directory)
            dirs[:] = [d for d in dirs if not d.startswith(".") and not is_link(parent / d)]
            mp3s.extend(parent / f for f in files if f.lower().endswith(".mp3") and not is_link(parent / f))
        if not mp3s:
            return
        if key in names:
            return
        name = album_name(mp3s, source.name, ffprobe)
        if name is None:
            for child in sorted(source.iterdir()):
                if child.is_dir() and not is_link(child) and not child.name.startswith("."):
                    finish(child)
            return
        renamed = target.with_name(name)
        # Never merge with or replace another existing album folder.
        number = 2
        while renamed != target and (renamed.exists() or is_link(renamed)):
            renamed = target.with_name(f"{name} ({number})")
            number += 1
        if renamed != target:
            target.rename(renamed)
            LOG.info("Renamed album folder: %s -> %s", target, renamed)
        names[key] = renamed.relative_to(folder / OUTPUT_FOLDER).as_posix()
        save_names(state, names)

    for source in sorted(folder.iterdir()):
        if source.name.startswith(".") or source.name == OUTPUT_FOLDER or is_link(source) or not source.is_dir():
            continue
        try:
            finish(source)
        except (OSError, RuntimeError, ValueError) as exc:
            LOG.error("Could not name album folder %s: %s", source, exc)


def main():
    global STOP_FILE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=INBOX)
    parser.add_argument("--once", action="store_true", help="Convert current files, then exit")
    parser.add_argument("--check", action="store_true", help="Check dependencies without converting")
    args = parser.parse_args()
    try:
        ffmpeg, ffprobe = media_tools()
    except RuntimeError as exc:
        parser.exit(1, str(exc) + "\n")
    if args.check:
        print("FFmpeg:", ffmpeg)
        print("FFprobe:", ffprobe)
        encoders = run_media([ffmpeg, "-hide_banner", "-encoders"])
        if "libmp3lame" not in encoders:
            parser.exit(1, "This FFmpeg build is missing the libmp3lame encoder.\n")
        run_media([ffprobe, "-version"])
        print("Dependencies OK. Album input folder:", args.folder.resolve())
        return 0
    folder = args.folder.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    state = folder / ".converter"
    state.mkdir(exist_ok=True)
    handler = RotatingFileHandler(state / "converter.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    lock = acquire_lock(state / "watcher.lock")
    if lock is None:
        print("A converter is already running for this folder.")
        return 0
    STOP_FILE = state / "stop.request"
    STOP_FILE.unlink(missing_ok=True)
    names_file = state / "folder-names.json"
    names = json.loads(names_file.read_text(encoding="utf-8")) if names_file.exists() else {}
    if not isinstance(names, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            or Path(key).is_absolute() or Path(value).is_absolute()
            or ".." in Path(key).parts or ".." in Path(value).parts
            for key, value in names.items()):
        raise SystemExit("Invalid folder-names.json; paths must stay inside the converter folder")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    LOG.info("Started watching %s", folder)
    observed = {}
    attempted = {}
    errors = 0
    while not STOP and not STOP_FILE.exists():
        try:
            PROBE_CACHE.clear()
            jobs = discover(folder, names)
            sources = {source for source, _ in jobs}
            observed = {p: value for p, value in observed.items() if p in sources}
            attempted = {p: value for p, value in attempted.items() if p in sources}
            for source, target in jobs:
                if STOP or STOP_FILE.exists():
                    stop(None, None)
                    break
                try:
                    current = signature(source)
                    if source.suffix.lower() != ".flac" and (target.exists() or is_link(target)):
                        # Allow a fresh conversion if the user later removes the MP3.
                        attempted.pop(source, None)
                        continue
                    previous, since = observed.get(source, (None, time.monotonic()))
                    if current != previous:
                        since = time.monotonic()
                        observed[source] = current, since
                    if not args.once and time.monotonic() - since < 4:
                        continue
                    if attempted.get(source) == current:
                        continue
                    attempted[source] = current
                    prepare_directory(target.parent, folder)
                    if source.suffix.lower() == ".flac":
                        convert(source, target, current, ffmpeg, ffprobe)
                    else:
                        copy_companion(source, target, current)
                except (OSError, RuntimeError, ValueError) as exc:
                    errors += 1
                    LOG.error("Could not convert %s: %s", source.name, exc)
            finalize_folders(folder, names, state, ffprobe)
        except OSError as exc:
            LOG.error("Cannot read folder: %s", exc)
        if args.once:
            break
        time.sleep(1)
    LOG.info("Stopped")
    lock.close()
    return 1 if args.once and errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
