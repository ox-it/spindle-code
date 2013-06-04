import json
import xml.etree.ElementTree as ET
import logging

from django.utils import timezone
from django.http import HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django import forms
from django.forms import ModelForm
from django.db.models import Q
from django.conf import settings
from django.core.urlresolvers import reverse, reverse_lazy
from django.views.generic.edit import UpdateView
from django.views.generic.detail import DetailView
from django.views.generic.edit import UpdateView

import celery.task.base

from spindle.models import Item, ArchivedItem, Track, TranscriptionTask
from spindle.readers import vtt, xmp
from spindle.keywords.keywords import keywords_and_ngrams
import spindle.transcribe
import spindle.tasks
import spindle.publish
from spindle.rest_api import json_login_required

import spindle.transcribe.koemei as koemei
import spindle.transcribe.sphinx as sphinx

logger = logging.getLogger(__name__)


# List items for transcription
@login_required
def itemlist(request):
    params = request.GET.dict()
    return do_itemlist(request, **params)

def do_itemlist(request, limit=15, offset=0, search=None,
                sort_by='published', sort_dir=-1, **ignored):
    offset = int(offset)
    limit = int(limit)
    sort_dir = int(sort_dir)

    # Construct the base search, without range slicing
    def base_query():
        if search:
            return Item.objects.filter(
                Q(name__icontains=search) |
                Q(audio_url__icontains=search) |
                Q(video_url__icontains=search))
        else:
            return Item.objects.all()

    # Sort, count and slice
    count = base_query().count()
    query = base_query().order_by(sort_by if (sort_dir > 0) else ("-" + sort_by))
    items = query[offset:offset+limit]

    # Construct readable descriptions of search and range
    if len(items) < limit:
        range_description = "all"
    else:
        range_description = "{} to {} of ".format(
            offset+1,
            min(offset+limit, count))
    search_description = "containing '{}'".format(search) if search else "in database"

    # Construct URLs for changing slice and sorting methods
    base_url = '?'
    base_params = QueryDict('').copy()
    base_params.update({'search': search if search else '',
                        'sort_by': sort_by, 'sort_dir': sort_dir, 'limit': limit })

    next_params = base_params.copy()
    prev_params = base_params.copy()

    next_params.update({ 'offset': min(offset + limit, count - 1) })
    prev_params.update({ 'offset': max(offset - limit, 0) })

    next_url = base_url + next_params.urlencode()
    prev_url = base_url + prev_params.urlencode()

    order_urls = {};
    for col in ['item_id', 'name', 'video_url',
                'media_type', 'duration', 'published',
                'track_count']:
        params = base_params.copy()

        if(col != sort_by):
            del params['sort_by']
            params.update({ 'sort_by': col })
        else:
            del params['sort_dir']
            params.update({ 'sort_dir': -sort_dir })

        order_urls[col] = base_url + params.urlencode()

    # Render template
    return render(request, 'spindle/itemlist.html', {
            'title': "Item list",
            'items': items,

            'range': range_description,
            'count': count,
            'search_description': search_description,

            'search': search if search else '',
            'next_url': next_url,
            'prev_url': prev_url,
            'order_urls': order_urls,
            })



# Item-level operations

# Item metadata form
class ItemMetadataForm(ModelForm):
    class Meta:
        model = Item
        fields = ('name', 'audio_url', 'video_url', 'keywords')

# New item form
@login_required
def new(request):
    if request.method == 'POST':
        form = ItemMetadataForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data.copy()
            if 'caption_file' in data: del data['caption_file']

            item = Item(**data)
            item.duration = 0   #  FIXME
            item.published = timezone.now()
            item.save()

            return redirect(item_tracks, item_id=item.id)
    else:
        form = ItemMetadataForm()

    return render(request, 'spindle/new.html', {
        'form': form,
        })

