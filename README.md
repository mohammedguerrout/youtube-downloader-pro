# 📥 YouTube Downloader PRO

A modern desktop YouTube downloader built in **Python** with **CustomTkinter**, capable of downloading video (with sound, at any available resolution) or audio-only, with a clean, responsive interface.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![CustomTkinter](https://img.shields.io/badge/GUI-CustomTkinter-3B8ED0)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ⚖️ Legal Notice

This application downloads content from YouTube for **personal, offline use only**. You are solely responsible for ensuring your use complies with YouTube's Terms of Service and all applicable copyright laws in your jurisdiction. Do not download or redistribute content you do not have the right to use. This notice is also shown inside the app on first launch.

---

## 📑 Table of Contents

- [✨ Features](#-features)
- [🛠️ How video quality actually works](#️-how-video-quality-actually-works)
- [🚀 Installation](#-installation)
- [▶️ Usage](#️-usage)
- [📂 Project structure](#-project-structure)
- [🧪 Running tests](#-running-tests)
- [📦 Building a standalone executable](#-building-a-standalone-executable)
- [🗺️ Known limitations / roadmap](#️-known-limitations--roadmap)
- [📜 License](#-license)

---

## ✨ Features

- 🎬 Download video (with sound) or 🎵 audio-only, optionally **converted to MP3**
- Automatic selection of the best available quality, **including resolutions YouTube no longer offers as a single combined file** (720p, 1080p, etc.) — handled via automatic video+audio merging, with ffmpeg bundled automatically (see below)
- 🔍 **Search YouTube directly in the app** — no need to find and copy a link first
- 📃 **Download entire playlists**, with a checklist to pick exactly which videos to include
- 📥 **Background download queue** — add as many videos as you like (from Download, Search, or Playlist) and they're processed one after another, with a live progress bar and a Cancel button per job
- 📝 Optional **subtitle (.srt) download**, alongside the video
- 🕘 **In-app download history** — every completed file, with one click to open its folder
- Live progress bar with download speed, accurate across every phase (video, audio, merge, MP3 conversion)
- Video info preview: title, author, duration, thumbnail
- Clipboard auto-paste for YouTube links
- Dark / Light / System appearance modes
- Settings (folder, appearance, mode, quality, MP3/subtitles toggles) persisted between sessions
- Clear, human-readable error messages instead of raw exceptions
- First-run legal disclaimer
- Full logging to a local file for troubleshooting

---

## 🛠️ How video quality actually works

Modern YouTube rarely provides a single file containing **both** video and audio above 360p. This app handles that automatically, **with zero setup required**:

1. If a combined (progressive) file exists at the requested quality → downloaded directly (fast).
2. Otherwise → the video-only and audio-only streams are downloaded separately and **merged into one file using ffmpeg**.
3. Unlike most downloaders, you never have to install ffmpeg yourself: the [`imageio-ffmpeg`](https://pypi.org/project/imageio-ffmpeg/) package (listed in `requirements.txt`, installed the normal way via `pip install -r requirements.txt`) bundles a small, self-contained ffmpeg binary automatically — no download page, no `PATH` configuration, no separate installer.
4. On the rare occasion this bundled binary isn't ready (e.g. no internet access at all on the very first run), the app falls back to the best combined quality available (usually 360p) rather than silently producing a file with no sound — a warning appears in the sidebar only in that case.

---

## 🚀 Installation

```bash
git clone https://github.com/mohammedguerrout/youtube-downloader-pro.git
cd youtube-downloader-pro

python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

pip install -r requirements.txt
python main.py
```

---

## ▶️ Usage

All shared settings (download type, quality, MP3/subtitles toggles, destination folder) live in the **sidebar** and apply to every tab.

- **⬇️ Download** — paste a URL (or click 📋 to auto-paste from clipboard), click **Fetch** to preview it, then **Add to Queue**.
- **🔍 Search** — type a search term, browse results with thumbnails, click **➕ Add** on any of them.
- **📃 Playlist** — paste a playlist URL, click **Load**, pick which videos to include, then **Add Selected to Queue**.
- **📥 Queue** — see every job's live progress; **✖** cancels a pending or running job.
- **🕘 History** — every completed download, with a shortcut to open its folder.

---

## 📂 Project structure

```
youtube-downloader-pro/
│
├── main.py                 # Entry point
├── config.py                 # Settings persistence, logging, constants
├── utils.py                    # Pure helper functions (fully unit-tested)
├── youtube_service.py            # All pytubefix/ffmpeg logic — no GUI code
├── queue_manager.py                # Background download queue (worker thread + job lifecycle)
├── history.py                        # Persisted in-app download history
│
├── gui/
│   ├── main_window.py                   # Shell: sidebar settings + tab view
│   ├── download_tab.py                    # Single-URL download
│   ├── search_tab.py                        # In-app YouTube search
│   ├── playlist_tab.py                        # Playlist loading + selection
│   ├── queue_tab.py                              # Live queue view
│   └── history_tab.py                              # Download history view
│
├── assets/
│   ├── icon.ico                        # Windows app icon
│   └── icon.png                          # Cross-platform app icon
│
├── tests/
│   ├── test_utils.py                        # Unit tests for utils.py
│   ├── test_youtube_service.py                # Unit tests for stream selection logic
│   ├── test_queue_manager.py                    # Unit tests for the queue's job lifecycle
│   └── test_captions.py                           # Unit tests for subtitle selection logic
│
├── build.spec                 # PyInstaller build configuration
├── requirements.txt
├── requirements-dev.txt         # + pytest, pyinstaller
├── README.md
├── LICENSE
└── .gitignore
```

**Architecture principle:** `youtube_service.py` contains zero GUI code and `gui/main_window.py` contains zero direct `pytubefix` calls. This separation is what makes the stream-selection logic (the exact code that caused the original "video won't download" bug) fully unit-testable without needing a live internet connection — see `tests/test_youtube_service.py`.

---

## 🧪 Running tests

```bash
pip install -r requirements-dev.txt
pytest -v
```

41 tests cover: filename sanitization, file-size/duration formatting, the exact stream-selection logic for every real-world scenario (progressive-only, adaptive-only, resolution-specific lookups, webm-only fallback), subtitle-track selection/fallback, and the download queue's full job lifecycle (success, cancellation while pending, cancellation while downloading, and — importantly — that one failed job never stops the rest of the queue) — all using fakes modeled directly on pytubefix's own source code, so nothing here needs network access to run.

---

## 📦 Building a standalone executable

```bash
pip install -r requirements-dev.txt
pyinstaller build.spec
```

The executable will be in `dist/`. It bundles CustomTkinter's theme files and the app icon automatically.

---

## 🗺️ Known limitations / roadmap

Honest list of what this version does **not** yet do, kept here instead of silently omitted:

- ❌ No desktop notification when a download finishes
- ❌ No drag-and-drop URL support
- ❌ No parallel downloads (the queue is intentionally sequential — one job at a time — to avoid competing for bandwidth/disk I/O)
- ❌ No subtitle language picker (automatically prefers English, then whatever is available)
- ❌ Playlist entries show as "Video 1, Video 2, ..." until their own download starts (their real titles aren't pre-fetched, to keep loading a large playlist fast)

These are reasonable next features if the project continues to grow.

---

## 📜 License

MIT — see [LICENSE](LICENSE). Note the additional usage notice regarding YouTube's Terms of Service.

---

## 👤 Author

**Mohammed Guerrout**
