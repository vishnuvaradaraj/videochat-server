import sys
import os
import logging
import traceback
import StringIO

import json
import simplejson

import datetime
import pytz
from itertools import izip 

from services import importhelpers
import services.securityservice as securityservice
import services.datamodel as datamodel
import services.metadataservice as metadataservice
import services.requestcontext as requestcontext
import services.utils as utils
import services.generalcounter as generalcounter

from google.appengine.ext import db, search

class DataService(object):
    '''
    Provides access to data
    '''
    @staticmethod
    def build_data_query(gq, q, data_query):
        ret = gq
        
        params = data_query.params
        if 'data_query_params' in q:
            params = q[data_query_params]
            
        if data_query.filters and params:
            for index in range(len(params)):
                ret.filter(data_query.filters[index], params[index])
            
        if data_query.orders:
            for item in data_query.orders:
                ret.order(item)

        return ret
    
    @staticmethod
    def GetImportStatementForType(type_name):
        ret = 'import_str'
        type_info = utils.find_entity_by_name(datamodel.TypeInfo, type_name)
        if type_info and type_info.import_type:
            ret = type_info.import_type
        return ret
        
    @staticmethod
    def build_query(gq, q):
        ret = gq
        for f in q['filters']:
            import_statement = DataService.GetImportStatementForType(f['type'])
            converter = utils.loadImportConverter(import_statement)  
            val = converter(f['param'])            
            ret.filter(f['condition'], val)
            
        for o in q['orders']:
            ret = ret.order(o)
        return ret
    
    @staticmethod
    def filter_query(req, query):
        query.filter('org =', req.org.name)
        
        if (not hasattr(req.app, 'security')) or (req.app.security == 'Private'):
            query.filter('owner =', req.user.name)
            
        return query
 
    @staticmethod
    def filter_data(req, data, em):
        ret = data
                   
        if em.public_columns or em.owner_columns:
            col_list = []
            if em.public_columns:
                col_list = em.public_columns.split(';')

            ret = []
            for d in data:
    
                enable_filter = False
                if d.owner != req.user.name:
                    if em.owner_columns:
                         if getattr(d, em.owner_columns) != req.user.name:
                            enable_filter = True
                    else:
                        enable_filter = True
    
                dd = {}
                if enable_filter:
                    if hasattr(d, 'isPrivate') and getattr(d, 'isPrivate'):
                        d = {}
                    else:
                        for col in col_list:
                            if hasattr(d, col):
                                dd[col] = getattr(d, col)                    
                else:
                    dd = d
    
                ret.append(dd)
        return ret
   
    #search_query, kind, columns, filters, orders, data_query, data_query_params
    # note on cursors: bookmark works across inserts, but cursors don't!!!
    @staticmethod
    def list(req, q, limit, offset=0, bookmark=None, cursor=None):
        data_query  = None
        kind        = None
        
        if 'data_query' in q and q['data_query']:
            data_query  = metadataservice.find_data_query(req, q['data_query'])
            kind        = data_query.type_of
        else:
            kind        = q['kind']
        
           
        em = metadataservice.find_entity_metadata(req, kind)
        if not em:
            logging.error('Invalid entity metadata type:%s' % (kind))
            return None
        
        #req.app.metadata.name
        gae_klazz = utils.loadModuleType(req.metadata.name, kind)

        gq = gae_klazz.all()
        
        # handle bookmark
        if bookmark:
            gq.filter("bookmark <", bookmark)
        gq.order("-bookmark")
        
        if 'fulltext_search' in q and  q['fulltext_search']:
            gq = gq.search(q.query)
        elif data_query:
            gq = DataService.build_data_query(gq, q, data_query)
        else:
            gq = DataService.build_query(gq, q)
        
        #apply generic filters
        if not em.public_columns:
            gq = DataService.filter_query(req, gq)
            
        if not ('include_deleted_items' in q and  q['include_deleted_items']):
            gq.filter('is_deleted =', False)
        
        if bookmark is None : 

            logging.info('legacy query')
            data = gq.fetch(limit+1, offset)

            nextBookmark = None
            if len(data) == limit+1:
                nextBookmark = data[-1].bookmark
                data = data[:limit]               
            if nextBookmark is None:
                nextBookmark = ""

            result = {'data': data, 'count': gq.count(), 'sync_token': nextBookmark, 'cursor':gq.cursor()}
        elif cursor:

            data = gq.with_cursor(cursor).fetch(limit)
            result = {'data': data, 'count': 0, 'sync_token': gq.cursor()}
        else:    
            nextBookmark = None
                        
            #logging.info('Data bookmark=' + bookmark)
            data = gq.fetch(limit+1)
            if len(data) == limit+1:
                #logging.info('More rows with bookmark=' + str(data[-1].bookmark))
                nextBookmark = data[-1].bookmark
                #logging.info('Next Data bookmark=' + nextBookmark)
                data = data[:limit]
            #elif len(data) > 0:
            #    nextBookmark = "data[-1].bookmark"
                
            if nextBookmark is None:
                nextBookmark = ""
                
            count = generalcounter.get_count(kind)
            result = {'data': data, 'count': count, 'sync_token': nextBookmark}
        #logging.info("List request: result count = %d.", gq.count());
        
        if em.public_columns:
            result['data'] = DataService.filter_data(req, result['data'], em)

        return result
    
    @staticmethod
    def save(req, entity, datatype):
        
        # special logic for ensuring unique friends.
        if datatype == 'Friends_User':
            gae_klazz = utils.loadModuleType(req.metadata.name, "Friends_User")
            q = gae_klazz.all()
            q.filter('nick =', entity.nick)
            friendUser = q.get()
            
            if friendUser:
                if friendUser.org == req.org.name and friendUser.owner == req.user.name:
                    logging.info('Found user:' + entity.nick)     
                    if  hasattr(entity, 'peerId'):             
                        friendUser.peerId = entity.peerId
                    if hasattr(entity, 'photo'):      
                        friendUser.photo = entity.photo
                    if hasattr(entity, 'location'):      
                        friendUser.location = entity.location
                    if hasattr(entity, 'approved'):      
                        friendUser.approved =  '1' if entity.approved == '1' else 0
                    entity = friendUser  
                else:
                    logging.info('User doesnt own this friend:' + entity.nick )
                    return entity
            else:
                logging.info('New friend to be saved:' + entity.nick)
                    
        entity.org      = req.org.name
        entity.owner    = req.user.name
        entity.updated  = datetime.datetime.now()
        entity.bookmark = utils.bookmark_for_kind(datatype, req.user.name, entity.updated)
        entity.is_deleted = False
        entity.put()
        
        return entity
    
    @staticmethod
    def delete(req, datakey, datatype):
        key_obj = db.Key.from_path(datatype, datakey)
        
        em = metadataservice.find_entity_metadata(req, datatype)
        if not em:
            logging.error('Invalid entity metadata type:%s' % (datatype))
            return False
        gae_klazz = utils.loadModuleType(em.metadata.name, em.name)
        
        data    = gae_klazz.get(key_obj)
        if data and (data.org == req.org.name or data.owner == req.user.name):
            data.is_deleted = True
            data.put()
            return True
        return False

    @staticmethod
    def cron_erase(app, datatype, max_count=50):      
        
        gae_klazz = utils.loadModuleType(app, datatype)
        
        query    = db.Query(gae_klazz, keys_only=True)
        query.filter('StartDate <', datetime.datetime.now() - datetime.timedelta(days=1))
        items = query.fetch(max_count)
        db.delete(items)
        return 0
    
    @staticmethod
    def cron_push_items(items, devtok):
        ret = 0
        if devtok.device_token is None:
            return 0
        
        pushed_items = []
        pushed_messages = []
        for item in items:
            logging.info(item)
            if hasattr(item, 'push_url') and item.push_url is not None:
                continue
            
            if hasattr(item, 'AlertMessage'):
                alertMsg = item.AlertMessage
                badgeNumber = 0
                schedule = item.AlertTime
                if schedule > datetime.datetime.utcnow():
                    push_message = {"schedule_for": schedule.strftime('%Y-%m-%d %H:%M:%S'), "aps": {"badge": badgeNumber, "alert": alertMsg, "sound": "default"}, "device_tokens": [devtok.device_token]}
                    pushed_messages.append(push_message)
                    pushed_items.append(item)
                    ret = ret+1
                
        response = utils.send_batch_push_notification(pushed_messages)
        if response:
            urls = simplejson.JSONDecoder().decode(response)
            if not urls is None:
                for url,item in izip(urls['scheduled_notifications'], pushed_items):
                    logging.info('%s -> %s' % (url, item))
                    item.push_url = url
                    item.AlertMessage = None
                    item.AlertTime = None
                    item.put()
            else:
                #TODO temporary workaround for empty response
                logging.info('Got empty response string from Urban airship')
                for item in pushed_items:
                    item.AlertMessage = None
                    item.AlertTime = None
                    item.put()
                
        return ret
    
    @staticmethod
    def cron_push(app, datatype, max_count=10):      
        
        total_pushed = 0
        
        gae_klazz = utils.loadModuleType(app, datatype)
        
        devtok_query = datamodel.UserDevice.all()
        devtoks = devtok_query.fetch(5)
        for devtok in devtoks:
            query    = db.Query(gae_klazz)
            now = datetime.datetime.utcnow()
            #today = datetime.datetime(now.year, now.month, now.day)
            query.filter('AlertTime >=', now) 
            query.filter('owner =', devtok.owner)
            query.order('AlertTime')
            items = query.fetch(max_count)
            
            try:   
                #get 10 items and ensure that they already had 
                push_count = DataService.cron_push_items(items, devtok)
                total_pushed += push_count
            except Exception, e:
                logging.error('Error sending notifications for: ' + devtok.owner)
                logging.error(traceback.format_exc())
                
        logging.info('Pushed notifications: %d' % (total_pushed)) 
        return 0
        
    @staticmethod
    def bulk_erase(req, datatype, id_list):      
        
        gae_klazz = utils.loadModuleType(req.metadata.name, datatype)
        
        for id_value in id_list:
            key_obj = db.Key.from_path(datatype, id_value)
            data    = gae_klazz.get(key_obj)
            if data:
                data.is_deleted = True
                data.put()
        return 0
    
    @staticmethod
    def get(req, datakey, datatype):
        '''
        item lookup
        '''
        ret     = None
                
        #req.app.metadata.name
        gae_klazz = utils.loadModuleType(req.metadata.name, datatype)

        key_obj = db.Key.from_path(datatype, datakey)
        data    = gae_klazz.get(key_obj)
        
        logging.info('getting data')
        
        if data and hasattr(data, 'is_deleted') and data.is_deleted:
            data = None
                
        em = metadataservice.find_entity_metadata(req, datatype)
        if not em:
            logging.error('Invalid entity metadata type:%s' % (datatype))
            return False

        if em.public_columns:
            res = DataService.filter_data(req, [data], em)
            data = res[0]

        return data
    
    @staticmethod
    def create_related(req, data, datatype, parent_key, parent_datatype, relation):
        return DataService.save(req, data, datatype)
    
    @staticmethod
    def add_related(req, data, datatype, parent_key, parent_datatype, relation):
        return DataService.save(req, data, datatype)
    
    @staticmethod
    def remove_related(req, data, datatype, parent_key, parent_datatype, relation):
        return DataService.delete(req, data, datatype)
            
    @staticmethod
    def lookup_entity_prefix(req, prefix, datatype, lookup_key):
        '''
        Foreign key lookup
        '''
        gae_klazz     = utils.loadModuleType(req.app.metadata.name, datatype)
        query = gae_klazz.all()
        query.filter( lookup_key + ' >=', prefix)
        query.filter( lookup_key + ' <=', prefix + 'z')
        res =  query.fetch(10)
        
        result = []
        for data in res:
            item = { 'id' : str(data.key().name()), 'name' : getattr(data, lookup_key)}
            result.append(item)
        return result
    
    @staticmethod
    def lookup_entity_name(req, datakey, datatype, lookup_key):
        '''
        Name lookup
        '''
        key_obj = db.Key.from_path(datatype, datakey)
        data    = db.Model.get(key_obj)
        
        return getattr(data, lookup_key)
    
    @staticmethod
    def upload_file(req, fileName, fileSize, fileType, byteArray):
        """ 
        Allows the upload of binary data
        """
        file = datamodel.UploadedFile()
        file.fileBlob = db.Blob(str(byteArray))
        file.fileName = fileName
        file.fileSize = fileSize
        file.fileType = fileType
        file.url      = "/assets/download/%s/%s" % (req.user.name, fileName)
        file.put()
    
    @staticmethod    
    def uploaded_files(req, pattern=None, limit=10, offset=0):
        """
        Get the list of uploaded files
        """
        query = datamodel.UploadedFile.all()
        result = query.fetch(limit, offset)
                
        return res
