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
                              null=True, blank=True,
                              related_name='triggers')

    next_trigger = models.ForeignKey('interactive.Trigger',
        default=None, null=True, blank=True,
        help_text='What, if any, is the next trigger associated with this?',
        related_name='next_triggers',
        )

    general_instructions = models.TextField(default='')

    submit_button_text = models.CharField(max_length=255,
                                          default='Submit your review',
                                          blank=False, null=False,
                            help_text='The text used on the submit button')

    maximum_score = models.FloatField(default=0.0)

    show_order = models.BooleanField(default=True,
            help_text=('Shows the order numbers. e.g "1. Assess ..."; else '
                       'it just shows: "Assess ..."'))

    submit_button_also_shown_on_top = models.BooleanField(default=True)

    show_maximum_score_per_item = models.BooleanField(default=True,
            help_text='Can be over-ridden on a per-item basis also.')

    show_median_words_with_complaint = models.BooleanField(default=True,
            help_text='Shows the word count and complains if below median.')

    minimum_word_count = models.PositiveSmallIntegerField(default=0,
            help_text=('If greater than zero, will require the user to fill in '
                       'a minimum number of words.'))

    thankyou_template = models.TextField(default='Thank-you ...',
        help_text=('The following replacements are available: {{r_actual}}, '
                   '{{n_missing}} (number of missing items); '
                   '{{word_count}}, {{median_words}} of all reviews '
                   '{{person}} (who just did the review) '
                   '{{total_score}} and {{percentage}}.'), )

    hook_function = models.CharField(max_length=100, blank=True, null=False,
                                     default='',
            help_text=('Hook that is called (with r_actual as only input)'
                       'when the review is completed. Called with async() '
                       'so it is OK if it is overhead intensive. Hook func '
                       'must exist in the "interactive" views.py application.'))

    def __str__(self):
        return u'{0}. [{1}] {2}'.format(self.id, self.trigger, self.title)


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
    evaluated = models.DateTimeField(blank=True, null=True,
        verbose_name='When did submitter evalute the review?',)

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

    # This rubric might be linked to a next rubric that follows on.
    next_code = models.CharField(max_length=16, editable=False, blank=True)

    # These are only valid once ``self.submitted=True``
    score = models.FloatField(default=0.0)
    word_count = models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        if not(self.rubric_code):
            self.rubric_code = generate_random_token(token_length=16)
        super(RubricActual, self).save(*args, **kwargs)

    def __str__(self):
        return u'Peer: {0}; Sub: {1}'.format(self.graded_by, self.submission)


    def report(self):
        """
            #report = get_peer_grading_data(reviewer, feedback_phase)

        """

        # Intentionally put the order_by here, to ensure that any errors in the
        # next part of the code (zip-ordering) are highlighted
        r_item_actuals = self.ritemactual_set.all().order_by('-modified')

        # Ensure the ``r_item_actuals`` are in the right order. These 3 lines
        # sort the ``r_item_actuals`` by using the ``order`` field on the
        # associated ``ritem_template`` instance.
        # I noticed that in some peer reviews the order was e.g. [4, 1, 3, 2]
        r_item_template_order = (i.ritem_template.order for i in r_item_actuals)
        zipped = list(zip(r_item_actuals, r_item_template_order))
        r_item_actuals, _ = list(zip(*(sorted(zipped, key=lambda x: x[1]))))

        has_prior_answers = False
        for item in r_item_actuals:
            item.results = {'score': None, 'max_score': None}
            item_template = item.ritem_template


            item.options = item_template.roptiontemplate_set.all()\
                                                             .order_by('order')
            #item.options = ROptionTemplate.objects.filter(\
            #                         rubric_item=item_template).order_by('order')

            for option in item.options:
                #prior_answer = ROptionActual.objects.filter(roption_template=option,
                #                                            ritem_actual=item,
                #                                            submitted=True)
                prior_answer = option.roptionactual_set.filter(submitted=True,
                                                              ritem_actual=item)
                if prior_answer.count():
                    has_prior_answers = True
                    if item_template.option_type in ('DropD', 'Chcks', 'Radio'):
                        option.selected = True
                        item.results['score'] = option.score
                        item.results['max_score'] = item_template.max_score
                    elif item_template.option_type == 'LText':
                        option.prior_text = prior_answer[0].comment




            # Store the peer- or self-review results in the item; to use in the
            # template to display the feedback.
            #item.results = report.get(item_template, [[], None, None, None, []])


            # Each key/value in the dictionary stores a list. The list has 5
            # elements:
            #   1. [list of raw scores] {or comments from peers}
            #   2. the maximum for this item,
            #   3. the average for this learner for this item
            #   4. the class average (not used at the moment)
            #   5. the comments from the instructor or TA (if any)

            # Randomize the comments and numerical scores before returning.
            #shuffle(item.results[0])
            #if item_template.option_type == 'LText':
            #    item.results[0] = '\n----------------------\n'.join(item.results[0])
            #    item.results[4] = '\n'.join(item.results[4])

        return r_item_actuals, has_prior_answers


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
    num_rows = models.PositiveSmallIntegerField(default=10,
                    help_text='Height of field, if it is a text box.')

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
        return u'[{0}] {1}. {2}'.format(self.r_template,
                                        self.order,
                                        self.criterion[0:50])


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
    order = models.IntegerField(help_text='Start from 1 and work upwards.')
    # NOTE: the ``order`` is ignored for type ``LText``, as there will/should
    #       only be 1 of those per Item.


    def save(self, *args, **kwargs):
        """ Override the model's saving function to do some checks """
        self.score = float(self.score)
        assert(self.order > 0)
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