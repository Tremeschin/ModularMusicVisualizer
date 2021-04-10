"""
===============================================================================
                                GPL v3 License                                
===============================================================================

Copyright (c) 2020 - 2021,
  - Tremeschin < https://tremeschin.gitlab.io > 

===============================================================================

Purpose: Enums for maybe some easier time configuring classes

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
from enum import Enum, auto

class EnumRunShadersMode(Enum):
    RealTime = "realtime"
    Render = "render"
    
class EnumsOS(Enum):
    Windows = "windows"
    Linux = "linux"
    MacOS = "macos"

class EnumsAudioSource(Enum):
    RealTime = auto()
    AudioFile = auto()
    
