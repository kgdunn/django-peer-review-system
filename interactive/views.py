# Verbs: Submit, Review, Evaluate, Rebut, Assess

import os
import sys
import csv
import json
import time
import random
import datetime
import tempfile
from statistics import mean
from random import shuffle
from collections import namedtuple, OrderedDict

# Django imports
from django.http import HttpResponse
from django.template.context_processors import csrf
from django.template import Context, Template, loader
from django.core.files import File
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from django.db.models import Q

# 3rd party imports
import networkx as nx
from networkx.readwrite import json_graph
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, PageBreak
from reportlab.lib.styles import ParagraphStyle, ListStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.colors import black, darkblue, darkred
from reportlab.platypus import Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from PyPDF2 import PdfFileReader, PdfFileMerger

# This app
from .models import Trigger, GroupConfig, Membership, ReviewReport
from .models import AchieveConfig, Achievement
from .models import EvaluationReport
from .models import ReleaseConditionConfig

# Our other apps
from basic.models import EntryPoint
from rubric.views import (handle_review, get_create_actual_rubric,
                          get_learner_details)
from rubric.models import RubricTemplate, RubricActual
from stats.views import create_hit
from submissions.views import (get_submission, upload_submission,
                               is_group_submission)
from submissions.models import Submission
from submissions.forms import (UploadFileForm_one_file,
                               UploadFileForm_multiple_file)

from utils import (send_email, insert_evaluate_variables, generate_random_token,
                   load_kwargs)

# Logging
import logging
logger = logging.getLogger(__name__)

# Summary structure
class Summary(object):
    def __init__(self, date=None, action='', link='', catg=''):
        if date is None:
            self.date = datetime.datetime.now()
        else:
            self.date = date
        self.action = action
        self.link = link
        self.catg = catg

    def __str__(self):
        return '[{0}] {1}'.format(self.date.strftime('%d %B %Y at %H:%M'),
                                  self.action)

    __repr__ = __str__


# Do not change function name: called from the database with this name.
def starting_point(request, course=None, learner=None, entry_point=None):
    """
    Start the interactive tool here:
    0. Can we even run this entry_point?
    1. push a grade of zero to their gradebook, if the first time visiting.
    2. Call the triggers to process sequentially.
    3. Render the page.
    """
    # Check if all/any release conditions are passed. If not, return immediately
    # with a display that shows which conditions are not passed yet.
    rc_configs = ReleaseConditionConfig.objects.filter(entry_point=entry_point)
    conditions = namedtuple('conditions', ['achieved', 'when', 'description',
                                           'entry_point'])
    html_releaseconditions = ''
    if rc_configs:
        ctx_rc = {'entry_point': entry_point}
        rc_config = rc_configs[0]
        condition_set = rc_config.releasecondition_set.all().order_by('order')
        conditions_met = [False, ] * condition_set.count()
        ctx_rc['condition_set'] = [None, ] * condition_set.count()
        for idx, condition in enumerate(condition_set):
            conditions_met[idx] = has(learner,
                                condition.achieveconfig,
                                entry_point=condition.achieveconfig.entry_point,
                                detailed=True)
            if conditions_met[idx]:
                ctx_rc['condition_set'][idx] = conditions(achieved=True,
                            when=conditions_met[idx].when,
                            description=condition.achieveconfig.description,
                            entry_point=condition.achieveconfig.entry_point)
            else:
                ctx_rc['condition_set'][idx] = conditions(achieved=False,
                            when=False,
                            description=condition.achieveconfig.description,
                            entry_point=condition.achieveconfig.entry_point)

        next_step = False
        if rc_config.any_apply and any(conditions_met):
            next_step = True
        if rc_config.all_apply and all(conditions_met):
            next_step = True

        # Non-learners are always allowed through
        if learner.role not in ('Learn',):
            next_step = True

        if not(next_step):
            html_releaseconditions = loader.render_to_string(('interactive/'
                                    'releasecondition_display.html'), ctx_rc)
            return HttpResponse(html_releaseconditions)


    # Step 1:
    # error_response = push_to_gradebook(learner, 0.0, entry_point,testing=True)
    # if error_response:  # We don't expect an error
    #    return HttpResponse(error_response)

    # Step 2: Call all triggers:
    triggers = entry_point.trigger_set.filter(is_active=True).order_by('order')
    module = sys.modules[__name__]
    now_time = datetime.datetime.now(datetime.timezone.utc)

    ctx_objects = {'now_time': now_time,
                   'learner': learner,
                   'course': course,
                   'entry_point': entry_point,

                   # Used for pushing grades to the platform
                   'sourcedid': \
                             request.POST.get('lis_result_sourcedid', ''),

                  }
    ctx_objects.update(csrf(request)) # add the csrf; used in forms


    # First run through to ensure all triggers exist
    for trigger in triggers:
        try:
            func = getattr(module, trigger.function)
        except AttributeError:
            return HttpResponse('Please create function {0}'.format(\
                                                             trigger.function))

        kwargs = trigger.kwargs.replace('\r','').replace('\n','').replace(' ', '')
        if kwargs:
            try:
                _ = json.loads(kwargs)
            except json.decoder.JSONDecodeError as err:
                return HttpResponse(('Error parsing the kwargs: {0} [{1}]'
                                     .format(err, kwargs)))

    create_hit(request, item=course, event='login', user=learner,
               other_info=entry_point)

    summaries = []

    if learner.role in ('Admin',):
        ctx_objects['overview_learners'] = overview_learners(entry_point,
                                                             admin=learner)
    else:
        # Only run this for learners
        for trigger in triggers:
            # Then actually run each trigger, but only if the requirements are
            # met, and we are within the time range for it.

            run_trigger = True
            if (trigger.start_dt > now_time):
                run_trigger = False
            if (trigger.end_dt) and (trigger.end_dt <= now_time):
                run_trigger = False
            if (trigger.always_run):
                run_trigger = True

            if not(run_trigger):
                continue

            func = getattr(module, trigger.function)
            if trigger.kwargs:
                kwargs = json.loads(trigger.kwargs.replace('\r', '')\
                                    .replace('\n', ''))
            else:
                kwargs = {}


            # Push these ``kwargs`` into trigger (getattr, settattr)
            for key, value in kwargs.items():
                try:
                    getattr(trigger, key)
                except AttributeError:
                    setattr(trigger, key, value)

            # Some default attributes for the Trigger
            if not(hasattr(trigger, 'show_dates')):
                setattr(trigger, 'show_dates', False)   # don't show dates in UI
            if not(hasattr(trigger, 'show_review_numbers')):
                setattr(trigger, 'show_review_numbers', True) # show "Peer A" in docs

            # Add self to ctx_objects
            ctx_objects['self'] = trigger

            # Call the function, finally.
            func(trigger,
                 learner=learner,
                 ctx_objects=ctx_objects,
                 entry_point=entry_point,
                 summaries=summaries,
                 request=request
               )

    ctx_objects['summary_list'] = summaries
    if settings.DEBUG:
        ctx_objects['header'] = '<h2>DEBUG ONLY: {}</h2><br>'.format(learner.display_name)

    global_summary = entry_point.course.entrypoint_set.filter(order=0)
    if global_summary:
        ctx_objects['global_summary_link'] = global_summary[0].full_URL


    html = loader.render_to_string('interactive/{}'.format(\
        entry_point.settings('landing_page')), ctx_objects)
    return HttpResponse(html)


def render_template(trigger, ctx_objects):
    """
    Renders the templated text in ``trigger`` using variables in ``ctx_objects``

    """
    ctx_objects['self'] = trigger
    return insert_evaluate_variables(trigger.template, ctx_objects)


# ------------------------------
# The various trigger functions
# ------------------------------
def get_submission_form(trigger, learner, entry_point=None, summaries=list(),
                   ctx_objects=dict(), **kwargs):
    """
    Displays the submission form, and handles the upload of it.

    Fields that can be used in the template:
        {{submission}}                The ``Submission`` model instance
        {{submission_error_message}}  Any error message
        {{file_upload_form}}          The HTML for the upload form
        {{allow_submit}}              If submissions are allowed

    Settings possible in the kwargs, with the defaults are shown.
    {  "accepted_file_types_comma_separated": "PDF",
       "max_file_upload_size_MB": <unlimited>,  [specify as 10 (not a string)]
       "allow_multiple_files": "false",
       "send_email_on_success": "false"
    }

    """
    # Remove the prior submission from the dict, so that PRs that use
    # multiple submission steps get the correct phase's submission
    #ctx_objects.pop('submission', None)

    # Get the (prior) submission
    submission = prior_submission = get_submission(learner,
                                                   trigger,
                                                   entry_point)

    # What the admin's see
    if learner.role != 'Learn':
        ctx_objects['self'].admin_overview = 'ADMIN TEXT GOES HERE STILL.'

    if not(getattr(trigger, 'accepted_file_types_comma_separated', False)):
        trigger.accepted_file_types_comma_separated = 'PDF'

    if not(getattr(trigger, 'max_file_upload_size_MB', False)):
        trigger.max_file_upload_size_MB = 5

    if not(hasattr(trigger, 'send_email_on_success')):
        trigger.send_email_on_success = False

    if getattr(trigger, 'allow_multiple_files', False):
        file_upload_form = UploadFileForm_multiple_file()
    else:
        file_upload_form = UploadFileForm_one_file()

    submission_error_message = ''
    if kwargs['request'].FILES and \
                          not(has(learner, 'started_a_review', entry_point)):

        submit_inst = upload_submission(kwargs['request'],
                                        learner,
                                        trigger)

        # Once processed, pop it out.
        kwargs['request'].FILES.pop('file_upload')

        # One final check: has a reviewer been allocated to this review
        # from this entry_point yet?
        group_submitter = Membership.objects.filter(role='Submit',
                                            learner=learner,
                                            group__entry_point=entry_point)

        if group_submitter.count():
            group = group_submitter[0].group
            reviewers = Membership.objects.filter(role='Review',
                                                  group=group,
                                                  fixed=True)

            if (reviewers.count() and prior_submission):

                logger.debug(('New submission set to False: {0} as item has '
                          'just started review.'.format(submit_inst)))
                submit_inst.is_valid = False
                submit_inst.save()

                prior_submission.is_valid = True
                prior_submission.save()

                submit_inst = (submit_inst, ('Your submission has been refused;'
                               ' a peer has just started reviewing your work.'))


        if isinstance(submit_inst, tuple):
            # Problem with the upload: revert back to the prior.
            submission_error_message = submit_inst[1]
            submission = prior_submission
        else:
            # Successfully uploaded a document. Mark it as submitted for this
            # learner, as well as their team members.
            submission_error_message = ''
            submission = submit_inst


            # TODO: Send an email here, if needed.

            # Create a group with this learner as the submitter
            learner_s = [learner, ]
            group_enrolled = is_group_submission(learner, entry_point)
            if group_enrolled:
                learner_s.extend(group_enrolled.group_members)
                learner_s = list(set(learner_s))

            for student in learner_s:


                # First, learner (or their group) has completed this step:
                completed(student, 'submitted', entry_point)

                # Check if the membership has been created. If not, create a
                # new GroupConfig, and make the student a member.
                memberships = student.membership_set.filter(role='Submit',
                                                group__entry_point=entry_point,
                                                fixed=True)

                if not(memberships.count()):
                    new_group = GroupConfig(entry_point=trigger.entry_point)
                    new_group.save()
                    member = Membership(learner=student,
                                        group=new_group,
                                        role='Submit',
                                        fixed=True)
                    member.save()

            # Finished creating a new group.

    else:
        submission = prior_submission


    # Whether a new submission or not, create the reviews
    invite_reviewers(trigger)

    # Store some fields on the ``trigger`` for rendering in the template
    trigger.submission = submission
    trigger.submission_error_message = submission_error_message
    trigger.file_upload_form = ctx_objects['file_upload_form'] = \
        file_upload_form

    # Note: this is triggered in 2 places: the learner cannot resubmit if
    #       they themselves have started a review of their peer (this is to
    #       prevent learners from seeing the rubric via a peer's work).
    #       Note: a learner is only invited to review once they themselves
    #             have submitted something already.
    #       Also, if the learner's work is started to being reviewed by a peer
    #       then the original submitter cannot resubmit.
    if has(learner, 'work_has_started_to_be_reviewed', entry_point):
        trigger.allow_submit = False  # False, if no more submissions allowed
    else:
        trigger.allow_submit = True

    if learner.role in ('admin',):
        trigger.allow_submit = False  # prevent issues with instructor's upload

    if trigger.deadline_dt and (trigger.deadline_dt < timezone.now()):
        trigger.allow_submit = False  # prevent late submissions

    ctx_objects['submission'] = trigger.template

    if trigger.submission:
        summary = Summary(date=trigger.submission.datetime_submitted,
                          action='{0} successfully submitted a document.'\
                        .format(trigger.submission.submitted_by.display_name,),
                          link='<a href="{0}" target="_blank">{1}</a>'.format(\
                              trigger.submission.file_upload.url,
                              "View"),
                          catg='')
        summaries.append(summary)

    ctx_objects['submission'] = render_template(trigger, ctx_objects)
    return trigger # newly added for CE course: to allow us to use fields


