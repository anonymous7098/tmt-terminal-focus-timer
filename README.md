# 🍅 TMT — Terminal Focus Timer

**A beautiful, lightweight focus timer that lives in your terminal.**

TMT combines a Pomodoro-style timer with ambient music, six color themes, eight interface languages, minimalist mode, and a motivational quote after every deep-work session. Everything runs locally — no accounts, no telemetry, no network requests.

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
![pygame](https://img.shields.io/badge/pygame-2.5%2B-56d698)
![colorama](https://img.shields.io/badge/colorama-0.4.6%2B-ff7a66)
[![MIT License](https://img.shields.io/badge/license-MIT-0d1117)](LICENSE)

---

## ✨ Features

- ⏱️ **Focus / break sessions** — 25/5 by default; focus is configurable from 1–180 minutes, breaks from 1–60.
- 🎵 **Automatic music discovery** — scans the project folder for `.mp3`, `.wav`, `.ogg`, and `.flac` files.
  - Play one track on repeat.
  - Shuffle a random track whenever the current one ends.
  - Disable music with option `0`.
  - Music pauses with the timer, fades out when a session ends, and stops instantly on quit.
- 🌍 **Eight languages** — English, Ukrainian, Russian, Spanish, German, French, Italian, Portuguese.
- 🎨 **Six color themes** — Hacker Green, Cyberpunk Neon, Monochrome Classic, Sunset Amber, Ocean Blue, Rose Quartz.
- 💬 **50 motivational quotes** — a localized quote is typed out smoothly after every completed focus session.
- 🖥️ **Two interface modes** — a full dashboard with large digits, or a one-line minimalist timer.
- 📊 **Local statistics** — daily sessions and focused minutes in a human-readable `stats.txt`.
- ⚡ **Lightweight by design** — standard library plus `colorama`; `pygame` is imported only when music is enabled.
- 🔔 **Completion sound** — a short melody on Windows, a terminal bell elsewhere.
- 🔒 **Offline and private** — no API keys, no tokens, no analytics.

---

## 📦 Requirements

- **Python 3.9+** on Windows, macOS, or Linux
- `colorama` and `pygame` (installed from `requirements.txt`)
- A terminal with Unicode support; **Windows Terminal** is recommended on Windows
- Optional: audio files placed in the project folder

---

## 🚀 Installation & Quick Start

```bash
# 1. Install dependencies
python -m pip install -r requirements.txt

# 2. Start the timer
python main.py
```

On Windows, `py` can be used instead of `python`:

```powershell
py -m pip install -r requirements.txt
py main.py
```

On first launch, TMT asks for:

1. **Language**
2. **Color theme**
3. **Music** (found tracks, shuffle, or `0` to disable)
4. **Focus / break duration**
5. **Interface mode** (full or minimalist)

Press `Enter` to accept a default. After setup, press `Space` to pause, and `Q` to quit.

> [!TIP]
> To skip the menus, pass CLI options. For example:
> ```bash
> python main.py --lang en --theme cyberpunk --work 50 --break 10 --music shuffle --minimal
> ```

---

## ▶️ What a session looks like

```text
                ╭──────────────────────────────────────────────╮
                │ 🎯  TMT · FOCUS TIMER             Session #3 │
                ├──────────────────────────────────────────────┤
                │                                              │
                │                  🍅  FOCUS                   │
                │             █  █  █      █▀▀█ █▀▀█           │
                │             █  █  █  ██  █  █ █  █           │
                │             █  █▄▄█      █  █ █  █           │
                │             █     █  ██  █  █ █  █           │
                │             █     █      █▄▄█ █▄▄█           │
                │                                              │
                │     █████████████▏░░░░░░░░░░░░░░░░   44%     │
                │                11:00 of 25:00                │
                ╰──────────────────────────────────────────────╯
                            Space — pause · Q — quit
```

When the session ends, TMT:

1. fades the music out,
2. plays the completion sound,
3. saves the session to `stats.txt`,
4. shows a completion notice and today's focus total,
5. types out a motivational quote,
6. offers a break and another session.

Minimalist mode reduces the live timer to a single line:

```text
  🍅 14:00  ███████████▉░░░░░░░   44%
```

---

## 🎵 Music

TMT recursively scans the folder containing `main.py` (or the `.exe`) and lists every supported audio file it finds. The recommended layout is a `Music/` folder next to the app:

```text
TMT/
├── main.py
└── Music/
    ├── ambient1.mp3
    ├── ambient2.mp3
    └── lofi1.mp3
```

The folder name is not important and nested folders work too — every audio file in the project is discovered automatically. The path shown in the menu is relative to the project, e.g. `Music/lofi1.mp3`.

| Format | Support |
| :--- | :--- |
| `.mp3` | ✅ |
| `.wav` | ✅ |
| `.ogg` | ✅ |
| `.flac` | ✅ (depends on the SDL_mixer build) |

**Menu behavior**

| Choice | Result |
| :--- | :--- |
| `0` | Music disabled |
| `1 … N` | The selected track loops for the whole focus session |
| Last option | Shuffle: a new random track starts when the previous one ends |

**Playback details**

- Music starts with the focus timer, not during setup.
- Pausing the timer pauses the music.
- Completing a session fades the music out over 700 ms.
- Pressing `Q` or `Ctrl+C` stops playback immediately.
- If `pygame` or an audio device is unavailable, TMT warns you and continues silently.
- Audio files are **not** bundled into the executable; copy the whole `Music/` folder next to `TMT.exe`.

> TMT works without music. The `.gitignore` excludes audio files inside `Music/` by default so the first push to GitHub stays small and copyright-safe. Remove those rules only if you own the rights and want to publish the soundtrack.

---

## 🌍 Languages

| Code | Language | Flag |
| :---: | :--- | :---: |
| `en` | English | 🇬🇧 |
| `uk` | Українська | 🇺🇦 |
| `ru` | Русский | 🇷🇺 |
| `es` | Español | 🇪🇸 |
| `de` | Deutsch | 🇩🇪 |
| `fr` | Français | 🇫🇷 |
| `it` | Italiano | 🇮🇹 |
| `pt` | Português | 🇵🇹 |

The entire interface — menus, timer labels, notices, statistics, shortcuts, and quotes — follows the selected language. Use `--lang <code>` to bypass the language menu.

---

## 🎨 Themes

| Name | CLI key |
| :--- | :--- |
| Hacker Green | `hacker` |
| Cyberpunk Neon | `cyberpunk` |
| Monochrome Classic | `mono` |
| Sunset Amber | `sunset` |
| Ocean Blue | `ocean` |
| Rose Quartz | `rose` |

Each theme recolors accents, borders, the timer digits, the progress bar, notices, and statistics. Select a theme interactively, or use `--theme <key>`.

---

## 🎮 Controls

| Key | Action |
| :--- | :--- |
| `Enter` | Accept the default choice |
| `Space` / `P` | Pause or resume the timer and music |
| `Q` | Quit (an interrupted focus session is not saved) |
| `Y` / `N` | Answer yes/no prompts |
| `Ctrl+C` | Emergency exit; restores the cursor and stops music |
| `0` | Disable music in the music menu |

Russian and Ukrainian keyboard layouts are supported for the pause and quit keys.

---

## 📊 Statistics

Completed focus sessions are appended to `stats.txt`, next to `main.py` (or next to the executable). Breaks and interrupted sessions are not counted.

```text
# TMT session log (ISO timestamp;minutes)
2026-10-21T09:15:42;25
2026-10-21T09:52:10;25
2026-10-21T11:03:07;50
```

View a formatted summary:

```bash
python main.py --stats
python main.py --stats --lang de
```

- Delete `stats.txt` to reset the statistics.
- Set the `TMT_STATS` environment variable to store the file elsewhere.
- Malformed lines are skipped safely; the rest of the file is preserved.

> TMT shows today's focus total at startup and after every session.

---

## ⚙️ Command-line options

| Option | Description |
| :--- | :--- |
| `--lang {en,uk,ru,es,de,fr,it,pt}` | Interface language |
| `--theme {hacker,cyberpunk,mono,sunset,ocean,rose}` | Color theme |
| `-w, --work MIN` | Focus duration, 1–180 minutes |
| `-b, --break MIN` | Break duration, 1–60 minutes |
| `--music FILE\|shuffle\|off` | Loop a file, shuffle the folder, or disable music |
| `--minimal` | Use the minimalist one-line timer |
| `--stats` | Print statistics and exit |
| `--no-color` | Disable ANSI colors |
| `--silent` | Disable completion sounds |
| `--version` | Show the version |
| `-h, --help` | Show help |

Examples:

```bash
# Classic 25/5 with the full dashboard
python main.py

# Deep work with a specific soundtrack
python main.py --work 50 --break 10 --music "Music/deep-focus.mp3"

# Non-interactive minimalist session
python main.py --lang en --theme hacker --work 25 --break 5 --music off --minimal

# Statistics in Spanish
python main.py --stats --lang es
```

---

## 🏗️ Build a standalone `.exe` (Windows)

PyInstaller can package TMT and its dependencies into a single executable.

```powershell
# 1. Install the runtime dependencies and PyInstaller
py -m pip install -r requirements.txt
py -m pip install pyinstaller

# 2. Build a one-file console executable
py -m PyInstaller --onefile --clean --name TMT main.py
```

The result is `dist\TMT.exe`.

**After building:**

- Copy the entire `Music/` folder next to `dist\TMT.exe`; TMT scans the executable's folder.
- Statistics are written next to the `.exe` (`stats.txt`), so place it in a writable folder.
- For a portable variant, keep `TMT.exe`, `Music\`, and the docs together in one folder (or distribute a ZIP).
- If pygame's native libraries are not picked up automatically, rebuild with:
  ```powershell
  py -m PyInstaller --onefile --clean --name TMT --collect-all pygame main.py
  ```
- Windows SmartScreen may warn about unsigned executables. That is expected for local builds.
- Antivirus false positives can occur with PyInstaller one-file executables; building without `--onefile` is a common alternative.

The build artifacts (`build/`, `dist/`, `*.spec`) are already ignored by `.gitignore`.

---

## 🐙 Publish on GitHub

This folder is ready for its first repository. Only source and documentation need to go to GitHub; local audio, statistics, and the compiled `.exe` stay out of the repository.

### What is uploaded

| Included in Git | Kept local only |
| :--- | :--- |
| `main.py`, `README.md`, `LICENSE`, `requirements.txt`, `.gitignore` | Audio files inside `Music/` |
| `Music/README.md` (folder instructions) | `stats.txt` |
| | `build/`, `dist/`, `*.spec` |
| | `.venv/`, `venv/`, editor files |

The pre-filled `.gitignore` already excludes all of the local-only items. To publish the soundtrack too, you must own the rights; remove the `Music/` rules from `.gitignore` and add the files explicitly.

### Option A — GitHub Desktop (easiest)

1. Create a free account at [github.com](https://github.com) and install [GitHub Desktop](https://desktop.github.com/).
2. Open GitHub Desktop and sign in.
3. Choose **File → Add local repository** and select this folder: `D:\TMT - Terminal Focus Timer`.
   - If GitHub Desktop says it is not a repository yet, choose **create a repository** and confirm the folder.
   - Do **not** initialize it with a new README, `.gitignore`, or license — those files already exist.
4. Open the **Changes** tab. You should see `main.py`, `README.md`, `LICENSE`, `requirements.txt`, `.gitignore`, and `Music/README.md`. You should **not** see the `.mp3` files, `stats.txt`, `dist/`, or `build/`.
5. Enter the summary `Initial commit: TMT — Terminal Focus Timer`, then click **Commit to main**.
6. Click **Publish repository**, choose a name such as `tmt-terminal-focus-timer`, select **Public** or **Private**, and publish.

That is all — GitHub Desktop creates the remote repository and pushes the commit.

### Option B — Git in PowerShell

First create an **empty** repository on GitHub: **New repository → do not add README/.gitignore/license → Create repository**. Then copy its HTTPS URL and run:

```powershell
cd "D:\TMT - Terminal Focus Timer"

git init
git add .
git status                  # Music/*.mp3, dist/, stats.txt must NOT be listed
git commit -m "Initial commit: TMT — Terminal Focus Timer"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/tmt-terminal-focus-timer.git
git push -u origin main
```

If Git asks who you are:

```powershell
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

When asked for a password, use the browser sign-in window from Git Credential Manager — **do not type your GitHub password into the terminal**. If anything feels confusing, use GitHub Desktop instead.

> Avoid the GitHub website's drag-and-drop upload for this project: the web uploader does not apply `.gitignore`, so it is easy to add the large audio files or the `.exe` by accident. GitHub Desktop or Git is safer.

### Publish the `.exe` as a Release

Do **not** commit `dist/TMT.exe`; binaries are intentionally ignored and releases are the right place for them.

1. Push the repository first.
2. Open the repository on GitHub → **Releases → Draft a new release**.
3. Tag it `v2.0.0`, add a title, and attach `dist/TMT.exe`.
4. Publish the release.
5. Optionally attach a ZIP containing `TMT.exe` and `Music/` **only if you have the rights to share that audio**.

GitHub may show a SmartScreen warning for unsigned executables. That is normal for a locally built `.exe`.

---

## 🗂️ Project structure

```text
.
├── main.py             # Entire application: i18n, UI, timers, music, quotes, stats
├── README.md           # This document
├── LICENSE             # MIT License
├── requirements.txt    # colorama, pygame
├── .gitignore          # stats, audio, virtualenvs, build artifacts
├── Music/
│   ├── README.md       # Tracked folder instructions
│   └── *.mp3           # Local soundtrack (auto-discovered, ignored by Git)
├── stats.txt           # Created locally after the first session (ignored)
└── dist/               # Optional local PyInstaller build (ignored)
    ├── TMT.exe
    └── Music/
```

TMT is intentionally a **single-file application**. No package layout, plugin system, or configuration directory is required.

---

## 🧠 How it works

- The countdown uses `time.monotonic()`, so changing the system clock cannot corrupt a session.
- The display redraws roughly once per second; while paused it is static, keeping CPU usage negligible.
- `colorama` provides Windows-safe ANSI colors; colors automatically turn off when output is redirected or `NO_COLOR` is set.
- `pygame.mixer` is imported lazily and only if music is enabled.
- Music is discovered with a recursive walk that skips virtualenvs, Git internals, and build directories.
- Quotes and translations are embedded in `main.py`; there are no external data files or downloads.
- Completed sessions are appended to a simple semicolon-separated log.

---

## 🛠️ Troubleshooting

<details>
<summary><b>Music does not play</b></summary>

- Verify that `pygame` is installed: `python -m pip show pygame`.
- Check that your audio files are `.mp3`, `.wav`, `.ogg`, or `.flac`.
- Make sure the file is not corrupted and that a working audio output device exists.
- Try selecting a different track, or run TMT without music using `--music off`.
- When using the `.exe`, copy music next to the executable, not inside the PyInstaller bundle.
</details>

<details>
<summary><b>Emoji or box drawing looks broken</b></summary>

Use a modern terminal such as **Windows Terminal**, iTerm2, GNOME Terminal, Kitty, or Alacritty, with a font that supports Unicode and emoji (for example Cascadia Mono or JetBrains Mono). On older consoles, try `--no-color` and the minimalist mode.
</details>

<details>
<summary><b>Stats cannot be saved</b></summary>

TMT needs write access to the folder containing `main.py` or `TMT.exe`. Move the app to a writable directory, or set `TMT_STATS` to a writable file path.
</details>

<details>
<summary><b>Keyboard shortcuts do not work</b></summary>

Pause and quit keys require an interactive terminal (`stdin` must be a TTY). When input is piped, TMT runs the timer in a non-interactive, plain-text mode.
</details>

<details>
<summary><b>PyInstaller build has no audio or crashes</b></summary>

Rebuild with `--collect-all pygame`. Also ensure the executable is run from a folder containing the music files, and try a folder build instead of `--onefile` while debugging.
</details>

<details>
<summary><b>I want to reset my progress</b></summary>

Delete `stats.txt` (or the file pointed to by `TMT_STATS`) and start a new session.
</details>

---

## 🔒 Privacy & security

- **No network activity.** TMT never contacts a server.
- **No credentials.** There are no API keys, tokens, or secret configuration files.
- **No telemetry.** Usage data is never collected or transmitted.
- **Local-only data.** Statistics stay in `stats.txt` on your machine.
- **Auditable code.** The entire application is in one readable file.
- **Minimal dependencies.** Only `colorama` and `pygame` are required.

You can publish this repository without hiding keys or scrubbing secrets.

---

## 📄 License

Released under the [MIT License](LICENSE).

<div align="center">

**Focus deeply. Rest deliberately. Repeat.** 🍅

</div>
