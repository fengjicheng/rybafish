import sys, os, time
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtGui import QIcon

from PyQt5.QtCore import QMutex

from datetime import datetime

import os

import locale

from decimal import Decimal

from yaml import safe_load, dump, YAMLError #pip install pyyaml

from binascii import hexlify
from profiler import profiler

import re

config = {}

global utils_alertReg
__alertReg__ = None

timers = []

#globals:
localeCfg = None
newNumbersFormatting = True
thousands_separator = ''
decimal_point = '.'
decimal_digits = 6

cfg_logmode = 'file'
cfg_loglevel = 3

configStats = {}

def pwdunhash(pwdhsh):
    pwd = pwdhsh[5:]
    print('------', pwd)
    return pwd
    
def pwdtohash(pwd):
    pwdhsh = 'hash!' + pwd
    return pwdhsh

def hextostr(value):
    if value:
        value_str = hexlify(bytearray(value)).decode('ascii')
    else:
        value_str = 'None'
        
    return(value_str)


def timerStart():
    timers.clear()
    timers.append([time.time(), ''])
    
def timeLap(desc = None):

    if desc is None:
        desc = 't'+str(len(timers))

    timers.append([time.time(), desc])

def timePrint():

    s = []
    
    for i in range(1, len(timers)):
        s.append('%s:%s' % (timers[i][1], str(round(timers[i][0]-timers[i-1][0], 3))))
        
    return s

class cfgManager():

    configs = {}
    path = None
    
    def reload(self):
        from cryptography.fernet import Fernet
        self.fernet = Fernet(b'aRPhXqZj9KyaC6l8V7mtcW7TvpyQRmdCHPue6MjQHRE=')
    
        cfs = None

        self.configs = {}

        try: 
            log(f'Opening connections file: {self.fname}', 3)
            
            f = open(self.fname, 'r')
        except:
            log('Cannot open the file, using defaults...', 2)
            
            return
        
        try:
            cfs = safe_load(f)
        except:
            log('Error reading yaml file', 2)
            return
            
        if not cfs:
            return

        for n in cfs:
                
            confEntry = cfs[n]
            
            if 'pwd' in confEntry:
                pwd = confEntry['pwd']
                pwd = self.fernet.decrypt(pwd).decode()
                confEntry['pwd'] = pwd
                
            self.configs[n] = confEntry

    def __init__(self, fname = None):

        if fname is None:
            script = sys.argv[0]
            path, file = os.path.split(script)
        
            self.fname = os.path.join(path, 'connections.yaml')
            
        else:
            self.fname = fname
            
        self.reload()
        
    def updateConf(self, confEntry):

        name = confEntry.pop('name')
        
        self.configs[name] = confEntry
        
        self.dump()
    
    def removeConf(self, entryName):
        if entryName in self.configs:
            del self.configs[entryName]
            
        self.dump()
        
    def dump(self):

        #ds = self.configs.copy()
        
        ds = {}
        for n in self.configs:
            confEntry = self.configs[n].copy()
            if 'pwd' in confEntry:
                pwd = confEntry['pwd']
                pwd = self.fernet.encrypt(pwd.encode())
        
                confEntry['pwd'] = pwd
                
                
            if confEntry.get('dbi') == 'S2J':
                if 'pwd' in confEntry:
                    del confEntry['pwd']
                
                if 'user' in confEntry:
                    del confEntry['user']
                    
            ds[n] = confEntry

        try: 
            f = open(self.fname, 'w')
            
            dump(ds, f, default_flow_style=None, sort_keys=False)
            f.close()
        except Exception as e:
            log('layout dump issue:' + str(e))

class Layout():
    
    lo = {}
    
    def __init__ (self, mode = False):

        if mode == False:
            return

        script = sys.argv[0]
        path, file = os.path.split(script)
        
        fname = os.path.join(path, 'layout.yaml')

        try: 
            f = open(fname, 'r')
            self.lo = safe_load(f)
        except:
            log('no layout, using defaults')
            
            self.lo['pos'] = None
            self.lo['size'] = [1400, 800]
            
    def __getitem__(self, name):
        if name in self.lo:
            return self.lo[name]
        else:
            return None

    def __setitem__(self, name, value):
        self.lo[name] = value
        
    def dump(self):
        try: 
            f = open('layout.yaml', 'w')
            dump(self.lo, f, default_flow_style=None, sort_keys=False)
            f.close()
        except:
            log('layout dump issue')
            
            return False
        
