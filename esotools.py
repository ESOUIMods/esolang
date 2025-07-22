# -*- coding: utf-8 -*-
import argparse
import sys
import os
import inspect
import re
import struct
import codecs
import chardet
from slpp import slpp as lua
from collections import defaultdict
from difflib import SequenceMatcher
import section_constants as section
import polib
import xml.etree.ElementTree as ET
from icu import Collator, Locale, UCollAttribute, UCollAttributeValue, UnicodeString, BreakIterator

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
                func(*func_args)
                break
        else:
            print("Unknown function: {}".format(function_name))
    else:
        print("No command provided.")


# Matches the 2-letter language prefix at the start of a filename, such as 'pl_itemnames.dat' or 'en.lang'
reFilenamePrefix = re.compile(r'^([a-z]{2})[_\.]', re.IGNORECASE)

# Matches lines in the format {{position-itemId-count}}string_text from itemnames .txt files
reItemnameTagged = re.compile(r'^\{\{(\d+)-(\d+)-(\d+)\}\}(.*)$')

# Matches lines in the format {{sectionId-sectionIndex-stringId:}}string_text from tagged .lang text files
reLangTagged = re.compile(r'^\{\{(\d+)-(\d+)-(\d+):\}\}(.*)$')

# Matches a gender or neutral suffix in the format ^M, ^F, ^m, ^f, ^N, or ^n
reGrammaticalSuffix = re.compile(r'\^[fFmMnNpP]')

# Matches a language index in the format {{identifier:}}text
reLangIndex = re.compile(r'^\{\{([^:]+):}}(.+?)$')

# Matches lines in the format {{sectionId-sectionIndex-stringId:}}string_text and captures only the stringId and string
reLangStringId = re.compile(r'^\{\{\d+-\d+-(\d+):\}\}(.*)$')

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

# Matches a resource name ID in the format sectionId-sectionIndex-stringIndex
reResNameId = re.compile(r'^(\d+)-(\d+)-(\d+)$')

reColorTag = re.compile(r'\|c[0-9A-Fa-f]{6}|\|r')

# Matches tagged lang entries with optional chunk index after colon
# Group 1: stringId as "sectionId-sectionIndex-stringIndex"
# Group 2 (optional): chunk index (e.g., ":1", ":2", etc.)
# Group 3: the actual translated or source text string
reLangChunkedString = re.compile(r'\{\{(\d+-\d+-\d+)(?::(\d+))?\}\}(.*)')


# Read and write binary structs
def readUByte(file): return struct.unpack('>B', file.read(1))[0]


def readUInt16(file): return struct.unpack('>H', file.read(2))[0]


def readUInt32(file): return struct.unpack('>I', file.read(4))[0]


def readUInt64(file): return struct.unpack('>Q', file.read(8))[0]


def writeUByte(file, value): file.write(struct.pack('>B', value))


def writeUInt16(file, value): file.write(struct.pack('>H', value))


def writeUInt32(file, value): file.write(struct.pack('>I', value))


def writeUInt64(file, value): file.write(struct.pack('>Q', value))


def restore_nbsp_bytes(raw_bytes):
    """
    Restores non-breaking space placeholder back to b'\xC2\xA0'.
    """
    return raw_bytes.replace(b"-=NB=-", b"\xC2\xA0")


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

    # Now guaranteed to be a str from here onward
    if any(ord(char) > 127 for char in text):
        return True

    latin_translation_chars = set("ñáéíóúüàâæçèêëîïôœùûÿäößãõêîìíòùąćęłńśźżğıİş")
    if any(char in latin_translation_chars for char in text.lower()):
        return True

    return False


from icu import Locale, BreakIterator, UnicodeString


def is_valid_language_code(code):
    try:
        loc = Locale(code)
        return bool(loc.getLanguage())  # returns False if language is invalid
    except:
        return False


def titlecase(text, base_lang_code):
    if not is_valid_language_code(base_lang_code):
        raise ValueError(f"Language code '{base_lang_code}' is not valid.")
    locale = Locale(base_lang_code)
    breaker = BreakIterator.createWordInstance(locale)
    return UnicodeString(text).toTitle(breaker, locale).__str__()


