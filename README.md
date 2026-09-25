# 📂 FileFlow
### Intelligent Download Folder Organizer using Python and Robotic Process Automation (RPA)

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi)
![UiPath](https://img.shields.io/badge/UiPath-RPA-orange)
![MongoDB](https://img.shields.io/badge/MongoDB-Database-47A248?logo=mongodb)
![AI](https://img.shields.io/badge/AI-Claude%20%7C%20Gemini%20(advisory%20only)-8A2BE2)
![Status](https://img.shields.io/badge/Status-In%20Development-yellow)

---

# 📖 Overview

**FileFlow** is an intelligent **Robotic Process Automation (RPA)** based file management system that automatically organizes files downloaded by the user.

Instead of manually sorting downloaded files, FileFlow continuously monitors one or more watch folders, intelligently classifies files (by extension, keyword, regex, file age, or even content), moves them into appropriate folders, handles duplicate files, creates folders automatically, maintains a per-account activity log, and provides real-time analytics through a modern web dashboard — with multiple independent accounts, each with their own folders, rules, and data. A downloadable Windows agent lets FileFlow watch a folder on your own machine even when the dashboard is hosted elsewhere, complete with auto-update and two-factor-protected accounts.

The project combines **React**, **FastAPI**, **MongoDB**, and **UiPath** to demonstrate how RPA can automate repetitive day-to-day file management tasks.

---

# 🎯 Problem Statement

Most users download dozens of files every day, causing the Downloads folder to become cluttered and difficult to manage.

Common problems include:

- Difficulty finding important files
- Duplicate files consuming storage
- Mixed file types in one folder
- Manual file organization
- Time wasted searching for downloaded files

FileFlow solves these problems through intelligent automation.

---

# 💡 Solution

FileFlow automatically performs the following tasks whenever a new file is downloaded:

- Detects new files in real time
- Identifies the file type
- Applies user-defined automation rules
- Detects duplicate files
- Automatically renames duplicate files
- Creates destination folders if required
- Moves files into appropriate folders (optionally via a real UiPath Robot)
- Records every activity, scoped to the account that owns it
- Displays desktop notifications
- Updates the web dashboard instantly

---

# 🚀 Key Features

## 👥 Per-Account Isolation

Every account gets its own watch folder, its own automation rules, its own activity log, and its own dashboard. Nothing is shared between accounts — registering a second account starts from a genuinely empty slate.

---

## 📁 Automatic Watch Folder Monitoring

- Real-time monitoring of each account's own watch folder(s)
- **Multiple watch folders per account** — add extra folders from Settings; all share the same rules and get organized independently (real-time watching, the manual sweep, archiving, and the scheduled nightly sweep all cover every folder, not just the first one)
- Pick a folder with a real native folder-picker dialog, no typing/pasting a path required (local dev setup only — see [Remote Agent](#-remote-agent--watch-your-own-machine) for watching a folder on a different machine than the dashboard)
- Detects newly downloaded (or dropped) files instantly
- No manual intervention required
- Togglable per account from Settings
- **Scheduled nightly sweep** — optionally run the "organize existing files" sweep automatically once a day at a chosen time, in addition to real-time watching and the on-demand button
- If a remote agent (see below) is actively connected for an account, the backend's own local watcher steps aside so the same file is never processed twice

---

## 📂 Intelligent File Classification

Automatically organizes files into categories such as:

- 📄 Documents
- 🖼 Images
- 🎥 Videos
- 🎵 Audio
- 📦 ZIP / RAR
- 💻 Software
- 💻 Source Code
- 📁 Others

---

## 🔍 Duplicate File Detection

Automatically:

- Detect duplicate filenames
- Compare file hashes
- Skip identical files, rename them, or replace the existing file (configurable per account)

Example:

```
Resume.pdf

↓

Resume (1).pdf
```

---

## ✏ Smart File Renaming

Automatically renames files using timestamps, per category, when enabled.

Example:

```
IMG_1234.jpg

↓

2025-03-14_15-45_Image.jpg
```

---

## ⚙ Custom Automation Rules

Each account can define its own automation rules, evaluated in order of specificity: filename keyword → regex → content keyword → extension → large-file → file age → generic category → fallback.

Example:

```
Extension : .py

↓

Python Projects
```

Example:

```
Keyword : Invoice

↓

Finance Folder
```

**Beyond extension and keyword, rules can also match:**

- **Regex** — a pattern against the filename (e.g. `^IMG_\d+` → `Camera`), validated server-side so an uncompilable pattern is rejected before it's ever saved
- **Content keyword** — searches inside the file's own bytes (first 64KB, best-effort text decode) for a keyword, not just its name — e.g. any file containing "confidential" → `Private`
- **File age** — files already older than N days when first organized go to a folder of their own (e.g. `> 90 days old` → `Old Stuff`), independent of the scheduled Archive sweep below

Every rule type can be individually enabled/disabled without deleting it, and previewed against your own already-organized history before saving (regex previews use real pattern matching; content/age rules skip the preview since there's no stored file content or mtime to check against).

## 🔁 Rule Templates — Export / Import

Download your entire rule set (categories, extension/keyword/regex/content/age rules, automation policy) as a JSON file, or upload one — your own backup, or someone else's setup — to replace your current rules in one shot. Entirely client-side plus the existing rules-save endpoint; a malformed or foreign file is rejected by the same schema validation a normal save goes through, with a confirmation dialog before anything is overwritten.

---

## 📁 Automatic Folder Creation

Destination folders are created automatically if they do not exist.

---

## 📦 Large File Management

Automatically detects files larger than a user-defined size.

Example:

```
> 500 MB

↓

Large Files Folder
```

---

## 🗃 Automatic Archive

Moves old files to an Archive folder after a specified number of days, per account, on a scheduled sweep.

---

## 📝 Activity Logging

Every automation activity is recorded, scoped to the account that triggered it.

Example:

| Time | File | Action |
|------|------|--------|
|10:20|Resume.pdf|Moved to Documents|
|10:21|Movie.mp4|Moved to Videos|
|10:22|Photo.png|Moved to Images|

Logs are stored in MongoDB (`activity_log`, indexed by `user_id`).

---

## ↩ Undo & Reclassify

Restore or re-run the most recent automation action — scoped to your own account only.

---

## 🔔 Desktop Notifications

Receive instant desktop notifications when a file is organized, togglable per account.

---

## 📊 Analytics Dashboard

View:

- Total files organized
- File category statistics
- Duplicate files detected
- Storage saved
- Today's activity
- Weekly activity
- Recent automation logs

---

## 📈 Weekly Report Generation

Automatically generates reports containing:

- Files organized
- File category statistics
- Duplicate files removed
- Archived files
- Storage optimization

Export formats: CSV, Excel, PDF. Also available as a per-account weekly email digest (via Resend), togglable.

---

## 🧪 Simulate Download (demo mode)

A one-click demo button that drops a small fake file (a genuine, openable generated PDF, or a text/script file) into your watch folder, so the full detect → classify → move pipeline can be shown off without needing a real download.

---

## 🔒 Auth Security

- Password hashing (bcrypt), JWT session cookies
- Rate limiting on login (brute-force protection) and registration (spam protection), per caller IP, with a `Retry-After` response
- Forgot-password / reset-password flow (emailed reset link, single-use hashed token, expires after a configurable window)
- **Two-factor authentication (TOTP)** — optional per account. Settings shows a QR code (compatible with Google Authenticator, Authy, etc.) plus the raw secret for manual entry; enabling it issues 8 one-time backup codes (shown once) for recovery if the authenticator app is lost. Once on, login is a two-step exchange: password first, then a short-lived (5-minute) purpose-limited token traded for a real session only after a valid code or unused backup code
- **Account deletion** — permanently removes the account, its rules, activity history, and stops watching its folder(s); requires re-entering your password to confirm
- Per-agent-token scoping (see below) so a leaked read-only token can't be used to actually move files

---

## 🖥 Remote Agent — watch your own machine

A downloadable Windows agent (`FileFlowAgentSetup.exe`, from the dashboard's navbar "Downloads" menu) lets FileFlow watch a real folder **on your own computer**, even when the web dashboard itself runs somewhere else — the same rule engine, the same activity log, just reachable over the network instead of only from whatever machine happens to run the backend.

- **Real installer** — per-user install (no admin/UAC prompt), Start Menu + Startup entry, a tray icon (pause/resume watching, reconfigure, open the watched folder, quit), and a clean uninstall that stops the running process first
- **Auto-update** — the agent checks for a newer version on a schedule, downloads it, verifies its SHA-256 before ever running it, and silently updates + relaunches itself. A single-instance lock (a bound localhost port, no extra dependency) stops a user from ever accidentally running two copies at once
- **Offline-tolerant** — a local SQLite outbox queues activity reports and command results when the backend is unreachable, with exponential backoff, and replays them once connectivity returns; a file dropped while offline is retried automatically, not silently dropped
- **Live settings sync** — toggling "Real-time monitoring" on the website pauses/resumes the real agent within one poll cycle. A manual "Pause watching" from the tray and the website's toggle are independent — both have to agree before watching actually resumes
- **Scoped tokens** — generate a **Full control** token (can watch, organize, and report activity) or a **Read-only** token (can only fetch rules — useful for a monitoring integration that should never be able to touch a file) from Settings
- Every piece of this was verified against a real installed agent on a real machine, not just unit tests — including a genuine two-version self-update cycle and a real install/uninstall lifecycle

*Current limitation:* the agent watches one folder per install (the [multiple watch folders](#-automatic-watch-folder-monitoring) feature above is currently backend-only); extending the agent itself to watch several folders is a natural follow-up.

---

## 🧠 AI Rule Generator

Describe a rule in plain English ("move anything with 'invoice' in the name to Finance") from the Rules page's "Create with AI" button and get back a structured **proposal** — never an automatically-saved rule. The AI only ever produces one of FileFlow's own six supported rule types (keyword, content keyword, regex, extension, file age, large file); every proposal is re-validated through the exact same schema, containment, and ReDoS checks a manually-typed rule goes through before it can be reviewed and explicitly saved. Rate-limited per IP; if no API key is configured, the feature responds with a clean "AI service is not configured" instead of failing.

## 💡 AI Unclassified File Suggestions

For files the real rule engine currently has no rule for, ask AI what they might be and where they could belong. Files are grouped by shared filename pattern first (e.g. `invoice_1.pdf`, `invoice_2.pdf`) so one suggestion — and, if accepted, one created rule — can cover a whole batch. The AI only ever sees safe metadata (filename, extension, size) — never file contents or the real filesystem path — and a suggested rule goes through the same validation as the AI Rule Generator's own proposals before it can be created.

## ⚠ Rule Conflict Detector

Explains where two or more of your own rules can match the same file, and what the real classifier actually does about it — shadowed rules that can never fire, redundant duplicates, and cross-type overlaps are all derived by running a synthetic candidate through the exact same classification function a real file goes through, never a second, invented precedence system. Available both as an on-demand check and automatically before saving a new rule, with the option to save anyway.

## 🧩 Smart Duplicate Groups

Finds files with **identical content** (SHA-256, not just a matching name) across your whole watch folder — including files already sorted into different category folders — and groups them with the potential storage that could be reclaimed. Purely advisory: it explains what's duplicated, it never deletes, moves, or picks a copy to keep for you.

## 🔎 Natural Language File Search

Type a plain-language request ("find PDF invoices from August", "show large files related to college") and get back real, ranked results with a plain-English reason each one matched. The AI's only job is turning that request into a structured, schema-validated query (filename/extension/size/date/location/category/duplicate filters) — it never sees a filename or file content, and a deterministic search engine (shared with the remote agent) is the only thing that decides which files actually match. Metadata only: it never reads file contents, and never performs OCR.

## 📊 Organization Health Dashboard

One glanceable overview of the whole workspace: classification coverage, duplicate groups and potentially-redundant storage, active rules and detected conflicts, and recent organization activity (24h/7d/30d) — every number aggregated from the features above, never a second, independently-computed metric. Links straight into Unclassified Suggestions, Duplicate Groups, and Rules for anything that needs attention; never triggers an AI call, a duplicate scan, or a rule change just by loading.

---

# 🤖 RPA Automation — Current Scope

**The Python/FastAPI backend is a complete, standalone automation system** — Watchdog detects files in real time, FastAPI applies the rule engine (keyword rules, extension rules, duplicate detection, auto-generated folders for unknown types), moves files, and pushes live updates to the dashboard over WebSocket. This is fully working and tested against real folders.

**UiPath has a real, live integration for the physical move step**, plus a separate standalone demo project. Two distinct pieces:

### `uipath/FileFlowMove/` — live integration (real, opt-in)

A minimal one-workflow package (`MoveFile.xaml`) that FastAPI invokes directly via UiPath Robot's CLI (`UiRobot execute --file ... --entry MoveFile.xaml --input '{...}'`) when `UIPATH_ENABLED=true` is set in `.env`. Python still owns detection, classification, and duplicate resolution (`rule_engine.classify`, `resolve_destination`) — UiPath Robot performs the actual file move, then Python logs the result to MongoDB and broadcasts it over the websocket, same as always. See `backend/services/uipath_service.py` and `backend/automation/organizer.py`.

This is genuinely tested end-to-end: `backend/tests/test_uipath_service.py` and `backend/tests/test_organizer.py::TestProcessFileUiPathWiring` cover the wiring with a mocked Robot process (the test suite never shells out to a real Robot — always mocked or disabled, so it stays fast and hermetic). It has also been verified for real, against an actual installed UiPath Robot: a file dropped into a live server's watch folder was organized, and UiPath's own execution log confirmed `FileFlowMove` ran via the Robot at the exact same timestamp as the move, with the real file landing in the right place on disk.

**It's off by default** (`UIPATH_ENABLED=false`) — the existing, well-tested Python `shutil.move` path is unchanged unless you opt in, and even when enabled, any failure (Robot missing, package not built, timeout, bad output) falls back to the Python move automatically. To enable it, see [Optional: real UiPath Robot integration](#optional-real-uipath-robot-integration) below.

### `uipath/FileFlow/` — standalone 5-workflow demo (course requirement)

A separate, more elaborate demo: 5 integrated workflows mirroring the dashboard's full pipeline (Detected → Classified → Duplicate check → Moved → Logged), orchestrated by `Main.xaml` via `Invoke Workflow File`:

| Stage | Workflow | Responsibility |
|---|---|---|
| Detected | `DetectFiles.xaml` | Scans the watch folder passed in as its `in_WatchFolder` argument, returns every file path found |
| Classified | `ClassifyFile.xaml` | Maps a file's extension to a destination category (`.pdf`/`.txt`→Documents, `.jpg`→Images, `.py`→Python Projects, else Others) |
| Duplicate check | `CheckDuplicate.xaml` | If a file with that name already exists at the destination, renames it `name (1).ext`, `name (2).ext`, etc. until a free name is found |
| Moved | `MoveFile.xaml` | Creates the destination folder if needed and moves the file into it |
| Logged | `LogActivity.xaml` | Appends a row (timestamp, original name, final name, category, destination) to the CSV activity log at the path passed in as its `in_ActivityLogPath` argument |

This project exists to satisfy the course's requirement to demonstrate the RPA pattern natively in UiPath — it's a standalone reference implementation, entirely separate from the live `FileFlowMove` integration above, and doesn't touch MongoDB, the FastAPI backend, or the dashboard.

**Packs, analyzes, and runs successfully**, verified with the real UiPath tooling: `uip rpa pack` produces a valid `.nupkg`, `uip rpa analyze` reports zero critical findings and zero errors, and `uip rpa run` completes the full Detect → Classify → Duplicate-check → Move → Log pipeline against real files on disk. An earlier version of `Main.xaml` failed to pack with `Missing key value on 'Dictionary' object` — the root cause was an incorrect Dictionary value type (`x:String, x:Object`) on all five `InvokeWorkflowFile.Arguments` blocks; each needed `System.Activities.Argument` instead, which is what current UiPath.System.Activities actually expects there. Fixed and re-verified against the real compiler, not just re-read.

`Main.xaml` also no longer hardcodes a developer machine's paths: `DetectFiles.xaml` and `LogActivity.xaml` receive their watch folder and CSV log path as `in_WatchFolder` / `in_ActivityLogPath` workflow arguments, and `Main.xaml` defaults both to project-relative paths (via `Environment.CurrentDirectory`) when they're not supplied. The repo ships `uipath/FileFlow/TestDownloads/.gitkeep` so that default folder exists immediately after a fresh clone. Portability was verified directly, not assumed: the whole project was copied to an unrelated folder (`C:\Temp\FileFlowDemo`) and packed and run from there with no arguments at all — no `C:\Users\...`-style path remains anywhere in the workflow source. This is still an academic/course demonstration, not a hardened production package (see [Known issues](#known-issues--not-yet-done) below).

---

# 🏗 System Architecture

```
                          User
                            │
                            ▼
              React Dashboard (Frontend)
                            │
                  REST API / WebSocket
                            │
                            ▼
                 FastAPI Backend (Python)
              (per-account: rules, watch folder)
                            │
               Automation Controller
                            │
                            ▼
                  Watchdog File Monitor
                (one watcher per account)
                            │
                            ▼
               Account's Own Watch Folder
                            │
                            ▼
             Detect → Classify → Rename
                            │
                            ▼
              Move (Python, or UiPath Robot
                  when UIPATH_ENABLED=true)
                            │
                            ▼
              MongoDB (per-account logs & rules)
                            │
                            ▼
                  Analytics Dashboard
```

---

# 🛠 Tech Stack

## Frontend

- React 19
- Vite
- Tailwind CSS
- shadcn/ui
- React Router
- Axios
- WebSocket (native browser API, no Socket.IO)
- Recharts
- Framer Motion (`motion/react`) — page transitions, entrance/hover animation
- GSAP (+ ScrollTrigger, Flip, DrawSVG, MotionPath) — pinned scroll sequences, SVG vector animation
- anime.js — additional vector-path drawing on the landing page

## Backend

- Python
- FastAPI
- pymongo
- Watchdog
- APScheduler
- PyJWT + bcrypt (auth)
- pyotp + qrcode + Pillow (two-factor authentication, QR code generation)
- pathlib / shutil / hashlib
- reportlab / openpyxl (PDF / Excel export)

## Database

- MongoDB

## RPA Tool

- UiPath Studio / Robot

## Remote Agent (Windows)

- PyInstaller (frozen one-folder build)
- Inno Setup (per-user installer, no admin/UAC)
- pystray (system tray icon)
- SQLite (local offline outbox)

## Email / Notifications

- Resend (weekly digest)
- Plyer (desktop notifications, backend and agent alike)

## AI (advisory features only)

- Anthropic Claude or Google Gemini (either one, configurable — see [AI Rule Generator](#-ai-rule-generator) etc. above) via a single thin HTTP provider abstraction (`backend/services/ai_provider.py`), no SDK dependency
- Used only to *propose* a rule, *suggest* a classification, or *interpret* a search request into a structured query — never to move a file, decide search results, or execute anything on its own. Every AI output is re-validated by FileFlow's own deterministic code before it can affect anything real
- Fully optional: with no API key configured, these three features degrade to a clean "not configured" response; every other feature is unaffected

---

# 📂 Project Structure

```
FileFlow/
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── assets/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── layouts/
│   │   ├── hooks/
│   │   ├── services/
│   │   ├── context/
│   │   ├── utils/
│   │   └── App.jsx
│
├── backend/
│   ├── api/            (routes, auth, 2FA, agent routes, rate limiting, websocket)
│   ├── automation/      (organizer -- detect/classify/move/undo)
│   ├── monitor/          (watchdog-based multi-folder watcher)
│   ├── scheduler/         (archive sweep, scheduled organize, weekly digest)
│   ├── rules/               (per-account rule engine + classifier)
│   ├── database/              (MongoDB connection, id counters)
│   ├── models/                  (Mongo document wrappers)
│   ├── services/                  (stats, reports, digest, UiPath, agent, AI provider + rule/
│   │                                unclassified/search services, rule conflicts, duplicates, health)
│   ├── config/                      (settings, .env loading, agent release info)
│   ├── agent_releases/               (published agent installer .exe files)
│   ├── tests/                        (pytest, real local MongoDB)
│   ├── main.py
│   └── requirements.txt
│
├── agent/            (downloadable Windows remote agent -- see Remote Agent above)
│   ├── main.py, watcher.py, commands.py, client.py, outbox.py, updater.py
│   ├── setup_gui.py, tray.py       (first-run wizard, system tray)
│   ├── installer/                    (Inno Setup script)
│   ├── fileflow_agent.spec              (PyInstaller build spec)
│   └── tests/
│
├── uipath/
│   ├── FileFlow/         (standalone 5-workflow RPA demo -- course requirement)
│   └── FileFlowMove/     (minimal package the backend actually invokes)
│
├── database/       (empty -- placeholder; MongoDB itself is external)
├── docs/           (empty -- placeholder)
├── screenshots/    (empty -- placeholder)
└── README.md
```

---

# 🧭 Getting Started

## Prerequisites

- [Python 3.12+](https://www.python.org/downloads/)
- [Node.js 18+](https://nodejs.org/) and npm
- [MongoDB Community Server](https://www.mongodb.com/try/download/community), running locally (`mongodb://localhost:27017` by default)
- Git
- *(Optional, for the real UiPath integration)* [UiPath Studio/Robot](https://www.uipath.com/product/studio) (Community edition) and [.NET SDK 8.0](https://dotnet.microsoft.com/download/dotnet/8.0)
- *(Optional, only to build the remote agent installer yourself, Windows)* [Inno Setup 6](https://jrsoftware.org/isinfo.php) and `pip install pyinstaller`

## 1. Clone the repository

```bash
git clone <repository-url>
cd FileFlow
```

## 2. Backend setup (FastAPI)

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
copy .env.example .env       # then edit WATCH_FOLDER etc.
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.

*(Optional)* To enable [AI Rule Generator](#-ai-rule-generator), [AI Unclassified Suggestions](#-ai-unclassified-file-suggestions), and [Natural Language File Search](#-natural-language-file-search), set `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` (plus `AI_PROVIDER`) in `backend/.env` — see the comments in `.env.example` for the full list of settings. Leaving both unset is fine; those three features just respond with "AI service is not configured" and every other feature works exactly the same.

## 3. Frontend setup (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

The dashboard will be available at `http://localhost:5173`. Register an account from there — your watch folder, rules, and dashboard are created automatically and are yours alone.

Other frontend commands: `npm test` (Vitest), `npm run lint` (ESLint — flat config in `eslint.config.js`, covering JS/JSX correctness and React Hooks rules), `npm run build` (production build).

## 4. Optional: the remote agent (Windows)

Easiest path: from the dashboard's navbar, open the **Downloads** menu → **FileFlow Agent (.exe)**, run the installer, and paste in a token generated from Settings → "Generate agent token".

To build it yourself instead (from the repo root, with the backend's venv active):

```bash
pip install pyinstaller
pyinstaller agent/fileflow_agent.spec --noconfirm
iscc agent/installer/fileflow_agent.iss   # requires Inno Setup installed
```

The resulting installer lands in `agent/installer/Output/`. To publish it so the dashboard serves it and the auto-updater picks it up: bump `agent/VERSION` and the `.iss` file's `AppVersion` together, rebuild, copy the installer into `backend/agent_releases/FileFlowAgentSetup-<version>.exe`, bump `AGENT_LATEST_VERSION` in `backend/config/agent_release.py`, and restart the backend.

To run the agent from source instead of building an installer: `python -m agent.main` from the repo root (needs `agent/config.json` — run `python -m agent.setup` once first, or let it prompt via its GUI wizard on first launch).

## 5. Optional: real UiPath Robot integration

Off by default (`UIPATH_ENABLED=false`). To turn it on:

1. Install UiPath Studio/Robot (Community edition) and sign in with a UiPath Automation Cloud account.
2. Install .NET SDK 8.0 (required by the workflow compiler).
3. Pack the integration project into a `.nupkg`:
   ```bash
   uip rpa pack uipath/FileFlowMove <output-dir>
   ```
4. In `backend/.env`, set `UIPATH_ENABLED=true`, `UIPATH_ROBOT_EXE` (path to `UiRobot.exe`), and `UIPATH_PACKAGE_PATH` (path to the `.nupkg` from step 3) — see `.env.example` for the exact shape.

## 6. UiPath standalone demo (course requirement)

Open `uipath/FileFlow/project.json` in UiPath Studio to inspect the 5-workflow pipeline, or pack/run it straight from the CLI (`uip rpa pack uipath/FileFlow <output-dir>`, `uip rpa run --file-path Main.xaml --project-dir uipath/FileFlow`). No path needs editing first: by default it watches `uipath/FileFlow/TestDownloads/` (present in the repo right after a fresh clone) and writes its CSV activity log to `uipath/FileFlow/ActivityLog.csv`, both resolved relative to wherever the project itself sits. To point it at a different folder or log file instead, pass `in_WatchFolder` / `in_ActivityLogPath` as workflow input arguments (e.g. `uip rpa run --input-arguments in_WatchFolder=... --input-arguments in_ActivityLogPath=...`). See [RPA Automation — Current Scope](#-rpa-automation--current-scope) above for the full pipeline breakdown.

---

# 🕓 Development Progress

Originally built as a single-tenant SQLite app, FileFlow has since gone through a full migration to real multi-tenancy on MongoDB, a live RPA integration, a downloadable remote agent, and a round of account-security and automation-rule features:

- **Migrated the entire backend off SQLite/SQLAlchemy onto MongoDB** (`pymongo`), including a from-scratch test suite rewrite against a real local `mongod` (disposable per-test databases, dropped after each test).
- **Built real per-account data isolation** — separate watch folders, rules, activity logs, and WebSocket delivery per account. This fixed the original bug where a second registered account could see the first account's data.
- **Added compound MongoDB indexes** (`user_id` + `_id` / `timestamp`) on `activity_log`, matching the app's actual per-account query patterns.
- **Wired a real UiPath Robot integration**: the physical file-move step can now genuinely be performed by an installed UiPath Robot (verified end-to-end against UiPath's own execution logs), with an automatic, always-safe fallback to a plain Python move if the Robot is ever unavailable.
- **Added rate limiting** on `/api/auth/login` and `/api/auth/register` (per-IP, with a `Retry-After` response), closing a real brute-force / registration-spam gap.
- **Added forgot-password / reset-password**, and later **account deletion** and **two-factor authentication (TOTP + backup codes)** — see [Auth Security](#-auth-security).
- **Built the downloadable Windows remote agent from scratch**, across four phases: (1) a durable local outbox so a dropped connection never loses a pending activity report or command, (2) offline-queue robustness with exponential backoff, (3) a real per-user installer (Inno Setup) with a tray icon and setup wizard, (4) checksum-verified self-updating. Shipped through its own auto-update pipeline multiple times against a real installed agent on a real machine. See [Remote Agent](#-remote-agent--watch-your-own-machine).
- **Found and fixed a genuine double-processing bug**: the backend's own local watcher never checked whether a remote agent was already covering an account's folder, so a file could be organized once by each, with the loser reporting a confusing false "duplicate". Fixed by having the local watcher defer to a connected agent, same as undo/reclassify/organize-existing already did.
- **Added scheduled nightly organizing, multiple watch folders per account, regex/content/file-age rule types, and rule template export/import** — see the feature sections above.
- Replaced a from-scratch task backlog with genuine end-to-end verification for each of the above: real accounts, real files on disk, real HTTP round trips against the live server (not just the test suite) — this is also how a handful of real bugs were caught that the test suite alone missed (a FastAPI default-value quirk that silently dropped a request body field; a browser caching an installer download and never re-fetching a newer one).
- **Added per-row Undo on the History page** (any operation can now be reversed independently of order, not just the most recent one) and a **category detail page** — clicking a Categories card opens every real file in that folder, sortable by size/date, with a Recycle-Bin-backed delete.
- **Ran a full backend reliability audit and fixed five real bugs it found**: category statistics (and the Dashboard's "by category" chart) now read live from disk instead of a historical `activity_log` aggregate, so a category correctly disappears once every file in it is gone; the scheduler's jobs were being registered with `next_run_time=None`, which silently added every one of them *paused* — the nightly archive sweep, recycle-bin purge, storage-threshold check, weekly digest, and scheduled-organize sweep were running on no schedule at all until this was found and fixed; account deletion wasn't actually removing the account's own rules document (an `int`/`str` `_id` type mismatch meant the delete query matched nothing); the UiPath fallback path could raise and lose an activity-log entry if a Robot genuinely completed a move but failed to report it cleanly; and the scheduled archive sweep plus the storage-threshold auto-archive were the one remaining file-move path not sharing the lock every other mover (`process_file`, undo, reclassify) already uses, closing a real destination-collision race. Also cleaned up stale WebSocket connections on any disconnect, not just the common case.
- **Fixed the standalone UiPath `Main.xaml` pack failure** (root cause: the wrong Dictionary value type on all five `InvokeWorkflowFile.Arguments` blocks) and made the standalone demo portable — `DetectFiles.xaml`/`LogActivity.xaml` now take `in_WatchFolder`/`in_ActivityLogPath` as workflow arguments instead of a hardcoded developer-machine path, `Main.xaml` defaults both to project-relative paths, and `uipath/FileFlow/TestDownloads/.gitkeep` keeps the default test folder present after a fresh clone. Verified for real with `uip rpa pack`, `uip rpa analyze`, and `uip rpa run` — including copying the whole project to an unrelated folder and running it there successfully with zero arguments. See [RPA Automation — Current Scope](#-rpa-automation--current-scope).
- **Added six advisory/AI capstone features on top of the core engine**: an [AI Rule Generator](#-ai-rule-generator) and [AI Unclassified File Suggestions](#-ai-unclassified-file-suggestions) (both strictly proposal-only — every AI output is re-validated through the same schema a manual rule goes through before it can be saved), a [Rule Conflict Detector](#-rule-conflict-detector) that runs synthetic candidates through the real classifier rather than a second precedence system, [Smart Duplicate Groups](#-smart-duplicate-groups) (SHA-256 content matching, purely advisory), [Natural Language File Search](#-natural-language-file-search) (the AI only ever produces a structured, schema-validated query — a deterministic engine shared with the remote agent decides what actually matches), and an [Organization Health Dashboard](#-organization-health-dashboard) that aggregates all of the above into one overview without introducing a second source of truth for any of them. All six ran through a dedicated final production-readiness/security/regression audit (auth token-type confusion, cross-account isolation, path-containment/ReDoS protection, AI-provider failure mapping, and a missing `(user_id, _id)` index on `agent_commands` were all specifically checked; the audit's only functional fix was that missing index).
- **1,385 tests currently pass** across backend (819, plus 2 release-artifact checks that only run with `FILEFLOW_VERIFY_RELEASE=1`), remote agent (257; one pre-existing Windows-only test remains a known, documented OS-level timing issue unrelated to FileFlow code — see [Known issues](#known-issues--not-yet-done)), and frontend (309 across 25 files) — verified against real infrastructure (a real MongoDB instance, a real running server, real file drops, a real installed Windows agent, real UiPath execution logs) rather than mocks alone.

## Known issues / not yet done

- No CI, no Docker/deployment setup.
- `secure=False` on the session cookie needs flipping before any real HTTPS deployment.
- **Watch-folder selection has no containment beyond preventing overlap with another account's folder** — any account can point its own primary or additional watch folder at any real path the backend process can reach (`resolve_watch_folder()` / `_check_folder_available()` in `backend/config/settings.py` / `backend/api/routes.py`). This is intentional and tested (`backend/tests/test_multi_user_isolation.py`): FileFlow's per-account isolation means accounts can't see or touch *each other's* data or files, not that the backend host's own filesystem is defended from its own registered users. That's the right tradeoff for the intended deployment — one instance, self-hosted by a person or trusted group, where every registered account is someone you'd trust with file-move access on that machine. **Do not deploy a single instance for open/self-service registration by mutually-untrusted strangers without first adding an operator-defined containment root** — the current design assumes that never happens.
- The remote agent installer is unsigned — Windows SmartScreen/antivirus may flag it; code signing is a paid certificate, out of scope for now.
- The remote agent watches one folder per install; the multiple-watch-folders feature is currently backend-only.
- Multiple watch folders share one rule set per account — independent rules per folder would be a larger, separate change.
- No pagination on Activity Log (capped at 500 rows); no multi-select bulk actions (undo/delete/reclassify still one row/file at a time, though no longer restricted to "most recent only"); no data export beyond the existing CSV/Excel/PDF reports.
- **No retention policy**: the `activity_log` and `agent_commands` collections only grow (no TTL or cleanup job). Queries are index-backed (including a `(user_id, _id)` index on `agent_commands`), so this affects storage, not correctness or query latency, for a personal/small-group deployment.
- Frontend dark mode covers the marketing pages only, not the authenticated app. Every route is already lazy-loaded (`React.lazy`/`Suspense` in `App.jsx`) into its own chunk. The production build still prints Vite's "chunks larger than 500 kB" warning for exactly one chunk: the shared entry/vendor bundle (~525 kB — React, React DOM, React Router, axios, needed by every route regardless). The Dashboard chunk (~412 kB) is the next largest, under the threshold, because it statically imports its own dialogs (Organization Preview, Unclassified Suggestions, Duplicate Groups, File Search, Health). Lazy-loading those dialogs individually was evaluated during the production-readiness audit and deliberately not done — it would add real risk to a large, currently 100%-passing test suite for a cosmetic saving on an internal, self-hosted tool.
- **A known, pre-existing agent test failure**: `agent/tests/test_singleton.py::test_a_crashed_holder_process_also_releases_the_port` fails on this Windows development environment (an abrupt `TerminateProcess` doesn't release the bound localhost port as fast as the test expects). Reproduced identically before and after every feature added since, with no related change to the singleton implementation — attributed to Windows OS-level lock-release timing, not a FileFlow bug. Left as-is (not weakened or skipped) per the project's own testing standards.
- **AI features (Rule Generator, Unclassified Suggestions, Natural Language Search) use UTC for every date computation** (e.g. "last month", "today"), matching every other timestamp already in FileFlow — there's no per-account timezone setting anywhere in the app yet.
- **Natural Language File Search is metadata-only** — filename, extension, size, dates, and current classification, exactly like the rest of FileFlow. It never reads file contents and never performs OCR, so a request like "find the file about machine learning" is correctly reported as unsupported rather than guessed at.
- **The Health Dashboard's classification/unclassified counts cover only each watch folder's top level** (the same scope AI Unclassified Suggestions already uses) — a file already sorted into a category subfolder isn't re-audited. It also has no historical "organization errors" metric: the underlying organizer never persists a per-file failure event, so the dashboard can only show a live count from its current scan, not a 7/30-day trend.
- For a connected remote agent, the Health Dashboard's file-classification and duplicate-scan cards report "not available yet" rather than executing a new background scan on every page load — open Unclassified Suggestions / Duplicate Files directly to check current numbers on demand.
- **AI provider verification scope**: all automated tests mock the provider boundary. A final manual smoke test (2026-09-25) exercised all three AI features live against **Google Gemini** (`gemini-3.6-flash`) — a real rule proposal, a real unclassified-file suggestion, and a real natural-language search interpretation each returned valid, schema-checked output and drove the normal FileFlow code paths. The **Anthropic** provider path is implemented and unit-tested but was **not** exercised live (no Anthropic key was available). During that run Gemini intermittently answered `503 UNAVAILABLE` ("high demand"); FileFlow reported it as "AI service is temporarily unavailable" with no destructive side effect, and a retry succeeded — expect the same on a busy provider. **At release freeze the live re-check could not be repeated:** the Gemini free-tier daily request quota for this model was exhausted (`429 RESOURCE_EXHAUSTED`, `GenerateRequestsPerDayPerProjectPerModel-FreeTier`), which FileFlow reported as "AI search is busy right now". The final build's AI code paths were therefore re-run end to end against a local *stub* provider (canned, schema-shaped answers through the real HTTP boundary) — that verifies FileFlow's side, not the model's behaviour, and is not a substitute for a live check.
- **Agent installer 1.0.4 is built from current source and published** at `backend/agent_releases/FileFlowAgentSetup-1.0.4.exe` (the older `-1.0.3.exe` is left alongside it). It is **unsigned** (`Get-AuthenticodeSignature`: `NotSigned`) — Windows SmartScreen/antivirus may warn. Verified on 2026-09-25: the frozen build contains handlers for all six command types (undo, reclassify, organize_existing, preview_organize_existing, duplicate_analysis, file_search); a real silent install into a scratch folder ran preview, organize-existing, duplicate analysis and file search through the agent, and an unknown command type did not stop the others; the version manifest, both download routes and the SHA-256 all matched. **Not re-tested:** the self-update *apply* cycle (it would install into the real per-user location) and an outage-and-replay of the outbox against the built exe. A build's `VERSION` string does not prove what is inside it — an earlier local build labelled `1.0.4` lacked three of those handlers — so rebuild after any change to `agent/commands.py`, and run `FILEFLOW_VERIFY_RELEASE=1 pytest backend/tests/test_release_artifact.py` before publishing. Uninstalling leaves the agent's own `config.json` (which holds its token) and outbox in the install folder.
- The authenticated app is **desktop-first**: below roughly 700 px width the sidebar does not collapse and the page scrolls horizontally (the new Health panel itself stacks correctly). Verified in a real headless-browser check; not addressed.
- **UiPath — what is actually verified (2026-09-25).** The only UiPath-powered step is the *physical file move* (`uipath/FileFlowMove/MoveFile.xaml`, invoked by `backend/services/uipath_service.py` from `organizer.process_file`) when `UIPATH_ENABLED=true`. Classification, rules, preview, duplicate/search/health, and the Windows agent's own moves are Python — the installed agent ships no `.env`, so it never uses UiPath unless `UIPATH_*` variables are set in its process environment, which was not tested. A live run through the production function moved a scratch file with the real Robot (cold start ~12 s, later moves ~4 s), UiPath's own execution log recorded `FileFlowMove execution started/ended`, and the three backend-organized files in the end-to-end flows each triggered one Robot execution. **Config drift:** `UIPATH_ROBOT_EXE` points into a *versioned* folder (`Robot/<version>/UiRobot.exe`); UiPath's auto-updater replaced `26.0.198-cloud.24248` with `26.0.202-cloud.25004`, so the previously configured path silently stopped existing and every move logged `UiPath Robot invocation failed to start` and fell back to the Python move. Re-point it after any UiPath update (safe failure mode: a missing or failed Robot never blocks a move).
- New accounts start with **real-time monitoring off** (the seed rule template sets `realtime_monitoring_enabled: false`), so the Dashboard shows "Automation engine paused" until it is switched on in Settings; the manual "Organize existing files" sweep works either way.

---

# 📸 Screenshots

_Screenshots of the dashboard and automation in action will be added here. See `screenshots/`._

---

# 🎯 Project Objectives

- Automate repetitive file management tasks.
- Keep the watch folder clean and organized.
- Reduce manual effort through RPA.
- Improve productivity and file accessibility.
- Demonstrate real-time automation using Python and UiPath.
- Provide a modern, multi-account web dashboard for monitoring automation.

---

# 📈 Future Enhancements

- AI-based file classification
- OCR for document recognition
- Google Drive / OneDrive / Dropbox integration
- Automatic email attachment organization
- Voice assistant support
- Duplicate image detection
- QR code document categorization
- Cloud backup
- Cross-platform support (Windows, Linux, macOS)

## Automation, specifically

- **Independent rules per watch folder** — right now every folder on an account shares one rule set; letting each folder define its own would make e.g. a "Downloads" folder and a "Screenshots" folder behave completely differently
- **Multi-folder support in the remote agent** — the backend already watches several folders per account; the downloadable agent still only watches one per install
- **Chained / conditional rules** — actions that trigger off another rule's result (e.g. "anything filed under Finance Folder that's also over 90 days old → also move to a Tax Archive"), instead of every rule being evaluated independently against the original file
- **Webhook / Slack / Discord actions** — send an automation event somewhere other than the desktop toast or weekly email digest, e.g. "post to a channel whenever a large file lands"
- **Bulk automation actions** — every History row can now be undone independently (no longer "most recent only"), and Category pages support per-file delete; still missing is multi-*select* (checkbox several rows/files and undo/delete/reclassify them together in one action)
- **Code-signed, auto-updating installer** — remove the current SmartScreen/antivirus friction on first install without giving up the checksum-verified auto-update pipeline already in place

---

# 📚 Learning Outcomes

This project demonstrates:

- Robotic Process Automation (RPA)
- Python Automation
- UiPath Workflow Development
- React Frontend Development
- FastAPI REST APIs
- Real-Time Folder Monitoring
- Rule-Based Automation
- File System Management
- Multi-Tenant Database Design (MongoDB)
- Analytics Dashboard
- Desktop Notifications
- Report Generation
- WebSocket Communication
- Auth Security (rate limiting, session management, two-factor authentication)
- Desktop Application Packaging & Auto-Update (PyInstaller, Inno Setup)
- Applied AI Integration with Human-in-the-Loop Safety (structured-output validation, provider abstraction, advisory-only design — the AI proposes, deterministic code decides)

---

# 👨‍💻 Developed By

**Tirth Vaghela**

Faculty of Computer Application & Information Technology

GLS University

---

# 📜 License

This project is developed for **academic purposes** as part of the **Robotic Process Automation (RPA)** course at **GLS University**. No open-source license has been applied yet — usage outside the course should be confirmed with the author/university. A `LICENSE` file will be added if the project is released publicly.