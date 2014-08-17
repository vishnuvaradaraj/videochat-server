
import utils
import logging
import services.datamodel as datamodel
import services.securityservice as securityservice
import settings

from google.appengine.ext import db
from google.appengine.api import memcache

class RequestContext(object):
    def __init__(self, token, app=None, format=None):      
        self.org        = None
        self.metadata   = None
        self.app        = app
        self.format     = format
            
        self.set_app(app)

        self.user   = securityservice.SecurityService.authenticate_user_token(token)
        if self.user:
        	logging.info('User=%s' % (self.user.name))
        self.roles  = set()
        self.perms  = set()
        self.perms_map = {}
        
        if self.user and self.org:
            logging.info('Fetching permissions and roles')
            self.perms = set([ p.name for p in self.user.perms_list(self.org.name)])
            self.roles = set([ r.name for r in self.user.roles_list(self.org.name)])
            self.perms_map = self.user.perms_map(self.org.name)
            self.user.update_cache_if_dirty()
            
    def has_perm(self, perm):
        ret = False
        if self.user and self.org and self.app:
            perm_list    = [self.org.name, self.app.name]
            perm_list    = perm_list + perm
            ret = self.user.has_perm(self.org.name, perm_list)
            logging.info('has_perm(%s)=%s' % (perm, ret))
        else:
            logging.info('invalid param' + str(self.user) + ',' + str(self.org) + ',' + str(self.app))
        return ret
        
    def set_app(self, app):
        if app:
            self.app        = utils.find_entity_by_name(datamodel.App, app)
            if self.app:
                self.org        = self.app.org
                self.metadata   = self.app.metadata
            else:
                logging.info('Failed to fetch app:' + app)
        else:
            logging.info('request doesnt have app')
                        
def create_request(token, app=None, format=None):
    req = memcache.get('token_request:' + token)
    if not req:
        logging.debug('memcache miss for %r', token)
        req = RequestContext(token, app, format)
        memcache.add('token_request:%s' % token, req, settings.SESSION_AGE)
    req.set_app(app)
    return req
