"""
===============================================================================
                                GPL v3 License                                
===============================================================================

Copyright (c) 2020 - 2021,
  - Tremeschin < https://tremeschin.gitlab.io > 

===============================================================================

Purpose: Interface for generating MMV Shaders

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

from mmv.mmvshader.mmv_shader_maker_transformations import MMVShaderMakerTransformations
from mmv.mmvshader.abstractions.abstraction_block_of_code import BlockOfCode
from mmv.mmvshader.mmv_shader_maker_loaders import MMVShaderMakerLoaders
from mmv.mmvshader.mmv_shader_maker_macros import MMVShaderMakerMacros
from mmv.common.cmn_utils import Utils
from pathlib import Path
import numpy as np
import logging
import shutil
import copy
import uuid
import sys
import os


BASE_FRAGMENT_SHADER = """\

// ===============================================================================
// This file was auto generated by MMVShaderMaker from something interfacing with
// one instantiated class. Note this is not guaranteed to be functional nor work
// out of the box, and most times will need MMV specification of variables to
// react from with the sound and to render recursively all the layer mappings you
// have.
// ===============================================================================

// // Includes, mappings

// Includes
//#shadermaker includes

// Mappings
//#shadermaker mappings

// // Functions
//#shadermaker functions

// Main function
void main() {
    // Include coordinates normalization
    //#mmv {"type": "include", "value": "coordinates_normalization", "mode": "multiple"}

    // Start with empty layered vec4, this is the one we progressively alpha composite
    // and is the final output
    vec4 layered = vec4(0.0);

    // Main part of the shader
    //#shadermaker transformations

    // Return
    fragColor = layered;
}
"""


class MMVShaderMaker:
    def __init__(self, working_directory, name = None, replaces = {}):
        debug_prefix = "[MMVShaderMaker.__init__]"

        # Instantiate classes
        self.utils = Utils()
        self.block_of_code = BlockOfCode

        # Refactors
        self.transformations = MMVShaderMakerTransformations()
        self.loaders = MMVShaderMakerLoaders(mmv_shader_maker = self)
        self.macros = MMVShaderMakerMacros(mmv_shader_maker = self)
    
        # Where to place directories and whatnot
        self.working_directory = working_directory

        # # Sessions and Shader Maker runtime directory

        # Reset runtime directory
        logging.info(f"{debug_prefix} Resetting directory")
        self.utils.reset_dir(self.working_directory)

        # # Add stuff

        # Attributes
        self._includes = []
        self._mappings = []
        self._functions = []
        self._transformations = []

        # Get and add name mapping
        self.name = name
        self.replaces = replaces
     
        # Start with the base shader
        self._fragment_shader = BASE_FRAGMENT_SHADER
        self._final_shader = None
        self._path_on_disk = None

    def clone(self): return copy.deepcopy(self)
    def set_name(self, name): self.name = name

    # Build the shader and save to the working directory, returns the final path
    def finish(self):
        debug_prefix = "[MMVShaderMaker.finish]"
        if self.name is None: self.name = str(uuid.uuid4())
        save = self.working_directory / f"{self.name}.glsl"
        logging.info(f"{debug_prefix} Finishing shader [{self.name}] saving to [{save}]")
        self.build_final_shader()
        self.save_shader_to_file(save)
        return self.get_path()

    # Load full shader from path
    def load_shader_from_path(self, path: Path, replaces = {}, get_name_from_file = True):
        debug_prefix = "[MMVShaderMaker.load_from_path]"
        path = self.utils.enforce_pathlib_Path(path)
        
        # Concatenate both dictionaries
        for key, item in self.replaces.items():
            replaces[key] = item

        # Log action
        logging.info(f"{debug_prefix} Loading shader from path [{path}]")
        logging.info(f"{debug_prefix} Replaces: {replaces}")

        # Assign same name of the file
        if (self.name is None) or get_name_from_file:
            logging.info(f"{debug_prefix} No name so far, getting filename.. will error if not pathlib.Path")
            self.name = path.stem
            logging.info(f"{debug_prefix} Ok! Name is [{self.name}]")

        # Load file on path
        with open(path, "r") as f:
            data = f.read()

        # Replace stuff
        for key, value in replaces.items():
            logging.info(f"{debug_prefix} | Replacing [{key}] -> [{value}]")
            data = data.replace(f"{{{key}}}", f"{value}")
        
        # Assign data to fragment shader
        self._fragment_shader = data

    # # # # Add functions

    # # Mappings

    # Add image from file mapping to a target width and height.
    # Uses the resolution of the read file if some width or height is None (or both)
    def add_image_mapping(self, name, path, width = None, height = None, repeat_x = True, repeat_y = True, mipmaps = True, anisotropy = 16):
        debug_prefix = "[MMVShaderMaker.add_image_mapping]"
        path = self.utils.enforce_pathlib_Path(path)
        mapping = {"type": "map", "name": name, "loader": "image", "value": str(path), "width": width, "height": height, "mipmaps": mipmaps, "repeat_x": repeat_x, "repeat_y": repeat_y, "anisotropy": anisotropy}
        self._mappings.append(BlockOfCode(f"//#mmv {mapping}", scoped = False, name = f"{debug_prefix}"))

    # Video mapping to a target width and height
    def add_video_mapping(self, name, path, width, height, anisotropy = 16):
        debug_prefix = "[MMVShaderMaker.add_video_mapping]"
        path = self.utils.enforce_pathlib_Path(path)
        mapping = {"type": "map", "name": name, "loader": "video", "value": str(path), "width": width, "height": height, "anisotropy": anisotropy}
        self._mappings.append(BlockOfCode(f"//#mmv {mapping}", scoped = False, name = f"{debug_prefix}"))

    # Pipeline (as) texture is for communicating big arrays from Python to ModernGL's shader being executed
    def add_pipeline_texture_mapping(self, name, width, height, depth, repeat_x = False, repeat_y = False, mipmaps = True, anisotropy = 16):
        debug_prefix = "[MMVShaderMaker.add_pipeline_texture_mapping]"
        mapping = {"type": "map", "name": name, "loader": "pipeline_texture", "width": width, "height": height, "depth": depth, "repeat_x": repeat_x, "repeat_y": repeat_y, "mipmaps": mipmaps, "anisotropy": anisotropy}
        self._mappings.append(BlockOfCode(f"//#mmv {mapping}", scoped = False, name = f"{debug_prefix}"))

    # Strict shader only renders at this target resolution internally, regardless of output dimensions
    def add_strict_shader_mapping(self, name, path, width, height, anisotropy = 16):
        debug_prefix = "[MMVShaderMaker.add_strict_shader_mapping]"
        path = self.utils.enforce_pathlib_Path(path)
        mapping = {"type": "map", "name": name, "loader": "shader", "value": str(path), "width": width, "height": height, "anisotropy": anisotropy}
        self._mappings.append(BlockOfCode(f"//#mmv {mapping}", scoped = False, name = f"{debug_prefix}"))

    # Dynamic shader adapts to the viewport / output dimensions, recommended
    def add_dynamic_shader_mapping(self, name, path, anisotropy = 16):
        debug_prefix = "[MMVShaderMaker.add_dynamic_shader_mapping]"
        path = self.utils.enforce_pathlib_Path(path)
        mapping = {"type": "map", "name": name, "loader": "dynshader", "value": str(path), "anisotropy": anisotropy}
        self._mappings.append(BlockOfCode(f"//#mmv {mapping}", scoped = False, name = f"{debug_prefix}"))

    # Name the shader on this class's name
    def _add_name_mapping(self):
        debug_prefix = "[MMVShaderMaker.add_name_mapping]"
        mapping = {"type": "name", "value": self.name}
        self._mappings.append(BlockOfCode(f"//#mmv {mapping}", scoped = False, name = f"{debug_prefix}"))

    # # Functions

    # Append some function to this shader
    def add_function(self, function: BlockOfCode):
        debug_prefix = "[MMVShaderMaker.add_include]"
        function.scoped = False  # Enforce non scoped functions
        self._functions.append(function)

    # # Includes

    # Include some file
    def add_include(self, include: str, mode = "multiple"):
        debug_prefix = "[MMVShaderMaker.add_include]"
        mapping = {"type": "include", "value": include, "mode": mode}
        self._includes.append(BlockOfCode(f"//#mmv {mapping}", scoped = False, name = f"{debug_prefix}"))

    # # Transformations

    # Append some transformation to this shader (executed in main function)
    def add_transformation(self, transformation: BlockOfCode):
        debug_prefix = "[MMVShaderMaker.add_transformation]"
        self._transformations.append(transformation)

    # # # # Generating, saving, getting strings

    def __replace_progressive(self, marker: str, data: str, indent: str):
        debug_prefix = "[MMVShaderMaker.__replace_progressive]"
        self._fragment_shader = self._fragment_shader.replace(f"{indent}{marker}", f"{data}{indent}{marker}")

    # # Core loop

    # Build the final shader, assign it to self._final_shader
    def build_final_shader(self) -> BlockOfCode:
        debug_prefix = "[MMVShaderMaker.build_final_shader]"
        self._add_name_mapping()

        # Replaces pair of name on the final shader and the items
        replaces = [
            ["includes", self._includes],
            ["mappings", self._mappings],
            ["functions", self._functions],
            ["transformations", self._transformations],
        ]

        # For each pair, replace with that object's content
        for mapping_type, items in replaces:

            # The marker we search for
            marker = f"//#shadermaker {mapping_type}"

            for block_of_code in items:
                have_marker = False
                for line in self._fragment_shader.split("\n"):
                    if marker in line:
                        indent = line.split(marker)[0]
                        have_marker = True

                if have_marker:
                    self.__replace_progressive(
                        marker = marker,
                        data = block_of_code.get_string_content(indent = indent),
                        indent = indent,
                    )
        
        # Assign final shader
        self._final_shader = BlockOfCode(self._fragment_shader, scoped = False, name = self.name)

    # String of the final shader
    def get_final_shader_string(self) -> str:
        debug_prefix = "[MMVShaderMaker.get_final_shader_string]"

        # Can't get shader if didn't run .build_final_shader()
        assert self._final_shader is not None, "You haven't run .build_final_shader()"
        return self._final_shader.get_string_content()

    # Save this shader to a file
    def save_shader_to_file(self, path):
        debug_prefix = "[MMVShaderMaker.save_shader_to_file]"
        self._path_on_disk = path

        # Log action
        logging.info(f"{debug_prefix} Saving shader name [{self.name}] to path [{path}]")

        # Open the file on the path and write the strings
        with open(path, "w") as shader_file:
            shader_file.write(self.get_final_shader_string())

    # Get the shader's path    
    def get_path(self):
        assert self._path_on_disk is not None, "You haven't run .save_shader_to_file()"
        return self._path_on_disk
