from django.conf.urls import url

from basic import views
from keyterm import views as keytermviews

urlpatterns = [
    url(r'^$', views.entry_point_discovery, name='keyterms_entry_point'),

    url(r'^vote/(?P<learner_hash>\w+)/$', keytermviews.vote_keyterm, name='vote_keyterm'),
]