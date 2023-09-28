import ctypes
from datetime import datetime
import logging
import time
import numpy as np
import matplotlib.pyplot as plt

from picosdk.ps5000a import ps5000a as ps
from picosdk.functions import adc2mV, assert_pico_ok, mV2adc


class PicoBlockCap():
    def __init__(self, handle, buffer,buffer_size):
        # Resolution defines the bit depth of the data collected, supported bit depths in the PicoDaq SW are 8 and 12 bit
        self.resolution = 1
        # Timebase is an integer that encodes the sampling interval of the scope, calculated using two different sets of equations for 8/12 bit 
        self.timebase = 1

        # ctypes integer that holds a unique reference for the API to use to know which device its communicating with
        self.handle = ctypes.c_int16(handle)
        # Holds the value of the maximum anologue-digital-converter, used for converting ADC_counts to voltage values, varies with bit depth
        self.max_adc = ctypes.c_int16()

        # used to tell the picoscope how many samples to collect, in this case it is equal to the size of the local buffer
        self.samples = buffer_size
        # ctypes copy of the max_samples value, used by the API for applying settings to scope
        self.max_samples = ctypes.c_int32(self.samples)

        # assigns the buffer passed in from outside the class to a class variable, for use throughout the program
        self.buffer = buffer
        # Dictionary to hold status codes returned from the picoSDK API, useful for tracking bugs and errors
        self.status = {}

        # overflow array, shouldn't need to be used, but is required by the API incase it collects more data than the buffer size
        self.overflow = ctypes.c_int16()
        # used by the GetValuesBulk function to check if the scope has finished data collection
        self.ready = ctypes.c_int16(0)
        # used by the GetValuesBulk function to check if the scope has finished data collection, by providing a known check value
        self.check = ctypes.c_int16(0)
        # used by the API to store how many samples can be present in each waveform
        self.samples_per_seg = ctypes.c_int32(0)
    
    def open_unit(self,res):
        """
            Function to open communication with the scope, and to assign the scope to a "handle" so that it can be
            commincated with using that handle throughout the rest of the program, opens the scope with the resolution,
            if the resolution is to be changed during the use of the program, the scope needs to close and reopen 
            communication with a new resolution provided
        """
        print(f'Handle before openunit: {self.handle}')
        # Calls and stores the status of the openunit funciton, the API will return a handle to use, and will apply it here
        self.status["openunit"] = ps.ps5000aOpenUnit(ctypes.byref(self.handle), None, res)
        print(f'Handle after openunit: {self.handle}')
        # Sets the value of max_adc based on the resolution, for use in some calculations later
        self.status["maximumValue"] = ps.ps5000aMaximumValue(self.handle, ctypes.byref(self.max_adc))
        return self.status["openunit"]
    
    def set_channel(self, channel, en, coupling, range, offset):
        """
            Function to set the parameters for any channel, the funciton needs to be passed the channel to target
            identified using 0,1,2,3 and various other parameters, some are enumerated value such as 0,1,2 others are float
        """
        # makes use of the SDK setchannel function, and passes the required variables to it, returns the status code returned from the function
        return ps.ps5000aSetChannel(self.handle, channel, int(en), coupling, range, offset)

    def set_simple_trigger(self, en, source, range, threshold_mv, direction, delay, auto_ms ):
        """
            Function to set the trigger parameters for the picoscope, this means setting the conditions for when the picoscope should 
            start collecting data
        """
        # Calculate the threshold as this needs to be in ADC counts, and is passed to the function as mV
        threshold = int(mV2adc(threshold_mv,range,self.max_adc))
        # makes use of the SDK setsimpletrigger function, and passes the required variables to it, returns the status code returned from the function
        return ps.ps5000aSetSimpleTrigger(self.handle, en, source, threshold, direction, delay, auto_ms)

    def set_buffer(self, channel, buffer, segment):
        """"
            Function to tell the picoscope API where on the PC it should be storing the data its collected, uses a predefined "buffer" 
            to store the data in to
        """
        # makes use of the SDK setdatabuffer function, and passes the required variables to it, returns the status code returned from the function
        return ps.ps5000aSetDataBuffer(self.handle, channel, buffer[0].ctypes.data_as(ctypes.POINTER(ctypes.c_int16)), self.max_samples, segment, 0)
    
    def set_captures(self, captures):
        """
            Function to tell the scope how many waveforms you want it to capture
        """
        # makes use of the sdk memorysegments function, this function splits the memory of the picoscope up into "segments"
        # ideally use 1 segment for 1 capture, this makes retrieving the data simple when you specify how many segments to retrieve
        # This funciton also returns the maximum amount of samples that can be in each segment you created
        self.status["MemorySegments"] = ps.ps5000aMemorySegments(self.handle, captures, ctypes.byref(self.samples_per_seg))
        # makes use of the sdk setnoofcaptures function to tell the picoscope how many waveforms to capture
        self.status["SetNoOfCaptures"] = ps.ps5000aSetNoOfCaptures(self.handle, captures)
        # creates an overflow buffer for each capture defined
        self.overflow = (ctypes.c_int16 * captures)()
        # returns the status code of the setnoofcaptures function
        return self.status["SetNoOfCaptures"]

    def initalise_parameters(self):
        """
            Function to call each of the setup functions in the correct order, and to prime the picoscope ready for data collection
        """
        # Calls each setup function, and provides sensible values
        self.status["openunit"] = self.open_unit(self.resolution)
        self.status["set_source"] = self.set_channel(0,True,0,9,0.0)
        self.status["set_source"] = self.set_channel(1,False,0,9,0.0)
        self.status["set_source"] = self.set_channel(2,False,0,9,0.0)
        self.status["set_source"] = self.set_channel(3,False,0,9,0.0)
        self.status["set_trigger"] = self.set_simple_trigger(1,0,9,0,2,0,10)
        self.status["set_captures"] = self.set_captures(1)
        self.status["set_buffer"] = self.set_buffer(0,self.buffer,0)

    def run_block(self):
        """
            Function for running the block data collection, and then retrieveing the information
        """
        print(self.status)
        # makes use of the sdk runblock function to tell the picoscope to start collecting data
        self.status["runblock"] = ps.ps5000aRunBlock(self.handle, 0, self.samples, self.timebase, None, 0, None, None)

        # use a while loop to check if "self.ready" has changed from its default of 0, if it has changed, that means data collectio is finished.
        print(f'Self.ready = {self.ready.value}')
        while self.ready.value == self.check.value:
            self.status["isReady"] = ps.ps5000aIsReady(self.handle, ctypes.byref(self.ready))
        print(f'Self.ready = {self.ready.value}')
        #time.sleep(10)

        # once data collection is finished, use the sdk getvaluesbulk function to retrieve all captures done, here you specify the start and end segments to retrieve
        self.status["GetValuesBulk"] = ps.ps5000aGetValuesBulk(self.handle, ctypes.byref(self.max_samples), 0, 0, 0, 0, ctypes.byref(self.overflow))
        # reset the self.ready value ready for another collection
        self.ready = ctypes.c_int16(0)

        print(f'Buffer contents {self.buffer}')

    def stop_scope(self):
        """
            Function to cleanly end the picoscope connection, tells the picoscope to stop its current action, and to close the connection
        """
        self.status["stop"] = ps.ps5000aStop(self.handle)
        self.status["close"] = ps.ps5000aCloseUnit(self.handle)
        print(f'Handle after closing device: {self.handle}')
        return self.status["close"]


