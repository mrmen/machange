# -*- encoding: UTF-8 -*-

import re
import sys
import os
import traceback

from ..ibdawg import IBDAWG
from ..echo import echo
from . import gc_options


__all__ = [ "lang", "locales", "pkg", "name", "version", "author", \
            "load", "parse", "getDictionary", \
            "setOptions", "getOptions", "getOptionsLabels", "resetOptions", \
            "ignoreRule", "resetIgnoreRules" ]

__version__ = u"0.5.7"


lang = u"fr"
locales = {'fr-CA': ['fr', 'CA', ''], 'fr-MC': ['fr', 'MC', ''], 'fr-FR': ['fr', 'FR', ''], 'fr-CH': ['fr', 'CH', ''], 'fr-BE': ['fr', 'BE', ''], 'fr-LU': ['fr', 'LU', '']}
pkg = u"grammalecte"
name = u"Grammalecte"
version = u"0.5.7"
author = u"Olivier R."

# commons regexes
_zEndOfSentence = re.compile(u'([.?!:;…][ .?!… »”")]*|.$)')
_zBeginOfParagraph = re.compile(u"^\W*")
_zEndOfParagraph = re.compile(u"\W*$")
_zNextWord = re.compile(u" +(\w[\w-]*)")
_zPrevWord = re.compile(u"(\w[\w-]*) +$")

# grammar rules and dictionary
_rules = None
_dOptions = dict(gc_options.dOpt)       # duplication necessary, to be able to reset to default
_aIgnoredRules = set()
_oDict = None
_dAnalyses = {}                         # cache for data from dictionary

_GLOBALS = globals()


#### Parsing

def parse (sText, sCountry="FR", bDebug=False, dOptions=None):
    "analyses the paragraph sText and returns list of errors"
    aErrors = None
    sAlt = sText
    dDA = {}
    dOpt = _dOptions  if not dOptions  else dOptions

    # parse paragraph
    try:
        sNew, aErrors = _proofread(sText, sAlt, 0, True, dDA, sCountry, dOpt, bDebug)
        if sNew:
            sText = sNew
    except:
        raise

    # parse sentences
    for iStart, iEnd in _getSentenceBoundaries(sText):
        if 4 < (iEnd - iStart) < 2000:
            dDA.clear()
            try:
                _, errs = _proofread(sText[iStart:iEnd], sAlt[iStart:iEnd], iStart, False, dDA, sCountry, dOpt, bDebug)
                aErrors.extend(errs)
            except:
                raise
    return aErrors


def _getSentenceBoundaries (sText):
    iStart = _zBeginOfParagraph.match(sText).end()
    for m in _zEndOfSentence.finditer(sText):
        yield (iStart, m.end())
        iStart = m.end()


def _proofread (s, sx, nOffset, bParagraph, dDA, sCountry, dOptions, bDebug):
    aErrs = []
    bChange = False
    
    if not bParagraph:
        # after the first pass, we modify automatically some characters
        if u" " in s:
            s = s.replace(u" ", u' ') # nbsp
            bChange = True
        if u" " in s:
            s = s.replace(u" ", u' ') # nnbsp
            bChange = True
        if u"@" in s:
            s = s.replace(u"@", u' ')
            bChange = True
        if u"'" in s:
            s = s.replace(u"'", u"’")
            bChange = True
        if u"‑" in s:
            s = s.replace(u"‑", u"-") # nobreakdash
            bChange = True

    bIdRule = option('idrule')

    for sOption, lRuleGroup in _getRules(bParagraph):
        if not sOption or dOptions.get(sOption, False):
            for zRegex, bUppercase, sRuleId, lActions in lRuleGroup:
                if sRuleId not in _aIgnoredRules:
                    for m in zRegex.finditer(s):
                        for sFuncCond, cActionType, sWhat, *eAct in lActions:
                            # action in lActions: [ condition, action type, replacement/suggestion/action[, iGroup[, message, URL]] ]
                            try:
                                if not sFuncCond or _GLOBALS[sFuncCond](s, sx, m, dDA, sCountry):
                                    if cActionType == "-":
                                        # grammar error
                                        # (text, replacement, nOffset, m, iGroup, sId, bUppercase, sURL, bIdRule)
                                        aErrs.append(_createError(s, sWhat, nOffset, m, eAct[0], sRuleId, bUppercase, eAct[1], eAct[2], bIdRule, sOption))
                                    elif cActionType == "~":
                                        # text processor
                                        s = _rewrite(s, sWhat, eAct[0], m, bUppercase)
                                        bChange = True
                                        if bDebug:
                                            echo(u"~ " + s + "  -- " + m.group(eAct[0]) + "  # " + sRuleId)
                                    elif cActionType == "=":
                                        # disambiguation
                                        _GLOBALS[sWhat](s, m, dDA)
                                        if bDebug:
                                            echo(u"= " + m.group(0) + "  # " + sRuleId + "\nDA: " + str(dDA))
                                    else:
                                        echo("# error: unknown action at " + sRuleId)
                            except Exception as e:
                                raise Exception(str(e), sRuleId)
    if bChange:
        return (s, aErrs)
    return (False, aErrs)


def _createWriterError (s, sRepl, nOffset, m, iGroup, sId, bUppercase, sMsg, sURL, bIdRule, sOption):
    "error for Writer (LO/OO)"
    xErr = SingleProofreadingError()
    #xErr = uno.createUnoStruct( "com.sun.star.linguistic2.SingleProofreadingError" )
    xErr.nErrorStart        = nOffset + m.start(iGroup)
    xErr.nErrorLength       = m.end(iGroup) - m.start(iGroup)
    xErr.nErrorType         = PROOFREADING
    xErr.aRuleIdentifier    = sId
    # suggestions
    if sRepl[0:1] == "=":
        sugg = _GLOBALS[sRepl[1:]](s, m)
        if sugg:
            if bUppercase and m.group(iGroup)[0:1].isupper():
                xErr.aSuggestions = tuple(map(str.capitalize, sugg.split("|")))
            else:
                xErr.aSuggestions = tuple(sugg.split("|"))
        else:
            xErr.aSuggestions = ()
    elif sRepl == "_":
        xErr.aSuggestions = ()
    else:
        if bUppercase and m.group(iGroup)[0:1].isupper():
            xErr.aSuggestions = tuple(map(str.capitalize, m.expand(sRepl).split("|")))
        else:
            xErr.aSuggestions = tuple(m.expand(sRepl).split("|"))
    # Message
    if sMsg[0:1] == "=":
        sMessage = _GLOBALS[sMsg[1:]](s, m)
    else:
        sMessage = m.expand(sMsg)
    xErr.aShortComment      = sMessage   # sMessage.split("|")[0]     # in context menu
    xErr.aFullComment       = sMessage   # sMessage.split("|")[-1]    # in dialog
    if bIdRule:
        xErr.aShortComment += "  # " + sId
    # URL
    if sURL:
        p = PropertyValue()
        p.Name = "FullCommentURL"
        p.Value = sURL
        xErr.aProperties    = (p,)
    else:
        xErr.aProperties    = ()
    return xErr


def _createDictError (s, sRepl, nOffset, m, iGroup, sId, bUppercase, sMsg, sURL, bIdRule, sOption):
    "error as a dictionary"
    dErr = {}
    dErr["nStart"]          = nOffset + m.start(iGroup)
    dErr["nEnd"]            = nOffset + m.end(iGroup)
    dErr["sRuleId"]         = sId
    dErr["sType"]           = sOption  if sOption  else "notype"
    # suggestions
    if sRepl[0:1] == "=":
        sugg = _GLOBALS[sRepl[1:]](s, m)
        if sugg:
            if bUppercase and m.group(iGroup)[0:1].isupper():
                dErr["aSuggestions"] = list(map(str.capitalize, sugg.split("|")))
            else:
                dErr["aSuggestions"] = sugg.split("|")
        else:
            dErr["aSuggestions"] = ()
    elif sRepl == "_":
        dErr["aSuggestions"] = ()
    else:
        if bUppercase and m.group(iGroup)[0:1].isupper():
            dErr["aSuggestions"] = list(map(str.capitalize, m.expand(sRepl).split("|")))
        else:
            dErr["aSuggestions"] = m.expand(sRepl).split("|")
    # Message
    if sMsg[0:1] == "=":
        sMessage = _GLOBALS[sMsg[1:]](s, m)
    else:
        sMessage = m.expand(sMsg)
    dErr["sMessage"]      = sMessage
    if bIdRule:
        dErr["sMessage"] += "  # " + sId
    # URL
    dErr["URL"] = sURL  if sURL  else ""
    return dErr


def _rewrite (s, sRepl, iGroup, m, bUppercase):
    "text processor: write sRepl in s at iGroup position"
    ln = m.end(iGroup) - m.start(iGroup)
    if sRepl == "*":
        sNew = " " * ln
    elif sRepl == ">" or sRepl == "_" or sRepl == u"~":
        sNew = sRepl + " " * (ln-1)
    elif sRepl == "@":
        sNew = "@" * ln
    elif sRepl[0:1] == "=":
        if sRepl[1:2] != "@":
            sNew = _GLOBALS[sRepl[1:]](s, m)
            sNew = sNew + " " * (ln-len(sNew))
        else:
            sNew = _GLOBALS[sRepl[2:]](s, m)
            sNew = sNew + "@" * (ln-len(sNew))
        if bUppercase and m.group(iGroup)[0:1].isupper():
            sNew = sNew.capitalize()
    else:
        sNew = m.expand(sRepl)
        sNew = sNew + " " * (ln-len(sNew))
    return s[0:m.start(iGroup)] + sNew + s[m.end(iGroup):]


def ignoreRule (sId):
    _aIgnoredRules.add(sId)


def resetIgnoreRules ():
    _aIgnoredRules.clear()


#### init

try:
    # LibreOffice / OpenOffice
    from com.sun.star.linguistic2 import SingleProofreadingError
    from com.sun.star.text.TextMarkupType import PROOFREADING
    from com.sun.star.beans import PropertyValue
    #import lightproof_handler_grammalecte as opt
    _createError = _createWriterError
except ImportError:
    _createError = _createDictError


def load ():
    global _oDict
    try:
        _oDict = IBDAWG("french.bdic")
    except:
        traceback.print_exc()


def setOptions (dOpt):
    _dOptions.update(dOpt)


def getOptions ():
    return _dOptions


def getOptionsLabels (sLang):
    return gc_options.getUI(sLang)


def resetOptions ():
    global _dOptions
    _dOptions = dict(gc_options.dOpt)


def getDictionary ():
    return _oDict


def _getRules (bParagraph):
    try:
        if not bParagraph:
            return _rules.lSentenceRules
        return _rules.lParagraphRules
    except:
        _loadRules()
    if not bParagraph:
        return _rules.lSentenceRules
    return _rules.lParagraphRules


def _loadRules2 ():
    from itertools import chain
    from . import gc_rules
    global _rules
    _rules = gc_rules
    # compile rules regex
    for rule in chain(_rules.lParagraphRules, _rules.lSentenceRules):
        try:
            rule[1] = re.compile(rule[1])
        except:
            echo("Bad regular expression in # " + str(rule[3]))
            rule[1] = "(?i)<Grammalecte>"


def _loadRules ():
    from itertools import chain
    from . import gc_rules
    global _rules
    _rules = gc_rules
    # compile rules regex
    for rulegroup in chain(_rules.lParagraphRules, _rules.lSentenceRules):
        for rule in rulegroup[1]:
            try:
                rule[0] = re.compile(rule[0])
            except:
                echo("Bad regular expression in # " + str(rule[2]))
                rule[0] = "(?i)<Grammalecte>"


def _getPath ():
    return os.path.join(os.path.dirname(sys.modules[__name__].__file__), __name__ + ".py")



#### common functions

def option (sOpt):
    "return True if option sOpt is active"
    return _dOptions.get(sOpt, False)


def displayInfo (dDA, tWord):
    "for debugging: retrieve info of word"
    if not tWord:
        echo("> nothing to find")
        return True
    if tWord[1] not in _dAnalyses and not _storeMorphFromFSA(tWord[1]):
        echo("> not in FSA")
        return True
    if tWord[0] in dDA:
        echo("DA: " + str(dDA[tWord[0]]))
    echo("FSA: " + str(_dAnalyses[tWord[1]]))
    return True


def _storeMorphFromFSA (sWord):
    "retrieves morphologies list from _oDict -> _dAnalyses"
    global _dAnalyses
    _dAnalyses[sWord] = _oDict.getMorph(sWord)
    return True  if _dAnalyses[sWord]  else False


def morph (dDA, tWord, sPattern, bStrict=True, bNoWord=False):
    "analyse a tuple (position, word), return True if sPattern in morphologies (disambiguation on)"
    if not tWord:
        return bNoWord
    if tWord[1] not in _dAnalyses and not _storeMorphFromFSA(tWord[1]):
        return False
    lMorph = dDA[tWord[0]]  if tWord[0] in dDA  else _dAnalyses[tWord[1]]
    if not lMorph:
        return False
    p = re.compile(sPattern)
    if bStrict:
        return all(p.search(s)  for s in lMorph)
    return any(p.search(s)  for s in lMorph)


def morphex (dDA, tWord, sPattern, sNegPattern, bNoWord=False):
    "analyse a tuple (position, word), returns True if not sNegPattern in word morphologies and sPattern in word morphologies (disambiguation on)"
    if not tWord:
        return bNoWord
    if tWord[1] not in _dAnalyses and not _storeMorphFromFSA(tWord[1]):
        return False
    lMorph = dDA[tWord[0]]  if tWord[0] in dDA  else _dAnalyses[tWord[1]]
    # check negative condition
    np = re.compile(sNegPattern)
    if any(np.search(s)  for s in lMorph):
        return False
    # search sPattern
    p = re.compile(sPattern)
    return any(p.search(s)  for s in lMorph)


def analyse (sWord, sPattern, bStrict=True):
    "analyse a word, return True if sPattern in morphologies (disambiguation off)"
    if sWord not in _dAnalyses and not _storeMorphFromFSA(sWord):
        return False
    if not _dAnalyses[sWord]:
        return False
    p = re.compile(sPattern)
    if bStrict:
        return all(p.search(s)  for s in _dAnalyses[sWord])
    return any(p.search(s)  for s in _dAnalyses[sWord])


def analysex (sWord, sPattern, sNegPattern):
    "analyse a word, returns True if not sNegPattern in word morphologies and sPattern in word morphologies (disambiguation off)"
    if sWord not in _dAnalyses and not _storeMorphFromFSA(sWord):
        return False
    # check negative condition
    np = re.compile(sNegPattern)
    if any(np.search(s)  for s in _dAnalyses[sWord]):
        return False
    # search sPattern
    p = re.compile(sPattern)
    return any(p.search(s)  for s in _dAnalyses[sWord])


def stem (sWord):
    "returns a list of sWord's stems"
    if not sWord:
        return []
    if sWord not in _dAnalyses and not _storeMorphFromFSA(sWord):
        return []
    return [ s[1:s.find(" ")]  for s in _dAnalyses[sWord] ]


## functions to get text outside pattern scope

# warning: check compile_rules.py to understand how it works

def nextword (s, iStart, n):
    "get the nth word of the input string or empty string"
    m = re.match(u"( +[\\w%-]+){" + str(n-1) + u"} +([\\w%-]+)", s[iStart:])
    if not m:
        return None
    return (iStart+m.start(2), m.group(2))


def prevword (s, iEnd, n):
    "get the (-)nth word of the input string or empty string"
    m = re.search(u"([\\w%-]+) +([\\w%-]+ +){" + str(n-1) + u"}$", s[:iEnd])
    if not m:
        return None
    return (m.start(1), m.group(1))


def nextword1 (s, iStart):
    "get next word (optimization)"
    m = _zNextWord.match(s[iStart:])
    if not m:
        return None
    return (iStart+m.start(1), m.group(1))


def prevword1 (s, iEnd):
    "get previous word (optimization)"
    m = _zPrevWord.search(s[:iEnd])
    if not m:
        return None
    return (m.start(1), m.group(1))


def look (s, sPattern, sNegPattern=None):
    "seek sPattern in s (before/after/fulltext), if sNegPattern not in s"
    if sNegPattern and re.search(sNegPattern, s):
        return False
    if re.search(sPattern, s):
        return True
    return False


def look_chk1 (dDA, s, nOffset, sPattern, sPatternGroup1, sNegPatternGroup1=None):
    "returns True if s has pattern sPattern and m.group(1) has pattern sPatternGroup1"
    m = re.search(sPattern, s)
    if not m:
        return False
    try:
        sWord = m.group(1)
        nPos = m.start(1) + nOffset
    except:
        #print("Missing group 1")
        return False
    if sNegPatternGroup1:
        return morphex(dDA, (nPos, sWord), sPatternGroup1, sNegPatternGroup1)
    return morph(dDA, (nPos, sWord), sPatternGroup1, False)


#### Disambiguator

def select (dDA, nPos, sWord, sPattern, lDefault=None):
    if not sWord:
        return True
    if nPos in dDA:
        return True
    if sWord not in _dAnalyses and not _storeMorphFromFSA(sWord):
        return True
    if len(_dAnalyses[sWord]) == 1:
        return True
    lSelect = [ sMorph  for sMorph in _dAnalyses[sWord]  if re.search(sPattern, sMorph) ]
    if lSelect:
        if len(lSelect) != len(_dAnalyses[sWord]):
            dDA[nPos] = lSelect
            #echo("= "+sWord+" "+str(dDA.get(nPos, "null")))
    elif lDefault:
        dDA[nPos] = lDefault
        #echo("= "+sWord+" "+str(dDA.get(nPos, "null")))
    return True


def exclude (dDA, nPos, sWord, sPattern, lDefault=None):
    if not sWord:
        return True
    if nPos in dDA:
        return True
    if sWord not in _dAnalyses and not _storeMorphFromFSA(sWord):
        return True
    if len(_dAnalyses[sWord]) == 1:
        return True
    lSelect = [ sMorph  for sMorph in _dAnalyses[sWord]  if not re.search(sPattern, sMorph) ]
    if lSelect:
        if len(lSelect) != len(_dAnalyses[sWord]):
            dDA[nPos] = lSelect
            #echo("= "+sWord+" "+str(dDA.get(nPos, "null")))
    elif lDefault:
        dDA[nPos] = lDefault
        #echo("= "+sWord+" "+str(dDA.get(nPos, "null")))
    return True


def define (dDA, nPos, lMorph):
    dDA[nPos] = lMorph
    #echo("= "+str(nPos)+" "+str(dDA[nPos]))
    return True


#### GRAMMAR CHECKER PLUGINS



#### GRAMMAR CHECKING ENGINE PLUGIN: Parsing functions for French language

from . import cregex as cr


def rewriteSubject (s1, s2):
    # s1 is supposed to be prn/patr/npr (M[12P])
    if s2 == "lui":
        return "ils"
    if s2 == "moi":
        return "nous"
    if s2 == "toi":
        return "vous"
    if s2 == "nous":
        return "nous"
    if s2 == "vous":
        return "vous"
    if s2 == "eux":
        return "ils"
    if s2 == "elle" or s2 == "elles":
        # We don’t check if word exists in _dAnalyses, for it is assumed it has been done before
        if cr.mbNprMasNotFem(_dAnalyses.get(s1, False)):
            return "ils"
        # si épicène, indéterminable, mais OSEF, le féminin l’emporte
        return "elles"
    return s1 + " et " + s2


def apposition (sWord1, sWord2):
    "returns True if nom + nom (no agreement required)"
    # We don’t check if word exists in _dAnalyses, for it is assumed it has been done before
    return cr.mbNomNotAdj(_dAnalyses.get(sWord2, False)) and cr.mbPpasNomNotAdj(_dAnalyses.get(sWord1, False))


def isAmbiguousNAV (sWord):
    "words which are nom|adj and verb are ambiguous (except être and avoir)"
    if sWord not in _dAnalyses and not _storeMorphFromFSA(sWord):
        return False
    if not cr.mbNomAdj(_dAnalyses[sWord]) or sWord == "est":
        return False
    if cr.mbVconj(_dAnalyses[sWord]) and not cr.mbMG(_dAnalyses[sWord]):
        return True
    return False


def isAmbiguousAndWrong (sWord1, sWord2, sReqMorphNA, sReqMorphConj):
    "use it if sWord1 won’t be a verb; word2 is assumed to be True via isAmbiguousNAV"
    # We don’t check if word exists in _dAnalyses, for it is assumed it has been done before
    a2 = _dAnalyses.get(sWord2, None)
    if not a2:
        return False
    if cr.checkConjVerb(a2, sReqMorphConj):
        # verb word2 is ok
        return False
    a1 = _dAnalyses.get(sWord1, None)
    if not a1:
        return False
    if cr.checkAgreement(a1, a2) and (cr.mbAdj(a2) or cr.mbAdj(a1)):
        return False
    return True


def isVeryAmbiguousAndWrong (sWord1, sWord2, sReqMorphNA, sReqMorphConj, bLastHopeCond):
    "use it if sWord1 can be also a verb; word2 is assumed to be True via isAmbiguousNAV"
    # We don’t check if word exists in _dAnalyses, for it is assumed it has been done before
    a2 = _dAnalyses.get(sWord2, None)
    if not a2:
        return False
    if cr.checkConjVerb(a2, sReqMorphConj):
        # verb word2 is ok
        return False
    a1 = _dAnalyses.get(sWord1, None)
    if not a1:
        return False
    if cr.checkAgreement(a1, a2) and (cr.mbAdj(a2) or cr.mbAdjNb(a1)):
        return False
    # now, we know there no agreement, and conjugation is also wrong
    if cr.isNomAdj(a1):
        return True
    #if cr.isNomAdjVerb(a1): # considered True
    if bLastHopeCond:
        return True
    return False


def checkAgreement (sWord1, sWord2):
    # We don’t check if word exists in _dAnalyses, for it is assumed it has been done before
    a2 = _dAnalyses.get(sWord2, None)
    if not a2:
        return True
    a1 = _dAnalyses.get(sWord1, None)
    if not a1:
        return True
    return cr.checkAgreement(a1, a2)


_zUnitSpecial = re.compile(u"[µ/⁰¹²³⁴⁵⁶⁷⁸⁹Ωℓ·]")
_zUnitNumbers = re.compile(u"[0-9]")

def mbUnit (s):
    if _zUnitSpecial.search(s):
        return True
    if 1 < len(s) < 16 and s[0:1].islower() and (not s[1:].islower() or _zUnitNumbers.search(s)):
        return True
    return False


#### Syntagmes

_zEndOfNG1 = re.compile(u" +(?:, +|)(?:n(?:’|e |o(?:u?s|tre) )|l(?:’|e(?:urs?|s|) |a )|j(?:’|e )|m(?:’|es? |a |on )|t(?:’|es? |a |u )|s(?:’|es? |a )|c(?:’|e(?:t|tte|s|) )|ç(?:a |’)|ils? |vo(?:u?s|tre) )")
_zEndOfNG2 = re.compile(r" +(\w[\w-]+)")
_zEndOfNG3 = re.compile(r" *, +(\w[\w-]+)")


def isEndOfNG (dDA, s, iOffset):
    if _zEndOfNG1.match(s):
        return True
    m = _zEndOfNG2.match(s)
    if m and morphex(dDA, (iOffset+m.start(1), m.group(1)), ":[VR]", ":[NAQP]"):
        return True
    m = _zEndOfNG3.match(s)
    if m and not morph(dDA, (iOffset+m.start(1), m.group(1)), ":[NA]", False):
        return True
    return False


#### Exceptions

aREGULARPLURAL = frozenset(["abricot", "amarante", "aubergine", "acajou", "anthracite", "brique", "caca", u"café", "carotte", "cerise", "chataigne", "corail", "citron", u"crème", "grave", "groseille", "jonquille", "marron", "olive", "pervenche", "prune", "sable"])
aSHOULDBEVERB = frozenset(["aller", "manger"]) 


#### GRAMMAR CHECKING ENGINE PLUGIN

#### Check date validity

_lDay = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_dMonth = { "janvier":1, u"février":2, "mars":3, "avril":4, "mai":5, "juin":6, "juillet":7, u"août":8, "aout":8, "septembre":9, "octobre":10, "novembre":11, u"décembre":12 }

