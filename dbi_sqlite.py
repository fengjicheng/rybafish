'''
    SQLite database interface implementation
    
    EVN, 2022-11-15
'''

import sqlite3
from datetime import datetime

import utils
from utils import cfg, dbException

from profiler import profiler

from kpis import kpis

import kpiDescriptions
import dpDBCustom

# from dbi_extention import getDBProperties seems not relevant

log = utils.getlog('SQLite')

class sqlite():

    name = 'SLT'
    options = {'keepalive': False, 'largeSQL': False}

    def __init__(self):
        log('Using SQLite as DB driver implementation (SLT)')
        
    def create_connection(self, server, dbProperties = None):
        dbFile = server['host']
        log(f'Open connection: {dbFile}')

        try:
            conn = sqlite3.connect(dbFile, check_same_thread=False)
        except sqlite3.Error as e:
            log(f'Cannot open SQLite source "{dbFile}": {e}', 2)
            raise dbException('Cannot open SQLite source: ' + str(e))

        if dbProperties is not None:
            dbProperties['dbi'] = 'SLT'
            dbProperties['tenant'] = dbFile

        log(f'created connection: {conn}')
        
        return conn
        
    def execute_query(self, connection, sql_string, params):

        log(f'[SQL] {sql_string}', 4)
        
        if params:
            log(f'[SQL] {params}', 4)
        
        try:
            cur = connection.cursor()
            cur.execute(sql_string, params)
            
            rows_tuples = cur.fetchall()

        except sqlite3.Error as e:
            log(f'SQL Executionex ception in: {sql_string}:: {e}', 2)
            raise dbException(f'Cannot execute: {sql_string}:: {e}')

        rows = []

        with profiler('SQLite rows convertion'):
            for r in rows_tuples:
                rows.append(list(r))
                    
        utils.alignTypes(rows)
        
        return rows
       
    '''
    def checkTable(self, conn, tableName):
        r = execute_query(f"select name from sqlite_master where type='table' AND name='?'", [tableName])
        
        if r:
            return True
        else:
            return False
    '''
        
    def destroy(self):
        log('DBI Destroy call...')

    def close_connection(self, connection):
        log('Close the connection', 5)
        connection.close()
        
    '''
        Console specific stuff below
    '''

    def console_connection(self, server):
        conn = self.create_connection(server)
        log(f'Console connection: {conn}')
        return conn

    def drop_statement(self, conn, stid):
        pass
        
    def get_connection_id(self, conn):
        # not sure this makes any sense for sqlite
        return None
    
    def execute_query_desc(self, connection, sql_string, params, resultSize, noLogging=False):
 
        rows = []
        cols = []

        if not noLogging:
            log(f'[SQL] {sql_string}', 4)
            
            if params:
                log(f'[SQL] {params}', 4)
                
        try:
            cur = connection.cursor()
            cur.execute(sql_string, params)
            
            rows_tuples = cur.fetchmany(resultSize)
            
            with profiler('SQLite rows convertion'):
                for r in rows_tuples:
                    rows.append(list(r))
            
            '''
            if len(rows):
                for i in range(len(cur.description)):
                    typeCode = scanType(rows, i)
                    #log(f'{cur.description[i][0]:32} {typeCode:3}', 5)
                    cols.append((cur.description[i][0], typeCode, None))
            '''
            
            if rows:
                colTypes = utils.alignTypes(rows)
                
                log(f'{colTypes=}', 5)
                
                #assert len(cur.description) == len(colTypes) +1, f'len(cur.description) == len(colTypes) --> {len(cur.description)} != {len(colTypes)}'
                if len(cur.description) != len(colTypes):
                    raise dbException(f'len(cur.description) == len(colTypes) --> {len(cur.description)} != {len(colTypes)}')
                
                for i in range(len(cur.description)):
                    cols.append((cur.description[i][0], colTypes[i][0], None))
            
            else:
                if cur.description:
                    for c in cur.description:
                        cols.append((c[0], -1, None))

        except sqlite3.Error as e:
            log(f'SQL Execution exception in: {sql_string}:: {e}', 2)
            raise dbException(f'Cannot execute: {sql_string}:: {e}')

        return [rows], [cols], None, None
        
    def ifLOBType(self, t):
        return False

    def ifRAWType(self, t):
        return False
        
    def ifNumericType(self, t):
        if t in (1, 2):
            return True
        else:
            return False

    def ifDecimalType(self, t):
        if t == 2:
            return True
        else:
            return False
        
    def ifVarcharType(self, t):
        if t == 3:
            return True
        else:
            return False
        
    def ifTSType(self, t):
        if t == 4:
            return True
        else:
            return False

    def ifBLOBType(self, t):
        log('ifBLOBType', 5)
        return False
        
            
    '''
        Charts related stuff below
        
        Only required if somehow different from HANA db
    '''
            
    def checkTable(self, conn, table):
        sql = "select count(*) from sqlite_master where type in ('table', 'view') and lower(name) = ?"

        cnt = self.execute_query(conn, sql, [table.lower()])
        
        if cnt and cnt[0][0]:
            return True
            
        return False
    
    def initHosts(self, conn, dpidx, dbProperties=[]):
        '''
            fills up the hosts list, returns nothing
        '''
        
        hosts = []
        
        # select count(*) from sqlite_master where type in ('table', 'view') and lower(name) = 'm_load_history_host'
        
        log('initHosts customization impl...', 4)
                
        
        host_load_history = self.checkTable(conn, 'm_load_history_host')
        service_load_history = self.checkTable(conn, 'm_load_history_service')

        rows = [] # host, port, from, to
        
        if host_load_history:
            #hostRows = self.execute_query(conn, "select distinct host, '' from m_load_history_host order by 1", [])
            hostRows = self.execute_query(conn, "select host, '', min(time), max(time) from m_load_history_host group by host order by 1", [])
            
            if hostRows:
                rows = rows + list(hostRows)
                
        if service_load_history:
            srvcRows = self.execute_query(conn, "select host, port, min(time), max(time) from m_load_history_service group by host, port order by 1, 2", [])
            
            if srvcRows:
                rows = rows + list(srvcRows)
                
        # by the way for proper ordering reorder of the rows array woold be good to have here
        
        if not rows:
            rows = [['', '']]  # tenant property is a filename for SLT dbi
            
        for r in rows:
            log(f'hosts intermediate table: {r}', 5)
            
        #build hosts based on rows
        for i in range(0, len(rows)):
            
            ten = str(dbProperties.get('tenant'))
            srv = None
                
            hosts.append({
                        'db': ten,
                        'host': rows[i][0],
                        'service': srv,
                        'port': str(rows[i][1]),
                        'from': rows[i][2],
                        'to': rows[i][3],
                        'dpi': dpidx
                        })

        '''
        '
        '   and the KPIs stuff below
        '
        '''
        
        def exists(source, name):
            '''
                checks if the source.name pair exists in existingKpis
                
                source - lowercased table name
                name - lowercased column(kpi) name
                
                returns true/false
            '''
            for r in existingKpis:
                if r[0].lower() == source and r[1].lower() == name:
                    break
            else:
                return False
            
            return True
            
        log('initKPIs customization impl...', 4)
        
        existingKpis = []
        
        if host_load_history:
            rows, cols, _, _ = self.execute_query_desc(conn, 'select * from m_load_history_host limit 1', [], 1)
            if cols:
                for c in cols[0]:
                    if c[0].lower() not in ('time', 'host'):
                        existingKpis.append(('m_load_history_host', c[0]))

        if service_load_history:
            rows, cols, _, _ = self.execute_query_desc(conn, 'select * from m_load_history_service limit 1', [], 1)
            
            if cols:
                for c in cols[0]:
                    if c[0].lower() not in ('time', 'host', 'port'):
                        existingKpis.append(('m_load_history_service', c[0]))
                    
        rows = []
        
        #now intersect the default kpis list with identified existing columns
        for r in kpis:            
            if exists(r[1].lower(), r[2].lower()):
                rows.append(r)

        #very similar logic called in default dpDB processing... somehow combine in one call?
        hostKPIs = []
        srvcKPIs = []
        kpiStylesNNN = {'host':{}, 'service':{}}

        kpiDescriptions.initKPIDescriptions(rows, hostKPIs, srvcKPIs, kpiStylesNNN)

        # just load all custom KPIs, deal with sources verification later
        log('load custom KPIs...')
        try:
            dpDBCustom.scanKPIsN(hostKPIs, srvcKPIs, kpiStylesNNN)
        except customKPIException as e:
            log('[e] error loading custom kpis')
            log('[e] fix or delete the problemmatic yaml for proper connect')
            raise e
            
        kpiDescriptions.clarifyGroups(kpiStylesNNN['host'])
        kpiDescriptions.clarifyGroups(kpiStylesNNN['service'])
        
        hostKPIsList = []
        hostKPIsStyles = []
        
        for host in hosts:
            if host['port'] == '':
                hostKPIsList.append(hostKPIs)
                hostKPIsStyles.append(kpiStylesNNN['host'])
            else:
                hostKPIsList.append(srvcKPIs)
                hostKPIsStyles.append(kpiStylesNNN['service'])

        return hosts, hostKPIsList, hostKPIsStyles
