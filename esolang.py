# -*- coding: utf-8 -*-
import argparse
import sys
import os
import inspect
import re
import struct
import codecs
from difflib import SequenceMatcher
import section_constants as section
import polib
import xml.etree.ElementTree as ET
from icu import Locale, BreakIterator
from datetime import datetime

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
        print("Usage: esolang.py function [args [args ...]]")
        print("       esolang.py --help-functions, or help")
        print("       esolang.py --list-functions, or list")
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
                if func == add_index_to_lang_file and len(func_args) < 2:
                    print("Usage: {} <txtFilename> <idFilename>".format(func.__name__))
                else:
                    func(*func_args)
                break
        else:
            print("Unknown function: {}".format(function_name))
    else:
        print("No command provided.")


# Regular Expressions for Text Processing -------------------------------------

# Matches the 2-letter language prefix at the start of a filename, such as 'pl_itemnames.dat' or 'en.lang'
reFilenamePrefix = re.compile(r'^([a-z]{2})[_\.]', re.IGNORECASE)

# Matches lines in the format {{position-itemId-count}}string_text from itemnames.dat files
reItemnameTagged = re.compile(r'^\{\{(\d+)-(\d+)-(\d+)\}\}(.*)$')

# Matches lines in the format {{sectionId-sectionIndex-stringId:}}string_text from tagged .lang text files
reLangTagged = re.compile(r'^\{\{(\d+)-(\d+)-(\d+):\}\}(.*)$')

# Tagged .lang lines with optional range: {{key:start,end}}string_text
reTaggedLangWithRange = re.compile(r'^\{\{(\d+-\d+-\d+)(?::(\d+),(\d+))?\}\}(.*)$')

# Matches a gender or neutral suffix in the format ^M, ^F, ^m, ^f, ^N, or ^n
reGrammaticalSuffix = re.compile(r'\^[fFmMnNpPzZ+]')

# Matches a language index in the format {{identifier:}}text
reLangIndex = re.compile(r'^\{\{([^:]+):\}\}(.+?)$')

# Matches lines in the format {{sectionId-sectionIndex-stringId:}}string_text and captures only the stringId and string
reLangStringId = re.compile(r'^\{\{\d+-\d+-(\d+):\}\}(.*)$')

# Matches an old-style language index in the format identifier text
reLangIndexOld = re.compile(r'^(\d{1,10}-\d{1,7}-\d{1,7}) (.+)$')

# Matches untagged client strings or empty lines in the format [key] = "value" or [key] = ""
reClientUntaged = re.compile(r'^\[([A-Z_0-9]+)\] = "(?!.*\{[CP]:)((?:[^"\\]|\\.)*)"$')

# Matches tagged client strings in the format [key] = "{tag:value}text"
reClientTaged = re.compile(r'^\[([A-Z_0-9]+)\] = "(\{[CP]:.+?\})((?:[^"\\]|\\.)*)"$')

# Matches empty client strings in the format [key] = ""
reEmptyString = re.compile(r'^\[(.+?)\] = ""$')

# Matches a font tag in the format [Font:font_name]
reFontTag = re.compile(r'^\[Font:(.+?)\] = "(.+?)"')

# Matches a resource name ID in the format sectionId-sectionIndex-stringIndex
reResNameId = re.compile(r'^(\d+)-(\d+)-(\d+)$')

# Matches ESO color tags in the format |cFFFFFF (start color) and |r (reset color)
reColorTag = re.compile(r'\|c[0-9A-Fa-f]{6}|\|r')

reEsoTexturePath = re.compile(r'(EsoUI/[^"\')\s|]+?\.dds)', re.IGNORECASE)

# Global Dictionaries ---------------------------------------------------------
textCurrentUntranslatedDict = {}
textPreviousUntranslatedDict = {}
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

SPECIAL_LANGUAGE_NAMES = {
    "SI_OFFICIALLANGUAGE0": "English",
    "SI_OFFICIALLANGUAGE1": "Français",
    "SI_OFFICIALLANGUAGE2": "Deutsch",
    "SI_OFFICIALLANGUAGE3": "日本語",
    "SI_OFFICIALLANGUAGE4": "Русский",
    "SI_OFFICIALLANGUAGE5": "Español",
    "SI_OFFICIALLANGUAGE6": "简体中文",
}


# Helper for escaped chars ----------------------------------------------------
def get_section_name(section_id):
    return section.section_info.get(section_id, {}).get("sectionName")


def get_num_strings(section_id):
    return section.section_info.get(section_id, {}).get("numStrings")


def get_max_string_length(section_id):
    return section.section_info.get(section_id, {}).get("maxStringLength")


def escape_lua_string(text):
    return text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace(r'\\\"', r'\"')


def preserve_escaped_sequences(text):
    return (
        text
            .replace("\\n", "-=CR=-")
            .replace('\\"', "-=EQ=-")
            .replace("\\\\", "-=DS=-")
    )


def restore_escaped_sequences(text):
    return (
        text
            .replace("-=CR=-", "\\n")
            .replace("-=EQ=-", '\\"')
            .replace("-=DS=-", "\\\\")
    )


def preserve_escaped_sequences_bytes(raw_bytes):
    raw_bytes = (
        raw_bytes
            .replace(b"\n", b"-=CR=-")
    )
    return raw_bytes


def restore_escaped_sequences_bytes(raw_bytes):
    return (
        raw_bytes
            .replace(b"-=CR=-", b"\n")
            .replace(b"-=DS=-", b"\\\\")
    )


def preserve_nbsp_bytes(raw_bytes):
    """
    Replaces non-breaking space (U+00A0 / b'\xC2\xA0') in bytes with a placeholder.
    """
    return raw_bytes.replace(b"\xC2\xA0", b"-=NB=-")


def restore_nbsp_bytes(raw_bytes):
    """
    Restores non-breaking space placeholder back to b'\xC2\xA0'.
    """
    return raw_bytes.replace(b"-=NB=-", b"\xC2\xA0")


def normalize_crowdin_csv_line(line):
    if line.startswith('"[') and line.count('","') == 1 and line.endswith('"'):
        key_part, value_part = line[1:-1].split('","', 1)
        return f"{key_part} = \"{value_part}\""
    return line


def clean_esoui_key(esoui_key):
    """
    Removes brackets from a esoui_key if present.

    Example:
        "[SI_ABILITYPROGRESSIONRESULT5]" -> "SI_ABILITYPROGRESSIONRESULT5"
        "SI_ABILITYPROGRESSIONRESULT5"   -> "SI_ABILITYPROGRESSIONRESULT5"
    """
    if esoui_key:
        match = re.match(r'^\[(.+)\]$', esoui_key)
        if match:
            return match.group(1)
    return esoui_key


def clean_tagged_lang_key(key):
    """
    Formats numeric keys into {{key:}} style for tagged lang files.

    Examples:
        "70901198-0-1000"       -> "{{70901198-0-1000:}}"
        "70901198-0-1000:1,2"   -> "{{70901198-0-1000:1,2}}"
        "{{70901198-0-1000:}}"   -> "{{70901198-0-1000:}}" (unchanged)
    """
    # Already correctly formatted
    if key.startswith("{{") and key.endswith("}}"):
        return key

    # Match using reTaggedLangWithRange
    match = reTaggedLangWithRange.match(f"{{{{{key}}}}}") if not key.startswith("{{") else reTaggedLangWithRange.match(key)
    if match:
        base_id = match.group(1)
        start = match.group(2)
        end = match.group(3)

        # If a range exists (start,end), return with range
        if start and end:
            return f"{{{{{base_id}:{start},{end}}}}}"
        # If no range, return with trailing colon
        return f"{{{{{base_id}:}}}}"

    # Fallback: wrap key with trailing colon
    return f"{{{{{key}:}}}}"


def readExtendedChar(file):
    """
    Reads a UTF-8 character from file, returning raw bytes and byte count.

    Args:
        file (file object): An open binary file (e.g., 'rb').

    Returns:
        tuple[bytes, int]: (char_bytes, total_bytes_read)
    """
    first_byte = file.read(1)
    if not first_byte:
        return b'', 0  # EOF

    value = int.from_bytes(first_byte, "big")

    if value <= 0x74:
        shift = 1
    elif 0xC0 <= value <= 0xDF:
        shift = 2
    elif 0xE0 <= value <= 0xEF:
        shift = 3
    elif 0xF0 <= value <= 0xF7:
        shift = 4
    else:
        shift = 1  # fallback for safety

    remaining = file.read(shift - 1) if shift > 1 else b''
    char_bytes = b''.join([first_byte, remaining])
    return char_bytes, shift


def readNullStringByChar(offset, start, file):
    """Reads a null-terminated UTF-8 string one char at a time, preserving raw binary bytes."""
    currentPosition = file.tell()
    file.seek(start + offset)

    nullChar = False
    textLine = b''

    while not nullChar:
        char, shift = readExtendedChar(file)
        if not char:
            break  # EOF

        if char == b'\x00':
            nullChar = True
            break

        textLine = b''.join([textLine, char])

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


def readTaggedLangFile(taggedFile):
    """
    Read a tagged language file and return a dictionary mapping tags to text.

    Args:
        taggedFile (str): The filename of the tagged language file to read.

    Returns:
        dict: A dictionary of key-text pairs extracted from the file.

    Example tagged entry:
        {{12345-0-1:}}Translated text
    """
    targetDict = {}
    with open(taggedFile, 'r', encoding="utf8") as textIns:
        for line in textIns:
            maLangIndex = reLangIndex.match(line)
            if maLangIndex:
                conIndex = maLangIndex.group(1)
                conText = maLangIndex.group(2)
                targetDict[conIndex] = conText

    return targetDict


def calculate_similarity_and_threshold(text1, text2):
    if not text1 or not text2:
        return False

    subText1 = reColorTag.sub('', text1)
    subText2 = reColorTag.sub('', text2)
    subText1 = reGrammaticalSuffix.sub('', subText1)
    subText2 = reGrammaticalSuffix.sub('', subText2)

    similarity_ratio = SequenceMatcher(None, subText1, subText2).ratio()
    return text1 == text2 or similarity_ratio > 0.6


def calculate_similarity_ratio(text1, text2):
    if text1 is None or text2 is None:
        return False

    subText1 = reColorTag.sub('', text1)
    subText2 = reColorTag.sub('', text2)
    subText1 = reGrammaticalSuffix.sub('', subText1)
    subText2 = reGrammaticalSuffix.sub('', subText2)

    similarity_ratio = SequenceMatcher(None, subText1, subText2).ratio()
    return similarity_ratio > 0.6


def isFallbackEnglish(translated, previous_text, current_text):
    return (translated == previous_text and translated != current_text) or (translated == current_text)


def isIdenticalText(current_text, previous_text):
    return current_text == previous_text


def isSimilarText(current_text, previous_text):
    return calculate_similarity_ratio(current_text, previous_text)


def calculate_english_fallback_similarity_ratio(text1, text2):
    if text1 is None or text2 is None:
        return False

    subText1 = reColorTag.sub('', text1)
    subText2 = reColorTag.sub('', text2)
    subText1 = reGrammaticalSuffix.sub('', subText1)
    subText2 = reGrammaticalSuffix.sub('', subText2)

    similarity_ratio = SequenceMatcher(None, subText1, subText2).ratio()
    return 0.73 < similarity_ratio < 0.95


def isSimilarEnglishFallbackText(translated_text, current_text):
    return calculate_english_fallback_similarity_ratio(translated_text, current_text)


