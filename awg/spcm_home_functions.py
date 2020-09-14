import numpy as np
import math
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from scipy import interpolate
import ctypes

import sys
import time
import json
import os

###############################################
## Currently this code does not do interpolation
## for the moving trap. Just static and ramp.
##################################################

def adjuster (requested_freq,samplerate,memSamples):
    """
    This function corrects the requested frequency to account for the fractional number of 
    cycles the card can produce for a given memory sample.
    The function takes the value of the requested frequency in MHz.
    The values of samplerate and memSamples are directly taken from the setup code to avoid small errors.
    These are typically given in Hz and bytes respectively.
    """
    nCycles = np.round(requested_freq/samplerate*memSamples)
    newFreq = np.round(nCycles*samplerate/memSamples)
    return newFreq

def minJerk(t,d,T):
    """
    This funtion is the smoothstep function used by the Ni group, which has minimum jerk. 
    t: sample/time
    d: total distance/frequency spanned
    T: total duration/number of samples desired
    """
    return d*(10*(1.*t/T)**3 - 15*(1.*t/T)**4 + 6*(1.*t/T)**5)


def hybridJerk(t,d,T,a):
    """
    Similar to the minimum Jerk trajectory, with the difference that you can control
    what percentage of the trajectory is meant to be minimum jerk.
    Here the function is converted into a piecewise function using if statements. 
    t: sample/time
    d: total distance/frequency spanned
    T: total duration/number of samples desired
    a: percentage of trajectory being minimum jerk (a=0 is 100% minimum jerk, a=1 is fully linear motion.
    
    """
    t=1.*t
    d=1.*d
    T=1.*T
    a=1.0*a
    if(a==1):
        return d/T*1.*t
    else:
        a1 = int(0.5*T*(1.-a))  # Handles the first portion of the acceleration.
        a2 = int(T-0.5*T*(1-a)) # Handles the linear part of the trajectory.
        a3 = int(T)             # Handles the last part of the deceleration.
        
        
        t[:a1]   = minJerk(t[:a1],2*d/(2+15./4.*a/(1-a)),T*(1-a))
        t[a1:a2] = 15.*d/(8*T + 7*T*a)*t[a1:a2] + 7*d*(a-1)/(2.*(8+7*a))
        t[a2:a3] = minJerk(t[a2:a3]-(T-T*(1-a)), 2.*d/(2+15./4*a/(1 - a)), T*(1 - a)) + a*T*15./8*8*d/(8*T + 7*T*a)
        return t
              
            

                
def chirp(t,d,T,a):
    """
    Chirping is a frequency modulation method where the phase component of a sine wave is no longer
    time-independent. The chip function is effectively the integral wrt time of the desired type of modulation..
    The function shown here is the integral of the hybridJerk function shown just above. The integration was done in
    Mathematica and was adapted for python use into a piecewise function. 
    t: sample/time
    d: total distance/frequency spanned
    T: total duration/number of samples desired
    a: percentage of trajectory being minimum jerk (a=0 is 100% minimum jerk, a=1 is fully linear motion.
    """
    a1 = int(0.5*T*(1.-a))  # Handles the first portion of the acceleration.
    a2 = int(T-0.5*T*(1-a)) # Handles the linear part of the trajectory.
    a3 = int(T)                  # Handles the last part of the deceleration.
    
    t[:a1]   = (8.*d*(t[:a1]**6 + 3*t[:a1]**5.*T*(a-1.) +5./2*T**2 * t[:a1]**4 * (a-1.)**2))/(1.*T**5 * (a-1.)**4 * (8.+7.*a))
    t[a1:a2] = 0.5*d*t[a1:a2]/(8.+7.*a)*(-7.+7.*a +15./T * t[a1:a2])
    t[a2:a3] = 1.*d/(T**5 * (a-1.)**4 * (8.+7.*a))*\
        (8.*t[a2:a3]**6 + 120.*t[a2:a3]**2 * T**4 * a**2 - 24.* t[a2:a3]**5 * T* (1.+a) - \
        80.* t[a2:a3]**3 * T**3 *a*(1.+a) +20.*t[a2:a3]**4 * T**2 * (1.+4.*a+a**2) + \
        1.*t[a2:a3] * T**5 * a *(15.-60.*a +10.*a**2-20.*a**3 + 7.*a**4))
    return t
    
        
