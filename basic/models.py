from django.db import models
from django.utils import timezone

# In general, in the rewrite:
# PR_Process -> EntryPoint
# PR_Phase   -> Trigger

# Our imports
from utils import generate_random_token


class Course(models.Model):
    """ Which courses are being supported."""
    name = models.CharField(max_length=300, verbose_name="Course name")
    label = models.CharField(max_length=300,
                             verbose_name="LTI POST label context_id",
        help_text=("Obtain this from the HTML POST field: 'context_id' "))
    # Brightspace:   u'lis_course_offering_sourcedid': <--- is another option
    #                                  [u'brightspace.tudelft.nl:training-IDE'],
    #
    # edX:   u'context_id': [u'course-v1:DelftX+IDEMC.1x+1T2017']

    base_url = models.CharField(max_length=200,
                                help_text="The base URL",
                                blank=True)
    offering = models.PositiveIntegerField(default='0000', blank=True,
        help_text="Which year/quarter is it being offered?")

    def __str__(self):
        return u'%s' % self.name


class Person(models.Model):
    """
    A learner, with their details provided from the LTI system.
    """
    ROLES = (('Admin', "Administrator"),
             ('Learn', "Learner"),
             ('TA', 'Teaching Assistant')
            )

    is_active = models.BooleanField(default=True, help_text=('NOT USED'))
    email = models.EmailField(blank=True, default='')
    student_number = models.CharField(max_length=15, blank=True, default='')

    display_name = models.CharField(max_length=400, verbose_name='Display name',
                                   blank=True)

    user_ID = models.CharField(max_length=100, blank=True,
                                            verbose_name='User ID from LMS/LTI')
    role = models.CharField(max_length=5, choices=ROLES, default='Learn')

    last_lis = models.CharField(max_length=100, blank=True,
                                verbose_name='Last known: lis_result_sourcedid')
    course = models.ForeignKey(Course, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return u'{0} [{1}]({2})'.format(self.email,
                                        self.user_ID[0:5],
                                        self.role)


class Group(models.Model):
    """ Used when learners work/submit in groups."""
    course = models.ForeignKey(Course)
    name = models.CharField(max_length=300, verbose_name="Group name")
    description = models.TextField(blank=True,
                                   verbose_name="Detailed group description")
    capacity = models.PositiveIntegerField(default=0,
        help_text=('How many people in this particular group instance?'))
    order = models.PositiveIntegerField(default=0, help_text=('For ordering '
            'purposes in the tables.'))

    def __str__(self):
        return u'{0}'.format(self.name)


class GroupEnrolled(models.Model):
    """
    Which group is a learner enrolled in"""
    person = models.ForeignKey(Person)
    group = models.ForeignKey(Group, null=True,
        help_text=('If blank/null: used internally to enrol the rest of the '
                                          'class list.'))
    is_enrolled = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)


class EntryPoint(models.Model):
    """ Describes the EntryPoint: requirements and deadlines.

    OLD:
    There is a one-to-one relationship to the rubric template. So create this
    PR_process first, then link it up later when you create the template.

    There is one of these for each peer review activity. If a course has 3
    peer activities, then there will be 3 of these instances.
    """
    class Meta:
        verbose_name = 'Entry point'
        verbose_name_plural = 'Entry points'

    # This can be used to branch code, if needed, for different LTI systems
    CHOICES = (('Brightspace-v1', 'Brightspace-v1'),
               ('edX-v1',         'edX-v1'),
               ('Coursera-v1',    'Coursera-v1'))

    # How to identify the LTI consumer?
    # ---------------------------------
    # Brightspace: HTML-POST: u'lti_version': [u'LTI-1p0'],
    # edX:         HTML-POST: resource_link_id contains "edX"

    LTI_system = models.CharField(max_length=50, choices=CHOICES,)
    #title = models.CharField(max_length=300, verbose_name="Your peer review title")
    LTI_id = models.CharField(max_length=50, verbose_name="LTI ID",
        help_text=('In Brightspace LTI post: "resource_link_id"'))
    LTI_title = models.CharField(max_length=300, verbose_name="LTI Title",
        help_text=('A title to identify this PR in the database'))


    course = models.ForeignKey(Course)

    uses_groups = models.BooleanField(default=False,
                            help_text='Are groups used to SUBMIT a document?')
    #gf_process = models.ForeignKey('groups.Group_Formation_Process',blank=True,
    #                               default=None, null=True,
    #    help_text=('Must be specified if groups are being used.'))

    #instructions = models.TextField(help_text='May contain HTML instructions',
    #            verbose_name='Overall instructions to learners', )

    order = models.PositiveSmallIntegerField(default=0,
            help_text=('Used to order the achievement display in a course with '
                       'many entry points.'))

    entry_function = models.CharField(max_length=100, default='',
       help_text='Django function, with syntax: "app_name.views.function_name"')

    def __str__(self):
        return '[{0}]:{1}'.format(self.course, self.LTI_title)