import datetime

def checkDate (day, month, year):
    "to use if month is a number"
    try:
        return datetime.date(int(year), int(month), int(day))
    except ValueError:
        return False
    except:
        return True

def checkDateWithString (day, month, year):
    "to use if month is a noun"
    try:
        return datetime.date(int(year), _dMonth.get(month.lower(), ""), int(day))
    except ValueError:
        return False
    except:
        return True

def checkDay (weekday, day, month, year):
    "to use if month is a number"
    oDate = checkDate(day, month, year)
    if oDate and _lDay[oDate.weekday()] != weekday.lower():
        return False
    return True
        
def checkDayWithString (weekday, day, month, year):
    "to use if month is a noun"
    oDate = checkDate(day, _dMonth.get(month, ""), year)
    if oDate and _lDay[oDate.weekday()] != weekday.lower():
        return False
    return True

def getDay (day, month, year):
    "to use if month is a number"
    return _lDay[datetime.date(int(year), int(month), int(day)).weekday()]

def getDayWithString (day, month, year):
    "to use if month is a noun"
    return _lDay[datetime.date(int(year), _dMonth.get(month.lower(), ""), int(day)).weekday()]


#### GRAMMAR CHECKING ENGINE PLUGIN: Suggestion mechanisms

from . import conj
from . import mfsp
from . import phonet


## Verbs

def suggVerb (sFlex, sWho, funcSugg2=None):
    aSugg = set()
    for sStem in stem(sFlex):
        tTags = conj._getTags(sStem)
        if tTags:
            # we get the tense
            aTense = set()
            for sMorph in _dAnalyses.get(sFlex, []): # we don’t check if word exists in _dAnalyses, for it is assumed it has been done before
                for m in re.finditer(sStem+" .*?(:(?:Y|I[pqsf]|S[pq]|K|P))", sMorph):
                    # stem must be used in regex to prevent confusion between different verbs (e.g. sauras has 2 stems: savoir and saurer)
                    if m:
                        if m.group(1) == ":Y":
                            aTense.add(":Ip")
                            aTense.add(":Iq")
                            aTense.add(":Is")
                        elif m.group(1) == ":P":
                            aTense.add(":Ip")
                        else:
                            aTense.add(m.group(1))
            for sTense in aTense:
                if sWho == u":1ś" and not conj._hasConjWithTags(tTags, sTense, u":1ś"):
                    sWho = ":1s"
                if conj._hasConjWithTags(tTags, sTense, sWho):
                    aSugg.add(conj._getConjWithTags(sStem, tTags, sTense, sWho))
    if funcSugg2:
        aSugg2 = funcSugg2(sFlex)
        if aSugg2:
            aSugg.add(aSugg2)
    if aSugg:
        return u"|".join(aSugg)
    return ""


def suggVerbPpas (sFlex, sWhat=None):
    aSugg = set()
    for sStem in stem(sFlex):
        tTags = conj._getTags(sStem)
        if tTags:
            if not sWhat:
                aSugg.add(conj._getConjWithTags(sStem, tTags, ":PQ", ":Q1"))
                aSugg.add(conj._getConjWithTags(sStem, tTags, ":PQ", ":Q2"))
                aSugg.add(conj._getConjWithTags(sStem, tTags, ":PQ", ":Q3"))
                aSugg.add(conj._getConjWithTags(sStem, tTags, ":PQ", ":Q4"))
                aSugg.discard("")
            elif sWhat == ":m:s":
                aSugg.add(conj._getConjWithTags(sStem, tTags, ":PQ", ":Q1"))
            elif sWhat == ":m:p":
                if conj._hasConjWithTags(tTags, ":PQ", ":Q2"):
                    aSugg.add(conj._getConjWithTags(sStem, tTags, ":PQ", ":Q2"))
                else:
                    aSugg.add(conj._getConjWithTags(sStem, tTags, ":PQ", ":Q1"))
            elif sWhat == ":f:s":
                if conj._hasConjWithTags(sStem, tTags, ":PQ", ":Q3"):
                    aSugg.add(conj._getConjWithTags(sStem, tTags, ":PQ", ":Q3"))
                else:
                    aSugg.add(conj._getConjWithTags(sStem, tTags, ":PQ", ":Q1"))
            elif sWhat == ":f:p":
                if conj._hasConjWithTags(sStem, tTags, ":PQ", ":Q4"):
                    aSugg.add(conj._getConjWithTags(sStem, tTags, ":PQ", ":Q4"))
                else:
                    aSugg.add(conj._getConjWithTags(sStem, tTags, ":PQ", ":Q1"))
            else:
                aSugg.add(conj._getConjWithTags(sStem, tTags, ":PQ", ":Q1"))
    if aSugg:
        return u"|".join(aSugg)
    return ""


def suggVerbTense (sFlex, sTense, sWho):
    aSugg = set()
    for sStem in stem(sFlex):
        if conj.hasConj(sStem, ":E", sWho):
            aSugg.add(conj.getConj(sStem, ":E", sWho))
    if aSugg:
        return u"|".join(aSugg)
    return ""


def suggVerbImpe (sFlex):
    aSugg = set()
    for sStem in stem(sFlex):
        tTags = conj._getTags(sStem)
        if tTags:
            if conj._hasConjWithTags(tTags, ":E", ":2s"):
                aSugg.add(conj._getConjWithTags(sStem, tTags, ":E", ":2s"))
            if conj._hasConjWithTags(tTags, ":E", ":1p"):
                aSugg.add(conj._getConjWithTags(sStem, tTags, ":E", ":1p"))
            if conj._hasConjWithTags(tTags, ":E", ":2p"):
                aSugg.add(conj._getConjWithTags(sStem, tTags, ":E", ":2p"))
    if aSugg:
        return u"|".join(aSugg)
    return ""


def suggVerbInfi (sFlex):
    return u"|".join(stem(sFlex))


_dQuiEst = { "je": ":1s", u"j’": ":1s", u"j’en": ":1s", u"j’y": ":1s", \
             "tu": ":2s", "il": ":3s", "on": ":3s", "elle": ":3s", "nous": ":1p", "vous": ":2p", "ils": ":3p", "elles": ":3p" }
_lIndicatif = [":Ip", ":Iq", ":Is", ":If"]
_lSubjonctif = [":Sp", ":Sq"]

def suggVerbMode (sFlex, cMode, sSuj):
    if cMode == ":I":
        lMode = _lIndicatif
    elif cMode == ":S":
        lMode = _lSubjonctif
    elif cMode.startswith((":I", ":S")):
        lMode = [cMode]
    else:
        return ""
    sWho = _dQuiEst.get(sSuj.lower(), None)
    if not sWho:
        if sSuj[0:1].islower(): # pas un pronom, ni un nom propre
            return ""
        sWho = ":3s"
    aSugg = set()
    for sStem in stem(sFlex):
        tTags = conj._getTags(sStem)
        if tTags:
            for sTense in lMode:
                if conj._hasConjWithTags(tTags, sTense, sWho):
                    aSugg.add(conj._getConjWithTags(sStem, tTags, sTense, sWho))
    if aSugg:
        return u"|".join(aSugg)
    return ""


## Nouns and adjectives

def suggPlur (sFlex, sWordToAgree=None):
    "returns plural forms assuming sFlex is singular"
    if sWordToAgree:
        if sWordToAgree not in _dAnalyses and not _storeMorphFromFSA(sWordToAgree):
            return ""
        sGender = cr.getGender(_dAnalyses.get(sWordToAgree, []))
        if sGender == ":m":
            return suggMasPlur(sFlex)
        elif sGender == ":f":
            return suggFemPlur(sFlex)
    aSugg = set()
    if "-" not in sFlex:
        if sFlex.endswith("l"):
            if sFlex.endswith("al") and len(sFlex) > 2 and _oDict.isValid(sFlex[:-1]+"ux"):
                aSugg.add(sFlex[:-1]+"ux")
            if sFlex.endswith("ail") and len(sFlex) > 3 and _oDict.isValid(sFlex[:-2]+"ux"):
                aSugg.add(sFlex[:-2]+"ux")
        if _oDict.isValid(sFlex+"s"):
            aSugg.add(sFlex+"s")
        if _oDict.isValid(sFlex+"x"):
            aSugg.add(sFlex+"x")
    if mfsp.hasMiscPlural(sFlex):
        aSugg.update(mfsp.getMiscPlural(sFlex))
    if aSugg:
        return u"|".join(aSugg)
    return ""


def suggSing (sFlex):
    "returns singular forms assuming sFlex is plural"
    if "-" in sFlex:
        return ""
    aSugg = set()
    if sFlex.endswith("ux"):
        if _oDict.isValid(sFlex[:-2]+"l"):
            aSugg.add(sFlex[:-2]+"l")
        if _oDict.isValid(sFlex[:-2]+"il"):
            aSugg.add(sFlex[:-2]+"il")
    if _oDict.isValid(sFlex[:-1]):
        aSugg.add(sFlex[:-1])
    if aSugg:
        return u"|".join(aSugg)
    return ""


def suggMasSing (sFlex):
    "returns masculine singular forms"
    # we don’t check if word exists in _dAnalyses, for it is assumed it has been done before
    aSugg = set()
    for sMorph in _dAnalyses.get(sFlex, []):
        if not ":V" in sMorph:
            # not a verb
            if ":m" in sMorph or ":e" in sMorph:
                aSugg.add(suggSing(sFlex))
            else:
                sStem = cr.getLemmaOfMorph(sMorph)
                if mfsp.isFemForm(sStem):
                    aSugg.update(mfsp.getMasForm(sStem, False))
        else:
            # a verb
            sVerb = cr.getLemmaOfMorph(sMorph)
            if conj.hasConj(sVerb, ":PQ", ":Q1"):
                aSugg.add(conj.getConj(sVerb, ":PQ", ":Q1"))
    if aSugg:
        return u"|".join(aSugg)
    return ""


def suggMasPlur (sFlex):
    "returns masculine plural forms"
    # we don’t check if word exists in _dAnalyses, for it is assumed it has been done before
    aSugg = set()
    for sMorph in _dAnalyses.get(sFlex, []):
        if not ":V" in sMorph:
            # not a verb
            if ":m" in sMorph or ":e" in sMorph:
                aSugg.add(suggPlur(sFlex))
            else:
                sStem = cr.getLemmaOfMorph(sMorph)
                if mfsp.isFemForm(sStem):
                    aSugg.update(mfsp.getMasForm(sStem, True))
        else:
            # a verb
            sVerb = cr.getLemmaOfMorph(sMorph)
            if conj.hasConj(sVerb, ":PQ", ":Q2"):
                aSugg.add(conj.getConj(sVerb, ":PQ", ":Q2"))
            elif conj.hasConj(sVerb, ":PQ", ":Q1"):
                aSugg.add(conj.getConj(sVerb, ":PQ", ":Q1"))
    if aSugg:
        return u"|".join(aSugg)
    return ""


def suggFemSing (sFlex):
    "returns feminine singular forms"
    # we don’t check if word exists in _dAnalyses, for it is assumed it has been done before
    aSugg = set()
    for sMorph in _dAnalyses.get(sFlex, []):
        if not ":V" in sMorph:
            # not a verb
            if ":f" in sMorph or ":e" in sMorph:
                aSugg.add(suggSing(sFlex))
            else:
                sStem = cr.getLemmaOfMorph(sMorph)
                if mfsp.isFemForm(sStem):
                    aSugg.add(sStem)
        else:
            # a verb
            sVerb = cr.getLemmaOfMorph(sMorph)
            if conj.hasConj(sVerb, ":PQ", ":Q3"):
                aSugg.add(conj.getConj(sVerb, ":PQ", ":Q3"))
    if aSugg:
        return u"|".join(aSugg)
    return ""


def suggFemPlur (sFlex):
    "returns feminine plural forms"
    # we don’t check if word exists in _dAnalyses, for it is assumed it has been done before
    aSugg = set()
    for sMorph in _dAnalyses.get(sFlex, []):
        if not ":V" in sMorph:
            # not a verb
            if ":f" in sMorph or ":e" in sMorph:
                aSugg.add(suggPlur(sFlex))
            else:
                sStem = cr.getLemmaOfMorph(sMorph)
                if mfsp.isFemForm(sStem):
                    aSugg.add(sStem+"s")
        else:
            # a verb
            sVerb = cr.getLemmaOfMorph(sMorph)
            if conj.hasConj(sVerb, ":PQ", ":Q4"):
                aSugg.add(conj.getConj(sVerb, ":PQ", ":Q4"))
    if aSugg:
        return u"|".join(aSugg)
    return ""


def switchGender (sFlex, bPlur=None):
    # we don’t check if word exists in _dAnalyses, for it is assumed it has been done before
    aSugg = set()
    if bPlur == None:
        for sMorph in _dAnalyses.get(sFlex, []):
            if ":f" in sMorph:
                if ":s" in sMorph:
                    aSugg.add(suggMasSing(sFlex))
                elif ":p" in sMorph:
                    aSugg.add(suggMasPlur(sFlex))
            elif ":m" in sMorph:
                if ":s" in sMorph:
                    aSugg.add(suggFemSing(sFlex))
                elif ":p" in sMorph:
                    aSugg.add(suggFemPlur(sFlex))
                else:
                    aSugg.add(suggFemSing(sFlex))
                    aSugg.add(suggFemPlur(sFlex))
    elif bPlur:
        for sMorph in _dAnalyses.get(sFlex, []):
            if ":f" in sMorph:
                aSugg.add(suggMasPlur(sFlex))
            elif ":m" in sMorph:
                aSugg.add(suggFemPlur(sFlex))
    else:
        for sMorph in _dAnalyses.get(sFlex, []):
            if ":f" in sMorph:
                aSugg.add(suggMasSing(sFlex))
            elif ":m" in sMorph:
                aSugg.add(suggFemSing(sFlex))
    if aSugg:
        return u"|".join(aSugg)
    return ""


def switchPlural (sFlex):
    # we don’t check if word exists in _dAnalyses, for it is assumed it has been done before
    aSugg = set()
    for sMorph in _dAnalyses.get(sFlex, []):
        if ":s" in sMorph:
            aSugg.add(suggPlur(sFlex))
        elif ":p" in sMorph:
            aSugg.add(suggSing(sFlex))
    if aSugg:
        return u"|".join(aSugg)
    return ""


def hasSimil (sWord):
    return phonet.hasSimil(sWord)


def suggSimil (sWord, sPattern):
    "return list of words phonetically similar to sWord and whom POS is matching sPattern"
    # we don’t check if word exists in _dAnalyses, for it is assumed it has been done before
    lSet = phonet.getSimil(sWord)
    if not lSet:
        return ""
    aSugg = set()
    for sSimil in lSet:
        if sSimil not in _dAnalyses:
            _storeMorphFromFSA(sSimil)
        for sMorph in _dAnalyses.get(sSimil, []):
            if re.search(sPattern, sMorph):
                aSugg.add(sSimil)
    if aSugg:
        return u"|".join(aSugg)
    return ""


def suggCeOrCet (s):
    if re.match("(?i)[aeéèêiouyâîï]", s):
        return "cet"
    if s[0:1] == "h" or s[0:1] == "H":
        return "ce|cet"
    return "ce"


def formatNumber (s):
    nLen = len(s)
    if nLen == 10:
        sRes = s[0] + u" " + s[1:4] + u" " + s[4:7] + u" " + s[7:]                                  # nombre ordinaire
        if s.startswith("0"):
            sRes += u"|" + s[0:2] + u" " + s[2:4] + u" " + s[4:6] + u" " + s[6:8] + u" " + s[8:]    # téléphone français
            if s[1] == "4" and (s[2]=="7" or s[2]=="8" or s[2]=="9"):
                sRes += u"|" + s[0:4] + u" " + s[4:6] + u" " + s[6:8] + u" " + s[8:]                # mobile belge
            sRes += u"|" + s[0:3] + u" " + s[3:6] + u" " + s[6:8] + u" " + s[8:]                    # téléphone suisse
        sRes += u"|" + s[0:4] + u" " + s[4:7] + "-" + s[7:]                                         # téléphone canadien ou américain
        return sRes
    elif nLen == 9:
        sRes = s[0:3] + u" " + s[3:6] + u" " + s[6:]                                                # nombre ordinaire
        if s.startswith("0"):
            sRes += "|" + s[0:3] + u" " + s[3:5] + u" " + s[5:7] + u" " + s[7:9]                    # fixe belge 1
            sRes += "|" + s[0:2] + u" " + s[2:5] + u" " + s[5:7] + u" " + s[7:9]                    # fixe belge 2
        return sRes
    elif nLen < 4:
        return ""
    sRes = ""
    nEnd = nLen
    while nEnd > 0:
        nStart = max(nEnd-3, 0)
        sRes = s[nStart:nEnd] + u" " + sRes  if sRes  else s[nStart:nEnd]
        nEnd = nEnd - 3
    return sRes


def formatNF (s):
    try:
        m = re.match(u"NF[  -]?(C|E|P|Q|S|X|Z|EN(?:[  -]ISO|))[  -]?([0-9]+(?:[/‑-][0-9]+|))", s)
        if not m:
            return ""
        return u"NF " + m.group(1).upper().replace(" ", u" ").replace("-", u" ") + u" " + m.group(2).replace("/", u"‑").replace("-", u"‑")
    except:
        traceback.print_exc()
        return "# erreur #"


def undoLigature (c):
    if c == u"ﬁ":
        return "fi"
    elif c == u"ﬂ":
        return "fl"
    elif c == u"ﬀ":
        return "ff"
    elif c == u"ﬃ":
        return "ffi"
    elif c == u"ﬄ":
        return "ffl"
    elif c == u"ﬅ":
        return "ft"
    elif c == u"ﬆ":
        return "st"
    return "_"



# generated code, do not edit
def c64p_1 (s, sx, m, dDA, sCountry):
    return option("num")
def s64p_1 (s, m):
    return m.group(0).replace(".", u" ")
def p64p_2 (s, m):
    return m.group(0).replace(".", u" ")
def p77p_1 (s, m):
    return m.group(1).replace(".", "")+"."
def c79p_1 (s, sx, m, dDA, sCountry):
    return m.group(0) != "i.e." and m.group(0) != "s.t.p."
def s79p_1 (s, m):
    return m.group(0).replace(".", "").upper()
def p79p_2 (s, m):
    return m.group(0).replace(".", "")
def c83p_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^etc", m.group(1))
def c88p_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":M[12]", False) and (morph(dDA, (m.start(3), m.group(3)), ":(?:M[12]|V)", False) or not _oDict.isValid(m.group(3)))
def c89p_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":M[12]", False) and look(s[m.end():], "^\W+[a-zéèêîïâ]")
def c131p_1 (s, sx, m, dDA, sCountry):
    return option("typo") and not m.group(0).endswith("·e·s")
def c131p_2 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ]", False)
def d131p_2 (s, m, dDA):
    return define(dDA, m.start(0), ":N:A:Q:e:i")
def c143p_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^(?:etc|[A-Z]|chap|cf|fig|hab|litt|circ|coll|r[eé]f|étym|suppl|bibl|bibliogr|cit|op|vol|déc|nov|oct|janv|juil|avr|sept)$", m.group(1)) and morph(dDA, (m.start(1), m.group(1)), ":", False) and morph(dDA, (m.start(2), m.group(2)), ":", False)
def s143p_1 (s, m):
    return m.group(2).capitalize()
def c154p_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":[DR]", False)
def c184p_1 (s, sx, m, dDA, sCountry):
    return not m.group(1).isdigit()
def c186p_1 (s, sx, m, dDA, sCountry):
    return _oDict.isValid(m.group(1))
def s207p_1 (s, m):
    return m.group(1)[0:-1]
def s208p_1 (s, m):
    return "nᵒˢ"  if m.group(1)[1:3] == "os"  else "nᵒ"
def c216p_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], "(?i)etc$")
def s217p_1 (s, m):
    return m.group(0).replace("...", "…").rstrip(".")
def c233p_1 (s, sx, m, dDA, sCountry):
    return not re.search("^(?:etc|[A-Z]|fig|hab|litt|circ|coll|ref|étym|suppl|bibl|bibliogr|cit|vol|déc|nov|oct|janv|juil|avr|sept)$", m.group(1))
def s266p_1 (s, m):
    return m.group(0)[0] + "|" + m.group(0)[1]
def s267p_1 (s, m):
    return m.group(0)[0] + "|" + m.group(0)[1]
def s268p_1 (s, m):
    return m.group(0)[0] + "|" + m.group(0)[1]
def c277p_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(3), m.group(3)), ";S", ":[VCR]") or mbUnit(m.group(3)) or not _oDict.isValid(m.group(3))
def c281p_1 (s, sx, m, dDA, sCountry):
    return (not re.search("^[0-9][0-9]{1,3}$", m.group(2)) and not _oDict.isValid(m.group(3))) or morphex(dDA, (m.start(3), m.group(3)), ";S", ":[VCR]") or mbUnit(m.group(3))
def c303p_1 (s, sx, m, dDA, sCountry):
    return sCountry != "CA"
def s303p_1 (s, m):
    return " "+m.group(0)
def s349p_1 (s, m):
    return undoLigature(m.group(0))
def c395p_1 (s, sx, m, dDA, sCountry):
    return not option("mapos") and morph(dDA, (m.start(2), m.group(2)), ":V", False)
def s395p_1 (s, m):
    return m.group(1)[:-1]+u"’"
def c398p_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":V", False)
def s398p_1 (s, m):
    return m.group(1)[:-1]+u"’"
def c402p_1 (s, sx, m, dDA, sCountry):
    return option("mapos") and not look(s[:m.start()], "(?i)(?:lettre|caractère|glyphe|dimension|variable|fonction|point) *$")
def s402p_1 (s, m):
    return m.group(1)[:-1]+u"’"
def c416p_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^(?:onz[ei]|énième|iourte|ouistiti|ouate|one-?step|Ouagadougou|I(?:I|V|X|er|ᵉʳ|ʳᵉ|è?re))", m.group(2)) and not m.group(2).isupper() and not morph(dDA, (m.start(2), m.group(2)), ":G", False)
def s416p_1 (s, m):
    return m.group(1)[0]+u"’"
def c432p_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^(?:onz|énième)", m.group(2)) and morph(dDA, (m.start(2), m.group(2)), ":[me]")
def c440p_1 (s, sx, m, dDA, sCountry):
    return not re.search("^NF (?:C|E|P|Q|S|X|Z|EN(?: ISO|)) [0-9]+(?:‑[0-9]+|)", m.group(0))
def s440p_1 (s, m):
    return formatNF(m.group(0))
def s445p_1 (s, m):
    return m.group(0).replace("2", "₂").replace("3", "₃").replace("4", "₄")
def c453p_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], "NF[  -]?(C|E|P|Q|X|Z|EN(?:[  -]ISO|)) *")
def s453p_1 (s, m):
    return formatNumber(m.group(0))
def c467p_1 (s, sx, m, dDA, sCountry):
    return not option("ocr")
def s467p_1 (s, m):
    return m.group(0).replace("O", "0")
def c468p_1 (s, sx, m, dDA, sCountry):
    return not option("ocr")
def s468p_1 (s, m):
    return m.group(0).replace("O", "0")
def c486p_1 (s, sx, m, dDA, sCountry):
    return not checkDate(m.group(1), m.group(2), m.group(3)) and not look(s[:m.start()], r"(?i)\bversions? +$")
def c489p_1 (s, sx, m, dDA, sCountry):
    return not checkDateWithString(m.group(1), m.group(2), m.group(3))
def c492p_1 (s, sx, m, dDA, sCountry):
    return not look(s[m.end():], r"^ +av(?:ant|\.) J(?:\.-C\.|ésus-Christ)") and not checkDay(m.group(1), m.group(2), m.group(3), m.group(4))
def s492p_1 (s, m):
    return getDay(m.group(2), m.group(3), m.group(4))
def c497p_1 (s, sx, m, dDA, sCountry):
    return not look(s[m.end():], r"^ +av(?:ant|\.) J(?:\.-C\.|ésus-Christ)") and not checkDayWithString(m.group(1), m.group(2), m.group(3), m.group(4))
