import os
import sys
import string

import logging
import string
import uuid
import re

import json
import simplejson

import services.datamodel as datamodel
import services.securityservice as securityservice

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

import datetime
from services import constants, echoservice, shellservice, metadataservice, dataservice, securityservice, utils, datamodel, transformservice, requestcontext, appservice, dataloader, geohash, blobstore_helper

def log_exception(*args, **kwds):
  """Django signal handler to log an exception."""
  cls, err = sys.exc_info()[:2]
  logging.exception('Exception in request: %s: %s', cls.__name__, err)


# Log all exceptions detected by Django.
django.core.signals.got_request_exception.connect(log_exception)

# Unregister Django's default rollback event handler.
django.core.signals.got_request_exception.disconnect(
    django.db._rollback_on_exception)

#import others
import wsgiref.handlers
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.api import images
from google.appengine.api import users

def get_request_value(request, name, default=None):
    ret = request.get(name)
    if not ret:
        try:
            ret = request.cookies.get(name)
        except KeyError:
            pass
        if not ret:
            ret = default
    return ret
   
#http://localhost:8093/google/login?app=ParabayOrg_Friends&org=ParabayOrg 
class MainHandler(webapp.RequestHandler):
    def post(self):
        token=None       
        ret                 = {}
        ret['status']       = constants.STATUS_INVALID_PARAM
        
        try:
            
            app = get_request_value(self.request, 'app')
            org = get_request_value(self.request, 'org')
            friend = get_request_value(self.request, 'friend')
        
            u = users.get_current_user()
            if u:
                user = securityservice.SecurityService.userid_to_user(u.email())
                if user:
                    token = securityservice.SecurityService.generate_user_token(user)
                else:
                    new_user                 = {}
                    new_user['name']         = u.email()
                    new_user['email']        = u.email()
                    new_user['password']     = utils.new_key()
                
                    user = securityservice.SecurityService.register_user(new_user, app, org)
                    if user:
                        token = securityservice.SecurityService.generate_user_token(user)
                    
                fd = {}
                if friend and friend == '1':
                    gae_klazz = utils.loadModuleType('Friends', 'Friends_User')
                    query = gae_klazz.all()
                    query.filter('owner =', user.name)
                    query.filter('nick =', user.name)
                    friendUser = query.get()   
                    if friendUser:
                        fd["nick"] = friendUser.nick
                        fd["age"] = friendUser.age
                        fd["gender"] = friendUser.gender
                        fd["description"] = friendUser.description
                        fd["photo"] = friendUser.photo
                        fd["location"] = friendUser.location
                        fd["approved"] =  1 if friendUser.approved == '1' else 0  

                ret['name']         = user.name
                ret['email']        = user.email
                ret['token']        = token
                ret['friend']       = fd
                ret['status']       = constants.STATUS_OK
            #if u
        except Exception, e:
            ret['status'] = constants.STATUS_FATAL_ERROR
            ret['error_message'] = str(e)
            logging.error(traceback.format_exc())

        self.response.out.write(simplejson.dumps(ret))

def main():
    application = webapp.WSGIApplication([
        ('/google/login', MainHandler),
    ], debug=True)
    wsgiref.handlers.CGIHandler().run(application)

if __name__ == '__main__':
  main()