######################
# Calibration data for interpolation
# Values that normally go above 1, are limited to 1.
# More info here: https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.interp1d.html
########################################################


importPath="Z:\\Tweezer\Experimental\\Setup and characterisation\\Settings and calibrations\\tweezer calibrations\\AWG calibrations\\"
importFile = "calFile_05.09.2020.txt"


with open(importPath+importFile) as json_file:
    calFile = json.load(json_file) 


contour_dict = calFile["Power_calibration"]
for key in contour_dict.keys():
    try:
        contour_dict[key]['Calibration'] = interpolate.interp1d(contour_dict[key]['Frequency (MHz)'], contour_dict[key]['RF Amplitude (mV)'])
    except Exception as e: print(e)


cal_umPerMHz = eval(calFile["umPerMHz"])


def ampAdjuster(freq, optical_power):
    i = np.argmin([abs(float(p) - optical_power) for p in contour_dict.keys()]) # find closest power in dictionary of contours
    key = list(contour_dict.keys())[i]
    y = np.array(contour_dict[key]['Calibration'](freq)) # return amplitude in mV to keep constant optical power
    y[y>220] = 220
    # if >220 print warning
    return y

def getFrequencies(action,*args):
    
    if action ==1 or action==3 or action ==4:
        if len(args)==7:
            freqs          = args[0]
            numberOfTraps  = args[1]
            distance       = args[2]
            duration       = args[3]
            freqAdjust     = args[4]
            sampleRate     = args[5]
            umpermhz       = args[6]
        else:
            print("Expecting 7 arguments: [freq,number of traps, distance,duration, bool_freqAdjust,sample rate, umPerMHz]")
    
    elif action ==2:
        if len(args)==5:
            startFreq      = args[0]
            endFreq        = args[1]
            duration       = args[2]
            freqAdjust     = args[3]
            sampleRate     = args[4]
        else:
            print("Expecting 5 arguments: [start freqs,ending freqs,duration, bool_freqAdjust,sample rate]")
    else:
        print("Action value not recognised.\n")
        print("1: Static trap. \n")
        print("2: Moving trap. \n")
        print("3: Amplitude ramp.\n")
    
    Samplerounding = 1024 # Reference number of samples
    memBytes = round(sampleRate * (duration*10**-3)/Samplerounding) #number of bytes as a multiple of kB
        
    if memBytes <1:
        memBytes =1
        
    numOfSamples = int(memBytes*Samplerounding) # number of samples
    
    if action ==1 or action==3:
    
        ############################
        # If the input is a list, then ignore numberOfTraps and separation.
        # The traps are not by virtue equidistant so no need to calculate those values.
        ######################################################################################
        if type(freqs)==list or type(freqs)==np.ndarray:
            freqs = np.array(freqs)
            numberOfTraps = len(freqs)
        else:
            separation = distance/cal_umPerMHz *10**6
            freqs = np.linspace(freqs,freqs+(numberOfTraps)*separation,numberOfTraps, endpoint=False)
            
        #########
        # Adjust the frequencies to full number of cycles for the 
        # given number of samples if requested.
        ###############################################
        if freqAdjust == True:
            adjFreqs = adjuster(freqs,sampleRate,numOfSamples)
            
        else:
            adjFreqs = freqs
        
        return adjFreqs
    
    elif action ==2:
        
        
        ############################
        # Standarise the input to ensure that we are dealing with a list.
        ##############################################################################
        if type(startFreq )== int or type(startFreq) == float:
            startFreq =  np.array([startFreq])
        if type(endFreq )== int or type(endFreq) == float:
            endFreq =  np.array([endFreq])
        
        #######################################
        # Standarize the input in case of a list. No effect if already an np.array()
        #################################################################################     
        startFreq = np.array(startFreq)
    
        endFreq = np.array(endFreq)
        
        if freqAdjust == True:
            sfreq    = adjuster(startFreq,sampleRate,numOfSamples) 
            ffreq    = adjuster(endFreq,sampleRate,numOfSamples)
        else:
            sfreq    = startFreq
            ffreq    = endFreq
    
        return np.array([sfreq,ffreq])
    