def s497p_1 (s, m):
    return getDayWithString(m.group(2), m.group(3), m.group(4))
def c535p_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0", False) or m.group(1) == "en"
def c542p_1 (s, sx, m, dDA, sCountry):
    return _oDict.isValid(m.group(1)+"-"+m.group(2)) and analyse(m.group(1)+"-"+m.group(2), ":", False)
def c546p_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[NB]", False)
def c547p_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[NB]", False) and not nextword1(s, m.end())
def c550p_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":N") and not re.search("(?i)^(?:aequo|nihilo|cathedra|absurdo|abrupto)", m.group(1))
def c552p_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ]", False)
def c553p_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":N", ":[AGW]")
def c556p_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ]", False)
def c558p_1 (s, sx, m, dDA, sCountry):
    return _oDict.isValid(m.group(1)+"-"+m.group(2)) and analyse(m.group(1)+"-"+m.group(2), ":", False)
def c562p_1 (s, sx, m, dDA, sCountry):
    return _oDict.isValid(m.group(1)+"-"+m.group(2)) and analyse(m.group(1)+"-"+m.group(2), ":", False) and morph(dDA, prevword1(s, m.start()), ":D", False, not bool(re.search("(?i)^s(?:ans|ous)$", m.group(1))))
def c566p_1 (s, sx, m, dDA, sCountry):
    return _oDict.isValid(m.group(1)+"-"+m.group(2)) and analyse(m.group(1)+"-"+m.group(2), ":N", False) and morph(dDA, prevword1(s, m.start()), ":(?:D|V0e)", False, True) and not (morph(dDA, (m.start(1), m.group(1)), ":G", False) and morph(dDA, (m.start(2), m.group(2)), ":[GYB]", False))
def s573p_1 (s, m):
    return m.group(0).replace(" ", "-")
def s574p_1 (s, m):
    return m.group(0).replace(" ", "-")
def c585p_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, prevword1(s, m.start()), ":Cs", False, True)
def s591p_1 (s, m):
    return m.group(0).replace(" ", "-")
def c597p_1 (s, sx, m, dDA, sCountry):
    return not nextword1(s, m.end())
def c599p_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, prevword1(s, m.start()), ":G")
def c603p_1 (s, sx, m, dDA, sCountry):
    return look(s[:m.start()], r"(?i)\b(?:les?|du|des|un|ces?|[mts]on) +")
def c610p_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":D", False)
def c612p_1 (s, sx, m, dDA, sCountry):
    return not ( morph(dDA, prevword1(s, m.start()), ":R", False) and look(s[m.end():], "^ +qu[e’]") )
def s660p_1 (s, m):
    return m.group(0).replace(" ", "-")
def c662p_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], "(?i)quatre $")
def s662p_1 (s, m):
    return m.group(0).replace(" ", "-").replace("vingts", "vingt")
def s664p_1 (s, m):
    return m.group(0).replace(" ", "-")
def s666p_1 (s, m):
    return m.group(0).replace(" ", "-").replace("vingts", "vingt")
def s690p_1 (s, m):
    return m.group(0).replace("-", " ")
def c692p_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":D", False, False)
def s695p_1 (s, m):
    return m.group(0).replace("-", " ")
def s696p_1 (s, m):
    return m.group(0).replace("-", " ")
def c744p_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":(?:G|V0)|>(?:t(?:antôt|emps|rès)|loin|souvent|parfois|quelquefois|côte|petit) ", False) and not m.group(1)[0].isupper()
def p760p_1 (s, m):
    return m.group(0).replace("‑", "")
def p761p_1 (s, m):
    return m.group(0).replace("‑", "")
def c797s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(0), m.group(0)), ":", False)
def c800s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":D", False)
def c801s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":A", False) and not morph(dDA, prevword1(s, m.start()), ":D", False)
def c838s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":(?:O[sp]|X)", False)
def d838s_1 (s, m, dDA):
    return select(dDA, m.start(1), m.group(1), ":V")
def d840s_1 (s, m, dDA):
    return select(dDA, m.start(1), m.group(1), ":V")
def c842s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":[YD]", False)
def d842s_1 (s, m, dDA):
    return exclude(dDA, m.start(1), m.group(1), ":V")
def d844s_1 (s, m, dDA):
    return exclude(dDA, m.start(1), m.group(1), ":V")
def d846s_1 (s, m, dDA):
    return exclude(dDA, m.start(1), m.group(1), ":V")
def c848s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":Y", False)
def d848s_1 (s, m, dDA):
    return exclude(dDA, m.start(1), m.group(1), ":V")
def c859s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":M", ":G") and not morph(dDA, (m.start(2), m.group(2)), ":N", False) and not prevword1(s, m.start())
def c869s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":E", False) and morph(dDA, (m.start(3), m.group(3)), ":M", False)
def c881s_1 (s, sx, m, dDA, sCountry):
    return option("mapos")
def s881s_1 (s, m):
    return m.group(1)[:-1]+"’"
def c888s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[GNAY]", ":(?:Q|3s)|>(?:priori|post[eé]riori|contrario|capella) ")
def c903s_1 (s, sx, m, dDA, sCountry):
    return not m.group(0).isdigit()
def s903s_1 (s, m):
    return m.group(0).replace("O", "0").replace("I", "1")
def s906s_1 (s, m):
    return m.group(0).replace("n", "u")
def c918s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\b([jn]’|il |on |elle )$")
def c921s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\b[jn]e +$")
def c927s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":N.*:f:s", False)
def c930s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":D.*:f:[si]")
def c933s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, nextword1(s, m.end()), ">(?:et|o[uù]) ")
def c942s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":D.*:p", False, False)
def c943s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, prevword1(s, m.start()), ":[VNA]", False, True)
def c947s_1 (s, sx, m, dDA, sCountry):
    return m.group(0).endswith("o")
def c947s_2 (s, sx, m, dDA, sCountry):
    return m.group(0).endswith("s") and not morph(dDA, prevword1(s, m.start()), ":D.*:[me]", False, False)
def c952s_1 (s, sx, m, dDA, sCountry):
    return m.group(0).endswith("s") and not morph(dDA, prevword1(s, m.start()), ":D.*:m:p", False, False)
def c952s_2 (s, sx, m, dDA, sCountry):
    return m.group(0).endswith("é") and not morph(dDA, prevword1(s, m.start()), ":D.*:m:[si]", False, False)
def c966s_1 (s, sx, m, dDA, sCountry):
    return not prevword1(s, m.start()) and morph(dDA, (m.start(2), m.group(2)), ":(?:O[on]|3s)", False)
def c970s_1 (s, sx, m, dDA, sCountry):
    return m.group(0).endswith("U")
def c970s_2 (s, sx, m, dDA, sCountry):
    return m.group(0).endswith("s")
def c975s_1 (s, sx, m, dDA, sCountry):
    return not m.group(0).endswith("s")
def c975s_2 (s, sx, m, dDA, sCountry):
    return m.group(0).endswith("s")
def s980s_1 (s, m):
    return m.group(0).replace("o", "e")
def c983s_1 (s, sx, m, dDA, sCountry):
    return look(s[:m.start()], r"\w") or not morph(dDA, (m.start(1), m.group(1)), ":Y", False)
def s987s_1 (s, m):
    return m.group(0).replace("é", "e").replace("É", "E").replace("è", "e").replace("È", "E")
def c994s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":(?:V0|N.*:m:[si])", False, False)
def c1000s_1 (s, sx, m, dDA, sCountry):
    return m.group(0).endswith("e") and not morph(dDA, prevword1(s, m.start()), ":D.*:[me]:[si]", False, False)
def c1000s_2 (s, sx, m, dDA, sCountry):
    return m.group(0).endswith("s") and not morph(dDA, prevword1(s, m.start()), ":D.*:[me]:[pi]", False, False)
def s1004s_1 (s, m):
    return m.group(0).replace("è", "ê").replace("È", "Ê")
def s1005s_1 (s, m):
    return m.group(0).replace("é", "ê").replace("É", "Ê")
def c1021s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\b(?:ne|il|on|elle|je) +$") and morph(dDA, (m.start(1), m.group(1)), ":[NA].*:[me]:[si]", False)
def c1023s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\b(?:ne|il|on|elle) +$") and morph(dDA, (m.start(1), m.group(1)), ":[NA].*:[fe]:[si]", False)
def c1025s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\b(?:ne|tu) +$") and morph(dDA, (m.start(1), m.group(1)), ":[NA].*:[pi]", False)
def c1032s_1 (s, sx, m, dDA, sCountry):
    return m.group(0).endswith("u") and not morph(dDA, prevword1(s, m.start()), ":D.*:m:s", False, False)
def c1032s_2 (s, sx, m, dDA, sCountry):
    return m.group(0).endswith("x") and not morph(dDA, prevword1(s, m.start()), ":D.*:m:p", False, False)
def c1040s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":D.*:m:p", False, False)
def c1043s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":D.*:f:s", False, False)
def c1046s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":D.*:[me]:p", False, False)
def c1052s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":D.*:m:s", False, False)
def c1061s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":A.*:f", False) or morph(dDA, prevword1(s, m.start()), ":D:*:f", False, False)
def s1061s_1 (s, m):
    return m.group(1).replace("è", "ê").replace("È", "Ê")
def s1069s_1 (s, m):
    return m.group(0).replace("a", "o").replace("A", "O")
def c1075s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\b(?:ce|d[eu]|un|quel|leur) +")
def c1089s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^([nv]ous|faire|en|la|lui|donnant|œuvre|h[éo]|olé|joli|Bora|couvent|dément|sapiens|très|vroum|[0-9]+)$", m.group(1)) and not (re.search("^(?:est|une?)$", m.group(1)) and look(s[:m.start()], "[’']$")) and not (m.group(1) == "mieux" and look(s[:m.start()], "(?i)qui +$"))
def s1103s_1 (s, m):
    return suggSimil(m.group(2), ":[NA].*:[pi]")
def s1105s_1 (s, m):
    return suggSimil(m.group(2), ":[NA].*:[si]")
def c1128s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^avoir$", m.group(1)) and morph(dDA, (m.start(1), m.group(1)), ">avoir ", False)
def c1143s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:être|mettre) ", False)
def c1174s_1 (s, sx, m, dDA, sCountry):
    return not look_chk1(dDA, s[m.end():], m.end(), r" \w[\w-]+ en ([aeo][a-zû]*)", ":V0a")
def c1194s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">abolir ", False)
def c1196s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">achever ", False)
def c1197s_1 (s, sx, m, dDA, sCountry):
    return not look(s[m.end():], r" +de?\b")
def c1206s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, prevword1(s, m.start()), ":A|>un", False)
def c1212s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">comparer ")
def c1213s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">contraindre ", False)
def c1224s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">joindre ")
def c1250s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">suffire ")
def c1251s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">talonner ")
def c1258s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:prévenir|prévoir|prédire|présager|préparer|pressentir|pronostiquer|avertir|devancer|réserver) ", False)
def c1263s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:ajourner|différer|reporter) ", False)
def c1330s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V.*:(?:Y|[123][sp])", ":[NAQ]:.:[si]") and m.group(2)[0].islower()
def s1330s_1 (s, m):
    return suggSimil(m.group(2), ":[NAQ]:[fe]:[si]")
def c1334s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V.*:(?:Y|[123][sp])", ":N.*:[fe]|:[AW]") and m.group(2)[0].islower() or m.group(2) == "va"
def c1334s_2 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V.*:(?:Y|[123][sp])", ":[NAQ]:.:[si]") and m.group(2)[0].islower() and hasSimil(m.group(2))
def s1334s_2 (s, m):
    return suggSimil(m.group(2), ":[NAQ]:[fe]:[si]")
def c1340s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V.*:(?:Y|[123][sp])", ":[NAQ]:.:[si]") and m.group(2)[0].islower()
def s1340s_1 (s, m):
    return suggSimil(m.group(2), ":[NAQ]:[me]:[si]")
def c1344s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V.*:(?:Y|[123][sp])", ":[NAQ]:.:[si]|:V0e.*:3[sp]|>devoir") and m.group(2)[0].islower() and hasSimil(m.group(2))
def s1344s_1 (s, m):
    return suggSimil(m.group(2), ":[NAQ]:[me]:[si]")
def c1348s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V.*:(?:Y|[123][sp])", ":[NAQ]:.:[si]") and m.group(2)[0].islower()
def s1348s_1 (s, m):
    return suggSimil(m.group(2), ":[NAQ]:.:[si]")
def c1352s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V.*:(?:Y|[123][sp])") and m.group(1)[0].islower() and not prevword1(s, m.start())
def s1352s_1 (s, m):
    return suggSimil(m.group(1), ":[NAQ]:[me]:[si]")
def c1356s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V.*:(?:Y|[123][sp])", ":[NAQ]:.:[pi]") and m.group(2)[0].islower() and not re.search(r"(?i)^quelques? soi(?:ent|t|s)\b", m.group(0))
def s1356s_1 (s, m):
    return suggSimil(m.group(2), ":[NAQ]:.:[pi]")
def c1360s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V.*:(?:Y|[123][sp])", ":[NAQ]:.:[pi]") and m.group(2)[0].islower()
def s1360s_1 (s, m):
    return suggSimil(m.group(2), ":[NAQ]:[me]:[pi]")
def c1364s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V.*:(?:Y|[123][sp])", ":[NAQ]:.:[pi]") and m.group(2)[0].islower()
def s1364s_1 (s, m):
    return suggSimil(m.group(2), ":[NAQ]:[fe]:[pi]")
def c1368s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[123][sp]", ":[NAQ]")
def s1368s_1 (s, m):
    return suggSimil(m.group(1), ":(?:[NAQ]:[fe]:[si])")
def c1375s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:[me]", ":[YG]") and m.group(2)[0].islower()
def c1375s_2 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[123][sp]", False)
def s1375s_2 (s, m):
    return suggSimil(m.group(2), ":Y")
def c1384s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[123][sp]", ":[NAQ]")
def s1384s_1 (s, m):
    return suggSimil(m.group(1), ":(?:[NAQ]:.:[si])")
def c1391s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":(?:Y|[123][sp])") and not look(s[:m.start()], "(?i)(?:dont|sauf|un à) +$")
def s1391s_1 (s, m):
    return suggSimil(m.group(1), ":[NAQ]:[me]:[si]")
def c1395s_1 (s, sx, m, dDA, sCountry):
    return m.group(1)[0].islower() and morph(dDA, (m.start(1), m.group(1)), ":V.*:[123][sp]")
def s1395s_1 (s, m):
    return suggSimil(m.group(1), ":[NA]")
def c1399s_1 (s, sx, m, dDA, sCountry):
    return m.group(1)[0].islower() and morphex(dDA, (m.start(1), m.group(1)), ":V.*:[123][sp]", ":[GNA]")
def s1399s_1 (s, m):
    return suggSimil(m.group(1), ":[NAQ]")
def c1403s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":", ":(?:[123][sp]|O[onw]|X)|ou ") and morphex(dDA, prevword1(s, m.start()), ":", ":3s", True)
def s1403s_1 (s, m):
    return suggSimil(m.group(1), ":(?:3s|Oo)")
def c1407s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":", ":(?:[123][sp]|O[onw]|X)|ou ") and morphex(dDA, prevword1(s, m.start()), ":", ":3p", True)
def s1407s_1 (s, m):
    return suggSimil(m.group(1), ":(?:3p|Oo)")
def c1411s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":", ":(?:[123][sp]|O[onw]|X)") and morphex(dDA, prevword1(s, m.start()), ":", ":1s", True)
def s1411s_1 (s, m):
    return suggSimil(m.group(1), ":(?:1s|Oo)")
def c1415s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":", ":(?:[123][sp]|O[onw]|X)") and morphex(dDA, prevword1(s, m.start()), ":", ":(?:2s|V0e)", True)
def s1415s_1 (s, m):
    return suggSimil(m.group(1), ":(?:2s|Oo)")
def c1428s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":P", False)
def c1429s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ]")
def c1435s_1 (s, sx, m, dDA, sCountry):
    return _oDict.isValid(m.group(2)) and not morph(dDA, (m.start(2), m.group(2)), ":(?:[123][sp]|Y|P|O[on]|X)|>(?:[lmts]|surtout|guère) ", False) and not re.search("(?i)-(?:ils?|elles?|[nv]ous|je|tu|on|ce)$", m.group(2))
def s1435s_1 (s, m):
    return suggSimil(m.group(2), ":(?:V|Oo)")
def c1438s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^se que?", m.group(0)) and _oDict.isValid(m.group(2)) and not morph(dDA, (m.start(2), m.group(2)), ":(?:[123][sp]|Y|P|Oo)|>[lmts] ", False) and not re.search("(?i)-(?:ils?|elles?|[nv]ous|je|tu|on|ce)$", m.group(2))
def s1438s_1 (s, m):
    return suggSimil(m.group(2), ":(?:V|Oo)")
def c1442s_1 (s, sx, m, dDA, sCountry):
    return _oDict.isValid(m.group(2)) and not morph(dDA, (m.start(2), m.group(2)), ":(?:[123][sp]|Y|P|Oo)", False) and not re.search("(?i)-(?:ils?|elles?|[nv]ous|je|tu|on|ce)$", m.group(2))
def s1442s_1 (s, m):
    return suggSimil(m.group(2), ":V")
def c1445s_1 (s, sx, m, dDA, sCountry):
    return _oDict.isValid(m.group(2)) and not morph(dDA, (m.start(2), m.group(2)), ":(?:[123][sp]|Y|P|O[onw]|X)", False) and not re.search("(?i)-(?:ils?|elles?|[nv]ous|je|tu|on|ce)$", m.group(2))
def s1445s_1 (s, m):
    return suggSimil(m.group(2), ":V")
def c1448s_1 (s, sx, m, dDA, sCountry):
    return _oDict.isValid(m.group(2)) and not morph(dDA, (m.start(2), m.group(2)), ":(?:[123][sp]|O[onw])", False)
def s1448s_1 (s, m):
    return suggSimil(m.group(2), ":[123][sp]")
def c1451s_1 (s, sx, m, dDA, sCountry):
    return _oDict.isValid(m.group(2)) and not morph(dDA, (m.start(2), m.group(2)), ":(?:[123][sp]|Y|P)|>(?:en|y|ils?) ", False) and not re.search("(?i)-(?:ils?|elles?|[nv]ous|je|tu|on|ce)$", m.group(2))
def s1451s_1 (s, m):
    return suggSimil(m.group(2), ":V")
def c1454s_1 (s, sx, m, dDA, sCountry):
    return _oDict.isValid(m.group(2)) and not morph(dDA, (m.start(2), m.group(2)), ":(?:[123][sp]|Y|P)|>(?:en|y|ils?|elles?) ", False) and not re.search("(?i)-(?:ils?|elles?|[nv]ous|je|tu|on|ce)$", m.group(2))
def s1454s_1 (s, m):
    return suggSimil(m.group(2), ":V")
def c1457s_1 (s, sx, m, dDA, sCountry):
    return _oDict.isValid(m.group(2)) and not morph(dDA, (m.start(2), m.group(2)), ":[123][sp]|>(?:en|y) ", False) and not re.search("(?i)-(?:ils?|elles?|[nv]ous|je|tu|on|dire)$", m.group(2))
def s1457s_1 (s, m):
    return suggSimil(m.group(2), ":V")
def c1475s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":(?:Y|[123][sp])", ":[GAQW]")
def c1479s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[123][sp]", ":(?:G|N|A|Q|W|M[12])")
def c1486s_1 (s, sx, m, dDA, sCountry):
    return not m.group(1)[0].isupper() and morphex(dDA, (m.start(1), m.group(1)), ":[123][sp]", ":[GNAQM]")
def c1490s_1 (s, sx, m, dDA, sCountry):
    return not m.group(1)[0].isupper() and morphex(dDA, (m.start(1), m.group(1)), ":[123][sp]", ":[GNAQM]") and not morph(dDA, prevword1(s, m.start()), ":[NA]:[me]:si", False)
def c1494s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[123][sp]", ":(?:G|N|A|Q|W|M[12]|T)")
def c1498s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":(?:[123][sp]|Y)", ":[GAQW]") and not morph(dDA, prevword1(s, m.start()), ":V[123].*:[123][sp]", False, False)
def c1505s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, prevword1(s, m.start()), ":[VN]", False, True)
def c1506s_1 (s, sx, m, dDA, sCountry):
    return not prevword1(s, m.start())
def c1509s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\b(?:[lmts]a|leur|une|en) +$")
def c1511s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":(?:D|Oo|M)", False)
def c1512s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">être ") and not look(s[:m.start()], r"(?i)\bce que? ")
def c1531s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^(?:côtés?|coups?|peu(?:-près|)|pics?|propos|valoir|plat-ventrismes?)", m.group(2))
def c1531s_2 (s, sx, m, dDA, sCountry):
    return re.search("(?i)^(?:côtés?|coups?|peu(?:-pr(?:ès|êts?|és?)|)|pics?|propos|valoir|plat-ventrismes?)", m.group(2))
def c1536s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":3s", False, False)
def c1539s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":(?:3s|R)", False, False) and not morph(dDA, nextword1(s, m.end()), ":Oo", False)
def c1544s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":Q", ":M[12P]")
def c1547s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ]", ":(?:Y|Oo)")
def c1551s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ]", ":(?:Y|Oo)")
def c1558s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\bce que?\b")
def c1560s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":(?:M[12]|D|Oo)")
def c1565s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[123][sp]") and not m.group(2)[0:1].isupper() and not m.group(2).startswith("tord")
def c1568s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)[ln]’$|(?<!-)\b(?:il|elle|on|y|n’en) +$")
def c1572s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)(\bque?\\b|[ln]’$|(?<!-)\b(?:il|elle|on|y|n’en) +$)")
def c1575s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)(\bque?\b|[ln]’$|(?<!-)\b(?:il|elle|on|y|n’en) +$)")
def c1579s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":Y", False) and not look(s[:m.start()], r"(?i)\bque? |(?:il|elle|on|n’(?:en|y)) +$")
def c1619s_1 (s, sx, m, dDA, sCountry):
    return not prevword1(s, m.start())
def c1626s_1 (s, sx, m, dDA, sCountry):
    return not nextword1(s, m.end()) or look(s[m.end():], "(?i)^ +que? ")
def c1628s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":G", ">(?:tr(?:ès|op)|peu|bien|plus|moins|toute) |:[NAQ].*:f")
def c1632s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f") and not re.search("^seule?s?", m.group(2))
def c1635s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"\b(?:[oO]h|[aA]h) +$")
def c1637s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":R")
def c1650s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ]", ":([123][sp]|Y|P|Q)|>l[ea]? ")
def c1653s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":Y")  and m.group(1) != "CE"
def c1655s_1 (s, sx, m, dDA, sCountry):
    return (m.group(0).find(",") >= 0 or morphex(dDA, (m.start(2), m.group(2)), ":G", ":[AYD]"))
def c1658s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":V[123].*:(?:Y|[123][sp])") and not morph(dDA, (m.start(2), m.group(2)), ">(?:devoir|pouvoir) ") and m.group(2)[0].islower() and m.group(1) != "CE"
def c1665s_1 (s, sx, m, dDA, sCountry):
    return not prevword1(s, m.start())
def c1667s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":V", ":[NAQ].*:[me]") or look(s[:m.start()], r"(?i)\b[cs]e +")
def c1670s_1 (s, sx, m, dDA, sCountry):
    return look(s[m.end():], "^ +[ldmtsc]es ") or ( morph(dDA, prevword1(s, m.start()), ":Cs", False, True) and not look(s[:m.start()], ", +$") and not look(s[m.end():], r"^ +(?:ils?|elles?)\b") and not morph(dDA, nextword1(s, m.end()), ":Q", False, False) )
def c1676s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":N.*:s", ":(?:A.*:[pi]|P)")
def c1698s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":N.*:p", ":(?:G|W|A.*:[si])")
def c1707s_1 (s, sx, m, dDA, sCountry):
    return m.group(1).endswith("en") or look(s[:m.start()], "^ *$")
def c1713s_1 (s, sx, m, dDA, sCountry):
    return not prevword1(s, m.start())
