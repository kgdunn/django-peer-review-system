from django.db import models
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
"""
---- Submission (by the student)
0	Not started, visited the starting page      -> send email
1   Has been sent a welcoming email             -> nothing
3	Submitted a document the first time         -> update text in page; thank email
                                                -> after sufficient peers
                                                   * send email to reviewers
                                                   * create rubric for peers
4, 5, 6, 7, 8, 9                                -> Everytime the document is submitted (again)
10  Document is submit and set; no more updates possible



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
@python_2_unicode_compatible
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

    description = models.TextField(max_length=500,
                                   help_text='Internal description')
    entry = models.ForeignKey('basic.EntryPoint')
    function = models.CharField(max_length=100,
                                help_text='function from the views.py file')
    args = models.TextField(blank=True, help_text='Comma separated entries')
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

