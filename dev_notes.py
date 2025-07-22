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
from collections import defaultdict

textUntranslatedLiveDict = {}
textUntranslatedPTSDict = {}
textTranslatedDict = {}

# Matches the 2-letter language prefix at the start of a filename, such as 'pl_itemnames.dat' or 'en.lang'
reFilenamePrefix = re.compile(r'^([a-z]{2})[_\.]', re.IGNORECASE)

# Matches lines in the format {{position-itemId-count}}string_text from itemnames .txt files
reItemnameTagged = re.compile(r'^\{\{(\d+)-(\d+)-(\d+)\}\}(.*)$')

# Matches lines in the format {{sectionId-sectionIndex-stringId:}}string_text from tagged .lang text files
reLangTagged = re.compile(r'^\{\{(\d+)-(\d+)-(\d+):\}\}(.*)$')

# Matches a gender or neutral suffix in the format ^M, ^F, ^m, ^f, ^N, or ^n
reGenderSuffix = re.compile(r'\^[MmFfNn]')

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

# Matches tagged lang entries with optional chunk index after colon
# Group 1: stringId as "sectionId-sectionIndex-stringIndex"
# Group 2 (optional): chunk index (e.g., ":1", ":2", etc.)
# Group 3: the actual translated or source text string
reLangChunkedString = re.compile(r'\{\{(\d+-\d+-\d+)(?::(\d+))?\}\}(.*)')

reColorTag = re.compile(r'\|c[0-9a-zA-Z]{1,6}|\|r')


# Read and write binary structs
def readUByte(file): return struct.unpack('>B', file.read(1))[0]


def readUInt16(file): return struct.unpack('>H', file.read(2))[0]


def readUInt32(file): return struct.unpack('>I', file.read(4))[0]


def readUInt64(file): return struct.unpack('>Q', file.read(8))[0]


def writeUByte(file, value): file.write(struct.pack('>B', value))


def writeUInt16(file, value): file.write(struct.pack('>H', value))


def writeUInt32(file, value): file.write(struct.pack('>I', value))


def writeUInt64(file, value): file.write(struct.pack('>Q', value))


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


def readTaggedLangFile(taggedFile, targetDict):
    reLangConstantTag = re.compile(r'^\{\{(.+?):\}\}(.+?)$')

    with open(taggedFile, 'r', encoding="utf8") as textIns:
        for line in textIns:
            maConstantText = reLangConstantTag.match(line)
            if maConstantText:
                conIndex = maConstantText.group(1)
                conText = maConstantText.group(2)
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


def diffIndexedLangText(translatedFilename, unTranslatedLiveFilename, unTranslatedPTSFilename):
    reColorTag = re.compile(r'\|c[0-9a-zA-Z]{1,6}|\|r')
    reControlChar = re.compile(r'\^f|\^n|\^F|\^N|\^p|\^P')

    # -- removeUnnecessaryText
    reColorTagError = re.compile(r'(\|c000000)(\|c[0-9a-zA-Z]{6,6})')

    def isTranslatedText(line):
        for char in range(0, len(line)):
            returnedBytes = bytes(line[char], 'utf-8')
            length = len(returnedBytes)
            if length > 1: return True
        return None

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
                hasExtendedChars = False
                hasTranslation = False
                if translatedTextStripped is not None:
                    hasExtendedChars = isTranslatedText(translatedTextStripped)
                # ---Determine Change Ratio between Live and Pts---
                liveAndPtsGreaterThanThreshold = False
                if liveTextStripped and ptsTextStripped:
                    subLiveText = reColorTag.sub('', liveTextStripped)
                    subPtsText = reColorTag.sub('', ptsTextStripped)
                    subLiveText = reControlChar.sub('', subLiveText)
                    subPtsText = reControlChar.sub('', subPtsText)
                    similarity_ratio = SequenceMatcher(None, subLiveText, subPtsText).ratio()
                    if liveTextStripped == ptsTextStripped or similarity_ratio > 0.6:
                        liveAndPtsGreaterThanThreshold = True
                # ---Determine Change Ratio between Translated and Pts ---
                translatedAndPtsGreaterThanThreshold = False
                if translatedTextStripped is not None and ptsTextStripped is not None:
                    subTranslatedText = reColorTag.sub('', translatedTextStripped)
                    subPtsText = reColorTag.sub('', ptsTextStripped)
                    subTranslatedText = reControlChar.sub('', subTranslatedText)
                    subPtsText = reControlChar.sub('', subPtsText)
                    similarity_ratio = SequenceMatcher(None, subTranslatedText, subPtsText).ratio()
                    if translatedTextStripped == ptsTextStripped or similarity_ratio > 0.6:
                        translatedAndPtsGreaterThanThreshold = True
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