def c1716s_1 (s, sx, m, dDA, sCountry):
    return not m.group(1).startswith("B")
def c1731s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":E|>le ", False, False)
def c1741s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":(?:[123][sp]|Y)", ":(?:G|N|A|M[12P])") and not look(s[:m.start()], r"(?i)\bles *$")
def c1756s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":W", False) and not morph(dDA, prevword1(s, m.start()), ":V.*:3s", False, False)
def s1768s_1 (s, m):
    return m.group(1).replace("pal", "pâl")
def s1771s_1 (s, m):
    return m.group(1).replace("pal", "pâl")
def c1783s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[AQ]", False)
def c1799s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ">(?:arriver|venir|à|revenir|partir|aller) ")
def c1804s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":P", False)
def c1815s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ]", ":(?:G|[123][sp]|W)")
def s1815s_1 (s, m):
    return m.group(1).replace(" ", "")
def c1820s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0e", False)
def c1828s_1 (s, sx, m, dDA, sCountry):
    return not prevword1(s, m.start()) and morph(dDA, (m.start(2), m.group(2)), ":V", False)
def c1831s_1 (s, sx, m, dDA, sCountry):
    return not prevword1(s, m.start()) and morph(dDA, (m.start(2), m.group(2)), ":V", False) and not ( m.group(1) == "sans" and morph(dDA, (m.start(2), m.group(2)), ":[NY]", False) )
def c1852s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[AQ].*:[pi]", False)
def c1855s_1 (s, sx, m, dDA, sCountry):
    return not prevword1(s, m.start())
def c1857s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\b(?:d[eu]|avant|après|sur|malgré) +$")
def c1859s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\b(?:d[eu]|avant|après|sur|malgré) +$") and not morph(dDA, (m.start(2), m.group(2)), ":(?:3s|Oo)", False)
def c1862s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\b(?:d[eu]|avant|après|sur|malgré) +$")
def c1868s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":f") and not look(s[:m.start()], "(?i)(?:à|pas|de|[nv]ous|eux) +$")
def c1871s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":m") and not look(s[:m.start()], "(?i)(?:à|pas|de|[nv]ous|eux) +$")
def c1875s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":N.*:[fp]", ":(?:A|W|G|M[12P]|Y|[me]:i|3s)") and morph(dDA, prevword1(s, m.start()), ":R|>de ", False, True)
def s1875s_1 (s, m):
    return suggMasSing(m.group(1))
def c1879s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:[mp]") and morph(dDA, prevword1(s, m.start()), ":R|>de ", False, True)
def s1879s_1 (s, m):
    return suggFemSing(m.group(1))
def c1883s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:[fs]") and morph(dDA, prevword1(s, m.start()), ":R|>de ", False, True)
def s1883s_1 (s, m):
    return suggMasPlur(m.group(1))
def c1887s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:[ms]") and morph(dDA, prevword1(s, m.start()), ":R|>de ", False, True)
def s1887s_1 (s, m):
    return suggFemPlur(m.group(1))
def c1898s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[123][sp]", False) and not (re.search("(?i)^(?:jamais|rien)$", m.group(3)) and look(s[:m.start()], r"\b(?:que?|plus|moins)\b"))
def c1902s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[123][sp]", False) and not (re.search("(?i)^(?:jamais|rien)$", m.group(3)) and look(s[:m.start()], r"\b(?:que?|plus|moins)\b"))
def c1906s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(3), m.group(3)), ":[123][sp]", False) and not (re.search("(?i)^(?:jamais|rien)$", m.group(3)) and look(s[:m.start()], r"\b(?:que?|plus|moins)\b"))
def c1910s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(3), m.group(3)), ":[123][sp]", False) and not (re.search("(?i)^(?:jamais|rien)$", m.group(3)) and look(s[:m.start()], r"\b(?:que?|plus|moins)\b"))
def c1925s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":(?:Y|W|O[ow])", False) and _oDict.isValid(m.group(1))
def s1925s_1 (s, m):
    return suggVerbInfi(m.group(1))
def c1949s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(2), m.group(2)), ":[NAQ]", False)
def c2184s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ]", ":G")
def c2191s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":R", False, False)
def c2202s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^(?:janvier|février|mars|avril|mai|juin|juillet|ao[ûu]t|septembre|octobre|novembre|décembre|vendémiaire|brumaire|frimaire|nivôse|pluviôse|ventôse|germinal|floréal|prairial|messidor|thermidor|fructidor)s?$", m.group(2))
def c2235s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">faire ", False)
def c2235s_2 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">faire ", False)
def c2254s_1 (s, sx, m, dDA, sCountry):
    return m.group(2).isdigit() or morph(dDA, (m.start(2), m.group(2)), ":B", False)
def c2267s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">prendre ", False)
def c2271s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">rester ", False)
def c2276s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:sembler|para[îi]tre) ") and morphex(dDA, (m.start(3), m.group(3)), ":A", ":G")
def c2277s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"\b(?:une|la|cette|[mts]a|[nv]otre|de) +")
def c2280s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">tenir ", False)
def c2282s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">trier ", False)
def c2284s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">venir ", False)
def c2298s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:[pi]", ":(?:G|3p)")
def c2303s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:[pi]", ":(?:G|3p)")
def c2310s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":B", False)
def c2311s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, prevword1(s, m.start()), ":V0", False) or not morph(dDA, nextword1(s, m.end()), ":A", False)
def c2312s_1 (s, sx, m, dDA, sCountry):
    return isEndOfNG(dDA, s[m.end():], m.end())
def c2313s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":W", False)
def c2314s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":A .*:m:s", False)
def c2316s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, prevword1(s, m.start()), ":(?:R|C[sc])", False, True)
def c2317s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":B", False) or re.search("(?i)^(?:plusieurs|maintes)", m.group(1))
def c2318s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, nextword1(s, m.end()), ":[NAQ]", False, True)
def c2319s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ]", ":V0")
def c2321s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":D", False)
def c2322s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":D.*:[me]:[si]", False)
def c2323s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, nextword1(s, m.end()), ":([AQ].*:[me]:[pi])", False, False)
def c2324s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(2), m.group(2)), ":A", False)
def c2325s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:croire|devoir|estimer|imaginer|penser) ")
def c2327s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":(?:R|D|[123]s|X)", False)
def c2328s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":D", False, False)
def c2329s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\bt(?:u|oi qui)\b")
def c2330s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":D", False, False)
def c2331s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":A", False)
def c2332s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":D", False, False)
def c2333s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":W", False)
def c2334s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[AW]", ":G")
def c2335s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[AW]", False)
def c2336s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(2), m.group(2)), ":Y", False)
def c2339s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NV]", ":D")
def c2340s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(2), m.group(2)), ":(?:3s|X)", False)
def c2341s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[me]", False)
def c2345s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":M[12]", False) and (morph(dDA, (m.start(2), m.group(2)), ":(?:M[12]|V)", False) or not _oDict.isValid(m.group(2)))
def c2346s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":M", False) and morph(dDA, (m.start(2), m.group(2)), ":M", False)
def c2347s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":M", False)
def c2348s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":(?:M[12]|N)") and morph(dDA, (m.start(2), m.group(2)), ":(?:M[12]|N)")
def c2349s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":MP")
def c2350s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":M[12]", False)
def c2351s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":M[12]", False)
def c2354s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[MT]", False) and morph(dDA, prevword1(s, m.start()), ":Cs", False, True) and not look(s[:m.start()], r"\b(?:plus|moins|aussi) .* que +$")
def p2354s_1 (s, m):
    return rewriteSubject(m.group(1),m.group(2))
def c2359s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0e", False)
def c2361s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0e", False)
def c2363s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":(?:V0e|N)", False) and morph(dDA, (m.start(3), m.group(3)), ":[AQ]", False)
def c2365s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0", False)
def c2367s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0", False) and morph(dDA, (m.start(3), m.group(3)), ":[QY]", False)
def c2369s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0a", False) and not (m.group(2) == "crainte" and look(s[:m.start()], r"\w"))
def c2371s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0a", False)
def c2373s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0a", False) and morph(dDA, (m.start(3), m.group(3)), ":B", False) and morph(dDA, (m.start(4), m.group(4)), ":(?:Q|V1.*:Y)", False)
def c2377s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V", False)
def c2378s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V[123]")
def c2379s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V[123]", False)
def c2380s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V", False)
def c2383s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":G")
def c2386s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(2), m.group(2)), "[NAQ].*:[me]:[si]", False)
def c2388s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:[me]", ":G") and morph(dDA, (m.start(3), m.group(3)), ":[AQ].*:[me]", False)
def c2390s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:[fe]", ":G") and morph(dDA, (m.start(3), m.group(3)), ":[AQ].*:[fe]", False)
def c2392s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:[pi]", ":[123][sp]") and morph(dDA, (m.start(3), m.group(3)), ":[AQ].*:[pi]", False)
def c2395s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[AW]")
def c2397s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[AW]", False)
def c2399s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[AQ]", False)
def c2401s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":W", ":3p")
def c2403s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[AW]", ":[123][sp]")
def c2407s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ]", False) and morph(dDA, (m.start(3), m.group(3)), ":W", False) and morph(dDA, (m.start(4), m.group(4)), ":[AQ]", False)
def c2409s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":D", False, True)
def c2410s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":W\\b")
def c2413s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ]", False)
def c2417s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":(?:N|A|Q|V0e)", False)
def c2480s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":1s", False, False)
def c2481s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":2s", False, False)
def c2482s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":3s", False, False)
def c2483s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":1p", False, False)
def c2484s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":2p", False, False)
def c2485s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":3p", False, False)
def c2486s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[123][sp]")
def c2492s_1 (s, sx, m, dDA, sCountry):
    return isAmbiguousNAV(m.group(3)) and morph(dDA, (m.start(1), m.group(1)), ":[NAQ]", False)
def c2495s_1 (s, sx, m, dDA, sCountry):
    return isAmbiguousNAV(m.group(3)) and morph(dDA, (m.start(1), m.group(1)), ":[NAQ]", False) and not re.search("^[dD](?:’une?|e la) ", m.group(0))
def c2498s_1 (s, sx, m, dDA, sCountry):
    return isAmbiguousNAV(m.group(3)) and ( morph(dDA, (m.start(1), m.group(1)), ":[NAQ]", False) or (morphex(dDA, (m.start(1), m.group(1)), ":[NAQ]", ":3[sp]") and not prevword1(s, m.start())) )
def c2514s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":(?:G|V0)", False)
def c2524s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[NAQ]", False)
def c2527s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[NAQ]", False)
def c2530s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f", False)
def c2545s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f", ":(?:e|m|P|G|W|[123][sp]|Y)")
def c2548s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:f", ":(?:e|m|P|G|W|[123][sp]|Y)") or ( morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:f", ":[me]") and morphex(dDA, (m.start(1), m.group(1)), ":R", ">(?:e[tn]|ou) ") and not (morph(dDA, (m.start(1), m.group(1)), ":Rv", False) and morph(dDA, (m.start(3), m.group(3)), ":Y", False)) )
def c2552s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f", ":(?:e|m|P|G|W|Y)")
def c2556s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f", ":[GWme]")
def c2559s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f", ":(?:e|m|G|W|V0|3s)")
def c2562s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f", ":(?:e|m|G|W|P)")
def c2565s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f", ":[GWme]")
def c2568s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f", ":[GWme]")
def c2571s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f:s", ":[GWme]")
def c2575s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m", ":(?:e|f|P|G|W|[1-3][sp]|Y)")
def c2578s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:m", ":(?:e|f|P|G|W|[1-3][sp]|Y)") or ( morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:m", ":[fe]") and morphex(dDA, (m.start(1), m.group(1)), ":[RC]", ">(?:e[tn]|ou) ") and not (morph(dDA, (m.start(1), m.group(1)), ":(?:Rv|C)", False) and morph(dDA, (m.start(3), m.group(3)), ":Y", False)) )
def c2582s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m", ":[efPGWY]")
def c2586s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m", ":[efGW]")
def c2589s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m", ":(?:e|f|G|W|V0|3s|P)") and not ( m.group(2) == "demi" and morph(dDA, nextword1(s, m.end()), ":N.*:f") )
def c2592s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m", ":(?:e|f|G|W|V0|3s)")
def c2595s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m", ":[efGWP]")
def c2598s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m", ":[efGW]")
def c2601s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m", ":[efGW]")
def s2601s_1 (s, m):
    return suggCeOrCet(m.group(2))
def c2605s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f", ":[GWme]")
def s2605s_1 (s, m):
    return m.group(1).replace("on", "a")
def c2608s_1 (s, sx, m, dDA, sCountry):
    return re.search("(?i)^[aâeéèêiîoôuûyœæ]", m.group(2)) and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f", ":[eGW]")
def s2608s_1 (s, m):
    return m.group(1).replace("a", "on")
def c2608s_2 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m", ":[efGW]")
def s2608s_2 (s, m):
    return m.group(1).replace("a", "on")
def c2615s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m", ":[efGW]")
def c2621s_1 (s, sx, m, dDA, sCountry):
    return ( morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:s") and not (look(s[m.end():], "^ +(?:et|ou) ") and morph(dDA, nextword(s, m.end(), 2), ":[NAQ]", True, False)) ) or m.group(1) in aREGULARPLURAL
def s2621s_1 (s, m):
    return suggPlur(m.group(1))
def c2625s_1 (s, sx, m, dDA, sCountry):
    return ( morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s") or (morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s", ":[pi]|>avoir") and morphex(dDA, (m.start(1), m.group(1)), ":[RC]", ">(?:e[tn]|ou) ") and not (morph(dDA, (m.start(1), m.group(1)), ":Rv", False) and morph(dDA, (m.start(2), m.group(2)), ":Y", False))) ) and not (look(s[m.end():], "^ +(?:et|ou) ") and morph(dDA, nextword(s, m.end(), 2), ":[NAQ]", True, False))
def s2625s_1 (s, m):
    return suggPlur(m.group(2))
def c2630s_1 (s, sx, m, dDA, sCountry):
    return (morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:s", ":[ipYPGW]") and not (look(s[m.end():], "^ +(?:et|ou) ") and morph(dDA, nextword(s, m.end(), 2), ":[NAQ]", True, False))) or m.group(1) in aREGULARPLURAL
def s2630s_1 (s, m):
    return suggPlur(m.group(1))
def c2635s_1 (s, sx, m, dDA, sCountry):
    return (morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:s", ":[ipGW]") and not (look(s[m.end():], "^ +(?:et|ou) ") and morph(dDA, nextword(s, m.end(), 2), ":[NAQ]", True, False))) or m.group(1) in aREGULARPLURAL
def s2635s_1 (s, m):
    return suggPlur(m.group(1))
def c2640s_1 (s, sx, m, dDA, sCountry):
    return (morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s", ":(?:[ipGW]|[123][sp])") and not (look(s[m.end():], "^ +(?:et|ou) ") and morph(dDA, nextword(s, m.end(), 2), ":[NAQ]", True, False))) or m.group(2) in aREGULARPLURAL
def s2640s_1 (s, m):
    return suggPlur(m.group(2))
def c2640s_2 (s, sx, m, dDA, sCountry):
    return (morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s", ":(?:[ipGW]|[123][sp])") and not (look(s[m.end():], "^ +(?:et|ou) ") and morph(dDA, nextword(s, m.end(), 2), ":[NAQ]", True, False))) or m.group(2) in aREGULARPLURAL
def c2649s_1 (s, sx, m, dDA, sCountry):
    return (morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:s", ":[ipPGW]") and not (look(s[m.end():], "^ +(?:et|ou) ") and morph(dDA, nextword(s, m.end(), 2), ":[NAQ]", True, False))) or m.group(1) in aREGULARPLURAL
def s2649s_1 (s, m):
    return suggPlur(m.group(1))
def c2659s_1 (s, sx, m, dDA, sCountry):
    return (morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:s", ":[ip]|>o(?:nde|xydation|or)\\b") and morphex(dDA, prevword1(s, m.start()), ":(?:G|[123][sp])", ":[AD]", True)) or m.group(1) in aREGULARPLURAL
def s2659s_1 (s, m):
    return suggPlur(m.group(1))
def c2665s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:s", ":[ip]") or m.group(1) in aREGULARPLURAL
def s2665s_1 (s, m):
    return suggPlur(m.group(1))
def c2669s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:s", ":[ip]") or m.group(1) in aREGULARPLURAL
def s2669s_1 (s, m):
    return suggPlur(m.group(1))
def c2673s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:p", ":[123][sp]|:[si]")
def s2673s_1 (s, m):
    return suggSing(m.group(1))
def c2677s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:p")
def s2677s_1 (s, m):
    return suggSing(m.group(1))
def c2680s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p") or ( morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p", ":[si]") and morphex(dDA, (m.start(1), m.group(1)), ":[RC]", ">(?:e[tn]|ou)") and not (morph(dDA, (m.start(1), m.group(1)), ":Rv", False) and morph(dDA, (m.start(2), m.group(2)), ":Y", False)) )
def s2680s_1 (s, m):
    return suggSing(m.group(2))
def c2684s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:p", ":[siGW]")
def s2684s_1 (s, m):
    return suggSing(m.group(1))
def c2688s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p")
def c2688s_2 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p")
def s2688s_2 (s, m):
    return suggSing(m.group(2))
def c2691s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(3), m.group(3)), ":[NAQ].*:p") or ( morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:p", ":[si]") and morphex(dDA, (m.start(1), m.group(1)), ":[RC]", ">(?:e[tn]|ou)") and not (morph(dDA, (m.start(1), m.group(1)), ":Rv", False) and morph(dDA, (m.start(3), m.group(3)), ":Y", False)) )
def c2691s_2 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(3), m.group(3)), ":[NAQ].*:p") or ( morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:p", ":[si]") and morphex(dDA, (m.start(1), m.group(1)), ":[RC]", ">(?:e[tn]|ou)") and not (morph(dDA, (m.start(1), m.group(1)), ":Rv", False) and morph(dDA, (m.start(3), m.group(3)), ":Y", False)) )
def s2691s_2 (s, m):
    return suggSing(m.group(3))
def c2696s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p", ":[siGW]")
def c2696s_2 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p", ":[siGW]")
def s2696s_2 (s, m):
    return suggSing(m.group(2))
def c2700s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:p", ":[siGW]")
def s2700s_1 (s, m):
    return suggSing(m.group(1))
def c2704s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p", ":[siGW]")
def c2708s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p", ":[siG]")
def c2712s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:p", ":[siGW]") and not morph(dDA, prevword(s, m.start(), 2), ":B", False)
def s2712s_1 (s, m):
    return suggSing(m.group(1))
def c2755s_1 (s, sx, m, dDA, sCountry):
    return (morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s") and not re.search("(?i)^(janvier|février|mars|avril|mai|juin|juillet|ao[ûu]t|septembre|octobre|novembre|décembre|rue|route|ruelle|place|boulevard|avenue|allée|chemin|sentier|square|impasse|cour|quai|chaussée|côte|vendémiaire|brumaire|frimaire|nivôse|pluviôse|ventôse|germinal|floréal|prairial|messidor|thermidor|fructidor)$", m.group(2))) or m.group(2) in aREGULARPLURAL
def s2755s_1 (s, m):
    return suggPlur(m.group(2))
def c2761s_1 (s, sx, m, dDA, sCountry):
    return (morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s") and not morph(dDA, prevword1(s, m.start()), ":N", False) and not re.search("(?i)^(janvier|février|mars|avril|mai|juin|juillet|ao[ûu]t|septembre|octobre|novembre|décembre|rue|route|ruelle|place|boulevard|avenue|allée|chemin|sentier|square|impasse|cour|quai|chaussée|côte|vendémiaire|brumaire|frimaire|nivôse|pluviôse|ventôse|germinal|floréal|prairial|messidor|thermidor|fructidor)$", m.group(2))) or m.group(2) in aREGULARPLURAL
def s2761s_1 (s, m):
    return suggPlur(m.group(2))
def c2767s_1 (s, sx, m, dDA, sCountry):
    return (morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:s") or m.group(1) in aREGULARPLURAL) and not look(s[:m.start()], r"(?i)\b(?:le|un|ce|du) +$")
def s2767s_1 (s, m):
    return suggPlur(m.group(1))
def c2771s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:p") and not re.search("(?i)^(janvier|février|mars|avril|mai|juin|juillet|ao[ûu]t|septembre|octobre|novembre|décembre|rue|route|ruelle|place|boulevard|avenue|allée|chemin|sentier|square|impasse|cour|quai|chaussée|côte|vendémiaire|brumaire|frimaire|nivôse|pluviôse|ventôse|germinal|floréal|prairial|messidor|thermidor|fructidor|Rois|Corinthiens|Thessaloniciens)$", m.group(1))
def s2771s_1 (s, m):
    return suggSing(m.group(1))
def c2775s_1 (s, sx, m, dDA, sCountry):
    return (m.group(1) != "1" and m.group(1) != "0" and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s") and not re.search("(?i)^(janvier|février|mars|avril|mai|juin|juillet|ao[ûu]t|septembre|octobre|novembre|décembre|rue|route|ruelle|place|boulevard|avenue|allée|chemin|sentier|square|impasse|cour|quai|chaussée|côte|vendémiaire|brumaire|frimaire|nivôse|pluviôse|ventôse|germinal|floréal|prairial|messidor|thermidor|fructidor)$", m.group(2))) or m.group(1) in aREGULARPLURAL
def s2775s_1 (s, m):
    return suggPlur(m.group(2))
def c2783s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f:p", ":(?:V0e|[NAQ].*:[me]:[si])")
def c2783s_2 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m:p", ":(?:V0e|[NAQ].*:[me]:[si])")
def c2783s_3 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f:[si]", ":(?:V0e|[NAQ].*:[me]:[si])")
def c2787s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f:s", ":(?:V0e|[NAQ].*:[me]:[pi])")
def c2787s_2 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m:s", ":(?:V0e|[NAQ].*:[me]:[pi])")
def c2787s_3 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f:[pi]", ":(?:V0e|[NAQ].*:[me]:[pi])")
def c2791s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m:p", ":(?:V0e|[NAQ].*:[fe]:[si])")
def c2791s_2 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f:p", ":(?:V0e|[NAQ].*:[fe]:[si])")
def c2791s_3 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m:[si]", ":(?:V0e|[NAQ].*:[fe]:[si])")
def c2795s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m:s", ":(?:V0e|[NAQ].*:[fe]:[pi])")
def c2795s_2 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f:s", ":(?:V0e|[NAQ].*:[fe]:[pi])")
def c2795s_3 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m:[pi]", ":(?:V0e|[NAQ].*:[fe]:[pi])")
def c2807s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"\btel(?:le|)s? +$")
def c2810s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"\btel(?:le|)s? +$")
def s2810s_1 (s, m):
    return m.group(1)[:-1]
def c2814s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"\btel(?:le|)s? +$") and morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:f", ":[me]")
def c2818s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"\btel(?:le|)s? +$") and morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:m", ":[fe]")
def c2822s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"\btel(?:le|)s? +$") and morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:f", ":[me]")
def c2826s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"\btel(?:le|)s? +$") and morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:m", ":[fe]")
def c2842s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":V0e", False)
def c2845s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":V0e", False) and morphex(dDA, (m.start(4), m.group(4)), ":[NAQ].*:m", ":[fe]")
def s2845s_1 (s, m):
    return m.group(1).replace("lle", "l")
def c2850s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":V0e", False)
def c2853s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":V0e", False) and morphex(dDA, (m.start(4), m.group(4)), ":[NAQ].*:f", ":[me]")
def s2853s_1 (s, m):
    return m.group(1).replace("l", "lle")
def c2872s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">trouver ", False) and morphex(dDA, (m.start(3), m.group(3)), ":A.*:(?:f|m:p)", ":(?:G|3[sp]|M[12P])")
def s2872s_1 (s, m):
    return suggMasSing(m.group(3))
def c2883s_1 (s, sx, m, dDA, sCountry):
    return ((morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:m") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f")) or (morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:f") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m"))) and not apposition(m.group(1), m.group(2))