class vrsException(Exception):
    def __init__ (self, message):
        super().__init__(message)

class dbException(Exception):

    CONN = 1
    SQL = 2

    def __init__ (self, message, type = None):
        self.type = type
        self.msg = message
        super().__init__(message, type)
        
    def __str__(self):
    
        message = self.msg
        
        if self.type is not None:
            message += ', Type ' + str(self.type)
    
        return message

class customKPIException(Exception):
    def __init__ (self, message):
        super().__init__(message)
    

def yesNoDialog(title, message, cancel = False, ignore = False, parent = None):

    if parent:
        msgBox = QMessageBox(parent)
    else:
        msgBox = QMessageBox()
        
    msgBox.setWindowTitle(title)
    msgBox.setText(message)

    if cancel == True:
        buttons = QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
    elif ignore:
        buttons = QMessageBox.Yes | QMessageBox.No | QMessageBox.Ignore
    else:
        buttons = QMessageBox.Yes | QMessageBox.No
        
    msgBox.setStandardButtons(buttons)
    msgBox.setDefaultButton(QMessageBox.Yes)
    iconPath = resourcePath('ico', 'favicon.png')
    msgBox.setWindowIcon(QIcon(iconPath))
    msgBox.setIcon(QMessageBox.Warning)
    
    reply = msgBox.exec_()
    
    #for some reason sometimes code CONTINUES to run after this

    if reply == QMessageBox.Yes:
        return True
    elif reply == QMessageBox.Ignore:
        return 'ignore'
    elif reply == QMessageBox.No:
        return False
        
    return None

def msgDialog(title, message):
    msgBox = QMessageBox()
    msgBox.setWindowTitle(title)
    msgBox.setText(message)

    buttons = QMessageBox.Ok
        
    msgBox.setStandardButtons(buttons)
    iconPath = resourcePath('ico', 'favicon.png')
    
    msgBox.setWindowIcon(QIcon(iconPath))
    msgBox.setIcon(QMessageBox.Warning)
    
    reply = msgBox.exec_()
    
    return
        

@profiler
def GB(bytes, scale = 'GB'):
    '''
        returns same number but in GB (/=1023^3)
    '''
    
    if bytes is None:
        return None
    
    if scale == 'MB':
        mult = 1024*1024
    elif scale == 'GB':
        mult = 1024*1024*1024
    elif scale == 'TB':
        mult = 1024*1024*1024*1024
    
    return bytes/mult
    
@profiler
def antiGB(gb, scale = 'GB'):
    '''
        returns same number but in bytes (*=1023^3)
    '''
    
    if scale == 'MB':
        mult = 1024*1024
    elif scale == 'GB':
        mult = 1024*1024*1024
    elif scale == 'TB':
        mult = 1024*1024*1024*1024
    
    return gb*mult
    
    
@profiler
def strftime(time):

    #ms = time.strftime('%f')
    ms = round(time.timestamp() % 1 * 10)
    str = time.strftime('%Y-%m-%d %H:%M:%S')
    
    return '%s.%i' % (str, ms)
    
    
def resourcePath(folder, file):
    '''
        resource path calculator
        for pyinstall
    '''

    try:
        base = sys._MEIPASS
    except:
        base = '.'

    #return base + '\\' + file
    return os.path.join(base, folder, file)
    
def fakeRaduga():
    global config
    config['raduga'] = ['#20b2aa', '#32cd32', '#7f007f', '#ff0000', '#ff8c00', '#7fff00', '#00fa9a', '#8a2be2']
    
def loadConfig(silent=False):

    global config
    global __alertReg__
    
    script = sys.argv[0]
    path, file = os.path.split(script)
    
    cfgFile = os.path.join(path, 'config.yaml')

    config.clear()

    try: 
        f = open(cfgFile, 'r')
        config = safe_load(f)
        f.close()
        
        if 'raduga' not in config:
            log('raduga list of colors is not defined in config, so using a pre-defined list...', 2)
            fakeRaduga()
            
    except:
        if not silent:
            log('no config file? <-')
            
        config = {}
        
        return False
        
    alertStr = cfg('alertTriggerOn')

    if alertStr and alertStr[0] == '{' and alertStr[-1:] == '}':
        __alertReg__ = re.compile(r'^{' + alertStr[1:-1] + r'(:[^!]*)?(!\d{1,3})?}$')
    else:
        __alertReg__ = None
        
    return True
    
