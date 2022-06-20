from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPen, QColor

from PyQt5.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QLineEdit, QLabel, QPushButton, QTableWidget, QTableWidgetItem

import random

kpiKeys = []
kpiGroup = {}

radugaColors = []
radugaPens = []

import utils
        
from utils import log, cfg
from utils import vrsException
from utils import resourcePath
from collections import UserDict

currentIndex = None

vrsStrDef = {}      # yaml definition, strings
vrsDef = {}         # yaml definition, dicts
vrsStrErr = {}      # True/False in case of parsing issues

vrsRepl = {}        # dict of pairs from/to per sqlIdx for character replacements

vrsStr = {}         # current string representation (for KPIs table)
vrs = {}            # actual dict

class Style(UserDict):
    exclude = ['sql'] # keys excluded from vars processing
    def __init__(self, idx, *args):
        self.idx = idx
        super().__init__(*args)
        
    def __missing__(self, key):
        log('[!] Style key missing: %s' % key, 1)
        raise KeyError(key)
            
    def __getitem__(self, key):
        if key in self.data:
            value = self.data[key]
            
            # if key == 'y_range': log(f'Style getitem[{self.idx}]: {key}/{value}')
            
            if self.idx and type(value) in (str, list):
                if self.idx in vrs and value != '' and key not in Style.exclude:
                    value = processVars(self.idx, value)
                    # if key == 'y_range': log(f'Post-process:[{self.idx}]: {key}/{value}')
            
            return value
            
        if hasattr(self.__class__, "__missing__"):
            return self.__class__.__missing__(self, key)
            
        raise KeyError(key)