def your_reviews_of_your_peers(trigger, learner, entry_point=None,
                         summaries=list(), ctx_objects=dict(), **kwargs):
    """
    We are filling in this template multiple times; once per num_peers:

    <span class="you-peer">
        <b>Your review of peer {0}</b>:
        <ul>
            <li class="{1}">{2}</li>
            <li class="{3}">{4}</li>
            <li class="{5}">{6}</li>
            <li class="{7}">{8}</li>
            <li class="{9}">{10}</li>
        </ul>
    </span>
    """
    review_to_peers = ''
    peer = {}
    peer['line1'] = get_line1(learner, trigger, summaries)
    peer['line2'] = get_line2(learner, trigger, summaries)
    peer['line3'] = get_line3(learner, trigger, summaries)
    peer['line4'] = get_line4(learner, trigger, summaries)
    peer['line5'] = get_line5(learner, trigger, summaries)

    for idx in range(trigger.entry_point.settings('num_peers')):
        review_to_peers += """
        <span class="you-peer">
        <b>Your review of peer {0}</b>:
        <ul>
            <li class="{1}">{2}</li>
            <li class="{3}">{4}</li>
            <li class="{5}">{6}</li>
            <li class="{7}">{8}</li>
            <li class="{9}">{10}</li>
        </ul>
        </span>
        """.format(chr(idx+65),
                   peer['line1'][idx][0],
                   peer['line1'][idx][1],
                   peer['line2'][idx][0],
                   peer['line2'][idx][1],
                   peer['line3'][idx][0],
                   peer['line3'][idx][1],
                   peer['line4'][idx][0],
                   peer['line4'][idx][1],
                   peer['line5'][idx][0],
                   peer['line5'][idx][1],
                )

    trigger.template = review_to_peers
    ctx_objects['review_to_peers'] = render_template(trigger, ctx_objects)


def get_line1(learner, trigger, summaries, ctx_objects=None):
    """
    Fills in line 1 of the template:
        > Waiting for a peer to submit their work ...
        > You must submit before you can review others
        > Start your review
        > Continue your review
        > Completed

    """
    out = []
    num_peers = trigger.entry_point.settings('num_peers')

    # All valid submissions for this EntryPoint
    valid_subs = Submission.objects.filter(entry_point=trigger.entry_point,
                            is_valid=True).exclude(status='A')

    if valid_subs:
        submission_trigger = valid_subs[0].trigger
    else:
        submission_trigger = None

    # Not guaranteed that this object is passed in
    can_be_done = True
    if ctx_objects:
        if ctx_objects['now_time'] > trigger.deadline_dt:
            can_be_done = False
            status = 'The time to start your peer review has passed.'


    # All ReviewReport that have been Allocated for Review to this learner
    allocated_reviews = ReviewReport.objects.filter(reviewer=learner,
        entry_point=trigger.entry_point).order_by('-created') # for consistency

    reviews_completed = [False, ] * num_peers
    achievement_text = ''
    achievement_grade = []
    for idx, review in enumerate(allocated_reviews):

        if not(review.order):
            review.order = idx+1
            review.save()

        if can_be_done:
            status = '<span class="still-to-do">Start</span> your review'

        grade = ''
        # What is the status of this review. Cross check with RubricActual
        prior = RubricActual.objects.filter(rubric_code=review.unique_code)
        prior_rubric = None
        if prior.count():
            prior_rubric = prior[0]
            if prior_rubric.status in ('C', 'L'):
                extra = ''
                if prior_rubric.status in ('C',) and can_be_done:
                    extra = (' <span class="still-to-do">(you can still make '
                             'changes)</span>')


                score = prior_rubric.score
                max_score = prior_rubric.rubric_template.maximum_score
                achievement_grade.append(score/max_score*100\
                                                     if max_score != 0 else 0.0)
                grade = '{:d}/{:d}={:3.1f}%'.format(int(score), int(max_score),
                                                    achievement_grade[-1])
                achievement_text += '{:d}/{:d} and '.format(int(score),
                                                       int(max_score))
                status = 'Completed' + extra
                reviews_completed[idx] = True
                if trigger.show_review_numbers:
                    action = 'You completed review number {0}; thank you!'\
                                                .format(chr(review.order+64))
                else:
                    action = 'You completed a review; thank you!'

                summary = Summary(date=prior_rubric.completed, action=action,
                        link=('<a href="/interactive/review/{0}" '
                         'target="_blank">View</a>').format(review.unique_code),
                        catg='rev')

                summaries.append(summary)

            elif prior_rubric.status in ('P', 'V'):
                status = ('<span class="still-to-do">Start/continue</span> '
                          'your review')


            if not(can_be_done) and prior_rubric.status not in ('C', 'L', 'F'):
                status = 'Deadline has passed to complete your review.'
                prior_rubric.status = 'L'
                prior_rubric.save()


        # We have a potential review
        out_text = ('<a href="/interactive/review/{0}" target="_blank">'
                         '{1}</a>').format(review.unique_code, status)
        if grade:
            out_text += ' [you gave: {0}]'.format(grade)

        out.append(('', out_text ))

        if prior.count() == 0:
            graph = group_graph(trigger.entry_point)
            potential_submitter = graph.get_submitter_for(reviewer=learner)
            if potential_submitter is None:
                # If there is no potential submitter, AND, no prior r_actuals:
                out[idx] = (('future',
                             'Waiting for a peer to submit their work ...'))


        if not(can_be_done):
            if (prior_rubric is None) or prior_rubric.status in ('P', 'V'):
                # This branch will only be caught if after the deadline.
                out[idx] = (('future', status))

    if sum(reviews_completed) == num_peers:
        if achievement_text:
            achievement_text = achievement_text[0:-5]
        completed(learner, 'completed_all_reviews', trigger.entry_point,
                  display=achievement_text, grade=mean(achievement_grade))

    for idx in range(num_peers-len(out)):

        if not(has(learner, 'submitted', trigger.entry_point)):
            out.append(('', 'You must submit before you can review others.'))
            continue

        mp = trigger.entry_point.settings('min_in_pool_before_grouping_starts')
        if not(valid_subs.count() >= mp):
            # Simplest case: no reviews are allocated to learner yet
            out.append(('', 'Waiting for a peer to submit their work ...'))
            continue

    if (allocated_reviews.count()==0) and len(out) != num_peers:
        # This code shouldn't occur, but it is a catch, in the case of
        # inconsistencies in the database.
        logger.error(('Code catch around inconsistencies in the allocated '
                     'reviews; please investigate.'))
        for idx in range(num_peers):
            out.append(('', 'You must submit before you can review others.'))

    return out

def get_line2(learner, trigger, summaries):
    """
    Get the Summary and text display related to the evaluation being read.
    """
    out = []
    allocated_reviews = ReviewReport.objects.filter(reviewer=learner,
        entry_point=trigger.entry_point).order_by('-created') # for consistency

    for idx in range(trigger.entry_point.settings('num_peers')):
        out.append(('future', 'Waiting for peer to read your review'))


    # We use ``allocated_reviews`` to ensure consistency of order,
    # but we jump from that, using .next_code, to EvaluationReport. There
    # we pick up the r_actual, and look at the dates and times on it.
    for idx, review in enumerate(allocated_reviews):
        rubrics = RubricActual.objects.filter(rubric_code=review.unique_code)
        if rubrics:
            rubric = rubrics[0]
        else:
            break
        evalrep = EvaluationReport.objects.filter(unique_code=rubric.next_code)
        for report in evalrep:
            if report.r_actual:
                out[idx] = ('', 'Peer has read your review')
                if trigger.show_review_numbers:
                    summaries.append(Summary(date=report.r_actual.created,
                            action='Peer {0} read your review.'.format(\
                                chr(idx+65)), link='', catg='rev')
                        )
                else:
                    summaries.append(Summary(date=report.r_actual.created,
                            action='A peer has read your review.',
                            link='', catg='rev')
                        )

    return out

def get_line3(learner, trigger, summaries):
    """
    Get the Summary and text display related to the evaluation being evaluated.
    """
    out = []
    allocated_reviews = ReviewReport.objects.filter(reviewer=learner,
        entry_point=trigger.entry_point).order_by('-created') # for consistency

    for idx in range(trigger.entry_point.settings('num_peers')):
        out.append(('future', 'Waiting for peer to evaluate your review'))

    # We use ``allocated_reviews`` to ensure consistency of order,
    # but we jump from that, using .next_code, to EvaluationReport. There
    # we pick up the r_actual, and look at the dates and times on it.
    for idx, review in enumerate(allocated_reviews):
        rubrics = RubricActual.objects.filter(rubric_code=review.unique_code)
        if rubrics:
            rubric = rubrics[0]
        else:
            break
        evalrep = EvaluationReport.objects.filter(unique_code=rubric.next_code)
        for report in evalrep:
            if not report.r_actual:
                continue
            if  getattr(report.r_actual, 'next_code', ''):
                eval_code = report.r_actual.next_code
            else:
                # Generate the ``next_code`` as needed, to allow the
                # reviewer to see the evaluation (read-only) of the original
                # submitter.
                report.r_actual.next_code = eval_code = generate_random_token()
                report.r_actual.save()

            if getattr(report.r_actual, 'evaluated', ''):

                link = ('<a href="/interactive/see-evaluation/{0}" '
                        'target="_blank">{1}</a>')
                out[idx] = ('',
                            'Peer evaluated your review: {0}'.format(link.\
                            format(eval_code, 'see evaluation')) )


                summary = Summary(action='Peer {0} evaluated your review.'.\
                                                      format(chr(idx+65)),
                                  date=report.r_actual.evaluated,
                                  link=link.format(eval_code, 'View'),
                                  catg='rev')
                summaries.append(summary)


    return out

