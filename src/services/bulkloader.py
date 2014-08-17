
# Standard Python imports.
import os
import sys
import logging

# Log a message each time this module get loaded.
logging.info('Loading %s, app version = %s',
             __name__, os.getenv('CURRENT_VERSION_ID'))

# Declare the Django version we need.
from google.appengine.dist import use_library
use_library('django', '1.0')

# Fail early if we can't import Django 1.x.  Log identifying information.
import django
logging.info('django.__file__ = %r, django.VERSION = %r',
             django.__file__, django.VERSION)
assert django.VERSION[0] >= 1, "This Django version is too old"

# AppEngine imports.
from google.appengine.ext.webapp import util


# Helper to enter the debugger.  This passes in __stdin__ and
# __stdout__, because stdin and stdout are connected to the request
# and response streams.  You must import this from __main__ to use it.
# (I tried to make it universally available via __builtin__, but that
# doesn't seem to work for some reason.)
def BREAKPOINT():
  import pdb
  p = pdb.Pdb(None, sys.__stdin__, sys.__stdout__)
  p.set_trace()


# Custom Django configuration.
os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'
from django.conf import settings
settings._target = None

# Import various parts of Django.
import django.core.handlers.wsgi
import django.core.signals
import django.db
import django.dispatch.dispatcher
import django.forms

# Work-around to avoid warning about django.newforms in djangoforms.
django.newforms = django.forms


def log_exception(*args, **kwds):
  """Django signal handler to log an exception."""
  cls, err = sys.exc_info()[:2]
  logging.exception('Exception in request: %s: %s', cls.__name__, err)


# Log all exceptions detected by Django.
django.core.signals.got_request_exception.connect(log_exception)

# Unregister Django's default rollback event handler.
django.core.signals.got_request_exception.disconnect(
    django.db._rollback_on_exception)


import uuid
import datetime
import services.utils as utils

from google.appengine.ext import bulkload
from google.appengine.api import datastore_types
from google.appengine.ext import search
from google.appengine.ext import db

from services import geohash
from services.importhelpers import *
from services.datamodel import *

import services.schemaloader as schemaloader
import services.utils as utils

class MetadataLoader(bulkload.Loader):
  def __init__(self):
    self.props = [('name', import_str),
                          ('description', import_text),
                          ('depends_on', str),
                          ]
    # select name,description from metadatas
    bulkload.Loader.__init__(self, 'Metadata', self.props)

  def HandleEntity(self, entity):
    import_fkname_list(entity, 'depends_on', 'Metadata')
    return utils.handle_entity_with_name_key(entity, 'Metadata', self.props)

class TypeInfoLoader(bulkload.Loader):
  def __init__(self):
    self.props = [('name', import_str),
                          ('description', import_text),
                          ('is_deleted', import_bool),
                          ('server_type', import_str),
                          ('reg_exp', import_str),
                          ('max_length',  import_int),
                          ('local_db_type', import_str),
                          ('import_type', import_str),
                          ('metadata', str),
                          ]
    # select ti.name, ti.description, is_deleted, server_type, reg_exp, max_length, local_db_type, m.name from type_infos ti left join metadatas m on ti.metadata_id = m.id
    bulkload.Loader.__init__(self, 'TypeInfo', self.props)


  def HandleEntity(self, entity):
    import_fkname(entity, 'metadata', 'Metadata')

    return utils.handle_entity_with_name_key(entity, 'TypeInfo', self.props)

class EnumerationLoader(bulkload.Loader):
  def __init__(self):
    self.props = [('name', import_str),
                          ('description', import_text),
                          ('is_deleted', import_bool),
                          ('metadata', str),
                          ]
    # select ti.name, ti.description, is_deleted,  m.name from enumerations ti left join metadatas m on ti.metadata_id = m.id
    bulkload.Loader.__init__(self, 'Enumeration', self.props)


  def HandleEntity(self, entity):
    import_fkname(entity, 'metadata', 'Metadata')

    return utils.handle_entity_with_name_key(entity, 'Enumeration', self.props)