def extract_itemnames_exclude_matching_english(input_itemnames_file, input_itemids_file, en_itemnames_file, en_itemids_file):
    """
    Parses translated itemnames.dat and itemids.dat to output each entry as:
    {{position-item_id-count}}string_text

    Skips any entry where the item_id exists in the English files AND
    string_value matches the English string for that item_id.
    """
    id_dict = parse_itemids_to_dict(input_itemids_file)
    en_id_dict = parse_itemids_to_dict(en_itemids_file)
    en_itemnames_dict = parse_itemnames_to_dict(en_itemnames_file)

    # Build reverse lookup: item_id → set of English strings
    en_strings_by_item_id = defaultdict(set)

    for position, data in en_itemnames_dict.items():
        itemName = data[2]  # Get the name from the third tuple element
        item_id = en_id_dict.get(position, ([0], None))[0][0]  # Get item_id from position
        en_strings_by_item_id[item_id].add(itemName)

    basename = os.path.basename(input_itemnames_file)
    if "_" in basename:
        prefix = basename.split("_", 1)[0]
        suffix = basename.split("_", 1)[1].rsplit(".", 1)[0]
        output_filename = "{}_output_{}_filtered.txt".format(prefix, suffix)
    else:
        output_filename = "output_itemnames_filtered.txt"

    with open(input_itemnames_file, "rb") as f, open(output_filename, "w", encoding="utf8") as out:
        header = readUInt32(f)

        while True:
            # Read null-terminated UTF-8 string
            string_bytes = bytearray()
            while True:
                char, shift = readExtendedChar(f)
                if not char or char == b'\x00':
                    break
                string_bytes.extend(char)

            if not string_bytes:
                break

            string_value = string_bytes.decode("utf-8", errors="replace")

            try:
                position_bytes = f.read(4)
                if len(position_bytes) < 4:
                    break
                position_value = struct.unpack(">I", position_bytes)[0]

                count_bytes = f.read(1)
                if not count_bytes:
                    break
                item_id_count = struct.unpack(">B", count_bytes)[0]

                f.read(4)  # skip offset

                item_id = id_dict.get(position_value, ([0], None))[0][0]

                # Skip exact English match
                if string_value in en_strings_by_item_id.get(item_id, set()):
                    continue

                out.write("{{{{{}-{}-{}}}}}{}\n".format(position_value, item_id, item_id_count, string_value))

            except Exception as e:
                print("Error at string '{}': {}".format(string_value, e))
                break

    print("Done. Output written to {}".format(output_filename))


def get_kdr_input():
    """
    Waits for user input: 'k', 'r', or 'd' (case-insensitive), followed by Enter.
    Returns the lowercase character when valid.
    """
    while True:
        key = input("Enter choice [k = keep, r = replace, d = discard]: ").strip().lower()
        if key in {"k", "r", "d"}:
            return key
        print("Invalid input. Please enter 'k', 'r', or 'd'.")