class Variables(QDialog):

    width = None
    height = None
    x = None
    y = None

    def __init__(self, hwnd, idx = None):
        super().__init__(hwnd)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint);
        
        self.initUI(idx)

    def fillVariables(self, mode = None):
    
        if mode == 'defaults':
            lvrsStr = vrsStrDef
            #lvrs = vrsDef -- those already parsed/replaced, cannot use those
        else:
            lvrsStr = vrsStr
            #lvrs = vrs -- those already parsed/replaced, cannot use those
            
            
        # need to parse str variables representation and build a dict to display in form of table
        # duplicated code from add Vars, sorry
        lvrs = {}
        
        for idx in lvrsStr:
            
            lvrs[idx] = {}
            
            vlist = [s.strip() for s in lvrsStr[idx].split(',')]
            
            vNames = []
            for v in vlist:
                p = v.find(':')
                if p > 0:
                    vName = v[:p].strip()
                    vVal = v[p+1:].strip()
                    
                lvrs[idx][vName] = vVal
    
        r = 0
        
        '''
        print('lvrsStr')
        for idx in lvrsStr:
            print(idx, ' --> ', lvrsStr[idx])
            print(idx, ' --> ', lvrs[idx])
        '''

        #print('\nvrs')
        for idx in lvrs:
            #print(idx, ' --> ', lvrs[idx])
            r += len(lvrs[idx])
            
        #print()

        self.vTab.setRowCount(r)

        row = 0
        for idx in lvrs:
            i = 0
            for var in lvrs[idx]:
                val = lvrs[idx][var]
                #print(idx, var, val)

                # idx
                if i == 0:
                    item1 = QTableWidgetItem(idx)
                else:
                    item1 = QTableWidgetItem('') # must be empty
                    
                item1.setFlags(item1.flags() & ~Qt.ItemIsEditable)
                self.vTab.setItem(row, 0, item1)
                    
                # variable
                item2 = QTableWidgetItem(var)
                item2.setFlags(item2.flags() & ~Qt.ItemIsEditable)
                self.vTab.setItem(row, 1, item2)
                
                #value
                self.vTab.setItem(row, 2, QTableWidgetItem(val))
                
                i += 1
                row += 1
                
        self.vTab.resizeColumnsToContents()
        
    def resetVars(self):
        self.fillVariables('defaults')
    
    def processVars(self):
    
        global vrs
        global vrsStr
        
        rowsCount = self.vTab.rowCount()
        
        vrsNew = {}
        
        idx = ''
        nvrsStr = {}
        nvrs = {}
        
        for i in range(rowsCount):
            if self.vTab.item(i, 0) and self.vTab.item(i, 0).text() != '' and self.vTab.item(i, 0).text() != idx:
                idx = self.vTab.item(i, 0).text()
                nvrs[idx] = {}
                
            var = self.vTab.item(i, 1).text()
            val = self.vTab.item(i, 2).text()
            
            nvrs[idx][var] = val

        #print('\nnew vrs:')
        
        #combone string representation...
        for idx in nvrs:
            #print(idx, '-->', nvrs[idx])
            
            nvrsStr[idx] = ', '.join(['%s: %s' % (key, value) for (key, value) in nvrs[idx].items()])
            
        #print('\nvrsStr')
        for idx in nvrsStr:
            #print(idx, ' --> ', nvrsStr[idx])
            
            try:
                addVars(idx, nvrsStr[idx], overwrite=True) #use common processing
            except vrsException as ex:
                utils.msgDialog('Error', f'There is an error parsing {idx}:\n\n{ex}\n\nChanges were not applied.')
            
        '''
        vrsStr = nvrsStr
        vrs = nvrs
        '''
            
        Variables.width = self.size().width()
        Variables.height = self.size().height()
        
        Variables.x = self.pos().x()
        Variables.y = self.pos().y()
        
        self.accept()
        
    def highlightIdx(self, idx):
        log(f'Need to highlight {idx}', 5)
        
        for i in range(self.vTab.rowCount()):
            item = self.vTab.item(i, 0)
            if item is not None and item.text() == idx:
                self.vTab.setCurrentItem(item)
        
        
    def initUI(self, idx):
    
        iconPath = resourcePath('ico\\favicon.png')
        
        vbox = QVBoxLayout()
        ocBox = QHBoxLayout()
        
        self.vTab = QTableWidget()
        
        self.vTab.setColumnCount(3)
        
        self.vTab.setHorizontalHeaderLabels(['KPI file', 'Variable', 'Value'])
        
        vbox.addWidget(self.vTab)
        
        rButton = QPushButton('Reset all to defaults')
        
        if len(vrsDef) == 0:
            rButton.setDisabled(True)
        
        okButton = QPushButton('Ok')
        cButton = QPushButton('Cancel')
        
        okButton.clicked.connect(self.processVars)
        rButton.clicked.connect(self.resetVars)
        cButton.clicked.connect(self.reject)
        
        ocBox.addStretch(1)
        ocBox.addWidget(okButton)
        ocBox.addWidget(rButton)
        ocBox.addWidget(cButton)
        
        vbox.addLayout(ocBox)
        
    
        self.setLayout(vbox)
        
        #self.setWindowIcon(QIcon(iconPath))
        
        #self.setGeometry(300, 300, 300, 150)
        
        self.resize(500, 300)
        self.setWindowTitle('Variables')
        
        self.fillVariables()
        self.highlightIdx(idx)
        
        if self.width and self.height:
            self.resize(self.width, self.height)

        if self.x and self.y:
            self.move(self.x, self.y)


def addVarsRepl(sqlIdx, repl):
    global vrsRepl
    
    vrsRepl[sqlIdx] = repl
    
