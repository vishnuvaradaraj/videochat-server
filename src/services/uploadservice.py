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

import datetime
from services import constants, utils


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


class InitUploadHandler(webapp.RequestHandler):
    def get(self, app):
        token = get_request_value(self.request, 'token')
        
        if token: 
            key = utils.new_key()
            upload_url = '/assets/upload/%s/%s' % (key, token)
            file_url = '/assets/upload?id=%s' % (key) 
            thumbnail_url = '/assets/upload?id=%s&size=thumbnail' % (key) 
            json_ret = '{"status": "0", "id": "%s", "uploadUrl": "%s", "fileUrl": "%s", "thumbnailUrl" : "%s"}' % (key, upload_url, file_url, thumbnail_url)
            self.response.out.write(json_ret)
            
        else:
            logging.error('File upload failed, invalid token')
            self.error(401)
    

class FileUploadHandler(webapp.RequestHandler):
    def get(self):        
        file = None
        user = None
        
        #token = get_request_value(self.request, 'token')
        fid = get_request_value(self.request, 'id')
        fsize = get_request_value(self.request, 'size', 'original')
        
        #if token:
        #  user   = securityservice.SecurityService.authenticate_user_token(token)
        if fid:
          file = utils.find_entity_by_name (datamodel.UploadedFile, fid)
          logging.info(fsize)
          
        if file and fsize=='original' and file.fileBlob:
          self.response.headers['Content-Type'] = str(file.fileType)
          self.response.out.write(file.fileBlob)
          
        elif file and fsize=='thumbnail' and file.thumbnailBlob:
          self.response.headers['Content-Type'] = str(file.fileType)
          self.response.out.write(file.thumbnailBlob)       
          
        elif file and fsize and file.fileSize < 2097152 and file.fileBlob:
          sizes = string.split(fsize, 'x')
          if (len(sizes) == 2):
              result = images.resize(file.fileBlob, int(sizes[0]), int(sizes[1]))
              self.response.headers['Content-Type'] = str(file.fileType)
              self.response.out.write(result)     
          else:
              self.error(404)
        else:
          self.error(404)
    
    def post(self, key, token):     
        #token = get_request_value(self.request, 'token')
        data = get_request_value(self.request, 'file')
        #key = get_request_value(self.request, 'id')
        user   = securityservice.SecurityService.authenticate_user_token(token)
        
        if key is None:
            key = utils.new_key()
            logging.info('No id in request: %s', key)
                   
        #logging.info(self.request)
        if user and data: # and len(data)<=2097152:
            file = datamodel.UploadedFile(key_name = key)
            file.ip = self.request.remote_addr
                        
            file.fileName = self.request.POST.get('file').filename;
            if not file.fileName:
                file.fileName = str(uuid.uuid1())     
            logging.info(file.fileName)
            
            file.fileType = None #self.request.headers.get('Content-Type')
            if not file.fileType:
                file.fileType = 'image/png'
            logging.info(file.fileType)
            
            if 'image' in file.fileType:
                img = images.Image(data)
                file.width = img.width
                file.height = img.height
                
            if len(data)<=524288 and 'image' in file.fileType:
                file.thumbnailBlob = db.Blob(images.resize(data, 96, 96))

            file.fileBlob = db.Blob(data)  
            file.fileSize = len(data)
            file.owner = user.name
            file.is_deleted = False
            file.updated = datetime.datetime.now()
            file.bookmark = utils.bookmark_for_kind('UploadedFile', user.name, file.updated)
            file.put()
            
            file.url = '/assets/upload?id=%s' % (key) 
            if file.thumbnailBlob:
                file.thumbnail = '/assets/upload?id=%s&size=thumbnail' % (key) 
            file.put()
            
            json_ret = '{"status": "0", "id": "%s", "url": "%s"}' % (key, file.url)
            self.response.out.write(json_ret)
            
        else:
            logging.error('File upload failed, upload key is missing or file size > 2MB')
            self.error(401)
    
class MainHandler(webapp.RequestHandler):
    def get(self):
        token = get_request_value(self.request, 'token')
        key = utils.new_key()
        upload_url = '/assets/upload/%s/%s' % (key, token)
        #upload_url = '/assets/upload'
        self.response.out.write('<html><body>')
        self.response.out.write('<form action="%s" method="POST" enctype="multipart/form-data">' % upload_url)
        #self.response.out.write('<input type="hidden" name="id" value="%s"> <input type="hidden" name="token" value="%s">' % (utils.new_key() , token))
        self.response.out.write("""Upload File: <input type="file" name="file"><br><input type="submit" 
            name="submit" value="Submit"> </form></body></html>""")


def main():
    application = webapp.WSGIApplication([
        ('/assets/init_upload/(.*)', InitUploadHandler),
        ('/assets/upload', FileUploadHandler),
        ('/assets/upload/(.*)/(.*)', FileUploadHandler),
        ('/assets/testupload', MainHandler),
    ], debug=True)
    wsgiref.handlers.CGIHandler().run(application)

if __name__ == '__main__':
  main()

