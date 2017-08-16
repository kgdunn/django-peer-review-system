from django.db import models
from utils import generate_random_token


class RubricTemplate(models.Model):
    """
    Describes the rubric that will be attached to a Peer Review.
    One instance per Peer Review (multiple instances for learners are based
    off this template).

    A Rubric consists of one or more Items (usually a row).
    Items consist of one or more Options (usually columns).

    """
    title = models.CharField(max_length=300, verbose_name="Peer review rubric")
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    # Was: ``pr_process``
    entry_point = models.ForeignKey('basic.EntryPoint', default=None,
                                   null=True, blank=True)

    # Make this the primary way to access the rubric (through a Trigger, not
    # an EntryPoint)

    # Was ``phase``
    trigger = models.ForeignKey('interactive.Trigger', default=None,
                              null=True, blank=True)

    general_instructions = models.TextField(default='')

    maximum_score = models.FloatField(default=0.0)

    show_order = models.BooleanField(default=True,
            help_text=('Shows the order numbers. e.g "1. Assess ..."; else '
                       'it just shows: "Assess ..."'))

    submit_button_also_shown_on_top = models.BooleanField(default=True)

    show_maximum_score_per_item = models.BooleanField(default=True,
            help_text='Can be over-ridden on a per-item basis also.')

    def __str__(self):
        return u'%s' % self.title


class RubricActual(models.Model):
    """
    The actual rubric: one instance per learner per submission.

    A submission is allocated to a person for grading. This tracks that:
    the status of it, the grade (only if completed and submitted); the
    ``RubricActual`` instance is also used as a ForeignKey in each
    ``RItemActual``. That way we can quickly pull the evaluated score of the
    rubric from these items.

    A few other handy statistics (score, and word_count) are tracked here,
    to minimize frequent or expensive hits on the database.

    """
    STATUS = (('A', 'Assigned to grader'),
              ('V', 'Grader has viewed it, at least once'),
              ('P', 'Progressing...'),
              ('C', 'Completed'),
              ('L', 'Locked')) # read-only

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    started = models.DateTimeField(verbose_name='When did user start grading?')
    completed = models.DateTimeField(verbose_name='When did user end grading?')
    status = models.CharField(max_length=2, default='A', choices=STATUS)
    submitted = models.BooleanField(default=False,
        help_text='Has been completed reviewed AND submitted by peer grader.')
    special_access = models.BooleanField(default=False,
        help_text='Set to true to allow the "graded_by" person to access it.')
    graded_by = models.ForeignKey('basic.Person')
    rubric_template = models.ForeignKey(RubricTemplate)
    submission = models.ForeignKey('submissions.Submission', null=True)

    # This is used to access the rubric, when graded in an external tab
    rubric_code = models.CharField(max_length=16, editable=False, blank=True)

    eval_code = models.CharField(max_length=16, editable=False, blank=True)

    # These are only valid once ``self.submitted=True``
    score = models.FloatField(default=0.0)
    word_count = models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        if not(self.rubric_code):
            self.rubric_code = generate_random_token(token_length=16)
        super(RubricActual, self).save(*args, **kwargs)

    def __str__(self):
        return u'Peer: {0}; Sub: {1}'.format(self.graded_by, self.submission)


class RItemTemplate(models.Model):
    """
    A (usually a row) in the rubric, containing 1 or more ROptionTemplate
    instances.
    An item corresponds to a criterion, and the peers will select an option,
    and also (probably) comment on the criterion.
    """
    r_template = models.ForeignKey(RubricTemplate)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    order = models.IntegerField()
    criterion = models.TextField(help_text=('The prompt/criterion for the row '
                                            'in the rubric'))
    max_score = models.FloatField(help_text='Highest score achievable here')

    TYPE = (('Radio', 'Radio buttons (default)'),
            ('DropD', 'Dropdown of scores'),
            ('Chcks', 'Checkbox options: multiple valid answers'), # no score
            ('LText', 'Long text [HTML Text area]'),
            ('SText', 'Short text [HTML input=text]'),)
    option_type = models.CharField(max_length=5, choices=TYPE, default='Radio')


    def save(self, *args, **kwargs):
        """ Override the model's saving function to do some checks """
        self.max_score = float(self.max_score)
        super(RItemTemplate, self).save(*args, **kwargs)

    def __str__(self):
        return u'%d. %s' % (self.order, self.criterion[0:50])


class RItemActual(models.Model):
    """
    The actual rubric item for a learner.
    """
    ritem_template = models.ForeignKey(RItemTemplate)
    r_actual = models.ForeignKey(RubricActual) # assures cascading deletes
    comment = models.TextField(blank=True) # comment added by the learner
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    # Has the question been submitted yet? True: user actively clicked the
    # submit button; ``False``: XHR stored answer.
    submitted = models.BooleanField(default=False)

    def __str__(self):
        return u'[Item {0}]'.format(self.ritem_template.order)


class ROptionTemplate(models.Model):
    """
    A rubric option template (a single cell in the rubric). Usually with
    other options to the left and right of it.
    """
    rubric_item = models.ForeignKey(RItemTemplate)
    score = models.FloatField(help_text='Usually: 1, 2, 3, 4, etc points')
    criterion = models.TextField(help_text='A prompt/criterion to the peers',
                                 blank=True)
    order = models.IntegerField()
    # NOTE: the ``order`` is ignored for type ``LText``, as there will/should
    #       only be 1 of those per Item.


    def save(self, *args, **kwargs):
        """ Override the model's saving function to do some checks """
        self.score = float(self.score)
        assert(self.score <= self.rubric_item.max_score)
        super(ROptionTemplate, self).save(*args, **kwargs)

    def __str__(self):
        out = u'[%d] order %d (%d pts). %s' % (self.rubric_item.order,
                                               self.order,
                                               self.score,
                                               self.criterion)
        return out[0:100]

class ROptionActual(models.Model):
    """
    The filled in ROptionTemplate by a specific learner.
    Note: an Item has one or more Options (ROptionTemplate) associated with it.
          we will not create an "ROptionActual" for each ROptionTemplate,
          only one ROptionActual is created.
          If the user changes their mind, old ROptionActuals are deleted.
    """
    roption_template = models.ForeignKey(ROptionTemplate)
    ritem_actual = models.ForeignKey(RItemActual, null=True)
    comment = models.TextField(blank=True)
    submitted = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return u'%s' % (self.roption_template, )