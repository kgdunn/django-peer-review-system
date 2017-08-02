from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^(?P<unique_code>.+)/$',
        views.review,
        name='review')
]