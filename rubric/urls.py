from django.conf.urls import url

from . import views

urlpatterns = [

    url(r'^xhr_store/(?P<ractual_code>.+)/$',
                views.xhr_store,
                name='xhr_store'),

    url(r'^xhr_store_text/(?P<ractual_code>.+)/$',
                views.xhr_store_text,
                name='xhr_store_text'),

    url(r'^submit-peer-review-feedback/(?P<ractual_code>.+)$',
                views.submit_peer_review_feedback,
                name='submit_peer_review_feedback'),

]