def isTranslatedText(text):
    """
    Determines whether the input appears to be translated text.

    - If text is bytes, it is decoded to UTF-8 first.
    - Checks for non-ASCII characters or distinctive Latin letters used in ESO translations.
    """
    if not text:
        return False

    if isinstance(text, (bytes, bytearray)):
        try:
            text = text.decode("utf-8", errors="ignore")
        except Exception:
            return False

    # Normalize punctuation and hidden formatting before language detection
    text = cleanText(text)

    # Now guaranteed to be a str from here onward
    if any(ord(char) > 127 for char in text):
        return True

    latin_translation_chars = set("ñáéíóúüàâæçèêëîïôœùûÿäößãõêîìíòùąćęłńśźżğıİş¡¿")
    if any(char in latin_translation_chars for char in text.lower()):
        return True

    return False


# Read and write binary structs
def readUByte(file): return struct.unpack('>B', file.read(1))[0]


def readUInt16(file): return struct.unpack('>H', file.read(2))[0]


def readUInt32(file): return struct.unpack('>I', file.read(4))[0]


def readUInt64(file): return struct.unpack('>Q', file.read(8))[0]


def writeUByte(file, value): file.write(struct.pack('>B', value))


def writeUInt16(file, value): file.write(struct.pack('>H', value))


def writeUInt32(file, value): file.write(struct.pack('>I', value))


def writeUInt64(file, value): file.write(struct.pack('>Q', value))


def is_valid_language_code(code):
    try:
        loc = Locale(code)
        return bool(loc.getLanguage())  # returns False if language is invalid
    except Exception:
        return False


def generate_output_filename(translated_file, name_text=None, file_extension=None, section_id=None, use_section_name=None, output_filename=None, output_folder=None):
    """
    Build a generated output filename from an input language filename.

    The input filename must begin with a valid two-letter language code, such as
    en.lang, ko_267200725_map_names.txt, en_cur.lang, or en_cur_client.str.
    Optional name_text and section information are appended to the generated base
    name. If file_extension is not supplied, .txt is used. If output_folder is
    supplied, the folder is created and the returned filename includes that path.

    Returns:
        tuple[str, str]: Generated output filename and base two-letter language code.
    """
    basename = os.path.basename(translated_file).lower()
    basename = re.sub(r"(esotokorean|koreantoeso)", "", basename)

    # Try to match known filename styles (most specific to most general)
    maLangCurrentClient = re.match(r"^([a-z]{2}_cur)_(.*)\.", basename)
    maLangPreviousClient = re.match(r"^([a-z]{2}_prv)_(.*)\.", basename)
    maLangCurrent = re.match(r"^([a-z]{2}_cur)\.", basename)
    maLangPrevious = re.match(r"^([a-z]{2}_prv)\.", basename)
    maLangUnderscore = re.match(r"^([a-z]{2})_(?!cur_|prv_)(.*)\.", basename)
    maLangName = re.match(r"^([a-z]{2})\.", basename)

    match = None
    if maLangCurrentClient:
        match = maLangCurrentClient
    elif maLangPreviousClient:
        match = maLangPreviousClient
    elif maLangCurrent:
        match = maLangCurrent
    elif maLangPrevious:
        match = maLangPrevious
    elif maLangUnderscore:
        match = maLangUnderscore
    elif maLangName:
        match = maLangName

    base_lang_code = None  # initialized for scope clarity
    base_filename = ""
    if match:
        lang_prefix = match.group(1)
        base_lang_code = lang_prefix[:2]
        if match.lastindex and match.lastindex >= 2:
            base_filename = match.group(2)
    else:
        raise ValueError(f"Filename '{basename}' does not match expected pattern '<lang>_<name>.txt'")

    if not is_valid_language_code(base_lang_code):
        raise ValueError(f"Language code '{base_lang_code}' is not valid.")

    # Use section name if applicable
    section_part = ""
    if section_id:
        if use_section_name:
            section_name = get_section_name(section_id)
            if re.match(r'section_unknown_\d+$', section_name):
                section_part = f"{section_id}_unknown_section_"
            else:
                section_part = f"{section_id}_{section_name}_"
        else:
            section_part = f"{section_id}_"

    # Determine base filename
    if output_filename:
        base_name = output_filename
    else:
        parts = []
        if section_part:
            parts.append(section_part.rstrip('_'))  # remove trailing _
        if base_filename:
            parts.append(base_filename.strip('_'))
        if name_text:
            parts.append(name_text.strip().lower().replace(' ', '_').strip('_'))
        base_name = "_".join(filter(None, parts))  # filter(None, ...) skips empty strings

    # Use requested file extension or default to .txt
    if file_extension:
        extension = file_extension if file_extension.startswith('.') else f".{file_extension}"
    else:
        extension = ".txt"

    file_name = f"{lang_prefix}_{base_name}{extension}"

    # Prepend output folder path if given
    if output_folder:
        os.makedirs(output_folder, exist_ok=True)
        return os.path.join(output_folder, file_name), base_lang_code
    else:
        return file_name, base_lang_code


def read_font_lines(fonts_filename):
    """
    Read font tag lines from a file to reuse them in other output files.

    Args:
        fonts_filename (str): Filename containing font lines

    Returns:
        list[str]: Lines like [Font:ZoFontAlert] = "...", newline-stripped.

    Example font entry:
        [Font:ZoFontAnnounceLarge] = "EsoKR/fonts/univers47.slug|36|soft-shadow-thick"
    """
    font_lines = []

    with open(fonts_filename, 'r', encoding="utf8") as file:
        for line in file:
            line = line.rstrip()
            if reFontTag.match(line):
                font_lines.append(line)

    return font_lines


ICU_LOCALE_MAP = {
    "en": "en_US",
    "ko": "ko_KR",
    "tr": "tr_TR",
    "fr": "fr_FR",
    "de": "de_DE",
    "ru": "ru_RU",
    "ja": "ja_JP",
    "zh": "zh_CN",
    "es": "es_ES",
    "it": "it_IT",
    "pl": "pl_PL",
    "pt": "pt_BR",
    "th": "th_TH",
    "uk": "uk_UA",
}


def get_icu_locale_from_filename(filename):
    basename = os.path.basename(filename)
    match = reFilenamePrefix.match(basename)
    if not match:
        raise ValueError(f"Filename '{basename}' does not start with a 2-letter language code.")

    lang_code = match.group(1)
    if lang_code not in ICU_LOCALE_MAP:
        raise ValueError(f"Language code '{lang_code}' is not in ICU_LOCALE_MAP.")

    return ICU_LOCALE_MAP[lang_code]


def get_crowdin_po_metadata(filename):
    basename = os.path.basename(filename)
    match = reFilenamePrefix.match(basename)
    if not match:
        raise ValueError(f"Filename '{basename}' does not start with a 2-letter language code.")

    lang_code = match.group(1)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M+0000")

    return {
        "PO-Revision-Date": now,
        "Language": lang_code,
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
        "Content-Transfer-Encoding": "8bit",
        "X-Generator": "ESO Translation Python Script",
    }


def parse_safe_add_string_line(line):
    maSafeAddString = re.match(r'^SafeAddString\((.*?), "(.*)", \d{1,2}\)$', line)
    maSAS = re.match(r'^SAS\((.*?), "(.*)", \d{1,2}\)$', line)

    match = maSAS or maSafeAddString
    if match:
        key, value = match.groups()
        return key, value
    return None  # optional clarity


# Conversion ------------------------------------------------------------------
@mainFunction
def add_index_to_lang_file(txtFilename, idFilename):
    """
    Add numeric identifiers as tags to language entries in a target file.

    This function reads a source text file containing language data and a corresponding identifier file
    containing unique numeric identifiers for each language entry. It appends these identifiers as tags
    to the matching lines in the target language file and writes the result to a filename generated from
    txtFilename with the add_lang_index suffix.

    Args:
        txtFilename (str): The filename of the source text file containing language data (e.g., 'en.lang.txt').
        idFilename (str): The filename of the identifier file containing unique numeric identifiers
                          (e.g., 'en.lang.id.txt').

    Notes:
        The source text file should contain text data, one entry per line, while the identifier file should
        contain numeric identifiers corresponding to each entry in the same order.

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

        Calling `add_index_to_lang_file('en.lang.txt', 'en.lang.id.txt')` will produce a generated output file:
        ```
        {{18173141-0-2944:}}Hello, world!
        {{7949764-0-51729:}}How are you?
        ```
    """
    textLines = []
    idLines = []

    output_filename, _ = generate_output_filename(txtFilename, "add_lang_index")

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

    with open(output_filename, 'w', encoding="utf8", newline='\n') as output:
        for i in range(len(textLines)):
            lineOut = f'{{{{{idLines[i]}:}}}}{textLines[i]}\n'
            output.write(lineOut)

    print(f"Output written to: {output_filename}")


@mainFunction
def remove_index_from_lang_file(txtFilename):
    """
    Remove numeric identifiers from language entries in a target file.

    This function reads a target text file containing language entries with numeric identifiers as tags
    and removes these identifiers, resulting in a clean language text file. The result is written to a
    filename generated from txtFilename with the remove_lang_index suffix.

    Args:
        txtFilename (str): The filename of the target text file containing language entries with identifiers (e.g., 'en.lang.txt').

    Notes:
        The function uses regular expressions to detect and remove numeric identifiers that are enclosed in double curly braces.

    Example:
        Given a target text file 'en.lang.txt':
        ```
        {{18173141-0-2944:}}Hello, world!
        {{7949764-0-51729:}}How are you?
        ```

        Calling `remove_index_from_lang_file('en.lang.txt')` will produce a generated output file:
        ```
        Hello, world!
        How are you?
        ```
    """

    # Get ID numbers ------------------------------------------------------
    textLines = []

    output_filename, _ = generate_output_filename(txtFilename, "remove_lang_index")

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

    with open(output_filename, 'w', encoding="utf8", newline='\n') as output:
        for line in textLines:
            lineOut = f"{line}\n"
            output.write(lineOut)

    print(f"Output written to: {output_filename}")


@mainFunction
def korean_to_eso(txtFilename):
    """
    Convert Korean UTF-8 encoded text to Chinese UTF-8 encoded text with byte offset.

    This function reads a source text file containing Korean UTF-8 encoded text and applies a byte offset to convert it to
    Chinese UTF-8 encoded text. The byte offset is used to shift the Korean text to a range that is normally occupied by
    Chinese characters. This technique is used in Elder Scrolls Online (ESO) to display Korean text using a nonstandard font
    that resides in the Chinese character range. The converted text is written to a filename generated from txtFilename with
    the koreanToEso suffix.

    Args:
        txtFilename (str): The filename of the source text file containing Korean UTF-8 encoded text.

    Notes:
        - The function reads the source file in binary mode and applies a byte-level analysis to determine the proper conversion.
        - A byte offset is added to the Unicode code points of the Korean characters to position them within the Chinese character range.
        - The resulting Chinese UTF-8 encoded text is written to a new UTF-8 text file.

    Example:
        Given a source text file 'korean.txt' with Korean UTF-8 encoded text:
        ```
        나는 가고 싶다
        ```

        Calling `koreanToEso('korean.txt')` will produce a generated output file:
        ```
        犘璔 渀滠 蓶瓤
        ```
    """
    output_filename, _ = generate_output_filename(txtFilename, "koreanToEso")

    not_eof = True
    with open(txtFilename, 'rb') as textIns:
        with open(output_filename, 'w', encoding="utf8", newline='\n') as out:
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
                outText = codecs.decode(char, "UTF-8")
                out.write(outText)

    print(f"Output written to: {output_filename}")


