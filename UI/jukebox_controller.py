import os
import time
import numpy as np
from pygame import mixer
import pygame.locals

from utils import *

SOUND_FINISHED = pygame.locals.USEREVENT + 1
import librosa

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

        self.selected_end_beat_id = jukebox.beats[-1]['id']

        self.selected_jump_beat_id_manual = 0
        self.selected_jump_beat_num = 0
        self.selected_jump_beat_id = 0

        self.selected_start_beat_id = 0
        self.trim_start = False

        self.debounce = False

        self.export_timestamp = None
        self.export_success = False

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
                    current_beat_id = self.selected_start_beat_id if self.trim_start else 0

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
                        self.beat_id = self.selected_start_beat_id if self.trim_start else 0

                self.playback_time = (self.playback_time - current_beat_end_time) + self.jukebox.beats[self.beat_id]['start']

        self.last_time = current_time

    def recluster(self, clusters):
        if self.jukebox.evecs.size > 0:
            self.channel.stop()
            self.is_paused = True
            self.jukebox.recompute_beat_array(clusters)

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

        verbose_info = info % (self.jukebox.filepath, hours, minutes, seconds,
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
        x = self.window.get_width() - BUTTON_WIDTH * 5 - 10
        y = self.window.get_height() - BUTTON_WIDTH - 10

        start_offset = self.jukebox.start_index
        if (self.selected_start_beat_id > 0):
            start_offset += self.jukebox.beats[self.selected_start_beat_id]['start_index']
        jump_offset = self.jukebox.beats[self.selected_jump_beat_id]['start_index'] + self.jukebox.start_index
        stop_offset = self.jukebox.beats[self.selected_end_beat_id]['stop_index'] + self.jukebox.start_index

        jump_text_color = Color.GREEN.value
        loop_text_color = Color.GREEN.value
        if (self.selected_jump_beat_id > self.selected_end_beat_id):
            jump_text_color = Color.RED.value
            loop_text_color = Color.Red.value
        start_text_color = Color.WHITE.value
        if self.trim_start:
            jump_offset -= start_offset
            stop_offset -= start_offset

            start_text_color = Color.VIOLET.value
            if (self.selected_start_beat_id > self.selected_jump_beat_id):
                start_text_color = Color.RED.value
                jump_text_color = Color.RED.value

        draw_text(f"Start: {start_offset}", self.font, start_text_color, self.window, x, y)
        draw_text(f"Start Loop: {jump_offset}", self.font, jump_text_color, self.window, x, y + 15)
        draw_text(f"End Loop: {stop_offset}", self.font, loop_text_color, self.window, x, y + 30)

        draw_text(f"Avg Amplitude: {self.jukebox.avg_amplitude:3.4f}", self.font, Color.WHITE.value, self.window, BAR_X + get_bar_width(self.window) / 4 + 10, y)
        draw_text(f"Clusters: {self.jukebox.clusters}", self.font, Color.WHITE.value, self.window, BAR_X + get_bar_width(self.window) / 4 + 10, y + 15)

    def draw_status_text(self):
        if self.export_timestamp:
            if self.export_success:
                draw_text(f'Exported to brstm at {self.export_timestamp}', self.font, Color.GREEN.value, self.window, 20, 40)
            else:
                draw_text(f'Error exporting to brstm at {self.export_timestamp}', self.font, Color.RED.value, self.window, 20, 40)
        else:
            if self.jukebox.time_elapsed >= 0:
                draw_text(f'Processed in {self.jukebox.time_elapsed:4.1f}s', self.font, Color.GREEN.value, self.window, 20, 40)
            else:
                draw_text(f'Loaded from cache', self.font, Color.GREEN.value, self.window,
                          20, 40)

    def select_file(self):
        self.channel.stop()  # Stop before opening prompt otherwise playback will speed up
        self.is_paused = True
        return prompt_file(select_multiple=True)

    def open_button(self, click, mx, my):

        ## Open a new file
        x = self.window.get_width() - BUTTON_WIDTH*2 - 10
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

    def export_brstm(self):
        if (self.selected_jump_beat_id <= self.selected_end_beat_id) and ((not self.trim_start) or (self.selected_start_beat_id <= self.selected_jump_beat_id)):
            self.channel.pause()
            self.is_paused = True

            jump_offset = self.jukebox.beats[self.selected_jump_beat_id]['start_index']
            stop_offset = self.jukebox.beats[self.selected_end_beat_id]['stop_index']
            filepath = self.jukebox.filepath

            if self.trim_start:
                # Adjust offset based on new start
                start_offset = 0
                if (self.selected_start_beat_id > 0):
                    start_offset = self.jukebox.beats[self.selected_start_beat_id]['start_index']

                jump_offset -= start_offset
                stop_offset -= start_offset

                tmp_dir = os.path.join(CONFIG['lacDir'], 'tmp')
                os.makedirs(tmp_dir, exist_ok=True)
                filepath = os.path.join(tmp_dir, Path(self.jukebox.filepath).stem + '.wav')

                export_trimmed_wav(filepath, self.jukebox.raw_audio, self.jukebox.sample_rate, start_offset)
                write_points_to_file(jump_offset, stop_offset, filepath, CONFIG['lacDir'])
                self.export_success = run_lac(filepath, self.jukebox.sample_rate)
                if not self.export_sucess:
                    os.remove(filepath)

            else:
                # Adjust offset based on part of song that is trimmed in algorithm
                jump_offset += self.jukebox.start_index
                stop_offset += self.jukebox.start_index

                write_points_to_file(jump_offset, stop_offset, filepath, CONFIG['lacDir'])
                self.export_success = run_lac(filepath, self.jukebox.sample_rate)

            self.export_timestamp = get_timestamp()
            self.create_and_play_playback_buffer()

    def export_button(self, click, mx, my):
        if (self.selected_jump_beat_id <= self.selected_end_beat_id) and ((not self.trim_start) or (self.selected_start_beat_id <= self.selected_jump_beat_id)):
            ## Export loop
            x = self.window.get_width() - BUTTON_WIDTH*2 - 10
            y = self.window.get_height() - BUTTON_WIDTH - 10
            w = BUTTON_WIDTH*2
            h = BUTTON_WIDTH

            export_button_box = pygame.Rect(x, y, w, h)
            pygame.draw.rect(self.window, Color.DARK_ORANGE.value, export_button_box)
            draw_text("Export [E]", self.font, Color.WHITE.value, self.window, x, y + h / 2)
            if export_button_box.collidepoint((mx, my)):
                if click == (1, 0, 0):
                    if not self.debounce:
                        self.export_brstm()
                    self.debounce = True
                else:
                    self.debounce = False

    def toggle_trim(self):
        self.trim_start = not self.trim_start

    def toggle_trim_button(self, click, mx, my):
        ## Toggle trim button
        x = self.window.get_width() - BUTTON_WIDTH * 6 - 30
        y = self.window.get_height() - BUTTON_WIDTH - 10
        w = BUTTON_WIDTH

        toggle_button_box = pygame.Rect(x, y, w, w)
        button_color = Color.PURPLE.value
        if self.trim_start:
            button_color = Color.VIOLET.value
        pygame.draw.rect(self.window, button_color, toggle_button_box)
        draw_text("[T]", self.font, Color.WHITE.value, self.window, x + w / 2, y + w / 2)

        button_text = "Trim Start"
        if self.trim_start:
            button_text = "Keep Start"
        draw_text(button_text, self.font, Color.WHITE.value, self.window, x - 10, y + w / 2 - 15)

        if toggle_button_box.collidepoint((mx, my)):
            if click == (1, 0, 0):
                if not self.debounce:
                    self.toggle_trim()
                self.debounce = True
            else:
                self.debounce = False

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
        x = self.window.get_width() / 2 - BUTTON_WIDTH / 2
        y = self.window.get_height() - BUTTON_WIDTH - 10
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
        x = self.window.get_width() / 2 - BUTTON_WIDTH
        y = self.window.get_height() - BUTTON_WIDTH - 10
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
            self.selected_jump_beat_num = -1
        elif self.selected_jump_beat_num < -1:
            self.selected_jump_beat_num = len(jump_beats) - 1

        if len(jump_beats):
            self.selected_jump_beat_id = jump_beats[self.selected_jump_beat_num]
            self.create_and_play_playback_buffer()

    def jump_buttons(self, click, mx, my):
        x = self.window.get_width() / 2 + BUTTON_WIDTH
        y = self.window.get_height() - BUTTON_WIDTH - 10
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
        y = self.window.get_height() - BUTTON_WIDTH - 10
        w = get_bar_width(self.window) / 4
        h = BUTTON_WIDTH
        volume_slider_bar = pygame.Rect(BAR_X, y, w, h)

        if volume_slider_bar.collidepoint((mx, my)):
            if click == (1, 0, 0):
                volume = ((mx - BAR_X) / (get_bar_width(self.window)  / 4))
                self.set_volume(volume)

        volume_slider_bar = pygame.Rect(x, y + h/4, w, h/4)
        pygame.draw.rect(self.window, Color.GRAY.value, volume_slider_bar)

        x_line = BAR_X + (self.volume) * get_bar_width(self.window)  / 4

        pygame.draw.rect(self.window, Color.GRAY.value, [x_line - SCROLL_WIDTH / 2, self.window.get_height() - BUTTON_WIDTH - 10, SCROLL_WIDTH*2, BUTTON_WIDTH])

    def music_slider(self, click, mx, my, keys):

        music_slider_bar = pygame.Rect(BAR_X, self.window.get_height() - BUTTON_WIDTH - 20 - BAR_HEIGHT - 10, get_bar_width(self.window), BAR_HEIGHT)

        ## Handle mouse
        scroll_index = -1
        if music_slider_bar.collidepoint((mx, my)):
            if click == (1, 0, 0):
                scroll_index = ((mx - BAR_X) / get_bar_width(self.window) ) * float(self.total_indices) + self.jukebox.beats[0]['start_index']
            elif click == (0, 0, 1):
                scroll_index = ((mx - BAR_X) / get_bar_width(self.window) ) * float(self.total_indices) + self.jukebox.beats[0]['start_index']
                if not (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]):
                    self.selected_end_beat_id = self.jukebox.beats[-1]['id']
                    if self.selected_jump_beat_num >= 0:
                        self.selected_jump_beat_num = 0
                        self.selected_jump_beat_id = 0

        pygame.draw.rect(self.window, Color.GRAY.value, music_slider_bar)

        current_segment = -1
        for beat in self.jukebox.beats:
            x_line = BAR_X + (float(beat['start_index'] - self.jukebox.beats[0]['start_index']) /
                              float(self.total_indices)) * get_bar_width(self.window)

            if scroll_index >= beat['start_index'] and scroll_index < beat['stop_index']: # find beat which index belongs to
                ## If start indices doesn't match, i.e. the scroll bar was moved, set beat id to new beat (based on which controls)
                # Left click controls play slider
                # Right click controls end beat
                # Shift right click controls jump beat
                # Shift left click controls start

                if click == (1, 0, 0):
                    if (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]) and self.trim_start:
                        if self.selected_start_beat_id != beat['id']:
                            self.selected_start_beat_id = beat['id']
                    else:
                        if self.beat_id != beat['id']:
                            self.beat_id = beat['id']
                            self.last_selected_beat_id = self.beat_id
                            self.create_and_play_playback_buffer()
                elif click == (0, 0, 1):
                    if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                        if self.selected_jump_beat_id_manual != beat['id']:
                            self.selected_jump_beat_id_manual = beat['id']
                    else:
                        if self.selected_end_beat_id != beat['id']:
                            self.selected_end_beat_id = beat['id']
                            self.create_and_play_playback_buffer()

            ## Draw segment borders in white
            if beat['segment'] > current_segment:
                current_segment = beat['segment']

                pygame.draw.rect(self.window, Color.WHITE.value,
                                 [x_line - SEGMENT_LINE_WIDTH/2, self.window.get_height() - BUTTON_WIDTH - 20 - BAR_HEIGHT - 20, SEGMENT_LINE_WIDTH,
                                  BAR_HEIGHT + 20])

            # Color current beat if it had a jump beat
            if len(beat['jump_candidates']) > 0:
                pygame.draw.rect(self.window, Color.LIGHT_BLUE.value,
                         [x_line - SEGMENT_LINE_WIDTH / 2,
                          self.window.get_height() - BUTTON_WIDTH - 20 - BAR_HEIGHT - 10, SEGMENT_LINE_WIDTH,
                          BAR_HEIGHT])

            # Color beats in the same cluster as selected end beat if holding shift to guide manual jump beat selection
            if keys[pygame.K_LSHIFT]:
                if (beat['segment'] < self.jukebox.beats[self.selected_end_beat_id]['segment']) and (beat['cluster'] == self.jukebox.beats[self.selected_end_beat_id]['cluster']):
                    x_jump_line = BAR_X + (float(beat['start_index'] - self.jukebox.beats[0]['start_index']) / float(self.total_indices)) * get_bar_width(self.window)
                    pygame.draw.rect(self.window, Color.DARK_ORANGE.value , [x_jump_line - SEGMENT_LINE_WIDTH / 2,
                                      self.window.get_height() - BUTTON_WIDTH - 20 - BAR_HEIGHT - 10 + 3 * BAR_HEIGHT / 4,
                                      SEGMENT_LINE_WIDTH, BAR_HEIGHT / 4])


        end_beat = self.jukebox.beats[self.selected_end_beat_id]

        jump_beat_num = 0
        for jump_beat_id in end_beat['jump_candidates']:

            if jump_beat_id > 0:
                x_jump_line = BAR_X + (float(self.jukebox.beats[jump_beat_id]['start_index'] - self.jukebox.beats[0]['start_index']) /
                                                    float(self.total_indices)) * get_bar_width(self.window)

                # Highlight selected jump beat in green, other ones in yellow
                jump_beat_color = Color.YELLOW.value

                if self.selected_jump_beat_num == jump_beat_num:
                    self.selected_jump_beat_id = jump_beat_id
                    jump_beat_color = Color.FOREST_GREEN.value

                pygame.draw.rect(self.window, jump_beat_color, [x_jump_line - SEGMENT_LINE_WIDTH / 2,
                                                                self.window.get_height() - BUTTON_WIDTH - 20 - BAR_HEIGHT - 10, SEGMENT_LINE_WIDTH,
                                                                BAR_HEIGHT])

            jump_beat_num += 1

        if jump_beat_num == 0:
            if self.selected_jump_beat_id_manual > 0: # i.e. manual jump beat was moved
                self.selected_jump_beat_num = -1

        if self.trim_start:
            # Color currect selected start index
            x_line = BAR_X + (float(self.jukebox.beats[self.selected_start_beat_id]['start_index'] -
                                    self.jukebox.beats[0]['start_index']) / float(self.total_indices)) * get_bar_width(self.window)
            pygame.draw.rect(self.window, Color.VIOLET.value, [x_line - SEGMENT_LINE_WIDTH / 2, self.window.get_height() - BUTTON_WIDTH - 20 - BAR_HEIGHT - 10,
                              SEGMENT_LINE_WIDTH, BAR_HEIGHT])

        # Display manually selected jump beat as shorter (starts at bottom)
        x_jump_line = BAR_X + (float(self.jukebox.beats[self.selected_jump_beat_id_manual]['start_index']
                                     - self.jukebox.beats[0]['start_index']) / float(self.total_indices)) * get_bar_width(self.window)
        jump_beat_color = Color.YELLOW.value
        if self.selected_jump_beat_num == -1 or jump_beat_num == 0:
            self.selected_jump_beat_id = self.selected_jump_beat_id_manual
            jump_beat_color = Color.FOREST_GREEN.value

        pygame.draw.rect(self.window, jump_beat_color,
                         [x_jump_line - SEGMENT_LINE_WIDTH / 2, self.window.get_height() - BUTTON_WIDTH - 20 - BAR_HEIGHT - 10 + 3*BAR_HEIGHT/4,
                          SEGMENT_LINE_WIDTH, BAR_HEIGHT/4])

        # Color current selected end index
        x_line = BAR_X + (float(self.jukebox.beats[self.selected_end_beat_id]['start_index'] - self.jukebox.beats[0]['start_index']) /
                          float(self.total_indices)) * get_bar_width(self.window)
        pygame.draw.rect(self.window, Color.FIREBRICK.value,
                         [x_line - SEGMENT_LINE_WIDTH / 2, self.window.get_height() - BUTTON_WIDTH - 20 - BAR_HEIGHT - 10,
                          SEGMENT_LINE_WIDTH, BAR_HEIGHT])

        # Draw last selected scroll location
        x_line = BAR_X + (float(self.jukebox.beats[self.last_selected_beat_id]['start_index'] - self.jukebox.beats[0]['start_index']) /
                 float(self.total_indices)) * get_bar_width(self.window)
        pygame.draw.rect(self.window, Color.BLACK.value,
                         [x_line - SCROLL_WIDTH / 2, self.window.get_height() - BUTTON_WIDTH - 20 - BAR_HEIGHT - 10,
                          SCROLL_WIDTH, BAR_HEIGHT/4])

        # Draw scroll location
        x_line = BAR_X + (float(self.jukebox.beats[self.beat_id]['start_index'] - self.jukebox.beats[0]['start_index']) /
                          float(self.total_indices)) * get_bar_width(self.window)
        pygame.draw.rect(self.window, Color.BLACK.value, [x_line - SCROLL_WIDTH / 2, self.window.get_height() - BUTTON_WIDTH - 20 - BAR_HEIGHT - 10, SCROLL_WIDTH, BAR_HEIGHT])


    ## Right click, highlight a beat (closest beat with jump beat to the left) in red and beats to transition to in yellow, select which jump beats using arrow keys

    # TODO: Display audio signal?

    ## Export loop, automatically convert using LoopingAudioConverter
    # Fixed LAC, since it used to hang when using command line
    # Avoid files with accents (flac uses a command which can mess it up)

    ## Manual set loop using shift left and right click.
    # Highlight same clusters as current selection when holding shift.
    # Shift right to move beginning loop point.

    ## Fixed audio playback
    # Tried a timer and different channels, still can be choppy
    # Pre-made buffer works, redid functionality so a buffer is made taking loop points into account, and timer updates UI accordingly

    # TODO: Update status during loading (doesn't update, would have to use async, not sure affect on performance)

    # TODO: Make more efficient? (already included some multiprocessing)

    ## Remove beginning silence when making brstm by exporting it as a wav file first. Includes toggle
    # Shift left to move start point.

    ## Config JSON: Total Clusters to try argument, max sample rate

    ## Opening multiple files at start -> cache mode, cache selected beats for later, next time you open beat individually will load cache (have status say loaded cache instead of processed)
    # TODO: Check , in paths
    # Update config before running jukebox, if cluster is not 0 then re cluster even with cache, display cluster
    # Have an always cache mode in json config and saveEvecs in json config
    # TODO: investigate best compression/format to save?

    # TODO: Refine algorithm on songs with lyrics

    # TODO: Create build commands/script to copy and paste dependent files after building with pyinstaller e.g. Loopatron.json, font file, LoopingAudioConverter
    # Put font and Looping audio path in json

    # TODO: Modify volume (either through amplify in LAC or modifying raw_audio array)

    ## Check if windows and LoopingAudioConverter.exe is present, if not just append to loop.txt (replace if entry exists)

    # TODO: Investigate clipping (maybe loop in middle of beat?)

    # TODO: Set clusters in main window (just save npy cache for current beat then, remove npy files when program opens / closes if saveEnums = False) But what about already cached, need to recalculate?


