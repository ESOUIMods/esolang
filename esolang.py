# -*- coding: utf-8 -*-
import argparse
import sys
import os
import inspect
import re
import struct
import codecs
import chardet
from difflib import SequenceMatcher
import ruamel.yaml
from ruamel.yaml.scalarstring import PreservedScalarString
from ruamel.yaml.scalarstring import DoubleQuotedScalarString
import section_constants as section
import polib

"""
From powershell 6.1.7600.16385 you may see question marks rather then the Korean or Chinese text on windows 7.
However, running esolang with powershell 7 on windows 10 the docstrings should print correctly.
On windows 7 in GitBash 2.35.1.2 you may see a UnicodeEncodeError charmap error.

The issue is related to the encoding used when printing Unicode characters in different terminal environments.
"""
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
        print("Usage: esokr.py function [args [args ...]]")
        print("       esokr.py --help-functions, or help")
        print("       esokr.py --list-functions, or list")
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
                if func == addIndexToLangFile and len(func_args) < 2:
                    print("Usage: {} <txtFilename> <idFilename>".format(func.__name__))
                else:
                    func(*func_args)
                break
        else:
            print("Unknown function: {}".format(function_name))
    else:
        print("No command provided.")


# Regular Expressions for Text Processing -------------------------------------
"""
Here's a breakdown of how the reClientUntaged expression works:
^: Anchors the start of the string.
\[(.+?)\]: Matches a string enclosed in square brackets and captures the content
 inside the brackets as group 1 (.*?). The (.+?) is a non-greedy match for any
 characters within the brackets.
= ": Matches the space, equals sign, and double quotation mark that follow the square brackets.
(?!.*{[CP]:): A negative lookahead assertion that checks that the text ahead does
 not contain either {C: or {P:. This ensures that the text within the double
 quotation marks is not tagged as a language constant.
(.*?): Captures the text between the double quotation marks as group 2 (.*?).
": Matches the closing double quotation mark.
$: Anchors the end of the string.
"""

# Matches a language index in the format {{identifier:}}text
reLangIndex = re.compile(r'^\{\{([^:]+):}}(.+?)$')

# Matches an old-style language index in the format identifier text
reLangIndexOld = re.compile(r'^(\d{1,10}-\d{1,7}-\d{1,7}) (.+)$')

# Matches untagged client strings or empty lines in the format [key] = "value" or [key] = ""
reClientUntaged = re.compile(r'^\[(.+?)\] = "(?!.*\{[CP]:)((?:[^"\\]|\\.)*)"$')

# Matches tagged client strings in the format [key] = "{tag:value}text"
reClientTaged = re.compile(r'^\[(.+?)\] = "(\{[CP]:.+?\})((?:[^"\\]|\\.)*)"$')

# Matches empty client strings in the format [key] = ""
reEmptyString = re.compile(r'^\[(.+?)\] = ""$')

# Matches a font tag in the format [Font:font_name]
reFontTag = re.compile(r'^\[Font:(.+?)\] = "(.+?)"')

# Matches a gender or neutral suffix in the format ^M, ^F, ^m, ^f, ^N, or ^n
reGenderSuffix = re.compile(r'\^[MmFfNn]')

# Global Dictionaries ---------------------------------------------------------
textUntranslatedLiveDict = {}
textUntranslatedPTSDict = {}
textTranslatedDict = {}
textUntranslatedDict = {}
textClientDict = {}
textPregameDict = {}

# Global Dictionaries Use for reading en.lang, en_pts.lang, kr.lang -----------
currentFileIndexes = {}
currentFileStrings = {}
previousFileIndexes = {}
previousFileStrings = {}
translatedFileIndexes = {}
translatedFileStrings = {}


# Helper for escaped chars ----------------------------------------------------
def get_section_id(section_key):
    return section.section_info.get(section_key, {}).get('sectionId', None)


def get_section_name(section_key):
    return section.section_info.get(section_key, {}).get('sectionName', None)


def get_section_key_by_id(section_id):
    for key, value in section.section_info.items():
        if value['sectionId'] == section_id:
            return key
    return None


def escape_lua_string(text):
    return text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace(r'\\\"', r'\"')


def preserve_and_restore_escaped_sequences(text):
    """
    Preserve escaped sequences using placeholders, then restore them after transformations.

    Args:
        text (str): Input string possibly containing escaped sequences.

    Returns:
        str: Transformed string with escaped sequences preserved and restored.
    """
    # Preserve sequences
    text = text.replace('\\\\', '-=DS=-')  # Escaped backslashes
    text = text.replace('\\n', '-=CR=-')  # Escaped newlines
    text = re.sub(r'\s+\\$', '-=ELS=-', text)  # Trailing backslash with optional whitespace
    text = text.replace('\\"', '-=DQ=-')  # Escaped double quotes
    text = text.replace('\\', '')  # Remove any remaining lone backslashes

    # Restore sequences
    text = text.replace('-=DS=-', '\\\\')
    text = text.replace('-=CR=-', '\\n')
    text = text.replace('-=ELS=-', '')  # End-of-line backslash removal
    text = text.replace('-=DQ=-', '\\"')

    return text


def preserve_escaped_sequences(text):
    """
    Convert Lua-style escape sequences to temporary placeholders to prevent interference during formatting.
    """
    return (
        text
            .replace("\\n", "-=CR=-")
            .replace('\\"', "-=EQ=-")
            .replace("\\\\", "-=DS=-")
    )


def preserve_escaped_sequences_bytes(raw_bytes):
    """
    Replaces common escape sequences in a bytes object with placeholders before decoding.

    Args:
        raw_bytes (bytes): e.g., b"Line1\\nLine2"

    Returns:
        str: A string with preserved escape sequences (e.g., "Line1-=CR=-Line2")
    """
    raw_bytes = (
        raw_bytes
            .replace(b"\n", b"-=CR=-")
    )
    return raw_bytes


def restore_escaped_sequences(text):
    """
    Restore temporary placeholders back to Lua-style escape sequences.
    """
    return (
        text
            .replace("-=CR=-", "\\n")
            .replace("-=EQ=-", '\\"')
            .replace("-=DS=-", "\\\\")
    )


def isTranslatedText(line):
    if line is None:
        return False
    return any(ord(char) > 127 for char in line)


# Read and write binary structs
def readUInt32(file): return struct.unpack('>I', file.read(4))[0]


def writeUInt32(file, value): file.write(struct.pack('>I', value))


# Conversion ------------------------------------------------------------------
@mainFunction
def addIndexToLangFile(txtFilename, idFilename):
    """
    Add numeric identifiers as tags to language entries in a target file.

    This function reads a source text file containing language data and a corresponding identifier file
    containing unique numeric identifiers for each language entry. It then appends these identifiers as tags
    to the respective lines in the target language file. The resulting output is saved in a new file named 'output.txt'.

    Args:
        txtFilename (str): The filename of the source text file containing language data (e.g., 'en.lang.txt').
        idFilename (str): The filename of the identifier file containing unique numeric identifiers
                          (e.g., 'en.lang.id.txt').

    Notes:
        The source text file should contain text data, one entry per line, while the identifier file should
        contain numeric identifiers corresponding to each entry in the same order.

        The function reads both files, associates numeric identifiers with their respective entries, and appends
        these identifiers as tags in the output file. The output file is saved in the same directory as the script.

    Example:
        Given a source text file 'en.lang.txt':
        ```
        Hello, world!
        How are you?
        ```

        And an identifier file 'en.lang.id.txt':
        ```
        18173141-0-2944
        7949764-0-51729
        ```

        Calling `addIndexToLangFile('en.lang.txt', 'en.lang.id.txt')` will produce an output file 'output.txt':
        ```
        {{18173141-0-2944:}}Hello, world!
        {{7949764-0-51729:}}How are you?
        ```

    """
    textLines = []
    idLines = []

    # Read text file and count lines
    textLineCount = 0
    with open(txtFilename, 'r', encoding="utf8") as textIns:
        for line in textIns:
            newstr = line.rstrip()
            textLines.append(newstr)
            textLineCount += 1

    # Read identifier file and count lines
    idLineCount = 0
    with open(idFilename, 'r', encoding="utf8") as idIns:
        for line in idIns:
            newstr = line.strip()
            idLines.append(newstr)
            idLineCount += 1

    if textLineCount != idLineCount:
        print("Error: Number of lines in text and identifier files do not match. Aborting.")
        return

    with open('output.txt', 'w', encoding="utf8") as output:
        for i in range(len(textLines)):
            lineOut = '{{{{{}:}}}}'.format(idLines[i]) + textLines[i] + '\n'
            output.write(lineOut)


@mainFunction
def removeIndexToLangFile(txtFilename):
    """
    Remove numeric identifiers from language entries in a target file.

    This function reads a target text file containing language entries with numeric identifiers as tags
    and removes these identifiers, resulting in a clean language text file. The output is saved in a new file named 'output.txt'.

    Args:
        txtFilename (str): The filename of the target text file containing language entries with identifiers (e.g., 'en.lang.txt').

    Notes:
        The function uses regular expressions to detect and remove numeric identifiers that are enclosed in double curly braces.
        It then writes the cleaned entries to the output file 'output.txt' in the same directory as the script.

    Example:
        Given a target text file 'en.lang.txt':
        ```
        {{18173141-0-2944:}}Hello, world!
        {{7949764-0-51729:}}How are you?
        ```

        Calling `removeIndexToLangFile('en.lang.txt')` will produce an output file 'output.txt':
        ```
        Hello, world!
        How are you?
        ```

    """

    # Get ID numbers ------------------------------------------------------
    textLines = []

    with open(txtFilename, 'r', encoding="utf8") as textIns:
        for line in textIns:
            matchIndex = reLangIndex.match(line)
            matchIndexOld = reLangIndexOld.match(line)
            if matchIndex:
                text = matchIndex.group(2)
                textLines.append(text)
            if matchIndexOld:
                text = matchIndexOld.group(2)
                newString = text.lstrip()
                textLines.append(newString)

    with open("output.txt", 'w', encoding="utf8") as out:
        for line in textLines:
            lineOut = '{}\n'.format(line)
            out.write(lineOut)


