from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.template.context_processors import csrf
from django.views.decorators.clickjacking import xframe_options_exempt
from django.utils import timezone

# Python and 3rd party imports
import re
import datetime
import numpy as np

# 3rd party models
from stats.views import create_hit
from grades.models import GradeItem, LearnerGrade

# Our imports
from .models import RubricTemplate, RubricActual
from .models import RItemTemplate, RItemActual
from .models import ROptionTemplate, ROptionActual

# Logging
import logging
logger = logging.getLogger(__name__)



@csrf_exempt
@xframe_options_exempt
def handle_review(request, ractual_code):
    """
    From the unique URL:
    1. Get the ``RubricActual`` instance
    2. Format the text for the user

    The user coming here is either:
    a) reviewing a peer's report (peer-review)
    b) the submitter, looking at their peers' feedback (peer-review, read-only)
    """
    show_feedback = False       # True for case (b) above, else it is case (a)
    report = {}
    r_actual, reviewer = get_learner_details(ractual_code)

    # The submitter is coming to read the review.
    #submitter_read


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

        r_actual.status = 'V'
        r_actual.save()

        logger.debug('Start-review: {0}'.format(reviewer))
        create_hit(request, item=r_actual, event='start-a-review-session',
                   user=reviewer, other_info='Fresh start')

        gitem = GradeItem.objects.get(entry=r_actual.rubric_template.entry_point)
        grade = LearnerGrade.objects.get(gitem=gitem, learner=reviewer)
        THRESHOLD_REVIEW_STARTING = 20.0
        THRESHOLD_REVIEW_ENDING = 24.0
        grade.value = min(THRESHOLD_REVIEW_ENDING,
                          max(THRESHOLD_REVIEW_STARTING, grade.value+1))
        grade.save()

    ctx = {'ractual_code': ractual_code,
           'submission': r_actual.submission,
           'person': reviewer,
           'r_item_actuals' : r_item_actuals,
           'rubric' : r_actual.rubric_template,
           'report': report,
           'show_feedback': False
           }
    return render(request, 'rubric/review_peer.html', ctx)


@csrf_exempt
@xframe_options_exempt
def submit_peer_review_feedback(request, ractual_code):
    """
    Learner is submitting the results of their evaluation.
    """
    # 1. Check that this is POST
    # 2. Create OptionActuals
    # 3. Calculate score for evaluations?

    r_actual, reviewer = get_learner_details(ractual_code)
    if reviewer is None:
        # This branch only happens with error conditions.
        return r_actual

    r_item_actuals = r_actual.ritemactual_set.all()

    items = {}
    # Create the dictionary: one key per ITEM.
    # The value associated with the key is a dictionary itself.
    # items[1] = {'options': [....]  <-- list of the options associated
    #             'item_obj': the item instance / object}
    #

    for item in r_item_actuals:
        item_template = item.ritem_template
        item_dict = {}
        items[item_template.order] = item_dict
        item_dict['options'] = item_template.roptiontemplate_set.all()\
                                                          .order_by('order')
        item_dict['item_obj'] = item
        item_dict['template'] = item_template

    # Stores the users selections as "ROptionActual" instances
    word_count = 0
    total_score = 0.0
    for key in request.POST.keys():

        # Small glitch: a set of checkboxes, if all unselected, will not appear
        # here, which means that that item will not be "unset".

        # Process each item in the rubric, one at a time. Only ``item``
        # values returned in the form are considered.
        if not(key.startswith('item-')):
            continue

        item_num, score, words = process_POST_review(key,
                                              request.POST.getlist(key, None),
                                              items)

        # Only right at the end: if all the above were successful:
        if (item_num is not False): # explicitly check, because here 0 \= False
            items.pop(item_num)  # this will NOT pop if "item_num=False"
                                 # which happens if an empty item is processed
        total_score += score
        word_count += words

    # All done with storing the results. Did the user fill everything in?

    words = [r.word_count for r in RubricActual.objects.filter(status='C')]
    words = np.array(words)
    median_words = np.median(words[words!=0])
    if np.isnan(median_words):
        median_words = 0

    if request.POST:
        request.POST._mutable = True
        request.POST.pop('csrfmiddlewaretoken', None) # don't want this in stats
        request.POST._mutable = False
    if len(items) == 0:
        # Once we have processed all options, and all items, the length is
        # zero, so we can also:
        r_actual.submitted = True
        r_actual.completed = timezone.now()
        r_actual.status = 'C' # completed
        r_actual.word_count = word_count
        r_actual.score = total_score
        r_actual.save()

        # Also mark the Submission as having one extra completed review:
        #r_actual.submission.number_reviews_completed += 1
        #r_actual.submission.save()

        # Set the student's grade
        gitem = GradeItem.objects.get(entry=r_actual.rubric_template.entry_point)
        grade = LearnerGrade.objects.get(gitem=gitem, learner=reviewer)
        THRESHOLD_REVIEW_COMPLETED_START = 25.0
        THRESHOLD_REVIEW_COMPLETED_END = 29.0
        grade.value = min(THRESHOLD_REVIEW_COMPLETED_END,
                          max(THRESHOLD_REVIEW_COMPLETED_START,
                                  grade.value+1))
        grade.save()



        logger.debug('ALL-DONE: {0}. Median={1} vs Actual={2}; Score={3}'\
                     .format(reviewer, median_words, word_count, total_score))
        create_hit(request, item=r_actual, event='ending-a-review-session',
                   user=reviewer, other_info=('COMPLETE; Median={0} vs '
                     'Actual={1}; Score={2}||').format(median_words, word_count,
                                    total_score) + str(request.POST))
    else:
        r_actual.submitted = False
        r_actual.completed = r_actual.started
        r_actual.status = 'P' # Still in progress
        r_actual.word_count = word_count
        r_actual.save()
        create_hit(request, item=r_actual, event='ending-a-review-session',
                   user=reviewer, other_info='MISSING {0}'.format(len(items))\
                                                     + str(request.POST)  )
        logger.debug('MISSING[{0}]: {1}'.format(len(items),
                                                reviewer))
    try:
        percentage = total_score/r_actual.rubric_template.maximum_score*100
    except ZeroDivisionError:
        percentage = 0.0
    ctx = {'n_missing': len(items),
           'r_actual': r_actual,
           'median_words': median_words,
           'word_count': word_count,
           'person': reviewer,
           'total_score': total_score,
           'percentage': percentage
           }
    return render(request, 'rubric/thankyou_problems.html', ctx)


