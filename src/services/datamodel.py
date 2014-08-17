import logging
from new import classobj
from google.appengine.ext import db,search
from google.appengine.api import memcache
from google.appengine.ext import blobstore

def check_perm(req, obj):
    ret = False
    if req is None:
        return True
    
    if obj.org is None or (obj.org and req.org.name == obj.org):
        if obj.permission is None:
            ret = True
        elif obj.permission in req.perms_map.keys():
            ret = True
    return ret

"""Database models used in the Parabay application.
"""
class BaseModel(db.Model):
    updated = db.DateTimeProperty(auto_now = True)
    created = db.DateTimeProperty(auto_now_add = True)
    owner   = db.StringProperty()
    permission   = db.StringProperty(required=False)
    version = db.IntegerProperty(default=0)
    bookmark = db.StringProperty()
    
    name    = db.StringProperty()
    description = db.TextProperty()
    
    def __str__(self):
        return "%s:%s" % (str(self.__class__.__name__), self.name)

class BaseDataModel(db.Expando):
    _kind = 'BaseDataModel2'
    
    updated = db.DateTimeProperty(auto_now = True)
    created = db.DateTimeProperty(auto_now_add = True)
    owner   = db.StringProperty()
    permission   = db.StringProperty(required=False)
    version = db.IntegerProperty(default=0)
    is_deleted = db.BooleanProperty(default=False)
    push_url   = db.StringProperty()
    bookmark = db.StringProperty()
        
    @classmethod
    def create_class(cls, k):
        cls = classobj(k,(dm.BaseDataModel,),{})
        return cls
        
    def __init__(self, parent=None, key_name=None, _app=None, **kwds):
        super(BaseDataModel, self).__init__(parent, key_name, _app, **kwds)
        
    def __str__(self):
        if hasattr(self, 'name'):
            name = self.name
        else:
            name = 'No name'
        return "%s:%s" % (str(self.__class__.__name__), name)
    
class UserDevice(BaseModel):
    device_token = db.TextProperty(default=None)
    app_version = db.StringProperty(default=None)
    metadata_version = db.StringProperty(default=None)

class UserLocation(BaseModel):
    device = db.ReferenceProperty(UserDevice, default=None)
    latitude = db.FloatProperty(default=None)
    longitude = db.FloatProperty(default=None)
    address = db.StringProperty(default=None)
    city = db.StringProperty(default=None)
    state = db.StringProperty(default=None)
    zipcode = db.StringProperty(default=None)
    bbhash1 = db.StringProperty(default=None)
    bbhash2 = db.StringProperty(default=None)
    bbhash = db.StringProperty(default=None)
    tags = db.StringProperty(default=None) 
    link = db.StringProperty(default=None)
    is_private = db.BooleanProperty()
        
class UserFeedback(BaseModel):
    typeof = db.StringProperty()
    target = db.StringProperty()
    message = db.TextProperty()
    rating = db.IntegerProperty(default=0)

