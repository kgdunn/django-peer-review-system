from django.db import models


class GradeBook(models.Model):
    """
    A gradebook for a course.
    """
    course = models.ForeignKey('basic.Course')
    passing_value = models.DecimalField(max_digits=5, decimal_places=2,
                                        help_text="A value between 0 and 100.")
    max_score = models.DecimalField(max_digits=5, decimal_places=2, default=100,
        help_text="A value between 0 and 100. Normally this is 100.0")
    last_updated = models.DateTimeField()
    def __str__(self):
        return 'Gradebook: {0} [{1}/{2}]'.format(self.course,
                                                 self.passing_value,
                                                 self.max_score)

# Our models for the phases uses ideas from:
# https://docs.djangoproject.com/en/1.10/topics/db/models/#model-inheritance
class GradeCategory(models.Model):
    """
    A category contains one or more GradeItems. A gradebook consists of
    GradeCategories.
    A GradeItem must be a child of GradeCategory, which is a child of the
    Gradebook.
    """
    class Meta:
        verbose_name = 'Grade category'
        verbose_name_plural = 'Grade categories'

    gradebook = models.ForeignKey(GradeBook)
    order = models.PositiveSmallIntegerField(
        help_text="Which column order is this item")
    display_name = models.CharField(max_length=250, default='Assignment ...')
    max_score = models.DecimalField(max_digits=5, decimal_places=2, default=100,
        help_text="The largest value a student can achieve for this item")
    weight = models.DecimalField(max_digits=4, decimal_places=3,
            help_text='The weight of this item; a value between 0.0 and 1.0')
    spread_evenly = models.BooleanField(default=True,
        help_text=("Spread weight across all items evenly. If 'True': no need "
                   "to specify weights on the GradeItems. "))

    def __str__(self):
        return '{0}. Category: {1} [wt={2}%]'.format(self.order,
                                                    self.display_name,
                                                    self.weight*100)


class GradeItem(models.Model):
    """
    An item in the gradebook. Each gradebook consists of one or more items
    (columns) in the gradebook.
    """
    category = models.ForeignKey(GradeCategory, blank=True, null=True)
    entry_point = models.ForeignKey('basic.EntryPoint', blank=True, null=True)
    order = models.PositiveSmallIntegerField(default=1,
        help_text="Which column order is this item")
    display_name = models.CharField(max_length=250, default='Assignment ...')
    max_score = models.DecimalField(max_digits=5, decimal_places=2, default=100,
        help_text="The largest value a student can achieve for this item")
    link = models.CharField(max_length=600, blank=True,
           help_text=("The link to the page where the student can complete "
                      "this; begin link after the base URL: /courseware/..."))
    weight = models.DecimalField(max_digits=4, decimal_places=3, default=-1.0,
                                 blank=True,
            help_text=('The weight of this item; a value between 0.0 and 1.0. '
                    'If weight=-1.0, then the weight is determined by the '
                    'category, which will assign equal weight to all items.'))
    droppable = models.BooleanField(default=False)


    def __str__(self):
        return '{0}. Item: {1}'.format(self.order, self.display_name)


class LearnerChecklistTemplate(models.Model):
    """
    A sequence of events that learners must/should complete.
    """
    category = models.ForeignKey(GradeCategory)
    item_name = models.CharField(max_length=50)  # e.g. reviewed_peer
    order = models.PositiveSmallIntegerField(default=0)


class LearnerChecklistItem(models.Model):
    learner = models.ForeignKey('basic.Person')
    checklist = models.ForeignKey(LearnerChecklistTemplate)
    done = models.BooleanField()

    def has(self):
        """
        Allows constructions in the code, such as:
        >> learner.has['reviewed_peer']
        >> learner.has['submitted']

        Where, in the LearnerChecklistTemplate we have defined an instance
        with ``item_name`` of "reviewed_peer" or "submitted", which is
        associated with a numeric ``order`` value too.
        """
        self.checklist



class LearnerGrade(models.Model):
    """
    A grade for the learner.
    """
    gitem = models.ForeignKey(GradeItem)
    learner = models.ForeignKey('basic.Person')
    value = models.DecimalField(max_digits=7, decimal_places=3, blank=True,
                                null=True,
        help_text="The grade earned by the learner. Between 0.0 and 100.0")
    not_graded_yet = models.BooleanField(default=True,
            help_text="If this item is not yet graded/submitted/etc")
    modfied_dt = models.DateTimeField(auto_now=True)

    def __str__(self):
        return '[{0}/{1}] for {2}'.format(self.value,
                                          self.gitem.max_score,
                                          self.learner)


    def save(self, *args, **kwargs):
        if kwargs.pop('push', False):
            # Put code here to push the grades to Brightspace
            pass
        super(LearnerGrade, self).save(*args, **kwargs)

