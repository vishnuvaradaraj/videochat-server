import sys
import os
import logging
import traceback
import StringIO

import json
import simplejson

from services import constants, echoservice, shellservice, metadataservice, dataservice, securityservice, utils, datamodel, transformservice, requestcontext

from google.appengine.ext import db, search

class AppService(object):
    '''
    Provides access to data
    '''
    @staticmethod
    def get_view_maps(req, names=None):
        view_maps = []
        view_maps = req.metadata.view_maps(req)
        if names:
            view_maps = [ x for x in view_maps if x.name in names ]
        return view_maps
    
    @staticmethod
    def get_root_view_maps(req, limit, offset):
        view_maps = []
        view_maps = req.metadata.view_maps(req)
        view_maps = [ x for x in view_maps ]
        return view_maps
    
    @staticmethod
    def get_view_defs(req, names=None):
        view_defs = []
        view_defs = req.metadata.view_definitions(req)
        if names:
            view_defs = [ x for x in view_defs if x.name in names ]
        return view_defs
    
    @staticmethod
    def get_entity_metadatas(req, names):
        entity_metadatas = []
        entity_metadatas = req.metadata.entity_metadatas(req)
        if names:
            entity_metadatas = [ x for x in entity_metadatas if x.name in names ]
        return entity_metadatas
    
    @staticmethod
    def get_enumerations(req, names):
        enumerations = []
        enumerations = req.metadata.enumerations(req)
        if names:
            enumerations = [ x for x in enumerations if x.name in names ]
        return enumerations
     
    @staticmethod
    def get_type_infos(req, names):
        type_infos = []
        type_infos = req.metadata.type_infos(req)
        if names:
            type_infos = [ x for x in type_infos if x.name in names ]
        return type_infos
       
    @staticmethod
    def get_l10n_content(req, names):
        l10n_content = []
        l10n_content = req.metadata.l10n_content(req)
        if names:
            l10n_content = [ x for x in l10n_content if x.name in names ]
        return l10n_content

    @staticmethod
    def get_relations(req, names):
        relations = []
        relations = req.metadata.entity_relations(req)
        if names:
            relations = [ x for x in relations if x.name in names ]
        return relations

    @staticmethod
    def find_l10n_for_page(req, page, lang, offset=0, limit=128):
        ret = None
        query = datamodel.L10n.all()
        if page:
            query.filter('page =', page)
        if lang:
            query.filter('lang =', lang)
        #query.filter('metadata =', req.metadata.key())
        ret = query.fetch(limit, offset)
        return ret

    # these two methods could be deleted?
    @staticmethod
    def get_relations_for_entity_metadata(req, entity_name):
        relations = []
        relations = req.metadata.entity_relations(req)
        if names:
            relations = [ x for x in relations if x.parent_entity == entity_name ]
        return relations
    
    @staticmethod
    def get_page_metadata(req, view_map_name):
        page_metadata = {}
        page_metadata['view_map']           = metadataservice.find_view_map(req, view_map_name)
        page_metadata['view_definition']    = metadataservice.find_view_definition(req, page_metadata['view_map'].view_def)
        dataquery_names                     = metadataservice.find_data_query(req, page_metadata['view_definition'])
        dataquery_names                     = simplejson.JSONDecoder().decode(dataquery_names)
        dataqueries                         = [ metadataservice.find_data_query(req, name) for name in dataquery_names ]
        page_metadata['data_queries']       = data_queries
        
        return page_metadata

    @staticmethod
    def format_perm(req, app, name):
        pname = app.org.name + '.' + app.org.name + '-' + app.metadata.name + '.' + name
        return pname
        
    @staticmethod
    def create_perm(req, app, name):
        pname = AppService.format_perm(req, app, name)
        rp = utils.find_entity_by_name(datamodel.Permission, pname)
        if not rp:
            logging.info('create permission: ' + pname)
            rp = datamodel.Permission(key_name=pname)
            rp.name=pname
            rp.description = app.org.name + ' Organisations ' + app.name + ' App ' + name + ' Permission'
            rp.owner = req.user.name
            rp.org = app.org.name
            rp.put()
        
        return rp
    
    @staticmethod
    #"Parabay-User-Role","Users of parabay","ParabayOrg","ParabayOrg.ParabayOrg-Contacts.Read;ParabayOrg.ParabayOrg-Contacts.Write;ParabayOrg.ParabayOrg-Outlook.Read;ParabayOrg.ParabayOrg-Outlook.Write;ParabayOrg.ParabayOrg-Timmy.Read;ParabayOrg.ParabayOrg-Timmy.Write;ParabayOrg.ParabayOrg-Docs.Read;ParabayOrg.ParabayOrg-Docs.Write;ParabayOrg.ParabayOrg-Friends.Read;ParabayOrg.ParabayOrg-Friends.Write"
    def create_role(req, app, name):
        rname = app.name + '.' + name + '-Role'
        role = utils.find_entity_by_name(datamodel.Role, rname)
        if not role:
            logging.info('create role: ' + rname)
            role = datamodel.Role(key_name=rname)
            role.name=rname
            role.description = name + 's of ' + app.name 
            role.owner = req.user.name
            role.org = app.org.name
            role.put()

        rp = utils.find_entity_by_name(datamodel.Permission, AppService.format_perm(req, app, 'Read'))
        wp = utils.find_entity_by_name(datamodel.Permission, AppService.format_perm(req, app, 'Write'))
        srp = utils.find_entity_by_name(datamodel.Permission, AppService.format_perm(req, app, 'Schema.Read'))
        swp = utils.find_entity_by_name(datamodel.Permission, AppService.format_perm(req, app, 'Schema.Write'))
        
        if rp and wp and srp and swp:
            logging.info('Setting role permissions..')
            role_perms = [rp.key(), wp.key(), srp.key()]
            if name == 'Admin':
                role_perms.append(swp.key())
                
            role.permissions = role_perms
            role.put()
            
        return role
               
    @staticmethod
    #"ParabayOrg-Friends.User-Group","Users of parabay friends app","ParabayOrg","Parabay-User-Role"
    def create_group(req, app, name):
        rname = app.name + '.' + name + '-Group'
        group = utils.find_entity_by_name(datamodel.Group, rname)
        if not group:
            logging.info('create group: ' + rname)
            group = datamodel.Group(key_name=rname)
            group.name=rname
            group.description = name + 's of ' + app.name 
            group.owner = req.user.name
            group.org = app.org.name
            group.put()

        ur = utils.find_entity_by_name(datamodel.Role, app.name + '.User-Role')
        ar = utils.find_entity_by_name(datamodel.Role, app.name + '.Admin-Role')
        
        if ur and ar:
            logging.info('Setting group roles..')
            group_roles = [ur.key()]
            if name == 'Admin':
                group_roles.append(ar.key())
                
            group.roles = group_roles
            group.put()
            
        return group
        
    @staticmethod
    def create_app(req, appInfo, organisation):
        appName = appInfo['name']
                
        app = utils.find_entity_by_name(datamodel.App, appName)
        if not app:
            logging.info('creating app:' + appName)
            app = datamodel.App(key_name=appName)
            app.name = appName
        else:
            logging.info('found existing app:' + appName)
            if app.owner != req.user.name:
                return constants.STATUS_ACCESS_DENIED

        if 'description' in appInfo:
            app.description = appInfo['description']
        app.owner = req.user.name
        app.org = organisation
        app.put()
        
        if 'metadata' in appInfo:
            appMetadata = appInfo['metadata']
            m = utils.find_entity_by_name(datamodel.Metadata, appMetadata)
            if not m:
                m = datamodel.Metadata(key_name=appMetadata)
                m.name=appMetadata
            m.owner = req.user.name
            m.description = 'Metadata for ' + appName
            m.put()
            
            app.metadata = m
            app.put()
            
        AppService.create_perm(req, app, 'Read')
        AppService.create_perm(req, app, 'Write')
        AppService.create_perm(req, app, 'Schema.Read')
        AppService.create_perm(req, app, 'Schema.Write')
        
        AppService.create_role(req, app, 'User')
        AppService.create_role(req, app, 'Admin')

        AppService.create_group(req, app, 'User')
        AppService.create_group(req, app, 'Admin')
        
        securityservice.SecurityService.add_user_app_perms(req.user, appName, organisation.name)
        
        return constants.STATUS_OK

    @staticmethod
    def save_data_query(req, data):

        dquery = None
        if 'data_query' in data:
            dquery = data['data_query']
        if dquery:
            dq = transformservice.reverse_transform_metadata(req, dquery, datamodel.DataQuery)
            dq.owner = req.user.name
            dq.org = req.org.name
            dq.metadata = req.metadata
            dq.put();

        en_list = None
        if 'enumerations' in data:
            en_list = data['enumerations']
        if en_list and len(en_list)>0:
            for en in en_list:
                ev_list = en['enumeration_values']
                del en['enumeration_values']
                        
                e =  transformservice.reverse_transform_metadata(req, en, datamodel.Enumeration)
                e.owner = req.user.name
                e.org = req.org.name
                e.metadata = req.metadata
                e.put();

                if ev_list:
                    for ev in ev_list:
                        v =  transformservice.reverse_transform_metadata(req, ev, datamodel.EnumerationValue)
                        v.owner = req.user.name
                        v.org = req.org.name
                        v.metadata = req.metadata
                        v.enumeration = e
                        v.put();
        
        em_list = None
        if 'entity_metadatas' in data:
            em_list = data['entity_metadatas']
        if em_list and len(em_list)>0:
            em_item = em_list[0]
            props_list = em_item['entity_property_metadatas']
            del em_item['entity_property_metadatas']
            logging.info(em_item)
            
            em = transformservice.reverse_transform_metadata(req, em_item, datamodel.EntityMetadata)
            em.owner = req.user.name
            em.org = req.org.name
            em.metadata = req.metadata
            logging.info(em.description)
            em.put()
            
            if props_list:
                for prop in props_list:
                    pp = prop['type_info']
                    del prop['type_info']
                    logging.info(pp)
                    
                    p =  transformservice.reverse_transform_metadata(req, prop, datamodel.EntityPropertyMetadata)
                    p.type_info = utils.find_entity_by_name(datamodel.TypeInfo, pp)
                    logging.info(p.type_info)
                    p.owner = req.user.name
                    p.org = req.org.name
                    p.metadata = req.metadata
                    p.entity_metadata = em
                    p.put();
            
        return None    
        
    @staticmethod
    def save_view_data(req, data):
        logging.info(data)

        viewdef = None
        if 'view_definition' in data:
            viewdef = data['view_definition']
        if viewdef:
            vd = transformservice.reverse_transform_metadata(req, viewdef, datamodel.ViewDefinition)
            vd.owner = req.user.name
            vd.org = req.org.name
            vd.metadata = req.metadata
            vd.put();

        viewmap = None
        if 'view_map' in data:
            viewmap = data['view_map']
        if viewmap:
            del viewmap['view_definition']
            vm = transformservice.reverse_transform_metadata(req, viewmap, datamodel.ViewMap)
            vm.view_definition = vd
            vm.owner = req.user.name
            vm.org = req.org.name
            vm.metadata = req.metadata
            vm.put();
                    
        return None    