def resolve_itemname_conflicts_interactive(input_file):
    """
    Reads a .txt file in {{position-itemId-count}}string format and resolves duplicates interactively.

    Prompts user to 'k' (keep), 'r' (replace), or 'd' (discard) when multiple entries exist for the same itemId.

    Outputs: resolved_<input_file> with cleaned and confirmed results.
    """
    entries_by_position = {}  # position → (itemId, count, string)
    itemid_to_positions = defaultdict(set)  # itemId → set of positions

    with open(input_file, "r", encoding="utf8") as f:
        for line in f:
            match = reItemnameTagged.match(line.strip())
            if not match:
                continue

            position = int(match.group(1))
            item_id = int(match.group(2))
            count = int(match.group(3))
            string_value = match.group(4).strip()

            print("{}-{}-{}-{}\n".format(position, item_id, count, string_value))

            existing_position = itemid_to_positions.get(item_id) or False
            if existing_position:
                # Conflict detected
                existing_pos = next(iter(existing_position))
                existing_entry = entries_by_position[existing_pos]

                print("\nConflict detected for itemId: {}".format(item_id))
                print("Existing: {{%d-%d-%d}}%s" % (existing_pos, item_id, existing_entry[1], existing_entry[2]))
                print("New     : {{%d-%d-%d}}%s" % (position, item_id, count, string_value))

                while True:
                    choice = get_kdr_input()
                    if choice == "k":
                        break  # Keep existing, skip new
                    elif choice == "r":
                        # Replace with new
                        for p in existing_position:
                            entries_by_position.pop(p, None)
                        itemid_to_positions[item_id].clear()
                        entries_by_position[position] = (item_id, count, string_value)
                        itemid_to_positions[item_id].add(position)
                        break
                    elif choice == "d":
                        # Discard both
                        for p in existing_position:
                            entries_by_position.pop(p, None)
                        itemid_to_positions[item_id].clear()
                        break

            elif position not in itemid_to_positions[item_id]:
                # No conflict — just add
                entries_by_position[position] = (item_id, count, string_value)
                itemid_to_positions[item_id].add(position)

    output_file = "resolved_" + os.path.basename(input_file)
    with open(output_file, "w", encoding="utf8") as out:
        for pos in sorted(entries_by_position.keys()):
            item_id, count, string_value = entries_by_position[pos]
            out.write("{{{{{}-{}-{}}}}}{}\n".format(pos, item_id, count, string_value))

    print("Done. Wrote resolved entries to {}".format(output_file))


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


def createEsoUIWeblateFile(inputFile, lang="en", outputFile=None, component=None):
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
def extractCleanLines(inputLangFile, outputFilename):
    print(f"Reading {inputLangFile}")
    currentFileIndexes, currentFileStrings = readLangFile(inputLangFile)
    print(f"Done reading {inputLangFile}")

    with open(outputFilename, 'w', encoding='utf8', newline='\n') as out:
        for index in range(currentFileIndexes['numIndexes']):
            entry = currentFileIndexes[index]
            secId = entry['sectionId']
            secIdx = entry['sectionIndex']
            strIdx = entry['stringIndex']
            raw_bytes = entry['string']

            preserved_nbsp = preserve_nbsp_bytes(raw_bytes)
            escaped_bytes = preserve_escaped_sequences_bytes(preserved_nbsp)
            utf8_string = bytes(escaped_bytes).decode("utf8", errors="replace")
            hasTranslation = isTranslatedText(cleanText(utf8_string))

            if '�' not in utf8_string and hasTranslation:
                formatted = f"{{{{{secId}-{secIdx}-{strIdx}:}}}}{utf8_string}"
                lineOut = restore_escaped_sequences(formatted)
                out.write(f"{lineOut}\n")


@mainFunction
def findFirstReplacementChar(inputLangFile):
    print(f"Reading {inputLangFile}")
    currentFileIndexes, currentFileStrings = readLangFile(inputLangFile)
    print(f"Done reading {inputLangFile}")

    for index in range(currentFileIndexes['numIndexes']):
        entry = currentFileIndexes[index]
        sectionId = entry['sectionId']
        raw_bytes = entry['string']
        raw_string = raw_bytes.decode('utf-8', errors='replace')

        if '�' in raw_string:
            print(f"🔴 Found U+FFFD replacement character at index {index}")
            print(f"Section ID: {sectionId}")
            print(f"Text: {raw_string}")
            return  # Stop after first hit

    print("✅ No replacement characters found.")


