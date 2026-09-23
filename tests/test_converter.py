import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import converter
from runtime import acquire_lock, media_tools

FFMPEG, FFPROBE = media_tools()


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="music converter ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        converter.STOP = False
        converter.STOP_FILE = None
        converter.PROBE_CACHE.clear()

    def audio(self, name, album="Example Album", artist="Example Artist", year="2001", tone=440):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        command = [FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"sine=frequency={tone}:duration=1", "-c:a", "flac"]
        for key, value in (("album", album), ("album_artist", artist), ("date", year)):
            if value:
                command += ["-metadata", f"{key}={value}"]
        subprocess.run(command + [str(path)], check=True)
        return path

    def once(self, ok=True):
        result = subprocess.run([sys.executable, str(APP / "converter.py"), "--folder", str(self.root), "--once"])
        self.assertEqual(result.returncode, 0 if ok else 1)

    def test_album_tree_deletion_naming_and_restart(self):
        source = self.audio("Drop/Disc 1/Track.FLAC")
        (self.root / "Drop/Notes.txt").write_text("Booklet", encoding="utf-8")
        (self.root / "Drop/Empty").mkdir()
        self.once()
        output = self.root / "Converted MP3/(2001) - Example Album - Example Artist"
        target = output / "Disc 1/Track.mp3"
        self.assertTrue(target.exists())
        self.assertFalse(source.exists())
        self.assertTrue((output / "Empty").is_dir())
        self.assertEqual((output / "Notes.txt").read_text(), "Booklet")
        data = converter.probe(target, FFPROBE)
        self.assertEqual(data["streams"][0]["codec_name"], "mp3")
        self.assertEqual(data["streams"][0]["bit_rate"], "320000")
        later = self.audio("Drop/Disc 2/Later.flac")
        self.once()
        self.assertFalse(later.exists())
        self.assertTrue((output / "Disc 2/Later.mp3").exists())
        self.assertFalse((self.root / "Converted MP3/Drop").exists())

    def test_existing_mp3_requires_matching_audio(self):
        source = self.audio("Song.flac")
        self.once()
        target = source.with_suffix(".mp3")
        original = target.read_bytes()
        self.audio("Song.flac")
        self.once()
        self.assertFalse(source.exists())
        self.assertEqual(target.read_bytes(), original)
        self.audio("Song.flac", tone=880)
        self.once(ok=False)
        self.assertTrue(source.exists())
        self.assertEqual(target.read_bytes(), original)

    def test_corrupt_source_and_destination_keep_originals(self):
        (self.root / "broken.flac").write_bytes(b"not audio")
        source = self.audio("existing.flac")
        source.with_suffix(".mp3").write_bytes(b"not mp3")
        self.once(ok=False)
        self.assertTrue(source.exists())
        self.assertTrue((self.root / "broken.flac").exists())
        self.assertFalse((self.root / "broken.mp3").exists())
        self.assertFalse(list(self.root.rglob(".converting-*")))

    def test_truncated_or_changed_sources_are_not_deleted(self):
        source = self.audio("incomplete.flac")
        original = source.read_bytes()
        packets = json.loads(subprocess.check_output([FFPROBE, "-v", "error", "-show_packets", "-show_entries", "packet=pos", "-of", "json", str(source)]))["packets"]
        source.write_bytes(original[:int(packets[-3]["pos"])])
        self.once(ok=False)
        self.assertTrue(source.exists())
        self.assertFalse(source.with_suffix(".mp3").exists())
        source.write_bytes(original)
        validate = converter.validate_conversion
        def change_source(*args):
            result = validate(*args)
            stamp = source.stat().st_mtime_ns
            os.utime(source, ns=(stamp + 1_000_000_000, stamp + 1_000_000_000))
            return result
        from unittest.mock import patch
        with patch.object(converter, "validate_conversion", change_source):
            converter.convert(source, source.with_suffix(".mp3"), converter.signature(source), FFMPEG, FFPROBE)
        self.assertTrue(source.exists())
        self.assertFalse(source.with_suffix(".mp3").exists())

    def test_collections_unicode_fallbacks_and_collisions(self):
        self.audio("Collection/A/Track.flac", album="Alpha")
        self.audio("Collection/B/Track.flac", album="Beta")
        self.audio("Missing/Track.flac", album="", artist="", year="")
        self.audio("Same 1/Track.flac", album="Café 東京")
        self.audio("Same 2/Track.flac", album="Café 東京")
        self.once()
        out = self.root / "Converted MP3"
        self.assertTrue((out / "Collection/(2001) - Alpha - Example Artist/Track.mp3").exists())
        self.assertTrue((out / "Collection/(2001) - Beta - Example Artist/Track.mp3").exists())
        self.assertTrue((out / "(Unknown Year) - Missing - Unknown Artist/Track.mp3").exists())
        self.assertTrue((out / "(2001) - Café 東京 - Example Artist (2)/Track.mp3").exists())

    def test_output_is_never_reprocessed(self):
        output_source = self.audio("Converted MP3/Leave.flac")
        self.once()
        self.assertTrue(output_source.exists())
        self.assertFalse(output_source.with_suffix(".mp3").exists())

    def test_lock_excludes_second_watcher(self):
        path = self.root / "watcher.lock"
        first = acquire_lock(path)
        self.assertIsNotNone(first)
        try:
            self.assertIsNone(acquire_lock(path))
        finally:
            first.close()
        again = acquire_lock(path)
        self.assertIsNotNone(again)
        again.close()

    def test_background_start_stop_and_windows_launchers(self):
        package = self.root / "App with spaces"
        package.mkdir()
        for name in ("converter.py", "runtime.py", "manage.py", "Check Setup.cmd"):
            shutil.copy2(APP / name, package / name)
        def manage(action):
            subprocess.run([sys.executable, str(package / "manage.py"), action], check=True, timeout=25)
        manage("check")
        if os.name == "nt":
            subprocess.run(["cmd.exe", "/c", str(package / "Check Setup.cmd")], input="\n", text=True, check=True, timeout=25)
        manage("start")
        try:
            source = self.audio("App with spaces/Music Inbox/Live/Track.flac")
            target = package / "Music Inbox/Converted MP3/(2001) - Example Album - Example Artist/Track.mp3"
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline and not target.exists():
                time.sleep(.2)
            self.assertTrue(target.exists())
            self.assertFalse(source.exists())
            manage("start")  # Idempotent; no duplicate process.
        finally:
            manage("stop")
        lock = acquire_lock(package / "Music Inbox/.converter/watcher.lock")
        self.assertIsNotNone(lock)
        lock.close()
        if os.name == "nt":
            try:
                manage("enable-login")
                shortcut = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup" / ("music-converter-" + hashlib.sha256(str(package.resolve()).encode()).hexdigest()[:12] + ".lnk")
                self.assertTrue(shortcut.exists())
            finally:
                manage("disable-login")


if __name__ == "__main__":
    unittest.main()
