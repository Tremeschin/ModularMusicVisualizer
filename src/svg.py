"""
===============================================================================

Purpose: SVG files utility

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

from wand.api import library
from io import BytesIO
from PIL import Image
import numpy as np
import wand.image
import wand.color
import cairosvg
import svgwrite
import base64
import sys
import os


class SVG():
    def __init__(self, width, height, rasterizer, mode):
        self.width = width
        self.height = height
        self.rasterizer = rasterizer
        self.mode = mode
        self.SVG_ROUND = 4

        if not self.rasterizer in ["cairo", "wand"]:
            print("Rasterizer invalid: [%s]" % self.rasterizer)
            sys.exit(-1)

        if not self.mode in ["png", "jpg"]:
            print("Mode invalid SVG --> [%s]" % self.mode)
            sys.exit(-1)
            
    def new_drawing(self, centered=True):
        if centered:
            self.dwg = svgwrite.Drawing(
                viewBox=('%s %s %s %s' % (-self.width/2, -self.height/2, self.width, self.height))
            )
        else:
            self.dwg = svgwrite.Drawing(
                viewBox=('%s %s %s %s' % (0, 0, self.width, self.height))
            )

    # Return a PNG PIL Image from this object svg
    def get_png(self, convert_to_png=True):
        
        svg_string = self.dwg.tostring()

        if self.rasterizer == "wand":
            with wand.image.Image(blob=svg_string.encode(), format="svg") as image:
                # if convert_to_png:
                #     with wand.color.Color('transparent') as background_color:
                #         library.MagickSetBackgroundColor(image.wand, background_color.resource) 
                return Image.open(BytesIO(image.make_blob(self.mode)))

        elif self.rasterizer == "cairo":

            # Save the file to this temporary buffer
            r, w = os.pipe()

            # Save the svg to the temporary buffer
            cairosvg.svg2png(bytestring=svg_string, write_to=open(w, "wb"))
            # cairosvg.surface.PNGSurface.convert(svg_string, write_to=buffer)

            # Open the image from the buffer, convert to png
            image = Image.open(open(r, "rb"))

            del r, w

            if convert_to_png:
                image = image.convert("RGBA")
            else:
                image = image.convert("RGB")

            return image

    def get_array(self):
        return np.array(self.get_png())