@mainFunction
def koreanToEso(txtFilename):
    """
    Convert Korean UTF-8 encoded text to Chinese UTF-8 encoded text with byte offset.

    This function reads a source text file containing Korean UTF-8 encoded text and applies a byte offset to convert it to
    Chinese UTF-8 encoded text. The byte offset is used to shift the Korean text to a range that is normally occupied by
    Chinese characters. This technique is used in Elder Scrolls Online (ESO) to display Korean text using a nonstandard font
    that resides in the Chinese character range. The converted text is saved in a new file named 'output.txt'.

    Args:
        txtFilename (str): The filename of the source text file containing Korean UTF-8 encoded text.

    Notes:
        - The function reads the source file in binary mode and applies a byte-level analysis to determine the proper conversion.
        - A byte offset is added to the Unicode code points of the Korean characters to position them within the Chinese character range.
        - The resulting Chinese UTF-8 encoded text is written to the 'output.txt' file in UTF-8 encoding.

    Example:
        Given a source text file 'korean.txt' with Korean UTF-8 encoded text:
        ```
        나는 가고 싶다
        ```

        Calling `koreanToEso('korean.txt')` will produce an output file 'output.txt':
        ```
        犘璔 渀滠 蓶瓤
        ```

    """
    not_eof = True
    with open(txtFilename, 'rb') as textIns:
        with open("output.txt", 'w', encoding="utf8") as out:
            while not_eof:
                shift = 1
                char = textIns.read(shift)
                value = int.from_bytes(char, "big")
                next_char = None
                if value > 0x00 and value <= 0x74:
                    shift = 1
                elif value >= 0xc0 and value <= 0xdf:
                    shift = 2
                elif value >= 0xe0 and value <= 0xef:
                    shift = 3
                elif value >= 0xf0 and value <= 0xf7:
                    shift = 4
                if shift > 1:
                    next_char = textIns.read(shift - 1)
                if next_char:
                    char = b''.join([char, next_char])
                if not char:
                    # eof
                    break
                temp = int.from_bytes(char, "big")
                if temp >= 0xE18480 and temp <= 0xE187BF:
                    temp = temp + 0x43400
                elif temp > 0xE384B0 and temp <= 0xE384BF:
                    temp = temp + 0x237D0
                elif temp > 0xE38580 and temp <= 0xE3868F:
                    temp = temp + 0x23710
                elif temp >= 0xEAB080 and temp <= 0xED9EAC:
                    if temp >= 0xEAB880 and temp <= 0xEABFBF:
                        temp = temp - 0x33800
                    elif temp >= 0xEBB880 and temp <= 0xEBBFBF:
                        temp = temp - 0x33800
                    elif temp >= 0xECB880 and temp <= 0xECBFBF:
                        temp = temp - 0x33800
                    else:
                        temp = temp - 0x3F800
                char = temp.to_bytes(shift, byteorder='big')
                outText = codecs.decode(char, 'UTF-8')
                out.write(outText)


@mainFunction
def esoToKorean(txtFilename):
    """
    Convert Chinese UTF-8 encoded text to traditional Korean UTF-8 encoded text with byte offset reversal.

    This function reads a source text file containing Chinese UTF-8 encoded text and applies an opposite byte offset to
    convert it to traditional Korean UTF-8 encoded text. The byte offset reversal is used to shift the Chinese text back
    to its original traditional Korean character range. This technique is used when working with Chinese text that has
    been encoded using a byte offset to simulate Korean characters. The converted text is saved in a new file named 'output.txt'.

    Args:
        txtFilename (str): The filename of the source text file containing Chinese UTF-8 encoded text (e.g., 'kr.lang.txt').

    Notes:
        - The function reads the source file in binary mode and applies a byte-level analysis to determine the proper conversion.
        - An opposite byte offset is subtracted from the Unicode code points of the Chinese characters to convert them back to
          their original traditional Korean characters.
        - The resulting traditional Korean UTF-8 encoded text is written to the 'output.txt' file in UTF-8 encoding.

    Example:
        Given a source text file 'kr.lang.txt' with Chinese UTF-8 encoded text:
        ```
        犘璔 渀滠 蓶瓤
        ```

        Calling `esoToKorean('kr.lang.txt')` will produce an output file 'output.txt':
        ```
        나는 가고 싶다
        ```

    """
    not_eof = True
    with open(txtFilename, 'rb') as textIns:
        with open("output.txt", 'w', encoding="utf8") as out:
            while not_eof:
                shift = 1
                char = textIns.read(shift)
                value = int.from_bytes(char, "big")
                next_char = None
                if value > 0x00 and value <= 0x74:
                    shift = 1
                elif value >= 0xc0 and value <= 0xdf:
                    shift = 2
                elif value >= 0xe0 and value <= 0xef:
                    shift = 3
                elif value >= 0xf0 and value <= 0xf7:
                    shift = 4
                if shift > 1:
                    next_char = textIns.read(shift - 1)
                if next_char:
                    char = b''.join([char, next_char])
                if not char:
                    # eof
                    break
                temp = int.from_bytes(char, "big")
                if temp >= 0xE5B880 and temp <= 0xE5BBBF:
                    temp = temp - 0x43400
                elif temp > 0xE5BC80 and temp <= 0xE5BC8F:
                    temp = temp - 0x237D0
                elif temp > 0xE5BC90 and temp <= 0xE5BD9F:
                    temp = temp - 0x23710
                elif temp >= 0xE6B880 and temp <= 0xE9A6AC:
                    if temp >= 0xE78080 and temp <= 0xE787BF:
                        temp = temp + 0x33800
                    elif temp >= 0xE88080 and temp <= 0xE887BF:
                        temp = temp + 0x33800
                    elif temp >= 0xE98080 and temp <= 0xE987BF:
                        temp = temp + 0x33800
                    else:
                        temp = temp + 0x3F800
                char = temp.to_bytes(shift, byteorder='big')
                outText = codecs.decode(char, 'UTF-8')
                out.write(outText)


@mainFunction
def addIndexToEosui(txtFilename):
    """
    Add numeric tags to language entries in kr_client.str or kr_pregame.str for use with translation files.

    This function reads a target text file containing language entries in the format of [key] = "value" pairs,
    such as 'kr_client.str' or 'kr_pregame.str'. It then adds numeric tags to the entries and generates new entries
    with the format [key] = "{C:numeric_tag}value" or [key] = "{P:numeric_tag}value", based on whether the entries
    are intended for the client or pregame context.

    Args:
        txtFilename (str): The filename of the target text file containing language entries (e.g., 'kr_client.str' or 'kr_pregame.str').

    Notes:
        - The function uses regular expressions to detect and modify the entries.
        - Entries listed in the 'no_prefix_indexes' list will retain their original format without numeric tags.

    Example:
        Given a target text file 'kr_client.str':
        ```
        [SI_PLAYER_NAME] = "Player Name"
        [SI_PLAYER_LEVEL] = "Player Level"
        ```

        Calling `addIndexToEosui('kr_client.str')` will produce an output file 'output.txt':
        ```
        [SI_PLAYER_NAME] = "{C:1}Player Name"
        [SI_PLAYER_LEVEL] = "{C:2}Player Level"
        ```
    """
    no_prefix_indexes = [
        "SI_INTERACT_PROMPT_FORMAT_PLAYER_NAME",
        "SI_PLAYER_NAME",
        "SI_PLAYER_NAME_WITH_TITLE_FORMAT",
        "SI_MEGASERVER0",
        "SI_MEGASERVER1",
        "SI_MEGASERVER2",
        "SI_KEYBINDINGS_LAYER_BATTLEGROUNDS",
        "SI_KEYBINDINGS_LAYER_DIALOG",
        "SI_KEYBINDINGS_LAYER_GENERAL",
        "SI_KEYBINDINGS_LAYER_HOUSING_EDITOR",
        "SI_KEYBINDINGS_LAYER_HOUSING_EDITOR_PLACEMENT_MODE",
        "SI_KEYBINDINGS_LAYER_HUD_HOUSING",
        "SI_KEYBINDINGS_LAYER_INSTANCE_KICK_WARNING",
        "SI_KEYBINDINGS_LAYER_NOTIFICATIONS",
        "SI_KEYBINDINGS_LAYER_SIEGE",
        "SI_KEYBINDINGS_LAYER_USER_INTERFACE_SHORTCUTS",
        "SI_KEYBINDINGS_LAYER_UTILITY_WHEEL",
        "SI_SLASH_CAMP",
        "SI_SLASH_CHATLOG",
        "SI_SLASH_DUEL_INVITE",
        "SI_SLASH_ENCOUNTER_LOG",
        "SI_SLASH_FPS",
        "SI_SLASH_GROUP_INVITE",
        "SI_SLASH_JUMP_TO_FRIEND",
        "SI_SLASH_JUMP_TO_GROUP_MEMBER",
        "SI_SLASH_JUMP_TO_GUILD_MEMBER",
        "SI_SLASH_JUMP_TO_LEADER",
        "SI_SLASH_LATENCY",
        "SI_SLASH_LOGOUT",
        "SI_SLASH_PLAYED_TIME",
        "SI_SLASH_QUIT",
        "SI_SLASH_READY_CHECK",
        "SI_SLASH_RELOADUI",
        "SI_SLASH_REPORT_BUG",
        "SI_SLASH_REPORT_CHAT",
        "SI_SLASH_REPORT_FEEDBACK",
        "SI_SLASH_REPORT_HELP",
        "SI_SLASH_ROLL",
        "SI_SLASH_SCRIPT",
        "SI_SLASH_STUCK",
    ]

    textLines = []
    indexPrefix = ""

    if re.search('client', txtFilename):
        indexPrefix = "C:"
    if re.search('pregame', txtFilename):
        indexPrefix = "P:"

    with open(txtFilename, 'r', encoding="utf8") as textIns:
        for indexCount, line in enumerate(textIns, start=1):
            maFontTag = reFontTag.match(line)
            maClientUntaged = reClientUntaged.match(line)
            maEmptyString = reEmptyString.match(line)

            if maFontTag:
                textLines.append(line)
                continue
            elif maEmptyString:
                conIndex = maEmptyString.group(1)
                lineOut = '[{}] = ""\n'.format(conIndex)
                textLines.append(lineOut)
            elif maClientUntaged:
                conIndex = maClientUntaged.group(1)
                conText = maClientUntaged.group(2) or ''
                conTextPreserved = preserve_escaped_sequences(conText)
                if conIndex not in no_prefix_indexes:
                    formattedLine = '[{}] = "{{{}}}{}"\n'.format(conIndex, indexPrefix + str(indexCount),
                                                                 conTextPreserved)
                else:
                    formattedLine = '[{}] = "{}"\n'.format(conIndex, conTextPreserved)
                lineOut = restore_escaped_sequences(formattedLine)
                textLines.append(lineOut)

    with open("output.txt", 'w', encoding="utf8") as out:
        for line in textLines:
            out.write(line)