def addVarsDef(sqlIdx, vStr):
    '''
        builds a dict for default values as it is defined in yaml definition
        string representation also stored.
        
        It is used two cases:
            1) to reset everithing to defaults when update from kpiTable submitted --- not any more...
            2) to set variables to empty value in case it is missing in vrsStr
    '''
    
    global vrsStrDef
    global vrsDef
    
    vrsStrDef[sqlIdx] = vStr
    
    vlist = [s.strip() for s in vStr.split(',')]
    
    if sqlIdx in vrsDef:
        log('%s already in the dict, anyway...' % sqlIdx, 4)
        
    vrsDef[sqlIdx] = {}
        
    for v in vlist:
        p = v.find(':')
        if p > 0:
            vName = v[:p].strip()
            vVal = v[p+1:].strip()
        else:
            vName = v
            vVal = ''
            
        vrsDef[sqlIdx][vName] = vVal
        
    log('yaml variables for %s defined as %s' % (sqlIdx, str(vrsDef[sqlIdx])))
    

def addVars(sqlIdx, vStr, overwrite = False):
    '''
        this one called on manual update of variables from the KPIs table
        
        (seems) it also actualizes vrs dict
    '''

    global vrs
    global vrsStr
    global vrsDef
    global vrsRepl
    
    def repl(idx, s):
        r = vrsRepl.get(idx)
        
        if r:
            smod = s.replace(r[0], r[1])
            if s != smod:
                log(f'Variable replace {idx}: {s} --> {smod}', 4)
            else:
                log(f'Didn\'t make any changes {idx}: {s} --> {smod}', 4)
            
                
            return smod
        else:
            log(f'no replacement for {idx}, s = {s}', 4)
            return s
        
    def validate(s):
        '''
            very simple validation routine
        '''
        vlist = [s.strip() for s in vStr.split(',')]
        
        for v in vlist:
            if v.find(':') <= 0:
                log('Not a valid variable definition: [%s]' % v, 2)
                return False
                
        return True
    
    log('addVars input: %s' % (str(vStr)), 5)
        
    for idx in vrs:
        log('%s --> %s' % (idx, str(vrs[idx])), 5)
    
    if vStr == None:
        return
    '''
    if overwrite:
        if sqlIdx in vrs:
            log('full refresh of %s vars' % (sqlIdx), a4)
            
            vrs[sqlIdx].clear()
    '''
    
    if not validate(vStr):
        log('[E] Variables parsing error!', 2)
        
        #vrsStr[sqlIdx] = None
        msg = 'Variables cannot have commas inside'
        vrsStrErr[sqlIdx] = '[!] '  + msg
        raise vrsException(msg)
        
        return
    else:
        vrsStrErr[sqlIdx] = False
        
    #if sqlIdx not in vrs or True: 2022-04-17
    if sqlIdx not in vrs:
        vrs[sqlIdx] = {}

    if sqlIdx not in vrsStr or overwrite:
        vrsStr[sqlIdx] = vStr

    vlist = [s.strip() for s in vStr.split(',')]
    
    vNames = []
    for v in vlist:
        p = v.find(':')
        if p > 0:
            vName = v[:p].strip()
            vVal = v[p+1:].strip()
                        
            vNames.append(vName)
        else:
            '''
            vName = v
            vVal = ''
            '''
            return 
            
        if vName in vrs[sqlIdx]:
            if overwrite:
                #log('Variable already in the list, will update...: %s -> %s' % (vName, vVal), 4)
                vrs[sqlIdx][vName] = repl(sqlIdx, vVal)
            else:
                # log(f'Overwrite is off, so only do the replacement {vName}', 4)
                vrs[sqlIdx][vName] = repl(sqlIdx, vrs[sqlIdx][vName])
        else:
            vrs[sqlIdx][vName] = repl(sqlIdx, vVal)
            
    #keysDelete = []
    # go throuth the result and remove the stuff that was not supplied in the input string, #602
    if sqlIdx in vrsDef:
        # otherwise it is probably an initial load
        for v in vrs[sqlIdx]:
            if v not in vNames:
                if v in vrsDef[sqlIdx]:
                    log('Variable \'%s\' seems missing in %s, restoring default from YAML' % (v, sqlIdx))
                    vrs[sqlIdx][v] = vrsDef[sqlIdx][v]
                else:
                    log('Seems variable \'%s\' is excluded from %s, it will be IGNORED' % (v, sqlIdx))
                    #log('Seems variable \'%s\' is excluded from %s, it will be erased from the runtime values' % (v, sqlIdx))
                    #keysDelete.append(v)
                    
        '''
        for k in keysDelete:
            log('deleting %s from %s' %(k, sqlIdx))
            vrs[sqlIdx].pop(k)
        '''
            
    # go through defined variables and add missing ones
    
    if sqlIdx not in vrsDef:
        log('[W] how come %s is missing in vrsDed??' % sqlIdx, 2)
    else:
        log('Variables YAML defaults: %s' % str(vrsDef[sqlIdx]), 5)
        for k in vrsDef[sqlIdx]:
            if k not in vrs[sqlIdx]:
                vrs[sqlIdx][k] = repl(sqlIdx, vrsDef[sqlIdx][k])
                log('[W] MUST NOT REACH THIS POINT #602\'%s\' was missing, setting to the default value from %s: %s' % (k, sqlIdx, vrsDef[sqlIdx][k]), 4)
        
    log(f'Actual variables for {sqlIdx} now are {vrs[sqlIdx]}', 4)


