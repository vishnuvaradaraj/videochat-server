import os
import sys
import logging

import wsgiref.handlers

import services.datamodel as datamodel
import services.schemaloader as schemaloader

import services.requestcontext as requestcontext

# You can also use a wildcard import services here.
from services import echoservice, shellservice, metadataservice, dataservice, securityservice, utils, datamodel

from google.appengine.ext import db
from google.appengine.api import memcache

""" Transformation functions """
def transform(req, data, datatype):
  '''
  Transform the GAE data to more friendly version for PyAmf
  '''
  if not isinstance(data, db.Model):
      return data
  
  rd            = {}
  rd['id']      = str(data.key().name())
  
  for key, value in data._dynamic_properties.iteritems():
      if value:
          rd[key] = value
  for key in data._properties.keys():
      if getattr(data, key):
          rd[key] = getattr(data, key)
  return rd

def normalize_results(req, result, datatype):
    '''
    Normalize each GAE data
    '''
    ret = [ transform(req, k, datatype) for k in result if k]
    return ret

def reverse_transform(req, data, datatype):
  '''
  Transform the PyAmf data to GAE data
  '''  
  gae_obj       = None    

  gae_klazz     = utils.loadModuleType(req.metadata.name, datatype)
  
  if ('id' in data):
      key       = data['id']
      key_obj   = db.Key.from_path(datatype, key)
      gae_obj   = db.Model.get(key_obj)
  else:
      key       = utils.new_key()
  
  if not gae_obj:
      gae_obj   = gae_klazz(key_name = key)

  '''
  em = metadataservice.find_entity_metadata(req, datatype)  
  for k in em.entity_property_metadatas(req):
      if data.has_key(k.name) and data[k.name]:
  ''' 
  for k in data.keys():
      val = data[k]
      setattr(gae_obj, k, val)
          
  return gae_obj 

def denormalize_results(req, data, datatype):
    '''
    Normalize each PyAmf data
    '''
    ret = [ reverse_transform(req, k, datatype) for k in data]
    return ret
    
def transform_metadata(entity):
  '''
  Transform the GAE entity to more friendly version for PyAmf
  '''
  if not isinstance(entity, db.Model):
      return entity
  
  rd = {}
  rd['id'] = str(entity.key().name())
  for k in entity.__class__._properties:
    val = getattr(entity, k)
    if isinstance(val, db.Model):
        val = val.key().name()
    elif isinstance(val, db.Key):
        val = val.name()
    elif isinstance(val, list):
        val = []
    rd[k] = val
  return rd

def encode_boolean_properties(entity, properties):
    ret = ""
    for k in properties:
        val = getattr(entity, k)
        if val:
            ret = ret + "1"
        else:
            ret = ret + "0"
    return ret

def transform_metadata_filter(entity, properties, bool_properties=[], include_id=True):
  '''
  Transform the GAE entity to more friendly version for PyAmf
  '''
  if not isinstance(entity, db.Model):
      return entity
  
  rd = {}
  if include_id:
      rd['id'] = str(entity.key().name())
  for k in properties:
    val = getattr(entity, k)
    if isinstance(val, db.Model):
        val = val.key().name()
    elif isinstance(val, db.Key):
        val = val.name()
    elif isinstance(val, list):
        val = []
    rd[k] = val
  rd['_encoded_flags'] = encode_boolean_properties(entity, bool_properties)
  return rd

def normalize_metadata_results(req, result):
    '''
    Normalize each GAE entity
    '''
    ret = [ transform_metadata(k) for k in result ]
    return ret

def normalize_entity_property_metadata_results(req, result):
    '''
    Normalize each GAE entity
    '''
    properties      = ["name", "type_info", "enumeration", "entity_relation", "human_name", "ref_type"]
    bool_properties = ["in_list_view", "in_show_view", "in_edit_view", "is_read_only", "is_primary_key", "is_foreign_key", "is_required", "is_search_key"]
    
    ret = [ transform_metadata_filter(k, properties, bool_properties, False) for k in result ]
    return ret

def normalize_typeinfo_results(req, result):
    '''
    Normalize each GAE entity
    '''
    properties      = ["name", "local_db_type", "reg_exp", "max_length"]
    
    ret = [ transform_metadata_filter(k, properties, [], False) for k in result ]
    return ret

def normalize_l10n_results(req, result):
    '''
    Normalize each GAE entity
    '''
    properties      = ["name", "value"]
    
    ret = [ transform_metadata_filter(k, properties, [], False) for k in result ]
    return ret

def normalize_em_results(req, result):
    '''
    Normalize EntityMetadata GAE entity
    '''
    ret = []
    for k in result:
        em = transform_metadata(k)
        em['entity_property_metadatas'] = normalize_entity_property_metadata_results(req, k.entity_property_metadatas(req))
        ret.append(em)
    return ret

def normalize_enumeration_value_results(req, result):
    '''
    Normalize each GAE entity
    '''
    properties = ["name"]
    ret = [ transform_metadata_filter(k, properties, [], False) for k in result ]
    return ret

def normalize_enum_results(req, result):
    '''
    Normalize Enumeration GAE entity
    '''
    ret = []
    for k in result:
        em = transform_metadata(k)
        em['enumerations'] = normalize_enumeration_value_results(req, k.enumeration_values(req))
        ret.append(em)
    return ret


def reverse_transform_location(req, data):
  '''
  Transform the PyAmf data to GAE data
  '''  
  gae_obj       = None    

  if ('id' in data):
      key       = data['id']
      key_obj   = db.Key.from_path('datamodel.UserLocation', key)
      gae_obj   = db.Model.get(key_obj)
  else:
      key       = utils.new_key()
  
  if not gae_obj:
      gae_obj   = datamodel.UserLocation(key_name = key)

  for k in data.keys():
      val = data[k]
      setattr(gae_obj, k, val)
          
  return gae_obj 

def denormalize_locations(req, data):
    '''
    Normalize each PyAmf data
    '''
    ret = [ reverse_transform_location(req, k) for k in data]
    return ret

def reverse_transform_metadata(req, data, datatype):
  '''
  Transform the PyAmf data to GAE data
  '''  
  gae_obj       = None    

  if ('name' in data):
      key       = data['name']
      key_obj   = db.Key.from_path(datatype.__name__, key)
      gae_obj   = db.Model.get(key_obj)
  else:
      key       = utils.new_key()
  
  if not gae_obj:
      gae_obj   = datatype(key_name = key)

  for k in data.keys():
      val = data[k]
      #check value type if the next line fails
      #logging.info(k)
      #logging.info(val)
      setattr(gae_obj, k, val)
          
  return gae_obj 

def denormalize_metadata(req, data):
    '''
    Normalize each PyAmf data
    '''
    ret = [ reverse_transform_location(req, k) for k in data]
    return ret