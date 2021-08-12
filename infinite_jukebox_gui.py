"""infinite_jukebox.py - (c) 2017 - Dave Rensin - dave@rensin.com

An attempt to re-create the amazing Infinite Jukebox (http://www.infinitejuke.com)
created by Paul Lamere of Echo Nest. Uses the Remixatron module to do most of the
work.

"""

import argparse
import numpy as np
import os
import pygame
import pygame.event
import pygame.locals
import signal
import soundfile as sf
import sys
import time
import tkinter as tk


from Remixatron import InfiniteJukebox
from pygame import mixer

from gui_utils import *

SOUND_FINISHED = pygame.locals.USEREVENT + 1

def process_args():

    """ Process the command line args """

    description = """Creates an infinite remix of an audio file by finding musically similar beats and computing a randomized play path through them. The default choices should be suitable for a variety of musical styles. This work is inspired by the Infinite Jukebox (http://www.infinitejuke.com) project created by Paul Lamere (paul@spotify.com)"""

    epilog = """
    """

    parser = argparse.ArgumentParser(description=description, epilog=epilog, formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("filename", type=str,
                        help="the name of the audio file to play. Most common audio types should work. (mp3, wav, ogg, etc..)")

    parser.add_argument("-clusters", metavar='N', type=int, default=0,
                        help="set the number of clusters into which we want to bucket the audio. Default: 0 (automatically try to find the optimal cluster value.)")

    parser.add_argument("-start", metavar='start_beat', type=int, default=1,
                        help="start on a specific beat. Default: 1")

    parser.add_argument("-save", metavar='label', type=str,
                        help="Save the remix to a file, rather than play it. Will create file named [label].wav")

    parser.add_argument("-duration", metavar='seconds', type=int, default=180,
                        help="length (in seconds) to save. Must use with -save. Default: 180")

    parser.add_argument("-verbose", action='store_true',
                        help="print extra info about the track and play vector")

    parser.add_argument("-use_v1", action='store_true',
                        help="use the original auto clustering algorithm instead of the new one. -clusters must not be set.")

    return parser.parse_args()

def MyCallback(pct_complete, message):

    """ The callback function that gets status updates. Just prints a low-fi progress bar and reflects
        the status message passed in.

        Example: [######    ] Doing some thing...
    """

    progress_bar = " [" + "".ljust(int(pct_complete * 10),'#') + "".ljust(10 - int(pct_complete * 10), ' ') + "] "
    log_line =  progress_bar + message

    #window.clear()
    #window.addstr(1,0,log_line)
    #window.refresh()


def display_playback_progress(v):

    """
        Displays a super low-fi playback progress map

        See README.md for details..

        Returns the time this function took so we can deduct it from the
        sleep time for the beat
    """

    time_start = time.time()

    #term_width = curses.tigetnum('cols')

    y_offset = 11

    beat = v['beat']
    min_sequence = v['seq_len']
    current_sequence = v['seq_pos']

    # compute a segment map and display it. See README.md for an
    # explanation of segment maps and cluster maps.

    segment_map = ''
    segment_chars = '#-'

    for b in jukebox.beats:
        segment_map += segment_chars[ b['segment'] % 2 ]

    #window.addstr(y_offset,0,segment_map + " ")

    # highlight all the jump candidates in the segment
    # map

    for c in jukebox.beats[beat]['jump_candidates']:

        b = jukebox.beats[c]

        #window.addch(y_offset + int(b['id'] / term_width),   # y position of character
        #              b['id'] % term_width,                  # x position of character
        #              ord(segment_chars[b['segment'] %2]),   # either '#' or '-' depending on the segment
        #              curses.A_REVERSE)                      # print in reverse highlight

    # print the position tracker on the segment map

    #x_pos = beat % term_width
    #y_pos = int(beat/term_width) + y_offset

    beats_until_jump = min_sequence - current_sequence

    buj_disp = ''

    # show the beats until the next jump. If the value == 0 then
    # then sequence wanted to jump but couldn't find a suitable
    # target. Display an appropriate symbol for that (a frowny face, of course!)

    if beats_until_jump > 0:
        buj_disp = str(beats_until_jump).zfill(2)
    else:
        buj_disp = ':('

    #window.addstr(y_pos, x_pos, buj_disp, curses.A_BOLD | curses.A_REVERSE | curses.A_STANDOUT )

    #window.refresh()

    time_finish = time.time()

    return time_finish - time_start

def get_verbose_info():
    """Show statistics about the song and the analysis"""

    info = """
    filename: %s
    duration: %02d:%02d:%02d
       beats: %d
       tempo: %d bpm
    clusters: %d
    segments: %d
  samplerate: %d
    """

    (minutes,seconds) = divmod(round(jukebox.duration),60)
    (hours, minutes)  = divmod(minutes, 60)

    verbose_info = info % (os.path.basename(args.filename), hours, minutes, seconds,
                           len(jukebox.beats), int(round(jukebox.tempo)), jukebox.clusters, jukebox.segments,
                           jukebox.sample_rate)

    segment_map = ''
    cluster_map = ''

    segment_chars = '#-'
    cluster_chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz1234567890-=,.<>/?;:!@#$%^&*()_+'

    for b in jukebox.beats:
        segment_map += segment_chars[ b['segment'] % 2 ]
        cluster_map += cluster_chars[ b['cluster'] ]

    verbose_info += "\n" + segment_map + "\n\n"

    if args.verbose:
        verbose_info += cluster_map + "\n\n"

    verbose_info += jukebox._extra_diag

    return verbose_info

def get_window_contents():
    """Dump the contents of the current curses window."""

    #tbox = curses.textpad.Textbox(window)
    #tbox.stripspaces = False

    #w_str = tbox.gather()

    #return w_str

    pass

def cleanup():
    """Cleanup before exiting"""

    #if not window:
    #    return

    #w_str = get_window_contents()
    #curses.curs_set(1)
    #curses.endwin()

    #print(w_str.rstrip())
    #print

    mixer.quit()

def graceful_exit(signum, frame):

    """Catch SIGINT gracefully"""

    # restore the original signal handler as otherwise evil things will happen
    # in raw_input when CTRL+C is pressed, and our signal handler is not re-entrant
    signal.signal(signal.SIGINT, original_sigint)

    cleanup()
    sys.exit(0)

def save_to_file(jukebox, label, duration):
    ''' Save a fixed length of audio to disk. '''

    avg_beat_duration = 60 / jukebox.tempo
    num_beats_to_save = int(duration / avg_beat_duration)

    # this list comprehension returns all the 'buffer' arrays from the beats
    # associated with the [0..num_beats_to_save] entries in the play vector

    main_bytes = [jukebox.beats[v['beat']]['buffer'] for v in jukebox.play_vector[0:num_beats_to_save]]

    # main_bytes is an array of byte[] arrays. We need to flatten it to just a
    # regular byte[]

    output_bytes = np.concatenate( main_bytes )

    # write out the wav file
    sf.write(label + '.wav', output_bytes, jukebox.sample_rate, format='WAV', subtype='PCM_24')


if __name__ == "__main__":

    # store the original SIGINT handler and install a new handler
    original_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, graceful_exit)

    #
    # Main program logic
    #

    #window = None

    args = process_args()

    #curses.setupterm()

    #window = curses.initscr()
    #curses.curs_set(0)

    # do the clustering. Run synchronously. Post status messages to MyCallback()
    jukebox = InfiniteJukebox(filename=args.filename, start_beat=args.start, clusters=args.clusters,
                                progress_callback=MyCallback, do_async=False, use_v1=args.use_v1)

    # show more info about what was found
    #window.addstr(2,0, get_verbose_info())
    #window.refresh()

    # if we're just saving the remix to a file, then just
    # find the necessarry beats and do that

    if args.save:
        save_to_file(jukebox, args.save, args.duration)
        graceful_exit(0, 0)

    # it's important to make sure the mixer is setup with the
    # same sample rate as the audio. Otherwise the playback will
    # sound too slow/fast/awful

    mixer.init(frequency=jukebox.sample_rate)
    channel = mixer.Channel(0)

    # pygame's event handling functions won't work unless the
    # display module has been initialized -- even though we
    # won't be making any display calls.


    pygame.init()
    pygame.display.init()
    pygame.font.init()

    # register the event type we want fired when a sound buffer
    # finishes playing

    channel.set_endevent(SOUND_FINISHED)

    # queue and start playing the first event in the play vector. This is basic
    # audio double buffering that will reduce choppy audio from impercise timings. The
    # goal is to always have one beat in queue to play as soon as the last one is done.

    # Window size
    WINDOW_WIDTH = 1000
    WINDOW_HEIGHT = 600
    WINDOW_SURFACE = pygame.HWSURFACE | pygame.DOUBLEBUF | pygame.RESIZABLE
    window = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), WINDOW_SURFACE)

    font = pygame.font.SysFont(None, 20)

    DARK_BLUE = (3, 5, 54)

    ### Main Loop
    clock = pygame.time.Clock()
    done = False

    beat_num = 0
    snd = mixer.Sound(buffer=jukebox.beats[beat_num]['buffer'])
    channel.queue(snd)

    click = False
    is_paused = False

    while not done:
        # Update the window, but not more than 60fps
        window.fill(DARK_BLUE)

        draw_text('Infinite Jukebox', font, (255, 255, 255), window, 20, 20 )

        mx, my = pygame.mouse.get_pos()

        play_button = pygame.Rect(50, 100, 50, 50)
        if play_button.collidepoint((mx, my)):
            if click:
                if not is_paused:
                    channel.pause()
                    is_paused = True
                else:
                    mixer.unpause()
                    is_paused = False


        pygame.draw.rect(window, (255, 0, 0), play_button)

        click = False
        # Handle user-input
        for event in pygame.event.get():
            if (event.type == pygame.QUIT):
                done = True
            elif (event.type == SOUND_FINISHED):
                beat_num+=1
                # Channel2 sound ended, start another!
                snd = mixer.Sound(buffer=jukebox.beats[beat_num]['buffer'])
                channel.play(snd)
                print("Sound ended")
            if event.type == MOUSEBUTTONDOWN:
                if event.button == 1:
                    click = True


        #pygame.display.flip()
        pygame.display.update()

        # Clamp FPS
        clock.tick_busy_loop(60)



    pygame.quit()

    # beat_to_play = jukebox.beats[ jukebox.play_vector[0]['beat'] ]
    #
    # snd = mixer.Sound(buffer=beat_to_play['buffer'])
    # channel.queue(snd)
    #
    #
    #
    #
    # display_playback_progress(jukebox.play_vector[0])
    #
    # # go through the rest of  the playback list, start playing each beat, display
    # # the progress and wait for the playback to complete. Playback happens on another
    # # thread in the pygame library, so we have to wait to be signaled to queue another
    # # event.
    #
    # for v in jukebox.play_vector[1:]:
    #
    #     beat_to_play = jukebox.beats[ v['beat'] ]
    #
    #     snd = mixer.Sound(buffer=beat_to_play['buffer'])
    #     channel.queue(snd)
    #
    #
    #
    #     pygame.event.wait()
    #
    #     display_playback_progress(v)