def processVars(sqlIdx, src):
    '''
        makes the actual replacement based on global variable vrs
        sqlIdx is a custom KPI file name with extention, example: 10_exp_st.yaml
        
        s is the string or list of strings for processing
        
        this function does not evaluate source definition, only vrs
        vrs actualization done in addVars - it restores missed values, etc
    '''

    global vrs
    
    # is it custom kpi at all?
    if not sqlIdx:
        return src

    # are there any variables?
    if sqlIdx not in vrs:
        return src


    outList = []
    
    if type(src) != list:
        srcList = [str(src)]
    else:
        srcList = src

    # go through list values
    for s in srcList:
        #if s is not None:
            #s = str(s)
        if type(s) == str:

            #log('---process vars...---------------------------------------', 5)
            #log('sqlIdx: ' + str(sqlIdx))
            #log('vrs: ' + str(vrs[sqlIdx]))
            #log('>>' + s, 5)
            #log('  -- -- -- --', 5)

            if sqlIdx in vrs:
                for v in vrs[sqlIdx]:
                    if v == '':
                        continue
                        
                    s = s.replace('$'+v, str(vrs[sqlIdx][v]))
                
            #log('<<' + s, 5)
            #log('---------------------------------------------------------', 5)
        
        outList.append(s)
        
    # return the same type: single string or list of strings
    if type(src) != list:
        return outList[0]
    else:
        return outList
        
    return s

def removeDeadKPIs(kpis, type):

    for kpi in kpis:
        if kpi[:1] != '.' and kpi not in kpiStylesNN[type]:
            print('deleting', kpi)
            kpis.remove(kpi)
            
    return

def generateRaduga():

    #random.seed(cfg('radugaSeed', 1))

    colors = utils.cfg('raduga')
        
    for c in colors:
        
        color = QColor(c)
        pen = QPen(color)
        
        radugaColors.append(color)
        radugaPens.append(pen)
        
    resetRaduga()
    

def getRadugaPen():
    global currentIndex
    
    n = len(radugaPens)
    
    if n == 0:
        return None
    
    pen = radugaPens[currentIndex]

    currentIndex += 1
    
    if currentIndex >= n:
        currentIndex = 0
    
    return pen

def resetRaduga():
    global currentIndex
    
    currentIndex = 0
    
kpiStylesN = {}
kpiStylesNN = {'host':{}, 'service':{}}

customSql = {}