@mainFunction
def removeIndexFromEosui(txtFilename):
    """
    Remove tags and identifiers from either kr_client.str or kr_pregame.str for use with official release.

    This function reads a target text file containing entries with tags and identifiers and removes these tags and identifiers,
    resulting in a clean language text file. The output is saved in a new file named 'output.txt'.

    Args:
        txtFilename (str): The filename of the target text file containing entries with tags and identifiers
                          (e.g., 'kr_client.str' or 'kr_pregame.str').

    Notes:
        - The function uses regular expressions to detect and remove tags, identifiers, and empty lines.
        - Entries containing '[Font:' are skipped, as well as empty lines.
        - The cleaned entries are written to the output file 'output.txt' in the same directory as the script.

    Example:
        Given a target text file 'kr_client.str':
        ```
        [SI_LOCATION_NAME] = "{C:10207}Gonfalon Bay"
        ```

        Calling `removeIndexFromEosui('kr_client.str')` will produce an output file 'output.txt':
        ```
        [SI_LOCATION_NAME] = "Gonfalon Bay"
        ```

    """
    textLines = []

    with open(txtFilename, 'r', encoding="utf8") as textIns:
        for line in textIns:
            line = line.rstrip()
            maFontTag = reFontTag.search(line)
            maEmptyString = reEmptyString.search(line)

            if maFontTag or maEmptyString:
                textLines.append(line + "\n")
                continue

            maClientTaged = reClientTaged.match(line)
            if maClientTaged:
                conIndex = maClientTaged.group(1)
                conText = maClientTaged.group(3)
                escaped = preserve_escaped_sequences(conText)
                formatted = '[{}] = "{}"\n'.format(conIndex, escaped)
                lineOut = restore_escaped_sequences(formatted)
                textLines.append(lineOut)
            elif line:
                textLines.append(line + "\n")

    with open("output.txt", 'w', encoding="utf8") as out:
        for lineOut in textLines:
            out.write(lineOut)


@mainFunction
def strip_gender_suffix(input_file, output_file="output.txt"):
    """
    Reads a text file and removes ^M, ^F, ^m, ^f, ^N, ^n suffixes from all matching lines.

    Args:
        input_file (str): The source file containing ESO lang-formatted lines.
        output_file (str): The output file with cleaned names.
    """

    with open(input_file, 'r', encoding='utf8') as infile, open(output_file, 'w', encoding='utf8') as outfile:
        for line in infile:
            cleaned_line = reGenderSuffix.sub('', line)
            outfile.write(cleaned_line)

    print("Stripped gender suffixes and saved to {}".format(output_file))


@mainFunction
def extract_npc_name_matches(tagged_txt_file, lua_input_file):
    """
    Parses a tagged ESO language file and a Lua file of known NPC names, then writes out two Lua files:
    one for matched names using stringIndex as keys and one for unmatched ones.

    Args:
        tagged_txt_file (str): File with lines like {{8290981-0-123:}}Julien Rissiel^M
        lua_input_file (str): Lua file with [npc_id] = "Name", lines
    """
    textUntranslatedLiveDict = {}
    readTaggedLangFile(tagged_txt_file, textUntranslatedLiveDict)

    # Build a cleaned name -> first stringIndex mapping from tagged lang file
    name_to_stringIndex = {}
    for tag, rawname in textUntranslatedLiveDict.items():
        cleaned_name = reGenderSuffix.sub('', rawname.strip())
        if cleaned_name not in name_to_stringIndex:
            parts = tag.split('-')
            if len(parts) == 3:
                string_index = int(parts[2])
                name_to_stringIndex[cleaned_name] = string_index

    matched_output = []
    unmatched_output = []

    in_table = False
    with open(lua_input_file, 'r', encoding='utf8') as luain:
        for line in luain:
            if 'lib.quest_givers["en"]' in line:
                in_table = True
                continue
            if in_table and '}' in line:
                break

            match = re.match(r'\s*\[(\d+)\]\s*=\s*"(.+?)",?', line)
            if match:
                npc_id = int(match.group(1))
                name = match.group(2).strip()
                if name in name_to_stringIndex:
                    string_index = name_to_stringIndex[name]
                    matched_output.append('    [{}] = "{}",'.format(string_index, name))
                else:
                    unmatched_output.append('    [{}] = "{}",'.format(npc_id, name))

    with open("npc_names_matched.lua", 'w', encoding='utf8') as out:
        out.write("return {\n")
        out.write("\n".join(matched_output))
        out.write("\n}\n")

    with open("npc_names_unmatched.lua", 'w', encoding='utf8') as out:
        out.write("return {\n")
        out.write("\n".join(unmatched_output))
        out.write("\n}\n")

    print("Done. Wrote matched and unmatched NPC name files.")


def readNullStringByChar(offset, start, file):
    """Reads one byte and any subsequent bytes of a multi byte sequence."""
    nullChar = False
    textLine = None
    currentPosition = file.tell()
    file.seek(start + offset)
    while not nullChar:
        shift = 1
        char = file.read(shift)
        value = int.from_bytes(char, "big")
        next_char = None
        if value > 0x00 and value <= 0x74:
            shift = 1
        elif value >= 0xc0 and value <= 0xdf:
            shift = 2
        elif value >= 0xe0 and value <= 0xef:
            shift = 3
        elif value >= 0xf0 and value <= 0xf7:
            shift = 4
        if shift > 1:
            next_char = file.read(shift - 1)
        if next_char:
            char = b''.join([char, next_char])
        if not char:
            # eof
            break
        if textLine is None:
            textLine = char
            continue
        if textLine is not None and char != b'\x00':
            textLine = b''.join([textLine, char])
        # if textLine is not None and char != b'\x00' and char == b'\x0A':
        #     textLine = b''.join([textLine, b'\x5C\x6E'])
        if textLine is not None and char == b'\x00':
            nullChar = True
    file.seek(currentPosition)
    return textLine


def readNullString(offset, start, file):
    """Reads a null-terminated string from the file, starting at the given offset within the chunk.

    Args:
        offset (int): The offset within the chunk to start reading the string.
        start (int): The starting position within the file.
        file (file): The file object to read from.

    Returns:
        bytes: The read null-terminated string.
    """
    chunkSize = 1024
    nullChar = False
    textLine = b''
    currentPosition = file.tell()
    file.seek(start + offset)
    while not nullChar:
        chunk = file.read(chunkSize)
        if not chunk:
            # End of file
            break
        null_index = chunk.find(b"\x00")
        if null_index >= 0:
            # Found the null terminator within the chunk
            textLine += chunk[:null_index]
            nullChar = True
        else:
            # Null terminator not found in this chunk, so append the whole chunk to textLine
            textLine += chunk
    file.seek(currentPosition)
    return textLine


def readLangFile(languageFileName):
    """Read a language file and extract index and string information.

    Args:
        languageFileName (str): The name of the language file to read.

    Returns:
        dict, dict: Dictionaries containing index and string information.
    """
    with open(languageFileName, 'rb') as lineIn:
        numSections = readUInt32(lineIn)
        numIndexes = readUInt32(lineIn)
        stringsStartPosition = 8 + (16 * numIndexes)
        predictedOffset = 0
        stringCount = 0
        fileIndexes = {'numIndexes': numIndexes, 'numSections': numSections}
        fileStrings = {'stringCount': stringCount}

        for index in range(numIndexes):
            chunk = lineIn.read(16)
            sectionId, sectionIndex, stringIndex, stringOffset = struct.unpack('>IIII', chunk)
            indexString = readNullString(stringOffset, stringsStartPosition, lineIn)
            fileIndexes[index] = {
                'sectionId': sectionId,
                'sectionIndex': sectionIndex,
                'stringIndex': stringIndex,
                'stringOffset': stringOffset,
                'string': indexString
            }
            if indexString not in fileStrings:
                # Create a dictionary entry for the offset with the indexString as a key
                fileStrings[indexString] = {
                    'stringOffset': predictedOffset,
                }
                # Create a dictionary entry for the string with stringCount as a key
                fileStrings[stringCount] = {
                    'string': indexString,
                }
                # add one to stringCount
                stringCount += 1
                # 1 extra for the null terminator
                predictedOffset += (len(indexString) + 1)
        fileStrings['stringCount'] = stringCount

    return fileIndexes, fileStrings