# Scrape RSS form
@login_required
def scrape(request):
    tasks = {
        'scrape': spindle.tasks.scrape
    }
    task_info = run_tasks(request, tasks)
    template_data = {
        'rss_url': settings.SPINDLE_SCRAPE_RSS_URL,
    }
    template_data.update(task_info)

    return render(request, 'spindle/scrape.html', template_data)

# Publish things
@login_required
def publish(request):
    # The tasks
    tasks = {
        'publish_all_items': spindle.publish.publish_all_items,
        'publish_exports_feed': spindle.publish.publish_exports_feed,
        'publish_fulltext_feed': spindle.publish.publish_fulltext_feed,
    }

    task_info = run_tasks(request, tasks)
    template_data = {
        'exports_rss_url': spindle.publish.EXPORTS_RSS_URL,
        'exports_fulltext_url': spindle.publish.FULLTEXT_RSS_URL,
    }
    template_data.update(task_info)
    return render(request, 'spindle/publish.html', template_data)






# File upload form
UPLOAD_FILE_TYPES = (('xmp', 'XMP (Adobe Premiere) file'),
                     ('srt', 'SRT/WebVTT file'),
                     ('koemei', 'Koemei XML transcript'),
                     ('sphinx', 'Raw Sphinx output'))
class UploadTrackForm(forms.Form):
    file_type = forms.ChoiceField(choices=UPLOAD_FILE_TYPES)
    caption_file = forms.FileField(required=True)

# Request transcription form
TRANSCRIPTION_ENGINES = [(key, engine['name'])
                         for key, engine
                         in spindle.transcribe.engine_map().iteritems()]
class RequestTranscriptForm(forms.Form):
    engine = forms.ChoiceField(choices=TRANSCRIPTION_ENGINES)

# List item transcripts
@login_required
def item_tracks(request, item_id):
    return DetailView.as_view(
        request,
        queryset = Item.objects,
        object_id = item_id,
        template_name = "spindle/item_tracks.html",
        template_object_name = "item")

@login_required
def item_revisions(request, item_id):
    return DetailView.as_view(
        request, queryset = Item.objects, object_id = item_id,
        template_name = "spindle/item_revisions.html",
        template_object_name = "item")

@login_required
def item_metadata(request, item_id):
    return UpdateView.as_view(request,
        form_class = ItemMetadataForm,
        object_id = item_id,
        template_name = "spindle/item_metadata.html",
        template_object_name = "item",
        post_save_redirect = reverse(item_metadata, kwargs={'item_id': item_id}))

@login_required
def item_add_track(request, item_id):
    item = get_object_or_404(Item, pk=item_id)
    new_track_form = upload_track_form = request_transcript_form = None

    if 'new_track' in request.POST:
        new_track_form = TrackMetadataForm(request.POST)
        if new_track_form.is_valid():
            data = new_track_form.cleaned_data
            track = Track(item=item, **data)
            track.save()
            return redirect(edit_track, track_id=track.id)
    elif 'upload_track' in request.POST:
        upload_track_form = UploadTrackForm(request.POST, request.FILES)
        if upload_track_form.is_valid():
            data = upload_track_form.cleaned_data
            file_type = data['file_type']
            upload = request.FILES['caption_file']

            if file_type == 'srt':
                speakers = []
                clips = vtt.read(upload)
            elif file_type == 'xmp':
                speakers = []
                clips = xmp.read(upload)
            elif file_type == 'koemei':
                xml = ET.parse(upload)
                objects = koemei.reader.read(xml)
                speakers = objects['speakers']
                clips = objects['clips']
            elif file_type == 'sphinx':
                speakers = []
                clips = sphinx.reader.read_clips(upload)
            else:
                raise Exception('Unrecognised caption file format')

            track = Track(item=item, name=upload.name)
            track.save()

            for speaker in speakers:
                speaker.track = track
                speaker.save()

            for clip in clips:
                clip.track = track
                # Next line is necessary to save the foreign key
                # correctly. Sigh.
                clip.speaker = clip.speaker
                clip.save()

        return redirect(edit_track, track_id=track.id)
    elif 'request_transcript' in request.POST:
        request_transcript_form = RequestTranscriptForm(request.POST)
        if request_transcript_form.is_valid():
            engine = request_transcript_form.cleaned_data['engine']
            if engine not in spindle.transcribe.engine_map():
                raise Exception(u"Bad value for engine: {}".format(engine))

            item.request_transcription(engine)
            return redirect('spindle_queue')

    if new_track_form is None: new_track_form = TrackMetadataForm()
    if upload_track_form is None: upload_track_form = UploadTrackForm()
    if request_transcript_form is None: request_transcript_form = RequestTranscriptForm()

    return render(request, 'spindle/item_add_transcript.html', {
            'item': item,
            'new_track_form': new_track_form,
            'upload_track_form': upload_track_form,
            'request_transcript_form': request_transcript_form,
            })

