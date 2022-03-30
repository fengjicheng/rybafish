from PyQt5.QtWidgets import (QWidget, QPlainTextEdit, QVBoxLayout, QHBoxLayout, QSplitter, QTableWidget, QTableWidgetItem,
        QTabWidget, QApplication, QAbstractItemView, QMenu, QFileDialog, QMessageBox, QInputDialog)

from PyQt5.QtGui import QTextCursor, QColor, QFont, QFontMetricsF, QPixmap, QIcon
from PyQt5.QtGui import QTextCharFormat, QBrush, QPainter

from PyQt5.QtCore import QTimer, QPoint

from PyQt5.QtCore import Qt, QSize

from PyQt5.QtCore import QObject, QThread

# crazy sound alert imports
from PyQt5.QtMultimedia import QSoundEffect
from PyQt5.QtCore import QUrl
#from PyQt5.QtCore import WindowState

import time, sys

#import shiboken2
#import sip

from dbi import dbi

import utils
from QPlainTextEditLN import QPlainTextEditLN

from utils import cfg
from utils import dbException, log
from utils import resourcePath
from utils import normalize_header

import re

import lobDialog, searchDialog
from autocompleteDialog import autocompleteDialog 

from SQLSyntaxHighlighter import SQLSyntaxHighlighter

import datetime
import os

from sqlparse import format

import customSQLs

from PyQt5.QtCore import pyqtSignal

reExpPlan = re.compile('explain\s+plan\s+for\s+sql\s+plan\s+cache\s+entry\s+(\d+)\s*$', re.I)

class sqlWorker(QObject):
    finished = pyqtSignal()

    def __init__(self, cons):
        super().__init__()
        
        self.psid = None
        
        self.cons = cons
        self.args = []
    
    def executeStatement(self):
    
        #print('0 --> main thread method')
        
        if not self.args:
            log('[!] sqlWorker with no args?')
            self.finished.emit()
            return
            
        sql, result, refreshMode = self.args
        
        cons = self.cons # cons - sqlConsole class itself, not just a console...

        cons.wrkException = None
        
        if cons.conn is None:
            #cons.log('Error: No connection')
            cons.wrkException = 'no db connection'
            self.finished.emit()
            return

        if len(sql) >= 2**17 and cons.conn.large_sql != True:
            log('reconnecting to handle large SQL')
            #print('replace by a pyhdb.constant? pyhdb.protocol.constants.MAX_MESSAGE_SIZE')
            
            self.dbi.largeSql = True
            
            try: 
                cons.conn = self.dbi.console_connection(cons.config)

                rows = self.dbi.execute_query(cons.conn, "select connection_id from m_connections where own = 'TRUE'", [])
                
                if len(rows):
                    self.cons.connection_id = rows[0][0]
                    log('connection open, id: %s' % self.cons.connection_id)
                    
            except dbException as e:
                err = str(e)
                #
                # cons.log('DB Exception:' + err, True)
                
                cons.wrkException = 'DB Exception:' + err
                
                cons.connect = None
                self.finished.emit()
                return
                
        #execute the query
        
        try:
            # t0 = time.time()
            
            #print('clear rows array here?')
            
            suffix = ''
            
            if len(sql) > 128:
                txtSub = sql[:128]
                suffix = '...'
            else:
                txtSub = sql
                
            m = re.search(r'^\s*select\s+top\s+(\d+)', sql, re.I)
            
            if m:
                explicitLimit = True
                resultSizeLimit = int(m.group(1))
            else:
                explicitLimit = False
                resultSizeLimit = cfg('resultSize', 1000)
                
            txtSub = txtSub.replace('\n', ' ')
            txtSub = txtSub.replace('\t', ' ')
            
            #print('start sql')
            
            m = re.search('^sleep\s?\(\s*(\d+)\s*\)$', txtSub)
            
            if m is not None:
                time.sleep(int(m.group(1)))
                self.rows_list = None
                self.cols_list = None
                dbCursor = None
                psid = None
                self.resultset_id_list = None
            else:
                self.rows_list, self.cols_list, dbCursor, psid = self.dbi.execute_query_desc(cons.conn, sql, [], resultSizeLimit)
            
                if dbCursor:
                    self.resultset_id_list = dbCursor._resultset_id_list
                else:
                    self.resultset_id_list = None
            
            result.explicitLimit = explicitLimit
            result.resultSizeLimit = resultSizeLimit          
            
            #no special treatment for the first resultset anymore
            #result.rows, result.cols = self.rows_list[0], self.cols_list[0]
            #_resultset_id = dbCursor._resultset_id_list[0]
            #print('sql finished')

            self.dbCursor = dbCursor
            self.psid = psid
            
        except dbException as e:
            err = str(e)
            
            # fixme 
            # cons.log('DB Exception:' + err, True)
            
            cons.wrkException = 'DB Exception:' + err
            
            if e.type == dbException.CONN:
                # fixme 
                log('connection lost, should we close it?')

                try: 
                    self.dbi.close_connection(cons.conn)
                except dbException as e:
                    log('[?] ' + str(e))
                except:
                    log('[!] ' + str(e))
                    
                cons.conn = None
                cons.connection_id = None
                
                
                log('connectionLost() used to be here, but now no UI possible from the thread')
                #cons.connectionLost()
                
        self.finished.emit()
        #time.sleep(0.5)
        
        #print('4 <-- main thread method <-- ')

def generateTabName():

    '''
        not used actually 01.12.20
    '''
    
    base = 'sql'
    i = 0
    
    while i < 100:
        if i > 0:
            fname = 'sql%i' % i
        else:
            fname = 'sql'
            
        #print('checking ', fname)
        
        if not os.path.isfile(fname+'.sqbkp'):
            return fname
            
        i += 1