def writeLangFile(languageFileName, fileIndexes, fileStrings):
    """Write index and string information back to a language file.

    Args:
        languageFileName (str): The name of the language file to write to.
        fileIndexes (dict): Dictionary containing index information.
        fileStrings (dict): Dictionary containing string information.
    """
    numIndexes = fileIndexes['numIndexes']
    numSections = fileIndexes['numSections']
    numStrings = fileStrings['stringCount']

    # Read the indexes and update offset if string length has changed.
    for index in range(numIndexes):
        currentIndex = fileIndexes[index]
        dictString = currentIndex['string']
        currentStringInfo = fileStrings[dictString]
        currentOffset = currentStringInfo['stringOffset']
        fileIndexes[index]['stringOffset'] = currentOffset

    with open(languageFileName, 'wb') as indexOut:
        writeUInt32(indexOut, numSections)
        writeUInt32(indexOut, numIndexes)
        for index in range(numIndexes):
            currentIndex = fileIndexes[index]
            sectionId = currentIndex['sectionId']
            sectionIndex = currentIndex['sectionIndex']
            stringIndex = currentIndex['stringIndex']
            stringOffset = currentIndex['stringOffset']
            chunk = struct.pack('>IIII', sectionId, sectionIndex, stringIndex, stringOffset)
            indexOut.write(chunk)
        for index in range(numStrings):
            currentDict = fileStrings[index]
            currentString = currentDict['string']
            indexOut.write(currentString + b'\x00')


@mainFunction
def readCurrentLangFile(currentLanguageFile):
    """Reads a language file, stores index and string data, and writes to an output file.

    Args:
        currentLanguageFile (str): The name of the current language file to read.

    Note:
        This function reads the provided language file, extracts index and string information,
        updates string offsets if needed, and writes the data back to an output file named 'output.lang'.
    """

    currentFileIndexes, currentFileStrings = readLangFile(currentLanguageFile)
    print(currentFileStrings['stringCount'])
    writeLangFile('output.lang', currentFileIndexes, currentFileStrings)


def processSectionIDs(outputFileName, currentFileIndexes):
    numIndexes = currentFileIndexes['numIndexes']
    currentSection = None
    sectionCount = 0
    with open(outputFileName, 'w') as sectionOut:
        for index in range(numIndexes):
            currentIndex = currentFileIndexes[index]
            sectionId = currentIndex['sectionId']
            if sectionId != currentSection:
                sectionCount += 1
                sectionOut.write(
                    "    'section_unknown_{}': {{'sectionId': {}, 'sectionName': 'section_unknown_{}'}},\n".format(
                        sectionCount, sectionId, sectionCount))
                currentSection = sectionId


@mainFunction
def extractSectionIDs(currentLanguageFile, outputFileName):
    """
    Extract section ID numbers from a language file and write them to an output file.

    This function reads a provided language file, extracts the section ID numbers
    associated with the strings in the language file, and writes a list of unique
    section ID numbers to the specified output file.

    Args:
        currentLanguageFile (str): The name of the current language file to read.
        outputFileName (str): The name of the output file to write section ID numbers to.

    Note:
        The extracted section ID numbers are written to the output file in the format:
        section_unknown_1 = <section_id>
        section_unknown_2 = <section_id>
        ...

    Example:
        Given a language file 'en.lang' containing strings and section ID information,
        calling extractSectionIDs('en.lang', 'section_ids.txt') will create 'section_ids.txt'
        with a list of unique section ID numbers.

    """
    currentFileIndexes, currentFileStrings = readLangFile(currentLanguageFile)
    processSectionIDs(outputFileName, currentFileIndexes)


@mainFunction
def extractSectionEntries(langFile, section_arg, useName=True):
    """
    Extracts all entries from a language file for a specific section (by name or ID).

    Args:
        langFile (str): The .lang file to read (e.g., en.lang).
        section_arg (str|int): Either the section name (e.g., "lorebook_names") or numeric section ID (e.g., 3427285).
        useName (bool): If True, filenames will include both ID and section name (if known). Default is False.

    Writes:
        <sectionId>.txt or <sectionId>-<sectionName>.txt
    """
    try:
        section_id = int(section_arg)
        section_key = get_section_key_by_id(section_id)
        if useName and section_key and not re.match(r'section_unknown_\d+$', section_key):
            output_name = "{}_{}.txt".format(section_id, section_key)
        else:
            output_name = "{}.txt".format(section_id)
    except ValueError:
        section_id = get_section_id(section_arg)
        if section_id is None:
            print("Error: Unknown section name '{}'".format(section_arg))
            return
        section_key = section_arg
        if useName:
            output_name = "{}-{}.txt".format(section_id, section_key)
        else:
            output_name = "{}.txt".format(section_id)

    fileIndexes, fileStrings = readLangFile(langFile)

    with open(output_name, "w", encoding="utf8") as out:
        for i in range(fileIndexes['numIndexes']):
            entry = fileIndexes[i]
            if entry['sectionId'] == section_id:
                secId = entry['sectionId']
                secIdx = entry['sectionIndex']
                strIdx = entry['stringIndex']
                raw_bytes = entry['string']
                escaped_bytes = preserve_escaped_sequences_bytes(raw_bytes)
                utf8_string = bytes(escaped_bytes).decode("utf8", errors="replace")
                formatted = "{{{{{}-{}-{}:}}}}{}\n".format(secId, secIdx, strIdx, utf8_string)
                lineOut = restore_escaped_sequences(formatted)
                out.write(lineOut)

    print("Done. Extracted entries from section {} to {}".format(section_id, output_name))


def processEosuiTextFile(filename, text_dict):
    """Read and process an ESOUI text file (en_client.str or en_pregame.str)
    and populate the provided text_dict.

    Args:
        filename (str): The filename of the ESOUI text file (en_client.str or en_pregame.str) to process.
        text_dict (dict): A dictionary to store the extracted text entries.

    Returns:
        None
    """
    with open(filename, 'r', encoding="utf8") as textIns:
        for line in textIns:
            line = line.rstrip()
            maEmptyString = reEmptyString.match(line)
            maClientUntaged = reClientUntaged.match(line)

            if maEmptyString:
                conIndex = maEmptyString.group(1)
                conText = ""
                text_dict[conIndex] = conText
            elif maClientUntaged:
                conIndex = maClientUntaged.group(1)  # Key (conIndex)
                conText = maClientUntaged.group(2) if maClientUntaged.group(2) is not None else ''
                text_dict[conIndex] = conText


@mainFunction
def combineClientFiles(client_filename, pregame_filename):
    """
    Combine content from en_client.str and en_pregame.str files.

    This function reads the content of en_client.str and en_pregame.str files, extracts
    constant entries that match the pattern defined by reClientUntaged or reEmptyString,
    and saves the combined information into an 'output.txt' file. If a constant exists
    in both files, only one entry will be written to eliminate duplication.

    Args:
        client_filename (str): The filename of the en_client.str file.
        pregame_filename (str): The filename of the en_pregame.str file.

    Notes:
        This function uses preserve_escaped_sequences and restore_escaped_sequences
        to ensure backslashes and quotes are correctly written to output format.

    Example:
        Given en_client.str:
            [SI_MY_CONSTANT] = "My Constant Text"
            [SI_CONSTANT] = "Some Constant Text"
        And en_pregame.str:
            [SI_CONSTANT] = "Some Constant Text"
            [SI_ADDITIONAL_CONSTANT] = "Additional Constant Text"
        Will produce output.txt:
            [SI_MY_CONSTANT] = "My Constant Text"
            [SI_CONSTANT] = "Some Constant Text"
            [SI_ADDITIONAL_CONSTANT] = "Additional Constant Text"
    """

    textClientDict = {}
    textPregameDict = {}

    # Load both files using shared helper
    processEosuiTextFile(client_filename, textClientDict)
    processEosuiTextFile(pregame_filename, textPregameDict)

    # Merge into single output dictionary
    mergedDict = {}
    mergedDict.update(textClientDict)
    mergedDict.update(textPregameDict)  # pregame entries will not overwrite existing ones

    with open("output.txt", 'w', encoding="utf8") as out:
        for conIndex, conText in mergedDict.items():
            if conText == "":
                lineOut = '[{}] = ""\n'.format(conIndex)
            else:
                escaped = preserve_escaped_sequences(conText)
                formatted = '[{}] = "{}"\n'.format(conIndex, escaped)
                lineOut = restore_escaped_sequences(formatted)
            out.write(lineOut)


@mainFunction
def createPoFileFromEsoUI(inputFile, lang="en", outputFile="messages.po", isBaseEnglish=False, inputEnglishFile=None):
    """
    Converts an ESO .str file into a .po file, using English as fallback if necessary.

    Args:
        inputFile (str): Path to the translated or base English .str file.
        lang (str): Language code for the PO file metadata.
        outputFile (str): Output PO file name.
        isBaseEnglish (bool): If True, produces empty msgstr entries.
        inputEnglishFile (str, optional): Path to English .str file to use for msgid fallback (required if isBaseEnglish=False).
    """
    if not isBaseEnglish and inputEnglishFile is None:
        print("Error: inputEnglishFile is required if isBaseEnglish is False.")
        return

    # Load English strings for msgid reference
    english_map = {}
    if inputEnglishFile:
        with open(inputEnglishFile, 'r', encoding='utf-8') as f_en:
            for line in f_en:
                m = reClientUntaged.match(line)
                if m:
                    k, v = m.group(1), m.group(2)
                    english_map[k] = bytes(v, 'utf-8').decode('unicode_escape')

    # Load current language strings (either English or translated)
    translated_map = {}
    with open(inputFile, 'r', encoding='utf-8') as f_trans:
        for line in f_trans:
            if reFontTag.match(line):
                continue
            m = reClientUntaged.match(line)
            if m:
                k, v = m.group(1), m.group(2)
                translated_map[k] = bytes(v, 'utf-8').decode('unicode_escape')

    # Create PO file
    po = polib.POFile()
    po.metadata = {
        'Content-Type': 'text/plain; charset=UTF-8',
        'Language': lang,
    }

    keys = set(english_map if not isBaseEnglish else translated_map)
    for key in sorted(keys):
        msgid = english_map.get(key, translated_map.get(key, ""))
        msgstr = "" if isBaseEnglish else translated_map.get(key, msgid)

        entry = polib.POEntry(
            msgctxt=key,
            msgid=msgid,
            msgstr=msgstr,
        )
        po.append(entry)

    po.save(outputFile)
    print("Done. Created .po file: {}".format(outputFile))


