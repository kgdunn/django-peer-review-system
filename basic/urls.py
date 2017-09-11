from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$',  views.entry_point_discovery, name='entry_point_discovery'),

    # Example: /validate/HGSAT
    #url(r'^validate/(?P<hashvalue>[-\w]+)/$', views.validate_user,
    #    name='validate_user'),

    # Example: /sign-in/QURAA
    #url(r'^sign-in/(?P<hashvalue>[-\w]+)/$', views.sign_in_user,
    #        name='sign_in_user'),

    # Example: /web-sign-in/
    #   url(r'^popup-sign-in$', views.popup_sign_in, name='popup_sign_in'),


]