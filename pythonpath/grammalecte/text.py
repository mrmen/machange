#!python3

from textwrap import wrap


def getParagraph (sText):
    "generator: returns paragraphs of text"
    iStart = 0
    iEnd = sText.find("\n", iStart)
    while iEnd != -1:
        #print(str(iStart) + ":" + str(iEnd))
        yield sText[iStart:iEnd]
        iStart = iEnd + 1
        iEnd = sText.find("\n", iStart)
    yield sText[iStart:]


def generateParagraph (sParagraph, aGrammErrs, aSpellErrs, nWidth=100):
    "Returns a text with readable errors"
    if not sParagraph:
        return ""
    lGrammErrs = sorted(aGrammErrs, key=lambda d: d["nStart"])
    lSpellErrs = sorted(aSpellErrs, key=lambda d: d['nStart'])
    lLines = wrap(sParagraph, nWidth, drop_whitespace=False)
    sText = ""
    nOffset = 0
    for sLine in lLines:
        sText += sLine + "\n"
        ln = len(sLine)
        sErrLine = ""
        nLenErrLine = 0
        nGrammErr = 0
        nSpellErr = 0
        for dErr in lGrammErrs:
            nStart = dErr["nStart"] - nOffset
            if nStart < ln:
                nGrammErr += 1
                if nStart >= nLenErrLine:
                    sErrLine += " " * (nStart - nLenErrLine) + "^" * (dErr["nEnd"] - dErr["nStart"])
                    nLenErrLine = len(sErrLine)
            else:
                break
        for dErr in lSpellErrs:
            nStart = dErr['nStart'] - nOffset
            if nStart < ln:
                nSpellErr += 1
                nEnd = dErr['nEnd'] - nOffset
                if nEnd > len(sErrLine):
                    sErrLine += " " * (nEnd - len(sErrLine))
                sErrLine = sErrLine[:nStart] + "°" * (nEnd - nStart) + sErrLine[nEnd:]
            else:
                break
        if sErrLine:
            sText += sErrLine + "\n"
        if nGrammErr:
            for dErr in lGrammErrs[:nGrammErr]:
                sMsg, *others = getReadableError(dErr).split("\n")
                sText += "\n".join(wrap(sMsg, nWidth, subsequent_indent="  ")) + "\n"
                for arg in others:
                    sText += "\n".join(wrap(arg, nWidth, subsequent_indent="    ")) + "\n"
            sText += "\n"
            del lGrammErrs[0:nGrammErr]
        if nSpellErr:
            del lSpellErrs[0:nSpellErr]
        nOffset += ln
    return sText


def getReadableError (dErr):
    "Returns an error dErr as a readable error"
    try:
        s = u"* {nStart}:{nEnd}  # {sRuleId}  : ".format(**dErr)
        s += dErr.get("sMessage", "# error : message not found")
        if dErr.get("aSuggestions", None):
            s += "\n  > Suggestions : " + " | ".join(dErr.get("aSuggestions", "# error : suggestions not found"))
        if dErr.get("URL", None):
            s += "\n  > URL: " + dErr["URL"]
        return s
    except KeyError:
        return u"* Non-compliant error: {}".format(dErr)
