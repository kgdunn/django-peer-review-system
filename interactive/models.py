from django.db import models
from django.utils import timezone
from utils import generate_random_token
"""

Key assumptions:
* You have to submit before you can start reviewing others


---- Submission (by the student)
0	Not started, visited the starting page   -> send email
1   Has been sent a welcoming email          -> nothing
3	Submitted a document the first time      -> update text in page; thank email
                                             -> after sufficient peers
                                                * send email to reviewers
                                                * create rubric for peers
4, 5, 6, 7, 8, 9                             -> Everytime the document is
                                                submitted (again)
10  Document is submitted and set; no more updates are possible

SUBMISSION_FIXED = 10

---- Evaluation (by the student of their peer)

11 Has read received review from peer 1  -> web update only (both sides)
12 Has read received review from peer 2  -> web update only & email after == N
13 Has read received review from peer 3
14 Has read received review from peer 4
15 Has read received review from peer 5  -> web update only & email after == N
                                            * email submitter. Reviews are in,
                                              and time to evaluate feedback from peers.

---- Review (by the student of their peers)
20	Started review of peer 1's work
21	Completed review of peer 1's work     -> web update for both sides
22	Started review of peer 2's work
23	Completed review of peer 2's work     -> web update for both sides
24	Started review of peer 3's work
25	Completed review of peer 3's work
26	Started review of peer 4's work
27	Completed review of peer 4's work
28	Started review of peer 5's work
29	Completed review of peer 5's work


---- Evaluation (by the student of their peer)
31 Has completely evaluated review from peer 1 -> weblink to see peer's eval
32 Has completely evaluated review from peer 2
33 Has completely evaluated review from peer 3
34 Has completely evaluated review from peer 4
35 Has completely evaluated review from peer 5

41 Has read evaluation received back from peer 1
42 Has read evaluation received back from peer 2
43 Has read evaluation received back from peer 3
44 Has read evaluation received back from peer 4
45 Has read evaluation received back from peer 5

---- Rebuttal (by the student back to their peer)
61 Has written rebuttal to peers

71 Has read the rebuttal received from peer 1
72 Has read the rebuttal received from peer 2
73 Has read the rebuttal received from peer 3
74 Has read the rebuttal received from peer 4
75 Has read the rebuttal received from peer 5

---- Assessment (of rebuttals)
81 Has assessed the rebuttal received from peer 1
82 Has assessed the rebuttal received from peer 2
83 Has assessed the rebuttal received from peer 3
84 Has assessed the rebuttal received from peer 4
85 Has assessed the rebuttal received from peer 5

---- Wrapping up
91 Has seen assessment from peer 1
92 Has seen assessment from peer 2
93 Has seen assessment from peer 3
94 Has seen assessment from peer 4
95 Has seen assessment from peer 5

100 Process completed
"""

class Trigger(models.Model):
    """
    Triggers are initiated when the learner gets to a certain score.

    Starting score = 0.0: trigger can be initiated. If task completed, then the
                          next trigger can be initiated.

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
    lower = models.PositiveSmallIntegerField(help_text='Called if >= to this')
    upper = models.PositiveSmallIntegerField(help_text='Called if <= to this')

#admin_only = models.BooleanField
    start_dt = models.DateTimeField(default=timezone.now,
                                verbose_name='Earliest time for this trigger',)
    end_dt = models.DateTimeField(default=timezone.now,
                                verbose_name='Latest time for this trigger',)



    def __str__(self):
        return '[{0}] {1}: "{2}"'.format(self.order,
                                         self.name,
                                         self.function)


class GroupConfig(models.Model):
    """
    Contains the configuration of the internal groups during the review process.
    """
    class Meta:
        unique_together = (('group_name', 'entry_point'), )
    class Lock:
        locked = False


    group_name = models.CharField(max_length=100,
                                  help_text='If empty, will be auto-generated',
                                  blank=True, null=True)
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
    fixed = models.BooleanField(default=False,
            help_text='Once fixed, this membership cannot be changed')

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

    have_emailed = models.BooleanField(default=False)

    group = models.ForeignKey('basic.Group', blank=True, null=True,
        default=None, help_text="If a group submission, links to group.")

    trigger = models.ForeignKey(Trigger, blank=True, null=True,
            help_text='Which trigger is this associated with?')

    submission = models.ForeignKey('submissions.Submission',
                                   null=True, blank=True,
            help_text='Not known, until the reviewer visits the page')

    grpconf = models.ForeignKey(GroupConfig, null=True, blank=True,
            help_text='Not known, until the reviewer visits the page')


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
