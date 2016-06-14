#!python3

import sys
import os.path
import argparse
import json

import grammalecte.fr as gce
import grammalecte.fr.lexicographe as lxg
import grammalecte.fr.textformatter as tf
import grammalecte.text as txt
import grammalecte.tokenizer as tkz
from grammalecte.echo import echo


_EXAMPLE = "Quoi ? Racontes ! Racontes-moi ! Bon sangg, parles ! Oui. Il y a des menteur partout. " \
           "Je suit sidéré par la brutales arrogance de cette homme-là. Quelle salopard ! Un escrocs de la pire espece. " \
           "Quant sera t’il châtiés pour ses mensonge ?             Merde ! J’en aie marre."

_HELP = """
    /help               /h      show this text
    ?word1 [word2] ...          words analysis
    /+opt1 [opt2] ...           activate grammar checking options
    /-opt1 [opt2] ...           disactivate grammar checking options
    /lopt               /l      list options
    /quit               /q      exit
    [ENTER]                     exit
"""


def _getText (sInputText):
    sText = input(sInputText)
    if sText == "*":
        return _EXAMPLE
    if sys.platform == "win32":
        # Apparently, the console transforms «’» in «'».
        # So we reverse it to avoid many useless warnings.
        sText = sText.replace("'", "’")
    return sText


def generateText (iParagraph, sText, oTokenizer, oDict, bJSON, nWidth=100, bDebug=False, bEmptyIfNoErrors=False):
    aGrammErrs = gce.parse(sText, "FR", bDebug)
    aSpellErrs = []
    for dToken in oTokenizer.genTokens(sText):
        if dToken['sType'] == "WORD" and not oDict.isValidToken(dToken['sValue']):
            aSpellErrs.append(dToken)
    if bEmptyIfNoErrors and not aGrammErrs and not aSpellErrs:
        return ""
    if not bJSON:
        return txt.generateParagraph(sText, aGrammErrs, aSpellErrs, nWidth)
    return "  " + json.dumps({ "iParagraph": iParagraph, "lGrammarErrors": aGrammErrs, "lSpellingErrors": aSpellErrs }, ensure_ascii=False)


def readfile (spf):
    if os.path.isfile(spf):
        with open(spf, "r", encoding="utf-8") as hSrc:
            for sText in hSrc:
                yield sText
    else:
        print("# Error: file not found.")


def output (sText, hDst=None):
    if not hDst:
        echo(sText, end="")
    else:
        hDst.write(sText)


def main ():
    xParser = argparse.ArgumentParser()
    xParser.add_argument("-f", "--file", help="parse file (UTF-8 required!) [on Windows, -f is similar to -ff]", type=str)
    xParser.add_argument("-ff", "--file_to_file", help="parse file (UTF-8 required!) and create a result file (*.res.txt)", type=str)
    xParser.add_argument("-j", "--json", help="generate list of errors in JSON", action="store_true")
    xParser.add_argument("-w", "--width", help="width in characters (40 < width < 200; default: 100)", type=int, choices=range(40,201,10), default=100)
    xParser.add_argument("-tf", "--textformatter", help="auto-format text according to typographical rules", action="store_true")
    xParser.add_argument("-tfo", "--textformatteronly", help="auto-format text and disable grammar checking (only with option 'file' or 'file_to_file')", action="store_true")
    xArgs = xParser.parse_args()

    gce.load()
    gce.setOptions({"html": True})
    echo("Grammalecte v{}".format(gce.version))
    oDict = gce.getDictionary()
    oTokenizer = tkz.Tokenizer("fr")
    oLexGraphe = lxg.Lexicographe(oDict)
    if xArgs.textformatter or xArgs.textformatteronly:
        oTF = tf.TextFormatter()

    sFile = xArgs.file or xArgs.file_to_file
    if sFile:
        # file processing
        hDst = open(sFile[:sFile.rfind(".")]+".res.txt", "w", encoding="utf-8")  if xArgs.file_to_file or sys.platform == "win32"  else None
        bComma = False
        if xArgs.json:
            output('{ "grammalecte": "'+gce.version+'", "lang": "'+gce.lang+'", "data" : [\n', hDst)
        for i, sText in enumerate(readfile(sFile), 1):
            if xArgs.textformatter or xArgs.textformatteronly:
                sText = oTF.formatText(sText)
            if xArgs.textformatteronly:
                output(sText, hDst)
            else:
                sText = generateText(i, sText, oTokenizer, oDict, xArgs.json, nWidth=xArgs.width)
                if sText:
                    if xArgs.json and bComma:
                        output(",\n", hDst)
                    output(sText, hDst)
                    bComma = True
            if hDst:
                echo("§ %d\r" % i, end="", flush=True)
        if xArgs.json:
            output("\n]}\n", hDst)
    else:
        # pseudo-console
        sInputText = "\n~==========~ Enter your text [/h /q] ~==========~\n"
        sText = _getText(sInputText)
        bDebug = False
        while True:
            if sText.startswith("?"):
                for sWord in sText[1:].strip().split():
                    if sWord:
                        echo("* {}".format(sWord))
                        for sMorph in oDict.getMorph(sWord):
                            echo("  {:<32} {}".format(sMorph, oLexGraphe.formatTags(sMorph)))
            elif sText.startswith("/+"):
                gce.setOptions({ opt:True  for opt in sText[2:].strip().split()  if opt in gce.getOptions() })
            elif sText.startswith("/-"):
                gce.setOptions({ opt:False  for opt in sText[2:].strip().split()  if opt in gce.getOptions() })
            elif sText == "/debug" or sText == "/d":
                bDebug = not(bDebug)
                echo("debug mode on"  if bDebug  else "debug mode off")
            elif sText == "/help" or sText == "/h":
                echo(_HELP)
            elif sText == "/lopt" or sText == "/l":
                echo("\n".join( [ k+":\t"+str(v)  for k, v  in sorted(gce.getOptions().items()) ] ))
            elif sText == "/quit" or sText == "/q":
                break
            elif sText.startswith("/rl"):
                # reload (todo)
                pass
            else:
                for sParagraph in txt.getParagraph(sText):
                    if xArgs.textformatter:
                        sText = oTF.formatText(sText)
                    sRes = generateText(0, sText, oTokenizer, oDict, xArgs.json, nWidth=xArgs.width, bDebug=bDebug, bEmptyIfNoErrors=True)
                    if sRes:
                        echo("\n" + sRes)
                    else:
                        echo("\nNo error found.")
            sText = _getText(sInputText)


if __name__ == '__main__':
    main()