class User(db.Model):
    name = db.StringProperty()
    device = db.ReferenceProperty(UserDevice, default=None)
    location = db.ReferenceProperty(UserLocation, default=None)
    chat_id = db.StringProperty()
    photo = db.StringProperty()
    contact_id = db.StringProperty(default=None)
    description = db.TextProperty()
    first_name = db.StringProperty()
    last_name = db.StringProperty()
    email = db.StringProperty()
    phone = db.StringProperty()
    password = db.StringProperty()
    receive_emails = db.BooleanProperty()
    salt = db.StringProperty()
    activation_code = db.StringProperty(default=None)
    is_active = db.BooleanProperty()
    is_paid_user = db.BooleanProperty()
    is_superuser = db.BooleanProperty(default=False)
    permissions = db.ListProperty(db.Key)
    groups = db.ListProperty(db.Key)
    roles = db.ListProperty(db.Key)
    version = db.IntegerProperty(default=0)
    created = db.DateTimeProperty(auto_now_add = True)
    updated = db.DateTimeProperty(auto_now = True)    
    
    _is_dirty = None
    _roles_list = {}
    _perms_list = {}
    _perms_map = {}
    
    def is_dirty(self):
        return self._is_dirty;
    
    def set_dirty(self, dirty, org_name=None):
        if org_name:
            if  hasattr(self._perms_list, org_name) and self._perms_list[org_name]:
                self._perms_list[org_name] = None
            
            if  hasattr(self._perms_map, org_name) and self._perms_map[org_name]:
                self._perms_map[org_name] = None
            
            if  hasattr(self._roles_list, org_name) and self._roles_list[org_name]:
                self._roles_list[org_name] = None
        
        self._is_dirty = dirty
        
    def roles_list(self, org_name):
        if  hasattr(self._roles_list, org_name) and self._roles_list[org_name]:
            org_roles   = self._roles_list[org_name]
        else:
            org_roles   = self.fetch_user_roles(org_name)
            self._roles_list[org_name] = org_roles
            
        return org_roles
    
    def perms_list(self, org_name):
        if  hasattr(self._perms_list, org_name) and self._perms_list[org_name]:
            org_perms = self._perms_list[org_name]
        else:
            org_perms = self.fetch_user_perms(org_name)
            self._perms_list[org_name] = org_perms
            
        return org_perms
    
    def perms_map(self, org_name):
        if  hasattr(self._perms_map, org_name) and self._perms_map[org_name]:
            org_perms_map = self._perms_map[org_name]
        else:
            temp_perms_map = {}
            for p in self.perms_list(org_name):
                    temp_perms_map[p.name] = p
            self._perms_map[org_name] = temp_perms_map
            org_perms_map = temp_perms_map
            
            self.set_dirty(True)
        return org_perms_map
                
    def format_perm(self, keys):
        return ".".join(keys)
            
    def has_perm(self, org_name, perm):
        
        if (not perm):
            return False      
        if not self.is_active:
            return False
        if self.is_superuser:
            return True
              
        if isinstance(perm, Permission):
            perm_name = perm.name  
        else:
            perm_name = perm
            if not isinstance(perm, str):
                perm_name = self.format_perm(perm)
        #logging.info(self.perms_map(org_name))
        
        perm_obj = None
        if perm_name in self.perms_map(org_name):
            perm_obj = self.perms_map(org_name)[perm_name]
        if perm_obj:
            return True
        else:
            return False
    
    def fetch_user_roles(self, org = None):
        '''Get the roles for the user'''
        
        user_roles = set()
        if len(self.roles)>0:            
            user_roles = set([r for r in db.get(self.roles) if r.org is None or r.org == org])

        #logging.info(self.groups)
        for group in Group.get(self.groups):
            if group and len(group.roles)>0:
                user_roles.update([r for r in db.get(group.roles) if r.org is None or r.org == org])
   
        self.set_dirty(True)
        return user_roles
    
    def fetch_user_perms(self, org=None):
        '''Get the permissions for the user'''
                
        user_roles = self.fetch_user_roles(org)
        
        all_perms = set()
        for role in user_roles:
            if len(role.permissions)>0:
                role_perms = set([p for p in db.get(role.permissions) if p.org is None or p.org == org])
                all_perms.update(role_perms)
        
        if len(self.permissions)>0:
            user_perms = set([p for p in db.get(self.permissions) if p.org is None or p.org == org])
            all_perms.update(user_perms)
         
        self.set_dirty(True)   
        return all_perms
    
    def update_cache_if_dirty(self):
        if self.is_dirty():
            memcache.set('userid_user:%s' % self.name, self)
            self.set_dirty(False)
            
    def __str__(self):
        return "%s:%s" % (self.__class__.__name__, self.name)
    
class Organisation(BaseModel):
    admin = db.ReferenceProperty(User, required=False)
        
class CacheEntry(BaseModel):
    value = db.TextProperty()
    format = db.StringProperty()
        
class Metadata(BaseModel):
    major_version = db.IntegerProperty(default=0)
    depends_on = db.ListProperty(db.Key)
    
    em_map_ = {}
    
    def get_entity_metadata(self, req, em_name):
        if (not self.em_map_) or (not em_name in self.em_map_):
            for em in self.entity_metadatas(req):
                self.em_map_[em.name] = em
        
        return self.em_map_[em_name]
        
    def entity_metadatas(self, req = None):
        res = [em for em in self.entitymetadata_set if check_perm(req, em)]
        for m in self.depends_on:
            m = Metadata.get(m)
            for em in m.entitymetadata_set:
                if check_perm(req, em):
                    res.append(em)
        return res
        
    def type_infos(self, req = None):
        res = [ti for ti in self.typeinfo_set if check_perm(req, ti)]
        for m in self.depends_on:
            m = Metadata.get(m)
            for ti in m.typeinfo_set:
                if check_perm(req, ti):
                    res.append(ti)
        return res
    
    def enumerations(self, req = None):
        res = [e for e in self.enumeration_set if check_perm(req, e)]
        for m in self.depends_on:
            m = Metadata.get(m)
            for e in m.enumeration_set:
                if check_perm(req, e):
                    res.append(e)
        return res

    def entity_relations(self, req = None):
        res = [er for er in self.entityrelation_set if check_perm(req, er)]
        for m in self.depends_on:
            m = Metadata.get(m)
            for er in m.entityrelation_set:
                if check_perm(req, er):
                    res.append(er)
        return res

    def l10n_content(self, req = None):
        res = [l for l in self.l10n_set if check_perm(req, l)]
        for m in self.depends_on:
            m = Metadata.get(m)
            for l in m.l10n_set:
                if check_perm(req, l):
                    res.append(l)
        return res        
    
    def view_definitions(self, req = None):
        res = [l for l in self.viewdefinition_set if check_perm(req, l)]
        for m in self.depends_on:
            m = Metadata.get(m)
            for l in m.viewdefinition_set:
                if check_perm(req, l):
                    res.append(l)
        return res   

    def view_maps(self, req = None):
        res = [l for l in self.viewmap_set if check_perm(req, l)]
        for m in self.depends_on:
            m = Metadata.get(m)
            for l in m.viewmap_set:
                if check_perm(req, l):
                    res.append(l)
        return res   
    
    def data_queries(self, req = None):
        res = [l for l in self.dataquery_set if check_perm(req, l)]

        for m in self.depends_on:
            m = Metadata.get(m)
            for l in m.dataquery_set:
                if check_perm(req, l):
                    res.append(l)
        return res

