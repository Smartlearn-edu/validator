#!/usr/bin/env python3
import os
import sys
import re
import shutil
import subprocess
import urllib.request
import argparse
import contextlib
from pathlib import Path

# Try importing rich, fall back to print with message if not found
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
    from rich.syntax import Syntax
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# Setup basic console if rich is not present
class MockConsole:
    def print(self, *args, **kwargs):
        # Strip rich-like formatting tags
        text = " ".join(map(str, args))
        clean_text = re.sub(r"\[/?\w+\s*[^\]]*\]", "", text)
        print(clean_text)
        
    @contextlib.contextmanager
    def status(self, status, spinner=None):
        print(f"... {status}")
        yield

if HAS_RICH:
    console = Console()
else:
    console = MockConsole()
    print("Warning: 'rich' library not found. Running in plain text mode. (Install with: pip install rich)")

CACHE_DIR = Path.home() / ".cache" / "moodle-plugin-ci"
PHAR_PATH = CACHE_DIR / "moodle-plugin-ci.phar"
DOWNLOAD_URL = "https://github.com/moodlehq/moodle-plugin-ci/releases/latest/download/moodle-plugin-ci.phar"

def check_environment():
    """Verify that PHP is installed on the system."""
    if not shutil.which("php"):
        console.print("[bold red]Error: PHP is not installed on this system.[/bold red]")
        console.print("Please install PHP (>= 7.1) to run the Moodle Plugin CI validator.")
        sys.exit(1)

def ensure_phar():
    """Ensure moodle-plugin-ci.phar exists in the cache, downloading it if necessary."""
    if PHAR_PATH.exists():
        return

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    console.print(f"[cyan]moodle-plugin-ci.phar not found. Downloading from GitHub...[/cyan]")
    
    try:
        req = urllib.request.Request(
            DOWNLOAD_URL, 
            headers={"User-Agent": "MoodlePluginValidator/1.0"}
        )
        
        with urllib.request.urlopen(req) as response:
            total_size = int(response.info().get('Content-Length', 0))
            
            if HAS_RICH:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                    console=console
                ) as progress:
                    task = progress.add_task("Downloading...", total=total_size)
                    
                    with open(PHAR_PATH, "wb") as f:
                        chunk_size = 1024 * 16
                        while True:
                            chunk = response.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            progress.update(task, advance=len(chunk))
            else:
                print("Downloading moodle-plugin-ci.phar...")
                with open(PHAR_PATH, "wb") as f:
                    shutil.copyfileobj(response, f)
                        
        console.print("[bold green]Download complete![/bold green]")
        PHAR_PATH.chmod(PHAR_PATH.stat().st_mode | 0o111)
        
    except Exception as e:
        console.print(f"[bold red]Failed to download moodle-plugin-ci.phar: {e}[/bold red]")
        if PHAR_PATH.exists():
            PHAR_PATH.unlink()
        sys.exit(1)

def get_plugin_component(plugin_path: Path) -> str | None:
    """Parse version.php to find the plugin component name."""
    version_file = plugin_path / "version.php"
    if not version_file.exists():
        return None
    try:
        content = version_file.read_text(encoding="utf-8")
        # Match $plugin->component = 'local_smartdashboard'; or similar
        match = re.search(r'\$plugin->component\s*=\s*[\'"]([^\'"]+)[\'"]', content)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None

def find_moodle_root_from_path(path: Path) -> Path | None:
    """Walk up from path to find a directory containing version.php and config.php."""
    current = path.resolve()
    for parent in [current] + list(current.parents):
        if (parent / "version.php").exists() and (parent / "config.php").exists():
            # Check if this looks like a Moodle root, not a plugin root
            # Moodle root has config.php and config-dist.php
            if (parent / "config-dist.php").exists() or (parent / "lib" / "moodlelib.php").exists():
                return parent
    return None

