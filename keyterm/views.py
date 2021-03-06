from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.conf import settings
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt

# Python import
import os
from random import shuffle
import tempfile
import datetime
from collections import defaultdict

# This app's imports
from .models import KeyTermSetting, KeyTermTask, Thumbs
from .forms import UploadFileForm_file_optional, UploadFileForm_file_required

# 3rd party imports: image rendering
import PIL
from PIL import ImageFont, Image, ImageDraw
from PyPDF2 import PdfFileMerger

# Import from our other apps
from utils import generate_random_token
from basic.models import Person
from stats.views import create_hit

#from submissions.models import Submission
from submissions.views import upload_submission
from basic.views import entry_point_discovery
from grades.views import push_grade


# Logging
import logging
logger = logging.getLogger(__name__)

OUTPUT_EXTENSION = 'png'

@csrf_exempt
def start_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """
    if learner.role in ('Admin', ):
        return finalize_keyterm(request, course, learner, entry_point)

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
                                  is_in_draft=True,
                                  lookup_hash=generate_random_token()
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

    create_hit(request, item=keytermtask, event='KT-draft',
               user=learner, other_info=keyterm.keyterm)


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

    create_hit(request, item=keytermtask, event='KT-preview',
               user=learner, other_info='Error={}'.format(error_message))

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
    entry_point = keytermtask.keyterm.entry_point

    # Settings for creating the image and thumbnail.
    targetWimg = int(1000)   # the pasted image is 1000 pixels wide
    targetWtxt = int(900)    # the text is 900 pixels wide
    targetW = targetWtxt + targetWimg
    targetHimg = int(1600)
    base_canvas_wh = (targetW, targetHimg)

    start_Lh = 0  # top left height coordinate (distance from top edge) of paste
    thumbWimg = thumbHimg = int(800)
    L_pad = R_pad = 20   # text padding
    bgcolor = "#EEE"
    color = "#000"
    REPLACEMENT_CHARACTER = u'\uFFFD'
    NEWLINE_REPLACEMENT_STRING = ' ' + REPLACEMENT_CHARACTER + ' '
    fontfullpath = settings.MEDIA_ROOT + 'keyterm/fonts/Lato-Regular.ttf'


    # These keyterms we will float the image left (odd numbers ID)
    if keytermtask.id % 2:
        start_Lw = 0          # top left width coordinate (distance from left
                              # edge) of pasted image
        text_width = targetW
        L_pad += targetWimg

    # These keyterms will have float the image right
    else:
        start_Lw = targetWtxt # top left width coordinate (distance from left
                              # edge) of pasted image
        text_width = targetWtxt
        L_pad = L_pad         # stays the same ...

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

    img = Image.new("RGB", base_canvas_wh, bgcolor)
    draw = ImageDraw.Draw(img)
    # https://www.snip2code.com/Snippet/1601691/Python-text-to-image-(png)-conversion-wi
    def text2png(text, draw, start_y=0, fontsize=50, leftpadding=3,
                 rightpadding=3, width=2000):
        """
        width:        the size of the canvas
        leftpadding:  the starting point where we write text from
        rightpadding: the fartherest right edge where we can write text up to
        """
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
                                   start_y=50, fontsize=75, leftpadding=L_pad,
                                   width=text_width)

    last_y, line_height = text2png(keytermtask.definition_text, draw,
                                   start_y=last_y+line_height*1,
                                   fontsize=32, width=text_width,
                                   leftpadding=L_pad, rightpadding=R_pad)

    last_y, line_height = text2png('Example/Explanation:', draw,
                                   start_y=last_y+line_height*2,
                                   fontsize=50, width=text_width,
                                   leftpadding=L_pad, rightpadding=R_pad)

    last_y, line_height = text2png(keytermtask.explainer_text, draw,
                                   start_y=last_y, fontsize=28, width=text_width,
                                   leftpadding=L_pad, rightpadding=R_pad)

    last_y, line_height = text2png('Reference:', draw,
                                   start_y=last_y+line_height*2,
                                   fontsize=30, width=text_width,
                                   leftpadding=L_pad, rightpadding=R_pad)

    last_y, line_height = text2png(keytermtask.reference_text, draw,
                                   start_y=last_y, fontsize=20, width=text_width,
                                   leftpadding=L_pad, rightpadding=R_pad)
    text = 'Created by: ' + keytermtask.learner.display_name
    last_y, line_height = text2png(text, draw,
                                   start_y=img.size[1]-2*line_height,
                                   fontsize=20, width=text_width,
                                   leftpadding=L_pad, rightpadding=R_pad)


    source = Image.open(keytermtask.image_raw.file_upload)
    width, height = source.width, source.height

    if (height/width) < (targetHimg/targetWimg):
        # Current image has width as the limiting constraint. Set width to target.
        height = int(max(height/width * targetWimg, 1))
        width = targetWimg
        start_Lh = start_Lh + int((targetHimg - height)/2)


    elif (height/width) > (targetHimg/targetWimg):
        # Current image has height as the limiting constraint. Set height to target.
        width = int(max(width/height * targetHimg, 1))
        height = targetHimg
        start_Lw = start_Lw + int((targetWimg-width)/2)

    source = source.resize((width, height))
    img.paste(source, (start_Lw, start_Lh))

    base_name = generate_random_token(token_length=16) + '.' + OUTPUT_EXTENSION
    submitted_file_name_django = 'uploads/{0}/{1}'.format(entry_point.id,
                                                          base_name)
    full_path = settings.MEDIA_ROOT + submitted_file_name_django
    img.save(full_path)

    keytermtask.image_modified = submitted_file_name_django
    keytermtask.save()


    # Repeat: make the uploaded image -> thumbnail
    submitted_file_name_django = 'uploads/{0}/thumbs/{1}'.format(entry_point.id,
                                                                 base_name)
    full_path = settings.MEDIA_ROOT + submitted_file_name_django
    width, height = source.size
    if (height/width) > (thumbHimg/thumbWimg):
        # Current image has width as the limiting constraint.
        # Set width to target; pick middle part (top to bottom) as thumbnail.
        height = int(max(height/width * thumbWimg, 1))
        width = thumbWimg
        source = source.resize((width, height))
        centerH = int(height/2.0)
        cropTh = int(centerH - thumbHimg/2.)
        cropBh = cropTh + thumbHimg
        source = source.crop((0, cropTh, thumbWimg, cropBh))

    if (height/width) <= (targetHimg/targetWimg):
        # Current image has height as the limiting constraint.
        # Set height to target; pick middle part (left to right) as thumbnail.
        width = int(max(width/height * thumbHimg, 1))
        height = thumbHimg
        source = source.resize((width, height))
        centerW = int(width/2.0)
        cropLw = int(centerW - thumbWimg/2.)
        cropRw = cropLw + thumbWimg
        source = source.crop((cropLw, 0, cropRw, thumbHimg))

    fill_color = ''  # your background
    if source.mode in ('RGBA', 'LA'):
        background = Image.new(source.mode[:-1], source.size, bgcolor)
        background.paste(source, source.split()[-1])
        source = background
    source.convert('RGB').save(full_path, quality=95)

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

    create_hit(request, item=keytermtask, event='KT-submit',
               user=learner, other_info='')

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

    # Get all prior keyterms: and show their thumbnails in random order
    # Show how many votes the user has left?
    valid_tasks = keyterm.keytermtask_set.filter(is_finalized=True)
    if learner.role in ('Learn', ):

        # We have 4 states: set the correct settings
        #                                        (in case page is reloaded here)
        keytermtask.is_in_draft = False
        keytermtask.is_in_preview = False
        keytermtask.is_submitted = False
        keytermtask.is_finalized = True
        keytermtask.save()

        own_task = valid_tasks.get(learner=learner)
        valid_tasks = list(valid_tasks)
        valid_tasks.remove(own_task)
        shuffle(valid_tasks)
        valid_tasks.insert(0, own_task)
    else:

        # Administrator's only
        valid_tasks = list(valid_tasks)
        shuffle(valid_tasks)
        if len(valid_tasks) == 0:
            return HttpResponse('There are no completed keyterms yet to view.')
        else:
            # Just grab the first task to use for display purposes and logic.
            keytermtask = valid_tasks[0]



    #Abuse the ``valid_tasks`` here, and add a field onto it that determines
    #if it has been voted on by this user.
    for task in valid_tasks:
        votes = task.thumbs_set.filter(awarded=True)
        task.number_votes = votes.count()
        task.this_learner_voted_it = votes.filter(voter=learner).count() > 0


    # TODO: push the grade async
    grade_push_url=request.POST.get('lis_outcome_service_url', '')
    response = push_grade(learner=learner,
                          grade_value=100,
                          entry_point=entry_point,
                          grade_push_url=grade_push_url,
                          testing=False)

    prior_votes = Thumbs.objects.filter(voter=learner, awarded=True,
                                        vote_type='thumbs-up',
                                        keytermtask__keyterm=keyterm).count()
    max_votes = keyterm.max_thumbs
    votes_left = max_votes - prior_votes


    logger.debug('Grade for {0} at [{1}]; response: {2}'.format(learner,
                                                                grade_push_url,
                                                                response))

    after_voting_deadline = False
    if timezone.now() > keytermtask.keyterm.deadline_for_voting:
        after_voting_deadline = True


    create_hit(request, item=keytermtask, event='KT-final',
               user=learner, other_info='Grade push = {}'.format(response))

    ctx = {'keytermtask': keytermtask,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           'valid_tasks': valid_tasks,
           'votes_left': votes_left,
           'after_voting_deadline': after_voting_deadline,
           }
    return render(request, 'keyterm/finalize.html', ctx)

@csrf_exempt
@xframe_options_exempt
def download_term(request, learner_hash=''):
    """
    POST request received from user to download a booklet of all the keyterms
    for a particular page.

    Creates a unique link, delay to compile the document and download it.
    """
    'download_task'
    learner = Person.objects.filter(hash_code=learner_hash)
    if learner.count() != 1:
        logger.error('Learner error hash={}; POST=[{}]'.format(learner_hash,
                                                               request.POST))
        return JsonResponse({'message': ('Error: could not identify who you '
                                         'are. Please reload the page.') })
    else:
        learner = learner[0]


    lookup_id = request.POST.get('download_task', 'keyterm-0')
    try:
        lookup_id = int(lookup_id.split('keyterm-')[1])
    except ValueError:
        lookup_id = 0


    keyterm = KeyTermSetting.objects.filter(id=lookup_id)
    if keyterm.count() != 1:
        logger.error('Keyterm not found={}; POST=[{}]'.format(lookup_id,
                                                                request.POST))
        return JsonResponse({'message': ('Error: Key term not found.') })
    else:
        keyterm = keyterm[0]

    merger = PdfFileMerger(strict=False, )
    all_terms = keyterm.keytermtask_set.filter(is_finalized=True).order_by('id')
    append_images = []
    for term in all_terms:

        outfile = term.image_modified.file.name.split('.'+OUTPUT_EXTENSION)[0]
        outfile += '.pdf'
        if not(os.path.isfile(outfile)):
            img = Image.open(term.image_modified.file)
            img.save(outfile, 'PDF')

        # Append the PDF
        merger.append(outfile, import_bookmarks=False)

    # All done
    merger.addMetadata({'/Title': 'Key term: ' + keyterm.keyterm,
                        '/Author': 'All students in the course',
                        '/Creator': 'Keyterms Booklet',
                        '/Producer': 'Keyterms Booklet'})

    base_file_dir = 'uploads/{0}/tmp/'.format(keyterm.entry_point.id)
    deepest_dir = settings.MEDIA_ROOT + base_file_dir
    fd, temp_file_dst = tempfile.mkstemp(prefix=keyterm.keyterm+'--',
                                         suffix='.pdf', dir=deepest_dir)
    server_URI = '/{0}{1}'.format(settings.MEDIA_URL,
                                  temp_file_dst.split(settings.MEDIA_ROOT)[1])

    merger.write(temp_file_dst)
    merger.close()
    try:
        os.close(fd)
    except OSError:
        pass

    message = ('Your download is ready now. <a href="{}" target="_blank">'
               'Click here to open it.</a>').format(server_URI)
    response = {'message': message}
    return JsonResponse(response)


@csrf_exempt
@xframe_options_exempt
def vote_keyterm(request, learner_hash=''):
    """
    POST request recieved when the user votes on an item. In the POST we get the
    keytermtask's ``lookup_hash``, and in the POST's URL we get the learner's
    hash. From this we can determine who is voting on what.
    """
    learner = Person.objects.filter(hash_code=learner_hash)
    if learner.count() != 1:
        logger.error('Learner error hash={}; POST=[{}]'.format(learner_hash,
                                                               request.POST))
        return HttpResponse(('Error: could not identify who you are. Please '
                             'reload the page.'))
    else:
        learner = learner[0]

    lookup_hash = request.POST.get('voting_task', None)
    keytermtask = KeyTermTask.objects.filter(lookup_hash=lookup_hash)
    if keytermtask.count() != 1:
        logger.error('Keytermtask error hash={}; POST=[{}]'.format(lookup_hash,
                                                                request.POST))
        return HttpResponse(('Error: could not identify who you are voting for.'
                ' Please reload the page.'))
    else:
        keytermtask = keytermtask[0]

    # Fail safe: rather not vote for the post, so assume it was 'true'
    prior_state = request.POST.get('state', 'true') == 'true'
    new_state = not(prior_state)

    # Before creating the vote; check if learner should be allowed to vote:
    # Own vote?
    valid_vote = ''
    html_class = ''
    max_votes = keytermtask.keyterm.max_thumbs
    prior_votes = Thumbs.objects.filter(voter=learner, awarded=True,
                                        vote_type='thumbs-up',
                                       keytermtask__keyterm=keytermtask.keyterm)

    if learner == keytermtask.learner:
        valid_vote = 'You may not vote for your own work.'
        html_class = 'warning'
        new_state = False
        logger.error('This should not occur, but is a safeguard. Investigate!')

    # Past the deadline?
    elif timezone.now() > keytermtask.keyterm.deadline_for_voting:
        valid_vote = 'The deadline to vote has passed; sorry.'
        html_class = 'warning'
        new_state = prior_state # do nothing

    elif not(valid_vote):
        prior_vote = learner.thumbs_set.filter(keytermtask=keytermtask,
                                               vote_type='thumbs-up')
        if prior_vote:
            thumb = prior_vote[0]
            thumb.awarded = new_state
            thumb.save()
        else:
            thumb, _ = Thumbs.objects.get_or_create(keytermtask=keytermtask,
                                                    voter=learner,
                                                    awarded=new_state,
                                                    vote_type='thumbs-up',
                    )
            thumb.save()

        # One last check (must come after voting!)
        # Too many votes already for others in this same keyterm?
        if prior_votes.count() > max_votes:
            # Undo the prior voting to get the user back to the level allowed
            thumb.awarded = False
            new_state = False
            valid_vote = 'All votes have been used up. '
            html_class = 'warning'
            thumb.save()

    logger.debug('Vote for [{}] by [{}]; new_state: {}'.format(lookup_hash,
                                                               learner_hash,
                                                               new_state))

    if new_state:
        short_msg = 'Vote recorded; '
    else:
        short_msg = 'Vote withdrawn; '
    if valid_vote == 'All votes have been used up. ':
        short_msg = valid_vote

    message = 'As of {}: you have '.format(timezone.now().strftime(\
                                                 '%d %B %Y at %H:%M:%S (UTC)'))
    if max_votes == prior_votes.count():
        message += ('no more votes left. You may withdraw prior votes by '
                    'clicking on the icon. ')
        short_msg += ('Zero votes left. <br><br>Remove prior votes to '
                    'vote again. ')
    elif (max_votes - prior_votes.count()) == 1:
        message += '1 more vote left. '
        short_msg += '1 more vote left. '
    else:
        message += '{} more votes left. '.format(max_votes-prior_votes.count())
        short_msg += '{} more votes left. '.format(max_votes-prior_votes.count())

    if valid_vote:
        message += ' <span class="{}">{}</span>'.format(html_class, valid_vote)

    create_hit(request, item=keytermtask, event='KT-vote',
                user=learner, other_info=message)


    response = {'message': message,
                'new_state': new_state,
                'task_hash': '#' + lookup_hash,
                'short_msg': short_msg}

    return JsonResponse(response)

@csrf_exempt
def student_downloads(request, course=None, learner=None, entry_point=None):
    """
    Generates all the information needed for a student download of the keyterm
    booklets
    """
    # Create place to store and stage files
    base_dir = settings.MEDIA_ROOT
    base_file_dir = 'uploads/{0}/tmp/'.format(entry_point.id)
    deepest_dir = base_dir + base_file_dir
    try:
        os.makedirs(deepest_dir)
    except OSError:
        if not os.path.isdir(deepest_dir):
            logger.error('Cannot create directory for PDF download: {0}'.format(
                deepest_dir))
            raise

    # Explicitly specify the variables we will use later
    total_votes = student_votes_given = student_votes_received = 0
    submitted_keyterms = draft_keyterms = maximum_keytermtasks = 0

    total_votes = Thumbs.objects.filter(awarded=True).count()
    n_persons = Person.objects.filter(course=course, role='Learn').count()
    student_votes_given = learner.thumbs_set.all().count()

    entry_points = course.entrypoint_set.all().order_by('order')
    all_keyterms = []
    for term in entry_points:
        if term != entry_point:
            all_keyterms.append(KeyTermSetting.objects.get(entry_point=term))

    maximum_keytermtasks = len(all_keyterms)

    # Settings for text placement
    placement_y = 225
    placement_offset_x = 16
    fontsize = 50
    image_W, image_H = (1900, 1600)
    offset_y = 0
    base_canvas_wh = (image_W, image_H)
    color = "#FFF"
    bgcolor = "#000"

    # Set up the text and placement for the student's name in the template
    student_name = learner.official_name or learner.display_name
    fontfullpath = base_dir + 'keyterm/fonts/Lato-Regular.ttf'
    img = Image.new("RGB", base_canvas_wh, bgcolor)
    draw = ImageDraw.Draw(img)
    cover_page = base_dir + 'keyterm-template-cover.jpg'
    source = Image.open(cover_page)
    img.paste(source, (0, 0))
    font = ImageFont.truetype(fontfullpath, fontsize)

    # The name is centered in the image
    x, y = ((image_W - font.getsize(student_name)[0])/2, placement_y)

    draw.text( (x+placement_offset_x, y), student_name, color, font=font)
    cover_page = deepest_dir + learner.display_name + '.pdf'
    if not(os.path.isfile(cover_page)):
        img.save(cover_page, 'PDF')

    merger = PdfFileMerger(strict=False, )
    merger.append(cover_page, import_bookmarks=False)

    voting = defaultdict(dict)
    for keyterm in all_keyterms:
        this_task = learner.keytermtask_set.filter(keyterm=keyterm)
        voting[keyterm.keyterm]['url'] = keyterm.entry_point.full_URL

        all_tasks = keyterm.keytermtask_set.all()
        all_votes = [kt.thumbs_set.all().count() for kt in all_tasks]
        # Don't sort, unless you are debugging and want to preview the ties.
        #all_votes.sort()
        #print(all_votes)
        max_votes = max(all_votes)
        max_votes_idx = all_votes.index(max_votes)
        voting[keyterm.keyterm]['top_task'] = all_tasks[max_votes_idx]
        if not(this_task):
            voting[keyterm.keyterm]['received_votes'] = ('You did not attempt '
                                                         'this key term.')
            continue
        else:
            this_task = this_task[0]

        if this_task.is_finalized:
            submitted_keyterms += 1
            voting[keyterm.keyterm]['received_votes'] = \
                                      this_task.thumbs_set.all().count()
            student_votes_received += this_task.thumbs_set.all().count()
            outfile = this_task.image_modified.file.name.split('.' + \
                                                            OUTPUT_EXTENSION)[0]
            outfile += '.pdf'
            if not(os.path.isfile(outfile)):
                img = Image.open(this_task.image_modified.file)
                img.save(outfile, 'PDF')

            # Append the PDF
            merger.append(outfile, import_bookmarks=False)

        elif this_task.is_in_draft:
            # The keyterm was started, but not finalized
            voting[keyterm.keyterm]['received_votes'] = ('You left this key '
                                                         'term as draft.')
            draft_keyterms += 1

    # All done
    merger.addMetadata({'/Title': 'Key terms for ' + course.name,
                       '/Author': learner.official_name or learner.display_name,
                       '/Creator': 'Keyterms Booklet',
                       '/Producer': 'Keyterms Booklet'})

    # First delete old files
    for dirpath, dnames, fnames in os.walk(deepest_dir):
        for f in fnames:
            if f.startswith(learner.display_name+'--'):
                os.remove(dirpath + f)

    # Then save their latest version of the booklet
    fd, temp_file_dst = tempfile.mkstemp(prefix=learner.display_name+'--',
                                         suffix='.pdf',
                                         dir=deepest_dir)
    server_URI = '/{0}{1}'.format(settings.MEDIA_URL,
                                  temp_file_dst.split(settings.MEDIA_ROOT)[1])

    merger.write(temp_file_dst)
    merger.close()
    # Then close the temp file
    try:
        os.close(fd)
    except OSError:
        pass

    merger = PdfFileMerger(strict=False, )
    cover_page = base_dir + 'keyterm-template-most-votes.pdf'

    # Only done once
    if not(os.path.isfile(cover_page)):
        img = Image.new("RGB", base_canvas_wh, bgcolor)
        draw = ImageDraw.Draw(img)
        source = Image.open(base_dir + 'keyterm-template-most-votes.jpg')
        img.paste(source, (0, 0))
        img.save(cover_page, 'PDF')

    # Continue on
    merger.append(cover_page, import_bookmarks=False)
    for keyterm in all_keyterms:
        this_task = voting[keyterm.keyterm]['top_task']
        if this_task.is_finalized:
            received_votes = this_task.thumbs_set.all().count()
            outfile = this_task.image_modified.file.name.split('.' + \
                                                            OUTPUT_EXTENSION)[0]
            outfile += '.pdf'
            if not(os.path.isfile(outfile)):
                img = Image.open(this_task.image_modified.file)
                img.save(outfile, 'PDF')

            # Append the PDF
            merger.append(outfile, import_bookmarks=False)
    # All done, finish up.
    timestamp = timezone.now().strftime('%d-%m-%Y-%H-%M-%S')
    fd, temp_file_dst = tempfile.mkstemp(prefix='Most-voted'+'-'+timestamp+'-',
                                         suffix='.pdf',
                                         dir=deepest_dir)
    most_voted_link = '/{0}{1}'.format(settings.MEDIA_URL,
                                  temp_file_dst.split(settings.MEDIA_ROOT)[1])

    merger.write(temp_file_dst)
    merger.close()

    # Pick the last key term from the prior fot loop to figure out what the
    # overall voting deadline is
    show_most_voted_booklet = False
    if datetime.datetime.now(datetime.timezone.utc) > keyterm.deadline_for_voting:
        show_most_voted_booklet = True

    ctx = {'learner_download_link': server_URI,
           'total_votes': total_votes,
           'n_persons': n_persons,
           'student_votes_given': student_votes_given,
           'student_votes_received': student_votes_received,
           'submitted_keyterms': submitted_keyterms,
           'draft_keyterms': draft_keyterms,
           'maximum_keytermtasks': maximum_keytermtasks,
           'maximum_votes_possible': submitted_keyterms * 3,
           'voting': dict(voting), # defaultdict->dict, to avoid template issues
           'most_voted_link': most_voted_link,
           'show_most_voted_booklet': show_most_voted_booklet,
           }
    return render(request, 'keyterm/learner_download.html', ctx)