#!python3

import re
from ..echo import echo


dReplTable = {
    # surnumerary_spaces
    "start_of_paragraph":          [(u"^[  ]+", "")],
    "end_of_paragraph":            [(u"[  ]+$", "")],
    "between_words":               [(u"  |  ", u" "),  # espace + espace insécable -> espace
                                    (u"  +", u" "),    # espaces surnuméraires
                                    (u"  +", u" ")],   # espaces insécables surnuméraires
    "before_punctuation":          [(u" +(?=[.,…])", "")],
    "within_parenthesis":          [(u"\\([  ]+", u"("),
                                    (u"[  ]+\\)", u")")],
    "within_square_brackets":      [(u"\\[[  ]+", u"["),
                                    (u"[  ]+\\]", u"]")],
    "within_quotation_marks":      [(u"“[  ]+", u"“"),
                                    (u"[  ]”", u"”")],
    ## non-breaking spaces
    # espaces insécables
    "nbsp_before_punctuation":     [(u"(?<=[]\\w…)»}])([:;?!])", u" \\1"),
                                    (u"[  ]+([:;?!])", u" \\1")],
    "nbsp_within_quotation_marks": [(u"«(?=\\w)", u"« "),
                                    (u"«[  ]+", u"« "),
                                    (u"(?<=[\\w.!?])»", u" »"),
                                    (u"[  ]+»", u" »")],
    "nbsp_within_numbers":         [(u"(\\d)[  ](?=\\d)", u"\\1 ")],
    # espaces insécables fines
    "nnbsp_before_punctuation":    [(u"(?<=[]\\w…)»}])([;?!])", u" \\1"),
                                    (u"[  ]+([;?!])", u" \\1"),
                                    (u"(?<=[]\\w…)»}]):", u" :"),
                                    (u"[  ]+:", u" :")],
    "nnbsp_within_quotation_marks":[(u"«(?=\\w)", u"« "),
                                    (u"«[  ]+", u"« "),
                                    (u"(?<=[\\w.!?])»", u" »"),
                                    (u"[  ]+»", u" »")],
    "nnbsp_within_numbers":        [(u"(\\d)[  ](\\d)", u"\\1 \\2")],
    # common
    "nbsp_before_symbol":          [(u"(\\d) ?([%‰€$£¥˚Ω℃])", u"\\1 \\2")],
    "nbsp_before_units":           [(u"(?<=[0-9⁰¹²³⁴⁵⁶⁷⁸⁹]) ?([kcmµn]?(?:[slgJKΩ]|m[²³]?|Wh?|Hz|dB)|[%‰]|°C)\\b", " \\1")],
    "nbsp_repair":                 [(u"(?<=[[(])[   ]([!?:;])", u"\\1"),
                                    (u"(https?|ftp)[   ]:(?=//)", u"\\1:")],
    ## missing spaces
    "add_space_after_punctuation": [(u"([;?!…])(?=\\w)", u"\\1 "),
                                    (u"\\.(?=[A-ZÉÈÎ][a-zA-ZàâÂéÉèÈêÊîÎïÏôÔöÖûÛüÜ])", u". "),
                                    (u"\\.(?=À)", u". "),
                                    (u"(?i)([,:])(?=[a-zàâäéèêëîïôöûü])", u"\\1 ")],
    "add_space_around_hyphens":    [(u" ([-–—])(?=[a-zàâäéèêëîïôöûü\"«“'‘])", u" \\1 "),
                                    (u"(?<=[a-zàâäéèêëîïôöûü\"»”'’])([-–—]) ", u" \\1 ")],
    "add_space_repair":            [(u"DnT, ([wA])\\b", u"DnT,\\1")],
    ## erase
    "erase_non_breaking_hyphens":  [(u"­", "")],
    ## typographic signs
    "ts_apostrophe":          [ (u"(?i)\\b([ldnjmtscç])['´‘′`](?=\\w)", u"\\1’"),
                                (u"(?i)(qu|jusqu|lorsqu|puisqu|quoiqu|quelqu|presqu|entr|aujourd|prud)['´‘′`]", u"\\1’") ],
    "ts_ellipsis":            [ (u"\\.\\.\\.", u"…"),
                                (u"(?<=…)[.][.]", u"…"),
                                (u"…[.](?![.])", u"…") ],
    "ts_n_dash_middle":       [ (u" [-—] ", u" – "), 
                                (u" [-—],", u" –,") ],
    "ts_m_dash_middle":       [ (u" [-–] ", u" — "),
                                (u" [-–],", u" —,") ],
    "ts_n_dash_start":        [ (u"^[-—][  ]", u"– "),
                                (u"^– ", u"– "),
                                (u"^[-–—](?=\\w)", u"– ") ],
    "ts_m_dash_start":        [ (u"^[-–][  ]", u"— "),
                                (u"^— ", u"— "),
                                (u"^[-–—](?=\\w)", u"— ") ],
    "ts_quotation_marks":     [ (u'"(\\w+)"', u"“$1”"),
                                (u"''(\\w+)''", u"“$1”"),
                                (u"'(\\w+)'", u"“$1”"),
                                (u"^(?:\"|'')(?=\\w)", u"« "),
                                (u" (?:\"|'')(?=\\w)", u" « "),
                                (u"\\((?:\"|'')(?=\\w)", u"(« "),
                                (u"(?<=\\w)(?:\"|'')$", u" »"),
                                (u"(?<=\\w)(?:\"|'')(?=[] ,.:;?!…)])", u" »"),
                                (u'(?<=[.!?…])" ', u" » "),
                                (u'(?<=[.!?…])"$', u" »") ],
    "ts_spell_ligatures":     [ (u"coeur", u"cœur"), (u"Coeur", u"Cœur"),
                                (u"coel(?=[aeio])", u"cœl"), (u"Coel(?=[aeio])", u"Cœl"),
                                (u"choeur", u"chœur"), (u"Choeur", u"Chœur"),
                                (u"foet", u"fœt"), (u"Foet", u"Fœt"),
                                (u"oeil", u"œil"), (u"Oeil", u"Œil"),
                                (u"oeno", u"œno"), (u"Oeno", u"Œno"),
                                (u"oesoph", u"œsoph"), (u"Oesoph", u"Œsoph"),
                                (u"oestro", u"œstro"), (u"Oestro", u"Œstro"),
                                (u"oeuf", u"œuf"), (u"Oeuf", u"Œuf"),
                                (u"oeuvr", u"œuvr"), (u"Oeuvr", u"Œuvr"),
                                (u"moeur", u"mœur"), (u"Moeur", u"Mœur"),
                                (u"noeu", u"nœu"), (u"Noeu", u"Nœu"),
                                (u"soeur", u"sœur"), (u"Soeur", u"Sœur"),
                                (u"voeu", u"vœu"), (u"Voeu", u"Vœu"),
                                (u"aequo", u"æquo"), (u"Aequo", u"Æquo") ],
    "ts_ligature_ffi_on":       [(u"ffi", u"ﬃ")],
    "ts_ligature_ffl_on":       [(u"ffl", u"ﬄ")],
    "ts_ligature_fi_on":        [(u"fi", u"ﬁ")],
    "ts_ligature_fl_on":        [(u"fl", u"ﬂ")],
    "ts_ligature_ff_on":        [(u"ff", u"ﬀ")],
    "ts_ligature_ft_on":        [(u"ft", u"ﬅ")],
    "ts_ligature_st_on":        [(u"st", u"ﬆ")],
    "ts_ligature_fi_off":       [(u"ﬁ", u"fi")],
    "ts_ligature_fl_off":       [(u"ﬂ", u"fl")],
    "ts_ligature_ff_off":       [(u"ﬀ", u"ff")],
    "ts_ligature_ffi_off":      [(u"ﬃ", u"ffi")],
    "ts_ligature_ffl_off":      [(u"ﬄ", u"ffl")],
    "ts_ligature_ft_off":       [(u"ﬅ", u"ft")],
    "ts_ligature_st_off":       [(u"ﬆ", u"st")],
    "ts_units":               [ (u"\\bN\\.([ms])\\b", u"N·\\1"), # N·m et N·m-1, N·s
                                (u"\\bW\\.h\\b", u"W·h"),
                                (u"\\bPa\\.s\\b", u"Pa·s"),
                                (u"\\bA\\.h\\b", u"A·h"),
                                (u"\\bΩ\\.m\\b", u"Ω·m"),
                                (u"\\bS\\.m\\b", u"S·m"),
                                (u"\\bg\\.s(?=-1)\\b", u"g·s"),
                                (u"\\bm\\.s(?=-[12])\\b", u"m·s"),
                                (u"\\bg\\.m(?=2|-3)\\b", u"g·m"),
                                (u"\\bA\\.m(?=-1)\\b", u"A·m"),
                                (u"\\bJ\\.K(?=-1)\\b", u"J·K"),
                                (u"\\bW\\.m(?=-2)\\b", u"W·m"),
                                (u"\\bcd\\.m(?=-2)\\b", u"cd·m"),
                                (u"\\bC\\.kg(?=-1)\\b", u"C·kg"),
                                (u"\\bH\\.m(?=-1)\\b", u"H·m"),
                                (u"\\bJ\\.kg(?=-1)\\b", u"J·kg"),
                                (u"\\bJ\\.m(?=-3)\\b", u"J·m"),
                                (u"\\bm[2²]\\.s\\b", u"m²·s"),
                                (u"\\bm[3³]\\.s(?=-1)\\b", u"m³·s"),
                                #(u"\\bJ.kg-1.K-1\\b", u"J·kg-1·K-1"),
                                #(u"\\bW.m-1.K-1\\b", u"W·m-1·K-1"),
                                #(u"\\bW.m-2.K-1\\b", u"W·m-2·K-1"),
                                (u"\\b(Y|Z|E|P|T|G|M|k|h|da|d|c|m|µ|n|p|f|a|z|y)Ω\\b", u"\\1Ω") ],
    ## misc
    "ordinals_exponant":      [ (u"\\b([0-9]+)(?:i?[èe]me|è|e)\\b", u"\\1ᵉ"),
                                (u"\\b([XVICL]+)(?:i?[èe]me|è)\\b", u"\\1ᵉ"),
                                (u"(?<=\\b(au|l[ea]|du) [XVICL])e\\b", u"ᵉ"),
                                (u"(?<=\\b[XVI])e(?= siècle)", u"ᵉ"),
                                (u"(?<=\\b[1I])er\\b", u"ᵉʳ"),
                                (u"(?<=\\b[1I])re\\b", u"ʳᵉ") ],
    "ordinals_no_exponant":   [ (u"\\b([0-9]+)(?:i?[èe]me|è)\\b", u"\\1e"),
                                (u"\\b([XVICL]+)(?:i?[èe]me|è)\\b", u"\\1e"),
                                (u"(?<=\\b[1I])ᵉʳ\\b", u"er"),
                                (u"(?<=\\b[1I])ʳᵉ\\b", u"er")],
    "etc":                    [ (u"etc(…|[.][.][.]?)", u"etc."),
                                (u"(?<!,) etc[.]", u", etc.") ],
    ## missing hyphens
    "mh_interrogatives":      [ (u"[ -]t[’'](?=il\\b|elle|on\\b)", u"-t-"),
                                (u" t-(?=il|elle|on)", u"-t-"),
                                (u"[ -]t[’'-](?=ils|elles)", u"-"),
                                (u"(?<=[td])-t-(?=il|elle|on)", u"-") ],
    "mh_numbers": [ (u"dix (sept|huit|neuf)", u"dix-\\1"),
                    (u"quatre vingt", u"quatre-vingt"),
                    (u"(soixante|quatre-vingt) dix", u"\\1-dix"),
                    (u"(vingt|trente|quarante|cinquante|soixante(?:-dix|)|quatre-vingt(?:-dix|)) (deux|trois|quatre|cinq|six|sept|huit|neuf)\\b", u"\\1-\\2")],
    "mh_frequent_words":      [ (u"(?i)ce(lles?|lui|ux) (ci|là)\\b", u"ce\\1-\\2"),
                                (u"(?i)(?<!-)\\b(ci) (joint|desso?us|contre|devant|avant|après|incluse|g[îi]t|gisent)", u"\\1-\\2"),
                                (u"vis à vis", u"vis-à-vis"),
                                (u"Vis à vis", u"Vis-à-vis"),
                                (u"week end", u"week-end"),
                                (u"Week end", u"Week-end"),
                                (u"(?i)(plus|moins) value", u"\\1-value") ],
    ## missing apostrophes
    "ma_word":                  [(u"(?i)(qu|lorsqu|puisqu|quoiqu|presqu|jusqu|aujourd|entr|quelqu|prud) ", u"\\1’")],
    "ma_1letter_lowercase":     [(u"\\b([ldjnmtscç]) (?=[aàeéêiîoôuyhAÀEÉÊIÎOÔUYH])", u"\\1’")],
    "ma_1letter_uppercase":     [(u"\\b([LDJNMTSCÇ]) (?=[aàeéêiîoôuyhAÀEÉÊIÎOÔUYH])", u"\\1’")]
}


