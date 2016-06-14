# -*- encoding: UTF-8 -*-

def getUI (sLang):
    if sLang in _dOptLabel:
        return _dOptLabel[sLang]
    return _dOptLabel["fr"]

lStructOpt = [('basic', [['typo', 'apos'], ['esp', 'nbsp'], ['tu', 'maj'], ['num', 'virg'], ['unit', 'nf'], ['liga', 'mapos'], ['chim', 'ocr']]), ('gramm', [['conf', 'sgpl'], ['gn']]), ('verbs', [['infi', 'gv'], ['imp', 'inte']]), ('style', [['bs', 'pleo'], ['redon1', 'redon2'], ['neg']]), ('misc', [['date', 'mc']]), ('debug', [['idrule']])]

dOpt = {'mapos': False, 'chim': False, 'idrule': False, 'num': True, 'maj': True, 'imp': True, 'infi': True, 'tu': True, 'conf': True, 'gv': True, 'redon1': False, 'liga': False, 'sgpl': True, 'ocr': False, 'nbsp': True, 'bs': True, 'unit': True, 'gn': True, 'virg': True, 'redon2': False, 'date': True, 'esp': True, 'pleo': True, 'inte': True, 'apos': True, 'neg': False, 'nf': True, 'mc': False, 'typo': True}