def parse_itemids_to_dict(input_file_path):
    """
    Reads en_itemids.dat and returns a dictionary:
      pos → (value(s), end_pos)
    """
    result = {}

    with open(input_file_path, "rb") as f:
        try:
            header = readUInt32(f)
        except Exception:
            print("Unable to read header.")
            return {}

        while True:
            pos = f.tell()
            try:
                chunk_type = readUByte(f)
            except:
                break  # EOF

            if chunk_type == 1:
                try:
                    item_id = readUInt32(f)
                    result[pos] = ((item_id,), f.tell() - 1)
                except:
                    break

            elif chunk_type == 3:
                try:
                    item_id = readUInt32(f)
                    param = readUInt16(f)
                    result[pos] = ((item_id, param), f.tell() - 1)
                except:
                    break

            elif chunk_type == 7:
                try:
                    item_id = readUInt32(f)
                    group = readUInt16(f)
                    index = readUInt16(f)
                    result[pos] = ((item_id, group, index), f.tell() - 1)
                except:
                    break

            else:
                print("Unknown chunk type {} at offset {}".format(chunk_type, pos))
                f.read(30)
                break

    return result


def parse_itemnames_to_dict(input_file_path):
    """
    Parses a language-specific itemnames.dat file into a dictionary.

    Key: position (from en_itemids.dat)
    Value: (count, next_offset, string_value)

    If duplicate positions are found, skips them with a warning.
    """
    import struct

    result = {}
    seen_positions = set()

    with open(input_file_path, "rb") as f:
        header = readUInt32(f)

        while True:
            # Read null-terminated UTF-8 string using readExtendedChar
            string_bytes = bytearray()
            while True:
                char, shift = readExtendedChar(f)
                if not char or char == b'\x00':
                    break
                string_bytes.extend(char)

            if not string_bytes:
                break  # EOF

            string_value = string_bytes.decode("utf-8", errors="replace")

            # Read 4-byte position in en_itemids.dat
            position_bytes = f.read(4)
            if len(position_bytes) < 4:
                break
            position_value = struct.unpack(">I", position_bytes)[0]

            # Read 1-byte count
            count_bytes = f.read(1)
            if not count_bytes:
                break
            count_value = struct.unpack(">B", count_bytes)[0]

            # Read 4-byte next_offset
            offset_bytes = f.read(4)
            if len(offset_bytes) < 4:
                break
            next_offset = struct.unpack(">I", offset_bytes)[0]

            if position_value in result:
                print("Warning: Duplicate position {}, skipping string: {}".format(position_value, string_value))
                continue

            result[position_value] = (count_value, next_offset, string_value)

    return result


@mainFunction
def parse_eso_doc(filename):
    protected = {}
    private = {}
    game_api = {}

    def categorize_line(line):
        if "*protected*" in line:
            return protected
        elif "*private*" in line:
            return private
        else:
            return game_api

    def format_type(raw_type):
        primitive_types = {"string", "integer", "number", "boolean", "table", "function", "luaindex",
                           "luaindex:nilable"}
        raw_type = raw_type.strip("*")
        if raw_type in primitive_types or raw_type.startswith("luaindex"):
            return "'''{}'''".format(raw_type)
        return "'''[[Globals#{0}|{0}]]'''".format(raw_type)

    with open(filename, "r", encoding="utf-8") as f:
        lines = f.readlines()

    current_dict = None
    current_key = None

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        if line.startswith("*"):
            target_dict = categorize_line(line)
            match = re.match(r"\* ([^\s\*]+) \*[^\*]+\* \((.*)\)", line)
            if not match:
                continue
            func_name = match.group(1)
            params = match.group(2)

            if not params or params.strip() == "":
                param_string = "()"
            else:
                formatted_params = []
                for param in re.split(r',\s*(?=[^)]*(?:\(|$))', params):
                    enum_match = re.match(r"\*\[([^|\]]+)\|#([^\]]+)\]\*", param)
                    if enum_match:
                        enum_type = enum_match.group(1)
                        var_name = param.split()[-1]
                        formatted_params.append("{} {}".format(format_type(enum_type), var_name))
                    else:
                        parts = param.strip().split()
                        if len(parts) >= 2:
                            formatted_params.append("{} {}".format(format_type(parts[0]), " ".join(parts[1:])))
                        elif len(parts) == 1:
                            formatted_params.append("{}".format(format_type(parts[0])))
                param_string = "(" + ", ".join(formatted_params) + ")"

            target_dict[func_name] = {
                "func": "* {{GitHubSearch|Search=" + func_name + "}} {{Private function}} [[" + func_name + "]]" + param_string,
                "return": None
            }
            current_dict = target_dict
            current_key = func_name
        elif line.startswith("** ''Returns:''") and current_dict and current_key:
            ret_match = re.match(r"\*\* ''Returns:'' '''([^']+)''' (.+)", line)
            if ret_match:
                return_type, return_var = ret_match.groups()
                formatted_type = format_type(return_type)
                current_dict[current_key]["return"] = "** ''Returns:'' {} {}".format(formatted_type, return_var)
            else:
                current_dict[current_key]["return"] = line

    return protected, private, game_api


