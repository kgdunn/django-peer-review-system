from django.conf import settings
from django.conf.urls import url, include
from django.contrib import admin

"""interactivepeer URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""

from basic import views

urlpatterns = [
    url(r'^admin/', admin.site.urls),

    # The interactive (main page)
    url(r'interactive/',
        include('interactive.urls'),
        name='interactive'),

    # The review/rubric filling part, (re)submitting, XHR events
    url(r'review/',
        include('rubric.urls'),
        name='rubric'),

    # Example: /validate/HGSAT    <--- not the nicest way, but it works
    url(r'^validate/(?P<hashvalue>[-\w]+)/$',
        views.validate_user,
        name='validate_user'),

    # Example: /sign-in/QURAA     <--- not the nicest way, but it works
    url(r'^sign-in/(?P<hashvalue>[-\w]+)/$',
        views.sign_in_user,
        name='sign_in_user'),

    # The rest of the entry points:
    url(r'course/(?P<course_code>.+)/(?P<entry_code>.+)/',
        include('basic.urls'),
        name='basic'),

    # The keyterms entry points:
    url(r'keyterms/',
        include('basic.urls'),
        name='basic'),

    url(r'', include('basic.urls'), name='basic'),

]

if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