def s2883s_1 (s, m):
    return switchGender(m.group(2))
def c2883s_2 (s, sx, m, dDA, sCountry):
    return ((morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:s") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p")) or (morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:p") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s"))) and not apposition(m.group(1), m.group(2))
def s2883s_2 (s, m):
    return switchPlural(m.group(2))
def c2891s_1 (s, sx, m, dDA, sCountry):
    return ((morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:m") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f")) or (morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:f") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m"))) and not apposition(m.group(1), m.group(2)) and morph(dDA, prevword1(s, m.start()), ":[VRX]", True, True)
def s2891s_1 (s, m):
    return switchGender(m.group(2))
def c2891s_2 (s, sx, m, dDA, sCountry):
    return ((morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:p") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s")) or (morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:s") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p"))) and not apposition(m.group(1), m.group(2)) and morph(dDA, prevword1(s, m.start()), ":[VRX]", True, True)
def s2891s_2 (s, m):
    return switchPlural(m.group(2))
def c2903s_1 (s, sx, m, dDA, sCountry):
    return ((morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:m", ":[GYfe]") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f")) or (morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:f", ":[GYme]") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m"))) and not apposition(m.group(1), m.group(2)) and morph(dDA, prevword1(s, m.start()), ":[VRX]", True, True)
def s2903s_1 (s, m):
    return switchGender(m.group(2))
def c2903s_2 (s, sx, m, dDA, sCountry):
    return ((morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:p", ":[GYsi]") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s")) or (morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:s", ":[GYpi]") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p"))) and not apposition(m.group(1), m.group(2)) and morph(dDA, prevword1(s, m.start()), ":[VRX]", True, True)
def s2903s_2 (s, m):
    return switchPlural(m.group(2))
def c2915s_1 (s, sx, m, dDA, sCountry):
    return ((morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:m", ":(?:[Gfe]|V0e|Y)") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f")) or (morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:f", ":(?:[Gme]|V0e|Y)") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m"))) and not apposition(m.group(1), m.group(2)) and morph(dDA, prevword1(s, m.start()), ":[VRX]", True, True)
def s2915s_1 (s, m):
    return switchGender(m.group(2))
def c2915s_2 (s, sx, m, dDA, sCountry):
    return ((morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:p", ":(?:[Gsi]|V0e|Y)") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s")) or (morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:s", ":(?:[Gpi]|V0e|Y)") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p"))) and not apposition(m.group(1), m.group(2)) and morph(dDA, prevword1(s, m.start()), ":[VRX]", True, True)
def s2915s_2 (s, m):
    return switchPlural(m.group(2))
def c2933s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^air$", m.group(1)) and not m.group(2).startswith("seul") and ((morph(dDA, (m.start(1), m.group(1)), ":m") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f")) or (morph(dDA, (m.start(1), m.group(1)), ":f") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m"))) and not apposition(m.group(1), m.group(2)) and not look(s[:m.start()], r"\b(?:et|ou|de) +$")
def s2933s_1 (s, m):
    return switchGender(m.group(2), False)
def c2933s_2 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^air$", m.group(1)) and not m.group(2).startswith("seul") and morph(dDA, (m.start(1), m.group(1)), ":[si]") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p") and not apposition(m.group(1), m.group(2)) and not look(s[:m.start()], r"\b(?:et|ou|de) +$")
def s2933s_2 (s, m):
    return suggSing(m.group(2))
def c2942s_1 (s, sx, m, dDA, sCountry):
    return not m.group(2).startswith("seul") and ((morph(dDA, (m.start(1), m.group(1)), ":m") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f")) or (morph(dDA, (m.start(1), m.group(1)), ":f") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m"))) and not morph(dDA, prevword1(s, m.start()), ":[NAQ]", False, False) and not apposition(m.group(1), m.group(2))
def s2942s_1 (s, m):
    return switchGender(m.group(2), False)
def c2942s_2 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^air$", m.group(1)) and not m.group(2).startswith("seul") and morph(dDA, (m.start(1), m.group(1)), ":[si]") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p") and not morph(dDA, prevword1(s, m.start()), ":[NAQ]", False, False) and not apposition(m.group(1), m.group(2))
def s2942s_2 (s, m):
    return suggSing(m.group(2))
def c2957s_1 (s, sx, m, dDA, sCountry):
    return m.group(1) != "fois" and not m.group(2).startswith("seul") and ((morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:m", ":[fe]") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f")) or (morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:f", ":[me]") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m"))) and morph(dDA, prevword1(s, m.start()), ":[VRBX]", True, True) and not apposition(m.group(1), m.group(2))
def s2957s_1 (s, m):
    return switchGender(m.group(2), True)
def c2957s_2 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:[pi]", False) and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s") and morph(dDA, prevword1(s, m.start()), ":[VRBX]", True, True) and not apposition(m.group(1), m.group(2))
def s2957s_2 (s, m):
    return suggPlur(m.group(2))
def c2978s_1 (s, sx, m, dDA, sCountry):
    return m.group(1) != "fois" and morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:[si]", False) and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p") and not m.group(2).startswith("seul") and not apposition(m.group(1), m.group(2)) and not look(s[:m.start()], r"\b(?:et|ou|d’) *$")
def s2978s_1 (s, m):
    return suggSing(m.group(2))
def c2982s_1 (s, sx, m, dDA, sCountry):
    return m.group(1) != "fois" and morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:[si]", False) and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p") and not m.group(2).startswith("seul") and not apposition(m.group(1), m.group(2)) and not morph(dDA, prevword1(s, m.start()), ":[NAQB]", False, False)
def s2982s_1 (s, m):
    return suggSing(m.group(2))
def c2992s_1 (s, sx, m, dDA, sCountry):
    return not m.group(3).startswith("seul") and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:[me]", ":(?:B|G|V0|f)") and morph(dDA, (m.start(3), m.group(3)), ":[NAQ].*:f") and not apposition(m.group(2), m.group(3)) and not look(s[:m.start()], r"\b(?:et|ou|de) +$")
def s2992s_1 (s, m):
    return suggMasPlur(m.group(3))  if re.search("(?i)^(?:certains|quels)", m.group(1)) else suggMasSing(m.group(3))
def c2998s_1 (s, sx, m, dDA, sCountry):
    return not m.group(3).startswith("seul") and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:[me]", ":(?:B|G|V0|f)") and morph(dDA, (m.start(3), m.group(3)), ":[NAQ].*:f") and not apposition(m.group(2), m.group(3)) and not morph(dDA, prevword1(s, m.start()), ":[NAQ]|>(?:et|ou) ", False, False)
def s2998s_1 (s, m):
    return suggMasPlur(m.group(3))  if re.search("(?i)^(?:certains|quels)", m.group(1)) else suggMasSing(m.group(3))
def c3006s_1 (s, sx, m, dDA, sCountry):
    return not m.group(3).startswith("seul") and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m", ":(?:B|G|e|V0|f)") and morph(dDA, (m.start(3), m.group(3)), ":[NAQ].*:f") and not apposition(m.group(2), m.group(3)) and not look(s[:m.start()], r"\b(?:et|ou|de) +$")
def s3006s_1 (s, m):
    return suggMasSing(m.group(3))
def c3011s_1 (s, sx, m, dDA, sCountry):
    return not m.group(3).startswith("seul") and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m", ":(?:B|G|e|V0|f)") and morph(dDA, (m.start(3), m.group(3)), ":[NAQ].*:f") and not apposition(m.group(2), m.group(3)) and not morph(dDA, prevword1(s, m.start()), ":[NAQ]|>(?:et|ou) ", False, False)
def s3011s_1 (s, m):
    return suggMasSing(m.group(3))
def c3018s_1 (s, sx, m, dDA, sCountry):
    return m.group(2) != "fois" and not m.group(3).startswith("seul") and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:[fe]", ":(?:B|G|V0|m)") and morph(dDA, (m.start(3), m.group(3)), ":[NAQ].*:m") and not apposition(m.group(2), m.group(3)) and not look(s[:m.start()], r"\b(?:et|ou|de) +$")
def s3018s_1 (s, m):
    return suggFemPlur(m.group(3))  if re.search("(?i)^(?:certaines|quelles)", m.group(1))  else suggFemSing(m.group(3))
def c3024s_1 (s, sx, m, dDA, sCountry):
    return m.group(2) != "fois" and not m.group(3).startswith("seul") and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:[fe]", ":(?:B|G|V0|m)") and morph(dDA, (m.start(3), m.group(3)), ":[NAQ].*:m") and not apposition(m.group(2), m.group(3)) and not morph(dDA, prevword1(s, m.start()), ":[NAQ]|>(?:et|ou) ", False, False)
def s3024s_1 (s, m):
    return suggFemPlur(m.group(3))  if re.search("(?i)^(?:certaines|quelles)", m.group(1))  else suggFemSing(m.group(3))
def c3032s_1 (s, sx, m, dDA, sCountry):
    return m.group(2) != "fois" and not m.group(3).startswith("seul") and not re.search("(?i)^quelque chose", m.group(0)) and ((morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m", ":(?:B|e|G|V0|f)") and morph(dDA, (m.start(3), m.group(3)), ":[NAQ].*:f")) or (morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f", ":(?:B|e|G|V0|m)") and morph(dDA, (m.start(3), m.group(3)), ":[NAQ].*:m"))) and not apposition(m.group(2), m.group(3)) and not look(s[:m.start()], r"\b(?:et|ou|de) +$")
def s3032s_1 (s, m):
    return switchGender(m.group(3), m.group(1).endswith("s"))
def c3037s_1 (s, sx, m, dDA, sCountry):
    return m.group(2) != "fois" and not m.group(3).startswith("seul") and not re.search("(?i)^quelque chose", m.group(0)) and ((morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m", ":(?:B|e|G|V0|f)") and morph(dDA, (m.start(3), m.group(3)), ":[NAQ].*:f")) or (morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f", ":(?:B|e|G|V0|m)") and morph(dDA, (m.start(3), m.group(3)), ":[NAQ].*:m"))) and not apposition(m.group(2), m.group(3)) and not morph(dDA, prevword1(s, m.start()), ":[NAQ]|>(?:et|ou) ", False, False)
def s3037s_1 (s, m):
    return switchGender(m.group(3), m.group(1).endswith("s"))
def c3046s_1 (s, sx, m, dDA, sCountry):
    return not m.group(2).startswith("seul") and morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:[si]", False) and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p") and not apposition(m.group(1), m.group(2)) and not look(s[:m.start()], r"\b(?:et|ou|de) +$")
def s3046s_1 (s, m):
    return suggSing(m.group(2))
def c3051s_1 (s, sx, m, dDA, sCountry):
    return not m.group(2).startswith("seul") and morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:[si]", False) and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p") and not apposition(m.group(1), m.group(2)) and not morph(dDA, prevword1(s, m.start()), ":[NAQ]|>(?:et|ou) ", False, False)
def s3051s_1 (s, m):
    return suggSing(m.group(2))
def c3058s_1 (s, sx, m, dDA, sCountry):
    return not m.group(2).startswith("seul") and morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:[si]", False) and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p", ":[GWi]") and not apposition(m.group(1), m.group(2)) and not look(s[:m.start()], r"\b(?:et|ou|de) +$")
def s3058s_1 (s, m):
    return suggSing(m.group(2))
def c3063s_1 (s, sx, m, dDA, sCountry):
    return not m.group(2).startswith("seul") and morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:[si]", False) and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p", ":[GWi]") and not apposition(m.group(1), m.group(2)) and not morph(dDA, prevword1(s, m.start()), ":[NAQ]|>(?:et|ou) ", False, False)
def s3063s_1 (s, m):
    return suggSing(m.group(2))
def c3070s_1 (s, sx, m, dDA, sCountry):
    return not m.group(2).startswith("seul") and morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:[pi]") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s") and not apposition(m.group(1), m.group(2)) and not look_chk1(dDA, s[m.end():], m.end(), r"^ +et +(\w[\w-]+)", ":A")
def s3070s_1 (s, m):
    return suggPlur(m.group(2))
def c3076s_1 (s, sx, m, dDA, sCountry):
    return not m.group(2).startswith("seul") and morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:[pi]", False) and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s") and not apposition(m.group(1), m.group(2)) and not look_chk1(dDA, s[m.end():], m.end(), r"^ +et +(\w[\w-]+)", ":A") and not look(s[:m.start()], r"(?i)\bune? de ")
def s3076s_1 (s, m):
    return suggPlur(m.group(2))
def c3110s_1 (s, sx, m, dDA, sCountry):
    return (morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:p") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:[pi]") and morph(dDA, (m.start(3), m.group(3)), ":[NAQ].*:s")) or (morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:s") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:[si]") and morph(dDA, (m.start(3), m.group(3)), ":[NAQ].*:p"))
def s3110s_1 (s, m):
    return switchPlural(m.group(3))
def c3115s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:[pi]") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:[pi]") and morph(dDA, (m.start(3), m.group(3)), ":[NAQ].*:s")
def s3115s_1 (s, m):
    return suggPlur(m.group(3))
def c3119s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:[pi]", False) and morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:[pi]", ":G") and morph(dDA, (m.start(4), m.group(4)), ":[NAQ].*:s") and not look(s[:m.start()], r"(?i)\bune? de ")
def s3119s_1 (s, m):
    return suggPlur(m.group(4))
def c3124s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:[si]", False) and morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:[si]", ":G") and morph(dDA, (m.start(4), m.group(4)), ":[NAQ].*:p")
def s3124s_1 (s, m):
    return suggSing(m.group(4))
def c3134s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:(?:m|f:p)", ":(?:G|P|[fe]:[is]|V0|3[sp])") and not apposition(m.group(1), m.group(2))
def s3134s_1 (s, m):
    return suggFemSing(m.group(2))
def c3138s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:(?:f|m:p)", ":(?:G|P|[me]:[is]|V0|3[sp])") and not apposition(m.group(1), m.group(2))
def s3138s_1 (s, m):
    return suggMasSing(m.group(2))
def c3142s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:f|>[aéeiou].*:e", False) and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:(?:f|m:p)", ":(?:G|P|m:[is]|V0|3[sp])") and not apposition(m.group(1), m.group(2))
def s3142s_1 (s, m):
    return suggMasSing(m.group(2))
def c3146s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:m", ":G|>[aéeiou].*:[ef]") and morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:(?:f|m:p)", ":(?:G|P|[me]:[is]|V0|3[sp])") and not apposition(m.group(2), m.group(3))
def s3146s_1 (s, m):
    return suggMasSing(m.group(3))
def c3151s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:m", ":G|>[aéeiou].*:[ef]") and not morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f|>[aéeiou].*:e", False) and morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:(?:f|m:p)", ":(?:G|P|[me]:[is]|V0|3[sp])") and not apposition(m.group(2), m.group(3))
def s3151s_1 (s, m):
    return suggMasSing(m.group(3))
def c3156s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s", ":(?:G|P|[me]:[ip]|V0|3[sp])") and not apposition(m.group(1), m.group(2))
def s3156s_1 (s, m):
    return suggPlur(m.group(2))
def c3174s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":B.*:p", False) and m.group(2) != "cents"
def c3209s_1 (s, sx, m, dDA, sCountry):
    return not prevword1(s, m.start())
def c3210s_1 (s, sx, m, dDA, sCountry):
    return not prevword1(s, m.start())
def c3211s_1 (s, sx, m, dDA, sCountry):
    return not prevword1(s, m.start())
def c3217s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\bquatre $")
def c3220s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, nextword1(s, m.end()), ":B", False) and not look(s[:m.start()], r"(?i)\b(?:numéro|page|chapitre|référence|année|test|série)s? +$")
def c3231s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, nextword1(s, m.end()), ":B|>une?", False, True) and not look(s[:m.start()], r"(?i)\b(?:numéro|page|chapitre|référence|année|test|série)s? +$")
def c3235s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, nextword1(s, m.end()), ":B|>une?", False, False)
def c3238s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:[pi]", ":G") and morphex(dDA, prevword1(s, m.start()), ":[VR]", ":B", True)
def c3243s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, nextword1(s, m.end()), ":B") or (morph(dDA, prevword1(s, m.start()), ":B") and morph(dDA, nextword1(s, m.end()), ":[NAQ]", False))
def c3254s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">faire ", False)
def c3257s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">faire ", False) and morph(dDA, (m.start(3), m.group(3)), ":(?:N|MP)")
def s3300s_1 (s, m):
    return m.group(1).rstrip("e")
def c3305s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":(?:V0e|W)|>très", False)
def c3313s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:co[ûu]ter|payer) ", False)
def c3330s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">donner ", False)
def c3345s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:mettre|mise) ", False)
def c3357s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:avoir|perdre) ", False)
def c3360s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\b(?:lit|fauteuil|armoire|commode|guéridon|tabouret|chaise)s?\b")
def c3367s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, prevword1(s, m.start()), ":(?:V|[NAQ].*:s)", ":(?:[NA]:.:[pi]|V0e.*:[123]p)", True)
def c3416s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:aller|partir) ", False)
def c3424s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":V0e.*:3p", False, False) or morph(dDA, nextword1(s, m.end()), ":Q", False, False)
def c3442s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:être|devenir|para[îi]tre|rendre|sembler) ", False)
def s3442s_1 (s, m):
    return m.group(2).replace("oc", "o")
def c3464s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">tenir ")
def c3478s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">mettre ", False)
def c3479s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">faire ", False)
def c3500s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:être|aller) ", False)
def s3502s_1 (s, m):
    return m.group(1).replace("auspice", "hospice")
def s3504s_1 (s, m):
    return m.group(1).replace("auspice", "hospice")
def c3525s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, nextword1(s, m.end()), ":[AQ]")
def s3539s_1 (s, m):
    return m.group(1).replace("cane", "canne")
def c3546s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:appuyer|battre|frapper|lever|marcher) ", False)
def s3546s_1 (s, m):
    return m.group(2).replace("cane", "canne")
def c3552s_1 (s, sx, m, dDA, sCountry):
    return not re.search("^C(?:annes|ANNES)", m.group(1))
def c3555s_1 (s, sx, m, dDA, sCountry):
    return not re.search("^C(?:annes|ANNES)", m.group(1))
def c3570s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">faire ", False)
def c3578s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0a", False)
def c3580s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, prevword1(s, m.start()), ":[VR]", False)
def c3584s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^à cor et à cri$", m.group(0))
def c3591s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">tordre ", False)
def c3593s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">rendre ", False)
def c3604s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">couper ")
def c3605s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:avoir|donner) ", False)
def c3617s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V.[^:]:(?!Q)")
def c3623s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\b(?:[lmtsc]es|des?|[nv]os|leurs|quels) +$")
def c3634s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, nextword1(s, m.end()), ":[GV]", ":[NAQ]", True)
def c3637s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, nextword1(s, m.end()), ":[GV]", ":[NAQ]")
def c3640s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, nextword1(s, m.end()), ":[GV]", ":[NAQ]", True)
def c3643s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, nextword1(s, m.end()), ":G", ":[NAQ]")
def c3646s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0e", False)
def s3646s_1 (s, m):
    return m.group(2).replace("nd", "nt")
def c3656s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, prevword1(s, m.start()), ":V0e", False, False)
def c3662s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ">(?:abandonner|céder|résister) ", False) and not look(s[m.end():], "^ d(?:e |’)")
def s3675s_1 (s, m):
    return m.group(1).replace("nt", "mp")
def c3690s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0e", False) and morph(dDA, (m.start(3), m.group(3)), ":(?:Y|Oo)", False)
def s3690s_1 (s, m):
    return m.group(2).replace("sens", "cens")
def s3699s_1 (s, m):
    return m.group(1).replace("o", "ô")
def c3714s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0a", False)
def c3731s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ">(?:desceller|desseller) ", False)
def s3731s_1 (s, m):
    return m.group(2).replace("descell", "décel").replace("dessell", "décel")
def c3735s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:desceller|desseller) ", False)
def s3735s_1 (s, m):
    return m.group(1).replace("descell", "décel").replace("dessell", "décel")
def c3749s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0", False)
def s3749s_1 (s, m):
    return m.group(2).replace("î", "i")
def c3752s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\b(?:[vn]ous|lui|leur|et toi) +$|[nm]’$")
def s3760s_1 (s, m):
    return m.group(1).replace("and", "ant")
def c3766s_1 (s, sx, m, dDA, sCountry):
    return not ( m.group(1) == "bonne" and look(s[:m.start()], r"(?i)\bune +$") and look(s[m.end():], "(?i)^ +pour toute") )
def c3769s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:faire|perdre|donner) ", False)
def c3794s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":D")
def s3864s_1 (s, m):
    return m.group(0)[:-1].replace(" ", "-")+u"à"
def c3865s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":[NAQ]")
def c3866s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ]", ":[123][sp]")
def c3870s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[123][sp]", ":[GQ]")
def c3872s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[123][sp]", ":[GQ]")
def c3876s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[123][sp]", ":[GQ]")
def c3884s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":Y", ":[NA].*:[pe]") and not look(s[:m.start()], r"(?i)\b[ld]es +$")
def c3892s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">soulever ", False)
def s3892s_1 (s, m):
    return m.group(1)[3:]
def c3904s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:être|habiter|trouver|situer|rester|demeurer?) ", False)
def c3915s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0a", False)
def c3919s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0a", False)
def c3933s_1 (s, sx, m, dDA, sCountry):
    return not (m.group(1) == "Notre" and look(s[m.end():], "Père"))
def s3933s_1 (s, m):
    return m.group(1).replace("otre", "ôtre")
def c3935s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\b(les?|la|du|des|aux?) +") and morph(dDA, (m.start(2), m.group(2)), ":[NAQ]", False)
def s3935s_1 (s, m):
    return m.group(1).replace("ôtre", "otre").rstrip("s")
def c3943s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":D", False, False)
def c3954s_1 (s, sx, m, dDA, sCountry):
    return not prevword1(s, m.start())
def c3957s_1 (s, sx, m, dDA, sCountry):
    return ( re.search("^[nmts]e$", m.group(2)) or (not re.search("(?i)^(?:confiance|envie|peine|prise|crainte|affaire|hâte|force|recours|somme)$", m.group(2)) and morphex(dDA, (m.start(2), m.group(2)), ":[123][sp]", ":[AG]")) ) and not prevword1(s, m.start())
def c3962s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V.*:(?:[1-3][sp])", ":(?:G|1p)") and not ( m.group(0).find(" leur ") and morph(dDA, (m.start(2), m.group(2)), ":[NA].*:[si]", False) ) and not prevword1(s, m.start())
def c3968s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":[VR]", False, False) and not look(s[m.end():], "^ +>") and not morph(dDA, nextword1(s, m.end()), ":3s", False)
def c3976s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":V.[a-z_!?]+:(?!Y)")
def c3977s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V0e", ":Y")
def c3979s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":D", False, False)
def s3985s_1 (s, m):
    return m.group(1).replace("pin", "pain")
def c3987s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:manger|dévorer|avaler|engloutir) ")
def s3987s_1 (s, m):
    return m.group(2).replace("pin", "pain")
def c3994s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">aller ", False)
def c4001s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0e", False)
def s4001s_1 (s, m):
    return m.group(2).replace("pal", "pâl")
def s4004s_1 (s, m):
    return m.group(2).replace("pal", "pâl")
def c4010s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">prendre ", False)
def c4011s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">tirer ", False)
def c4012s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">faire ", False)
def c4014s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">prendre ", False)
def c4022s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[NAQ]")
def c4023s_1 (s, sx, m, dDA, sCountry):
    return not prevword1(s, m.start())
def c4029s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":A") and not re.search("(?i)^seule?s?$", m.group(2))
def c4034s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":(?:N|A|Q|G|MP)")
def c4047s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":(?:Y|M[12P])")
def c4050s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], "(?i)(?:peu|de) $") and morph(dDA, (m.start(2), m.group(2)), ":Y|>(tout|les?|la) ")
def c4062s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0a", False)
def c4068s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":Q")
def c4076s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, nextword1(s, m.end()), ":[AQ]", False)
def c4096s_1 (s, sx, m, dDA, sCountry):
    return not nextword1(s, m.end())
