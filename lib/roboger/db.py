__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018 Altertech Group"
__license__ = "See https://www.roboger.com/"
__version__ = "1.0.0"

import logging
import roboger.core

db_engine = None

db = None

db_host = None

db_user = None

db_password = None

db_name = None


def update_config(cfg):
    global db_engine, db, db_host, db_user, db_password, db_name
    try:
        db_engine = cfg.get('db', 'engine')
    except:
        db_engine = 'mysql'
    try:
        db_host = cfg.get('db', 'host')
    except:
        db_host = '127.0.0.1'
    try:
        db_user = cfg.get('db', 'user')
    except:
        db_user = 'root'
    try:
        db_password = cfg.get('db', 'password')
    except:
        db_password = ''
    try:
        db_name = cfg.get('db', 'database')
    except:
        db_name = 'roboger'
    try:
        if db_engine == 'sqlite' and db_name[0]!='/':
            db_name = roboger.core.dir_roboger + '/' + db_name
    except:
        pass
    db = connect()
    if db:
        if db_engine == 'sqlite':
            logging.debug('database connected: sqlite:%s' % db_name)
        else:
            logging.debug('database connected: %s:%s@%s/%s' % \
                    (db_engine, db_user, db_host, db_name))
    else:
        logging.error('Database connection error %s:%s@%s/%s' % \
                (db_engine, db_user, db_host, db_name))
        return False
    return True


def connect():
    if db_engine == 'sqlite':
        import sqlite3
        return True
    elif db_engine == 'mysql':
        import MySQLdb
        try:
            db = MySQLdb.connect(
                db_host, db_user, db_password, db_name, charset='utf8')
            return db
        except:
            roboger.core.log_traceback()
            return None
    else:
        return None


def check(dbconn=None):
    if db_engine == 'sqlite': return True
    elif db_engine == 'mysql':
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
    if db_engine == 'sqlite':
        return sql.replace('%s', '?')
    else:
        return sql


def query(sql, args=(), do_commit=False, dbconn=None):
    global db
    try:
        if db_engine == 'sqlite':
            import sqlite3
            dbconn = sqlite3.connect(db_name)
            cursor = dbconn.cursor()
        else:
            if dbconn:
                cursor = dbconn.cursor()
            else:
                cursor = db.cursor()
        cursor.execute(prepare_sql(sql), args)
    except (AttributeError, MySQLdb.OperationalError):
        roboger.core.log_traceback()
        if dbconn:
            dbconn = connect()
            if not dbconn: return None
        else:
            db = connect()
            if not db: return None
        try:
            if dbconn:
                cursor = dbconn.cursor()
            else:
                cursor = db.cursor()
            cursor.execute(sql, args)
        except:
            return None
    except:
        cursor.close()
        if dbconn:
            dbconn.rollback()
        else:
            db.rollback()
        raise
    if do_commit:
        return commit(cursor, dbconn)
    return cursor

def free(dbconn=None):
    if db_engine != 'sqlite': return
    try:
        if dbconn: dbconn.close()
    except:
        roboger.core.log_traceback()


def commit(c=None, dbconn=None):
    try:
        if dbconn: dbconn.commit()
        else: db.commit()
        if c:
            lrid = c.lastrowid
            c.close()
            return lrid
        if db_engine == 'sqlite':
            dbconn.close()
        return True
    except:
        if db_engine == 'sqlite':
            dbconn.close()
        roboger.core.log_traceback()
        return False
