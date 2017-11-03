from django.conf.urls import url

from basic import views

urlpatterns = [
    url(r'^$', views.entry_point_discovery, name='keyterms_entry_point'),
    #url(r'^draft/$', views.draft_keyterm, name='draft_keyterm'),
    #url(r'^preview/$', views.preview_keyterm, name='preview_keyterm'),
    #url(r'^submit/$', views.submit_keyterm, name='submit_keyterm'),
    #url(r'^final/$', views.final_keyterms, name='view_all_keyterms'),
]