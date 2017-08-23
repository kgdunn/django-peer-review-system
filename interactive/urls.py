from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^review/(?P<unique_code>.+)/$',
        views.review,
        name='review_with_unique_code'),


    url(r'^evaluate/(?P<unique_code>.+)/$',
        views.evaluate,
        name='evaluate_with_unique_code'),



]