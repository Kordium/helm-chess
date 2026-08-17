"""Build Project Golem into a single Windows executable.

    python build_exe.py

The result is dist/ProjectGolem.exe, which runs on a machine with no Python
installed at all. That is the real reason to build it.

A word on what this does not do: it does not protect the source. PyInstaller
packs the Python bytecode into the executable, and freely available tools
unpack it again in seconds. Treat the exe as a convenience for people who do
not want to install Python, not as a lock on the code.
"""

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "ProjectGolem"


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
        return True
    except ImportError:
        pass
    print("PyInstaller is not installed. Installing it now...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("Could not install PyInstaller:")
        print((result.stderr or result.stdout)[-2000:])
        return False
    return True


def build():
    sounds = os.path.join(HERE, "sounds")
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile",
        "--windowed",               # no console window behind the game
        "--name", NAME,
        # accessible_output2 ships the screen reader client DLLs as data, and
        # loads its output backends by name, so nothing can be pruned.
        "--collect-all", "accessible_output2",
        "--collect-submodules", "accessible_output2.outputs",
        "--hidden-import", "chess",
        "--hidden-import", "chess.engine",
        "--hidden-import", "chess.pgn",
    ]
    if os.path.isdir(sounds):
        command += ["--add-data", "%s%ssounds" % (sounds, os.pathsep)]
    command.append(os.path.join(HERE, "project_golem.py"))

    print("building...")
    result = subprocess.run(command, cwd=HERE)
    if result.returncode != 0:
        print("the build failed")
        return 1

    exe = os.path.join(HERE, "dist", NAME + ".exe")
    if not os.path.isfile(exe):
        print("the build reported success but %s is missing" % exe)
        return 1

    size = os.path.getsize(exe) / (1024 * 1024)
    print("\nbuilt %s (%.1f MB)" % (exe, size))
    print("It needs no Python installed. Copy it anywhere and run it.")
    return 0


def main():
    if os.name != "nt":
        print("This builds a Windows executable and needs to run on Windows.")
        return 1
    if not ensure_pyinstaller():
        return 1
    for folder in ("build", "dist"):
        shutil.rmtree(os.path.join(HERE, folder), ignore_errors=True)
    return build()


if __name__ == "__main__":
    sys.exit(main())