class EnumerationValueLoader(bulkload.Loader):
  def __init__(self):
    self.props = [('name', import_str),
                          ('description', import_text),
                          ('is_deleted', import_bool),
                          ('enumeration', str),
                          ('metadata', str),
                          ]
    # select ti.name, ti.description, is_deleted,  e.name as enumeration,  'Global' as metadata from enumeration_values ti left join enumerations e on ti.enumeration_id = e.id
    bulkload.Loader.__init__(self, 'EnumerationValue', self.props)


  def HandleEntity(self, entity):
    import_fkname(entity, 'metadata', 'Metadata')
    import_fkname(entity, 'enumeration', 'Enumeration')
    
    return utils.handle_entity_with_name_key(entity, 'EnumerationValue', self.props)

class EntityMetadataLoader(bulkload.Loader):
  def __init__(self):
    self.props = [('name', import_str),
                          ('description', import_text),
                          ('rss_title', import_str),
                          ('rss_description', import_str),
                          ('rss_updated', import_str),
                          ('plural_name', import_str),
                          ('human_name', import_str),
                          ('underscore_name', import_str),
                          ('camel_name', import_str),
                          ('owner_columns', import_text),
                          ('public_columns', import_text),
                          ('metadata', str)
                          ]
    # select name,description, rss_title, rss_description, plural_name, human_name, underscore_name, camel_name, metadata_id from Entity_metadatas
    bulkload.Loader.__init__(self, 'EntityMetadata', self.props)


  def HandleEntity(self, entity):
    import_fkname(entity, 'metadata', 'Metadata')
      
    return utils.handle_entity_with_name_key(entity, 'EntityMetadata', self.props)

class EntityPropertyMetadataLoader(bulkload.Loader):
  def __init__(self):
    self.props = [('name', import_str),
                          ('description', import_text),
                          ('max_length', import_int),
                          ('min_value', import_int),
                          ('max_value', import_int),
                          ('reg_exp', import_str),
                          ('is_deleted', import_bool),
                          ('has_generated', import_bool),
                          ('is_foreign_key', import_bool),
                          ('is_read_only', import_bool),
                          ('is_required', import_bool),
                          ('is_search_key', import_bool),
                          ('is_full_text', import_bool),
                          ('in_list_view', import_bool),
                          ('in_show_view', import_bool),
                          ('in_edit_view', import_bool),
                          ('display_group', import_str),
                          ('display_index', import_int),
                          ('human_name', import_str),
                          ('camel_name', import_str),
                          ('flags', import_int),
                          ('enumeration', str),
                          ('type_info', str),
                          ('ref_type', import_str),
                          ('entity_relation', import_str),
                          ('entity_metadata', str),
                          ('metadata', str)
                          ]
    # select ep.name, ep.description, ep.max_length, min_value, max_value, ep.reg_exp, ep.is_deleted, ep.has_generated, is_foreign_key, is_read_only, is_required, is_search_key, is_full_text, in_list_view, in_show_view, in_edit_view, ep.human_name, ep.camel_name, flags , enum_type , ti.name as type_info, em.name as entity_metadata, 'Global' as metadata from Entity_Property_Metadatas ep left join Type_Infos ti on ti.id=ep.type_info_id left join Entity_metadatas em on ep.entity_metadata_id = em.id
    bulkload.Loader.__init__(self, 'EntityPropertyMetadata', self.props)


  def HandleEntity(self, entity):
    'Handle the foreign keys'
    key_name = entity['entity_metadata'] + '_' + entity['name']
    
    import_fkname(entity, 'metadata', 'Metadata')
    import_fkname(entity, 'enumeration', 'Enumeration')
    import_fkname(entity, 'type_info', 'TypeInfo')
    import_fkname(entity, 'entity_metadata', 'EntityMetadata')
        
    return utils.handle_entity_with_name_key_custom(entity, 'EntityPropertyMetadata', self.props, key_name)