def cfgSet(param, value):
    global config

    config[param] = value

def cfgPersist(param, value, layout):
    cfgSet(param, value)
    
    if 'settings' not in layout:
        layout['settings'] = {}
        
    layout['settings'][param] = value

@profiler
def cfg(param, default = None):

    global config
    global configStats

    if configStats:
        if param in configStats:
            configStats[param] += 1
        else:
            configStats[param] = 1
    
    if param in config:
        return config[param]
    else:
        return default
        
def configReportStats():

    global configStats
    
    if not configStats:
        return
    
    params = sorted(configStats.keys(), key=lambda x: configStats[x], reverse=True)
    
    maxLen = len(max(configStats.keys(), key=lambda x: len(x)))
    numLen = len(str(configStats[params[0]]))
        
    log('Config stats:')
    log('-'*(maxLen+4+numLen+1))
    
    c = 0
    for p in params:
        log(f'{p:{maxLen+4}} {configStats[p]}')
        c += configStats[p]
        
        if configStats[p] <= 5:
            break
        
    log('-')
    log(f'Total config calls: {c}')
    log('-'*(maxLen+4+numLen+1))
    
     
def getlog(prefix):
    '''
        returns logging function with provided prefix
    '''
    pref = None
    
    pref = prefix
    def logf(s, *args, **kwargs):
        s = '[%s] %s' % (pref, s)
        
        log(s, *args, **kwargs)
    
    return logf
    
class fakeMutex():
    def tryLock(self, timeout=0):
        pass
        
    def lock(self):
        pass
        
    def unlock(self):
        pass

loadConfig(silent=True) # try to silently init config...

if cfg('threadSafeLogging', False):
    mtx = QMutex()
else:
    mtx = fakeMutex()

@profiler
def log(s, loglevel = 3, nots = False, nonl = False):
    '''
        log the stuff one way or another...
    '''
    
    if cfg_loglevel < loglevel:
        return

    if not nots:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' '
    else:
        ts = ''
    
    if cfg_logmode == 'screen' or cfg_logmode == 'duplicate':
        print('[l]', s)
        
    if nonl:
        nl = ''
    else:
        nl = '\n'
    
    if cfg_logmode != 'screen':
    
        with profiler('log mutex lock'):
            mtx.tryLock(200)
            
        f = open('.log', 'a')
        #f.seek(os.SEEK_END, 0)
    
        try:
            f.write(ts + str(s) + nl)

        except Exception as e:
            f.write(ts + str(e) + nl)
    
        f.close()
        
        mtx.unlock()

if cfg('threadSafeLogging', False):
    log('threadSafeLogging enabled')
    mtx = QMutex()
else:
    log('threadSafeLogging disabled')
    mtx = fakeMutex()
        
@profiler
def normalize_header(header):
    if header.isupper() and (header[0].isalpha() or header[0] == '_'):
        if cfg('lowercase-columns', False):
            h = header.lower()
        else:
            h = header
    else:
        h = '"%s"' % (header)
        
    return h
        
def securePath(filename, backslash = False):

    if filename is None:
        return None
    # apparently filename is with normal slashes, but getcwd with backslashes on windows, :facepalm:
    cwd = os.getcwd()
    
    if backslash:
        cwd = cwd.replace('\\','/') 
    
    #remove potentially private info from the trace
    fnsecure = filename.replace(cwd, '..')
    
    return fnsecure
    
@profiler
def safeBool(s):
    if type(s) == str:
        return False if s.lower().strip() == 'false' else True
    else:
        return s
    
@profiler
def safeInt(s, default = 0):
    
    try:
        i = int(s)
    except ValueError as e:
        log('error converting %s to integer: %s' % (s, str(e)), 2)
        return default
        
    return i
    

