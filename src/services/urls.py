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

"""URL mappings for the codereview package."""

# NOTE: Must import *, since Django looks for things here, e.g. handler500.
from django.conf.urls.defaults import *

from services import feeds

urlpatterns = patterns(
    'services.apiservice',
    #(r'^api/erase_all_data$', 'erase_all_data'),
    (r'^api/login$', 'login'),
    (r'^api/logout$', 'logout'),
    (r'^api/list/(?P<app>[^/]+)$', 'list_data'),
    (r'^api/get/(?P<app>[^/]+)/(?P<datatype>[^/]+)/(?P<datakey>[^/]+)$', 'get_data'),
    (r'^api/save/(?P<app>[^/]+)/(?P<datatype>[^/]+)$', 'save_data'),
    (r'^api/savearray/(?P<app>[^/]+)/(?P<datatype>[^/]+)$', 'save_data_array'),
    (r'^api/delete/(?P<app>[^/]+)/(?P<datatype>[^/]+)/(?P<datakey>[^/]+)$', 'delete_data'),
    (r'^api/register_user$', 'register_user'),
    (r'^api/check_user_exists$', 'check_user_exists'),
    (r'^api/check_userid$', 'check_userid'),
    (r'^api/forgot_password$', 'forgot_password'),
    #(r'^api/resend_activation$', 'resend_activation'),
    #(r'^api/activate_user$', 'activate_user'),
    (r'^api/delete_user$', 'delete_user'),
    (r'^api/validate_user_token$', 'validate_user_token'),
    #(r'^api/type_infos/(?P<app>[^/]+)$', 'get_type_infos'),
    #(r'^api/entity_metadatas/(?P<app>[^/]+)$', 'get_entity_metadatas'),
    #(r'^api/enumerations/(?P<app>[^/]+)$', 'get_enumerations'),
    #(r'^api/l10n_content/(?P<app>[^/]+)$', 'get_l10n_content'),
    #(r'^api/relations/(?P<app>[^/]+)$', 'get_relations'),
    #(r'^api/view_maps/(?P<app>[^/]+)$', 'get_view_maps'),
    (r'^api/root_view_maps/(?P<app>[^/]+)$', 'get_root_view_maps'),
    #(r'^api/view_defs/(?P<app>[^/]+)$', 'get_view_defs'),    
    #(r'^api/synchronize_metadata/(?P<app>[^/]+)$', 'synchronize_metadata'),
    (r'^api/generate_default_views/(?P<app>[^/]+)$', 'generate_default_views'),
    #(r'^api/import_data/(?P<app>[^/]+)$', 'import_data'),
    #(r'^api/cron_erase/(?P<app>[^/]+)/(?P<datatype>[^/]+)$', 'cron_erase_data'),
    #(r'^api/bulk_erase/(?P<app>[^/]+)/(?P<datatype>[^/]+)$', 'bulk_erase_data'),    
    (r'^api/page_metadata/(?P<app>[^/]+)/(?P<page>[^/]+)$', 'get_page_metadata'),
    (r'^api/dataquery_metadata/(?P<app>[^/]+)/(?P<dataquery>[^/]+)$', 'get_dataquery_metadata'),
    #(r'^api/l10n/(?P<app>[^/]+)/(?P<page>[^/]+)$', 'get_l10n_data'),
    #(r'^api/flush_cache$', 'flush_cache'),
    (r'^api/settings/(?P<app>[^/]+)$', 'client_settings'),
    (r'^api/files/(?P<app>[^/]+)$', 'list_files'),
    #(r'^api/locations/(?P<app>[^/]+)$', 'list_locations'),
    #(r'^api/save_locations/(?P<app>[^/]+)$', 'save_location_array'),
    (r'^api/register_iphone/(?P<app>[^/]+)$', 'register_iphone'),    
    #(r'^api/push_notification/(?P<app>[^/]+)$', 'push_notification'),    
    (r'^api/submit_feedback/(?P<app>[^/]+)$', 'submit_feedback'),
    #(r'^api/locate_users/(?P<app>[^/]+)$', 'locate_users'),
    #(r'^api/cron_push/(?P<app>[^/]+)/(?P<datatype>[^/]+)$', 'cron_push_notifications'),
    (r'^api/upload_file/(?P<app>[^/]+)$', 'upload_file'),
    (r'^api/serve_file/(?P<app>[^/]+)$', 'serve_file'),
    (r'^api/init_upload/(?P<app>[^/]+)$', 'init_upload'),
    (r'^api/update_peer/(?P<app>[^/]+)$', 'update_peer'),
    (r'^api/approve_user/(?P<app>[^/]+)$', 'approve_user'),
    (r'^api/fixup/(?P<app>[^/]+)$', 'fixup'),
    (r'^api/apps$', 'get_apps'),
    (r'^api/views$', 'get_views'),
    (r'^api/entities$', 'get_entities'),
    (r'^api/entity_details$', 'get_entity_details'),
    (r'^api/create_app$', 'create_app'),
    (r'^api/save_data_query$', 'save_data_query'),
    (r'^api/save_view_data$', 'save_view_data'),
    (r'^api/view_details$', 'get_view'),
    (r'^api/invite_user$', 'invite_user'),
    (r'^api/user_details/(?P<app>[^/]+)$', 'user_details'),    
    (r'^api/save_user_stats$', 'save_user_stats')
    )


feed_dict = {
  'mine' : feeds.MineFeed,
  'item' : feeds.OneItemFeed,
}

urlpatterns += patterns(
    '',
    (r'^rss/(?P<url>.*)$', 'django.contrib.syndication.views.feed',
     {'feed_dict': feed_dict}),
    )

# LOGIN
urlpatterns += patterns('services.views',
    (r'^$', 'login_login'),
    (r'^login$', 'login_login'),
    (r'^join$', 'login_join'),
    (r'^forgot$', 'login_forgot'),
    (r'^logout$', 'login_logout'),
    (r'^test_upload$', 'test_upload'),
)
