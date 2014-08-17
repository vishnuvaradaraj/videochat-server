
import logging

# Workaround for issue 128: Import the standard email library
# http://code.google.com/p/googleappengine/issues/detail?id=182
#import email

from google.appengine.api import users
from google.appengine.ext import db

from google.appengine.api.mail import EmailMessage
from google.appengine.api.datastore_errors import BadValueError

from datetime import datetime
from datetime import timedelta

import services.utils as utils
import services.datamodel as datamodel


def send_activation_email(user):
    '''Send the welcome email'''
    e = EmailMessage()
    e.subject = "Welcome to Parabay."
    e.body = """
    
    Hello,
    
    Thanks for signing up, please click the link below to download the Outlook plugin.
    
    %(url)s
    
    - Parabay team.
    
    """ % {'email': user.email, 'url': '%s/%s' % ('http://parabaydemo.appspot.com', 'app/ParabayOutlookSetup.msi')}
    
    e.sender = utils.SENDER_EMAIL
    e.to = user.email
    e.send()

def send_password_reset(user, raw_password):
    '''Send the password reset email'''
    e = EmailMessage()
    e.subject = "Parabay - Password reset"
    e.body = """
    
    Hello,
    
    Your password has been reset to '%(password)s'.
        
    - Parabay team.
    
    """ % {'email': user.email, 'password': raw_password}
    
    e.sender = utils.SENDER_EMAIL
    e.to = user.email
    e.send()

def send_account_deleted(user):
    '''Send the account deleted email'''
    e = EmailMessage()
    e.subject = "Parabay - Account Deleted"
    e.body = """
    
    Hello,
    
    Your account has been deleted.
        
    - Parabay team.
    
    """ % {'email': user.email}
    
    e.sender = utils.SENDER_EMAIL
    e.to = user.email
    e.send()