@mainFunction
def eso_to_korean(txtFilename):
    """
    Convert Chinese UTF-8 encoded text to traditional Korean UTF-8 encoded text with byte offset reversal.

    This function reads a source text file containing Chinese UTF-8 encoded text and applies an opposite byte offset to
    convert it to traditional Korean UTF-8 encoded text. The byte offset reversal is used to shift the Chinese text back
    to its original traditional Korean character range. This technique is used when working with Chinese text that has
    been encoded using a byte offset to simulate Korean characters. The converted text is written to a filename generated
    from txtFilename with the esoToKorean suffix.

    Args:
        txtFilename (str): The filename of the source text file containing Chinese UTF-8 encoded text (e.g., 'kr.lang.txt').

    Notes:
        - The function reads the source file in binary mode and applies a byte-level analysis to determine the proper conversion.
        - An opposite byte offset is subtracted from the Unicode code points of the Chinese characters to convert them back to
          their original traditional Korean characters.
        - The resulting traditional Korean UTF-8 encoded text is written to a new UTF-8 text file.

    Example:
        Given a source text file 'kr.lang.txt' with Chinese UTF-8 encoded text:
        ```
        犘璔 渀滠 蓶瓤
        ```

        Calling `esoToKorean('kr.lang.txt')` will produce a generated output file:
        ```
        나는 가고 싶다
        ```
    """
    output_filename, _ = generate_output_filename(txtFilename, "esoToKorean")

    not_eof = True
    with open(txtFilename, 'rb') as textIns:
        with open(output_filename, 'w', encoding="utf8", newline='\n') as out:
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
                outText = codecs.decode(char, "UTF-8")
                out.write(outText)

    print(f"Output written to: {output_filename}")