class EntityRelationLoader(bulkload.Loader):
  def __init__(self):  
    self.props = [('name', import_str),
                          ('description', db.Text),
                          ('type_of', import_str),
                          ('parent_entity', import_str),
                          ('child_entity', import_str),
                          ('max_count', import_int),
                          ('delete_policy', import_int),
                          ('has_inverse', import_bool),
                          ('parent_column', import_str),
                          ('child_column', import_str),
                          ('metadata', str),
                          ]
    # select name, description, type_of, parent_entity, child_entity, through, 'Global' as metadata from entity_relation_metadatas
    bulkload.Loader.__init__(self, 'EntityRelation', self.props)


  def HandleEntity(self, entity):
    import_fkname(entity, 'metadata', 'Metadata')

    return utils.handle_entity_with_name_key(entity, 'EntityRelation', self.props)

class MetadataCommitLoader(bulkload.Loader):
  def __init__(self):  
    self.props = [('name', import_str)]
    # select name, description, type_of, parent_entity, child_entity, through, 'Global' as metadata from entity_relation_metadatas
    bulkload.Loader.__init__(self, 'MetadataCommit', self.props)


  def HandleEntity(self, entity): 
    schemaloader.AppImporterAndLoader.commitMetadataChanges(entity['name'])
    return []

class DeleteAllLoader(bulkload.Loader):
  def __init__(self):  
    self.props = [('name', import_str)]
    # select name, description, type_of, parent_entity, child_entity, through, 'Global' as metadata from entity_relation_metadatas
    bulkload.Loader.__init__(self, 'DeleteAll', self.props)


  def HandleEntity(self, entity): 
    schemaloader.AppImporterAndLoader.deleteAllRecords()
    return []

class UserLoader(bulkload.Loader):
  def __init__(self):
    self.kind = 'User'
    self.props = [('name', import_str),
                          ('description', import_text),
                          ('first_name', import_str),
                          ('last_name', import_str),
                          ('email', import_str),
                          ('password', import_password),
                          ('salt', import_str),
                          ('is_active', import_bool),
                          ('permissions', str),
                          ('groups', str),
                          ('roles', str),
                          ]
    # select name,description from metadatas
    bulkload.Loader.__init__(self, self.kind, self.props)

  def HandleEntity(self, entity):
    import_fkname_list(entity, 'permissions', 'Permission')
    import_fkname_list(entity, 'groups', 'Group')
    import_fkname_list(entity, 'roles', 'Role')
    
    return utils.handle_entity_with_name_key(entity, self.kind, self.props)

class GroupLoader(bulkload.Loader):
  def __init__(self):
    self.kind = 'Group'
    self.props = [('name', import_str),
                          ('description', import_text),
                          ('org', import_str),
                          ('roles', str),
                          
                          ]
    # select name,description from metadatas
    bulkload.Loader.__init__(self, self.kind, self.props)

  def HandleEntity(self, entity):
    import_fkname_list(entity, 'roles', 'Role')
    return utils.handle_entity_with_name_key(entity, self.kind, self.props)

class PermissionLoader(bulkload.Loader):
  def __init__(self):
    self.kind = 'Permission'
    self.props = [('name', import_str),
                          ('description', import_text),
                          ('org', import_str),
                          ]
    # select name,description from metadatas
    bulkload.Loader.__init__(self, self.kind, self.props)

  def HandleEntity(self, entity):
    return utils.handle_entity_with_name_key(entity, self.kind, self.props)

