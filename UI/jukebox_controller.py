import os
import time
import numpy as np
from pygame import mixer
import pygame.locals

from UI.gui_utils import *

SOUND_FINISHED = pygame.locals.USEREVENT + 1

class JukeboxController:

    def __init__(self, window, font, jukebox):
        self.window = window
        self.font = font

        self.volume = 1.0

        self.initialize_controller(jukebox)

    def initialize_controller(self, jukebox):
        self.jukebox = jukebox

        # mixer.init(frequency=jukebox.sample_rate)
        self.channel = mixer.Channel(0)
        self.channel.set_volume(self.volume)

        # register the event type we want fired when a sound buffer
        # finishes playing
        #self.channel.set_endevent(SOUND_FINISHED)

        self.is_paused = True
        self.beat_id = 0

        self.total_indices = jukebox.beats[-1]['stop_index'] - jukebox.beats[0]['start_index']

        self.last_selected_beat_id = 0

        #self.selected_end_index = jukebox.beats[-1]['stop_index']
        self.selected_end_beat_id = jukebox.beats[-1]['id']

        self.selected_jump_beat_num = 0
        self.selected_jump_beat_id = 0

        self.debounce = False

        self.export_timestamp = None

        self.playback_time = jukebox.beats[0]['start']
        self.last_time = 0

        self.create_and_play_playback_buffer()

    def create_and_play_playback_buffer(self, max_buffer = None):
        ## create buffer of audio path (because playing chunks at a time causes choppiness)
        if not max_buffer:
            max_buffer = len(self.jukebox.raw_audio)

        self.channel.stop()

        if len(self.jukebox.raw_audio.shape) == 1:
            playback_buffer = np.zeros([max_buffer], dtype='int16')
        else:
            playback_buffer = np.zeros([max_buffer, 2], dtype='int16')

        current_pos = 0
        current_beat_id = self.beat_id
        current_buffer = self.jukebox.beats[current_beat_id]['buffer']

        while (current_pos + len(current_buffer)) < max_buffer:

            # Assign buffer from beat
            if len(playback_buffer.shape) == 1:
                playback_buffer[current_pos:current_pos + len(current_buffer)] = current_buffer
            else:
                playback_buffer[current_pos:current_pos + len(current_buffer)] = current_buffer

            current_pos += len(current_buffer)

            # If on selected end beat, go to selected jump beat, otherwise increment by 1
            if current_beat_id == self.selected_end_beat_id:
                current_beat_id = self.selected_jump_beat_id
            else:
                current_beat_id += 1
                if current_beat_id >= len(self.jukebox.beats):  # if no beats left (i.e. song finished)
                    current_beat_id = 0

            current_buffer = self.jukebox.beats[current_beat_id]['buffer']


        if len(playback_buffer.shape) == 1:
            playback_buffer = playback_buffer[0:current_pos - len(current_buffer)]
        else:
            playback_buffer = playback_buffer[0:current_pos - len(current_buffer), :]

        snd = mixer.Sound(buffer=playback_buffer)
        self.channel.queue(snd)
        self.playback_time = self.jukebox.beats[self.beat_id]['start']
        if self.is_paused:
            self.channel.pause()

    def playback_timer(self):
        ## Because audio path is premade, this function will keep track of the current beat based on time (Note: breakpoints breaks this) so slider UI can update
        current_time = time.time()
        if not self.is_paused:
            self.playback_time += current_time - self.last_time

            current_beat_end_time = self.jukebox.beats[self.beat_id]['start'] + self.jukebox.beats[self.beat_id]['duration']

            # If current time is past the current beat
            if self.playback_time > current_beat_end_time:

                # If on selected end beat, go to selected jump beat, otherwise increment by 1
                if self.beat_id == self.selected_end_beat_id:
                    self.beat_id = self.selected_jump_beat_id
                else:
                    self.beat_id += 1
                    if self.beat_id >= len(self.jukebox.beats): # if no beats left (i.e. song finished
                        self.beat_id = 0

                self.playback_time = (self.playback_time - current_beat_end_time) + self.jukebox.beats[self.beat_id]['start']

        self.last_time = current_time


    def get_verbose_info(self, verbose):
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

        (minutes, seconds) = divmod(round(self.jukebox.duration), 60)
        (hours, minutes) = divmod(minutes, 60)

        verbose_info = info % (self.jukebox.filename, hours, minutes, seconds,
                               len(self.jukebox.beats), int(round(self.jukebox.tempo)), self.jukebox.clusters, self.jukebox.segments,
                               self.jukebox.sample_rate)

        segment_map = ''
        cluster_map = ''

        segment_chars = '#-'
        cluster_chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz1234567890-=,.<>/?;:!@#$%^&*()_+'

        for b in self.jukebox.beats:
            segment_map += segment_chars[b['segment'] % 2]
            cluster_map += cluster_chars[b['cluster']]

        verbose_info += "\n" + segment_map + "\n\n"

        if verbose:
            verbose_info += cluster_map + "\n\n"

        verbose_info += self.jukebox._extra_diag

        return verbose_info

    def draw_loop_points_text(self):
        x = WINDOW_WIDTH - BUTTON_WIDTH * 5
        y = WINDOW_HEIGHT - BUTTON_WIDTH - 10

        draw_text(f"Start: {self.jukebox.start_index}", self.font, Color.WHITE.value, self.window, x, y)

        start_offset = self.jukebox.beats[self.selected_jump_beat_id]['start_index']
        loop_offset = self.jukebox.beats[self.selected_end_beat_id]['stop_index']
        draw_text(f"Start Loop: {start_offset}", self.font, Color.WHITE.value, self.window, x, y + 15)
        draw_text(f"End Loop: {loop_offset}", self.font, Color.WHITE.value, self.window, x, y + 30)

    def draw_status_text(self):
        if self.export_timestamp:
            draw_text(f'Exported to brstm at {self.export_timestamp}', self.font, Color.GREEN.value, self.window, 20, 40)
        else:
            draw_text(f'Processed in {self.jukebox.time_elapsed:4.1f}s', self.font, Color.GREEN.value, self.window, 20, 40)

    def select_file(self):
        self.channel.stop()  # Stop before opening prompt otherwise playback will speed up
        return prompt_file()

    def open_button(self, click, mx, my):

        ## Open a new file
        x = WINDOW_WIDTH - BUTTON_WIDTH*2 - 10
        y = 20
        w = BUTTON_WIDTH*2
        h = BUTTON_WIDTH

        open_button_box = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.window, Color.GRAY.value, open_button_box)
        draw_text("Open [O]", self.font, Color.WHITE.value, self.window, x, y + h / 2)
        if open_button_box.collidepoint((mx, my)):
            if click == (1, 0, 0):
                return self.select_file()

        return None

    def write_points_to_file(self, lac_dir = ""):
        start_offset = self.jukebox.beats[self.selected_jump_beat_id]['start_index']
        loop_offset = self.jukebox.beats[self.selected_end_beat_id]['stop_index']
        with open(os.path.join(lac_dir, "loop.txt"), "w") as output:
            output.write("\n%d " % (self.jukebox.start_index + start_offset))
            output.write("%d " % (self.jukebox.start_index + loop_offset))
            output.write(os.path.basename(self.jukebox.filename))

    def export_brstm(self):
        self.channel.pause()
        self.is_paused = True
        self.write_points_to_file(LAC_DIR)
        run_lac(self.jukebox.filename)
        self.create_and_play_playback_buffer()
        return get_timestamp()

    def export_button(self, click, mx, my):

        ## Export loop
        x = WINDOW_WIDTH - BUTTON_WIDTH*2 - 10
        y = WINDOW_HEIGHT - BUTTON_WIDTH - 10
        w = BUTTON_WIDTH*2
        h = BUTTON_WIDTH

        export_button_box = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.window, Color.DARK_ORANGE.value, export_button_box)
        draw_text("Export [E]", self.font, Color.WHITE.value, self.window, x, y + h / 2)
        if export_button_box.collidepoint((mx, my)):
            if click == (1, 0, 0):
                return self.export_brstm()
        return None

    def play_pause(self):
        if not self.is_paused:
            self.channel.pause()
            self.is_paused = True
        else:
            self.create_and_play_playback_buffer()
            self.channel.unpause()
            self.is_paused = False


    def play_button(self, click, mx, my):

        ## Play / pause
        x = WINDOW_WIDTH / 2 - BUTTON_WIDTH / 2
        y = WINDOW_HEIGHT - BUTTON_WIDTH - 10
        w = BUTTON_WIDTH

        play_button_box = pygame.Rect(x, y, w, w)
        if play_button_box.collidepoint((mx, my)):
            if click == (1, 0, 0):
                if not self.debounce:
                    self.play_pause()
                self.debounce = True
            else:
                self.debounce = False

        if self.is_paused:
            pygame.draw.rect(self.window, Color.GREEN.value, play_button_box)
            draw_text("[SPACE]", self.font, Color.WHITE.value, self.window, x, y + w/2)
        else:
            pygame.draw.rect(self.window, Color.RED.value, play_button_box)
            draw_text("[SPACE]", self.font, Color.WHITE.value, self.window, x, y + w / 2)


    def set_beat_to_last_selected(self):
        if (self.last_selected_beat_id >= 0):
            self.beat_id = self.last_selected_beat_id
            self.create_and_play_playback_buffer()

    def back_button(self, click, mx, my):
        ## Rewind to where cursor was last placed
        x = WINDOW_WIDTH / 2 - BUTTON_WIDTH
        y = WINDOW_HEIGHT - BUTTON_WIDTH - 10
        w = BUTTON_WIDTH / 2
        h = BUTTON_WIDTH
        back_button_box = pygame.Rect(x, y, w, h)
        if back_button_box.collidepoint((mx, my)):
            if click == (1, 0, 0):
                if not self.debounce:
                    self.set_beat_to_last_selected()
                self.debounce = True
            else:
                self.debounce = False

        pygame.draw.rect(self.window, Color.BLACK.value, back_button_box)
        draw_text("[B]", self.font, Color.WHITE.value, self.window, x, y + h / 2)

    def increment_jump_beat(self, increment):
        self.selected_jump_beat_num += increment
        # If the selected jump beat number is outside range of jump beats
        jump_beats = self.jukebox.beats[self.selected_end_beat_id]['jump_candidates']
        if self.selected_jump_beat_num >= len(jump_beats):
            self.selected_jump_beat_num = 0
        elif self.selected_jump_beat_num < 0:
            self.selected_jump_beat_num = len(jump_beats) - 1

        if len(jump_beats):
            self.selected_jump_beat_id = jump_beats[self.selected_jump_beat_num]
            self.create_and_play_playback_buffer()

    def jump_buttons(self, click, mx, my):
        x = WINDOW_WIDTH / 2 + BUTTON_WIDTH
        y = WINDOW_HEIGHT - BUTTON_WIDTH - 10
        w = BUTTON_WIDTH / 2
        h = BUTTON_WIDTH
        increment_left_button_box = pygame.Rect(x, y, w, h)
        if increment_left_button_box.collidepoint((mx, my)):
            if click == (1, 0, 0):
                if not self.debounce:
                    self.increment_jump_beat(-1)
                self.debounce = True
            else:
                self.debounce = False

        pygame.draw.rect(self.window, Color.YELLOW.value, increment_left_button_box)
        draw_text("<-", self.font, Color.BLACK.value, self.window, x, y + h / 2)

        x += w
        increment_right_button_box = pygame.Rect(x, y, w, h)
        if increment_right_button_box.collidepoint((mx, my)):
            if click == (1, 0, 0):
                if not self.debounce:
                    self.increment_jump_beat(1)
                self.debounce = True
            else:
                self.debounce = False

        pygame.draw.rect(self.window, Color.YELLOW.value, increment_right_button_box)
        draw_text("->", self.font, Color.BLACK.value, self.window, x + w/2, y + h / 2)

        pygame.draw.rect(self.window, Color.BLACK.value, [x, y, SCROLL_WIDTH, h])

    def set_volume(self, new_volume=1.0):
        new_volume = max(0, min(new_volume, 1.0))

        self.volume = new_volume
        self.channel.set_volume(self.volume)

    def volume_slider(self, click, mx, my):
        x = BAR_X
        y = WINDOW_HEIGHT - BUTTON_WIDTH - 10
        w = BAR_WIDTH / 4
        h = BUTTON_WIDTH
        volume_slider_bar = pygame.Rect(BAR_X, y, w, h)

        if volume_slider_bar.collidepoint((mx, my)):
            if click == (1, 0, 0):
                volume = ((mx - BAR_X) / (BAR_WIDTH / 4))
                self.set_volume(volume)

        volume_slider_bar = pygame.Rect(x, y + h/4, w, h/4)
        pygame.draw.rect(self.window, Color.GRAY.value, volume_slider_bar)

        x_line = BAR_X + (self.volume) * BAR_WIDTH / 4

        pygame.draw.rect(self.window, Color.GRAY.value, [x_line - SCROLL_WIDTH / 2, WINDOW_HEIGHT - BUTTON_WIDTH - 10, SCROLL_WIDTH*2, BUTTON_WIDTH])

    def music_slider(self, click, mx, my):

        music_slider_bar = pygame.Rect(BAR_X, WINDOW_HEIGHT - BUTTON_WIDTH - 20 - BAR_HEIGHT - 10, BAR_WIDTH, BAR_HEIGHT)

        ## Handle mouse
        scroll_index = -1
        selected_end_index = -1
        if music_slider_bar.collidepoint((mx, my)):
            if click == (1, 0, 0):
                scroll_index = ((mx - BAR_X) / BAR_WIDTH) * float(self.total_indices) + self.jukebox.beats[0]['start_index']
            elif click == (0, 0, 1):
                selected_end_index = ((mx - BAR_X) / BAR_WIDTH) * float(self.total_indices) + self.jukebox.beats[0]['start_index']
                self.selected_end_beat_id = self.jukebox.beats[-1]['id']
                self.selected_jump_beat_num = 0
                self.selected_jump_beat_id = 0

        pygame.draw.rect(self.window, Color.GRAY.value, music_slider_bar)

        current_jump_beat_num = 0
        current_segment = -1
        for beat in self.jukebox.beats:
            x_line = BAR_X + (float(beat['start_index'] - self.jukebox.beats[0]['start_index']) /
                              float(self.total_indices)) * BAR_WIDTH

            if scroll_index >= beat['start_index'] and scroll_index < beat['stop_index']: # find beat which index belongs to

                ## If start indices doesn't match, i.e. the scroll bar was moved, set beat id to new beat
                if self.beat_id != beat['id']:
                    self.beat_id = beat['id']
                    self.last_selected_beat_id = self.beat_id
                    self.create_and_play_playback_buffer()


            ## Draw segment borders in white
            if beat['segment'] > current_segment:
                current_segment = beat['segment']

                pygame.draw.rect(self.window, Color.WHITE.value,
                                 [x_line - SEGMENT_LINE_WIDTH/2, WINDOW_HEIGHT - BUTTON_WIDTH - 20 - BAR_HEIGHT - 20, SEGMENT_LINE_WIDTH,
                                  BAR_HEIGHT + 20])

            current_beat_color = None
            for jump_beat_id in beat['jump_candidates']:

                current_beat_color = Color.LIGHT_BLUE.value # Highlight beats with a earlier loop in light blue
                if selected_end_index >= beat['start_index'] and selected_end_index < beat['stop_index']: # find beat which selected end index belongs to
                    ## If id doesn't match, i.e. the end bar was moved, set end beat id to new beat
                    if self.selected_end_beat_id != beat['id']:
                        self.selected_end_beat_id = beat['id']
                        self.create_and_play_playback_buffer()

                if self.selected_end_beat_id == beat['id']:
                    current_beat_color = Color.FIREBRICK.value # Highlight selected beat with ealier loop in red

                    x_jump_line = BAR_X + (float(self.jukebox.beats[jump_beat_id]['start_index'] - self.jukebox.beats[0]['start_index']) /
                                           float(self.total_indices)) * BAR_WIDTH

                    # Highlight selected jump beat in green, other ones in yellow
                    jump_beat_color = Color.YELLOW.value
                    if self.selected_jump_beat_num == current_jump_beat_num:
                        self.selected_jump_beat_id = jump_beat_id
                        jump_beat_color = Color.FOREST_GREEN.value

                    pygame.draw.rect(self.window, jump_beat_color,
                                     [x_jump_line - SEGMENT_LINE_WIDTH / 2,
                                      WINDOW_HEIGHT - BUTTON_WIDTH - 20 - BAR_HEIGHT - 10, SEGMENT_LINE_WIDTH,
                                      BAR_HEIGHT])

                    current_jump_beat_num += 1

            # Color current beat if it had a jump beat
            if current_beat_color:
                pygame.draw.rect(self.window, current_beat_color,
                         [x_line - SEGMENT_LINE_WIDTH / 2,
                          WINDOW_HEIGHT - BUTTON_WIDTH - 20 - BAR_HEIGHT - 10, SEGMENT_LINE_WIDTH,
                          BAR_HEIGHT])



        # Draw last selected scroll location
        x_line = BAR_X + (float(self.jukebox.beats[self.last_selected_beat_id]['start_index'] - self.jukebox.beats[0]['start_index']) /
                 float(self.total_indices)) * BAR_WIDTH
        pygame.draw.rect(self.window, Color.BLACK.value,
                         [x_line - SCROLL_WIDTH / 2, WINDOW_HEIGHT - BUTTON_WIDTH - 20 - BAR_HEIGHT - 20,
                          SCROLL_WIDTH, (BAR_HEIGHT + 20)/4])

        # Draw scroll location
        x_line = BAR_X + (float(self.jukebox.beats[self.beat_id]['start_index'] - self.jukebox.beats[0]['start_index']) /
                          float(self.total_indices)) * BAR_WIDTH
        pygame.draw.rect(self.window, Color.BLACK.value, [x_line - SCROLL_WIDTH / 2, WINDOW_HEIGHT - BUTTON_WIDTH - 20 - BAR_HEIGHT - 20, SCROLL_WIDTH, BAR_HEIGHT + 20])


    ## Right click, highlight a beat (closest beat with jump beat to the left) in red and beats to transition to in yellow, select which jump beats using arrow keys

    # TODO: Display audio signal?

    # TODO: Export loop, automatically convert using LoopingAudioConverter
    # Need to include message if it completed successfully or not
    # Need to fix LAC, since it hangs when using command line

    # TODO: Manual set loop using shift left and right click? Maybe highlight same clusters as current selection when holding shift

    ## Fixed audio playback
    # Tried a timer and different channels, still can be choppy
    # Pre-made buffer works, redid functionality so a buffer is made taking loop points into account, and timer updates UI accordingly

    # TODO: Update status during loading (doesn't update, would have to use async, not sure affect on performance)

    # TODO: Make more efficient? (already included some multiprocessing)

    # TODO: Remove beginning silence when making brstm

    # TODO: Allow resize window?

    # TODO: Total Clusters to try argument, multi-processing argument, cut beginning silence argument