class console(QPlainTextEditLN):
#class console(QPlainTextEdit):
    
    executionTriggered = pyqtSignal(['QString'])
    
    log = pyqtSignal(['QString'])
    
    closeSignal = pyqtSignal()
    goingToCrash = pyqtSignal()
    
    openFileSignal = pyqtSignal()
    saveFileSignal = pyqtSignal()
    
    connectSignal = pyqtSignal()
    disconnectSignal = pyqtSignal()
    abortSignal = pyqtSignal()
    
    explainSignal = pyqtSignal(['QString'])
    
    autocompleteSignal = pyqtSignal()
    
    def insertTextS(self, str):
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        cursor.insertText(str)
        
        self.setFocus()

    def __init__(self, parent):
        self.lock = False
        
        self.haveHighlighrs = False #have words highlighted
        self.bracketsHighlighted = False

        self.highlightedWords = [] # list of (start, stop) tuples of highlighed words
        
        
        self.modifiedLayouts = [] # backup of the original layouts: tuples (position, layout, additionalFormats)
                                  # position - block position (start of the paragraph)
                                  # layout - hz
                                  # af - list of modifications as a result of syntax highlighting, for example
        
        '''
        self.modifiedLayouts = {}
        
        self.modifiedLayouts['br'] = [] #Brackets only this one used as work around 
        self.modifiedLayouts['w'] = [] #words
        '''
        
        self.manualSelection = False
        self.manualSelectionPos = []
        self.manualStylesRB = [] # rollback styles

        self.lastSearch = ''    #for searchDialog
        
        super().__init__(parent)

        fontSize = utils.cfg('console-fontSize', 10)
        
        try: 
            font = QFont ('Consolas', fontSize)
        except:
            font = QFont ()
            font.setPointSize(fontSize)
            
        self.setFont(font)
        
        
        #self.setStyleSheet('{selection-background-color: #48F; selection-color: #fff;}')
        self.setStyleSheet('selection-background-color: #48F')

        self.setTabStopDistance(QFontMetricsF(font).width(' ') * 4)
        
        self.cursorPositionChanged.connect(self.cursorPositionChangedSignal) # why not just overload?
        self.selectionChanged.connect(self.consSelection)
        
        self.rehighlightSig.connect(self.rehighlight)
        
    def rehighlight(self):
        #need to force re-highlight manually because of #476

        cursor = self.textCursor()
        block = self.document().findBlockByLineNumber(cursor.blockNumber())
        
        self.SQLSyntax.rehighlightBlock(block)  # enforce highlighting 


    '''
    def insertFromMimeData(self, src):
        
            # for some reason ctrl+v does not trigger highliqter
            # so do it manually
        
        a = super().insertFromMimeData(src)
        print('insertFromMimeData(src)')
        
        cursor = self.textCursor()
        block = self.document().findBlockByLineNumber(cursor.blockNumber())
        
        self.SQLSyntax.rehighlightBlock(block)  # enforce highlighting 
        
        return a
        
    '''

    '''
    def _cl earHighlighting(self):
        self.lock = True
        
        txt = self.toPlainText()
        cursor = QTextCursor(self.document())

        format = cursor.charFormat()
        format.setBackground(QColor('white'))

        #utils.timerStart()
        
        for w in self.highlightedWords:
            cursor.setPosition(w[0],QTextCursor.MoveAnchor)
            cursor.setPosition(w[1],QTextCursor.KeepAnchor)

            cursor.setCharFormat(format)
            
        self.highlightedWords.clear()
        
        self.lock = False
    '''
      
    #def newLayout(self, type, position, lo, af):
    def newLayout(self, position, lo, af):
        
        #for l in self.modifiedLayouts[type]:
        for l in self.modifiedLayouts:
            if l[0] == position:
                #this layout already in the list
                return
            
        #self.modifiedLayouts[type].append([position, lo, af])
        #log('add layout: %s' % str(lo), 5)
        self.modifiedLayouts.append([position, lo, af])
            
    def highlight(self):
        '''
            highlights word in document based on self.highlightedWords[]
        '''
    
        blkStInit = None
        blkStCurrent = None
    
        charFmt = QTextCharFormat()
        charFmt.setBackground(QColor('#8F8'))

        for p in self.highlightedWords:
            txtblk = self.document().findBlock(p[0])
            
            blkStCurrent = txtblk.position()
    
            delta = p[0] - blkStCurrent
            
            lo = txtblk.layout()
            
            r = lo.FormatRange()
            
            r.start = delta
            r.length = p[1] - p[0]
            
            r.format = charFmt
            
            af = lo.additionalFormats()
            
            if blkStInit != blkStCurrent:
                #self.newLayout('br', blkStCurrent, lo, af)
                self.newLayout(blkStCurrent, lo, af)
                
                blkStInit = blkStCurrent

            lo.setAdditionalFormats(af + [r])

        self.haveHighlighrs = True
        
    def searchWord(self, str):
        if self.lock:
            return
            
        self.lock = True
        #print('lets search/highlight: ' + str)
        
        #for i in range(self.cons.blockCount()):
        #    txtline = self.cons.document().findBlockByLineNumber(i)
            
        #line = txtline.text()
        line = self.toPlainText()
        
        st = 0
        
        self.highlightedWords = []
        
        #print('okay, search...', str)
        
        while st >= 0:
            st = line.find(str, st)
            
            if st >= 0:
                # really this should be a \b regexp here instead of isalnum
                
                if st > 0:
                    sample = line[st-1:st+len(str)+1]
                else:
                    sample = line[0:len(str)+1]

                #mask = r'.?\b%s\b.?' % (str)
                #mask = r'.\b%s\b.' % (str)
                mask = r'\W?%s\W' % (str)

                if re.match(mask, sample):
                    #self.highlight(self.document(), st, st+len(str))
                    self.highlightedWords.append([st, st+len(str)])
                
                st += len(str)
                    
        self.lock = False
        
        if self.highlightedWords:
            self.highlight()
            
            self.viewport().repaint()
            
        return
        
    def consSelection(self):
        #512 
        if self.manualSelection:
            self.clearManualSelection()

        if cfg('noWordHighlighting'):
            return
    
        if self.lock:
            return
            
        cursor = self.textCursor()
        selected = cursor.selectedText()

        #if True or self.haveHighlighrs:
        if self.haveHighlighrs:
            # we ignore highlighted brackets here
            #log('consSelection clear highlighting', 5)
            self.clearHighlighting()

        #txtline = self.document().findBlockByLineNumber(cursor.blockNumber()) one of the longest annoing bugs, someday I will give it a name
        txtline = self.document().findBlockByNumber(cursor.blockNumber())
        line = txtline.text()
        
        if re.match('\w+$', selected):
            if re.search('\\b%s\\b' % selected, line):
                self.searchWord(selected)

        return
        
    def explainPlan(self):
    
        cursor = self.textCursor()
    
        if cursor.selection().isEmpty():
            self.log.emit('You need to select the statement manually first')
            return

        st = cursor.selection().toPlainText()
        
        st = st.strip().rstrip(';')
        
        self.explainSignal.emit(st)
    
    def formatSelection(self):
        cursor = self.textCursor()

        if cursor.selection().isEmpty():
            self.log.emit('Select the statement manually first')
            return
            
        txt = cursor.selection().toPlainText()
        
        trailingLN = False
        
        if txt[-1:] == '\n':
            trailingLN = True
        
        txt = format(txt, reindent=True, indent_width=4)
        
        if trailingLN:
           txt += '\n' 
           
        cursor.insertText(txt)
        
        
    def contextMenuEvent(self, event):
       
        cmenu = QMenu(self)
        
        menuExec = cmenu.addAction('Execute statement/selection\tF8')
        menuExecNP = cmenu.addAction('Execute without parsing\tAlt+F8')
        menuExecLR = cmenu.addAction('Execute but leave the results\tCtrl+F9')
        cmenu.addSeparator()
        menuOpenFile = cmenu.addAction('Open File in this console')
        menuSaveFile = cmenu.addAction('Save File\tCtrl+S')
        cmenu.addSeparator()
        menuDisconnect = cmenu.addAction('Disconnect from the DB')
        menuConnect = cmenu.addAction('(re)connecto to the DB')
        menuAbort = cmenu.addAction('Generate cancel session sql')
        menuClose = cmenu.addAction('Close console\tCtrl+W')
        
        #if cfg('experimental'):
        cmenu.addSeparator()
        explainPlan = cmenu.addAction('Explain Plan\tCtrl+Shift+X')
        sqlFormat = cmenu.addAction('Format SQL\tCtrl+Shift+O')
            
        if cfg('dev'):
            cmenu.addSeparator()
            menuTest = cmenu.addAction('Test menu')
            createDummyTable = cmenu.addAction('Generate test result')
            createClearResults = cmenu.addAction('Clear results')
            generateCrash = cmenu.addAction('Crash now!')

        action = cmenu.exec_(self.mapToGlobal(event.pos()))

        if cfg('dev'):
            if action == createDummyTable:
                self._parent.closeResults()
                self._parent.dummyResultTable2(200 * 1000)

            if action == generateCrash:
                log('Im going to crash!!')
                log('Im going to crash: %i' % (1/0))
                
            if action == createClearResults:
                self._parent.closeResults()


        if action == menuExec:
            self.executionTriggered.emit('normal')
        if action == menuExecNP:
            self.executionTriggered.emit('no parsing')
        if action == menuExecLR:
            self.executionTriggered.emit('leave results')
        elif action == menuDisconnect:
            self.disconnectSignal.emit()
        elif action == menuAbort:
            self.abortSignal.emit()
        elif action == menuConnect:
            self.connectSignal.emit()
        elif action == menuOpenFile:
            self.openFileSignal.emit()
        elif action == menuSaveFile:
            self.saveFileSignal.emit()
        elif action == menuClose:
            self.closeSignal.emit()
        elif cfg('dev') and action == menuTest:
            cursor = self.textCursor()
            cursor.removeSelectedText()
            cursor.insertText('123')
            self.setTextCursor(cursor)
            
        #if cfg('experimental') and action == sqlFormat:
        if action == sqlFormat:
            self.formatSelection()
        
        if action == explainPlan:
            self.explainPlan()
            
    def findString(self, str = None):
    
        if str is None:
            if self.lastSearch  is None:
                return
                
            str = self.lastSearch 
        else:
            self.lastSearch = str
    
        def select(start, stop):
            cursor = QTextCursor(self.document())

            cursor.setPosition(start,QTextCursor.MoveAnchor)
            cursor.setPosition(stop,QTextCursor.KeepAnchor)
            
            self.setTextCursor(cursor)
            
        text = self.toPlainText().lower()
        
        st = self.textCursor().position()
        
        st = text.find(str.lower(), st)
        
        if st >= 0:
            select(st, st+len(str))
        else:
            #search from the start
            st = text.find(str, 0)
            if st >= 0:
                select(st, st+len(str))
        
    # the stuff moved to QPlainTextEditLN because I am stupid and lazy.
    
    '''
    def duplicateLine (self):
        cursor = self.textCursor()
        
        if cursor.selection().isEmpty():
            txtline = self.document().findBlockByLineNumber(cursor.blockNumber())
            
            #self.moveCursor(QTextCursor.EndOfLine, QTextCursor.MoveAnchor)
            cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.MoveAnchor)
            cursor.insertText('\n' + txtline.text())
        else:
            txt = cursor.selectedText()

            cursor.clearSelection()
            cursor.insertText(txt)

    def tabKey(self):
        
        cursor = self.textCursor()
        
        cursor.beginEditBlock() # deal with undo/redo
        
        txt = cursor.selectedText()
        
        stPos = cursor.selectionStart()
        endPos = cursor.selectionEnd()
        
        stLine = self.document().findBlock(stPos).blockNumber()
        endLineBlock = self.document().findBlock(endPos)
        endLine = endLineBlock.blockNumber()
        
        #check the selection end position
        if stLine != endLine and endLineBlock.position() < endPos:
            endLine += 1 # endLine points to the next line after the block we move
        
        if not cursor.hasSelection() or (stLine == endLine):
            cursor.removeSelectedText()
            cursor.insertText('    ')
        else:

            for i in range(stLine, endLine):
                line = self.document().findBlockByLineNumber(i)
                pos = line.position()

                #move selection start to start of the line
                if i == stLine:
                    stPos = pos

                cursor.setPosition(pos, QTextCursor.MoveAnchor)
                cursor.insertText('    ')
                
            #calculate last line end position to update selection
            endPos = pos + len(line.text()) + 1
            
            cursor.clearSelection()
            cursor.setPosition(stPos, QTextCursor.MoveAnchor)
            cursor.setPosition(endPos, QTextCursor.KeepAnchor)
            
        self.setTextCursor(cursor)
        
        cursor.endEditBlock() 
        
    def shiftTabKey(self):
        
        cursor = self.textCursor()
        
        cursor.beginEditBlock() # deal with undo/redo
        
        txt = cursor.selectedText()
        
        stPos = cursor.selectionStart()
        endPos = cursor.selectionEnd()
        
        stLine = self.document().findBlock(stPos).blockNumber()
        endLineBlock = self.document().findBlock(endPos)
        endLine = endLineBlock.blockNumber()
        
        #check the selection end position
        if endLineBlock.position() < endPos:
            endLine += 1 # endLine points to the next line after the block we move
        
        if not cursor.hasSelection() or (stLine == endLine):
            #cursor.removeSelectedText()
            
            line = self.document().findBlockByLineNumber(stLine)
            pos = line.position()
            cursor.setPosition(pos, QTextCursor.MoveAnchor)

            txt = line.text()[:4]
            
            if len(txt) > 0 and txt[0] == '\t':
                cursor.deleteChar()
            else:
                l = min(len(txt), 4)
                for j in range(l):

                    if txt[j] == ' ':
                        cursor.deleteChar()
                    else:
                        break
            
        else:

            for i in range(stLine, endLine):

                line = self.document().findBlockByLineNumber(i)
                pos = line.position()
                cursor.setPosition(pos, QTextCursor.MoveAnchor)

                #move selection start to start of the line
                if i == stLine:
                    stPos = pos

                txt = line.text()[:4]
                
                l = min(len(txt), 4)
                
                if len(txt) > 0 and txt[0] == '\t':
                    cursor.deleteChar()
                else:
                    for j in range(l):
                        if txt[j] == ' ':
                            cursor.deleteChar()
                        else:
                            break
                
            #calculate last line end position to update selection

            if endLine < self.document().blockCount():
                endPos = pos + len(line.text()) + 1
            else:
                endPos = pos + len(line.text())
            
            cursor.clearSelection()
            cursor.setPosition(stPos, QTextCursor.MoveAnchor)
            
            cursor.setPosition(endPos, QTextCursor.KeepAnchor)
            
        self.setTextCursor(cursor)
        
        cursor.endEditBlock() 
    '''
    
    '''
    def moveLine(self, direction):

        cursor = self.textCursor()
        pos = cursor.position()
        
        lineFrom = self.document().findBlock(pos)

        startPos = lineFrom.position()
        endPos = startPos + len(lineFrom.text())

        if direction == 'down':
            lineTo = self.document().findBlock(endPos + 1)
        else:
            lineTo = self.document().findBlock(startPos - 1)

        cursor.beginEditBlock() #deal with unso/redo
        # select original line
        cursor.setPosition(startPos, QTextCursor.MoveAnchor)
        cursor.setPosition(endPos, QTextCursor.KeepAnchor)
        
        textMove = cursor.selectedText()
        
        # replace it by text from the new location
        cursor.insertText(lineTo.text())

        # now put moving text in place
        startPos = lineTo.position()
        endPos = startPos + len(lineTo.text())

        cursor.setPosition(startPos, QTextCursor.MoveAnchor)
        cursor.setPosition(endPos, QTextCursor.KeepAnchor)

        cursor.insertText(textMove)
        
        cursor.endEditBlock() #deal with unso/redo
        
        self.repaint()
        
        cursor.setPosition(startPos, QTextCursor.MoveAnchor)
        cursor.setPosition(startPos + len(textMove), QTextCursor.KeepAnchor)
        
        self.setTextCursor(cursor)
    '''
    
    def keyPressEvent (self, event):
    
        #print('console keypress')
        
        modifiers = QApplication.keyboardModifiers()

        if event.key() == Qt.Key_F8 or  event.key() == Qt.Key_F9:

            if modifiers & Qt.AltModifier:
                self.executionTriggered.emit('no parsing')
            elif modifiers & Qt.ControlModifier:
                self.executionTriggered.emit('leave results')
            else:
                self.executionTriggered.emit('normal')
            
            '''
            
            all this moved to QPlainTextEdit
            
            elif modifiers & Qt.ControlModifier and event.key() == Qt.Key_D:
                self.duplicateLine()

            elif modifiers & Qt.ControlModifier and event.key() == Qt.Key_Down:
                self.moveLine('down')

            elif modifiers & Qt.ControlModifier and event.key() == Qt.Key_Up:
                self.moveLine('up')

            elif event.key() == Qt.Key_Backtab and not (modifiers & Qt.ControlModifier):
                self.shiftTabKey()

            elif event.key() == Qt.Key_Tab and not (modifiers & Qt.ControlModifier):
                self.tabKey()
                
            elif modifiers & Qt.ControlModifier and modifiers & Qt.ShiftModifier and event.key() == Qt.Key_U:
                cursor = self.textCursor()
                
                txt = cursor.selectedText()
                
                cursor.insertText(txt.upper())
                
            elif modifiers == Qt.ControlModifier and event.key() == Qt.Key_U:
                cursor = self.textCursor()
                
                txt = cursor.selectedText()
                
                cursor.insertText(txt.lower())
            '''
        elif modifiers == Qt.ControlModifier and event.key() == Qt.Key_F:
                search = searchDialog.searchDialog(self.lastSearch)
                
                search.findSignal.connect(self.findString)
                
                search.exec_()
        elif event.key() == Qt.Key_F3:
            self.findString()
        elif event.key() == Qt.Key_O and (modifiers == Qt.ControlModifier | Qt.ShiftModifier):
            self.formatSelection()
        elif event.key() == Qt.Key_X and (modifiers == Qt.ControlModifier | Qt.ShiftModifier):
            self.explainPlan()
            
        elif modifiers == Qt.ControlModifier and event.key() == Qt.Key_Space:
            self.autocompleteSignal.emit()
        else:
            #have to clear each time in case of input right behind the braket
            #elif event.key() not in (Qt.Key_Shift, Qt.Key_Control):
            '''
            if self.haveHighlighrs:
                self.clearHighlighting('br')
            if self.bracketsHighlighted:
                self.clearHighlighting('br')
            '''
            if self.bracketsHighlighted:
                #log('keypress clear highlighting', 5)
                self.clearHighlighting()
                
            super().keyPressEvent(event)
            
            #if modifiers == Qt.ControlModifier and event.key() == Qt.Key_V:
                #print('QSyntaxHighlighter::rehighlightBlock')
            '''
                cursor = self.textCursor()
                block = self.document().findBlockByLineNumber(cursor.blockNumber())
        
                self.SQLSyntax.rehighlightBlock(block)  # enforce highlighting 
            '''

    #def clearHighlighting(self, type):
    def clearHighlighting(self):
        #log('modifiedLayouts count: %i' % len(self.modifiedLayouts), 5)
        #return
        #log('clearHighlighting', 5)
        if self.bracketsHighlighted or self.haveHighlighrs and not self.lock:
            
            #for lol in self.modifiedLayouts[type]:
            
            #log('modifiedLayouts count: %i' % len(self.modifiedLayouts), 5)
            for lol in self.modifiedLayouts:
            
                lo = lol[1]
                af = lol[2]

                #log('mod: %s' % str(lo), 5)
                #log('lines: %s' % lo.lineCount(), 5)
                lo.setAdditionalFormats(af)
                #log('clear went ok', 5)
                
            #self.modifiedLayouts[type].clear()
            self.viewport().repaint()

        self.modifiedLayouts.clear()
            
        self.bracketsHighlighted = False # <<<< this is not true in case of #382
                                         # <<<< we came here just to clear words
                                         # somehow need to manage this explicitly
                                         
        self.haveHighlighrs = False

        '''
        if type == 'br':
            self.bracketsHighlighted = False
        elif type == 'br':
            self.haveHighlighrs = False
        '''

    def clearManualSelection(self):
        #print('clear manualSelectionPos', self.manualSelectionPos)
        
        start = self.manualSelectionPos[0]
        stop = self.manualSelectionPos[1]
        
        cursor = QTextCursor(self.document())
        
        for (lo, af) in self.manualStylesRB:
            lo.setAdditionalFormats(af)
            
        self.manualStylesRB.clear()

        self.manualSelection = False
        self.manualSelectionPos = []
        
        self.viewport().repaint()
        

    def cursorPositionChangedSignal(self):
        #log('cursorPositionChangedSignal', 5)
    
        t0 = time.time()
        
        #print('cursorPositionChangedSignal', self.lock)
    
        if self.manualSelection:
            self.clearManualSelection()
    
        if cfg('noBracketsHighlighting'):
            return
    
        self.checkBrackets()
        
        t1 = time.time()
        
        #log('cursorPositionChangedSignal: %s ms' % (str(round(t1-t0, 3))), 5)
        
    def highlightBrackets(self, block, pos1, pos2, mode):
        #print ('highlight here: ', pos1, pos2)
    
        txtblk1 = self.document().findBlock(pos1)
        txtblk2 = self.document().findBlock(pos2)
        
        delta1 = pos1 - txtblk1.position()
        delta2 = pos2 - txtblk2.position()
        
        charFmt = QTextCharFormat()
        charFmt.setForeground(QColor('#F00'))
        
        #fnt = charFmt.font().setWeight(QFont.Bold)
        #charFmt.setFont(fnt)
        
        lo1 = txtblk1.layout()
        r1 = lo1.FormatRange()
        r1.start = delta1
        r1.length = 1
        
        if txtblk1.position() == txtblk2.position():
            lo2 = lo1
            
            r2 = lo2.FormatRange()
            r2.start = delta2
            r2.length = 1
            
            r1.format = charFmt
            r2.format = charFmt

            af = lo1.additionalFormats()
            
            lo1.setAdditionalFormats(af + [r1, r2])
            
            #self.newLayout('br', txtblk1.position(), lo1, af)
            self.newLayout(txtblk1.position(), lo1, af)
        else:
            lo2 = txtblk2.layout()

            r2 = lo2.FormatRange()
            r2.start = delta2
            r2.length = 1

            r1.format = charFmt
            r2.format = charFmt
            
            af1 = lo1.additionalFormats()
            af2 = lo2.additionalFormats()
            
            lo1.setAdditionalFormats(af1 + [r1])
            lo2.setAdditionalFormats(af2 + [r2])
            
            #self.newLayout('br', txtblk2.position(), lo2, af2) zhere??
            self.newLayout(txtblk1.position(), lo1, af1)
            self.newLayout(txtblk2.position(), lo2, af2)
        
        self.viewport().repaint()
        
    def checkBrackets(self):
    
        if self.bracketsHighlighted:
            #log('checkBrackets clear', 5)
            self.clearHighlighting()
            #self.clearHighlighting('br')
            #self.clearHighlighting('w')
    
        cursor = self.textCursor()
        pos = cursor.position()

        text = self.toPlainText()

        textSize = len(text)
        
        def scanPairBracket(pos, shift):
        
            bracket = text[pos]
        
            depth = 0
        
            if bracket == ')':
                pair = '('
            elif bracket == '(':
                pair = ')'
            elif bracket == '[':
                pair = ']'
            elif bracket == ']':
                pair = '['
            else:
                return -1
            
            i = pos + shift
            
            if bracket in (')', ']'):
                # skan forward
                stop = 0
                step = -1
            else:
                stop = textSize-1
                step = 1
                
            
            while i != stop:
                i += step
                ch = text[i]
                
                if ch == bracket:
                    depth += 1
                    continue
                
                if ch == pair:
                    if depth == 0:
                        return i
                    else:
                        depth -=1
                    
            return -1
            
        # text[pos] - symboll right to the cursor
        # when pos == textSize text[pos] - crash
        
        bPos = None
        
        if pos > 0 and text[pos-1] in ('(', '[', ')', ']', ):
            brLeft = True
        else:
            brLeft = False
            
        if pos < textSize and text[pos] in ('(', '[', ')', ']', ):
            brRight = True
        else:
            brRight = False
            
            
        if brLeft or brRight:
        
            if brLeft:
                bPos = pos-1
                if text[pos-1] in ('(', '['):
                    shift = 0
                else:
                    shift = 0
                pb = scanPairBracket(bPos, shift)
            else:
                bPos = pos
                shift = 0
                pb = scanPairBracket(bPos, shift)

            if pb >= 0:
                self.bracketsHighlighted = True
                self.highlightBrackets(self.document(), bPos, pb, True)