def createStyle(kpi, custom = False, sqlIdx = None):

    log(str(kpi))

    #style = {}
    style = Style(sqlIdx)
    
    # mandatory stuff
    
    style['type'] = 's' if kpi['type'] == 'service' else 'h'
    style['subtype'] = kpi.get('subtype')
    
    if custom:
        style['name'] = 'cs-' + kpi['name']
    else:
        style['name'] = kpi['name']
        
    if custom:
        style['sqlname'] = kpi.get('sqlname', '') # gantt subtype always uses START/STOP so no sql column name used
        style['nofilter'] = True if kpi.get('nofilter') else False
            
    # optional stuff
    style['group'] = kpi.get('group', '')
    style['desc'] = kpi.get('description', '')
    style['label'] = kpi.get('label', '')
        
    if 'sUnit' in kpi and 'dUnit' in kpi:
        sUnit = kpi['sUnit'].split('/')
        dUnit = kpi['dUnit'].split('/')
        
        if len(sUnit) > 1 and len(dUnit) > 1 and sUnit[1] == 'sample' and dUnit[1] == 'sec':
            style['sUnit'] = sUnit[0]
            style['dUnit'] = dUnit[0]
            style['perSample'] = True
        else:
            style['sUnit'] = kpi['sUnit']
            style['dUnit'] = kpi['dUnit']
    else:
        style['sUnit'] = '-'

    #create pen
    if 'color' in kpi:
        color = QColor(kpi['color'])
    else:
        color = QColor('#DDD')
        
        
        
    penStyles = {
        'solid': Qt.SolidLine,
        'dotted': Qt.DotLine,
        'dashed': Qt.DashLine,
        'dotline': Qt.DotLine,
        'bar': Qt.DotLine,
        'candle': Qt.DotLine,
        'unknown': Qt.DashDotDotLine
    }
        
    if 'style' in kpi:
        st = kpi.get('style', 'unknown')
        penStyle = penStyles[st]
        
        if st == 'unknown': log('[W] pen style unknown: %s - [%s]' % (kpi['name'], (kpi['style'])), 2)
    else:
        log('[W] pen style not defined for %s, using default' % (kpi['name']), 2)
        if style['type'] == 'h':
            penStyle = Qt.DashLine
        else:
            penStyle = Qt.SolidLine
    
    if kpi['name'][:7] == '---#---':
        style['pen'] = '-'
    else:
        if kpi.get('subtype') == 'gantt':
            # gantt stuff
            style['width'] = kpi.get('width', 8)
            style['font'] = kpi.get('fontSize', 8)
            style['tfont'] = kpi.get('titleFontSize', style['font']-1)
            style['shift'] = kpi.get('shift', 2)
            style['title'] = kpi.get('title')
            style['gradient'] = kpi.get('gradient')
            
            style['style'] = kpi.get('style', 'bar')
            
            if style['style'] not in ('bar', 'candle'):
                log('[W] unsupported gantt style (%s), using default' % style['style'], 2)
                style['style'] = 'bar'

            clr = QColor(color)
            style['brush'] = clr

            penColor = QColor(clr.red()*0.75, clr.green()*0.75, clr.blue()*0.75)
            style['pen'] = QPen(penColor, 1, Qt.SolidLine)

            brightnessTo = kpi.get('gradientTo', '#F00')
            clrFade = QColor(brightnessTo)
            style['gradientTo'] = clrFade

            yr = kpi.get('y_range')
            
            if type(yr) == list and len(yr) == 2:
                style['y_range'] = yr
            else:
                log('[W] unsupported y_range value for %s: %s, using default: 0, 100' % (kpi['name'], str(yr)), 2)
                style['y_range'] = [0, 100]
            
        elif kpi.get('subtype') == 'multiline':
        
            if 'splitby' not in kpi:
                log('[W] multiline KPI (%s) must have splitby definition, skipping!' % (kpi['name']), 2)
                return None

            style['groupby'] = kpi['splitby']
            style['stacked'] = kpi.get('stacked', False)
            style['multicolor'] = kpi.get('multicolor', False)
            style['descending'] = kpi.get('desc', False)
            style['legendCount'] = kpi.get('legendCount', 5)
            style['others'] = kpi.get('others', False)

            ordby = kpi.get('orderby', 'unknown')
            if ordby not in ['max', 'avg', 'name', 'deviation']:
                log('[W] unsupported orderby value %s/%s, using default (max)' % (kpi['name'], kpi.get('orderby')), 2)
                    
            style['orderby'] = ordby
            
            if style['multicolor']:
                style['pen'] = QPen(QColor('#48f'), 1, Qt.SolidLine)
            else:
                style['pen'] = QPen(QColor(color), 1, Qt.SolidLine)
                
            style['brush'] = None
            style['style'] = 'multiline'
            
        else:
            # regular kpis
            style['pen'] = QPen(color, 1, penStyle)

    style['sql'] = sqlIdx
    
    '''
    except Exception as e:
        log(str(kpi))
        log(style)
        log('Error creating a style: %s' % str(e))
        
        return None
    '''
    return style
    
