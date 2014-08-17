# Copyright 2008 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import string
import datetime
import md5
import logging
import urllib

from django.contrib.syndication.feeds import Feed
from django.core.exceptions import ObjectDoesNotExist
from django.utils.feedgenerator import Atom1Feed

import json
import simplejson

# Maximum number of issues reported by RSS feeds
RSS_LIMIT = 10

from services import dataservice, securityservice, utils, datamodel, requestcontext

from datetime import tzinfo, timedelta, datetime

ZERO = timedelta(0)
HOUR = timedelta(hours=1)

# A UTC class.

class UTC(tzinfo):
    """UTC"""

    def utcoffset(self, dt):
        return ZERO

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return ZERO

utc = UTC()

class BaseFeed(Feed):
  title = 'Parabay Inc'
  link = '/'
  description = 'Parabay Inc. data'
  feed_type = Atom1Feed

  def author_name(self):
    return 'Parabay Inc.'

  def item_guid(self, item):
    return 'urn:md5:%s' % (md5.new(str(item.key())).hexdigest())

  def item_link(self, item):
    return '/'

  def item_title(self, item):
    return title

  def item_author_name(self, item):
    if isinstance(item, datamodel.BaseDataModel):
      return item.owner
    return 'Parabay Inc.'

  def item_pubdate(self, item):
    ret = None
    if isinstance(item, datamodel.BaseDataModel):
      if hasattr(item, 'rss_updated'):
          ret = getattr(item, 'rss_updated')
      else:
          ret = item.updated
    return ret


class BaseAppFeed(BaseFeed):
  
  def get_object(self, bits):
    """Returns the account for the requested user feed.

    bits is a list of URL path elements. The first element of this list
    should be the user's nickname. A 404 is raised if the list is empty or
    has more than one element or if the a user with that nickname
    doesn't exist.
    """
    if len(bits) != 1:
      raise ObjectDoesNotExist
    self.app = bits[0]
    return bits

class MineFeed(BaseAppFeed):
  title = 'Parabay Inc - My items'

  def items(self,obj):
    return self.rss_list_helper(obj)

  def item_link(self, item):
        
    if isinstance(item, datamodel.BaseDataModel):
         return ('/rss/item/%s/%s/%s' %
                (self.app, self.kind, urllib.quote_plus(str(item.key().name())))) #item.__class__.__name__
    else:
        return '/'

  #http://localhost:8080/rss/mine/ParabayOrg-Outlook?query={"columns":%20[],%20"kind":%20"Calendar_Appointment",%20"filters":%20[{"condition":"StartDate >", "param":"26/06/2009","type":"date"}],%20"orders":%20["StartDate", "StartTime"]}
  def rss_list_helper(self, obj):
    self.token  = utils.get_request_value(self.request, 'token')
    dataquery   = utils.get_request_value(self.request, 'dataquery')
    query       = utils.get_request_value(self.request, 'query')
    limit       = utils.get_request_value(self.request, 'limit', "10")
    offset      = utils.get_request_value(self.request, 'offset', "0")
  
    if self.token is None:
        logging.info('Invalid token')
        return []
    
    req = requestcontext.create_request(self.token, self.app) 
    if not req.has_perm([securityservice.READ_PERMISSION]):
      logging.error('RSS - access denied')
      items  = []
    else:
      if not dataquery is None:
          dq = utils.find_entity_by_name(datamodel.DataQuery, dataquery)
          if dq is None or dq.query is None:
              logging.info('Dataquery not found')
              return []       
            
          today = datetime.now()
          query = string.replace(dq.query, '@@today@@', today.strftime("%d/%m/%y"))
 
      q         = simplejson.JSONDecoder().decode(query)
      self.kind = q['kind']
      self.em   = utils.find_entity_by_name(datamodel.EntityMetadata, self.kind)
      
      result    = dataservice.DataService.list(req, q, int(limit), int(offset))      
      items     = result['data']
      logging.info(items)
           
    return [ transform_feed_item(self.em, item) for item in items ]
  
class OneItemFeed(BaseFeed):
  title = 'Parabay Inc.'
  link = '/'

  def get_object(self, bits):
    if len(bits) < 3:
      raise ObjectDoesNotExist
    obj = self.rss_item_helper(bits)
    if obj:
      return obj
    raise ObjectDoesNotExist
    
  def title(self, obj):
    item      = transform_feed_item(self.em, obj)
    return 'Parabay - %s' % (item.rss_title)
  
  def items(self, obj):
    return [obj]

  def rss_item_helper(self, obj):
    logging.info(repr(obj))
    app       = obj[0]
    kind      = obj[1]
    datakey   = obj[2]
    
    if len(obj)>3:
        datakey = "/".join(obj[2:])
    
    token  = utils.get_request_value(self.request, 'token')
    
    req = requestcontext.create_request(token, app) 
    if not req.has_perm([securityservice.READ_PERMISSION]):
      logging.error('RSS - access denied')
      item  = None
    else:      
      self.em   = utils.find_entity_by_name(datamodel.EntityMetadata, kind)
      result    = dataservice.DataService.get(req, datakey, kind)  
      item      = transform_feed_item(self.em, result)
      
    return item

def transform_feed_item(em, item):
  if em and em.rss_title and hasattr(item, em.rss_title):
      item.rss_title = utils.remove_unsafe(getattr(item, em.rss_title))
  else:
      item.rss_title = 'No title'
      
  if em and em.rss_description and hasattr(item, em.rss_description):
      item.rss_description = utils.remove_unsafe(getattr(item, em.rss_description))
  else:
      item.rss_description = 'No Description'         
      
  if em and em.rss_updated and hasattr(item, em.rss_updated):
      item.rss_updated = getattr(item, em.rss_updated)
  else:
      item.rss_updated = item.updated     
  return item