class resultSet(QTableWidget):
    '''
        Implements the result set widget, basically QTableWidget with minor extensions
        
        Created to show the resultset (one result tab), destroyed when re-executed.

        Table never refilled. 
    '''
    
    alertSignal = pyqtSignal(['QString'])
    insertText = pyqtSignal(['QString'])
    executeSQL = pyqtSignal(['QString', 'QString'])
    triggerAutorefresh = pyqtSignal([int])
    
    def __init__(self, conn):
    
        self._resultset_id = None    # filled manually right after execute_query

        self._connection = None      # this one populated in sqlFinished # 2021-07-16, #377
        
        self.statement = None        # statements string (for refresh)
        
        self.LOBs = False            # if the result contains LOBs
        self.detached = None         # supposed to be defined only if LOBs = True
        self.detachTimer = None      # results detach timer
        
        self.cols = [] # column descriptions
        self.rows = [] # actual data 
        
        self.headers = [] # column names
        
        self.psid = None # psid to drop on close
        
        # overriden in case of select top xxxx
        self.explicitLimit = False 
        self.resultSizeLimit = cfg('resultSize', 1000)
        
        self.timer = None
        self.timerDelay = None
        
        self.timerSet = None        # autorefresh menu switch flag
        
        self.alerted = None         # one time alarm signal flag
        
        super().__init__()
        
        verticalHeader = self.verticalHeader()
        verticalHeader.setSectionResizeMode(verticalHeader.Fixed)
        
        scale = 1

        fontSize = utils.cfg('result-fontSize', 10)
        
        font = QFont ()
        font.setPointSize(fontSize)
        
        self.setFont(font)
        
        itemFont = QTableWidgetItem('').font()
        
        #rowHeight = scale * QFontMetricsF(itemFont).height() + 7 
        rowHeight = scale * QFontMetricsF(itemFont).height() + 8
        
        #rowHeight = 19
        
        verticalHeader.setDefaultSectionSize(rowHeight)
        
        self.setWordWrap(False)
        self.horizontalHeader().setStyleSheet("QHeaderView::section { background-color: lightgray }")
        
        self.cellDoubleClicked.connect(self.dblClick) # LOB viewer

        self.keyPressEvent = self.resultKeyPressHandler
        
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        
        self.horizontalHeader().setMinimumSectionSize(0)

        # any style change resets everything to some defaults....
        # like selected color, etc. just gave up.

        #self.setStyleSheet('QTableWidget::item {padding: 2px; border: 1px}')
        #self.setStyleSheet('QTableWidget::item {margin: 3px; border: 1px}')
        
        #self.setStyleSheet('QTableWidget::item {padding: 2px; border: 1px; selection-background-color}')
        #self.setStyleSheet('QTableWidget::item:selected {padding: 2px; border: 1px; background-color: #08D}')
        
        self.highlightColumn = None     # column index to highlight
        self.highlightValue = None      # value to highlight, when None - changes will be highlighted

        
    def highlightRefresh(self):
        rows = self.rowCount()
        cols = self.columnCount()
        
        col = self.highlightColumn
        value = self.highlightValue

        if col == -1 or rows == 0:
            return

        hl = False

        clr = QColor(cfg('highlightColor', '#def'))
        hlBrush = QBrush(clr)

        clr = QColor(clr.red()*0.9, clr.green()*0.9, clr.blue()*0.95)
        hlBrushLOB = QBrush(clr)
        
        wBrush = QBrush(QColor('#ffffff'))
        wBrushLOB = QBrush(QColor('#f4f4f4'))
        
        if value is None:
            val = self.item(0, col).text()
        else:
            val = value
            
        lobCols = []
        
        for i in range(len(self.cols)):
            if self.dbi.ifLOBType(self.cols[i][1]):
                lobCols.append(i)
            
        for i in range(rows):
        
            if value is None:
                if val != self.item(i, col).text():
                    hl = not hl
            else:
                if val == self.item(i, col).text():
                    hl = True
                else:
                    hl = False
            
            if hl:
                for j in range(cols):
                    if j in lobCols:
                        self.item(i, j).setBackground(hlBrushLOB)
                    else:
                        self.item(i, j).setBackground(hlBrush)
            else:
                for j in range(cols):
                    if j in lobCols:
                        self.item(i, j).setBackground(wBrushLOB)
                    else:
                        self.item(i, j).setBackground(wBrush)
                    
            if value is None:
                val = self.item(i, col).text()
    
    def contextMenuEvent(self, event):
        def prepareColumns():
            headers = []
            headers_norm = []
            
            sm = self.selectionModel()
            
            for c in sm.selectedIndexes():
                r, c = c.row(), c.column()

                cname = self.headers[c]
                
                if cname not in headers:
                    headers.append(cname)
                
                
            for h in headers:
                headers_norm.append(normalize_header(h))
                
            return headers_norm
            
       
        cmenu = QMenu(self)

        copyColumnName = cmenu.addAction('Copy Column Name(s)')
        copyTableScreen = cmenu.addAction('Take a Screenshot')
        
        cmenu.addSeparator()
        insertColumnName = cmenu.addAction('Insert Column Name(s)')
        copyFilter = cmenu.addAction('Generate Filter Condition')
        
        cmenu.addSeparator()
        
        refreshTimerStart = None
        refreshTimerStop = None
        
        i = self.currentColumn()
        
        #if cfg('experimental'):
        cmenu.addSeparator()
    
        highlightColCh = cmenu.addAction('Highlight changes')
        highlightColVal = cmenu.addAction('Highlight this value')
            
        cmenu.addSeparator()
        
        abapCopy = cmenu.addAction('ABAP-style copy')

        cmenu.addSeparator()
        
        if not self.timerSet:
            refreshTimerStart = cmenu.addAction('Schedule automatic refresh for this result set')
        else:
            refreshTimerStop = cmenu.addAction('Stop autorefresh')
        
        if i >= 0 and self.headers[i] in customSQLs.columns:
            cmenu.addSeparator()

            for m in customSQLs.menu[self.headers[i]]:
                customSQL = cmenu.addAction(m)

        action = cmenu.exec_(self.mapToGlobal(event.pos()))
        
        if action == None:
            return

        '''
        if action == copyColumnName:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.cols[i][0])
        '''
        
        #if cfg('experimental') and action == highlightColCh:
        if action == highlightColCh:
            self.highlightColumn = i
            self.highlightRefresh()

        #if cfg('experimental') and action == highlightColVal:
        if action == highlightColVal:
            self.highlightColumn = i
            self.highlightValue = self.item(self.currentRow(), i).text()
            self.highlightRefresh()
        
        if action == insertColumnName:
            headers_norm = prepareColumns()
                
            names = ', '.join(headers_norm)
            
            self.insertText.emit(names)
            
        if action == copyColumnName:
            clipboard = QApplication.clipboard()
            
            headers_norm = prepareColumns()
                
            names = ', '.join(headers_norm)

            clipboard.setText(names)

        if action == copyFilter:
            sm = self.selectionModel()
            
            values = []
                        
            for c in sm.selectedIndexes():
                r, c = c.row(), c.column()

                value = self.rows[r][c]
                cname = self.headers[c]

                if self.dbi.ifNumericType(self.cols[c][1]):
                    values.append('%s = %s' % (normalize_header(cname), value))
                elif self.dbi.ifTSType(self.cols[c][1]):
                    values.append('%s = \'%s\'' % (normalize_header(cname), utils.timestampToStr(value)))
                else:
                    values.append('%s = \'%s\'' % (normalize_header(cname), str(value)))
                    
            filter = ' and '.join(values)

            self.insertText.emit(filter)
            
        if action == copyTableScreen:
            w = self.verticalHeader().width() + self.horizontalHeader().length() + 1
            h = self.verticalHeader().length() + self.horizontalHeader().height() + 1
            #pixmap = QPixmap(self.size())
            
            if w > self.size().width():
                w = self.size().width()
            
            if h > self.size().height():
                h = self.size().height()
            
            pixmap = QPixmap(QSize(w, h))
            
            self.render(pixmap)
            
            QApplication.clipboard().setPixmap(pixmap)

        if action == refreshTimerStart:
            '''
                triggers the auto-refresh timer
                
                the timer itself is to be processed by the parent SQLConsole object as it has 
                all the relevant accesses
                
                the feature is blocked when there are several resultset tabs
            '''

            id = QInputDialog

            value, ok = id.getInt(self, 'Refresh interval', 'Input the refresh interval in seconds                          ', self.defaultTimer[0], 0, 3600, 5)
            
            if ok:
                self.triggerAutorefresh.emit(value)
                self.timerSet = True
                
                self.defaultTimer[0] = value

        if action == refreshTimerStop:
            log('disabeling the timer...')
            self.triggerAutorefresh.emit(0)
            self.timerSet = False

        if action == abapCopy:
            self.copyCells(abapMode=True)
            
        if action is not None and i >= 0:
            
            key = self.headers[i] + '.' + action.text()
            
            if key in customSQLs.sqls:
                # custom sql menu item
            
                r = self.currentItem().row()
                c = self.currentItem().column()
                
                sm = self.selectionModel()

                if len(sm.selectedIndexes()) != 1:
                    self.log('Only single value supported for this action.', True)
                    return
                
                value = str(self.rows[r][c])
                
                #sql = customSQLs.sqls[key].replace('$value', value)
                
                self.executeSQL.emit(key, value)
                
                
        
    def detach(self):
        if self._resultset_id is None:
            # could be if the result did not have result: for example DDL or error statement
            # but it's strange we are detachung it...
            log('[!] attempted to detach resultset with no _resultset_id')
            return
            
        result_str = utils.hextostr(self._resultset_id)
        
        if self._connection is None:
            log('[!] resultset connection is None!')
            return
        
        if self.detached == False and self._resultset_id is not None:
            log('closing the resultset: %s' % (result_str))
            try:
                self.dbi.close_result(self._connection, self._resultset_id) 
                self.detached = True
            except Exception as e:
                log('[!] Exception: ' + str(e))
        else:
            log('[?] already detached?: %s' % result_str)

    def detachCB(self):
        log('detach timer triggered')
        
        if self.detachTimer is None:
            log('[?] why the timer is None?')
            return
            
        self.detachTimer.stop()
        self.detachTimer = None
        self.detach()
        
    def triggerDetachTimer(self, window):
        dtimer = cfg('detachTimeout', 300)
        
        log('Setting detach timer for %s %i sec' % (utils.hextostr(self._resultset_id), dtimer))
        self.detachTimer = QTimer(window)
        self.detachTimer.timeout.connect(self.detachCB)
        self.detachTimer.start(1000 * dtimer)
    
    def csvVal(self, v, t):
        '''escapes single value based on type'''
        
        if v is None:
            return utils.cfg('nullStringCSV', '')
        elif self.dbi.ifBLOBType(t):
            return str(v.encode())
        else:
            if self.dbi.ifNumericType(t):
                return utils.numberToStrCSV(v, False)
            elif self.dbi.ifRAWType(t):
                return v.hex()
            elif self.dbi.ifTSType(t):
                return utils.timestampToStr(v)
            else:
                return str(v)
        
    
    def csvRow_deprecado(self, r):
        
        values = []
        
        # print varchar values to be quoted by "" to be excel friendly
        for i in range(self.columnCount()):
            #values.append(table.item(r, i).text())

            val = self.rows[r][i]
            vType = self.cols[i][1]
            
            values.append(self.csvVal(val, vType))
            
        return ';'.join(values)
        
    def copyCells(self, abapMode = False):
        '''
            copy cells or rows or columns implementation
        '''
        
        def abapCopy():

            maxWidth = 32
            widths = []
            
            widths = [0]*len(colList)
            types = [0]*len(colList)
            
            for c in range(len(colList)):
            
                types[c] = self.cols[colList[c]][1]
            
                for r in range(len(copypaste)):
                
                    if widths[c] < len(copypaste[r][c]):
                        if len(copypaste[r][c]) >= maxWidth:
                            widths[c] = maxWidth
                            break
                        else:
                            widths[c] = len(copypaste[r][c])
                            
                            
            tableWidth = 0
            
            for c in widths:
                tableWidth += c + 1
                
            tableWidth -= 1
                
            topLine = '-' + '-'.rjust(tableWidth, '-') + '-'
            mdlLine = '|' + '-'.rjust(tableWidth, '-') + '|'
                            
            csv = topLine + '\n'
            
            i = 0
            for r in copypaste:
                for c in range(len(colList)):
                    #val = r[c][:maxWidth]
                    
                    if len(r[c]) > maxWidth:
                        val = r[c][:maxWidth-1] + '…'
                    else:
                        val = r[c][:maxWidth]
                    
                    if self.dbi.ifNumericType(types[c]) and i > 0:
                        val = val.rjust(widths[c], ' ')
                    else:
                        val = val.ljust(widths[c], ' ')
                    
                    csv += '|' + val
                    
                csv += '|\n'

                if i == 0:
                    csv += mdlLine + '\n'
                    i += 1
                
            csv += topLine + '\n'
            
            return csv
        
    
        sm = self.selectionModel()
        
        colIndex = []
        colList = []
        
        for c in sm.selectedColumns():
            colIndex.append(c.column())
        
        rowIndex = []
        for r in sm.selectedRows():
            rowIndex.append(r.row())
            
        copypaste = []
        
        if len(rowIndex) >= 1000:
            # and len(colIndex) >= 5 ?
            # it is to expensive to check
            cellsSelection = False
        else:
            #this will be checked right away
            cellsSelection = True
        
        if (colIndex or rowIndex):
            # scan all selected cells to make sure this is pure column or row selection
        
            utils.timerStart()
        
            cellsSelection = False
            
            if len(sm.selectedIndexes()) == 1:
                #single cell selected, no need header for this
                cellsSelection = True
            else:
                for cl in sm.selectedIndexes():
                    r = cl.row()
                    c = cl.column()
                    
                    if (colIndex and c not in colIndex) or (rowIndex and r not in rowIndex):
                        # okay, something is not really inside the column (row), full stop and make regular copy
                    
                        cellsSelection = True
                        break
                    
            utils.timeLap()
            s = utils.timePrint()
            
            log('Selection model check: %s' % s[0], 5)
            
        if False and cellsSelection and abapMode:
            self.log('ABAP mode is only available when rows or columns are selected.', True)
        
        if not cellsSelection and rowIndex: 
            # process rows
            
            utils.timerStart()
            rowIndex.sort()
            
            cc = self.columnCount()
                
            hdrrow = []
            
            i = 0
            
            for h in self.headers:
            
                if len(self.headers) > 1 or abapMode:
                
                    if self.columnWidth(i) > 4:
                        hdrrow.append(h)
                        
                        colList.append(i) # important for abapCopy
                    
                i+=1
                    
            if hdrrow:
                copypaste.append(hdrrow)
    
    
            for r in rowIndex:
                values = []
                for c in range(cc):
                
                    if self.columnWidth(c) > 4:
                        values.append(self.csvVal(self.rows[r][c], self.cols[c][1]))
                    
                copypaste.append(values)
                
            if abapMode:
                csv = abapCopy()
            else:
                csv = ''
                for r in copypaste:
                    csv += ';'.join(r) + '\n'
            
            QApplication.clipboard().setText(csv)

            utils.timeLap()
            s = utils.timePrint()
            
            log('Clipboard formatting took: %s' % s[0], 5)
            QApplication.clipboard().setText(csv)

        elif not cellsSelection and colIndex: 
            # process columns
            colIndex.sort()
            
            hdrrow = []
            
            for c in colIndex:

                if self.columnWidth(c) > 4:
                    hdrrow.append(self.headers[c])
                    colList.append(c)

                
            if self.rowCount() > 1 or abapMode:
                copypaste.append(hdrrow)
                
            for r in range(self.rowCount()):
                values = []
                
                for c in colIndex:
                    if self.columnWidth(c) > 4:
                        values.append(self.csvVal(self.rows[r][c], self.cols[c][1]))
                
                copypaste.append(values)
            
            if abapMode:
                csv = abapCopy()
            else:
                csv = ''
                for r in copypaste:
                    csv += ';'.join(r) + '\n'
            
            QApplication.clipboard().setText(csv)
            
        else:
            # copy column
            #print('just copy')
            
            rowIndex = []
            colIndex = {}

            # very likely not the best way to order list of pairs...
            
            for c in sm.selectedIndexes():
            
                r = c.row() 
            
                if r not in rowIndex:
                    rowIndex.append(r)
                    
                if r in colIndex.keys():
                    colIndex[r].append(c.column())
                else:
                    colIndex[r] = []
                    colIndex[r].append(c.column())
            
            rowIndex.sort()
            
            if abapMode:
                # check if the square area selected first
                
                if len(colIndex) > 0:
                    colList = colIndex[rowIndex[0]].copy()
                else:
                    colList = range(len(self.cols)) #fake 'all columns selected' list when the selection is empty
                
                abapNotPossible = False
                
                for ci in colIndex:
                    
                    if colList != colIndex[ci]:
                        abapNotPossible = True
                        break
                        
                if abapNotPossible:
                    self.log('ABAP-style copy is only possible for rectangular selections.', True)
                    return
                        
                values = []
                for c in colList:
                    if self.columnWidth(c) > 4:
                        values.append(self.headers[c])
                        
                copypaste.append(values)

                for r in rowIndex:
                    values = []

                    for c in colList:
                    
                        if self.columnWidth(c) > 4:
                            values.append(self.csvVal(self.rows[r][c], self.cols[c][1]))
                        
                    copypaste.append(values)
                    
                    
                csv = abapCopy()
                
                QApplication.clipboard().setText(csv)
                
                return
                
            
            rows = []
            
            for r in rowIndex:
                colIndex[r].sort()

                values = []
                
                for c in colIndex[r]:
                
                    value = self.rows[r][c]
                    vType = self.cols[c][1]
                    
                    if value is None:
                        values.append(utils.cfg('nullStringCSV', ''))
                    else:
                        if self.dbi.ifBLOBType(vType):
                            values.append(str(value.encode()))
                        else:
                            if self.dbi.ifNumericType(vType):
                                values.append(utils.numberToStrCSV(value, False))
                            elif self.dbi.ifRAWType(vType):
                                values.append(value.hex())
                            elif self.dbi.ifTSType(vType):
                                #values.append(value.isoformat(' ', timespec='milliseconds'))
                                values.append(utils.timestampToStr(value))
                            else:
                                values.append(str(value))
                                
                rows.append( ';'.join(values))

            result = '\n'.join(rows)
            
            QApplication.clipboard().setText(result)
        

    def resultKeyPressHandler(self, event):
    
        modifiers = QApplication.keyboardModifiers()
        
        if modifiers == Qt.ControlModifier:
            if event.key() == Qt.Key_A:
                self.selectAll()
            
            if event.key() == Qt.Key_C or event.key() == Qt.Key_Insert:
                self.copyCells()
        
        else:
            super().keyPressEvent(event)
            
    def populate(self, refreshMode = False):
        '''
            populates the result set based on
            self.rows, self.cols
        '''
    
        self.clear()
    
        cols = self.cols
        rows = self.rows
    
        row0 = []

        for c in cols:
            row0.append(c[0])
            
        self.headers = row0.copy()
           
        self.setColumnCount(len(row0))

        self.setHorizontalHeaderLabels(row0)
        
        
        if not refreshMode:
            self.resizeColumnsToContents()
        
        self.setRowCount(len(rows))
        
        adjRow = 10 if len(rows) >= 10 else len(rows)

        #return -- it leaks even before this point
        
        alert_str = cfg('alertTriggerOn')
        
        if alert_str:
            if alert_str[0:1] == '{' and alert_str[-1:] == '}':
                alert_prefix = alert_str[:-1]
                alert_len = len(alert_str)
        
        #fill the result table
                
        for r in range(len(rows)):
            #log('populate result: %i' % r, 5)
            for c in range(len(row0)):
                
                val = rows[r][c]
                
                if val is None:
                    val = utils.cfg('nullString', '?')
                    
                    item = QTableWidgetItem(val)
                elif self.dbi.ifNumericType(cols[c][1]):
                
                    if self.dbi.ifDecimalType(cols[c][1]):
                        #val = utils.numberToStr(val, 3)
                        val = utils.numberToStrCSV(val)
                    else:
                        val = utils.numberToStr(val)
                    
                    item = QTableWidgetItem(val)
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                elif self.dbi.ifLOBType(cols[c][1]): #LOB
                    #val = val.read()
                    if self.dbi.ifBLOBType(cols[c][1]):
                        if val is None:
                            val = utils.cfg('nullString', '?')
                        else:
                            val = str(val.encode())
                    else:
