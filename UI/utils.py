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

import ctypes
from win10toast import ToastNotifier

VERSION = "v1.0.0"

#FONT_PATH = "FreeSansBold.ttf"

CONFIG_JSON = "Loopatron.json"

#LAC_DIR = "/LoopingAudioConverter" #"C:/Users/Ilir/Documents/Games/Brawl/Project+ Modding/Music/LoopingAudioConverter/LoopingAudioConverter/bin/Release"
LAC_EXE = "LoopingAudioConverter.exe"
#LAC_CONFIG_XML = "LoopingAudioConverter.xml"

WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 300

BUTTON_WIDTH = 50

BAR_HEIGHT = 100
BAR_X = 10

SCROLL_WIDTH = 2

SEGMENT_LINE_WIDTH = 2

def get_config():
    if os.path.exists(CONFIG_JSON):
        # Use singleton pattern to store config file location/load config once
        with open(CONFIG_JSON, 'r') as f:
            return json.load(f)
    else:
        return {
            "clusters": 0,
            "maxClusters": 48,
            "useV1": False,
            "maxSampleRate": 32000,
            "alwaysCache": False,
            "cacheEvecs": False,
            "outputDir": "./output",
            "cacheDir": "./cache",
            "lacDir": "./LoopingAudioConverter",
            "lacXML": "LoopingAudioConverter.xml",
            "fontPath": "./resources/FreeSansBold.ttf"
        }

CONFIG = get_config()

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
    GOLDENROD = (218,165,32)
    LIGHT_SKY_BLUE = (135,206,250)
    DODGE_BLUE = (30,144,255)
    DARK_SLATE_BLUE = (72,61,139)
    PERU = (205,133,63)

class CacheOptions(Enum):
    DISCARD = 0,
    KEEP_CACHE = 1,
    KEEP_CACHE_AND_EVECS = 2

def notify(message):
    if os.name == 'nt':
        toaster = ToastNotifier()
        toaster.show_toast("Loopatron",
                           message,
                           icon_path=None,
                           duration=10)

def prompt_file(select_multiple = False):
    """Create a Tk file dialog and cleanup when finished"""
    top = tkinter.Tk()
    top.withdraw()  # hide window
    if select_multiple:
        file_names = tkinter.filedialog.askopenfilenames(parent=top, title = "Choose a song to loop (or choose multiple songs to process and cache)")
    else:
        file_names = tkinter.filedialog.askopenfilename(parent=top, title="Choose a song to loop")
    top.destroy()
    return file_names

def get_bar_width(window):
    return window.get_width() - BAR_X * 2

def draw_text(text, font, color, surface, x, y):
    textobj = font.render(text, 1, color)
    textrect = textobj.get_rect()
    textrect.topleft = (x, y)
    surface.blit(textobj, textrect)

def draw_status_message(main_status, sub_status, font, sub_status_color, window):
    window.fill(Color.DARK_BLUE.value)
    draw_text(main_status, font, Color.WHITE.value, window, 20, 20)
    draw_text(sub_status, font, sub_status_color, window, 20, 40)
    draw_text(VERSION, font, Color.WHITE.value, window, window.get_width() - BUTTON_WIDTH * 3 - 20, 20)

def draw_status_message_and_update(main_status, sub_status, font, sub_status_color, window):
    draw_status_message(main_status, sub_status, font, sub_status_color, window)
    pygame.display.update()

def get_timestamp():
    return datetime.now().strftime("%H:%M:%S")

def edit_lac_xml(xml_path, sample_rate, amplify_ratio, output_dir):

    tree = ET.parse(xml_path)
    root = tree.getroot()

    # modifying an attribute
    sample_rate_node = root.find('SampleRate')
    sample_rate_node.text = str(min(sample_rate, CONFIG['maxSampleRate']))

    amplify_ratio_node = root.find('AmplifyRatio')
    amplify_ratio_node.text = "{:2.3f}".format(amplify_ratio)

    output_node = root.find('OutputDir')
    output_node.text = os.path.abspath(output_dir)

    tree.write(xml_path)

def export_trimmed_wav(output_path, raw_audio, sample_rate, new_start_index = 0):
    # write out the wav file with trimmed start
    sf.write(output_path, raw_audio[new_start_index:] , sample_rate, format='WAV', subtype='PCM_24')

def is_lac_present(lac_dir = CONFIG['lacDir'], lac_exe = LAC_EXE):
    return (os.name == 'nt') and (os.path.isfile(os.path.join(lac_dir, lac_exe)))

def write_points_to_file(jump_offset, stop_offset, filepath, lac_dir = CONFIG['lacDir']):

    all_entries = []

    # Append if LAC is not present
    if not is_lac_present(lac_dir, LAC_EXE):
        with open(os.path.join(lac_dir, "loop.txt"), 'r') as f:
            for current_entry in f:
                if (len(current_entry) > 3) and (os.path.basename(filepath) not in current_entry): # if entry already exists, remove
                    all_entries.append(current_entry)

    with open(os.path.join(lac_dir, "loop.txt"), 'w') as output:
        output.writelines(all_entries)
        output.write("\n%d " % (jump_offset))
        output.write("%d " % (stop_offset))
        output.write(os.path.basename(filepath))

def run_lac(filename, sample_rate, amplify_ratio, output_dir = CONFIG['outputDir'], lac_dir = CONFIG['lacDir'], lac_exe = LAC_EXE, lac_config_xml = CONFIG['lacXML']):

    if os.path.isfile(os.path.join(output_dir, Path(filename).stem + '.brstm')):
        os.remove(os.path.join(output_dir, Path(filename).stem + '.brstm'))

    if is_lac_present(lac_dir, lac_exe):
        if os.path.isfile(os.path.join(lac_dir, lac_config_xml)):
            edit_lac_xml(os.path.join(lac_dir, lac_config_xml), sample_rate, amplify_ratio, output_dir)
            subprocess.run([os.path.join(lac_dir, lac_exe), "--auto", os.path.join(lac_dir, lac_config_xml), filename], cwd = lac_dir)
            return os.path.isfile(os.path.join(output_dir, Path(filename).stem + '.brstm'))
        else:
            subprocess.run([os.path.join(lac_dir, lac_exe), "--auto", filename], cwd = lac_dir)
            return os.path.isfile(os.path.join(output_dir, Path(filename).stem + '.brstm'))

    return False