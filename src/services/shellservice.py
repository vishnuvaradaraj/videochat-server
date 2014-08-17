"""
Adapted from Google shell sample.
"""
import sys
import logging
import traceback
import StringIO

from google.appengine.api import datastore
from google.appengine.api import datastore_types
from google.appengine.api import datastore_errors
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template

import services.schemaloader as schemaloader

def evalCode(statement):
    
    #line ending fix:
    statement = statement.replace('\r\n', '\n')
    statement = statement.replace('\r', '\n')
    
    #run the code
    try:
      logging.info('Compiling and evaluating:\n%s' % statement)
      compiled = compile(statement, '<string>', 'exec')
      try:
        old_stdout = sys.stdout
        sys.stdout = StringIO.StringIO()
        #eval(compiled)
        exec(compiled)
        ret = sys.stdout.getvalue()
      finally:
        sys.stdout = old_stdout
    except:
        logging.error("Compiler error")
        lines = traceback.format_exception(*sys.exc_info())
        return '>>> %s\n%s' % (statement, ''.join(lines))
    
    return  str(ret)

    
    
    
    