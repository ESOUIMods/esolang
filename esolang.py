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
reClientUntaged = re.compile(r'^\[(.+?)\] = "(?!.*{[CP]:)(.*?)"$')

# Matches tagged client strings in the format [key] = "{tag:value}text"
reClientTaged = re.compile(r'^\[(.+?)\] = "(\{[CP]:.+?\})(.+?)"$')

# Matches empty client strings in the format [key] = ""
reEmptyString = re.compile(r'^\[(.+?)\] = ""$')

# Matches a font tag in the format [Font:font_name]
reFontTag = re.compile(r'^\[Font:(.+?)\] = "(.+?)"')

# Global Dictionaries ---------------------------------------------------------
textUntranslatedLiveDict = {}
textUntranslatedPTSDict = {}
textTranslatedDict = {}
textUntranslatedDict = {}

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


def escape_special_characters(text):
    return text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace(r'\\\"', r'\"')


def isTranslatedText(line):
    return any(ord(char) > 127 for char in line)


# Conversion ------------------------------------------------------------------
# (txtFilename, idFilename)
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
        "SI_KEYBINDINGS_LAYER_UTILITY_WHEEL"
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
                conIndex = maEmptyString.group(1)  # Key (conIndex)
                lineOut = '[{}] = ""\n'.format(conIndex)
                textLines.append(lineOut)
            elif maClientUntaged:
                conIndex = maClientUntaged.group(1)  # Key (conIndex)
                conText = maClientUntaged.group(2) if maClientUntaged.group(2) is not None else ''
                if conIndex not in no_prefix_indexes and maClientUntaged.group(2) is not None:
                    lineOut = '[{}] = "{{{}}}{}"\n'.format(conIndex, indexPrefix + str(indexCount), conText)
                else:
                    lineOut = '[{}] = "{}"\n'.format(conIndex, conText)
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
                lineOut = '[{}] = "{}"\n'.format(conIndex, conText)
                textLines.append(lineOut)

    with open("output.txt", 'w', encoding="utf8") as out:
        for lineOut in textLines:
            out.write(lineOut)


def readUInt32(file): return struct.unpack('>I', file.read(4))[0]


def writeUInt32(file, value): file.write(struct.pack('>I', value))


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


@mainFunction
def combineClientFiles(client_filename, pregame_filename):
    """
    Combine content from en_client.str and en_pregame.str files.

    This function reads the content of en_client.str and en_pregame.str files, extracts
    constant entries that match the pattern defined by reClientUntaged, and saves the combined
    information into an 'output.txt' file. The goal is to avoid duplication of SI_ constants
    by combining the entries from both files. If a constant exists in both files, only one
    entry will be written to the output file to eliminate duplicated constants for translation.

    Args:
        client_filename (str): The filename of the en_client.str file.
        pregame_filename (str): The filename of the en_pregame.str file.

    Notes:
        This function uses regular expressions to identify and extract constant entries
        from the input files. The extracted entries are then formatted and stored in the
        'output.txt' file.

    Example:
        Given en_client.str:
        ```
        [SI_MY_CONSTANT] = "My Constant Text"
        [SI_CONSTANT] = "Some Constant Text"
        ```

        Given en_pregame.str:
        ```
        [SI_CONSTANT] = "Some Constant Text"
        [SI_ADDITIONAL_CONSTANT] = "Additional Constant Text"
        ```

        Calling `combineClientFiles('en_client.str', 'en_pregame.str')` will produce an output file 'output.txt':
        ```
        [SI_MY_CONSTANT] = "My Constant Text"
        [SI_CONSTANT] = "Some Constant Text"
        [SI_ADDITIONAL_CONSTANT] = "Additional Constant Text"
        ```

    """
    textLines = []
    conIndex_set = set()

    def extract_constant(line):
        conIndex = None
        conText = None
        maClientUntaged = reClientUntaged.match(line)
        maEmptyString = reEmptyString.match(line)
        if maEmptyString:
            conIndex = maEmptyString.group(1)  # Key (conIndex)
            conText = ''
        elif maClientUntaged:
            conIndex = maClientUntaged.group(1)  # Key (conIndex)
            conText = maClientUntaged.group(2) if maClientUntaged.group(2) is not None else ''
        return conIndex, conText

    def add_line(conIndex, conText):
        if conIndex not in conIndex_set:
            escaped_conText = escape_special_characters(conText)
            textLines.append('[{}] = "{}"\n'.format(conIndex, escaped_conText))
            conIndex_set.add(conIndex)

    def process_text_file(filename):
        with open(filename, 'r', encoding="utf8") as textInsClient:
            for line in textInsClient:
                line = line.rstrip()
                if line.startswith("["):
                    conIndex, conText = extract_constant(line)
                    add_line(conIndex, conText)
                else:
                    textLines.append(line + "\n")

    # Process client.str file
    process_text_file(client_filename)
    # Process pregame.str file
    process_text_file(pregame_filename)

    # Write output to output.txt
    with open("output.txt", 'w', encoding="utf8") as out:
        for lineOut in textLines:
            out.write(lineOut)


