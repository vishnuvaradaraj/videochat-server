
import uuid
import md5
import base64
import settings
import cPickle as pickle
import logging
import sys
import new

import datetime
import time

import json
import simplejson

import dateutil
import pytz
import hashlib

import urllib
import base64
from google.appengine.api import urlfetch

import re
#from django.http import HttpResponseRedirect, HttpResponse


from google.appengine.ext import search, db
from google.appengine.api import memcache
from google.appengine.api import datastore

import services.datamodel as datamodel
import services.generalcounter as generalcounter

URL_PREFIX      = 'http://parabayapps.appspot.com'
HOME_PREFIX     = 'http://www.parabay.com'
SENDER_EMAIL    = 'support@parabay.com'

def format_perm(keys):
    return ".".join(keys)

def format_key(key):
    return 'k' + key

def new_key():
    return format_key(str(uuid.uuid1()))

def loadImportConverter(name):
    mod = getattr(__import__('services'), 'importhelpers')
    return getattr(mod, name)

def import_data_module(modname):
    mod = None
    
    if hasattr(sys.modules, modname):
        mod = sys.modules[modname]
    else:
        mod = new.module(modname.encode('latin-1'))
        mod.__file__ = "__datamodel__BaseDataModel__"
        sys.modules[modname] = mod

    return mod
        
def loadModuleType(modname, attname):
    mod = import_data_module(modname)
    if not mod:
        return None
    
    cls = None
    if not hasattr(mod, attname):
        cls = new.classobj(attname.encode('latin-1'),(datamodel.BaseDataModel,),{})
        mod.__dict__[attname]= cls
    else:
        cls = getattr(mod, attname)

    return cls    

def handle_entity(entity, kind, props):
    ent = datastore.Entity(kind, name = new_key())
    for k,v in props:
        if entity.has_key(k):
            val = entity[k]
            ent[k] = val
    return ent

def handle_entity_with_name_key(entity, kind, props):
    ent = datastore.Entity(kind, name = entity['name'])
    for k,v in props:
        if entity.has_key(k):
            val = entity[k]
            ent[k] = val
    return ent

def handle_entity_with_name_key_custom(entity, kind, props, key_name):
    ent = datastore.Entity(kind, name = key_name)
    for k,v in props:
        if entity.has_key(k):
            val = entity[k]
            ent[k] = val
    return ent

def find_entity_by_name(kind, name):
    '''
    Find an entity by name.
    '''
    return db.get(db.Key.from_path(kind.__name__, name))

def delete_all_entities(kind, max_count=100):
    '''
    Delete all entity by name.
    '''
    logging.info(str(kind))
    query = kind.all()
    models = query.fetch(max_count)
    for m in models:
        m.delete()

def encode(obj):
    "Encodes the object and md5 encoded as a string."
    token = pickle.dumps(obj)
    token_md5 = md5.new(token + settings.SECRET_KEY).hexdigest()

    return base64.urlsafe_b64encode(token + token_md5).replace('=', '%3D')

def decode(blob):
    encoded_data = base64.decodestring(blob.replace('%3D', '='))
    token, tamper_check = encoded_data[:-32], encoded_data[-32:]
    if md5.new(token + settings.SECRET_KEY).hexdigest() != tamper_check:
        raise ValueError("User tampered with session info.")
    obj = pickle.loads(token)
    return obj  

def encode_password(raw_password):
    import sha, random
    algo = 'sha1'
    salt = sha.new(str(random.random())).hexdigest()[:5]
    hsh = sha.new(salt+raw_password).hexdigest()
    return '%s$%s$%s' % (algo, salt, hsh)
   
def get_l10n(key, lang, org=None):
    ret = key
    query = datamodel.L10n.all()
    query.filter('name =', key)
    query.filter('lang =', lang)
    l10n = query.get()
    if l10n:
        ret = l10n.value
    return ret

def url_prefix():
    return URL_PREFIX

def rfc3339date(date):
  """Formats the given date in RFC 3339 format for feeds."""
  if not date: return ''
  date = date + datetime.timedelta(seconds=-time.timezone)
  if time.daylight:
    date += datetime.timedelta(seconds=time.altzone)
  return date.strftime('%Y-%m-%dT%H:%M:%SZ')