def c4099s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">résonner ", False)
def s4099s_1 (s, m):
    return m.group(1).replace("réso", "raiso")
def c4109s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":M1", False)
def s4122s_1 (s, m):
    return m.group(1).replace("sale", "salle")
def c4126s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0e", False)
def s4126s_1 (s, m):
    return m.group(2).replace("salle", "sale")
def s4140s_1 (s, m):
    return m.group(1).replace("scep","sep")
def c4143s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">être ", False)
def s4143s_1 (s, m):
    return m.group(2).replace("sep", "scep")
def c4151s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">suivre ", False)
def c4159s_1 (s, sx, m, dDA, sCountry):
    return not look(s[m.end():], " soit ")
def c4160s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, nextword1(s, m.end()), ":[GY]", True, True) and not look(s[:m.start()], "(?i)quel(?:s|les?|) qu $|on $|il $") and not look(s[m.end():], " soit ")
def c4177s_1 (s, sx, m, dDA, sCountry):
    return ( morphex(dDA, (m.start(2), m.group(2)), ":N.*:[me]:s", ":[GW]") or (re.search("(?i)^[aeéiîou]", m.group(2)) and morphex(dDA, (m.start(2), m.group(2)), ":N.*:f:s", ":G")) ) and ( look(s[:m.start()], r"(?i)^ *$|\b(?:à|avec|chez|dès|contre|devant|derrière|en|par|pour|sans|sur) +$|, +$") or (morphex(dDA, prevword1(s, m.start()), ":V", ":(?:G|W|[NA].*:[pi])") and not look(s[:m.start()], r"(?i)\bce que?\b")) )
def s4197s_1 (s, m):
    return m.group(1).replace("sur", "sûr")
def s4200s_1 (s, m):
    return m.group(1).replace("sur", "sûr")
def c4206s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":M1", False)
def c4209s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":Y", False)
def s4209s_1 (s, m):
    return m.group(1).replace("sur", "sûr")
def c4218s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":N", ":[GMY]|>(?:fond|envergure|ampleur|importance) ")
def s4218s_1 (s, m):
    return m.group(1).replace("â", "a")
def s4222s_1 (s, m):
    return m.group(1).replace("â", "a")
def c4232s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ">aller ", False)
def c4235s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ">faire ", False)
def s4238s_1 (s, m):
    return m.group(1).replace("taule", "tôle")
def c4248s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0e", False) and morph(dDA, (m.start(3), m.group(3)), ":Y", False)
def c4256s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">avoir ", False)
def c4281s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:[me]:s")
def c4300s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">ouvrir ", False)
def c4309s_1 (s, sx, m, dDA, sCountry):
    return not prevword1(s, m.start()) and morph(dDA, (m.start(2), m.group(2)), ":A") and not morph(dDA, nextword1(s, m.end()), ":D", False, False)
def c4338s_1 (s, sx, m, dDA, sCountry):
    return not m.group(1).isdigit() and not m.group(2).isdigit() and not morph(dDA, (m.start(0), m.group(0)), ":", False) and not morph(dDA, (m.start(2), m.group(2)), ":G", False) and _oDict.isValid(m.group(1)+m.group(2))
def c4338s_2 (s, sx, m, dDA, sCountry):
    return m.group(2) != u"là" and not re.search("(?i)^(?:ex|mi|quasi|semi|non|demi|pro|anti|multi|pseudo|proto|extra)$", m.group(1)) and not m.group(1).isdigit() and not m.group(2).isdigit() and not morph(dDA, (m.start(2), m.group(2)), ":G", False) and not morph(dDA, (m.start(0), m.group(0)), ":", False) and not _oDict.isValid(m.group(1)+m.group(2))
def c4351s_1 (s, sx, m, dDA, sCountry):
    return look(s[:m.start()], r"[\w,] +$")
def s4351s_1 (s, m):
    return m.group(0).lower()
def c4356s_1 (s, sx, m, dDA, sCountry):
    return look(s[:m.start()], r"[\w,] +$") and not( ( m.group(0)=="Juillet" and look(s[:m.start()], "(?i)monarchie +de +$") ) or ( m.group(0)=="Octobre" and look(s[:m.start()], "(?i)révolution +d’$") ) )
def s4356s_1 (s, m):
    return m.group(0).lower()
def c4375s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^fonctions? ", m.group(0)) or not look(s[:m.start()], r"(?i)\ben $")
def c4382s_1 (s, sx, m, dDA, sCountry):
    return m.group(2).istitle() and morphex(dDA, (m.start(1), m.group(1)), ":N", ":(?:A|V0e|D|R|B)") and not re.search("(?i)^[oO]céan Indien", m.group(0))
def s4382s_1 (s, m):
    return m.group(2).lower()
def c4382s_2 (s, sx, m, dDA, sCountry):
    return m.group(2).islower() and not m.group(2).startswith("canadienne") and ( re.search("(?i)^(?:certaine?s?|cette|ce[ts]?|[dl]es|[nv]os|quelques|plusieurs|chaque|une)$", m.group(1)) or ( re.search("(?i)^un$", m.group(1)) and not look(s[m.end():], "(?:approximatif|correct|courant|parfait|facile|aisé|impeccable|incompréhensible)") ) )
def s4382s_2 (s, m):
    return m.group(2).capitalize()
def s4396s_1 (s, m):
    return m.group(1).capitalize()
def c4400s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:parler|cours|leçon|apprendre|étudier|traduire|enseigner|professeur|enseignant|dictionnaire|méthode) ", False)
def s4400s_1 (s, m):
    return m.group(2).lower()
def s4405s_1 (s, m):
    return m.group(1).lower()
def c4417s_1 (s, sx, m, dDA, sCountry):
    return not prevword1(s, m.start())
def c4429s_1 (s, sx, m, dDA, sCountry):
    return look(s[:m.start()], r"\w")
def s4440s_1 (s, m):
    return m.group(1).capitalize()
def s4442s_1 (s, m):
    return m.group(1).capitalize()
def c4450s_1 (s, sx, m, dDA, sCountry):
    return re.search("^(?:Mètre|Watt|Gramme|Seconde|Ampère|Kelvin|Mole|Cand[eé]la|Hertz|Henry|Newton|Pascal|Joule|Coulomb|Volt|Ohm|Farad|Tesla|W[eé]ber|Radian|Stéradian|Lumen|Lux|Becquerel|Gray|Sievert|Siemens|Katal)s?|(?:Exa|P[ée]ta|Téra|Giga|Méga|Kilo|Hecto|Déc[ai]|Centi|Mi(?:lli|cro)|Nano|Pico|Femto|Atto|Ze(?:pto|tta)|Yo(?:cto|etta))(?:mètre|watt|gramme|seconde|ampère|kelvin|mole|cand[eé]la|hertz|henry|newton|pascal|joule|coulomb|volt|ohm|farad|tesla|w[eé]ber|radian|stéradian|lumen|lux|becquerel|gray|sievert|siemens|katal)s?", m.group(2))
def s4450s_1 (s, m):
    return m.group(2).lower()
def c4477s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":Y", False)
def c4479s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V1") and not look(s[:m.start()], r"(?i)\b(?:quelqu(?:e chose|’une?)|(?:l(es?|a)|nous|vous|me|te|se)[ @]trait|personne|rien(?: +[a-zéèêâîûù]+|) +$)")
def s4479s_1 (s, m):
    return suggVerbInfi(m.group(1))
def c4482s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V1", ":M[12P]")
def s4482s_1 (s, m):
    return suggVerbInfi(m.group(1))
def c4484s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V1", False)
def s4484s_1 (s, m):
    return suggVerbInfi(m.group(1))
def c4486s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":[123][sp]")
def c4488s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V1", ":[NM]") and not morph(dDA, prevword1(s, m.start()), ">(?:tenir|passer) ", False)
def s4488s_1 (s, m):
    return suggVerbInfi(m.group(1))
def c4491s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V1", False)
def s4491s_1 (s, m):
    return suggVerbInfi(m.group(1))
def c4493s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V1", ":[NM]")
def s4493s_1 (s, m):
    return suggVerbInfi(m.group(1))
def c4495s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":Q", False)
def c4497s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":(?:Q|2p)", False)
def s4497s_1 (s, m):
    return suggVerbInfi(m.group(1))
def c4499s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":Q", False) and not morph(dDA, prevword1(s, m.start()), "V0.*[12]p", False)
def c4501s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:devoir|savoir|pouvoir) ", False) and morphex(dDA, (m.start(2), m.group(2)), ":(?:Q|A|[13]s|2[sp])", ":[GYW]")
def s4501s_1 (s, m):
    return suggVerbInfi(m.group(2))
def c4504s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":(?:Q|A|[13]s|2[sp])", ":[GYWM]")
def s4504s_1 (s, m):
    return suggVerbInfi(m.group(1))
def s4513s_1 (s, m):
    return m.group(1)[:-1]
def c4538s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V", False)
def c4542s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">sembler ", False)
def c4556s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ]", False) and isEndOfNG(dDA, s[m.end():], m.end())
def c4559s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V[123]_i_._") and isEndOfNG(dDA, s[m.end():], m.end())
def c4561s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":A", False) and morphex(dDA, (m.start(2), m.group(2)), ":A", ":[GM]")
def c4563s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":A", False)
def c4565s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:s", False) and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s", ":[GV]") and isEndOfNG(dDA, s[m.end():], m.end())
def c4567s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":N", ":[GY]") and isEndOfNG(dDA, s[m.end():], m.end())
def c4570s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ]", ":V0") and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ]", ":(?:G|[123][sp]|P)")
def c4581s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ]", False) and isEndOfNG(dDA, s[m.end():], m.end())
def c4585s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], "[jn]’$")
def c4593s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ]", ":G") and isEndOfNG(dDA, s[m.end():], m.end())
def c4596s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ]", False) and isEndOfNG(dDA, s[m.end():], m.end())
def c4599s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ]", False) and isEndOfNG(dDA, s[m.end():], m.end())
def c4603s_1 (s, sx, m, dDA, sCountry):
    return not prevword1(s, m.start())
def c4606s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":N", ":[GY]") and isEndOfNG(dDA, s[m.end():], m.end())
def c4608s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ]", False) and isEndOfNG(dDA, s[m.end():], m.end())
def c4610s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ]", ":Y") and isEndOfNG(dDA, s[m.end():], m.end())
def c4642s_1 (s, sx, m, dDA, sCountry):
    return re.search("(?i)^(?:fini|terminé)s?", m.group(2)) and morph(dDA, prevword1(s, m.start()), ":C", False, True)
def c4642s_2 (s, sx, m, dDA, sCountry):
    return re.search("(?i)^(?:assez|trop)$", m.group(2)) and (look(s[m.end():], "^ +d(?:e |’)") or not nextword1(s, m.end()))
def c4642s_3 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":A", ":[GVW]") and morph(dDA, prevword1(s, m.start()), ":C", False, True)
def c4654s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">aller", False) and not look(s[m.end():], " soit ")
def c4662s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V", False)
def s4662s_1 (s, m):
    return suggVerbInfi(m.group(1))
def c4664s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V", False)
def s4664s_1 (s, m):
    return suggVerbInfi(m.group(1))
def c4666s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V", False)
def s4666s_1 (s, m):
    return suggVerbInfi(m.group(1))
def c4669s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:faire|vouloir) ", False) and not look(s[:m.start()], r"(?i)\b(?:en|[mtsld]es?|[nv]ous|un) +$") and morphex(dDA, (m.start(2), m.group(2)), ":V", ":M")
def s4669s_1 (s, m):
    return suggVerbInfi(m.group(2))
def c4672s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">savoir :V", False) and morph(dDA, (m.start(2), m.group(2)), ":V", False) and not look(s[:m.start()], r"(?i)\b(?:[mts]e|[vn]ous|les?|la|un) +$")
def s4672s_1 (s, m):
    return suggVerbInfi(m.group(2))
def c4675s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":(?:Q|2p)", False)
def s4675s_1 (s, m):
    return suggVerbInfi(m.group(1))
def c4678s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":(?:Q|2p)", ":N")
def s4678s_1 (s, m):
    return suggVerbInfi(m.group(1))
def c4722s_1 (s, sx, m, dDA, sCountry):
    return (morph(dDA, (m.start(2), m.group(2)), ">(?:être|sembler|devenir|re(?:ster|devenir)|para[îi]tre) ", False) or m.group(2).endswith(" été")) and morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:p", ":[GWYsi]")
def s4722s_1 (s, m):
    return suggSing(m.group(3))
def c4726s_1 (s, sx, m, dDA, sCountry):
    return (morph(dDA, (m.start(1), m.group(1)), ">(?:être|sembler|devenir|re(?:ster|devenir)|para[îi]tre) ", False) or m.group(1).endswith(" été")) and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p", ":[GWYsi]")
def s4726s_1 (s, m):
    return suggSing(m.group(2))
def c4730s_1 (s, sx, m, dDA, sCountry):
    return (morph(dDA, (m.start(2), m.group(2)), ">(?:être|sembler|devenir|re(?:ster|devenir)|para[îi]tre) ", False) or m.group(2).endswith(" été")) and (morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:p", ":[GWYsi]") or morphex(dDA, (m.start(3), m.group(3)), ":[AQ].*:f", ":[GWYme]"))
def s4730s_1 (s, m):
    return suggMasSing(m.group(3))
def c4735s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:p", ":[GWYsi]") or ( morphex(dDA, (m.start(1), m.group(1)), ":[AQ].*:f", ":[GWYme]") and not morph(dDA, nextword1(s, m.end()), ":N.*:f", False, False) )
def s4735s_1 (s, m):
    return suggMasSing(m.group(1))
def c4739s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ].*:p", ":[GWYsi]") or ( morphex(dDA, (m.start(1), m.group(1)), ":[AQ].*:f", ":[GWYme]") and not morph(dDA, nextword1(s, m.end()), ":N.*:f", False, False) )
def s4739s_1 (s, m):
    return suggMasSing(m.group(1))
def c4743s_1 (s, sx, m, dDA, sCountry):
    return (morph(dDA, (m.start(2), m.group(2)), ">(?:être|sembler|devenir|re(?:ster|devenir)|para[îi]tre) ", False) or m.group(2).endswith(" été")) and (morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:p", ":[GWYsi]") or morphex(dDA, (m.start(3), m.group(3)), ":[AQ].*:f", ":[GWYme]")) and not morph(dDA, prevword1(s, m.start()), ":R", False, False)
def s4743s_1 (s, m):
    return suggMasSing(m.group(3))
def c4749s_1 (s, sx, m, dDA, sCountry):
    return (morph(dDA, (m.start(2), m.group(2)), ">(?:être|sembler|devenir|re(?:ster|devenir)|para[îi]tre) ", False) or m.group(2).endswith(" été")) and (morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:p", ":[GWYsi]") or morphex(dDA, (m.start(3), m.group(3)), ":[AQ].*:m", ":[GWYfe]")) and not morph(dDA, prevword1(s, m.start()), ":R|>de ", False, False)
def s4749s_1 (s, m):
    return suggFemSing(m.group(3))
def c4755s_1 (s, sx, m, dDA, sCountry):
    return (morph(dDA, (m.start(2), m.group(2)), ">(?:être|sembler|devenir|re(?:ster|devenir)|para[îi]tre) ", False) or m.group(2).endswith(" été")) and (morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:p", ":[GWYsi]") or morphex(dDA, (m.start(3), m.group(3)), ":[AQ].*:m", ":[GWYfe]"))
def s4755s_1 (s, m):
    return suggFemSing(m.group(3))
def c4760s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^légion$", m.group(2)) and not look(s[:m.start()], r"(?i)\b(?:nous|ne) +$") and ((morph(dDA, (m.start(1), m.group(1)), ">(?:être|sembler|devenir|re(?:ster|devenir)|para[îi]tre) ", False) and morph(dDA, (m.start(1), m.group(1)), ":1p", False)) or m.group(1).endswith(" été")) and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s", ":[GWYpi]")
def s4760s_1 (s, m):
    return suggPlur(m.group(2))
def c4766s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^légion$", m.group(3)) and (morph(dDA, (m.start(2), m.group(2)), ">(?:être|sembler|devenir|re(?:ster|devenir)|para[îi]tre) ", False) or m.group(2).endswith(" été")) and (morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:s", ":[GWYpi]") or morphex(dDA, (m.start(3), m.group(3)), ":[AQ].*:f", ":[GWYme]")) and not look(s[:m.start()], "(?i)ce que? +$") and (not re.search("^(?:ceux-(?:ci|là)|lesquels)$", m.group(1)) or not morph(dDA, prevword1(s, m.start()), ":R", False, False))
def s4766s_1 (s, m):
    return suggMasPlur(m.group(3))
def c4772s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^légion$", m.group(3)) and (morph(dDA, (m.start(2), m.group(2)), ">(?:être|sembler|devenir|re(?:ster|devenir)|para[îi]tre) ", False) or m.group(2).endswith(" été")) and (morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:s", ":[GWYpi]") or morphex(dDA, (m.start(3), m.group(3)), ":[AQ].*:m", ":[GWYfe]")) and (not re.search("(?i)^(?:elles|celles-(?:ci|là)|lesquelles)$", m.group(1)) or not morph(dDA, prevword1(s, m.start()), ":R", False, False))
def s4772s_1 (s, m):
    return suggFemPlur(m.group(3))
def c4778s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">avoir ", False) and morphex(dDA, (m.start(2), m.group(2)), ":[123]s", ":[GNAQWY]")
def s4778s_1 (s, m):
    return suggVerbPpas(m.group(2))
def c4859s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ">(?:sembler|para[îi]tre|pouvoir|penser|préférer|croire|d(?:evoir|éclarer|ésirer|étester|ire)|vouloir|affirmer|aimer|adorer|souhaiter|estimer|imaginer) ", False) and morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:p", ":[GWYsi]")
def s4859s_1 (s, m):
    return suggSing(m.group(3))
def c4863s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:sembler|para[îi]tre|pouvoir|penser|préférer|croire|d(?:evoir|éclarer|ésirer|étester|ire)|vouloir|affirmer|aimer|adorer|souhaiter|estimer|imaginer) ", False) and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p", ":[GWYsi]")
def s4863s_1 (s, m):
    return suggSing(m.group(2))
def c4867s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ">(?:sembler|para[îi]tre|pouvoir|penser|préférer|croire|d(?:evoir|éclarer|ésirer|étester|ire)|vouloir|affirmer|aimer|adorer|souhaiter|estimer|imaginer) ", False) and (morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:p", ":[GWYsi]") or morphex(dDA, (m.start(3), m.group(3)), ":[AQ].*:f", ":[GWYme]"))
def s4867s_1 (s, m):
    return suggMasSing(m.group(3))
def c4872s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ">(?:sembler|para[îi]tre|pouvoir|penser|préférer|croire|d(?:evoir|éclarer|ésirer|étester|ire)|vouloir|affirmer|aimer|adorer|souhaiter|estimer|imaginer) ", False) and (morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:p", ":[MWYsi]") or morphex(dDA, (m.start(3), m.group(3)), ":[AQ].*:f", ":[GWYme]")) and not morph(dDA, prevword1(s, m.start()), ":R", False, False)
def s4872s_1 (s, m):
    return suggMasSing(m.group(3))
def c4878s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ">(?:sembler|para[îi]tre|pouvoir|penser|préférer|croire|d(?:evoir|éclarer|ésirer|étester|ire)|vouloir|affirmer|aimer|adorer|souhaiter|estimer|imaginer) ", False) and (morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:p", ":[GWYsi]") or morphex(dDA, (m.start(3), m.group(3)), ":[AQ].*:m", ":[GWYfe]")) and not morph(dDA, prevword1(s, m.start()), ":R", False, False)
def s4878s_1 (s, m):
    return suggFemSing(m.group(3))
def c4884s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ">(?:sembler|para[îi]tre|pouvoir|penser|préférer|croire|d(?:evoir|éclarer|ésirer|étester|ire)|vouloir|affirmer|aimer|adorer|souhaiter|estimer|imaginer) ", False) and (morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:p", ":[MWYsi]") or morphex(dDA, (m.start(3), m.group(3)), ":[AQ].*:m", ":[GWYfe]"))
def s4884s_1 (s, m):
    return suggFemSing(m.group(3))
def c4889s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^légion$", m.group(2)) and morph(dDA, (m.start(1), m.group(1)), ">(?:sembler|para[îi]tre|pouvoir|penser|préférer|croire|d(?:evoir|éclarer|ésirer|étester|ire)|vouloir|affirmer|aimer|adorer|souhaiter|estimer|imaginer) ", False) and morph(dDA, (m.start(1), m.group(1)), ":1p", False) and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s", ":[GWYpi]")
def s4889s_1 (s, m):
    return suggPlur(m.group(2))
def c4894s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^légion$", m.group(3)) and morph(dDA, (m.start(2), m.group(2)), ">(?:sembler|para[îi]tre|pouvoir|penser|préférer|croire|d(?:evoir|éclarer|ésirer|étester|ire)|vouloir|affirmer|aimer|adorer|souhaiter|estimer|imaginer) ", False) and (morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:s", ":[GWYpi]") or morphex(dDA, (m.start(3), m.group(3)), ":[AQ].*:f", ":[GWYme]")) and (not re.search("^(?:ceux-(?:ci|là)|lesquels)$", m.group(1)) or not morph(dDA, prevword1(s, m.start()), ":R", False, False))
def s4894s_1 (s, m):
    return suggMasPlur(m.group(3))
def c4900s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^légion$", m.group(3)) and morph(dDA, (m.start(2), m.group(2)), ">(?:sembler|para[îi]tre|pouvoir|penser|préférer|croire|d(?:evoir|éclarer|ésirer|étester|ire)|vouloir|affirmer|aimer|adorer|souhaiter|estimer|imaginer) ", False) and (morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:s", ":[GWYpi]") or morphex(dDA, (m.start(3), m.group(3)), ":[AQ].*:m", ":[GWYfe]")) and (not re.search("^(?:elles|celles-(?:ci|là)|lesquelles)$", m.group(1)) or not morph(dDA, prevword1(s, m.start()), ":R", False, False))
def s4900s_1 (s, m):
    return suggFemPlur(m.group(3))
def c4931s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p", ":[GMWYsi]") and not morph(dDA, (m.start(1), m.group(1)), ":G", False)
def s4931s_1 (s, m):
    return suggSing(m.group(2))
def c4935s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^légion$", m.group(2)) and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s", ":[GWYpi]") and not morph(dDA, (m.start(1), m.group(1)), ":G", False)
def s4935s_1 (s, m):
    return suggPlur(m.group(2))
def c4940s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^légion$", m.group(3)) and ((morphex(dDA, (m.start(3), m.group(3)), ":[AQ].*:f", ":[GWme]") and morphex(dDA, (m.start(2), m.group(2)), ":m", ":[Gfe]")) or (morphex(dDA, (m.start(3), m.group(3)), ":[AQ].*:m", ":[GWfe]") and morphex(dDA, (m.start(2), m.group(2)), ":f", ":[Gme]"))) and not ( morph(dDA, (m.start(3), m.group(3)), ":p", False) and morph(dDA, (m.start(2), m.group(2)), ":s", False) ) and not morph(dDA, prevword1(s, m.start()), ":(?:R|P|Q|Y|[123][sp])", False, False) and not look(s[:m.start()], r"\b(?:et|ou|de) +$")
def s4940s_1 (s, m):
    return switchGender(m.group(3))
def c4947s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^légion$", m.group(2)) and ((morphex(dDA, (m.start(1), m.group(1)), ":M[1P].*:f", ":[GWme]") and morphex(dDA, (m.start(2), m.group(2)), ":m", ":[GWfe]")) or (morphex(dDA, (m.start(1), m.group(1)), ":M[1P].*:m", ":[GWfe]") and morphex(dDA, (m.start(2), m.group(2)), ":f", ":[GWme]"))) and not morph(dDA, prevword1(s, m.start()), ":(?:R|P|Q|Y|[123][sp])", False, False) and not look(s[:m.start()], r"\b(?:et|ou|de) +$")
def s4947s_1 (s, m):
    return switchGender(m.group(2))
