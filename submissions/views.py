# Django imports
from django.conf import settings

# Python and 3rd party tool imports
import os
import magic
from PyPDF2 import PdfFileReader

# Import from our other apps
from utils import get_IP_address, generate_random_token, send_email

# Imports from this app
from submissions.models import Submission

# Logging
import logging
logger = logging.getLogger(__name__)


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
    #if entry_point.uses_groups:
        # NOTE: an error condition can develop if a learner isn't
        #       allocated into a group, and you are using group submissions.

    #    pass
        # TODO
        #if search_earlier:

            ## NOTE: will only get submissions for a phase LTE (less than and
            ##       equal) to the current ``phase``.

            #subs = subs.filter(phase__order__lte=phase.order,
                               #group_submitted=grp_info['group_instance'])\
                                                #.order_by('-datetime_submitted')
        #else:
            ## This will only get it in the exact phase required
            #subs = subs.filter(phase__order=phase.order,
                               #group_submitted=grp_info['group_instance'])\
                                                            #.order_by('-datetime_submitted')
    #else:
        # Individual submission
    #    subs = subs.filter(submitted_by=learner).order_by('-datetime_submitted')


    # Just use this for now.
    subs = subs.filter(submitted_by=learner).order_by('-datetime_submitted')


    if subs:
        return subs[0]
    else:
        return None


