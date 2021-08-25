import pygame
import sys
import tkinter
import tkinter.filedialog
from datetime import datetime
import os
import subprocess
from pathlib import Path

from pygame.locals import *
from enum import Enum
import soundfile as sf


import xml.etree.ElementTree as ET
import json
import typing

VERSION = "v1.0.0"

CONFIG_JSON = "Loopatron.json"

LAC_DIR = "C:/Users/Ilir/Documents/Games/Brawl/Project+ Modding/Music/LoopingAudioConverter/LoopingAudioConverter/bin/Release"
LAC_EXE = "LoopingAudioConverter.exe"
LAC_CONFIG_XML = "LoopingAudioConverter.xml"

WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 300

BUTTON_WIDTH = 50

BAR_HEIGHT = 100
BAR_X = 10

SCROLL_WIDTH = 2

SEGMENT_LINE_WIDTH = 2

if os.path.exists(os.path.join(LAC_DIR, CONFIG_JSON)):
    # Use singleton pattern to store config file location/load config once
    with open(os.path.join(LAC_DIR, CONFIG_JSON), 'r') as f:
        CONFIG = json.load(f)
else:
    CONFIG = {
        "clusters": 0,
        "maxClusters": 48,
        "useV1": False,
        "maxSampleRate": 32000
    }


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
    PURPLE = (128, 0, 128)
    VIOLET = (238,130,238)

def prompt_file():
    """Create a Tk file dialog and cleanup when finished"""
    top = tkinter.Tk()
    top.withdraw()  # hide window
    file_name = tkinter.filedialog.askopenfilename(parent=top)
    top.destroy()
    return file_name

def get_bar_width(window):
    return window.get_width() - BAR_X * 2

def draw_text(text, font, color, surface, x, y):
    textobj = font.render(text, 1, color)
    textrect = textobj.get_rect()
    textrect.topleft = (x, y)
    surface.blit(textobj, textrect)

def update_message(main_status, sub_status, window, font):
    window.fill(Color.DARK_BLUE.value)
    draw_text(main_status, font, Color.WHITE.value, window, 20, 20)
    draw_text(sub_status, font, Color.GREEN.value, window, 20, 40)
    draw_text(VERSION, font, Color.WHITE.value, window, window.get_width() - BUTTON_WIDTH*3 - 20, 20)
    pygame.display.update()

def get_timestamp():
    return datetime.now().strftime("%H:%M:%S")

def edit_lac_xml(xml_path, sample_rate):

    tree = ET.parse(xml_path)
    root = tree.getroot()

    # modifying an attribute
    sample_rate_node = root.find('SampleRate')
    sample_rate_node.text = str(min(sample_rate, CONFIG['maxSampleRate']))
    tree.write(xml_path)

def export_trimmed_wav(output_path, raw_audio, sample_rate, new_start_index = 0):
    # write out the wav file with trimmed start
    sf.write(output_path, raw_audio[new_start_index:] , sample_rate, format='WAV', subtype='PCM_24')


def write_points_to_file(jump_offset, stop_offset, filepath, lac_dir =""):
    with open(os.path.join(lac_dir, "loop.txt"), "w") as output:
        output.write("\n%d " % (jump_offset))
        output.write("%d " % (stop_offset))
        output.write(os.path.basename(filepath))

def run_lac(filename, sample_rate, lac_dir = LAC_DIR, lac_exe = LAC_EXE, lac_config_xml = LAC_CONFIG_XML):

    if os.path.isfile(os.path.join(lac_dir, 'output', Path(filename).stem + '.brstm')):
        os.remove(os.path.join(lac_dir, 'output', Path(filename).stem + '.brstm'))

    if os.path.isfile(os.path.join(lac_dir, lac_exe)):
        if os.path.isfile(os.path.join(lac_dir, lac_config_xml)):
            edit_lac_xml(os.path.join(lac_dir, lac_config_xml), sample_rate)
            subprocess.run([os.path.join(lac_dir, lac_exe), "--auto", os.path.join(lac_dir, lac_config_xml), filename], cwd = lac_dir)
        else:
            subprocess.run([os.path.join(lac_dir, lac_exe), "--auto", filename], cwd = lac_dir)

        if os.path.isfile(os.path.join(lac_dir, 'output', Path(filename).stem + '.brstm')):
            return True
    return False