@mainFunction
def createWeblateFile(inputFile, lang="en", outputFile=None, component=None):
    """
    Generate a YAML file for Weblate translation.

    This function reads a text file containing ESO string definitions and generates
    a single YAML file structured for use with Weblate.

    Args:
        inputFile (str): The filename of the text file containing ESO strings.
        lang (str): Language code used for the output file name (e.g., "en", "tr"). Default is "en".
        outputFile (str, optional): The filename of the output YAML file. If None, defaults to <basename>.<lang>.yaml.
        component (str, optional): Optional top-level key (e.g., "client"). If None, the output will be flat.

    Notes:
        This function extracts constant entries using the reClientUntaged pattern from the input file,
        builds a dictionary of translations, and writes them in YAML format suitable for Weblate.

    Example:
        Given 'output.txt':
        ```
        [SI_MY_CONSTANT] = "My Constant Text"
        [SI_CONSTANT] = "Some Constant Text"
        ```

        Calling `createWeblateFile('output.txt', lang='tr', component='client')` will produce:
        - 'output.tr.yaml':
          ```
          client:
            SI_MY_CONSTANT: "My Constant Text"
            SI_CONSTANT: "Some Constant Text"
          ```
    """
    if outputFile is None:
        base = os.path.splitext(os.path.basename(inputFile))[0]
        outputFile = "{}.{}.yaml".format(base, lang)

    try:
        with open(inputFile, 'r', encoding="utf8") as textIns:
            translations = {}
            for line in textIns:
                maEmptyString = reEmptyString.match(line)
                maClientUntaged = reClientUntaged.match(line)
                if maEmptyString:
                    conIndex = maEmptyString.group(1)
                    conText = ''
                    translations[conIndex] = DoubleQuotedScalarString(conText)
                elif maClientUntaged:
                    conIndex = maClientUntaged.group(1)
                    conText = maClientUntaged.group(2) if maClientUntaged.group(2) is not None else ''
                    translations[conIndex] = DoubleQuotedScalarString(conText)
    except FileNotFoundError:
        print("{} not found. Aborting.".format(inputFile))
        return

    if not translations:
        print("No translations found in {}. Aborting.".format(inputFile))
        return

    yaml = ruamel.yaml.YAML()
    yaml.preserve_quotes = True
    yaml.width = float("inf")

    with open(outputFile, 'w', encoding="utf8") as weblate_file:
        if component:
            yaml.dump({component: translations}, weblate_file)
        else:
            yaml.dump(translations, weblate_file)

    print("Generated Weblate file: {}".format(outputFile))


@mainFunction
def importClientTranslations(inputYaml, inputEnglishFile, inputLocalizedFile, langValue):
    """
    Import translated text from localized and English client files and generate an updated YAML.

    This function reads untranslated text from the specified inputEnglishFile (e.g., en_client.str)
    and translated text from the inputLocalizedFile (e.g., tr_client.str or ua_client.str). If an existing
    YAML file is present, it is used to seed the initial data. Otherwise, a fresh YAML file is generated.

    Args:
        inputYaml (str): The filename of the YAML file to update. If the file does not exist, it will be created.
        inputEnglishFile (str): The filename of the English untranslated client or pregame file.
        inputLocalizedFile (str): The filename of the localized client or pregame file to extract translations from.
        langValue (str): The language name to use as the field name in the YAML (e.g., "turkish").

    Notes:
        This function ensures that only strings currently present in the English file are included in the output.
        If a key in the English file has no corresponding translation in the localized file, it will be output
        with an empty string. Obsolete entries (ones no longer in the English file) are discarded.

    Example:
        Calling `importClientTranslations('translations.yaml', 'en_client.str', 'tr_client.str', 'turkish')` will produce:
        ```
        SI_MY_CONSTANT:
          english: "My Constant Text"
          turkish: "Benim Sabit Metnim"
        SI_NEW_CONSTANT:
          english: "New String"
          turkish: ""
        ```
        Updated translations saved to translations_updated.yaml.
    """
    translations = {}

    yaml = ruamel.yaml.YAML()
    yaml.preserve_quotes = True
    yaml.width = float("inf")

    # Load from inputYaml if it exists
    if os.path.isfile(inputYaml):
        with open(inputYaml, 'r', encoding="utf8") as yaml_file:
            yaml_data = yaml.load(yaml_file) or {}
        for conIndex, conText in yaml_data.items():
            translations[conIndex] = {
                'english': conText.get('english', ''),
                langValue: conText.get(langValue, ''),
            }

    # Read English .str file and populate or update base entries
    with open(inputEnglishFile, 'r', encoding="utf8") as en_file:
        for line in en_file:
            ma = reClientUntaged.match(line)
            if ma:
                key = ma.group(1)
                value = ma.group(2)
                if key not in translations:
                    translations[key] = {}
                translations[key]['english'] = value
                if langValue not in translations[key]:
                    translations[key][langValue] = ""

    # Read localized .str file and populate only existing keys
    with open(inputLocalizedFile, 'r', encoding="utf8") as loc_file:
        for line in loc_file:
            ma = reClientUntaged.match(line)
            if ma:
                key = ma.group(1)
                value = ma.group(2)
                if key in translations:
                    if value != translations[key].get('english', ''):
                        translations[key][langValue] = value

    # Restrict output to keys that still exist in the English file
    filtered_translations = {
        k: v for k, v in translations.items() if 'english' in v
    }

    # Wrap values with DoubleQuotedScalarString
    for key, fields in filtered_translations.items():
        fields['english'] = DoubleQuotedScalarString(fields['english'])
        fields[langValue] = DoubleQuotedScalarString(fields[langValue])

    # Write updated YAML output
    output_filename = os.path.splitext(inputYaml)[0] + "_updated.yaml"
    with open(output_filename, 'w', encoding="utf8") as out_file:
        yaml.dump(filtered_translations, out_file)

    print("Updated translations saved to {}.".format(output_filename))


@mainFunction
def createWeblateMonolingualYamls(input_en, input_translated=None, langTag=None, section_name=None):
    """
    Generate two monolingual Weblate-compatible YAML files named after section_name.

    Args:
        input_en (str): Path to the English source file (Lua-style).
        input_translated (str, optional): Path to the translated file (Lua-style). If None, translation falls back to English.
        langTag (str): Language code for the translation (e.g., 'kr', 'tr', 'uk').
        section_name (str): YAML top-level key and file prefix (e.g., 'client', 'pregame').
    """
    if not langTag:
        print("Missing langTag (e.g., 'kr', 'tr'). Aborting.")
        return
    if not section_name:
        print("Missing section_name (e.g., 'client', 'pregame'). Aborting.")
        return

    def parse_lua_file(path):
        entries = {}
        for line in open(path, encoding="utf-8"):
            ma = reClientUntaged.match(line)
            if ma:
                key, val = ma.group(1), ma.group(2)
                entries[key] = val
        return entries

    en_data = parse_lua_file(input_en)
    tr_data = parse_lua_file(input_translated) if input_translated else {}

    out_en_file = "{}.en.yaml".format(section_name)
    out_tr_file = "{}.{}.yaml".format(section_name, langTag)

    yaml = ruamel.yaml.YAML()
    yaml.preserve_quotes = True
    yaml.width = float("inf")

    def write_yaml(filepath, dictionary):
        data = {section_name: {}}
        for key, val in sorted(dictionary.items()):
            data[section_name][key] = DoubleQuotedScalarString(val)
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

    write_yaml(out_en_file, en_data)

    merged_tr_data = {
        key: tr_data.get(key, "") or en_data.get(key, "")
        for key in en_data
    }
    write_yaml(out_tr_file, merged_tr_data)

    print("Wrote Weblate YAML files:")
    print("  - {}".format(out_en_file))
    print("  - {}".format(out_tr_file))


@mainFunction
def processTranslationFiles(inputYaml, clientStrings, pregameStrings, languageKey):
    """
    Process translation files using the provided YAML file and create output files.

    This function reads the client and pregame strings files, processes the translations
    using the provided YAML file, and generates separate output files for both client and
    pregame strings with the translated values if available.

    Args:
        inputYaml (str): The filename of the YAML file containing translations.
        clientStrings (str): The filename of the client strings file (e.g., tr_client.str).
        pregameStrings (str): The filename of the pregame strings file (e.g., tr_pregame.str).
        languageKey (str): The key corresponding to the desired language in the translations.
    """
    if not isinstance(languageKey, str):
        print("languageKey must be a string. Aborting.")
        return

    clientStringsDict = {}
    pregameStringsDict = {}
    processEosuiTextFile(clientStrings, clientStringsDict)
    processEosuiTextFile(pregameStrings, pregameStringsDict)

    translations = {}
    yaml = ruamel.yaml.YAML()
    yaml.preserve_quotes = True
    yaml.width = float("inf")

    try:
        with open(inputYaml, 'r', encoding='utf8') as yaml_file:
            translations = yaml.load(yaml_file)
    except FileNotFoundError:
        print("{} not found. Aborting.".format(inputYaml))
        return

    client_output_path = "client.{}.output.txt".format(languageKey)
    pregame_output_path = "pregame.{}.output.txt".format(languageKey)

    with open(client_output_path, 'w', encoding='utf8') as client_output_file:
        for key, value in clientStringsDict.items():
            output = value
            if key in translations and languageKey in translations[key]:
                output = translations[key][languageKey]
            escaped = preserve_escaped_sequences(output)
            formatted = '[{}] = "{}"\n'.format(key, escaped)
            restored = restore_escaped_sequences(formatted)
            client_output_file.write(restored)

    with open(pregame_output_path, 'w', encoding='utf8') as pregame_output_file:
        for key, value in pregameStringsDict.items():
            output = value
            if key in translations and languageKey in translations[key]:
                output = translations[key][languageKey]
            escaped = preserve_escaped_sequences(output)
            formatted = '[{}] = "{}"\n'.format(key, escaped)
            restored = restore_escaped_sequences(formatted)
            pregame_output_file.write(restored)

    print("Wrote client output to: {}".format(client_output_path))
    print("Wrote pregame output to: {}".format(pregame_output_path))


