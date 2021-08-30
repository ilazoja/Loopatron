# Loopatron

This python program is designed to help find loops in songs. The program will output potential loops and through the user interface, the user can select the desired looping points by listening to the audio playback with the selected loops. Through the use of LoopingAudioConverter, the user can export the song as A brstm, a looping audio format used by games like Super Smash Brothers Brawl.

***
# Installation
Note: This application was tested on Python 3.7

pip install --upgrade pip  
pip install --user -r requirements.txt  

Then open Loopatron.json and set lacDir to the LoopingAudioConverter folder
***
# Usage

Loopatron.py 

When running this program, you will be greeted with a open file prompt, choose the song you'd like to loop. It will then begin to process the song. When finished, you should see the following screen:

**Example 1:**

Play a song infinitely.

    $ python infinite_jukebox.py i_cant_go_for_that.mp3

<img src='images/playback.png'/>

*Clusters* are buckets of musical similarity. Every beat belongs to exactly *one* cluster. Beats in the same cluster are musically similar -- ie. have similar pitch or timbre. When jumps are computed they always try to match clusters.

*Segments* are contiguous blocks of beats in the same cluster.

During playback the program displays a *segment map* of the song. This shows the general outline of the musical segments of the track. The bolded number is called the *position tracker*. The *location* of the tracker shows the position currently playing in the song. The *number* displayed in the tracker shows how many beats until a possible jump can occur. The highlighted characters in the segment map show the possible viable jump positions from the currently playing beat.

**Example 2:**

Play with verbose info.

    $ python infinite_jukebox.py test_audio_files/i_got_bills.mp3 -verbose

<img src="images/verbose.png"/>

The block of information under the segment map is the *cluster map*. This is the same layout as the segment map, except that the beats have been replaced by their cluster IDs. Beats with the same cluster ID are musically similar. In the above image, for example, we can see that the position tracker rests on a beat that belongs to cluster "5". (As do all the highlighted jump candidates.)

**Example 3:**

Create a 4 minute remix named *myRemix.wav*

    $ python infinite_jukebox.py i_cant_go_for_that.mp3 -save myRemix -duration 240

    [##########] ready

       filename: i_cant_go_for_that.mp3
       duration: 00:03:44
          beats: 396
          tempo: 110 bpm
       clusters: 14
     samplerate: 44100


***

# Some notes about the code

The core work is done in the InfiniteJukebox class in the Remixatron module. *infinite_jukebox.py* is just a simple demonstration on how to use that class.

The InfiniteJukebox class can do its processing in a background thread and reports progress via the progress_callback arg. To run in a thread, pass *async=True* to the constructor. In that case, it exposes an Event named *play_ready* -- which will be signaled when the processing is complete. The default mode is to run synchronously.

Simple async example:

      def MyCallback(percentage_complete_as_float, string_message):
        print "I am now %f percent complete with message: %s" % (percentage_complete_as_float * 100, string_message)

      jukebox = InfiniteJukebox(filename='some_file.mp3', progress_callback=MyCallback, async=True)
      jukebox.play_ready.wait()

      <some work here...>

Simple Non-async example:

      def MyCallback(percentage_complete_as_float, string_message):
        print "I am now %f percent complete with message: %s" % (percentage_complete_as_float * 100, string_message)

      jukebox = InfiniteJukebox(filename='some_file.mp3', progress_callback=MyCallback, async=False)

      <blocks until completion... some work here...>

Example: Playing the first 32 beats of a song:

    from Remixatron import InfiniteJukebox
    from pygame import mixer
    import time

    jukebox = InfiniteJukebox('some_file.mp3')
    mixer.init(frequency=jukebox.sample_rate)
    channel = pygame.mixer.Channel(0)

    for beat in jukebox.beats[0:32]:
        snd = mixer.Sound(buffer=beat['buffer'])
        channel.queue(snd)
        time.sleep(beat['duration'])
        
# Acknowledgements
B. McFee and D. Ellis for the [Laplacian Segmentation](https://librosa.org/librosa_gallery/auto_examples/plot_segmentation.html#sphx-glr-auto-examples-plot-segmentation-py) method

drensin for [Remixatron](https://github.com/drensin/Remixatron)

libertyernie for [LoopingAudioConverter](https://github.com/libertyernie/LoopingAudioConverter) as well as contributors to its dependencies

JGiubardo for the [Looper](https://github.com/JGiubardo/Looper) integration with LoopingAudioConverter