def moving(startFreq, endFreq,duration,a,tot_amp,startAmp,endAmp,freq_phase,freq_adjust,amp_adjust,sampleRate):
    """
    Identical to the moving function above. The only difference is that it also applies the adjuster function
    to ensure that the starting and end frequencies are as close as possible to the frequencies needed
    to complete full cycles.
    startFreq  : Initial frequency in Hz
    endFreq    : Final frequency in Hz
    duration   : duration of chirp in ms. It automatically calculates the adequate number of samples needed. 
    a          : percentage of trajectory being minimum jerk (a=0 is 100% minimum jerk, a=1 is fully linear motion.
    tot_amp    : global amplitude control over all frequencies
    startAmp   : list for individual starting amplitude control
    endAmp     : list for individual ending amplitude control
    freq_phase : list for individual phase control
    freq_adjust: Boolean for frequency correction
    amp_adjust : Boolean for amplitude flattening
    sampleRate : sample rate in Samples per second
    """
    Samplerounding = 1024
    
    memBytes = round(sampleRate * (duration*10**-3)/Samplerounding) #number of bytes as a multiple of kB
    if memBytes <1:
        memBytes =1
    numOfSamples = int(memBytes*Samplerounding )# number of samples
    t = np.arange(numOfSamples)
    
    ############################
    # Standarise the input to ensure that we are dealing with a list.
    ##############################################################################
    if type(startFreq )== int or type(startFreq) == float:
           startFreq =  np.array([startFreq])
    if type(endFreq )== int or type(endFreq) == float:
           endFreq =  np.array([endFreq])
    
    #######################################
    # Standarize the input in case of a list. No effect if already an np.array()
    #################################################################################     
    startFreq = np.array(startFreq)

    endFreq = np.array(endFreq)
    
    ##############################
    # Ensure that the freq_amp/freq_phase all have the correct size.
    ################################################################################
    if len(startFreq) != len(endFreq):
        print("Number of initial and final frequencies do not match.")
        endFreq = np.array([170]*len(startFreq))
    
    l = len(startFreq)
    
    ######################
    # Adjust the frequencies to full number of cycles for the 
    # given number of samples if requested.
    ###############################################
    
    if freq_adjust == True:
        sfreq    = adjuster(startFreq,sampleRate,numOfSamples) 
        ffreq    = adjuster(endFreq,sampleRate,numOfSamples)
        rfreq    = np.asarray(ffreq-sfreq)
    else:
        sfreq    = startFreq
        ffreq    = endFreq
        rfreq    = np.asarray(ffreq-sfreq)
    
    if len(startAmp) != l:
        startAmp = [1]*l
        print("Number of set starting amplitudes do not match number of frequencies. All starting amplitudes have been set to max (1).")
    
    if len(endAmp) != l:
        endAmp = [1]*l
        print("Number of set ending amplitudes do not match number of frequencies. All ending amplitudes have been set to max (1).")
    
    amp_ramp = np.array([(1.*startAmp[Y] + (1.*endAmp[Y] - 1.*startAmp[Y])*t/numOfSamples) for Y in range(l)])
            
    if len(freq_phase) != l:
        freq_phase = [0]*l
        print("Number of set phases do no match the number of frequencies. All individual phases have been set to 0. ")
            
    #########
    # Generate the data 
    ##########################   
   # t is now defined further up, after numberOfSamples
    
    if(a==1) and not amp_adjust: # Linear sweep
            y = 1.*tot_amp/282/len(startFreq)*0.5*2**16 *np.sum([\
            amp_ramp[Y]*\
            np.sin(2.*math.pi*(1.*sfreq[Y]/sampleRate*t+0.5*(rfreq[Y])/sampleRate/numOfSamples*t**2)+freq_phase[Y])\
            for Y in range(l)],axis=0) 
            
    elif amp_adjust: 
            # take samples across the diffraction efficiency curve and then interpolate
            idxs = np.linspace(0, len(t)-1, 50).astype(int)
            amp_ramp_adjusted = [interpolate.interp1d(t[idxs], 
                    [ampAdjuster(sfreq[Y]*1e-6 + hybridJerk(t[i], rfreq[Y]*1e-6, numOfSamples, a), amp_ramp[Y][i])
                        for i in idxs], kind='linear')
                for Y in range(l)]

            y = 1./282/len(startFreq)*0.5*2**16 *np.sum([
                amp_ramp_adjusted[Y](t) * 
                np.sin(2*math.pi*(sfreq[Y]/sampleRate*t + chirp(t, rfreq[Y]/sampleRate, numOfSamples, a)) 
                + freq_phase[Y]) for Y in range(l)], axis=0) 
            
    else: # Hybrid/Minimum jerk
            
            y  = 1.*tot_amp/282/len(startFreq)*0.5*2**16 *np.sum([\
            amp_ramp[Y]*\
            np.sin(2.*math.pi*(sfreq[Y]/sampleRate*t +\
            chirp(t, rfreq[Y]/sampleRate, numOfSamples, a)) \
            +freq_phase[Y]) for Y in range(l)],axis=0)

    return y  