@mainFunction
def convertLangToYaml(input_txt, output_yaml=None):
    """
    Convert ESO lang-formatted text ({{sectionId-sectionIndex-stringIndex:}}Text) into a Weblate-compatible YAML file.

    Args:
        input_txt (str): Input filename like '70901198.txt'.
        output_yaml (str, optional): Output YAML filename. If not provided, derived from input filename.

    Writes:
        A .yaml file where each entry uses the key from the lang index and a quoted string.
    """
    if output_yaml is None:
        base = os.path.splitext(os.path.basename(input_txt))[0]
        output_yaml = "{}_weblate.yaml".format(base)

    with open(input_txt, 'r', encoding='utf8') as infile, open(output_yaml, 'w', encoding='utf8') as outfile:
        for line in infile:
            match = reLangIndex.match(line.rstrip())
            if match:
                key = match.group(1)
                text = match.group(2).replace('"', '\\"')
                outfile.write('{}: "{}"\n'.format(key, text))

    print("YAML output written to {}".format(output_yaml))


@mainFunction
def convertLangToPo(input_txt, output_po=None):
    """
    Convert ESO lang-formatted text ({{sectionId-sectionIndex-stringIndex:}}Text) into a Weblate-compatible PO file.

    Args:
        input_txt (str): Input filename like '70901198.txt'.
        output_po (str, optional): Output PO filename. If not provided, derived from input filename.

    Writes:
        A .po file with msgctxt as the lang key and empty msgstr values for translation.
    """
    po = polib.POFile()

    if output_po is None:
        base = os.path.splitext(os.path.basename(input_txt))[0]
        output_po = "{}_weblate.po".format(base)

    with open(input_txt, 'r', encoding='utf8') as infile:
        for line in infile:
            match = reLangIndex.match(line.rstrip())
            if match:
                key = match.group(1)
                text = match.group(2)
                entry = polib.POEntry(
                    msgctxt=key,
                    msgid=text,
                    msgstr=""
                )
                po.append(entry)

    po.save(output_po)
    print("PO output written to {}".format(output_po))


def readTaggedLangFile(taggedFile, targetDict):
    with open(taggedFile, 'r', encoding="utf8") as textIns:
        for line in textIns:
            maLangIndex = reLangIndex.match(line)
            if maLangIndex:
                conIndex = maLangIndex.group(1)
                conText = maLangIndex.group(2)
                targetDict[conIndex] = conText


def cleanText(line):
    if line is None:
        return None

    # Strip weird dots … or other chars
    line = line.replace('…', '').replace('—', '').replace('â€¦', '')

    # Remove unnecessary color tags
    reColorTagError = re.compile(r'(\|c000000)(\|c[0-9a-zA-Z]{6,6})')
    maColorTagError = reColorTagError.match(line)
    if maColorTagError:
        line = line.replace("|c000000", "")

    return line


def calculate_similarity_and_threshold(text1, text2):
    reColorTag = re.compile(r'\|c[0-9a-zA-Z]{1,6}|\|r')
    reControlChar = re.compile(r'\^f|\^n|\^F|\^N|\^p|\^P')

    if not text1 or not text2:
        return False

    subText1 = reColorTag.sub('', text1)
    subText2 = reColorTag.sub('', text2)
    subText1 = reControlChar.sub('', subText1)
    subText2 = reControlChar.sub('', subText2)

    similarity_ratio = SequenceMatcher(None, subText1, subText2).ratio()

    return text1 == text2 or similarity_ratio > 0.6


def calculate_similarity_ratio(text1, text2):
    reColorTag = re.compile(r'\|c[0-9a-zA-Z]{1,6}|\|r')
    reControlChar = re.compile(r'\^f|\^n|\^F|\^N|\^p|\^P')

    # Check if either text1 or text2 is None
    if text1 is None or text2 is None:
        return False

    # Remove color tags and control characters
    subText1 = reColorTag.sub('', text1)
    subText2 = reColorTag.sub('', text2)
    subText1 = reControlChar.sub('', subText1)
    subText2 = reControlChar.sub('', subText2)

    # Calculate similarity ratio
    similarity_ratio = SequenceMatcher(None, subText1, subText2).ratio()

    # Return True only when similarity_ratio > 0.6
    return similarity_ratio > 0.6


@mainFunction
def mergeExtractedSectionIntoLang(fullLangFile, sectionLangFile, outputLangFile="output.txt"):
    """
    Import a translated section into a full language file by matching tagged keys.

    This function reads:
      - A **translated section** file, typically created using `extractSectionEntries()`, which contains a subset
        of translated entries in the format `{{sectionId-sectionIndex-stringIndex:}}TranslatedText`
      - A **full language file** that contains the complete set of entries for a language (typically untranslated).

    It then replaces any matching entries in the full language file with the corresponding translated entries,
    based on exact key matches. Only lines starting with a valid key tag will be considered.

    The output is written to `output.txt` (or a specified output file), preserving the untranslated entries and
    merging in any provided translations from the section file.

    Args:
        translatedSectionFile (str): The filename of the translated section file, e.g. `lorebooks_uk.txt`, containing tagged entries.
        fullLangFile (str): The full language file to update, e.g. `en.lang_tag.txt`, containing all entries.
        outputLangFile (str, optional): The filename to write the merged output to. Defaults to `"output.txt"`.

    Notes:
        - This function expects both files to use tagged entry formats like `{{211640654-0-5066:}}Some text`
        - It performs exact key matches using the part inside the double curly braces.
        - Unmatched lines are written through unchanged.
    """
    textTranslatedDict.clear()

    # Read the translated section file into the global dict
    with open(sectionLangFile, 'r', encoding="utf8") as sec:
        for line in sec:
            m = reLangIndex.match(line)
            if m:
                key, value = m.groups()
                textTranslatedDict[key] = value.rstrip("\n")

    # Read the full lang file and replace lines with translated ones
    with open(fullLangFile, 'r', encoding="utf8") as full, open(outputLangFile, 'w', encoding="utf8") as out:
        for line in full:
            m = reLangIndex.match(line)
            if m:
                key, _ = m.groups()
                if key in textTranslatedDict:
                    line = "{{{{{}:}}}}{}\n".format(key, textTranslatedDict[key])
            out.write(line)

    print("Merged translations from {} into {} → {}".format(sectionLangFile, fullLangFile, outputLangFile))


@mainFunction
def diffIndexedLangText(translatedFilename, unTranslatedLiveFilename, unTranslatedPTSFilename):
    """
    Compare translations between different versions of language files.

    This function compares translations between different versions of language files and writes the results to output files.

    Args:
        translatedFilename (str): The filename of the translated language file (e.g., kb.lang.txt).
        unTranslatedLiveFilename (str): The filename of the previous/live English language file with tags (e.g., en_prv.lang_tag.txt).
        unTranslatedPTSFilename (str): The filename of the current/PTS English language file with tags (e.g., en_cur.lang_tag.txt).

    Notes:
        - `translatedFilename` should be the translated language file, usually for another language.
        - `unTranslatedLiveFilename` should be the previous/live English language file with tags.
        - `unTranslatedPTSFilename` should be the current/PTS English language file with tags.
        - The output is written to "output.txt" and "verify_output.txt" files.

    The function performs the following steps:
    - Reads the translations from the specified files into dictionaries.
    - Cleans and preprocesses the texts by removing unnecessary characters and color tags.
    - Compares the PTS and live texts to determine if translation changes are needed.
    - Writes the output to "output.txt" with potential new translations and to "verify_output.txt" for verification purposes.
    """

    # Get Previous Translation ------------------------------------------------------
    readTaggedLangFile(translatedFilename, textTranslatedDict)
    print("Processed Translated Text")
    # Get Previous/Live English Text ------------------------------------------------------
    readTaggedLangFile(unTranslatedLiveFilename, textUntranslatedLiveDict)
    print("Processed Previous Text")
    # Get Current/PTS English Text ------------------------------------------------------
    readTaggedLangFile(unTranslatedPTSFilename, textUntranslatedPTSDict)
    print("Processed Current Text")
    # Compare PTS with Live text, write output -----------------------------------------
    print("Begining Comparison")
    with open("output.txt", 'w', encoding="utf8") as out:
        with open("verify_output.txt", 'w', encoding="utf8") as verifyOut:
            for key in textUntranslatedPTSDict:
                translatedText = textTranslatedDict.get(key)
                liveText = textUntranslatedLiveDict.get(key)
                ptsText = textUntranslatedPTSDict.get(key)
                translatedTextStripped = cleanText(translatedText)
                liveTextStripped = cleanText(liveText)
                ptsTextStripped = cleanText(ptsText)
                # -- Assign lineOut to ptsText
                lineOut = ptsText
                useTranslatedText = False
                hasExtendedChars = isTranslatedText(translatedTextStripped)
                writeOutput = False
                # ---Determine Change Ratio between Live and Pts---
                liveAndPtsGreaterThanThreshold = False
                # ---Determine Change Ratio between Translated and Pts ---
                # translatedAndPtsGreaterThanThreshold = calculate_similarity_ratio(translatedTextStripped, ptsTextStripped)
                # live deleted, discard live text
                # live and pts the same, use translation
                # live and pts slightly different, use translation
                # live and pts very different, use pts Text
                # pts new line, use pts Text

                # hasTranslation is not named well, it means that it is acceptable to use
                # translated text if it exists
                if liveTextStripped is not None and ptsTextStripped is None:
                    continue
                if liveTextStripped is not None and ptsTextStripped is not None:
                    liveAndPtsGreaterThanThreshold = calculate_similarity_ratio(liveTextStripped, ptsTextStripped)
                    if liveTextStripped == ptsTextStripped or liveAndPtsGreaterThanThreshold:
                        useTranslatedText = True
                    if not liveAndPtsGreaterThanThreshold:
                        useTranslatedText = False
                        writeOutput = True
                if liveTextStripped is None and ptsTextStripped is not None:
                    useTranslatedText = False

                if useTranslatedText and translatedText is not None:
                    lineOut = translatedText
                lineOut = '{{{{{}:}}}}{}\n'.format(key, lineOut.rstrip())
                # -- Save questionable comparison to verify
                if writeOutput:
                    if translatedText is not None:
                        verifyOut.write('T{{{{{}:}}}}{}\n'.format(key, translatedText.rstrip()))
                    verifyOut.write('L{{{{{}:}}}}{}\n'.format(key, liveText.rstrip()))
                    verifyOut.write('P{{{{{}:}}}}{}\n'.format(key, ptsText.rstrip()))
                    verifyOut.write('{{{}}}:{{{}}}\n'.format(liveAndPtsGreaterThanThreshold, lineOut))
                out.write(lineOut)


