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

# Debugging
import wingdbstub

def email__no_reviews_after_submission():
    """
    Send email to learners that have waited more than 24 hours since uploading
    a valid submission, but haven't yet started a review
    """
    logger.info('email__no_reviews_after_submission: success')


def send_emails__evaluation_and_rebuttal():
    """
    Send emails for the Evaluation step: i.e. when two reviews are returned,
    are ready to be evaluated.
    """
    import time
    from basic.models import EntryPoint
    from interactive.models import EvaluationReport
    from interactive.views import has
    from utils import send_email, insert_evaluate_variables
    from django.conf import settings as DJANGO_SETTINGS
    from django.template import loader
    from django.db.models import Q

    entry_points = EntryPoint.objects.all()
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


            if learner.email_task_set.filter(entry_point=entry_point):
                continue

            # This is the submisison by the learner
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
            subject = 'Interactive Peer Review: start evaluating ...'


            logger.debug("Will send email to: {} | {}".format(to_addresses,
                                                              messages))
            send_email(to_addresses, subject, messages)

            email_task = Email_Task(learner=learner,
                                    message = messages,
                                    entry_point = entry_point,
                                    subject = subject
                                    )
            email_task.save()

            # Let's wait some time before each email is sent out
            time.sleep(13)


    logger.info('Success: send_emails__evaluation_and_rebuttal')