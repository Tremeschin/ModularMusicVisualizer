"""
===============================================================================
                                GPL v3 License                                
===============================================================================

Copyright (c) 2020 - 2021,
  - Tremeschin < https://tremeschin.gitlab.io > 

===============================================================================

Purpose: Basic usage example of MMV

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

# Add current directory to PATH so we find the "mmv" package
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Continue imports
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
import mmv.common.cmn_any_logger
from tqdm import tqdm
import numpy as np
import itertools
import soundcard
import logging
import typer
import time
import mmv


# Watchdog for changes, reload shaders
class AnyModification(FileSystemEventHandler):
    def __init__(self, controller):
        self.controller = controller
        self.reload = False

    def on_modified(self, event):
        debug_prefix = "[AnyModification.on_modified]"
        logging.info(f"{debug_prefix} Some modification event [{event}], reloading shaders..")
        self.reload = True


class MMVShadersCLI:
    def __init__(self):
        debug_prefix = "[MMVShadersCLI.__init__]"
        self.sep = os.path.sep

        # # Initialize stuff

        # MMV interface
        self.mmv_package_interface = mmv.MMVPackageInterface()
        self.utils = self.mmv_package_interface.utils

        # Shaders interface and MGL
        self.mgl = self.mmv_package_interface.get_mmv_shader_mgl()(master_shader = True)

        # Interpolator
        self.interpolator = ValuesInterpolator()

        # Advanced config
        self.advanced_config = self.mmv_package_interface.utils.load_yaml(
            self.mmv_package_interface.shaders_dir / "shaders_advanced_config.yaml"
        )

        # Ensure FFmpeg on Windows
        self.mmv_package_interface.check_download_externals(target_externals = ["ffmpeg"])

        # IO defaults
        self._input_audio = self.mmv_package_interface.assets_dir / "free_assets" / "kawaii_bass.ogg"
        self._output_video = "rendered_shader.mkv"

        # Audio
        self._audio_batch_size = int(self.advanced_config["audio"]["batch_size"])
        self._sample_rate = int(self.advanced_config["audio"]["sample_rate"])
        self._override_record_device = None

        # Resolution, rendering
        self._width = 1920
        self._height = 1080
        self._fps = 60
        self._ssaa = 1.1
        self._msaa = 8
        self._multiplier = 3.0

        # Use default preset
        self._preset_name = "default"
        self.watchdog = True

    # # Configuration

    # Target width, height and framerate
    def resolution(self, 
        width: int = typer.Option(1920, help = "Output resolution width (horizontal pixel count)"),
        height: int = typer.Option(1080, help = "Output resolution height (vertical pixel count)"),
        fps: float = typer.Option(60, help = "Output frame rate in Frames Per Seconds (FPS)"),
    ):
        logging.info(f"[MMVShadersCLI.resolution] Set [width={width}] [height={height}] [fps={fps}]")

        # Assign values
        self._width = int(width)
        self._height = int(height)
        self._fps = int(fps)

    # SuperSampling AntiAliasing SSAA
    def antialiasing(self, 
        ssaa: float = typer.Option(1.1, help = (
            "Internally render in target resolution multiplied by this, then downscale to target. "
            "Greately degrades performance but reduces jagged edges a lot, use 1.5 or 2 when final exporting "
            "and 1, 1.1, 1.2 for real time mode if you want more smoothness. Defaults to 1.1")),
        msaa: int = typer.Option(8, help = (
            "Multi Sampling Anti Aliasing, can only be 1, 2, 4 or 8."
        ))
    ):
        logging.info(f"[MMVShadersCLI.antialiasing] Set [ssaa={ssaa}] [msaa={msaa}]")
        self._ssaa = float(ssaa)
        self._msaa = int(msaa)

    def load(self, 
        preset: str = typer.Option("default", help = (
            "Load some preset, executes the python file under /src/mmv/shaders/presets/{name}.py")),
        file: str = typer.Option("", help = (
            "Load a raw shader from disk."
        )),
        watchdog: bool = typer.Option(True, help = (
            "Watch for main shader or Python preset file on disk file modifications, rebuilds and reloads shaders. Good for development of shaders."
        ))
    ):
        debug_prefix = "[MMVShadersCLI.preset]"
        self.watchdog = watchdog

        # User sent some file to be the main shader so we 
        if file:
            logging.info(f"{debug_prefix} Load raw shader!! Set [preset master shader={file}]")
            self._preset_name = None
            self._preset_master_shader = file
        else:
            logging.info(f"{debug_prefix} Execute preset file!! Set [preset={preset}]")
            self._preset_name = preset

    def multiplier(self, 
        value: float = typer.Option(3.0, help = (
            "Multiply target interpolation values by this amount, yields more aggressiveness"
        ))
    ):
        logging.info(f"[MMVShadersCLI.multiplier] Set [multiplier={value}]")
        self._multiplier = float(value)

    # # Running, executing

    # Set MMVShaderMGL target settings
    def __mgl_target_render_settings(self):
        self.mgl.target_render_settings(
            width = self._width,
            height = self._height,
            ssaa = self._ssaa,
            fps = self._fps,
        )

    def __load_master_shader(self):
        self.mgl.load_shader_from_path(fragment_shader_path = self._preset_master_shader)

    def __configure_audio_processing(self):
        # Configure FFT TODO: advanced config?
        self.audio_source.audio_processing.configure(config = [
            {
                "original_sample_rate": 48000,
                "target_sample_rate": 1000,
                "start_freq": 80,
                "end_freq": 500,
            },
            {
                "original_sample_rate": 48000,
                "target_sample_rate": 48000,
                "start_freq": 500,
                "end_freq": 20000,
            }
        ])
        self.MMV_FFTSIZE = self.audio_source.audio_processing.FFT_length

    def __load_preset(self):
        debug_prefix = "[MMVShadersCLI.__load_preset]"

        # # Will we load preset file or raw file shader? 

        # Raw file
        if self._preset_name is None:
            self.mgl.include_dir(self.mmv_package_interface.shaders_dir / "include")

        # Preset file
        else:
            # Stuff to replace
            replaces = {
                "MMV_FFTSIZE": self.MMV_FFTSIZE,
                "AUDIO_BATCH_SIZE": self._audio_batch_size,
                "WIDTH": self._width,
                "HEIGHT": self._height,
            }

            # Directory of this preset
            preset_file = self.mmv_package_interface.shaders_dir / "presets" / f"{self._preset_name}.py"
            working_directory = self.mmv_package_interface.runtime_dir
            shadermaker = self.mmv_package_interface.get_mmv_shader_maker()
            interface = self.mmv_package_interface
            sep = os.path.sep
            NULL = "MMV_MGL_NULL_FRAGMENT_SHADER"

            # Open and execute the file with this scope's variables
            # Note: we can access like locals()["replaces"] from the other file!!
            with open(preset_file, "rb") as f:
                code = compile(f.read(), preset_file, "exec")

            # We get this info dictionary back from the executed file
            exec(code, globals(), locals())

            # pylint: disable=E0602 # Disable undefined variables because this info must exist
            logging.info(f"{debug_prefix} Got info from preset file [{preset_file}]: {info}")

            self._preset_master_shader = info["master_shader"]

            # Include directories
            self.mgl.preprocessor.reset()
            to_include = info.get("include_directories", ["default"])

            # Add every directory or the default one, note first returned ones have higher priority
            for directory in self.utils.force_list(to_include):
                if directory == "default":
                    self.mgl.include_dir(self.mmv_package_interface.shaders_dir / "include")
                else:
                    self.mgl.include_dir(directory)

    # List capture devices by index
    def list_captures(self):
        debug_prefix = "[MMVShadersCLI.list_captures]"

        logging.info(f"{debug_prefix} Available devices to record audio:")
        for index, device in enumerate(soundcard.all_microphones(include_loopback = True)):
            logging.info(f"{debug_prefix} > ({index}) [{device.name}]")

        logging.info(f"{debug_prefix} :: Run [realtime] command with argument --cap N")

    # Display shaders real time
    def realtime(self,
        window_class: str = typer.Option("glfw", help = "ModernGL Window backend to use, see [https://moderngl-window.readthedocs.io/en/latest/guide/window_guide.html], values are [sdl2, pyglet, glfw, pyqt5], GLFW works dynshader mode so I advise that. Please install the others if you wanna use them [poetry add / pip install pysdl2, pyqt5 etc]"),
        cap: int = typer.Option(None, help = "Capture device index to override first loopback we find. Run command [list-captures] to see available indexes, None is to get automatically")
    ):
        debug_prefix = "[MMVShadersCLI.realtime]"
        self.__mgl_target_render_settings()
        self.mode = "view"

        # # Audio source Real Time
        self.audio_source = self.mmv_package_interface.get_audio_source_realtime()

        # Configure audio source
        self.audio_source.configure(
            batch_size = self._audio_batch_size,
            sample_rate = self._sample_rate,
            recorder_numframes =  None,
            do_calculate_fft = True
        )

        # Search for loopback or get index of recorder device
        if (cap is None):
            self.audio_source.init(search_for_loopback = True)
        else:
            for index, device in enumerate(soundcard.all_microphones(include_loopback = True)):
                if index == cap:
                    self.audio_source.init(recorder_device = device)

        self.__configure_audio_processing()
        self.__load_preset()

        # Start mgl window
        self.mgl.mode(
            window_class = window_class,
            vsync = False,
            msaa = self._msaa,
            strict = False,
        )

        # Load master shader
        self.__load_master_shader()

        # Start reading data
        self.audio_source.start_async()
        self._core_loop()

    # Render config to video file
    def render(self,
        output_video: str = typer.Option("rendered_shader.mkv", help = (
            "Name of the final video"
        )),
        audio: str = typer.Option(None, help = "Which audio to use as source on file?"),
    ):
        debug_prefix = "[MMVShadersCLI.render]"

        self._output_video = output_video
        if audio is not None:
            self._input_audio = audio

        self.__mgl_target_render_settings()
        self.mode = "render"

        # # Audio source File
        self.audio_source = self.mmv_package_interface.get_audio_source_file()

        # Configure audio source
        self.audio_source.configure(
            target_fps = self._fps,
            process_batch_size = self._audio_batch_size,
            sample_rate = self._sample_rate,
            do_calculate_fft = True,
        )

        # Read source audio file
        self.audio_source.init(audio_path = self._input_audio)
        self.__configure_audio_processing()
        self.__load_preset()

        # How much bars we'll have
        self.MMV_FFTSIZE = self.audio_source.audio_processing.FFT_length

        # Get video encoder
        self.ffmpeg = self.mmv_package_interface.get_ffmpeg_wrapper()

        # Settings, see /src/mmv/common/wrappers/wrap_ffmpeg.py for what those do
        self.ffmpeg.configure_encoding(
            width = self._width,
            height = self._height,
            input_audio_source = self._input_audio,
            input_video_source = "pipe",
            output_video = self._output_video,
            framerate = self._fps,
            preset = self.advanced_config["ffmpeg"]["preset"],
            crf = self.advanced_config["ffmpeg"]["crf"],
            tune = self.advanced_config["ffmpeg"]["tune"],
            vflip = self.advanced_config["ffmpeg"]["vflip"],
            vcodec = "libx264",
            hwaccel = "auto",
            loglevel = "panic",
            pix_fmt = "rgb24",
            hide_banner = True,
            override = True,
            nostats = True,
            opencl = False,
        )
        self.ffmpeg.start()

        # Set window mode to headless
        self.mgl.mode(
            window_class = "headless",
            strict = True,
            vsync = False,
            msaa = self._msaa,
        )

        # # Load shaders
        self.__load_master_shader()

        # Main routines
        self._core_loop()

    def __error_assertion(self):
        assert os.path.exists(self._input_audio)

    # Common main loop for both view and render modes
    def _core_loop(self):
        debug_prefix = "[MMVShadersCLI.render]"

        self.__error_assertion()
        self.mgl.set_reset_function(obj = self.__load_preset)

        # Look for file changes
        if self.watchdog:
            logging.info(f"{debug_prefix} Starting watchdog")

            self.any_modification_watchdog = AnyModification(controller = self)

            sd = self.mmv_package_interface.shaders_dir
            paths = [
                sd / "presets", sd / "assets", sd / "include",
                self.mmv_package_interface.runtime_dir,
            ]

            self.watchdog_observer = Observer()

            for path in paths:
                self.watchdog_observer.schedule(self.any_modification_watchdog, path = path, recursive = True)

            self.watchdog_observer.start()

        # FPS, manual vsync dealing
        self.start = time.time()
        self.fps_last_n = 120
        self.frame_times = [time.time() + i / self._fps for i in range(self.fps_last_n)]

        # Start audio source
        self.audio_source.start()
        logging.info(f"{debug_prefix} Started audio source")

        steps_each = 0.01 # Generate and write interpolation values 0.00, 0.01, 0.02.. 0.80, 0.81, 0.82
        size = int(1 / steps_each)
        audio_features = ["rms", "std"]

        # Init interpolations based on name and channel yieldeds
        for feature in audio_features:
            for index, channel_name in enumerate("rlm"):
                self.interpolator.add_interpolater(f"mmv_{feature}_{channel_name}", size)
                self.interpolator.add_interpolater(f"mmv_progressive_{feature}_{channel_name}", size)

        # Progressive audio amplitude
        mmv_progressive_rms = [0, 0, 0]

        # FFTs
        self.interpolator.add_interpolater(f"mmv_fft", self.MMV_FFTSIZE, fixed_ratio = 0.2)
        logging.info(f"{debug_prefix} Created interpolators")
        logging.info(f"{debug_prefix} Starting main render loop")

        # Render mode have progress bar
        if self.mode == "render":

            # Create progress bar
            self.progress_bar = tqdm(
                total = self.audio_source.total_steps,
                # unit_scale = True,
                unit = " frames",
                dynamic_ncols = True,
                colour = '#38bed6',
                position = 0,
                smoothing = 0.3
            )

            # Set description
            self.progress_bar.set_description(
                f"Rendering [SSAA={self._ssaa}]({int(self._width * self._ssaa)}x{int(self._height * self._ssaa)})->({self._width}x{self._height})[{self.audio_source.duration:.2f}s] MMV video"
            )

        # Main loop
        for step in itertools.count(start = 0):

            # To reload or not to reload
            if self.any_modification_watchdog.reload:
                self.mgl._read_shaders_from_paths_again()
                self.any_modification_watchdog.reload = False

            # The time this loop is starting
            startcycle = time.time()

            # Calculate the fps
            fps = round(self.fps_last_n / (max(self.frame_times) - min(self.frame_times)), 1)
            
            # Next iteration of some audio reader
            self.audio_source.next(step)

            # Get info to pipe, and the pipelined built info
            pipeline_info = self.audio_source.get_info()
            pipelined = {}

            multiplier = self._multiplier * self.mgl.window_handlers.intensity

            # Shader is not frozen (don't interpolate nor write stuff)
            if not self.mgl.freezed_pipeline:
            
                # Interpolate values
                for feature in audio_features:
                    for index, channel_name in enumerate("rlm"):
                        if f"mmv_{feature}" in pipeline_info.keys():
                            self.interpolator.next(
                                name = f"mmv_{feature}_{channel_name}",
                                feed = pipeline_info[f"mmv_{feature}"][index] * multiplier
                            )

                            self.interpolator.next(
                                name = f"mmv_progressive_{feature}_{channel_name}",
                                feed = (pipeline_info[f"mmv_{feature}"][index] * multiplier) * 4.0,
                                mode = "add"
                            )

                            # Add mono 
                            if feature == "rms":
                                mmv_progressive_rms[index] = \
                                    mmv_progressive_rms[index] + pipeline_info[f"mmv_rms"][index] * multiplier


                # Interpolate FFT, write to FFT texture
                if "mmv_fft" in pipeline_info.keys():
                    self.interpolator.next(name = f"mmv_fft", feed = pipeline_info["mmv_fft"], mode = "replace")
                    self.mgl.write_texture_pipeline(
                        texture_name = "mmv_fft",
                        data = self.interpolator.interpolaters["mmv_fft"]["current"].astype(np.float32) * multiplier
                    )

                # Write spectrogram values
                for v in ["mmv_raw_audio_left", "mmv_raw_audio_right"]:
                    if v in pipeline_info.keys():
                        audio_batch = pipeline_info[v].astype(np.float32)
                        audio_batch_size = audio_batch.shape[0]

                        side = "right" in v

                        self.mgl.write_texture_pipeline(
                            texture_name = "raw_audio",
                            data = audio_batch,
                            viewport = (
                                0, side,
                                audio_batch_size, 1
                            )
                        )

                # Build full pipeline from the interpolator, must be tuple and only current values
                for feature in audio_features:
                    for n in range(size):
                        ratio_prefix = f"{round(n * steps_each, 2):.02f}".replace(".", "_")

                        # The pairs of Right, Left, Mono values vec3 mmv_rms -> mmv_rms[0] [1] [2]
                        pipelined[f"mmv_{feature}_{ratio_prefix}"] = tuple([
                            list(self.interpolator.interpolaters[f"mmv_{feature}_{channel_name}"]["current"])[n]
                            for channel_name in "rlm"
                        ])

                        pipelined[f"mmv_progressive_{feature}_{ratio_prefix}"] = tuple([
                            list(self.interpolator.interpolaters[f"mmv_progressive_{feature}_{channel_name}"]["current"])[n]
                            for channel_name in "rlm"
                        ])

                pipelined["mmv_progressive_rms"] = tuple(mmv_progressive_rms)

            # Next iteration
            self.mgl.next(custom_pipeline = pipelined)

            # Write current image to the video encoder
            if self.mode == "render":
                self.progress_bar.update(1)

                # Write to the FFmpeg stdin
                self.mgl.read_into_subprocess_stdin(self.ffmpeg.subprocess.stdin)

                # Looped the audio one time, exit
                if step == self.audio_source.total_steps - 2:
                    self.ffmpeg.subprocess.stdin.close()
                    break

            # View mode we just update window, print fps
            elif self.mode == "view":
                self.mgl.update_window()

                print(f":: Resolution: [SSAA={self.mgl.ssaa:.2f}]({int(self.mgl.width * self.mgl.ssaa)}x{int(self.mgl.height * self.mgl.ssaa)})->({self.mgl.width}x{self.mgl.height}) Average FPS last ({self.fps_last_n} frames): [{fps}] \r", end = "", flush = True)
                
                # The window received close command
                if self.mgl.window_handlers.window_should_close:
                    self.audio_source.stop()
                    self.mmv_package_interface.thanks_message()
                    break

            # Print FPS, well, kinda, the average of the last fps_last_n frames
            self.frame_times[step % self.fps_last_n] = time.time()

            # Manual vsync (yea we really need this)
            if (not self.mgl.window_handlers.vsync) and (self.mode == "view"):
                while (time.time() - startcycle) < (1 / self._fps):
                    time.sleep(1 / (self._fps * 100))

class ValuesInterpolator:
    def __init__(self):
        self.interpolaters = {}
    
    # Add value to interpolate
    # Size is a np.linspace that goes from 0 to 1 (where interpolation makes sense)
    # if fixed ratio is given then use array filled with that as ratios (ie. FFT bars)
    def add_interpolater(self, name, size, fixed_ratio = None):
        if fixed_ratio is None:
            ratios = np.linspace(0, 1, size)
        else:
            ratios = np.zeros(size, dtype = np.float32)
            ratios.fill(fixed_ratio)
        
        # Build interpolater
        self.interpolaters[name] = {
            "current": np.zeros(size, dtype = np.float32),
            "target": np.zeros(size, dtype = np.float32),
            "ratios": ratios,
        }

    def next(self, name, feed, mode = "fill"):
        # Set new target
        if mode == "fill":
            self.interpolaters[name]["target"].fill(feed)
        if mode == "replace":
            self.interpolaters[name]["target"] = feed
        if mode == "add":
            self.interpolaters[name]["target"] += feed

        # Apply progressive interpolation on ratios, "sc" is shortcut
        sc = self.interpolaters[name]

        # Calculate interpolation between current and target values
        self.interpolaters[name]["current"] = (sc["current"] + ((sc["target"] - sc["current"]) * sc["ratios"]))


# main function to use typer for CLI
def main():
    app = typer.Typer(chain = True)
    cli = MMVShadersCLI()
    app.command()(cli.resolution)
    app.command()(cli.antialiasing)
    app.command()(cli.multiplier)
    app.command()(cli.realtime)
    app.command()(cli.list_captures)
    app.command()(cli.render)
    app.command()(cli.load)
    app()

# This wouldn't be required but Windows :p
if __name__ == "__main__":
    main()
