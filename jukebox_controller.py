
from pygame import mixer
import pygame.locals

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
        self.beat_num = 0

    def on_sound_finished(self):
        self.beat_num += 1
        # Channel2 sound ended, start another!
        snd = mixer.Sound(buffer=self.jukebox.beats[self.beat_num]['buffer'])
        self.channel.play(snd)

    def play_button(self, click, mx, my):
        play_button = pygame.Rect(50, 100, 50, 50)
        if play_button.collidepoint((mx, my)):
            if click:
                if not self.is_paused:
                    self.channel.pause()
                    self.is_paused = True
                else:
                    self.channel.unpause()
                    self.is_paused = False

        pygame.draw.rect(self.window, (255, 0, 0), play_button)

    def music_slider_button(self, click, mx, my, action = None):
        pass