@mainFunction
def diffEsouiText(translatedFilename, liveFilename, ptsFilename):
    """Diff and Merge ESOUI Text Files with Existing Translations.

    This function reads three input ESOUI text files: translatedFilename, liveFilename, and ptsFilename,
    and performs a diff and merge operation. The purpose is to update the translated ESOUI text by
    comparing the live and PTS (Public Test Server) text files and using the existing translations when
    the text is the same.

    Args:
        translatedFilename (str): The filename of the translated ESOUI text file (en_client.str or en_pregame.str).
        liveFilename (str): The filename of the live ESOUI text file (kb_client.str or kb_pregame.str).
        ptsFilename (str): The filename of the PTS (Public Test Server) ESOUI text file (kb_client.str or kb_pregame.str).

    Note:
        This function uses reLangIndex to identify language constant entries and their associated text.

    The function compares the live and PTS text for each constant entry and determines whether to use
    the existing translation or the live/PTS text. The result is saved in an 'output.txt' file containing
    merged entries with translated text if available.

    """
    # Read translated text ----------------------------------------------------
    processEosuiTextFile(translatedFilename, textTranslatedDict)
    # Read live text ----------------------------------------------------
    processEosuiTextFile(liveFilename, textUntranslatedLiveDict)
    # Read pts text ----------------------------------------------------
    processEosuiTextFile(ptsFilename, textUntranslatedPTSDict)
    # --Write Output ------------------------------------------------------
    with open("output.txt", 'w', encoding="utf8") as out:
        for key in textUntranslatedPTSDict:
            translatedText = textTranslatedDict.get(key)
            liveText = textUntranslatedLiveDict.get(key)
            ptsText = textUntranslatedPTSDict.get(key)
            maEmptyString = reEmptyString.match(ptsText)
            if maEmptyString:
                conIndex = maEmptyString.group(1)
                lineOut = '[{}] = ""\n'.format(conIndex)
                out.write(lineOut)
                continue
            hasExtendedChars = isTranslatedText(translatedText)
            hasTranslation = False
            outputText = ptsText

            if translatedText is not None and (translatedText != ""):
                if (translatedText != ptsText):
                    hasTranslation = True
            if not hasTranslation and hasExtendedChars:
                hasTranslation = True
            if translatedText is None:
                hasTranslation = False

            if hasTranslation:
                outputText = translatedText

            escaped = preserve_escaped_sequences(outputText)
            formatted = '[{}] = "{}"\n'.format(key, escaped)
            restored = restore_escaped_sequences(formatted)
            out.write(restored)


@mainFunction
def diffEnglishLangFiles(LiveFilename, ptsFilename):
    """
    Compare differences between the current and PTS 'en.lang' files after conversion to text and tagging.

    This function analyzes differences between two versions of 'en.lang' files: the current version and the PTS version.
    It then categorizes and writes the findings to separate output files.

    Args:
        LiveFilename (str): The filename of the previous/live 'en.lang' file with tags.
        ptsFilename (str): The filename of the current/PTS 'en.lang' file with tags.

    Notes:
        The function reads the translation data from the specified files using the 'readTaggedLangFile' function.
        The analysis results are categorized into 'matched', 'close match', 'changed', 'added', and 'deleted' indexes.
        Output is written to various output files for further review and analysis.

    The function performs the following steps:
    - Reads translation data from the specified files into dictionaries.
    - Compares translations between PTS and live texts, categorizing indexes as 'matched', 'close match', 'changed',
      'added', or 'deleted'.
    - Identifies and categorizes new and deleted indexes.
    - Writes analysis results to separate output files.

    Outputs:
    - 'matchedIndexes.txt': Indexes that have identical translations in PTS and live versions.
    - 'closeMatchLiveIndexes.txt': Indexes with translations that are close in similarity between PTS and live versions.
    - 'closeMatchPtsIndexes.txt': Corresponding PTS translations for 'closeMatchLiveIndexes.txt'.
    - 'changedIndexes.txt': Indexes with changed translations between PTS and live versions.
    - 'deletedIndexes.txt': Indexes present in the live version but absent in the PTS version.
    - 'addedIndexes.txt': Indexes that are newly added in the PTS version.
    """

    def write_output_file(filename, targetList, targetCount, targetString):
        with open(filename, 'w', encoding="utf8") as out:
            lineOut = '{}: indexes {}\n'.format(targetCount, targetString)
            out.write(lineOut)
            for i in range(len(targetList)):
                lineOut = targetList[i]
                out.write(lineOut)

    # Get Previous/Live English Text ------------------------------------------------------
    readTaggedLangFile(LiveFilename, textUntranslatedLiveDict)
    # Get Current/PTS English Text ------------------------------------------------------
    readTaggedLangFile(ptsFilename, textUntranslatedPTSDict)
    # Compare PTS with Live text, write output -----------------------------------------
    matchedText = []
    closeMatchLiveText = []
    closeMatchPtsText = []
    changedText = []
    deletedText = []
    addedText = []
    addedIndexCount = 0
    matchedCount = 0
    closMatchCount = 0
    changedCount = 0
    deletedCount = 0
    for key in textUntranslatedPTSDict:
        ptsText = textUntranslatedPTSDict.get(key)
        liveText = textUntranslatedLiveDict.get(key)
        if textUntranslatedLiveDict.get(key) is None:
            addedIndexCount = addedIndexCount + 1
            lineOut = '{{{{{}:}}}}{}\n'.format(key, ptsText)
            addedText.append(lineOut)
            continue
        liveAndPtsGreaterThanThreshold = calculate_similarity_and_threshold(liveText, ptsText)
        if liveText == ptsText:
            matchedCount = matchedCount + 1
            lineOut = '{{{{{}:}}}}{}\n'.format(key, ptsText)
            matchedText.append(lineOut)
        elif liveAndPtsGreaterThanThreshold:
            closMatchCount = closMatchCount + 1
            lineOut = '{{{{{}:}}}}{}\n'.format(key, liveText)
            closeMatchLiveText.append(lineOut)
            lineOut = '{{{{{}:}}}}{}\n'.format(key, ptsText)
            closeMatchPtsText.append(lineOut)
        else:
            changedCount = changedCount + 1
            lineOut = '{{{{{}:pts:}}}}{}\n{{{{{}:live:}}}}{}\n\n'.format(key, ptsText, key, liveText)
            changedText.append(lineOut)
    for key in textUntranslatedLiveDict:
        liveText = textUntranslatedLiveDict.get(key)
        if textUntranslatedPTSDict.get(key) is None:
            deletedCount = deletedCount + 1
            lineOut = '{{{{{}:}}}}{}\n'.format(key, liveText)
            deletedText.append(lineOut)
    print('{}: new indexes added'.format(addedIndexCount))
    print('{}: indexes matched'.format(matchedCount))
    print('{}: indexes were a close match'.format(closMatchCount))
    print('{}: indexes changed'.format(changedCount))
    print('{}: indexes deleted'.format(deletedCount))
    # Write matched indexes
    write_output_file("matchedIndexes.txt", matchedText, matchedCount, 'matched')
    # Write close match Live indexes
    write_output_file("closeMatchLiveIndexes.txt", closeMatchLiveText, closMatchCount, 'were a close match')
    # Write close match PTS indexes
    write_output_file("closeMatchPtsIndexes.txt", closeMatchPtsText, closMatchCount, 'were a close match')
    # Write changed indexes
    write_output_file("changedIndexes.txt", changedText, changedCount, 'changed')
    # Write deleted indexes
    write_output_file("deletedIndexes.txt", deletedText, deletedCount, 'deleted')
    # Write added indexes
    write_output_file("addedIndexes.txt", addedText, addedIndexCount, 'added')


@mainFunction
def apply_byte_offset_to_hangul(input_filename):
    """
    Apply Byte Offset to Korean Hangul Characters (BETA)

    This function is in BETA stages and not currently used. It provides a simplified method
    to apply a byte offset to Korean Hangul characters in the input text file, converting them
    to Chinese UTF-8 characters starting from U+6E00. The result is saved in an "output.txt" file.

    Args:
        input_filename (str): The filename of the input text file containing Korean text.

    Note:
        This function is intended for experimental purposes and may not produce desired results.
        It uses a simple character-based approach to apply the byte offset and does not use the
        fontforge API. For accurate font manipulation, it's recommended to explore the use of
        the fontforge API as demonstrated in previous examples.

    Example:
        Given an input text file 'korean_text.txt':
        ```
        가나다
        ```

        Calling `apply_byte_offset_to_hangul('korean_text.txt')` will create an "output.txt" file with:
        ```
        京京京
        ```
    """
    output_filename = "output.txt"

    with open(input_filename, "r", encoding="utf-8") as input_file:
        input_text = input_file.read()

    converted_text = ""
    for char in input_text:
        char_code = ord(char)
        if 0xAC00 <= char_code <= 0xD7A3:  # Korean Hangul range
            target_code = char_code + (0x6E00 - 0xAC00) + 0xE000  # Adjust for 3-byte characters
            converted_text += chr(target_code)
        else:
            converted_text += char

    with open(output_filename, "w", encoding="utf-8") as output_file:
        output_file.write(converted_text)


@mainFunction
def test_section_functions():
    section_key = 'section_unknown_1'
    section_id = get_section_id(section_key)
    section_name = get_section_name(section_key)

    print("Section ID for '{}': {}".format(section_key, section_id))
    print("Section Name for '{}': {}".format(section_key, section_name))

    section_id_to_find = 242841733
    section_key_found = get_section_key_by_id(section_id_to_find)

    print("The sction key found was '{}': using {}".format(section_key_found, section_id_to_find))


