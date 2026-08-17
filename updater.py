"""Self-updater.

Checks the GitHub repo for a newer version, downloads it, and swaps the
files in place. Uses nothing but the standard library so it works on a bare
Python install, and it never needs a GitHub token because the repo is public.

It can be run on its own:

    python updater.py            # check and, if there is one, install
    python updater.py --check    # only report what is available

or from inside the game with control+u.
"""

import io
import json
import os
import re
import shutil
import ssl
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

from version import GITHUB_OWNER, GITHUB_REPO, __version__

USER_AGENT = "helm-chess-updater/%s" % __version__
TIMEOUT = 20

API_LATEST = "https://api.github.com/repos/%s/%s/releases/latest"
RAW_VERSION = "https://raw.githubusercontent.com/%s/%s/main/version.py"
BRANCH_ZIP = "https://github.com/%s/%s/archive/refs/heads/main.zip"

# Files the updater is allowed to replace. Anything else in the folder --
# saved games, a Stockfish binary you dropped in, notes -- is left alone.
UPDATABLE_SUFFIXES = (".py", ".md", ".txt")


class UpdateError(Exception):
    pass


def parse_version(text):
    """"1.2.3" or "v1.2.3" into a tuple that sorts correctly."""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    if not match:
        raise UpdateError("could not read a version number from %r" % text)
    return tuple(int(part) for part in match.groups())


def _open(url):
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    try:
        return urllib.request.urlopen(request, timeout=TIMEOUT)
    except urllib.error.HTTPError as exc:
        raise UpdateError("GitHub returned %s for %s" % (exc.code, url))
    except urllib.error.URLError as exc:
        raise UpdateError("could not reach GitHub: %s" % exc.reason)
    except ssl.SSLError as exc:
        raise UpdateError("secure connection failed: %s" % exc)


def check_for_update():
    """Return (latest_version_string, download_url, notes) or None if current.

    Prefers a published release; falls back to reading version.py off the
    main branch so the check still works between releases.
    """
    current = parse_version(__version__)

    try:
        with _open(API_LATEST % (GITHUB_OWNER, GITHUB_REPO)) as response:
            release = json.load(response)
        latest_text = release.get("tag_name") or release.get("name") or ""
        latest = parse_version(latest_text)
        url = release.get("zipball_url") or BRANCH_ZIP % (GITHUB_OWNER, GITHUB_REPO)
        notes = (release.get("body") or "").strip()
        if latest > current:
            return latest_text.lstrip("v"), url, notes
        return None
    except UpdateError:
        pass  # No releases yet, or the API is unhappy. Try the branch.

    with _open(RAW_VERSION % (GITHUB_OWNER, GITHUB_REPO)) as response:
        text = response.read().decode("utf-8", "replace")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
    if not match:
        raise UpdateError("version.py on GitHub is not in the expected format")
    latest_text = match.group(1)
    if parse_version(latest_text) > current:
        return latest_text, BRANCH_ZIP % (GITHUB_OWNER, GITHUB_REPO), ""
    return None


def download_and_install(url, install_dir=None, backup=True):
    """Fetch the zip and copy the updated files over the installation.

    Returns the list of file names that changed. Raises UpdateError if the
    download looks wrong, and restores the backup if the copy fails halfway.
    """
    install_dir = install_dir or os.path.dirname(os.path.abspath(__file__))

    with _open(url) as response:
        payload = response.read()
    if len(payload) < 1024:
        raise UpdateError("the download was suspiciously small (%d bytes)" % len(payload))

    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile:
        raise UpdateError("the download was not a valid zip file")

    staging = tempfile.mkdtemp(prefix="helm-chess-update-")
    backup_dir = None
    try:
        archive.extractall(staging)

        # GitHub wraps everything in a single top-level folder.
        entries = [os.path.join(staging, name) for name in os.listdir(staging)]
        roots = [path for path in entries if os.path.isdir(path)]
        source = roots[0] if len(roots) == 1 else staging

        incoming = [
            name for name in os.listdir(source)
            if name.lower().endswith(UPDATABLE_SUFFIXES)
            and os.path.isfile(os.path.join(source, name))
        ]
        if not any(name == "version.py" for name in incoming):
            raise UpdateError("the download does not look like Helm Chess")

        if backup:
            backup_dir = os.path.join(install_dir, ".update-backup")
            shutil.rmtree(backup_dir, ignore_errors=True)
            os.makedirs(backup_dir, exist_ok=True)
            for name in incoming:
                existing = os.path.join(install_dir, name)
                if os.path.isfile(existing):
                    shutil.copy2(existing, os.path.join(backup_dir, name))

        changed = []
        try:
            for name in incoming:
                shutil.copy2(os.path.join(source, name), os.path.join(install_dir, name))
                changed.append(name)
        except Exception as exc:
            if backup_dir:
                for name in os.listdir(backup_dir):
                    shutil.copy2(os.path.join(backup_dir, name),
                                 os.path.join(install_dir, name))
            raise UpdateError("copy failed and the old version was restored: %s" % exc)

        return sorted(changed)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def update(check_only=False):
    """Convenience wrapper used by the command line and by the game."""
    result = check_for_update()
    if result is None:
        return "Helm Chess %s is up to date." % __version__
    latest, url, notes = result
    if check_only:
        message = "Version %s is available (you have %s)." % (latest, __version__)
        return message + ("\n\n" + notes if notes else "")
    changed = download_and_install(url)
    return ("Updated to version %s. %d files replaced. "
            "Restart Helm Chess to use it." % (latest, len(changed)))


if __name__ == "__main__":
    try:
        print(update(check_only="--check" in sys.argv))
    except UpdateError as exc:
        print("Update failed: %s" % exc)
        sys.exit(1)