def static(centralFreq=170*10**6,numberOfTraps=4,distance=0.329*5,duration = 0.1,tot_amp=10,freq_amp = [1],freq_phase=[0],freqAdjust=True,ampAdjust=True,sampleRate = 625*10**6,umPerMHz =cal_umPerMHz):
    """
    centralFreq   : Defined in [MHz]. Accepts int/float/list/numpy.arrays()
    numberOfTraps : Defines the total number of traps including the central frequency.
    distance      : Defines the relative distance between each of the trap in [MICROmeters]. Can accept negative values.
    duration      : Defines the duration of the static trap in [MILLIseconds]. The actual duration is handled by the number of loops.
    tot_amp       : Defines the global amplitude of the sine waves [mV]
    freq_amp      : Defines the individual frequency amplitude as a fraction of the global (ranging from 0 to 1).
    freq_phase    : Defines the individual frequency phase in degrees [deg].
    freqAdjust    : On/Off switch for whether the frequency should be adjusted to full number of cycles [Bool].
    sampleRate    : Defines the sample rate by which the data will read [in Hz].
    umPerMHz      : Conversion rate for the AWG card.
    """
    Samplerounding = 1024 # Reference number of samples
    
    ############################
    # If the input is a list, then ignore numberOfTraps and separation.
    # The traps are not by virtue equidistant so no need to calculate those values.
    ######################################################################################
    if type(centralFreq)==list or type(centralFreq)==np.ndarray:
        freqs = np.array(centralFreq)
        numberOfTraps = len(freqs)
    else:
        separation = distance/umPerMHz *10**6
        freqs = np.linspace(centralFreq,centralFreq+(numberOfTraps)*separation,numberOfTraps, endpoint=False)
    
    ##############################
    # Ensure that the freq_amp/freq_phase all have the correct size.
    ################################################################################
    
    if numberOfTraps != len(freq_amp):
        freq_amp = [1]*numberOfTraps
        print("ERROR: Number of amplitudes do not match number of traps. All traps set to 100%\n")
             
    
    if numberOfTraps != len(freq_phase):
        freq_phase = [0]*numberOfTraps
        print("ERROR: Number of phases do not match number of traps. All trap phases set to 0.\n")
    
    ################
    # Calculate the number of samples
    ######################################### 
    memBytes = round(sampleRate * (duration*10**-3)/Samplerounding) #number of bytes as a multiple of kB
    
    if memBytes <1:
        memBytes =1
        
    numOfSamples = int(memBytes*Samplerounding) # number of samples
    
    #########
    # Adjust the frequencies to full number of cycles for the 
    # given number of samples if requested.
    ###############################################
    if freqAdjust == True:
        adjFreqs = adjuster(freqs,sampleRate,numOfSamples)
        
    else:
        adjFreqs = freqs
    
    #########
    # Generate the data 
    ########################## 
    t = np.arange(numOfSamples)
    if ampAdjust ==True:
        return 1./282/len(freqs)*0.5*2**16*np.sum([ampAdjuster(freqs[Y]*10**-6,freq_amp[Y])*np.sin(2.*np.pi*t*adjFreqs[Y]/sampleRate+ 2*np.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)],axis=0)
    else:
        return 1.*tot_amp/282/len(freqs)*0.5*2**16*np.sum([freq_amp[Y]*np.sin(2.*np.pi*t*adjFreqs[Y]/sampleRate+ 2*np.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)],axis=0)
    


