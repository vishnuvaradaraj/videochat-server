import sys
import os
import new
import logging

import datamodel
import cacheservice
import utils

from google.appengine.ext.webapp import template
from google.appengine.api import memcache

import_path = '!!parabay!!'

MAX_ENTITY_METADATA             = 512
MAX_ENTITY_PROPERTY_METADATA    = 32 * MAX_ENTITY_METADATA

def reftype(value):
    '''format the reference type'''
    ret = str(value)
    if not value:
        ret = ''
    return ret

#Register the template filter.
register = template.create_template_register()
register.filter(reftype)
template.register_template_library(
    'services.schemaloader')

class TemplateItem:
    '''
    Helper class to provide for each iteration in the template
    This exists as I was unable to figure out issues in using a dictionary
    '''
    entity  = None
    properties = []
    fkstring = ''
        
class AppImporterAndLoader(object):
    '''
    Class used to support the dynamic loading of application classes.
    '''
    def __init__(self, path=import_path):
        '''
        Respond to only our predefined path in sys.path
        '''
        if path != import_path:
            raise ImportError
        self.path = path
        
    def _get__path__(self):
        '''
        Return the path used to initialize the module
        '''
        return self.path

    def find_module(self, fullname, path=None):
        '''
        check if the module is a valid application in our list.
        '''
        return self

    @staticmethod
    def find_metadata_by_name(app):
        query = datamodel.Metadata.all()
        query.filter('name =', app)
        return query.get()

    @staticmethod
    def generate(template_name, template_values={}):
        '''
        Helper function to generate code from template
        '''
        values = {}
        
        values.update(template_values)
        path = os.path.join(os.path.dirname(__file__), template_name)
        return template.render(path, values, debug=True)
     
    @staticmethod   
    def processFk(entity, prop):
      '''
      Helper function to generate the fk code template
      '''
      ret = ''
      query = datamodel.EntityRelation.all()
      query.filter('child_entity =', entity.name)
      query.filter('link_column =', prop.name)
      query.filter('type_of =', 1)
    
      relations = query.fetch(1)
      if len(relations)  > 0:
        rel = relations[0]
        ret =  "import_fk(entity, '%(column)s', %(parent)s)\n" % {'column':prop.name, 'parent':rel.parent_entity}
      else:
        logging.error('FK relation not found for property' + prop.name)
      
      return ret

    @staticmethod
    def sort_entity_metadata_list(em_list, rel_list):
        em_map = dict([(k.name, k) for k in em_list])
        
        res = []
        for rel in rel_list:
            if em_map.has_key(rel.parent_entity):
                em = em_map[rel.parent_entity]
                if not em in res:
                    res.append(em)
    
        for em in em_list:
            if not em in res:
                res.append(em)
    
        return res          
    
    @staticmethod
    def getAppModuleCode(app, useCache=True):
        '''
        Generate the code for this application module
        '''
        if useCache:
            cache_code1 = cacheservice.PersistentCache.lookupItem([app, 'code1'])
            cache_code2 = cacheservice.PersistentCache.lookupItem([app, 'code2'])
            if cache_code1 and cache_code2:
                return [cache_code1, cache_code2]
        
        metadata = AppImporterAndLoader.find_metadata_by_name(app)
        if (not metadata):
          return ''
    
        entities_list           = []
        
        entity_metadatas = AppImporterAndLoader.sort_entity_metadata_list(metadata.entity_metadatas(), metadata.entity_relations())
        
        for entity_metadata in entity_metadatas:
            query   = datamodel.EntityPropertyMetadata.all()
            query.filter('metadata =', metadata)
            query.filter('entity_metadata =', entity_metadata)
            entity_property_metadatas = query.fetch(MAX_ENTITY_PROPERTY_METADATA)
            
            fkstring = ''
            for prop in entity_property_metadatas:
                if prop.type_info.name == 'fk':
                    fkstring += AppImporterAndLoader.processFk(entity_metadata, prop)
            
            item = TemplateItem()
            item.entity = entity_metadata
            item.properties = entity_property_metadatas
            item.fkstring = fkstring
            
            entities_list.append(item)
    
        result_code1 = AppImporterAndLoader.generate('entity.template', {'entities_list': entities_list, 'module_name' : app } )
        #logging.info(result_code1)
        
        result_code2 = AppImporterAndLoader.generate('entityloader.template', {'entities_list': entities_list, 'module_name' : app } )
        #logging.info(result_code2)
        
        # cache the result always, also used by commit changes.
        cacheservice.PersistentCache.cacheItem([app, 'code1'], result_code1)
        cacheservice.PersistentCache.cacheItem([app, 'code2'], result_code2)
        
        return [result_code1, result_code2]
    
    @staticmethod
    def commitMetadataChanges(app):
        '''
        cache the metadata code and reload if necessary.
        '''
        metadata = AppImporterAndLoader.find_metadata_by_name(app)       
        if (metadata):
            # force load the code for the metadata in persistent cache.
            code = AppImporterAndLoader.getAppModuleCode(app, False)       
            
            if hasattr(sys.modules, app):
                reload(sys.modules[app])
            else:
                loader = AppImporterAndLoader()
                sys.modules[app] = loader.load_module(app)        
       
    @staticmethod
    def deleteAllMemCache():
        query1 = datamodel.User.all()
        models1 = query1.fetch(100)
        for u in models1:
            memcache.delete('userid_user:%s' % u.name)
            
        query2 = datamodel.UserToken.all()
        models2 = query2.fetch(100)
        for t in models2:
            memcache.delete('token_req:%s' % t.value)
            
    @staticmethod
    def deleteAllRecords():
        '''
        Delete all the uploaded data
        '''

        AppImporterAndLoader.deleteAllMemCache()
        
        utils.delete_all_entities(datamodel.ViewMap)
        utils.delete_all_entities(datamodel.ViewDefinition)
        utils.delete_all_entities(datamodel.App)
        utils.delete_all_entities(datamodel.Organisation)
        utils.delete_all_entities(datamodel.User)
        utils.delete_all_entities(datamodel.Group)
        utils.delete_all_entities(datamodel.RolePermissions)
        utils.delete_all_entities(datamodel.Role)
        utils.delete_all_entities(datamodel.Permission)
        utils.delete_all_entities(datamodel.SynchSubscription)
        utils.delete_all_entities(datamodel.L10n)
        utils.delete_all_entities(datamodel.EntityPropertyMetadata)
        utils.delete_all_entities(datamodel.EntityMetadata)
        utils.delete_all_entities(datamodel.EntityRelation)
        utils.delete_all_entities(datamodel.EnumerationValue)
        utils.delete_all_entities(datamodel.Enumeration)
        utils.delete_all_entities(datamodel.TypeInfo)
        utils.delete_all_entities(datamodel.Metadata)
        utils.delete_all_entities(datamodel.DataQuery)
        utils.delete_all_entities(datamodel.UploadedFile)
        utils.delete_all_entities(datamodel.SynchSubscription)
        utils.delete_all_entities(datamodel.SynchSession)
        utils.delete_all_entities(datamodel.CacheEntry)
        utils.delete_all_entities(datamodel.SynchSession)
        utils.delete_all_entities(datamodel.UserToken)
        utils.delete_all_entities(datamodel.ImportProfile)
        
    @staticmethod
    def load_modules_for_all_metadata():
        '''Load all modules for metadata'''
        logging.info('Loading all the modules.')
        
        query = datamodel.Metadata.all()
        for m in query:
            loader = AppImporterAndLoader()
            sys.modules[m.name] = loader.load_module(str(m.name))
    
    def load_module(self, fullname):
        '''
        Generate the code for the module and execute it
        '''
        logging.info('load_module:%s' % fullname)
        
        metadata = AppImporterAndLoader.find_metadata_by_name(fullname)       
        if not metadata:
            return None

        code = AppImporterAndLoader.getAppModuleCode(fullname, True)
        
        mod = new.module(fullname.encode('latin-1'))
        sys.modules[fullname] = mod
        mod.__file__ = "%s" % self.__class__.__name__
        mod.__loader__ = self
        
        #logging.info(code[0])
        compiled = compile(code[0], 'schemaloader', 'exec')
        exec compiled  in mod.__dict__    
        
        #logging.info("code is '%s'" % code[1] )
        #compiled = compile(code[1], 'schemaloader', 'exec')
        #exec compiled  in mod.__dict__ 
        
        return mod
    
def register_loader_hooks():
    sys.path_hooks.append(AppImporterAndLoader)
    sys.path.append(import_path)
    
# add the class to the hook and its fake-path marker to the path 
#register_loader_hooks()
