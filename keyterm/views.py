from django.http import HttpResponse
from django.shortcuts import render
from django.conf import settings

# Python import
import os
from random import shuffle

# This app's imports
from .models import KeyTermSetting, KeyTermTask
from .forms import UploadFileForm_file_optional, UploadFileForm_file_required

# 3rd party imports: image rendering
import PIL
from PIL import ImageFont, Image, ImageDraw

# Import from our other apps
from utils import generate_random_token

#from submissions.models import Submission
from submissions.views import upload_submission
from basic.views import entry_point_discovery
from grades.views import push_grade


# Logging
import logging
logger = logging.getLogger(__name__)

def start_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """
    prior = learner.keytermtask_set.filter(keyterm__entry_point=entry_point)
    if prior.count():
        keytermtask = prior[0]
        keyterm = keytermtask.keyterm
    else:
        # Create the new KeyTermTask for this learner
        try:
            keyterm = KeyTermSetting.objects.get(entry_point=entry_point)
        except KeyTermSetting.DoesNotExist:
            return HttpResponse(('Please add KeyTermSetting to database first; '
                                 "and don't forget to add the GradeItem too."))
        keytermtask = KeyTermTask(keyterm=keyterm,
                                  learner=learner,
                                  definition_text='',
                                  explainer_text='',
                                  reference_text='',
                                  is_in_draft=True
                                  )
        keytermtask.save()

    if request.POST.get('preview-keyterm', ''):
        return preview_keyterm(request, course, learner, entry_point)

    if request.POST.get('draft-keyterm', ''):
        return draft_keyterm(request, course, learner, entry_point)

    if request.POST.get('submit-keyterm', ''):
        return submit_keyterm(request, course, learner, entry_point)

    if request.POST.get('finalize-keyterm', '') or keytermtask.is_finalized:
        return finalize_keyterm(request, course, learner, entry_point)

    # If nothing else (usually the first time we start, we start with drafting)
    return draft_keyterm(request, course, learner, entry_point)


def draft_keyterm(request, course=None, learner=None, entry_point=None,
                  error_message=''):
    """
    The user is in Draft mode: adding the text
    """
    prior = learner.keytermtask_set.filter(keyterm__entry_point=entry_point)
    if prior.count():
        keytermtask = prior[0]
        keyterm = keytermtask.keyterm
    else:
        try:
            keyterm = KeyTermSetting.objects.get(entry_point=entry_point)
        except KeyTermSetting.DoesNotExist:
            logger.error('Draft: An error occurred. [{0}]'.format(learner))
            return HttpResponse('An error occurred.')

    # We have 4 states: set the correct settings (in case page is reloaded here)
    keytermtask.is_in_draft = True
    keytermtask.is_in_preview = False
    keytermtask.is_submitted = False
    keytermtask.is_finalized = False
    keytermtask.save()


    # TODO: Reference should also be shown

    if keytermtask.image_raw:
        entry_point.file_upload_form = UploadFileForm_file_optional()
    else:
        entry_point.file_upload_form = UploadFileForm_file_required()


    # TODO: real-time saving of the text as it is typed??

    if keytermtask.reference_text == '<no reference>':
        keytermtask.reference_text = ''

    ctx = {'error_message': error_message,
           'keytermtask': keytermtask,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           'grade_push_url': request.POST.get('lis_outcome_service_url', '')
           }
    return render(request, 'keyterm/draft.html', ctx)


def preview_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """

    prior = learner.keytermtask_set.filter(keyterm__entry_point=entry_point)
    if prior.count():
        keytermtask = prior[0]
        keyterm = keytermtask.keyterm
    else:
        try:
            keyterm = KeyTermSetting.objects.get(entry_point=entry_point)
        except KeyTermSetting.DoesNotExist:
            logger.error('Preview: An error occurred. [{0}]'.format(learner))
            return HttpResponse('An error occurred.')

    # 1. Now you have the task ``keytermtask``: set state
    # 2. Store new values in the task
    # 3. Process the image (store it too, but only in staging area)
    # 4. Render the template image  (store it too, but only in staging area)
    # 5. Float the submit buttons left and right of each other

    # We have 4 states: set the correct settings (in case page is reloaded here)
    keytermtask.is_in_draft = True   # intentional
    keytermtask.is_in_preview = True
    keytermtask.is_submitted = False
    keytermtask.is_finalized = False


    # For the ``Submission`` app we need a Trigger. We don't have that, or
    # need it. So abuse ``entry_point`` as the trigger instead.
    # A ``trigger`` needs an entry_point field, so just refer back to itself.
    entry_point.entry_point = entry_point
    entry_point.accepted_file_types_comma_separated = 'JPEG, PNG, JPG'
    entry_point.max_file_upload_size_MB = 5
    entry_point.send_email_on_success = False

    # Get the (prior) image submission
    submission = prior_submission = None
    subs = learner.submission_set.filter(is_valid=True, entry_point=entry_point)
    subs = subs.order_by('-datetime_submitted')
    if subs.count():
        submission = prior_submission = subs[0]


    error_message = ''
    if request.FILES:

        submit_inst = upload_submission(request, learner, trigger=entry_point,
                                        no_thumbnail=False)

        if isinstance(submit_inst, tuple):
            # Problem with the upload
            error_message = submit_inst[1]
            submission = prior_submission
        else:
            # Successfully uploaded a document
            error_message = ''
            submission = submit_inst

        # Now that the image is processed:
        keytermtask.image_raw = submission


    definition_text = request.POST.get('keyterm-definition', '')
    definition_text = definition_text or '<no definition>'
    definition_text = definition_text.replace('\r\n', '\n')
    keytermtask.definition_text = definition_text
    if len(definition_text.replace('\n','').replace('\r','')) > 515:
        keytermtask.definition_text = definition_text[0:515] + ' ...'

    explainer_text = request.POST.get('keyterm-explanation', '')
    explainer_text = explainer_text or '<no explanation>'
    explainer_text = explainer_text.replace('\r\n', '\n')
    keytermtask.explainer_text = explainer_text
    if len(explainer_text.replace('\n','').replace('\r','')) > 1015:
            keytermtask.explainer_text = explainer_text[0:1015] + ' ...'

    reference_text = request.POST.get('keyterm-reference', '')
    reference_text = reference_text or '<no reference>'
    keytermtask.reference_text = reference_text
    if len(reference_text.replace('\n','').replace('\r','')) > 245:
        keytermtask.reference_text = reference_text[0:245] + ' ...'

    keytermtask.save()

    # We have saved, but if there was an error message: go back to DRAFT
    if error_message:
        return draft_keyterm(request, course=course, learner=learner,
                        entry_point=entry_point, error_message=error_message)
    else:
        create_preview(keytermtask)


    ctx = {'keytermtask': keytermtask,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           'grade_push_url': request.POST.get('lis_outcome_service_url', '')
           }
    return render(request, 'keyterm/preview.html', ctx)