#                        val = str(val)
                        if val is None:
                            val = utils.cfg('nullString', '?')
                        else:
                            val = str(val)
                            
                    item = QTableWidgetItem(val)
                    
                    if cfg('highlightLOBs', True):
                        item.setBackground(QBrush(QColor('#f4f4f4')))
                    
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop);

                elif self.dbi.ifRAWType(cols[c][1]): #VARBINARY
                    val = val.hex()
                    
                    item = QTableWidgetItem(val)
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop);
                    
                elif self.dbi.ifVarcharType(cols[c][1]):
                    item = QTableWidgetItem(val)
                    
                    if '\n' in val:
                        item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop);
                    else:
                        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter);
                        
                    if cfg('experimental') and alert_str:
                        #and val == cfg('alertTriggerOn'): # this is old, not flexible style
                        #'{alert}'
                        
                        sound = None
                        
                        if val[:alert_len - 1] == alert_prefix:
                            # okay this looks like alert
                            if val == alert_str: 
                                # simple one
                                sound = ''
                            else:
                                # might be a customized one?
                                if val[-1:] == '}' and val[alert_len-1:alert_len] == ':':
                                    sound = val[alert_len:-1]
                                    
                        if sound is not None and not self.alerted:
                            self.alerted = True
                            
                            item.setBackground(QBrush(QColor('#FAC')))
                            self.alertSignal.emit(sound)

                
                elif self.dbi.ifTSType(cols[c][1]):
                    #val = val.isoformat(' ', timespec='milliseconds') 
                    val = utils.timestampToStr(val)
                    item = QTableWidgetItem(val)
                else:
                    val = str(val)
                        
                    item = QTableWidgetItem(val)
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter);
                    
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                
                
                self.setItem(r, c, item) # Y-Scale

            if r == adjRow - 1 and not refreshMode:
                self.resizeColumnsToContents();
                
                for i in range(len(row0)):
                    if self.columnWidth(i) >= 512:
                        self.setColumnWidth(i, 512)
                        
    def dblClick(self, i, j):
    
        if self.dbi.ifLOBType(self.cols[j][1]):
            if self.detached:
                self.log('warning: LOB resultset already detached', True)
                
                if self.dbi.ifBLOBType(self.cols[j][1]):
                    blob = str(self.rows[i][j].encode())
                else:
                    blob = str(self.rows[i][j])
            else:
                if self.rows[i][j] is not None:
                    try:
                        value = self.rows[i][j].read()
                    except Exception as e:
                        self.log('LOB read() error: %s' % str(e), True)
                        value = '<error1>'
                    
                    if self.dbi.ifBLOBType(self.cols[j][1]):
                        blob = str(value.decode("utf-8", errors="ignore"))
                    else:
                        blob = str(value)
                else:
                    blob = '<Null value>'

            if self.rows[i][j]:
                self.rows[i][j].seek(0) #rewind just in case
        else:
            blob = str(self.rows[i][j])

        lob = lobDialog.lobDialog(blob, self)
        
        lob.exec_()

        return False

    def wheelEvent (self, event):
    
        p = event.angleDelta()
        
        if p.y() < 0:
            mode = 1
        else:
            mode = -1
            
        modifiers = QApplication.keyboardModifiers()
        
        if modifiers == Qt.ShiftModifier:
            #x = 0 - self.pos().x() 
            x = self.horizontalScrollBar().value()
            
            step = self.horizontalScrollBar().singleStep() * 2 #pageStep()
            self.horizontalScrollBar().setValue(x + mode * step)
        else:
            super().wheelEvent(event)
        
class logArea(QPlainTextEdit):
    def __init__(self):
        super().__init__()

    def contextMenuEvent(self, event):
       
        cmenu = QMenu(self)

        '''
        print delete this
        t1 = cmenu.addAction('test html')
        t2 = cmenu.addAction('test text')
        '''
        reset = cmenu.addAction('Clear log')
        
        # cmenu.addSeparator()

        action = cmenu.exec_(self.mapToGlobal(event.pos()))

        if action == reset:
            # will it restore the color?
            self.clear()
            
        '''
        if action == t1:
            self.appendHtml('<font color = "red">%s</font>' % 'red text');
            
        if action == t2:
            self.appendPlainText('random text')
        '''
              
        
