from PyQt5.QtWidgets import QApplication, QMessageBox;
from PyQt5.QtGui import QPainter, QIcon

import sys
from os import getcwd
import hslWindow

from PyQt5 import QtCore

from utils import log

import utils
from utils import resourcePath
from _constants import build_date, version

import traceback
import sqlConsole

'''
    TODO
    
    - log console (log all exceptions through signals)
    - file import dialog
    - hosts/tenants pane
    - config screen
        - favorite connections
        - smart checks (show ooms, show expst)
    - statistics server charts
    - memory allocators chart
    
'''

class ExceptionHandler(QtCore.QObject):

    errorSignal = QtCore.pyqtSignal()

    def __init__(self):
        super(ExceptionHandler, self).__init__()

    def handler(self, exctype, value, tb):
    
        global ryba
    
        cwd = getcwd()
        log('[!] fatal exception\n')
        
        #details = '%s: %s\n' % (str(exctype), str(value))
        details = '%s.%s: %s\n\n' % (exctype.__module__ , exctype.__qualname__  , str(value))
        #???

        #self.errorSignal.emit()
        #sys._excepthook(exctype, value, traceback)
        

        for s in traceback.format_tb(tb):
            details += '>>' + s.replace('\\n', '\n').replace(cwd, '..')

        log(details, nots = True)


        if ryba.tabs:
            for i in range(ryba.tabs.count() -1, 0, -1):

                w = ryba.tabs.widget(i)
                
                if isinstance(w, sqlConsole.sqlConsole):
                    w.delayBackup()

        msgBox = QMessageBox()
        msgBox.setWindowTitle('Fatal error')
        msgBox.setText('Unhandled exception occured. Check the log file for details.')
        msgBox.setIcon(QMessageBox.Critical)
        msgBox.setDetailedText(details)
        iconPath = resourcePath('ico\\favicon.ico')
        msgBox.setWindowIcon(QIcon(iconPath))
        msgBox.exec_()
        
        sys.exit(0)

if __name__ == '__main__':
    
    global ryba
    
    exceptionHandler = ExceptionHandler()
    #sys._excepthook = sys.excepthook
    sys.excepthook = exceptionHandler.handler
        
    log('Starting %s build %s' % (version, build_date))
    log('qt version: %s' %(QtCore.QT_VERSION_STR))
    
    app = QApplication(sys.argv)

    loadConfig = True
    
    while loadConfig:

        ok = utils.loadConfig()
        
        if not ok:
            loadConfig = utils.yesNoDialog('Config error', 'Cannot load/parse config.yaml\nTry again?')
        else:
            loadConfig = False

    #ex = hslWindow.hslWindow()
    ryba = hslWindow.hslWindow()
    #ex = hslWindow.hslWindow()
    
    loadConfig = True
    
    sys.exit(app.exec_())
    app.exec_()