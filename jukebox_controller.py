
from pygame import mixer
import pygame.locals

from gui_utils import *

SOUND_FINISHED = pygame.locals.USEREVENT + 1

class JukeboxController:

    def __init__(self, window, jukebox):
        self.window = window
        self.jukebox = jukebox

        #mixer.init(frequency=jukebox.sample_rate)
        self.channel = mixer.Channel(0)

        self.channel.set_endevent(SOUND_FINISHED)

        snd = mixer.Sound(buffer=jukebox.beats[0]['buffer'])
        self.channel.queue(snd)

        self.is_paused = False
        self.beat_id = 0

        self.total_indices = jukebox.beats[-1]['stop_index'] - jukebox.beats[0]['start_index']
        self.scroll_index = BAR_X
        self.selected_index = 0

        self.selected_jump_beat_num = 0
        self.selected_jump_beat_id = -1

        self.debounce = False

    def on_sound_finished(self):

        if self.selected_jump_beat_id >= 0 and self.beat_id == self.selected_beat_id:
            self.beat_id = self.selected_jump_beat_id
        else:
            self.beat_id += 1
            if self.beat_id >= len(self.jukebox.beats):
                self.beat_id = 0

        self.scroll_index = BAR_X + (float(self.jukebox.beats[self.beat_id]['start_index']) / float(self.total_indices)) * BAR_WIDTH
        # Channel2 sound ended, start another!
        snd = mixer.Sound(buffer=self.jukebox.beats[self.beat_id]['buffer'])
        self.channel.play(snd)

    def play_button(self, click, mx, my):

        play_button_box = pygame.Rect(WINDOW_WIDTH / 2 - BUTTON_WIDTH / 2, WINDOW_HEIGHT - BUTTON_WIDTH - 10, BUTTON_WIDTH, BUTTON_WIDTH)
        if play_button_box.collidepoint((mx, my)):
            if click == (1, 0, 0):
                if not self.debounce:
                    if not self.is_paused:
                        self.channel.pause()
                        self.is_paused = True
                    else:
                        self.channel.unpause()
                        self.is_paused = False
                self.debounce = True
            else:
                self.debounce = False

        pygame.draw.rect(self.window, Color.RED.value, play_button_box)

    def music_slider(self, click, mx, my, action = None):


        music_slider_bar = pygame.Rect(BAR_X, WINDOW_HEIGHT - BUTTON_WIDTH - 20 - BAR_HEIGHT, BAR_WIDTH, BAR_HEIGHT)

        ## Handle mouse
        if music_slider_bar.collidepoint((mx, my)):
            if click == (1, 0, 0):
                self.scroll_index = ((mx - BAR_X) / BAR_WIDTH) * float(self.total_indices) + self.jukebox.beats[0]['start_index']
            elif click == (0, 0, 1):
                self.selected_index = ((mx - BAR_X) / BAR_WIDTH) * float(self.total_indices) + self.jukebox.beats[0]['start_index']
                self.selected_beat_id = -1
                self.selected_jump_beat_num = 0
                self.selected_jump_beat_id = -1

                #TODO: Play start of beat

        pygame.draw.rect(self.window, Color.GRAY.value, music_slider_bar)

        # TODO: Draw segment borders in white, highlight beats with a earlier loop in light blue

        current_jump_beat_num = 0
        current_segment = -1
        for beat in self.jukebox.beats:
            x_line = BAR_X + (float(beat['start_index']) / float(self.total_indices)) * BAR_WIDTH

            if self.scroll_index >= beat['start_index'] and self.scroll_index < beat['stop_index']:
                self.scroll_index = BAR_X + (float(beat['start_index']) / float(self.total_indices)) * BAR_WIDTH

                if beat['start_index'] != self.jukebox.beats[self.beat_id]['start_index']:
                    self.beat_id = beat['id'] - 1


            if beat['segment'] > current_segment:
                current_segment = beat['segment']

                pygame.draw.rect(self.window, Color.WHITE.value,
                                 [x_line - SEGMENT_LINE_WIDTH/2, WINDOW_HEIGHT - BUTTON_WIDTH - 20 - BAR_HEIGHT - 10, SEGMENT_LINE_WIDTH,
                                  BAR_HEIGHT + 20])

            current_beat_color = None
            for jump_beat_id in beat['jump_candidates']:

                if jump_beat_id < beat['id']: # if there is a jumping point to an earlier beat, draw line at start of beat
                    current_beat_color = Color.LIGHT_BLUE.value
                    if self.selected_index >= beat['start_index'] and self.selected_index < beat['stop_index']:
                        self.selected_beat_id = beat['id']
                        current_beat_color = Color.FIREBRICK.value

                        x_jump_line = BAR_X + (float(self.jukebox.beats[jump_beat_id]['start_index']) / float(self.total_indices)) * BAR_WIDTH

                        jump_beat_color = Color.YELLOW.value
                        if self.selected_jump_beat_num == current_jump_beat_num:
                            self.selected_jump_beat_id = jump_beat_id
                            jump_beat_color = Color.FOREST_GREEN.value

                        pygame.draw.rect(self.window, jump_beat_color,
                                         [x_jump_line - SEGMENT_LINE_WIDTH / 2,
                                          WINDOW_HEIGHT - BUTTON_WIDTH - 20 - BAR_HEIGHT, SEGMENT_LINE_WIDTH,
                                          BAR_HEIGHT])

                        current_jump_beat_num += 1

                if current_beat_color:
                    pygame.draw.rect(self.window, current_beat_color,
                             [x_line - SEGMENT_LINE_WIDTH / 2,
                              WINDOW_HEIGHT - BUTTON_WIDTH - 20 - BAR_HEIGHT, SEGMENT_LINE_WIDTH,
                              BAR_HEIGHT])





        pygame.draw.rect(self.window, Color.BLACK.value, [self.scroll_index - SCROLL_WIDTH / 2, WINDOW_HEIGHT - BUTTON_WIDTH - 20 - BAR_HEIGHT - 10, SCROLL_WIDTH, BAR_HEIGHT + 20])


        # TODO: Right click, highlight a beat (maybe closest beat to the left) in red and beats to transition to in yellow, select beats using keypad, scrollwheel or arrow keys

        # TODO: Display audio signal?

        # TODO: Export loop, automatically convert using LoopingAudioConverter