class sqlConsole(QWidget):

    nameChanged = pyqtSignal(['QString'])
    statusMessage = pyqtSignal(['QString', bool])
    selfRaise = pyqtSignal(object)
    alertSignal = pyqtSignal()

    def __init__(self, window, config, tabname = None):
    
        self.thread = QThread()             # main sql processing thread
        self.sqlWorker = sqlWorker(self)    # thread worker object (linked to console instance)
        self.sqlRunning = False             # thread is running flag
        
        self.wrkException = None            # thread exit exception
        self.indicator = None               # progress indicator widget, assigned OUTSIDE
        
        self.stQueue = []                   # list of statements to be executed
                                            # for the time being for one statement we do not build a queue, just directly run executeStatement
                                            
        self.t0 = None                      # set on statement start
        
        #todo:
        #self.t0 = None                      # set on queue start
        #self.t1 = None                      # set on statement start

        # one time thread init...
        self.sqlWorker.moveToThread(self.thread)
        self.sqlWorker.finished.connect(self.sqlFinished)
        #self.thread.finished.connect(self.sqlFinished)
        self.thread.started.connect(self.sqlWorker.executeStatement)
        
        #self.window = None # required for the timer
        
        self.conn = None
        self.config = None
        self.dbi = None
        self.timer = None           # keep alive timer
        self.rows = []
        
        self.splitterSizes = None
        
        self.fileName = None
        self.unsavedChanges = False
        
        self.backup = None
    
        self.results = [] #list of resultsets
        self.resultTabs = None # tabs widget
        
        self.noBackup = False
        
        self.connection_id = None
        
        self.runtimeTimer = None

        # self.psid = None # prepared statement_id for drop_statement -- moved to the resultset!
        
        self.timerAutorefresh = None
        
        self.defaultTimer = [60]
        
        super().__init__()
        self.initUI()
        
        
        if tabname is not None:
            self.tabname = tabname
        else:
            self.tabname = '!ERROR!'
            
            '''
            # old logic (before layouts), 2020-12-02
            
            if os.path.isfile(tabname+'.sqbkp'):
                #looks we had a backup?
                self.openFile(tabname+'.sqbkp')
                
                self.unsavedChanges = True
            '''

        self.cons.textChanged.connect(self.textChangedS)
        
        #self.cons.selectionChanged.connect(self.selectionChangedS)
        
        self.cons.updateRequest.connect(self.updateRequestS)
        
        self.cons.connectSignal.connect(self.connectDB)
        self.cons.disconnectSignal.connect(self.disconnectDB)
        self.cons.abortSignal.connect(self.cancelSession)
        self.cons.autocompleteSignal.connect(self.autocompleteHint)
        
        self.cons.explainSignal.connect(self.explainPlan)

        if config is None:
            return
        
        try: 
            dbimpl = dbi(config['dbi'])
            self.dbi = dbimpl.dbinterface
            
            self.sqlWorker.dbi = self.dbi

            log('starting console connection')
            self.conn = self.dbi.console_connection(config)
            self.config = config
            
            self.connection_id = self.dbi.get_connection_id(self.conn)
            log('connection open, id: %s' % self.connection_id)
            '''
            moved to DBI implementation
            
            rows = self.dbi.execute_query(self.conn, "select connection_id from m_connections where own = 'TRUE'", [])
            
            if len(rows):
                self.connection_id = rows[0][0]
                
                log('connection open, id: %s' % self.connection_id)
            '''
            
        except dbException as e:
            log('[!] failed!')
            raise e
            return
            
        # print(self.conn.session_id) it's not where clear how to get the connection_id
        # 

        if cfg('keepalive-cons'):
            keepalive = int(cfg('keepalive-cons'))
            self.enableKeepAlive(self, keepalive)

    '''
    def selectionChangedS(self):
        if self.cons.manualSelection:
            self.cons.clearManualSelection()
    '''
        
    def updateRequestS(self, rect):
        '''
            okay all this logic below is a workaround for #382
            
            somehow the brackets highlighting disappears by itself on any text change
            
            therefore we can just clear the list and set the flags (flags?) off
        '''
        
        if self.cons.lock:
            return
            
        if rect.width() > 11:
            # width == 10 means just cursor blinking with any (!) font size
            if self.cons.bracketsHighlighted:
                #log('updateRequestS FAKE clear highlighting', 5)
                #self.cons.clearHighlighting()

                self.cons.modifiedLayouts.clear()
                    
                self.cons.bracketsHighlighted = False
                self.cons.haveHighlighrs = False

        
    def textChangedS(self):
    
        if self.cons.lock:
            return
            
        if not cfg('noWordHighlighting'):
            if not self.cons.lock:
                if self.cons.haveHighlighrs:
                    #log('textChangedS, clear highlighting', 5)
                    self.cons.clearHighlighting()
        '''
        this does not work because textChanged is called on background change...
        this can be resolved by a lock, but...
        it is called after the change, so the issue persists
        
        if self.cons.manualSelection:

            self.cons.lock = True
            
            start = self.cons.manualSelectionPos[0]
            stop = self.cons.manualSelectionPos[1]
            
            cursor = QTextCursor(self.cons.document())
            cursor.joinPreviousEditBlock()

            format = cursor.charFormat()
            format.setBackground(QColor('white'))
        
            cursor.setPosition(start,QTextCursor.MoveAnchor)
            cursor.setPosition(stop,QTextCursor.KeepAnchor)
            
            cursor.setCharFormat(format)
            
            cursor.endEditBlock() 
            self.cons.manualSelection = False
            
            self.cons.lock = False
        '''
        
        '''
        # 2021-05-29
        print('textChangedS')
        if self.cons.bracketsHighlighted:
            log('textChangedS clear highlighting', 5)
            self.cons.clearHighlighting()
        '''

        if self.unsavedChanges == False: #and self.fileName is not None:
            if self.cons.toPlainText() == '':
                return
                
            self.unsavedChanges = True
                
            self.nameChanged.emit(self.tabname + ' *')

            '''
            sz = self.parentWidget().size()

            pos = self.mapToGlobal(self.pos())
            
            print(sz)
            print(pos.x(), pos.y())
            
            x = pos.x() + sz.width()/2
            y = pos.y() + sz.height()/2
            
            print(msgBox.size())
            
            #msgBox.move(x, y)
            '''
    
    def delayBackup(self):
        '''
            self.backup is a full path to a backup file
            
            if it's empty - it'll be generated as first step
            if the file already exists - the file will be owerritten
        '''
        
        if self.noBackup:
            return
    
        if self.unsavedChanges == False:
            return
    
        if not self.backup:
            if self.fileName is not None:
                path, file = os.path.split(self.fileName)
                
                file, ext = os.path.splitext(file)
            
                filename = file + '.sqbkp'
            else:
                filename = self.tabname + '.sqbkp'

            script = sys.argv[0]
            path, file = os.path.split(script)
            
            bkpFile = os.path.join(path, 'bkp', filename)
            bkpFile = os.path.abspath(bkpFile)
            
            self.backup = bkpFile
            
            bkpPath = os.path.join(path, 'bkp')
            
            if not os.path.isdir(bkpPath):
                os.mkdir(bkpPath)
            
        filename = self.backup
        
        fnsecure = utils.securePath(filename)
    
        try:
            with open(filename, 'w') as f:
            
                data = self.cons.toPlainText()

                f.write(data)
                f.close()

                log('%s backup saved' % fnsecure)
        
        except Exception as e:
            # so sad...
            log('[!] %s backup NOT saved' % fnsecure)
            log('[!]' + str(e))
            
    def keyPressEvent(self, event):
    
        #print('sql keypress')
   
        modifiers = QApplication.keyboardModifiers()

        if event.key() == Qt.Key_F12:
        
            backTo = self.spliter.sizes()

            if self.splitterSizes is None:
                #self.splitterSizes = [4000, 200, 100]
                self.splitterSizes = [200, 800, 100]
                
            self.spliter.setSizes(self.splitterSizes)
            
            self.splitterSizes = backTo

        #elif event.key() == Qt.Key_F11:
            #self.manualSelect(4, 8)
            
                
        super().keyPressEvent(event)

    def saveFile(self):
        if self.fileName is None:
            fname = QFileDialog.getSaveFileName(self, 'Save as...', '','*.sql')
            
            filename = fname[0]
            
            if filename == '':
                return
            
            self.fileName = filename

        else:
            filename = self.fileName

        try:
            with open(filename, 'w') as f:
            
                data = self.cons.toPlainText()

                f.write(data)
                f.close()

                basename = os.path.basename(filename)
                self.tabname = basename.split('.')[0]
                self.nameChanged.emit(self.tabname)
                
                self.unsavedChanges = False
                
                if self.backup is not None:
                    try:
                        log('delete backup: %s' % self.backup)
                        os.remove(self.backup)
                        self.backup = None
                    except:
                        log('delete backup faileld, passing')
                        # whatever...
                        pass

                self.log('File saved')
                
        except Exception as e:
            self.log ('Error: ' + str(e), True)
    
    def openFile(self, filename = None, backup = None):

        fnsecure = utils.securePath(filename, True)
        bkpsecure = utils.securePath(backup)
        
        log('openFile: %s, %s' % (fnsecure, bkpsecure))

        if filename is None and backup is None:
            fname = QFileDialog.getOpenFileName(self, 'Open file', '','*.sql')
            filename = fname[0]

        if filename == '':
            return

        self.fileName = filename
        self.backup = backup
        
        if filename is None:
            filename = backup

        if filename is not None and backup is not None:
            filename = backup           # we open backed up copy
            
        try:
            with open(filename, 'r') as f:
                data = f.read()
                f.close()
        except Exception as e:
            log ('Error: ' + str(e), 1, True)
            self.log ('Error: opening %s / %s' % (self.fileName, self.backup), True)
            self.log ('Error: ' + str(e), True)
            
            return
            
        basename = os.path.basename(filename)
        self.tabname = basename.split('.')[0]
        
        ext = basename.split('.')[1]
        
        self.cons.setPlainText(data)

        self.unsavedChanges = False

        if filename is None:
            self.unsavedChanges = True

        if filename is not None and backup is not None:
            self.unsavedChanges = True

        if self.unsavedChanges:
            self.tabname += ' *'
            
        '''
        if ext == 'sqbkp':
            pass
        else:
            self.fileName = filename
            self.backup = backup
            
        '''

        self.nameChanged.emit(self.tabname)
        
        self.setFocus()
    
    def close(self, cancelPossible = True):
    
        log('closing sql console...')
        log('indicator:' + self.indicator.status, 4)
        
        if self.unsavedChanges and cancelPossible is not None:
            answer = utils.yesNoDialog('Unsaved changes', 'There are unsaved changes in "%s" tab, do yo want to save?' % self.tabname, cancelPossible, parent=self)
            
            if answer is None: #cancel button
                return False

            if answer == False:
                try:
                    #log('delete backup: %s' % (str(self.tabname+'.sqbkp')))
                    #os.remove(self.tabname+'.sqbkp')
                    log('delete backup: %s' % (utils.securePath(self.backup)))
                    os.remove(self.backup)
                except:
                    log('delete backup 2 faileld, passing')
                    # whatever...
                    pass
            
            if answer == True:
                self.saveFile()
                
        log('closing results...', 5)
        
        self.closeResults()

        try: 
            self.stopKeepAlive()
            
            if self.conn is not None:
                log('close the connection...', 5)
                self.indicator.status = 'sync'
                self.indicator.repaint()
                self.dbi.close_connection(self.conn)
                
        except dbException as e:
            log('close() db exception: '+ str(e))
            super().close()
            return True
        except Exception as e:
            log('close() exception: '+ str(e))
            super().close()
            return True
        
        log('super().close()...', 5)

        super().close()
        
        log('super().close() done', 5)
        
        return True
            
    def explainPlan(self, st):
        sqls = []
        
        st_name = 'rf'
        
        sqls.append("explain plan set statement_name = '%s' for %s" % (st_name, st))
        sqls.append("select * from explain_plan_table where statement_name = '%s'" % (st_name))
        sqls.append("delete from sys.explain_plan_table where statement_name = '%s'" % (st_name))
            
        self.stQueue = sqls.copy()
        self.launchStatementQueue()
        
    def autocompleteHint(self):
            
            if self.conn is None:
                self.log('The console is not connected to the DB', True)
                return
                
            if self.sqlRunning:
                self.log('Autocomplete is blocked while the sql is still running...')
                return
            
            cursor = self.cons.textCursor()
            pos = cursor.position()
            linePos = cursor.positionInBlock();
            lineFrom = self.cons.document().findBlock(pos)
            
            line = lineFrom.text()

            j = i = 0
            # check for the space
            for i in range(linePos-1, 0, -1):
                if line[i] == ' ':
                    break
            else:
                #start of the line reached
                i = -1
                
            # check for the dot
            for j in range(linePos-1, i+1, -1):
                if line[j] == '.':
                    break
            else:
                j = -1
                
            if j > i:
                schema = line[i+1:j]
                
                if schema.islower() and schema[0] != '"' and schema[-1] != '"':
                    schema = schema.upper()
                    
                term = line[j+1:linePos].lower() + '%'
                
            else:
                schema = 'PUBLIC'
                term = line[i+1:linePos].lower() + '%'
                    
            if linePos - i <= 2:
                #string is to short for autocomplete search
                return
                 
            if j == -1:
                stPos = lineFrom.position() + i + 1
            else:
                stPos = lineFrom.position() + j + 1

            endPos = lineFrom.position() + linePos

            log('get autocomplete input (%s)... ' % (term), 3)
            
            if j != -1:
                self.statusMessage.emit('Autocomplete request: %s.%s...' % (schema, term), False)
            else:
                self.statusMessage.emit('Autocomplete request: %s...' % (term), False)
            
            self.indicator.status = 'sync'
            self.indicator.repaint()
            
            t0 = time.time()
            

            try:
                if schema == 'PUBLIC':
                    rows = self.dbi.execute_query(self.conn, 'select distinct schema_name object, \'SCHEMA\' type from schemas where lower(schema_name) like ? union select distinct object_name object, object_type type from objects where schema_name = ? and lower(object_name) like ? order by 1', [term, schema, term])
                else:
                    rows = self.dbi.execute_query(self.conn, 'select distinct object_name object, object_type type from objects where schema_name = ? and lower(object_name) like ? order by 1', [schema, term])
                    
            except dbException as e:
                err = str(e)
                
                self.statusMessage.emit('db error: %s' % err, False)

                self.indicator.status = 'error'
                self.indicator.repaint()
                return

            t1 = time.time()

            self.indicator.status = 'idle'
            self.indicator.repaint()
            
            n = len(rows)
            
            log('ok, %i rows: %s ms' % (n, str(round(t1-t0, 3))), 3, True)
            
            if n == 0:
                self.statusMessage.emit('No suggestions found', False)
                return
                
            self.statusMessage.emit('', False)

            if n > 1:
                lines = []
                for r in rows:
                    lines.append('%s (%s)' % (r[0], r[1]))
                    
                line, ok = autocompleteDialog.getLine(self, lines)
            else:
                #single suggestion, let's fake "OK":
                ok = True
                line = rows[0][0]
                
            line = line.split(' (')[0]

            if ok:
                cursor.clearSelection()
                cursor.setPosition(stPos, QTextCursor.MoveAnchor)
                cursor.setPosition(endPos, QTextCursor.KeepAnchor)
            
                cursor.insertText(normalize_header(line))
                
    def cancelSession(self):
        self.log("\nNOTE: the SQL needs to be executed manually from the other SQL console:\nalter system cancel session '%s'" % (str(self.connection_id)))
        
    def disconnectDB(self):

        try: 
        
            self.stopResults()
        
            if self.conn is not None:
                self.dbi.close_connection(self.conn)
                
                self.stopKeepAlive()
                
                self.conn = None
                self.connection_id = None
                self.log('\nDisconnected')
                
        except dbException as e:
            log('close() db exception: '+ str(e))
            self.log('close() db exception: '+ str(e), True)
            
            self.stopKeepAlive()
            self.conn = None # ?
            self.connection_id = None
            return
        except Exception as e:
            log('close() exception: '+ str(e))
            self.log('close() exception: '+ str(e), True)
            
            self.stopKeepAlive()
            self.conn = None # ?
            self.connection_id = None
            return
        
    def connectDB(self):
        try: 
            log('connectDB, indicator sync', 4)
            self.indicator.status = 'sync'
            self.indicator.repaint()

            if self.conn is not None:
                self.dbi.close_connection(self.conn)
                
                self.stopKeepAlive()
                self.conn = None
                self.connection_id = None
                self.log('\nDisconnected')

            self.sqlRunning = False
            self.stQueue.clear()

            if self.dbi == None:
                dbimpl = dbi(self.config['dbi'])
                self.dbi = dbimpl.dbinterface
                
                self.sqlWorker.dbi = self.dbi

                
            self.conn = self.dbi.console_connection(self.config)                

            rows = self.dbi.execute_query(self.conn, "select connection_id  from m_connections where own = 'TRUE'", [])
            
            if len(rows):
                self.connection_id = rows[0][0]
                
                log('connection open, id: %s' % self.connection_id)

            if cfg('keepalive-cons') and self.timer is None:
                keepalive = int(cfg('keepalive-cons'))
                self.enableKeepAlive(self, keepalive)
            
        except dbException as e:
            log('close() db exception: '+ str(e))
            self.log('close() db exception: '+ str(e), True)
        except Exception as e:
            log('close() exception: '+ str(e))
            self.log('close() exception: '+ str(e), True)


        log('connectDB, indicator idle?', 4)
        self.indicator.status = 'idle'
        self.indicator.repaint()
        
        self.log('Connected.')

    
    def reconnect(self):
            
        try:
        
            conn = self.dbi.console_connection(self.config)

            rows = self.dbi.execute_query(conn, "select connection_id  from m_connections where own = 'TRUE'", [])
            
            if len(rows):
                self.connection_id = rows[0][0]
                
                log('connection open, id: %s' % self.connection_id)

        except Exception as e:
            raise e
        
        if conn is None:
            self.log('[i] Failed to reconnect, dont know what to do next')
            raise Exception('Failed to reconnect, dont know what to do next...')
        else:
            self.log('re-connected')
            self.conn = conn

    def autorefreshRun(self):
        log('autorefresh...', 4)
        
        self.timerAutorefresh.stop()

        self.refresh(0)
        
        self.timerAutorefresh.start()
    
    def setupAutorefresh(self, interval, suppressLog = False):
    
        if interval == 0:
            log('Stopping the autorefresh: %s' % self.tabname.rstrip(' *'))
            
            if suppressLog == False:
                self.log('--> Stopping the autorefresh')

            if self.indicator.status in ('autorefresh', 'alert'):
                self.indicator.status = 'idle'
                self.indicator.bkpStatus = 'idle'
                self.indicator.repaint()
            
            if self.timerAutorefresh is not None:
                self.timerAutorefresh.stop()
                self.timerAutorefresh = None
            
            return
         
        
        if self.resultTabs.count() != 1:
            self.log('Autorefresh only possible for single resultset output.', True)
            return
        
        self.indicator.status = 'autorefresh'
        self.indicator.repaint()

        self.log('\n--> Scheduling autorefresh, logging will be supressed. Autorefresh will stop on manual query execution or context menu -> stop autorefresh')
        log('Scheduling autorefresh %i (%s)' % (interval, self.tabname.rstrip(' *')))
            
        if self.timerAutorefresh is None:
            self.timerAutorefresh = QTimer(self)
            self.timerAutorefresh.timeout.connect(self.autorefreshRun)
            self.timerAutorefresh.start(1000 * interval)
        else:
            log('[W] autorefresh timer is already running, ignoring the new one...', 2)
            self.log('Autorefresh is already running? Ignoring the new one...', True)
            
    def alertProcessing(self, fileName, manual = False):
    
        #print('alertProcessing')
    
        if fileName == '' or fileName is None:
            fileName = cfg('alertSound', 'default')
        else:
            pass
            
        #print('filename:', fileName)
            
        if fileName.find('.') == -1:
            fileName += '.wav'
            
        #print('filename:', fileName)
            
        if '/' in fileName or '\\' in fileName:
            #must be a path to some file...
            pass
        else:
            #try open normal file first
            fileName = 'snd\\' + fileName
            if os.path.isfile(fileName):
                log('seems there is a file in the rybafish snd folder: %s' % (fileName), 4)
            else:
                #okay, take it from the build then...
                fileName = resourcePath(fileName)
                
        #print('filename:', fileName)

        #log('Sound file name: %s' % fileName, 4)
        
        if not os.path.isfile(fileName):
            log('warning: sound file does not exist: %s' % fileName, 2)
            return
    
        if self.timerAutorefresh and not manual:
            log('console [%s], alert...' % self.tabname.rstrip(' *'), 3)
            ts = datetime.datetime.now().strftime('%H:%M:%S') + ' '
            self.logArea.appendHtml(ts + '<font color = "#c6c">Alert triggered</font>.');
            
            
        vol = cfg('alertVolume', 80)
        
        try:
            vol = int(vol)
        except ValueError:
            vol = 80
            
        vol /= 100
        
        if not manual:
            self.indicator.status = 'alert'

        self.sound = QSoundEffect()
        soundFile = QUrl.fromLocalFile(fileName)
        self.sound.setSource(soundFile)
        self.sound.setVolume(vol)
            
        self.sound.play()
        
        if cfg('alertAutoPopup', True):
            if not self.isActiveWindow():
                self.selfRaise.emit(self)
            
            self.alertSignal.emit()
    
    def newResult(self, conn, st):
        
        result = resultSet(conn)
        result.dbi = self.dbi
        
        result.statement = st
        
        result.defaultTimer = self.defaultTimer
        
        result._connection = conn
        
        result.log = self.log
        
        result.insertText.connect(self.cons.insertTextS)
        result.executeSQL.connect(self.surprizeSQL)
        result.alertSignal.connect(self.alertProcessing)
        result.triggerAutorefresh.connect(self.setupAutorefresh)
        
        if len(self.results) > 0:
            rName = 'Results ' + str(len(self.results)+1)
        else:
            rName = 'Results'
        
        self.results.append(result)
        self.resultTabs.addTab(result, rName)
        
        #self.resultTabs.setCurrentIndex(len(self.results) - 1)
        self.resultTabs.setCurrentIndex(self.resultTabs.count() - 1)
        
        return result
        
    def stopResults(self):
    
        log('Stopping all the results, %s...' % (self.tabname.rstrip(' *')), 4)
        
        for result in self.results:

            # stop autorefresh if any
            if self.timerAutorefresh is not None:
                log('Stopping autorefresh as it was enabled')
                result.log('--> Stopping the autorefresh...', True)
                self.timerAutorefresh.stop()
                self.timerAutorefresh = None

            if result.LOBs and not result.detached:
                if result.detachTimer is not None:
                    log('Stopping the detach timer as we are disconnecting...')
                    result.detachTimer.stop()
                    result.detachTimer = None
                    
                result.detach()

            if self.conn is not None:
                try:
                    self.indicator.status = 'sync'
                    self.indicator.repaint()
                    self.dbi.drop_statement(self.conn, result.psid)
                    self.indicator.status = 'idle'
                    self.indicator.repaint()
                except Exception as e:
                    log('[E] exeption during console close/drop statement: %s' % str(e), 2)
                    self.indicator.status = 'error'
                    self.indicator.repaint()
    
    def closeResults(self):
        '''
            closes all results tabs, detaches resultsets if any LOBs
        '''
        
        self.stopResults()
        
        for i in range(len(self.results) - 1, -1, -1):
            
            self.resultTabs.removeTab(i)

            result = self.results[i]
            
            
            #model = result.model()
            #model.removeRows(0, 10000)

            result.clear()

            del(result.cols)
            del(result.rows)
            
            #same code in refresh()
            
            #result.destroy()
            #result.deleteLater()
            
            del(result)
            del self.results[i]
            
        self.results.clear()
            
    def enableKeepAlive(self, window, keepalive):
    
        if not self.dbi.options.get('keepalive'):
            log('Keep-alives not supported by this DBI')
            return
    
        log('Setting up console keep-alive requests: %i seconds' % (keepalive))
        self.timerkeepalive = keepalive
        self.timer = QTimer(window)
        self.timer.timeout.connect(self.keepAlive)
        self.timer.start(1000 * keepalive)
        
    def stopKeepAlive(self):
    
        if self.timer is not None:
            self.timer.stop()
            self.timer = None
            
            cname = self.tabname.rstrip(' *')
            log('keep-alives stopped (%s)' % cname)
    
    def renewKeepAlive(self):
        if self.timer is not None:
            self.timer.stop()
            self.timer.start(1000 * self.timerkeepalive)

    def keepAlive(self):
    
        if self.conn is None:
            return
            
        if self.sqlRunning:
            log('SQL still running, skip keep-alive') # #362
            self.timer.stop()
            self.timer.start(1000 * self.timerkeepalive)
            return

        try:
            cname = self.tabname.rstrip(' *')
            log('console keep-alive (%s)... ' % (cname), 3, False, True)
            
            log('keepAlive, indicator sync', 4)
            self.indicator.status = 'sync'
            self.indicator.repaint()
            
            t0 = time.time()
            self.dbi.execute_query(self.conn, 'select * from dummy', [])
            t1 = time.time()

            #self.indicator.status = 'idle'
            
            if self.timerAutorefresh:
                self.indicator.status = 'autorefresh'
            else:
                self.indicator.status = 'idle'
            
            self.indicator.repaint()
            
            log('ok: %s ms' % (str(round(t1-t0, 3))), 3, True)
        except dbException as e:
            log('Trigger autoreconnect...')
            self.log('Connection lost, trigger autoreconnect...')
            try:
                conn = self.dbi.console_connection(self.config)
                if conn is not None:
                    self.conn = conn
                    log('Connection restored automatically')
                    self.indicator.status = 'idle'

                    rows = self.dbi.execute_query(self.conn, "select connection_id  from m_connections where own = 'TRUE'", [])
                    
                    if len(rows):
                        self.connection_id = rows[0][0]
                        
                        log('connection open, id: %s' % self.connection_id)
                        
                else:
                    log('Some connection issue, give up')
                    self.log('Some connection issue, give up', 1, True)
                    self.stopKeepAlive()
                    self.conn = None
                    self.connection_id = None
            except:
                log('Connection lost, give up')

                self.indicator.status = 'disconnected'
                self.indicator.repaint()
                self.log('Connection lost, give up', True)
                # print disable the timer?
                self.stopKeepAlive()
                self.conn = None
                self.connection_id = None
                
                if self.timerAutorefresh is not None:
                    self.log('--> Stopping the autorefresh on keep-alive fail...', True)
                    self.setupAutorefresh(0, suppressLog=True)
                
                    if cfg('alertDisconnected'):
                        self.alertProcessing(cfg('alertDisconnected'), True)
                
        except Exception as e:
            log('[!] unexpected exception, disable the connection')
            log('[!] %s' % str(e))
            self.log('[!] unexpected exception, disable the connection', True)

            self.stopKeepAlive()

            self.conn = None
            self.connection_id = None
            self.indicator.status = 'disconnected'
            self.indicator.repaint()
            
                        
    def log(self, text, error = False):
        if error:
            self.logArea.appendHtml('<font color = "red">%s</font>' % text);
        else:
            self.logArea.appendPlainText(text)
            
        self.logArea.verticalScrollBar().setValue(self.logArea.verticalScrollBar().maximum())
        
    def dummyResultTable2(self, n):
        row0 = []
    
        cols = [
            ['Name',11],
            ['Integer',3],
            ['Decimal',5],
            ['Str',11]
        ]

        
        rows = []
        for i in range(n):
            row = ['name ' + str(i), i, i/312, 'String String String String String String String String']
            rows.append(row)
        
        result = self.newResult(self.conn, 'select * from dummy')
        
        result.rows = rows
        result.cols = cols
        
        result.populate()

    
    def dummyResultTable(self):
    
        row0 = []
    
        cols = [
            ['Name', 11],
            ['STATEMENT_ID', 26],
            ['7CONNECTION_ID', 3],
            ['/USER_NAME', 5],
            ['dontknow', 61]     # 16 - old timestamp (millisec), 61 - longdate
        ]

        ''''
        ['LOB String',26],
        ['Integer',3],
        ['Decimal',5],
        ['Timestamp',16]
        '''
        
        dt1 = datetime.datetime.strptime('2001-01-10 11:23:07.123456', '%Y-%m-%d %H:%M:%S.%f')
        dt2 = datetime.datetime.strptime('2001-01-10 11:23:07.12300', '%Y-%m-%d %H:%M:%S.%f')
        dt3 = datetime.datetime.strptime('2001-01-10 11:23:07', '%Y-%m-%d %H:%M:%S')
        
        rows = [
                ['name 1','select * from dummy fake blob 1', 1024, 1/12500, dt1],
                ['name 2','select * from \r\n dummy blob 2', 22254, 2/3, dt2],
                ['name 3','select 1/16 from dummy blob 3', 654654, 1/16, dt3],
                ['name 4','''select 10000 from dummy blob 3 
                
                and too many 
                
                \n
                
                characters''', 654654, 10000, datetime.datetime.now()]
            ]
        
        result = self.newResult(self.conn, '<None>')
        result._parent = self
        
        result.rows = rows
        result.cols = cols
        
        result.populate()
    
    def refresh(self, idx):
        '''
            executed the attached statement without full table cleanup
            and header processing
        '''
        
        result = self.results[idx]
        
        #result.clear()

        # same code in close_results
        if result.LOBs and not result.detached:
            if result.detachTimer is not None:
                log('stopping the detach timer in advance...')
                result.detachTimer.stop()
                result.detachTimer = None
                
            result.detach()
            
        result.alerted = False

        self.executeStatement(result.statement, result, True)
        
    def executeSelection(self, mode):
    
        if self.config is None:
            self.log('No connection, connect RybaFish to the DB first.')
            return
            
        if self.conn is None:
            self.log('The console is disconnected...')
            
            #answer = utils.yesNoDialog('Connect to db', 'The console is not connected to the DB. Connect as "%s@%s:%s"?' % (self.config['user'], self.config['host'], str(self.config['port'])))
            answer = utils.yesNoDialog('Connect to db', 'The console is not connected to the DB. Connect now?', parent = self)
            
            if not answer:
                return 
                
            self.connectDB()
    
        if self.timerAutorefresh:
            self.setupAutorefresh(0)
            
        if mode == 'normal':
            self.executeSelectionParse()
        elif mode == 'no parsing':
            self.executeSelectionNP(False)
        elif mode == 'leave results':
            self.executeSelectionNP(True)
            
    def surprizeSQL(self, key, value):
        
        sqls = []
        
        for st in customSQLs.sqls[key]:
            sqls.append(st.replace('$value', value))
            
        if len(sqls) == 0:
            self.log('No sql defined', 2)
        
        if len(sqls) == 1:
            self.executeSelectionNP(True, sqls[0])
        else:
            self.stQueue = sqls.copy()
            self.launchStatementQueue()
        
    def executeSelectionNP(self, leaveResults, sql = None):
    
        cursor = self.cons.textCursor()
    
        if cursor.selection().isEmpty() and sql is None:
            self.log('You need to select statement manually for this option')
            return

        if leaveResults == False:
            self.closeResults()

        if sql == None:
            statement = cursor.selection().toPlainText()
        else:
            statement = sql
        
        result = self.newResult(self.conn, statement)
        self.executeStatement(statement, result)
        
    def manualSelect(self, start, stop, color):
        
        #print('manualSelect %i - %i (%s)' % (start, stop, color))
        
        updateMode = False
        
        if self.cons.manualSelection:
            # make sure we add additional formattin INSIDE existing one
            
            updateMode = True
            
            if start < self.cons.manualSelectionPos[0] or stop > self.cons.manualSelectionPos[1]:
                log('[W] Attemt to change formatting (%i:%i) outside already existing one (%i:%i)!' % \
                    (start, stop, self.cons.manualSelectionPos[0], self.cons.manualSelectionPos[1]), 2)
            
                return
            

        '''
        # modern (incorrect) style from here:

        cursor = QTextCursor(self.cons.document())

        cursor.joinPreviousEditBlock()

        format = cursor.charFormat()
        format.setBackground(QColor('#ADF'))

        cursor.setPosition(start,QTextCursor.MoveAnchor)
        cursor.setPosition(stop,QTextCursor.KeepAnchor)
        
        cursor.setCharFormat(format)
        
        cursor.endEditBlock() 
        
        #to here
        '''
        
       # old (good) style from here:
        
        '''
        not sure why it was so complex, 
        simplified during #478
        
        and reverted because issues with removing the highlighted background ...
        
        low level approach is better as it does not go into the undo/redo history, #482, #485
        but in this case also the exception highlighting must be low-level
        '''
        
        
        charFmt = QTextCharFormat()
        charFmt.setBackground(QColor(color))

        block = tbStart = self.cons.document().findBlock(start)
        tbEnd = self.cons.document().findBlock(stop)
        
        fromTB = block.blockNumber()
        toTB = tbEnd.blockNumber()
        
        #print('from tb, to:', fromTB, toTB)
        
        curTB = fromTB

        while curTB <= toTB and block.isValid():
        
            #print('block, pos:', curTB, block.position())
            
            if block == tbStart:
                delta = start - block.position()
            else:
                delta = 0

            if block == tbEnd:
                lenght = stop - block.position() - delta
            else:
                lenght = block.length()
            
            lo = block.layout()
            
            r = lo.FormatRange()
            
            r.start = delta
            r.length = lenght
            
            r.format = charFmt
            
            af = lo.additionalFormats()
            
            if not updateMode:
                self.cons.manualStylesRB.append((lo, af))

            lo.setAdditionalFormats(af + [r])
            
            block = block.next()
            curTB = block.blockNumber()

        #cursor.endEditBlock()

        if self.cons.manualSelection == False:
            #only enable it if not set yet
            #we also never narrow down the manualSelectionPos start/stop (it is checked in procedure start)
            self.cons.manualSelection = True
            self.cons.manualSelectionPos  = [start, stop]

        #print('manualSelectionPos[] = ', self.cons.manualSelectionPos)
        
        #print('manualSelectionPos', self.cons.manualSelectionPos)
            
        self.cons.viewport().repaint()
            
    def executeSelectionParse(self):
    
        txt = ''
        statements = []
        F9 = True
        
        self.delayBackup()
        
        if self.sqlRunning:
            if len(self.stQueue) > 0:
                self.log('SQL still running, %i left in queue' % (len(self.stQueue)), True)
            else:
                self.log('SQL still running', True)
            
            return
        
        def isItCreate(s):
            '''
                if in create procedure now?
            '''
            
            if re.match('^\s*create\s+procedure\W.*', s, re.IGNORECASE) or \
                re.match('^\s*create\s+function\W.*', s, re.IGNORECASE) or \
                re.match('^\s*do\s+begin\W.*', s, re.IGNORECASE):
                return True
            else:
                return False
                
        def isItEnd(s):
            '''
                it shall ignore whitspaces
                and at this point ';' already 
                checked outside, so just \bend\b regexp check


                The logic goes like this
                
                if there is a selection:
                    split and execute stuff inside
                else:
                    f9 mode - detect and execute one line

            '''
            #if s[-3:] == 'end':
            if re.match('.*\W*end\s*$', s, re.IGNORECASE):
                return True
            else:
                return False
        
        def selectSingle(start, stop):
            #print('selectSingle', start, stop)
            
            self.manualSelect(start, stop, '#adf')
            
            #cursor = QTextCursor(self.cons.document())

            #cursor.setPosition(start,QTextCursor.MoveAnchor)
            #cursor.setPosition(stop,QTextCursor.KeepAnchor)
            
            #self.cons.setTextCursor(cursor)
        
        def statementDetected(start, stop):

            str = txt[start:stop]
            
            if str == '': 
                #typically only when start = 0, stop = 1
                if not (start == 0 and stop <= 1):
                    log('[w] unusual empty string matched')
                return
                
            statements.append(str)
        
        cursor = self.cons.textCursor()

        selectionMode = False
        
        txt = self.cons.toPlainText()
        length = len(txt)

        cursorPos = None

        if not cursor.selection().isEmpty():
            F9 = False
            selectionMode = True
            scanFrom = cursor.selectionStart()
            scanTo = cursor.selectionEnd()
        else:
            F9 = True
            scanFrom = 0
            scanTo = length
            if F9:
                #detect and execute just one statement
                cursorPos = self.cons.textCursor().position()
            else:
                cursorPos = None
                
        #print('ran from: ', cursorPos)
        
        str = ''
        
        i = 0
        start = stop = 0
        
        leadingComment = False
        insideString = False
        insideProc = False
        
        # main per character loop:

        # print('from to: ', scanFrom, scanTo)
        
        # startDelta = 0
        # clearDelta = False
        
        ### print('from, to', scanFrom, scanTo)
        
        for i in range(scanFrom, scanTo):
            c = txt[i]
            
            '''
            if clearDelta:
                startDelta = 0
                clearDelta = False
            '''

            #print('['+c+']')
            if not insideString and c == ';':
                #print(i)
                if not insideProc:
                    ### print("str = '' #1")
                    str = ''
                    
                    #if stop < start: # this is to resolve #486
                    if stop < start or (start == 0 and stop == 0): # this is to resolve # 486, 2 
                        stop = i
                    # clearDelta = True
                    continue
                else:
                    if isItEnd(str[-10:]):
                        insideProc = False
                        ### print("str = '' #2")
                        str = ''
                        stop = i
                        # clearDelta = True
                        continue
            
            if str == '':
                #happens when semicolon detected.
                # print('str = \'\'', 'startDelta: ', startDelta)
                if c in (' ', '\n', '\t') and not leadingComment:
                    # warning: insideString logic skipped here (as it is defined below this line
                    # skip leading whitespaces
                    # print(start, stop, cursorPos, i)
                    # startDelta += 1
                    continue
                elif not leadingComment and c == '-' and i < scanTo and txt[i] == '-':
                    leadingComment = True
                elif leadingComment:
                    ### print(c, i, start, stop)
                    if c == '\n':
                        leadingComment = False
                    else:
                        continue
                else:
                    #if F9 and (start <= cursorPos < stop):
                    #reeeeeallly not sure!
                    if F9 and (start <= cursorPos <= stop) and (start < stop):
                        #print('start <= cursorPos <= stop:', start, cursorPos, stop)
                        #print('warning! selectSingle used to be here, but removed 05.02.2021')
                        #selectSingle(start, stop)
                        ### print('stop detected')
                        break
                    else:
                        if not F9:
                            statementDetected(start, stop)
                        
                    start = i
                    str = str + c
                    ### print(i, 'sTr:', str, start, stop)
            else:
                str = str + c
                ### print(i, 'str:', str, start, stop)

            if not insideString and c == '\'':
                insideString = True
                continue
                
            if insideString and c == '\'':
                insideString = False
                continue
                
            if not insideProc and isItCreate(str[:64]):
                insideProc = True
                
        ### print('[just stop]')


        '''
        print('F9?', F9)
        print('cursorPos', cursorPos)
        # print('startDelta', startDelta)
        print('scanFrom, scanTo', scanFrom, scanTo)
        print('start, stop', start, stop)
        print('str:', str)
        '''
        
        if stop == 0:
            # no semicolon met
            stop = scanTo
        
        #if F9 and (start <= cursorPos < stop):
        #print so not sure abous this change
        if F9 and (start <= cursorPos <= stop) and (start < stop):
            selectSingle(start, stop)
        elif F9 and (start > stop and start <= cursorPos): # no semicolon in the end
            selectSingle(start, scanTo)
        else:
            if not F9:
                statementDetected(start, stop)
            
        self.closeResults()
        
        #if F9 and (start <= cursorPos < stop):
        #print so not sure abous this change
        if F9 and (start <= cursorPos <= stop):
            #print('-> [%s] ' % txt[start:stop])
            
            st = txt[start:stop]
            result = self.newResult(self.conn, st)
            self.executeStatement(st, result)
            
        elif F9 and (start > stop and start <= cursorPos): # no semicolon in the end
            #print('-> [%s] ' % txt[start:scanTo])
            st = txt[start:scanTo]

            result = self.newResult(self.conn, st)
            self.executeStatement(st, result)

        else:
            '''
            for st in statements:
                #print('--> [%s]' % st)
                
                result = self.newResult(self.conn, st)
                self.executeStatement(st, result)
                
                #self.update()
                self.repaint()
            '''
            
            if len(statements) > 1:
                self.stQueue = statements.copy()
                self.launchStatementQueue()
            elif len(statements) > 0:
                result = self.newResult(self.conn, statements[0])
                self.executeStatement(statements[0], result)
            else:
                #empty string selected
                pass
                
        #move the cursor to initial position
        #cursor = console.cons.textCursor()
        #print('exiting, move to', cursorPos)
        #cursor.setPosition(cursorPos, cursor.MoveAnchor)
        #self.cons.setTextCursor(cursor)

        return
        
    def launchStatementQueue(self):
        '''
            triggers statements queue execution using new cool QThreads
            list of statements is in self.statements
            
            each execution pops the statement from the list right after thread start!
        '''
        
        #print('0 launchStatementQueue')
        if self.stQueue:
            st = self.stQueue.pop(0)
            result = self.newResult(self.conn, st)
            self.executeStatement(st, result)
    
    def connectionLost(self, err_str = ''):
        '''
            very synchronous call, it holds controll until connection status resolved
        '''
        disconnectAlert = None
        
        log('Connection Lost...')

        if self.timerAutorefresh is not None and cfg('alertDisconnected'):      # Need to do this before stopResults as it resets timerAutorefresh
            log('disconnectAlert = True', 5)
            disconnectAlert = True
        else:
            log('disconnectAlert -- None', 5)
        
        self.stopResults()
        
        msgBox = QMessageBox(self)
        msgBox.setWindowTitle('Connection lost')
        msgBox.setText('Connection failed, reconnect?')
        msgBox.setStandardButtons(QMessageBox.Yes| QMessageBox.No)
        msgBox.setDefaultButton(QMessageBox.Yes)
        iconPath = resourcePath('ico\\favicon.png')
        msgBox.setWindowIcon(QIcon(iconPath))
        msgBox.setIcon(QMessageBox.Warning)

        if disconnectAlert:
            log('play the disconnect sound...', 4)
            self.alertProcessing(cfg('alertDisconnected'), True)
            
        reply = None
        
        while reply != QMessageBox.No and self.conn is None:
            log('connectionLost, indicator sync')
            self.indicator.status = 'sync'
            self.indicator.repaint()
            
            reply = msgBox.exec_()
            if reply == QMessageBox.Yes:
                try:
                    self.log('Reconnecting to %s:%s...' % (self.config['host'], str(self.config['port'])))
                    self.reconnect()
                    #self.log('Connection restored <<')
                    self.logArea.appendHtml('Connection restored. <font color = "blue">You need to restart SQL manually</font>.');
                    
                    self.indicator.status = 'idle'
                    self.indicator.repaint()
                    
                    if cfg('keepalive-cons') and self.timer is None:
                        keepalive = int(cfg('keepalive-cons'))
                        self.enableKeepAlive(self, keepalive)
                    else:
                        self.renewKeepAlive() 
                        
                except Exception as e:
                    self.indicator.status = 'disconnected'
                    self.indicator.repaint()
                    
                    log('Reconnect failed: %s' % e)
                    self.log('Reconnect failed: %s' % str(e))

        if reply == QMessageBox.Yes:
            return True
        else:
            self.indicator.status = 'disconnected'
            return False
            
    def sqlFinished(self):
        '''
            post-process the sql reaults
            also handle exceptions
        '''
        #print('2 --> sql finished')

        self.thread.quit()
        self.sqlRunning = False
        
        self.indicator.status = 'render'
        self.indicator.repaint()
        
        log('(%s) psid to save --> %s' % (self.tabname.rstrip(' *'), utils.hextostr(self.sqlWorker.psid)), 4)
        
        if self.wrkException is not None:
            self.log(self.wrkException, True)
            
            #self.thread.quit()
            #self.sqlRunning = False

            if self.conn is not None:
                self.indicator.status = 'error'
                
                if cfg('blockLineNumbers', True) and self.cons.manualSelection:
                    pos = self.cons.manualSelectionPos
                    doc = self.cons.document()
                    
                    #print('selection: ', pos)
                    startBlk = doc.findBlock(pos[0])
                    stopBlk = doc.findBlock(pos[1])
                    
                    if startBlk and stopBlk:
                        fromLine = startBlk.blockNumber() + 1
                        toLine = stopBlk.blockNumber() + 1
                    
                        #print('selection lines:', fromLine, toLine)
                        
                        self.cons.lineNumbers.fromLine = fromLine
                        self.cons.lineNumbers.toLine = toLine
                        
                        self.cons.lineNumbers.repaint()
                        
                        # exception text example: sql syntax error: incorrect syntax near "...": line 2 col 4 (at pos 13)
                        # at pos NNN - absolute number
                        
                        linePos = self.wrkException.find(': line ')
                        posPos = self.wrkException.find(' pos ')
                        
                        if linePos > 0 or posPos > 0:
                        
                            linePos += 7
                            posPos += 5
                            
                            linePosEnd = self.wrkException.find(' ', linePos)
                            posPosEnd = self.wrkException.find(')', posPos)
                            
                            errLine = None
                            errPos = None
                            
                            if linePosEnd > 0:
                                errLine = self.wrkException[linePos:linePosEnd]
                                
                                try:
                                    errLine = int(errLine)
                                except ValueError:
                                    log('[w] ValueError exception: [%s]' % (errLine))
                                    errLine = None
                                    
                            if linePosEnd > 0:
                                errPos = self.wrkException[posPos:posPosEnd]
                                try:
                                    errPos = int(errPos)
                                except ValueError:
                                    log('[w] ValueError exception: [%s]' % (errPos))
                                    errPos = None
                                    

                            if errLine or errPos:
                            
                                cursor = QTextCursor(doc)
                                #cursor.joinPreviousEditBlock()

                                if errLine and toLine > fromLine:
                                    doc = self.cons.document()
                                    
                                    blk = doc.findBlockByNumber(fromLine - 1 + errLine - 1)
                                    
                                    start = blk.position()
                                    stop = start + blk.length() - 1
                                    
                                    if stop > pos[1]:
                                        stop = pos[1]
                                    
                                    #print('error highlight:', start, stop)

                                    '''
                                    format = cursor.charFormat()
                                    format.setBackground(QColor('#FCC'))
                                
                                    cursor.setPosition(start,QTextCursor.MoveAnchor)
                                    cursor.setPosition(stop,QTextCursor.KeepAnchor)
                                    
                                    cursor.setCharFormat(format)
                                    '''
                                    
                                    self.manualSelect(start, stop, '#fcc')
                                    
                                if errPos:
                                    
                                    start = self.cons.manualSelectionPos[0] + errPos - 1
                                    
                                    '''
                                    format = cursor.charFormat()
                                    format.setBackground(QColor('#F66'))
                                
                                    cursor.setPosition(start,QTextCursor.MoveAnchor)
                                    cursor.setPosition(start + 1,QTextCursor.KeepAnchor)
                                    
                                    cursor.setCharFormat(format)
                                    '''
                                    self.manualSelect(start, start+1, '#f66')

                                #cursor.endEditBlock()
                
            else:
                self.indicator.status = 'disconnected'
                
                log('console connection lost')
                
                self.connectionLost()
                #answer = utils.yesNoDialog('Connectioni lost', 'Connection to the server lost, reconnect?' cancelPossible)
                #if answer == True:


            t0 = self.t0
            t1 = time.time()
            
            logText = 'Query was running for... %s' % utils.formatTime(t1-t0)
            
            self.t0 = None
            self.log(logText)

            self.indicator.runtime = None
            self.updateRuntime('off')

            self.indicator.repaint()
            
            if self.stQueue:
                self.log('Queue processing stopped due to this exception.', True)
                self.stQueue.clear()

            return
        
        sql, result, refreshMode = self.sqlWorker.args
        
        dbCursor = self.sqlWorker.dbCursor
        
        if dbCursor is not None:
            result._connection = dbCursor.connection
        
        #self.psid = self.sqlWorker.psid
        #log('psid saved: %s' % utils.hextostr(self.psid))
        
        if dbCursor is not None:
            log('Number of resultsets: %i' % len(dbCursor.description_list), 3)

        t0 = self.t0
        t1 = time.time()
        
        self.t0 = None

        logText = 'Query execution time: %s' % utils.formatTime(t1-t0)
        
        rows_list = self.sqlWorker.rows_list
        cols_list = self.sqlWorker.cols_list
        resultset_id_list = self.sqlWorker.resultset_id_list
        
        #if rows_list is None or cols_list is None:
        if not cols_list:
            # that was not exception, but
            # it was a DDL or something else without a result set so we just stop
            
            if dbCursor is not None:
                logText += ', ' + utils.numberToStr(dbCursor.rowcount) + ' rows affected'
            
            result.clear()
            
            # now destroy the tab, #453
            # should we also remove the result from self.results? Do we know which one?
            # self.results.remove(result) ?
            
            i = self.resultTabs.count()
            log ('no resultset, so kill the tab #%i...' % i, 4)
            
            self.resultTabs.removeTab(i-1)
            
            #return 2021-08-01
            
            numberOfResults = 0
            
        else:
            numberOfResults = len(cols_list)
        
        for i in range(numberOfResults):
            
            #print('result:', i)
            
            if i > 0:
                result = self.newResult(self.conn, result.statement)
                
            result.rows = rows_list[i]
            result.cols = cols_list[i]
            
            result.psid = self.sqlWorker.psid
            log('psid saved: %s' % utils.hextostr(result.psid), 4)
            
            if result.cols[0][2] == 'SCALAR':
                result._resultset_id = None
            else:
                if resultset_id_list is not None:
                    result._resultset_id = resultset_id_list[i]
                else:
                    result._resultset_id = None
                
            rows = rows_list[i]
        
            resultSize = len(rows_list[i])

            # copied from statementExecute (same code still there!)
            result.detached = False
            
            if result.cols is not None:
                for c in result.cols:
                    if self.dbi.ifLOBType(c[1]):
                        result.LOBs = True
                        
                        #print('LOBS!', utils.hextostr(result._resultset_id))
                        
                        break
                        
                        
            if result.LOBs == False and (not result.explicitLimit and resultSize == result.resultSizeLimit):
                log('detaching due to possible SUSPENDED because of unfinished fetch')
                result.detach()
                        

            if result.LOBs:
                result.triggerDetachTimer(self)

            lobs = ', +LOBs' if result.LOBs else ''

            logText += '\n' + str(len(rows)) + ' rows fetched' + lobs
            if resultSize == cfg('resultSize', 1000): logText += ', note: this is the resultSize limit'

            result.populate(refreshMode)
            
            if result.highlightColumn:
                result.highlightRefresh()

        if not self.timerAutorefresh:
            self.log(logText)

        if numberOfResults:
            log('clearing lists (cols, rows): %i, %i' % (len(cols_list), len(rows_list)), 4)
            
            for i in range(len(cols_list)):
                #log('rows %i:%i' % (i, len(rows_list[0])))
                del rows_list[0]
                #log('cols %i:%i' % (i, len(cols_list[0])))
                del cols_list[0]
            
        if self.indicator.status != 'alert':
            '''
            if self.indicator.bkpStatus == 'autorefresh':
                self.indicator.status = self.indicator.bkpStatus
            else:
            '''
            if self.timerAutorefresh:
                self.indicator.status = 'autorefresh'
            else:
                self.indicator.status = 'idle'
            
        self.indicator.runtime = None
        self.updateRuntime('off')
        self.indicator.repaint()
        
        # should rather be some kind of mutex here...
        
        if self.thread.isRunning():
            time.sleep(0.05)
            
        if self.thread.isRunning():
            log('[!!] self.thread.isRunning()!')
            time.sleep(0.1)

        if self.thread.isRunning():
            log('[!!!] self.thread.isRunning()!')
            time.sleep(0.2)
            
        self.launchStatementQueue()
        
        #print('3 <-- finished')
        
    def executeStatement(self, sql, result, refreshMode = False):
        '''
            triggers thread to execute the string without any analysis
            result populated in callback signal sqlFinished
        '''
        
        m = reExpPlan.search(sql)
        
        if m is not None:

            plan_id = m.group(1)
        
            if len(self.stQueue) > 0:
                self.log('explain plan not possible in queue, please run by itesf', True)
                return

            i = self.resultTabs.count()
            log ('Normal statement execution flow aborted, so kill the tab #%i' % i, 4)
            
            self.resultTabs.removeTab(i-1)

            sqls = []
            
            sqls.append("explain plan set statement_name = 'st$%s' for sql plan cache entry %s" % (plan_id, plan_id))
            sqls.append("select * from explain_plan_table where statement_name = 'st$%s'" % (plan_id))
            sqls.append("delete from explain_plan_table where statement_name = 'st$%s'" % (plan_id))
            sqls.append("commit")
                
            self.stQueue = sqls.copy()
            self.launchStatementQueue()
        
        if self.sqlRunning:
            self.log('SQL still running...')
            return
        
        self.renewKeepAlive()
        
        suffix = ''
        
        if len(sql) > 128:
            txtSub = sql[:128]
            suffix = '...'
        else:
            txtSub = sql
            
        txtSub = txtSub.replace('\n', ' ')
        txtSub = txtSub.replace('\t', ' ')
        txtSub = txtSub.replace('    ', ' ')
        
        if not self.timerAutorefresh:
            self.log('\nExecute: ' + txtSub + suffix)

        ##########################
        ### trigger the thread ###
        ##########################
        
        self.sqlWorker.args = [sql, result, refreshMode]
        
        self.t0 = time.time()
        self.sqlRunning = True
        
        self.indicator.bkpStatus = self.indicator.status
        self.indicator.status = 'running'
        self.indicator.repaint()
        
        #print('--> self.thread.start()')
        self.thread.start()
        #print('<-- self.thread.start()')
            
        return
        
    def resultTabsKey (self, event):

        modifiers = QApplication.keyboardModifiers()

        if not ((modifiers & Qt.ControlModifier) or (modifiers & Qt.AltModifier)):
            if event.key() == Qt.Key_F8 or event.key() == Qt.Key_F9 or event.key() == Qt.Key_F5:
            
                i = self.resultTabs.currentIndex()
                log('refresh %i' % i)
                self.refresh(i) # we refresh by index here...
                return
                
        super().keyPressEvent(event)
        
    def updateRuntime(self, mode = None):
        t0 = self.t0
        t1 = time.time()
        
        if mode == 'on' and t0 is not None:
            if self.runtimeTimer == None:
                self.runtimeTimer = QTimer(self)
                self.runtimeTimer.timeout.connect(self.updateRuntime)
                self.runtimeTimer.start(1000)
                
        elif mode == 'off':
            if self.runtimeTimer is not None:
                self.indicator.runtime = None
                self.runtimeTimer.stop()
                self.runtimeTimer = None  

                self.indicator.updateRuntime()
                
                return
        
        if t0 is not None:
            self.indicator.runtime = utils.formatTimeShort(t1-t0)
            
        self.indicator.updateRuntime()
                
    '''
    def updateRuntime(self):
        t0 = self.t0
        t1 = time.time()
        
        if t0 is not None:
            self.indicator.runtime = utils.formatTime(t1-t0)
            
            self.indicator.updateRuntime()
            
            if self.runtimeTimer == None:
                self.runtimeTimer = QTimer(self)
                self.runtimeTimer.timeout.connect(self.updateRuntime)
                self.runtimeTimer.start(500)
            
        else:
            if self.runtimeTimer is not None:
                self.indicator.runtime = None
                self.runtimeTimer.stop()
                self.runtimeTimer = None    
    '''
        
    def reportRuntime(self):
    
        self.selfRaise.emit(self)
    
        '''
        t0 = self.t0
        t1 = time.time()
        
        if t0 is not None:
            self.log('Current run time: %s' % (utils.formatTime(t1-t0)))
        else:
            self.log('Nothing is running')
            
        '''
    
    def initUI(self):
        '''
            main sqlConsole UI 
        '''
        vbar = QVBoxLayout()
        hbar = QHBoxLayout()
        
        #self.cons = QPlainTextEdit()
        self.cons = console(self)
        
        self.cons._parent = self
        
        self.cons.executionTriggered.connect(self.executeSelection)
        self.cons.log.connect(self.log)
        
        self.cons.openFileSignal.connect(self.openFile)
        self.cons.goingToCrash.connect(self.delayBackup)
        
        self.resultTabs = QTabWidget()
        
        self.resultTabs.keyPressEvent = self.resultTabsKey
                
        self.spliter = QSplitter(Qt.Vertical)
        #self.logArea = QPlainTextEdit()
        self.logArea = logArea()
        
        self.spliter.addWidget(self.cons)
        self.spliter.addWidget(self.resultTabs)
        self.spliter.addWidget(self.logArea)
        
        self.spliter.setSizes([300, 200, 10])
        
        vbar.addWidget(self.spliter)
        
        self.setLayout(vbar)
        
        # self.SQLSyntax = SQLSyntaxHighlighter(self.cons.document())
        self.cons.SQLSyntax = SQLSyntaxHighlighter(self.cons.document())
        #console = QPlainTextEdit()
        
        self.cons.setFocus()