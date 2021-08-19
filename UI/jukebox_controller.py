import os
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
        self.channel.set_endevent(SOUND_FINISHED)

        snd = mixer.Sound(buffer=jukebox.beats[0]['buffer'])
        self.channel.queue(snd)

        self.channel.pause()

        self.is_paused = True
        self.beat_id = 0


        self.total_indices = jukebox.beats[-1]['stop_index'] - jukebox.beats[0]['start_index']
        self.scroll_index = BAR_X

        self.last_selected_beat_id = 0

        self.selected_end_index = jukebox.beats[-1]['stop_index']
        self.selected_end_beat_id = jukebox.beats[-1]['id']

        self.selected_jump_beat_num = 0
        self.selected_jump_beat_id = 0

        self.debounce = False

        self.export_timestamp = None

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
        ## Export loop
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

    def on_sound_finished(self):

        # If on selected beat, go to selected jump beat, otherwise increment by 1
        if self.beat_id == self.selected_end_beat_id:
            self.beat_id = self.selected_jump_beat_id
        else:
            self.beat_id += 1
            if self.beat_id >= len(self.jukebox.beats): # if no beats left (i.e. song finished
                self.beat_id = 0

        self.scroll_index = BAR_X + (float(self.jukebox.beats[self.beat_id]['start_index'] - self.jukebox.beats[0]['start_index'])
                                     / float(self.total_indices)) * BAR_WIDTH
        # Channel2 sound ended, start another!

        snd = mixer.Sound(buffer=self.jukebox.beats[self.beat_id]['buffer'])
        self.channel.play(snd)

    def select_file(self):
        self.channel.pause()  # Pause before opening prompt otherwise playback will speed up
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
        self.write_points_to_file(LOOPING_AUDIO_CONVERTER_DIR)
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
            self.scroll_index = BAR_X + (
                        float(self.jukebox.beats[self.beat_id]['start_index'] - self.jukebox.beats[0]['start_index'])
                        / float(self.total_indices)) * BAR_WIDTH

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
        if music_slider_bar.collidepoint((mx, my)):
            if click == (1, 0, 0):
                self.scroll_index = ((mx - BAR_X) / BAR_WIDTH) * float(self.total_indices) + self.jukebox.beats[0]['start_index']
            elif click == (0, 0, 1):
                self.selected_end_index = ((mx - BAR_X) / BAR_WIDTH) * float(self.total_indices) + self.jukebox.beats[0]['start_index']
                self.selected_end_beat_id = self.jukebox.beats[-1]['id']
                self.selected_jump_beat_num = 0
                self.selected_jump_beat_id = 0

        pygame.draw.rect(self.window, Color.GRAY.value, music_slider_bar)

        current_jump_beat_num = 0
        current_segment = -1
        for beat in self.jukebox.beats:
            x_line = BAR_X + (float(beat['start_index'] - self.jukebox.beats[0]['start_index']) /
                              float(self.total_indices)) * BAR_WIDTH

            ## Adjust scroll bar so that it is at start of beat
            if self.scroll_index >= beat['start_index'] and self.scroll_index < beat['stop_index']: # find beat which index belongs to
                self.scroll_index = BAR_X + (float(beat['start_index'] - self.jukebox.beats[0]['start_index'])
                                             / float(self.total_indices)) * BAR_WIDTH

                ## If start indices doesn't match, i.e. the scroll bar was moved, set beat id to new beat
                if beat['start_index'] != self.jukebox.beats[self.beat_id]['start_index']:
                    self.beat_id = beat['id'] - 1
                    self.last_selected_beat_id = self.beat_id


            ## Draw segment borders in white
            if beat['segment'] > current_segment:
                current_segment = beat['segment']

                pygame.draw.rect(self.window, Color.WHITE.value,
                                 [x_line - SEGMENT_LINE_WIDTH/2, WINDOW_HEIGHT - BUTTON_WIDTH - 20 - BAR_HEIGHT - 20, SEGMENT_LINE_WIDTH,
                                  BAR_HEIGHT + 20])

            current_beat_color = None
            for jump_beat_id in beat['jump_candidates']:

                current_beat_color = Color.LIGHT_BLUE.value # Highlight beats with a earlier loop in light blue
                if self.selected_end_index >= beat['start_index'] and self.selected_end_index < beat['stop_index']: # find beat which selected end index belongs to
                    self.selected_end_beat_id = beat['id']
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

        # If the selected jump beat number is outside range of jump beats
        if self.selected_jump_beat_num >= current_jump_beat_num:
            self.selected_jump_beat_num = 0
        elif self.selected_jump_beat_num < 0:
            self.selected_jump_beat_num = current_jump_beat_num - 1

        # Draw last selected scroll location
        x_line = BAR_X + (float(self.jukebox.beats[self.last_selected_beat_id]['start_index'] - self.jukebox.beats[0]['start_index']) /
                 float(self.total_indices)) * BAR_WIDTH
        pygame.draw.rect(self.window, Color.BLACK.value,
                         [x_line - SCROLL_WIDTH / 2, WINDOW_HEIGHT - BUTTON_WIDTH - 20 - BAR_HEIGHT - 20,
                          SCROLL_WIDTH, (BAR_HEIGHT + 20)/4])

        # Draw scroll location
        pygame.draw.rect(self.window, Color.BLACK.value, [self.scroll_index - SCROLL_WIDTH / 2, WINDOW_HEIGHT - BUTTON_WIDTH - 20 - BAR_HEIGHT - 20, SCROLL_WIDTH, BAR_HEIGHT + 20])


        # Right click, highlight a beat (closest beat with jump beat to the left) in red and beats to transition to in yellow, select which jump beats using arrow keys

        # TODO: Display audio signal?

        # TODO: Export loop, automatically convert using LoopingAudioConverter

        # TODO: Manual set loop using shift left and right click? Maybe highlight same clusters as current selection when holding shift

        # TODO: Fix audio playback

        # TODO: Display start and end loops

        # TODO: Update status during loading (doesn't update, would have to use async, not sure affect on performance)

        # TODO: Make more efficient? (already included some multiprocessing)

        # TODO: Remove beginning silence when making brstm

        # TODO: Allow resize window?

        # TODO: Total Clusters to try argument, multi-processing argument, cut beginning silence argument
