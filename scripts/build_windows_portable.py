"""Build the self-contained Windows offline package.

The package contains the official Python embeddable runtime, the ARTHIVIO app,
openpyxl and the Windows launchers. The target machine does not need Python,
Node, a database server, or internet access.

Usage:
    python scripts/build_windows_portable.py
    python scripts/build_windows_portable.py --zip
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST_ROOT = ROOT / "dist"
CACHE = ROOT / "build-cache"
APP_NAME = "ARTHIVIO-Offline"
PYTHON_VERSION = "3.14.6"
PYTHON_ZIP = f"python-{PYTHON_VERSION}-embed-amd64.zip"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/{PYTHON_ZIP}"

IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".pytest_cache")


def app_version() -> str:
    text = (ROOT / "app" / "server.py").read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "unknown"


def download_runtime() -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / PYTHON_ZIP
    if target.exists() and target.stat().st_size > 1_000_000:
        print(f"Using cached {target}")
        return target
    print(f"Downloading {PYTHON_URL}")
    tmp = target.with_suffix(".zip.tmp")
    with urllib.request.urlopen(PYTHON_URL, timeout=120) as response, \
            open(tmp, "wb") as out:
        shutil.copyfileobj(response, out)
    os.replace(tmp, target)
    print(f"Saved {target} ({target.stat().st_size:,} bytes)")
    return target


def copy_package(name: str, target_site: Path) -> None:
    source = ROOT / ".venv" / "Lib" / "site-packages" / name
    if not source.is_dir():
        raise SystemExit(f"Missing dependency folder: {source}. "
                         "Run: .venv\\Scripts\\python.exe -m pip install -r requirements.txt")
    shutil.copytree(source, target_site / name, ignore=IGNORE)


def build(do_zip: bool) -> Path:
    runtime_zip = download_runtime()
    if DIST_ROOT.exists():
        # Only remove the package folder and its zip, not unrelated user files.
        for path in (DIST_ROOT / APP_NAME,):
            if path.exists():
                shutil.rmtree(path)
    target = DIST_ROOT / APP_NAME
    target.mkdir(parents=True, exist_ok=True)

    runtime = target / "runtime"
    runtime.mkdir()
    print(f"Extracting Python {PYTHON_VERSION} embeddable runtime")
    with zipfile.ZipFile(runtime_zip) as zf:
        zf.extractall(runtime)

    print("Copying application")
    shutil.copytree(ROOT / "app", target / "app", ignore=IGNORE)
    shutil.copytree(ROOT / "docs", target / "docs", ignore=IGNORE)
    scripts_target = target / "scripts"
    scripts_target.mkdir()
    for path in (ROOT / "scripts").iterdir():
        if path.is_file() and path.name != "build_windows_portable.py":
            shutil.copy2(path, scripts_target / path.name)
    for name in ("README.md", "requirements.txt"):
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, target / name)

    site = runtime / "Lib" / "site-packages"
    site.mkdir(parents=True)
    for package in ("openpyxl", "openpyxl-3.1.5.dist-info",
                    "et_xmlfile", "et_xmlfile-2.0.0.dist-info"):
        copy_package(package, site)

    # The embeddable runtime ignores normal site-packages unless this file lists
    # it. `..` is the package root, which is where `import app` resolves.
    pth = runtime / "python314._pth"
    pth.write_text(
        "python314.zip\n"
        ".\n"
        "Lib\\site-packages\n"
        "..\n"
        "import site\n",
        encoding="ascii",
    )

    for name in ("data", "backups", "logs"):
        (target / name).mkdir(exist_ok=True)

    for bat in (ROOT / "packaging" / "windows").glob("*.bat"):
        shutil.copy2(bat, target / bat.name)

    version = app_version()
    (target / "VERSION.txt").write_text(
        f"ARTHIVIO offline edition\nBuild {version}\n"
        f"Python runtime {PYTHON_VERSION} (embeddable)\n",
        encoding="utf-8",
    )
    (target / "README-OFFLINE.txt").write_text(
        f"""ARTHIVIO OFFLINE EDITION - Build {version}
==========================================

No Python installation and no internet connection are needed.

FIRST RUN
1. Double-click "Start ARTHIVIO.bat".
2. The browser opens at http://127.0.0.1:8000/.
3. Create your business and owner login on the first-run page.
   Use a password of 12 or more characters.

EVERYDAY USE
- Start: double-click "Start ARTHIVIO.bat" or the desktop shortcut.
- Stop: close the ARTHIVIO server window.
- Data: the "data" folder. Do not delete it.
- Logs: the "logs" folder. Share the error ID with support if something fails.
- Backups: use "Backup ARTHIVIO.bat" and choose a folder on an external drive.
  The backup is verified before and after copying.

OPTIONAL AUTOSTART
- Run "Install autostart.bat" to add a desktop shortcut and start ARTHIVIO
  minimized at Windows login. Run "Remove autostart.bat" to undo it.

IMPORTANT
- This is a single-user offline package. Keep the whole folder together.
- Copying only the .exe or only the data folder is not a backup.
- A committed entry survives a power cut. Text still open in a form may not.
- Keep at least one verified backup on a different physical drive.
- GST outputs are working aids, not filed returns.
""",
        encoding="utf-8",
    )

    print("Testing embedded runtime")
    test = subprocess.run(
        [str(runtime / "python.exe"), "-c",
         "import openpyxl, sqlite3; from app import server; "
         "print('openpyxl', openpyxl.__version__); "
         "print('arthivio', server.APP_VERSION)"],
        cwd=target, capture_output=True, text=True, timeout=120)
    if test.returncode != 0:
        print(test.stdout)
        print(test.stderr)
        raise SystemExit("Embedded runtime test failed")
    print(test.stdout.strip())

    if do_zip:
        archive = DIST_ROOT / f"{APP_NAME}-{version}"
        print(f"Creating {archive}.zip")
        if Path(f"{archive}.zip").exists():
            Path(f"{archive}.zip").unlink()
        shutil.make_archive(str(archive), "zip", root_dir=DIST_ROOT,
                            base_dir=APP_NAME)
        print(f"ZIP: {archive}.zip")

    print(f"Built: {target}")
    print(f"Size:  {sum(p.stat().st_size for p in target.rglob('*') if p.is_file()):,} bytes")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the ARTHIVIO Windows offline package")
    parser.add_argument("--zip", action="store_true", help="Also create a ZIP archive")
    args = parser.parse_args()
    build(args.zip)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