def c4956s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":A.*:p", ":(?:G|E|M1|W|s|i)")
def s4956s_1 (s, m):
    return suggSing(m.group(1))
def c4960s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":A.*:[fp]", ":(?:G|E|M1|W|m:[si])")
def s4960s_1 (s, m):
    return suggMasSing(m.group(1))
def c4964s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":A.*:[mp]", ":(?:G|E|M1|W|f:[si])|>(?:désoler|pire) ")
def s4964s_1 (s, m):
    return suggFemSing(m.group(1))
def c4968s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":A.*:[fs]", ":(?:G|E|M1|W|m:[pi])|>(?:désoler|pire) ")
def s4968s_1 (s, m):
    return suggMasPlur(m.group(1))
def c4972s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":A.*:[ms]", ":(?:G|E|M1|W|f:[pi])|>(?:désoler|pire) ")
def s4972s_1 (s, m):
    return suggFemPlur(m.group(1))
def c4989s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), "V0e", False)
def c4996s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":(?:[123][sp]|Y|[NAQ].*:p)", ":[GWsi]")
def s4996s_1 (s, m):
    return suggSing(m.group(1))
def c4999s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":(?:[123][sp]|Y|[NAQ].*:p)", ":[GWsi]")
def s4999s_1 (s, m):
    return suggSing(m.group(1))
def c5002s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":(?:[123][sp]|Y|[NAQ].*:[pf])", ":(?:G|W|[me]:[si])") and not (m.group(1) == "ce" and morph(dDA, (m.start(2), m.group(2)), ":Y", False))
def s5002s_1 (s, m):
    return suggMasSing(m.group(2))
def c5005s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":(?:[123][sp]|Y|[NAQ].*:[pm])", ":(?:G|W|[fe]:[si])")
def s5005s_1 (s, m):
    return suggFemSing(m.group(1))
def c5008s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":(?:[123][sp]|Y|[NAQ].*:s)", ":[GWpi]")
def s5008s_1 (s, m):
    return suggPlur(m.group(1))
def c5011s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^légion$", m.group(1)) and (morphex(dDA, (m.start(1), m.group(1)), ":(?:[123][sp]|Y|[NAQ].*:s)", ":[GWpi]") or morphex(dDA, (m.start(1), m.group(1)), ":(?:[123][sp]|[AQ].*:f)", ":[GWme]"))
def s5011s_1 (s, m):
    return suggMasPlur(m.group(1))
def c5014s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^légion$", m.group(1)) and (morphex(dDA, (m.start(1), m.group(1)), ":(?:[123][sp]|Y|[NAQ].*:s)", ":[GWpi]") or morphex(dDA, (m.start(1), m.group(1)), ":(?:[123][sp]|[AQ].*:m)", ":[GWfe]"))
def s5014s_1 (s, m):
    return suggFemPlur(m.group(1))
def c5043s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[NAQ]", ":[QWGBMpi]") and not re.search("(?i)^(?:légion|nombre|cause)$", m.group(1)) and not look(s[:m.start()], r"(?i)\bce que?\b")
def s5043s_1 (s, m):
    return suggPlur(m.group(1))
def c5043s_2 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":(?:N|A|Q|W|G|3p)") and not look(s[:m.start()], r"(?i)\bce que?\b")
def s5043s_2 (s, m):
    return suggVerbPpas(m.group(1), ":m:p")
def c5054s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:montrer|penser|révéler|savoir|sentir|voir|vouloir) ", False) and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p", ":[GWsi]")
def s5054s_1 (s, m):
    return suggSing(m.group(2))
def c5058s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:montrer|penser|révéler|savoir|sentir|voir|vouloir) ", False) and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:p", ":[GWsi]")
def s5058s_1 (s, m):
    return suggSing(m.group(2))
def c5062s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ">(?:montrer|penser|révéler|savoir|sentir|voir|vouloir) ", False) and (morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:p", ":[GWsi]") or morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:f", ":[GWme]")) and (not re.search("^(?:celui-(?:ci|là)|lequel)$", m.group(1)) or not morph(dDA, prevword1(s, m.start()), ":R", False, False))
def s5062s_1 (s, m):
    return suggMasSing(m.group(3))
def c5068s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ">(?:montrer|penser|révéler|savoir|sentir|voir|vouloir) ", False) and (morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:p", ":[GWsi]") or morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:m", ":[GWfe]")) and not morph(dDA, prevword1(s, m.start()), ":R", False, False)
def s5068s_1 (s, m):
    return suggFemSing(m.group(3))
def c5074s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ">(?:montrer|penser|révéler|savoir|sentir|voir|vouloir) ", False) and (morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:p", ":[GWsi]") or morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:m", ":[GWfe]"))
def s5074s_1 (s, m):
    return suggFemSing(m.group(3))
def c5079s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:montrer|penser|révéler|savoir|sentir|voir|vouloir) ", False) and morphex(dDA, (m.start(2), m.group(2)), ":[NAQ].*:s", ":[GWpi]")
def s5079s_1 (s, m):
    return suggPlur(m.group(2))
def c5083s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ">(?:montrer|penser|révéler|savoir|sentir|voir|vouloir) ", False) and (morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:s", ":[GWpi]") or morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:f", ":[GWme]")) and (not re.search("^(?:ceux-(?:ci|là)|lesquels)$", m.group(1)) or not morph(dDA, prevword1(s, m.start()), ":R", False, False))
def s5083s_1 (s, m):
    return suggMasPlur(m.group(3))
def c5089s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ">(?:montrer|penser|révéler|savoir|sentir|voir|vouloir) ", False) and (morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:s", ":[GWpi]") or morphex(dDA, (m.start(3), m.group(3)), ":[NAQ].*:m", ":[GWfe]")) and (not re.search("^(?:elles|celles-(?:ci|là)|lesquelles)$", m.group(1)) or not morph(dDA, prevword1(s, m.start()), ":R", False, False))
def s5089s_1 (s, m):
    return suggFemPlur(m.group(3))
def c5097s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:trouver|considérer|croire) ", False) and morphex(dDA, (m.start(2), m.group(2)), ":[AQ]:(?:m:p|f)", ":(?:G|[AQ]:m:[is])")
def s5097s_1 (s, m):
    return suggMasSing(m.group(2))
def c5100s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:trouver|considérer|croire) ", False) and morphex(dDA, (m.start(2), m.group(2)), ":[AQ]:(?:f:p|m)", ":(?:G|[AQ]:f:[is])")
def s5100s_1 (s, m):
    return suggFemSing(m.group(2))
def c5103s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:trouver|considérer|croire) ", False) and morphex(dDA, (m.start(2), m.group(2)), ":[AQ].*:s", ":(?:G|[AQ].*:[ip])")
def s5103s_1 (s, m):
    return suggPlur(m.group(2))
def c5106s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ">(?:trouver|considérer|croire) ", False) and morphex(dDA, (m.start(3), m.group(3)), ":[AQ].*:p", ":(?:G|[AQ].*:[is])")
def s5106s_1 (s, m):
    return suggSing(m.group(3))
def c5109s_1 (s, sx, m, dDA, sCountry):
    return ( morphex(dDA, (m.start(1), m.group(1)), ">(?:trouver|considérer|croire) ", ":1p") or (morph(dDA, (m.start(1), m.group(1)), ">(?:trouver|considérer|croire) .*:1p", False) and look(s[:m.start()], r"\bn(?:ous|e) +$")) ) and morphex(dDA, (m.start(2), m.group(2)), ":[AQ].*:s", ":(?:G|[AQ].*:[ip])")
def s5109s_1 (s, m):
    return suggPlur(m.group(2))
def c5131s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^(?:confiance|cours|envie|peine|prise|crainte|cure|affaire|hâte|force|recours)$", m.group(3)) and morph(dDA, (m.start(2), m.group(2)), ":V0a", False) and morphex(dDA, (m.start(3), m.group(3)), ":(?:[123][sp]|Q.*:[fp])", ":(?:G|W|Q.*:m:[si])")
def s5131s_1 (s, m):
    return suggMasSing(m.group(3))
def c5137s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^(?:confiance|cours|envie|peine|prise|crainte|cure|affaire|hâte|force|recours)$", m.group(4)) and morph(dDA, (m.start(3), m.group(3)), ":V0a", False) and morphex(dDA, (m.start(4), m.group(4)), ":(?:[123][sp]|Q.*:[fp])", ":(?:G|W|Q.*:m:[si])")
def s5137s_1 (s, m):
    return suggMasSing(m.group(4))
def c5143s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0a", False) and morphex(dDA, (m.start(2), m.group(2)), ":V[0-3]..t.*:Q.*:s", ":[GWpi]") and not morph(dDA, nextword1(s, m.end()), ":V", False)
def s5143s_1 (s, m):
    return suggPlur(m.group(2))
def c5148s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0a", False) and morphex(dDA, (m.start(2), m.group(2)), ":V[0-3]..t_.*:Q.*:s", ":[GWpi]") and not look(s[:m.start()], r"\bque?\b")
def s5148s_1 (s, m):
    return suggPlur(m.group(2))
def c5153s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0a", False) and morphex(dDA, (m.start(2), m.group(2)), ":V[0-3]..t.*:Q.*:p", ":[GWsi]") and not morph(dDA, nextword1(s, m.end()), ":V", False)
def s5153s_1 (s, m):
    return m.group(2)[:-1]
def c5158s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":V0a", False) and morphex(dDA, (m.start(3), m.group(3)), ":V[0-3]..t_.*:Q.*:p", ":[GWsi]") and not look(s[:m.start()], r"\bque?\b") and not morph(dDA, nextword1(s, m.end()), ":V", False)
def s5158s_1 (s, m):
    return m.group(3)[:-1]
def c5163s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":Q.*:(?:f|m:p)", ":m:[si]")
def s5163s_1 (s, m):
    return suggMasSing(m.group(1))
def c5169s_1 (s, sx, m, dDA, sCountry):
    return not re.search("(?i)^(?:confiance|cours|envie|peine|prise|crainte|cure|affaire|hâte|force|recours)$", m.group(1)) and morphex(dDA, (m.start(1), m.group(1)), ":Q.*:(?:f|m:p)", ":m:[si]") and look(s[:m.start()], "(?i)(?:après +$|sans +$|pour +$|que? +$|quand +$|, +$|^ *$)")
def s5169s_1 (s, m):
    return suggMasSing(m.group(1))
def c5199s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(3), m.group(3)), ":V0a", False) and not (re.search("^(?:décidé|essayé|tenté)$", m.group(4)) and look(s[m.end():], " +d(?:e |’)")) and morph(dDA, (m.start(2), m.group(2)), ":[NAQ]", False) and morphex(dDA, (m.start(4), m.group(4)), ":V[0-3]..t.*:Q.*:s", ":[GWpi]") and not morph(dDA, nextword1(s, m.end()), ":(?:Y|Oo)", False)
def s5199s_1 (s, m):
    return suggPlur(m.group(4), m.group(2))
def c5207s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(3), m.group(3)), ":V0a", False) and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:m", False) and (morphex(dDA, (m.start(4), m.group(4)), ":V[0-3]..t.*:Q.*:f", ":[GWme]") or morphex(dDA, (m.start(4), m.group(4)), ":V[0-3]..t.*:Q.*:p", ":[GWsi]"))
def s5207s_1 (s, m):
    return suggMasSing(m.group(4))
def c5214s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(3), m.group(3)), ":V0a", False) and not (re.search("^(?:décidé|essayé|tenté)$", m.group(4)) and look(s[m.end():], " +d(?:e |’)")) and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:f", False) and (morphex(dDA, (m.start(4), m.group(4)), ":V[0-3]..t.*:Q.*:m", ":[GWfe]") or morphex(dDA, (m.start(4), m.group(4)), ":V[0-3]..t.*:Q.*:p", ":[GWsi]")) and not morph(dDA, nextword1(s, m.end()), ":(?:Y|Oo)|>que?", False)
def s5214s_1 (s, m):
    return suggFemSing(m.group(4))
def c5234s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0a", False) and (morphex(dDA, (m.start(2), m.group(2)), ":V[0-3]..t.*:Q.*:f", ":[GWme]") or morphex(dDA, (m.start(2), m.group(2)), ":V[0-3]..t.*:Q.*:p", ":[GWsi]"))
def s5234s_1 (s, m):
    return suggMasSing(m.group(2))
def c5240s_1 (s, sx, m, dDA, sCountry):
    return not re.search("^(?:A|avions)$", m.group(1)) and morph(dDA, (m.start(1), m.group(1)), ":V0a", False) and morph(dDA, (m.start(2), m.group(2)), ":V.+:(?:Y|2p)", False)
def s5240s_1 (s, m):
    return suggVerbPpas(m.group(2), ":m:s")
def c5246s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0a", False) and (morph(dDA, (m.start(3), m.group(3)), ":Y") or re.search("^(?:[mtsn]e|[nv]ous|leur|lui)$", m.group(3)))
def c5250s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0a", False) and (morph(dDA, (m.start(3), m.group(3)), ":Y") or re.search("^(?:[mtsn]e|[nv]ous|leur|lui)$", m.group(3)))
def c5256s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, nextword1(s, m.end()), ":[NAQ].*:[me]", False)
def c5258s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0e", False)
def c5275s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0a", False) and morphex(dDA, (m.start(2), m.group(2)), ":(?:Y|2p|Q.*:[fp])", ":m:[si]") and m.group(2) != "prise" and not morph(dDA, prevword1(s, m.start()), ">(?:les|[nv]ous|en)|:[NAQ].*:[fp]", False) and not look(s[:m.start()], r"(?i)\bquel(?:le|)s?\b")
def s5275s_1 (s, m):
    return suggMasSing(m.group(2))
def c5281s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":V0a", False) and morphex(dDA, (m.start(3), m.group(3)), ":(?:Y|2p|Q.*:p)", ":[si]")
def s5281s_1 (s, m):
    return suggMasSing(m.group(3))
def c5286s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0a", False) and morphex(dDA, (m.start(2), m.group(2)), ":V[123]..t.* :Q.*:s", ":[GWpi]")
def s5286s_1 (s, m):
    return suggPlur(m.group(2))
def c5292s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":(?:G|Y|P|1p|3[sp])") and not look(s[m.end():], "^ +(?:je|tu|ils?|elles?|on|[vn]ous) ")
def s5292s_1 (s, m):
    return suggVerb(m.group(1), ":1p")
def c5298s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":(?:G|Y|P|2p|3[sp])") and not look(s[m.end():], "^ +(?:je|ils?|elles?|on|[vn]ous) ")
def s5298s_1 (s, m):
    return suggVerb(m.group(1), ":2p")
def c5335s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[NAQ]", ":G")
def c5343s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V[13].*:Ip.*:2s", ":[GNA]")
def s5343s_1 (s, m):
    return m.group(1)[:-1]
def c5346s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V[13].*:Ip.*:2s", ":G")
def s5346s_1 (s, m):
    return m.group(1)[:-1]
def c5351s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[MOs]")
def c5354s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V[23].*:Ip.*:3s", ":[GNA]") and analyse(m.group(1)[:-1]+"s", ":E:2s", False) and not re.search("(?i)^doit$", m.group(1)) and not (re.search("(?i)^vient$", m.group(1)) and look(s[m.end():], " +l[ea]"))
def s5354s_1 (s, m):
    return m.group(1)[:-1]+"s"
def c5358s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V[23].*:Ip.*:3s", ":G") and analyse(m.group(1)[:-1]+"s", ":E:2s", False)
def s5358s_1 (s, m):
    return m.group(1)[:-1]+"s"
def c5363s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V3.*:Ip.*:3s", ":[GNA]")
def c5366s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V3.*:Ip.*:3s", ":G")
def c5376s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":A", ":G") and not look(s[m.end():], r"\bsoit\b")
def c5387s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":E|>chez", False) and _oDict.isValid(m.group(1))
def s5387s_1 (s, m):
    return suggVerbImpe(m.group(1))
def c5392s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":E|>chez", False) and _oDict.isValid(m.group(1))
def s5392s_1 (s, m):
    return suggVerbTense(m.group(1), ":E", ":2s")
def c5417s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":E", ":[GM]")
def c5422s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":E", ":[GM]") and morphex(dDA, nextword1(s, m.end()), ":", ":(?:Y|3[sp])", True) and morph(dDA, prevword1(s, m.start()), ":Cc", False, True) and not look(s[:m.start()], "~ +$")
def c5427s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":E", ":[GM]") and morphex(dDA, nextword1(s, m.end()), ":", ":(?:N|A|Q|Y|B|3[sp])", True) and morph(dDA, prevword1(s, m.start()), ":Cc", False, True) and not look(s[:m.start()], "~ +$")
def c5432s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":E", ":[GM]") and morphex(dDA, nextword1(s, m.end()), ":", ":(?:N|A|Q|Y|MP)", True) and morph(dDA, prevword1(s, m.start()), ":Cc", False, True) and not look(s[:m.start()], "~ +$")
def c5450s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":E", ":(?:G|M[12])") and morphex(dDA, nextword1(s, m.end()), ":", ":(?:Y|[123][sp])", True)
def s5450s_1 (s, m):
    return m.group(0).replace(" ", "-")
def c5455s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":E", False)
def s5455s_1 (s, m):
    return m.group(0).replace(" ", "-")
def c5460s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":E", False) and morphex(dDA, nextword1(s, m.end()), ":[RC]", ":[NAQ]", True)
def s5460s_1 (s, m):
    return m.group(0).replace(" ", "-")
def c5465s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":E", False) and morphex(dDA, nextword1(s, m.end()), ":[RC]", ":Y", True)
def s5465s_1 (s, m):
    return m.group(0).replace(" ", "-")
def c5471s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, nextword1(s, m.end()), ":Y", False, False)
def s5471s_1 (s, m):
    return m.group(0).replace(" ", "-")
def c5473s_1 (s, sx, m, dDA, sCountry):
    return not prevword1(s, m.start()) and not morph(dDA, nextword1(s, m.end()), ":Y", False, False)
def s5475s_1 (s, m):
    return m.group(0).replace(" ", "-")
def c5501s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":R", False, True)
def c5502s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":R", False, False)
def c5504s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":R", False, False)
def c5506s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[123][sp]")
def c5507s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":[123]s", False, False)
def c5508s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":(?:[123]s|R)", False, False)
def c5509s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":(?:[123]p|R)", False, False)
def c5510s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, prevword1(s, m.start()), ":3p", False, False)
def c5511s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[123][sp]", False)
def c5512s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[123][sp]", ":(?:[NAQ].*:m:[si]|G|M)")
def c5513s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[123][sp]", ":(?:[NAQ].*:f:[si]|G|M)")
def c5514s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[123][sp]", ":(?:[NAQ].*:[si]|G|M)")
def c5515s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[123][sp]", ":(?:[NAQ].*:[si]|G|M)")
def c5517s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[123][sp]", ":(?:A|G|M|1p)")
def c5518s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":[123][sp]", ":(?:A|G|M|2p)")
def c5520s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":V", False)
def c5521s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":V", False)
def c5522s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(2), m.group(2)), ":2s", False) or look(s[:m.start()], r"(?i)\b(?:je|tu|on|ils?|elles?|nous) +$")
def c5523s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(2), m.group(2)), ":2s|>(ils?|elles?|on) ", False) or look(s[:m.start()], r"(?i)\b(?:je|tu|on|ils?|elles?|nous) +$")
def c5537s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V", False)
def c5540s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":Y")
def c5554s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\b(?:ce que?|tout) ")
def c5567s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":M") and not (m.group(1).endswith("ez") and look(s[m.end():], " +vous"))
def s5567s_1 (s, m):
    return suggVerbInfi(m.group(1))
def c5570s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":(?:Q|2p)", ":M")
def s5570s_1 (s, m):
    return suggVerbInfi(m.group(1))
def c5573s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:aimer|aller|désirer|devoir|espérer|pouvoir|préférer|souhaiter|venir) ", False) and not morph(dDA, (m.start(1), m.group(1)), ":[GN]", False) and morphex(dDA, (m.start(2), m.group(2)), ":V", ":M")
def s5573s_1 (s, m):
    return suggVerbInfi(m.group(2))
def c5577s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">devoir ", False) and morphex(dDA, (m.start(2), m.group(2)), ":V", ":M") and not morph(dDA, prevword1(s, m.start()), ":D", False)
def s5577s_1 (s, m):
    return suggVerbInfi(m.group(2))
def c5580s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:cesser|décider|défendre|suggérer|commander|essayer|tenter|choisir|permettre|interdire) ", False) and morphex(dDA, (m.start(2), m.group(2)), ":(?:Q|2p)", ":M")
def s5580s_1 (s, m):
    return suggVerbInfi(m.group(2))
def c5583s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":(?:Q|2p)", ":M")
def s5583s_1 (s, m):
    return suggVerbInfi(m.group(1))
def c5586s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">valoir ", False) and morphex(dDA, (m.start(2), m.group(2)), ":(?:Q|2p)", ":[GM]")
def s5586s_1 (s, m):
    return suggVerbInfi(m.group(2))
def c5589s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V1", ":[NM]") and not m.group(1).istitle() and not look(s[:m.start()], "> +$")
def s5589s_1 (s, m):
    return suggVerbInfi(m.group(1))
def c5592s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V1", ":N")
def s5592s_1 (s, m):
    return suggVerbInfi(m.group(2))
def c5605s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":V0e", False) and (morphex(dDA, (m.start(2), m.group(2)), ":Y", ":[NAQ]") or m.group(2) in aSHOULDBEVERB) and not re.search("(?i)^(?:soit|été)$", m.group(1)) and not morph(dDA, prevword1(s, m.start()), ":Y|>ce", False, False) and not look(s[:m.start()], "(?i)ce (?:>|qu|que >) $") and not look_chk1(dDA, s[:m.start()], 0, r"(\w[\w-]+) +> $", ":Y") and not look_chk1(dDA, s[:m.start()], 0, r"^ *>? *(\w[\w-]+)", ":Y")
def s5605s_1 (s, m):
    return suggVerbPpas(m.group(2))
def c5616s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":1s|>(?:en|y)", False)
def s5616s_1 (s, m):
    return suggVerb(m.group(1), ":1s")
def c5619s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:1s|G)") and not (morph(dDA, (m.start(2), m.group(2)), ":[PQ]", False) and morph(dDA, prevword1(s, m.start()), ":V0.*:1s", False, False))
def s5619s_1 (s, m):
    return suggVerb(m.group(2), ":1s")
def c5622s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:1s|G|1p)")
def s5622s_1 (s, m):
    return suggVerb(m.group(2), ":1s")
def c5625s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:1s|G|1p)")
def s5625s_1 (s, m):
    return suggVerb(m.group(2), ":1s")
def c5628s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:1s|G|1p|3p!)")
def s5628s_1 (s, m):
    return suggVerb(m.group(2), ":1s")
def c5648s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:G|[ISK].*:2s)") and not (morph(dDA, (m.start(2), m.group(2)), ":[PQ]", False) and morph(dDA, prevword1(s, m.start()), ":V0.*:2s", False, False))
def s5648s_1 (s, m):
    return suggVerb(m.group(2), ":2s")
def c5651s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:G|[ISK].*:2s)")
def s5651s_1 (s, m):
    return suggVerb(m.group(2), ":2s")
def c5654s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:G|2p|3p!|[ISK].*:2s)")
def s5654s_1 (s, m):
    return suggVerb(m.group(2), ":2s")
def c5665s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:3s|P|G)") and not (morph(dDA, (m.start(2), m.group(2)), ":[PQ]", False) and morph(dDA, prevword1(s, m.start()), ":V0.*:3s", False, False))
def s5665s_1 (s, m):
    return suggVerb(m.group(2), ":3s")
def c5668s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:3s|P|G)")
def s5668s_1 (s, m):
    return suggVerb(m.group(2), ":3s")
def c5683s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:N|A|3s|P|Q|G|V0e.*:3p)")
def s5683s_1 (s, m):
    return suggVerb(m.group(2), ":3s")
def c5687s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:3s|P|Q|G)")
def s5687s_1 (s, m):
    return suggVerb(m.group(2), ":3s")