# Version control
@require_POST
@login_required
def revert_item(request, version_id):
    version = get_object_or_404(ArchivedItem, pk=version_id)

    version.revert()
    return redirect(item_tracks, item_id=version.item.id)

@login_required
def diff_item(request, version_id):
    version = get_object_or_404(ArchivedItem, pk=version_id)

    diff_file = version.diff()
    resp = HttpResponse('', content_type='text/plain')
    for line in diff_file: resp.write(line)
    return resp


# Track-level operations

# Edit track
@login_required
def edit_track(request, track_id):
    track = get_object_or_404(Track, pk=track_id)
    item = track.item

    return render(request, 'spindle/edit.html', {
            'item': item,
            'track': track,
            })

# Track metadata
class TrackMetadataForm(ModelForm):
    class Meta:
        model = Track
        fields = ('name', 'kind', 'lang',
                  'publish_text', 'publish_vtt', 'publish_transcript')

class TrackMetaView(UpdateView):
    model = Track
    template_name = "spindle/track_meta.html"
    form_class = TrackMetadataForm
    pk_url_kwarg = 'track_id'
    template_object_name = 'track'

    def get_success_url(self, **kwargs):
        return reverse('spindle_track_meta', kwargs=self.kwargs)

    def get_context_data(self, **kwargs):
        context = super(TrackMetaView, self).get_context_data(**kwargs)
        context['item'] = context['track'].item
        return context

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        # logger.info("args=%s, kwargs=%s", args, kwargs)
        return super(TrackMetaView, self).dispatch(*args, **kwargs)

    def post(self, request, track_id, *args, **kwargs):
        response = super(TrackMetaView, self).post(request, *args,
                                                   track_id=track_id, **kwargs)
        if 'publish' in request.POST:
            item = Track.objects.get(pk=track_id).item
            logger.info("Publishing item %s", item)
            spindle.publish.publish_item(item)
        return response



# Display keywords
@login_required
def keywords(request, track_id):
    track = get_object_or_404(Track, pk=track_id)
    item = track.item
    text = (clip.caption_text for clip in track.clip_set.all())
    kw, ngrams = keywords_and_ngrams(text)

    def keyword_html(sorted_x):
        tags = ""
        for (word, ll) in sorted_x[0:100]:
            # Word size determined by log likelihood
            # only using 5 classes but we could follow wikipedia tag cloud equation
            # using tmax and tmin to determine the classes, ignored at the moment
            # until we know what we want as output
            size = int(ll / 20)
            if size > 4:
                size = 4
            tags += '<a href="#" class="tag c{}">{}</a> '.format(size, word)
        return tags

    def ngram_html(ngrams):
        tags = ""
        # scale = max(n for _, n in ngrams) if ngrams else 0

        for ((w1, w2), n) in reversed(ngrams):
            size = 4            # 4 * int(n / scale)
            tags += '<a href="#" class="tag c{}">{} {}</a> '.format(size, w1, w2)
        return tags

    return render(request, 'spindle/keywords.html', {
            'title': u"Keywords: '{}'".format(item.name),
            'item': item,
            'track': track,
            'keywordblock': keyword_html(kw),
            'ngramblock': ngram_html(ngrams),
            'oxitems_keywords': item.keywords
            })