test_strings = [
    '[Font:ZoFontAlert] = "EsoKR/fonts/univers47.otf|24|soft-shadow-thick"',
    '[SI_ABANDON_QUEST_CONFIRM] = "Abandon"',
    '[SI_LOCATION_NAME] = "Gonfalon Bay"',
    '[SI_ADDONLOADSTATE1] = ""',
    '[SI_PLAYER_NAME] = "<<1>>"',
    '[SI_INTERACT_PROMPT_FORMAT_UNIT_NAME] = "<<C:1>>"',
    '[SI_INTERACT_PROMPT_FORMAT_REMOTE_COMPANIONS_NAME] = "<<1>>''s <<2{Companion/Companion}>>"',
    '[SI_INTERACT_PROMPT_FORMAT_UNIT_NAME_TAGGED] = "{C:5327}<<C:1>>"',
    '[SI_ACTIONRESULT3410] = "{P:117}You can''t weapon swap while changing gear."',
]


@mainFunction
def test_remove_tags():
    print("Using reClientUntaged:")
    for string in test_strings:
        maClientUntaged = reClientUntaged.match(string)
        if maClientUntaged:
            conIndex = maClientUntaged.group(1)
            conText = maClientUntaged.group(2) if maClientUntaged.group(2) is not None else ''  # Handle empty string
            print('[{}] = "{}"'.format(conIndex, conText))

    print("\nUsing reClientTaged:")
    for string in test_strings:
        maClientTaged = reClientTaged.match(string)
        if maClientTaged:
            conIndex = maClientTaged.group(1)
            conText = maClientTaged.group(3)
            print('[{}] = "{}"'.format(conIndex, conText))

    print("\nUsing reEmptyString:")
    for string in test_strings:
        maEmptyString = reEmptyString.match(string)
        if maEmptyString:
            conIndex = maEmptyString.group(1)
            print('[{}] = ""'.format(conIndex))


@mainFunction
def test_add_tags():
    no_prefix_indexes = [
        "SI_INTERACT_PROMPT_FORMAT_PLAYER_NAME",
        "SI_PLAYER_NAME",
        "SI_PLAYER_NAME_WITH_TITLE_FORMAT",
        "SI_MEGASERVER0",
        "SI_MEGASERVER1",
        "SI_MEGASERVER2",
        "SI_KEYBINDINGS_LAYER_BATTLEGROUNDS",
        "SI_KEYBINDINGS_LAYER_DIALOG",
        "SI_KEYBINDINGS_LAYER_GENERAL",
        "SI_KEYBINDINGS_LAYER_HOUSING_EDITOR",
        "SI_KEYBINDINGS_LAYER_HOUSING_EDITOR_PLACEMENT_MODE",
        "SI_KEYBINDINGS_LAYER_HUD_HOUSING",
        "SI_KEYBINDINGS_LAYER_INSTANCE_KICK_WARNING",
        "SI_KEYBINDINGS_LAYER_NOTIFICATIONS",
        "SI_KEYBINDINGS_LAYER_SIEGE",
        "SI_KEYBINDINGS_LAYER_USER_INTERFACE_SHORTCUTS",
        "SI_KEYBINDINGS_LAYER_UTILITY_WHEEL",
        "SI_SLASH_CAMP",
        "SI_SLASH_CHATLOG",
        "SI_SLASH_DUEL_INVITE",
        "SI_SLASH_ENCOUNTER_LOG",
        "SI_SLASH_FPS",
        "SI_SLASH_GROUP_INVITE",
        "SI_SLASH_JUMP_TO_FRIEND",
        "SI_SLASH_JUMP_TO_GROUP_MEMBER",
        "SI_SLASH_JUMP_TO_GUILD_MEMBER",
        "SI_SLASH_JUMP_TO_LEADER",
        "SI_SLASH_LATENCY",
        "SI_SLASH_LOGOUT",
        "SI_SLASH_PLAYED_TIME",
        "SI_SLASH_QUIT",
        "SI_SLASH_READY_CHECK",
        "SI_SLASH_RELOADUI",
        "SI_SLASH_REPORT_BUG",
        "SI_SLASH_REPORT_CHAT",
        "SI_SLASH_REPORT_FEEDBACK",
        "SI_SLASH_REPORT_HELP",
        "SI_SLASH_ROLL",
        "SI_SLASH_SCRIPT",
        "SI_SLASH_STUCK",
    ]

    indexPrefix = ""
    testingFilename = "en_client_cur.lua"

    if re.search('client', testingFilename):
        indexPrefix = "C:"
    if re.search('pregame', testingFilename):
        indexPrefix = "P:"

    print("Using reClientUntaged:")
    for count, string in enumerate(test_strings, start=1):
        maFontTag = reFontTag.match(string)
        maClientUntaged = reClientUntaged.match(string)
        maEmptyString = reEmptyString.match(string)

        if maFontTag:
            print(string)
            continue
        elif maEmptyString:
            conIndex = maEmptyString.group(1)  # Key (conIndex)
            newString = '[{}] = ""'.format(conIndex)
            print("String #{}:".format(count))
            print("Group 0:", maEmptyString.group(0))
            print("Group 1:", maEmptyString.group(1))
            print(newString)
            print()
        elif maClientUntaged:
            conIndex = maClientUntaged.group(1)  # Key (conIndex)
            conText = maClientUntaged.group(2)  # Text content
            conText = escape_lua_string(conText)

            if conText:
                if conIndex in no_prefix_indexes:
                    newString = '[{}] = "{}"'.format(conIndex, conText)
                else:
                    newString = '[{}] = "{{{}}}{}"'.format(conIndex, indexPrefix + str(count), conText)
            else:
                newString = '[{}] = ""'.format(conIndex)

            print("String #{}:".format(count))
            print("Group 0:", maClientUntaged.group(0))
            print("Group 1:", maClientUntaged.group(1))
            print("Group 2:", maClientUntaged.group(2))
            print("conIndex:", conIndex)
            print("conText:", conText)
            print(newString)
            print()


@mainFunction
def print_groups():
    for count, string in enumerate(test_strings, start=1):
        maClientUntaged = reClientUntaged.match(string)
        maClientTaged = reClientTaged.match(string)
        maEmptyString = reEmptyString.match(string)
        maFontTag = reFontTag.match(string)

        print("String #{}: {}".format(count, string))

        if maClientUntaged:
            print("Using reClientUntaged:")
            print("Group 0:", maClientUntaged.group(0))
            print("Group 1:", maClientUntaged.group(1))
            print("Group 2:", maClientUntaged.group(2))
        if maClientTaged:
            print("Using reClientTaged:")
            print("Group 0:", maClientTaged.group(0))
            print("Group 1:", maClientTaged.group(1))
            print("Group 2:", maClientTaged.group(2))
            print("Group 3:", maClientTaged.group(3))
        if maEmptyString:
            print("Using reEmptyString:")
            print("Group 0:", maEmptyString.group(0))
            print("Group 1:", maEmptyString.group(1))
        if maFontTag:
            print("Using reFontTag:")
            print("Group 0:", maFontTag.group(0))
            print("Group 1:", maFontTag.group(1))
            print("Group 2:", maFontTag.group(2))

        print()


@mainFunction
def detect_encoding_for_each_char(inputFile):
    """
    This function reads each character from the specified binary file (inputFile)
    and attempts to detect the encoding of each character individually using the
    chardet library. It is important to note that this approach is for testing purposes
    only and is not a definitive method to accurately determine the encoding of each
    character. Encoding detection is a complex task, and relying on individual characters
    may lead to inaccurate results.

    Usage:
    detect_encoding_for_each_char(inputFile)

    Parameters:
    - inputFile (str): The path to the binary file to be analyzed.

    Note: The results are printed to the console, displaying the character and the
    detected encoding for each. It is recommended not to use this method as a means
    to argue or determine the encoding of a string comprehensively.

    Example:
    detect_encoding_for_each_char("example.bin")
    """

    not_eof = True
    with open(inputFile, 'rb') as textIns:
        while not_eof:
            shift = 1
            char = textIns.read(shift)
            value = int.from_bytes(char, "big")
            next_char = None
            if value > 0x00 and value <= 0x74:
                shift = 1
            elif value >= 0xc0 and value <= 0xdf:
                shift = 2
            elif value >= 0xe0 and value <= 0xef:
                shift = 3
            elif value >= 0xf0 and value <= 0xf7:
                shift = 4
            if shift > 1:
                next_char = textIns.read(shift - 1)
            if next_char:
                char = b''.join([char, next_char])
            if not char:
                # eof
                break

            result = chardet.detect(char)
            detected_encoding = result['encoding']
            print("Character: {}, Detected Encoding: {}".format(char.decode(detected_encoding, 'replace'),
                                                                detected_encoding))


@mainFunction
def convert_file_encoding(inputFile):
    not_eof = True
    with open(inputFile, 'rb') as textIns:
        with open("output.txt", 'w', encoding="utf-8") as out:
            while not_eof:
                shift = 1
                char = textIns.read(shift)
                value = int.from_bytes(char, "big")
                next_char = None
                if value > 0x00 and value <= 0x74:
                    shift = 1
                elif value >= 0xc0 and value <= 0xdf:
                    shift = 2
                elif value >= 0xe0 and value <= 0xef:
                    shift = 3
                elif value >= 0xf0 and value <= 0xf7:
                    shift = 4
                if shift > 1:
                    next_char = textIns.read(shift - 1)
                if next_char:
                    char = b''.join([char, next_char])
                if not char:
                    # eof
                    break

                result = chardet.detect(char)
                detected_encoding = result['encoding']
                decoded_char = char.decode(detected_encoding, 'replace')

                # Re-encode the decoded character to UTF-8
                utf8_encoded_char = decoded_char.encode('utf-8')

                # Write the re-encoded character to the output file
                out.write(utf8_encoded_char.decode('utf-8'))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--help-docstrings":
        print_docstrings()
    else:
        main()
