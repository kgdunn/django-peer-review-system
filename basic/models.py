from django.db import models
from django.utils import timezone

# In general, in the rewrite:
# PR_Process -> EntryPoint
# PR_Phase   -> Trigger

# Our imports
from utils import generate_random_token
import hashlib


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

    is_validated = models.BooleanField(default=False)
    email = models.EmailField(blank=True, default='')
    display_name = models.CharField(max_length=400, verbose_name='Display name',
                                   blank=True)

    user_ID = models.CharField(max_length=100, blank=True,
                                            verbose_name='User ID from LMS/LTI')
    role = models.CharField(max_length=5, choices=ROLES, default='Learn')

    last_lis = models.CharField(max_length=200, blank=True,
                                verbose_name='Last known: lis_result_sourcedid')
    last_grade_push_url = models.CharField(max_length=500, blank=True,
                default='', verbose_name='Last known: lis_outcome_service_url')
    course = models.ForeignKey(Course, blank=True, null=True, default=None)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    hash_code = models.CharField(max_length=16, default='', blank=True)
    initials = models.CharField(max_length=5, default='', blank=True,
                                help_text='Initials of the user (for display)')

    def save(self, *args, **kwargs):
        """
        Modifications when a ``Person`` instance is saved.
        """
        self.email = self.email.lower()

        if self.initials == '' and self.display_name:
            initials = ''
            for word in self.display_name.split(' '):
                if word[0].lower() != word[0]:
                    initials += word[0]

            others = Person.objects.filter(initials=initials)
            if others:
                initials = '{}{}'.format(initials, others.count())

            self.initials = initials[0:5]

        super(Person, self).save(*args, **kwargs)

        if not(self.hash_code):
            code = hashlib.sha256()
            code.update(str(self.id).encode('utf-8'))
            self.hash_code = code.hexdigest()[0:16]

        super(Person, self).save(*args, **kwargs)



    def get_initials(self):
        """
        Abuse this function to also add some information to profiles over time.
        """
        if self.initials == '':
            self.save()
        if not(self.hash_code):
            self.save()
        return self.initials

    def show_group(self):
        groups = self.groupenrolled_set.all()
        if groups.count() == 1:
            return '[{}]'.format(groups[0].group.name)
        else:
            return ''


    def __str__(self):
        return u'[{0}]({1})'.format(self.initials or self.id, self.role)

class Token(models.Model):
    """ Tokens capture time/date and permissions of a user to access.
    """
    person = models.ForeignKey('Person', null=True, blank=True)
    hash_value = models.CharField(max_length=32, editable=False, default='-'*32)
    was_used = models.BooleanField(default=False)
    time_used = models.DateTimeField(auto_now=True, auto_now_add=False)
    next_uri = models.CharField(max_length=254, default='')


class Group_Formation_Process(models.Model):
    """Umbrella to hold all the groups for a given course."""
    class Meta:
        verbose_name = 'Group formation process'
        verbose_name_plural = 'Group formation processes'

    name = models.CharField(max_length=200)
    course = models.ForeignKey(Course)

    def __str__(self):
        return u'{0}'.format(self.name)

class Group(models.Model):
    """ Used when learners work/submit/restricted to groups."""
    gfp = models.ForeignKey(Group_Formation_Process, blank=True, default=None,
                            verbose_name='Group formation process')
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

    def __str__(self):
        return u'{0}: "{1}" is enrolled'.format(self.group, self.person)



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
    LTI_id = models.CharField(max_length=50, verbose_name="LTI ID",
        help_text=('In Brightspace LTI post: "resource_link_id"'))
    LTI_title = models.CharField(max_length=300, verbose_name="LTI Title",
        help_text=('A title to identify this PR in the database'))


    course = models.ForeignKey(Course)

    uses_groups = models.BooleanField(default=False,
        help_text='Are groups used to restrict reviews?')

    only_review_within_group = models.BooleanField(default=False,
        help_text=('If checked: then students only review within; If unchecked:'
                   ' then students review outside their group.'))
    gf_process = models.ForeignKey('Group_Formation_Process', blank=True,
                                   default=None, null=True,
        help_text=('Must be specified if groups are being used.'))

    #instructions = models.TextField(help_text='May contain HTML instructions',
    #            verbose_name='Overall instructions to learners', )

    order = models.PositiveSmallIntegerField(default=0,
            help_text=('Used to order the achievement display in a course with '
                       'many entry points.'))

    entry_function = models.CharField(max_length=100, default='',
       help_text='Django function, with syntax: "app_name.views.function_name"')

    full_URL = models.CharField(max_length=255, default='', blank=True,
        help_text=('Full URL to the entry point in the given platform, starting'
                   'with "/"; eg: /course/12345/98765432'))

    def __str__(self):
        return '[{0}]:{1}'.format(self.course, self.LTI_title[0:17])


class Email_Task(models.Model):
    """
    Used to track emails to students, and to avoid duplicate mailings.
    """
    learner = models.ForeignKey(Person)
    entry_point = models.ForeignKey(EntryPoint)
    message = models.TextField(blank=True, default='')
    subject = models.CharField(max_length=500)
    sent_datetime = models.DateTimeField(auto_now=True)
