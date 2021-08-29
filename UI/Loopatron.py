"""infinite_jukebox.py - (c) 2017 - Dave Rensin - dave@rensin.com

An attempt to re-create the amazing Infinite Jukebox (http://www.infinitejuke.com)
created by Paul Lamere of Echo Nest. Uses the Remixatron module to do most of the
work.

"""

import argparse
import os
import pygame.event
import pygame.locals
import signal
import time
import multiprocessing

from Remixatron import InfiniteJukebox
from pygame import mixer

from utils import *
from jukebox_controller import JukeboxController

SOUND_FINISHED = pygame.locals.USEREVENT + 1


def process_args():

    """ Process the command line args """

    description = """Creates an infinite remix of an audio file by finding musically similar beats and computing a randomized play path through them. The default choices should be suitable for a variety of musical styles. This work is inspired by the Infinite Jukebox (http://www.infinitejuke.com) project created by Paul Lamere (paul@spotify.com)"""

    epilog = """
    """

    parser = argparse.ArgumentParser(description=description, epilog=epilog, formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("filepath", type=str,
                        help="the name of the audio file to play. Most common audio types should work. (mp3, wav, ogg, etc..)")

    parser.add_argument("-clusters", metavar='N', type=int, default=0,
                        help="set the number of clusters into which we want to bucket the audio. Default: 0 (automatically try to find the optimal cluster value.)")

    parser.add_argument("-verbose", action='store_true',
                        help="print extra info about the track and play vector")

    parser.add_argument("-use_v1", action='store_true',
                        help="use the original auto clustering algorithm instead of the new one. -clusters must not be set.")

    return parser.parse_args()

def NoCallback(pct_complete, message, filepath):
    pass

def UpdateMessageCallback(pct_complete, message, filepath):
    draw_status_message_and_update(f'Loopatron - {os.path.basename(filepath)}', f'{str(pct_complete*100)}% - {message}', font, Color.DARK_ORANGE.value, window)

def cleanup(current_songname = None, keep_cache = False, keep_evec_cache = False):
    """Cleanup before exiting"""

    #if not window:
    #    return

    #w_str = get_window_contents()
    #curses.curs_set(1)
    #curses.endwin()

    #print(w_str.rstrip())
    #print

    if current_songname:
        if not keep_cache:
            if os.path.isfile(os.path.join(CONFIG['cacheDir'], current_songname + '.csv')):
                os.remove(os.path.join(CONFIG['cacheDir'], current_songname + '.csv'))
        if not keep_evec_cache:
            if os.path.isfile(os.path.join(CONFIG['cacheDir'], current_songname + '.npy')):
                os.remove(os.path.join(CONFIG['cacheDir'], current_songname + '.npy'))

    mixer.quit()

def graceful_exit(signum, frame):

    """Catch SIGINT gracefully"""

    # restore the original signal handler as otherwise evil things will happen
    # in raw_input when CTRL+C is pressed, and our signal handler is not re-entrant
    signal.signal(signal.SIGINT, original_sigint)

    cleanup()
    sys.exit(0)

def run_looping_audio_converter():
    pass

def initialize_jukebox(filepath, do_async = False):

    #pygame.display.quit()
    #pygame.font.quit()
    mixer.quit()

    config = get_config()
    jukebox = InfiniteJukebox(filepath=filepath, start_beat=0, use_cache = True,
                              clusters=config['clusters'], max_clusters = config['maxClusters'],
                              progress_callback=UpdateMessageCallback, do_async=do_async, use_v1=config['useV1'])

    jukebox.save_cache(cache_evecs = True)

    if not do_async:
        # it's important to make sure the mixer is setup with the
        # same sample rate as the audio. Otherwise the playback will
        # sound too slow/fast/awful
        mixer.init(frequency=jukebox.sample_rate)

    return jukebox

def play_loop(filepath):
    # do the clustering. Run synchronously. Post status messages to MyCallback()
    #jukebox = initialize_jukebox(filepath)
    #jukebox_controller = JukeboxController(window, jukebox)

    ### Main Loop
    clock = pygame.time.Clock()
    done = False

    pygame.display.set_caption("Loopatron - Loading...")
    draw_status_message_and_update(f'Loopatron - {os.path.basename(filepath)}', f'Loading...', font, Color.DARK_ORANGE.value, window)
    jukebox = initialize_jukebox(filepath)
    jukebox_controller = JukeboxController(window, font, jukebox)
    is_init = True
    last_click = (0, 0, 0)
    while not done:
        # Update the window, but not more than 60fps
        #window.fill(Color.DARK_BLUE.value)
        #draw_text(f'Loopatron - {os.path.basename(filepath)}', font, Color.WHITE.value, window, 20, 20)
        #draw_text(VERSION, font, Color.WHITE.value, window, window.get_width() - BUTTON_WIDTH * 3 - 20, 20)


        if not is_init:
            if len(filepath) > 1:
                cache_selected_files(filepath)


            filepath = filepath[0]
            pygame.display.set_caption("Loopatron - Loading...")
            draw_status_message_and_update(f'Loopatron - {os.path.basename(filepath)}', f'Loading...', font,
                                           Color.DARK_ORANGE.value, window)
            #draw_text(f'Loading...', font, Color.GREEN.value, window, 20, 40)
            #pygame.display.update()
            jukebox = initialize_jukebox(filepath)
            jukebox_controller.initialize_controller(jukebox)
            is_init = True
        else:
            window.fill(Color.DARK_BLUE.value)
            draw_text(f'Loopatron - {os.path.basename(filepath)}', font, Color.WHITE.value, window, 20, 20)

            jukebox_controller.playback_timer()

            pygame.display.set_caption(f'Loopatron - {os.path.basename(filepath)}')
            mx, my = pygame.mouse.get_pos()
            click = pygame.mouse.get_pressed()
            keys = pygame.key.get_pressed()

            jukebox_controller.play_button(click, mx, my)
            jukebox_controller.back_button(click, mx, my)
            jukebox_controller.jump_buttons(click, mx, my)
            jukebox_controller.toggle_trim_button(click, mx, my)
            jukebox_controller.volume_slider(click, mx, my)
            jukebox_controller.music_slider(click, mx, my, keys)

            if not jukebox_controller.channel.get_busy():
                jukebox_controller.create_and_play_playback_buffer()
            # Handle user-input
            for event in pygame.event.get():
                if (event.type == pygame.QUIT):
                    config = get_config()
                    keep_cache = (jukebox.time_elapsed < 0) or config['alwaysCache'] # keep cache if jukebox was retrieved from cache or if always cache
                    keep_evec_cache = (jukebox.time_elapsed < 0) or (config['alwaysCache'] and config['cacheEvecs'])
                    cleanup(Path(filepath).stem, keep_cache, keep_evec_cache)
                    done = True
                #elif (event.type == pygame.VIDEORESIZE):
                    #window.blit(pygame.transform.scale(window_copy, event.dict['size']), (0, 0))
                #elif (event.type == SOUND_FINISHED):
                    #jukebox_controller.on_sound_finished()
                    #print("Sound ended")
                elif (event.type == pygame.KEYUP):
                    if (event.key == pygame.K_SPACE):
                        jukebox_controller.play_pause()
                    elif (event.key == pygame.K_b):
                        jukebox_controller.set_beat_to_last_selected()
                    elif (event.key == pygame.K_UP):
                        jukebox_controller.set_volume(jukebox_controller.volume + 0.05)
                    elif (event.key == pygame.K_DOWN):
                        jukebox_controller.set_volume(jukebox_controller.volume - 0.05)
                    elif (event.key == pygame.K_LEFT):
                        jukebox_controller.increment_jump_beat(-1)
                    elif (event.key == pygame.K_RIGHT):
                        jukebox_controller.increment_jump_beat(1)
                    elif (event.key == pygame.K_t):
                        jukebox_controller.toggle_trim()
                    elif (event.key == pygame.K_1):
                        jukebox_controller.recluster(clusters = 10)
                    elif (event.key == pygame.K_2):
                        jukebox_controller.recluster(clusters = 20)
                    elif (event.key == pygame.K_3):
                        jukebox_controller.recluster(clusters = 30)
                    elif (event.key == pygame.K_4):
                        jukebox_controller.recluster(clusters = 40)
                    elif (event.key == pygame.K_5):
                        jukebox_controller.recluster(clusters = 50)
                    elif (event.key == pygame.K_6):
                        jukebox_controller.recluster(clusters = 60)
                    elif (event.key == pygame.K_7):
                        jukebox_controller.recluster(clusters = 70)
                    elif (event.key == pygame.K_8):
                        jukebox_controller.recluster(clusters = 80)
                    elif (event.key == pygame.K_9):
                        jukebox_controller.recluster(clusters = 90)
                    elif (event.key == pygame.K_0):
                        jukebox_controller.recluster(clusters = 0)
                    elif (event.key == pygame.K_e):
                        jukebox_controller.export_brstm()
                    elif (event.key == pygame.K_o):
                        selected_filepath = jukebox_controller.select_file()
                        if selected_filepath:
                            filepath = selected_filepath
                            is_init = False
                #elif event.type == MOUSEWHEEL:
                #    jukebox_controller.increment_jump_beat(event.y)

            if last_click != (1, 0, 0): # Allow export to only happen on single click (rather than accidentally going over button while holding mouse down)
                jukebox_controller.export_button(click, mx, my)
            else:
                jukebox_controller.export_button((0, 0, 0), mx, my)

            if last_click != (1, 0, 0):
                button_response = jukebox_controller.open_button(click, mx, my)
                if button_response:
                    filepath = button_response
                    is_init = False
            else:
                jukebox_controller.open_button((0, 0, 0), mx, my)

            last_click = click

            jukebox_controller.draw_loop_points_text()
            jukebox_controller.draw_status_text()

            # pygame.display.flip()
            pygame.display.update()

        # Clamp FPS
        clock.tick_busy_loop(60)

    mixer.quit()
    pygame.quit()

def cache_selected_files(filepaths):

    pygame.display.set_caption("Loopatron - Caching...")
    draw_status_message_and_update(f'Loopatron - Caching...', f'Processing {len(filepaths)} songs...', font, Color.DARK_ORANGE.value, window)

    config = get_config()
    for i, filepath in enumerate(filepaths):
        draw_status_message(f'Loopatron - Caching...', f'Processing ({i + 1}/{len(filepaths)}) {os.path.basename(filepath)}...', font, Color.DARK_ORANGE.value, window)

        text_y = 60
        for prev_filepath in reversed(filepaths[:i]):
            draw_text(f'Processed {os.path.basename(prev_filepath)}', font, Color.GREEN.value, window, 20, text_y)
            text_y += 20

        pygame.display.update()

        jukebox = InfiniteJukebox(filepath=filepath, start_beat=0, use_cache = False, clusters=config['clusters'],
                                  max_clusters=config['maxClusters'],
                                  progress_callback=NoCallback, do_async=False, use_v1=config['useV1'])

        jukebox.save_cache(config['cacheEvecs'])



    notify(f"Finished processing and caching {len(filepaths)} songs")

    #os.path.join(LAC_DIR, 'cache', Path(filepath).stem + 'csv')

if __name__ == "__main__":
    multiprocessing.freeze_support() # Needed for pyinstaller and multiprocessing with pygame

    # store the original SIGINT handler and install a new handler
    original_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, graceful_exit)

    #
    # Main program logic
    #

    #args = process_args()

    # if we're just saving the remix to a file, then just
    # find the necessarry beats and do that

    #if args.save:
    #    save_to_file(jukebox, args.save, args.duration)
    #    graceful_exit(0, 0)

    # queue and start playing the first event in the play vector. This is basic
    # audio double buffering that will reduce choppy audio from impercise timings. The
    # goal is to always have one beat in queue to play as soon as the last one is done.

    # pygame's event handling functions won't work unless the
    # display module has been initialized -- even though we
    # won't be making any display calls.

    #pygame.init()
    pygame.display.init()
    pygame.font.init()

    # Window size
    WINDOW_SURFACE = pygame.HWSURFACE | pygame.DOUBLEBUF | pygame.RESIZABLE
    window = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), WINDOW_SURFACE)
    pygame.display.set_caption("Loopatron")
    #font = pygame.font.SysFont(None, 20)
    font = pygame.font.Font(CONFIG['fontPath'], 15)
    #font = pygame.font.SysFont('arial', 20)

    filepaths = prompt_file(select_multiple=True)

    if len(filepaths) == 1:
        play_loop(filepaths[0])
    elif len(filepaths) > 1:
        cache_selected_files(filepaths)
        play_loop(filepaths[0])
    #pygame.quit()


