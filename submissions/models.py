from django.db import models
#from django.utils import timezone
from utils import generate_random_token
import os

def peerreview_directory_path(instance, filename, randomize=True):
    """
    The file will be uploaded to MEDIA_ROOT/uploads/nnn/<filename>
    """
    if '.' not in filename:
        filename = filename + '.'
    extension = filename.split('.')[-1].lower()
    if randomize:
        filename = generate_random_token(token_length=16) + '.' + extension
    else:
        filename = ''.join(filename.split('.')[0:-1]) + '.' + extension
    return '{0}{1}{2}{1}{3}'.format('uploads',
                                    os.sep,
                                    instance.entry_point.id,
                                    filename)
class Submission(models.Model):
    """
    An instance of a submission for a learner/group of learners.

    Old files are kept, but not available for download.<-- remove old submissions

    Show submissions for people in the same group in top/bottom order
    Allow multiple uploads till submission deadline is reached.
    """
    STATUS = (('S', 'Submitted'),
              ('T', 'Submitted late'),
              ('F', 'Finished'),
              ('G', 'Being peer-reviewed/graded'),
              ('N', 'Nothing submitted yet'),
              ('A', 'Automated (internal)'),
              ('X', 'File has been deleted from webserver'),
              )

    submitted_by = models.ForeignKey('basic.Person')
    group_submitted = models.ForeignKey('basic.Group', blank=True, null=True,
        default=None, help_text="If a group submission, it links back to it.")


    # ``status`` is probably not used in the old code, and definitely not in
    # the new version
    status = models.CharField(max_length=2, choices=STATUS, default='N')


    entry_point = models.ForeignKey('basic.EntryPoint',
                                    verbose_name="Entry point")

    # By eliminating ``phase`` (which is now replaced by ``Trigger``) we might
    # be limiting ourselves to one submission per EntryPoint. Confirm still.
    trigger = models.ForeignKey('interactive.Trigger',
                              verbose_name="Attached with which Trigger",
                              default=None, null=True) #to allow migrations

    is_valid = models.BooleanField(default=False,
        help_text=('Valid if: it was submitted on time, or if this is the most '
                   'recent submission (there might be older ones).'))
    file_upload = models.FileField(upload_to=peerreview_directory_path)
    thumbnail = models.FileField(upload_to=peerreview_directory_path,
                                 blank=True, null=True)
    submitted_file_name = models.CharField(max_length=255, default='')

    ip_address = models.GenericIPAddressField(blank=True, null=True)
    datetime_submitted = models.DateTimeField(auto_now_add=True,
        verbose_name="Date and time the learner/group submitted.")

    def __str__(self):
        return '[{0}]: {1}'.format(self.submitted_by,
                                   self.submitted_file_name)