def output_wiki_format(protected, private, game_api):
    def emit_section(section_dict):
        lines = []
        for func_name in sorted(section_dict.keys(), key=lambda k: k.lower()):
            lines.append(section_dict[func_name]["func"])
            if section_dict[func_name]["return"]:
                lines.append(section_dict[func_name]["return"])
        return lines

    out_lines = []
    out_lines += emit_section(protected)
    out_lines += emit_section(private)
    out_lines += emit_section(game_api)

    return "\n".join(out_lines)


def normalize_map_key(path, strip_ui_map=False, keep_map_num=True):
    path = path.lower()
    path = path.split("/maps/")[-1]
    if strip_ui_map:
        path = path.replace("ui_map_", "")
    path = path.replace(".dds", "")
    if not keep_map_num:
        path = re.sub(r"\d*$", "", path)
        path = re.sub(r"_+$", "", path)
    return path


@mainFunction
def find_missing_maps(lua_file, dds_file, strip_ui_map=False, keep_map_num=True, zone_prefix=None, output_file=None):
    """
    Compare map keys from Lua with DDS filenames, emulating LibMapPins behavior.
    """

    # Load and parse Lua keys
    with open(lua_file, "r", encoding="utf-8") as f:
        raw = f.read()
        if raw.strip().startswith("return"):
            raw = raw[6:].strip()
        lua_data = lua.decode(raw)

    lua_keys_set = set()
    for key in lua_data:
        norm = normalize_map_key(key, strip_ui_map, keep_map_num)
        if not zone_prefix or norm.startswith(zone_prefix.lower()):
            lua_keys_set.add(norm)

    # Load and normalize DDS paths
    with open(dds_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    dds_set = set()
    for line in lines:
        path = line.strip().replace("\\", "/")
        if path.endswith(".dds") and "/maps/" in path:
            norm = normalize_map_key(path, strip_ui_map, keep_map_num)
            dds_set.add(norm)

    # Compare
    missing = sorted(lua_keys_set - dds_set)

    if missing:
        print("Missing texture files:")
        for key in missing:
            print("  {}".format(key))
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                for key in missing:
                    f.write(key + "\n")
    else:
        print("All Lua keys have matching texture files.")


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
            cleaned_line = reGrammaticalSuffix.sub('', line)
            outfile.write(cleaned_line)

    print("Stripped gender suffixes and saved to {}".format(output_file))


def readTaggedLangFile(taggedFile, targetDict):
    with open(taggedFile, 'r', encoding="utf8") as textIns:
        for line in textIns:
            maLangIndex = reLangIndex.match(line)
            if maLangIndex:
                conIndex = maLangIndex.group(1)
                conText = maLangIndex.group(2)
                targetDict[conIndex] = conText


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
        cleaned_name = reGrammaticalSuffix.sub('', rawname.strip())
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


@mainFunction
def extract_formatted_itemnames(input_file):
    """
    Extracts all null-terminated UTF-8 strings from a formatted item names file (e.g., ua_formatteditemnames.dat)
    and writes them to <prefix>_output_<suffix>.txt with LF endings.

    Args:
        input_file (str): Path to a .dat file such as 'ua_formatteditemnames.dat' or 'en_formatteditemnames.dat'.

    Notes:
        This function assumes the file is a raw binary stream of null-terminated UTF-8 strings.
        It outputs one decoded string per line.
    """
    basename = os.path.basename(input_file)
    match = reFilenamePrefix.match(basename)
    prefix = match.group(1) if match else "xx"
    suffix = basename.rsplit(".", 1)[0].split("_", 1)[-1]
    output_filename = "{}_output_{}.txt".format(prefix, suffix)

    string_count = 0
    with open(input_file, 'rb') as f, open(output_filename, 'w', encoding="utf8") as out:
        buffer = bytearray()
        while True:
            byte = f.read(1)
            if not byte:
                if buffer:
                    out.write(buffer.decode("utf-8", errors="replace") + "\n")
                    string_count += 1
                break
            if byte == b'\x00':
                if buffer:
                    out.write(buffer.decode("utf-8", errors="replace") + "\n")
                    string_count += 1
                    buffer.clear()
            else:
                buffer.extend(byte)

    print("Done. Extracted {} strings to {}.".format(string_count, output_filename))


@mainFunction
def rebuild_formatted_itemnames_binary(input_itemnames_dat, input_itemids_dat, item_names_txt):
    """
    Builds a language-specific formatteditemnames .dat file using names from a language file.

    Inputs:
        pl_itemnames_dat: Path to the localized itemnames.dat
        pl_itemids_dat:   Path to the localized itemids.dat
        item_names_txt:   Path to the formatted names text (e.g. 242841733_item_names_ko.txt)

    Output:
        <prefix>_output_<suffix>.dat (binary)
    """
    itemid_to_formatted_itemnames = {}
    with open(item_names_txt, "r", encoding="utf8") as f:
        for line in f:
            match = reLangStringId.match(line.strip())
            if match:
                item_id = int(match.group(1))
                name = match.group(2).strip()
                itemid_to_formatted_itemnames[item_id] = name

    id_dict = parse_itemids_to_dict(input_itemids_dat)
    names_dict = parse_itemnames_to_dict(input_itemnames_dat)

    basename = os.path.basename(item_names_txt)
    prefix = basename.split("_", 1)[0]
    suffix = basename.split("_", 1)[1].rsplit(".", 1)[0]
    output_bin = "{}_output_{}.dat".format(prefix, suffix)

    with open(output_bin, "wb") as out:
        out.write(struct.pack(">I", 0x00000001))  # Header

        for position in sorted(names_dict.keys()):
            count, next_offset, fallback_name = names_dict[position]
            item_id = id_dict.get(position, ([0], None))[0][0]
            string = itemid_to_formatted_itemnames.get(item_id, fallback_name).strip()
            out.write(string.encode("utf-8") + b'\x00')

    print("Done. Binary written to", output_bin)


@mainFunction
def rebuild_formatted_itemnames_binary_with_uppercase(input_itemnames_dat):
    """
    Builds a language-specific formatteditemnames .dat file using titlecased fallback names.

    Inputs:
        input_itemnames_dat: Path to the localized itemnames.dat
        input_itemids_dat:   Path to the localized itemids.dat
        item_names_txt:      Path to the formatted names text (only used for output file name)

    Output:
        <prefix>_output_<suffix>.dat (binary)
    """
    names_dict = parse_itemnames_to_dict(input_itemnames_dat)

    basename = os.path.basename(input_itemnames_dat)
    match = reFilenamePrefix.match(basename)
    prefix = match.group(1) if match else "xx"  # fallback to "xx" if no match
    suffix = basename.rsplit(".", 1)[0].split("_", 1)[-1]
    output_bin = "{}_output_formatteditemnames.dat".format(prefix, suffix)

    with open(output_bin, "wb") as out:
        out.write(struct.pack(">I", 0x00000001))  # Header

        for position in sorted(names_dict.keys()):
            count, next_offset, string_text = names_dict[position]
            string = titlecase(string_text.strip(), lang="pl")
            out.write(string.encode("utf-8") + b'\x00')

    print("Done. Binary written to", output_bin)


@mainFunction
def extract_itemnames_for_rebuild(input_itemnames_file, input_itemids_file):
    """
    Parses en_itemnames.dat and en_itemids.dat:
    - Handles extended characters using readExtendedChar.
    - Reads string, a 4-byte item ID file position pointer, a 1-byte count of associated item IDs,
      and a 4-byte value representing the offset to the next string.
    - Looks up item_id from en_itemids.dat using the position pointer.
    - Outputs: {{position-item_id-count}}string
    """
    item_names_dict = parse_itemnames_to_dict(input_itemnames_file)
    id_dict = parse_itemids_to_dict(input_itemids_file)

    basename = os.path.basename(input_itemnames_file)
    if "_" in basename:
        prefix = basename.split("_", 1)[0]
        suffix = basename.split("_", 1)[1].rsplit(".", 1)[0]
        output_filename = "{}_output_{}_rebuild.txt".format(prefix, suffix)
    else:
        output_filename = "output_itemnames_rebuild.txt"

    with open(output_filename, "w", encoding="utf8") as out:
        for position in sorted(item_names_dict.keys()):
            count, _, string_value = item_names_dict[position]

            if position not in id_dict:
                print("Warning: Position {} not found in itemids file. Skipping.".format(position))
                continue

            values, _ = id_dict[position]
            item_id = values[0]

            out.write("{{{{{}-{}-{}}}}}{}\n".format(
                position,
                item_id,
                count,
                string_value
            ))

    print("Done. Output written to {}".format(output_filename))


@mainFunction
def rebuild_itemnames_binary(input_txt, sort=False):
    """
    Rebuilds en_itemnames.dat-style binary file from text format:
    Each line: {{position-item_id-count}}name
    Structure per entry:
      - UTF-8 null-terminated string
      - 4-byte position in en_itemids.dat
      - 1-byte count of item IDs
      - 4-byte offset to next string (absolute)
    """
    entries = []
    basename = os.path.basename(input_txt)
    prefix = basename.split("_", 1)[0]
    suffix = basename.split("_", 1)[1].rsplit(".", 1)[0]
    output_bin = "{}_output_{}.dat".format(prefix, suffix)

    with open(input_txt, "r", encoding="utf-8") as infile:
        for line in infile:
            match = re.match(r"\{\{(\d+)-\d+-(\d+)\}\}(.*)", line.strip())
            if match:
                pos, count, name = match.groups()
                entries.append((name.encode("utf-8"), int(pos), int(count)))
            else:
                print("Skipping invalid line:", line.strip())

    if sort is True:
        collator = Collator.createInstance(Locale.getRoot())
        collator.setStrength(Collator.PRIMARY)
        collator.setAttribute(UCollAttribute.CASE_LEVEL, UCollAttributeValue.OFF)
        entries.sort(key=lambda x: collator.getSortKey(x[0].decode("utf-8")))

    with open(output_bin, "wb") as out:
        out.write(struct.pack(">I", 0x00000002))  # Actual header from original file

        previous_offset = 4
        previous_len = 0
        current_offset = None

        for i, (encoded_name, pos, count) in enumerate(entries):
            restored = restore_nbsp_bytes(encoded_name)
            name_len = len(restored) + 1  # null terminator

            # Write string + null
            out.write(restored)
            out.write(b'\x00')

            # Write 4-byte position
            out.write(struct.pack(">I", pos))

            # Write 1-byte count
            out.write(struct.pack(">B", count))

            current_offset = previous_offset + previous_len
            out.write(struct.pack(">I", current_offset))
            previous_offset = current_offset
            previous_len = name_len

    print("Binary file written to", output_bin)


@mainFunction
def merge_translated_itemnames(translated_txt_file, en_itemnames_file, en_itemids_file):
    """
    Builds a new itemnames file based on English structure, with translated strings substituted
    where available by itemId match.

    Inputs:
        translated_txt_file: A .txt file of the form {{position-itemId-count}}translated name
        en_itemnames_file: The English .dat file (names)
        en_itemids_file: The English .dat file (ids)

    Outputs:
        merged_<translated_txt_file>.txt with full 1:1 line count, either translated or original English.
    """
    itemid_to_translated_strings = {}  # itemId → set of positions
    with open(translated_txt_file, "r", encoding="utf8") as f:
        for line in f:
            match = re.match(r"^\{\{(\d+)-(\d+)-(\d+)\}\}(.*)$", line.strip())
            if match:
                position = int(match.group(1))
                item_id = int(match.group(2))
                count = int(match.group(3))
                text = match.group(4).strip()
                itemid_to_translated_strings[item_id] = text

    # Read English itemids
    id_dict = parse_itemids_to_dict(en_itemids_file)
    # Read English itemnames
    names_dict = parse_itemnames_to_dict(en_itemnames_file)

    # Build output
    output_lines = []
    for position, data in names_dict.items():
        item_id = id_dict[position][0][0]
        count = data[0]
        next_offset = data[1]
        string_text = data[2]
        hasTranslation = itemid_to_translated_strings.get(item_id) is not None
        if hasTranslation:
            string_text = itemid_to_translated_strings.get(item_id)
        output_lines.append("{{{{{}-{}-{}}}}}{}".format(position, item_id, count, string_text))

    out_file = "merged_" + os.path.basename(translated_txt_file)
    with open(out_file, "w", encoding="utf8") as out:
        for line in output_lines:
            out.write(line + "\n")

    print("Merged output written to", out_file)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--help-docstrings":
        print_docstrings()
    else:
        main()