def c5695s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:3s|P|Q|G|3p!)") and not morph(dDA, prevword1(s, m.start()), ":[VR]|>de", False, False) and not(m.group(1).endswith("out") and morph(dDA, (m.start(2), m.group(2)), ":Y", False))
def s5695s_1 (s, m):
    return suggVerb(m.group(2), ":3s")
def c5712s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":(?:3s|P|G|3p!)") and not morph(dDA, prevword1(s, m.start()), ":R|>(?:et|ou)", False, False) and not (morph(dDA, (m.start(1), m.group(1)), ":[PQ]", False) and morph(dDA, prevword1(s, m.start()), ":V0.*:3s", False, False))
def s5712s_1 (s, m):
    return suggVerb(m.group(1), ":3s")
def c5716s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":(?:3s|P|G|3p!)") and not morph(dDA, prevword1(s, m.start()), ":R|>(?:et|ou)", False, False)
def s5716s_1 (s, m):
    return suggVerb(m.group(1), ":3s")
def c5733s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":3p", ":(?:G|3s)")
def c5736s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":3s", ":(?:G|3p)")
def c5739s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":3p", ":(?:G|3s)") and (not prevword1(s, m.start()) or look(s[:m.start()], r"(?i)\b(?:parce que?|quoi ?que?|pour ?quoi|puisque?|quand|com(?:ment|bien)|car|tandis que?) +$"))
def c5743s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":3s", ":(?:G|3p)") and (not prevword1(s, m.start()) or look(s[:m.start()], r"(?i)\b(?:parce que?|quoi ?que?|pour ?quoi|puisque?|quand|com(?:ment|bien)|car|tandis que?) +$"))
def s5751s_1 (s, m):
    return m.group(1)[:-1]+"t"
def c5754s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:3s|P|G)") and morphex(dDA, prevword1(s, m.start()), ":C", ":(?:Y|P|Q|[123][sp]|R)", True) and not( m.group(1).endswith("ien") and look(s[:m.start()], "> +$") and morph(dDA, (m.start(2), m.group(2)), ":Y", False) )
def s5754s_1 (s, m):
    return suggVerb(m.group(2), ":3s")
def c5772s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:3s|P|G|Q)") and morphex(dDA, prevword1(s, m.start()), ":C", ":(?:Y|P|Q|[123][sp]|R)", True)
def s5772s_1 (s, m):
    return suggVerb(m.group(2), ":3s")
def c5776s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:3s|P|G)") and morphex(dDA, prevword1(s, m.start()), ":C", ":(?:Y|P|Q|[123][sp]|R)", True)
def s5776s_1 (s, m):
    return suggVerb(m.group(2), ":3s")
def c5784s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":Y", False) and morph(dDA, (m.start(2), m.group(2)), ":V.[a-z_!?]+(?!.*:(?:3s|P|Q|Y|3p!))")
def s5784s_1 (s, m):
    return suggVerb(m.group(2), ":3s")
def c5792s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, prevword1(s, m.start()), ":C", ":(?:Y|P)", True) and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:[si]", False) and morphex(dDA, (m.start(3), m.group(3)), ":V", ":(?:3s|P|Q|Y|3p!|G)") and not (look(s[:m.start()], r"(?i)\b(?:et|ou) +$") and morph(dDA, (m.start(3), m.group(3)), ":[1-3]p", False)) and not look(s[:m.start()], r"(?i)\bni .* ni\b") and not checkAgreement(m.group(2), m.group(3))
def s5792s_1 (s, m):
    return suggVerb(m.group(3), ":3s")
def c5796s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, prevword1(s, m.start()), ":C", ":(?:Y|P)", True) and morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:[si]", False) and morphex(dDA, (m.start(3), m.group(3)), ":V", ":(?:3s|1p|P|Q|Y|3p!|G)") and not (look(s[:m.start()], r"(?i)\b(?:et|ou) +$") and morph(dDA, (m.start(3), m.group(3)), ":[123]p", False)) and not look(s[:m.start()], r"(?i)\bni .* ni\b")
def s5796s_1 (s, m):
    return suggVerb(m.group(3), ":3s")
def c5819s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, prevword1(s, m.start()), ":C", ":(?:Y|P)", True) and isAmbiguousAndWrong(m.group(2), m.group(3), ":s", ":3s") and not (look(s[:m.start()], r"(?i)\b(?:et|ou) +$") and morph(dDA, (m.start(3), m.group(3)), ":(?:[123]p|p)", False)) and not look(s[:m.start()], r"(?i)\bni .* ni\b")
def s5819s_1 (s, m):
    return suggVerb(m.group(3), ":3s", suggSing)
def c5824s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, prevword1(s, m.start()), ":C", ":(?:Y|P)", True) and isVeryAmbiguousAndWrong(m.group(2), m.group(3), ":s", ":3s", not prevword1(s, m.start())) and not (look(s[:m.start()], r"(?i)\b(?:et|ou) +$") and morph(dDA, (m.start(3), m.group(3)), ":(?:[123]p|p)", False)) and not look(s[:m.start()], r"(?i)\bni .* ni\b")
def s5824s_1 (s, m):
    return suggVerb(m.group(3), ":3s", suggSing)
def c5830s_1 (s, sx, m, dDA, sCountry):
    return ( morph(dDA, (m.start(0), m.group(0)), ":1s") or ( look(s[:m.start()], "> +$") and morph(dDA, (m.start(0), m.group(0)), ":1s", False) ) ) and not (m.group(0)[0:1].isupper() and look(sx[:m.start()], r"\w")) and not look(sx[:m.start()], r"(?i)\b(?:j(?:e |[’'])|moi(?:,? qui| seul) )")
def s5830s_1 (s, m):
    return suggVerb(m.group(0), ":3s")
def c5834s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(0), m.group(0)), ":2s", ":(?:E|G|W|M|J|[13][sp]|2p)") and not m.group(0)[0:1].isupper() and not look(s[:m.start()], "^ *$") and ( not morph(dDA, (m.start(0), m.group(0)), ":[NAQ]", False) or look(s[:m.start()], "> +$") ) and not look(sx[:m.start()], r"(?i)\bt(?:u |[’']|oi,? qui |oi seul )")
def s5834s_1 (s, m):
    return suggVerb(m.group(0), ":3s")
def c5839s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(0), m.group(0)), ":2s", ":(?:G|W|M|J|[13][sp]|2p)") and not (m.group(0)[0:1].isupper() and look(sx[:m.start()], r"\w")) and ( not morph(dDA, (m.start(0), m.group(0)), ":[NAQ]", False) or look(s[:m.start()], "> +$") ) and not look(sx[:m.start()], r"(?i)\bt(?:u |[’']|oi,? qui |oi seul )")
def s5839s_1 (s, m):
    return suggVerb(m.group(0), ":3s")
def c5844s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(0), m.group(0)), ":[12]s", ":(?:E|G|W|M|J|3[sp]|2p|1p)") and not (m.group(0)[0:1].isupper() and look(sx[:m.start()], r"\w")) and ( not morph(dDA, (m.start(0), m.group(0)), ":[NAQ]", False) or look(s[:m.start()], "> +$") or ( re.search("(?i)^étais$", m.group(0)) and not morph(dDA, prevword1(s, m.start()), ":[DA].*:p", False, True) ) ) and not look(sx[:m.start()], r"(?i)\b(?:j(?:e |[’'])|moi(?:,? qui| seul) |t(?:u |[’']|oi,? qui |oi seul ))")
def s5844s_1 (s, m):
    return suggVerb(m.group(0), ":3s")
def c5849s_1 (s, sx, m, dDA, sCountry):
    return not (m.group(0)[0:1].isupper() and look(sx[:m.start()], r"\w")) and not look(sx[:m.start()], r"(?i)\b(?:j(?:e |[’'])|moi(?:,? qui| seul) |t(?:u |[’']|oi,? qui |oi seul ))")
def s5849s_1 (s, m):
    return suggVerb(m.group(0), ":3s")
def c5852s_1 (s, sx, m, dDA, sCountry):
    return not (m.group(0)[0:1].isupper() and look(sx[:m.start()], r"\w")) and not look(sx[:m.start()], r"(?i)\b(?:j(?:e |[’'])|moi(?:,? qui| seul) |t(?:u |[’']|oi,? qui |oi seul ))")
def s5852s_1 (s, m):
    return suggVerb(m.group(0), ":3s")
def c5860s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":(?:1p|3[sp])") and not look(s[m.end():], "^ +(?:je|tu|ils?|elles?|on|[vn]ous)")
def s5860s_1 (s, m):
    return suggVerb(m.group(1), ":1p")
def c5863s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":1p") and not look(s[m.end():], "^ +(?:je|tu|ils?|elles?|on|[vn]ous)")
def s5863s_1 (s, m):
    return suggVerb(m.group(1), ":1p")
def c5866s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":1p") and not look(s[m.end():], "^ +(?:ils|elles)")
def s5866s_1 (s, m):
    return suggVerb(m.group(1), ":1p")
def c5875s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":(?:2p|3[sp])") and not look(s[m.end():], "^ +(?:je|ils?|elles?|on|[vn]ous)")
def s5875s_1 (s, m):
    return suggVerb(m.group(1), ":2p")
def c5878s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":2p") and not look(s[m.end():], "^ +(?:je|ils?|elles?|on|[vn]ous)")
def s5878s_1 (s, m):
    return suggVerb(m.group(1), ":2p")
def c5887s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(0), m.group(0)), ":V.*:1p", ":[EGMNAJ]") and not (m.group(0)[0:1].isupper() and look(s[:m.start()], r"\w")) and not look(s[:m.start()], r"\b(?:[nN]ous(?:-mêmes?|)|[eE]t moi),? ")
def s5887s_1 (s, m):
    return suggVerb(m.group(0), ":3p")
def c5891s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(0), m.group(0)), ":V.*:2p", ":[EGMNAJ]") and not (m.group(0)[0:1].isupper() and look(s[:m.start()], r"\w")) and not look(s[:m.start()], r"\b(?:[vV]ous(?:-mêmes?|)|[eE]t toi|[tT]oi et),? ")
def c5900s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:3p|P|Q|G)") and not (morph(dDA, (m.start(2), m.group(2)), ":[PQ]", False) and morph(dDA, prevword1(s, m.start()), ":V0.*:3p", False, False))
def s5900s_1 (s, m):
    return suggVerb(m.group(2), ":3p")
def c5903s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:3p|P|Q|G)")
def s5903s_1 (s, m):
    return suggVerb(m.group(2), ":3p")
def c5907s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:3p|P|Q|G)")
def s5907s_1 (s, m):
    return suggVerb(m.group(2), ":3p")
def c5911s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:3p|P|Q|G)") and not morph(dDA, prevword1(s, m.start()), ":[VR]", False, False)
def s5911s_1 (s, m):
    return suggVerb(m.group(2), ":3p")
def c5915s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":(?:3p|P|Q|G)") and not morph(dDA, prevword1(s, m.start()), ":R", False, False) and not (morph(dDA, (m.start(1), m.group(1)), ":[PQ]", False) and morph(dDA, prevword1(s, m.start()), ":V0.*:3p", False, False))
def s5915s_1 (s, m):
    return suggVerb(m.group(1), ":3p")
def c5918s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V", ":(?:3p|P|Q|G)") and not morph(dDA, prevword1(s, m.start()), ":R", False, False)
def s5918s_1 (s, m):
    return suggVerb(m.group(1), ":3p")
def c5933s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"(?i)\b(?:à|avec|sur|chez|par|dans|parmi|contre|ni|de|pour|sous) +$")
def c5940s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:3p|P|Q|mg)") and not morph(dDA, prevword1(s, m.start()), ":[VR]|>de ", False, False)
def s5940s_1 (s, m):
    return suggVerb(m.group(2), ":3p")
def c5944s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:3p|P|Q|G)") and not morph(dDA, prevword1(s, m.start()), ":[VR]", False, False)
def s5944s_1 (s, m):
    return suggVerb(m.group(2), ":3p")
def c5954s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:G|N|A|3p|P|Q)") and not morph(dDA, prevword1(s, m.start()), ":[VR]", False, False)
def s5954s_1 (s, m):
    return suggVerb(m.group(2), ":3p")
def c5961s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:[pi]", False) and morphex(dDA, (m.start(3), m.group(3)), ":V", ":(?:[13]p|P|Q|Y|G|A.*:e:[pi])") and morphex(dDA, prevword1(s, m.start()), ":C", ":[YP]", True) and not checkAgreement(m.group(2), m.group(3))
def s5961s_1 (s, m):
    return suggVerb(m.group(3), ":3p")
def c5964s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(2), m.group(2)), ":[NAQ].*:[pi]", False) and morphex(dDA, (m.start(3), m.group(3)), ":V", ":(?:[13]p|P|Y|G)") and morphex(dDA, prevword1(s, m.start()), ":C", ":[YP]", True)
def s5964s_1 (s, m):
    return suggVerb(m.group(3), ":3p")
def c5984s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:[pi]", False) and morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:[13]p|P|G|Q.*:p)") and morph(dDA, nextword1(s, m.end()), ":(?:R|D.*:p)|>au ", False, True)
def s5984s_1 (s, m):
    return suggVerb(m.group(2), ":3p")
def c5987s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":[NAQ].*:[pi]", False) and morphex(dDA, (m.start(2), m.group(2)), ":V", ":(?:[13]p|P|G)")
def s5987s_1 (s, m):
    return suggVerb(m.group(2), ":3p")
def c5993s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, prevword1(s, m.start()), ":C", ":[YP]", True) and isAmbiguousAndWrong(m.group(2), m.group(3), ":p", ":3p")
def s5993s_1 (s, m):
    return suggVerb(m.group(3), ":3p", suggPlur)
def c5997s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, prevword1(s, m.start()), ":C", ":[YP]", True) and isVeryAmbiguousAndWrong(m.group(1), m.group(2), ":p", ":3p", not prevword1(s, m.start()))
def s5997s_1 (s, m):
    return suggVerb(m.group(2), ":3p", suggPlur)
def c6001s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, prevword1(s, m.start()), ":C", ":[YP]", True) and isVeryAmbiguousAndWrong(m.group(1), m.group(2), ":m:p", ":3p", not prevword1(s, m.start()))
def s6001s_1 (s, m):
    return suggVerb(m.group(2), ":3p", suggMasPlur)
def c6005s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, prevword1(s, m.start()), ":C", ":[YP]", True) and isVeryAmbiguousAndWrong(m.group(1), m.group(2), ":f:p", ":3p", not prevword1(s, m.start()))
def s6005s_1 (s, m):
    return suggVerb(m.group(2), ":3p", suggFemPlur)
def c6038s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V0e", ":3s")
def s6038s_1 (s, m):
    return suggVerb(m.group(1), ":3s")
def c6042s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V0e.*:3s", ":3p")
def s6042s_1 (s, m):
    return m.group(1)[:-1]
def c6048s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V0e", ":3p")
def s6048s_1 (s, m):
    return suggVerb(m.group(1), ":3p")
def c6052s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":V0e.*:3p", ":3s")
def c6063s_1 (s, sx, m, dDA, sCountry):
    return not look(s[:m.start()], r"\b(?:et |ou |[dD][eu] |ni |[dD]e l’) *$") and morph(dDA, (m.start(1), m.group(1)), ":M", False) and morphex(dDA, (m.start(2), m.group(2)), ":[123][sp]", ":(?:G|3s|3p!|P|M|[AQ].*:[si])") and not morph(dDA, prevword1(s, m.start()), ":[VRD]", False, False) and not look(s[:m.start()], r"([A-ZÉÈ][\w-]+), +([A-ZÉÈ][\w-]+), +$")
def s6063s_1 (s, m):
    return suggVerb(m.group(2), ":3s")
def c6070s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":M", False) and morph(dDA, (m.start(2), m.group(2)), ":M", False) and morphex(dDA, (m.start(3), m.group(3)), ":[123][sp]", ":(?:G|3p|P|Q.*:[pi])") and not morph(dDA, prevword1(s, m.start()), ":R", False, False)
def s6070s_1 (s, m):
    return suggVerb(m.group(3), ":3p")
def c6088s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":(?:[12]s|3p)", ":(?:3s|G|W|3p!)") and not look(s[m.end():], "^ +et (?:l(?:es? |a |’|eurs? )|[mts](?:a|on|es) |ce(?:tte|ts|) |[nv]o(?:s|tre) |du )")
def s6088s_1 (s, m):
    return suggVerb(m.group(1), ":3s")
def c6093s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[123]s", ":(?:3p|G|W)")
def s6093s_1 (s, m):
    return suggVerb(m.group(1), ":3p")
def c6098s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[12][sp]", ":(?:G|W|3[sp]|Y|P|Q)")
def c6103s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[12][sp]", ":(?:G|W|3[sp])")
def c6117s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V.*:1s", ":[GNW]") and not look(s[:m.start()], r"(?i)\bje +>? *$")
def s6117s_1 (s, m):
    return m.group(1)[:-1]+"é-je"
def c6120s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":V.*:1s", ":[GNW]") and not look(s[:m.start()], r"(?i)\b(?:je|tu) +>? *$")
def c6123s_1 (s, sx, m, dDA, sCountry):
    return not look(s[m.end():], "^ +(?:en|y|ne|>)") and morphex(dDA, (m.start(1), m.group(1)), ":V.*:2s", ":[GNW]") and not look(s[:m.start()], r"(?i)\b(?:je|tu) +>? *$")
def c6126s_1 (s, sx, m, dDA, sCountry):
    return not look(s[m.end():], "^ +(?:en|y|ne|>)") and morphex(dDA, (m.start(1), m.group(1)), ":V.*:3s", ":[GNW]") and not look(s[:m.start()], r"(?i)\b(?:ce|il|elle|on) +>? *$")
def s6126s_1 (s, m):
    return m.group(0).replace(" ", "-")
def c6129s_1 (s, sx, m, dDA, sCountry):
    return not look(s[m.end():], "^ +(?:en|y|ne|aussi|>)") and morphex(dDA, (m.start(1), m.group(1)), ":V.*:3s", ":[GNW]") and not look(s[:m.start()], r"(?i)\b(?:ce|il|elle|on) +>? *$")
def c6132s_1 (s, sx, m, dDA, sCountry):
    return not look(s[m.end():], "^ +(?:en|y|ne|aussi|>)") and morphex(dDA, (m.start(1), m.group(1)), ":V.*:1p", ":[GNW]") and not morph(dDA, prevword1(s, m.start()), ":Os", False, False) and not morph(dDA, nextword1(s, m.end()), ":Y", False, False)
def c6136s_1 (s, sx, m, dDA, sCountry):
    return not look(s[m.end():], "^ +(?:en|y|ne|aussi|>)") and not m.group(1).endswith("euillez") and morphex(dDA, (m.start(1), m.group(1)), ":V.*:2pl", ":[GNW]") and not morph(dDA, prevword1(s, m.start()), ":Os", False, False) and not morph(dDA, nextword1(s, m.end()), ":Y", False, False)
def c6140s_1 (s, sx, m, dDA, sCountry):
    return not look(s[m.end():], "^ +(?:en|y|ne|aussi|>)") and morphex(dDA, (m.start(1), m.group(1)), ":V.*:3p", ":[GNW]") and not look(s[:m.start()], r"(?i)\b(?:ce|ils|elles) +>? *$")
def s6140s_1 (s, m):
    return m.group(0).replace(" ", "-")
def c6145s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":1[sśŝ]", False) and _oDict.isValid(m.group(1)) and not re.search("(?i)^vite$", m.group(1))
def s6145s_1 (s, m):
    return suggVerb(m.group(1), ":1ś")
def c6148s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":[ISK].*:2s", False) and _oDict.isValid(m.group(1)) and not re.search("(?i)^vite$", m.group(1))
def s6148s_1 (s, m):
    return suggVerb(m.group(1), ":2s")
def c6151s_1 (s, sx, m, dDA, sCountry):
    return m.group(1) != "t" and not morph(dDA, (m.start(1), m.group(1)), ":3s", False) and (not m.group(1).endswith("oilà") or m.group(2) != "il") and _oDict.isValid(m.group(1)) and not re.search("(?i)^vite$", m.group(1))
def s6151s_1 (s, m):
    return suggVerb(m.group(1), ":3s")
def c6154s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":3p", ":3s") and _oDict.isValid(m.group(1))
def c6157s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":(?:1p|E:2[sp])", False) and _oDict.isValid(m.group(1)) and not re.search("(?i)^(?:vite|chez)$", m.group(1))
def s6157s_1 (s, m):
    return suggVerb(m.group(1), ":1p")
def c6160s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":2p", False) and _oDict.isValid(m.group(1)) and not re.search("(?i)^(?:tes|vite)$", m.group(1)) and not _oDict.isValid(m.group(0))
def s6160s_1 (s, m):
    return suggVerb(m.group(1), ":2p")
def c6163s_1 (s, sx, m, dDA, sCountry):
    return m.group(1) != "t" and not morph(dDA, (m.start(1), m.group(1)), ":3p", False) and _oDict.isValid(m.group(1))
def s6163s_1 (s, m):
    return suggVerb(m.group(1), ":3p")
def c6167s_1 (s, sx, m, dDA, sCountry):
    return not morph(dDA, (m.start(1), m.group(1)), ":V", False) and not re.search("(?i)^vite$", m.group(1)) and _oDict.isValid(m.group(1)) and not ( m.group(0).endswith("il") and m.group(1).endswith("oilà") ) and not ( m.group(1) == "t" and re.search("(?:ils?|elles?|on)$", m.group(0)) )
def c6186s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">avoir ", False) and morph(dDA, (m.start(2), m.group(2)), ":V.......e_.*:Q", False)
def c6188s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">avoir ", False) and morph(dDA, (m.start(2), m.group(2)), ":V.......e_.*:Q", False)
def c6198s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":(?:Os|M)", False) and morphex(dDA, (m.start(2), m.group(2)), ":[SK]", ":(?:G|V0|I)") and not prevword1(s, m.start())
def c6201s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":[SK]", ":(?:G|V0|I)") and not prevword1(s, m.start())
def c6207s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":(?:Os|M)", False) and morphex(dDA, (m.start(2), m.group(2)), ":S", ":[IG]")
def s6207s_1 (s, m):
    return suggVerbMode(m.group(2), ":I", m.group(1))
def c6207s_2 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":(?:Os|M)", False) and morph(dDA, (m.start(2), m.group(2)), ":K", False)
def s6207s_2 (s, m):
    return suggVerbMode(m.group(2), ":If", m.group(1))
def c6218s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ">(?:afin|pour|quoi|permettre|falloir|vouloir|ordonner|exiger|désirer|douter|suffire) ", False) and morph(dDA, (m.start(2), m.group(2)), ":(?:Os|M)", False) and not morph(dDA, (m.start(3), m.group(3)), ":[GYS]", False) and not (morph(dDA, (m.start(1), m.group(1)), ">douter ", False) and morph(dDA, (m.start(3), m.group(3)), ":(?:If|K)", False))
def s6218s_1 (s, m):
    return suggVerbMode(m.group(3), ":S", m.group(2))
def c6233s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":(?:Os|M)", False) and not morph(dDA, (m.start(2), m.group(2)), ":[GYS]", False)
def s6233s_1 (s, m):
    return suggVerbMode(m.group(2), ":S", m.group(1))
def c6241s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(2), m.group(2)), ":S", ":[GIK]") and not re.search("^e(?:usse|û[mt]es|ût)", m.group(2))
def s6241s_1 (s, m):
    return suggVerbMode(m.group(2), ":I", m.group(1))
def c6244s_1 (s, sx, m, dDA, sCountry):
    return morphex(dDA, (m.start(1), m.group(1)), ":S", ":[GIK]") and m.group(1) != "eusse"
def s6244s_1 (s, m):
    return suggVerbMode(m.group(1), ":I", "je")
def c6254s_1 (s, sx, m, dDA, sCountry):
    return morph(dDA, (m.start(1), m.group(1)), ":(?:Os|M)", False) and (morph(dDA, (m.start(2), m.group(2)), ":V.*:S") or morph(dDA, (m.start(2), m.group(2)), ":V0e.*:S", False))
def s6254s_1 (s, m):
    return suggVerbMode(m.group(2), ":I", m.group(1))

