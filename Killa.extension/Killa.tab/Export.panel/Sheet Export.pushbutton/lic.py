# -*- coding: utf-8 -*-
"""
_kzk_lic.py  —  Kidzink Trial License Gate
============================================
Per-tool run counter stored in %APPDATA%\\Kidzink\\
Counter file: .kzk_<TOOL_ID>
Key file:     .kzk_<TOOL_ID>_key   (optional — bypasses limit permanently)

IronPython 2.7 compatible. No f-strings, no hasattr on .NET types.

Usage in script.py:
    SCRIPT_DIR = __commandpath__
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    import _kzk_lic
    _kzk_lic.check("SheetExport", limit=10)
    # ^ exits script immediately if trial expired; otherwise increments count

Admin helpers (run from any standard Python — not required in Revit):
    import _kzk_lic
    _kzk_lic.status("SheetExport")       # print current count
    _kzk_lic.reset("SheetExport")        # reset to 0  (delete counter file)
    _kzk_lic.set_count("SheetExport", 7) # force a specific count
    _kzk_lic.issue_key("SheetExport")    # write a key file -> bypasses limit
    _kzk_lic.revoke_key("SheetExport")   # remove key file -> limit re-applies
"""

import os
import sys
import hashlib

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------
_XOR_KEY   = 0x4B          # single-byte XOR mask — not cryptographic,
                            # just makes the file unreadable as plain text
_APPDATA   = os.environ.get("APPDATA", os.path.expanduser("~"))
_STORE_DIR = os.path.join(_APPDATA, "Kidzink")

# Salt mixed into the key hash — change this string before shipping to make
# keys non-transferable between your different clients.
_KEY_SALT  = "KidzinkKoda2026"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_dir():
    try:
        if not os.path.isdir(_STORE_DIR):
            os.makedirs(_STORE_DIR)
    except Exception:
        pass


def _counter_path(tool_id):
    return os.path.join(_STORE_DIR, ".kzk_" + tool_id)


def _key_path(tool_id):
    return os.path.join(_STORE_DIR, ".kzk_" + tool_id + "_key")


def _xor(data):
    """XOR-obfuscate/de-obfuscate a bytes object."""
    return bytes([b ^ _XOR_KEY for b in bytearray(data)])


def _read_count(tool_id):
    """Return current run count, or 0 if file missing/corrupt."""
    path = _counter_path(tool_id)
    try:
        with open(path, "rb") as f:
            raw = f.read()
        return int(_xor(raw).decode("ascii").strip())
    except Exception:
        return 0


def _write_count(tool_id, n):
    """Write run count to the counter file."""
    _ensure_dir()
    path = _counter_path(tool_id)
    try:
        data = str(n).encode("ascii")
        with open(path, "wb") as f:
            f.write(_xor(data))
    except Exception:
        pass


def _expected_key_hash(tool_id):
    """Return the SHA-256 hex digest that a valid key file must contain."""
    raw = _KEY_SALT + "|" + tool_id
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _has_valid_key(tool_id):
    """Return True if a valid key file exists for this tool."""
    path = _key_path(tool_id)
    try:
        with open(path, "r") as f:
            stored = f.read().strip()
        return stored == _expected_key_hash(tool_id)
    except Exception:
        return False


def _show_expired_dialog(tool_id, limit):
    """Show the branded Kidzink trial-expired TaskDialog and exit the script."""
    try:
        from Autodesk.Revit.UI import TaskDialog, TaskDialogCommonButtons
        import ctypes
        # Bring Revit forward before showing the dialog
        try:
            hwnd = __revit__.MainWindowHandle.ToInt64()     # type: ignore
            ctypes.windll.user32.AllowSetForegroundWindow(hwnd)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

        dlg = TaskDialog("Kidzink - Trial Expired")
        dlg.MainInstruction = "Trial limit reached"
        dlg.MainContent = (
            "You have used Kidzink {tool} {limit} times.\n\n"
            "Your trial has expired. Please contact Kidzink Koda to\n"
            "obtain a full licence.\n\n"
            "www.kidzink.com"
        ).format(tool=tool_id, limit=limit)
        dlg.CommonButtons = TaskDialogCommonButtons.Close
        dlg.Show()
    except Exception:
        # Fallback if Revit UI is unavailable (e.g. unit test context)
        try:
            from pyrevit import forms
            forms.alert(
                "Trial limit of {limit} uses reached for {tool}.\n"
                "Contact www.kidzink.com for a full licence.".format(
                    tool=tool_id, limit=limit),
                title="Kidzink - Trial Expired")
        except Exception:
            pass

    # Exit the calling script unconditionally
    try:
        from pyrevit import script as _script
        _script.exit()
    except Exception:
        sys.exit(0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check(tool_id, limit=10):
    """
    Main gate — call this at the top of script.py.

    1. If a valid key file exists  → do nothing (full licence).
    2. If count >= limit           → show expiry dialog and exit.
    3. Otherwise                   → increment count and return.

    tool_id : short identifier, e.g. "SheetExport".  Must be filesystem-safe.
    limit   : number of allowed runs (default 10).
    """
    # Full-licence bypass
    if _has_valid_key(tool_id):
        return

    count = _read_count(tool_id)

    if count >= limit:
        _show_expired_dialog(tool_id, limit)
        return  # _show_expired_dialog calls sys.exit / script.exit — belt & braces

    # Increment and persist before running — counts the attempt, not the success,
    # so the user can't game it by force-closing Revit mid-export.
    _write_count(tool_id, count + 1)


# ---------------------------------------------------------------------------
# Admin helpers  (safe to call from standard Python outside Revit)
# ---------------------------------------------------------------------------

def status(tool_id):
    """Print current count for tool_id."""
    count = _read_count(tool_id)
    print("Kidzink trial [{tool}]: {count} uses recorded".format(
        tool=tool_id, count=count))


def reset(tool_id):
    """Reset counter to 0 by deleting the counter file."""
    path = _counter_path(tool_id)
    try:
        if os.path.isfile(path):
            os.remove(path)
        print("Kidzink trial [{tool}]: reset to 0".format(tool=tool_id))
    except Exception as e:
        print("Reset failed: " + str(e))


def set_count(tool_id, n):
    """Force the counter to a specific value."""
    _write_count(tool_id, n)
    print("Kidzink trial [{tool}]: count set to {n}".format(tool=tool_id, n=n))


def issue_key(tool_id):
    """
    Write a valid key file for tool_id.
    Run this on your own machine, then ship the .kzk_<tool>_key file
    alongside the extension (or drop it into the company's %APPDATA%\\Kidzink\\).
    """
    _ensure_dir()
    path = _key_path(tool_id)
    digest = _expected_key_hash(tool_id)
    try:
        with open(path, "w") as f:
            f.write(digest)
        print("Key written to: " + path)
        print("Ship this file to: %APPDATA%\\Kidzink\\" + os.path.basename(path))
    except Exception as e:
        print("issue_key failed: " + str(e))


def revoke_key(tool_id):
    """Remove the key file — trial limit re-applies on next run."""
    path = _key_path(tool_id)
    try:
        if os.path.isfile(path):
            os.remove(path)
            print("Key revoked for [{tool}]".format(tool=tool_id))
        else:
            print("No key file found for [{tool}]".format(tool=tool_id))
    except Exception as e:
        print("revoke_key failed: " + str(e))
