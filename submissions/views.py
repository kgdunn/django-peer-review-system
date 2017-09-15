# Django imports
from django.conf import settings

# Python and 3rd party tool imports
import os
import magic
import shutil
import tempfile
from PyPDF2 import PdfFileReader, PdfFileMerger

# Import from our other apps
from utils import get_IP_address, generate_random_token

# Imports from this app
from submissions.models import Submission

# Logging
import logging
logger = logging.getLogger(__name__)

# Debugging
import wingdbstub

def get_submission(learner, trigger, entry_point=None):

    """
    Gets the ``submission`` instance at the particular ``trigger`` in the
    process.
    Allow some flexibility in the function signature here, to allow retrieval
    via the ``entry_point`` in the future.
    """
    # Whether or not we are submitting, we might have a prior submission
    # to display
    #grp_info = {}
    #if phase:
    #    grp_info = get_group_information(learner, phase.pr.gf_process)


    submission = None
    subs = Submission.objects.filter(is_valid=True, trigger=trigger)


    #if entry_point.uses_groups:  <-- removed this for version 2
        # NOTE: an error condition can develop if a learner isn't
        #       allocated into a group, and you are using group submissions.


    # Just use this for now.
    subs = subs.filter(submitted_by=learner).order_by('-datetime_submitted')


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


    elif trigger.allow_multiple_files:
        # Refer to prior code: this is removed for now
        filename = ''
        extension = ''
        submitted_file_name_django = ''
        full_path = ''


    # Check that the file format is PDF, if that is required.
    strike1 = False
    if 'pdf' in trigger.accepted_file_types_comma_separated.lower():
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
            return None, 'Invalid file upload. Uploaded file must be a PDF.'

        doc = PdfFileReader(full_path)
        if doc.isEncrypted:
            logger.debug('Encrypted PDF upload: {0}'.format(full_path))
            return None, ('An encrypted PDF cannot be uploaded. Please remove '
                          'the encryption and try again.')

    strike2 = False
    if extension.lower() not in \
                            trigger.accepted_file_types_comma_separated.lower():
        logger.debug('Invalid file type upload: expected {0}; [{1}]'.format(\
                                                    extension, full_path))
        return None, ('Invalid file upload. Uploaded file must be: {}'.format(\
                                 trigger.accepted_file_types_comma_separated))


    # Uses individual submissions:
    prior = Submission.objects.filter(status='S',
                                      submitted_by=learner,
                                      entry_point=entry_point,
                                      trigger=trigger,
                                      is_valid=True
                                    )

    for item in prior:
        logger.debug(('Setting prior submission to False: {0} and name '
                      '"{1}"'.format(str(item), item.submitted_file_name)))
        item.is_valid = False
        item.save()

    sub = Submission(submitted_by=learner,
                     group_submitted=None,
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