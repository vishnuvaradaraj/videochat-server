import sys
import os
import logging
import traceback
import StringIO
import datetime
import datamodel
import cPickle as pickle

from google.appengine.ext import db,search
from google.appengine.api import memcache

class PersistentCache(object):
    '''
    Provide caching service
    '''
    @staticmethod
    def cacheItem(key, value):
        '''
        Add item to cache
        '''
        if isinstance(key, list):
            key = ".".join(key)
            
        query = datamodel.CacheEntry.all()
        query.filter('name =', key)
        
        entries = query.fetch(1)
        
        if (not entries) or (len(entries) < 1):
            entry = datamodel.CacheEntry()
        else:
            entry = entries[0]
        
        entry.name = key
        
        if isinstance(value, str):
            entry.value = value
            entry.format = 'string'
        else:
            entry.value = pickle.dumps(value)
            entry.format = 'pickle'
            
        entry.put()

    @staticmethod
    def lookupItem(key):
        '''
        Lookup item in cache
        '''
        if isinstance(key, list):
            key = ".".join(key)
            
        query = datamodel.CacheEntry.all()
        query.filter('name =', key)
        
        entry = query.get()
        
        ret = None
        if entry:
            if entry.format == 'string' or (not entry.format):
                ret = entry.value
            else:
                ret = pickle.loads(entry.value)
        
        return ret
