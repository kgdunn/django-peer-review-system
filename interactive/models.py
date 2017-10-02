from django.db import models
from django.utils import timezone
from utils import generate_random_token
from django.core.exceptions import ValidationError
"""

Key assumptions:
* You have to submit before you can start reviewing others
* We start the review process when we have a sufficiently large pool of reviewers
* You have to wait till your work is reviewed before you can review someone else


5	Submitted a document the first time
10  Document is submitted and set; no more updates are possible
20	Started review of peer's work
30 	Completed reviews of peer's work
50  Has completely evaluated review from peer
70  Has written rebuttal to peers
80  Has assessed all rebuttals from peers
90  Has seen assessments; actually it will jump to 100 at that point
100 Process completed
"""

class AchieveConfig(models.Model):
    """
    The achievements of a person expected
    """
    name = models.CharField(max_length=100, help_text='Display name')
    description = models.TextField(blank=True, null=True,
                                   help_text='Detailed description')
    score = models.PositiveSmallIntegerField(default=0)
    entry_point = models.ForeignKey('basic.EntryPoint', null=True, blank=True)

    achievements = models.ManyToManyField('basic.Person',
                                     through='Achievement',
                                     )

    def __str__(self):
        return '[{0}] [{1}] "{2}"'.format(self.entry_point,
                                           self.score,
                                           self.name,
                                         )

class Achievement(models.Model):
    """
    """
    learner = models.ForeignKey('basic.Person', on_delete=models.CASCADE)
    achieved = models.ForeignKey(AchieveConfig, on_delete=models.CASCADE)
    when = models.DateTimeField(auto_now_add=True)
    last = models.DateTimeField(auto_now=True)

    # Has the learner achieved this goal, or not?
    done = models.BooleanField(default=False)


    def __str__(self):
        return '[{0}] achieved {1}'.format(self.learner,
                                           self.achieved)


class ReleaseConditionConfig(models.Model):
    """

    """
    name = models.CharField(max_length=200)
    entry_point = models.ForeignKey('basic.EntryPoint')
    all_apply = models.BooleanField(default=False,
                    verbose_name='All rules must apply',
                    help_text='All rules must pass before it is valid')
    any_apply = models.BooleanField(default=False,
                    help_text='Any or more rules must pass before it is valid',
                    verbose_name='Any rule applies')


    def __str__(self):
        if self.all_apply:
            return '[{0}]: ALL apply'.format(self.name )
        elif self.all_apply:
            return '[{0}]: ALL apply'.format(self.name )


    def clean(self):
        if self.all_apply  and self.any_apply:
            raise ValidationError('Specify either ALL or ANY apply; not both.')


class ReleaseCondition(models.Model):
    """
    Specifies a single release condition
    """
    rc_config = models.ForeignKey(ReleaseConditionConfig,
                                  verbose_name='Release condition set',)
    achieveconfig = models.ForeignKey(AchieveConfig)
    order = models.PositiveSmallIntegerField(default=0,
                    help_text='To order the display for students.')


class Trigger(models.Model):
    """
    Triggers are cycled through to build up the rubric. They are linked with
    Achievements. By testing if certain achievements are met, the
    triggers may be more and more complex in what they cover.

    Types of triggers are to:
        * send emails,
        * create rubrics,
        * add/update links
        * add grades to our gradebook

    """
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=False,
                        help_text='If inactive: will skip this trigger.')
    name = models.CharField(max_length=100, help_text='For database display')

    description = models.TextField(max_length=500, default='',
                                   help_text='Internal description')
    entry_point = models.ForeignKey('basic.EntryPoint')
    function = models.CharField(max_length=100,
                                help_text='function from the views.py file')
    kwargs = models.TextField(blank=True,
                              help_text='Comma separated key-value pairs')
    template = models.TextField(blank=True,
               help_text='This template will be rendered with the variables.')

    start_dt = models.DateTimeField(default=timezone.now,
            verbose_name='Earliest time for this trigger',
            help_text='Trigger will not run prior to the start date/time')
    end_dt = models.DateTimeField(default=timezone.now, blank=True, null=True,
            verbose_name='Latest time for this trigger',
            help_text='Trigger will not run after the start date/time')

    deadline_dt = models.DateTimeField(default=None, blank=True, null=True,
            verbose_name='Deadline date and time',
            help_text=('Sometimes you want a deadline to use in your logic. '
                       'Set it here.'))

    def __str__(self):
        return '[{0};{1}] {2}: "{3}"'.format(self.order,
                                             self.entry_point,
                                             self.function[0:8],
                                             self.name)


