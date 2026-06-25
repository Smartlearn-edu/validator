#!/usr/bin/env python3
import sys
import os
import subprocess
import argparse
import datetime
from pathlib import Path

# Paths
PHAR_PATH = "/home/mohammad/.cache/moodle-plugin-ci/moodle-plugin-ci.phar"

def get_boilerplate(package_name, author, email, year):
    return f"""<?php
// This file is part of Moodle - https://moodle.org/
//
// Moodle is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// Moodle is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with Moodle.  If not, see <https://www.gnu.org/licenses/>.

/**
 * {package_name} plugin.
 *
 * @package     {package_name}
 * @copyright   {year} {author} <{email}>
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
"""

def fix_boilerplates(plugin_dir, package_name, author, email, year):
    """Safely injects Moodle boilerplate if missing."""
    print("... Scanning for files missing Moodle boilerplates ...")
    plugin_path = Path(plugin_dir)
    fixed_count = 0

    for filepath in plugin_path.rglob('*.php'):
        if 'vendor' in filepath.parts or 'node_modules' in filepath.parts:
            continue
            
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check if the full boilerplate already exists
        if "GNU General Public License" in content and "https://moodle.org" in content:
            continue

        # If it has a short header, replace it, otherwise prepend
        if content.startswith("<?php"):
            # Strip out any existing short PHP opening or partial comments at the top
            content_without_php = content[5:].lstrip()
            # If there's an existing short moodle comment, remove it
            if content_without_php.startswith("// This file is part of Moodle"):
                lines = content_without_php.split('\n')
                new_lines = []
                in_short_comment = True
                for line in lines:
                    if in_short_comment and (line.startswith('//') or line.strip() == '' or line.startswith('/**')):
                        if line.startswith('namespace') or line.startswith('defined') or line.startswith('class') or line.startswith('require'):
                            in_short_comment = False
                            new_lines.append(line)
                    else:
                        in_short_comment = False
                        new_lines.append(line)
                content_without_php = '\n'.join(new_lines).lstrip()

            new_content = get_boilerplate(package_name, author, email, year) + "\n" + content_without_php
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            fixed_count += 1
            print(f"  [FIXED] Added boilerplate to: {filepath.relative_to(plugin_dir)}")
            
    print(f"✓ Fixed {fixed_count} missing boilerplates.\n")


def run_phpcbf(plugin_dir):
    """Runs the Moodle Code Beautifier and Fixer"""
    print("... Running Moodle Code Beautifier and Fixer (PHPCBF) ...")
    if not os.path.exists(PHAR_PATH):
        print(f"❌ Error: moodle-plugin-ci.phar not found at {PHAR_PATH}")
        sys.exit(1)

    try:
        # phpcbf returns exit code 1 if it fixed files, 0 if nothing needed fixing, and 2+ for errors
        result = subprocess.run(
            ['php', PHAR_PATH, 'phpcbf', plugin_dir],
            capture_output=True,
            text=True
        )
        # We just print the output because it's usually helpful
        if "A TOTAL OF" in result.stdout:
            for line in result.stdout.split('\n'):
                if "A TOTAL OF" in line or "FIXED IN" in line:
                    print(f"  [PHPCBF] {line.strip()}")
        else:
            print("  [PHPCBF] No fixable formatting errors found or all already fixed.")
            
        print("✓ PHPCBF formatting complete.\n")
    except Exception as e:
        print(f"❌ Error running PHPCBF: {e}")

def main():
    parser = argparse.ArgumentParser(description="Moodle Plugin Auto-Fixer Utility")
    parser.add_argument("plugin_dir", help="Path to the Moodle plugin directory")
    parser.add_argument("--add-boilerplates", action="store_true", help="Auto-inject missing GPL boilerplates")
    parser.add_argument("--author", default="Mohammad Nabil", help="Author name for boilerplates")
    parser.add_argument("--email", default="mohammad@smartlearn.education", help="Author email for boilerplates")
    
    args = parser.parse_args()
    plugin_dir = os.path.abspath(args.plugin_dir)
    package_name = os.path.basename(plugin_dir).replace('moodle_', '') # Guess package name from folder
    current_year = datetime.datetime.now().year

    if not os.path.isdir(plugin_dir):
        print(f"Error: {plugin_dir} is not a valid directory.")
        sys.exit(1)

    print("╭───────────────────────────────────────────╮")
    print("│ 🛠️ MOODLE PLUGIN AUTO-FIXER                │")
    print("╰───────────────────────────────────────────╯")
    print(f"Target Plugin:  {plugin_dir} ({package_name})")
    print("-" * 60)

    # 1. Run standard PHPCBF formatter (Always safe)
    run_phpcbf(plugin_dir)

    # 2. Add boilerplates if requested
    if args.add_boilerplates:
        fix_boilerplates(plugin_dir, package_name, args.author, args.email, current_year)
    else:
        print("💡 Tip: Run with --add-boilerplates to automatically inject missing Moodle GPL headers.")

    print("-" * 60)
    print("🎉 Auto-fixing complete! Run validator.py to check remaining errors.")

if __name__ == "__main__":
    main()