def get_line4(learner, trigger, summaries):
    """
    Check if a rebuttal is available.
    """
    out = []
    for idx in range(trigger.entry_point.settings('num_peers')):
        if has(learner, 'completed_all_reviews', trigger.entry_point) or \
                     not(has(learner, 'started_a_review', trigger.entry_point)):
            out.append(('future', "Waiting for peer's rebuttal of your review"))
        else:
            out.append(('future', "Please complete all allocated reviews first"))

    if not(has(learner, 'completed_all_reviews', trigger.entry_point)):
        return out

    allocated_reviews = ReviewReport.objects.filter(reviewer=learner,
        entry_point=trigger.entry_point).order_by('-created') # for consistency


    # We use ``allocated_reviews`` to ensure consistency of order,
    # but we jump from that directly to the Rebuttal report (sort_report='A')
    # that was generated by the submitter (evaluator=review.submission.submitted_by)

    for idx, review in enumerate(allocated_reviews):
        if not review.submission:
            continue
        rebut_reports = EvaluationReport.objects.filter(sort_report='A',
                                       trigger__entry_point=trigger.entry_point,
                                       evaluator=review.submission.submitted_by)

        if rebut_reports:
            out[idx] = ('', 'Peer has written a rubuttal')
        else:
            continue

    # All done!
    return out


def get_line5(learner, trigger, summaries):
    """
    Get the text display related to the rebuttal being assessed.
    """
    out = []
    for idx in range(trigger.entry_point.settings('num_peers')):
        out.append(('future', "Your assessment of their rebuttal"))

    if not(has(learner, 'completed_all_reviews', trigger.entry_point)):
        return out

    # Added this to avoid assessment happening before rebuttal
    if not(has(learner, 'completed_rebuttal', trigger.entry_point)):
        return out

    allocated_reviews = ReviewReport.objects.filter(reviewer=learner,
        entry_point=trigger.entry_point).order_by('-created') # for consistency


    # We use ``allocated_reviews`` to ensure consistency of order,
    # but we jump from that directly to the Rebuttal report (sort_report='A')
    # that was generated by the submitter (evaluator=review.submission.submitted_by)

    n_rebuttals_completed = 0

    for idx, review in enumerate(allocated_reviews):
        if not review.submission:
            continue
        rebut_reports = EvaluationReport.objects.filter(sort_report='A',
                                       evaluator=review.submission.submitted_by,
                                       trigger__entry_point=trigger.entry_point,
                                       peer_reviewer=learner)

        if rebut_reports:
            rebuttal = rebut_reports[0]
        else:
            continue

        link = ('{3}<a href="/interactive/assessment/{0}" target="_blank">'
                '{1}</a> {2}')
        out[idx] = ('', link.format(rebuttal.unique_code,
            '<span class="still-to-do">Read and assess</span> their rebuttal',
            'of your review', ''))

        extra = 'Assess it'
        try:
            rubric = RubricActual.objects.get(rubric_code=rebuttal.unique_code)
            if rubric.status in ('C', 'L'):
                n_rebuttals_completed += 1
                extra = 'View'
                out[idx] = ('', link.format(rebuttal.unique_code,
                                            'assessed their rebuttal',
                                            'of your review', 'You have '))
                summary = Summary(action='You assessed rebuttal for peer {0}.'.format(idx+1),
                        date=rebuttal.r_actual.completed,
                        link=link.format(rebuttal.unique_code, extra, '', ''),
                        catg='rev')
                summaries.append(summary)


        except RubricActual.DoesNotExist:
            pass

        summary = Summary(action='Peer {0} wrote a rebuttal.'.format(\
                          chr(idx+65)),
                          date=rebuttal.created,
                          link=link.format(rebuttal.unique_code, extra, '', ''),
                          catg='rev')
        summaries.append(summary)


    if n_rebuttals_completed == trigger.entry_point.settings('num_peers'):
        completed(learner, 'assessed_rebuttals',
                  trigger.entry_point)


    # All done!
    return out



def peers_read_evaluate_feedback(trigger, learner, entry_point=None,
                         summaries=list(), ctx_objects=dict(), **kwargs):
    """
    We are filling in this part of the template:

    <span class="indent">
    <ul>
        <li class="peers_to_you {0}" type="a">(a) {1}</li>  <--- this line
        <li class="peers_to_you {2}" type="a">(b) {3}</li>
        <li class="peers_to_you {4}" type="a">(c) {5}</li>
    </ul>
    """
    num_peers = trigger.entry_point.settings('num_peers')
    ctx_objects['peers_to_submitter_header'] = ('You must first submit some '
                                            'work for your peers to review.')
    ctx_objects['lineA'] = ('future',
                            "Read and evaluate reviewers' feedback")


    my_submission = Submission.objects.filter(entry_point=trigger.entry_point,
                                              is_valid=True,
                                              submitted_by=learner)\
                                      .exclude(status='A')

    if my_submission.count() > 1:
        logger.warn('More than one submission encountered')

    if not(has(learner, 'submitted', entry_point)) or my_submission.count()==0:
        return


    submission = my_submission[0]
    reports = [False, ] * num_peers
    reviews = [False,] * num_peers
    idx = 0
    my_reviews = []


    my_reviews = ReviewReport.objects.filter(submission=submission).\
        order_by('created') # to ensure consistency in display
    for report in my_reviews:
        # There should be at most "num_peers" reviews.

        # An error occurs here where a review is allocated beyond the number of
        # intended reviews.
        reports[idx] = report
        try:
            rubric = RubricActual.objects.get(rubric_code=reports[idx].unique_code)
        except RubricActual.DoesNotExist:
            continue
        if rubric.submitted:
            reviews[idx] = True


        # Bump the counter and get the rest of the reviews.
        idx += 1

    # This message is overridden later for the case when everyone is completed.
    template = """{{n_reviewed}} peer{{ n_reviewed|pluralize:" has,s have" }}
     completely reviewed your work. Waiting for {{n_more}} more
        peer{{n_more|pluralize}} to start and complete their
        review{{n_more|pluralize}}."""

    header = insert_evaluate_variables(template, {'n_reviewed': sum(reviews),
                                        'n_more': num_peers - sum(reviews)})


    # This strange if statement allows for learners to slip past this gate,
    # in the exceptional cases when they do not have sufficient number of peers.
    if (sum(reviews) == num_peers) or has(learner,
                                            'all_reviews_from_peers_completed',
                                            entry_point=entry_point):
        completed(learner, 'all_reviews_from_peers_completed', entry_point)
        header = "All peers have completely reviewed your work."

    ctx_objects['peers_to_submitter_header'] = header

    # From the perspective of the learner, we should always order the peers
    # is the same way. Use the ``created`` field for that.
    rubrics = RubricActual.objects.filter(submission=submission)\
                                                            .order_by('created')
    for idx, ractual in enumerate(rubrics):
        summary = Summary(date=ractual.created, link='', catg='sub',
          action='Peer {} began a review of your work.'.format(idx+1))
        summaries.append(summary)

        if ractual.status in ('C', 'L') and ractual.submitted:
            summary = Summary(date=ractual.completed, link='', catg='sub',
                action='Peer {} completed a review of your work.'.format(idx+1))
            summaries.append(summary)

    if sum(reviews) == 0:
        # There is no point to go further if there are no reviews completed
        # of the learner's work.
        return

    if not(has(learner, 'started_a_review', entry_point)):
        # The learner hasn't reviewed other's work; so they are not in state
        # to evaluate others yet either.
        ctx_objects['lineA'] = ('', ('Please complete a review first, before '
                                     'evaluating their reviews.'))

        return


    # We cannot go further, unless all the reviews by the learner's peers are
    # completed.
    if not(has(learner, 'all_reviews_from_peers_completed', entry_point)):
        return


    # Slow-down throttle here: we don't want to allow the submitter to start
    # evaluation unless they have finished their reviews.
    if not(has(learner, 'completed_all_reviews', entry_point)):
        header = ("All peers have completely reviewed your work. However, you "
                  "can only see that feedback once you have finished all your "
                  "allocated reviews.")
        ctx_objects['peers_to_submitter_header'] = header
        return


    # If we have reached this point it is because the submitter can now
    # view their feedback. Therefore we only iterate over the COMPLETED rubrics.
    #
    # 1/ Set the r_actual review to be locked (read-only)
    # 2/ Create a rubric for evaluation of the review

    text = 'Read and evaluate their feedback: '
    for idx, ractual in enumerate(rubrics):
        ractual.status = 'L'
        ractual.save()
        try:
            report = EvaluationReport.objects.get(unique_code=ractual.next_code)
        except EvaluationReport.DoesNotExist as e:
            logger.error('EvaluationReport not found. Please correct:[{0}:{1}]'\
                         .format(ractual.id, ractual))
            ctx_objects['lineA'] = ('',
                                    ("The links to read and evaluate reviewers'"
                                     " feedback are still being generated. "
                                     "Please wait."))
            return

        extra = ' <span class="still-to-do">(still to do)</span>'
        if hasattr(report.r_actual, 'status'):
            if report.r_actual.status in ('C', 'L'):
                extra = ' (completed)'

        if (idx > 0) and (idx < num_peers):
            text += ';&nbsp;'

        text += ('evaluate <a href="/interactive/evaluate/{0}/" '
                 'target="_blank">peer {1}</a>{2}').format(report.unique_code,
                                                           idx+1, extra)

    text += '.'
    ctx_objects['lineA'] = ('', text)


    if has(learner, 'completed_rebuttal', entry_point):
        pass


def peers_provide_rebuttal(trigger, learner, entry_point=None,
                         summaries=list(), ctx_objects=dict(), **kwargs):
    """
    We are filling in this part of the template:

    <span class="indent">
    <ul>
        <li class="peers_to_you {0}" type="a">(a) {1}</li>
        <li class="peers_to_you {2}" type="a">(b) {3}</li>   <--- this line
        <li class="peers_to_you {4}" type="a">(c) {5}</li>
    </ul>
    """
    ctx_objects['lineB'] = ('future',
                            'Provide rebuttal back to peers once you evaluated')

    # Learner has not only seen, but also evaluated all the reviews. Now it
    # is time to do fill in the rebuttal rubric.
    if has(learner, 'read_and_evaluated_all_reviews', entry_point):
        evaluations = EvaluationReport.objects.filter(trigger=trigger,
                                                      sort_report='R',
                                                    evaluator=learner)
        if evaluations.count() == 0:
            logger.warn('No evaluations found: likely a student in override?')
            return
        else:
            evaluation = evaluations[0]

        link = '<a href="/interactive/rebuttal/{}" target="_blank">{}</a> {}'

        if has(learner, 'completed_rebuttal', entry_point):
            summary = Summary(date=evaluation.created,
                              action=('You evaluated all reviews; thank you!'),
                              catg='sub')
            summaries.append(summary)
            summary = Summary(date=evaluation.r_actual.completed,
                              action=('You completed the rebuttal; thank you!'),
                              link=link.format(evaluation.unique_code, 'View',
                                               ''),
                              catg='sub')
            summaries.append(summary)
            ctx_objects['lineB'] = ('', link.format(evaluation.unique_code,
                                        'Provide a rebuttal',
                                        'back to your peers (completed)'))
        else:
            summary = Summary(date=evaluation.created,
                              action=('You evaluated all reviews. Please '
                                      'complete the rebuttal.'),
                                      link=link.format(evaluation.unique_code,
                                                       'Rebuttal', ''),
                                      catg='sub')
            summaries.append(summary)
            ctx_objects['lineB'] = ('', link.format(evaluation.unique_code,
                '<span class="still-to-do">Provide</span> a rebuttal',
                'back to your peers'))


