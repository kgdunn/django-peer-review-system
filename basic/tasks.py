"""
Tasks which are called at different schedules. Write the functions here.
These are functions (in this file) which are run on a periodic basis.
Each function should do its own imports. Do not have imports up here at the top
of the function.

Add the scheduled task in ``admin.py``.

For example:

schedule('math.hypot',
         3, 4,                              <---- these are the inputs
         schedule_type=Schedule.MINUTES,
         minutes=5,
         repeats=24,
         next_run=arrow.utcnow().replace(hour=18, minute=0))

Schedule.ONCE = 'O'
Schedule.MINUTES = 'I'
Schedule.HOURLY = 'H'
Schedule.DAILY = 'D'
Schedule.WEEKLY = 'W'
Schedule.MONTHLY = 'M'
Schedule.QUARTERLY = 'Q'
Schedule.YEARLY = 'Y'
"""
import logging
logger = logging.getLogger(__name__)

from .models import Email_Task

def email__no_reviews_after_submission():
    """
    Send email to learners that have waited more than 24 hours since uploading
    a valid submission, but haven't yet started a review
    """
    subject = 'Start your peer review'

    import time
    import datetime
    from basic.models import EntryPoint
    from interactive.views import has, group_graph
    from rubric.models import RubricActual
    from utils import send_email
    from django.conf import settings as DJANGO_SETTINGS
    from django.template import loader

    entry_points = EntryPoint.objects.all()
    idx = 0
    for entry_point in entry_points:

        course = entry_point.course
        # All valid submissions for this EntryPoint
        valid_subs = entry_point.submission_set.filter(is_valid=True)\
                                                    .exclude(status='A')
        if valid_subs.count():
            trigger = valid_subs[0].trigger
            if not(trigger):
                continue

        all_learners = course.person_set.filter(role='Learn') # is_validated=True
        for learner in all_learners:

            now_time = datetime.datetime.now(datetime.timezone.utc)
            # Find triggers that have just had a deadline that has passed.
            if hasattr(trigger, 'deadline_dt') and now_time < trigger.deadline_dt:
                continue

            if has(learner, 'started_a_review', entry_point=entry_point):
                continue

            # All ReviewReport that have been Allocated for Review to this learner
            allocated_reviews = entry_point.reviewreport_set.filter(reviewer=learner)\
                .order_by('-created') # for consistency
            if allocated_reviews.count() == 0:
                continue

            logger.info(str(trigger) + str(learner) + str(allocated_reviews))

            for review in allocated_reviews:
                prior = RubricActual.objects.filter(rubric_code=review.unique_code)

                if prior.count() == 0:
                    graph = group_graph(entry_point)
                    potential_submitter = graph.get_submitter_for(reviewer=learner)
                    if potential_submitter is None:
                        logger.info('No sub to review for {} in {}'.format(\
                            learner, entry_point))

                        # Stop here if there are no potential submitters
                        continue


            # OK, if we get this far, we likely need to send an email:
            # but, let's not spam the learner.
            if learner.email_task_set.filter(entry_point=entry_point,
                                             subject=subject).count():
                continue

            platform_link = '{0}/{1}'.format(DJANGO_SETTINGS.BASE_URL,
                                             entry_point.full_URL)
            platform_link = platform_link.replace('//', '/')
            ctx_dict = {'platform_link': platform_link,
                        'course': course.name,
                        'deliverable': entry_point.LTI_title,}
            messages = loader.render_to_string(\
                'basic/email_outstanding_reviews_to_start.txt',
                                                  ctx_dict)
            to_addresses = [learner.email, ]


            logger.debug("Will send email to: {} | {}".format(to_addresses,
                                                              messages))
            send_email(to_addresses, subject, messages)

            email_task = Email_Task(learner=learner,
                                    message=messages,
                                    entry_point=entry_point,
                                    subject=subject
                                    )
            email_task.save()

            # Let's wait some time before each email is sent out
            time.sleep(13)

    logger.info('email__no_reviews_after_submission: success')


def send_emails__evaluation_and_rebuttal():
    """
    Send emails for the Evaluation step: i.e. when two reviews are returned,
    are ready to be evaluated.
    """
    subject = 'Interactive Peer Review: start evaluating ...'
    import time
    from basic.models import EntryPoint
    from interactive.models import EvaluationReport
    from interactive.views import has
    from utils import send_email, insert_evaluate_variables
    from django.conf import settings as DJANGO_SETTINGS
    from django.template import loader
    from django.db.models import Q

    entry_points = EntryPoint.objects.all()

    # Exclude, for now, the Circular Economy course entry points
    entry_points = entry_points.exclude(course__label='66765')


    for entry_point in entry_points:

        course = entry_point.course
        all_learners = course.person_set.filter(is_validated=True)
        for learner in all_learners:

            all_subs = learner.submission_set.filter(entry_point=entry_point,
                                    is_valid=True).exclude(status='A')

            if not(has(learner, 'submitted', entry_point)) or \
                                                           all_subs.count()==0:
                continue

            if has(learner, 'read_and_evaluated_all_reviews', entry_point) and\
               has(learner, 'completed_rebuttal', entry_point):
                continue


            if learner.email_task_set.filter(entry_point=entry_point,
                                             subject=subject):
                continue

            # This is the submission by the learner
            submission = all_subs[0]
            crit1 = Q(status='C')
            crit2 = Q(status='L')
            reviews_associated = submission.rubricactual_set.filter(\
                                    rubric_template__entry_point=entry_point).\
                                    filter(crit1 | crit2)

            # Are there any rubrics associated with it?
            if not(reviews_associated):
                continue

            platform_link = '{0}/{1}'.format(DJANGO_SETTINGS.BASE_URL,
                                             entry_point.full_URL)
            platform_link = platform_link.replace('//', '/')
            ctx_dict = {'platform_link': platform_link,
                        'course': course.name,
                        'deliverable': entry_point.LTI_title,
                        'N_peers': reviews_associated.count()}
            messages = loader.render_to_string(\
                'basic/email_outstanding_evaluations_to_read_evaluate.txt',
                                                  ctx_dict)
            to_addresses = [learner.email, ]



            logger.debug("Will send email to: {} | {}".format(to_addresses,
                                                              messages))
            send_email(to_addresses, subject, messages)

            email_task = Email_Task(learner=learner,
                                    message=messages,
                                    entry_point=entry_point,
                                    subject=subject
                                    )
            email_task.save()

            # Let's wait some time before each email is sent out
            time.sleep(13)


    logger.info('Success: send_emails__evaluation_and_rebuttal')