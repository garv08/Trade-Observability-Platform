# 🛠️ Installation guide

This guide gets TOP running on **Linux, macOS, or Windows** in about five minutes, then covers upgrading, uninstalling, running it in the background, and fixing common problems.

- [Requirements](#requirements)
- [Option A: clone and install (recommended)](#option-a-clone-and-install-recommended)
  - [Ubuntu / Debian](#ubuntu--debian) · [macOS](#macos) · [Windows](#windows-powershell)
- [Option B: install without cloning](#option-b-install-without-cloning)
- [First run](#first-run)
- [Check the install](#check-the-install)
- [Where your data lives](#where-your-data-lives)
- [Upgrade](#upgrade) · [Uninstall](#uninstall)
- [Run in the background (Linux)](#run-in-the-background-linux)
- [Older CPUs](#older-cpus)
- [Troubleshooting](#troubleshooting)

---

## Requirements

| Need | Version / size | Why |
| --- | --- | --- |
| Python | **3.10, 3.11, 3.12, or 3.13** | DuckDB 1.1.3 has no wheels for 3.14 yet |
| git | any | To clone the repository |
| Internet | first run only | Downloads about five years of daily bars for 50 stocks (1–2 minutes) |
| Disk | ~20 MB | The DuckDB database |
| Browser | any modern browser | Chrome, Edge, Firefox, Safari |

The only Python dependency is **`duckdb==1.1.3`**, installed automatically. No NumPy, Node.js, database server, or API keys are needed.

---

## Option A: clone and install (recommended)

You get the code, docs, and tests, and you can edit and update easily.

### Ubuntu / Debian

```bash
# 1. System packages (once)
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip

# 2. Get the code
git clone https://github.com/garv08/Trade-Observability-Platform.git
cd Trade-Observability-Platform

# 3. Create a virtual environment and install
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .

# 4. Start
top-platform
```

> [!NOTE]
> If `python3 -m venv` complains about `ensurepip`, install the versioned package, for example `sudo apt install python3.12-venv`.

### macOS

```bash
# Python 3.10–3.13 from python.org, or: brew install python@3.12 git
git clone https://github.com/garv08/Trade-Observability-Platform.git
cd Trade-Observability-Platform

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .

top-platform
```

### Windows (PowerShell)

1. Install **Python 3.12** from [python.org](https://www.python.org/downloads/windows/). Tick **"Add python.exe to PATH"**.
2. Install **[Git for Windows](https://git-scm.com/download/win)**.
3. In PowerShell:

```powershell
git clone https://github.com/garv08/Trade-Observability-Platform.git
cd Trade-Observability-Platform

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install --upgrade pip
pip install -e .

top-platform
```

> [!TIP]
> `pip install -e .` is an *editable* install: edits to `top/` take effect the next time you start the server. Front-end edits in `top/web/` need only a browser reload.

---

## Option B: install without cloning

Use this if you just want to run TOP. Ubuntu and Debian block `pip install` into the system Python, so install into a virtual environment, or use `pipx`.

**With a virtual environment:**

```bash
sudo apt install -y git python3-venv python3-pip                 # once (Ubuntu/Debian)
python3 -m venv ~/top-venv
~/top-venv/bin/pip install "git+https://github.com/garv08/Trade-Observability-Platform.git"
~/top-venv/bin/top-platform
```

**With [pipx](https://pipx.pypa.io/)**, which creates and manages the environment for you:

```bash
sudo apt install -y git pipx && pipx ensurepath                  # once; then open a new terminal
pipx install "git+https://github.com/garv08/Trade-Observability-Platform.git"
top-platform
```

To pin a release, add `@v0.1.0` to the URL.

---

## First run

```bash
top-platform              # or: python -m top
```

```text
TOP - Trade Observability Platform at http://127.0.0.1:8000 (also http://localhost:8000)
```

1. Open **http://127.0.0.1:8000**.
2. TOP creates `data/nse.duckdb` and downloads history for all 50 stocks in the background. The top bar shows `Sync 12/50`, then `DuckDB 50/50`.
3. Pick a stock, add studies, and read the Interpretation pane. See the [user guide](user-guide.md).

Prefer to download the data first, without the server?

```bash
top-sync                  # prints progress for each of the 50 stocks
```

Useful options:

```bash
top-platform --port 8050                 # another port
top-platform --no-sync                   # never download on start
TOP_DB=~/top-data/nse.duckdb top-platform  # keep the database in one place
```

---

## Check the install

```bash
top-platform --help
python -c "import top; print('TOP', top.__version__)"
python -m top.verify                     # after the first sync: runs every self-check, exits 0 on success
```

From a clone you can also run the offline test suite:

```bash
python -m unittest discover -s tests -t . -v
```

---

## Where your data lives

| What | Where |
| --- | --- |
| Market data | `./data/nse.duckdb`, relative to the folder you start TOP from, or the path in `TOP_DB` |
| Fundamentals cache | In memory, for six hours |
| Settings | None stored; use [shareable links](user-guide.md#shareable-links) to save set-ups |

Delete the database file to start fresh; TOP downloads it again on the next start.

---

## Upgrade

**Clone:**

```bash
cd Trade-Observability-Platform
git pull
source .venv/bin/activate && pip install -e .
```

**Virtual environment or pipx:**

```bash
~/top-venv/bin/pip install --upgrade "git+https://github.com/garv08/Trade-Observability-Platform.git"
# or
pipx upgrade trade-observability-platform
```

Restart `top-platform`, then hard-reload the browser (Ctrl+Shift+R).

## Uninstall

```bash
pip uninstall trade-observability-platform      # inside the venv; or: pipx uninstall trade-observability-platform
rm -rf .venv data                                # in the clone, to remove the environment and the database
```

---

## Run in the background (Linux)

A user-level systemd service starts TOP at login and restarts it if it stops. Adjust the paths to your clone.

```ini
# ~/.config/systemd/user/top-platform.service
[Unit]
Description=TOP - Trade Observability Platform

[Service]
WorkingDirectory=%h/Trade-Observability-Platform
ExecStart=%h/Trade-Observability-Platform/.venv/bin/top-platform
Restart=on-failure

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now top-platform
systemctl --user status top-platform
```

Refresh data after the market closes with a cron entry, for example at 18:30 on weekdays:

```cron
30 18 * * 1-5  cd ~/Trade-Observability-Platform && .venv/bin/top-sync >> ~/top-sync.log 2>&1
```

---

## Older CPUs

TOP pins `duckdb==1.1.3` and avoids NumPy so it runs on older x86 processors without SSE4.2/POPCNT (for example 2009-era laptops). Newer DuckDB and NumPy 2 builds stop there with `Illegal instruction`. Keep the pin, and don't install NumPy 2 into TOP's environment.

---

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `Command 'pip' not found` | `sudo apt install python3-pip`, then install inside a virtual environment as above |
| `error: externally-managed-environment` | Ubuntu/Debian protect the system Python. Use a virtual environment or `pipx`, not `sudo pip` |
| `python3 -m venv` fails with `ensurepip is not available` | `sudo apt install python3-venv` (or `python3.12-venv`, matching your Python) |
| `top-platform: command not found` | Activate the environment (`source .venv/bin/activate`) or call it by path, for example `~/top-venv/bin/top-platform` |
| Typing `top` opens a process viewer | That's the system `top`. TOP's command is `top-platform` (or `python -m top`) |
| `No matching distribution found for duckdb==1.1.3` | Use Python 3.10–3.13 |
| `Illegal instruction` on start | See [Older CPUs](#older-cpus); reinstall with `pip install duckdb==1.1.3` |
| `Address already in use` | Another program (or another TOP) uses port 8000: `top-platform --port 8050` |
| Browser: "Failed to fetch" / "The desk did not answer" | Make sure `top-platform` is still running, then reload. Both `127.0.0.1` and `localhost` work |
| Page looks old after an update | Hard-reload: Ctrl+Shift+R (Cmd+Shift+R on macOS) |
| Some stocks show "no bars" | Click **Sync history** or run `top-sync`; Yahoo sometimes rate-limits, so retry later |
| Fundamentals error | Screener.in may be unreachable or rate-limiting; try later |
| `git clone` asks for a username and password | The URL is wrong or the repository is private. Public clones never need a password; check the URL is `https://github.com/garv08/Trade-Observability-Platform.git` |

Still stuck? [Open an issue](https://github.com/garv08/Trade-Observability-Platform/issues/new/choose) with your OS, Python version (`python3 --version`), and the full error.
