# 📦 LitterWatch

**Automatic image uploader for [Litterbox](https://litterbox.catbox.moe) — watches a folder, uploads instantly, copies the link.**

Built by [Killoxs](https://killoxs.com) as an open-source desktop utility for anyone who screenshots, saves, or exports images and wants a shareable link without lifting a finger.

---

## What it does

Drop an image into your watched folder — LitterWatch detects it, uploads it to Litterbox in the background, and copies the URL straight to your clipboard. No browser, no drag-and-drop, no manual steps.

- Monitors any local folder for new image files
- Uploads silently using Python's built-in networking (no `curl`, no terminal popups)
- Copies the Litterbox link to clipboard the moment it's ready
- Lets you choose how long the file lives: 1h / 12h / 24h / 72h
- Shows a live log with colour-coded status per upload
- Retries automatically on failure with WAF-aware backoff

---

## Preview

```
KILLOXS × LITTERBOX                              ● LIVE

WATCH FOLDER
[ C:/Users/you/Screenshots                  ] [ BROWSE ]

EXPIRY
[ 1h ]  [ 12h ]  [ 24h ]  [■ 72h ]

[ ▶  START ]  [ ■  STOP ]

OK  3    FAIL  0    QUEUED  0

LOG
[14:02:11] INIT C:/Users/you/Screenshots
[14:02:11] CONF expiry=72h
[14:02:44] SCAN screenshot_001.png
[14:02:44] UP   screenshot_001.png  [72h]
[14:02:46] OK   https://litter.catbox.moe/xxxxxx.png
[14:02:46] CLIP link copied
```

---

## Requirements

- Windows 10 / 11
- Python 3.10 or later — [python.org](https://www.python.org/downloads/)

---

## Installation

```bash
git clone https://github.com/killoxs/litterwatch.git
cd litterwatch
py -m pip install watchdog pyperclip
py killoxs_litterbox.py
```

---

## Build a standalone `.exe`

If you want a single executable with no Python dependency:

1. Put `killoxs_litterbox.py` and `build.bat` in the same folder
2. Double-click `build.bat`
3. Your exe will appear at `dist\KilloxsLitterbox.exe`

The build script handles installing PyInstaller and bundling everything automatically.

---

## Usage

1. Launch the app
2. Click **BROWSE** and pick the folder you want to monitor
3. Select an expiry duration (default: 72h)
4. Click **▶ START**

From this point, any image saved into that folder is uploaded automatically. The link is copied to your clipboard and logged in the event panel.

To stop, click **■ STOP** or close the window.

---

## Supported formats

`.png` `.jpg` `.jpeg` `.gif` `.bmp` `.webp`

---

## How uploads work

LitterWatch uses Python's built-in `urllib` to POST directly to the Litterbox API — no `curl`, no subprocess, no command window ever appears. Uploads include browser-like headers to pass Litterbox's WAF layer (BunkerWeb). On failure it retries up to 5 times with increasing delays.

---

## Project structure

```
litterwatch/
├── killoxs_litterbox.py   # main application
├── build.bat              # one-click Windows exe builder
└── README.md
```

---

## Dependencies

| Package | Purpose |
|---|---|
| [watchdog](https://github.com/gorakhargosh/watchdog) | Folder monitoring |
| [pyperclip](https://github.com/asweigart/pyperclip) | Clipboard access |

Both are pip-installable. The rest of the app uses Python's standard library only.

---

## License

MIT License — free to use, modify, and distribute.

---

## Credits

Made by [Killoxs](https://killoxs.com) · hello@killoxs.com · 2026
