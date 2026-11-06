#!/usr/bin/env python3
"""Make a throwaway inbox with a synthetic tagged album, for trying the converter safely.

Usage:
    python3 docs/make_demo_inbox.py /tmp/demo-inbox
    python3 converter.py --folder /tmp/demo-inbox --once

The tracks are generated sine tones, so nothing of value is deleted. The folder must
not exist yet.
"""
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from runtime import media_tools  # noqa: E402

ALBUM = "Synthetic Tones"
ARTIST = "Test Signal Ensemble"
YEAR = "2024"
TRACKS = [("Disc 1", "01 A440.flac", 440), ("Disc 1", "02 E659.flac", 659),
          ("Disc 2", "01 C523.flac", 523)]


def run(command):
    subprocess.run(command, check=True)


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    inbox = Path(sys.argv[1])
    if inbox.exists():
        raise SystemExit(f"{inbox} already exists; pick a new folder")
    ffmpeg, _ = media_tools()
    album = inbox / "Synthetic Tones (rip)"
    for disc, name, frequency in TRACKS:
        (album / disc).mkdir(parents=True, exist_ok=True)
        run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration=3",
             "-ac", "2", "-metadata", f"title={Path(name).stem[3:]}", "-metadata", f"album={ALBUM}",
             "-metadata", f"album_artist={ARTIST}", "-metadata", f"artist={ARTIST}",
             "-metadata", f"date={YEAR}", str(album / disc / name)])
    run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=300x300", "-frames:v", "1",
         str(album / "cover.jpg")])
    # A loose FLAC with no tags: its MP3 is written beside it.
    run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=330:duration=2", "-ac", "2",
         str(inbox / "loose track.flac")])
    print(f"Demo inbox ready: {inbox}")


if __name__ == "__main__":
    main()