def create_preview(keytermtask):
    """
    Creates the keyterm page (PNG file), from the text, image, reference..
    Renders the image; uploads it as a submission.
    """

    # Settings for creating the image and thumbnail.
    targetWimg = 1000   # the pasted image is 1000 pixels wide
    targetWtxt =  900   # the text is 900 pixels wide
    targetW = targetWtxt + targetWimg
    targetH = 1600
    start_Lw = targetWtxt # top left width coordinate (distance from left edge)
                          # of pasted image
    start_Lh = 0  # top left height coordinate (distance from top edge) of paste
    thumbWimg = thumbHimg = 200

    base_image_wh = (targetW, targetH)
    bgcolor = "#EEE"
    color = "#000"
    REPLACEMENT_CHARACTER = u'\uFFFD'
    NEWLINE_REPLACEMENT_STRING = ' ' + REPLACEMENT_CHARACTER + ' '
    fontfullpath = settings.MEDIA_ROOT + 'keyterm/fonts/Lato-Regular.ttf'
    output_extension  = 'jpg'

    entry_point = keytermtask.keyterm.entry_point

    # Is the storage space reachable?

    deepest_dir = settings.MEDIA_ROOT + 'uploads/{0}/thumbs/'.format(
        entry_point.id)

    try:
        os.makedirs(deepest_dir)
    except OSError:
        if not os.path.isdir(deepest_dir):
            logger.error('Cannot create directory for upload: {0}'.format(
                deepest_dir))
            raise

    img = Image.new("RGB", base_image_wh, bgcolor)
    draw = ImageDraw.Draw(img)
    # https://www.snip2code.com/Snippet/1601691/Python-text-to-image-(png)-conversion-wi
    def text2png(text, draw, start_y=0, fontsize=50, leftpadding=3,
                 rightpadding=3, width=2000):
        #font = ImageFont.load_default()
        font =  ImageFont.truetype(fontfullpath, fontsize)
        text = text.replace('\n\n', NEWLINE_REPLACEMENT_STRING)
        text = text.replace('\n', NEWLINE_REPLACEMENT_STRING)
        lines = []
        line = u""

        for word in text.split():
            if word == REPLACEMENT_CHARACTER: # Give a blank line
                lines.append( line[1:] )      # Slice the white space in the begining of the line
                line = u""
                lines.append( u"" ) # blank line
            elif font.getsize( line + ' ' + word )[0] <= (width - rightpadding - leftpadding):
                line += ' ' + word
            else: #start a new line
                lines.append( line[1:] ) #slice the white space
                line = u""

                #TODO: handle too long words at this point
                line += ' ' + word # Assume no word alone can exceed line width

        if len(line) != 0:
            lines.append( line[1:] ) # add last line

        line_height = font.getsize(text)[1]
        img_height = line_height * (len(lines) + 1)

        y = start_y
        for line in lines:
            if line == '':
                line = ' '
            draw.text( (leftpadding, y), line, color, font=font)
            y += line_height

        return y, line_height


    last_y, line_height = text2png(keytermtask.keyterm.keyterm, draw,
                                   start_y=50, fontsize=75, leftpadding=20)

    last_y, line_height = text2png(keytermtask.definition_text, draw,
                                   start_y=last_y+line_height*1,
                                   fontsize=32, width=targetWtxt-20*2,
                                   leftpadding=20, rightpadding=20)

    last_y, line_height = text2png('Example/Explanation:', draw,
                                   start_y=last_y+line_height*2,
                                   fontsize=50, width=targetWtxt-20*2,
                                   leftpadding=20, rightpadding=20)

    last_y, line_height = text2png(keytermtask.explainer_text, draw,
                                   start_y=last_y, fontsize=28,
                                   width=targetWtxt-20*2,
                                   leftpadding=20, rightpadding=20)

    last_y, line_height = text2png('Reference:', draw,
                                   start_y=last_y+line_height*2,
                                   fontsize=30, width=targetWtxt-20*2,
                                   leftpadding=20, rightpadding=20)

    last_y, line_height = text2png(keytermtask.reference_text, draw,
                                   start_y=last_y, fontsize=20,
                                   width=targetWtxt-20*2,
                                   leftpadding=20, rightpadding=20)



    source = Image.open(keytermtask.image_raw.file_upload)
    width, height = source.width, source.height

    targetHimg = targetH

    if (height/width) < (targetHimg/targetWimg):
        # Current image has width as the limiting constraint. Set width to target.
        height = int(height/width * targetWimg)
        width = targetWimg
        start_Lh = start_Lh + int((targetHimg - height)/2)


    elif (height/width) > (targetHimg/targetWimg):
        # Current image has height as the limiting constraint. Set height to target.
        width = int(width/height * targetHimg)
        height = targetHimg
        start_Lw = targetWimg + int((targetWimg-width)/2)

    source = source.resize((width, height))
    img.paste(source, (start_Lw, start_Lh))



    base_name = generate_random_token(token_length=16) + '.' + output_extension
    submitted_file_name_django = 'uploads/{0}/{1}'.format(entry_point.id,
                                                          base_name)
    full_path = settings.MEDIA_ROOT + submitted_file_name_django
    img.save(full_path)

    keytermtask.image_modified = submitted_file_name_django
    keytermtask.save()


    # Repeat: make the uploaded image -> thumbnail
    thumbWimg = 400
    thumbHimg = 400
    submitted_file_name_django = 'uploads/{0}/thumbs/{1}'.format(entry_point.id,
                                                                 base_name)
    full_path = settings.MEDIA_ROOT + submitted_file_name_django
    source.thumbnail((thumbWimg, thumbHimg))
    fill_color = ''  # your background
    if source.mode in ('RGBA', 'LA'):
        background = Image.new(source.mode[:-1], source.size, bgcolor)
        background.paste(source, source.split()[-1])
        source = background
    source.save(full_path, quality=95)

    keytermtask.image_thumbnail = submitted_file_name_django
    keytermtask.save()


