from django.conf.urls import url

from basic import views
from keyterm import views as keytermviews

urlpatterns = [
    url(r'^$', views.entry_point_discovery, name='keyterms_entry_point'),

    url(r'^vote/$', keytermviews.vote_keyterm, name='vote_keyterm'),
    #url(r'^preview/$', views.preview_keyterm, name='preview_keyterm'),
    #url(r'^submit/$', views.submit_keyterm, name='submit_keyterm'),
    #url(r'^final/$', views.final_keyterms, name='view_all_keyterms'),
]