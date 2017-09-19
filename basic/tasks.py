"""
Tasks which are called at different schedules. Write the scheduled tasks here.
These are functions (in this file) which are run on a periodic basis.
Each function should do its own imports. Do not have imports up here at the top
of the function.

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

# Debugging
import wingdbstub


def send_emails__evaluation():
    """
    Send emails for the Evaluation step: i.e. when two reviews are returned,
    are ready to be evaluated.
    """
    from basic.models import EntryPoint
    from interactive.models import EvaluationReport
    from interactive.views import has
    from utils import send_email, insert_evaluate_variables
    from django.conf import settings as DJANGO_SETTINGS
    from django.db.models import Q

    #entry_points = EntryPoint.objects.all()
    #for entry_point in entry_points:
        #logger.info(entry_point)
        #course = entry_point.course
        #all_learners = course.person_set.filter(is_validated=True)
        #for learner in all_learners:

            #all_subs = learner.submission_set.filter(entry_point=entry_point,
                                    #is_valid=True).exclude(status='A')

            #if not(has(learner, 'submitted', entry_point)) or \
                                                           #all_subs.count()==0:
                #continue

            ## This is the submisison by the learner
            #submission = all_subs[0]

            ## Are there any rubrics associated with it?
            #crit1 = Q(status='C')
            #crit2 = Q(status='L')
            #rubrics = submission.rubricactual_set.filter(crit1 | crit2)


            #if not(has(learner, 'read_and_evaluated_all_reviews', entry_point)):

                #for item in rubrics:
                    #report = EvaluationReport.objects.get(unique_code=ractual.next_code)

                #platform_link = '{0}/'.format(DJANGO_SETTINGS.BASE_URL,
                                              #entry_point.full_URL)
                #ctx_dict = {'platform_link': platform_link,
                            #'course': course.name}
                #messages = loader.render_to_string(\
                    #'basic/email_outstanding_evaluations_to_read_evaluate',
                                                      #ctx_dict)
                #to_addresses = [learner.email, ]
                #subject = 'Interactive Peer Review: start evaluating ...'

                #print("Will send to: {} | {}".format(to_addresses, messages))

                ##send_email(to_addresses, subject, messages)


    logger.info('--> Send_emails__evaluation: completed')