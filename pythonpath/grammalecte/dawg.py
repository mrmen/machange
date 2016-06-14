#!python3

# FSA DICTIONARY BUILDER
#
# by Olivier R.
# License: MPL 2
#
# This tool encodes lexicon into an indexable binary dictionary 
# Input files MUST be encoded in UTF-8.


import sys
import os
import collections

from . import str_transform as st
from .progressbar import ProgressBar


class DAWG:
    """DIRECT ACYCLIC WORD GRAPH"""
    # This code is inspired from Steve Hanov’s DAWG, 2011. (http://stevehanov.ca/blog/index.php?id=115)
    # We store suffix/affix codes and tags within the graph after the “real” word.
    # A word is a list of numbers [ c1, c2, c3 . . . cN, iAffix, iTags]
    # Each arc is an index in self.lArcVal, where are stored characters, suffix/affix codes for stemming and tags.
    # Important: As usual, the last node (after ‘iTags’) is tagged final, AND the node after ‘cN’ is ALSO tagged final.

    def __init__ (self, spfSrc, sLangName, cStemming):
        print("===== Direct Acyclic Word Graph - Minimal Acyclic Finite State Automaton =====")
        cStemming = cStemming.upper()
        if cStemming == "A":
            funcStemmingGen = st.defineAffixCode
        elif cStemming == "S":
            funcStemmingGen = st.defineSuffixCode
        elif cStemming == "N":
            funcStemmingGen = st.noStemming
        else:
            print("# Error code: {}".format(cStemming))
            exit()

        lEntry = []
        lChar = ['']; dChar = {}; nChar = 1; dCharOccur = {}
        lAff  = [];   dAff  = {}; nAff  = 0; dAffOccur = {}
        lTag  = [];   dTag  = {}; nTag  = 0; dTagOccur = {}
        nErr = 0
        
        # read lexicon
        with open(spfSrc, 'r', encoding='utf-8') as hSrc:
            print(" > Reading lexicon: " + spfSrc + " ...")
            for line in hSrc:
                line = line.strip()
                if not (line.startswith('#') or line == ''):
                    try:
                        flex, stem, tag = line.split("\t")
                    except:
                        nErr += 1
                        continue
                    # chars
                    for c in flex:
                        if c not in dChar:
                            dChar[c] = nChar
                            lChar.append(c)
                            nChar += 1
                        dCharOccur[c] = dCharOccur.get(c, 0) + 1
                    # affixes to find stem from flexion
                    aff = funcStemmingGen(flex, stem)
                    if aff not in dAff:
                        dAff[aff] = nAff
                        lAff.append(aff)
                        nAff += 1
                    dAffOccur[aff] = dCharOccur.get(aff, 0) + 1
                    # tags
                    if tag not in dTag:
                        dTag[tag] = nTag
                        lTag.append(tag)
                        nTag += 1
                    dTagOccur[tag] = dTagOccur.get(tag, 0) + 1
                    lEntry.append((flex, dAff[aff], dTag[tag]))
            hSrc.close()
        if nErr:
            print(" # Lines ignored: {:>10}".format(nErr))
        if not(lEntry):
            print(" # Empty lexicon")
            exit()
        
        # Preparing DAWG
        print(" > Preparing list of words")
        lVal = lChar + lAff + lTag
        lWord = [ [dChar[c] for c in sFlex] + [iAff+nChar] + [iTag+nChar+nAff]  for sFlex, iAff, iTag in lEntry ]
        lEntry = None
        
        # Dictionary of arc values occurrency, to sort arcs of each node
        dValOccur = dict( [ (dChar[c], dCharOccur[c])  for c in dChar ] \
                        + [ (dAff[aff]+nChar, dAffOccur[aff]) for aff in dAff ] \
                        + [ (dTag[tag]+nChar+nAff, dTagOccur[tag]) for tag in dTag ] )
        #with open(spfSrc[:-8]+".valuesfreq.txt", 'w', encoding='utf-8') as hFreqDst:  # DEBUG
        #    for iKey, nOcc in sorted(dValOccur.items(), key=lambda t: t[1], reverse=True):
        #        hFreqDst.write("{}: {}\n".format(lVal[iKey], nOcc))
        #    hFreqDst.close()
        
        self.sFile = spfSrc
        self.sLang = sLangName
        self.nEntry = len(lWord)
        self.previousWord = []
        DawgNode.resetNextId()
        self.root = DawgNode()
        self.uncheckedNodes = []  # list of nodes that have not been checked for duplication.
        self.minimizedNodes = {}  # list of unique nodes that have been checked for duplication.
        self.sortedNodes = []     # version 2 and 3
        self.nNode = 0
        self.nArc = 0
        self.dChar = dChar
        self.nChar = len(dChar)
        self.nAff = nAff
        self.lArcVal = lVal
        self.nArcVal = len(lVal)
        self.nTag = self.nArcVal - self.nChar - nAff
        self.cStemming = cStemming.upper()
        if cStemming == "A":
            self.funcStemming = st.getStemFromAffixCode
        elif cStemming == "S":    
            self.funcStemming = st.getStemFromSuffixCode
        else:
            self.funcStemming = st.noStemming
        
        # build
        lWord.sort()
        oProgBar = ProgressBar(0, len(lWord))
        for word in lWord:
            self.insert(word)
            oProgBar.increment(1)
        oProgBar.done()
        self.finish()
        self.countNodes()
        self.countArcs()
        self.sortNodes()
        self.sortNodeArcs(dValOccur)
        self.displayInfo()

    # BUILD DAWG
    def insert (self, word):
        if word < self.previousWord:
            sys.exit("# Error: Words must be inserted in alphabetical order.")
        
        # find common prefix between word and previous word
        commonPrefix = 0
        for i in range(min(len(word), len(self.previousWord))):
            if word[i] != self.previousWord[i]:
                break
            commonPrefix += 1

        # Check the uncheckedNodes for redundant nodes, proceeding from last
        # one down to the common prefix size. Then truncate the list at that point.
        self._minimize(commonPrefix)

        # add the suffix, starting from the correct node mid-way through the graph
        if len(self.uncheckedNodes) == 0:
            oNode = self.root
        else:
            oNode = self.uncheckedNodes[-1][2]

        iChar = commonPrefix
        for c in word[commonPrefix:]:
            oNextNode = DawgNode()
            oNode.arcs[c] = oNextNode
            self.uncheckedNodes.append((oNode, c, oNextNode))
            if iChar == (len(word) - 2): 
                oNode.final = True
            iChar += 1
            oNode = oNextNode
        oNode.final = True
        self.previousWord = word

    def finish (self):
        "minimize unchecked nodes"
        self._minimize(0)

    def _minimize (self, downTo):
        # proceed from the leaf up to a certain point
        for i in range( len(self.uncheckedNodes)-1, downTo-1, -1 ):
            (parent, char, child) = self.uncheckedNodes[i]
            if child in self.minimizedNodes:
                # replace the child with the previously encountered one
                parent.arcs[char] = self.minimizedNodes[child]
            else:
                # add the state to the minimized nodes.
                self.minimizedNodes[child] = child
            self.uncheckedNodes.pop()

    def countNodes (self):
        self.nNode = len(self.minimizedNodes)

    def countArcs (self):
        self.nArc = 0
        for node in self.minimizedNodes:
            self.nArc += len(node.arcs)
    
    def sortNodeArcs (self, dValOccur):
        print(" > Sort node arcs")
        self.root.sortArcs(dValOccur)
        for oNode in self.minimizedNodes:
            oNode.sortArcs(dValOccur)
    
    def sortNodes (self):
        print(" > Sort nodes")
        for oNode in self.root.arcs.values():
            self._parseNodes(oNode)
    
    def _parseNodes (self, oNode):
        # Warning: recursive method
        if oNode.pos > 0:
            return
        oNode.setPos()
        self.sortedNodes.append(oNode)
        for oNextNode in oNode.arcs.values():
             self._parseNodes(oNextNode)
        
    def lookup (self, sWord):
        oNode = self.root
        for c in sWord:
            if self.dChar.get(c, '') not in oNode.arcs:
                return False
            oNode = oNode.arcs[self.dChar[c]]
        return oNode.final

    def morph (self, sWord):
        oNode = self.root
        for c in sWord:
            if self.dChar.get(c, '') not in oNode.arcs:
                return ''
            oNode = oNode.arcs[self.dChar[c]]
        if oNode.final:
            s = "* "
            for arc in oNode.arcs:
                if arc >= self.nChar:
                    s += " [" + self.funcStemming(sWord, self.lArcVal[arc])
                    oNode2 = oNode.arcs[arc]
                    for arc2 in oNode2.arcs:
                        s += " / " + self.lArcVal[arc2]
                    s += "]"
            return s
        return ''

    def displayInfo (self):
        print(" * {:<12} {:>16,}".format("Entries:", self.nEntry))
        print(" * {:<12} {:>16,}".format("Characters:", self.nChar))
        print(" * {:<12} {:>16,}".format("Affixes:", self.nAff))
        print(" * {:<12} {:>16,}".format("Tags:", self.nTag))
        print(" * {:<12} {:>16,}".format("Arc values:", self.nArcVal))
        print(" * {:<12} {:>16,}".format("Nodes:", self.nNode))
        print(" * {:<12} {:>16,}".format("Arcs:", self.nArc))
        print(" * {:<12} {:>16}".format("Stemming:", self.cStemming + "FX"))

    def getArcStats (self):
        d = {}
        for oNode in self.minimizedNodes:
            n = len(oNode.arcs)
            d[n] = d.get(n, 0) + 1
        s = " * Nodes:\n"
        for n in d:
            s = s + " {:>9} nodes have {:>3} arcs\n".format(d[n], n)
        return s

    def writeInfo (self, sPathFile):
        print(" > Write informations")
        with open(sPathFile, 'w', encoding='utf-8') as hDst:
            hDst.write(self.getArcStats())
            hDst.write("\n * Values:\n")
            for i, s in enumerate(self.lArcVal):
                hDst.write(" {:>6}. {}\n".format(i, s))
            hDst.close()

    # BINARY CONVERSION
    def createBinary (self, sPathFile, nMethod, bDebug=False):
        print(" > Write DAWG as an indexable binary dictionary [method: %d]" % nMethod)
        if nMethod == 1:
            self.nBytesArc = ( ( (self.nArcVal).bit_length() + 2 ) // 8 ) + 1   # We add 2 bits. See DawgNode.convToBytes1()
            self._calcNumBytesNodeAddress()
            self._calcNodesAddress1()
        elif nMethod == 2:
            self.nBytesArc = ( ( (self.nArcVal).bit_length() + 3 ) // 8 ) + 1   # We add 3 bits. See DawgNode.convToBytes2()
            self._calcNumBytesNodeAddress()
            self._calcNodesAddress2()
        elif nMethod == 3:
            self.nBytesArc = ( ( (self.nArcVal).bit_length() + 3 ) // 8 ) + 1   # We add 3 bits. See DawgNode.convToBytes3()
            self.nBytesOffset = 1
            self.nMaxOffset = (2 ** (self.nBytesOffset * 8)) - 1
            self._calcNumBytesNodeAddress()
            self._calcNodesAddress3()
        else:
            print(" # Error: unknown compression method")
        print("   Arc values (chars, affixes and tags): {}  ->  {} bytes".format( self.nArcVal, len("\t".join(self.lArcVal).encode("utf-8")) ))
        print("   Arc size: {} bytes, Address size: {} bytes   ->   {} * {} = {} bytes".format( self.nBytesArc, self.nBytesNodeAddress, \
                                                                                                self.nBytesArc+self.nBytesNodeAddress, self.nArc, \
                                                                                                (self.nBytesArc+self.nBytesNodeAddress)*self.nArc ))
        self._writeBinary(sPathFile, nMethod)
        if bDebug:
            self._writeNodes(sPathFile, nMethod)

    def _calcNumBytesNodeAddress (self):
        "how many bytes needed to store all nodes/arcs in the binary dictionary"
        self.nBytesNodeAddress = 1
        while ((self.nBytesArc + self.nBytesNodeAddress) * self.nArc) > (2 ** (self.nBytesNodeAddress * 8)):
            self.nBytesNodeAddress += 1

    def _calcNodesAddress1 (self):
        nBytesNode = self.nBytesArc + self.nBytesNodeAddress
        iAddr = len(self.root.arcs) * nBytesNode
        for oNode in self.minimizedNodes:
            oNode.addr = iAddr
            iAddr += max(len(oNode.arcs), 1) * nBytesNode

    def _calcNodesAddress2 (self):
        nBytesNode = self.nBytesArc + self.nBytesNodeAddress
        iAddr = len(self.root.arcs) * nBytesNode
        for oNode in self.sortedNodes:
            oNode.addr = iAddr
            iAddr += max(len(oNode.arcs), 1) * nBytesNode
            for oNextNode in oNode.arcs.values():
                if (oNode.pos + 1) == oNextNode.pos:
                    iAddr -= self.nBytesNodeAddress
                    #break

    def _calcNodesAddress3 (self):
        nBytesNode = self.nBytesArc + self.nBytesNodeAddress
        # theorical nodes size if only addresses and no offset
        self.root.size = len(self.root.arcs) * nBytesNode
        for oNode in self.sortedNodes:
            oNode.size = max(len(oNode.arcs), 1) * nBytesNode
        # rewind and calculate dropdown from the end, several times
        nDiff = self.nBytesNodeAddress - self.nBytesOffset
        bEnd = False
        while not bEnd:
            bEnd = True
            # recalculate addresses
            iAddr = self.root.size
            for oNode in self.sortedNodes:
                oNode.addr = iAddr
                iAddr += oNode.size
            # rewind and calculate dropdown from the end, several times
            for i in range(self.nNode-1, -1, -1):
                nSize = max(len(self.sortedNodes[i].arcs), 1) * nBytesNode
                for oNextNode in self.sortedNodes[i].arcs.values():
                    if 1 < (oNextNode.addr - self.sortedNodes[i].addr) < self.nMaxOffset:
                        nSize -= nDiff
                if self.sortedNodes[i].size != nSize:
                    self.sortedNodes[i].size = nSize
                    bEnd = False

    def _writeBinary (self, sPathFile, nMethod):
        """
        Format of the binary indexable dictionary:
        Each section is separated with 4 bytes of \0
        
        - Section Header:
            /pyfsa/[version]
                * version is an ASCII string
        
        - Section Informations:
            /[tag_lang]
            /[number of chars]
            /[number of bytes for each arc]
            /[number of bytes for each address node]
            /[number of entries]
            /[number of nodes]
            /[number of arcs]
            /[number of affixes]
                * each field is a ASCII string
            /[stemming code]
                * "S" means stems are generated by /suffix_code/, "A" means they are generated by /affix_code/
                  See defineSuffixCode() and defineAffixCode() for details.
                  "N" means no stemming
        
        - Section Values:
                * a list of strings encoded in binary from utf-8, each value separated with a tabulation
        
        - Section Word Graph (nodes / arcs)
                * A list of nodes which are a list of arcs with an address of the next node.
                  See DawgNode.convToBytes() for details.
        """
        if not sPathFile.endswith(".bdic"):
            sPathFile += "."+str(nMethod)+".bdic"
        with open(sPathFile, 'wb') as hDst:
            # header
            hDst.write("/pyfsa/{}/".format(nMethod).encode("utf-8"))
            hDst.write(b"\0\0\0\0")
            # infos
            hDst.write("{}/{}/{}/{}/{}/{}/{}/{}/{}".format(self.sLang, self.nChar, self.nBytesArc, self.nBytesNodeAddress, \
                                                           self.nEntry, self.nNode, self.nArc, self.nAff, self.cStemming).encode("utf-8"))
            hDst.write(b"\0\0\0\0")
            # lArcVal
            hDst.write("\t".join(self.lArcVal).encode("utf-8"))
            hDst.write(b"\0\0\0\0")
            # DAWG: nodes / arcs
            if nMethod == 1:
                hDst.write(self.root.convToBytes1(self.nBytesArc, self.nBytesNodeAddress))
                for oNode in self.minimizedNodes:
                    hDst.write(oNode.convToBytes1(self.nBytesArc, self.nBytesNodeAddress))
            elif nMethod == 2:
                hDst.write(self.root.convToBytes2(self.nBytesArc, self.nBytesNodeAddress))
                for oNode in self.sortedNodes:
                    hDst.write(oNode.convToBytes2(self.nBytesArc, self.nBytesNodeAddress))
            elif nMethod == 3:
                hDst.write(self.root.convToBytes3(self.nBytesArc, self.nBytesNodeAddress, self.nBytesOffset))
                for oNode in self.sortedNodes:
                    hDst.write(oNode.convToBytes3(self.nBytesArc, self.nBytesNodeAddress, self.nBytesOffset))
            hDst.close()

    def _writeNodes (self, sPathFile, nMethod):
        "for debugging only"
        print(" > Write nodes")
        with open(sPathFile+".nodes."+str(nMethod)+".txt", 'w', encoding='utf-8') as hDst:
            if nMethod == 1:
                hDst.write(self.root.getTxtRepr1(self.nBytesArc, self.nBytesNodeAddress, self.lArcVal)+"\n")
                #hDst.write( ''.join( [ "%02X " %  z  for z in self.root.convToBytes1(self.nBytesArc, self.nBytesNodeAddress) ] ).strip() )
                for oNode in self.minimizedNodes:
                    hDst.write(oNode.getTxtRepr1(self.nBytesArc, self.nBytesNodeAddress, self.lArcVal)+"\n")
            if nMethod == 2:
                hDst.write(self.root.getTxtRepr2(self.nBytesArc, self.nBytesNodeAddress, self.lArcVal)+"\n")
                for oNode in self.sortedNodes:
                    hDst.write(oNode.getTxtRepr2(self.nBytesArc, self.nBytesNodeAddress, self.lArcVal)+"\n")
            if nMethod == 3:
                hDst.write(self.root.getTxtRepr3(self.nBytesArc, self.nBytesNodeAddress, self.nBytesOffset, self.lArcVal)+"\n")
                #hDst.write( ''.join( [ "%02X " %  z  for z in self.root.convToBytes3(self.nBytesArc, self.nBytesNodeAddress, self.nBytesOffset) ] ).strip() )
                for oNode in self.sortedNodes:
                    hDst.write(oNode.getTxtRepr3(self.nBytesArc, self.nBytesNodeAddress, self.nBytesOffset, self.lArcVal)+"\n")
            hDst.close()
    
    def writeResults (self, sPathFile):
        bFileExits = os.path.isfile("_lexicons.res.txt")
        with open("_lexicons.res.txt", "a", encoding='utf-8') as hDst:
            sFormat1 = "{:<12} {:>12} {:>5} {:>8} {:>8} {:>6} {:>8} {:>9} {:>9} {:>15} {:>12} {:>12}\n"
            sFormat2 = "{:<12} {:>12,} {:>5,} {:>8,} {:>8} {:>6,} {:>8,} {:>9,} {:>9,} {:>15,} {:>12,} {:>12,}\n"
            if not bFileExits:
                hDst.write(sFormat1.format("Lexicon", "Entries", "Chars", "Affixes", "Stemming", "Tags", "Values", "Nodes", "Arcs", "Lexicon (Kb)", "Dict (Kb)", "LT Dict (Kb)"))
            hDst.write(sFormat2.format(self.sLang, self.nEntry, self.nChar, self.nAff, self.cStemming + "FX", self.nTag, self.nArcVal, \
                                       self.nNode, self.nArc, os.path.getsize(self.sFile), os.path.getsize(sPathFile), \
                                       os.path.getsize("cfsa/dict/{}.dict".format(self.sLang)) if os.path.isfile("cfsa/dict/{}.dict".format(self.sLang)) else 0))
            hDst.close()



class DawgNode:
    NextId = 0
    NextPos = 1 # (version 2)
    
    def __init__ (self):
        self.i = DawgNode.NextId
        DawgNode.NextId += 1
        self.final = False
        self.arcs = {}          # key: arc value; value: a node
        self.addr = 0           # address in the binary dictionary
        self.pos = 0            # position in the binary dictionary (version 2)
        self.size = 0           # size of node in bytes (version 3)

    @classmethod
    def resetNextId (cls):
        cls.NextId = 0

    def setPos (self): # version 2
        self.pos = DawgNode.NextPos
        DawgNode.NextPos += 1

    def __str__ (self):
        # Caution! this function is used for hashing and comparison!
        l = []
        if self.final: 
            l.append("1")
        else:
            l.append("0")
        for (key, node) in self.arcs.items():
            l.append(str(key))
            l.append(str(node.i))
        return "_".join(l)

    def __hash__ (self):
        # Used as a key in a python dictionary.
        return self.__str__().__hash__()

    def __eq__ (self, other):
        # Used as a key in a python dictionary.
        # Nodes are equivalent if they have identical arcs, and each identical arc leads to identical states.
        return self.__str__() == other.__str__()

    def sortArcs (self, dValOccur):
        self.arcs = collections.OrderedDict(sorted(self.arcs.items(), key=lambda t: dValOccur[t[0]], reverse=True))

    # VERSION 1 =====================================================================================================
    def convToBytes1 (self, nBytesArc, nBytesNodeAddress):
        """
        Node scheme:
        - Arc length is defined by nBytesArc
        - Address length is defined by nBytesNodeAddress
                                       
        |                Arc                |                         Address of next node                          |
        |                                   |                                                                       |
         /---------------\ /---------------\ /---------------\ /---------------\ /---------------\ /---------------\
         | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
         \---------------/ \---------------/ \---------------/ \---------------/ \---------------/ \---------------/
         [...]
         /---------------\ /---------------\ /---------------\ /---------------\ /---------------\ /---------------\
         | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
         \---------------/ \---------------/ \---------------/ \---------------/ \---------------/ \---------------/
          ^ ^
          | |
          | |
          |  \___ if 1, last arc of this node
           \_____ if 1, this node is final (only on the first arc)
        """
        nArc = len(self.arcs)
        nFinalNodeMask = 1 << ((nBytesArc*8)-1)
        nFinalArcMask = 1 << ((nBytesArc*8)-2)
        if len(self.arcs) == 0:
            val = nFinalNodeMask | nFinalArcMask
            by = val.to_bytes(nBytesArc, byteorder='big')
            by += (0).to_bytes(nBytesNodeAddress, byteorder='big')
            return by
        by = b""
        for i, arc in enumerate(self.arcs, 1):
            val = arc
            if i == 1 and self.final:
                val = val | nFinalNodeMask
            if i == nArc:
                val = val | nFinalArcMask
            by += val.to_bytes(nBytesArc, byteorder='big')
            by += self.arcs[arc].addr.to_bytes(nBytesNodeAddress, byteorder='big')
        return by
        
    def getTxtRepr1 (self, nBytesArc, nBytesNodeAddress, lVal):
        nArc = len(self.arcs)
        nFinalNodeMask = 1 << ((nBytesArc*8)-1)
        nFinalArcMask = 1 << ((nBytesArc*8)-2)
        s = "i{:_>10} -- #{:_>10}\n".format(self.i, self.addr)
        if len(self.arcs) == 0:
            s += "  {:<20}  {:0>16}  i{:_>10}   #{:_>10}\n".format("", bin(nFinalNodeMask | nFinalArcMask)[2:], "0", "0")
            return s
        for i, arc in enumerate(self.arcs, 1):
            val = arc
            if i == 1 and self.final:
                val = val | nFinalNodeMask
            if i == nArc:
                val = val | nFinalArcMask
            s += "  {:<20}  {:0>16}  i{:_>10}   #{:_>10}\n".format(lVal[arc], bin(val)[2:], self.arcs[arc].i, self.arcs[arc].addr)
        return s

    # VERSION 2 =====================================================================================================
    def convToBytes2 (self, nBytesArc, nBytesNodeAddress):
        """
        Node scheme:
        - Arc length is defined by nBytesArc
        - Address length is defined by nBytesNodeAddress
                                       
        |                Arc                |                         Address of next node                          |
        |                                   |                                                                       |
         /---------------\ /---------------\ /---------------\ /---------------\ /---------------\ /---------------\
         | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
         \---------------/ \---------------/ \---------------/ \---------------/ \---------------/ \---------------/
         [...]
         /---------------\ /---------------\ /---------------\ /---------------\ /---------------\ /---------------\
         | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
         \---------------/ \---------------/ \---------------/ \---------------/ \---------------/ \---------------/
          ^ ^ ^
          | | |
          | |  \_ if 1, caution, no address: next node is the following node
          |  \___ if 1, last arc of this node
           \_____ if 1, this node is final (only on the first arc)
        """
        nArc = len(self.arcs)
        nFinalNodeMask = 1 << ((nBytesArc*8)-1)
        nFinalArcMask = 1 << ((nBytesArc*8)-2)
        nNextNodeMask = 1 << ((nBytesArc*8)-3)
        if len(self.arcs) == 0:
            val = nFinalNodeMask | nFinalArcMask
            by = val.to_bytes(nBytesArc, byteorder='big')
            by += (0).to_bytes(nBytesNodeAddress, byteorder='big')
            return by
        by = b""
        for i, arc in enumerate(self.arcs, 1):
            val = arc
            if i == 1 and self.final:
                val = val | nFinalNodeMask
            if i == nArc:
                val = val | nFinalArcMask
            if (self.pos + 1) == self.arcs[arc].pos and self.i != 0:
                val = val | nNextNodeMask
                by += val.to_bytes(nBytesArc, byteorder='big')
            else:
                by += val.to_bytes(nBytesArc, byteorder='big')
                by += self.arcs[arc].addr.to_bytes(nBytesNodeAddress, byteorder='big')
        return by
        
    def getTxtRepr2 (self, nBytesArc, nBytesNodeAddress, lVal):
        nArc = len(self.arcs)
        nFinalNodeMask = 1 << ((nBytesArc*8)-1)
        nFinalArcMask = 1 << ((nBytesArc*8)-2)
        nNextNodeMask = 1 << ((nBytesArc*8)-3)
        s = "i{:_>10} -- #{:_>10}\n".format(self.i, self.addr)
        if nArc == 0:
            s += "  {:<20}  {:0>16}  i{:_>10}   #{:_>10}\n".format("", bin(nFinalNodeMask | nFinalArcMask)[2:], "0", "0")
            return s
        for i, arc in enumerate(self.arcs, 1):
            val = arc
            if i == 1 and self.final:
                val = val | nFinalNodeMask
            if i == nArc:
                val = val | nFinalArcMask
            if (self.pos + 1) == self.arcs[arc].pos  and self.i != 0:
                val = val | nNextNodeMask
                s += "  {:<20}  {:0>16}\n".format(lVal[arc], bin(val)[2:], "")
            else:
                s += "  {:<20}  {:0>16}  i{:_>10}   #{:_>10}\n".format(lVal[arc], bin(val)[2:], self.arcs[arc].i, self.arcs[arc].addr)
        return s

    # VERSION 3 =====================================================================================================
    def convToBytes3 (self, nBytesArc, nBytesNodeAddress, nBytesOffset):
        """
        Node scheme:
        - Arc length is defined by nBytesArc
        - Address length is defined by nBytesNodeAddress
        - Offset length is defined by nBytesOffset
                                       
        |                Arc                |            Address of next node  or  offset to next node              |
        |                                   |                                                                       |
         /---------------\ /---------------\ /---------------\ /---------------\ /---------------\ /---------------\
         |1|0|0| | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
         \---------------/ \---------------/ \---------------/ \---------------/ \---------------/ \---------------/
         [...]
         /---------------\ /---------------\ /---------------\
         |0|0|1| | | | | | | | | | | | | | | | | | | | | | | |     Offsets are shorter than addresses
         \---------------/ \---------------/ \---------------/ 
         /---------------\ /---------------\ /---------------\ /---------------\ /---------------\ /---------------\
         |0|1|0| | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
         \---------------/ \---------------/ \---------------/ \---------------/ \---------------/ \---------------/

          ^ ^ ^
          | | |
          | |  \_ if 1, offset instead of address of next node
          |  \___ if 1, last arc of this node
           \_____ if 1, this node is final (only on the first arc)
        """
        nArc = len(self.arcs)
        nFinalNodeMask = 1 << ((nBytesArc*8)-1)
        nFinalArcMask = 1 << ((nBytesArc*8)-2)
        nNextNodeMask = 1 << ((nBytesArc*8)-3)
        nMaxOffset = (2 ** (nBytesOffset * 8)) - 1
        if nArc == 0:
            val = nFinalNodeMask | nFinalArcMask
            by = val.to_bytes(nBytesArc, byteorder='big')
            by += (0).to_bytes(nBytesNodeAddress, byteorder='big')
            return by
        by = b""
        for i, arc in enumerate(self.arcs, 1):
            val = arc
            if i == 1 and self.final:
                val = val | nFinalNodeMask
            if i == nArc:
                val = val | nFinalArcMask
            if 1 < (self.arcs[arc].addr - self.addr) < nMaxOffset and self.i != 0:
                val = val | nNextNodeMask
                by += val.to_bytes(nBytesArc, byteorder='big')
                by += (self.arcs[arc].addr-self.addr).to_bytes(nBytesOffset, byteorder='big')
            else:
                by += val.to_bytes(nBytesArc, byteorder='big')
                by += self.arcs[arc].addr.to_bytes(nBytesNodeAddress, byteorder='big')
        return by
        
    def getTxtRepr3 (self, nBytesArc, nBytesNodeAddress, nBytesOffset, lVal):
        nArc = len(self.arcs)
        nFinalNodeMask = 1 << ((nBytesArc*8)-1)
        nFinalArcMask = 1 << ((nBytesArc*8)-2)
        nNextNodeMask = 1 << ((nBytesArc*8)-3)
        nMaxOffset = (2 ** (nBytesOffset * 8)) - 1
        s = "i{:_>10} -- #{:_>10}  ({})\n".format(self.i, self.addr, self.size)
        if nArc == 0:
            s += "  {:<20}  {:0>16}  i{:_>10}   #{:_>10}\n".format("", bin(nFinalNodeMask | nFinalArcMask)[2:], "0", "0")
            return s
        for i, arc in enumerate(self.arcs, 1):
            val = arc
            if i == 1 and self.final:
                val = val | nFinalNodeMask
            if i == nArc:
                val = val | nFinalArcMask
            if 1 < (self.arcs[arc].addr - self.addr) < nMaxOffset and self.i != 0:
                val = val | nNextNodeMask
                s += "  {:<20}  {:0>16}  i{:_>10}   +{:_>10}\n".format(lVal[arc], bin(val)[2:], self.arcs[arc].i, self.arcs[arc].addr - self.addr)
            else:
                s += "  {:<20}  {:0>16}  i{:_>10}   #{:_>10}\n".format(lVal[arc], bin(val)[2:], self.arcs[arc].i, self.arcs[arc].addr)
        return s