@mainFunction
def repair_linefeed_cr_encodings(input_translated_file, input_english_file):
    """
    Replaces CRLF sequences (\r\n) with \n\n in translated strings only when
    the corresponding English string contains \n\n. Also logs raw \r not followed by \n.

    Args:
        input_translated_file (str): Path to the .lang file with translated strings.
        input_english_file (str): Path to the .lang file with English source strings.

    Output:
        <prefix>_crfixed_<suffix>.txt — fixed translated text
        <prefix>_crflagged_<suffix>.txt — flagged entries with \r but no \n
    """
    translatedFileIndexes, translatedFileStrings = readLangFile(input_translated_file)
    print("Done reading translated file...")
    englishFileIndexes, englishFileStrings = readLangFile(input_english_file)
    print("Done reading english file...")

    basename = os.path.basename(input_translated_file)
    prefix = basename.split("_", 1)[0]
    suffix = basename.split("_", 1)[1].rsplit(".", 1)[0]
    fixed_filename = f"{prefix}_crfixed_{suffix}.txt"
    flagged_filename = f"{prefix}_crflagged_{suffix}.txt"

    with open(fixed_filename, "w", encoding="utf-8", newline="\n") as fixed_out, \
            open(flagged_filename, "w", encoding="utf-8", newline="\n") as flagged_out:

        for i in range(translatedFileIndexes["numIndexes"]):
            flagged_text = False
            translated_entry = translatedFileIndexes[i]
            secId = translated_entry["sectionId"]
            secIdx = translated_entry["sectionIndex"]
            strIdx = translated_entry["stringIndex"]
            string = translated_entry["string"]  # this is bytes

            if b"\r" in string:
                pos = string.find(b"\r")
                if pos != -1 and pos + 1 < len(string) and string[pos + 1:pos + 2] == b"\n":
                    eng_string = b""
                    for eidx in range(englishFileIndexes["numIndexes"]):
                        e = englishFileIndexes[eidx]
                        if (e["sectionId"] == secId and
                                e["sectionIndex"] == secIdx and
                                e["stringIndex"] == strIdx):
                            eng_string = e["string"]
                            break

                    if b"\n\n" in eng_string:
                        string = string.replace(b"\r\n", b"\n\n")
                    if b"\r" in string:
                        flagged_text = True
                    if b'\xef\xbf\xbd' in string:
                        flagged_text = True
                else:
                    flagged_text = True

            if flagged_text:
                string = string.replace(b"\r", b"")
                preserved_nbsp = preserve_nbsp_bytes(string)
                escaped = preserve_escaped_sequences_bytes(preserved_nbsp)
                decoded = escaped.decode("utf-8", errors="replace").rstrip()
                formatted = f"{{{{{secId}-{secIdx}-{strIdx}:}}}}{decoded}\n"
                restored = restore_escaped_sequences(formatted)
                flagged_out.write(restored)
            else:
                preserved_nbsp = preserve_nbsp_bytes(string)
                escaped = preserve_escaped_sequences_bytes(preserved_nbsp)
                decoded = escaped.decode("utf-8", errors="replace").rstrip()
                formatted = f"{{{{{secId}-{secIdx}-{strIdx}:}}}}{decoded}\n"
                restored = restore_escaped_sequences(formatted)
                fixed_out.write(restored)

    print(f"Fixed output written to: {fixed_filename}")
    print(f"Flagged entries written to: {flagged_filename}")