def customKpi (kpi):
    if kpi[:3] == 'cs-':
        return True
    else:
        return False

def getTimeKey(type, kpi):

    if customKpi(kpi):
        timeKey = 'time:' + kpiStylesNN[type][kpi]['sql']
    else:
        timeKey = 'time'
        
    return timeKey

def getSubtype(type, kpi):

    if kpi in kpiStylesNN[type]:
        subtype = kpiStylesNN[type][kpi]['subtype']
    else:
        subtype = None
        
    return subtype
        
def nsStyle (idx):
    
    defStyles = ['', 'solid', 'dashed', 'dotted', 'dotline']
    
    if idx <= len(defStyles):
        return defStyles[idx]
    else:
        return defStyles[0]

def hType (i, hosts):
    '''
        returns host type based on host index
        currently host/service
        used for kpiStylesNN[type]
    '''
    if hosts[i]['port'] == '':
        return 'host'
    else:
        return 'service'
        
def clarifyGroups():
    '''
        gives pre-defined names to most useful groups
    '''

    thread_kpis = ['active_thread_count',
            'waiting_thread_count',
            'total_thread_count',
            'active_sql_executor_count',
            'waiting_sql_executor_count',
            'total_sql_executor_count']

    thread_kpis_ns = ['indexserverthreads',
            'waitingthreads',
            'totalthreads',
            'activesqlexecutors',
            'waitingsqlexecutors',
            'totalsqlexecutors']

    def update_hardcoded(kpis, kpiList, grp):
        for kpi in kpis:
            if kpis[kpi]['name'] in kpiList:
                kpis[kpi]['group'] = grp
            
    def update(grpIdx, grpName):
        if grpIdx == 0:
            return;
    
        if grpIdx == grpName:
            return
    
        for h in kpiStylesNN:
            for kpi in kpiStylesNN[h]:
                if kpiStylesNN[h][kpi]['group'] == grpIdx:
                    kpiStylesNN[h][kpi]['group'] = grpName
                    
    def updateDunit(grpIdx, dUnit):
        for h in kpiStylesNN:
            for kpi in kpiStylesNN[h]:
                if kpiStylesNN[h][kpi]['group'] == grpIdx:
                    kpiStylesNN[h][kpi]['dUnit'] = dUnit
        
    for h in kpiStylesNN:
    
        if 'cpu' in kpiStylesNN[h]:
            update(kpiStylesNN[h]['cpu']['group'], 'cpu')

        if 'memory_used' in kpiStylesNN[h]:
            update(kpiStylesNN[h]['memory_used']['group'], 'mem')
            

        # those two for dpTrace as it is based on ns KPI names
        if 'cpuused' in kpiStylesNN[h]:
            update(kpiStylesNN[h]['cpuused']['group'], 'cpu')

        if 'memoryused' in kpiStylesNN[h]:
            update(kpiStylesNN[h]['memoryused']['group'], 'mem')

        if cfg('memoryGB'):
            updateDunit('mem', 'GB')
            
        # enforce threads scaling
        if thread_kpis[0] in kpiStylesNN[h]:
            update_hardcoded(kpiStylesNN[h], thread_kpis, 33)

        if 'active_thread_count' in kpiStylesNN[h]:
            update(kpiStylesNN[h]['active_thread_count']['group'], 'thr')
            
        # now the same for ns... 
        if thread_kpis_ns[0] in kpiStylesNN[h]:
            update_hardcoded(kpiStylesNN[h], thread_kpis_ns, 33)

        if 'indexserverthreads' in kpiStylesNN[h]:
            update(kpiStylesNN[h]['indexserverthreads']['group'], 'thr')
        