def peers_rebuttal_assessment(trigger, learner, entry_point=None,
                         summaries=list(), ctx_objects=dict(), **kwargs):
    """
    We are filling in this part of the template:

    <span class="indent">
    <ul>
        <li class="peers_to_you {0}" type="a">(a) {1}</li>
        <li class="peers_to_you {2}" type="a">(b) {3}</li>
        <li class="peers_to_you {4}" type="a">(c) {5}</li>    <--- this line
    </ul>
    """
    ctx_objects['lineC'] = ('future',
                            'Waiting for rebuttal to be read and assessed')

    # Update on the status of the assessment.


    if not(has(learner, 'completed_rebuttal', entry_point)):
        return

    # From the perspective of the learner, we should always order the peers
    # is the same way. Use the ``created`` field for that.
    my_submission = Submission.objects.filter(entry_point=trigger.entry_point,
                                              is_valid=True,
                                              submitted_by=learner)\
                                                            .exclude(status='A')

    rubrics = RubricActual.objects.filter(submission=my_submission)\
        .order_by('created')

    text = 'Rebuttal status: '

    # There should also be ``num_peers`` reports here
    assessments = EvaluationReport.objects.filter(trigger=trigger,
                                                  sort_report='A',
                                                  evaluator=learner)

    for idx, ractual in enumerate(rubrics):
        assessment = assessments.filter(peer_reviewer=ractual.graded_by)
        extra = ''
        link = ('<a href="/interactive/see-assessment/{}" target="_blank">'
                '{}</a>')

        if assessment[0].r_actual:
            verb = 'has been read by'
            extra =' (waiting for their assessment)'
            if assessment[0].r_actual.status in ('C', 'L'):
                verb = 'assessed by'
                extra = ' ({})'.format(link.format(\
                                    assessment[0].r_actual.rubric_code,
                                    'view it', ''))

                summary = Summary(date=assessment[0].r_actual.completed,
                    action=('Peer {} assessed your rebuttal.').format(idx+1),
                    link=link.format(assessment[0].r_actual.rubric_code, 'View',
                                     ''),
                    catg='sub')
                summaries.append(summary)
        else:
            verb = 'waiting for'
            extra = ' to read it'


        text += '{} peer {}{}'.format(verb, idx+1, extra)
        if (idx >= 0) and (idx < len(rubrics)-1):
            text += ';&nbsp;'

    text += '.'
    ctx_objects['lineC'] = ('', text)


def peers_summarize(trigger, learner, entry_point=None,
                         summaries=list(), ctx_objects=dict(), **kwargs):
    """
    We are filling in this template:

    {{peers_to_submitter_header}}
    <span class="indent">
    <ul>
        <li class="peers_to_you {0}" type="a">(a) {1}</li>
        <li class="peers_to_you {2}" type="a">(b) {3}</li>
        <li class="peers_to_you {4}" type="a">(c) {5}</li>
    </ul>
    """
    peers_back_to_submitter  = """
    <style>.peers_to_you{{list-style-type:None}}</style>

    {{{{peers_to_submitter_header}}}}
    <span class="indent">
    <ul>
        <li class="peers_to_you {0}" type="a">(a) {1}</li>
        <li class="peers_to_you {2}" type="a">(b) {3}</li>
        <li class="peers_to_you {4}" type="a">(c) {5}</li>
    </ul>
    </span>
    """.format(ctx_objects['lineA'][0], ctx_objects['lineA'][1],
               ctx_objects['lineB'][0], ctx_objects['lineB'][1],
               ctx_objects['lineC'][0], ctx_objects['lineC'][1],)

    trigger.template = peers_back_to_submitter
    ctx_objects['peers_back_to_submitter'] = render_template(trigger,
                                                             ctx_objects)


def invite_reviewers(trigger):
    """
    Invites reviewers to start the review process
    """
    num_peers = trigger.entry_point.settings('num_peers')
    valid_subs = Submission.objects.filter(trigger=trigger, is_valid=True).\
                                                            exclude(status='A')
    if not(valid_subs.count() >= \
            trigger.entry_point.settings('min_in_pool_before_grouping_starts')):
        return

    # We have enough Submissions instances for the current trigger:
    # it is time to start reviewing
    #
    # The number of Submissions should be equal to the nubmer of nodes in graph:
    graph = group_graph(trigger.entry_point)

    # This is not true anymore when we have groups submitting.
    valid_submissions = 0
    for sub in valid_subs:
        if sub.group_submitted:
            valid_submissions += len(is_group_submission(sub.submitted_by,
                                            trigger.entry_point).group_members)



    #if len(valid_subs) != graph.graph.order():
    #    logger.warn(('Number of valid subs [{0}] is not equal to graph '
    #            'order [{1}]'.format(len(valid_subs), graph.graph.order())))
    # Rather return; fix it up and then come back later
    #
    #    return

    for student in graph.graph.nodes():
        # These ``Persons`` have a valid submission. Invite them to review.
        # Has a reviewer been allocated this submission yet?
        allocated = ReviewReport.objects.filter(entry_point=trigger.entry_point,
                                                reviewer=student)

        if allocated.count() == num_peers:
            continue

        for idx in range(num_peers - allocated.count()):
            review = ReviewReport(entry_point=trigger.entry_point,
                                  trigger=trigger,
                                  reviewer=student)
            review.save()


# -------------------------------------------
# Functions related to the graph and grouping
# -------------------------------------------
class group_graph(object):
    """
    Creates the group graph.

    Rules:
    1. Nodes are ``Person`` instances.
    2. A node is added to the graph if, and only if, the person has submitted.
    3. Edges are directed. From a submitter, to a reviewer.
    4. An edge is only created if the reviewer has opened (therefore seen) the
       allocated review.
       A review is allocated in real time, when the reviewer wants to start.
    5. The edge contains a ``Submission`` instance.
    """
    def __init__(self, entry_point, trigger=None):

        groups = GroupConfig.objects.filter(entry_point=entry_point,
                                            trigger=trigger)

        # Added these two lines, so the graphs are always created randomly
        groups = list(groups)
        shuffle(groups)

        self.graph = nx.DiGraph()
        self.entry_point = entry_point
        for group in groups:
            reviewers = group.membership_set.filter(role='Review', fixed=True)
            submitters = group.membership_set.filter(role='Submit', fixed=True)
            for submitter in submitters:
                self.graph.add_node(submitter.learner)

            for reviewer in reviewers:
                self.graph.add_node(reviewer.learner)
                self.graph.add_edge(submitter.learner,
                                    reviewer.learner,
                                    weight=1)


    #def get_next_review(self, exclude=None):
        #"""
        #Given the graph, get the next reviewer.
        #"""
        #potential = list(self.graph.nodes())
        #if exclude:
            #index = potential.index(exclude)
            #potential.pop(index)

        #shuffle(potential)
        #in_degree = []
        #for idx, node in enumerate(potential):
            #in_degree.append((self.graph.in_degree(node), idx))

        #in_degree.sort()
        #next_one = in_degree.pop(0)

        #if next_one[0] <= num_peers:
            #return potential[next_one[1]]
        #else:
            #return None


    #def get_submitter_to_review_old(self, exclude_reviewer):
        #"""
        #Get the next submitter's work to review. You must specify the
        #reviewer's Person instance (``exclude_reviewer``), to ensure they are
        #excluded as a potential submission to evaluate.

        #Rules:
        #1. Arrows go FROM the submitter, and TO the reviewer.
        #2. Avoid an arrow back to the submitter
        #3. If unavoidable, go to the person with the least number of allocated
           #reviews (incoming arrows)
        #4. After that, assign randomly.

            #potential = list(self.graph.nodes())
            #if exclude_reviewer:
                #index = potential.index(exclude_reviewer)
                #potential.pop(index)

            ## Important to shuffle here, so the indices are randomized
            #shuffle(potential)

            ## tuple-order: (outdegree, indegree, node_index)
            #allocate = []
            #for idx, node in enumerate(potential):
                #allocate.append((self.graph.out_degree(node),
                                 #self.graph.in_degree(node),
                                 #idx))

            ## Even now when we sort, we are sorting on indices that have been
            ## randomly allocated
            #allocate.sort()

            #next_one = allocate.pop(0)
            #num_peers = trigger.entry_point.settings('num_peers')
            #while (next_one[0] <= num_peers) and (self.graph.has_edge(\
                    #potential[next_one[2]], exclude_reviewer)):
                #next_one = allocate.pop(0)

            #return potential[next_one[2]]

        #Revised version:

        #1. Arrows go FROM the submitter, and TO the reviewer.
        #2. Exclude/prevent the review from possibly happening a second time!!
        #2. Exclude nodes which are saturated: in = out = Nmax
        #2. Score the nodes as: deg(in) - deg(out). Therefore 0 is a balanced
           #node, and negative means that the node's work has gone out more
           #times than the person self has reviewed others.
        #3. Add small (+/- 0.1 amounts of random (normal distributed) noise to
           #the score.
        #4. Subtract (Nmax-0.5) from the score if the the current
           #``exclude_reviewer`` already has their work reviewed by the person.
           #This avoids a back-arrow, but doesn't make it impossible.
        #"""
        #potential = list(self.graph.nodes())
        #if exclude_reviewer:
            #index = potential.index(exclude_reviewer)
            #potential.pop(index)

        ## Important to shuffle here, so the indices are randomized
        #shuffle(potential)

        #scores = []  # of tuples: (score, node_index)
        #for idx, node in enumerate(potential):
            ## The learner (``exclude_reviewer``) has already reviewed ``node``
            #if self.graph.has_edge(node, exclude_reviewer):
                #continue

            #if self.graph.out_degree(node) >= \
                                         #self.entry_point.settings('num_peers'):
                ## We cannot over-review a node, so ensure its out degree is not
                ## too high. Keep working through the scores till you find one.
                #continue

            #bias = random.normalvariate(mu=0, sigma=0.1)
            #if self.graph.has_edge(exclude_reviewer, node):
                #bias = bias - (self.entry_point.settings('num_peers')-0.5)

            #score = self.graph.in_degree(node) \
                    #- self.graph.out_degree(node) \
                    #+ bias

            #scores.append((score, idx))

        ## Sort from low to high, and next we pop off the last value (highest)
        #scores.sort()
        #try:
            #next_one = scores.pop()
        #except IndexError:
            #logger.error(('No more nodes to pop out for next reviewer. '
                          #'learner={}\n----{}\n----{}').format(exclude_reviewer,
                                                             #self.graph.nodes(),
                                                             #self.graph.edges()
                                                            #))
            ## Only to prevent failure, but this is serious.
            #return None


        #return potential[next_one[1]]

    def get_submitter_for(self, reviewer):
        """
        The ``reviewer`` wants a submitter's document to review. How do we
        select that?
        Experiments show that we get the higher chance of a balanced digraph
        when purely random assignments are made, without hindering the reviewer.
        """

        # Assume we don't use groups
        potential = list(self.graph.nodes())

        # At this point we also want to ensure the ``reviewer`` only sees
        # reports from their own ``group``, or only reports outside the group.
        gfp = self.entry_point.gf_process
        reviewer_groups = reviewer.groupenrolled_set.filter(group__gfp=gfp)
        if reviewer_groups:
            reviewer_group = reviewer_groups[0].group

        if (self.entry_point.uses_groups and reviewer_groups.count()==0):
            logger.error(('Student {0} is NOT enrolled in a group while {1} '
                          'uses groups'.format(reviewer, gfp)))
            return None

        if self.entry_point.uses_groups:
            all_groups = gfp.group_set.all()
            superset = []

            # Exclude all other groups
            if self.entry_point.only_review_within_group:

                for enrollment in reviewer_group.groupenrolled_set.all():
                    superset.append(enrollment.person)


            # Or, exclude only people in the person's group, and make up the
            # potential set from the other groups
            else:
                for group in all_groups:
                    if group == reviewer_group:
                        continue
                    for enrollment in group.groupenrolled_set.all():
                        superset.append(enrollment.person)

                # End: going through all groups in this ``gfp``


            # Now we have a superset of potential reviewers. Find the
            # intersection of ``potential`` and ``superset`` (i.e. exclude from
            # ``superset`` the entries not in ``potential``):
            potential  = list(set(superset).intersection(potential))

        # End: if reducing the pool of potential reviewers due to grouping.

        if reviewer:
            try:
                index = potential.index(reviewer)
                potential.pop(index)
            except ValueError:
                pass

        # Shuffle here, so the indices are randomized
        shuffle(potential)

        runs = 0
        while potential:
            runs += 1

            node = potential.pop()
            if self.graph.has_edge(node, reviewer):
                # 2: already a connection.
                continue

            # Adding in the fact that edges cannot be reversed increases the
            # failure rate. TODO: avoid mirrored edges rather (it is too extreme
            #  to prevent mirrored edges)
            #elif self.graph.has_edge(reviewer, node):
            #    a=2


            if self.graph.out_degree(node) >= \
                                        self.entry_point.settings('num_peers'):

                # 3: We cannot over-review a node, so ensure its out degree is
                #    not too high. Keep working through the scores till you find
                #    one.
                continue

            else:
                return node

        return None

    def plot_graph(self):
        """
        Plots the graph for this entry point.

        43639/1931107264
        from basic.models import Course, EntryPoint
        orig_course = Course.objects.get(label='36957')
        orig_ep = EntryPoint.objects.get(course=orig_course, LTI_id='1475539468')
        from interactive.views import group_graph
        graph = group_graph(orig_ep)
        graph.plot_graph()

        """
        #import matplotlib.pyplot as plt
        #plt.figure(1,figsize=(8,8))
        #plt.clf()
        #pos = nx.circular_layout(self.graph)
        #nx.draw(self.graph,
                #pos = pos,
                #with_labels=True,
                #node_size=800,
                #node_color = 'lightgrey',
                #node_shape = 's',            #so^>v<dph8'.
                #edge_color = 'b',
                #style = 'solid',             # solid|dashed|dotted,dashdot
                #font_size = 16,
                #font_color= 'black',
                #)


        pass

    def graph_json(self, reports):
        serialized = json_graph.node_link_data(self.graph,
            attrs=dict(id='id', source='source', target='target', key='key'))
        for idx, node in enumerate(serialized['nodes']):
            node['title'] = node['id'].get_initials()

            if reports.get(node['id'], False):
                node['achieved'] = \
                          reports[node['id']].get('_highest_achievement',
                                                  'None')
                if node['id'].groupenrolled_set.all().count():
                    group_enrolled = node['id'].groupenrolled_set.all()[0]
                    node['groupid'] = group_enrolled.group.id
            else:
                node['achieved'] = 'NOT_FOUND'

            # Finally, re-write over the ID to avoid using actual names
            node['id'] = idx

        return serialized

