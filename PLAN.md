# 📐 Plan: Python Moodle Plugin Validator Utility

This project acts as a wrapper around `moodle-plugin-ci`, automatically managing its installation, running validation checks against any target Moodle plugin folder, and presenting a clean, colorized terminal summary.

## 🗂️ 1. Proposed Project Structure
```
validator/
├── validator.py          # Main Python CLI entry point
├── requirements.txt      # Python dependencies (e.g., colorama or rich for nice terminal output)
└── PLAN.md               # This project plan
```

---

## ⚙️ 2. Core Features of the Python Script
The Python script (`validator.py`) will perform the following actions automatically:
1. **Target Directory Detection:** Accept a directory path as an argument (e.g., `python validator.py /path/to/local_smartdashboard`).
2. **Environment Pre-check:** Check if `php` is installed on the host system.
3. **Automatic Phar Management:**
   - Look for `moodle-plugin-ci.phar` in a local cache directory (e.g., `~/.cache/moodle-plugin-ci/`).
   - If not found, download it automatically from GitHub via Python's `urllib` or `requests`.
4. **Execution Wrapper:** Run the standard validation checks using Python's `subprocess` module:
   - `phplint` (PHP syntax)
   - `mustache` (Mustache template linting)
   - `codechecker` (Moodle coding standards)
5. **Output Beautifier:** Parse the raw, messy CLI outputs and present a clean, color-coded dashboard in the terminal indicating exactly which files failed and why.

---

## 🛠️ 3. Step-by-Step Implementation Steps

### Step 1: Create the Project Directory
Initialize a new directory outside of your Moodle installation:
```bash
mkdir -p /home/mohammad/Dev/validator
```

### Step 2: Implement the Downloader & Environment Check
In `validator.py`, write functions to check if `php` exists and fetch `moodle-plugin-ci.phar` from GitHub if it's missing.

### Step 3: Implement Check Execution
Use Python's `subprocess.run()` to execute commands like:
```bash
php moodle-plugin-ci.phar phplint <target_plugin_path>
```
Capture the outputs (`stdout` and `stderr`) programmatically.

### Step 4: Add Output Formatting
Parse the output of each command. If a command exits with code `0`, print a green `[PASS]`. If it fails (code > `0`), extract the file path and line numbers from the error stack and print them in bold red.

### Step 5: Test and Command Integration
Test the Python script against any plugin folder:
```bash
python validator.py /home/mohammad/Dev/plugins/local/moodle_local_smartdashboard
```