#######################################################################################################################################################
##                                                       Example usage of code above                                                                 ##
#######################################################################################################################################################


# Create a "buffer" for the scope data to go into
streaming_buffer = []
# add a numpy array into the buffer, numpy allows for easy selection of the shape and data type for the array
streaming_buffer.append(np.zeros(100000,dtype='int16'))

# initalise an instance of the picoblockcap class called "test", this will represent the scope, and pass it the resolution, the buffer, and the sample size of the waveforms
test = PicoBlockCap(0,streaming_buffer,100000)


# tell the scope to setup with the default parameters for the picoscope
test.initalise_parameters()

# tell the scope to run the block data collection
test.run_block()
# using a graphing library, plot the data from the buffer
plt.plot(streaming_buffer[0])
# using a graphing library, show the plotted data
plt.show()

# tell the scope to run another capture with the same settings, and plot and display as before
test.run_block()
plt.plot(streaming_buffer[0])
plt.show()

# tell the scope to change some of the default settings that were set in "initalise_parameters", in this case we are switching from channel 0 (a) to channel 1 (b)
test.status["set_source"] = test.set_channel(0,False,0,9,0.0)
test.status["set_source"] = test.set_channel(1,True,0,9,0.0)
test.status["set_buffer"] = test.set_buffer(1,test.buffer,0)
ret = test.set_simple_trigger(1,1,9,0,2,0,10)
# tell the scope to run a new block collection with the changed settings, and display as before
test.run_block()
plt.plot(streaming_buffer[0])
plt.show()

# Once we are done with the picoscope we tell it to stop what its doing, and to close the connection for a clean and error free stop
test.stop_scope()
