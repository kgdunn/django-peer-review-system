from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$',  views.entry_point_discovery,
                name='index'),

]