@mainFunction
def createWeblateFile(input_filename, langValue, langTag):
    """
    Generate separate YAML-like files for Weblate translation.

    This function reads the 'output.txt' file generated by the combineClientFiles function
    and creates separate YAML-like files for use with Weblate translation. The langValue parameter
    is used to specify the language value, such as 'turkish', to be used as the name of the translated
    string in the resulting YAML files. The langTag parameter specifies the language tag to be used
    as the first line in the output files.

    Args:
        input_filename (str): The filename of the 'output.txt' file generated by combineClientFiles.
        langValue (str): The language value to use as the name of the translated string.
        langTag (str): The language tag to be used as the first line in the output files.

    Notes:
        This function extracts constant entries using the reClientUntaged pattern from the input file,
        creates separate dictionaries of translations for each language, and generates separate YAML-like
        files with the format suitable for Weblate.

    Example:
        Given 'output.txt':
        ```
        [SI_MY_CONSTANT] = "My Constant Text"
        [SI_CONSTANT] = "Some Constant Text"
        [SI_ADDITIONAL_CONSTANT] = "Additional Constant Text"
        ```

        Calling `createWeblateFile('output.txt', 'turkish', 'tr')` will produce two output files:
        - 'output_tr.yaml':
          ```
          tr:
            SI_MY_CONSTANT:
              turkish: "My Constant Text"
            SI_CONSTANT:
              turkish: "Some Constant Text"
            SI_ADDITIONAL_CONSTANT:
              turkish: "Additional Constant Text"
          ```
        - 'output_en.yaml':
          ```
          en:
            SI_MY_CONSTANT:
              english: "My Constant Text"
            SI_CONSTANT:
              english: "Some Constant Text"
            SI_ADDITIONAL_CONSTANT:
              english: "Additional Constant Text"
          ```

    """
    output_filename = os.path.splitext(input_filename)[0] + "_output_" + langTag + ".yaml"

    try:
        with open(input_filename, 'r', encoding="utf8") as textIns:
            translations = {}
            for line in textIns:
                maEmptyString = reEmptyString.match(line)
                maClientUntaged = reClientUntaged.match(line)
                if maEmptyString:
                    conIndex = maEmptyString.group(1)  # Key (conIndex)
                    conText = ''
                    translations[conIndex] = conText
                elif maClientUntaged:
                    conIndex = maClientUntaged.group(1)  # Key (conIndex)
                    conText = maClientUntaged.group(2) if maClientUntaged.group(2) is not None else ''
                    translations[conIndex] = conText
    except FileNotFoundError:
        print("{} not found. Aborting.".format(input_filename))
        return

    if not translations:
        print("No translations found in {}. Aborting.".format(input_filename))
        return

    # Generate the YAML-like output
    with open(output_filename, 'w', encoding="utf8") as weblate_file:
        weblate_file.write("weblate:\n")
        for conIndex, conText in translations.items():
            weblate_file.write('  {}: "{}"\n'.format(conIndex, conText))

    print("Generated Weblate file: {}".format(output_filename))