class RoleLoader(bulkload.Loader):
  def __init__(self):
    self.kind = 'Role'
    self.props = [('name', import_str),
                          ('description', import_text),
                          ('org', import_str),
                          ('permissions', str),
                          ]
    # select name,description from metadatas
    bulkload.Loader.__init__(self, self.kind, self.props)

  def HandleEntity(self, entity):
    import_fkname_list(entity, 'permissions', 'Permission')
    return utils.handle_entity_with_name_key(entity, self.kind, self.props)

class RolePermissionsLoader(bulkload.Loader):
  def __init__(self):
    self.kind = 'RolePermissions'
    self.props = [('name', import_str),
                          ('role', str),
                          ('perm', str),
                          ('org', import_str),
                          ]
    # select name,description from metadatas
    bulkload.Loader.__init__(self, self.kind, self.props)

  def HandleEntity(self, entity):
    import_fkname(entity, 'role', 'Role')
    import_fkname(entity, 'perm', 'Permission')
    return utils.handle_entity(entity, self.kind, self.props)

class L10nLoader(bulkload.Loader):
  def __init__(self):
    self.kind = 'L10n'
    self.props = [('name', import_str),
                          ('value', import_str),
                          ('lang', import_str),
                          ('page', import_str),
                          ('org', import_str),
                          ('metadata', str),
                          ]
    # select name,description from metadatas
    bulkload.Loader.__init__(self, self.kind, self.props)

  def HandleEntity(self, entity):
    import_fkname(entity, 'metadata', 'Metadata')
    return utils.handle_entity_with_name_key(entity, self.kind, self.props)

class AppLoader(bulkload.Loader):
  def __init__(self):
    self.kind = 'App'
    self.props = [('name', import_str),
                          ('description', import_text),
                          ('licenses', import_int),
                          ('security', import_str),
                          ('org', str),
                          ('metadata', str),
                          ]
    # select name,description from metadatas
    bulkload.Loader.__init__(self, self.kind, self.props)

  def HandleEntity(self, entity):
    import_fkname(entity, 'org', 'Organisation')
    import_fkname(entity, 'metadata', 'Metadata')
    return utils.handle_entity_with_name_key(entity, self.kind, self.props)

class OrganisationLoader(bulkload.Loader):
  def __init__(self):
    self.kind = 'Organisation'
    self.props = [('name', import_str),
                          ('description', import_text),
                          ('admin', str),
                          ]
    # select name,description from metadatas
    bulkload.Loader.__init__(self, self.kind, self.props)

  def HandleEntity(self, entity):
    import_fkname(entity, 'admin', 'User')
    return utils.handle_entity_with_name_key(entity, self.kind, self.props)

class ViewDefinitionLoader(bulkload.Loader):
  def __init__(self):
    self.kind = 'ViewDefinition'
    self.props = [('name', import_str),
                          ('description', import_text),
                          ('type_of', import_str),
                          ('default_entity', import_str),
                          ('data_queries', import_str),
                          ('default_layout', import_str),
                          ('mobile_layout', import_text),
                          ('report_layout', import_text),
                          ('sub_views', import_str),
                          ('org', import_str),
                          ('metadata', str),
                          ]
    # select name,description from metadatas
    bulkload.Loader.__init__(self, self.kind, self.props)

  def HandleEntity(self, entity):
    import_fkname(entity, 'metadata', 'Metadata')
    return utils.handle_entity_with_name_key(entity, self.kind, self.props)

class ViewMapLoader(bulkload.Loader):
  def __init__(self):
    self.kind = 'ViewMap'
    self.props = [('name', import_str),
                          ('title', import_str),
                          ('description', import_text),
                          ('is_root', import_bool),
                          ('url', import_str),
                          ('view_definition', str),
                          ('parent_viewmap', str),
                          ('org', import_str),
                          ('metadata', str),
                          ]
    # select name,description from metadatas
    bulkload.Loader.__init__(self, self.kind, self.props)

  def HandleEntity(self, entity):
    import_fkname(entity, 'view_definition', 'ViewDefinition')
    import_fkname(entity, 'parent_viewmap', 'ViewMap')
    import_fkname(entity, 'metadata', 'Metadata')
    return utils.handle_entity_with_name_key(entity, self.kind, self.props)