class TypeInfo(BaseModel):
    metadata = db.ReferenceProperty(Metadata, required=False)
    is_deleted = db.BooleanProperty(default=False)
    server_type = db.StringProperty()
    reg_exp = db.StringProperty()
    max_length = db.IntegerProperty()
    local_db_type = db.StringProperty()
    import_type = db.StringProperty()
    org = db.StringProperty()

class Enumeration(BaseModel):
    metadata = db.ReferenceProperty(Metadata, required=False)
    org = db.StringProperty()
    
    def enumeration_values(self, req = None):
        res = [ev for ev in self.enumerationvalue_set if check_perm(req, ev)]
        return res

class EnumerationValue(BaseModel):
    identifier = db.IntegerProperty()
    enumeration = db.ReferenceProperty(Enumeration, required=False)
    metadata = db.ReferenceProperty(Metadata, required=False)
    org = db.StringProperty()

class EntityRelation(BaseModel):
    metadata = db.ReferenceProperty(Metadata, required=False)
    parent_entity = db.StringProperty()
    child_entity = db.StringProperty()
    parent_column = db.StringProperty()
    child_column = db.StringProperty()
    max_count = db.IntegerProperty()
    delete_policy = db.IntegerProperty() #1=Nullify, 2=Cascade
    has_inverse = db.BooleanProperty(default=True)
    org = db.StringProperty()

class EntityMetadata(BaseModel):
    rss_title = db.StringProperty()
    rss_description = db.StringProperty()
    rss_updated = db.StringProperty()
    metadata = db.ReferenceProperty(Metadata, required=False)
    is_deleted = db.BooleanProperty(default=False)
    has_generated = db.BooleanProperty(default=False)
    plural_name = db.StringProperty()
    human_name = db.StringProperty()
    underscore_name = db.StringProperty()
    camel_name = db.StringProperty()
    owner_columns = db.TextProperty() 
    public_columns = db.TextProperty()
    org = db.StringProperty()
    
    ep_map_ = {}

    def entity_property_metadatas(self, req = None):
        res = [ep for ep in self.entitypropertymetadata_set if check_perm(req, ep)]
        return res
        
    def get_entity_property_metadata(self, req, ep_name):
        if not self.ep_map_:
            for ep in self.entity_property_metadatas(req):
                self.ep_map_[ep.name] = ep
        
        return self.ep_map_[ep_name]
        
class EntityPropertyMetadata(BaseModel):
    type_info = db.ReferenceProperty(TypeInfo, required=False)
    max_length = db.IntegerProperty(default=0)
    is_primary_key = db.BooleanProperty(default=False)
    is_foreign_key = db.BooleanProperty(default=False)
    is_required = db.BooleanProperty(default=False)
    is_search_key = db.BooleanProperty(default=False)
    is_full_text = db.BooleanProperty(default=False)
    in_list_view = db.BooleanProperty(default=False)
    in_show_view = db.BooleanProperty(default=False)
    in_edit_view = db.BooleanProperty(default=False)
    display_width = db.IntegerProperty(default=0)
    display_height = db.IntegerProperty(default=0)
    display_group = db.StringProperty()
    display_index = db.IntegerProperty(default=0)
    enumeration = db.ReferenceProperty(Enumeration, required=False)
    min_value = db.IntegerProperty()
    max_value = db.IntegerProperty()
    default_value = db.StringProperty()
    flags = db.IntegerProperty()
    entity_metadata = db.ReferenceProperty(EntityMetadata, required=False)
    entity_relation = db.StringProperty()
    reg_exp = db.StringProperty()
    is_deleted = db.BooleanProperty(default=False)
    has_generated = db.BooleanProperty(default=False)
    human_name = db.StringProperty()
    camel_name = db.StringProperty()
    is_read_only = db.BooleanProperty(default=False)
    display_type = db.StringProperty()
    ref_type = db.StringProperty()
    metadata = db.ReferenceProperty(Metadata, required=False)
    org = db.StringProperty()

