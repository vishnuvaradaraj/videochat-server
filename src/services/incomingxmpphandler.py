import datetime
import time
import os
import random
import string
import sys
import logging
import traceback
import uuid
import urllib
import re

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

from google.appengine.api import xmpp
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

from services import constants, echoservice, shellservice, metadataservice, dataservice, securityservice, utils, datamodel, transformservice, requestcontext, appservice, dataloader, geohash, blobstore_helper

class XMPPHandler(webapp.RequestHandler):
  def post(self):
    message = xmpp.Message(self.request.POST)
    
    to_address = message.to.split('@')[0] 
    from_email_address = message.sender.split('/')[0] 
    logging.info('xmpp searching for: ' + to_address + ' from ' + from_email_address )
    
    chat_message_sent = False    
    gae_klazz_user = utils.loadModuleType("Friends", "Friends_User")
    uq = gae_klazz_user.all()
    uq.filter('nick =', to_address)
    friend = uq.get()
    
    uq = gae_klazz_user.all()
    uq.filter('emailAddress =', from_email_address)
    sender = uq.get()
    
    if friend and sender:
        status_code = xmpp.send_message(friend.emailAddress, message.body)
        chat_message_sent = (status_code != xmpp.NO_ERROR)
        logging.info('XMPP send to:' + friend.emailAddress + ' = ' + str(status_code))
    
        if not chat_message_sent:    
            logging.info('Failed to send message')
            gae_klazz_queue = utils.loadModuleType("Friends", "Friends_Queue")
            q = gae_klazz_queue(key_name=utils.new_key())
            q.owner = sender.name
            q.targetUser = to_address
            q.comments = message.body
            q.org = 'ParabayOrg'
            q.isPrivate = False 
            q.itemType = 1
            q.updated  = datetime.datetime.now()
            q.bookmark = utils.bookmark_for_kind('Friends_Queue', sender.name, q.updated)
            q.put()
            message.reply("The user is currently offline. Your message will be delivered when the user is online.")
        else:
            logging.info('Sent message')
    else:
        logging.info('invalid friend:' + to_address + ', ' + from_email_address)
        
application = webapp.WSGIApplication([('/_ah/xmpp/message/chat/', XMPPHandler)],
                                     debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