@mainFunction
def importClientTranslations(inputYaml, inputClientFile, langValue):
    """
    Import translated text from a YAML file into the client or pregame file.

    This function reads the translated text from the specified inputYaml file,
    which is generated by the createWeblateFile function. It then updates the specified
    language's translation in either the inputClientFile (en_client.str) or inputPregameFile (en_pregame.str).

    Args:
        inputYaml (str): The filename of the YAML file generated by createWeblateFile.
        inputClientFile (str): The filename of the client or pregame file to update.
        langValue (str): The language value used as the key for the specified language in the YAML file.

    Notes:
        This function accesses the translated text from the YAML file, and for each constant entry in
        the inputClientFile, updates the translation with the corresponding entry from the YAML file.
        The updated translations are then saved to an '_updated.yaml' file.

    Example:
        Given 'translations.yaml':
        ```
        SI_MY_CONSTANT:
          english: "My Constant Text"
          turkish: "Benim Sabit Metnim"
        SI_CONSTANT:
          english: "Some Constant Text"
          turkish: "Bazı Sabit Metin"
        ```

        Calling `importClientTranslations('translations.yaml', 'en_client.str', 'turkish')` will update the
        'turkish' translation in 'en_client.str' and create an 'translations_updated.yaml' file:
        ```
        SI_MY_CONSTANT:
          english: "My Constant Text"
          turkish: "Benim Sabit Metnim"
        SI_CONSTANT:
          english: "Some Constant Text"
          turkish: "Bazı Sabit Metin"
        Updated translations saved to translations_updated.yaml.
        ```

    """
    translations = {}

    # Read the translations from the YAML file
    yaml = ruamel.yaml.YAML()
    yaml.preserve_quotes = True
    with open(inputYaml, 'r', encoding="utf8") as yaml_file:
        yaml_data = yaml.load(yaml_file)

    # Access the YAML items
    for conIndex, conText in yaml_data.items():
        translations[conIndex] = {
            'english': conText['english'],
            langValue: conText[langValue],  # Use langValue as the key for the specified language
        }

    # Update translations from the inputClientFile
    with open(inputClientFile, 'r', encoding="utf8") as textIns:
        for line in textIns:
            maEmptyString = reEmptyString.match(line)
            maClientUntaged = reClientUntaged.match(line)
            if maEmptyString:
                conIndex = maEmptyString.group(1)
                conText = ''
                translations[conIndex][langValue] = conText
            elif maClientUntaged:
                conIndex = maClientUntaged.group(1)  # Key (conIndex)
                conText = maClientUntaged.group(2) if maClientUntaged.group(2) is not None else ''
                if conIndex in translations and conText != translations[conIndex]['english']:
                    translations[conIndex][langValue] = conText  # Update the specified language

    # Generate the updated YAML-like output with double-quoted scalars and preserved formatting
    output_filename = os.path.splitext(inputYaml)[0] + "_updated.yaml"
    with open(output_filename, 'w', encoding="utf8") as updatedFile:
        for conIndex, values in translations.items():
            escaped_english_text = escape_special_characters(values['english'])
            escaped_lang_text = escape_special_characters(values[langValue])  # Use langValue here
            yaml_text = (
                "{}:\n  english: \"{}\"\n  {}: \"{}\"\n".format(
                    conIndex, escaped_english_text, langValue, escaped_lang_text
                )
            )
            updatedFile.write(yaml_text)

    print("Updated translations saved to {}.".format(output_filename))


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
def mergeCurrentEosuiText(translatedFilename, unTranslatedFilename):
    """Merge translated and untranslated ESOUI text (en_client.str or en_pregame.str)
    for current live server files.

    Args:
        translatedFilename (str): The filename of the translated ESOUI text file (en_client.str or en_pregame.str).
        unTranslatedFilename (str): The filename of the untranslated ESOUI text file (en_client.str or en_pregame.str).

    This function merges the translated ESOUI text from the specified translatedFilename with the
    untranslated ESOUI text from the unTranslatedFilename. It creates an 'output.txt' file containing
    merged entries, prioritizing translated text over untranslated text if available.

    Note:
        This function was replaced by the `diffEsouiText` function and uses reClientUntaged to identify
        constant entries and empty lines. It generates merged entries based on the translated and
        untranslated dictionaries.

    """

    # Read and process translated ESOUI text
    processEosuiTextFile(translatedFilename, textTranslatedDict)

    # Read and process untranslated ESOUI text
    processEosuiTextFile(unTranslatedFilename, textUntranslatedDict)

    # Write merged output
    with open("output.txt", 'w', encoding="utf8") as out:
        for key in textUntranslatedDict:
            conIndex = key
            conText = textTranslatedDict.get(conIndex, textUntranslatedDict[key])
            lineOut = '[{}] = "{}"\n'.format(conIndex, conText)
            out.write(lineOut)


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