@mainFunction
def mergeUpdatedValuesIntoLangPreservingOrder(oldLangFile, newLangFile, outputFilename, verificationFilename):
    """
    made to update esokr when there were possible line of corruption beginning with �

    Merge values from newLangFile into oldLangFile if they are safe and improved.
    Write all lines from oldLangFile, replacing only when a better newVal is found.
    Also outputs to a verification file if a match needs manual review.
    """
    reLangIndex = re.compile(r"\{\{(\d+-\d+-\d+):\}\}(.*)")

    oldMap = {}
    newMap = {}

    # Read old lines into oldMap
    with open(oldLangFile, 'r', encoding="utf8") as f:
        for line in f:
            m = reLangIndex.match(line)
            if m:
                key, value = m.groups()
                oldMap[key] = value.strip()

    # Read new lines into newMap
    with open(newLangFile, 'r', encoding="utf8") as f:
        for line in f:
            m = reLangIndex.match(line)
            if m:
                key, value = m.groups()
                newMap[key] = value.strip()

    # Merge and write
    with open(oldLangFile, 'r', encoding="utf8") as infile, \
            open(outputFilename, 'w', encoding="utf8", newline='\n') as out, \
            open(verificationFilename, 'w', encoding="utf8", newline='\n') as verify:

        for line in infile:
            m = reLangIndex.match(line)
            if not m:
                out.write(line)
                continue

            key, oldVal = m.groups()
            oldVal = oldVal.strip()
            newVal = newMap.get(key, "").strip()

            oldTranslated = isTranslatedText(cleanText(oldVal))
            newTranslated = isTranslatedText(cleanText(newVal))

            # Case A: old not translated, new is
            if not oldTranslated and newTranslated:
                out.write(f"{{{{{key}:}}}}{newVal}\n")

            # Case B: both translated
            elif oldTranslated and newTranslated:
                if newVal in oldVal:
                    index = oldVal.index(newVal)
                    if index == 0 and newVal != oldVal:
                        verify.write(f"{{{{{key}:}}}}{newVal}\n")
                    else:
                        out.write(f"{{{{{key}:}}}}{oldVal}\n")
                else:
                    out.write(f"{{{{{key}:}}}}{oldVal}\n")

            # Case C: fallback
            else:
                out.write(f"{{{{{key}:}}}}{oldVal}\n")

    print(f"✅ Merged complete: {outputFilename}")
    print(f"📝 Verification lines written to: {verificationFilename}")


@mainFunction
def extract_itemname_values(input_file):
    """
    Parses en_itemnames.dat:
    - Handles extended characters using readExtendedChar.
    - Reads string, a 4-byte item ID file position pointer, a 1-byte count of associated item IDs,
      and a 4-byte value that represents the byte offset of the next string (not the current string's length).
    - Outputs: string, position, count, next_string_offset.
    """
    basename = os.path.basename(input_file)
    if "_" in basename:
        prefix = basename.split("_", 1)[0]  # e.g., "en"
        suffix = basename.split("_", 1)[1].rsplit(".", 1)[0]  # e.g., "itemnames"
        output_filename = "{}_output_{}.txt".format(prefix, suffix)
    else:
        output_filename = "output_itemnames_values.txt"

    item_names_dict = parse_itemnames_to_dict(input_file)

    with open(output_filename, "w", encoding="utf8") as out:
        for position in sorted(item_names_dict.keys()):
            count, next_string_offset, string_value = item_names_dict[position]
            out.write("{}, {}, {}, {}\n".format(
                string_value,
                position,
                count,
                next_string_offset
            ))

    print("Done. Output written to {}".format(output_filename))


@mainFunction
def extract_itemnames_raw_data(input_file, input_itemids_file):
    """
    Parses itemnames.dat and itemids.dat to output each entry as:
    {{position-item_id-count}}string_text

    Notes:
    - Does not use parse_itemnames_to_dict (no deduplication or validation).
    - Uses parse_itemids_to_dict to resolve item_id from position.
    - This is meant as a raw data dump, including duplicates.
    """
    id_dict = parse_itemids_to_dict(input_itemids_file)

    basename = os.path.basename(input_file)
    if "_" in basename:
        prefix = basename.split("_", 1)[0]
        suffix = basename.split("_", 1)[1].rsplit(".", 1)[0]
        output_filename = "{}_output_{}_raw.txt".format(prefix, suffix)
    else:
        output_filename = "output_itemnames_raw.txt"

    with open(input_file, "rb") as f, open(output_filename, "w", encoding="utf8") as out:
        header = readUInt32(f)

        while True:
            # Read null-terminated UTF-8 string
            string_bytes = bytearray()
            while True:
                char, shift = readExtendedChar(f)
                if not char or char == b'\x00':
                    break
                string_bytes.extend(char)

            if not string_bytes:
                break

            string_value = string_bytes.decode("utf-8", errors="replace")

            try:
                position_bytes = f.read(4)
                if len(position_bytes) < 4:
                    break
                position_value = struct.unpack(">I", position_bytes)[0]

                count_bytes = f.read(1)
                if not count_bytes:
                    break
                item_id_count = struct.unpack(">B", count_bytes)[0]

                f.read(4)  # skip offset

                item_id = id_dict.get(position_value, ([0], None))[0][0]  # fallback 0
                out.write("{{{{{}-{}-{}}}}}{}\n".format(position_value, item_id, item_id_count, string_value))
            except Exception as e:
                print("Error at string '{}': {}".format(string_value, e))
                break

    print("Done. Output written to {}".format(output_filename))