# Transcription queue
@login_required
def queue(request):
    if request.POST:
        if 'delete_finished' in request.POST:
            for task in TranscriptionTask.queue.all():
                if task.status() in ('SUCCESS', 'FAILURE'):
                    task.delete()

        if 'delete_task' in request.POST:
            task_id = request.POST['delete_task_id']
            TranscriptionTask.queue.filter(task_id=task_id).delete()

        return redirect(queue)

    return render(request, 'spindle/queue.html', {
            'title': "Transcription queue",
            'queue': get_queue()
            })

@login_required
def queuepartial(request):
    return render(request, 'spindle/queuepartial.html', {
            'queue': get_queue()
            })

def get_queue():
    def sort_key(req):
        try:
            return ['PROGRESS',
                    'DOWNLOADING',
                    'TRANSCODING',
                    'PENDING',
                    'SUCCESS',
                    'FAILURE'].index(req['task'].status())
        except ValueError:
            return 0

    def format_status(task):
        if task.status() == 'PROGRESS':
            return "{}% complete".format(int(task.result()['progress'] * 100))
        else:
            try:
                return {'PENDING' : "Queued",
                        'DOWNLOADING' : 'Fetching media',
                        'TRANSCODING' : 'Converting audio',
                        'SUCCESS' : "Finished",
                        'FAILURE' : "Error"}[task.status()]
            except KeyError:
                return "Unknown"

    queue = []
    for task in TranscriptionTask.queue.all():
        req = dict(task=task, item=task.item)
        queue.append(req)

        req['raw_status'] = task.status()
        req['status'] = format_status(task)
        try:
            req['engine'] = spindle.transcribe.engine_map()[task.engine]['name']
        except:
            req['engine'] = ''
        req['is_running'] = req['raw_status'] in ('DOWNLOADING, TRANSCODING',
                                                  'PROGRESS')
        req['is_pending'] = req['raw_status'] in ('PENDING')
        req['is_finished'] = req['raw_status'] in ('SUCCESS', 'FAILURE')

        if task.status() == 'PROGRESS' or task.status() == 'RUNNING': # FIXME
            res = task.result()
            req['eta'] = res['eta']
            req['progress_bar'] = True
            req['percent'] = int(res['progress'] * 100)

    return sorted(queue, key=sort_key)


def run_tasks(request, task_classes):
    """Process requests involving long-running Celery tasks in a generic way."""
    tasks = dict((key, {}) for key in task_classes)

    # Find any running tasks
    for key, data in tasks.iteritems():
        task_class = task_classes[key]
        data['task'] = task_class.get_running_instance()
        # Start a new task if requested
        if key in request.POST and \
           (not data['task'] or data['task'].status == 'SUCCESS'):
            data['task'] = task_class.delay()


    # Make progress bars for any running tasks
    for key, data in tasks.iteritems():
        task = data['task']
        if not task:
            data['progress_bar'] = False
            data['progress'] = None
        else:
            data['progress_bar'] = True
            if task.status == 'PROGRESS':
                data['progress'] = task.result['progress'] * 100
            elif task.status == 'SUCCESS':
                data['progress'] = 100
            else:
                data['progress'] = 0

    return tasks


@json_login_required
def task_info(request, task_id):
    task_class = celery.task.base.Task
    task = task_class.AsyncResult(task_id)
    if task.status == 'PROGRESS':
        response = json.dumps(dict(status=task.status,
                                   result=task.result))
    else:
        response = json.dumps(dict(status=task.status))
    return HttpResponse(response, content_type='application/json')
