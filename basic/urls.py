from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$',  views.entry_point_discovery, name='entry_point_discovery'),

    #url(r'^import_groups$', views.import_groups, name='import_group_division')
]