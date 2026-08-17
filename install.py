"""Installer for Helm Chess.

Checks that this Python can run the game, installs the two libraries it
needs, optionally puts a Stockfish binary in place, and offers a desktop
shortcut. Safe to run more than once -- it skips whatever is already done.

    python install.py                 # normal install
    python install.py --check         # report only, change nothing
    python install.py --no-shortcut   # skip the desktop shortcut
"""

import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MIN_PYTHON = (3, 8)

# Everything the game imports that is not in the standard library.
REQUIREMENTS = [
    ("chess", "chess>=1.10", "the rules of chess: legality, castling, promotion"),
    ("accessible_output2", "accessible_output2>=0.17",
     "speech through NVDA, JAWS, or SAPI"),
]

OK = "  [ok]   "
ADD = "  [add]  "
WARN = "  [warn] "
FAIL = "  [fail] "


def report(prefix, message):
    print(prefix + message)


def check_python():
    if sys.version_info < MIN_PYTHON:
        report(FAIL, "Python %d.%d or newer is required, this is %s"
               % (MIN_PYTHON[0], MIN_PYTHON[1], sys.version.split()[0]))
        return False
    report(OK, "Python %s at %s" % (sys.version.split()[0], sys.executable))
    return True


def check_tkinter():
    """Tkinter is standard, but some Linux distributions split it into a package."""
    try:
        import tkinter  # noqa: F401
        report(OK, "tkinter (the window that receives your keystrokes)")
        return True
    except ImportError:
        report(FAIL, "tkinter is missing. On Windows, reinstall Python with the "
                     "tcl/tk option ticked. On Debian or Ubuntu: "
                     "sudo apt install python3-tk")
        return False


def pip_install(spec):
    command = [sys.executable, "-m", "pip", "install", "--upgrade", spec]
    result = subprocess.run(command, capture_output=True, text=True)
    return result.returncode == 0, (result.stderr or result.stdout).strip()


def install_requirements(check_only=False):
    ok = True
    for module, spec, why in REQUIREMENTS:
        try:
            __import__(module)
            report(OK, "%s -- %s" % (module, why))
            continue
        except ImportError:
            pass

        if check_only:
            report(ADD, "%s would be installed -- %s" % (spec, why))
            continue

        report(ADD, "installing %s ..." % spec)
        success, output = pip_install(spec)
        if success:
            report(OK, "%s installed" % spec)
        else:
            ok = False
            report(FAIL, "could not install %s" % spec)
            for line in output.splitlines()[-5:]:
                print("         " + line)
    return ok


def check_stockfish():
    """Stockfish is optional. Without it the built-in engine takes over."""
    sys.path.insert(0, HERE)
    try:
        from engine import find_stockfish
        path = find_stockfish()
    except Exception:
        path = shutil.which("stockfish")

    if path:
        report(OK, "Stockfish found at %s" % path)
    else:
        report(WARN, "no Stockfish found -- the built-in engine will be used")
        print("         To use Stockfish instead, download it from")
        print("         https://stockfishchess.org/download/ and put the")
        print("         executable in: %s" % os.path.join(HERE, "engines"))
    return True


def make_shortcut():
    """Windows desktop shortcut. Quietly skipped elsewhere."""
    if os.name != "nt":
        return True
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(desktop):
        report(WARN, "no Desktop folder found, skipping the shortcut")
        return True

    target = os.path.join(desktop, "Helm Chess.lnk")
    launcher = os.path.join(HERE, "helm_chess.py")
    # pythonw runs it without a console window tagging along.
    runner = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(runner):
        runner = sys.executable

    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%s'); "
        "$s.TargetPath = '%s'; "
        "$s.Arguments = '\"%s\"'; "
        "$s.WorkingDirectory = '%s'; "
        "$s.Description = 'Helm Chess'; "
        "$s.Save()" % (target, runner, launcher, HERE)
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and os.path.isfile(target):
        report(OK, "desktop shortcut created: %s" % target)
        return True
    report(WARN, "could not create the desktop shortcut")
    return True


def verify():
    """Import the game's own modules, so a broken install fails here and not later."""
    sys.path.insert(0, HERE)
    for module in ("version", "describe", "engine", "updater"):
        try:
            __import__(module)
        except Exception as exc:
            report(FAIL, "%s.py failed to load: %s" % (module, exc))
            return False
    report(OK, "all Helm Chess modules load")
    return True


def main():
    parser = argparse.ArgumentParser(description="Install Helm Chess.")
    parser.add_argument("--check", action="store_true",
                        help="report what is missing without installing anything")
    parser.add_argument("--no-shortcut", action="store_true",
                        help="do not create a desktop shortcut")
    args = parser.parse_args()

    print("Helm Chess installer")
    print("=" * 60)

    steps = [check_python(), check_tkinter()]
    if not all(steps):
        print("\nFix the problems above, then run this again.")
        return 1

    if not install_requirements(check_only=args.check):
        print("\nSome dependencies could not be installed.")
        print("Try running this from a command prompt as your own user, or:")
        print("  %s -m pip install --user chess accessible_output2" % sys.executable)
        return 1

    check_stockfish()

    if args.check:
        print("\nCheck complete. Nothing was changed.")
        return 0

    if not verify():
        return 1
    if not args.no_shortcut:
        make_shortcut()

    print("=" * 60)
    print("Done. Start the game with:")
    print("  python \"%s\"" % os.path.join(HERE, "helm_chess.py"))
    print("Press F1 inside the game for the key list.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
