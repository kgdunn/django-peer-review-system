# Django imports
from django.conf import settings
from django.db.models import Q

# Python and 3rd party tool imports
import os
import magic
import shutil
import tempfile
from PyPDF2 import PdfFileReader, PdfFileMerger

# Import from our other apps
from utils import get_IP_address, generate_random_token, load_kwargs
from basic.models import GroupEnrolled

# Imports from this app
from submissions.models import Submission

# Logging
import logging
logger = logging.getLogger(__name__)

def is_group_submission(learner, entry_point):
    """
    Is this for a group submission?

    If so, it also "abuses" the group_enrolled object to add a
    ``group_members`` field that contains a list of the learner's group members.
    The learner will also be one of the entries in that list.
    """
    # Is this for a group submission?
    if entry_point.uses_groups and not(entry_point.only_review_within_group):
        # Very specific type of group formation: students work in groups to
        # submit their document, but their document is ONLY reviewed by
        # learners outside their groups.
        gfp = entry_point.gf_process

        # If this fails it is either becuase the user is not enrolled in a
        # ``gfp`` for this course

        # NOTE: an error condition can develop if a learner isn't
        #       allocated into a group, and you are using group submissions.
        try:
            group_enrolled = learner.groupenrolled_set.get(is_enrolled=True,
                                            group__gfp=entry_point.gf_process)
            group_enrolled.group_members = [g.person for g in \
                               group_enrolled.group.groupenrolled_set.all()]
            load_kwargs(group_enrolled.group, target_obj=group_enrolled)

            return group_enrolled
        except GroupEnrolled.DoesNotExist:
            return None
    else:
        return None


def get_submission(learner, trigger, entry_point=None):

    """
    Gets the ``submission`` instance at the particular ``trigger`` in the
    process.
    Allow some flexibility in the function signature here, to allow retrieval
    via the ``entry_point`` in the future.
    """
    submission = None
    subs = trigger.submission_set.filter(is_valid=True).\
                                               order_by('-datetime_submitted')

    if is_group_submission(learner, entry_point):
        # At this point it means the user is part of a group, so the
        # document can be overwritten by another member of the group.
        # So ``subs`` should not be limited to only the learner, but also
        # all learners in that group.
        group_enrolled = is_group_submission(learner, entry_point)
        subs = subs.filter(group_submitted=group_enrolled.group)
    else:
        # Just use this for now.
        subs = subs.filter(submitted_by=learner)
    if subs:
        return subs[0]
    else:
        return None