class DataQueryLoader(bulkload.Loader):
  def __init__(self):
    self.kind = 'DataQuery'
    self.props = [('name', import_str),
                          ('description', import_text),
                          ('type_of', import_str),
                          ('query', import_str),
                          ('fulltext_search', import_str),
                          ('parent_relation', import_str),
                          ('parent_data_query', import_str),
                          ('child_data_queries', import_str),
						  ('org', import_str),
                          ('metadata', str),
                          ]
    # select name,description from metadatas
    bulkload.Loader.__init__(self, self.kind, self.props)

  def HandleEntity(self, entity):
    import_fkname(entity, 'metadata', 'Metadata')
    return utils.handle_entity_with_name_key(entity, self.kind, self.props)

class SynchSubscriptionLoader(bulkload.Loader):
  def __init__(self):
    self.props = [('query', str),
                          ('app', str),
                          ]
    # select name,description from metadatas
    bulkload.Loader.__init__(self, 'SynchSubscription', self.props)

  def HandleEntity(self, entity):
    import_fkname(entity, 'query', 'DataQuery')
    import_fkname(entity, 'app', 'App')
    return utils.handle_entity_with_name_key(entity, 'SynchSubscription', self.props)

class ImportProfileLoader(bulkload.Loader):
  def __init__(self):
    self.kind = 'ImportProfile'
    self.props = [('name', import_str),
                          ('type_of', import_str),
                          ('field_mapping', import_str)
                          ]
    # select name,description from metadatas
    bulkload.Loader.__init__(self, self.kind, self.props)

  def HandleEntity(self, entity):
    import_fkname_list(entity, 'field_mapping', 'EntityPropertyMetadata')
    return utils.handle_entity_with_name_key(entity, self.kind, self.props)

class UserLocationLoader(bulkload.Loader):
  def __init__(self):
    self.kind = 'UserLocation'
    self.props = [('name', import_str),
                          ('description', import_str),
                          ('longitude', import_float),
                          ('latitude', import_float),
                          ('address', import_str),
                          ('city', import_str),
                          ('state', import_str),
                          ('zipcode', import_str),
                          ('tags', import_str),
                          ]
    # select name,description from metadatas
    bulkload.Loader.__init__(self, self.kind, self.props)

  def HandleEntity(self, entity):
    #logging.info(entity['name'])
    entity = utils.handle_entity_with_name_key(entity, self.kind, self.props)

    latitude = entity['latitude']
    longitude = entity['longitude']
    if latitude and longitude:
        hash = str(geohash.Geohash((float(longitude),float(latitude))))
        #logging.info(hash)
        entity['bbhash1'] = hash[:2]
        entity['bbhash2'] = hash[:4]
        entity['bbhash'] = hash
        
    entity['updated'] = datetime.datetime.now()
    entity['bookmark'] = utils.bookmark_for_kind(self.kind, 'user.name', entity['updated'])    
    return entity

if __name__ == '__main__':
  bulkload.main(MetadataLoader(), 
                EntityMetadataLoader(), 
                EntityPropertyMetadataLoader(), 
                TypeInfoLoader(), 
                EnumerationLoader(), 
                EnumerationValueLoader(), 
                EntityRelationLoader(), 
                MetadataCommitLoader(),
                DeleteAllLoader(),
                UserLoader(),
                GroupLoader(),
                PermissionLoader(),
                RoleLoader(),
                RolePermissionsLoader(),
                AppLoader(),
                OrganisationLoader(),
                L10nLoader(),
                ViewDefinitionLoader(),
                ViewMapLoader(),
                DataQueryLoader(),
                SynchSubscriptionLoader(),
                ImportProfileLoader(),
                UserLocationLoader())

