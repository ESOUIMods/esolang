# -*- coding: utf-8 -*-
import argparse
import sys
import os
import inspect
import icu

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
            encoded_docstring = docstring.encode('utf-8', errors='ignore').decode(sys.stdout.encoding)
            print(encoded_docstring)
        else:
            print("No docstring available.")


def main():
    parser = argparse.ArgumentParser(description="A script to perform various operations on text files.")
    parser.add_argument("--help-functions", action="store_true", help="Print available functions and their docstrings.")
    parser.add_argument("--list-functions", action="store_true", help="List available functions without docstrings.")
    parser.add_argument("--usage", action="store_true", help="Display usage information.")
    parser.add_argument("function", nargs="?", help="The name of the function to execute.")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments for the function.")

    args = parser.parse_args()

    if args.usage:
        print("Usage: esoutils.py function [args [args ...]]")
        print("       esoutils.py --help-functions, or help")
        print("       esoutils.py --list-functions, or list")
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
                func_args = args.args
                func(*func_args)
                break
        else:
            print("Unknown function: {}".format(function_name))
    else:
        print("No command provided.")


def detect_and_fix_utf8_bom(file_path):
    """
    Check if a file has a UTF-8 BOM and remove it if present.
    Ensures the file is saved in proper UTF-8 without BOM and normalized.
    Only reports when a BOM is fixed.
    """
    try:
        # Read full content as bytes
        with open(file_path, 'rb') as f:
            content_bytes = f.read()

        # Check for BOM
        if content_bytes.startswith(b'\xef\xbb\xbf'):
            # Decode, normalize, and rewrite
            text = content_bytes.decode('utf-8-sig')
            normalizer = icu.Normalizer2.getNFCInstance()
            text = normalizer.normalize(text)

            with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)

            print(f"Fixing BOM in {file_path}")  # Only log when BOM was fixed

        # If no BOM, skip silently
        # (No logs for files without BOM to reduce noise)

    except Exception as e:
        print(f"Error processing {file_path}: {e}")


@mainFunction
def add_license_header(root_path, header_file):
    """
    Add a specified license header to all .lua files in a directory (recursively).

    Args:
        root_path (str): The root folder to walk through and update .lua files.
        header_file (str): Path to a text file containing the license header.
    """
    if not os.path.isdir(root_path):
        print(f"Error: {root_path} is not a valid directory.")
        return

    if not os.path.isfile(header_file):
        print(f"Error: {header_file} does not exist.")
        return

    # Read the license header content
    with open(header_file, 'r', encoding='utf-8') as f:
        license_header = f.read().strip() + "\n\n"

    updated_files = []

    for dirpath, _, filenames in os.walk(root_path):
        for filename in filenames:
            if filename.endswith(".lua"):
                file_path = os.path.join(dirpath, filename)

                # Fix BOM before reading
                detect_and_fix_utf8_bom(file_path)

                # Read the current content
                with open(file_path, 'r', encoding='utf-8') as lua_file:
                    content = lua_file.read()

                # Add header only if not already present
                if license_header.strip() not in content:
                    normalizer = icu.Normalizer2.getNFCInstance()
                    updated_content = license_header + content
                    updated_content = normalizer.normalize(updated_content)

                    with open(file_path, 'w', encoding='utf-8', newline='\n') as lua_file:
                        lua_file.write(updated_content)

                    updated_files.append(file_path)

    if updated_files:
        print(f"Updated {len(updated_files)} files with license header.")
    else:
        print("No files were updated (header may already be present).")


# To run the main function
if __name__ == "__main__":
    main()
