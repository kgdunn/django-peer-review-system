from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.template.context_processors import csrf
from django.views.decorators.clickjacking import xframe_options_exempt
from django.utils import timezone

from .models import RubricTemplate, RubricActual
from .models import RItemTemplate, RItemActual
from .models import ROptionTemplate, ROptionActual


@csrf_exempt
@xframe_options_exempt
def handle_review(request, ractual_code):
    """
    From the unique URL:

    1. Get the ``RubricActual`` instance
    2. Format the text for the user
    3. Handle interactions and XHR saving.

    The user coming here is either:
    a) reviewing their own report (self-review)
    b) reviewing a peer's report (peer-review)
    c) self-review, but with their group's feedback (read-only mode)
    d) peer-review, but with their peer's feedback (peer-review, read-only)
    """
    self_review = False
    report = {}
    r_actual, reviewer = get_learner_details(ractual_code)

    # TODO: code here incase the r_actual was not found

    logger.debug('Getting review for {0}:'.format(reviewer))

    #report = get_peer_grading_data(reviewer, feedback_phase)

    # Intentionally put the order_by here, to ensure that any errors in the
    # next part of the code (zip-ordering) are highlighted
    r_item_actuals = r_actual.ritemactual_set.all().order_by('-modified')

    # Ensure the ``r_item_actuals`` are in the right order. These 3 lines
    # sort the ``r_item_actuals`` by using the ``order`` field on the associated
    # ``ritem_template`` instance.
    # I noticed that in some peer reviews the order was e.g. [4, 1, 3, 2]
    r_item_template_order = (i.ritem_template.order for i in r_item_actuals)
    zipped = list(zip(r_item_actuals, r_item_template_order))
    r_item_actuals, _ = list(zip(*(sorted(zipped, key=lambda x: x[1]))))


    has_prior_answers = False
    for item in r_item_actuals:
        item_template = item.ritem_template

        item.options = ROptionTemplate.objects.filter(\
                                 rubric_item=item_template).order_by('order')

        for option in item.options:
            prior_answer = ROptionActual.objects.filter(roption_template=option,
                                                        ritem_actual=item,
                                                        submitted=True)
            if prior_answer.count():
                has_prior_answers = True
                if item_template.option_type in ('DropD', 'Chcks', 'Radio'):
                    option.selected = True
                elif item_template.option_type == 'LText':
                    option.prior_text = prior_answer[0].comment


        # Store the peer- or self-review results in the item; to use in the
        # template to display the feedback.
        #item.results = report.get(item_template, [[], None, None, None, []])

        # Randomize the comments and numerical scores before returning.
        #shuffle(item.results[0])
        #if item_template.option_type == 'LText':
        #    item.results[0] = '\n----------------------\n'.join(item.results[0])
        #    item.results[4] = '\n'.join(item.results[4])


    if has_prior_answers:
        logger.debug('Continue-review: {0}'.format(reviewer))
        create_hit(request, item=r_actual, event='continue-review-session',
                   user=reviewer, other_info='Returning back')

    else:
        logger.debug('Start-review: {0}'.format(reviewer))
        create_hit(request, item=r_actual, event='start-a-review-session',
                   user=reviewer, other_info='Fresh start')

    ctx = {'ractual_code': ractual_code,
           'submission': r_actual.submission,
           'person': reviewer,
           'r_item_actuals' : r_item_actuals,
           'rubric' : r_actual.rubric_template,
           'report': report,
           'self_review': self_review,
           }
    return render(request, 'review/review_peer.html', ctx)


def get_learner_details(ractual_code):
    """
    Verifies the learner is genuine.
    Returns: r_actual (an instance of ``RubricActual``)
             learner  (an instance of ``Person``)
    """
    r_actual = RubricActual.objects.filter(rubric_code=ractual_code)
    if r_actual.count() == 0:
        return HttpResponse(("You have an incorrect link. Either something "
                             "is broken in the peer review website, or you "
                             "removed/changed part of the link.")), None
    r_actual = r_actual[0]
    learner = r_actual.graded_by
    return r_actual, learner


def get_peer_grading_data(learner, phase, role_filter=''):
    """
    Gets the grading data and associated feedback for this ``learner`` for the
    given ``phase`` in the peer review.

    Filters for the role of the grader, can also be provided.
    """
    submission = get_submission(learner, phase, search_earlier=True)
    peer_data = dict()
    peer_data['n_reviews'] = 0
    peer_data['overall_max_score'] = 0.0
    peer_data['learner_total'] = 0.0
    peer_data['did_submit'] = False

    if submission is None:
        return peer_data

    # and only completed reviews
    if role_filter:
        reviews = RubricActual.objects.filter(submission=submission,
                                              status='C',
                                              graded_by__role=role_filter)
    else:
        reviews = RubricActual.objects.filter(submission=submission, status='C')

    if reviews.count() == 0:
        # You must return here if there are no reviews. The rest of the
        # code is not otherwise valid.
        peer_data['did_submit'] = True
        return peer_data




def get_submission(learner, pr_process=None):
    """
    Gets the ``submission`` instance at the particular ``phase`` in the PR
    process.

    Allow some flexibility in the function signature here, to allow retrieval
    via the ``pr_process`` in the future.
    """
    # Whether or not we are submitting, we might have a prior submission
    # to display
    grp_info = {}
    if phase:
        grp_info = get_group_information(learner, phase.pr.gf_process)


    submission = None
    subs = Submission.objects.filter(is_valid=True, pr_process=phase.pr)
    subs = subs.filter(submitted_by=learner).order_by('-datetime_submitted')




def get_create_actual_rubric(learner, trigger, submission, rubric_code=None):
    """
    Creates a new actual rubric for a given ``learner`` (the person doing the)
    evaluation. It will be based on the parent template defined in ``template``,
    and for the given ``submission`` (either their own submission if it is a
    self-review, or another person's submission for peer-review).

    If the rubric already exists it returns it.
    """
    # Get the ``RubricTemplate`` instance via the trigger.
    template = RubricTemplate.objects.get(trigger=trigger)

    # Create an ``rubric_actual`` instance:
    r_actual, new_rubric = RubricActual.objects.get_or_create(\
                        graded_by=learner,
                        rubric_template=template,
                        submission=submission,
                        rubric_code=rubric_code,
                        defaults={'started': timezone.now(),
                                  'completed': timezone.now(),
                                  'status': 'A',         # To be explicit
                                  'submitted': False,
                                  'score': 0.0,
                                  'word_count': 0})


    if new_rubric:

        # Creates the items (rows) associated with an actual rubric
        for r_item in RItemTemplate.objects.filter(r_template=template)\
                                                           .order_by('order'):
            r_item_actual = RItemActual(ritem_template = r_item,
                                        r_actual = r_actual,
                                        comment = '',
                                        submitted = False)
            r_item_actual.save()

    return r_actual, new_rubric