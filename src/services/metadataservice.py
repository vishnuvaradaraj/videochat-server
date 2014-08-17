import sys
import os
import logging
import traceback
import StringIO

import schemaloader

import services.cacheservice as cacheservice
import services.securityservice as securityservice

import services.datamodel as datamodel
import services.utils as utils

from google.appengine.ext import db
from google.appengine.ext.webapp import template
 
import json
import simplejson

MAX_ENTITY_METADATA             = 512
MAX_ENTITY_PROPERTY_METADATA    = 32 * MAX_ENTITY_METADATA
      
def synchronizeMetadata(req):
    '''
    Respond to client queries for metadata updates
    '''
    ret = {}
    
    metadata = utils.find_entity_by_name(datamodel.Metadata, req.metadata.name)
    if (not metadata):
      raise LookupError, 'Invalid metadata key:' + str(req.metadata.name)
      return
  
    return metadata

def generate_default_views(req, overwrite=None):
    logging.info("Generating default views")
    vd_list = req.metadata.view_definitions(req)
    
    for vd in vd_list:
        generate_default_view(req, vd, overwrite)
        
def generate_default_view(req, view_def, overwrite=None):
    if overwrite or (not view_def.mobile_layout):
        logging.info("Generating default view for:" + view_def.name)
        
        obj = {}
        obj['type'] = view_def.type_of
        
        em = find_entity_metadata(req, view_def.default_entity)
        if (view_def.type_of == "EntityListTab"):
            obj['layout'] = 'simple'
            
            objFields = []
            for k in em.entity_property_metadatas(req):
                if k.is_search_key:
                    objField = {}
                    objField['type'] = 'title'
                    objParams = {}
                    objParams['data'] = k.name
                    objField['params'] = objParams
                    objFields.append(objField)
            obj['fields'] = objFields
            
        elif (view_def.type_of == "EntityEditorTab"):
            obj['layout'] = 'group'

            objGroups = []
            
            objGroup = {}
            objGroup['name'] = 'default'
            
            objFields = []
            for k in em.entity_property_metadatas(req):
                if k.in_edit_view:
                    type = k.type_info

                    objField = {}
                    objField['type'] = type.name
                    objParams = {}
                    objParams['data'] = k.name
                    objField['params'] = objParams
                    objFields.append(objField)
            objGroup['fields'] = objFields
            
            objGroups.append(objGroup)
            obj['groups'] = objGroups

        str = json.encode(obj)
        #logging.info(str)
        view_def.mobile_layout = str
        datamodel.ViewDefinition.put(view_def)
        
def find_entity_metadata(req, name):
    ret = req.metadata.get_entity_metadata(req, name)
    return ret

def find_entity_property_metadata(req, em, name):
    ret = None
    for k in em.entity_property_metadatas(req):
        if k.name == name:
            ret = k
            break
    return ret

def find_enumerations_for_entity_metadata(req, em):
    ret_set = set()
    for k in em.entity_property_metadatas(req):
        if k.enumeration:
            ret_set.add(k.enumeration)
    ret = [ x for x in ret_set]
    return ret

def find_relations_for_entity_metadata(req, em):
    ret_set = set()
    for k in em.entity_property_metadatas(req):
        if k.entity_relation:
            ret_set.add(find_entity_relation(req, em, k))
    ret = [ x for x in ret_set if x is not None]
    return ret

def find_typeinfos_for_entity_metadata(req, em):
    ret_set = set()
    for k in em.entity_property_metadatas(req):
        if k.type_info:
            ret_set.add(k.type_info)
    ret = [ x for x in ret_set]
    return ret

def find_enumeration(req, name):
    ret = None
    e_list = req.metadata.enumerations(req)
    for e in e_list:
        if e.name == name:
            ret = e
            break
    return ret

def find_type_info(req, name):
    ret = None
    ti_list = req.metadata.entity_metadatas(req)
    for ti in ti_list:
        if ti.name == name:
            ret = ti
            break
    return ret

def find_entity_relation(req, child_entity, link_column):
    ret = None
    er_list = req.metadata.entity_relations(req)
    for er in er_list:
        #logging.info(er.name + '-(er.child_entity:)' + repr(er.child_entity)  + ' (child_entity:)' + repr(child_entity))
        if (er.child_column == link_column.name or er.parent_column == link_column.name) and (er.parent_entity == child_entity.name or er.child_entity == child_entity.name):
            ret = er
            break
    return ret

def find_view_map(req, name):
    ret = None
    ti_list = req.metadata.view_maps(req)
    #logging.info(repr(ti_list))
    for ti in ti_list:
        #logging.info("%s==%s, %r", name, ti.name, ti)
        if ti.name == name:
            logging.info("Found")
            ret = ti
            break
    return ret

def find_view_definition(req, name):
    ret = None
    ti_list = req.metadata.view_definitions(req)
    for ti in ti_list:
        if ti.name == name:
            ret = ti
            break
    return ret

def find_data_query(req, name):
    ret = None
    ti_list = req.metadata.data_queries(req)
    for ti in ti_list:
        if ti.name == name:
            ret = ti
            break
    return ret

    