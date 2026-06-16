# -*- coding: utf-8 -*-
import argparse
import sys
import os
import inspect
import re
import struct
import codecs
import xml.etree.ElementTree as ET
from icu import Locale, BreakIterator
import datetime
import time

# List to hold information about callable functions
callable_functions = []


def mainFunction(func):
    """Decorator to mark functions as callable and add them to the list."""
    callable_functions.append(func)
    return func


def print_help():
    print("Available callable functions:")
    for func in callable_functions:
        print("- {}: {}".format(func.__name__, func.__doc__))


def print_docstrings():
    print("Docstrings for callable functions:")
    for func in callable_functions:
        print("\nFunction: {}".format(func.__name__))
        docstring = inspect.getdoc(func)
        if docstring:
            encoded_docstring = docstring.encode("utf-8", errors="ignore").decode(sys.stdout.encoding, errors="ignore")
            print(encoded_docstring)
        else:
            print("No docstring available.")


def main():
    parser = argparse.ArgumentParser(description="Patch ESO addon font references for EsoKR.")
    parser.add_argument("--help-functions", action="store_true", help="Print available functions and their docstrings.")
    parser.add_argument("--list-functions", action="store_true", help="List available functions without docstrings.")
    parser.add_argument("--usage", action="store_true", help="Display usage information.")
    parser.add_argument("function", nargs="?", help="The name of the function to execute.")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments for the function.")

    args = parser.parse_args()

    if args.usage:
        print("Usage: esoKRFontPatcher.py function [args [args ...]]")
        print("       esoKRFontPatcher.py --help-functions, or help")
        print("       esoKRFontPatcher.py --list-functions, or list")
    elif args.help_functions or args.function == "help":
        print_docstrings()
    elif args.list_functions or args.function == "list":
        print("Available functions:")
        for func in callable_functions:
            print(func.__name__)
    elif args.function:
        function_name = args.function
        for func in callable_functions:
            if func.__name__ == function_name:
                func(*args.args)
                break
        else:
            print("Unknown function: {}".format(function_name))
    else:
        # No command provided -> run normal patch mode
        patch_addon_fonts()


# Font replacement configuration ---------------------------------------------
# These are based on the old addon_KRpatch cmd/fart replacements.
# Use .slug by default for console/Bethesda.net style packaging.
FONT_REPLACEMENTS = {
    "EsoUI/Common/Fonts/univers55.otf": "EsoKR/fonts/univers57.slug",
    "EsoUI/Common/Fonts/univers57.otf": "EsoKR/fonts/univers57.slug",
    "EsoUI/Common/Fonts/univers67.otf": "EsoKR/fonts/univers67.slug",
    "EsoUI/Common/Fonts/Univers57.otf": "EsoKR/fonts/univers57.slug",
    "EsoUI/Common/Fonts/Univers67.otf": "EsoKR/fonts/univers67.slug",
    "EsoUI/Common/Fonts/FTN47.otf": "EsoKR/fonts/ftn47.slug",
    "EsoUI/Common/Fonts/FTN57.otf": "EsoKR/fonts/ftn57.slug",
    "EsoUI/Common/Fonts/FTN87.otf": "EsoKR/fonts/ftn87.slug",
    "EsoUI/Common/Fonts/trajanpro-regular.otf": "EsoKR/fonts/trajanpro-regular.slug",
    "EsoUI/Common/Fonts/Handwritten_Bold.otf": "EsoKR/fonts/handwritten_bold.slug",
    "EsoUI/Common/Fonts/ProseAntiquePSMT.otf": "EsoKR/fonts/proseantiquepsmt.slug",

    "$(MEDIUM_FONT)": "EsoKR/fonts/univers57.slug",
    "$(BOLD_FONT)": "EsoKR/fonts/univers67.slug",
    "$(CHAT_FONT)": "EsoKR/fonts/univers67.slug",
}

TEXT_EXTENSIONS = {
    ".lua", ".xml", ".txt", ".addon",
}
SKIP_FOLDERS = {
    ".idea", ".git", ".svn", "__pycache__",
}

LOG_FILE = "esoKR_font_patcher_log.txt"


# Helpers --------------------------------------------------------------------
def redact_username_from_path(message):
    return re.sub(
        r"(C:\\{1,2}Users\\{1,2})[^\\]+",
        r"\1<user name>",
        message,
        flags=re.IGNORECASE,
    )


def ensure_running_in_addons_root(current_folder, log_lines):
    here = os.path.abspath(current_folder)
    base = os.path.basename(here).lower()
    parent = os.path.basename(os.path.dirname(here)).lower()

    if base == "addons" and parent in ("live", "pts"):
        return True

    log_lines.append(
        "Safety check failed: This utility must be run from the ESO AddOns root "
        "(...\\live\\AddOns or ...\\pts\\AddOns). "
        f"Current folder: {here}. Move the EXE into the AddOns folder and run it there."
    )
    return False