@mainFunction
def mergeCurrentLangText(translatedFilename, unTranslatedFilename):
    """Untested: Merge translated and untranslated language text for current live server files.

    Args:
        translatedFilename (str): The filename of the translated language text file.
        unTranslatedFilename (str): The filename of the untranslated language text file.

    This function merges the translated language text from the specified translatedFilename with the
    untranslated language text from the unTranslatedFilename. It creates an 'output.txt' file containing
    merged entries, prioritizing translated text over untranslated text if available.

    Args:
        translatedFilename (str): The filename of the translated language text file.
        unTranslatedFilename (str): The filename of the untranslated language text file.

    This function reads the translated and untranslated language text files, extracts constant indexes
    and text using reLangIndex, and then generates merged entries based on the presence of translated
    text.

    Note:
        This function assumes that the input files follow the format of indexed language text entries
        like "{{{3427285-5-36:}}}TEXT".

    Note:
        This function is untested and not currently used.

    """

    # Get translated text entries
    with open(translatedFilename, 'r', encoding="utf8") as textIns:
        for line in textIns:
            maLangIndex = reLangIndex.match(line)
            if maLangIndex:
                conIndex, conText = maLangIndex.groups()
                textTranslatedDict[conIndex] = conText

    # Get untranslated text entries
    with open(unTranslatedFilename, 'r', encoding="utf8") as textIns:
        for line in textIns:
            maLangIndex = reLangIndex.match(line)
            if maLangIndex:
                conIndex, conText = maLangIndex.groups()
                textUntranslatedDict[conIndex] = conText

    # Write merged output
    with open("output.txt", 'w', encoding="utf8") as out:
        for key in textUntranslatedDict:
            conText = None
            if textTranslatedDict.get(key) is None:
                conText = textUntranslatedDict[key]
                lineOut = '{{{{{}:}}}}{}\n'.format(key, conText.rstrip())
                out.write(lineOut)
                continue
            if textTranslatedDict.get(key) is not None:
                if isTranslatedText(textTranslatedDict.get(key)):
                    conText = textTranslatedDict[key]
            if not conText:
                conText = textUntranslatedDict[key]
            lineOut = '{{{{{}:}}}}{}\n'.format(key, conText)
            out.write(lineOut)


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
    # Get Previous/Live English Text ------------------------------------------------------
    readTaggedLangFile(unTranslatedLiveFilename, textUntranslatedLiveDict)
    # Get Current/PTS English Text ------------------------------------------------------
    readTaggedLangFile(unTranslatedPTSFilename, textUntranslatedPTSDict)
    # Compare PTS with Live text, write output -----------------------------------------
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
                hasTranslation = False
                hasExtendedChars = isTranslatedText(translatedTextStripped)
                # ---Determine Change Ratio between Live and Pts---
                liveAndPtsGreaterThanThreshold = calculate_similarity_and_threshold(liveTextStripped, ptsTextStripped)
                # ---Determine Change Ratio between Translated and Pts ---
                translatedAndPtsGreaterThanThreshold = calculate_similarity_and_threshold(translatedTextStripped,
                                                                                          ptsTextStripped)
                writeOutput = False
                # -- Determine if there is a questionable comparison
                if translatedTextStripped and ptsTextStripped and not translatedAndPtsGreaterThanThreshold and not hasExtendedChars:
                    if translatedTextStripped != ptsTextStripped:
                        hasTranslation = True
                        writeOutput = True
                # Determine translation state ------------------------------
                if not hasTranslation and hasExtendedChars:
                    hasTranslation = True
                if translatedTextStripped is None:
                    hasTranslation = False
                # -- changes between live and pts requires new translation
                if liveTextStripped is not None and ptsTextStripped is not None:
                    if not liveAndPtsGreaterThanThreshold:
                        hasTranslation = False
                # -- New Line from ptsText that did not exist previously
                if liveTextStripped is None and ptsTextStripped is not None:
                    hasTranslation = False
                if hasTranslation:
                    lineOut = translatedText
                lineOut = '{{{{{}:}}}}{}\n'.format(key, lineOut.rstrip())
                # -- Save questionable comparison to verify
                if writeOutput:
                    verifyOut.write('{{{{{}:}}}}{}\n'.format(key, translatedText.rstrip()))
                    verifyOut.write('{{{{{}:}}}}{}\n'.format(key, liveText.rstrip()))
                    verifyOut.write('{{{{{}:}}}}{}\n'.format(key, ptsText.rstrip()))
                    verifyOut.write(lineOut)
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
    readTaggedLangFile(translatedFilename, textTranslatedDict)
    # Read live text ----------------------------------------------------
    readTaggedLangFile(liveFilename, textUntranslatedLiveDict)
    # Read pts text ----------------------------------------------------
    readTaggedLangFile(ptsFilename, textUntranslatedPTSDict)
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
            lineOut = '[{}] = "{}"\n'.format(key, outputText)
            out.write(lineOut)


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
        "SI_KEYBINDINGS_LAYER_UTILITY_WHEEL"
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
            conText = escape_special_characters(conText)

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


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--help-docstrings":
        print_docstrings()
    else:
        main()