def groups():
    # generates list of actual kpi groups

    groups = []

    for h in kpiStylesNN:
        for kpi in kpiStylesNN[h]:
            if kpiStylesNN[h][kpi]['group'] not in groups:
                groups.append(kpiStylesNN[h][kpi]['group'])
                
    return groups

def normalize (kpi, value, d = 0):

    if 'sUnit' in kpi and 'dUnit' in kpi:
        sUnit, dUnit = kpi['sUnit'], kpi['dUnit']
    else:
        return value

    nValue = None
    
    if sUnit == 'Byte' and dUnit == 'GB':
        nValue = round(utils.GB(value, 'GB'), d)
    elif sUnit == 'Byte' and dUnit == 'MB':
        nValue = round(utils.GB(value, 'MB'), d)

    elif sUnit == 'usec' and dUnit == 'sec':
        nValue = round(value/1000000, d)

    # ('[N] %s: %s -> %s %i -> %s ' % (kpi['name'], kpi['sUnit'], kpi['dUnit'], value, str(nValue)))
    
    if nValue is not None:
        return nValue
    else:
        return value

def denormalize (kpi, value):

    if 'sUnit' in kpi and 'dUnit' in kpi:
        sUnit, dUnit = kpi['sUnit'], kpi['dUnit']
    else:
        return value

    nValue = None
    
    if sUnit == 'Byte' and dUnit == 'GB':
        nValue = utils.antiGB(value, 'GB')
    elif sUnit == 'Byte' and dUnit == 'MB':
        nValue = utils.antiGB(value, 'MB')

    elif sUnit == 'usec' and dUnit == 'sec':
        nValue = value*1000000

    # ('[dN] %s: %s -> %s %i -> %s ' % (kpi['name'], kpi['sUnit'], kpi['dUnit'], value, str(nValue)))
    
    if nValue is not None:
        return nValue
    else:
        return value
        
def initKPIDescriptions(rows, hostKPIs, srvcKPIs):
    '''
        Same interface to be reused for DB trace
        
        Output:
            hostKPIs, srvcKPIs are filled with the respective KPIs lists
            
            kpiStylesNN - GLOBAL <--- list of KPIs...
    '''
    
    for kpi in rows:
        
        if kpi[1].lower() == 'm_load_history_host':
            type = 'host'
        else:
            type = 'service'
    
        if kpi[1] == '': #hierarchy nodes
            if len(kpi[0]) == 1:
                continue # top level hierarchy node (Host/Service)
            else:
                # Normal hierarchy node
                kpiName = '.' + kpi[4]
        else:
            kpiName = kpi[2].lower()
            kpiDummy = {
                    'hierarchy':    kpi[0],
                    'type':         type,
                    'name':         kpiName,
                    'group':        kpi[3],
                    'label':        kpi[4],
                    'description':  kpi[5],
                    'sUnit':        kpi[6],
                    'dUnit':        kpi[7],
                    'color':        kpi[8],
                    'style':        nsStyle(kpi[9])
                }
            
            kpiStylesNN[type][kpiName] = createStyle(kpiDummy)
                    
        if kpi[1].lower() == 'm_load_history_host':
            hostKPIs.append(kpiName)
        else:
            srvcKPIs.append(kpiName)
