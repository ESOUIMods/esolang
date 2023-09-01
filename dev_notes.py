textUntranslatedLiveDict = {}
textUntranslatedPTSDict = {}
textTranslatedDict = {}

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

@mainFunction
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
                
Here's an example of how you could use a list comprehension for generating the keys that need verification:

keys_to_verify = [
    key for key in textUntranslatedPTSDict 
    if (
        (translatedTextStripped := cleanText(textTranslatedDict.get(key))) and
        (liveTextStripped := cleanText(textUntranslatedLiveDict.get(key))) and
        (ptsTextStripped := cleanText(textUntranslatedPTSDict.get(key))) and
        translatedTextStripped != ptsTextStripped and
        not (
            (translatedAndPtsGreaterThanThreshold := isTranslatedText(translatedTextStripped)) and
            (subTranslatedText := reColorTag.sub('', translatedTextStripped)) and
            (subPtsText := reColorTag.sub('', ptsTextStripped)) and
            SequenceMatcher(None, subTranslatedText, subPtsText).ratio() > 0.6
        )
    )
]
