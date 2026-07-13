# Windows Setup (WSL2) — for Ryzen 3 / 8GB RAM laptops

Verilator and Yosys don't run natively on Windows in a reliable way. Use
WSL2 (Windows Subsystem for Linux) — it's free, built into Windows 10/11,
and VS Code + Pylance work inside it exactly like on native Linux.

## 1. Install WSL2 (one-time, ~10 min)

Open **PowerShell as Administrator** and run:

```powershell
wsl --install -d Ubuntu-22.04
```

Restart when prompted. On first launch of Ubuntu, set a username/password
(this is separate from your Windows login).

## 2. Install the EDA toolchain inside WSL2

Open the "Ubuntu" app from your Start menu (this is now your Linux
terminal), then:

```bash
sudo apt update
sudo apt install -y verilator yosys build-essential python3-pip python3-venv git
verilator --version
yosys -V
```

If `apt`'s Verilator version is old (< 4.2), see the note at the bottom.

## 3. Get the project into WSL2

Your Windows files are visible from WSL at `/mnt/c/Users/<you>/...`, but
**don't run the project from there** — cross-filesystem I/O (Windows disk
accessed from Linux) is noticeably slower and can cause odd file-lock
issues with Verilator's build step. Instead, copy the project into your
Linux home directory:

```bash
mkdir -p ~/projects
cp -r /mnt/c/Users/<you>/Downloads/EvoHDL ~/projects/
cd ~/projects/EvoHDL
```

(Or `git clone` it directly if you push this to GitHub — recommended, see
`PITCH_ONE_PAGER.md` for why a public repo matters for applications.)

## 4. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r config/requirements.txt
```

## 5. Tune config for 8GB RAM / Ryzen 3

Edit `config/system_config.yaml` before your first real run:

```yaml
population_size: 8        # was 24 -- start small
generations: 15           # was 30
max_parallel_evals: 1     # was 4 -- IMPORTANT: parallel Verilator builds will exhaust 8GB fast
```

Once you confirm a small run completes cleanly, you can raise
`max_parallel_evals` to 2 and watch RAM usage (Task Manager, or
`htop` inside WSL) before pushing further.

## 6. Run it

```bash
python run_self_learner.py --check-tools     # verify toolchain first
python run_self_learner.py                   # full run
```

In a second WSL terminal (open a new Ubuntu window):

```bash
cd ~/projects/EvoHDL
source .venv/bin/activate
streamlit run dashboard/app.py
```

Streamlit will print a `localhost:8501` link — open it in your normal
Windows browser, it works transparently across the WSL2/Windows boundary.

## 7. VS Code

Install the **WSL** extension in VS Code (on Windows), then from your
WSL terminal:

```bash
cd ~/projects/EvoHDL
code .
```

This opens VS Code running *against* the WSL filesystem — Pylance, your
Python interpreter, and the integrated terminal all run inside Linux
automatically. Select the `.venv` interpreter when VS Code prompts you
(bottom-right corner, or Ctrl+Shift+P → "Python: Select Interpreter").

## If apt's Verilator is too old

Ubuntu 22.04's repo Verilator is usually fine (≥ 4.2), but if
`verilator --version` shows something older than v4.2 or `run_self_learner.py --check-tools` complains, build from source (takes ~10-15 min on Ryzen 3):

```bash
sudo apt install -y git help2man perl python3 make g++ libfl2 libfl-dev zlibc zlib1g zlib1g-dev
git clone https://github.com/verilator/verilator
cd verilator
git checkout stable
autoconf && ./configure && make -j2   # -j2, not -j4 -- keep RAM headroom
sudo make install
```
