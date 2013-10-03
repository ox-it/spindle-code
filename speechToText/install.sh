#!/bin/bash

SPHINX_URL=http://sourceforge.net/projects/cmusphinx/files/sphinx4/1.0%20beta6/sphinx4-1.0beta6-src.zip/download
HUB4_ACOUSTIC_URL=http://sourceforge.net/projects/cmusphinx/files/Acoustic%20and%20Language%20Models/US%20English%20HUB4%20Acoustic%20Model/hub4opensrc.cd_continuous_8gau.zip/download
HUB4_TRIGRAM_URL=http://sourceforge.net/projects/cmusphinx/files/Acoustic%20and%20Language%20Models/US%20English%20HUB4%20Language%20Model/HUB4_trigram_lm.zip/download 
DICTIONARY_URL=https://svn.code.sf.net/p/cmusphinx/code/trunk/cmudict/sphinxdict/cmudict.0.7a_SPHINX_40

echo '* Downloading Sphinx 4'
curl -L $SPHINX_URL > sphinx.zip \
    && unzip -o sphinx.zip

echo '* Downloading HUB4 acoustic model'
(cd sphinx4-1.0beta6/models/acoustic/ \
    && curl -L $HUB4_ACOUSTIC_URL > hub4.zip \
    && unzip -o hub4.zip)

echo '* Downloading HUB4 language model'
(cd sphinx4-1.0beta6/models/language/ \
    && curl -L $HUB4_TRIGRAM_URL > hub4_trigram.zip \
    && unzip -o hub4_trigram.zip language_model.arpaformat.DMP)

echo '* Downloading cmudict'
(cd sphinx4-1.0beta6/models/  \
    && mkdir -p dictionary \
    && cd dictionary \
    && curl $DICTIONARY_URL > cmudict.0.7a_SPHINX_40)

echo '* Patching Transcriber.java'
patch sphinx4-1.0beta6/src/apps/edu/cmu/sphinx/demo/transcriber/Transcriber.java <<EOF
--- sphinx4-1.0beta6/src/apps/edu/cmu/sphinx/demo/transcriber/Transcriber.java.orig	2012-11-26 11:28:55.000000000 +0000
+++ sphinx4-1.0beta6/src/apps/edu/cmu/sphinx/demo/transcriber/Transcriber.java	2012-11-26 11:26:35.000000000 +0000
@@ -50,9 +50,9 @@
         // Loop until last utterance in the audio file has been decoded, in which case the recognizer will return null.
         Result result;
         while ((result = recognizer.recognize())!= null) {
-
-                String resultText = result.getBestResultNoFiller();
-                System.out.println(resultText);
+            if (result != null) {
+                System.out.println(result.getTimedBestResult(true, true)); 
+            }
         }
     }
 }
EOF

echo '* Copying config.xml'
cp config.xml sphinx4-1.0beta6/src/apps/edu/cmu/sphinx/demo/transcriber/ 

echo '* Building Sphinx'
(cd sphinx4-1.0beta6/ && ant)