def get_mdk_www_path() -> Path | None:
    """Try to read moodle web path from mdk configuration."""
    mdk_path = shutil.which("mdk") or "/home/mohammad/.local/bin/mdk"
    if os.path.exists(mdk_path):
        try:
            res = subprocess.run([mdk_path, "config", "list"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    if "www" in line and ":" in line:
                        parts = line.split(":", 1)
                        path_str = parts[1].strip()
                        p = Path(path_str).expanduser()
                        # If www has a public folder, check both
                        if (p / "public").exists():
                            p = p / "public"
                        if (p / "version.php").exists() and (p / "config.php").exists():
                            return p
        except Exception:
            pass
    return None

def detect_moodle_root(plugin_path: Path) -> Path | None:
    """Detect Moodle root using path-based, mdk-based and common fallbacks."""
    # 1. Check path tree
    root = find_moodle_root_from_path(plugin_path)
    if root:
        return root
        
    # 2. Check MDK configuration
    root = get_mdk_www_path()
    if root:
        return root
        
    # 3. Check common path fallbacks
    for path_str in ["/var/www/html/moodle_dev/public", "/var/www/html/moodle_dev", "/var/www/html/moodle/public", "/var/www/html/moodle"]:
        p = Path(path_str)
        if p.exists() and (p / "version.php").exists() and (p / "config.php").exists():
            return p
            
    return None

@contextlib.contextmanager
def temporary_moodle_link(plugin_path: Path, moodle_root: Path):
    """Context manager to link a plugin path into a Moodle directory if it is outside Moodle."""
    component = get_plugin_component(plugin_path)
    if not component:
        # Fallback: run directly without linking
        yield plugin_path, None, None
        return
        
    parts = component.split("_", 1)
    if len(parts) != 2:
        yield plugin_path, component, None
        return
        
    plugintype, pluginname = parts
    target_link = moodle_root / plugintype / pluginname
    
    # If target link is the same as the plugin path, we are already inside Moodle
    try:
        if target_link.exists() and target_link.resolve() == plugin_path.resolve():
            yield plugin_path, component, None
            return
    except Exception:
        pass
        
    # We need to temporarily link
    backup_path = None
    existing_link_target = None
    was_symlink = False
    
    try:
        # Ensure parent exists (e.g. local/, mod/)
        target_link.parent.mkdir(parents=True, exist_ok=True)
        
        if target_link.exists() or target_link.is_symlink():
            if target_link.is_symlink():
                existing_link_target = os.readlink(target_link)
                was_symlink = True
                target_link.unlink()
            else:
                backup_path = target_link.with_name(f"{target_link.name}.bak_{os.getpid()}")
                target_link.rename(backup_path)
                
        os.symlink(plugin_path.resolve(), target_link)
        yield target_link, component, target_link
        
    finally:
        # Clean up the symlink
        if target_link.is_symlink():
            target_link.unlink()
            
        # Restore backup or original symlink
        if backup_path and backup_path.exists():
            backup_path.rename(target_link)
        elif was_symlink and existing_link_target:
            os.symlink(existing_link_target, target_link)

def sanitize_path(path_str: str, symlink_path: Path | None, original_path: Path) -> str:
    """Replace occurrences of symlink path with original path in outputs."""
    if symlink_path:
        sym_abs = str(symlink_path.resolve())
        orig_abs = str(original_path.resolve())
        if sym_abs in path_str:
            path_str = path_str.replace(sym_abs, orig_abs)
        sym_raw = str(symlink_path)
        if sym_raw in path_str:
            path_str = path_str.replace(sym_raw, orig_abs)
    return path_str

# Output Parsers

def parse_phplint(output: str, symlink_path: Path | None, original_path: Path) -> dict:
    if "No syntax error found" in output:
        return {"status": "PASS", "errors": []}
        
    errors = []
    blocks = output.split("------------------------------------------------------------")
    for block in blocks:
        block = block.strip()
        if not block.startswith("Parse error:"):
            continue
            
        lines = block.splitlines()
        first_line = lines[0]
        
        m = re.match(r"^Parse error:\s*(.*?):(\d+)$", first_line)
        if m:
            file_path = sanitize_path(m.group(1), symlink_path, original_path)
            line_no = int(m.group(2))
            
            # Message is the last line
            details = lines[-1].strip()
            # Middle lines are code snippet
            code_lines = lines[1:-1]
            code_snippet = "\n".join(code_lines).strip()
            
            errors.append({
                "file": file_path,
                "line": line_no,
                "snippet": code_snippet,
                "message": details
            })
            
    return {
        "status": "FAIL" if errors else "PASS",
        "errors": errors
    }

def parse_phpcs(output: str, symlink_path: Path | None, original_path: Path) -> dict:
    if "FOUND" not in output and "Time:" in output:
        return {"status": "PASS", "files": {}}
        
    files = {}
    file_blocks = output.split("FILE: ")
    for block in file_blocks[1:]:
        lines = block.splitlines()
        if not lines:
            continue
            
        filepath = sanitize_path(lines[0].strip(), symlink_path, original_path)
        file_errors = []
        current_error = None
        
        for line in lines[1:]:
            line = line.rstrip()
            if not line:
                continue
                
            m = re.match(r"^\s*(\d+)\s*\|\s*(ERROR|WARNING)\s*\|\s*\[([x\s])\]\s*(.*)$", line)
            if m:
                if current_error:
                    file_errors.append(current_error)
                
                line_no = int(m.group(1))
                err_type = m.group(2).strip()
                fixable = m.group(3) == 'x'
                message = m.group(4).strip()
                
                current_error = {
                    "line": line_no,
                    "type": err_type,
                    "fixable": fixable,
                    "message": message
                }
            elif current_error and re.match(r"^\s*\|\s*\|\s*(.*)$", line):
                m_sub = re.match(r"^\s*\|\s*\|\s*(.*)$", line)
                current_error["message"] += " " + m_sub.group(1).strip()
            elif "FOUND" in line or "---" in line or "PHPCBF CAN FIX" in line:
                if current_error:
                    file_errors.append(current_error)
                    current_error = None
                    
        if current_error:
            file_errors.append(current_error)
            
        if file_errors:
            files[filepath] = file_errors
            
    return {
        "status": "FAIL" if files else "PASS",
        "files": files
    }

def parse_mustache(output: str, symlink_path: Path | None, original_path: Path) -> dict:
    results = []
    lines = output.splitlines()
    has_errors = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        m = re.match(r"^(.*?)\s*-\s*(OK|WARNING|ERROR|INFO):\s*(.*)$", line)
        if m:
            file_path = sanitize_path(m.group(1).strip(), symlink_path, original_path)
            status = m.group(2).strip()
            message = m.group(3).strip()
            
            if status == "ERROR":
                has_errors = True
                
            results.append({
                "file": file_path,
                "status": status,
                "message": message
            })
        elif line.startswith("Skipping mobile app template:"):
            file_path = sanitize_path(line.replace("Skipping mobile app template:", "").strip(), symlink_path, original_path)
            results.append({
                "file": file_path,
                "status": "SKIP",
                "message": "Mobile app template (skipped)"
            })
            
    return {
        "status": "FAIL" if has_errors else "PASS",
        "results": results
    }

def parse_validate(output: str, exit_code: int) -> dict:
    lines = output.splitlines()
    checks = []
    errors = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("RUN") or line.startswith("Validating"):
            continue
            
        if line.startswith(">"):
            checks.append(line[1:].strip())
        else:
            errors.append(line)
            
    return {
        "status": "FAIL" if exit_code != 0 or errors else "PASS",
        "checks": checks,
        "errors": errors
    }

def run_phpcbf(plugin_path: Path, moodle_root: Path | None, original_path: Path, symlink_path: Path | None):
    """Run phpcbf to fix formatting issues."""
    console.print("\n[bold yellow]🔧 Running phpcbf (Code Beautifier and Fixer)...[/bold yellow]")
    
    cmd = ["php", str(PHAR_PATH), "phpcbf"]
    cmd.append(str(plugin_path))
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        # phpcbf returns exit code 1 if files were fixed, 0 if nothing was fixed, 2 if some errors couldn't be fixed
        output = sanitize_path(res.stdout + res.stderr, symlink_path, original_path)
        console.print(output)
        
        if res.returncode in [0, 1]:
            console.print("[bold green]✓ phpcbf execution finished successfully.[/bold green]")
        else:
            console.print("[bold yellow]! phpcbf finished, but some violations could not be automatically fixed.[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]Failed to run phpcbf: {e}[/bold red]")

def get_php_version() -> str:
    try:
        res = subprocess.run(["php", "-v"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0 and res.stdout:
            first_line = res.stdout.splitlines()[0]
            m = re.search(r"PHP\s+([^\s]+)", first_line)
            if m:
                return m.group(1)
            return first_line
    except Exception:
        pass
    return "Unknown"

def main():
    parser = argparse.ArgumentParser(description="📐 Moodle Plugin Validator Utility")
    parser.add_argument("plugin", nargs="?", default=".", help="Path to the Moodle plugin directory (default: current directory)")
    parser.add_argument("-m", "--moodle", help="Path to the Moodle installation root")
    parser.add_argument("-c", "--checks", default="validate,phplint,phpcs,mustache", help="Comma-separated checks to run (validate, phplint, phpcs, mustache)")
    parser.add_argument("--fix", action="store_true", help="Run phpcbf to automatically fix codechecker style errors")
    
    args = parser.parse_args()
    
    # Verify environment
    check_environment()
    ensure_phar()
    
    plugin_path = Path(args.plugin).resolve()
    if not plugin_path.exists() or not plugin_path.is_dir():
        console.print(f"[bold red]Error: Target plugin path does not exist or is not a directory: {plugin_path}[/bold red]")
        sys.exit(1)
        
    version_file = plugin_path / "version.php"
    if not version_file.exists():
        console.print(f"[bold red]Error: The target directory does not contain a version.php file. Is it a Moodle plugin?[/bold red]")
        sys.exit(1)
        
    # Detect Moodle path
    moodle_root = None
    if args.moodle:
        moodle_root = Path(args.moodle).resolve()
        if not moodle_root.exists() or not (moodle_root / "version.php").exists() or not (moodle_root / "config.php").exists():
            console.print(f"[bold yellow]Warning: Specified Moodle path does not appear to be a valid Moodle root: {moodle_root}[/bold yellow]")
    else:
        moodle_root = detect_moodle_root(plugin_path)
        
    # Set up selected checks
    enabled_checks = [c.strip().lower() for c in args.checks.split(",")]
    
    # CLI Title Header
    if HAS_RICH:
        console.print(Panel(
            "[bold green]📐 MOODLE PLUGIN VALIDATOR[/bold green]\n"
            f"[dim]Wrapper utility for moodle-plugin-ci.phar[/dim]",
            expand=False,
            border_style="green"
        ))
    else:
        print("📐 MOODLE PLUGIN VALIDATOR")
        print("-------------------------")
        
    # Show metadata table
    php_ver = get_php_version()
    component = get_plugin_component(plugin_path) or "Unknown"
    
    if HAS_RICH:
        meta_table = Table.grid(padding=(0, 2))
        meta_table.add_column("Key", style="cyan")
        meta_table.add_column("Value", style="white")
        meta_table.add_row("Target Plugin:", f"{plugin_path} ([bold magenta]{component}[/bold magenta])")
        meta_table.add_row("Moodle Root:", f"{moodle_root}" if moodle_root else "[yellow]None (Some checks might be skipped or fail)[/yellow]")
        meta_table.add_row("PHP Version:", php_ver)
        meta_table.add_row("PHAR Path:", str(PHAR_PATH))
        console.print(meta_table)
        console.print("-" * 60)
    else:
        print(f"Target Plugin: {plugin_path} ({component})")
        print(f"Moodle Root:   {moodle_root if moodle_root else 'None'}")
        print(f"PHP Version:   {php_ver}")
        print("------------------------------------------------------------")
        
    # Context link to run inside Moodle
    with contextlib.ExitStack() as stack:
        active_plugin_path = plugin_path
        symlink_path = None
        
        if moodle_root:
            active_plugin_path, _, symlink_path = stack.enter_context(temporary_moodle_link(plugin_path, moodle_root))
            
        results = {}
        
        # 1. Run phpcbf if --fix requested
        if args.fix:
            run_phpcbf(active_plugin_path, moodle_root, plugin_path, symlink_path)
            
        # 2. RUN VALIDATE Check
        if "validate" in enabled_checks:
            if not moodle_root:
                results["validate"] = {"status": "SKIPPED", "reason": "Requires a Moodle root path (--moodle)"}
            else:
                with console.status("[bold blue]Running validation check...[/bold blue]"):
                    cmd = ["php", str(PHAR_PATH), "validate", "--moodle", str(moodle_root), str(active_plugin_path)]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    results["validate"] = parse_validate(res.stdout + res.stderr, res.returncode)
                    
        # 3. RUN PHPLINT Check
        if "phplint" in enabled_checks:
            with console.status("[bold blue]Running PHP Syntax Linting...[/bold blue]"):
                cmd = ["php", str(PHAR_PATH), "phplint", str(active_plugin_path)]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                results["phplint"] = parse_phplint(res.stdout + res.stderr, symlink_path, plugin_path)
                
        # 4. RUN PHPCS Check (Codechecker)
        if "phpcs" in enabled_checks:
            with console.status("[bold blue]Running Moodle CodeChecker (PHPCS)...[/bold blue]"):
                cmd = ["php", str(PHAR_PATH), "phpcs", str(active_plugin_path)]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
                results["phpcs"] = parse_phpcs(res.stdout + res.stderr, symlink_path, plugin_path)
                
        # 5. RUN MUSTACHE Check
        if "mustache" in enabled_checks:
            if not moodle_root:
                results["mustache"] = {"status": "SKIPPED", "reason": "Requires a Moodle root path (--moodle)"}
            else:
                with console.status("[bold blue]Running Mustache Templates Linting...[/bold blue]"):
                    cmd = ["php", str(PHAR_PATH), "mustache", "--moodle", str(moodle_root), str(active_plugin_path)]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    results["mustache"] = parse_mustache(res.stdout + res.stderr, symlink_path, plugin_path)
                    
        # --- Present Results Summary ---
        console.print("\n[bold]Validation Summary:[/bold]")
        
        all_passed = True
        for check, res_data in results.items():
            status = res_data.get("status")
            if status == "PASS":
                console.print(f"  [bold green]✓[/bold green] {check:<10} : [bold green]PASS[/bold green]")
            elif status == "SKIPPED":
                console.print(f"  [bold yellow]![/bold yellow] {check:<10} : [bold yellow]SKIPPED[/bold yellow] ({res_data.get('reason')})")
            else:
                console.print(f"  [bold red]✗[/bold red] {check:<10} : [bold red]FAIL[/bold red]")
                all_passed = False
                
        # --- Present Detailed Failure Reports ---
        for check, res_data in results.items():
            status = res_data.get("status")
            if status != "FAIL":
                continue
                
            console.print("\n" + "=" * 60)
            console.print(f"[bold red]❌ DETAILED FAILURE REPORT: {check.upper()}[/bold red]")
            console.print("=" * 60)
            
            if check == "validate":
                for err in res_data.get("errors", []):
                    console.print(f"[red]{err}[/red]")
                    
            elif check == "phplint":
                for err in res_data.get("errors", []):
                    console.print(f"\n[bold red]Parse Error in {err['file']} on line {err['line']}:[/bold red]")
                    console.print(f"Message: [yellow]{err['message']}[/yellow]")
                    if err["snippet"]:
                        console.print("[dim]Snippet:[/dim]")
                        syntax = Syntax(err["snippet"], "php", theme="monokai", line_numbers=True, start_line=max(1, err["line"] - 2))
                        console.print(syntax)
                        
            elif check == "phpcs":
                files_errors = res_data.get("files", {})
                for file_path, errors in files_errors.items():
                    console.print(f"\n[bold cyan]File: {file_path}[/bold cyan]")
                    
                    if HAS_RICH:
                        table = Table(show_header=True, header_style="bold blue")
                        table.add_column("Line", style="dim", justify="right", width=6)
                        table.add_column("Type", width=10)
                        table.add_column("Fixable", justify="center", width=8)
                        table.add_column("Message", ratio=1)
                        
                        for err in errors:
                            type_text = f"[bold red]ERROR[/bold red]" if err["type"] == "ERROR" else f"[bold yellow]WARNING[/bold yellow]"
                            fix_text = f"[green]Yes[/green]" if err["fixable"] else "[grey]No[/grey]"
                            table.add_row(str(err["line"]), type_text, fix_text, err["message"])
                            
                        console.print(table)
                    else:
                        for err in errors:
                            fix_marker = "[x]" if err["fixable"] else "[ ]"
                            print(f"  Line {err['line']} | {err['type']} | {fix_marker} {err['message']}")
                            
            elif check == "mustache":
                results_list = res_data.get("results", [])
                
                if HAS_RICH:
                    table = Table(show_header=True, header_style="bold blue")
                    table.add_column("Template File", ratio=1)
                    table.add_column("Status", width=10)
                    table.add_column("Details", ratio=1)
                    
                    for r in results_list:
                        status_text = ""
                        if r["status"] == "OK":
                            status_text = "[bold green]OK[/bold green]"
                        elif r["status"] == "WARNING":
                            status_text = "[bold yellow]WARNING[/bold yellow]"
                        elif r["status"] == "ERROR":
                            status_text = "[bold red]ERROR[/bold red]"
                        elif r["status"] == "SKIP":
                            status_text = "[dim]SKIP[/dim]"
                        else:
                            status_text = r["status"]
                            
                        table.add_row(r["file"], status_text, r["message"])
                    console.print(table)
                else:
                    for r in results_list:
                        print(f"  {r['file']} | {r['status']} | {r['message']}")
                        
        console.print("")
        if all_passed:
            console.print("[bold green]🎉 All checks passed! Beautiful code.[/bold green]\n")
            sys.exit(0)
        else:
            console.print("[bold red]❌ Some validation checks failed. Please fix the violations listed above.[/bold red]\n")
            sys.exit(1)

if __name__ == "__main__":
    main()
