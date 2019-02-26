__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018-2019 Altertech Group"
__license__ = "Apache License 2.0"
__version__ = "1.0.0"

import logging
import roboger.core

from types import SimpleNamespace

database = SimpleNamespace(
    connection=None,
    engine=None,
    host=None,
    user=None,
    password=None,
    name=None)


def update_config(cfg):
    try:
        database.engine = cfg.get('db', 'engine')
    except:
        database.engine = 'sqlite'
    try:
        database.host = cfg.get('db', 'host')
    except:
        database.host = '127.0.0.1'
    try:
        database.user = cfg.get('db', 'user')
    except:
        database.user = 'root'
    try:
        database.password = cfg.get('db', 'password')
    except:
        database.password = ''
    try:
        database.name = cfg.get('db', 'database')
    except:
        database.name = 'roboger'
    try:
        if database.engine == 'sqlite' and database.name[0] != '/':
            database.name = roboger.core.dir_roboger + '/' + database.name
    except:
        pass
    database.connection = connect()
    if database.connection:
        if database.engine == 'sqlite':
            logging.debug('database connected: sqlite:%s' % database.name)
        else:
            logging.debug('database connected: %s:%s@%s/%s' % \
                    (database.engine, database.user, database.host, database.name))
    else:
        logging.error('Database connection error %s:%s@%s/%s' % \
                (database.engine, database.user, database.host, database.name))
        return False
    return True


def connect():
    if database.engine == 'sqlite':
        import sqlite3
        return True
    elif database.engine == 'mysql':
        import MySQLdb
        try:
            database.connection = MySQLdb.connect(
                database.host,
                database.user,
                database.password,
                database.name,
                charset='utf8')
            return database.connection
        except:
            roboger.core.log_traceback()
            return None
    else:
        return None


def check(dbconn=None):
    if database.engine == 'sqlite': return True
    elif database.engine == 'mysql':
        try:
            if dbconn:
                cursor = dbconn.cursor()
            else:
                cursor = db.cursor()
            cursor.execute('select 1')
            cursor.close()
        except:
            logging.debug('database check: server has gone away')
            return False
    else:
        return False


def prepare_sql(sql):
    if database.engine == 'sqlite':
        return sql.replace('%s', '?')
    else:
        return sql


def query(sql, args=(), do_commit=False, dbconn=None):
    if database.engine == 'sqlite':
        import sqlite3
        oe = sqlite3.OperationalError
    elif database.engine == 'mysql':
        import MySQLdb
        oe = MySQLdb.OperationalError
    try:
        if database.engine == 'sqlite':
            dbconn = sqlite3.connect(database.name)
            cursor = dbconn.cursor()
        else:
            if dbconn:
                cursor = dbconn.cursor()
            else:
                cursor = database.connection.cursor()
        cursor.execute(prepare_sql(sql), args)
    except (AttributeError, oe):
        roboger.core.log_traceback()
        if dbconn:
            dbconn = connect()
            if not dbconn: return None
        else:
            database.connection = connect()
            if not database.connection: return None
        try:
            if dbconn:
                cursor = dbconn.cursor()
            else:
                cursor = databse.connection.cursor()
            cursor.execute(sql, args)
        except:
            return None
    except:
        cursor.close()
        if dbconn:
            dbconn.rollback()
        else:
            database.connection.rollback()
        raise
    if do_commit:
        return commit(cursor, dbconn)
    return cursor


def free(dbconn=None):
    if database.engine != 'sqlite': return
    try:
        if dbconn: dbconn.close()
    except:
        roboger.core.log_traceback()


def commit(c=None, dbconn=None):
    try:
        if dbconn: dbconn.commit()
        else: database.connection.commit()
        if c:
            lrid = c.lastrowid
            c.close()
            return lrid
        if database.engine == 'sqlite':
            dbconn.close()
        return True
    except:
        if database.engine == 'sqlite':
            dbconn.close()
        roboger.core.log_traceback()
        return False