def submit_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """
    prior = learner.keytermtask_set.filter(keyterm__entry_point=entry_point)
    if prior.count():
        keytermtask = prior[0]
        keyterm = keytermtask.keyterm
    else:
        try:
            keyterm = KeyTermSetting.objects.get(entry_point=entry_point)
        except KeyTermSetting.DoesNotExist:
            logger.error('Submit: An error occurred. [{0}]'.format(learner))
            return HttpResponse('An error occurred.')

    # 1. Now you have the task ``keytermtask``: set state
    # 2. Store new values in the task
    # 3. Process the image (store it too, but only in staging area)
    # 4. Render the template image  (store it too, but only in staging area)
    # 5. Float the submit buttons left and right of each other

    # We have 4 states: set the correct settings (in case page is reloaded here)
    keytermtask.is_in_draft = False
    keytermtask.is_in_preview = False
    keytermtask.is_submitted = True
    keytermtask.is_finalized = False

    valid_tasks = keyterm.keytermtask_set.filter(is_finalized=True)
    NN_to_upload = keyterm.min_submissions_before_voting - valid_tasks.count()

    # Get all other user's keyterms: how many othersare uploaded already?
    ctx = {'keytermtask': keytermtask,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           'NN_to_upload_still': max(0, NN_to_upload),
           'total_finalized': valid_tasks.count(),
           'grade_push_url': request.POST.get('lis_outcome_service_url', '')
           }
    return render(request, 'keyterm/submit.html', ctx)


def finalize_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """
    prior = learner.keytermtask_set.filter(keyterm__entry_point=entry_point)
    if prior.count():
        keytermtask = prior[0]
        keyterm = keytermtask.keyterm
    else:
        try:
            keyterm = KeyTermSetting.objects.get(entry_point=entry_point)
        except KeyTermSetting.DoesNotExist:
            logger.error('Finalize: An error occurred. [{0}]'.format(learner))
            return HttpResponse('An error occurred.')

    # We have 4 states: set the correct settings (in case page is reloaded here)
    keytermtask.is_in_draft = False
    keytermtask.is_in_preview = False
    keytermtask.is_submitted = False
    keytermtask.is_finalized = True
    keytermtask.save()

    # Get all prior keyterms: and show their thumbnails in random order
    # Show how many votes the user has left?

    valid_tasks = keyterm.keytermtask_set.filter(is_finalized=True)
    own_task = valid_tasks.get(learner=learner)
    valid_tasks = list(valid_tasks)
    valid_tasks.remove(own_task)
    shuffle(valid_tasks)
    valid_tasks.insert(0, own_task)


    # TODO: push the grade async
    grade_push_url=request.POST.get('lis_outcome_service_url', '')
    response = push_grade(learner=learner,
                          grade_value=100,
                          entry_point=entry_point,
                          grade_push_url=grade_push_url,
                          testing=False)

    logger.debug('Grade for {0} at [{1}]; response: {2}'.format(learner,
                                                                grade_push_url,
                                                                response))

    ctx = {'keytermtask': keytermtask,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           'valid_tasks': valid_tasks,
           }
    return render(request, 'keyterm/finalize.html', ctx)