lOptRepl = [
    ("ts_units", True),
    ("start_of_paragraph", True),
    ("end_of_paragraph", True),
    ("between_words", True),
    ("before_punctuation", True),
    ("within_parenthesis", True),
    ("within_square_brackets", True),
    ("within_quotation_marks", True),
    ("nbsp_before_punctuation", True),
    ("nbsp_within_quotation_marks", True),
    ("nbsp_within_numbers", True),
    ("nnbsp_before_punctuation", False),
    ("nnbsp_within_quotation_marks", False),
    ("nnbsp_within_numbers", False),
    ("nbsp_before_symbol", True),
    ("nbsp_before_units", True),
    ("nbsp_repair", True),
    ("add_space_after_punctuation", True),
    ("add_space_around_hyphens", True),
    ("add_space_repair", True),
    ("erase_non_breaking_hyphens", False),
    ("ts_apostrophe", True),
    ("ts_ellipsis", True),
    ("ts_n_dash_middle", True),
    ("ts_m_dash_middle", False),
    ("ts_n_dash_start", False),
    ("ts_m_dash_start", True),
    ("ts_quotation_marks", True),
    ("ts_spell_ligatures", True),
    ("ts_ligature_ffi_on", False),
    ("ts_ligature_ffl_on", False),
    ("ts_ligature_fi_on", False),
    ("ts_ligature_fl_on", False),
    ("ts_ligature_ff_on", False),
    ("ts_ligature_ft_on", False),
    ("ts_ligature_st_on", False),
    ("ts_ligature_fi_off", False),
    ("ts_ligature_fl_off", False),
    ("ts_ligature_ff_off", False),
    ("ts_ligature_ffi_off", False),
    ("ts_ligature_ffl_off", False),
    ("ts_ligature_ft_off", False),
    ("ts_ligature_st_off", False),
    ("ordinals_exponant", False),
    ("ordinals_no_exponant", True),
    ("etc", True),
    ("mh_interrogatives", True),
    ("mh_numbers", True),
    ("mh_frequent_words", True),
    ("ma_word", True),
    ("ma_1letter_lowercase", False),
    ("ma_1letter_uppercase", False),
]


class TextFormatter:

    def __init__ (self):
        for sOpt, lTup in dReplTable.items():
            for i, t in enumerate(lTup):
                lTup[i] = (re.compile(t[0]), t[1])

    def formatText (self, sText, **args):
        for sOptName, bVal in lOptRepl:
            if bVal:
                for zRgx, sRep in dReplTable[sOptName]:
                    #echo("{}  -->  {}".format(zRgx.pattern, sRep))
                    sText = zRgx.sub(sRep, sText)
                    #echo(sText)
        return sText
