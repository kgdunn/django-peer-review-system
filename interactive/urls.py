from django.conf.urls import url

from . import views

urlpatterns = [

    # Review
    url(r'^review/(?P<unique_code>.+)/$',
        views.review,
        name='review_with_unique_code'),

    # Evaluation
    url(r'^evaluate/(?P<unique_code>.+)/$',
        views.evaluate,
        name='evaluate_with_unique_code'),
    url(r'^see-evaluation/(?P<unique_code>.+)/$',
        views.see_evaluation,
        name='see_readonly_evaluation_with_unique_code'),

    # Rebuttal
    url(r'^rebuttal/(?P<unique_code>.+)/$',
        views.rebuttal,
        name='rebuttal_with_unique_code'),

    # Assessment
    url(r'^assessment/(?P<unique_code>.+)/$',
        views.assessment,
        name='assessment_with_unique_code'),
    url(r'^see-assessment/(?P<unique_code>.+)/$',
        views.see_assessment,
        name='see_readonly_assessment_with_unique_code'),

    # CSV download
    url(r'^csv_summary_download/$',
        views.csv_summary_download,
        name='csv_summary_download'),


]