@mainFunction
def add_index_to_eosui(txtFilename):
    """
    Add numeric tags to ESOUI language entries for use with translation files.

    This function reads a target text file containing language entries in the format of [key] = "value" pairs.
    It adds numeric tags to matching entries and writes the result to a filename generated from txtFilename with
    the add_esoui_index suffix.

    Args:
        txtFilename (str): The filename of the target text file containing ESOUI language entries,
                           such as 'kr_client.str' or 'kr_pregame.str'.

    Notes:
        - The function uses regular expressions to detect and modify the entries.
        - Entries listed in the no_prefix_indexes list retain their original format without numeric tags.

    Example:
        Given a target text file 'kr_client.str':
        ```
        [SI_PLAYER_NAME] = "Player Name"
        [SI_PLAYER_LEVEL] = "Player Level"
        ```

        Calling `add_index_to_eosui('kr_client.str')` will produce a generated output file such as
        'kr_client_add_esoui_index.txt':
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
        "SI_KEYBINDINGS_LAYER_ACCESSIBLE_QUICKWHEEL",
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

    output_filename, _ = generate_output_filename(txtFilename, "add_esoui_index")

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
                lineOut = '[{}] = ""'.format(conIndex)
                textLines.append(lineOut)
            elif maClientUntaged:
                conIndex = maClientUntaged.group(1)
                conText = maClientUntaged.group(2) or ''
                conTextPreserved = preserve_escaped_sequences(conText)
                if conIndex not in no_prefix_indexes:
                    formattedLine = '[{}] = "{{{}}}{}"'.format(conIndex, indexPrefix + str(indexCount), conTextPreserved)
                else:
                    formattedLine = '[{}] = "{}"'.format(conIndex, conTextPreserved)
                lineOut = restore_escaped_sequences(formattedLine)
                textLines.append(lineOut)

    with open(output_filename, 'w', encoding="utf8", newline='\n') as out:
        for line in textLines:
            out.write(f"{line}\n")


@mainFunction
def remove_index_from_eosui(txtFilename):
    """
    Remove ESOUI translation tags from tagged client or pregame entries.

    This function reads a target text file containing entries with {C:n} or {P:n} tags, removes those tags,
    and writes the clean entries to a filename generated from txtFilename with the remove_esoui_index suffix.

    Args:
        txtFilename (str): The filename of the target text file containing tagged ESOUI entries,
                           such as 'kr_client.str' or 'kr_pregame.str'.

    Notes:
        - The function uses regular expressions to detect and remove client and pregame tags.
        - Entries containing '[Font:' are skipped, as well as empty lines.

    Example:
        Given a target text file 'kr_client.str':
        ```
        [SI_LOCATION_NAME] = "{C:10207}Gonfalon Bay"
        ```

        Calling `remove_index_from_eosui('kr_client.str')` will produce a generated output file such as
        'kr_client_remove_esoui_index.txt':
        ```
        [SI_LOCATION_NAME] = "Gonfalon Bay"
        ```
    """
    textLines = []

    output_filename, _ = generate_output_filename(txtFilename, "remove_esoui_index")

    with open(txtFilename, 'r', encoding="utf8") as textIns:
        for line in textIns:
            line = line.rstrip()
            maFontTag = reFontTag.search(line)
            maEmptyString = reEmptyString.search(line)

            if maFontTag or maEmptyString:
                textLines.append(line)
                continue

            maClientTaged = reClientTaged.match(line)
            if maClientTaged:
                conIndex = maClientTaged.group(1)
                conText = maClientTaged.group(3)
                escaped = preserve_escaped_sequences(conText)
                formatted = '[{}] = "{}"'.format(conIndex, escaped)
                lineOut = restore_escaped_sequences(formatted)
                textLines.append(lineOut)
            elif line:
                textLines.append(line)

    with open(output_filename, 'w', encoding="utf8", newline='\n') as out:
        for lineOut in textLines:
            out.write(f"{lineOut}\n")


@mainFunction
def write_client_file_with_fonts(source_filename):
    """
    Create a cleaned Korean ESOUI client file with custom font declarations prepended.

    This function reads a Korean-translated client `.str` file, processes it using
    `process_eosui_client_file()` to remove unwanted entries (such as font tags or
    tagged lines), and prepends a reusable font header from `koread_font_header.txt`.

    The result is written to a new `.str` file using a standardized output filename
    generated by `generate_output_filename()` with a `name_text` such as "with_fonts".

    Args:
        source_filename (str): The input filename for the Korean-translated `.str` file.

    Notes:
        - The font declarations are read from `koread_font_header.txt`, which should contain
          lines like: `[Font:ZoFontAlert] = "EsoKR/fonts/univers47.slug|24|..."`.
        - This function is intended to create final distribution files for use in the ESO UI.
        - The output is written using UTF-8 encoding and Unix-style line endings (`\n`).
    """
    fonts_filename = "korean_font_header.txt"
    output_filename, _ = generate_output_filename(source_filename, "with_fonts", file_extension="str")

    font_lines = read_font_lines(fonts_filename)
    text_dict = process_eosui_client_file(source_filename)

    with open(output_filename, 'w', encoding="utf8", newline='\n') as out:
        # Write font header
        for line in font_lines:
            out.write(line + "\n")
        # Write translated strings
        for key, value in text_dict.items():
            out.write(f"[{key}] = \"{value}\"\n")

    print(f"Done. Output written to {output_filename}")


@mainFunction
def convert_lua_to_str_file(input_filename):
    """
    Converts a .lua file containing SafeAddString(...) or SAS(...) calls into a .str format,
    sorted by the string identifier (e.g., SI_ABILITY_NAME).

    Args:
        input_filename (str): The path to the .lua input file.

    Output:
        Writes a .str file with lines in [KEY] = "VALUE" format, sorted by KEY.
    """
    output_filename, _ = generate_output_filename(input_filename, file_extension="str")

    entries = []

    with open(input_filename, "r", encoding="utf-8") as infile:
        for line in infile:
            line = line.strip()
            parsed = parse_safe_add_string_line(line)
            if parsed:
                entries.append(parsed)

    # Sort by the key (SI_... name)
    entries.sort(key=lambda pair: pair[0])

    with open(output_filename, "w", encoding="utf-8", newline="\n") as outfile:
        for key, value in entries:
            outfile.write(f'[{key}] = "{value}"\n')

    print(f"Done. Output written to {output_filename}")


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
            restore_nbsp = restore_nbsp_bytes(currentString)
            indexOut.write(restore_nbsp + b'\x00')
        print(f"[writeLangFile]: Number of Indexes: {numIndexes}")
        print(f"[writeLangFile]: String Count: {numStrings}")


def processSectionIDs(currentFileIndexes, outputFileName):
    numIndexes = currentFileIndexes['numIndexes']
    currentSection = None
    sectionCount = 1
    section_lines = []

    # Build lookup of known sectionId -> name
    known_names = {
        sid: info.get("sectionName", "")
        for sid, info in section.section_info.items()
    }

    current_string_count = 0
    current_max_length = 0

    for index in range(numIndexes):
        currentIndex = currentFileIndexes[index]
        sectionId = currentIndex['sectionId']
        stringValue = currentIndex['string'].decode('utf-8', errors='replace') if isinstance(currentIndex['string'], bytes) else str(currentIndex['string'])
        stringLength = len(stringValue)

        if sectionId != currentSection:
            # Save previous section info
            if currentSection is not None:
                known_key = known_names.get(currentSection)

                if known_key and not known_key.startswith("section_unknown_"):
                    name = known_key
                else:
                    name = f"section_unknown_{sectionCount}"
                    sectionCount += 1

                section_lines.append(
                    f"    {currentSection}: {{'numStrings': {current_string_count}, 'maxStringLength': {current_max_length}, 'sectionName': '{name}'}},"
                )

            currentSection = sectionId
            current_string_count = 1
            current_max_length = stringLength

        else:
            current_string_count += 1
            current_max_length = max(current_max_length, stringLength)

    # Final section write-out
    if currentSection is not None:
        known_key = known_names.get(currentSection)
        if known_key and not known_key.startswith("section_unknown_"):
            name = known_key
        else:
            name = f"section_unknown_{sectionCount}"
        section_lines.append(
            f"    {currentSection}: {{'numStrings': {current_string_count}, 'maxStringLength': {current_max_length}, 'sectionName': '{name}'}},"
        )

    # Write output Python file
    with open(outputFileName, 'w', encoding='utf-8') as sectionOut:
        sectionOut.write("section_info = {\n")
        sectionOut.write("\n".join(section_lines))
        sectionOut.write("\n}\n")


@mainFunction
def build_section_constants(currentLanguageFile):
    """
    Builds section_constants_output.py containing section constant mappings
    extracted from a .lang file. Each unique sectionId is labeled with
    a generated section name like 'section_unknown_X'.

    Args:
        currentLanguageFile (str): Path to the input .lang file.

    Output:
        section_constants_output.py (ready to import as a Python file)
    """
    currentFileIndexes, currentFileStrings = readLangFile(currentLanguageFile)
    outputFileName = "section_constants_output.py"
    processSectionIDs(currentFileIndexes, outputFileName)
    print("Section constants written to:", outputFileName)


@mainFunction
def extract_section_entries(langFile, section_arg, output_filename=None, output_folder=None, useName=True):
    """
    Extract all entries from a language file for a specific numeric section ID.

    The output filename is generated from langFile, the section ID, and the section name when useName is true.
    If output_folder is provided, the generated file is written inside that folder. Output lines use tagged
    language format: {{sectionId-sectionIndex-stringId:}}text.

    Args:
        langFile (str): Path to the input .lang file.
        section_arg (str | int): Numeric section ID to extract.
        output_filename (str | None): Optional explicit base output filename.
        output_folder (str | None): Optional folder for the generated output file.
        useName (bool): Include the section name in the generated output filename when possible.
    """
    # Determine section_id and section_name
    if isinstance(section_arg, int) or str(section_arg).isdigit():
        section_id = int(section_arg)
    else:
        print(f"Error: section_arg '{section_arg}' must be a numeric section ID")
        return

    output_path, _ = generate_output_filename(
        translated_file=langFile,
        section_id=section_id,
        use_section_name=useName,
        output_filename=output_filename,
        output_folder=output_folder
    )

    fileIndexes, _ = readLangFile(langFile)

    with open(output_path, "w", encoding="utf8", newline='\n') as out:
        for i in range(fileIndexes['numIndexes']):
            entry = fileIndexes[i]
            if entry['sectionId'] == section_id:
                secId = entry['sectionId']
                secIdx = entry['sectionIndex']
                strIdx = entry['stringIndex']
                raw_bytes = entry['string']
                preserved_nbsp = preserve_nbsp_bytes(raw_bytes)
                escaped_bytes = preserve_escaped_sequences_bytes(preserved_nbsp)
                utf8_string = bytes(escaped_bytes).decode("utf8", errors="replace")
                formatted = f"{{{{{secId}-{secIdx}-{strIdx}:}}}}{utf8_string}"
                lineOut = restore_escaped_sequences(formatted)
                out.write(f"{lineOut}\n")

    print(f"Done. Extracted entries from section {section_id} to {output_path}")


@mainFunction
def extract_all_sections(langFile):
    """
    Extract every known section from a .lang file.

    For each section in section.section_info, this calls extract_section_entries() with that section ID
    and writes the tagged output into the tagged_text folder. Because useName=True is passed, each output
    file is generated with the section ID and section name when possible.

    Args:
        langFile (str): Path to the input .lang file (e.g., 'en_cur.lang').
    """
    for section_id, section_data in section.section_info.items():
        section_name = section_data.get('sectionName')
        print(f"Processing section: {section_id} ({section_name})...")
        extract_section_entries(
            langFile=langFile,
            section_arg=section_id,
            output_filename=None,
            output_folder="tagged_text",
            useName=True
        )


def process_eosui_client_file(input_filename):
    """
    Read and process an ESOUI text file (e.g., en_client.str or en_pregame.str)
    and return a dictionary of extracted key-text entries.

    Args:
        input_filename (str): The filename of the ESOUI text file to process.

    Returns:
        dict: A dictionary mapping keys to extracted text.
    """
    text_dict = {}

    with open(input_filename, 'r', encoding="utf8") as textIns:
        for line in textIns:
            line = line.rstrip()
            line = normalize_crowdin_csv_line(line)
            maEmptyString = reEmptyString.match(line)
            maClientUntaged = reClientUntaged.match(line)

            if maEmptyString:
                conIndex = maEmptyString.group(1)
                text_dict[conIndex] = ""
            elif maClientUntaged:
                conIndex = maClientUntaged.group(1)
                conText = maClientUntaged.group(2) if maClientUntaged.group(2) is not None else ""
                text_dict[conIndex] = conText

    return text_dict


@mainFunction
def combine_client_files(client_filename, pregame_filename):
    """
    Combine content from en_client.str and en_pregame.str files.

    This function reads the content of en_client.str and en_pregame.str files, extracts
    constant entries that match the pattern defined by reClientUntaged or reEmptyString,
    and writes the combined information to a filename generated from client_filename with
    the combined_files suffix. If a constant exists in both files, only one entry is written
    to eliminate duplication.

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
        The generated output file will contain:
            [SI_MY_CONSTANT] = "My Constant Text"
            [SI_CONSTANT] = "Some Constant Text"
            [SI_ADDITIONAL_CONSTANT] = "Additional Constant Text"
    """
    output_filename, _ = generate_output_filename(client_filename, "combined_files")

    textClientDict = process_eosui_client_file(client_filename)
    textPregameDict = process_eosui_client_file(pregame_filename)

    # Merge into single output dictionary
    mergedDict = {}
    mergedDict.update(textClientDict)
    mergedDict.update(textPregameDict)

    # Sort keys alphabetically
    sorted_keys = sorted(mergedDict.keys())

    with open(output_filename, 'w', encoding="utf8", newline='\n') as out:
        for conIndex in sorted_keys:
            conText = mergedDict[conIndex]
            if conText == "":
                lineOut = f'[{conIndex}] = ""'
            else:
                escaped = preserve_escaped_sequences(conText)
                formatted = f'[{conIndex}] = "{escaped}"'
                lineOut = restore_escaped_sequences(formatted)
            out.write(f"{lineOut}\n")

    print(f"Done. Created file: {output_filename}")


@mainFunction
def find_long_po_entries(po_file, limit=512):
    """
    Find translation entries whose text exceeds 512 characters.
    """
    po = polib.pofile(po_file)
    for entry in po:
        if len(entry.msgid) > limit:
            print(f"Long msgid ({len(entry.msgid)} chars) at key: {entry.msgctxt}")
        if len(entry.msgstr) > limit:
            print(f"Long msgstr ({len(entry.msgstr)} chars) at key: {entry.msgctxt}")


def is_inside_eso_placeholder(text, pos):
    """
    Return True if pos is inside an ESO placeholder such as:
        <<1>>
        <<1[/character/characters]>>
        <<t:1>>
        <<C:1>>

    This prevents PO splitting inside <<...>> tokens.
    """
    last_open = text.rfind("<<", 0, pos)
    last_close = text.rfind(">>", 0, pos)
    return last_open > last_close


def is_after_protected_newline(text, pos):
    """
    preserve_escaped_sequences() changes \\n into -=CR=-.
    This returns True only when pos is immediately after the full marker.
    """
    return text[max(0, pos - 6):pos] == "-=CR=-"


def is_inside_protected_marker(text, pos):
    """
    Prevent splitting inside preserved escape markers:
        -=CR=-
        -=EQ=-
        -=DS=-

    Splitting immediately before or after the full marker is allowed.
    Splitting inside the marker is not allowed.
    """
    markers = ("-=CR=-", "-=EQ=-", "-=DS=-")

    for marker in markers:
        for match in re.finditer(re.escape(marker), text):
            start = match.start()
            end = match.end()

            if start < pos < end:
                return True

    return False


def get_preferred_po_split_positions(text, locale):
    """
    Build a list of safe candidate split positions.

    ICU still supplies the language-aware word boundaries.
    Extra positions are added for protected \\n and whitespace.
    Unsafe positions inside ESO placeholders or protected markers are removed.
    """
    positions = set()

    # ICU language-aware word boundaries.
    word_bi = BreakIterator.createWordInstance(Locale(locale))
    word_bi.setText(text)
    for pos in word_bi:
        positions.add(pos)

    # Explicitly add positions after preserved escaped newlines.
    for match in re.finditer(r"-=CR=-", text):
        positions.add(match.end())

    # Prefer natural sentence-ending whitespace where possible.
    for match in re.finditer(r"(?<=[.!?。！？])\s+", text):
        positions.add(match.end())

    # General whitespace fallback.
    for match in re.finditer(r"\s+", text):
        positions.add(match.end())

    safe_positions = []
    for pos in sorted(positions):
        if pos <= 0 or pos >= len(text):
            continue

        if is_inside_eso_placeholder(text, pos):
            continue

        if is_inside_protected_marker(text, pos):
            continue

        safe_positions.append(pos)

    return safe_positions


def choose_po_split_position(text, start, max_len, locale):
    """
    Choose a split point near start + max_len.

    Priority:
    1. Prefer a safe boundary close to max_len.
    2. Prefer a protected newline only if it is close enough.
    3. Otherwise use the closest ICU/whitespace boundary before max_len.
    4. If there is no safe boundary before max_len, use the first safe one after.
    """
    target = start + max_len

    if target >= len(text):
        return len(text)

    near_window = 100
    near_start = max(start + 1, target - near_window)

    positions = [
        pos for pos in get_preferred_po_split_positions(text, locale)
        if pos > start
    ]

    # Prefer protected \n only when it is close enough to the target.
    linefeed_before = [
        pos for pos in positions
        if near_start <= pos <= target
           and is_after_protected_newline(text, pos)
    ]
    if linefeed_before:
        return linefeed_before[-1]

    # Otherwise use the closest safe ICU/whitespace boundary before target.
    before = [pos for pos in positions if pos <= target]
    if before:
        return before[-1]

    # If no safe split exists before target, allow the first safe split after target.
    after = [pos for pos in positions if pos > target]
    if after:
        return after[0]

    # Absolute fallback.
    return len(text)


def split_if_long(text, locale="en_US"):
    """
    Supported ESOUI Mod Translation Languages for ICU BreakIterator

    These locale codes are compatible with PyICU and should be used with
    Locale(...) and BreakIterator.createSentenceInstance(Locale(...)) or
    createWordInstance(...) where appropriate.

    +------------------------+-------------------------------+--------------+
    | Language               | Description                   | ICU Locale   |
    +------------------------+-------------------------------+--------------+
    | English                | Source Language               | en_US        |
    | Korean                 | Korean (South Korea)          | ko_KR        |
    | Turkish                | Turkish (Turkey)              | tr_TR        |
    | French                 | French (France)               | fr_FR        |
    | German                 | German (Germany)              | de_DE        |
    | Russian                | Russian (Russia)              | ru_RU        |
    | Japanese               | Japanese (Japan)              | ja_JP        |
    | Chinese (Simplified)   | Simplified Chinese (Mainland) | zh_CN        |
    | Spanish                | Spanish (Spain)               | es_ES        |
    | Italian                | Italian (Italy)               | it_IT        |
    | Polish                 | Polish (Poland)               | pl_PL        |
    | Portuguese (Brazilian) | Portuguese (Brazil)           | pt_BR        |
    | Thai                   | Thai (Thailand)               | th_TH        |
    | Ukrainian              | Ukrainian (Ukraine)           | uk_UA        |
    +------------------------+-------------------------------+--------------+

    Notes:
    - These are ICU-compliant locales and match CLDR standards.
    - Use `Locale("ko_KR")` for Korean, not just `"ko"`.
    """
    max_len = 500

    if len(text) <= max_len:
        return [text], 1

    protected_text = preserve_escaped_sequences(text)

    chunks = []
    start = 0

    while start < len(protected_text):
        end = choose_po_split_position(protected_text, start, max_len, locale)

        chunk = protected_text[start:end]

        chunk = re.sub(r"^ ", "<<LS>>", chunk)
        chunk = re.sub(r" $", "<<TS>>", chunk)

        chunk = restore_escaped_sequences(chunk)

        chunks.append(chunk)
        start = end

    return chunks, len(chunks)


@mainFunction
def create_po_from_esoui(translated_input_file, english_input_file, isBaseEnglish=False):
    """
    Converts ESO .str files into a .po file, splitting long entries with sentence boundaries
    and preserving leading/trailing space via <<LS>> and <<TS>> tags.

    Args:
        translated_input_file (str): Path to the translated .str file.
        english_input_file (str): Path to the English .str file.
        isBaseEnglish (bool): If True, produces a base .po with empty msgstr fields.
    """
    po = polib.POFile()
    po.metadata = get_crowdin_po_metadata(translated_input_file)
    output_filename, _ = generate_output_filename(translated_input_file, "esoui_client_strings", file_extension="po")
    locale_translated = get_icu_locale_from_filename(translated_input_file)
    locale_english = get_icu_locale_from_filename(english_input_file)
    english_map = {}
    translated_map = {}

    with open(english_input_file, 'r', encoding='utf-8') as f_en:
        for line in f_en:
            if reFontTag.match(line):
                continue
            m = reClientUntaged.match(line)
            if m:
                k, v = m.group(1), m.group(2)
                english_map[k] = v

    with open(translated_input_file, 'r', encoding='utf-8') as f_tr:
        for line in f_tr:
            if reFontTag.match(line):
                continue
            m = reClientUntaged.match(line)
            if m:
                k, v = m.group(1), m.group(2)
                translated_map[k] = v

    keys = sorted(english_map.keys())
    for key in keys:
        msgid_full = english_map.get(key, "")
        msgstr_full = "" if isBaseEnglish else translated_map.get(key, "")

        msgid_chunks, msgid_chunk_count = split_if_long(msgid_full, locale=locale_english)
        msgstr_chunks, msgstr_chunk_count = split_if_long(msgstr_full, locale=locale_translated)

        if msgstr_chunk_count < msgid_chunk_count:
            msgstr_chunks += [""] * (msgid_chunk_count - msgstr_chunk_count)
        elif msgstr_chunk_count > msgid_chunk_count:
            msgid_chunks += [""] * (msgstr_chunk_count - msgid_chunk_count)
            msgid_chunk_count = msgstr_chunk_count

        if msgid_chunk_count == 1:
            entry = polib.POEntry(
                msgctxt=key,
                msgid=msgid_chunks[0],
                msgstr=msgstr_chunks[0]
            )
            po.append(entry)
        else:
            for i, (msgid, msgstr) in enumerate(zip(msgid_chunks, msgstr_chunks), start=1):
                chunked_key = f"{key}:{i},{msgid_chunk_count}"
                entry = polib.POEntry(
                    msgctxt=chunked_key,
                    msgid=msgid,
                    msgstr=msgstr
                )
                po.append(entry)

    po.save(output_filename)
    print(f"Done. Created .po file: {output_filename}")


@mainFunction
def create_po_from_tagged_lang_text(translated_input_file, english_input_file, isBaseEnglish=False):
    """
    Converts two tagged ESO lang files ({{key:}}Text format) into a .po file,
    using ICU sentence-aware chunking when text exceeds 500 characters.

    Args:
        translated_txt (str): Translated tagged file (e.g., kr_tagged_kr.txt).
        english_txt (str): English tagged file (e.g., en_tagged.txt).
    """
    po = polib.POFile()
    po.metadata = get_crowdin_po_metadata(translated_input_file)
    output_po, _ = generate_output_filename(translated_input_file, file_extension="po")
    locale_translated = get_icu_locale_from_filename(translated_input_file)
    locale_english = get_icu_locale_from_filename(english_input_file)
    english_map = {}
    translated_map = {}

    with open(english_input_file, 'r', encoding='utf-8') as f_en:
        for line in f_en:
            m = reLangIndex.match(line.strip())
            if m:
                key, text = m.group(1), m.group(2)
                english_map[key] = text

    with open(translated_input_file, 'r', encoding='utf-8') as f_trans:
        for line in f_trans:
            m = reLangIndex.match(line.strip())
            if m:
                key, text = m.group(1), m.group(2)
                translated_map[key] = text

    for key in sorted(english_map):
        msgid_full = english_map.get(key, "")
        msgstr_full = "" if isBaseEnglish else translated_map.get(key, "")

        msgid_chunks, msgid_chunk_count = split_if_long(msgid_full, locale=locale_english)
        msgstr_chunks, msgstr_chunk_count = split_if_long(msgstr_full, locale=locale_translated)

        # Pad shorter list with empty strings
        if msgstr_chunk_count < msgid_chunk_count:
            msgstr_chunks += [""] * (msgid_chunk_count - msgstr_chunk_count)
        elif msgstr_chunk_count > msgid_chunk_count:
            msgid_chunks += [""] * (msgstr_chunk_count - msgid_chunk_count)
            msgid_chunk_count = msgstr_chunk_count

        if msgid_chunk_count == 1:
            entry = polib.POEntry(
                msgctxt=f"{{{{{key}:}}}}",
                msgid=msgid_chunks[0],
                msgstr=msgstr_chunks[0]
            )
            po.append(entry)
        else:
            for i, (msgid, msgstr) in enumerate(zip(msgid_chunks, msgstr_chunks), start=1):
                chunked_key = f"{{{{{key}:{i},{msgid_chunk_count}}}}}"
                entry = polib.POEntry(
                    msgctxt=chunked_key,
                    msgid=msgid,
                    msgstr=msgstr
                )
                po.append(entry)

    po.save(output_po)
    print(f"PO output written to: {output_po}")


def cleanText(line):
    if line is None:
        return None

    # Strip weird dots … or other chars
    line = line.replace('…', '').replace('—', '').replace('â€¦', '').replace('â€”', '').replace('•', '')

    # Remove black/hidden text color blocks entirely
    reColorTagError = re.compile(r'\|c000000(.*?)\|r')
    line = reColorTagError.sub('', line)

    return line


@mainFunction
def merge_section_into_lang(main_lang_file, source_lang_file):
    """
    Import a translated section into a full language file by matching tagged keys.

    This function reads:
      - A **translated section** file, typically created using `extractSectionEntries()`, which contains a subset
        of translated entries in the format `{{sectionId-sectionIndex-stringIndex:}}TranslatedText`
      - A **full language file** that contains the complete set of entries for a language (typically untranslated).

    It then replaces any matching entries in the full language file with the corresponding translated entries,
    based on exact key matches. Only entries with a valid tag will be considered.

    The output is written to a file named with `merged_lang_section` appended to the original filename.

    Args:
        main_lang_file (str): The full language file to update, e.g. `en.lang_tag.txt`, containing all entries.
        source_lang_file (str): The translated section file, e.g. `lorebooks_uk.txt`, containing tagged entries.

    Notes:
        - Both input files must use the format: `{{211640654-0-5066:}}Some text`
        - Only keys in the main file are written; any extra keys in the source file are ignored.
        - Unmatched keys are preserved as-is.
    """
    output_filename, _ = generate_output_filename(main_lang_file, "merged_lang_section")

    main_dict = readTaggedLangFile(main_lang_file)
    source_dict = readTaggedLangFile(source_lang_file)

    # Overwrite main_dict values with those in source_dict if key matches
    for key in source_dict:
        if key in main_dict:
            main_dict[key] = source_dict[key]

    # Write merged output
    with open(output_filename, 'w', encoding="utf8", newline='\n') as out:
        for key, value in main_dict.items():
            out.write(f"{{{{{key}:}}}}{value}\n")

    print(f"Merged translations from {source_lang_file} into {main_lang_file} → {output_filename}")


@mainFunction
def merge_esoui_client_files(main_client_file, source_client_file):
    """
    Merge translations from a source ESOUI-format file into a main client file.

    This function reads:
      - A **main_client_file**: the ESOUI client file to update (e.g. `ko_client.str` or `ko_client.lua`).
      - A **source_client_file**: a file containing translations (e.g. generated from XLIFF).

    Any matching keys found in both files will have the **value in the main file replaced with the value from the source file**.

    Args:
        main_client_file (str): The target ESOUI-format client file to merge into (e.g. `ko_client.str`).
        source_client_file (str): The ESOUI-format file providing updated translations.

    Output:
        A merged `.txt` file (e.g., `ko_client_merged_esoui.txt`) with updated strings.

    Notes:
        - This assumes both files are valid ESOUI-format client files.
        - Only keys that already exist in the main client file will be updated.
    """
    output_filename, _ = generate_output_filename(main_client_file, "merged_esoui")

    # Parse both files into dictionaries
    main_map = process_eosui_client_file(main_client_file)
    source_map = process_eosui_client_file(source_client_file)

    # Merge source entries into main
    for key in main_map:
        if key in source_map:
            main_map[key] = source_map[key]

    # Write output
    with open(output_filename, "w", encoding="utf-8", newline='\n') as out:
        for key in sorted(main_map.keys()):
            lineOut = f"[{key}] = \"{main_map[key]}\""
            out.write(f"{lineOut}\n")

    print(f"Merged ESOUI entries from {source_client_file} into {main_client_file} → {output_filename}")


@mainFunction
def distribute_esoui_to_source_files(combined_client_file, source_client_file, source_pregame_file):
    """
    Distribute strings from a merged combined ESOUI-format language file back into the original
    client and pregame files.

    This function:
      - Reads a combined .str file (client + pregame merged)
      - Reads the original client and pregame .str files
      - Updates each original file's keys with values from the combined file
      - Writes the updated client and pregame files as new .str files (for comparison)

    Args:
        combined_client_file (str): Combined ESOUI-format language file (merged client + pregame).
        source_client_file (str): Original client .str file (base template).
        source_pregame_file (str): Original pregame .str file (base template).

    Output:
        Two updated .str files:
          - `<source_client_file>_merged_split_esoui.str`
          - `<source_pregame_file>_merged_split_esoui.str`
    """
    # Output filenames
    output_client_filename, _ = generate_output_filename(source_client_file, "merged_split_esoui", file_extension="str")
    output_pregame_filename, _ = generate_output_filename(source_pregame_file, "merged_split_esoui", file_extension="str")

    # Parse all input files into dictionaries
    combined_map = process_eosui_client_file(combined_client_file)
    client_map = process_eosui_client_file(source_client_file)
    pregame_map = process_eosui_client_file(source_pregame_file)

    # Update client and pregame maps with values from combined file
    for key in client_map:
        if key in combined_map:
            client_map[key] = combined_map[key]

    for key in pregame_map:
        if key in combined_map:
            pregame_map[key] = combined_map[key]

    # Write updated client file
    with open(output_client_filename, "w", encoding="utf-8", newline='\n') as out:
        for key in sorted(client_map.keys()):
            out.write(f"[{key}] = \"{client_map[key]}\"\n")

    # Write updated pregame file
    with open(output_pregame_filename, "w", encoding="utf-8", newline='\n') as out:
        for key in sorted(pregame_map.keys()):
            out.write(f"[{key}] = \"{pregame_map[key]}\"\n")

    print(f"Updated client file written: {output_client_filename}")
    print(f"Updated pregame file written: {output_pregame_filename}")


@mainFunction
def compare_tagged_lang_files_for_translation(translated_tagged_text, previous_tagged_english_text, current_tagged_english_text):
    """
    Compare translations between different versions of tagged language files.

    This function compares translated tagged text against previous/live English tagged text and current/PTS
    English tagged text to determine whether existing translations can still be reused. It writes the merged
    comparison output to a filename generated from translated_tagged_text with the compared_lang_files suffix,
    and writes the verification output to a generated filename with the compared_lang_verify suffix.

    Args:
        translated_tagged_text (str): The filename of the translated language file (e.g., ko.lang.txt).
        previous_tagged_english_text (str): The filename of the previous/live English language file with tags (e.g., en_prv.lang_tag.txt).
        current_tagged_english_text (str): The filename of the current/PTS English language file with tags (e.g., en_cur.lang_tag.txt).

    Notes:
        - translated_tagged_text should be the translated language file, usually for another language.
        - previous_tagged_english_text should be the previous/live English language file with tags.
        - current_tagged_english_text should be the current/PTS English language file with tags.

    The function performs the following steps:
    - Reads the translations from the specified files into dictionaries.
    - Cleans and preprocesses the texts by removing unnecessary characters and color tags.
    - Compares the PTS and live texts to determine if translation changes are needed.
    - Writes generated comparison and verification output files.
    """
    # Generate a dynamic output filename from the translated string file
    output_filename, _ = generate_output_filename(translated_tagged_text, "compared_lang_files")
    output_verify_filename, _ = generate_output_filename(translated_tagged_text, "compared_lang_verify")

    # Get Previous Translation ------------------------------------------------------
    textTranslatedDict = readTaggedLangFile(translated_tagged_text)
    print("Processed Translated Text")
    # Get Current/PTS English Text ------------------------------------------------------
    textCurrentUntranslatedDict = readTaggedLangFile(current_tagged_english_text)
    print("Processed Current Text")
    # Get Previous/Live English Text ------------------------------------------------------
    textPreviousUntranslatedDict = readTaggedLangFile(previous_tagged_english_text)
    print("Processed Previous Text")

    added_english_fallback = 0
    needs_review = 0
    removed_obsolete = 0
    for key in textPreviousUntranslatedDict:
        if key not in textCurrentUntranslatedDict:
            removed_obsolete += 1

    # Compare PTS with Live text, write output -----------------------------------------
    print("Begining Comparison")
    with open(output_filename, 'w', encoding="utf8", newline='\n') as out:
        with open(output_verify_filename, 'w', encoding="utf8", newline='\n') as verifyOut:
            for key in textCurrentUntranslatedDict:
                # Retrieve source and translated text entries by ID
                translatedText = textTranslatedDict.get(key)
                current_text = textCurrentUntranslatedDict.get(key)
                previous_text = textPreviousUntranslatedDict.get(key)

                # Clean tags and formatting from text strings
                current_texture_path = None
                translated_texture_path = None
                if current_text is not None:
                    current_texture_path = reEsoTexturePath.search(current_text)
                if translatedText is not None:
                    translated_texture_path = reEsoTexturePath.search(translatedText)

                if current_texture_path and translated_texture_path:
                    current_texture_path = current_texture_path.group(1)
                    translated_texture_path = translated_texture_path.group(1)

                    if current_texture_path != translated_texture_path:
                        translatedText = translatedText.replace(
                            translated_texture_path,
                            current_texture_path
                        )

                # Clean tags and formatting from text strings
                translatedTextStripped = cleanText(translatedText)
                current_textStripped = cleanText(current_text)
                previous_textStripped = cleanText(previous_text)

                # Initialize default output to current_text text
                lineOut = current_text

                textsAreIdentical = False
                textsAreSimilar = False
                textIsFallbackEnglishText = False
                translatedLooksTranslated = False
                useTranslatedText = False
                writeOutput = False  # Flag to determine whether to log to verify_output.txt

                if current_textStripped is not None and previous_textStripped is not None:
                    textsAreIdentical = isIdenticalText(current_textStripped, previous_textStripped)
                    textsAreSimilar = isSimilarText(current_textStripped, previous_textStripped)

                    if translatedTextStripped is not None:
                        textIsFallbackEnglishText = isFallbackEnglish(translatedText, current_textStripped, previous_textStripped)
                        translatedLooksTranslated = isTranslatedText(translatedTextStripped) or not textIsFallbackEnglishText

                    if textsAreIdentical or textsAreSimilar:
                        if translatedLooksTranslated:
                            useTranslatedText = True
                    else:
                        writeOutput = True

                if useTranslatedText:
                    lineOut = translatedText

                lineOut = lineOut.rstrip()
                lineOut = f"{{{{{key}:}}}}{lineOut}"

                if translatedText is None:
                    added_english_fallback += 1

                if writeOutput:
                    if translatedText is not None:
                        needs_review += 1
                        verifyOut.write(f"T{{{{{key}:}}}}{translatedText.rstrip()}\n")
                        verifyOut.write(f"L{{{{{key}:}}}}{current_text.rstrip()}\n")
                        verifyOut.write(f"P{{{{{key}:}}}}{previous_text.rstrip()}\n")
                        verifyOut.write(f"{{{textsAreSimilar}}}:{{{lineOut}}}\n")

                out.write(f"{lineOut}\n")

            verifyOut.write("--------------------\n")
            verifyOut.write("Statistics\n")
            verifyOut.write("--------------------\n")
            verifyOut.write(f"Added English fallback lines: {added_english_fallback}\n")
            verifyOut.write(f"Removed obsolete lines: {removed_obsolete}\n")
            verifyOut.write(f"Needs review: {needs_review}\n")

    print(f"Added English fallback lines: {added_english_fallback}")
    print(f"Removed obsolete lines: {removed_obsolete}")
    print(f"Needs review: {needs_review}")
    print(f"Done. Output written to {output_filename}")
    print(f"Done. Output for verification written to {output_verify_filename}")


@mainFunction
def compare_esoui_files_for_translation(translated_string_file, previous_english_string_file, current_english_string_file):
    """
    Compare ESOUI text files with existing translations.

    This function reads three input ESOUI text files: translated_string_file, previous_english_string_file,
    and current_english_string_file, then compares the live and PTS text files to determine whether existing
    translations can still be used. The result is written to a filename generated from translated_string_file
    with the compared_esoui_files suffix.

    Args:
        translated_string_file (str): The filename of the translated ESOUI text file (e.g., ko_client.str or ko_pregame.str).
        previous_english_string_file (str): The filename of the live ESOUI text file (e.g., en_client.str or en_pregame.str).
        current_english_string_file (str): The filename of the PTS ESOUI text file (e.g., en_client.str or en_pregame.str).

    Note:
        This function uses reLangIndex to identify language constant entries and their associated text.
    """

    # Generate a dynamic output filename from the translated string file
    output_filename, _ = generate_output_filename(translated_string_file, "compared_esoui_files")

    # Read translated text ----------------------------------------------------
    textTranslatedDict = process_eosui_client_file(translated_string_file)
    # Read pts text ----------------------------------------------------
    textCurrentUntranslatedDict = process_eosui_client_file(current_english_string_file)
    # Read live text ----------------------------------------------------
    textPreviousUntranslatedDict = process_eosui_client_file(previous_english_string_file)
    # --Write Output ------------------------------------------------------
    with open(output_filename, 'w', encoding="utf8", newline='\n') as out:
        for key in textCurrentUntranslatedDict:
            translatedText = textTranslatedDict.get(key)
            current_text = textCurrentUntranslatedDict.get(key)
            previous_text = textPreviousUntranslatedDict.get(key)

            if key in SPECIAL_LANGUAGE_NAMES:
                translatedText = SPECIAL_LANGUAGE_NAMES[key]

            # Clean tags and formatting from text strings
            current_texture_path = None
            translated_texture_path = None
            if current_text is not None:
                current_texture_path = reEsoTexturePath.search(current_text)
            if translatedText is not None:
                translated_texture_path = reEsoTexturePath.search(translatedText)

            if current_texture_path and translated_texture_path:
                current_texture_path = current_texture_path.group(1)
                translated_texture_path = translated_texture_path.group(1)

                if current_texture_path != translated_texture_path:
                    translatedText = translatedText.replace(
                        translated_texture_path,
                        current_texture_path
                    )

            # Comment
            maEmptyString = reEmptyString.match(current_text)
            if maEmptyString:
                conIndex = maEmptyString.group(1)
                out.write(f'[{conIndex}] = ""\n')
                continue

            lineOut = current_text
            useTranslatedText = False

            if current_text is not None and previous_text is not None:
                textsAreIdentical = isIdenticalText(current_text, previous_text)
                textsAreSimilar = isSimilarText(current_text, previous_text)
                textIsFallbackEnglishText = isFallbackEnglish(translatedText, current_text, previous_text)

                if not textIsFallbackEnglishText:
                    if textsAreIdentical or textsAreSimilar:
                        if translatedText is not None and isTranslatedText(translatedText):
                            useTranslatedText = True

            if useTranslatedText:
                lineOut = translatedText

            escaped = preserve_escaped_sequences(lineOut)
            formatted = f'[{key}] = "{escaped}"\n'
            restored = restore_escaped_sequences(formatted)
            out.write(restored)

    print(f"Done. Output written to {output_filename}")


@mainFunction
def create_tagged_lang_text(input_lang_file):
    """
    Reads a .lang file and outputs:
    1. A tagged text file in the format {{sectionId-sectionIndex-stringIndex:}}text
    2. A parallel .txt file containing just the IDs (sectionId-sectionIndex-stringIndex), line-for-line aligned.

    Args:
        input_lang_file (str): Path to a .lang file like en.lang, ko.lang, etc.

    Output:
        <prefix>_tagged_<suffix>.txt — tagged entries
        <prefix>_ids_only_<suffix>.txt — IDs only (for rebuild support)
    """
    currentFileIndexes, currentFileStrings = readLangFile(input_lang_file)

    output_filename, _ = generate_output_filename(input_lang_file, "tagged_lang_text")
    id_output_filename, _ = generate_output_filename(input_lang_file, "tagged_lang_ids")

    with open(output_filename, 'w', encoding="utf-8", newline='\n') as out_tagged, \
            open(id_output_filename, 'w', encoding="utf-8", newline='\n') as out_ids:

        for index in range(currentFileIndexes["numIndexes"]):
            entry = currentFileIndexes[index]
            text = entry.get("string")
            if text:
                section_id = entry['sectionId']
                section_index = entry['sectionIndex']
                string_index = entry['stringIndex']
                entry_id = f"{section_id}-{section_index}-{string_index}"

                preserved_nbsp = preserve_nbsp_bytes(text)
                escaped = preserve_escaped_sequences_bytes(preserved_nbsp)
                decoded = escaped.decode("utf-8", errors="replace").rstrip()
                formatted = f"{{{{{entry_id}:}}}}{decoded}"
                lineOut = restore_escaped_sequences(formatted)

                out_tagged.write(f"{lineOut}\n")
                out_ids.write(f"{entry_id}\n")

    print(f"Tagged language text written to: {output_filename}")
    print(f"Corresponding ID list written to: {id_output_filename}")


def read_tagged_text_to_dict(tagged_text_file):
    """
    Parses a tagged .txt file (e.g. {{sectionId-sectionIndex-stringId:}}text) into
    dictionaries.

    Args:
        tagged_text_file (str): Path to the tagged language text file.

    Returns:
        fileIndexes (dict), fileStrings (dict): Mapped data from tagged input.
    """
    numSections = 0
    numIndexes = 0
    predictedOffset = 0
    stringCount = 0
    fileIndexes = {'numIndexes': numIndexes, 'numSections': numSections}
    fileStrings = {'stringCount': stringCount}
    index = 0

    with open(tagged_text_file, 'r', encoding='utf-8') as f:
        for line in f:
            match = reLangTagged.match(line)
            if not match:
                continue  # skip invalid lines

            sectionId = int(match.group(1))
            sectionIndex = int(match.group(2))
            stringIndex = int(match.group(3))
            stringText = match.group(4).rstrip()
            escaped = preserve_escaped_sequences(stringText)
            encoded = escaped.encode("utf-8")
            stringText = restore_escaped_sequences_bytes(encoded)

            fileIndexes[index] = {
                'sectionId': sectionId,
                'sectionIndex': sectionIndex,
                'stringIndex': stringIndex,
                'stringOffset': predictedOffset,
                'string': stringText,
            }

            # Ensure each string is stored once in fileStrings
            if stringText not in fileStrings:
                fileStrings[stringText] = {
                    'stringOffset': predictedOffset,
                }
                fileStrings[stringCount] = {
                    'string': stringText,
                }
                # add one to stringCount
                stringCount += 1
                # 1 extra for the null terminator
                string_length_str = stringText
                string_length_str = restore_nbsp_bytes(string_length_str)
                predictedOffset += (len(string_length_str) + 1)

            index += 1

    fileIndexes["numIndexes"] = index
    fileIndexes["numSections"] = 2  # can be updated if needed
    fileStrings["stringCount"] = stringCount

    print(f"String Count: {stringCount}")
    print(f"Number of Indexes: {index}")
    return fileIndexes, fileStrings


@mainFunction
def rebuild_lang_file_from_lang_file(inputLangFile):
    """
    Reads a language file, identifies duplicate strings, and ensures that repeated strings
    share the same offset in the output. This rebuilds the language file so that identical
    strings are stored only once.

    Args:
        inputLangFile (str): The name of the input .lang file (e.g. 'en.lang', 'ko.lang').

    Output:
        {prefix}_output_{suffix}.lang: the optimized language file

        For example, if the input is 'en.lang', the output will be 'en_output.lang'.
    """
    output_filename, _ = generate_output_filename(inputLangFile, "rebuilt_lang_file", file_extension="lang")

    currentFileIndexes, currentFileStrings = readLangFile(inputLangFile)
    print(currentFileStrings['stringCount'])
    writeLangFile(output_filename, currentFileIndexes, currentFileStrings)

    print("Optimized file written to: {}".format(output_filename))


@mainFunction
def rebuild_lang_file_from_tagged_text(input_tagged_file):
    """
    Reads a tagged language text file and rebuilds a .lang file using the
    identifiers stored in each tag.

    Args:
        input_tagged_file (str): The name of the tagged language text file
            (e.g. 'en_tagged_lang_text.txt', 'ko_tagged_lang_text.txt').

    Output:
        {prefix}_rebuilt_tagged_lang_file.lang: the rebuilt language file

        For example, if the input is 'en_tagged_lang_text.txt', the output
        will be 'en_rebuilt_tagged_lang_file.lang'.
    """
    output_filename, _ = generate_output_filename(input_tagged_file, "rebuilt_tagged_lang_file", file_extension="lang")

    currentFileIndexes, currentFileStrings = read_tagged_text_to_dict(input_tagged_file)
    print(f"String Count: {currentFileStrings['stringCount']}")
    writeLangFile(output_filename, currentFileIndexes, currentFileStrings)

    print(f"Optimized file written to: {output_filename}")


@mainFunction
def convert_xliff_to_tagged_lang_text(input_xliff_file):
    """
    Parses a Crowdin XLIFF 1.2 file and writes ESO-tagged lines for entries with numeric keys
    from <context context-type="source"> and target state 'translated' or 'final'.

    Args:
        input_xliff_file (str): Path to the input .xliff file.
    """
    output_filename, _ = generate_output_filename(input_xliff_file, "xliff_file")
    context = ET.iterparse(input_xliff_file, events=("start", "end"))
    _, root = next(context)  # get root element

    current_key = None
    current_state = None
    current_text = None
    output_lines = []

    for event, elem in context:
        if event == "start":
            if elem.tag.endswith("target"):
                current_state = elem.attrib.get("state")

        elif event == "end":
            if elem.tag.endswith("context") and elem.attrib.get("context-type") == "source":
                # Get key from <context>
                current_key = clean_tagged_lang_key(elem.text.strip())

            elif elem.tag.endswith("target"):
                current_text = (elem.text or "").strip()

            elif elem.tag.endswith("trans-unit"):
                # Only process if the key is numeric and state is valid
                if current_key and current_state in ("translated", "final"):
                    output_line = f"{current_key}{current_text}"
                    output_lines.append(output_line)

                # Reset for next unit
                current_key = None
                current_state = None
                current_text = None
                elem.clear()
                root.clear()

    # Write output
    with open(output_filename, "w", encoding="utf-8", newline='\n') as out_file:
        for line in output_lines:
            out_file.write(f"{line}\n")

    print(f"Parsed XLIFF written to: {output_filename}")


@mainFunction
def convert_tagged_lang_text_to_xliff(original_xliff_file, tagged_text_file):
    """
    Updates the <target> values in the original XLIFF with translations from a tagged text file.
    Forces &quot; in <source> and <target> elements when writing.
    """
    # 1. Read tagged text into dict
    translations = {}
    with open(tagged_text_file, "r", encoding="utf-8") as f:
        for line in f:
            match = reResNameId.match(line)
            if match:
                sectionId, sectionIndex, stringIndex = match.groups()
                key = f"{sectionId}-{sectionIndex}-{stringIndex}"
                text = re.sub(r"^\{\{.*?:\}\}", "", line).strip()
                translations[key] = text

    # 2. Parse original XLIFF using ET
    tree = ET.parse(original_xliff_file)
    root = tree.getroot()

    # 3. Update <source> and <target> elements, enforcing &quot;
    for trans_unit in root.iterfind(".//{*}trans-unit"):
        resname = trans_unit.get("resname")

        # Handle <source>
        source_elem = trans_unit.find("{*}source")
        if source_elem is not None and source_elem.text:
            source_elem.text = source_elem.text.replace('"', '&quot;')

        # Handle <target>
        target = trans_unit.find("{*}target")
        if resname and resname in translations:
            if target is None:
                target = ET.SubElement(trans_unit, "target")

            # Apply translation and enforce &quot;
            text_to_write = translations[resname].replace('"', '&quot;')
            target.text = text_to_write
            target.set("state", "translated")
        elif target is not None and target.text:
            # Keep existing target but enforce &quot;
            target.text = target.text.replace('"', '&quot;')

    # 4. Register namespace if needed
    if root.tag.startswith("{"):
        namespace_uri = root.tag[1:].split("}")[0]
        if namespace_uri:
            ET.register_namespace('', namespace_uri)

    # 5. Write updated XLIFF using ET
    output_filename, _ = generate_output_filename(
        original_xliff_file, "updated_xliff", file_extension="xliff"
    )
    tree.write(output_filename, encoding="utf-8", xml_declaration=True)

    # 6. Post-process to fix double-escaped &quot; in <source> and <target>
    with open(output_filename, "r", encoding="utf-8") as f:
        lines = f.readlines()

    with open(output_filename, "w", encoding="utf-8", newline='\n') as f:
        for line in lines:
            if "<source>" in line or "<target" in line:
                line = line.replace('&amp;quot;', '&quot;')
            f.write(line)

    print(f"Updated XLIFF created: {output_filename}")


@mainFunction
def convert_xliff_to_esoui(xliff_path):
    """
    Converts Crowdin XLIFF 1.2 into ESOUI-formatted file.

    Includes *all* entries, regardless of <target> state, so it rebuilds a
    binary-equal ESOUI file.
    """
    output_filename, _ = generate_output_filename(xliff_path, "xliff_to_esoui", file_extension="txt")

    context = ET.iterparse(xliff_path, events=("start", "end"))
    _, root = next(context)

    current_key = None
    current_text = None
    output_lines = []

    for event, elem in context:
        if event == "end":
            if elem.tag.endswith("context") and elem.attrib.get("context-type") == "source":
                # Extract and clean the key from context-type="source"
                current_key = clean_esoui_key((elem.text or "").strip())

            elif elem.tag.endswith("target"):
                current_text = elem.text

            elif elem.tag.endswith("trans-unit"):
                if current_key and current_text is None:
                    line = f"[{current_key}] = \"\""
                    output_lines.append(line)

                if current_key and current_text is not None:
                    line = f"[{current_key}] = \"{current_text}\""
                    output_lines.append(line)

                # Reset for next trans-unit
                current_key = None
                current_text = None
                elem.clear()
                root.clear()

    # Write the ESOUI output file
    with open(output_filename, "w", encoding="utf-8", newline='\n') as out_file:
        for line in output_lines:
            lineOut = line.rstrip('\n')
            out_file.write(f"{lineOut}\n")

    print(f"ESOUI file written to: {output_filename}")


@mainFunction
def convert_esoui_to_xliff(original_xliff_file, esoui_file):
    """
    Updates original XLIFF <target> with translations from ESOUI-formatted file.

    ESOUI format uses: [KEY] = "Text"
    XLIFF resname uses: KEY (without brackets)
    """
    # 1. Read ESOUI file into dict
    translations = process_eosui_client_file(esoui_file)

    # 2. Parse original XLIFF
    tree = ET.parse(original_xliff_file)
    root = tree.getroot()

    # 3. Update matching <target> elements
    for trans_unit in root.iterfind(".//{*}trans-unit"):
        # Find the key from <context context-type="source">
        context_elem = trans_unit.find(".//{*}context[@context-type='source']")
        if context_elem is not None:
            esoui_key = clean_esoui_key(context_elem.text.strip())

            # Find <target> and read its text
            target = trans_unit.find("{*}target")

            # current_text will be None if <target></target> is empty
            current_text = target.text if target is not None else None

            # Case 1: target is completely empty (like <target></target>)
            if current_text is None:
                # Do nothing, just rebuild this block exactly as it is
                continue

            # Case 2: target is not None, we can decide if it needs updating
            if esoui_key in translations:
                new_text = translations[esoui_key]

                # Always prepare the text for XML
                text_to_write = new_text

                if current_text != new_text:
                    # Update <target> only if different
                    target.text = text_to_write
                    target.set("state", "translated")

    # 4. Get the namespace from the root tag dynamically
    if root.tag.startswith("{"):
        namespace_uri = root.tag[1:].split("}")[0]
        ET.register_namespace('', namespace_uri)

    # 5. Write updated XLIFF with detected namespace
    output_filename, _ = generate_output_filename(esoui_file, "esoui_converted_xliff", file_extension="xliff")
    tree.write(output_filename, encoding="utf-8", newline='\n', xml_declaration=True, short_empty_elements=False)

    # Post-process to replace \" with \&quot; in <source> and <target> lines
    with open(output_filename, "r", encoding="utf-8") as f:
        lines = f.readlines()

    with open(output_filename, "w", encoding="utf-8", newline='\n') as f:
        for line in lines:
            if "<source>" in line or "<target" in line:
                line = line.replace('\\"', '\\&quot;')
            f.write(line)

    print(f"Updated XLIFF created: {output_filename}")


def isTokenOnlyText(text):
    if not text:
        return True

    temp = reColorTag.sub("", text)

    # Remove texture tags
    temp = re.sub(r"\|t\d+:\d+:[^|]+\|t", "", temp)

    # Remove simple ESO tokens
    temp = re.sub(r"<<[A-Za-z]?:?\d+>>", "", temp)

    # Remove whitespace
    temp = temp.strip()

    # If anything resembling a letter or number remains,
    # then it is not token-only.
    return not bool(re.search(r"[A-Za-z0-9]", temp))


@mainFunction
def extract_english_esoui_lines(input_file):
    """
    Extract ESOUI .str entries whose text still appears to be English.

    Reads lines in [KEY] = "text" format, skips empty strings, known language-name
    strings, and token-only strings, then writes matching entries back in ESOUI
    format for translation review.
    """
    output_filename, _ = generate_output_filename(input_file, "esoui_english_only")

    with open(input_file, "r", encoding="utf8") as textIns, \
            open(output_filename, "w", encoding="utf8", newline="\n") as out:

        for line in textIns:
            line = line.rstrip()

            maEmptyString = reEmptyString.match(line)
            if maEmptyString:
                continue

            maClientUntaged = reClientUntaged.match(line)
            if not maClientUntaged:
                continue

            key = maClientUntaged.group(1)
            text = maClientUntaged.group(2) or ""

            if key in SPECIAL_LANGUAGE_NAMES:
                continue

            if isTokenOnlyText(text):
                continue

            text = cleanText(text)
            if not isTranslatedText(text):
                out.write(f'[{key}] = "{text}"\n')

    print(f"English-looking ESOUI lines written to: {output_filename}")


@mainFunction
def extract_english_tagged_lang_lines(input_file):
    """
    Extract tagged .lang text entries whose text still appears to be English.

    Reads tagged lines in {{sectionId-sectionIndex-stringId:}}text format, skips
    empty and token-only strings, then writes matching entries back in tagged
    .lang text format for translation review.
    """
    output_filename, _ = generate_output_filename(input_file, "tagged_lang_english_only")

    tagged_lines = readTaggedLangFile(input_file)

    with open(output_filename, "w", encoding="utf8", newline="\n") as out:
        for key, text in tagged_lines.items():
            text = text or ""

            if isTokenOnlyText(text):
                continue

            text = cleanText(text)
            if not isTranslatedText(text):
                out.write(f'{{{{{key}:}}}}{text}\n')

    print(f"English-looking tagged lang lines written to: {output_filename}")


@mainFunction
def diff_tagged_lang_files(official_or_current_tagged_lang_file, candidate_or_previous_tagged_lang_file, source_tagged_lang_file=None):
    """
    Compare differences between two tagged language files.

    This function compares an official/current tagged language file against a
    candidate/previous tagged language file. It supports English vs English,
    Korean vs Korean, and mixed English/Korean comparisons.

    Args:
        official_or_current_tagged_lang_file (str): Tagged official/current language file.
        candidate_or_previous_tagged_lang_file (str): Tagged candidate/previous language file.
        source_tagged_lang_file (str, optional): Tagged source language file used for review context.

    Behavior:
        - Reads both files into dictionaries using `readTaggedLangFile()`.
        - Optionally reads a source tagged language file for review context.
        - Compares entries using exact match and similarity threshold logic.
        - Categorizes results into:
            - Identical entries, counted in the report only
            - Close (similar) entries
            - Changed entries
            - Newly added entries
            - Deleted entries
            - Translation candidates
            - Current already translated entries

    Output:
        Uses `generate_output_filename()` to create output filenames based on the input file.
        Filenames follow the pattern:
            <lang_prefix>_<base>_<category>.txt
        where:
            - <lang_prefix> is derived from the input filename (e.g., 'en_cur')
            - <base> is the base tag like 'lang', 'pregame', etc.
            - <category> includes:
                - diff_tagged_lang_files_report.txt
                - close_match_current_indexes.txt
                - close_match_previous_indexes.txt
                - changed_indexes.txt
                - deleted_indexes.txt
                - added_indexes.txt
                - translation_candidates.txt
                - current_already_translated.txt

    Notes:
        - Input files must use the tagged format: {{section-index-string:}}Text
        - Translation candidates are candidate/previous translated strings where
          official/current is not translated.
        - translation_candidates.txt is written as normal tagged-language text:
          {{key:}}Translated Text
        - If source_tagged_lang_file is provided, source text is added to changed indexes
          and current already translated entries for review context.
    """

    def write_output_file(filename, targetList):
        with open(filename, 'w', encoding="utf8") as out:
            for line in targetList:
                out.write(line)

    def write_tagged_output_file(filename, targetList):
        with open(filename, 'w', encoding="utf8") as out:
            for line in targetList:
                out.write(line)

    # Get Official/Current Text ----------------------------------------------------------
    textCurrentUntranslatedDict = readTaggedLangFile(official_or_current_tagged_lang_file)
    # Get Candidate/Previous Text --------------------------------------------------------
    textPreviousUntranslatedDict = readTaggedLangFile(candidate_or_previous_tagged_lang_file)
    # Get Source Text --------------------------------------------------------
    sourceTextDict = {}
    if source_tagged_lang_file:
        sourceTextDict = readTaggedLangFile(source_tagged_lang_file)

    # Compare official/current with candidate/previous text, write output ----------------
    closeMatchLiveText = []
    closeMatchPtsText = []
    changedText = []
    deletedText = []
    addedText = []
    translationCandidateText = []
    currentAlreadyTranslatedText = []

    addedIndexCount = 0
    matchedCount = 0
    bothTranslatedIdenticalCount = 0
    bothUntranslatedIdenticalCount = 0
    closMatchCount = 0
    changedCount = 0
    deletedCount = 0
    translationCandidateCount = 0
    currentAlreadyTranslatedCount = 0

    for key in textCurrentUntranslatedDict:
        current_text = textCurrentUntranslatedDict.get(key)
        previous_text = textPreviousUntranslatedDict.get(key)
        if previous_text is None:
            addedIndexCount += 1
            lineOut = '{{{{{}:}}}}{}\n'.format(key, current_text)
            addedText.append(lineOut)
            continue

        current_is_translated = isTranslatedText(current_text)
        previous_is_translated = isTranslatedText(previous_text)

        if previous_is_translated and not current_is_translated:
            translationCandidateCount += 1
            lineOut = '{{{{{}:}}}}{}\n'.format(key, previous_text)
            translationCandidateText.append(lineOut)
            continue

        if current_is_translated and not previous_is_translated:
            currentAlreadyTranslatedCount += 1

            lineOut = '{{{{{}:current:}}}}{}\n'.format(key, current_text)

            source_text = sourceTextDict.get(key)
            if source_text:
                lineOut += '{{{{{}:source:}}}}{}\n\n'.format(key, source_text)

            currentAlreadyTranslatedText.append(lineOut)
            continue

        similarity_above_threshold = calculate_similarity_and_threshold(current_text, previous_text)
        if current_text == previous_text:
            matchedCount += 1
            if current_is_translated and previous_is_translated:
                bothTranslatedIdenticalCount += 1
            elif not current_is_translated and not previous_is_translated:
                bothUntranslatedIdenticalCount += 1
        elif similarity_above_threshold:
            closMatchCount += 1
            lineOut = '{{{{{}:}}}}{}\n'.format(key, current_text)
            closeMatchLiveText.append(lineOut)
            lineOut = '{{{{{}:}}}}{}\n'.format(key, previous_text)
            closeMatchPtsText.append(lineOut)
        else:
            changedCount += 1
            lineOut = '{{{{{}:previous:}}}}{}\n{{{{{}:current:}}}}{}\n'.format(key, previous_text, key, current_text)

            source_text = sourceTextDict.get(key)
            if source_text:
                lineOut += '{{{{{}:source:}}}}{}\n'.format(key, source_text)

            lineOut += '\n'
            changedText.append(lineOut)

    for key in textPreviousUntranslatedDict:
        if key not in textCurrentUntranslatedDict:
            deletedCount += 1
            previous_text = textPreviousUntranslatedDict.get(key)
            lineOut = '{{{{{}:}}}}{}\n'.format(key, previous_text)
            deletedText.append(lineOut)

    print('{}: indexes matched'.format(matchedCount))
    print('{}: both translated and identical'.format(bothTranslatedIdenticalCount))
    print('{}: both untranslated and identical'.format(bothUntranslatedIdenticalCount))
    print('{}: indexes added'.format(addedIndexCount))
    print('{}: indexes deleted'.format(deletedCount))
    print('{}: indexes were a close match'.format(closMatchCount))
    print('{}: indexes changed'.format(changedCount))
    print('{}: translation candidates'.format(translationCandidateCount))
    print('{}: current already translated'.format(currentAlreadyTranslatedCount))

    output_filename, _ = generate_output_filename(official_or_current_tagged_lang_file, "diff_tagged_lang_files_report")
    with open(output_filename, 'w', encoding="utf8") as out:
        out.write('{}: indexes matched\n'.format(matchedCount))
        out.write('{}: both translated and identical\n'.format(bothTranslatedIdenticalCount))
        out.write('{}: both untranslated and identical\n'.format(bothUntranslatedIdenticalCount))
        out.write('{}: indexes added\n'.format(addedIndexCount))
        out.write('{}: indexes deleted\n'.format(deletedCount))
        out.write('{}: indexes close match\n'.format(closMatchCount))
        out.write('{}: indexes changed\n'.format(changedCount))
        out.write('{}: translation candidates\n'.format(translationCandidateCount))
        out.write('{}: current already translated\n'.format(currentAlreadyTranslatedCount))

    # Write close match current indexes
    output_filename, _ = generate_output_filename(official_or_current_tagged_lang_file, "close_match_current_indexes")
    write_output_file(output_filename, closeMatchLiveText)
    # Write close match previous indexes
    output_filename, _ = generate_output_filename(official_or_current_tagged_lang_file, "close_match_previous_indexes")
    write_output_file(output_filename, closeMatchPtsText)
    # Write changed indexes
    output_filename, _ = generate_output_filename(official_or_current_tagged_lang_file, "changed_indexes")
    write_output_file(output_filename, changedText)
    # Write deleted indexes
    output_filename, _ = generate_output_filename(official_or_current_tagged_lang_file, "deleted_indexes")
    write_output_file(output_filename, deletedText)
    # Write added indexes
    output_filename, _ = generate_output_filename(official_or_current_tagged_lang_file, "added_indexes")
    write_output_file(output_filename, addedText)
    # Write translation candidates
    output_filename, _ = generate_output_filename(official_or_current_tagged_lang_file, "translation_candidates")
    write_tagged_output_file(output_filename, translationCandidateText)
    # Write current already translated
    output_filename, _ = generate_output_filename(official_or_current_tagged_lang_file, "current_already_translated")
    write_tagged_output_file(output_filename, currentAlreadyTranslatedText)


# =============================================================================
# Functions below this line are for testing or future use only
# =============================================================================

@mainFunction
def test_apply_byte_offset_to_hangul(input_filename):
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
    section_id = 242841733
    section_name = get_section_name(section_id)
    num_strings = get_num_strings(section_id)
    max_length = get_max_string_length(section_id)

    print(f"Section ID: {section_id}")
    print(f"Section Name: {section_name}")
    print(f"Number of Strings: {num_strings}")
    print(f"Max String Length: {max_length}")


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
def test_print_groups():
    input_filename = "test_input.str"
    test_dict = {}
    with open(input_filename, 'r', encoding="utf8") as textIns:
        for line in textIns:
            line = line.rstrip()
            maEmptyString = reEmptyString.match(line)
            maClientUntaged = reClientUntaged.match(line)
            maClientTaged = reClientTaged.match(line)
            maFontTag = reFontTag.match(line)

            if maEmptyString:
                conIndex = maEmptyString.group(1)
                test_dict[conIndex] = ""
            elif maClientUntaged:
                conIndex = maClientUntaged.group(1)
                conText = maClientUntaged.group(2) if maClientUntaged.group(2) is not None else ""
                test_dict[conIndex] = conText
            elif maClientTaged:
                conIndex = maClientTaged.group(1)
                tag = maClientTaged.group(2)
                text = maClientTaged.group(3)
                test_dict[conIndex] = f"{tag}{text}"
            elif maFontTag:
                conIndex = f"Font:{maFontTag.group(1)}"
                conText = maFontTag.group(2)
                test_dict[conIndex] = conText

    for count, (key, value) in enumerate(test_dict.items(), start=1):
        string = f"[{key}] = \"{value}\""
        maClientUntaged = reClientUntaged.match(string)
        maClientTaged = reClientTaged.match(string)
        maEmptyString = reEmptyString.match(string)
        maFontTag = reFontTag.match(string)

        print(f"String #{count}: {string}")

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
