# Fresh Mac setup

The same Python program supports Apple Silicon and Intel Macs. This guide uses Homebrew to install its dependencies. Homebrew's current supported macOS versions are listed on [brew.sh](https://brew.sh/).

**Original FLACs placed in Music Inbox are permanently deleted after verified MP3 conversion.** Keep a separate lossless library if you want one.

## 1. Install dependencies

Install Homebrew using the instructions at [brew.sh](https://brew.sh/). Follow the installer's printed next steps, including its shell configuration instructions. Then open Terminal and run:

```sh
brew install python ffmpeg
python3 --version
ffmpeg -version
ffprobe -version
```

Python 3.10 or newer is required. No pip packages are needed. The launcher checks the usual Homebrew locations on both Apple Silicon and Intel Macs.

## 2. Download the program

Open [the repository](https://github.com/cadeKukk/music-converter), choose **Code → Download ZIP**, and extract the archive. Move the extracted folder to a permanent local location, such as `~/MusicConverter`.

Use a local APFS volume. FAT/exFAT removable drives and some network/cloud-backed folders do not provide the hard links used for safe publication.

## 3. Check and start

Double-click **Check Setup.command**, then **Start Converter.command**. The `.cmd` files are for Windows.

If Finder says the launcher is not executable, open Terminal, type `cd `, drag the extracted application folder into Terminal, press Return, then run:

```sh
chmod +x ./*.command
python3 manage.py check
python3 manage.py start
```

Review any macOS download/security prompt for the specific file you downloaded. You can use the Terminal commands above if Finder does not open the launcher. If macOS asks for folder access, grant access to the input/output location.

After the running message appears, close Terminal if you wish. Drop complete album folders into **Music Inbox** inside the application folder. Results appear in **Music Inbox/Converted MP3**. Completed albums use `(Release Year) - Album Name - Artist`; nested disc folders remain intact. Loose FLACs produce MP3s beside them.

The program deletes a source FLAC only after its MP3 passes decoding and duration checks. Failed files remain and are recorded in `Music Inbox/.converter/converter.log`.

## 4. Optional login startup

Double-click **Enable Login Startup.command**. It starts the converter now and installs a LaunchAgent for future logins at:

```text
~/Library/LaunchAgents/local.music-converter-<installation-id>.plist
```

This is per user and does not require sudo. The Mac must be awake and you must be signed in.

**Stop Converter.command** stops the current process; the next login still starts it. **Disable Login Startup.command** removes the LaunchAgent and stops the process. **Converter Status.command** reports both states.

## 5. Moving, updating, and removing

Disable login startup before moving the application or changing Python installations. Re-enable it from the new location afterward.

For updates, stop the converter and replace only program files/buttons. Preserve Music Inbox and its `.converter` folder, especially `folder-names.json`. If Homebrew removes the exact Python version recorded by the LaunchAgent, run Disable Login Startup and Enable Login Startup again using the current interpreter.

To uninstall, disable startup, move any music out, then delete the application folder. Python and FFmpeg remain installed separately.

If upgrading from the earlier Desktop-only converter, stop that installation with its original **Stop Converter.command** first. This repository uses a dedicated **Music Inbox** and its own startup controls. Do not run two versions against the same input. You can retain the earlier installation separately; installing this package does not modify it automatically.

## Troubleshooting

- **Missing FFmpeg/Python:** rerun the dependency installation and Check Setup.
- **Unknown year/artist:** tag the FLACs before conversion. Missing tags are not looked up online.
- **File retained:** inspect the error log. An incomplete source, decode error, or conflicting existing MP3 prevents deletion.
- **No activity:** use Converter Status and inspect `Music Inbox/.converter/service.log` for startup errors.
- **Hidden state/log files:** press Command-Shift-period in Finder to show hidden items.
- **One-time batch:** stop the watcher, then run `python3 converter.py --once` from the application folder. Only use this with complete input files; it skips the four-second settling delay.

Run the synthetic integration tests with:

```sh
python3 -m unittest discover -s tests -v
```
