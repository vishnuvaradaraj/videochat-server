import os
import sys

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
import cgi
import wsgiref.handlers
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.api import images

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

class FileListHandler(webapp.RequestHandler):
  def get(self):
    user = None
    token = get_request_value(self.request, 'token')
    if token:
          user   = securityservice.SecurityService.authenticate_user_token(token)
    
    if user:      
        self.response.out.write('<html><body>')
        query_str = "SELECT * FROM UploadedFile WHERE owner = '" + user.name + "' LIMIT 10"
        files = db.GqlQuery (query_str)
            
        for f in files:
          self.response.out.write("<div><a href='%s'>%s</a></div>" %
                                  (f.url, cgi.escape(f.fileName)))
    
        self.response.out.write("""
              <form action="/assets" enctype="multipart/form-data" method="post">
                <div><label>Upload test file:</label></div>
                <div><input type="file" name="upload"/></div>
                <div><input type="submit" value="Upload"></div>
              </form>
            </body>
          </html>""")
    else:
        self.response.out.write('Access denied')
    
def main():
    application = webapp.WSGIApplication([
        ('/assetlist', FileListHandler),
    ], debug=True)
    wsgiref.handlers.CGIHandler().run(application)

if __name__ == '__main__':
  main()