def ramp(freqs=[170e6],numberOfTraps=4,distance=0.329*5,duration =0.1,tot_amp=220,startAmp=[1],endAmp=[0],freq_phase=[0],freqAdjust=True,ampAdjust=True,sampleRate = 625*10**6,umPerMHz =cal_umPerMHz):
    """
    freqs         : Defined in [MHz]. Accepts int, list and np.arrays()
    numberOfTraps : Defines the total number of traps including the central frequency.
    distance      : Defines the relative distance between each of the trap in [MICROmeters]. Can accept negative values.
    duration      : Defines the duration of the static trap in [MILLIseconds]. The actual duration is handled by the number of loops.
    tot_amp       : Defines the global amplitude of the sine waves [mV]
    startAmp      : Defines the individual frequency starting amplitude as a fraction of the global (ranging from 0 to 1).
    endAmp        : Defines the individual frequency ending amplitude as a fraction of the global (ranging from 0 to 1).
    freq_phase    : Defines the individual frequency phase in degrees [deg].
    freqAdjust    : On/Off switch for whether the frequency should be adjusted to full number of cycles [Bool].
    ampAdjust     : On/Off switch for whether the amplitude should be adjusted to create a diffraction flattened profile.
    sampleRate    : Defines the sample rate by which the data will read [in Hz].
    umPerMHz      : Conversion rate for the AWG card.
    """
    Samplerounding = 1024 # Reference number of samples
    
    
    ############################
    # If the input is a list, then ignore numberOfTraps and separation.
    # The traps are not by virtue equidistant so no need to calculate those values.
    ######################################################################################
    if type(freqs)==list or type(freqs)==np.ndarray:
        
        freqs = np.array(freqs)
        numberOfTraps = len(freqs)
    else:
        separation = distance/umPerMHz *10**6
        freqs = np.linspace(freqs,freqs+numberOfTraps*separation,numberOfTraps, endpoint=False)
    

    ##############################
    # Ensure that the startAmp/endAmp/freq_phase all have the correct size.
    ################################################################################
    
    if numberOfTraps != len(startAmp):
        startAmp = [1]*numberOfTraps
        print("ERROR: Number of start amplitudes do not match number of traps. All traps set to 100%\n")
            
    if numberOfTraps != len(endAmp):
        endAmp = [0]*numberOfTraps
        print("ERROR: Number of end amplitudes do not match number of traps. All end traps set to 0.\n")
    
    if numberOfTraps != len(freq_phase):
        freq_phase = [0]*numberOfTraps
        print("ERROR: Number of phases do not match number of traps. All trap phases set to 0.\n")
        

    ################
    # Calculate the number of samples
    ######################################### 
    memBytes = round(sampleRate * (duration*10**-3)/Samplerounding) #number of bytes as a multiple of kB
    
    if memBytes <1:
        memBytes =1
        
    numOfSamples = int(memBytes*Samplerounding) # number of samples
    
    #########
    # Adjust the frequencies to full number of cycles for the 
    # given number of samples if requested.
    ###############################################
    if freqAdjust == True:
        adjFreqs = adjuster(freqs,sampleRate,numOfSamples)
        
    else:
        adjFreqs = freqs
        
    ########
    # Adjust the amplitude of the starting and finish
    # to be relative to the diffraction flattened profile
    ###############################
    
    #########
    # Generate the data 
    ##########################   
    t =np.arange(numOfSamples)
    
    y = 1.*tot_amp/282/len(freqs)*0.5*2**16*\
    np.sum([(1.*startAmp[Y] + (1.*endAmp[Y] - 1.*startAmp[Y])*t/numOfSamples)*np.sin(2.*np.pi*t*adjFreqs[Y]/sampleRate + 2*np.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)],axis=0)
    
    return y


