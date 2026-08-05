# 📂 FileFlow
### Intelligent Download Folder Organizer using Python and Robotic Process Automation (RPA)

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi)
![UiPath](https://img.shields.io/badge/UiPath-RPA-orange)
![MongoDB](https://img.shields.io/badge/MongoDB-Database-47A248?logo=mongodb)
![Status](https://img.shields.io/badge/Status-In%20Development-yellow)

---

# 📖 Overview

**FileFlow** is an intelligent **Robotic Process Automation (RPA)** based file management system that automatically organizes files downloaded by the user.

Instead of manually sorting downloaded files, FileFlow continuously monitors a watch folder, intelligently classifies files, moves them into appropriate folders, handles duplicate files, creates folders automatically, maintains a per-account activity log, and provides real-time analytics through a modern web dashboard — with multiple independent accounts, each with their own folder, rules, and data.

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

- Real-time monitoring of each account's own watch folder
- Detects newly downloaded (or dropped) files instantly
- No manual intervention required
- Togglable per account from Settings

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

Each account can define its own automation rules.

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

---

# 🤖 RPA Automation — Current Scope

**The Python/FastAPI backend is a complete, standalone automation system** — Watchdog detects files in real time, FastAPI applies the rule engine (keyword rules, extension rules, duplicate detection, auto-generated folders for unknown types), moves files, and pushes live updates to the dashboard over WebSocket. This is fully working and tested against real folders.

**UiPath has a real, live integration for the physical move step**, plus a separate standalone demo project. Two distinct pieces:

### `uipath/FileFlowMove/` — live integration (real, opt-in)

A minimal one-workflow package (`MoveFile.xaml`) that FastAPI invokes directly via UiPath Robot's CLI (`UiRobot execute --file ... --entry MoveFile.xaml --input '{...}'`) when `UIPATH_ENABLED=true` is set in `.env`. Python still owns detection, classification, and duplicate resolution (`rule_engine.classify`, `resolve_destination`) — UiPath Robot performs the actual file move, then Python logs the result to MongoDB and broadcasts it over the websocket, same as always. See `backend/services/uipath_service.py` and `backend/automation/organizer.py`.

This is genuinely tested end-to-end: `backend/tests/test_uipath_service.py` and `backend/tests/test_organizer.py::TestProcessFileUiPathWiring` cover the wiring with a mocked Robot process (the test suite never shells out to a real Robot — always mocked or disabled, so it stays fast and hermetic). It has also been verified for real, against an actual installed UiPath Robot: a file dropped into a live server's watch folder was organized, and UiPath's own execution log confirmed `FileFlowMove` ran via the Robot at the exact same timestamp as the move, with the real file landing in the right place on disk.

**It's off by default** (`UIPATH_ENABLED=false`) — the existing, well-tested Python `shutil.move` path is unchanged unless you opt in, and even when enabled, any failure (Robot missing, package not built, timeout, bad output) falls back to the Python move automatically. To enable it, see [Optional: real UiPath Robot integration](#optional-real-uipath-robot-integration) below.

### `uipath/FileFlow/` — standalone 5-workflow demo (known issue)

A separate, more elaborate demo: 5 integrated workflows mirroring the dashboard's full pipeline (Detected → Classified → Duplicate check → Moved → Logged), orchestrated by `Main.xaml` via `Invoke Workflow File`:

| Stage | Workflow | Responsibility |
|---|---|---|
| Detected | `DetectFiles.xaml` | Scans the watch folder, returns every file path found |
| Classified | `ClassifyFile.xaml` | Maps a file's extension to a destination category (`.pdf`/`.txt`→Documents, `.jpg`→Images, `.py`→Python Projects, else Others) |
| Duplicate check | `CheckDuplicate.xaml` | If a file with that name already exists at the destination, renames it `name (1).ext`, `name (2).ext`, etc. until a free name is found |
| Moved | `MoveFile.xaml` | Creates the destination folder if needed and moves the file into it |
| Logged | `LogActivity.xaml` | Appends a row (timestamp, original name, final name, category, destination) to a CSV activity log |

This project exists to satisfy the course's requirement to demonstrate the RPA pattern natively in UiPath — it's a standalone reference implementation, entirely separate from the live `FileFlowMove` integration above, and doesn't touch MongoDB, the FastAPI backend, or the dashboard.

**`Main.xaml` currently fails to pack/compile**, confirmed against the real `uip rpa pack` compiler: `Could not load Main.xaml file: 'Missing key value on 'Dictionary' object.' Line number '106'`, from one of the `InvokeWorkflowFile.Arguments` dictionaries used to pass arguments between the 5 workflows. Each of the 4 sub-workflows is individually valid on its own — only the orchestrating `Main.xaml` is affected. Not yet resolved.

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

## Backend

- Python
- FastAPI
- pymongo
- Watchdog
- APScheduler
- PyJWT + bcrypt (auth)
- pathlib / shutil / hashlib
- reportlab / openpyxl (PDF / Excel export)

## Database

- MongoDB

## RPA Tool

- UiPath Studio / Robot

## Email / Notifications

- Resend (weekly digest)
- Plyer (desktop notifications)

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
│   ├── api/            (routes, auth, rate limiting, websocket)
│   ├── automation/      (organizer -- detect/classify/move/undo)
│   ├── monitor/          (watchdog-based multi-folder watcher)
│   ├── scheduler/         (archive sweep, weekly digest)
│   ├── rules/               (per-account rule engine)
│   ├── database/              (MongoDB connection, id counters)
│   ├── models/                  (Mongo document wrappers)
│   ├── services/                  (stats, reports, digest, UiPath)
│   ├── config/                      (settings, .env loading)
│   ├── tests/                        (pytest, real local MongoDB)
│   ├── main.py
│   └── requirements.txt
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

## 3. Frontend setup (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

The dashboard will be available at `http://localhost:5173`. Register an account from there — your watch folder, rules, and dashboard are created automatically and are yours alone.

## 4. Optional: real UiPath Robot integration

Off by default (`UIPATH_ENABLED=false`). To turn it on:

1. Install UiPath Studio/Robot (Community edition) and sign in with a UiPath Automation Cloud account.
2. Install .NET SDK 8.0 (required by the workflow compiler).
3. Pack the integration project into a `.nupkg`:
   ```bash
   uip rpa pack uipath/FileFlowMove <output-dir>
   ```
4. In `backend/.env`, set `UIPATH_ENABLED=true`, `UIPATH_ROBOT_EXE` (path to `UiRobot.exe`), and `UIPATH_PACKAGE_PATH` (path to the `.nupkg` from step 3) — see `.env.example` for the exact shape.

## 5. UiPath standalone demo (course requirement)

Open `uipath/FileFlow/project.json` in UiPath Studio to inspect the 5-workflow pipeline. See [RPA Automation — Current Scope](#-rpa-automation--current-scope) above for its current known issue.

---

# 🕓 Development Progress

Originally built as a single-tenant SQLite app, FileFlow has since gone through a full migration to real multi-tenancy on MongoDB, plus a live RPA integration:

- **Migrated the entire backend off SQLite/SQLAlchemy onto MongoDB** (`pymongo`), including a from-scratch test suite rewrite against a real local `mongod` (disposable per-test databases, dropped after each test).
- **Built real per-account data isolation** — separate watch folders, rules, activity logs, and WebSocket delivery per account. This fixed the original bug where a second registered account could see the first account's data.
- **Added compound MongoDB indexes** (`user_id` + `_id` / `timestamp`) on `activity_log`, matching the app's actual per-account query patterns.
- **Wired a real UiPath Robot integration**: the physical file-move step can now genuinely be performed by an installed UiPath Robot (verified end-to-end against UiPath's own execution logs), with an automatic, always-safe fallback to a plain Python move if the Robot is ever unavailable.
- **Added rate limiting** on `/api/auth/login` and `/api/auth/register` (per-IP, with a `Retry-After` response), closing a real brute-force / registration-spam gap.
- **168 backend tests / 23 frontend tests passing**, verified against real infrastructure (a real MongoDB instance, a real running server, real file drops, real UiPath execution logs) rather than mocks alone.

## Known issues / not yet done

- **No git repository yet** — the single biggest risk right now; none of the above has version control or backup.
- `uipath/FileFlow/Main.xaml` fails to pack/compile (see [RPA Automation — Current Scope](#-rpa-automation--current-scope)).
- No password reset / email verification flow.
- No CI, no Docker/deployment setup.
- `secure=False` on the session cookie needs flipping before any real HTTPS deployment.
- No pagination on Activity Log (capped at 500 rows); no bulk actions; no account deletion/data export.
- Frontend dark mode covers the marketing pages only, not the authenticated app; ~935KB JS bundle, not code-split.

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
- Auth Security (rate limiting, session management)

---

# 👨‍💻 Developed By

**Tirth Vaghela**

Faculty of Computer Application & Information Technology

GLS University

---

# 📜 License

This project is developed for **academic purposes** as part of the **Robotic Process Automation (RPA)** course at **GLS University**. No open-source license has been applied yet — usage outside the course should be confirmed with the author/university. A `LICENSE` file will be added if the project is released publicly.
