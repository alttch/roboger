__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018 Altertech Group"
__license__ = "See https://www.roboger.com/"
__version__ = "0.0.1"

import MySQLdb
import logging
import roboger.core

db = None

db_host = None

db_user = None

db_password = None

db_name = None

def update_config(cfg):
    global db, db_host, db_user, db_password, db_name
    try: db_host = cfg.get('db', 'host')
    except: db_host = '127.0.0.1'
    try: db_user = cfg.get('db', 'user')
    except: db_user = 'root'
    try: db_password = cfg.get('db', 'password')
    except: db_password = ''
    try: db_name = cfg.get('db', 'database')
    except: db_name = 'roboger'
    db = connect()
    if db:
        logging.debug('database connected: %s@%s/%s' % \
                (db_user, db_host, db_name))
    else:
        logging.error('Database connection error %s@%s/%s' % \
                (db_user, db_host, db_name))
        return False
    return True


def connect():
    try:
        db = MySQLdb.connect(db_host, db_user, db_password, db_name)
        return db
    except:
        roboger.core.log_traceback()
        return None


def check(dbconn = None):
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

def query(sql, args = (), do_commit = False, dbconn = None):
    global db
    # print(sql)
    try:
        if dbconn:
            cursor = dbconn.cursor()
        else:
            cursor = db.cursor()
        cursor.execute(sql, args)
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
    if do_commit:
        return commit(cursor, dbconn)
    return cursor


def commit(c = None, dbconn = None):
    try:
        if dbconn: dbconn.commit()
        else: db.commit()
        if c:
            lrid = c.lastrowid
            c.close()
            return lrid
        return True
    except:
        roboger.core.log_traceback()
        return False