class GroupConfig(models.Model):
    """
    Contains the configuration of the internal groups during the review process.
    """
    class Meta:
        unique_together = (('group_name', 'entry_point'), )

    group_name = models.CharField(max_length=100,
                                  help_text='If empty, will be auto-generated',
                                  blank=True, null=True)

    # Must specify the entry point, because in different entry points, the
    # group names will be different, and used for different purposes.
    entry_point = models.ForeignKey('basic.EntryPoint', null=True, blank=True)
    members = models.ManyToManyField('basic.Person',
                                     through='Membership',
                                     )
    created_on = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return '[{0}] {1}'.format(self.entry_point,
                                   self.group_name)

    def save(self, *args, **kwargs):
        if self.group_name:
            super(GroupConfig, self).save(*args, **kwargs)
            return

        prior_groups = GroupConfig.objects.filter(entry_point=self.entry_point)
        highest_number = 0
        for item in prior_groups:
            parts = item.group_name.lower().split('group ')
            if len(parts) > 1:
                try:
                    if int(parts[1]) >= highest_number:
                        highest_number = int(parts[1])
                except ValueError:
                    pass

        # So we should have the highest next number now
        # but verify no group already exists with that name:

        highest_number += 1
        prior_groups = GroupConfig.objects.filter(entry_point=self.entry_point,
                                                  group_name='Group {}'.format(
                                                        highest_number))
        while prior_groups.count() > 0:
            highest_number += 1
            prior_groups = GroupConfig.objects.filter(\
                                entry_point=self.entry_point,
                                group_name='Group {}'.format(highest_number))
        self.group_name = 'Group {}'.format(highest_number)
        super(GroupConfig, self).save(*args, **kwargs)



class Membership(models.Model):

    ROLES = (('Submit', "Submitter"),
             ('Review', "Reviewer"),
             )

    learner = models.ForeignKey('basic.Person', on_delete=models.CASCADE)
    group = models.ForeignKey(GroupConfig, on_delete=models.CASCADE)
    role = models.CharField(choices=ROLES, max_length=6)

    # Note: in practice, we don't use this field. It's always fixed. But leave
    #       it here for future use
    fixed = models.BooleanField(default=False,
            help_text='Once fixed, this membership cannot be changed')

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return '[{0}] is {{{1}}}: {2}'.format(self.group.group_name,
                                                self.role,
                                                self.learner)