def review(request, unique_code=None):
    """
    A review link (with ``unique_code``) is created the moment we have enough
    submitters to pool up. The link is created, and shown in the user-interface.
    When they visit that link, the review process starts:

    1/ Select a submission to attach this to, if not already attached.
    2/ prevent the document from being re-uploaded by submitter
    3/ prevent the document from being re-uploaded by submitter - another time
    4/ create rubric / Get the rubric (with prior filled in answers)
    5/ Return the rendered HTML to the reviewer.
    """
    reports = ReviewReport.objects.filter(unique_code=unique_code)
    if reports.count() != 1:
        logger.error('Incorrect review requested: {}'.format(unique_code))
        return HttpResponse(("You've used an incorrect link. Please check the "
                             'web address to ensure there was not a typing '
                             'error.<p>No peer review found with that link.'))

    report = reports[0]


    # 1. Select a submission to attach this to, if not already attached.
    if report.submission:
        # This is going to be called later by the handle_review function. Might
        # as well check that the user's rubric etc is correctly created.
        r_actual, reviewer = get_learner_details(report.unique_code)
        if reviewer is None:
            return r_actual
        else:
            return handle_review(request, unique_code)

    # 2. Can this still be completed?
    now_time = datetime.datetime.now(datetime.timezone.utc)

    #if now_time > report.trigger.deadline_dt:
    #    logger.warn(report.trigger)
    #    logger.warn('Late review to start: {}'.format(str(report)))
    #    return HttpResponse(("The deadline for this step has passed; you "
    #                         "cannot start/continue on anymore."))


    graph = group_graph(report.entry_point)
    submitter = graph.get_submitter_for(reviewer=report.reviewer)

    if submitter is None:
        logger.error('NO MORE SUBMITTERS FOR {}; entry point "{}". '.format(\
                                        report.reviewer,
                                        report.entry_point))
        return HttpResponse(('The number of available reviews is currently '
                             'ZERO. Please wait and return later to get a '
                             'review after one of your peers uploads. '))


    subs = report.trigger.submission_set.filter(entry_point=report.entry_point,
                                            is_valid=True).exclude(status='A')

    # The ``submitter``: are they part of a group? The ``submitter`` might not
    # have been the person that actually submitted, so look for a report
    # from that perons's group.
    group_enrolled_sub = is_group_submission(submitter, report.entry_point)
    if group_enrolled_sub:
        # At this point it means the user is part of a group, so if needed,
        # also filter by group submitted
        valid_subs = subs.filter(group_submitted=group_enrolled_sub.group)
    else:
        valid_subs = subs.filter(submitted_by=submitter)

        # Original filter:
        # (is_valid=True, entry_point=report.entry_point,
        # trigger=report.trigger, submitted_by=submitter).exclude(status='A')

    if valid_subs.count() != 1:
        logger.error(('Found more than 1 valid Submission for {} in entry '
                      'point "{}". Or a prior error occured'.format(valid_subs,
                                                   report.entry_point)))
        return HttpResponse(("You've used an incorrect link; or a problem with "
                             'the peer review system has occurred. Please '
                             'content k.g.dunn@tudelft.nl with the approximate '
                             'date and time that this occurred, and he can '
                             'try to assist you further.'))

    submission = valid_subs[0]
    report.submission = submission
    report.save()

    # 2. Prevent the document from being re-uploaded by submitter/submitting grp
    if group_enrolled_sub:
        for student in group_enrolled_sub.group_members:
            completed(student, 'work_has_started_to_be_reviewed',
                      report.entry_point)
    else:
        completed(report.submission.submitted_by,
                  'work_has_started_to_be_reviewed',
                  report.entry_point)


    # 3. Indicate that this person has started a review (not necessarily their
    #    group members)
    completed(report.reviewer, 'started_a_review', report.entry_point)

    # 3. Also prevent the learner/learner's group from resubmitting their report
    group_enrolled_review = is_group_submission(report.reviewer,
                                                report.entry_point)
    if group_enrolled_review:
        for student in group_enrolled_review.group_members:
            completed(student, 'work_has_started_to_be_reviewed',
                      report.entry_point)
    else:
        completed(report.reviewer, 'work_has_started_to_be_reviewed',
                          report.entry_point)

    # Update the Membership, which will update the graph.

    if report.grpconf is None: # which it also should be ...
        submitter_member = Membership.objects.get(learner=submitter,
                                                  role='Submit',
                                                  fixed=True,
                            group__entry_point=report.entry_point)

        new_membership, _ = Membership.objects.get_or_create(role='Review',
                                                             fixed=True,
                                            learner=report.reviewer,
                                            group=submitter_member.group)


        report.grpconf = new_membership.group
        report.save()


    # 4/ Create a RubricActual instance

    # Creates a new actual rubric for a given ``learner`` (the person
    # doing the) evaluation. It will be based on the parent template
    # defined in ``template``, and for the given ``submission`` (either
    # their own submission if it is a self-review, or another person's
    # submission for peer-review).

    get_create_actual_rubric(graded_by=report.reviewer,
                             trigger=report.trigger,
                             submission=submission,
                             rubric_code=unique_code)


    # 5/ Finally, return to the same point as if we were at the top of this func
    return handle_review(request, unique_code)


def evaluate(request, unique_code=None):
    """
    Generate the RubricActual from the template.

    """
    reports = EvaluationReport.objects.filter(unique_code=unique_code)
    if reports.count() != 1:
        logger.error('Incorrect Evaluation requested: {}'.format(unique_code))
        return HttpResponse(("You've used an incorrect link. Please check the "
                             'web address to ensure there was not a typing '
                             'error.<p>No evaluation found with that link.'))

    report = reports[0]


    # We have a report to be evaluated, now generate the links.
    if report.r_actual is None:
        # Generate the actual rubric here for it.
        eval_actual, _ = get_create_actual_rubric(graded_by=report.evaluator,
                                                trigger=report.trigger,
                                                submission=report.submission,
                                                rubric_code=report.unique_code)
        report.r_actual = eval_actual
        report.save()

    return handle_review(request, unique_code)


def see_evaluation(request, unique_code=None):
    """
    Shows the read-only evaluation to the peer reviewer (who originally
    reviewed the report, and has been evaluated by the original submitter).

    Set the r_actual to locked (to prevent the evaluator, i.e. the original
    submitter from changing anything further to the report)
    """

    # Note: we use the ``next_code`` field here, not the actual ``unique_code``
    #       field, since we want to first set the rubric to locked, so it
    #       shows as read-only.
    rubrics = RubricActual.objects.filter(next_code=unique_code)
    if rubrics.count() != 1:
        logger.error('Incorrect R/O eval requested: {}'.format(unique_code))
        return HttpResponse(("You've used an incorrect link. Please check the "
                             'web address to ensure there was not a typing '
                             'error.<p>No evaluation to see with that link.'))

    rubric = rubrics[0]
    rubric.status = 'L'
    rubric.save()

    # Now pass the rubric.rubric_code through, not the acquired unique_code.
    return handle_review(request, rubric.rubric_code)



def rebuttal(request, unique_code=None):
    """
    Generates the rebuttal rubric, if needed, and returns that to the process
    that handles display and processing of the rubric.
    """
    reports = EvaluationReport.objects.filter(unique_code=unique_code)
    if reports.count() != 1:
        error = True

        # Rebuttals are a special case for now. Try looking up the r_actual
        # with that same code instead.

        rubric = RubricActual.objects.filter(rubric_code=unique_code)
        if rubric.count() == 1:
            reports = rubric[0].evaluationreport_set.filter(sort_report='R',
                                            evaluator=rubric[0].graded_by)
            if reports:
                error = False

        if error:
            logger.error('Incorrect Rebuttal requested: {}'.format(unique_code))
            return HttpResponse(("You've used an incorrect link. Please check "
                             'the web address to ensure there was not a typing '
                             'error.<p>No rebuttal found with that link.'))

    report = reports[0]


    # We have a report to be evaluated, now generate the links.
    if report.r_actual is None:
        # Generate the actual rubric here for it.
        rebut_actual, _ = get_create_actual_rubric(graded_by=report.evaluator,
                                                trigger=report.trigger,
                                                submission=report.submission,
                                                rubric_code=report.unique_code)
        report.r_actual = rebut_actual
        report.r_actual.next_code = unique_code
        report.save()

    return handle_review(request, report.r_actual.rubric_code)


def assessment(request, unique_code=None):
    """
    Generates the assessment rubric, if needed, and returns that to the process
    that handles display and processing of the rubric.
    """
    reports = EvaluationReport.objects.filter(unique_code=unique_code)
    if reports.count() != 1:
        logger.error('Incorrect Assessment requested: {}'.format(unique_code))
        return HttpResponse(("You've used an incorrect link. Please check the "
                             'web address to ensure there was not a typing '
                             'error.<p>No assessment found with that link.'))

    report = reports[0]


    # We have a report to be evaluated, now generate the links.
    if report.r_actual is None:
        # Generate the actual rubric here for it.
        rebut_actual, _ = get_create_actual_rubric(graded_by=report.evaluator,
                                                trigger=report.trigger,
                                                submission=report.submission,
                                                rubric_code=report.unique_code)
        report.r_actual = rebut_actual
        report.save()


    # One final step: set the rebuttal rubric from which the assessment
    # is derived to locked.
    rebuttal_ract = RubricActual.objects.filter(rubric_code=report.prior_code)
    if rebuttal_ract:
        if rebuttal_ract[0].status == 'C':
            rebuttal_ract[0].status = 'L'
            rebuttal_ract[0].save()

    # Now pass this on to be
    return handle_review(request, report.r_actual.rubric_code)


