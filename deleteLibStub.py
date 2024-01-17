# -*- coding: utf-8 -*-
import argparse
import sys
import os
import inspect
import re
import struct
import codecs
from difflib import SequenceMatcher
from ruamel.yaml.scalarstring import PreservedScalarString
import ruamel.yaml
import section_constants as section
import shutil
import fnmatch

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
        print("Usage: deleteLibStub.py function [args [args ...]]")
        print("       deleteLibStub.py --help-functions, or help")
        print("       deleteLibStub.py --list-functions, or list")
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

@mainFunction
def delete_all_modification_folders():
    current_folder = os.getcwd()  # Get the current working directory

    # List of folder names to check and delete
    folders_to_check = ['Lib3D', 'LibAddonMenu-2.0', 'LibAddonMenuOrderListBox', 'LibAddonMenuSoundSlider', 'LibAlchemy', 'LibAlchemyStation', 'LibAsync', 'LibBinaryEncode', 'LibCharacterKnowledge', 'LibChatMessage', 'LibCombat', 'LibCustomMenu', 'LibDateTime', 'LibDebugLogger', 'LibDialog', 'LibFeedback', 'LibFilters-3.0', 'LibFoodDrinkBuff', 'LibGetText', 'LibGPS', 'LibGroupSocket', 'LibGuildRoster', 'LibHistoire', 'LibLazyCrafting', 'LibMainMenu-2.0', 'LibMapData', 'LibMapPing', 'LibMapPins-1.0', 'LibMediaProvider-1.0', 'LibMsgWin-1.0', 'LibNotification', 'LibPhinixFunctions', 'LibPotionBuff', 'LibPrice', 'LibPromises', 'LibQuestData', 'LibResearch', 'LibSavedVars', 'LibScrollableMenu', 'LibSets', 'LibShifterBox', 'LibSlashCommander', 'LibStub', 'LibTableFunctions-1.0', 'LibTextFilter', 'LibZone']

    
    # Get the list of modification folders within the current working directory
    modification_folders = [folder for folder in os.listdir(current_folder) if os.path.isdir(os.path.join(current_folder, folder))]

    for modification_folder in modification_folders:
        modification_folder_path = os.path.join(current_folder, modification_folder)

        # Recursively search for and delete specified folders within the modification folder
        for folder_to_check in folders_to_check:
            for root, dirs, files in os.walk(modification_folder_path):
                matching_folders = fnmatch.filter(dirs, folder_to_check)

                for matching_folder in matching_folders:
                    folder_path = os.path.join(root, matching_folder)
                    print("Deleting {} folder under {}: {}".format(folder_to_check, modification_folder, folder_path))
                    shutil.rmtree(folder_path)

        # Check if there are any subfolders remaining in the modification folder, and delete them if empty
        remaining_subfolders = [subfolder for subfolder in os.listdir(modification_folder_path) if os.path.isdir(os.path.join(modification_folder_path, subfolder))]

        for remaining_subfolder in remaining_subfolders:
            subfolder_path = os.path.join(modification_folder_path, remaining_subfolder)
            
            if not os.listdir(subfolder_path):
                print("Deleting empty subfolder under {}: {}".format(modification_folder, subfolder_path))
                os.rmdir(subfolder_path)


# To run the main function
if __name__ == "__main__":
    main()