_dOptLabel = {'fr': {'mapos': ('Apostrophes manquantes après lettres isolées [!]', 'Apostrophes manquantes après les lettres l d s n c j m t ç. Cette option sert surtout à repérer les défauts de numérisation des textes et est déconseillée pour les textes scientifiques.'), 'maj': ('Majuscules', 'Vérifie l’utilisation des majuscules et des minuscules (par exemple, « la raison d’État », « les Européens »).'), 'idrule': ('Identifiant des règles de contrôle [!]', 'Affiche l’identifiant de la règle de contrôle dans les messages d’erreur.'), 'num': ('Nombres', 'Espaces insécables sur les grands nombres (> 10 000). Vérifie la présence de « O » au lieu de « 0 ».'), 'imp': ('Impératif', 'Vérifie notamment la deuxième personne du singulier (par exemple, les erreurs : « vas … », « prend … », « manges … »).'), 'chim': ('Chimie [!]', 'Typographie des composés chimiques (H₂O, CO₂, etc.).'), 'basic': ('Typographie', ''), 'gramm': ('Accords, pluriels et confusions', ''), 'ocr': ('Erreurs de numérisation (OCR) [!]', 'Erreurs de reconnaissance optique des caractères. Beaucoup de faux positifs.'), 'conf': ('Confusions, homonymes et faux-amis', 'Cherche des erreurs souvent dues à l’homonymie (par exemple, les confusions entre « faîte » et « faite »).'), 'misc': ('Divers', ''), 'infi': ('Infinitif', 'Confusion entre l’infinitif et d’autres formes.'), 'gv': ('Conjugaisons', 'Accord des verbes avec leur sujet.'), 'eif': ('Espaces insécables fines [!]', 'Pour placer des espaces insécables fines avant les ponctuations « ? ! ; »'), 'redon1': ('Répétitions dans le paragraphe [!]', 'Sont exclus les mots grammaticaux, ceux commençant par une majuscule, ainsi que “être” et “avoir”.'), 'liga': ('Signaler ligatures typographiques', 'Ligatures de fi, fl, ff, ffi, ffl, ft, st.'), 'sgpl': ('Pluriels (locutions)', 'Vérifie l’usage du pluriel ou du singulier dans certaines locutions.'), 'nbsp': ('Espaces insécables', 'Vérifie les espaces insécables avec les ponctuations « ! ? : ; » (à désactiver si vous utilisez une police Graphite)'), 'bs': ('Populaire', 'Souligne un langage courant considéré comme erroné, comme « malgré que ».'), 'unit': ('Espaces insécables avant unités de mesure', ''), 'gn': ('Accords de genre et de nombre', 'Accords des noms et des adjectifs.'), 'virg': ('Virgules', 'Virgules manquantes avant “mais”, “car” et “etc.”.'), 'redon2': ('Répétitions dans la phrase [!]', 'Sont exclus les mots grammaticaux, ainsi que “être” et “avoir”.'), 'verbs': ('Verbes', ''), 'esp': ('Espaces surnuméraires', 'Signale les espaces inutiles en début et en fin de ligne.'), 'pleo': ('Pléonasmes', 'Repère des redondances sémantiques, comme « au jour d’aujourd’hui », « monter en haut », etc.'), 'tu': ('Traits d’union', 'Cherche les traits d’union manquants ou inutiles.'), 'style': ('Style', ''), 'inte': ('Interrogatif', 'Vérifie les formes interrogatives et suggère de lier les pronoms personnels avec les verbes.'), 'apos': ('Apostrophe typographique', 'Correction des apostrophes droites. Automatisme possible dans le menu Outils > Options d’autocorrection > Options linguistiques > Guillemets simples > Remplacer (à cocher)'), 'debug': ('Débogage', ''), 'neg': ('Adverbe de négation [!]', 'Ne … pas, ne … jamais, etc.'), 'nf': ('Normes françaises', ''), 'mc': ('Mots composés [!]', 'Vérifie si les mots composés à trait d’union existent dans le dictionnaire (hormis ceux commençant par ex-, mi-, quasi-, semi-, non-, demi- et d’autres préfixes communs).'), 'typo': ('Signes typographiques', ''), 'date': ('Validité des dates', '')}, 'en': {'mapos': ('Missing apostrophes after single letters [!]', 'Missing apostrophes after l d s n c j m t ç. This option is mostly useful to detect defects of digitized texts and is not recommended for scientific texts.'), 'maj': ('Capitals', 'Checks the use of uppercase and lowercase letters (i.e. « la raison d’État », « les Européens »).'), 'idrule': ('Display control rule identifier [!]', 'Display control rule identifier in the context menu message'), 'num': ('Numbers', 'Large numbers and « O » instead of « 0 ».'), 'imp': ('Imperative mood', 'Checks particularly verbs at second person singular (i.e. errors such as: « vas … », « prend … », « manges … »).'), 'chim': ('Chemistry [!]', 'Typography for molecules (H₂O, CO₂, etc.)'), 'basic': ('Typography', ''), 'gramm': ('Agreement, plurals, confusions', ''), 'ocr': ('OCR errors [!]', 'Warning: many false positives.'), 'conf': ('Confusions, homonyms and false friends', 'Seeks errors often due to homonymy (i.e. confusions between « faîte » et « faite »).'), 'misc': ('Miscellaneous', ''), 'infi': ('Infinitive', 'Checks confusions between infinitive forms and other forms.'), 'gv': ('Conjugation', 'Agreement between verbs and their subject.'), 'eif': ('Narrow non breaking spaces [!]', 'To set narrow non breaking spaces before the characters “? ! ;”'), 'redon1': ('Duplicates in paragraph [!]', 'Are excluded grammatical words, words beginning by a capital letter, and also “être” and “avoir”.'), 'liga': ('Report typographical ligatures', 'Ligatures of fi, fl, ff, ffi, ffl, ft, st.'), 'sgpl': ('Plural (locutions)', 'Checks the use of plural and singular in locutions.'), 'nbsp': ('Non-breakable spaces', 'Checks the use of non-breakable spaces with the following punctuation marks: « ! ? : ; » (deactivate it if you use a Graphite font)'), 'bs': ('Popular style', 'Underlines misuse of language though informal and commonly used.'), 'unit': ('Non-breaking spaces before units of measurement', ''), 'gn': ('Agreement (gender and number)', 'Agreement between nouns and adjectives.'), 'virg': ('Commas', 'Missing commas before “mais”, “car” and “etc.”.'), 'redon2': ('Duplicates in sentence [!]', 'Are excluded grammatical words, and also “être” and “avoir”.'), 'verbs': ('Verbs', ''), 'esp': ('Unuseful spaces', 'Checks spaces at the beginning and the end of lines.'), 'pleo': ('Pleonasms', 'Semantic replications, like « au jour d’aujourd’hui », « monter en haut », etc.'), 'tu': ('Hyphens', 'Checks missing or useless hyphens.'), 'style': ('Style', ''), 'inte': ('Interrogative mood', 'Checks interrogative forms and suggests linking the personal pronouns with verbs.'), 'apos': ('Typographical apostrophe', 'Detects typewriter apostrophes. You may get automatically typographical apostrophes in Tools > Autocorrect options > Localized options > Single quote > Replace (checkbox).'), 'debug': ('Debug', ''), 'neg': ('Negation adverb [!]', 'Ne … pas, ne … jamais, etc.'), 'nf': ('French standards', ''), 'mc': ('Compound words [!]', 'Check if words with hyphen exist in the dictionary (except those beginning by ex-, mi-, quasi-, semi-, non-, demi- and other common prefixes)'), 'typo': ('Typographical glyphs', ''), 'date': ('Date validity', '')}}