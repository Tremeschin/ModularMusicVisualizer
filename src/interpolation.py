"""
===============================================================================

Purpose: Interpolation file with step functions

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

from functions import Functions


class Interpolation():

    def __init__(self):
        self.functions = Functions()

    # Linear, between point A and B based on a current "step" and total steps
    def linear(self, a, b, current, total, this_coord, arg_a):
        part = (b - a) / total
        walked = part * current
        return a + walked

    # "Biased" remaining linear
    def remaining_approach(self, a, b, current, total, this_coord, arg_a):
        ratio = arg_a
        if current == 0:
            return a
        return this_coord + ( (b - this_coord) * ratio )

    # Sigmoid activation between two points, smoothed out "linear" curver
    def sigmoid(self, a, b, current, total, this_coord, arg_a):
        smooth = arg_a
        distance = (b - a)
        where = self.functions.proportion(total, 1, current)
        walk = distance*self.functions.sigmoid(where, smooth)
        return a + walk