# These two functions process ESO language files like en_itemids.dat or pl_itemids.dat.
# They extract item IDs from binary chunks in the file:
#   - `extract_itemids_with_positions`: outputs item ID(s) and byte position ranges.
#   - `extract_itemids_and_subtypes`: outputs item ID(s) only, without position information.

@mainFunction
def extract_itemids_with_positions(input_file_path):
    """
    Reads a binary item ID file and outputs each ID along with the byte position it was read from.
    Formats:
      - chunk_type 0x01: ID
      - chunk_type 0x03: ID \t param
      - chunk_type 0x07: ID \t group \t index
    Output format: ID [\t param(s)] {start:end}
    """
    basename = os.path.basename(input_file_path)
    if "_" in basename:
        prefix = basename.split("_", 1)[0]
        suffix = basename.split("_", 1)[1].rsplit(".", 1)[0]
        output_file_path = "{}_output_{}_pos.txt".format(prefix, suffix)
    else:
        output_file_path = "output_itemids.txt"

    id_dict = parse_itemids_to_dict(input_file_path)
    max_item_id = 0

    with open(output_file_path, "w", encoding="utf-8") as out:
        for pos in sorted(id_dict.keys()):
            values, end = id_dict[pos]
            if values and isinstance(values[0], int):
                max_item_id = max(max_item_id, values[0])
            out.write("{} {{{}:{}}}\n".format(" ".join(str(v) for v in values), pos, end))

    print("Done. Output written to {}".format(output_file_path))
    print("Highest item_id encountered: {}".format(max_item_id))


@mainFunction
def extract_itemids_and_subtypes(input_file_path):
    """
    Reads en_itemids.dat and outputs only the item ID data (no positions).
    Handles chunk types:
      - 0x01: item_id
      - 0x03: item_id sub_type
      - 0x07: item_id group index

    Output format:
    item_id [sub_type] [group index]
    """
    import os

    basename = os.path.basename(input_file_path)
    if "_" in basename:
        prefix = basename.split("_", 1)[0]
        suffix = basename.split("_", 1)[1].rsplit(".", 1)[0]
        output_file_path = "{}_output_{}.txt".format(prefix, suffix)
    else:
        output_file_path = "output_itemids.txt"

    id_dict = parse_itemids_to_dict(input_file_path)
    max_item_id = 0

    with open(output_file_path, "w", encoding="utf-8") as out:
        for pos in sorted(id_dict.keys()):
            values, _ = id_dict[pos]
            if values and isinstance(values[0], int):
                max_item_id = max(max_item_id, values[0])
            out.write("{}\n".format(" ".join(str(v) for v in values)))

    print("Done. Output written to {}".format(output_file_path))
    print("Highest item_id encountered: {}".format(max_item_id))



def main():
    """ This is to be run from the fontforge UI not any version of python
    however it won't work because arabic is right to left text with scaling
    and combining of glyphs it was an experement and I want to preserve this
    """
    # Open the font file
    font = fontforge.open("myfont.ttf")

    # Define the source (Arabic) and target (Chinese) Unicode code point ranges
    source_start = 0x0600
    target_start = 0x6E00

    num_glyphs_to_copy = 11172
    for offset in range(num_glyphs_to_copy):
        source_unicode = source_start + offset
        target_unicode = target_start + offset

        source_glyph = font[chr(source_unicode)]
        target_glyph = font.createMappedChar(target_unicode)

        target_glyph.clear()
        target_glyph.importOutlines(source_glyph)

    font.save("modified_font.ttf")
    font.close()
