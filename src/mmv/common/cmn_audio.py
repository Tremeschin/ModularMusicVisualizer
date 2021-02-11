"""
===============================================================================
                                GPL v3 License                                
===============================================================================

Copyright (c) 2020 - 2021,
  - Tremeschin < https://tremeschin.gitlab.io > 

===============================================================================

Purpose: Deal with converting, reading audio files and getting their info

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

from mmv.common.cmn_functions import Functions
from mmv.common.cmn_utils import DataUtils
from mmv.common.cmn_fourier import Fourier
import mmv.common.cmn_any_logger
import audio2numpy
import numpy as np
import samplerate
import subprocess
import audioread
import soundcard
import soundfile
import threading
import logging
import math
import time
import os


class AudioSourceRealtime:
    def __init__(self):
        self.audio_processing = AudioProcessing()

    def init(self, recorder_device = None, search_for_loopback = False):
        debug_prefix = "[AudioSourceRealtime.init]"

        # Search for the first loopback device (monitor of the current audio output)
        # Probably will fail on Linux if not using PulseAudio but oh well
        if (search_for_loopback) and (recorder_device is None):
            logging.info(f"{debug_prefix} Attempting to find the first loopback device for recording")

            # Iterate on every "microphone", or recorder-capable devices to be more precise
            for device in soundcard.all_microphones(include_loopback = True):

                # If it's marked as loopback then we'll use it
                if device.isloopback:
                    self.recorder = device
                    logging.info(f"{debug_prefix} Found loopback device: [{device}]")
                    break            

            # If we didn't match anyone then recorder_device will be None and we'll error out soon
        else:
            # Assign the recorder given by the user since 
            self.recorder = recorder_device

        # Recorder device should not be none
        assert (self.recorder is not None), "Auto search is off and didn't give a target recorder device"

    # Set the target batch size and sample rate.
    def configure(self, batch_size, sample_rate, recorder_numframes = None):
        debug_prefix = "[AudioSourceRealtime.configure]"
        self.batch_size = batch_size
        self.sample_rate = sample_rate
        self.recorder_numframes = recorder_numframes

    # Start the main routines since we configured everything
    def start_async(self):
        debug_prefix = "[AudioSourceRealtime.start_async]"
    
        logging.info(f"{debug_prefix} Starting the main capture and processing thread..")

        # Start the thread we capture and process the audio
        self.capture_process_thread = threading.Thread(target = self.capture_and_process_loop, daemon = True)
        self.capture_process_thread.start()

        # Wait until we have some info so we don't accidentally crash with None type has no attribute blabla
        self.info = {}
        while not self.info:
            time.sleep(0.016)
    
    # Stop the main thread
    def stop(self):
        self.__should_stop = True

    # This is the thread we capture the audio and process it, it's a bit more complicated than a 
    # class that reads from a file because we don't have guaranteed slices we read and also to 
    # synchronize the processing part and the frames we're rendering so it's better to just do
    # stuff as fast as possible here and get whatever next numframes we have to read 
    def capture_and_process_loop(self):

        # A float32 zeros to store the current audio to process
        self.current_batch = np.zeros((2, self.batch_size), dtype = np.float32)

        self.__should_stop = False
        self.info = {}

        # Open a recorder microphone otherwise we open and close the stream on each loop
        with self.recorder.recorder(samplerate = self.sample_rate, channels = 2) as source:

            # Until the user don't run the function stop
            while not self.__should_stop:

                # The array with new stereo data to process, we get whatever there is ready that was
                # buffered (numframes = None) so we don't have to sync with the video or block the code
                # (though we're supposed to be multithreaded here so it won't matter but we lose the
                # ability to have big batch sizes in a "progressive" processing mode).
                # We also transpose the result so we get a [channels, samples] array shape
                new_audio_data = source.record(numframes = int(self.recorder_numframes)).T
    
                # The number of new samples we got
                new_audio_data_len = new_audio_data.shape[1]

                # Offset the Left and Right arrays on the current batch itself by the length of the
                # new data, this is so we always use the index 0 as the next new and unread value
                # relative to when we keep adding and wrapping around
                self.current_batch = np.roll(self.current_batch, - new_audio_data_len, axis = -1)

                # Assign the new data to the current batch arrays
                for channel_number in [0, 1]:

                    # Fade old values on each cycle (multiply by 0.8 should be enough?)
                    self.current_batch[channel_number] = self.current_batch[channel_number] * 0.95

                    # We simply np.put the new data on the current batch array with its entirety
                    # of the length (0, batch_size) on the mode to wrap the values around
                    np.put(
                        self.current_batch[channel_number], # Target array
                        range(0, self.batch_size),          # Where on target array to put the data
                        new_audio_data[channel_number],     # Input data
                        mode = "wrap"                       # Mode (wrap)
                    )
                
                # This yields information as it was calculated so we assign the key (index 0) to the value (index 1)
                for info in self.audio_processing.get_info_on_audio_slice(self.current_batch, original_sample_rate = self.sample_rate):
                    self.info[info[0]] = info[1]

        self.__should_stop = False

    # Do nothing, we're threaded processing the audio
    def next(self):
        pass
    
    # We just return the current info
    def get_info(self):
        return self.info


class AudioFile:

    # Read a .wav file from disk and gets the values on a list
    def read(self, path: str) -> None:
        debug_prefix = "[AudioFile.read]"

        logging.info(f"{debug_prefix} Reading stereo audio in path [{path}], trying soundfile")
        try:
            # Attempt to use soundfile for reading the audio
            self.stereo_data, self.sample_rate = soundfile.read(path)
            
        except RuntimeError:
            # Except it can't, try audio2numpy
            logging.warn(f"{debug_prefix} Couldn't read file with soundfile, trying audio2numpy..")
            self.stereo_data, self.sample_rate = audio2numpy.open_audio(path)

        # We need to transpose to a (2, -1) array
        logging.info(f"{debug_prefix} Transposing audio data")
        self.stereo_data = self.stereo_data.T

        # Calculate the duration and see how much channels this audio file have
        self.duration = self.stereo_data.shape[1] / self.sample_rate
        self.channels = self.stereo_data.shape[0]
        
        # Log few info on the audio file
        logging.info(f"{debug_prefix} Duration of the audio file = [{self.duration:.2f}s]")
        logging.info(f"{debug_prefix} Audio sample rate is         [{self.sample_rate}]")
        logging.info(f"{debug_prefix} Audio data shape is          [{self.stereo_data.shape}]")
        logging.info(f"{debug_prefix} Audio have                   [{self.channels}]")

        # Get the mono data of the audio
        logging.info(f"{debug_prefix} Calculating mono audio")
        self.mono_data = (self.stereo_data[0] + self.stereo_data[1]) / 2

        # Just make sure the mono data is right..
        logging.info(f"{debug_prefix} Mono data shape:             [{self.mono_data.shape}]")


class AudioProcessing:
    def __init__(self) -> None:
        debug_prefix = "[AudioProcessing.__init__]"

        # Create some util classes
        self.fourier = Fourier()
        self.datautils = DataUtils()
        self.functions = Functions()
        self.config = None

        # MMV specific, where we return repeated frequencies from the
        # function process
        self.where_decay_less_than_one = 440
        self.value_at_zero = 5

        # List of full frequencies of notes
        # - 50 to 68 yields freqs of 24.4 Hz up to 
        self.piano_keys_frequencies = [round(self.get_frequency_of_key(x), 2) for x in range(-50, 68)]
        logging.info(f"{debug_prefix} Whole notes frequencies we'll care: [{self.piano_keys_frequencies}]")

    # # New Methods

    def get_info_on_audio_slice(self, audio_slice: np.ndarray, original_sample_rate) -> dict:

        # Calculate MONO
        mono = (audio_slice[0] + audio_slice[1]) / 2

        # # Average audio amplitude

        # L, R, Mono respectively
        average_amplitudes = []

        # Iterate, calculate the median of the absolute values
        for channel_number in [0, 1]:
            average_amplitudes.append(np.median(np.abs(audio_slice[channel_number])))
        
        # Append mono average amplitude
        average_amplitudes.append(sum(average_amplitudes) / 2)

        # Yield average amplitudes info
        yield ["average_amplitudes", tuple([round(value, 8) for value in average_amplitudes])]

        # # Standard deviations

        yield ["standard_deviations", tuple([
            np.std(audio_slice[0]),
            np.std(audio_slice[1]),
            np.std(mono)
        ])]

        # # FFT shenanigans

        processed = []

        # For each channel
        for data in audio_slice:

            # Iterate on config
            for _, value in self.config.items():

                # Get info on config
                sample_rate = value.get("sample_rate")
                start_freq = value.get("start_freq")
                end_freq = value.get("end_freq")

                # Get the frequencies we want and will return in the end
                wanted_freqs = self.datautils.list_items_in_between(
                    self.piano_keys_frequencies,
                    start_freq, end_freq,
                )

                # Resample our data to the one specified on the config
                resampled = self.resample(
                    data = data,
                    original_sample_rate = original_sample_rate,
                    new_sample_rate = sample_rate,
                )

                # Calculate the binned FFT, we get N vectors of [freq, value] of this FFT
                binned_fft = self.fourier.binned_fft(
                    data = resampled,

                    # # Target (re?)sample rate so we normalize the FFT values
                    sample_rate =  sample_rate,
                    original_sample_rate = original_sample_rate,
                )

                # Get the nearest freq and add to processed            
                for freq in wanted_freqs:

                    # Get the nearest and FFT value
                    nearest = self.find_nearest(binned_fft[0], freq)
                    value = binned_fft[1][nearest[0]]

                    # TODO: make configurable
                    flatten_scalar = self.functions.value_on_line_of_two_points(
                        Xa = 20,
                        Ya = 0.2,
                        Xb = 20000,
                        Yb = 62,
                        get_x = nearest[0]
                    )

                    # Append on the wanted FFT values
                    processed.append(abs(value) * flatten_scalar * 6)

        # Yield FFT data
        yield ["fft", np.array(processed).astype(np.float32)]

    # # Common Methods

    # Resample an audio slice (raw array) to some other frequency, this is useful when calculating
    # FFTs because a lower sample rate means we get more info on the bass freqs
    def resample(self,
            data: np.ndarray,
            original_sample_rate: int,
            new_sample_rate: int
    ) -> np.ndarray:

        # If the ratio is 1 then we don't do anything cause new/old = 1, just return the input data
        if new_sample_rate == original_sample_rate:
            return data
        else:
            # Use libsamplerate for resampling the audio otherwise
            return samplerate.resample(data, ratio = (new_sample_rate / original_sample_rate), converter_type = 'sinc_best')

    # Get N semitones above / below A4 key, 440 Hz
    #
    # get_frequency_of_key(-12) = 220 Hz
    # get_frequency_of_key(  0) = 440 Hz
    # get_frequency_of_key( 12) = 880 Hz
    #
    def get_frequency_of_key(self, n, A4 = 440):
        return A4 * (2**(n/12))

    # https://stackoverflow.com/a/2566508
    # Find nearest value inside one array from a given target value
    # I could make my own but this one is more efficient because it uses numpy
    # Returns: index of the match and its value
    def find_nearest(self, array, value):
        index = (np.abs(array - value)).argmin()
        return index, array[index]
    

    # # Old methods [compatibility]


    # Slice a mono and stereo audio data TODO: make this a generator and also accept "real time input?"
    def slice_audio(self,
            stereo_data: np.ndarray,
            mono_data: np.ndarray,
            sample_rate: int,
            start_cut: int,
            end_cut: int,
            batch_size: int=None
        ) -> None:
        
        # Cut the left and right points range
        left_slice = stereo_data[0][start_cut:end_cut]
        right_slice = stereo_data[1][start_cut:end_cut]

        # Cut the mono points range
        # mono_slice = mono_data[start_cut:end_cut]

        if not batch_size == None:
            # Empty audio slice array if we're at the end of the audio
            self.audio_slice = np.zeros([3, batch_size])

            # Get the audio slices of the left and right channel
            self.audio_slice[0][ 0:left_slice.shape[0] ] = left_slice
            self.audio_slice[1][ 0:right_slice.shape[0] ] = right_slice
            # self.audio_slice[2][ 0:mono_slice.shape[0] ] = mono_slice

        else:
            # self.audio_slice = [left_slice, right_slice, mono_slice]
            self.audio_slice = [left_slice, right_slice]

        # Calculate average amplitude
        self.average_value = float(np.mean(np.abs(
            mono_data[start_cut:end_cut]
        )))

    # Calculate the FFT of this data, get only wanted frequencies based on the musical notes
    def process(self,
            data: np.ndarray,
            original_sample_rate: int,
        ) -> None:
        
        # The returned dictionary
        processed = {}

        # Iterate on config
        for _, value in self.config.items():

            # Get info on config
            sample_rate = value.get("sample_rate")
            start_freq = value.get("start_freq")
            end_freq = value.get("end_freq")

            # Get the frequencies we want and will return in the end
            wanted_freqs = self.datautils.list_items_in_between(
                self.piano_keys_frequencies,
                start_freq, end_freq,
            )

            # Calculate the binned FFT, we get N vectors of [freq, value]
            # of this FFT
            binned_fft = self.fourier.binned_fft(
                # Resample our data to the one specified on the config
                data = self.resample(
                    data = data,
                    original_sample_rate = original_sample_rate,
                    new_sample_rate = sample_rate,
                ),

                # # Target (re?)sample rate so we normalize the FFT values

                sample_rate =  sample_rate,
                original_sample_rate = original_sample_rate,
            )

            # Get the nearest freq and add to processed            
            for freq in wanted_freqs:

                # Get the nearest and FFT value
                nearest = self.find_nearest(binned_fft[0], freq)
                value = binned_fft[1][nearest[0]]
     
                # How much bars we'll render duped at this freq, see
                # this function on the Functions class for more detail
                N = math.ceil(
                    self.functions.how_much_bars_on_this_frequency(
                        x = freq,
                        where_decay_less_than_one = self.where_decay_less_than_one,
                        value_at_zero = self.value_at_zero,
                    )
                )

                # Add repeated bars or just one, this is a hacky workaround since we
                # add a small fraction on the target freq, it shouldn't really overlap
                for i in range(N):
                    processed[nearest[1] + (i/10)] = value
        
        # FIXME: inefficient

        # # Convert a dictionary of FFTs to a list of values:frequencies
        # We can use a array with shape (N, 2) but I'm lazy to change that

        linear_processed_fft = []
        frequencies = []

        # For each pair in the dictionary, append to each list
        for frequency, value in processed.items():
            frequencies.append(frequency)
            linear_processed_fft.append(value)
        
        return [linear_processed_fft, frequencies]