def create_thumbnail():


    if len(files) == 1:
        filename = files[0].name
        extension = filename.split('.')[-1].lower()
        submitted_file_name_django = 'uploads/{0}/{1}'.format(entry_point.id,
                    generate_random_token(token_length=16) + '.' + extension)
        full_path = base_dir_for_file_uploads + submitted_file_name_django
        with open(full_path, 'wb+') as dst:
            for chunk in files[0].chunks():
                dst.write(chunk)

    elif trigger.allow_multiple_files:
        joint_file_name = ''
        logger.debug('Processing uploads: ' + str(files))
        for f_to_process in files:
            filename = f_to_process.name
            extension = filename.split('.')[-1].lower()
            joint_file_name += '.'.join(filename.split('.')[0:-1])

            with open(thumbnail_dir + filename, 'wb+') as dst:
                for chunk in f_to_process.chunks():
                    dst.write(chunk)

        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.units import cm
        full_path = base_dir_for_file_uploads + 'uploads/{0}/{1}'.format(
            entry_point.id, generate_random_token(token_length=16) + '.pdf')

        try:
            c = canvas.Canvas(full_path, pagesize=A4, )
            c.setPageSize(landscape(A4))
            for f_to_process in files:
                c.setFont("Helvetica", 14)
                c.drawString(10, 10, f_to_process.name)
                c.drawImage(thumbnail_dir + f_to_process.name,
                            x=cm*1, y=cm*1,
                            width=cm*(29.7-2), height=cm*(21-2), mask=None,
                            preserveAspectRatio=True, anchor='c')
                c.showPage()
            c.save()
        except IOError as exp:
            logger.error('Exception: ' + str(exp))
            # TODO: raise error message

        for f_to_process in files:
            filename = f_to_process.name
            # Delete: thumbnail_dir + filename


        submitted_file_name_django = full_path.split(base_dir_for_file_uploads)[1]
        extension = 'pdf'
        filename = joint_file_name[0:251] + '.' + extension



    group_members = get_group_information(learner, entry_point.gf_process)


    if (group_members['group_instance'] is None) and (entry_point.uses_groups\
                                                      ==False):
        # Uses individual submissions:
        prior = Submission.objects.filter(status='S',
                                          submitted_by=learner,
                                entry_point=entry_point,
                                trigger=trigger,
                                is_valid=True)

    else:
        # Has this group submitted this before?
        prior = Submission.objects.filter(status='S',
                                group_submitted=group_members['group_instance'],
                                entry_point=entry_point,
                                trigger=trigger,
                                is_valid=True)

    if prior:
        for item in prior:
            logger.debug('Set old submission False: {0} and name "{1}"'.format(\
                str(item), item.submitted_file_name))
            item.is_valid = False
            item.save()

    strike1 = False
    if 'pdf' in trigger.accepted_file_types_comma_separated.lower():
        try:
            mime = magic.from_file(full_path, mime=True).decode('utf-8')
        except Exception as exp:
            logger.error('Could not determine MIME type: ' + str(exp))
            strike1 = True

        if 'application/pdf' not in mime.lower():
            strike1 = True

        if strike1:
            logger.debug('Invalid upload: {0} [{1}]'.format(mime,
                                                            full_path))
            return None, 'Invalid file upload. Uploaded file must be a PDF.'

    # Make the thumbnail of the PDF -> PNG
    strike2 = False
    try:
        from wand.image import Image
        imageFromPdf = Image(filename=full_path)
        image = Image(width=imageFromPdf.width, height=imageFromPdf.height)
        image.composite(imageFromPdf.sequence[0], top=0, left=0)
        image.format = "png"
        thumbnail_filename = submitted_file_name_django.split('uploads/{0}/'.format(entry_point.id))[1]
        thumbnail_full_name = thumbnail_dir + \
            thumbnail_filename.replace('.'+extension,
                                                               '.png')
        thumbnail_file_name_django = 'uploads/{0}/tmp/{1}'.format(entry_point.id,
                                                                  thumbnail_filename.replace('.'+extension, '.png'))


        image.save(filename=thumbnail_full_name)

    except Exception as exp:
        strike2 = True
        logger.error('Exception for thumbnail: ' + str(exp))
        thumbnail_file_name_django = None

    if strike2:
        return None, 'Invalid file upload. Uploaded file must be a PDF.'


    sub = Submission(submitted_by=learner,
                     group_submitted=group_members['group_instance'],
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


    # Sending email for submissions has now been moved to the calling
    # ``Trigger`` instance.

    #if group_members['group_name']:
        #address = group_members['member_email_list']
        #first_line = 'You, or someone in your group,'
        #extra_line = ('That is why all members in your group will receive '
                      #'this message.')
    #else:
        #address = [learner.email, ]
        #first_line = 'You'
        #extra_line = ''

    #message = ('{0} have successfully submitted a document for: {1}.\n'
               #'This is for the course: {2}.\n'
               #'\n'
               #'You may submit multiple times, up to the deadline. Only the '
               #'most recent submission is kept. {3}\n'
               #'\n--\n'
               #'This is an automated message. Please do not reply to this '
               #'email address.\n')
    #message = message.format(first_line, entry_point.LTI_title,
                             #entry_point.course.name,
                             #extra_line)

    #if trigger.send_email_on_success:
        #logger.debug('Sending email: {0}'.format(address))
        #subject = trigger.name + ' for peer review: successfully submitted'
        #out = send_email(address, subject, message)
        #logger.debug('Number of emails sent (should be 1): {0}'.format(out[0]))




def upload_submission(request, learner, entry_point, trigger, no_thumbnail=True):
    """
    Handles the upload of the user's submission.
    """
    base_dir_for_file_uploads = settings.MEDIA_ROOT
    thumbnail_file_name_django = ''

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



    group_members = None #get_group_information(learner, entry_point.gf_process)
    group_members = {'group_instance': None}
    if (group_members['group_instance'] is None) and (entry_point.uses_groups\
                                                      ==False):
        # Uses individual submissions:
        prior = Submission.objects.filter(status='S',
                                            submitted_by=learner,
                                            entry_point=entry_point,
                                            trigger=trigger,
                                            is_valid=True
                                         )

    else:
        # Has this group submitted this before?
        prior = Submission.objects.filter(status='S',
                                group_submitted=group_members['group_instance'],
                                entry_point=entry_point,
                                trigger=trigger,
                                is_valid=True)

    if prior:
        for item in prior:
            logger.debug(('Setting prior submission to False: {0} and name '
                          '"{1}"'.format(str(item), item.submitted_file_name)))
            item.is_valid = False
            item.save()

    sub = Submission(submitted_by=learner,
                     group_submitted=group_members['group_instance'],
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


    if group_members['group_instance']:
        address = group_members['member_email_list']
        first_line = 'You, or someone in your group,'
        extra_line = ('That is why all members in your group will receive '
                      'this message.')
    else:
        address = [learner.email, ]
        first_line = 'You'
        extra_line = ''

    message = ('{0} have successfully submitted a document for: {1}.\n'
               'This is for the course: {2}.\n'
               '\n'
               'You may submit multiple times, up to the deadline, or until '
               'your report is sent out for peer review. Only the most recent '
               'submission is kept. {3}\n'
               '\n--\n'
               'This is an automated message. Please do not reply to this '
               'email address. It will not be received by anyone.\n')
    message = message.format(first_line, entry_point.LTI_title,
                             entry_point.course.name,
                             extra_line)

    if trigger.send_email_on_success:
        logger.debug('Sending email: {0}'.format(address))
        subject = trigger.name + ' for peer review: successfully submitted'
        out = send_email(address, subject, message)
        logger.debug('Number of emails sent (should be 1): {0}'.format(out[0]))

    return sub