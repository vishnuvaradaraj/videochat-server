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

from google.appengine.ext import db
from google.appengine.ext import blobstore

from django import http
from django import shortcuts
from django import template
from django.conf import settings
from django.template import loader
from django.core.cache import cache
from django.http import HttpResponseRedirect
from django.http import HttpResponse

import utils
import datamodel
import securityservice
import metadataservice

import json
import simplejson

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

def index(request):
    return HttpResponse(content='')

def login_login(request):

  #token       = utils.get_request_value(request, 'token')
  #if token:
  #    response = http.HttpResponseRedirect('/logout')
  #    return response

  token = None
  if request.POST:
    request.user = None
    try:
      username = request.POST.get('log', None)
      password = request.POST.get('pwd', None)
      rememberme = request.POST.get('rememberme', None)
      
      request.user    = securityservice.SecurityService.authenticate_user(username, password)
      if request.user:
          token   = securityservice.SecurityService.generate_user_token(request.user)   
            
      if not token:
          request.errors = 'Invalid username or password'
      else:
          request.errors = 'Login successful'
    except Exception, e:
      logging.error(str(e))
      request.errors = 'Failed to login'

  #if request.user:
  #  return http.HttpResponseRedirect('/login/logout')
  
  c = template.RequestContext(request, locals())    
  t = loader.get_template('login/login.html')
  response = http.HttpResponse(t.render(c))
  if token:
      utils.set_cookie(response, 'token', token)    
  return response

def login_logout(request):
  token       = utils.get_request_value(request, 'token')
  if token:
      securityservice.SecurityService.logoff_user_token(token)
      
  c = template.RequestContext(request, locals())
  t = loader.get_template('login/logout.html')

  response = http.HttpResponse(t.render(c))
  utils.set_cookie(response, 'token', '')
  return response

def login_forgot(request):

  if request.POST:
    try:
        email = request.POST.get('nick_or_email', None)
        res = securityservice.SecurityService.forgot_password(email)
        if not res:
            request.errors = 'Failed to retrieve user information.'
        else:
            request.errors = 'Please check your email for login information.'
    except Exception, e:
      logging.error(str(e))
      request.errors = 'Failed to recover password.'

  c = template.RequestContext(request, locals())
  t = loader.get_template('login/forgot.html')

  response = http.HttpResponse(t.render(c))
  return response
  
def login_join(request):
  # get the submitted vars
  nick = request.REQUEST.get('nick', '');
  first_name = request.REQUEST.get('first_name', '');
  last_name = request.REQUEST.get('last_name', '');
  email = request.REQUEST.get('email', '');
  password = request.REQUEST.get('password', '');
  confirm = request.REQUEST.get('confirm', '');

  if request.POST:
    if password != confirm:
        request.errors = 'Password does not match'
    else:
        try:
            app = 'ParabayOrg-Outlook'
            user = {}
            user['first_name'] = first_name
            user['last_name'] = last_name
            user['name'] = nick
            user['email'] = email
            user['password'] = password
    
            u = securityservice.SecurityService.register_user(user, app)
            if not u:
                request.errors = 'User already exists.'
            else:
                request.errors = 'Registration successful, please check your email for more information.' 
        except Exception, e:
          logging.error(str(e))
          request.errors = 'Failed to register user.'

  c = template.RequestContext(request, locals())
  t = loader.get_template('login/join.html')
  return http.HttpResponse(t.render(c))


def test_upload(request):
  # get the submitted vars
  upload_url = blobstore.create_upload_url('/api/upload_file/ParabayOrg-Friends?app=ParabayOrg-Friends&token=Uyd0b2tfZDM3NTUxNDIyZmNjZDJlNjExYWJhNmRlZjk0MjViZTYnCnAwCi5hODdiMjRlMGVmMjc5NzJkOTg0NTlhMDg5YTNjYzVhNg%3D%3D&key=Uyd0b2tfZDM3NTUxNDIyZmN')

  c = template.RequestContext(request, locals())
  t = loader.get_template('upload.html')
  return http.HttpResponse(t.render(c))