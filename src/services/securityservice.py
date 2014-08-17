import sys
import os
import base64
import md5
import random
import time
import logging
import traceback
import StringIO
import base64
import datetime

import datamodel
import settings
import emailservice

import utils

import cacheservice
from google.appengine.ext import db
from google.appengine.api import memcache
from google.appengine.api import users

WRITE_PERMISSION    = 'Write'
READ_PERMISSION     = 'Read'
SHARE_PERMISSION    = 'Share'
APPEND_PERMISSION   = 'Append'

class UserTokenStore(object): 
    def __init__(self, session_key=None): 
        self.session_key_prefix = 'tok' 
        
    def _get_new_token(self):
        "Returns token that isn't being used."
        # The random module is seeded when this Apache child is created.
        # Use settings.SECRET_KEY as added salt.
        try:
            pid = os.getpid()
        except AttributeError:
            # No getpid() in Jython, for example
            pid = 1
        while 1:
            session_key = md5.new("%s%s%s%s" % (random.randint(0, sys.maxint - 1),
                                  pid, time.time(), settings.SECRET_KEY)).hexdigest()
            if not self.exists(self._prefix_key(session_key)):
                break
        return self._prefix_key(session_key)
    
    def _prefix_key(self, session_key): 
        """ 
        Add prefix to session key to prevent BadArgumentError exceptions from 
        appengine (Names may not begin with a digit). 
        """ 
        return '%s_%s' % (self.session_key_prefix, session_key) 

    def find(self, session_key): 
        s = datamodel.UserToken.get_by_key_name(session_key) 
        if s and s.expire_date >= datetime.datetime.now(): 
            return s 
        else:
            return None
 
    def exists(self, session_key): 
        if datamodel.UserToken.get_by_key_name(session_key): 
            return True 
        return False 
 
    def create(self, user=None): 
        raw_token = self._get_new_token()
        token = datamodel.UserToken(key_name = raw_token,
                value = raw_token,
                user = user,
                expire_date = (datetime.datetime.now() + 
                    datetime.timedelta(seconds=settings.SESSION_AGE)) 
        )
        token.put()
        return token
 
    def delete(self, raw_token): 
        s = datamodel.UserToken.get_by_key_name(raw_token)
        if s: 
            memcache.delete('token_request:%s' % s.value)
            s.delete() 

    def expire(self, token_param):
        if not isinstance(token_param, datamodel.UserToken):
            token = self.find(token_param)
        else:
            token = token_param 
        
        if token:
            token.expire_date = datetime.datetime.now()
            token.put()
            memcache.delete('token_request:%s' % token.value)
            return token
        return None
    
    def expire_user_tokens(self, user):
        query = datamodel.UserToken.all()
        query.filter('user =', user)
            
        # TODO: security review
        tokens = query.fetch(128)
        for token in tokens:
            expire(token) 
            
