import os
import sys
import string

import logging
import string
import uuid
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
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.api import images
from google.appengine.api import mail

from google.appengine.ext.webapp.mail_handlers import InboundMailHandler
from google.appengine.ext.webapp.util import run_wsgi_app

class MailHandler(InboundMailHandler):
  def receive(self, message):
    uemail = datamodel.UserEmail()
    uemail.sender = message.sender
    uemail.receiver = message.to
    uemail.subject = message.subject
    
    bodies = message.bodies(content_type='text/plain')
    allBodies = "";
    for body in bodies:
      # body[0] = "text/plain"
      # body[1] = EncodedPayload --> body[1].decode()
      allBodies = allBodies + "\n" + body[1].decode()
          
    uemail.body = allBodies
    uemail.put()
    pass

application = webapp.WSGIApplication([
  MailHandler.mapping()
], debug=True)

def main():
  run_wsgi_app(application)
if __name__ == "__main__":
  main()
  
  