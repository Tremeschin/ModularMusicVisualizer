"""
===============================================================================
                                GPL v3 License                                
===============================================================================

Copyright (c) 2020,
  - Tremeschin < https://tremeschin.gitlab.io > 

===============================================================================

Purpose: Abstract, wrap, connect other files

===============================================================================

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.

===============================================================================
"""

from mmv.common.cmn_constants import LOG_NEXT_DEPTH, LOG_NO_DEPTH
from mmv.mmvskia.pyskt.pyskt_backend import SkiaNoWindowBackend
from mmv.common.cmn_coordinates import PolarCoordinates
from mmv.common.cmn_interpolation import Interpolation
from mmv.mmvskia.mmv_animation import MMVSkiaAnimation
from mmv.common.cmn_audio import AudioProcessing
from mmv.mmvskia.mmv_context import MMVContext
from mmv.common.cmn_functions import Functions
from mmv.mmvskia.mmv_image import MMVSkiaImage
from mmv.common.cmn_video import FFmpegWrapper
from mmv.mmvskia.mmv_core import MMVSkiaCore
from mmv.common.cmn_audio import AudioFile
from mmv.common.cmn_fourier import Fourier
from mmv.common.cmn_utils import Utils
from PIL import Image
import numpy as np
import argparse
import logging
import math
import time
import sys
import os


class MMVSkiaMain:
    def __init__(self, interface):
        self.mmvskia_interface = interface
        self.prelude = self.mmvskia_interface.prelude
        
    # Creates classes and send to Core
    def setup(self, depth = LOG_NO_DEPTH) -> None:
        debug_prefix = "[MMVSkiaMain.setup]"
        ndepth = depth + LOG_NEXT_DEPTH

        self.utils = Utils()

        logging.info(f"{depth}{debug_prefix} Creating MMVContext() class")
        self.context = MMVContext(mmv_main = self, depth = ndepth)

        logging.info(f"{depth}{debug_prefix} Creating SkiaNoWindowBackend() class")
        self.skia = SkiaNoWindowBackend()

        logging.info(f"{depth}{debug_prefix} Creating Functions() class")
        self.functions = Functions()

        logging.info(f"{depth}{debug_prefix} Creating Interpolation() class")
        self.interpolation = Interpolation()

        logging.info(f"{depth}{debug_prefix} Creating PolarCoordinates() class")
        self.polar_coordinates = PolarCoordinates()

        logging.info(f"{depth}{debug_prefix} Creating Canvas() class")
        self.canvas = MMVSkiaImage(mmvskia_main = self, depth = ndepth)

        logging.info(f"{depth}{debug_prefix} Creating Fourier() class")
        self.fourier = Fourier()

        logging.info(f"{depth}{debug_prefix} Creating FFmpegWrapper() class")
        self.ffmpeg = FFmpegWrapper()

        logging.info(f"{depth}{debug_prefix} Creating AudioFile() class")
        self.audio = AudioFile()

        logging.info(f"{depth}{debug_prefix} Creating AudioProcessing() class")
        self.audio_processing = AudioProcessing()

        logging.info(f"{depth}{debug_prefix} Creating MMVSkiaAnimation() class")
        self.mmv_animation = MMVSkiaAnimation(mmv_main = self, depth = ndepth)
    
        logging.info(f"{depth}{debug_prefix} Creating MMVSkiaCore() class")
        self.core = MMVSkiaCore(mmvskia_main = self, depth = ndepth)

    # Execute the program
    def run(self, depth = LOG_NO_DEPTH) -> None:
        debug_prefix = "[MMVSkiaMain.run]"
        ndepth = depth + LOG_NEXT_DEPTH
        
        try:
            # import cProfile
            # p = cProfile.Profile()
            # p.enable()
            logging.info(f"{depth}{debug_prefix} Executing MMVSkiaCore.run()")
            self.core.run(depth = ndepth)
            
            logging.info(f"{depth}{debug_prefix} Finished, terminating GLFW")
            self.skia.terminate_glfw()
            # p.disable()
            # p.dump_stats("res.prof")
        except KeyboardInterrupt:
            self.skia.terminate_glfw()
            self.ffmpeg.close_pipe()
            sys.exit(-1)
        
        # Say thanks message
        self.mmvskia_interface.top_level_interace.thanks_message()

        # Wait for FFmpeg pipe to stop
        while not self.ffmpeg.stop_piping:
            time.sleep(0.05)

        logging.info(f"{depth}{debug_prefix} Quitting Python")
        sys.exit(0)
