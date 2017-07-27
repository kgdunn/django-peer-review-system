DEBUG = True

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', ]  # only checked in production

# 02 January 2017: to test LetsEncrypt
CSRF_TRUSTED_ORIGINS = [".edx.org", '127.0.0.1']

EMAIL_HOST = 'smtp.webfaction.com'
EMAIL_HOST_USER = 'kevindunn'
EMAIL_HOST_PASSWORD = 'DrAD4dra'
EMAIL_USE_TLS = True
EMAIL_PORT = 587
DEFAULT_FROM_EMAIL = 'Local Server Development <noreply@example.com>'
SERVER_EMAIL = DEFAULT_FROM_EMAIL
SEND_BROKEN_LINK_EMAILS = not(DEBUG)

import re
IGNORABLE_404_URLS = [
    re.compile(r'^/apple-touch-icon.*\.png$'),
    re.compile(r'^/favicon\.ico$'),
    re.compile(r'^/robots\.txt$'),
]

ADMINS = (('Kevin Dunn', 'kgdunn@gmail.com'), )
MANAGERS = ADMINS

MEDIA_ROOT = '/Users/kevindunn/TU-Delft/CLE/interactivepeer/documents/'
MEDIA_URL = 'documents/'

#STATIC_URL = '/static/'
#STATIC_ROOT = '/Users/kevindunn/TU-Delft/CLE/peer/static/'

# For Brightspace
KEY = 'key'
SECRET = 'secret'

Q_CLUSTER = {
    'name': 'DjangORM',
    'workers': 4,
    'timeout': 90,
    'retry': 120,      # Don’t set the retry timer to a lower or equal number than the task timeout.
    'queue_limit': 50, # Don’t set the queue_limit so high that tasks time out while waiting to be processed.
    'bulk': 10,
    'orm': 'default'
}
# Before using the database cache, you must create the cache table with this command: python manage.py createcachetable
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'my_cache_table',
    }
}



import os
BASE_DIR_LOCAL = os.path.dirname(os.path.abspath(__file__))
LOG_FILENAME = BASE_DIR_LOCAL + os.sep + 'logfile.log'
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': LOG_FILENAME,
            'formatter': 'verbose',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'include_html': True,
            'formatter': 'verbose',
        }
    },
    'formatters': {
        'verbose': {
            'format': "%(levelname)s :: %(funcName)s:%(lineno)s :: %(asctime)s :: %(message)s",
            },
        'simple': {
            'format': '%(levelname)s %(message)s'
            },
        },
    'loggers': {
        'django.request': {
            'handlers': ['file', 'mail_admins'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'review.views': {
            'handlers': ['file', ],
            'level': 'DEBUG',
        },
        'basic.views': {
            'handlers': ['file', ],
            'level': 'DEBUG',
        },
        'utils.__init__': {
            'handlers': ['file', ],
            'level': 'DEBUG',
        }
    },
}

