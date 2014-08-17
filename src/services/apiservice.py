#!/usr/bin/env python

__author__ = 'Vishnu Varadaraj'

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

from services import constants, echoservice, shellservice, metadataservice, dataservice, securityservice, utils, datamodel, transformservice, requestcontext, appservice, dataloader, geohash, blobstore_helper
import services.schemaloader as schemaloader

from google.appengine.ext import db
from google.appengine.ext.db import djangoforms
from google.appengine.ext.webapp import template
from google.appengine.api import memcache
from google.appengine.api.labs import taskqueue
from google.appengine.ext import blobstore
from google.appengine.api import images
from google.appengine.api import xmpp

import django
from django import http
from django import shortcuts
from django.http import HttpResponseRedirect, HttpResponse, HttpRequest

import json
import simplejson

_DEBUG = os.environ['SERVER_SOFTWARE'].startswith('Dev')  # Development server
        
def login_required(func):
  """Decorator that redirects to the login page if you're not logged in."""

  def login_wrapper(request, app, *args, **kwds):
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token   = get_request_value(request, 'token')
        if token and app:
            
            req = requestcontext.create_request(token, app)            
            if not req.has_perm([securityservice.READ_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED    
            else:
                request.req = req
                return func(request, app, *args, **kwds)
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
    
    return HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

  return login_wrapper


def admin_required(func):
  """Decorator that insists that you're logged in as administratior."""

  def admin_wrapper(request, app, *args, **kwds):
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token   = get_request_value(request, 'token')
        if token and app:
            
            req = requestcontext.create_request(token, app)            
            if not req.has_perm([securityservice.WRITE_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED    
            else:
                request.req = req
                return func(request, app, *args, **kwds)
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
    
    return HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

  return admin_wrapper

def su_required(func):
  """Decorator that insists that you're logged in as administratior."""

  def su_wrapper(request, *args, **kwds):
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token   = get_request_value(request, 'token')
        if token:
            user   = securityservice.SecurityService.authenticate_user_token(token)
            if not user.is_superuser:
                ret['status']   = constants.STATUS_ACCESS_DENIED    
            else:
                return func(request, *args, **kwds)
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
    
    return HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

  return su_wrapper

#http://localhost:8080/api/login?username=vishnuv&password=sa1985&friend=1
def login(request):
    logging.info('login')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM
    
    try:
        username = get_request_value(request, 'username') 
        password = get_request_value(request, 'password')
        friend = get_request_value(request, 'friend')
    
        logging.info('Logging in: %s' % username)
        
        token = None
        
        if username and password:
            ret['status']       = constants.STATUS_ERROR
            fd                     = None

            user    = securityservice.SecurityService.authenticate_user(username, password)    
            if user:
                token   = securityservice.SecurityService.generate_user_token(user)
            
                if friend and friend == '1':
                    gae_klazz = utils.loadModuleType('Friends', 'Friends_User')
                    query = gae_klazz.all()
                    query.filter('owner =', username)
                    query.filter('nick =', username)
                    friendUser = query.get()   
                    if friendUser:
                        fd = {}
                        fd["nick"] = friendUser.nick
                        fd["age"] = friendUser.age
                        fd["gender"] = friendUser.gender
                        fd["description"] = friendUser.description
                        fd["photo"] = friendUser.photo
                        fd["location"] = friendUser.location
                        fd["approved"] =  1 if friendUser.approved == '1' else 0  

                ret                 = {}
                
                ret['name']         = user.name
                ret['email']        = user.email
                ret['token']        = token
                ret['friend']       = fd
                ret['status']       = constants.STATUS_OK
    
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain") 

    if token:
        utils.set_cookie(response, 'token', token)

    return response

#http://localhost:8080/api/logout?token=
def logout(request):
    logging.info('logout')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')

        if token:
            securityservice.SecurityService.logoff_user_token(token)
        
            ret['status']   = constants.STATUS_OK

    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
    
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    utils.set_cookie(response, 'token', '')

    return response

#http://localhost:8080/api/register_user?user={"password":%20"mon","name":%20"varadarajan",%20"first_name":%20"Varadarajan",%20"last_name":%20"Raghavan",%20"phone":%20"011-91-470-2601633",%20"email":%20"varadarajan@gmail.com"}&app=ParabayOrg-Outlook
def register_user(request):
    "register a new user"
    
    logging.info('register user')
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        user    = get_request_value(request, 'user') 
        app     = get_request_value(request, 'app', None)
        
        if user:
            user = simplejson.JSONDecoder().decode(user);
            
            ret['status']   = constants.STATUS_ERROR
            u = securityservice.SecurityService.register_user(user, app)
            if u:
                ret['name']         = u.name
                ret['email']        = u.email
                ret['token']        = securityservice.SecurityService.generate_user_token(u)
            
                ret['status']   = constants.STATUS_OK
            else:
                ret['status']   = constants.STATUS_EXISTING_USER;
      
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
              
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

def check_user_exists(request):
    "check if a user is already registered"
    
    logging.info('check_user_exists')
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        email     = get_request_value(request, 'email', None)
    
        if email:
            ret['status']   = constants.STATUS_ERROR
            res = securityservice.SecurityService.check_user_exists(email)
            if res:
                ret['status']   = constants.STATUS_OK
   
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())

    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

#http://192.168.0.105:8080/api/check_userid?userid=vishnuv
def check_userid(request):
    "check if a user id is already registered"
    
    logging.info('check_user_id')
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        email     = get_request_value(request, 'userid', None)
    
        if email:
            ret['status']   = constants.STATUS_ERROR
            res = securityservice.SecurityService.check_userid_exists(email)
            if res:
                ret['status']   = constants.STATUS_OK
   
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())

    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

def forgot_password(request):
    "User forgot password"
    
    logging.info('forgot_password')
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        email     = get_request_value(request, 'email', None)
    
        if email:
            ret['status']   = constants.STATUS_ERROR
            res = securityservice.SecurityService.forgot_password(email)
            if res:
                ret['status']   = constants.STATUS_OK
          
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
          
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

def resend_activation(request):
    "Resend activation email"
    
    logging.info('resend_activation')
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        email     = get_request_value(request, 'email', None)
    
        if email:
                ret['status']   = constants.STATUS_ERROR
                res = securityservice.SecurityService.resend_activation(email)
                if res:
                    ret['status']   = constants.STATUS_OK
                
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)                
        logging.error(traceback.format_exc())
            
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

def activate_user(request):
    "active user account"
    
    logging.info('activate_user')
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        code     = get_request_value(request, 'code')
    
        if code:
            ret['status']   = constants.STATUS_ERROR
            res = securityservice.SecurityService.activate_user(code)
            if res:
                ret['status']   = constants.STATUS_OK
       
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
                    
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

def delete_user(token):
    "Delete user account"
    
    logging.info('delete_user')
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token     = get_request_value(request, 'token')
    
        if token:
            ret['status']   = constants.STATUS_ERROR
            req = requestcontext.create_request(token)
            res = securityservice.SecurityService.delete_user(req.user)
            if res:
                ret['status']   = constants.STATUS_OK
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
                    
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response
    
#http://localhost:8080/api/validate_user_token?token=
def validate_user_token(request):
    "validate user account"
    
    logging.info('validate_user_token')
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        app         = get_request_value(request, 'app', None)
    
        if token:
            ret['status']       = constants.STATUS_ERROR
            
            req                 = requestcontext.create_request(token, app)   
            if req.user:                    
                u                   = {}
                u['name']           = req.user.name
                u['first_name']     = req.user.first_name
                u['last_name']      = req.user.last_name
                u['email']          = req.user.email
                u['phone']          = req.user.phone
                
                ret['user']         = u
                ret['status']       = constants.STATUS_OK   
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
                 
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

#http://localhost:8080/api/list/ParabayOrg-Outlook?query={"columns":%20[],%20"kind":%20"Calendar_Appointment",%20"filters":%20[{"condition":"StartDate >", "param":"26/07/2009","type":"date"}],%20"orders":%20["StartDate", "StartTime"]}
#http://localhost:8080/api/list/ParabayOrg-Outlook?query={"columns":%20[],%20"kind":%20"Calendar_Appointment",%20"filters":%20[ {"condition":"updated > ","param":"2009-09-02T00:53:41.948000","type":"timestamp"}],%20"orders":%20[]}
#http://localhost:8080/api/list/ParabayOrg-Outlook?query={"columns":%20[],%20"kind":%20"Timmy_Store",%20"filters":%20[],%20"orders":%20[]}
#Query: search_query, kind, columns, filters, orders, data_query,data_query_params
#http://192.168.0.103:8080/api/list/ParabayOrg-Outlook?query={"columns":%20[],%20"kind":%20"Timmy_Store",%20"filters":%20[{"condition":"bookmark > ","param":"","type":"string"}],%20"orders":%20[]}
def list_data(request, app):
    '''List the data'''
    
    logging.info('list data:' + app )

    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token   = get_request_value(request, 'token')
        query   = get_request_value(request, 'query')
        bookmark   = get_request_value(request, 'bookmark')
        limit   = get_request_value(request, 'limit', "10")
        offset  = get_request_value(request, 'offset', "0")
        logging.info(query)
        
        if token and app and query:
            
            req = requestcontext.create_request(token, app)            
            if not req.has_perm([securityservice.READ_PERMISSION]):
                logging.info('No read access; check if app is defined')
                ret['status']   = constants.STATUS_ACCESS_DENIED
                
            else:
                ret['data']     = [{}]
                ret['count']    = 0
                ret['sync_token'] = ''

                q       = simplejson.JSONDecoder().decode(query)
                result  = dataservice.DataService.list(req, q, int(limit), int(offset), bookmark)
                data    = transformservice.normalize_results(req, result['data'], q['kind'])

                ret['status']   = constants.STATUS_OK
                
                if data and len(data)>0:
                    logging.info('Got valid list results...')
                    ret['count']    = result['count']                    
                    ret['data']     = data
                    
                if result:
                    ret['sync_token'] = result['sync_token']
                    #cursor doesn't allow incremental fetch across inserts.
                    #ret['cursor'] = result['cursor']
                    #logging.info(ret)
        else:
            logging.info('Invalid token, app or query')
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
    
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response

#http://localhost:8080/api/get/ParabayOrg-Outlook/Calendar_Appointment/k023ecb40-be25-11dd-b96c-63515cb8edc7?token=Uyd0b2tfODkxZTIwMjU0OTBmYzhlNDRlZTBjMzIyZDI0MzM1OGEnCnAwCi5hNDJiMmY4ZjdlMmUwMzBiNDUzMzc0M2JiM2EyZTU1Yw%3D%3D
def get_data(request, app, datatype, datakey):
    '''Get data'''
    
    logging.info('get data')

    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        
        if token and app and datakey and datatype:
            req = requestcontext.create_request(token, app)
            if not req.has_perm([securityservice.READ_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
            
            else:
                result = dataservice.DataService.get(req, datakey, datatype)
                    
                if result:
                    ret['data']     = transformservice.transform(req, result, datatype)
                    ret['status']   = constants.STATUS_OK
        else:
             logging.info('Not getting data')           
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    logging.info('Return status = ' + str(ret['status']))
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response

#http://localhost:8080/api/save/ParabayOrg-Outlook/Calendar_Appointment?token=Uyd0b2tfODkxZTIwMjU0OTBmYzhlNDRlZTBjMzIyZDI0MzM1OGEnCnAwCi5hNDJiMmY4ZjdlMmUwMzBiNDUzMzc0M2JiM2EyZTU1Yw%3D%3D&data={"MeetingOrganizer":%20"Varadaraj,%20Vishnu2",%20"Subject":%20"Subaru%20Forrester%20appt2."}
def save_data(request, app, datatype):
    '''Save data'''
    logging.info('save data')

    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        data        = get_request_value(request, 'data')
    
        if token and app and data and datatype:
            req = requestcontext.create_request(token, app)
            if not req.has_perm([securityservice.WRITE_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
            
            else:
                data    = simplejson.JSONDecoder().decode(data)
                data    = transformservice.reverse_transform(req, data, datatype)
                
                result  = dataservice.DataService.save(req, data, datatype)
                if result:
                    ret['id']         = str(result.key().name())
                    ret['status']   = constants.STATUS_OK
                    
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
            
    logging.info('Return status = ' + str(ret['status']))
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response

#http://localhost:8080/api/savearray/ParabayOrg-Outlook/Calendar_Appointment?data=[{"MeetingOrganizer":%20"Varadaraj,%20Vishnu2",%20"Subject":%20"Subaru%20Forrester%20appt2."}]
def save_data_array(request, app, datatype):
    '''Save data'''
    logging.info('save data array')

    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        data        = get_request_value(request, 'data')
    
        if token and app and data and datatype:
            req = requestcontext.create_request(token, app)
            if not req.has_perm([securityservice.WRITE_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
            
            else:
                data    = simplejson.JSONDecoder().decode(data)
                data    = transformservice.denormalize_results(req, data, datatype)
                
                save_status = {}
                for item in data:
                    save_status[item.key().name()] = False
                    result = dataservice.DataService.save(req, item, datatype)
                    if result:
                        save_status[item.key().name()] = True
                    
                ret['save_status']  = save_status
                ret['status']       = constants.STATUS_OK
                    
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
            
    logging.info('Return status = ' + str(ret['status']))
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response


#http://localhost:8080/api/delete/ParabayOrg-Outlook/Calendar_Appointment/k023ecb40-be25-11dd-b96c-63515cb8edc7?token=Uyd0b2tfODkxZTIwMjU0OTBmYzhlNDRlZTBjMzIyZDI0MzM1OGEnCnAwCi5hNDJiMmY4ZjdlMmUwMzBiNDUzMzc0M2JiM2EyZTU1Yw%3D%3D    
def delete_data(request, app, datatype, datakey):
    '''Delete data'''
    
    logging.info('delete data')

    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    token       = get_request_value(request, 'token')
    
    try:
        if token and app and datakey and datatype:
            req = requestcontext.create_request(token, app)
            if not req.has_perm([securityservice.WRITE_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
            
            else:
                ret['status']   = constants.STATUS_ERROR
                if dataservice.DataService.delete(req, datakey, datatype):
                    ret['status']   = constants.STATUS_OK
                    
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    logging.info('Return status = ' + str(ret['status']))
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response

def get_metadata_list_helper(request, app, method, normalize_method="normalize_metadata_results"):
    logging.info('get_type_infos')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        names       = get_request_value(request, 'names')
        token       = get_request_value(request, 'token')
        
        if token and app:
            ret['status']   = constants.STATUS_ERROR
            
            names   = simplejson.JSONDecoder().decode(names)
            req     = requestcontext.create_request(token, app)
            data    = getattr(appservice.AppService, method)(req, names)
            ret['data' ]    = getattr(transformservice, normalize_method)(req, data)
            
            ret['status']   = constants.STATUS_OK
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
            
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain") 
    return response

#http://localhost:8080/api/type_infos/ParabayOrg-Outlook?token=Uyd0b2tfODkxZTIwMjU0OTBmYzhlNDRlZTBjMzIyZDI0MzM1OGEnCnAwCi5hNDJiMmY4ZjdlMmUwMzBiNDUzMzc0M2JiM2EyZTU1Yw%3D%3D&names=loo
def get_type_infos(request, app):
    return get_metadata_list_helper(request, app, "get_type_infos")

#http://localhost:8080/api/entity_metadatas/ParabayOrg-Outlook?token=Uyd0b2tfODkxZTIwMjU0OTBmYzhlNDRlZTBjMzIyZDI0MzM1OGEnCnAwCi5hNDJiMmY4ZjdlMmUwMzBiNDUzMzc0M2JiM2EyZTU1Yw%3D%3D&names=["Contacts_Contact"]
def get_entity_metadatas(request, app):
    return get_metadata_list_helper(request, app, "get_entity_metadatas", "normalize_em_results")

#http://localhost:8080/api/enumerations/ParabayOrg-Outlook?token=Uyd0b2tfODkxZTIwMjU0OTBmYzhlNDRlZTBjMzIyZDI0MzM1OGEnCnAwCi5hNDJiMmY4ZjdlMmUwMzBiNDUzMzc0M2JiM2EyZTU1Yw%3D%3D&names=["Countries"]
def get_enumerations(request, app):
    return get_metadata_list_helper(request, app, "get_enumerations", "normalize_enum_results")

def get_l10n_content(request, app):
    return get_metadata_list_helper(request, app, "get_l10n_content")

def get_relations(request, app):
    return get_metadata_list_helper(request, app, "get_relations")

#http://localhost:8080/api/view_defs/ParabayOrg-Outlook?token=Uyd0b2tfODkxZTIwMjU0OTBmYzhlNDRlZTBjMzIyZDI0MzM1OGEnCnAwCi5hNDJiMmY4ZjdlMmUwMzBiNDUzMzc0M2JiM2EyZTU1Yw%3D%3D&names=["oo"]
def get_view_defs(request, app):
    return get_metadata_list_helper(request, app, "get_view_defs")    

#http://localhost:8080/api/view_maps/ParabayOrg-Outlook?token=Uyd0b2tfODkxZTIwMjU0OTBmYzhlNDRlZTBjMzIyZDI0MzM1OGEnCnAwCi5hNDJiMmY4ZjdlMmUwMzBiNDUzMzc0M2JiM2EyZTU1Yw%3D%3D
def get_view_maps(request, app):
    return get_metadata_list_helper(request, app, "get_view_maps")   

#http://localhost:8080/api/root_view_maps/ParabayOrg-Outlook
def get_root_view_maps(request, app):
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        limit   = get_request_value(request, 'limit', "32")
        offset  = get_request_value(request, 'offset', "0")
            
        if token and app:
            logging.info('App=' + app)
            ret['status']   = constants.STATUS_ERROR
            req = requestcontext.create_request(token, app)
            
            root_view_maps = appservice.AppService.get_root_view_maps(req, int(limit), int(offset))
            result = transformservice.normalize_metadata_results(req, root_view_maps)
            ret['data' ] = result
            ret['status']   = constants.STATUS_OK

    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
                
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain") 
    return response

def synchronize_metadata(request, app):
    logging.info('synchronize_metadata')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:       
        token       = get_request_value(request, 'token')
        
        if token and app:
            ret['status']   = constants.STATUS_ERROR
            
            req = requestcontext.create_request(token, app)
            metadataservice.synchronizeMetadata(req)
        
            ret['status']   = constants.STATUS_OK
    
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
            
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

#http://localhost:8080/api/l10n/ParabayOrg-Outlook/Tasks_Tasks
def get_l10n_data(request, app, page):
    logging.info('get_l10n_data')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        lang        = get_request_value(request, 'lang')
        limit       = get_request_value(request, 'limit', "128")
        offset      = get_request_value(request, 'offset', "0")
    
        if token and app:
            ret['status']   = constants.STATUS_ERROR
            
            req             = requestcontext.create_request(token, app)
            l10n_results    = appservice.AppService.find_l10n_for_page(req, page, lang, int(offset), int(limit))
            ret['data' ]    = transformservice.normalize_l10n_results(req, l10n_results)
            
            ret['status']   = constants.STATUS_OK
    
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())        
        
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain") 
    return response

#http://localhost:8080/api/page_metadata/ParabayOrg-Outlook/Tasks_Tasks
def get_page_metadata(request, app, page):
    logging.info('get_page_metadata')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        lang        = get_request_value(request, 'locale', '')
            
        if token and app:
            ret['status']   = constants.STATUS_ERROR
            
            page_metadata   = None
            
            req = requestcontext.create_request(token, app)
            if not req.has_perm([securityservice.READ_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
            else:
                cache_key       = [app, page, lang]
                #page_metadata   = utils.check_memcache(cache_key)

                if not page_metadata:
                    logging.info('Creating page metadata')
                    page_metadata = {}
                    view_map                            = metadataservice.find_view_map(req, page)
                    page_metadata['view_map']           = transformservice.transform_metadata(view_map)
                    view_def                            = view_map.view_definition
                    #logging.info(view_def.data_queries)
                    page_metadata['view_definition']    = transformservice.transform_metadata(view_def)
                    dataquery_names                     = view_def.data_queries
                    logging.info(dataquery_names)
                    if not dataquery_names is None:
                        dataquery_names                     = simplejson.JSONDecoder().decode(dataquery_names)
                        logging.info(dataquery_names)
                        logging.info(metadataservice.find_data_query(req, 'Docs_Documents_List'))
                        data_queries                        = [ metadataservice.find_data_query(req, name) for name in dataquery_names ]
                        page_metadata['data_queries']       = transformservice.normalize_metadata_results(req, data_queries) 
                    #root_view_maps                      = appservice.AppService.get_root_view_maps(req, 8, 0)
                    #page_metadata['root_view_maps']     = transformservice.normalize_metadata_results(req, root_view_maps)
                    if lang != '':
                        l10n_results                    = appservice.AppService.find_l10n_for_page(req, page, lang)
                        page_metadata['l10n']           = transformservice.normalize_l10n_results(req, l10n_results)
                
                    utils.set_memcache(cache_key, page_metadata)
                
            ret["page_metadata"] = page_metadata           
            ret['status']   = constants.STATUS_OK
    
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

#http://localhost:8080/api/dataquery_metadata/ParabayOrg-Outlook/Tasks_Tasks_List
@admin_required
def get_dataquery_metadata(request, app, dataquery):
    logging.info('get_dataquery_metadata' + dataquery )
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    if request.req:
        ret['status']   = constants.STATUS_ERROR
        
        req = request.req
        dataquery_metadata = None
        
        cache_key       = [app, dataquery]
        dataquery_metadata   = utils.check_memcache(cache_key)
        
        if not dataquery_metadata:
            dataquery_metadata = {}
            data_query                              = metadataservice.find_data_query(req, dataquery)
            logging.info(data_query.type_of)
            dataquery_metadata['data_query']        = transformservice.transform_metadata(data_query)
            entity_metadata                         = metadataservice.find_entity_metadata(req, data_query.type_of)
            dataquery_metadata['entity_metadatas']  = transformservice.normalize_em_results(req, [entity_metadata])
            enumerations                            = metadataservice.find_enumerations_for_entity_metadata(req, entity_metadata)
            dataquery_metadata['enumerations']      = transformservice.normalize_enum_results(req, enumerations)
            typeinfos                               = metadataservice.find_typeinfos_for_entity_metadata(req, entity_metadata)
            dataquery_metadata['type_infos']        = transformservice.normalize_typeinfo_results(req, typeinfos)
            entity_relations                        = metadataservice.find_relations_for_entity_metadata(req, entity_metadata)
            #dataquery_metadata['entity_relations']  = transformservice.normalize_metadata_results(req, entity_relations)
            utils.set_memcache(cache_key, dataquery_metadata)
            
        ret["dataquery_metadata"] = dataquery_metadata     
        ret['status']   = constants.STATUS_OK
    
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

#http://localhost:8080/api/generate_default_views/ParabayOrg-Outlook
def generate_default_views(request, app):
    logging.info('generate default views')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        overwrite      = get_request_value(request, 'overwrite')
        
        if token:
            ret['status']   = constants.STATUS_ERROR
            
            req = requestcontext.create_request(token, app)

            if overwrite:
                overwrite = True
            else:
                overwrite = False
              
            metadataservice.generate_default_views(req, overwrite)
            ret['status']       = constants.STATUS_OK
    
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response

#http://parabaydata.appspot.com/api/erase_all_data
def erase_all_data(request):
    logging.info('delete everything')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        metadatas = datamodel.Metadata.all().fetch(100)
        for m in metadatas:
            metadata_name = m.name
            entity_metadatas = m.entitymetadata_set
            for em in entity_metadatas:
                metadata_class = utils.loadModuleType(metadata_name, em.name)
                utils.delete_all_entities(metadata_class)
            
        schemaloader.AppImporterAndLoader.deleteAllRecords()     
        ret['status']       = constants.STATUS_OK
    
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response

#http://localhost:8080/api/import_data/ParabayOrg-Outlook?kind=Tasks_Task&csv=test,pri
def import_data(request, app):
    logging.info('Import data')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        kind        = get_request_value(request, 'kind')
        csv         = get_request_value(request, 'csv')
        
        if token and app and csv:
            ret['status']   = constants.STATUS_ERROR
            
            req = requestcontext.create_request(token, app)
            
            if not req.has_perm([securityservice.READ_PERMISSION]):
                logging.error('Data upload failed - Access denied')
                ret['status']   = constants.STATUS_ACCESS_DENIED
            else:
                #taskqueue.add(url='/worker', params={'key': key})
                data_importer = dataloader.DataImporter(req, kind)
                data_importer.import_data(csv)
            
            ret['status']       = constants.STATUS_OK
        else:
            logging.error('Invalid parameter')
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response

#cron job
def cron_erase_data(request, app, datatype):
    logging.info('Cron erase data- not just marking data for deletion')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM
   
    try:   
        #logging.info(repr(request.META)) hasattr(request.META, 'HTTP_X_APPENGINE_CRON') and 
        if app and datatype:
            ret['status']   = constants.STATUS_ERROR
            
            dataservice.DataService.cron_erase(app, datatype, 50)            
            ret['status']       = constants.STATUS_OK
        else:
            logging.info('Missing cron header')
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response

#http://localhost:8080/api/bulk_erase/ParabayOrg-Outlook/Calendar_Appointment?delete=["1"]
def bulk_erase_data(request, app, datatype):
    logging.info('Bulk erase data- not just marking data for deletion')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        ids         = get_request_value(request, 'delete')
        
        if token and app and datatype and ids:
            ret['status']   = constants.STATUS_ERROR
            
            req = requestcontext.create_request(token, app)
            if not req.has_perm([securityservice.READ_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
            else:
                id_list             = simplejson.JSONDecoder().decode(ids)
                dataservice.DataService.bulk_erase(req, datatype, id_list)            
                ret['status']       = constants.STATUS_OK
    
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response

#http://localhost:8080/api/flush_cache
#@su_required
def flush_cache(request):
    logging.info('flush_cache')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:

        token       = get_request_value(request, 'token')
        if token:
            memcache.flush_all()
        
            ret['status']   = constants.STATUS_OK

    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
    
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

#http://localhost:8080/api/settings/ParabayOrg-Outlook
def client_settings(request, app):
    logging.info('client_settings')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:

        token       = get_request_value(request, 'token')
        client      = get_request_value(request, 'client')
        outlook     = get_request_value(request, 'outlook')
        version     = get_request_value(request, 'version', '1.0.0.2')
        
        logging.info(outlook)
        
        if token:
            req = requestcontext.create_request(token, app)
            if req.user:
                '''
                gae_klazz = utils.loadModuleType('Friends', 'Friends_User')
                query = gae_klazz.all()
                results = query.fetch(100)
                for f in results:
                    if not(hasattr(f, 'approved') and f.approved == '1'):
                        f.approved = '0'
                        f.put() 
                '''
                ret['outlook_client_version']  = '1.0.0.2'
                ret['outlook_client_update_url']  = ''
                if version != ret['outlook_client_version']:
                    ret['outlook_client_update_url']  = 'http://parabaydemo.appspot.com/app/OutlookSyncAddIn.dll'
                ret['min_sync_interval'] = 10
                ret['max_sync_items'] = 50
                ret['sync_items'] = 255
                ret['server_busy_delay'] = 0
                ret['status']   = constants.STATUS_OK

    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
    
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response    

def image_result(img):
    ret = {}
    ret['Url'] = img.url
    ret['FileFormat'] = img.fileType
    ret['FileSize'] = img.fileSize
    if img.height>0 and img.width>0:
        ret['Height'] = img.height
        ret['Width'] = img.width
    if img.thumbnail:
        thumb = {}
        thumb['Url'] = img.thumbnail
        ret['Thumbnail'] = thumb
    return ret
    
#http://localhost:8080/api/files/ParabayOrg-Outlook
#http://192.168.0.103:8080/api/files/ParabayOrg-Outlook?query={"kind":"UploadedFiles","include_deleted_items":true,"orders":[],"columns":[],"filters":[{"condition":"updated >=","param":"2009-12-10T16:52:26.821978","type":"timestamp"}]}
def list_files(request, app):
    '''List the images'''
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token   = get_request_value(request, 'token')
        query   = get_request_value(request, 'query', '{"columns":[],"kind":"UploadedFile","filters":[],"orders":[]}')
        limit   = int(get_request_value(request, 'limit', "10"))
        offset  = int(get_request_value(request, 'offset', "0"))
        
        if token and app:
            
            req = requestcontext.create_request(token, app)            
            if not req.has_perm([securityservice.READ_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
                
            else:
                rs = {}
                rs['firstResultPosition'] = offset
        
                logging.info(query)
                q = simplejson.JSONDecoder().decode(query)
                gq = utils.build_query_for_class(datamodel.UploadedFile, q)                    
                
                data = gq.fetch(limit+1)
                if len(data) == limit+1:
                    next = gq.cursor()
                    data = data[:limit]
                else:
                    next = ''

                rs['totalResultsAvailable'] = gq.count()
                rs['Result'] = [image_result(f) for f in data] 
                ret['ResultSet']     = rs

                ret['sync_token'] = next
                ret['status']   = constants.STATUS_OK
                   
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
    
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

#http://localhost:8080/api/upload_file/ParabayOrg-Outlook
def upload_file(request, app):
    logging.info('upload file')
    
    ret                 = {}
    redirect_url        = '/'
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token = get_request_value(request, 'token')
        key = get_request_value(request, 'id')
        
        if token and app :
            ret['status']   = constants.STATUS_ERROR
            
            req = requestcontext.create_request(token, app)
            
            if not req.has_perm([securityservice.READ_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
            else:
                if key is None:
                    key = utils.new_key()
                    logging.info('No id in request: %s', key)

                upload_files = blobstore_helper.get_uploads(request, 'file')  # 'file' is file upload field in the form
                blob_info = upload_files[0]
                #logging.info(vars(blob_info))
                
                file = datamodel.UploadedFile(key_name = key)

                file.fileName = blob_info.filename
                if not file.fileName:
                    file.fileName = str(uuid.uuid1())     
                #logging.info(file.fileName)

                file.fileType = blob_info.content_type
                if not file.fileType:
                    file.fileType = 'image/jpeg'
                #logging.info(file.fileType)
                file.fileSize = blob_info.size
                
                file.fileBlobRef = blob_info.key()  
                file.owner = req.user.name
                file.is_deleted = False
                file.updated = datetime.datetime.now()
                file.put()

                redirect_url = '/api/serve_file/%s?id=%s' % (app, key) 
                logging.info(redirect_url)
                
                file.url = redirect_url
                thumbnail_url = images.get_serving_url(blob_info.key(), 79)
                file.thumbnail = thumbnail_url
                file.put()

                ret['status']       = constants.STATUS_OK
                ret['id'] = key
                ret['url'] = file.url
                ret['thumbnail'] = file.thumbnail

        else:
            logging.error('Invalid parameter')
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    #response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    response = HttpResponseRedirect(redirect_url)
    return response

#http://localhost:8080/api/serve_file/ParabayOrg-Outlook
def serve_file(request, app):
    #logging.info('serve file')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        key = get_request_value(request, 'id')
        saveas = int(get_request_value(request, 'save_as', "0"))
        
        logging.info('Serving file: ' + key)
        
        if app :
            ret['status']   = constants.STATUS_ERROR
            
            file = utils.find_entity_by_name (datamodel.UploadedFile, key)
            if file:
                blob = blobstore.BlobInfo.get(file.fileBlobRef.key())
                if saveas:
                    saveas = True
                else:
                    saveas = False
                return blobstore_helper.send_blob(request, blob, save_as=saveas)
        else:
            logging.error('Invalid parameter')
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

#http://localhost:8080/api/init_upload/ParabayOrg-Outlook
def init_upload(request, app):
    logging.info('init_upload')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        
        if token and app:
            ret['status']   = constants.STATUS_ERROR
            
            req = requestcontext.create_request(token, app)
            
            if not req.has_perm([securityservice.READ_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
            else:
                key                 = str(uuid.uuid1()) 
                ret['id']           = key 
                
                uploadUrl           = '/api/upload_file/%s?token=%s&id=%s' % (app, token, key)
                fileUrl             = '/api/serve_file/%s?id=%s' % (app, key) 
                logging.info(fileUrl)
                
                ret['uploadUrl']    = blobstore.create_upload_url(uploadUrl)
                ret['fileUrl']      = fileUrl
                ret['status']       = constants.STATUS_OK
        else:
            logging.error('Invalid parameter')
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response
    
#http://192.168.0.105:8080/api/approve_user/ParabayOrg-Friends?nick=John
def approve_user(request, app):
    logging.info('approve_user')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        nick        = get_request_value(request, 'nick')
        approved      = get_request_value(request, 'approved', '0')
        
        if token and app:
            ret['status']   = constants.STATUS_ERROR
            
            req = requestcontext.create_request(token, app)
            
            if req.user.name != 'support':
                ret['status']   = constants.STATUS_ACCESS_DENIED
            else:
                gae_klazz = utils.loadModuleType(req.metadata.name, "Friends_User")
                q = gae_klazz.all()
                q.filter('nick =', nick)
                friend = q.get()
                
                if friend:
                    logging.info('Approving user:' + nick)
                    friend.approved = '1' if approved == '1' else 0                  
                    friend.put()
                    
                    ret['status']       = constants.STATUS_OK
        else:
            logging.error('Invalid parameter')
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response


#http://192.168.0.105:8080/api/update_peer/ParabayOrg-Friends?peerId=32
def update_peer(request, app):
    logging.info('update_peer')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        peerId      = get_request_value(request, 'peerId')
        ipAddress   = request.META['REMOTE_ADDR']
        
        if token and app:
            ret['status']   = constants.STATUS_ERROR
            
            req = requestcontext.create_request(token, app)
            
            if not req.has_perm([securityservice.READ_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
            else:
                gae_klazz = utils.loadModuleType(req.metadata.name, "Friends_User")
                q = gae_klazz.all()
                q.filter('nick =', req.user.name)
                q.filter('owner =', req.user.name)
                friend = q.get()
                
                if friend:
                    logging.info('Saving peer id:' + peerId)
                    friend.peerId = peerId
                    friend.ipAddress = ipAddress
                    
                    if len(peerId) > 0:
                        friend.lastLogin = datetime.datetime.now()
                    friend.put()
                    
                    ret['status']           = constants.STATUS_OK
                    ret['approved']         = 1 if friend.approved == '1' else 0  
                    ret['pulseInterval']    = 60000
                    ret['clientVersion']    = 10
                    ret['disablePeer']      = 0
                    ret['disableServer']    = 0
                    ret['message']          = ''
        else:
            logging.error('Invalid parameter')
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response
    
#http://localhost:8080/api/push_notification/ParabayOrg-Outlook?receiver=vishnuv&message=test&badge=2
def push_notification(request, app):
    logging.info('Push notification')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        receiver    = get_request_value(request, 'receiver')
        message     = get_request_value(request, 'message')
        badge       = get_request_value(request, 'badge', '0')
        schedule    = get_request_value(request, 'schedule')
        
        if token and app and receiver and message:
            ret['status']   = constants.STATUS_ERROR
            
            req = requestcontext.create_request(token, app)
            
            if not req.has_perm([securityservice.READ_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
            else:
                if req.user.device and req.user.device.device_token:
                    utils.send_push_notification(req.user.device.device_token, message, int(badge), schedule)
                    ret['status']       = constants.STATUS_OK
        else:
            logging.error('Invalid parameter')
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response

#http://localhost:8080/api/register_iphone/ParabayOrg-Outlook?devicetoken= f739e47a9de323321c685804d6bfdbfe343b4deb999e27cbb9b9c6cc9e0402cb 
def register_iphone(request, app):
    logging.info('Register iPhone')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token           = get_request_value(request, 'token')
        devicetoken     = get_request_value(request, 'devicetoken')
        app_version     = get_request_value(request, 'app_version', '')
        metadata_version     = get_request_value(request, 'metadata_version', '')
        device      = get_request_value(request, 'device')
        longitude   = get_request_value(request, 'longitude')
        latitude    = get_request_value(request, 'latitude')
        photo    = get_request_value(request, 'photo')
        
        if token and app:
            ret['status']   = constants.STATUS_ERROR
            
            req = requestcontext.create_request(token, app)
            
            if not req.has_perm([securityservice.READ_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
            else:
                user = securityservice.SecurityService.userid_to_user(req.user.name)
                if photo:
                    user.photo = photo

                if longitude and latitude:
                    location = datamodel.UserLocation()
                    location.longitude = float(longitude)
                    location.latitude = float(latitude)
                    hash = str(geohash.Geohash((float(longitude),float(latitude))))
                    location.bbhash1 = hash[:2]
                    location.bbhash2 = hash[:4]
                    location.bbhash = hash
                    location.owner = req.user.name
                    location.updated = datetime.datetime.now()
                    location.put()
                    user.location = location
                    
                if devicetoken:
                    device_rec = datamodel.UserDevice.get_or_insert(devicetoken)
                    device_rec.device_token = devicetoken
                    device_rec.app_version = app_version
                    device_rec.metadata_version = metadata_version
                    device_rec.owner = req.user.name
                    device_rec.put()
                    user.device = device_rec

                user.put()
                user.set_dirty(True)
                user.update_cache_if_dirty()                            
                    
                ret['status']       = constants.STATUS_OK
        else:
            logging.error('Invalid parameter')
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
            
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response

#http://localhost:8080/api/submit_feedback/ParabayOrg-Outlook?message=good&msgtype=Comments
def submit_feedback(request, app):
    logging.info('Submit user feedback')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        typeof      = get_request_value(request, 'msgtype', 'Comments')
        message     = get_request_value(request, 'message', None)
        target     = get_request_value(request, 'target', None)
        
        if token and app and message:
            ret['status']   = constants.STATUS_ERROR
            
            req = requestcontext.create_request(token, app)
            
            if not req.has_perm([securityservice.READ_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
            else:
                feedback = datamodel.UserFeedback()
                feedback.typeof = typeof
                feedback.target = target
                feedback.message = message
                feedback.owner = req.user.name
                feedback.put()
                
                if target and typeof and 'Abuse' == typeof:
                    gae_klazz = utils.loadModuleType(req.metadata.name, "Friends_User")
                    q = gae_klazz.all()
                    q.filter('nick =', target)
                    friend = q.get()

                    if friend:
                        logging.info('Blocking user:' + nick)
                        friend.approved = '0'                 
                        friend.put()
                    
                ret['status']       = constants.STATUS_OK
        else:
            logging.error('Invalid parameter')
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response

def user_location_result(location):
    ret = {}
    ret['longitude'] = location.longitude
    ret['latitude'] = location.latitude
    ret['address'] = location.address
    if location.owner:
        user = securityservice.SecurityService.userid_to_user(location.owner)
        ret['user'] = user.name
        ret['chat_id'] = user.chat_id
    return ret

#http://localhost:8080/api/locate_users/ParabayOrg-Outlook
def locate_users(request, app):
    '''List the images'''
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token   = get_request_value(request, 'token')
        radius   = int(get_request_value(request, 'radius', "0"))
        limit   = int(get_request_value(request, 'limit', "10"))
        offset  = int(get_request_value(request, 'offset', "0"))
        
        if token and app:
            
            req = requestcontext.create_request(token, app)            
            if not req.has_perm([securityservice.READ_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
                
            else:
                rs = {}
                rs['firstResultPosition'] = offset
                
                gq = datamodel.UserLocation.all()              
                if radius <= 2:
                    rindex = 1
                elif radius <=4:
                    rindex = 2
                else:
                    rindex = 3    
                if (not req.user.location is None) and (not req.user.location.bbhash3 is None) and (radius > 0):
                    radius = rindex * 2
                    gq.filter('bbhash' + str(rindex) + ' =', req.user.location.bbhash3[:radius])
                users = gq.fetch(limit, offset)
                
                rs['totalResultsAvailable'] = gq.count()
                rs['Result'] = [user_location_result(u) for u in users] 
                ret['ResultSet']     = rs

                ret['status']   = constants.STATUS_OK
                   
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
    
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

def location_result(location):
    ret = {}
    ret['name'] = location.name
    ret['description'] = location.description
    ret['longitude'] = location.longitude
    ret['latitude'] = location.latitude
    ret['address'] = location.address
    ret['city'] = location.city
    ret['state'] = location.state
    ret['zipcode'] = location.zipcode
    ret['tags'] = location.tags
    ret['geohash'] = location.bbhash
    ret['is_deleted'] = False
    return ret

#http://localhost:8080/api/locations/ParabayOrg-Outlook
def list_locations(request, app):
    '''List the locations'''
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token   = get_request_value(request, 'token')
        query   = get_request_value(request, 'query', '{"columns":[],"kind":"UserLocations","filters":[{"condition":"bookmark >= ","param":"","type":"string"}],"orders":[]}')
        limit   = int(get_request_value(request, 'limit', "10"))
        offset  = int(get_request_value(request, 'offset', "0"))
        bookmark   = get_request_value(request, 'bookmark')
        
        if token and app:
            
            req = requestcontext.create_request(token, app)            
            if not req.has_perm([securityservice.READ_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
                
            else:
                rs = {}
                rs['firstResultPosition'] = offset
                
                logging.info(query)
                q = simplejson.JSONDecoder().decode(query)
                gq = utils.build_query_for_class(datamodel.UserLocation, q)                    
                
                data = gq.fetch(limit+1)
                if len(data) == limit+1:
                    next = data[-1].bookmark
                    data = data[:limit]
                else:
                    next = ''

                rs['totalResultsAvailable'] = 0
                rs['Result'] = [location_result(f) for f in data] 
                ret['ResultSet']     = rs

                ret['sync_token'] = next
                ret['status']   = constants.STATUS_OK
                   
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
    
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

#http://localhost:8080/api/saveLocation/ParabayOrg-Timmy?data=[{"MeetingOrganizer":%20"Varadaraj,%20Vishnu2",%20"Subject":%20"Subaru%20Forrester%20appt2."}]
def save_location_array(request, app):
    '''Save data'''
    logging.info('save location array')

    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        data        = get_request_value(request, 'data')
    
        if token and app and data and datatype:
            req = requestcontext.create_request(token, app)
            if not req.has_perm([securityservice.WRITE_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
            
            else:
                data    = simplejson.JSONDecoder().decode(data)
                data    = transformservice.denormalize_locations(req, data)
                
                save_status = {}
                for item in data:
                    save_status[item.key().name()] = False
                    item.org      = req.org.name
                    item.owner    = req.user.name
                    item.updated  = datetime.datetime.now()
                    item.bookmark = utils.bookmark_for_kind('UserLocation', req.user.name, item.updated)
                    item.is_deleted = False
                    item.put()
                    if item:
                        save_status[item.key().name()] = True
                    
                ret['save_status']  = save_status
                ret['status']       = constants.STATUS_OK
                    
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
            
    logging.info('Return status = ' + str(ret['status']))
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response

#cron job - send push notifications
#http://localhost:8080/api/cron_push/ParabayOrg-Outlook/Calendar_Appointment
def cron_push_notifications(request, app, datatype):
    logging.info('Cron push data- use urban airship')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM
   
    try:   
        #logging.info(repr(request.META)) hasattr(request.META, 'HTTP_X_APPENGINE_CRON') and 
        if app and datatype:
            ret['status']   = constants.STATUS_ERROR
            
            dataservice.DataService.cron_push(app, datatype, 5)            
            ret['status']       = constants.STATUS_OK
        else:
            logging.info('Missing cron header')
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response

def get_request_value(request, name, default=None):
    ret = None
    try:
        ret = request.REQUEST[name]
    except KeyError:
        if request.COOKIES.get(name):
            ret = request.COOKIES[name]
        else:
            ret = default
    return ret 

@login_required
def get_user_details(request, app):
    logging.info('get_user_details')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    if request.req:
        ret['status']   = constants.STATUS_ERROR
        
        req = request.req
        token   = get_request_value(request, 'token')
         
        cache_key       = ['user', app, token]
        user_details   = utils.check_memcache(cache_key)
        
        if not user_details:
            user_details = {}
            if user_details:
                utils.set_memcache(cache_key, user_details)
            
        ret["user_details"] = user_details     
        ret['status']   = constants.STATUS_OK
    
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

#http://localhost:8080/api/fixup/ParabayOrg-Friends
def fixup(request, app):
    logging.info('fixup')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:

        token       = get_request_value(request, 'token')
        
        if token:
            req = requestcontext.create_request(token, app)
            if req.user:
                gae_klazz = utils.loadModuleType('Friends', 'Friends_User')
                #query = gae_klazz.all()
                #query.filter('approved =', '0')
                #results = query.fetch(50)
                #for f in results:
                #    f.approved = '1'
                #    f.put()
                    
                query = gae_klazz.all()
                query.filter('approved =', 0)
                results = query.fetch(50)
                for f in results:
                    f.approved = '1'
                    f.put()
                    
                ret['status']   = constants.STATUS_OK

    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
    
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response    

#http://192.168.0.103:8080/api/apps
def get_apps(request):
    logging.info('get_apps')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM
    
    try:

        token       = get_request_value(request, 'token')
        org       = get_request_value(request, 'org', 'ParabayOrg')
        
        if token:
            req = requestcontext.create_request(token)
            organisation = utils.find_entity_by_name(datamodel.Organisation, org)
            req.org = organisation
            
            if req.user and organisation:
                query = datamodel.App.all()
                query.filter('org =', organisation)
                results = query.fetch(100)
                ret['apps'] = transformservice.normalize_metadata_results(req, results)
                ret['status']   = constants.STATUS_OK
            else:
                logging.info('invalid token or org')
                
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
    
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response    

#http://192.168.0.103:8080/api/create_app
def create_app(request):
    logging.info('create_app')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM
    
    try:

        token       = get_request_value(request, 'token')   
        app       = get_request_value(request, 'app')    
        org       = get_request_value(request, 'org', 'ParabayOrg')
          
        if token:
            req = requestcontext.create_request(token)
            
            #securityservice.SecurityService.create_user_org(req.user, org)
            organisation = utils.find_entity_by_name(datamodel.Organisation, org)
            req.org = organisation
            
            if req.user and organisation:
                logging.info(app)
                application       = simplejson.JSONDecoder().decode(app)   
                status = appservice.AppService.create_app(req, application, organisation)
                ret['status']   = status
            else:
                logging.info('invalid user or org')
                
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
    
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response    

#http://192.168.0.103:8080/api/entities
def get_entities(request):
    logging.info('entities')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM
    
    #try:

    token       = get_request_value(request, 'token')
    app         = get_request_value(request, 'app')
    logging.info('app=' + app)
    
    if token and app:
        req = requestcontext.create_request(token, app)
        
        if req.user:
            results = req.metadata.entity_metadatas(req)
            
            if results == []:
                ret['data'] = [{}]
            else:
                ret['data'] = transformservice.normalize_metadata_results(req, results)
                
            ret['status']   = constants.STATUS_OK
        else:
            logging.info('invalid user')

    '''
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
    '''    
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response
    
#http://192.168.0.103:8080/api/entity_details
def get_entity_details(request):
    logging.info('get_entity_details')
      
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        app     = get_request_value(request, 'app')
        entity    = get_request_value(request, 'entity')
        token       = get_request_value(request, 'token')    
        dataquery = entity + 's_List'
        logging.info('app=' + app + ' dataquery=' + dataquery)
    
        if token and app:
            req = requestcontext.create_request(token, app)
        
            if not req.has_perm([securityservice.WRITE_PERMISSION]):
                logging.info('no permission')
                ret['status']   = constants.STATUS_ACCESS_DENIED
        
            else:
                ret['status']   = constants.STATUS_ERROR
        
                dataquery_metadata = None
        
                cache_key       = [app, dataquery]
                dataquery_metadata   = utils.check_memcache(cache_key)
            
                if not dataquery_metadata:
                    logging.info('&&&&')
                    dataquery_metadata = {}
                
                    data_query                              = metadataservice.find_data_query(req, dataquery)
                    if data_query:
                        dataquery_metadata['data_query']        = transformservice.transform_metadata(data_query)
                
                        entity_metadata                         = metadataservice.find_entity_metadata(req, data_query.type_of)
                        dataquery_metadata['entity_metadatas']  = transformservice.normalize_em_results(req, [entity_metadata])
                        if not entity_metadata:
                            dataquery_metadata['entity_metadatas'] = [{}]
                    
                        enumerations                            = metadataservice.find_enumerations_for_entity_metadata(req, entity_metadata)
                        dataquery_metadata['enumerations']      = transformservice.normalize_enum_results(req, enumerations)
                        if enumerations == []:
                            dataquery_metadata['enumerations'] = [{}]
                
                        typeinfos                               = metadataservice.find_typeinfos_for_entity_metadata(req, entity_metadata)
                        dataquery_metadata['type_infos']        = transformservice.normalize_typeinfo_results(req, typeinfos)
                        if typeinfos == []:
                            dataquery_metadata['type_infos'] = [{}]                
                
                        entity_relations                        = metadataservice.find_relations_for_entity_metadata(req, entity_metadata)
                        dataquery_metadata['entity_relations']  = transformservice.normalize_metadata_results(req, entity_relations)
                        if entity_relations == []:
                            dataquery_metadata['entity_relations'] = [{}]
                
                        utils.set_memcache(cache_key, dataquery_metadata)
                        ret["dataquery_metadata"] = dataquery_metadata     
                        ret['status']   = constants.STATUS_OK

                    else:
                        logging.error('data query not found:' + dataquery)
                
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
    
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

#http://192.168.0.103:8080/api/save_data_query
def save_data_query(request):
    logging.info('save_data_query')
      
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    app     = get_request_value(request, 'app')
    token       = get_request_value(request, 'token')    
    dataquery    = get_request_value(request, 'dataquery')
    
    if token and app:
        req = requestcontext.create_request(token, app)
        
        if not req.has_perm([securityservice.WRITE_PERMISSION]):
            ret['status']   = constants.STATUS_ACCESS_DENIED
        
        else:
            ret['status']   = constants.STATUS_ERROR
            
            logging.info(dataquery)
            
            data_query_obj = simplejson.JSONDecoder().decode(dataquery) 
            data_query_name = data_query_obj['data_query']['name']
            appservice.AppService.save_data_query(req, data_query_obj)
            
            cache_key       = [app, data_query_name]
            utils.set_memcache(cache_key, None)       
              
            ret['dataquery'] = data_query_name
            ret['status']   = constants.STATUS_OK
    
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

#http://192.168.0.103:8080/api/save_view_data
def save_view_data(request):
    logging.info('save_view_data')
      
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    app     = get_request_value(request, 'app')
    token       = get_request_value(request, 'token')    
    pagemetadata    = get_request_value(request, 'pagemetadata')
    
    if token and app:
        req = requestcontext.create_request(token, app)
        
        if not req.has_perm([securityservice.WRITE_PERMISSION]):
            ret['status']   = constants.STATUS_ACCESS_DENIED
        
        else:
            ret['status']   = constants.STATUS_ERROR
            
            page_metadata_obj = simplejson.JSONDecoder().decode(pagemetadata) 
            page_metadata_name = page_metadata_obj['view_map']['name']
            appservice.AppService.save_view_data(req, page_metadata_obj)
            
            cache_key       = [app, page_metadata_name]
            utils.set_memcache(cache_key, None)       
              
            ret['pagemetadata'] = page_metadata_name
            ret['status']   = constants.STATUS_OK
    
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

#http://localhost:8080/api/views?app=ParabayOrg-Outlook
def get_views(request):
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token = get_request_value(request, 'token')
        app   = get_request_value(request, 'app')
            
        if token and app:
            logging.info('App=' + app)
            ret['status']   = constants.STATUS_ERROR
            req = requestcontext.create_request(token, app)
            
            root_view_maps = appservice.AppService.get_root_view_maps(req, 100, 0)
            ret['data' ] = [{}]
            if root_view_maps != []:
                result = transformservice.normalize_metadata_results(req, root_view_maps)
                ret['data' ] = result
            ret['status']   = constants.STATUS_OK

    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
                
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain") 
    return response
    
#http://localhost:8080/api/view_details?app=ParabayOrg-Outlook&view=Tasks_Tasks
def get_view(request):
    logging.info('get_page_metadata')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        app       = get_request_value(request, 'app')
        page       = get_request_value(request, 'view')
        lang        = get_request_value(request, 'locale', '')
            
        if token and app:
            ret['status']   = constants.STATUS_ERROR
            
            page_metadata   = None
            
            req = requestcontext.create_request(token, app)
            if not req.has_perm([securityservice.READ_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
            else:
                cache_key       = [app, page, lang]
                page_metadata   = utils.check_memcache(cache_key)

                if not page_metadata:
                    logging.info('Creating page metadata')
                    page_metadata = {}
                    view_map                            = metadataservice.find_view_map(req, page)
                    page_metadata['view_map']           = transformservice.transform_metadata(view_map)
                    view_def                            = view_map.view_definition
                    #logging.info(view_def.data_queries)
                    page_metadata['view_definition']    = transformservice.transform_metadata(view_def)
                    dataquery_names                     = view_def.data_queries
                    logging.info(dataquery_names)
                    if not dataquery_names is None:
                        dataquery_names                     = simplejson.JSONDecoder().decode(dataquery_names)
                        logging.info(dataquery_names)
                        #logging.info(metadataservice.find_data_query(req, 'Docs_Documents_List'))
                        page_metadata['data_queries'] = [{}]
                        data_queries                        = [ metadataservice.find_data_query(req, name) for name in dataquery_names ]
                        if data_queries != []:
                            page_metadata['data_queries']       = transformservice.normalize_metadata_results(req, data_queries) 
                    #root_view_maps                      = appservice.AppService.get_root_view_maps(req, 8, 0)
                    #page_metadata['root_view_maps']     = transformservice.normalize_metadata_results(req, root_view_maps)
                    if lang != '':
                        l10n_results                    = appservice.AppService.find_l10n_for_page(req, page, lang)
                        page_metadata['l10n']           = transformservice.normalize_l10n_results(req, l10n_results)
                
                    utils.set_memcache(cache_key, page_metadata)
                
            ret["page_metadata"] = page_metadata           
            ret['status']   = constants.STATUS_OK
    
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

#http://localhost:8080/api/save_user_stats?stats=[{"dest":%20"April"}, {"dest":%20"Sandra"}]&app=ParabayOrg-Outlook
def save_user_stats(request):
    
    logging.info('save_user_stats')
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        app       = get_request_value(request, 'app')
        stats    = get_request_value(request, 'stats') 
        
        if token and app:
            ret['status']   = constants.STATUS_ERROR
            
            page_metadata   = None
            
            req = requestcontext.create_request(token, app)
            if not req.has_perm([securityservice.READ_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
            else:
        
                if stats:
                    stats = simplejson.JSONDecoder().decode(stats);
            
                    ret['status']   = constants.STATUS_ERROR
            
                    for ss in stats:
                        s = datamodel.FriendStats(key_name=utils.new_key()) 
                        if 'dest' in ss:
                            s.dest = ss['dest']                        
                        if 'action' in ss:
                            s.action = ss['action']
                        if 'is_ok' in ss:
                            s.is_ok = ss['is_ok']
                        if 'body' in ss:
                            s.body = ss['body']
                        if 'action_date' in ss:
                            s.action_date = ss['action_date']
                        s.owner = req.user.name
                        s.put()
                    ret['status']   = constants.STATUS_OK
      
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
              
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")
    return response

#http://192.168.0.105:8080/api/invite_user/ParabayOrg-Friends
def invite_user(request, app):
    logging.info('invite_user')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        
        if token and app:
            ret['status']   = constants.STATUS_ERROR
            
            req = requestcontext.create_request(token, app)
            
            if not req.has_perm([securityservice.READ_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
            else:
                gae_klazz = utils.loadModuleType(req.metadata.name, "Friends_User")
                q = gae_klazz.all()
                q.filter('nick =', req.user.name)
                friend = q.get()
                
                if friend:
                    logging.info('Found user:' + req.user.name)
                    xmpp.send_invite(friend.email)
        else:
            logging.error('Invalid parameter')
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response

#http://192.168.0.102:8090/api/user_details/ParabayOrg-Friends?nick=vishnuv
def user_details(request, app):
    logging.info('user_details')
    
    ret                 = {}
    ret['status']       = constants.STATUS_INVALID_PARAM

    try:
        token       = get_request_value(request, 'token')
        nick       = get_request_value(request, 'nick')
        
        if token and app:
            ret['status']   = constants.STATUS_ERROR
            
            req = requestcontext.create_request(token, app)
            
            if not req.has_perm([securityservice.READ_PERMISSION]):
                ret['status']   = constants.STATUS_ACCESS_DENIED
            else:
                fd = {}
                
                gae_klazz = utils.loadModuleType(req.metadata.name, "Friends_User")
                q = gae_klazz.all()
                q.filter('nick =', nick)
                friendUser = q.get()
                
                if friendUser:
                    logging.info('Found user:' + nick)     
                    fd["updated"] = friendUser.updated
                    if  hasattr(friendUser, 'peerId'):             
                        fd["peerId"] = friendUser.peerId
                    if hasattr(friendUser, 'nick'):      
                        fd["nick"] = friendUser.nick
                    if hasattr(friendUser, 'photo'):      
                        fd["photo"] = friendUser.photo
                    if hasattr(friendUser, 'location'):      
                        fd["location"] = friendUser.location
                    if hasattr(friendUser, 'approved'):      
                        fd["approved"] =  1 if friendUser.approved == '1' else 0  

                    ret['friend']       = fd
                    ret['status']       = constants.STATUS_OK
                
        else:
            logging.error('Invalid parameter')
            
    except Exception, e:
        ret['status'] = constants.STATUS_FATAL_ERROR
        ret['error_message'] = str(e)
        logging.error(traceback.format_exc())
        
    response = HttpResponse(utils.encode_json(request, ret), mimetype="text/plain")

    return response