class SecurityService(object):
    @staticmethod
    def _check_password(raw_password, enc_password):
        """
        Returns a boolean of whether the raw_password was correct. Handles
        encryption formats behind the scenes.
        """
        algo, salt, hsh = enc_password.split('$')
        if algo == 'md5':
            import md5
            return hsh == md5.new(salt+raw_password).hexdigest()
        elif algo == 'sha1':
            import sha
            return hsh == sha.new(salt+raw_password).hexdigest()
        raise ValueError, "Got unknown password algorithm type in password."

    @staticmethod
    def userid_to_user(userid):
        '''Convert userid to user object'''
        user = memcache.get('userid_user:' + userid)
        if not user:
            logging.debug('memcache miss for %r', userid)
            user = db.get(db.Key.from_path('User', userid))
            memcache.set('userid_user:%s' % userid, user)
        return user
    
    @staticmethod
    def role_name_to_role(name):
        '''Convert role name to role object'''
        return db.get(db.Key.from_path('Role', name))
    
    @staticmethod
    def perm_name_to_perm(name):
        '''Convert perm name to perm object'''
        if not isinstance(name, str):
            name = utils.format_perm(name)
            
        return db.get(db.Key.from_path('Permission', name))
    
    @staticmethod
    def get_user_roles(user, org = None):
        '''Get the roles for the user - obsoleted by User Model'''
        return user.roles_list(org)
    
    @staticmethod
    def get_user_perms(user, org=None):
        '''Get the permissions for the user - obsoleted by User Model'''
        if not req.user:
            return []        
        return user.perms_list(org)

    @staticmethod
    def user_has_perm(req, perm):
        "Returns user if the user has the specified permission."   
        if not req.user:
            return False
        return req.user.has_perm(req.org.name, perm)
    
    @staticmethod
    def is_user_in_role(req, role):
        "Check if the user is in a role"
        if not req.user:
            return False
        
        if isinstance(role, datamodel.Role):
            role = role.name
            
        if not req.user.is_active:
            return False
        if req.user.is_superuser:
            return True
        
        for r in req.roles:
            if r.name == role:
                return True
        return False

    @staticmethod
    def generate_user_token(user):
        "Generate a temp token"
        if not isinstance(user, datamodel.User):
            user = SecurityService.userid_to_user(user)    
        if not user:
            return None
            
        token_store = UserTokenStore()
        token = token_store.create(user)
        return utils.encode(token.value)
        
    @staticmethod
    def authenticate_user(user, password):
        "Authenticate an user"
        if not isinstance(user, datamodel.User):
            user = SecurityService.userid_to_user(user)
        
        if hasattr(user, 'activation_code') and user.activation_code:
            return None
        
        if user and SecurityService._check_password(password, user.password):
            return user
        else:
            return None
    
    @staticmethod
    def authenticate_user_token(blob):
        "authenticate a user from token"
        if not blob:
            return None
        
        token_store = UserTokenStore()
        raw_token = utils.decode(blob)
        
        token = token_store.find(raw_token)
        user = None
        if token:
            user = SecurityService.userid_to_user(token.user.name)
            if user and user.activation_code:
                user = None
            
        return user

    @staticmethod
    def logoff_user_token(blob):
        "authenticate a user from token"
        token_store = UserTokenStore()
        raw_token = utils.decode(blob)
        
        return token_store.expire(raw_token)
    
    @staticmethod
    def random_string(user):
        res = utils.encode(md5.new("%s%s%s" % (random.randint(0, sys.maxint - 1), 
                                                             time.time(), user.name)).hexdigest())
        logging.info(res)
        return res
        
    @staticmethod
    def create_user_org(user, orgName=None):
        "create org for user"
        
        if not orgName:
            orgName = user.name
            
        org = utils.find_entity_by_name(datamodel.Organisation, orgName)
        if not org:
            org = datamodel.Organisation(key_name=orgName)
            org.name=orgName
            org.admin = user
            org.owner = user.name
            org.put()
            return org
        else:
            return None
    
    
    @staticmethod
    def register_user(user, app=None, orgName=None):
        "register a new user"
        u = datamodel.User.get_or_insert(user['name'])
        
        if not u.email:
            for k in user:
                setattr(u, k, user[k])     
            u.password = utils.encode_password(u.password)       
            u.activation_code = None #SecurityService.random_string(u)
            u.chat_id = ''
            u.is_active = True
            u.put()
            
            SecurityService.create_user_org(u)                
            SecurityService.add_user_app_perms(u, app, orgName)
            
            u.set_dirty(True)
            u.update_cache_if_dirty()
            
            logging.info("Sending activation email: %s " % u.email)
            #emailservice.send_activation_email(u)
            return u
        
        return None
        
    @staticmethod
    def check_user_exists(email):
        "check if a user is already registered"
        if not email:
            return False
        
        query = datamodel.User.all()
        query.filter('email =', email)
        
        user = query.get()   
        ret = False
        if user:
            ret = True
            
        return ret
    
    @staticmethod
    def check_userid_exists(email):
        "check if a user is already registered"
        if not email:
            return False
          
        
        query = datamodel.User.all()
        query.filter('name =', email)
        
        user = query.get()   
        ret = False
        if user:
            ret = True

        return ret

    @staticmethod
    def forgot_password(email):
        "send an email to the user"
        if not email:
            return False
        
        query = datamodel.User.all()
        query.filter('email =', email)
        user = query.get()   
        
        if user:
            raw_password = SecurityService.random_string(user)[:8]
            user.password = utils.encode_password(raw_password)
            user.put()
        
            emailservice.send_password_reset(user, raw_password)
            
            user.set_dirty(True)
            user.update_cache_if_dirty()            
            return True
        
        return False
        
        
    @staticmethod
    def delete_user(user):
        "delete user account"
        if not isinstance(user, datamodel.User):
            user = SecurityService.userid_to_user(user)
            
        if user:
            token_store = UserTokenStore()
            token_store.expire_user_tokens(user)
            
            user.is_active = False
            user.put()          
            emailservice.send_account_deleted(user)            
            
            memcache.delete('userid_user:%s' % user.name)
            return True
        
        return False

    @staticmethod
    def resend_activation(email):
        "resend activation code"
        if (not email):
            return False
        
        query = datamodel.User.all()
        query.filter('email =', email)
        user = query.get()   
        
        if user:
            if user.activation_code:
                user.activation_code = SecurityService.random_string(user)
                user.put()
                emailservice.send_activation_email(user)
                
                user.set_dirty(True)
                user.update_cache_if_dirty()            
                return True
            
        return False

    @staticmethod
    def activate_user(code):
        "activate user account"
        query = datamodel.User.all()
        query.filter('activation_code =', code)
        user = query.get()
  
        if user:
            user.activation_code = None
            user.is_active = True
            user.put()

            user.set_dirty(True)
            user.update_cache_if_dirty()            
            return True
        
        return False

    @staticmethod
    def add_user_app_perms(user, app, org_name):
        "add permissions to the user"
        
        if not app:
            return
        
        if not isinstance(user, datamodel.User):
            user = SecurityService.userid_to_user(user)
            
        group_name = app + '.User-Group'      
        group = utils.find_entity_by_name(datamodel.Group, group_name)
        
        logging.info(group_name)
        if  user and group:
            if not hasattr(user, 'groups'):
                user.groups = []
            user.groups.append(group.key())            
            user.put()
                            
            user.set_dirty(True, org_name)
            user.update_cache_if_dirty()            