def upload_submission(request, learner, trigger, no_thumbnail=True):
    """
    Handles the upload of the user's submission.
    """
    base_dir_for_file_uploads = settings.MEDIA_ROOT
    thumbnail_file_name_django = ''
    entry_point = trigger.entry_point

    files = request.FILES.getlist('file_upload', None)
    if files is None:
        return None

    # Is the storage space reachable?
    deepest_dir = base_dir_for_file_uploads + 'uploads/{0}/tmp/'.format(
        entry_point.id)

    try:
        os.makedirs(deepest_dir)
    except OSError:
        if not os.path.isdir(deepest_dir):
            logger.error('Cannot create directory for upload: {0}'.format(
                deepest_dir))
            raise

    if len(files) == 1:
        filename = files[0].name
        extension = filename.split('.')[-1].lower()
        submitted_file_name_django = 'uploads/{0}/{1}'.format(entry_point.id,
                      generate_random_token(token_length=16) + '.' + extension)
        full_path = base_dir_for_file_uploads + submitted_file_name_django
        with open(full_path, 'wb+') as dst:
            for chunk in files[0].chunks():
                dst.write(chunk)


        f_size = os.path.getsize(full_path)
        if f_size > trigger.max_file_upload_size_MB * 1024 * 1024:
            logger.warning('File too large {0}'.format(
                                                    submitted_file_name_django))
            return None, ('File too large ({0} MB); it must be less than '
                    '{1} MB.'.format(round(float(f_size/1024.0/1024.0), 1),
                                    trigger.max_file_upload_size_MB))


    else:  #if trigger.allow_multiple_files: this is removed for now
        filename = ''
        extension = ''
        submitted_file_name_django = ''
        full_path = ''


    # Check that the file format is PDF, if that is required.
    strike1 = False
    if 'pdf' in trigger.accepted_file_types_comma_separated.lower() and \
       extension in ('pdf',):
        try:
            mime = magic.from_file(full_path, mime=True)
            if not(isinstance(mime, str)):
                mime = mime.decode('utf-8')
        except Exception as exp:
            logger.error('Could not determine MIME type: ' + str(exp))
            mime = ''
            strike1 = True

        if 'application/pdf' not in mime.lower():
            strike1 = True

        if strike1:
            logger.debug('Invalid PDF upload: {0} [{1}]'.format(mime,
                                                            full_path))
            return None, 'Invalid file uploaded. Uploaded file must be a PDF.'

        doc = PdfFileReader(full_path)
        if doc.isEncrypted:
            logger.debug('Encrypted PDF upload: {0}'.format(full_path))
            return None, ('An encrypted PDF cannot be uploaded. Please remove '
                          'the encryption and try again.')


    strike1 = False
    if (('jpeg' in trigger.accepted_file_types_comma_separated.lower()) or \
       ('jpg' in trigger.accepted_file_types_comma_separated.lower())) and \
       extension in ('jpg', 'jpeg'):

        try:
            mime = magic.from_file(full_path, mime=True)
            if not(isinstance(mime, str)):
                mime = mime.decode('utf-8')
        except Exception as exp:
            logger.error('Could not determine MIME type: ' + str(exp))
            mime = ''
            strike1 = True

        if 'image/jpeg' not in mime.lower():
            strike1 = True

        if strike1:
            logger.debug('Invalid JPG upload: {0} [{1}]'.format(mime,
                                                            full_path))
            return None, ('Invalid file. Uploaded image should be a valid '
                          'and readable JPEG file.')


    strike1 = False
    if ('png' in trigger.accepted_file_types_comma_separated.lower()) and \
       extension in ('png',):

        try:
            mime = magic.from_file(full_path, mime=True)
            if not(isinstance(mime, str)):
                mime = mime.decode('utf-8')
        except Exception as exp:
            logger.error('Could not determine MIME type: ' + str(exp))
            mime = ''
            strike1 = True

        if 'image/png' not in mime.lower():
            strike1 = True

        if strike1:
            logger.debug('Invalid PNG upload: {0} [{1}]'.format(mime,
                                                                full_path))
            return None, ('Invalid file. Uploaded image should be a valid '
                          'and readable PNG file.')


    strike2 = False
    if extension.lower() not in \
                            trigger.accepted_file_types_comma_separated.lower():
        logger.debug('Invalid file type upload: received ".{0}"; [{1}]'.format(\
                                                    extension, full_path))
        return None, ('Invalid file uploaded. Uploaded file must be: {}'.format(\
                                 trigger.accepted_file_types_comma_separated))


    if trigger == entry_point:
        # In some instances we don't use triggers, just entry_points
        prior = Submission.objects.filter(status='S',
                                          submitted_by=learner,
                                          entry_point=entry_point,
                                          is_valid=True
                                        )
    else:
        prior_indiv = Q(status='S', submitted_by=learner, entry_point=entry_point,
                  trigger=trigger, is_valid=True)

        # We need this here, but also for the code later in the next
        # if (trigger==entry_point) part

        # Default returned by this function is ``None`` if the user is not
        # enrolled in a group, or if this course simply does not use groups.
        group_submitted = is_group_submission(learner, entry_point)
        if is_group_submission(learner, entry_point):
            group_submitted = group_submitted.group

            prior_group = Q(status='S', group_submitted=group_submitted,
                            entry_point=entry_point, trigger=trigger,
                            is_valid=True)
        else:
            prior_group = Q()

        prior = Submission.objects.filter(prior_indiv | prior_group)


    for item in prior:
        logger.debug(('Setting prior submission to False: {0} and name '
                      '"{1}"'.format(str(item), item.submitted_file_name)))
        item.is_valid = False
        item.save()


    if trigger == entry_point:
        # In some instances we don't use triggers, just entry_points
        sub = Submission(submitted_by=learner,
                         group_submitted=None,
                         status='S',
                         entry_point=entry_point,
                         is_valid=True,
                         file_upload=submitted_file_name_django,
                         thumbnail=thumbnail_file_name_django,
                         submitted_file_name=filename,
                         ip_address=get_IP_address(request),
                         )
        sub.save()
    else:

        sub = Submission(submitted_by=learner,
                             group_submitted=group_submitted,
                             status='S',
                             entry_point=entry_point,
                             trigger=trigger,
                             is_valid=True,
                             file_upload=submitted_file_name_django,
                             thumbnail=thumbnail_file_name_django,
                             submitted_file_name=filename,
                             ip_address=get_IP_address(request),
                             )
        sub.save()

    if 'pdf' in trigger.accepted_file_types_comma_separated.lower() and \
                                                         extension in ('pdf',):
        clean_PDF(sub)

    return sub


def clean_PDF(submission):
    """
    Strips out any personal information in the PDF.
    """
    src = submission.file_upload.file.name
    pdf1 = PdfFileReader(src)
    merger = PdfFileMerger(strict=False, )
    merger.append(pdf1, import_bookmarks=False)
    merger.addMetadata({'/Title': '',
                        '/Author': '',
                        '/Creator': '',
                        '/Producer': ''})
    fd, temp_file = tempfile.mkstemp(suffix='.pdf')
    merger.write(temp_file)
    merger.close()
    os.close(fd)
    shutil.move(temp_file, src) # replace the original PDF on the server