def process_POST_review(key, options, items):
    """
    Each ``key`` in ``request.POST`` has a list (usually with 1 element)
    associated with it. This function processes that(those) element(s) in the
    list.

    The ``items`` dict, created in the calling function, contains the template
    for each item and its associated options.

    If unsuccessfully processed (because it is an empty ``option``), it will
    return "False" as the 1st returned item.
    """
    r_opt_template = None
    item_number = int(key.split('item-')[1])
    comment = ''
    did_succeed = False
    words = 0
    if items[item_number]['template'].option_type in ('Chcks',):
        prior_options_submitted = ROptionActual.objects.filter(
                                    ritem_actual=items[item_number]['item_obj'])

        prior_options_submitted.delete()

    for value in options:

        if items[item_number]['template'].option_type == 'LText':
            r_opt_template = items[item_number]['options'][0]
            if value:
                comment = value
                words += len(re.split('\s+', comment))
                did_succeed = True
            else:
                # We get for text feedback fields that they can be empty.
                # In these cases we must continue as if they were not filled
                # in.
                #continue
                pass  # <--- this is a better option, in case user wants to
                      #      remove their comment entirely.

        elif items[item_number]['template'].option_type in ('Radio', 'DropD',
                                                             'Chcks'):
            selected = int(value.split('option-')[1])

            # in "selected-1": the '-1' part is critical
            try:
                r_opt_template = items[item_number]['options'][selected-1]
                did_succeed = True
            except (IndexError, AssertionError):
                continue

        if items[item_number]['template'].option_type in ('Radio', 'DropD',
                                                          'LText'):
            # Checkboxes ('Chks') should NEVER DELETE, nor ALTER, the prior
            # ``ROptionActual`` instances for this item type, as you might
            # otherwise see for dropdowns, radio buttons, or text fields.

            # If necessary, prior submissions for the same option are adjusted
            # as being .submitted=False (perhaps the user changed their mind)
            prior_options_submitted = ROptionActual.objects.filter(
                                   ritem_actual=items[item_number]['item_obj'])

            prior_options_submitted.update(submitted=False)


        # Then set the "submitted" field on each OPTION
        ROptionActual.objects.get_or_create(roption_template=r_opt_template,

                            # This is the way we bind it back to the user!
                            ritem_actual=items[item_number]['item_obj'],
                            submitted=True,
                            comment=comment)

        # Set the RItemActual.submitted = True for this ITEM
        items[item_number]['item_obj'].submitted = True
        items[item_number]['item_obj'].save()

    if did_succeed:
        return item_number, r_opt_template.score, words
    else:
        return did_succeed, 0.0, 0



