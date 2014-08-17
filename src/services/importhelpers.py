
import sys
import traceback
import logging

import time, datetime
import utils

from google.appengine.ext import bulkload
from google.appengine.api import datastore_types
from google.appengine.ext import search
from google.appengine.ext import db

from feed.date import rfc3339

def _date_to_datetime(value):
  assert isinstance(value, datetime.date)
  return datetime.datetime(value.year, value.month, value.day)

def _time_to_datetime(value):
  assert isinstance(value, datetime.time)
  return datetime.datetime(1970, 1, 1,
                           value.hour, value.minute, value.second,
                           value.microsecond)

def import_int(x):
    ret = (int(x)) if x != 'NULL' else 0
    return ret

def import_bool(x):
    try:
        ret = (bool(int(x))) if x != 'NULL' else None
    except Exception, e:
	    ret = (bool(x)) if x != 'NULL' else None
    return ret

def import_str(x):
    ret = (str(x)) if x != 'NULL' else None
    return ret

def import_text(x):
    ret = (db.Text(x)) if x != 'NULL' else None
    return ret

def import_datetime(x):
    ret = (datetime.datetime.fromtimestamp(rfc3339.tf_from_timestamp(x))) if (x != 'NULL' and len(x)>0) else None
    return ret

def import_float(x):
    ret = (float(x)) if x != 'NULL' else None
    return ret

def import_password(x):
    ret = utils.encode_password(x)
    return ret

def import_perm_key(x):
    ret = None
    if x != 'NULL' and len(x) > 0:
        result = x.split(':')
        mod = __import__('services.datamodel')
        mod= getattr(mod,'datamodel')
        klazz = getattr(mod, result[0])
        query = klazz.all()
        query.filter('name =', result[1])
        ret = query.get()
    return ret
        
def import_fk(entity, name, klazz):
    if entity[name] != 'NULL' and len(entity[name]) > 0:
        query = klazz.all()
        query.filter('name =', entity[name])
        result = query.get()
        entity[name] = (result.key() if result else None)
    else:
        del entity[name]

def import_fkname(entity, name, kind):
    if entity[name] != 'NULL' and len(entity[name]) > 0:
        entity[name] = db.Key.from_path(kind, entity[name])
    else:
        del entity[name] 
        
def import_list(entity, name, klazz):
    result = []
    if entity[name] != 'NULL' and len(entity[name]) > 0:
        str_list = entity[name].split(';')
        for s in str_list:
            query = klazz.all()
            query.filter('name =', s)
            item = None
            try:
                item = query.get()
            except:
                exc_info = sys.exc_info()
                stacktrace = traceback.format_exception(*exc_info)
                logging.info('Error:\n%s' % stacktrace)
            
            if item:
                result.append(item.key())
                
    if len(result)>0:
        entity[name] = result
    else:
        del entity[name]

def import_fkname_list(entity, name, kind):
    result = []
    if entity[name] != 'NULL' and len(entity[name]) > 0:
        str_list = entity[name].split(';')
        result = [ db.Key.from_path(kind, datakey) for datakey in str_list]
                
    if len(result)>0:
        entity[name] = result
    else:
        del entity[name]
        
def import_str_list(entity, name):
    result = []
    if entity[name] != 'NULL' and len(entity[name]) > 0:
        str_list = entity[name].split(';')
        for s in str_list:
            result.append(s)
                
    if len(result)>0:
        entity[name] = result
    else:
        del entity[name]

time_formats = ['%H:%M', '%H:%M:%S', '%I : %M %p', '%H', '%I %p']

date_formats_with_year = ['%d %m %Y', '%Y %m %d', '%d %B %Y', '%B %d %Y',
                                                  '%d %b %Y', '%b %d %Y',
                          '%d %m %y', '%y %m %d', '%d %B %y', '%B %d %y',
                                                  '%d %b %y', '%b %d %y']

date_formats_without_year = ['%d %B', '%B %d',
                             '%d %b', '%b %d']

def import_time(string):
    string = string.strip()
    if not string: return None
    if string == 'NULL': return None
    
    for format in time_formats:
        try:
            result = time.strptime(string, format)
            return _time_to_datetime(datetime.time(result.tm_hour, result.tm_min))
        except ValueError:
            pass
            
    logging.error('No match for time: %s' % string)            
    raise ValueError()

    
def import_date(string):
    string = string.strip()
    if not string: return None
    if string == 'NULL': return None
    
    string = string.replace('/',' ').replace('-',' ').replace(',',' ')
    
    for format in date_formats_with_year:
        try:
            result = time.strptime(string, format)
            return _date_to_datetime(datetime.date(result.tm_year, result.tm_mon, result.tm_mday))
        except ValueError:
            pass

    for format in date_formats_without_year:
        try:
            result = time.strptime(string, format)
            year = datetime.date.today().year
            return _date_to_datetime(datetime.date(year, result.tm_mon, result.tm_mday))
        except ValueError:
            pass
         
    logging.error('No match for date: %s' % string) 
    raise ValueError()
