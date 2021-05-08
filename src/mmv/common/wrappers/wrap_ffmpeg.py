"""
===============================================================================
                                GPL v3 License                                
===============================================================================

Copyright (c) 2020 - 2021,
  - Tremeschin < https://tremeschin.gitlab.io > 

===============================================================================

Purpose: Deals with Video related stuff, also a FFmpeg wrapper in its own class

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


import mmv.common.cmn_any_logger
from PIL import Image
import numpy as np
import subprocess
import logging
import copy
import time
import sys
import cv2


class FFmpegWrapper:
    def __init__(self, ffmpeg_binary_path):
        self.ffmpeg_binary_path = ffmpeg_binary_path

    # Generator for keeping outputting raw audio from some file in f32 format (normalized)
    def raw_audio_from_file(self, input_file, batch_size = 2048, sample_rate = 48000, channels = 2):

        # Output values ranging from 0 to 1, float 32
        self.command = [
            self.ffmpeg_binary_path,
            "-loglevel", "panic", "-hide_banner",
            "-i", input_file,
            "-acodec", "pcm_f32le",
            "-f", "f32le",
            "-ac", f"{channels}",
            "-ar", f"{sample_rate}",
            "-"  # Output to stdout
        ]

        # Open subprocess
        self.subprocess = subprocess.Popen(self.command, stdin = subprocess.PIPE, stdout = subprocess.PIPE)

        # Size to read (4 bytes (f32), times channel and target batch size)
        read_batch_size = 4 * channels * batch_size

        # Value we yield on the loop
        to_yield = np.zeros((channels, batch_size), dtype = np.float32)
        
        while True:
            # Try reading some data (or until it closes so we have partial data, keep this in mind)
            data = self.subprocess.stdout.read(read_batch_size)

            # If we have at least some data, else break
            if data:

                # Load into one numpy array, can be less sized than batch_size, transposed
                data = np.fromstring(data, dtype = np.float32).reshape((channels, -1), order = "F")

                # Zero fill the full array with the target batch size output
                to_yield.fill(0.0)

                # Insert new data into the zero filled array with length of data
                for channel in range(channels):
                    np.put(to_yield[channel], range(0, data.shape[1]), data[channel])

                # Yield new data
                yield to_yield
            else:
                break

    def raw_audio_to_file(self, sample_rate, output_file):
        self.command = [
            self.ffmpeg_binary_path, "-y",
            "-loglevel", "panic", "-hide_banner",
            "-f", f"f32le",
            "-acodec", f"pcm_f32le", 
            "-ar", str(sample_rate),
            "-ac", "2",  # 2 channels
            "-i", "-", "-vn",  # Input from pipe, don't expect video
            "-b:a", "200k",
            output_file
        ]

    def concatenate_video_and_audio(self, video, audio, output):
        self.command = [
            self.ffmpeg_binary_path, "-y",
            "-loglevel", "panic", "-hide_banner",
            "-i", video,
            "-i", audio,
            "-map", "0:v",
            "-map", "1:a",
            "-c", "copy",
            output
        ]
        self.run()

    def extract_audio_from_video(self, video, save_to):
        self.command = [
            self.ffmpeg_binary_path, "-y",
            "-i", video,
            "-b:a", "230k",
            save_to
        ]
        return save_to

    def run(self):
        debug_prefix = "[FFmpegWrapper.run]"
        logging.info(f"{debug_prefix} Run FFmpeg, blocking code with command {self.command}")
        subprocess.run(self.command)

    # Create a FFmpeg writable pipe for generating a video
    # For more detailed info see [https://trac.ffmpeg.org/wiki/Encode/H.264]
    def configure_encoding(self, 
        width: int,
        height: int,
        input_audio_source: str,  # Path, None for disabling
        input_video_source: str,  # Path, "pipe" for pipe
        output_video: str, # Path
        pix_fmt: str,  # rgba, rgb24, bgra
        framerate: int,
        preset: str = "slow",  # libx264 ffmpeg preset
        hwaccel = "auto",  # Try utilizing hardware acceleration? None ignores this flag
        loglevel: str = "",  # Please set to panic if using pipe, None or "" disables this
        nostats: bool = False, 
        hide_banner: bool = True,
        opencl: bool = False,  # Add -x264opts opencl ?
        crf: int = 17,  # Constant Rate Factor [0: lossless, 23: default, 51: worst] 
        tune: str = "film",  # x264 tuning, ["film", "animation"]
        vcodec: str = "libx264",  # Encoder library, libx264 or libx265
        override: bool = True,  # Do override the target output video if it exists?
        t: float = None,  # Stop rendering at some time?
        vflip: bool = True,  # Apply -vf vflip?
        scale: str = None,  # Apply -vf scale=WxH, send like 1280:720 
        shortest: bool = True,
        profile_compat: str = "baseline",  # x264 profile to use, baseline or main, None to disable, sets -vf yuv420
    ) -> None:

        debug_prefix = "[FFmpegWrapper.configure_encoding]"

        # Generate the command for piping images to
        self.command = [
            self.ffmpeg_binary_path
        ]

        # Add hwaccel flag if it's set
        if hwaccel is not None:
            self.command += ["-hwaccel", hwaccel]

        if loglevel:
            self.command += ["-loglevel", loglevel]
        
        if nostats:
            self.command += ["-nostats"]
        
        if hide_banner:
            self.command += ["-hide_banner"]

        # Add the rest of the command
        self.command += [
            "-pix_fmt", pix_fmt,
            "-r", f"{framerate}",
            "-s", f"{width}x{height}"
        ]

        # Stop rendering at some point in time
        if t:
            self.command += ["-t", f"{t}"]
        
        # Input video source
        if input_video_source == "pipe":
            self.command += ["-f", "rawvideo", "-i", "-"]

            # Danger, we can overflow the buffer this way and get soft locked
            if not loglevel == "panic":
                logging.info(f"{debug_prefix} You are piping a video and loglevel is not set to PANIC")
        else:
            self.command += ["-i", input_video_source]
        
        # Do input audio or not
        if input_audio_source is not None:
            self.command += ["-i", input_audio_source, "-c:a", "copy"]
        
        # Continue adding commands
        self.command += [
            "-c:v", f"{vcodec}",
            "-preset", preset,
            "-r", f"{framerate}",
            "-crf", f"{crf}",
        ]

        # video filters
        vf = []

        # Add opencl to x264 flags?
        if opencl:
            self.command += ["-x264opts", "opencl"]

        # Apply vertical flip?
        if vflip:
            vf.append("vflip")
        
        if scale:
            vf.append(f"scale={scale}")
        
        if shortest:
            self.command += ["-shortest"]

        # h264 profiles / compat        
        if profile_compat is not None:
            self.command += ["-profile:v", profile_compat, "-level", "3.0"]
            vf.append("format=yuv420p")
        
        # Add filters
        filters = ','.join(vf)
        if filters:
            self.command += ["-vf", filters]

        # Add output video
        self.command += [output_video]

        # Do override the target output video
        if override:
            self.command.append("-y")

        # Log the command for generating final video
        logging.info(f"{debug_prefix} FFmpeg command is: {self.command}")
      
        self.stop_piping = False
        self.lock_writing = False
        self.images_to_pipe = {}

    def start(self, stdin = subprocess.PIPE, stdout = subprocess.PIPE):
        debug_prefix = "[FFmpegWrapper.start]"
        logging.info(f"{debug_prefix} Starting FFmpeg subprocess with command {self.command}")

        # Create a subprocess in the background
        self.subprocess = subprocess.Popen(self.command, stdin  = stdin, stdout = stdout)
    
    def run(self, stdin = subprocess.PIPE, stdout = subprocess.PIPE):
        debug_prefix = "[FFmpegWrapper.run]"
        logging.info(f"{debug_prefix} Run FFmpeg subprocess with command {self.command}")

        # Run blocking code
        subprocess.run(self.command, stdin = stdin, stdout = stdout)

    # Write images into pipe, run pipe_writer_loop first!!
    def write_to_pipe(self, index, image):
        while len(list(self.images_to_pipe.keys())) >= self.max_images_on_pipe_buffer:
            print("Too many images on pipe buffer")
            time.sleep(0.1)

        self.images_to_pipe[index] = image
        del image

    # Thread save the images to the pipe, this way processing.py can do its job while we write the images
    def pipe_writer_loop(self, duration_seconds: float, fps: float, frame_count: int, max_images_on_pipe_buffer: int, show_status = True):
        debug_prefix = "[FFmpegWrapper.pipe_writer_loop]"

        self.max_images_on_pipe_buffer = max_images_on_pipe_buffer
        self.count = 0

        while not self.stop_piping:
            if self.count in list(self.images_to_pipe.keys()):
                if self.count == 0:
                    start = time.time()
                
                # We're writing stuff
                self.lock_writing = True

                # Get the next image from the list as count is on the images to pipe dictionary keys
                image = self.images_to_pipe.pop(self.count)

                # Pipe the numpy RGB array as image
                self.subprocess.stdin.write(image)

                # Finished writing
                self.lock_writing = False

                # Are we finished on the expected total number of images?
                if self.count == frame_count - 1:
                    self.close_pipe()
                
                self.count += 1

                if show_status:
                    # Stats
                    current_time = (self.count / fps)   # Current second we're processing
                    propfinished = ((current_time + (1/fps)) / duration_seconds) * 100  # Overhaul percentage completion
                    remaining = duration_seconds - current_time  # How much seconds left to produce
                    now = time.time()
                    took = now - start  # Total time took in this runtime
                    eta = (took * remaining) / current_time

                    # Convert to minutes
                    took /= 60
                    eta /= 60
                    took_plus_eta = took + eta

                    took_plus_eta = f"{int(took_plus_eta)}m:{(took_plus_eta - int(took_plus_eta))*60:.0f}s"
                    took = f"{int(took)}m:{(took - int(took))*60:.0f}s"
                    eta = f"{int(eta)}m:{(eta - int(eta))*60:.0f}s"

                    print(f"\rProgress=[Frame: {self.count} - {current_time:.2f}s / {duration_seconds:.2f}s = {propfinished:0.2f}%] Took=[{took}] ETA=[{eta}] EST Total=[{took_plus_eta}]", end="")
            else:
                time.sleep(0.1)
        
        self.subprocess.stdin.close()

    # Close stdin and stderr of subprocess and wait for it to finish properly
    def close_pipe(self):

        debug_prefix = "[FFmpegWrapper.close_pipe]"

        print(debug_prefix, "Closing pipe")

        # Wait for all images to be piped, noted: the last one will still be there because of .pop and
        # will have a false signal of images to pipe being empty, we correct on the next loop
        while not len(self.images_to_pipe.keys()) == 0:
            print(debug_prefix, "Waiting for image buffer list to end, len [%s]" % len(self.images_to_pipe))
            time.sleep(0.1)

        # Is there any more images left to pipe? ie, are we holding one image on memory and piping to ffmpeg
        while self.lock_writing:
            print(debug_prefix, "Lock writing is on, should only have one image?")
            time.sleep(0.1)

        self.stop_piping = True

        print(debug_prefix, "Stopped pipe!!")

