from django.db import models
from django.utils.timezone import now
from datetime import timedelta

def get_submit_deadline():
    return now() + timedelta(days=10)

def get_deadline():
    return now() + timedelta(days=20)

class KeyTermSetting(models.Model):
    class Meta:
        verbose_name = "Key Term Setting"
        verbose_name_plural = "Key Term Settings"

    keyterm = models.CharField(max_length=200)
    entry_point = models.ForeignKey('basic.EntryPoint')
    max_thumbs = models.PositiveSmallIntegerField(default=3,
                    help_text='Maximum number of thumbs up that can be awarded')
    min_submissions_before_voting = models.PositiveSmallIntegerField(default=10,
            help_text='Minimum number of submissions before voting can start.')
    deadline_for_submission = models.DateTimeField(default=get_submit_deadline)
    deadline_for_voting = models.DateTimeField(default=get_deadline)
    terms_per_page = models.PositiveIntegerField(default=100,
            help_text='Number of terms shown per page.')


    def __str__(self):
        return u'{0}: deadline = {1}'.format(self.keyterm,
                                             self.deadline_for_voting)


class KeyTermTask(models.Model):
    """
    The details that 1 learner has filled in for 1 keyterm.
    """
    class Meta:
        verbose_name = "Key Term Task"
        verbose_name_plural = "Key Term Tasks"

    keyterm = models.ForeignKey(KeyTermSetting)
    learner = models.ForeignKey('basic.Person')
    image_raw = models.ForeignKey('submissions.Submission',
                                  blank=True, null=True)
    image_modified = models.ImageField(blank=True, null=True)
    image_thumbnail = models.ImageField(blank=True, null=True)
    last_edited = models.DateTimeField(auto_now=True, auto_now_add=False)


    definition_text = models.TextField(blank=True, null=True,
                                       help_text='Capped at 500 characters.')
    explainer_text = models.TextField(blank=True, null=True)
    reference_text = models.CharField(max_length=250, blank=True, null=True)


    is_in_draft = models.BooleanField(help_text=('User is in draft mode'),
                                      default=False)
    is_in_preview = models.BooleanField(help_text=('Preview mode'),
                                      default=False)
    is_finalized = models.BooleanField(help_text=('User has submitted, and it '
                                                  'is after the deadline'),
                                       default=False)
    is_submitted = models.BooleanField(help_text=('User has submitted'),
                                       default=False)
    allow_to_share = models.BooleanField(help_text=('Student is OK to share '
                                                    'their work with class.'),
                                         default=True)


    def __str__(self):
        return u'[{0}][{1}] on {2:%Y-%m-%d %H:%M}'.format(\
            self.keyterm, self.learner.initials, self.last_edited)


    def save(self, *args, **kwargs):
        if self.definition_text and (len(self.definition_text)>=500):
            self.definition_text = self.definition_text[0:501] + ' ...'

        super(KeyTermTask, self).save(*args, **kwargs)


class Thumbs(models.Model):
    """
    Rating for each submission.
    """
    class Meta:
        verbose_name = "Thumbs up"
        verbose_name_plural = "Thumbs up"

    keytermtask = models.ForeignKey(KeyTermTask)
    voter = models.ForeignKey('basic.Person')
    awarded = models.BooleanField(default=False)
    last_edited = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return u'Thumb up by [{0}] for {1}'.format(self.voter,
                                                   self.keyterm_task)