def ampModulation(centralFreq=170*10**6,numberOfTraps=4,distance=0.329*5,duration = 0.1,tot_amp=10,freq_amp = [1],mod_freq=100e3,mod_depth=0.2,freq_phase=[0],freqAdjust=True,ampAdjust=True,sampleRate = 625*10**6,umPerMHz =cal_umPerMHz):
    """
    centralFreq   : Defined in [MHz]. Accepts int/float/list/numpy.arrays()
    numberOfTraps : Defines the total number of traps including the central frequency.
    distance      : Defines the relative distance between each of the trap in [MICROmeters]. Can accept negative values.
    duration      : Defines the duration of the static trap in [MILLIseconds]. The actual duration is handled by the number of loops.
    tot_amp       : Defines the global amplitude of the sine waves [mV]
    freq_amp      : Defines the individual frequency amplitude as a fraction of the global (ranging from 0 to 1).
    mod_freq      : Defines the amplitude modulation frequency for all trap frequencies [Hz]
    mod_depth     : Defines the modulation depth of the amplitude modualtion (fraction, ranging from 0 to 1)
    freq_phase    : Defines the individual frequency phase in degrees [deg].
    freqAdjust    : On/Off switch for whether the frequency should be adjusted to full number of cycles [Bool].
    sampleRate    : Defines the sample rate by which the data will read [in Hz].
    umPerMHz      : Conversion rate for the AWG card.
    """
    Samplerounding = 1024 # Reference number of samples
    
    ############################
    # If the input is a list, then ignore numberOfTraps and separation.
    # The traps are not by virtue equidistant so no need to calculate those values.
    ######################################################################################
    if type(centralFreq)==list or type(centralFreq)==np.ndarray:
        freqs = np.array(centralFreq)
        numberOfTraps = len(freqs)
    else:
        separation = distance/umPerMHz *10**6
        freqs = np.linspace(centralFreq,centralFreq+(numberOfTraps)*separation,numberOfTraps, endpoint=False)
    
    ##############################
    # Ensure that the freq_amp/freq_phase all have the correct size.
    ################################################################################
    
    if numberOfTraps != len(freq_amp):
        freq_amp = [1]*numberOfTraps
        print("ERROR: Number of amplitudes do not match number of traps. All traps set to 100%\n")
             
    
    if numberOfTraps != len(freq_phase):
        freq_phase = [0]*numberOfTraps
        print("ERROR: Number of phases do not match number of traps. All trap phases set to 0.\n")
    
    ################
    # Calculate the number of samples
    ######################################### 
    memBytes = round(sampleRate * (duration*10**-3)/Samplerounding) #number of bytes as a multiple of kB
    
    if memBytes <1:
        memBytes =1
        
    numOfSamples = int(memBytes*Samplerounding) # number of samples
    
    #########
    # Adjust the frequencies to full number of cycles for the 
    # given number of samples if requested.
    ###############################################
    if freqAdjust == True:
        adjFreqs = adjuster(freqs,sampleRate,numOfSamples)
        
    else:
        adjFreqs = freqs
    
    #########
    # Generate the data 
    ########################## 
    
    t = np.arange(numOfSamples)
    mod_amp = mod_depth*np.sin(2.*np.pi*t*mod_freq/sampleRate)
    if ampAdjust:
        return 1./282/len(freqs)*0.5*2**16*np.sum([ampAdjuster(freqs[Y]*10**-6,freq_amp[Y] * (1+mod_depth*np.sin(2.*np.pi*t*mod_freq/sampleRate)))*np.sin(2.*np.pi*t*adjFreqs[Y]/sampleRate+ 2*np.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)],axis=0)
    else:
       return 1.*tot_amp/282/len(freqs)*0.5*2**16*np.sum([freq_amp[Y]*(1+mod_amp)*np.sin(2.*np.pi*t*adjFreqs[Y]/sampleRate+ 2*np.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)],axis=0)
    
#Using ideas from the following:
#https://towardsdatascience.com/reshaping-numpy-arrays-in-python-a-step-by-step-pictorial-tutorial-aed5f471cf0b
def multiplex_old(*array):
    """
    converts a list of arguments in the form of [a,a,a,...], [b,b,b,...],[c,c,c,...]
    into a multiplexed sequence: [a,b,c,a,b,c,a,b,c,...]
    """
    l=len(array)
    a_stack = np.stack((array[x] for x in range(l)),axis=0)
    return a_stack.ravel(order="F")

