# Moodle Validator & Auto-Fixer Toolkit

This toolkit helps you ensure that any Moodle plugin passes the strict Moodle Marketplace code review standards. It uses the official Moodle PHP Code Beautifier and Fixer (`moodle-plugin-ci`).

## 1. Validating a Plugin (`validator.py`)
Run this tool to check if your plugin has any errors. It will scan for PHP syntax errors, Moodle coding style violations, and Mustache template issues.

**How to use:**
```bash
python3 /home/mohammad/Dev/validator/validator.py /path/to/your/plugin
```

**Example:**
```bash
python3 /home/mohammad/Dev/validator/validator.py /home/mohammad/Dev/plugins/local/moodle_local_smartdashboard
```

---

## 2. Auto-Fixing a Plugin (`fixer.py`)
If the validator finds formatting errors (like wrong spaces, indentation, or array styles), this tool will automatically fix the majority of them for you.

**How to use:**
```bash
python3 /home/mohammad/Dev/validator/fixer.py /path/to/your/plugin
```

**Example:**
```bash
python3 /home/mohammad/Dev/validator/fixer.py /home/mohammad/Dev/plugins/local/moodle_local_smartdashboard
```

---

## 3. Injecting Missing Moodle Boilerplates
Moodle strictly requires a GNU GPL License header at the top of **every single** `.php` file. If you created lots of new files and forgot to add the 15-line license text, this tool will safely inject it into all missing files at once.

**How to use (add `--add-boilerplates`):**
```bash
python3 /home/mohammad/Dev/validator/fixer.py /path/to/your/plugin --add-boilerplates
```

**Example:**
```bash
python3 /home/mohammad/Dev/validator/fixer.py /home/mohammad/Dev/plugins/local/moodle_local_smartdashboard --add-boilerplates
```

### Advanced Boilerplate Options
By default, the script sets the author to "Mohammad Nabil" and the email to "mohammad@smartlearn.education". If you want to change it, you can pass custom options:
```bash
python3 /home/mohammad/Dev/validator/fixer.py /path/to/your/plugin --add-boilerplates --author "John Doe" --email "john@example.com"
```
