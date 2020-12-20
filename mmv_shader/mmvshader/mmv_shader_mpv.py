"""
===============================================================================

Purpose: Utility to wrap around mpv and add processing shaders, target
resolutions, input / output

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

from PIL import Image
import numpy as np
import subprocess
import base64
import os


class MMVShaderMPV:
    def __init__(self, main):
        debug_prefix = "[MMVShaderMPV.__init__]"
        self.mmv_main = main

        # Create empty config
        self.reset()

    # Reset configured stuff
    def reset(self):
        debug_prefix = "[MMVShaderMPV.reset]"
        print(debug_prefix, "Resetting MMVShaderMPV to empty configuration")

        # List of shaders to apply
        self.shaders = []

        # Where and what to load, output
        self.input_video = ""
        self.output_video = ""

        # Default resolution / fps values
        self.width = 1280
        self.height = 720
        self.fps = None  # None means use the input's fps

        # # Final command to run, start with the mpv executable

        # Linux and MacOS don't use suffixes
        mpv_binary = "mpv"

        # On Windows look for an .exe extensions
        if (self.mmv_main.utils.os == "windows"):
            mpv_binary += ".exe"
        
        # Try finding mpv binary
        print(debug_prefix, f"Getting mpv binary [{mpv_binary}] path..")
        mpv_binary_path = self.mmv_main.utils.get_executable_with_name(mpv_binary)

        # get_executable_with_name returns False if it's not found, up for who
        # uses the function to handle errors so here we are
        if not mpv_binary_path:
            raise RuntimeError(f"Could not find mpv binary named [{mpv_binary}] on the system.")

        print(debug_prefix, f"mpv binary path is [{mpv_binary_path}]")

        # Start with the mpv binary
        self.__command = [mpv_binary_path]

    # # Internal functions

    # Converts an numpy array into a sequence of hexadecimal raw pixel values
    # Used when defining TEXTURES on mpv shaders
    def __np_array_to_uint8_hex(self, array):
        return array.astype(np.uint8).tobytes().hex().upper()

    # Loads an image from path and converts to raw hexadecimal rgba pixels
    def __image2hex_rgba(self, path):
        return self.__np_array_to_uint8_hex(np.array(Image.open(path).convert("RGBA")))

    # Generate the final command to run
    def __generate_command(self):
        debug_prefix = "[MMVShaderMPV.__generate_command]"
        print(debug_prefix, "Generating run command")
        
        # Preliminary error assertion
        assert (not self.input_video == ""), "No input video specified"

        # Add input source
        self.__command += [self.input_video]

        # # Append shaders flags for every shader we added

        # If we do have at least one shader, add --glsl-shader=path for every shader path
        if self.shaders:

            # Assert that every shader is a valid file on the disk
            assert (not any([os.path.isfile(path) for path in self.shaders]))

            # For every shader add its flag
            self.__command += [f"--glsl-shader={shader}" for shader in self.shaders]

        # Render on the GPU with the specified width and height
        self.__command.append(f'--vf=gpu=w={self.width}:h={self.height}') 

        # If we have some output video, render to it, otherwise display realtime (no -o flag)
        if self.output_video is not None:
            self.__command += ["-o", self.output_video]
        
        print(debug_prefix, "Full command is", self.__command)

    # # Interface, end user functions

    # Adds a new shader as processing layer to the final video
    def add_shader(self, shader_path):
        debug_prefix = "[MMVShaderMPV.__init__]"

        # Get absolute path always
        shader_path = self.mmv_main.utils.get_abspath(shader_path)

        # Warn info
        print(debug_prefix, f"> Add shader with path: [{shader_path}]")

        # Assign values
        self.shaders.append(shader_path)

    # Configure input and output, if output is None that means don't render, only display real time
    def input_output(self, input_video, output_video = None):
        debug_prefix = "[MMVShaderMPV.input_output]"

        # Get absolute path always
        input_video = self.mmv_main.utils.get_abspath(input_video)
        output_video = self.mmv_main.utils.get_abspath(output_video)

        # Warn info
        print(debug_prefix, f"> Set input video: [{input_video}]")
        print(debug_prefix, f"> Set output video: [{output_video}]")

        # Assign values
        self.input_video = input_video
        self.output_video = output_video
    
    # Configure the resolution width, height to render
    def resolution(self, width, height):
        debug_prefix = "[MMVShaderMPV.resolution]"

        # Warn info
        print(debug_prefix, f"> Set resolution width: [{width}]")
        print(debug_prefix, f"> Set resolution height: [{height}]")

        # Assign values
        self.width = width
        self.height = height
        
    # Execute this class with the stuff configured
    def run(self, execute = True):
        debug_prefix = "[MMVShaderMPV.run]"
        
        # Generate command
        self.__generate_command()

        if execute:
            subprocess.run(self.__command)

    def generate_shader(self):
        with open("warp-template.glsl", "r") as f:
            shader = f.read()
        
        shader = shader.replace("<+IMAGEHEX+>", imghex)

        with open("warp.glsl", "w") as f:
            f.write(shader)
