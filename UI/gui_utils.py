import pygame
import sys
import tkinter
import tkinter.filedialog

from pygame.locals import *
from enum import Enum

is_paused = False

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

def open_button(window, click, mx, my):

    ## Open a new file
    open_button_box = pygame.Rect(100, 20, 100, 50)
    pygame.draw.rect(window, Color.GRAY.value, open_button_box)
    if open_button_box.collidepoint((mx, my)):
        if click == (1, 0, 0):
            return prompt_file()

    return None