@profiler
def parseAlertString(value):
    '''parses alert string to extract filename and volume
    
        format: '{alert:soundFile!volume}'
        
        soundFile is uptional, could be just a filname or path
        volume - 2-digits, will be converted to integer
        
        alert - cfg('alertTriggerOn')
        if the string is not wrapped in {} - no any parsing will be executed, only sound file will be extracted
    '''
        
    if __alertReg__ is None:
        return None, None
    
    alertStr = cfg('alertTriggerOn')
    volume = cfg('alertVolume', 80)
    vol = None
    sound = ''
    
    if value[0] == '{' and value[-1:] == '}':
        #ml = re.search('^{alert(:[^!]*)?(!\d{1,3})?}$', value)
        ml = __alertReg__.search(value)
        
        if ml is None:
            return None, None
            
        for g in ml.groups():
            if g and g[0] == ':':
                sound = g[1:]

            if g and g[0] == '!':
                vol = g[1:]
            
        if vol is not None:
            volume = int(vol)
        
    else:
        if value == alertStr:
            sound = ''
        else:
            return None, None
            
    log(f'alert parsed: {sound}/{volume}', 5)
    
    return sound, volume 
    
@profiler
def initLocale():
    '''
        sets the locale based configuration
        
        sets thousands_separator and decimal_point globals
    '''
    
    global localeCfg
    global thousands_separator
    global decimal_point
    global decimal_digits
    global newNumbersFormatting

    localeCfg = cfg('locale', '')
    if localeCfg != '':
        log(f'Locale setting to: {localeCfg}')
        try:
            locale.setlocale(locale.LC_ALL, localeCfg)
        except Exception as e:
            localeCfg = ''
            log(f'[!] Locale error: {str(e)}, {localeCfg}', 2)
            log(f'[!] List of supported locales: {str(list(locale.locale_alias.keys()))}', 2)
                
    # just once now, 2022-10-03
        
    if localeCfg == '':
        locale.setlocale(locale.LC_ALL, localeCfg)
        
    newNumbersFormatting = cfg('newNumbersFormatting', True)
        
    thousands_separator = cfg('thousandsSeparator') or locale.localeconv()['thousands_sep']
    decimal_point = cfg('decimalPoint') or locale.localeconv()['decimal_point']
    decimal_digits = cfg('decimalDigits', 6)
    
    log(f'Locale thousands separator is: [{thousands_separator}], decimal point: [{decimal_point}]')
    
def initGlobalSettings():
    global configStats
    global cfg_logmode
    global cfg_loglevel
    
    if cfg('dev'):
        configStats['dummy'] = 0
        
    cfg_logmode = cfg('logmode')
    cfg_loglevel = cfg('loglevel', 3)
    
    initLocale()
    
initGlobalSettings()
    
def intToStr(x, grp = True):
    #only integers, only >= 0
    
    #separator = '\xa0'
    global thousands_separator
    
    if grp == False:
        return str(x)
    
    #print('int processing:', x)

    '''
    if type(x) is not int:
        raise TypeError(f'Not an integer: {x}, {type(x)}')
    '''

    if x < 1000:
        return str(x)
    else:
        x, r = divmod(x, 1000)
        #return intToStr(x) + '\xa0' + str(r)
        #x, r = divmod(x, 1000)
        #return intToStr(int(x/1000)) + '\xa0' + '%03d' % (x % 1000)    
        return f'{intToStr(x)}{thousands_separator}{r:03}'

def saneNumberToStr(x, grp=True, digits=None):

    global decimal_point
            
    #bkp = x
    
    if x < 0:
        x = -x
        sign = '-'
    else:
        sign = ''
    
    fr = x%1
    x = int(x)
    
    #print(f'{bkp} ==> sign:{sign} int: {x} dec: {fr}, {grp=}, {digits=}')
    
    if fr:
        if digits:
            frs = decimal_point + f'{fr:.{digits}f}'[2:]        # duplicated formula, but a bit different case
        elif digits == 0:
            frs = ''
        else:
            frs = decimal_point + f'{fr:.{decimal_digits}f}'.rstrip('0').rstrip(decimal_point)[2:]
    else:
        if digits:
            frs = decimal_point + f'{fr:.{digits}f}'[2:]        # duplicated formula, but a bit different case
        else:
            frs = ''
    
    #print(f'{bkp} --> int={intToStr(x, grp)}, dec:{frs}')
            
    return sign + intToStr(x, grp) + frs

