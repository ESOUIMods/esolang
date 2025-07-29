# -*- coding: utf-8 -*-
import argparse
import sys
import os
import inspect
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
    """
    Deletes embedded library folders from modification folders in the ESO AddOns directory.

    Special cases:
        - Delete LibGroupSocket and LibMediaProvider-1.0 if they exist at the root AddOns folder.
        - Do NOT delete LibMediaProvider-1.0 if it is inside the LibMediaProvider addon itself.
        - Do NOT delete LibGroupSocket if it is inside the LibGroupBroadcast addon itself (compatibility).
    """

    folders_to_check = [
        'Lib3D', 'LibAddonMenu-2.0', 'LibAddonMenuOrderListBox', 'LibAddonMenuSoundSlider', 'LibAlchemy',
        'LibAlchemyStation', 'LibAsync', 'LibBinaryEncode', 'LibCharacterKnowledge', 'libChat2', 'LibChatMessage',
        'LibCombat', 'LibCustomMenu', 'LibDateTime', 'LibDebugLogger', 'LibDialog', 'LibFeedback', 'LibFilters-3.0',
        'LibFoodDrinkBuff', 'LibGetText', 'LibGPS', 'LibGroupBroadcast', 'LibGroupSocket', 'LibGuildRoster',
        'LibHarvensAddonSettings', 'LibHistoire', 'LibId64', 'LibLazyCrafting', 'LibMainMenu-2.0', 'LibMapData',
        'LibMapPing', 'LibMapPins-1.0', 'LibMediaProvider-1.0', 'LibMsgWin-1.0', 'LibNotification', 'LibPhinixFunctions',
        'LibPotionBuff', 'LibPrice', 'LibPromises', 'LibQuestData', 'LibRecipe', 'LibResearch', 'LibSavedVars',
        'LibScrollableMenu', 'LibSets', 'LibShifterBox', 'LibSlashCommander', 'LibStub', 'LibTableFunctions-1.0',
        'LibTextFilter', 'LibUespQuestData', 'LibZone',
    ]

    # Folders to delete ONLY from the root folder (never from inside addons)
    root_folders_to_delete = [
        'LibGroupSocket', 'LibMediaProvider-1.0'
    ]

    # Define skip rules: key = folder_to_check, value = parent folder to skip under
    skip_rules = {
        "LibMediaProvider-1.0": "LibMediaProvider",
        "LibGroupSocket": "LibGroupBroadcast",
        "LibUespQuestData": "LibUespQuestData",
    }

    current_folder = os.getcwd()

    # --- Special case: Delete certain root-only folders if found ---
    all_items = os.listdir(current_folder)
    for root_folder in root_folders_to_delete:
        if root_folder in all_items:
            full_path = os.path.join(current_folder, root_folder)
            if os.path.isdir(full_path):
                print(f"Deleting ROOT-LEVEL folder: {full_path}")
                shutil.rmtree(full_path)

    # Initialize an empty list to hold only directories (modification folders)
    modification_folders = []

    # Loop through each item and check if it's a directory
    for item in all_items:
        full_path = os.path.join(current_folder, item)
        if os.path.isdir(full_path):
            modification_folders.append(item)

    # Process each addon folder
    for modification_folder in modification_folders:
        modification_folder_path = os.path.join(current_folder, modification_folder)

        # Recursively search for and delete specified folders within this addon
        for folder_to_check in folders_to_check:
            for root, dirs, files in os.walk(modification_folder_path):
                matching_folders = fnmatch.filter(dirs, folder_to_check)

                for matching_folder in matching_folders:
                    folder_path = os.path.join(root, matching_folder)

                    if folder_to_check in skip_rules and modification_folder == skip_rules[folder_to_check]:
                        print(f"Skipping {folder_to_check} inside {modification_folder} (skip rule)")
                        continue

                    print(f"Deleting {folder_to_check} folder under {modification_folder}: {folder_path}")
                    shutil.rmtree(folder_path)

        # Now handle any remaining subfolders and delete them if empty
        all_subitems = os.listdir(modification_folder_path)
        remaining_subfolders = []

        # Loop through each item and check if it's a directory
        for subitem in all_subitems:
            subfolder_path = os.path.join(modification_folder_path, subitem)
            if os.path.isdir(subfolder_path):
                remaining_subfolders.append(subitem)

        # Delete empty subfolders
        for remaining_subfolder in remaining_subfolders:
            subfolder_path = os.path.join(modification_folder_path, remaining_subfolder)
            if not os.listdir(subfolder_path):
                print(f"Deleting empty subfolder under {modification_folder}: {subfolder_path}")
                os.rmdir(subfolder_path)






# To run the main function
if __name__ == "__main__":
    main()