def see_assessment(request, unique_code=None):
    """
    Shows the read-only assessment to the peer reviewer (who originally
    reviewed the report, and has been rebutted by the original submitter).

    Set the r_actual to locked (to prevent the evaluator, i.e. the original
    submitter from changing anything further to the report)
    """
    # Get the rubric and s it to locked, so it shows as read-only.
    reports = EvaluationReport.objects.filter(unique_code=unique_code)
    if reports.count() != 1:
        logger.error('Incorrect R/O Assessment request: {}'.format(unique_code))
        return HttpResponse(("You've used an incorrect link. Please check the "
                             'web address to ensure there was not a typing '
                             'error.<p>No assessment found with that link.'))

    report = reports[0]

    rubric = report.r_actual
    rubric.status = 'L'
    rubric.save()

    # Now pass the rubric.rubric_code through, not the acquired unique_code.
    return handle_review(request, rubric.rubric_code)


# -------------------------------------------
# Utility function: to handle the generation of a ``Submission`` for a
# report evaluation.
# -------------------------------------------
def reportlab_styles():
    """
    Format the review with these styles.
    """
    styles= {
        'default': ParagraphStyle('default',
            fontName='Helvetica',
            fontSize=9,
            leading=12,
            leftIndent=0,
            rightIndent=0,
            firstLineIndent=0,
            alignment=TA_LEFT,
            spaceBefore=0,
            spaceAfter=0,
            bulletFontName='Arial',
            bulletFontSize=10,
            bulletIndent=0,
            textColor=black,
            backColor=None,
            wordWrap=None,
            borderWidth= 0,
            borderPadding= 0,
            borderColor= None,
            borderRadius= None,
            allowWidows= 1,
            allowOrphans= 0,
            textTransform=None,  # 'uppercase' | 'lowercase' | None
            endDots=None,
            splitLongWords=1,
        )
    }
    styles['title'] = ParagraphStyle('title',
        parent=styles['default'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=42,
        alignment=TA_CENTER,
        textColor=black,
    )
    styles['header'] = ParagraphStyle('header',
        parent=styles['default'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        alignment=TA_LEFT,
        textColor=black,
    )
    styles['list_default'] = ListStyle('list_default',
        leftIndent=18,
        rightIndent=0,
        spaceBefore=0,
        #spaceAfter=0,
        bulletAlign='left',
        bulletType='1',
        bulletColor=darkblue,
        bulletFontName='Helvetica',
        bulletFontSize=10,
        bulletOffsetY=0,
        bulletDedent='auto',
        bulletDir='ltr',
    )
    styles['warning'] = ParagraphStyle('warning',
        parent=styles['default'],
        textColor=darkred,
    )
    return styles

styles = reportlab_styles()
default = styles['default']
# all margins are 1.5cm on A4 paper
default_frame = Frame(1.5*cm, 1.5*cm, A4[0]-3.0*cm, A4[1]-3.0*cm, id=None)

def report_render_rubric(r_actual, flowables):
    """
    Continues the rendering of the body of the report, using the rubric
    ``r_actual``, and the supplied list of flowables which are appended to.
    """
    styles = reportlab_styles()
    review_items, _ = r_actual.report()


    flowables.append(Paragraph('Any graded value of "8" in the report below is '
            'actually scored as 8.5 in the grading.', styles['warning']))
    flowables.append(Spacer(1, 2))
    for item in review_items:

        flowables.append(Paragraph(item.ritem_template.criterion,
                                   styles['header']))
        flowables.append(Spacer(1, 3))

        # A single option is not put into a list, it is likely a text box.
        if len(item.options) == 1:
            # if item.options[0].rubric_item.option_type
            text = item.options[0].prior_text
            flowables.append(Paragraph(text.replace('\n','<br />\n'), default))

        else:
            for idx, option in enumerate(item.options):
                out = []
                leftIndent = 18
                firstLineIndent = 10
                if hasattr(option, 'selected'):
                    leftIndent = 10
                    firstLineIndent = 0
                    if option.criterion:
                        out.append(Paragraph(('&larr; <strong>{0}</strong>'
                                        '').format(option.criterion), default))
                    else:
                        out.append(Paragraph(('&larr; <strong><em>This in-between '
                        'option was selected for a score of {} points'
                        '</em></strong>').format(option.score).replace('.0', ''),
                                             default))
                else:
                    if option.criterion:
                        out.append(Paragraph('<font color="grey">{0}</font>'.\
                                            format(option.criterion), default))

                flowables.append(ListFlowable(out,
                            start='{:}'.format(int(option.score)),
                            leftIndent=leftIndent,
                            firstLineIndent=firstLineIndent,
                            style=styles['list_default'],))


        flowables.append(Spacer(1, 6))



def create_evaluation_PDF(r_actual):
    """
    Take an original submission (PDF), and combines an extra page or two,
    that contains a SINGLE review (``r_actual``).
    """
    report = ReviewReport.objects.get(unique_code=r_actual.rubric_code)
    load_kwargs(report.trigger)
    try:
        show_review_numbers = report.trigger.show_review_numbers
    except AttributeError:
        show_review_numbers = True

    try:
        custom_review_header = report.trigger.custom_review_header
    except AttributeError:
        custom_review_header = None


    # From the perspective of the submitter, which peer am I?
    rubrics = RubricActual.objects.filter(submission=report.submission)\
                                                            .order_by('created')
    peer_number = 64
    for idx, rubric in enumerate(rubrics):
        if report.reviewer == rubric.graded_by:
            peer_number += 1
            break

    base_dir_for_file_uploads = settings.MEDIA_ROOT
    token = generate_random_token(token_length=16)
    src = r_actual.submission.file_upload.file.name
    filename = 'uploads/{0}/{1}'.format(
                            r_actual.rubric_template.entry_point.id,
                            token + '.pdf')
    dst = base_dir_for_file_uploads + filename

    flowables = []
    if show_review_numbers:
        flowables.append(Paragraph("Review from peer number {}".format(\
                                         chr(peer_number)), styles['title']))
    elif custom_review_header:
        flowables.append(Paragraph(custom_review_header, styles['title']))
    else:
        flowables.append(Paragraph("Review from a peer", styles['title']))

    flowables.append(Spacer(1, 6))
    flowables.append(Paragraph(("The option in bold represents the one selected"
                                " by your reviewer."), default))
    flowables.append(Spacer(1, 6))

    report_render_rubric(r_actual, flowables)

    fd, temp_file = tempfile.mkstemp(suffix='.pdf')
    doc = BaseDocTemplate(temp_file)
    doc.addPageTemplates([PageTemplate( frames=[default_frame,]),])
    doc.build(flowables)
    os.close(fd)

    # Append the extra PDF page:
    pdf1 = PdfFileReader(src)
    pdf2 = PdfFileReader(temp_file)
    merger = PdfFileMerger(strict=False, )
    merger.append(pdf2, import_bookmarks=False) # 30 nov 2017: switch around
    merger.append(pdf1, import_bookmarks=False)
    merger.addMetadata({'/Title': '',
                        '/Author': '',
                        '/Creator': '',
                        '/Producer': ''})
    merger.write(dst)
    merger.close()

    # Cleaning up ``pdf2``
    os.remove(temp_file)

    with open(dst, "rb") as out_file:
        django_file = File(out_file)

        # Key point: use the ``submitted_file_name`` field to check if
        # this is a re-review (i.e. then we reuse the Submission instance).
        new_sub, was_new = Submission.objects.get_or_create(status='A',
                            entry_point=r_actual.rubric_template.entry_point,
                            trigger=r_actual.rubric_template.next_trigger,
                            is_valid=True,
                            submitted_by=r_actual.graded_by,
                            submitted_file_name = r_actual.rubric_code
                        )

        new_sub.file_upload = django_file
        new_sub.save()

    # The ``dst`` is not needed once we have saved the instance.
    os.unlink(dst)

    learner = r_actual.submission.submitted_by
    entry_point = r_actual.rubric_template.entry_point
    group_enrolled = is_group_submission(learner, entry_point)
    learner_s = [r_actual.submission.submitted_by,]
    if group_enrolled:
        learner_s.extend(group_enrolled.group_members)
        learner_s = list(set(learner_s))

        for student in learner_s:

            # DELETE ANY PRIOR ATTEMPTS FOR THIS trigger/submitted_by combination.
            prior_evals = EvaluationReport.objects.filter(
                                    trigger=r_actual.rubric_template.next_trigger,
                                    peer_reviewer=r_actual.graded_by,
                                    sort_report='E',
                                    evaluator=student,  # <-- key part
                                )
            prior_evals.delete()

    # Now we create here the link between the EvaluationReport
    # and the original submission's review (r_actual.next_code).
    # They both use the same token.
    # Note: the token is only seen by the submitter (the person whose work
    #       was reviewed.)
    r_actual.next_code = token
    r_actual.save()

    prior_token = token

    for student in learner_s:
        if student == r_actual.submission.submitted_by:
            token = prior_token
        else:
            token = generate_random_token(token_length=16)

        review_back_to_submitter = EvaluationReport(
            submission=new_sub,
            trigger=r_actual.rubric_template.next_trigger,
            unique_code=token,
            sort_report='E',
            peer_reviewer=r_actual.graded_by,
            evaluator=student,
        )
        review_back_to_submitter.save()

def create_rebuttal_PDF(r_actual):
    """
    Take an original submission (PDF), and combines an extra page or two,
    that contains the N review (``r_actual``) from the N peers. Not just 1 peer.


    """
    learner = r_actual.graded_by
    report = EvaluationReport.objects.get(unique_code=r_actual.rubric_code)

    submission = Submission.objects.filter(submitted_by=report.evaluator,
                                    entry_point=report.submission.entry_point,
                                    is_valid=True).exclude(status='A')
    submission = submission[0]

    rubrics = RubricActual.objects.filter(submission=submission).order_by('created')

    src = submission.file_upload.file.name

    flowables = []
    for idx, rubric in enumerate(rubrics):
        review_items, _ = rubric.report()
        flowables.append(Paragraph("Review from peer number {}".format(\
                                chr(idx+65)), styles['title']))
        flowables.append(Spacer(1, 6))
        flowables.append(Paragraph(("The option in bold represents the one "
                                    "selected by the reviewer."), default))
        flowables.append(Spacer(1, 6))

        report_render_rubric(rubric, flowables)

        flowables.append(PageBreak())

        # While we are here, also set the ``evaluated`` date/time on the rubric
        # but only on the rubric that we are currently evaluating
        if rubric.graded_by == report.peer_reviewer:
            #rubric.evaluated = timezone.now()
            #rubric.save()
            # The evaluation date/time belongs with the rubric attached to
            # the EvaluationReport (when was the evaluation completed by the
            # submitter; not the rubric.evaluated, since that was submitted
            # by the reviewer)
            report.r_actual.evaluated = timezone.now()
            report.r_actual.save()

    n_evaluations = RubricActual.objects.filter(graded_by=r_actual.graded_by,
                            rubric_template=r_actual.rubric_template).count()

    # This strange construction is to allow manual overrides:
    # 1. Prior to this the admin has likely set the Achievement of the learner
    #    for 'all_reviews_from_peers_completed' to True
    # 2. Then the admin has set 'read_and_evaluated_all_reviews' to True.
    # Once both those are in place, and the admin visits this link for the
    # Evaluation, the system will continue here and generate the PDF document
    # for the rebuttal step.
    if (n_evaluations < report.submission.entry_point.settings('num_peers')) \
                and not(has(learner, 'read_and_evaluated_all_reviews',
                            r_actual.rubric_template.trigger.entry_point)):
        return


    # Only continue to generate this report if it is the last review
    completed(learner,
              'read_and_evaluated_all_reviews',
              r_actual.rubric_template.trigger.entry_point)


    fd, temp_file = tempfile.mkstemp(suffix='.pdf')
    doc = BaseDocTemplate(temp_file)
    doc.addPageTemplates([PageTemplate( frames=[default_frame,]),])
    doc.build(flowables)
    os.close(fd)


    # Append the extra PDF page:
    pdf1 = PdfFileReader(src)
    pdf2 = PdfFileReader(temp_file)
    merger = PdfFileMerger(strict=False, )
    merger.append(pdf2, import_bookmarks=False)  # 30 nov 2017: switched around
    merger.append(pdf1, import_bookmarks=False)
    merger.addMetadata({'/Title': '',
                        '/Author': '',
                        '/Creator': '',
                        '/Producer': ''})
    fd, dst_file = tempfile.mkstemp(suffix='.pdf')

    merger.write(dst_file)
    merger.close()

    # Cleaning up ``pdf2``
    os.remove(temp_file)

    with open(dst_file, "rb") as out_file:
        django_file = File(out_file)

        # Key point: use the ``submitted_file_name`` field to check if
        # this is a re-review (i.e. then we reuse the Submission instance).
        new_sub, was_new = Submission.objects.get_or_create(\
                            status='A',
                            entry_point=r_actual.rubric_template.entry_point,
                            trigger=r_actual.rubric_template.next_trigger,
                            is_valid=True,
                            submitted_by=learner,

                            # This fields can be left out, but we add something
                            # here for display, to emphasize it is a merger
                            # of reviews from N different peers.
                            submitted_file_name = 'Merged reviews from eval'
                        )

        new_sub.file_upload = django_file
        new_sub.save()

    # The ``dst_file`` is not needed once we have saved the instance.
    os.unlink(dst_file)

    # UPDATE any prior EvaluationReport
    prior_eval, _ = EvaluationReport.objects.get_or_create(
                            trigger=r_actual.rubric_template.next_trigger,
                            sort_report='R',
                            evaluator=learner
                        )

    token = new_sub.file_upload.name.split('/')[2].strip('.pdf')
    prior_eval.unique_code = token
    prior_eval.submission = new_sub
    prior_eval.save()

def create_assessment_PDF(r_actual):
    """
    Take an rebuttal PDF (from the submitter) and attaches another section
    containing the rebuttal.

    """
    learner = r_actual.graded_by

    flowables = []
    review_items, _ = r_actual.report()
    flowables.append(Paragraph("Rebuttal", styles['title']))
    flowables.append(Spacer(1, 6))
    flowables.append(Paragraph(("The rebuttal is a point-by-point response to "
                                "reviewer' comments. This single rebuttal text"
                                " is sent to all reviewers, so not all comments"
                                " might apply to you."), default))
    flowables.append(Paragraph(("The original submission, with all peer reviews"
                                " is attached below. Scroll down to see them."),
                               default))

    flowables.append(Spacer(1, 6))
    report_render_rubric(r_actual, flowables)
    flowables.append(PageBreak())

    # This marks the point where the learner has completed their rebuttal
    completed(learner, 'completed_rebuttal',
              r_actual.rubric_template.entry_point)


    fd, temp_file = tempfile.mkstemp(suffix='.pdf')
    doc = BaseDocTemplate(temp_file)
    doc.addPageTemplates([PageTemplate( frames=[default_frame,]),])
    doc.build(flowables)
    os.close(fd)

    # Append the extra PDF page:
    pdf1 = PdfFileReader(r_actual.submission.file_upload.file.name)
    pdf2 = PdfFileReader(temp_file)
    merger = PdfFileMerger(strict=False, )

    # NOTE: we want the rebuttal on the top, the document afterwards.
    merger.append(pdf2, import_bookmarks=False)
    merger.append(pdf1, import_bookmarks=False)
    merger.addMetadata({'/Title': '',
                        '/Author': '',
                        '/Creator': '',
                        '/Producer': ''})
    fd, dst_file = tempfile.mkstemp(suffix='.pdf')

    merger.write(dst_file)
    merger.close()

    # Cleaning up ``pdf2``
    os.remove(temp_file)

    with open(dst_file, "rb") as out_file:
        django_file = File(out_file)

        # Key point: use the ``submitted_file_name`` field to check if
        # this is a re-review (i.e. then we reuse the Submission instance).
        new_sub, was_new = Submission.objects.get_or_create(\
                            status='A',
                            entry_point=r_actual.rubric_template.entry_point,
                            trigger=r_actual.rubric_template.next_trigger,
                            is_valid=True,
                            submitted_by=learner,

                            # This fields can be left out, but we add something
                            # here for display, to emphasize it is a rebuttal.
                            submitted_file_name = 'Rebuttal from submitter'
        )
        new_sub.file_upload = django_file
        new_sub.save()

    # The ``dst_file`` is not needed once we have saved the instance.
    os.unlink(dst_file)

    # UPDATE any prior EvaluationReport
    # Create an assessment report, one for each peer

    # Who are the learner's peers at this point?
    my_group = Membership.objects.get(role='Submit',
                                          learner=learner,
                                          group__entry_point=r_actual.rubric_template.entry_point)

    my_peers = Membership.objects.filter(role='Review',
                                             group=my_group.group).order_by('created')


    for peer in my_peers:


        prior_assess, _ = EvaluationReport.objects.get_or_create(
                                trigger=r_actual.rubric_template.next_trigger,
                                sort_report='A',
                                evaluator=learner,
                                peer_reviewer=peer.learner,
        )

        # DO NOT assign the unique_code. Let it be automatically created when
        # the .save() function is called. We want different codes for the
        # different peers, so we get N_peers distinct assessments.
        #prior_assess.unique_code = token

        # But, we definitely want linkage back to the rebuttal rubric, so
        # store that in the EvaluationReport
        prior_assess.prior_code = r_actual.rubric_code
        prior_assess.submission = new_sub
        prior_assess.save()


    # At this point you should async email the peers:
    #
    #


#---------
def has(learner, achievement, entry_point, detailed=False):
    """
    See if a user has completed a certain ``achievement``.

    If ``achievement`` is an AchieveConfig instance, it will extract the
    achievement text, and use that.

    Functions related to the learner's progress (achievements)

    Achievement                       Description
    -----------                       -----------
    submitted	                      Has submitted a document

    work_has_started_to_be_reviewed	  This submitter's work has already
                                      started to be reviewed. No further
                                      changes can be accepted.

    all_reviews_from_peers_completed  All the reviews from the learner's peers
                                      are completed now.

    started_a_review	              The learner has started with a review
                                      (at least one).

    completed_all_reviews	          Completed all required reviews of peers.

    read_and_evaluated_all_reviews	  Learner has evaluated all the reviews he
                                      has received.

    viewed_all_evaluations	          Learner has seen his N evaluations

    completed_rebuttal	              Learner has completed the rebuttal back
                                      to his peers.

    read_all_rebuttals	              Learner has read all the rebuttals
                                      received back.

    assessed_rebuttals	              Learner has assessed all the rebuttals.

    seen_all_assessments	          Has seen all assessments of the rebuttals.

    completed	                      Completed the entire process.
"""

    if isinstance(achievement, AchieveConfig):
        achievement = achievement.name
    possible = Achievement.objects.filter(learner=learner,
                                          achieved__name=achievement,
                                          achieved__entry_point=entry_point)
    if possible.count() == 0:
        return False
    else:
        if detailed:
            return possible[0]
        else:
            return possible[0].done


def completed(learner, achievement, entry_point, display='', grade=None):
    """
    Complete this item for the learner's achievement.

    Note: grades are only pushed to the DB once, the first time the status
          changes for field ``.done``.

          However, if you use ``score_override``, it will always write the
          value you provide in ``score_override`` to the gradebook.
    """
    possible = Achievement.objects.filter(learner=learner,
                                          achieved__name=achievement,
                                          achieved__entry_point=entry_point)
    if possible.count() == 0:
        try:
            achieve_config = AchieveConfig.objects.get(name=achievement,
                                                   entry_point=entry_point)
        except AchieveConfig.DoesNotExist:
            # This is for system admins who might forget to create
            # AchieveConfig instances for an entry_point
            logger.error(('CRITICAL: create this achievement "{0}" for '
                          'entry_point: {1}').format(achievement,
                                                     entry_point))
            assert(False)

        completed = Achievement(learner=learner,
                                achieved=achieve_config)
    else:
        completed = possible[0]


    # Update the achievement on second/subsequent calls,
    # as we might want to record a different `display`, or a newer date/time
    completed.done = True
    completed.display = display

    # We don't check the values here, assuming it is a reasonable grade
    # since it can be used for purposed where the value is between 0 and 10,
    # or 0 and 100, or sometimes even -3 to +3.
    if grade is not None:
        completed.grade = grade
    completed.save()


# Do not change function name: called from the database with this name.
def overview(request, course=None, learner=None, entry_point=None):
    """
    Student gets an overview of their grade here.
    We use all ``entry_points`` related to a course, except this entry point.
    """
    def reportcard(learner, entry_point):
        """
        Get the "reportcard" (a dictionary) of the learner's achievements
        """
        report = OrderedDict()
        for item in AchieveConfig.objects.filter(entry_point=entry_point)\
                                                          .order_by('score'):
            report[item.name] = has(learner, item.name, entry_point,
                                    detailed=True)
            if not(report[item.name]):  # they haven't done it
                # Store the ``achieveconfig`` instance, because we will
                # want to access the deadline
                item.done = False         # add a fake field to the instance
                report[item.name] = item
        return report




    entries = EntryPoint.objects.filter(course=course).order_by('order')
    achieved = {}
    entry_display = []

    # For admins (NOT USED)
    if learner.role in ('Admin', ):
        graphs = []
        for entry in entries:
            graphs.append(group_graph(entry).graph)

    num_completed = 0
    total_entries = 0
    for entry in entries:
        if entry == entry_point:
            continue
        else:
            total_entries += 1

        achieved[entry] = reportcard(learner, entry)
        entry_display.append(entry)

        if achieved[entry].get('assessed_rebuttals').done:
            num_completed += 1


    # Show a special extra image if the user has `all_completed`
    all_completed = False
    if total_entries == num_completed and total_entries != 0:
        all_completed = True

    ctx = {'learner': learner,
           'course': course,
           'achieved': achieved,
           'entry_display': entry_display,
           'entry_point': entry_point,
           'all_completed': all_completed}

    html = loader.render_to_string('interactive/display_progress.html', ctx)
    return HttpResponse(html)


def format_text_overview(r_actual, text, total, url=''):
    """
    Formats text for the learner overview
    """
    if r_actual is None: # It has not been started yet
        return text, total
    else:
        if r_actual.status in ('C', 'L'):
            score = int(r_actual.score)
            return '{0}<a href="{1}" target="_blank">{2:+d}</a> '.format(text,
                     url+r_actual.rubric_code, score), total+score

        else:
            return text, total



def overview_learners(entry_point, admin=None):
    """
    Provides an overview to the instructor of what is going on
    """
    class Display_Text(object):
        """ A simply class so we can object.display and object.sortorder
            instances of this class in a table.
        """
        def __init__(self, display='', sortorder=0):
            self.display = display
            self.sortorder = sortorder

        def __str__(self):
            return self.display

        def format_text(self, r_actual, url=''):
            if r_actual:
                # Only formatted if r_actual exists, and if completed or locked
                if r_actual.status in ('C', 'L'):
                    score = int(report.r_actual.score)
                    self.display += ('<a href="{0}" target="_blank">{1:+d}'
                                     '</a> ').format(\
                                    url+report.r_actual.rubric_code, score)
                    self.sortorder += score

    ctx = {}
    # Not the most robust way to group students; will fall apart if a student
    # uses this system in more than 1 course
    learners = entry_point.course.person_set.filter(role='Learn',
                                    is_validated=True).order_by('-created')
    reports = {}
    filters = ('submitted',
               'completed_all_reviews',
               'read_and_evaluated_all_reviews',
               'completed_rebuttal',
               'assessed_rebuttals')

    for learner in learners:
        # Note: you get an OrderedDict back from `filtered_overview`.
        #       the order is important, since the table overview will
        #       be rendered column-for-column in this order.
        reports[learner], highest_achievement = filtered_overview(learner,
                                                                  entry_point,
                                                                  filters)

        # ---- Submissions
        if isinstance(reports[learner]['submitted'], Achievement):
            sub = learner.submission_set.filter(is_valid=True,
                                entry_point=entry_point).exclude(status='A')
            if sub:
                reports[learner]['submitted'].hyperlink = '/{}'.format(\
                                                        sub[0].file_upload.url)

        # ---- Reviewed by ...
        slink = Display_Text(display='<tt>')
        wtext = Display_Text(display='<tt>')
        learner_group = learner.membership_set.filter(role='Submit',
                                                group__entry_point=entry_point)
        if learner_group:
            members = learner_group[0].group.membership_set.filter\
                    (role='Review')
            for member in members:
                report = ReviewReport.objects.filter(reviewer=member.learner,
                                            entry_point=entry_point,
                                            submission__submitted_by=learner)

                code = ''
                if report:
                    rubric = RubricActual.objects.get(\
                            rubric_code=report[0].unique_code)
                    code = report[0].unique_code

                initials = member.learner.get_initials()
                if code:
                    slink.display += (' <a href="/interactive/review/{0}" '
                                     'target="_blank">{1}</a> [{2:3.1f}]<br>')\
                                                      .format(code, initials,
                        rubric.score/rubric.rubric_template.maximum_score*10,)
                    slink.sortorder += rubric.score

                    wtext.display += '{0:4d}<br>'.format(rubric.word_count)
                    wtext.sortorder += rubric.word_count
                else:
                    slink.display += ' {}<br>'.format(initials)


        slink.display = slink.display[0:-4] + '</tt>'
        wtext.display = wtext.display[0:-4] + '</tt>'
        reports[learner]['reviewed_by_score'] = slink
        reports[learner]['reviewed_by_words'] = wtext

        # ---- Reviewer of ...
        slink = Display_Text(display='<tt>')
        wtext = Display_Text(display='<tt>')

        reviewer_of = learner.reviewreport_set.filter(entry_point=entry_point)
        for review in reviewer_of:

            code = review.unique_code
            ractual = RubricActual.objects.filter(rubric_code=code)
            if ractual.count() == 0:
                logger.error('MISSING REVIEW: {}'.format(code))
                continue
            else:
                ractual = ractual[0]

            initials = ractual.submission.submitted_by.get_initials()
            slink.display += (' <a href="/interactive/review/{0}" '
                              'target="_blank">{1}</a> [{2:3.1f}]<br>').\
                format(code, initials,
                       ractual.score/ractual.rubric_template.maximum_score*10)
            slink.sortorder += ractual.score

            wtext.display += '{0:4d}<br>'.format(ractual.word_count)
            wtext.sortorder += ractual.word_count


        slink.display = slink.display[0:-4] + '</tt>'
        wtext.display = wtext.display[0:-4] + '</tt>'
        reports[learner]['reviewer_of_score'] = slink
        reports[learner]['reviewer_of_words'] = wtext

        # ---- Evaluations: earned and given
        earned = learner.peer_reviewer.filter(trigger__entry_point=entry_point,
                                              sort_report='E')
        earn_text = Display_Text()
        for report in earned:
            earn_text.format_text(report.r_actual, url='/interactive/evaluate/')

        if not(earn_text.display):
            earn_text.display = ''
        else:
            earn_text.display = '<tt>{0}= <b>{1:+d}</b></tt>'.format(\
                earn_text.display, int(earn_text.sortorder))


        given = learner.evaluator.filter(trigger__entry_point=entry_point,
                                         sort_report='E')
        give_text = Display_Text()
        for report in given:
            give_text.format_text(report.r_actual, url='/interactive/evaluate/')

        if not(give_text.display):
            give_text.display = ''
        else:
            give_text.display = '<tt>{0}= <b>{1:+d}</b></tt>'.format(\
                give_text.display, int(give_text.sortorder))

        reports[learner]['read_and_evaluated_all_reviews_earn'] = earn_text
        reports[learner]['read_and_evaluated_all_reviews_gave'] = give_text

        # ---- Rebuttals
        if reports[learner]['completed_rebuttal']:
            rebuttals = learner.evaluator.filter(sort_report='R',
                                             trigger__entry_point=entry_point)
            hyperlink = ''         # Sometimes we have manually overridden the
                                   # achievement of `completed_rebuttal`, but no
                                   # actual rebuttal exists. So make the
                                   # hyperlink is empty.
            if rebuttals.count()==1:
                hyperlink = '/interactive/rebuttal/{0}'.format(
                        rebuttals[0].r_actual.rubric_code)

            reports[learner]['completed_rebuttal'].hyperlink = hyperlink

        # ---- Assessments: earned and given
        earned = learner.evaluator.filter(trigger__entry_point=entry_point,
                                              sort_report='A')
        earn_text = Display_Text()
        for report in earned:
            earn_text.format_text(report.r_actual,
                                  url='/interactive/assessment/')

        if not(earn_text.display):
            earn_text.display = ''
        else:
            earn_text.display = '<tt>{0}= <b>{1:+d}</b></tt>'.format(\
                earn_text.display, int(earn_text.sortorder))

        given = learner.peer_reviewer.filter(trigger__entry_point=entry_point,
                                        sort_report='A')
        give_text = Display_Text()
        for report in given:
            give_text.format_text(report.r_actual, url='/interactive/assessment/')

        if not(give_text.display):
            give_text.display = ''
        else:
            give_text.display = '<tt>{0}= <b>{1:+d}</b></tt>'.format(\
                give_text.display, int(give_text.sortorder))

        reports[learner]['assessed_rebuttals_earn'] = earn_text
        reports[learner]['assessed_rebuttals_gave'] = give_text

        # Used by the D3.js animation
        reports[learner]['_highest_achievement'] = highest_achievement

        order = ['submitted',
                 'reviewed_by_score',
                 'reviewed_by_words',
                 'reviewer_of_score',
                 'reviewer_of_words',
                 'completed_all_reviews',
                 'read_and_evaluated_all_reviews_earn',
                 'read_and_evaluated_all_reviews_gave',
                 'completed_rebuttal',
                 'assessed_rebuttals_earn',
                 'assessed_rebuttals_gave',
                 '_highest_achievement']

        new_dict = OrderedDict()
        for i in order:
            new_dict[i] = reports[learner][i]

        reports[learner] = new_dict


    ctx['learners'] = learners
    ctx['graph'] = group_graph(entry_point).graph_json(reports)
    ctx['reports'] = reports
    global_summary = entry_point.course.entrypoint_set.filter(order=0)
    if global_summary:
        ctx['global_summary_link'] = global_summary[0].full_URL

    return loader.render_to_string('interactive/learner_overview.html', ctx)


def filtered_overview(learner, entry_point, filters):
    """
    Takes the report card and adds supplemental information to it for the
    learner. Also returns the highest achievement found in the input
    list/set of ``filters``.
    """
    report = OrderedDict()
    highest_achievement = ''
    for name in filters:
        item = AchieveConfig.objects.get(entry_point=entry_point, name=name)
        report[item.name] = has(learner, item.name, entry_point, detailed=True)
        if report[item.name]:
            highest_achievement = name

    return report, highest_achievement



def csv_summary_download(request):
    """
    Returns a CSV download of the student names and scores.
    """
    from basic.views import get_course_ep_info
    info = get_course_ep_info(request)
    if info['learner'].role != 'Admin':
        return HttpResponse('')

    entry_point = info['entry_point']
    fname = slugify('{}-{}-{}'.format(entry_point.course,
                                      entry_point.LTI_id,
                         timezone.now().strftime('%Y-%m-%d-%H-%M'))) + '.csv'



    learners = entry_point.course.person_set.filter(role='Learn',
                                        is_validated=True).order_by('-created')

    # Create the HttpResponse object with the appropriate CSV header.
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="{}"'.format(fname)

    writer = csv.writer(response)
    writer.writerow(['Learner',
                     'Email',
                     'Deliverable',
                     'EvaluationsEarn',
                     'EvaluationsGave',
                     'RebuttalDone',
                     'AssessmentEarn',
                     'AssessmentGave'])

    # Columns: EvaluationsEarn, EvaluationsGave, RebuttalDone,  AssessmentEarn,
    #          AssessmentGave
    for learner in learners:

        # ---- Evaluations: earned and given
        earned = learner.peer_reviewer.filter(trigger__entry_point=entry_point,
                                              sort_report='E')
        total_eval_earn = 'NotDone'
        for report in earned:
            if report.r_actual is None: # It has not been started yet
                continue
            else:
                if report.r_actual.status in ('C', 'L'):
                    try:
                        total_eval_earn += report.r_actual.score
                    except TypeError:
                        total_eval_earn = report.r_actual.score


        given = learner.evaluator.filter(trigger__entry_point=entry_point,
                                         sort_report='E')
        total_eval_gave = 'NotDone'
        for report in given:
            if report.r_actual is None: # It has not been started yet
                continue
            else:
                if report.r_actual.status in ('C', 'L'):
                    try:
                        total_eval_gave += report.r_actual.score
                    except TypeError:
                        total_eval_gave = report.r_actual.score

        # Rebuttal
        rebuttal_completed = '-'
        rebuttals = learner.evaluator.filter(sort_report='R',
                                             trigger__entry_point=entry_point)
        if rebuttals.count()==1:
            if rebuttals[0].r_actual:
                rebuttal_completed = rebuttals[0].r_actual.completed.strftime('%Y-%m-%d %H:%S')
            else:
                a = 4


        # ---- Assessments: earned and given
        earned = learner.evaluator.filter(trigger__entry_point=entry_point,
                                              sort_report='A')
        total_assess_earn = 'NotDone'
        for report in earned:
            if report.r_actual is None: # It has not been started yet
                continue
            else:
                if report.r_actual.status in ('C', 'L'):
                    try:
                        total_assess_earn += report.r_actual.score
                    except TypeError:
                        total_assess_earn = report.r_actual.score


        given = learner.peer_reviewer.filter(trigger__entry_point=entry_point,
                                         sort_report='A')
        total_assess_gave = 'NotDone'
        for report in given:
            if report.r_actual is None: # It has not been started yet
                continue
            else:
                if report.r_actual.status in ('C', 'L'):
                    try:
                        total_assess_gave += report.r_actual.score
                    except TypeError:
                        total_assess_gave = report.r_actual.score


        # All finished for this student
        writer.writerow([learner.display_name,
                         learner.email,
                         entry_point.LTI_title,
                         total_eval_earn,
                         total_eval_gave,
                         rebuttal_completed,
                         total_assess_earn,
                         total_assess_gave])

    return response


