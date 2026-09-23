# Fresh Windows PC setup

These steps are intended for a Windows 11 PC, using the 64-bit Python and FFmpeg builds. The code also works with compatible dependencies on Windows 10. For a Windows ARM PC, choose compatible Python/FFmpeg builds; the GitHub Windows tests use x64.

**The converter permanently deletes FLAC files from its Music Inbox after verifying their MP3s.** For your first test, copy one album into the inbox while keeping your original library elsewhere.

## 1. Install Python and FFmpeg

Open **Start → Terminal** or **PowerShell**. Run these commands one at a time:

```powershell
winget install --id Python.Python.3.13 --exact --source winget
winget install --id Gyan.FFmpeg.Essentials --exact --source winget
```

Accept the installers' prompts. Then **close Terminal and open it again** so it sees the updated PATH.

Verify the installation:

```powershell
py -3 --version
ffmpeg -version
ffprobe -version
```

Each should print a version. There are no Python packages to install with pip. Python 3.10 or newer is sufficient; the commands above select Python 3.13.

References: [Microsoft's WinGet installation command](https://learn.microsoft.com/en-us/windows/package-manager/winget/install), [Python's Windows installation guide](https://docs.python.org/3.13/using/windows.html), and the Microsoft package manifests for [Python](https://github.com/microsoft/winget-pkgs/tree/master/manifests/p/Python/Python/3/13) and [FFmpeg Essentials](https://github.com/microsoft/winget-pkgs/tree/master/manifests/g/Gyan/FFmpeg/Essentials).

### If WinGet is unavailable or you prefer manual installation

1. Install Python from [python.org](https://www.python.org/downloads/windows/). Choose a normal Windows installer, enable **Add python.exe to PATH** if that option is shown, and include the Python launcher. Follow the installer to completion.
2. Open [FFmpeg's official download page](https://ffmpeg.org/download.html). Under Windows, follow its link to [Gyan's builds](https://www.gyan.dev/ffmpeg/builds/).
3. Download the **release essentials ZIP**, then extract it. Its `bin` folder contains `ffmpeg.exe` and `ffprobe.exe`.
4. Either add that `bin` directory to your user PATH, or, after extracting Music Converter in the next step, create a folder named `tools` beside `converter.py` and copy those two executables into it. The `tools` method needs no PATH changes. Use the static essentials ZIP, not a shared build that needs additional DLLs.
5. Close and reopen Terminal. Check Python with `py -3 --version` or `python --version`. For local `tools` executables, the application's Check Setup button performs the FFmpeg check.

## 2. Download and extract Music Converter

1. Open [the GitHub repository](https://github.com/cadeKukk/music-converter).
2. Choose **Code → Download ZIP**.
3. Right-click the ZIP → **Extract All**. Do not run the program from inside the ZIP preview.
4. Move the extracted folder to a permanent location, for example:

```text
C:\Users\YourName\MusicConverter
```

A short path helps avoid Windows filename-length limits. Use a local NTFS drive, outside OneDrive or other synced folders. Do not use a FAT/exFAT USB drive as the working inbox: safe output publication requires hard-link support.

Inside the folder, you should see `converter.py`, `manage.py`, several `.cmd` buttons, `docs`, and `Music Inbox`. File Explorer may hide the `.cmd` extensions; look for the corresponding names with a gear-style icon. The `.command` files are for Macs.

## 3. Check the installation

Double-click **Check Setup.cmd**.

Expected result:

```text
Python: ...
FFmpeg: ...
FFprobe: ...
Dependencies OK. Album input folder: ...\Music Inbox
```

If an error appears, follow the troubleshooting section below before continuing. This check does not convert or delete music.

## 4. Start and test one album

1. Double-click **Start Converter.cmd**.
2. Wait for the message that the converter is running. You can then press a key and close the launcher; conversion continues in the background.
3. **Copy** one completed album folder into `Music Inbox`. If you want to keep your original lossless library, leave that library outside the inbox.
4. Wait while the MP3s are encoded and verified. The program waits four seconds before processing a stable file, then works through songs one at a time.
5. Open `Music Inbox\Converted MP3`.
6. After all tracks have converted and companion files are copied, the album folder will be named like:

```text
(1977) - Rumours - Fleetwood Mac
```

Disc subfolders and song filenames remain. The copied FLACs inside Music Inbox disappear after successful verification. Booklets/artwork and empty original folders may remain in the input area.

For large collections, put the whole collection in Music Inbox. Albums should be in their own subfolders with embedded album/year/artist tags. Files added later are picked up automatically.

## 5. Start automatically when you sign in (optional)

Double-click **Enable Login Startup.cmd**. This starts the converter now and creates a shortcut for your Windows account in its Startup folder. Administrator access is not required for this control.

The converter runs at future sign-ins without an open Terminal window. It does not run while you are signed out or while the PC is asleep.

To inspect the shortcut, press **Win+R**, enter `shell:startup`, and press Enter. Its name starts with `music-converter-` and includes an identifier for this installation.

- **Stop Converter.cmd** stops the current session. Login startup remains enabled.
- **Disable Login Startup.cmd** removes that installation's startup shortcut and stops the converter.
- **Converter Status.cmd** shows its current state.

## 6. Update, move, or remove it

**Update:** stop the converter, download a new copy, and replace the program files and buttons. Keep `Music Inbox` and its `.converter` state folder. Do not replace your existing Music Inbox with an empty one. If Python has changed locations, disable and re-enable login startup.

**Move:** disable login startup first, move the whole application folder, and enable it again from the new location. The shortcut records the application and Python locations.

**Remove:** disable login startup, move out any music you want to keep, then delete the application folder. Python and FFmpeg are separate installations and are not removed by this operation.

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| `winget` is not recognized | Use the manual installation steps, or install/update Microsoft's App Installer. |
| `py` or `python` is not recognized | Install Python, reopen Terminal, and check its version. The buttons try `py -3`, then `python`. |
| Python opens the Microsoft Store | Install Python from python.org and verify `py -3 --version`; a Store alias alone is not a Python installation. |
| FFmpeg/FFprobe is missing | Reopen the launcher after installation, or put both executables in `tools` beside `converter.py`. |
| Folder name contains Unknown | Add album, date/year, and album-artist tags before dropping the album in. There is no online tag lookup. |
| A FLAC stays in the inbox | Check the log. It may be corrupt, incomplete, or conflict with an existing MP3. It is kept when verification fails. |
| Existing MP3 does not match | Stop the converter, move that MP3 elsewhere, and restart to create a verified replacement. The existing file is never overwritten automatically. |
| Access denied or hard-link error | Use a writable local NTFS folder. Avoid a protected, synced, network, FAT, or exFAT location. |
| Path is too long | Use a shorter application path and shorter album/track filenames. |
| It stopped after reboot | Enable Login Startup, sign in, then check Converter Status. Re-enable startup if Python or the application moved. |
| Nothing happens | Run Check Setup, then Converter Status. Inspect both logs below. |

Logs are under `Music Inbox\.converter`: `converter.log` records conversions/deletions/errors, and `service.log` records background startup errors. Open them with Notepad. The state folder may require **View → Show → Hidden items** to be visible.

For a foreground diagnostic run, stop the background converter, open Terminal in the application folder, and run:

```powershell
py -3 converter.py
```

This performs real conversions and deletions in Music Inbox. Press Ctrl+C to stop. For a dependency-only check, use `py -3 manage.py check` instead.