class ImportProfile(BaseModel):
    type_of = db.StringProperty()
    field_mapping  = db.ListProperty(db.Key)
    org = db.StringProperty()
    _fields = []
        
class UserToken(BaseModel):
    value = db.StringProperty()
    expire_date = db.DateTimeProperty()
    source_ip  = db.StringProperty(default=None)
    user = db.ReferenceProperty(User, required=False)

class Group(BaseModel):
    roles = db.ListProperty(db.Key)
    org = db.StringProperty()
    
class Permission(BaseModel):
    item_key = db.StringProperty()
    org = db.StringProperty()
    
class Role(BaseModel):
    permissions = db.ListProperty(db.Key)
    org = db.StringProperty()
    
#NOT USED?
class RolePermissions(BaseModel):
    perm = db.ReferenceProperty(Permission, required=False)
    role = db.ReferenceProperty(Role, required=False)
    org = db.StringProperty()
    
class L10n(BaseModel):
    value = db.StringProperty()
    lang = db.StringProperty()
    page = db.StringProperty()
    metadata = db.ReferenceProperty(Metadata, required=False)
    org = db.StringProperty()
    
class App(BaseModel):
    org = db.ReferenceProperty(Organisation, required=False)
    metadata = db.ReferenceProperty(Metadata, required=False)
    licenses = db.IntegerProperty()
    theme = db.StringProperty()
    security = db.StringProperty(required=False, choices=set(["Private", "Shared", "Public"]))

class DataQuery(BaseModel):
    type_of = db.StringProperty()
    query = db.StringProperty(required=False)
    fulltext_search = db.StringProperty(required=False)
    parent_relation = db.StringProperty(required=False) #used for child data queries
    parent_data_query = db.StringProperty(required=False)
    child_data_queries = db.StringProperty(required=False)
    org = db.StringProperty(required=False)
    metadata = db.ReferenceProperty(Metadata, required=False)

class ViewDefinition(BaseModel):
    type_of = db.StringProperty(required=False)
    org = db.StringProperty(required=False)
    metadata = db.ReferenceProperty(Metadata, required=False)
    default_entity = db.StringProperty(required=False)
    data_queries = db.StringProperty(required=False)
    sub_views = db.StringProperty(required=False)
    default_layout = db.TextProperty(required=False)
    mobile_layout = db.TextProperty(required=False)
    report_layout = db.TextProperty(required=False)
    swfurl = db.StringProperty(required=False)

class ViewMap(BaseModel):
    is_root = db.BooleanProperty()
    title = db.StringProperty(required=False)
    url = db.StringProperty(required=False)
    org = db.StringProperty(required=False)
    view_definition = db.ReferenceProperty(ViewDefinition, required=False)
    metadata = db.ReferenceProperty(Metadata, required=False)
    parent_viewmap = db.SelfReferenceProperty(required=False)

class UploadedFile(BaseModel):
    fileBlob = db.BlobProperty()
    thumbnailBlob = db.BlobProperty()
    fileBlobRef = blobstore.BlobReferenceProperty()
    fileName = db.StringProperty(default=None)
    fileType = db.StringProperty(default=None)
    fileSize = db.IntegerProperty(default=0)
    width = db.IntegerProperty(default=0)
    height = db.IntegerProperty(default=0)
    is_private = db.BooleanProperty()
    ip  = db.StringProperty(default=None)
    url  = db.StringProperty(default=None)
    thumbnail  = db.StringProperty(default=None)
    tags  = db.StringProperty(default=None)

class UserEmail(BaseModel):
    sender = db.StringProperty(default=None)
    receiver = db.StringProperty(default=None)
    reply_to = db.StringProperty(default=None)
    subject = db.StringProperty(default=None)
    body = db.TextProperty(default=None)
    html = db.TextProperty(default=None)

class UserChat(BaseModel):
    sender = db.StringProperty(default=None)
    receiver = db.StringProperty(default=None)
    body = db.TextProperty(default=None)
        
class FriendStats(BaseModel):
    dest = db.StringProperty(default=None)
    is_ok = db.BooleanProperty()
    action = db.IntegerProperty()
    action_time = db.DateTimeProperty(auto_now = True)
    body = db.TextProperty(default=None)
    
class SynchSubscription(BaseModel):
    query = db.ReferenceProperty(DataQuery, required = False)
    app = db.ReferenceProperty(App, required = False)
    conflict_policy = db.StringProperty(required=False, choices=set(["Client", "Server", "Manual"]))
    
class SynchSession(BaseModel):
    server_token = db.StringProperty()
    client_device = db.StringProperty()
    subscription = db.ReferenceProperty(SynchSubscription, required = False)