@profiler
def numberToStrCSV(num, grp = True):
    '''
        formats numbers according to locale
            - thouthand groupping
            - decimal point
            - truncates zeroes in the end of the fractional
    '''
    
    global newNumbersFormatting
    
    if newNumbersFormatting:
        return saneNumberToStr(num, grp)

    global localeCfg
    global thousands_separator
    global decimal_point
    
    '''
    if localeCfg is None:
        
        localeCfg = cfg('locale', '')
                
        if localeCfg != '':
            try:
                locale.setlocale(locale.LC_ALL, localeCfg)
            except Exception as e:
                localeCfg = ''
                log('[!] '+ str(e))
                
        # just once now, 2022-10-03
        locale.setlocale(locale.LC_ALL, localeCfg)
    '''
    
    if localeCfg is None:
        initLocale()
        
    
    if num is None:
        return '?'

    #fmt = '%g'

    fmt = '%f'
    s = locale.format_string(fmt, num, grouping = grp)
    
    # trim zeroes for f, even integers have .000000 after %f formatting
    
    s = s.rstrip('0').rstrip(decimal_point)

    
    return s

@profiler
def numberToStr(num, d=0):
    '''
        in consoles it is used for integer type only
        for decimals numberToStrCSV used (for some reason)
        
        never used for copy
        
        this one is very straight-forward:
        when d is not zero - it will result in fixed number of digits after decimal point
        
        allways uses thouthands groupping
        mainly used for charts, not results render
    '''

    global newNumbersFormatting

    if newNumbersFormatting:
        return saneNumberToStr(num, grp=True, digits=d)
        
    global localeCfg
    global thousands_separator
    global decimal_point

    '''
    if localeCfg is None:
        localeCfg = cfg('locale', '')
        if localeCfg != '':
            log(f'Locale setting to: {localeCfg}')
            try:
                locale.setlocale(locale.LC_ALL, localeCfg)
            except Exception as e:
                localeCfg = ''
                log(f'[!] Locale error: {str(e)}, {localeCfg}', 2)
                log(f'[!] List of supported locales: {str(list(locale.locale_alias.keys()))}', 2)
                
        # just once now, 2022-10-03
        locale.setlocale(locale.LC_ALL, localeCfg)
        thousands_separator = locale.localeconv()['thousands_sep']
        decimal_point = locale.localeconv()['decimal_point']
        log(f'Locale thousands separator is: [{thousands_separator}], decimal point: [{decimal_point}]')
    '''
    if localeCfg is None:
        initLocale()
    
    if num is None:
        return '?'
        
    fmt = '%.{0}f'.format(d)
        
    s = locale.format_string(fmt, num, grouping=True)
    
    #print(f'{num} --> {s}')
    
    return s

@profiler
def formatTimeShort(t):
    (ti, ms) = divmod(t, 1)
    
    if ti < 60:
        
        s = str(round(t)) + ' sec'
        
    elif ti < 3600:
        format = '%M:%S'
            
        s = time.strftime(format, time.gmtime(ti))
    else:
        format = '%H:%M:%S'
        s = time.strftime(format, time.gmtime(ti))
    
    return s

@profiler
def formatTime(t, skipSeconds = False, skipMs = False):
    
    (ti, ms) = divmod(t, 1)
    
    ms = round(ms, 3)
    
    if ms == 1:
        ti += 1
        ms = '0'
    else:
        ms = str(int(ms*1000)).rstrip('0')
    
    if ti < 60:
        
        s = str(round(t, 3)) + ' s'
        
    elif ti < 3600:
        format = '%M:%S'

        msStr = '.%s' % ms if not skipMs else ''
            
        s = time.strftime(format, time.gmtime(ti)) + msStr
    else:
        format = '%H:%M:%S'
        msStr = '.%s' % ms if not skipMs else ''
        s = time.strftime(format, time.gmtime(ti)) + msStr
    
    if not skipSeconds:
        s += '   (' + str(round(t, 3)) + ')'
    
    return s

@profiler
def timestampToStr(ts, trimZeroes = True):

    if trimZeroes:
        if ts.microsecond:
            s = ts.strftime('%Y-%m-%d %H:%M:%S.%f').rstrip('0')
        else:
            s = ts.strftime('%Y-%m-%d %H:%M:%S')
    else:
        s = ts.strftime('%Y-%m-%d %H:%M:%S.%f')
        
    return s