# Based on the following        
# https://stackoverflow.com/questions/3195660/how-to-use-numpy-array-with-ctypes    
def multiplex(*array):
    """
    converts a list of arguments in the form of [a,a,a,...], [b,b,b,...],[c,c,c,...]
    into a multiplexed sequence: [a,b,c,a,b,c,a,b,c,...]
    """
    l = len(array)
    c = np.empty((len(array[0]) * l,), dtype=array[0].dtype)
    for x in range(l):
        c[x::l] = array[x]
    return c
# a1 = np.array([1,3,5])
# a2 = np.array([2,4,6])
# a3 = np.array([12,14,16])
# print(multiplex(a1,a2))

def lenCheck(*args):
    """
    Accepts a set of lists or arrays and test that all arguments have the same length.
    """

    return all(len(args[0])==len(args[x]) for x in range(0,len(args)))

# a1 = np.array([1,3,5])
# a2 = np.array([2,4,6])
# a3 = np.array([12,14,16])
# print(lenCheck(a1,a2))
    
def typeChecker(x):
    """
    Checks if the input is in string, and returns
    the eval version of it if it is. 
    """
    if type(x) == str:
        return eval(x)
    else:
        return x

if __name__ == "__main__":
    ls = np.array([100e6,150e6,180e6])
    ls2 = np.array([200e6,170e6,180e6])
    l2=len(ls)
    set1 =[ls,ls2,0.12,625e6]
    set2 =[[1,2,3],[10,8,1],1024,100]
    var = set1
   
    """
    Standard templates for each of the 'actions'
    """
    #template = static(170e6,3,-0.329*5,0.02,220,[1,0,0],[0,0,0],False,False,625*10**6)
    template   = moving(var[0], var[1],var[2],1,220,[1,0,0],[0,0,0],[0]*l2,False,False,var[3])
    #template = ramp(np.array([138e6,180e6]),2,-0.329*50,0.2,220,[1,0],[0.5,0],[0,0],False,False,625e6)
    template2 = ampModulation(170e6,3,-0.329*5,0.02,220,[1,0,0],100e3,0.5,[0,0,0],False,False,625*10**6)
    
    """
    The following lines are for multiplexing data
    """
    # a1 = static(var[0][0],1,-0.329*5,var[2],220,[1],[0],False,False,var[3])
    # a2 = static(var[1][0],1,-0.329*5,var[2],220,[1],[0],False,False,var[3])
    # am = multiplex(a1,a2)
    # template  = am[ : :2]
    # template2 = am[1: :2]
    
    r = template
    r2=template2
    length = 10000 # len(r)
    
    """
    Basic data plots for static/move/ramp functions
    """
    # fig1,axs = plt.subplots(2,1)
    # axs[0].plot(np.arange(0,length),r[:length])
    # axs[0].plot(np.arange(0,length),r2[:length])
    # #axs[0].set_ylim([-0.5*2**16,0.5*2**16])
    # axs[0].set_xlabel("Number of Samples (First " +str(length)+ ")")
    # axs[0].set_ylabel("Amplitude , arb")
    # 
    # 
    # 
    # axs[1].plot(np.arange(0,length),r[-length:])
    # axs[1].plot(np.arange(0,length),r2[-length:])
    # #axs[1].set_ylim([-0.5*2**16,0.5*2**16])
    # axs[1].set_xlabel("Number of Samples (Last " +str(length)+ ")")
    # axs[1].set_ylabel("Amplitude, arb")
    # fig1.tight_layout(pad=3.0)
    # fig1.show()
    
    
    
    
    
    """
    FFT plot of the selected action function.
    """
    
    ##fft
    #plt.figure()
    #plt.plot(np.fft.fftfreq(len(r), 1/625e6), np.fft.fft(r))
    
    
    """
    Plots of the amplitude flattening for the static and ramp functions
    as well as useful interpolation curves.
    """
    