def set_cookie(response, key, value, expire=None):
    if expire is None:
        max_age = 7*24*60*60  #7 days
    else:
        max_age = expire
    expires = datetime.datetime.strftime(datetime.datetime.utcnow() + datetime.timedelta(seconds=max_age), "%a, %d-%b-%Y %H:%M:%S GMT")
    response.set_cookie(key, value, max_age=max_age, expires=expires)
    return response
    
def format_memcache_key(keys):
    return "_".join(keys)

def check_memcache(keys):
    key     = format_memcache_key(keys)
    data    = memcache.get(key)
    return None #data

def set_memcache(keys, value, time=0):
    key     = format_memcache_key(keys)
    logging.info("Setting cache-key:" + key)
    memcache.set(key, value, time)

def get_request_value(request, name, default=None):
    ret = None
    try:
        ret = request.REQUEST[name]
    except KeyError:
        if request.COOKIES.get(name):
            ret = request.COOKIES[name]
        else:
            ret = default
    return ret 

def encode_json(request, obj):
    callback = get_request_value(request, 'callback')
    if callback:
        ret = callback + '(' + json.encode(obj) + ');'
    else:
        ret = json.encode(obj)
    return ret

def remove_unsafe(s):
    subber = re.compile(r"[^\ -\~]").sub
    return subber("", str(s))


def send_push_notification(deviceToken, alertMsg, badgeNumber, schedule):
    
    ret = None
    
    UA_API_APPLICATION_KEY = 'skDMWRt2SkC27yiX7Rhp1g' 
    UA_API_APPLICATION_PUSH_SECRET = 'apnPdkC-RbitsnK2elxDlw' 
    url = 'https://go.urbanairship.com/api/push/'
    
    auth_string = 'Basic ' + base64.encodestring('%s:%s' % (UA_API_APPLICATION_KEY,UA_API_APPLICATION_PUSH_SECRET))[:-1]        
    body = simplejson.dumps(   {"schedule_for": schedule.strftime('%Y-%m-%d %H:%M:%S'), "aps": {"badge": badgeNumber, "alert": alertMsg}, "device_tokens": [deviceToken]}  )
    logging.info(body)
    
    if schedule > datetime.datetime.now():
        logging.info('Sending notification: ' + deviceToken)
        
        data = urlfetch.fetch(url, headers={'content-type': 'application/json','authorization' : auth_string}, payload=body,method=urlfetch.POST)
        if data.status_code == 200:
            logging.info("Remote Notification successfully sent to UrbanAirship "+str(data.status_code))
            ret = data.content
        else:
            logging.error("Unknown error sending Remote Notification: "+str(data.status_code))

    return ret

def send_batch_push_notification(message):
    
    ret = None
    
    UA_API_APPLICATION_KEY = 'Cfwn1otKQ8m8g20RtQZWIw' 
    UA_API_APPLICATION_PUSH_SECRET = 'aKYsOYjLSt-KQXQcb5bhMA' 
    url = 'https://go.urbanairship.com/api/push/batch/'
    
    auth_string = 'Basic ' + base64.encodestring('%s:%s' % (UA_API_APPLICATION_KEY,UA_API_APPLICATION_PUSH_SECRET))[:-1]        
    body = simplejson.dumps(   message  )
    logging.info(message)
        
    data = urlfetch.fetch(url, headers={'content-type': 'application/json','authorization' : auth_string}, payload=body,method=urlfetch.POST)
    if data.status_code == 200:
        logging.info("Remote Notification successfully sent to UrbanAirship "+str(data.status_code))
        ret = data.content
    else:
        logging.error("Unknown error sending Remote Notification: "+str(data.status_code))

    return ret

def getImportStatementForType(type_name):
    ret = 'import_str'
    type_info = find_entity_by_name(datamodel.TypeInfo, type_name)
    if type_info and type_info.import_type:
        ret = type_info.import_type
    return ret
    
def build_query_for_class(klazz, q):
    ret = klazz.all()
    for f in q['filters']:
        import_statement = getImportStatementForType(f['type'])
        converter = loadImportConverter(import_statement)  
        val = converter(f['param'])            
        ret.filter(f['condition'], val)
        
    for o in q['orders']:
        ret = ret.order(o)
    return ret

def bookmark_for_kind(name, owner, now=None):
    if now is None:
        now = datetime.datetime.now()
    generalcounter.increment(name)
    count = generalcounter.get_count(name)
    bookmark = now.isoformat()[0:19] + '|' + hashlib.md5(owner + '|' + str(count)).hexdigest()
    #logging.info('creating bookmark: %s - %s' % (count, bookmark))
    return bookmark