@xframe_options_exempt
def xhr_store(request, ractual_code):
    """
    Stores, in real-time, the results from the peer review.
    """

    option = request.POST.get('option', None)
    if option is None or option=='option-NA':
        return HttpResponse('')

    item_post = request.POST.get('item', None)
    if item_post.startswith('item-'):
        item_number = int(item_post.split('item-')[1])
    else:
        return HttpResponse('')


    r_actual, learner = get_learner_details(ractual_code)
    if learner is None:
        # This branch only happens with error conditions.
        return HttpResponse('')
    r_item_actual = r_actual.ritemactual_set.filter(\
                                             ritem_template__order=item_number)
    if r_item_actual.count() == 0:
        return HttpResponse('')
    else:
        r_item = r_item_actual[0]


    item_template = r_item.ritem_template
    r_options = item_template.roptiontemplate_set.all().order_by('order')

    r_opt_template = None
    comment = ''
    if item_template.option_type == 'LText':
        if value:
            r_opt_template = r_options[0]
            comment = value
        else:
            return HttpResponse('')

    if (item_template.option_type == 'Radio') or \
       (item_template.option_type == 'DropD'):
        selected = int(option.split('option-')[1])

        # in "selected-1": the '-1' part is critical
        try:
            r_opt_template = r_options[selected-1]
        except (IndexError, AssertionError):
            return HttpResponse(('<b>Invalid</b>. This should never occur. '
                                'Please report it.'))

    # If necessary, prior submissions for the same option are deleted!
    prior_options_submitted = ROptionActual.objects.filter(ritem_actual=r_item)
    prior_options_submitted.delete()

    # Then set the "submitted" field on each OPTION
    ROptionActual.objects.get_or_create(roption_template=r_opt_template,

                        # This is the way we bind it back to the user!
                        ritem_actual=r_item,
                        submitted=True,
                        comment=comment)

    # Set the RItemActual.submitted = True for this ITEM
    r_item.submitted = True
    r_item.save()

    if r_actual.status in ('A', 'V'):
        r_actual.status = 'P'
        r_actual.started = timezone.now()
        r_actual.save()


    logger.debug('XHR: [{0}]: item={1}; option={2}'.format(learner,
                                                           item_number,
                                                           option))

    now_time = datetime.datetime.now()
    return HttpResponse('Last saved at {}'.format(
                    now_time.strftime('%H:%M:%S')))


@xframe_options_exempt
def xhr_store_text(request, ractual_code):
    """
    Processes the XHR for text fields: it is slightly different than the
    ``xhr_store`` function elsewhere in this file.
    """
    for item, comment in request.POST.items():
        if not comment:
            continue
        comment = comment.encode('utf-8').strip()
        if not item.startswith('item-'):
            continue
        else:
            item_number = int(item.split('item-')[1])


        r_actual, learner = get_learner_details(ractual_code)
        if learner is None:
            return HttpResponse('')
        r_item_actual = r_actual.ritemactual_set.filter(\
                                            ritem_template__order=item_number)

        if r_item_actual.count() == 0:
            continue
        else:
            r_item = r_item_actual[0]

        item_template = r_item.ritem_template
        r_options = item_template.roptiontemplate_set.all().order_by('order')

        r_opt_template = None
        if item_template.option_type == 'LText':
            r_opt_template = r_options[0]
        else:
            continue

        # If necessary, prior submissions for the same option are adjusted
        # as being .submitted=False (perhaps the user changed their mind)
        prior_options_submitted = ROptionActual.objects.filter(ritem_actual\
                                                                       =r_item)
        if prior_options_submitted.count():
            r_option_actual = prior_options_submitted[0]
            if r_option_actual.comment != comment:
                r_option_actual.comment = comment
                r_option_actual.submitted = True
                logger.debug('XHR: [{0}]: item={1}; comment='.format(learner,
                                    item_number))
                r_option_actual.save()
        else:

            # Then set the "submitted" field on each OPTION
            ROptionActual.objects.get_or_create(roption_template=r_opt_template,
                            # This is the way we bind it back to the user!
                            ritem_actual=r_item,
                            submitted=True,
                            comment=comment)
            logger.debug('XHR: [{0}]: item={1}; comment='.format(learner,
                                        item_number))

        # Set the RItemActual.submitted = True for this ITEM
        r_item.submitted = True
        r_item.save()

        if r_actual.status in ('A', 'V'):
            r_actual.status = 'P'
            r_actual.started = timezone.now()
            r_actual.save()

    # Return with something at the end
    now_time = datetime.datetime.now()
    return HttpResponse('Last saved at {}'.format(
                        now_time.strftime('%H:%M:%S')))



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