def preflight_filesystem_probe(current_folder, log_lines):
    if not os.access(current_folder, os.W_OK | os.X_OK):
        log_lines.append(
            f"Preflight failed: No write/execute permission in AddOns folder: {redact_username_from_path(current_folder)}. "
            "Close ESO/Minion, pause OneDrive if enabled, or run as Administrator."
        )
        return False

    probe_dir = os.path.join(
        current_folder,
        f"esoKR_font_patcher_temp_{os.getpid()}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    )
    probe_file = os.path.join(probe_dir, "probe.txt")

    try:
        os.makedirs(probe_dir, exist_ok=False)
        with open(probe_file, "w", encoding="utf-8", newline="\n") as f:
            f.write("probe\n")
        os.remove(probe_file)
        os.rmdir(probe_dir)
        return True
    except Exception as e:
        log_lines.append(f"Preflight failed: {redact_username_from_path(str(e))}")
        return False


def read_text_file(path):
    with open(path, "r", encoding="utf-8-sig", errors="ignore", newline="") as f:
        return f.read()


def write_text_file(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def is_patchable_text_file(path):
    return os.path.splitext(path)[1].lower() in TEXT_EXTENSIONS


def walk_patchable_files(root_folder):
    for dirpath, dirnames, filenames in os.walk(root_folder):
        dirnames[:] = [d for d in dirnames if d not in SKIP_FOLDERS]

        for filename in filenames:
            path = os.path.join(dirpath, filename)
            if is_patchable_text_file(path):
                yield path


def replace_font_references(text):
    changed = False
    replacements_made = []

    for old, new in FONT_REPLACEMENTS.items():
        if old in text:
            text = text.replace(old, new)
            changed = True
            replacements_made.append((old, new))

    return text, changed, replacements_made


def write_log(log_lines):
    with open(LOG_FILE, "w", encoding="utf-8", newline="\n") as out:
        out.write("EsoKR Font Patcher\n")
        out.write("Run: {}\n\n".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        for line in log_lines:
            out.write(redact_username_from_path(line) + "\n")


# Main routines ---------------------------------------------------------------
@mainFunction
def list_font_references():
    """
    Scan patchable addon files and list files containing known ESO font references.
    Does not modify files.
    Must be run from the ESO AddOns root folder.
    """
    current_folder = os.getcwd()
    log_lines = []

    if not ensure_running_in_addons_root(current_folder, log_lines):
        write_log(log_lines)
        print(f"Safety check failed. See {LOG_FILE}")
        return

    match_count = 0

    for path in walk_patchable_files(current_folder):
        try:
            text = read_text_file(path)
        except Exception as e:
            log_lines.append(f"Read error: {path}: {e}")
            continue

        found = [old for old in FONT_REPLACEMENTS if old in text]

        if found:
            match_count += 1
            log_lines.append(f"Found font references in: {path}")

            for old in found:
                log_lines.append(f"  {old} -> {FONT_REPLACEMENTS[old]}")

    if match_count == 0:
        log_lines.append("No known font references found.")

    write_log(log_lines)
    print(f"Done. Files with font references: {match_count}. See {LOG_FILE}")


@mainFunction
def patch_addon_fonts():
    """
    Patch known ESO font references in Lua/XML/manifest text files to EsoKR font paths.
    Must be run from the ESO AddOns root folder.
    """
    current_folder = os.getcwd()
    log_lines = []

    if not ensure_running_in_addons_root(current_folder, log_lines):
        write_log(log_lines)
        print(f"Safety check failed. See {LOG_FILE}")
        return

    if not preflight_filesystem_probe(current_folder, log_lines):
        write_log(log_lines)
        print(f"Preflight failed. See {LOG_FILE}")
        return

    files_modified = 0
    replacements_total = 0

    for path in walk_patchable_files(current_folder):
        try:
            original = read_text_file(path)
        except Exception as e:
            log_lines.append(f"Read error: {path}: {e}")
            continue

        updated, changed, replacements = replace_font_references(original)
        if not changed:
            continue

        try:
            write_text_file(path, updated)
        except PermissionError:
            try:
                os.chmod(path, stat.S_IWRITE)
                write_text_file(path, updated)
            except Exception as e:
                log_lines.append(f"Write error: {path}: {e}")
                continue
        except Exception as e:
            log_lines.append(f"Write error: {path}: {e}")
            continue

        files_modified += 1
        replacements_total += len(replacements)
        log_lines.append(f"Patched: {path}")

        for old, new in replacements:
            log_lines.append(f"  {old} -> {new}")

    if files_modified == 0:
        log_lines.append("No files were modified.")

    write_log(log_lines)
    print(f"Done. Files modified: {files_modified}. Replacement types hit: {replacements_total}. See {LOG_FILE}")


@mainFunction
def dry_run_patch_addon_fonts():
    """
    Show what would be patched without modifying files.
    Must be run from the ESO AddOns root folder.
    """
    current_folder = os.getcwd()
    log_lines = []

    if not ensure_running_in_addons_root(current_folder, log_lines):
        write_log(log_lines)
        print(f"Safety check failed. See {LOG_FILE}")
        return

    files_would_modify = 0
    replacements_total = 0

    for path in walk_patchable_files(current_folder):
        try:
            text = read_text_file(path)
        except Exception as e:
            log_lines.append(f"Read error: {path}: {e}")
            continue

        _, changed, replacements = replace_font_references(text)

        if changed:
            files_would_modify += 1
            replacements_total += len(replacements)
            log_lines.append(f"Would patch: {path}")

            for old, new in replacements:
                log_lines.append(f"  {old} -> {new}")

    if files_would_modify == 0:
        log_lines.append("No known font references would be patched.")

    write_log(log_lines)
    print(f"Done. Files that would be modified: {files_would_modify}. Replacement types hit: {replacements_total}. See {LOG_FILE}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--help-docstrings":
        print_docstrings()
    else:
        main()