#     gs=GridSpec(3,2) # 2 rows, 2 columns
#     fig=plt.figure(figsize=(8,8))
#     
#     xint =np.arange(120,220,0.1)
#     yint = int166(xint) 
#     
#     intmVtoDEX =  np.arange(100,280,0.1)      
#     intmVtoDEY = intmVtoDE(intmVtoDEX)
# 
#     ax1=fig.add_subplot(gs[0,:]) # First row, span columns  
#     ax2=fig.add_subplot(gs[1,0]) # Second row, first column
#     ax3=fig.add_subplot(gs[1,1]) # Second row, second column
#     ax4=fig.add_subplot(gs[2,:]) # Third row, span columns 
#     
#     ax1.plot(cal166X,cal166Y, linestyle='--', marker='o')
#     ax1.plot(xint,yint)
#     ax1.set_xlabel("Frequency, MHz")
#     ax1.set_ylabel("Relative DE (@166 MHz)")
#     
#     ax2.plot(mVs,mVtoDE, linestyle='--', marker='o')
#     ax2.plot(intmVtoDEX,intmVtoDEY)
#     ax2.set_xlabel("AWG output ,  mV")
#     ax2.set_ylabel("DE % (@170 MHz)")
#     
#     ax3.plot(mVtoDE,mVs, linestyle='--', marker='o')
#     ax3.plot(intmVtoDEY,intmVtoDEX)
#     ax3.set_xlabel("DE % (@170 MHz)")
#     ax3.set_ylabel("AWG output ,  mV")
#     
#     
#     x2=np.linspace(120,220,1000)
#     ax4.plot(x2,ampAdjuster(x2,1))
#     ax4.plot(x2,ampAdjuster(x2,0.9))
#     ax4.plot(x2,ampAdjuster(x2,0.8))
#     ax4.plot(x2,ampAdjuster(x2,0.6))
#     ax4.set_xlabel("Frequency, MHz")
#     ax4.set_ylabel("Fractional Amplitude (rel. to 166 MHz)")
# 
#     fig.tight_layout()
#     fig.show()

    """
    Testing the amplitude flattening during a move action.
    Frequencies spanned are reproduced according to the hybridicity value a.
    These frquencies are then fed into the amplitude conversion (for a given total amplitude)
    """
    #samples = 1000
    #tvals= np.arange(samples)
    #startFreq = 120
    #endFreq =200
    #d = (endFreq-startFreq)
    #
    #
    #freqChange0 = startFreq+hybridJerk(tvals,d, samples,0) #calculates the frequencies used for a given hybridicity trajectory a=0
    #freqChange1 = startFreq+hybridJerk(tvals,d, samples,1) #calculates the frequencies used for a given hybridicity trajectory a=1
    #
    #ampMove0 = ampAdjuster(freqChange0,1)
    #ampMove1 = ampAdjuster(freqChange1,1)
    #
    #gs=GridSpec(2,1) # 2 rows, 2 columns
    #fig2=plt.figure(figsize=(6,6))
    #ax1=fig2.add_subplot(gs[0,:]) # First row, span columns
    #ax1.plot(tvals,freqChange0, linestyle='--', marker='o')
    #ax1.plot(tvals,freqChange1, linestyle='--', marker='o')
    #ax1.set_xlabel("Samples")
    #ax1.set_ylabel("Frequency, arb")
    #
    #
    #
    #
    #ax2 =fig2.add_subplot(gs[1,:]) # First row, span columns
    #ax2.plot(tvals,ampMove0, linestyle='--', marker='o')
    #ax2.plot(tvals,ampMove1, linestyle='--', marker='o')
    #ax2.set_xlabel("Samples")
    #ax2.set_ylabel("Fractional Amplitude correction")
    #fig2.tight_layout()
    #fig2.show()

    """
    For timing purposes
    """
    from timeit import default_timer as timer
    
    # start = timer()
    # template = ampModulation(170e6,2,-0.329*5,100,220,[1,1],100e3,[0,0],False,True,625*10**6)
    # end = timer()
    # print(end - start) # Time in seconds, e.g. 5.38091952400282
    #
    #start = timer()
    #template2   = moving(var[0], var[1],1,1,220,[1,1,1],[1,1,1],[0]*l2,False,True,var[3])
    #end = timer()
    #print(end - start) # Time in seconds, e.g. 5.38091952400282
    #print(len(template2))