class ReviewReport(models.Model):
    """
    Used for coordinating the review process between submitter and reviewers.

    The key point is that the ``ReviewReport`` instance is associated with the
    reviewer. When they visit the page, the review is assigned to them; not
    ahead of time. Once assigned, the submitter cannot re-upload.
    """
    # Was ``learner`` when we copied this from v1.
    reviewer = models.ForeignKey('basic.Person')

    group = models.ForeignKey('basic.Group', blank=True, null=True,
        default=None, help_text="If a group submission, links to group.")

    trigger = models.ForeignKey(Trigger, blank=True, null=True,
            help_text='Which trigger is this associated with?')

    entry_point = models.ForeignKey('basic.EntryPoint', blank=True, null=True,
            help_text='Which entry_point is this associated with?')

    submission = models.ForeignKey('submissions.Submission',
                                   null=True, blank=True,
            help_text='Not known, until the reviewer visits the page')

    grpconf = models.ForeignKey(GroupConfig, null=True, blank=True,
            help_text='Not known, until the reviewer visits the page')

    order = models.PositiveSmallIntegerField(help_text='Used to order reviews',
                                             default=0, editable=False)


    # This field is the linking key between ``ReviewReport`` and ``RubricActual``
    # We could have merged both models, but they do belong logically separate.
    unique_code = models.CharField(max_length=16, editable=False, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    last_viewed = models.DateTimeField(auto_now=True)

    # This is used to access the report in an external tab
    def save(self, *args, **kwargs):
        if not(self.unique_code):
            self.unique_code = generate_random_token(token_length=16)
        super(ReviewReport, self).save(*args, **kwargs)

    def __str__(self):
        return u'Report for: {0}; Sub: {1} [{2}]'.format(self.reviewer,
                                                         self.submission,
                                                         self.unique_code)


class EvaluationReport(models.Model):
    """
    Used for coordinating the evaluation of the reviewer's review, with
    the original submitter.
    """
    # The person who 'created' this review (ie it is the original submission
    # plus the appended review). The reviewer whose review is appended here
    # is the ``peer_reviewer``.
    peer_reviewer = models.ForeignKey('basic.Person',
                                      related_name='peer_reviewer',
                                      blank=True, null=True,
                                      help_text=('The reviewer whose review is '
                                                 'appended here. Leave blank '
                                                 'for rebuttals.'))

    # What type of report is this?
    STATUS = (('-', '----------'),
              ('E', 'Evaluation'), # <-- going from review to rebuttal
              ('R', 'Rebuttal'),   # <-- going from evaluation to rebuttal
              ('A', 'Assessment')  # <-- going from rebuttal to assessment
              )
    sort_report = models.CharField(max_length=2, choices=STATUS, default='-')

    # The original submitter is the evaluator (they will evalute the review)
    #
    # TODO: rename this field to ``submitter`` (since in different sort_report
    #       the word "evaluator" is confusing, e.g. during assessment phase)
    evaluator = models.ForeignKey('basic.Person', related_name='evaluator',
                        help_text='The original submitter is the evaluator')

    # The r_actual that the submitter will fill in
    r_actual = models.ForeignKey('rubric.RubricActual', blank=True, null=True,
                        help_text='Might be created just in time')

    trigger = models.ForeignKey(Trigger, blank=True, null=True,
            help_text='Which trigger is this associated with?')

    submission = models.ForeignKey('submissions.Submission',
                                   null=True, blank=True,
            help_text='Might not be known, until the reviewer visits the page')

    # This field is the linking key between ``EvaluationReport`` and
    # ``RubricActual``
    # We could have merged both models, but they do belong logically separate.
    unique_code = models.CharField(max_length=16, editable=False, blank=True)

    # This helps us link the Evaluation report to any prior rubric/phase
    # that came before this one.
    prior_code = models.CharField(max_length=16, editable=False, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    last_viewed = models.DateTimeField(auto_now=True)

    # This is used to access the report in an external tab
    def save(self, *args, **kwargs):
        if not(self.unique_code):
            self.unique_code = generate_random_token(token_length=16)
        super(EvaluationReport, self).save(*args, **kwargs)

    def __str__(self):
        if self.sort_report == 'R':
            return ('[{0}]: Rebuttal by submitter [{1}] of review that was '
                    'completed by peers').format(self.unique_code,
                                                 self.evaluator)

        elif self.sort_report == 'A':
            return ('[{0}]: Assessment of rebuttal supplied by submitter [{1}]; '
                            'done by {2}').format(self.unique_code,
                                                  self.evaluator,
                                                  self.peer_reviewer)
        elif self.sort_report == 'E':
            return ('[{0}]: Evaluation by submitter [{1}] of review that was '
                    'completed by [{2}]').format(self.unique_code,
                                                 self.evaluator,
                                                 self.peer_reviewer)