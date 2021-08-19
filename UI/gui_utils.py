import pygame
import sys
import tkinter
import tkinter.filedialog
from datetime import datetime

from pygame.locals import *
from enum import Enum

LOOPING_AUDIO_CONVERTER_DIR = "C:/Users/Ilir/Documents/Games/Brawl/Project+ Modding/Music/LoopingAudioConverter-2.4"


WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 600

BUTTON_WIDTH = 50

BAR_HEIGHT = 100
BAR_X = 10
BAR_WIDTH = WINDOW_WIDTH - BAR_X * 2

SCROLL_WIDTH = 2

SEGMENT_LINE_WIDTH = 2

class Color(Enum):
    GRAY = (220, 220, 200)
    RED = (255, 0, 0)
    FIREBRICK = (178,34,34)
    GREEN = (0, 255, 0)
    FOREST_GREEN = (34,139,34)
    WHITE = (255, 255, 255)
    DARK_BLUE = (3, 5, 54)
    LIGHT_BLUE = (173,216,230)
    BLACK = (0, 0, 0)
    YELLOW = (255, 255, 0)
    DARK_ORANGE = (255, 140, 0)

def prompt_file():
    """Create a Tk file dialog and cleanup when finished"""
    top = tkinter.Tk()
    top.withdraw()  # hide window
    file_name = tkinter.filedialog.askopenfilename(parent=top)
    top.destroy()
    return file_name

def draw_text(text, font, color, surface, x, y):
    textobj = font.render(text, 1, color)
    textrect = textobj.get_rect()
    textrect.topleft = (x, y)
    surface.blit(textobj, textrect)

def update_message(main_status, sub_status, window, font):
    window.fill(Color.DARK_BLUE.value)
    draw_text(main_status, font, Color.WHITE.value, window, 20, 20)
    draw_text(sub_status, font, Color.GREEN.value, window, 20, 40)
    pygame.display.update()

def get_timestamp():
    return datetime.now().strftime("%H:%M:%S")


