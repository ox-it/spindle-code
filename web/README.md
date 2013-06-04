# Spindle web interface

## Overview

This is a prototype system for combining automated speech recognition
with human editing and correction for indexing and transcribing
podcasts and open educational resources.  It has the following features:

  - import audio and video podcasts from RSS, matching up audio and
    video recordings of the same material where possible
  - import transcripts from formats including SRT/WebVTT, Adobe
    Premiere XMP files, and others 
  - edit imported transcripts in sync with the audio or video, or
    start with a blank transcript and create one from scratch
  - queue items for automated speech-to-text transcription, either
    using the freely available
    [CMU Sphinx4](http://cmusphinx.sourceforge.net/) system or
    interfacing with the Koemei ASR service (http://koemei.com)
  - automatically extract keywords for items with associated
    transcript text
  - export edited captions and transcripts in SRT, plain text, and
    HTML form
  - publish exported captions and transcripts to a directory of static
    files, with control over which items are published and in what
    form
  - publish a copy of the incoming RSS feed, including automatically
    extracted keywords as `<category>` tags

Some of these features are relatively complete; others are
experimental. This should be considered prototype/pre-alpha software
for now.

## Installation

The web interface is a Django application which requires recent
versions of Django and Python 2.7 to run. All the dependencies
are managed through the [pip](http://pypi.python.org/pypi/pip) Python
package manager, using the `requirements.txt` file.

While not required, it's probably a good idea to install
[virtualenv](http://www.virtualenv.org/en/latest/index.html) and
[virtualenvwrapper](http://www.doughellmann.com/projects/virtualenvwrapper/)
in order to keep the library dependencies separate.

Using `virtualenvwrapper`, the following commands should be enough
to install the web interface for testing purposes:

    mkvirtualenv spindle
    workon spindle
    git clone https://github.com/ox-it/spindle
    cd spindle
    pip install -r requirements.txt

## Configuring

Running the web interface requires configuring some local settings for
databases, file paths, etc. in the `demo/local_settings.py` file.

First, do

    cd demo
    cp local_settings.py.template local_settings.py

At a minimum, you need to set up a database for Django to store data
in.  The easiest option is an SQLite database, which doesn't require a
separate server or extra configuration.  In the new
`local_settings.py`, change the lines following `DATABASE` to
something like the following:

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': '/path/to/database/file.db',     
            ....

The database file can be located anywhere, and will be created
automatically (provided the containing directory exists).

To set up the database, from the `demo` directory run the following:

    ./manage.py syncdb
    ./manage.py createcachetable django_cache_table    
This step will also prompt you to create a "superuser" name and
password, which you will need once the server is running to be able to
log in.

Finally, run the following commands to create the database structures:

    ./manage.py migrate sitetree
    ./manage.py migrate spindle
    ./manage.py loaddata spindle/fixtures/sitetree.json

At this point you should be able to run the development server by doing

    ./manage.py runserver
    
and loading [http://localhost:8000/](http://localhost:8000/) in your
web browser. Log in using the username and password created above.

## Basic functionality

### Items

The web interface maintains a list of podcasts, or "items", each of
which has an identifying title and may have an audio URL, a video URL,
or both.  The audio and video files are assumed to be hosted somewhere
else -- there's no provision (yet) for uploading and storing files in
the platform itself.  For local testing you could simply use URLs with
a `localhost://` scheme.

The main screen presented on logging in is a list of all items in the
database.  Click on "New item", on the left hand side of the screen,
to add a new item to the system. (Or see the section below on
importing from RSS for an easier way).

The table of items can be sorted by different columns (by clicking on
the column header) and searched by title or URL.

### Transcripts

Text associated with an item is referred to as a "transcript", whether
it is intended to eventually take the form of a printed transcript,
video subtitles, or neither.  Each item may have any number of
separate transcripts associated with it.  For example, a lecture might
have subtitle tracks in multiple languages.  Newly created items have
no transcript associated; see the next section for ways to create a
transcript.

A "transcript", for the purpose of this program, is a collection of
captions: short text snippets with an "in" and "out" point for
synchronization with the associated audio or video.  To say this
another way, timecode information is maintained only at the level of
the caption -- not at the level of each word.  A caption usually lasts
for three to five seconds, and includes only about as much text as can
fit on one or two lines when displayed as a video caption.  This is a
similar model to [SRT/WebVTT](http://dev.w3.org/html5/webvtt/).

A transcript may also contain a list of speaker names, and captions
may have a speaker name associated with them.  For exporting
transcripts in more readable form, a caption may also be marked as
beginning a new paragraph in the printed transcript.  For more, see
the section on "Editing transcripts", below.

Each transcript may have a descriptive name. Transcripts can be
further categorized into one of five different kinds: "subtitles",
"captions", "chapters", "metadata", or "notes".  (These are then same
types supported by the HTML5 `<video>` tag).  However, no special use
is made of these categories internally yet.

### Creating transcripts

Clicking on an item in the list of items shows a list of all the
associated transcripts for that item, or instructions on creating a
transcript if none yet exist.  Creating a transcript can be done in
three ways, all listed under the "Add transcript" tab on the item
detail page:

- Create a blank transcript and start transcribing from scratch.

- Import an existing transcript file as created by another service: an
  SRT/WebVTT file, an XML `.xmp` file from Adobe Premiere's
  transcription engine, an output file from CMU Sphinx, or an output
  file from the Koemei service.
  
- Queue the item for automatic speech recognition transcription using
  Sphinx or Koemei. This requires additional configuration: see "other
  settings", below.
  
### Editing transcripts
    
Creating a new blank transcript, importing a transcript, or clicking
on a transcript from the item detail page opens the transcript editor.

Note that changes made in the editor will not be saved until clicking
the "Save" button on the right above the caption list!  A future
update should address this.

For simplicity, the remainder of this section refers to "video" only,
but exactly the same applies to transcripts of audio items.

The transcript editor is divided into two halves: the top half of the
screen shows the video player, the bottom half shows the transcript's
captions in a scrollable pane.  Video playback is synchronized with
text editing, in the following ways:

- If the video player is *paused*, clicking on a caption in the list
  moves the playback point to the "in" time for that caption.
  Similarly, moving the playback point manually with the mouse scrolls
  through the caption list so that the associated caption stays visible.

- When the video player is *playing*, no automatic scrolling happens,
  and clicking on captions in the list does not jump back to the start
  point.  The idea behind this is that if the transcript is mostly
  correct you should be able edit to edit its text on the fly while
  the video plays without causing the player to jump around.  (The
  "playback speed" menu between the video player and caption list
  allows changing playback speed to 75%, 60% or half normal speed,
  which may also help with this way of working.)
  
A few keyboard shortcuts facilitate working with the editor without
using the mouse. `Tab` and `Shift-Tab` move forward and back in the
list of captions.  `Ctrl-Space` plays and pauses the video.  In
addition, if the video playback has moved past the end of the caption
being edited when you press `Ctrl-Space`, the playback point will jump
back to the "in" point of the caption.  This is handy for checking and
double-checking a single caption as a "loop" when transcribing or
editing.

It's possible to split a long caption in two, or join a short caption
to the previous one.  To split a caption, put the cursor in the middle
of the text and press `Return`; to join a caption to the previous one,
put the cursor at the beginning and press `Delete` (`Backspace`).  A
word of caution: since there are no individual word timecodes, the in
and out points of captions which are split are inevitably approximate.
For some applications they may be good enough; however, a future
improvement should address this problem.

Finally, note that for transcript purposes it is useful to mark the
speaker of each caption and to mark the appropriate places as
paragraph breaks.  Controls to do this are between the timecode on the
left and the text field; they are hidden until moused over, to reduce
visual clutter.  To create new speakers or edit speaker names, choose
"Edit speakers..." from the pop-up menu.

Note that changing the speaker for a particular caption will apply the
same change to *all* the following captions up to the next change of
speaker.


## Other configuration settings

### RSS Importing
It's easiest to import podcasts into Spindle by pulling them from an
RSS feed. Set `SPINDLE_SCRAPE_RSS_URL` in `local_settings.py` to
enable this; then you can run `./manage.py spindle_scrape` to import
data, or use the "New item" page within the web interface.

### CMU Sphinx integration

The web platform can maintain a queue of items to be transcribed using
automatic speech recognition.  (A queue is necessary to limit the
number of simultaneous ASR processes, which are usually processor- and
memory-intensive and time-consuming, requiring at least the length of
the audio being transcribed).

One way to use this feature is to set up a local installation of
[CMU Sphinx4](http://cmusphinx.sourceforge.net/), a freely available
set of speech recognition tools written in Java.  See the
[instructions](https://github.com/ox-it/spindle-code/tree/master/speechToText/)
elsewhere in this repository for details: there are several pieces
which must be downloaded separately.  The Sphinx installation can be
anywhere on the filesystem, provided that permissions allow the Django
process to run it.

Once Sphinx is correctly set up in continuous large-vocabulary
recognition mode, the following steps are necessary to enable the web
platform to interface with it:

- In `local_settings.py`, set the `SPINDLE_SPHINX_DIRECTORY` variable
  to the root location of the CMU Sphinx installation.  That is,
  `"$SPINDLE_SPHINX_DIRECTORY/bin/Transcriber.jar"` should be an
  absolute path to the `Transcriber.jar` program.

- The asynchronous nature of the queue is managed using the
  [Celery](http://celeryproject.org/) framework.  These tasks will run
  in their own independent python process.  To start it, run the
  following command in the background (from the `demo/` directory):

    ./manage.py celery worker --settings=settings
    

### Koemei integration 

Spindle has some experimental support for integration with the
[Koemei](http://www.koemei.com) online speech-to-text service. To enable
this, you will need to sign up for a Koemei account through their web
page; then set the `SPINDLE_KOEMEI_USERNAME` and
`SPINDLE_KOEMEI_PASSWORD` configuration variables in
`local_settings.py`.

Integrating with Koemei also requires starting a Celery worker
process, as shown above.

### Public directories

Spindle can export transcripts in plain text, HTML and VTT formats,
and publish an annotated copy of the incoming RSS feed which includes
keywords automatically extracted from transcript text. See the
variables `SPINDLE_PUBLIC_DIRECTORY`, `SPINDLE_PUBLIC_URL`,
`SPINDLE_PUBLISH_RSS_NAME` in `local_settings.py`.

What gets published is controlled through the web interface.  From the
transcript editor, click on the "Publishing & Metadata" tab.  Actually
causing things to be published currently has to be done from the
command line:

    ./manage.py spindle_publish all
