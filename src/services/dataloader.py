import Cookie
import StringIO
import csv
import httplib
import os
import sys
import traceback
import types
import struct
import zlib
import logging
import services.json as json
import simplejson
import datetime

import google
from google.appengine.api import datastore
from google.appengine.api import datastore_types
from google.appengine.ext import webapp
from google.appengine.ext.bulkload import constants

import services.securityservice as securityservice
import services.metadataservice as metadataservice
import services.datamodel as datamodel
import services.utils as utils
import services.constants as constants 
import services.importhelpers as importhelpers

from google.appengine.ext import bulkload
from google.appengine.ext import db,search
from google.appengine.api import memcache
import wsgiref.handlers

class DataImporter:
    
    __profile = None
    __kind = None
    __req = None   
    __profile_obj = None
    
    def __init__(self, req, profile):
        self.__profile  = profile
        self.__req   = req
        self.__profile_obj = db.get(db.Key.from_path('ImportProfile', self.__profile))
        if self.__profile_obj.field_mapping:
            self.__profile_obj._fields = db.get(self.__profile_obj.field_mapping)
        
    def import_data(self, data):
        '''
        Import data
        '''            
        if not self.__profile_obj:
            logging.error("Invalid profile")
            return ['profile is invalid']
         
        self.__kind = self.__profile_obj.type_of
                    
        buffer = StringIO.StringIO(data)
        reader = csv.reader(buffer, skipinitialspace=True)
    
        try:
          csv.field_size_limit(800000)
        except AttributeError:
          pass
    
        return self.LoadEntities(self.IterRows(reader))

    def GetImportStatementForType(self, type_info):
        ret = 'import_str'
        if type_info.import_type:
            ret = type_info.import_type
        return ret
    
    def CreateEntity(self, values):
        #logging.info('Creating entity: %s'  % (self.__kind))
        
        props = []
        for ep in self.__profile_obj._fields:
            if not ep:
                logging.error("Error: bad property mapping in import profile")
            import_statement = self.GetImportStatementForType(ep.type_info)
            #logging.info(import_statement)
            converter = utils.loadImportConverter(import_statement)            
            props.append( (ep.name, converter) )   
        
        key_name = utils.new_key()
        if props[0][0] == 'name':
            key_name = utils.format_key(values[0])
        
        entity = datastore.Entity(self.__kind, name=key_name)
        for (name, converter), val in zip(props, values):
          #logging.info('%s = %s' % (name, val))
          if converter is bool and val.lower() in ('0', 'false', 'no'):
              val = False
          if name != 'name':
              entity[name] = converter(val)
          
        entity['org']           = self.__req.org.name
        entity['owner']         = self.__req.user.name
        entity['is_deleted']    = False
        entity['created']       = datetime.datetime.now()
        entity['updated']       = datetime.datetime.now()
        entity['bookmark']      = utils.bookmark_for_kind(self.__kind, self.__req.user.name, entity['updated'])
        #logging.info('Data bookmark=' + entity['bookmark'])
        return [entity]

    def IterRows(self, reader):
        line_num = 1
        for columns in reader:
          yield (line_num, columns)
          line_num += 1
          
    def LoadEntities(self, iter):
        entities = []
        output = []
        for line_num, columns in iter:
          if columns:
            try:
              #logging.info('\nLoading from line %d...' % line_num)
              new_entities = self.CreateEntity(columns)
              if new_entities:
                entities.extend(new_entities)
              #logging.info('done.')
            except:
              stacktrace = traceback.format_exc()
              logging.info('error:\n%s' % stacktrace)
              return output 
        
        datastore.Put(entities)
            
        return output
    
