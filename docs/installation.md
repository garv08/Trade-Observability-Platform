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
| Disk | ~20 MB (Nifty 50) · ~300 MB with all BSE stocks and ETFs | The DuckDB database |
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

To pin a release, add `@v0.8.0` to the URL.

---

## First run

```bash
top-platform              # or: python -m top
```

```text
TOP - Trade Observability Platform at http://127.0.0.1:8000 (also http://localhost:8000)
```

1. Open **http://127.0.0.1:8000**.
2. TOP creates `data/nse.duckdb` and downloads history for the Nifty 50 in the background. The top bar shows `Nifty sync 12/50`, then `DuckDB 50/50`.
3. Pick a stock, add studies, and read the Interpretation pane. See the [user guide](user-guide.md).

### Get all the data on a new machine

The database is **not in git**: it is about 480 MB of generated data, and GitHub refuses files over 100 MB, so `git clone` and `git pull` bring only the code. A banner on the desk (*Only the Nifty 50 is loaded*) offers two ways to fill it:

| Way | How | Time | You get |
| --- | --- | --- | --- |
| **Ready-made snapshot** | **Download ready-made data** on the desk, or (server stopped) `top-sync --snapshot` | minutes (≈225 MB) | Every NSE and BSE stock, ETFs, indices, delivery %, FII/DII, and the computed leaderboard as of the snapshot date |
| **From the exchanges** | **Sync history** on the desk, or `top-sync --bhav`, then **Run backtests** on the Leaderboard page | 1–2 hours + a few hours | The same, built on your machine |

After a snapshot, click **Sync history** once to add the days since it was made (only those days are downloaded). The snapshot comes from the newest [GitHub release](https://github.com/garv08/Trade-Observability-Platform/releases) that has a `top-data.duckdb.gz` asset. Its SHA-256 is checked against `top-data.json`, and the file is opened as a test before it replaces your store. Your old store is kept as `data/nse.duckdb.bak`.

You can also copy a store yourself, for example on a USB stick or cloud drive:

```bash
top-sync --make-snapshot ~/top-snapshot     # on the machine with data (server stopped)
top-sync --snapshot ~/top-snapshot/top-data.duckdb.gz   # on the other machine (server stopped)
```

`--snapshot` also accepts a URL, or a plain `nse.duckdb` file.

Prefer to download the data first, without the server?

```bash
top-sync --nifty          # the Nifty 50 from Yahoo (1–2 minutes)
top-sync --bhav           # all BSE stocks + NSE/BSE ETFs + indices + delivery % (first run 1–2 hours)
top-sync --indices        # only NSE and BSE indices (first run 20–30 minutes)
top-sync --delivery       # only NSE delivery % and the FII/DII snapshot (first run 20–30 minutes)
top-sync --snapshot       # install the ready-made data snapshot from the GitHub releases (minutes)
top-leaderboard           # every strategy on every script for the Leaderboard page (hours; resumable)
top-sync                  # both
top-sync --bhav --years 2 # less history, faster first run
```

> [!NOTE]
> Don't run `top-sync` or `top-leaderboard` while `top-platform` is running on the same database; DuckDB allows one process at a time. Use **Sync history** and the Leaderboard page's **Run backtests** in the app instead, which run inside the server.

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
| Market data | `./data/nse.duckdb`, relative to the folder you start TOP from, or the path in `TOP_DB`. Holds the Nifty 50 (Yahoo), BSE stocks and ETFs (bhavcopies), and the split/bonus adjustments |
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

On Windows (PowerShell or Command Prompt):

```bat
cd Trade-Observability-Platform
git pull
.venv\Scripts\pip install -e .
```

`git pull` changes the files, but a `top-platform` that is already running keeps the old code. Always stop it (<kbd>Ctrl</kbd>+<kbd>C</kbd> in its window) and start it again from the same folder, so it also finds the same `data\nse.duckdb`.

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

## Automatic daily data update

TOP keeps every script's OHLC data (Nifty 50, NSE and BSE stocks, ETFs, indices, delivery %) current by itself.

**While `top-platform` runs**, a built-in scheduler reads the system clock, converts it to India time, and runs the full update once per weekday after **19:00 IST**, when the day's exchange files are out. If the PC was off or the server stopped, the missed update runs at the next start. The machine's own time zone does not matter. Exchange holidays find no new file and change nothing. A long leaderboard run does not hold up the data; it picks up the new bars afterwards. Hover over the DuckDB pill on the desk to see the last and next update.

**Cron, for when the server is not always running** (Linux and macOS):

```bash
top-sync --install-cron            # adds one crontab line; run it from your clone
top-sync --install-cron --at 18:30 # a different update time (IST)
```

The line runs `top-sync --auto` every 30 minutes. `--auto` updates only when a weekday's update time has passed and that day is not done yet:
- if `top-platform` is running, it asks the server to update (DuckDB allows only one program to open the store, so a plain `top-sync` would fail);
- otherwise it updates directly, then refreshes the leaderboard rows for scripts with new bars;
- overlapping runs are skipped through a lock file.

Output goes to `data/auto-update.log`; the last update is recorded in `data/auto-update.json`. `top-sync --auto --force` updates now. Remove the line with `crontab -e`.

On a fresh store (under 1,000 scripts) the automatic update refreshes only the Nifty 50; install the ready-made snapshot first.

| Setting | Flag | Environment variable | Default |
| --- | --- | --- | --- |
| Turn the server's scheduler off | `top-platform --no-auto-update` | `TOP_AUTO_UPDATE=0` | on |
| Update time (IST) | `top-platform --update-at`, `top-sync --at` | `TOP_AUTO_UPDATE_AT` | `19:00` |

On Windows, keep `top-platform` running (for example from Task Scheduler at log-on); its scheduler does the rest.

---

## Older CPUs

TOP pins `duckdb==1.1.3` and avoids NumPy so it runs on older x86 processors without SSE4.2/POPCNT (for example 2009-era laptops). Newer DuckDB and NumPy 2 builds stop there with `Illegal instruction`. Keep the pin, and don't install NumPy 2 into TOP's environment.

---

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Leaderboard **Run backtests** button grey, or a page looks unstyled (often on Windows) | Update to 0.3.1 or later and **restart** `top-platform`, then hard-reload (<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>R</kbd>). Older versions let Windows' registry serve `.css`/`.js` as `text/plain`. Then read the line under the progress bar: it says when the store has nothing to compute yet (click **Sync history** first) or when the server needs a restart |
| Leaderboard says *nothing to compute* | The server is using a database without history, usually because it was started from another folder. Start it from the project folder, set `TOP_DB`, or click **Sync history** in the charting desk |
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
| Some stocks show "no bars" | Click **Sync history** or run `top-sync`; Yahoo sometimes rate-limits (HTTP 429), so retry later |
| `Could not set lock on file … nse.duckdb` | Another process (usually `top-platform`) has the database open. Stop it, or sync from the app |
| BSE/ETF sync stopped partway | Run it again; finished days are skipped, so it resumes where it left off |
| Fundamentals error | Screener.in may be unreachable or rate-limiting; try later |
| `git clone` asks for a username and password | The URL is wrong or the repository is private. Public clones never need a password; check the URL is `https://github.com/garv08/Trade-Observability-Platform.git` |

Still stuck? [Open an issue](https://github.com/garv08/Trade-Observability-Platform/issues/new/choose) with your OS, Python version (`python3 --version`), and the full error.
