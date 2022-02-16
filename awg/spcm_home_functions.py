import numpy as np
import math
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from scipy.interpolate import interp1d, RectBivariateSpline
from scipy.optimize import minimize
from collections import OrderedDict
import ctypes
import itertools
import sys
import time
import json
import os

def phase_adjust(N):
    """Minimise the crest factor analytically. See DOI 10.5755/j01.eie.23.2.18001 """
    phi = np.zeros(N)
    for i in range(N):
        phi[i] = -np.pi/2-np.pi*(i+1)**2/N
    phi = phi /np.pi * 180
    return(phi)    
    
def crest(phases, freqs=[85,87,89], dur=1, sampleRate=625, freqAmps=[1,1,1]):
    """Get the crest factor for data generated for a static trap"""
    y = static(freqs,1,1,dur,20,freqAmps,phases,False,False,sampleRate=sampleRate)
    return np.max(y)/np.sqrt(np.mean(y**2))
    
def crest_index(phi, phases, ind, freqs=[85,87,89], dur=1, sampleRate=625, freqAmps=[1,1,1]):
    phases[ind] = phi
    return crest(phases, freqs, dur, sampleRate, freqAmps)

def phase_minimise(freqs=[85,87,89], dur=1, sampleRate=625, freqAmps=[1]*3):
    """Numerically optimise the phases to reduce the crest factor"""
    if len(freqAmps) != len(freqs):
        freqAmps = [1]*len(freqs)
    # start by optimizing them all
    result = minimize(crest, phase_adjust(len(freqs)), args=(freqs, dur, sampleRate, freqAmps))
    phases = result.x
    for i in range(len(freqs)): # then one by one
        result = minimize(crest_index, phases[i], args=(phases,i,freqs,dur,sampleRate,freqAmps))
        phases[i] = result.x
    print('Minimiser succeeded.' if result.success else 'Minimiser failed')
    print(result.message)
    print('Minimiser result: ', result.fun)
    return phases
    

def RMS(signal):
    """Calculate the RMS of a signal"""
    rms = np.sqrt(np.sum(signal**2)/np.abs(len(signal)))
    #print(rms)
    return(rms)

def checkWaveformAmp(y):
    """ Function checks if waveform exceeds 280mV and warns user. Doesn't modify waveform. 
        Waveform is clipped to max value set in AWG hardware by awgHandler.setMaxOutput.
        The amplitude in BITS is up to 2^16/2 = 32768, corresponding to tot_amp set elsewhere.
    """
    y=y/((2**16)/2)*282
    peak = max([abs(max(y)), abs(min(y))])
    rms = RMS(y)
    if peak > 300 or rms > 200 :
        print('CLIP WARNING:')
        print('  Wave amp is '+str(round(peak, 1))+'/280 mV')
        print('   and RMS is '+str(round(rms, 1))+'/200 mV')
    return peak, rms

def adjuster (requested_freq,samplerate,memSamples):
    """
    This function corrects the requested frequency to account for the fractional number of 
    cycles the card can produce for a given memory sample.
    The function takes the value of the requested frequency in MHz.
    The values of samplerate and memSamples are directly taken from the setup code to avoid small errors.
    These are typically given in Hz and bytes respectively.
    """
    nCycles = np.round(requested_freq/samplerate*memSamples)
    newFreq = nCycles*samplerate/memSamples
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
    NOTE I THINK THIS INTEGRAL IS CALCULATED WRONG (RVB 29.07.21)
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
########################################################

def load_calibration(filename, fs = np.linspace(135,190,150), power = np.linspace(0,1,50)):
    """Convert saved diffraction efficiency data into a 2D freq/amp calibration"""
    with open(filename) as json_file:
        calFile = json.load(json_file) 
    contour_dict = OrderedDict(calFile["Power_calibration"]) # for flattening the diffraction efficiency curve: keep constant power as freq is changed
    for key in contour_dict.keys():
        try:
            contour_dict[key]['Calibration'] = interp1d(contour_dict[key]['Frequency (MHz)'], contour_dict[key]['RF Amplitude (mV)'])
        except Exception as e: print(e)
    
    def ampAdjuster1d(freq, optical_power):
        """Find closest optical power in the presaved dictionary of contours, 
        then use interpolation to get the RF amplitude at the given frequency"""
        i = np.argmin([abs(float(p) - optical_power) for p in contour_dict.keys()]) 
        key = list(contour_dict.keys())[i]
        y = np.array(contour_dict[key]['Calibration'](freq), ndmin=1) # return amplitude in mV to keep constant optical power
        if (np.size(y)==1 and y>280) or any(y > 280):
            print('WARNING: power calibration overflow: required power is > 280mV')
            y[y>280] = 280
        return y

    mv = np.zeros((len(power), len(fs)))
    for i, p in enumerate(power):
        try:
            mv[i] = ampAdjuster1d(fs, p)
        except Exception as e: print('Warning: could not create power calibration for %s\n'%p+str(e))
        
    return RectBivariateSpline(power, fs, mv)
    

importPath="Z:\\Tweezer\Experimental\\Setup and characterisation\\Settings and calibrations\\tweezer calibrations\\AWG calibrations\\"
importFile = "calFile_08.06.2021.txt"

with open(importPath+importFile) as json_file:
    calFile1 = json.load(json_file) 

cal_umPerMHz = calFile1["umPerMHz"]

cal2d = load_calibration(importPath+importFile)

def ampAdjuster2d(freqs, optical_power, cal=cal2d):
    """Sort the arguments into ascending order and then put back so that we can 
    use the 2D calibration"""
    if np.size(freqs) > 1: # interpolating frequency
        inds = np.argsort(freqs)
        f = freqs[inds]
        return cal(optical_power, f)[0][np.argsort(inds)]
    elif np.size(optical_power) > 1: # interpolating amplitude
        inds = np.argsort(optical_power)
        a = optical_power[inds]
        return cal(a, freqs)[:,0][np.argsort(inds)]
    else:
        return cal(optical_power, freqs)[0]

def getFrequencies(action,*args):
    
    if action ==1 or action>=3:
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
        return 0
        
    Samplerounding = 1024 # Reference number of samples
    memBytes = round(sampleRate * (duration*10**-3)/Samplerounding) #number of bytes as a multiple of kB
        
    if memBytes <1:
        memBytes =1
        
    numOfSamples = int(memBytes*Samplerounding) # number of samples
    
    if action ==1 or action==3 or action==5:
    
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
    

def moving(startFreq, endFreq,duration,a,tot_amp,startAmp,endAmp,freq_phase,
        freq_adjust,amp_adjust,sampleRate, cal=cal2d):
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
    
    if len(freq_phase) != l:
        freq_phase = [0]*l
        print("Number of set phases do no match the number of frequencies. All individual phases have been set to 0. ")

    ##########################
    # Generate the data 
    ##########################   
    if amp_adjust:
        amp_ramp = np.array([ampAdjuster2d(sfreq[Y]*1e-6 + hybridJerk(t, 1e-6*rfreq[Y], numOfSamples, a), startAmp[Y], cal=cal) for Y in range(l)])
        s = np.sum(amp_ramp, axis=0)
        if any(s > 280):
            print('WARNING: multiple moving traps power overflow: total required power is > 280mV, peak is: '+str(round(max(s),2))+'mV')
            amp_ramp = np.ones(l)/l*tot_amp
    else: # nmt amp adjust
        if np.sum(tot_amp*np.array(startAmp)) > 280:
            print('WARNING: startAmp power overflow: total required power is > 280mV, is:'+str(np.sum(tot_amp*startAmp))+'mV')
            startAmp = np.ones(l) / l
        if np.sum(tot_amp*np.array(endAmp)) > 280:
            print('WARNING: startAmp power overflow: total required power is > 280mV, is:'+str(np.sum(tot_amp*endAmp))+'mV')
            endAmp = np.ones(l) / l
    
        amp_ramp = tot_amp*np.array([(1.*startAmp[Y] + (1.*endAmp[Y] - 1.*startAmp[Y])*t/numOfSamples) for Y in range(l)])
    
    if all(startAmp[i]-endAmp[i]<0.01 for i in range(l)) and a==1:
        # not ramping amplitude, just sweeping frequency linearly
        y = 1./282 *0.5*2**16 *np.sum([amp_ramp[Y]* 
            np.sin(2*math.pi*(sfreq[Y]/sampleRate*t + 0.5*(rfreq[Y])/sampleRate/numOfSamples*t**2) 
            + freq_phase[Y]) for Y in range(l)], axis=0)

    elif all(startAmp[i]-endAmp[i]<0.01 for i in range(l)):
        # not ramping amplitude, just sweeping frequency
        y = 1./282*0.5*2**16  *np.sum([amp_ramp[Y]* 
            np.sin(2*math.pi*(sfreq[Y]/sampleRate*t + np.cumsum(hybridJerk(t, rfreq[Y]/sampleRate, numOfSamples, a))) # np.cumsum is integral of hybridjerk
            + freq_phase[Y]) for Y in range(l)], axis=0)

    elif amp_adjust:
        # take samples across the diffraction efficiency curve and then interpolate
        idxs = np.linspace(0, len(t)-1, 100).astype(int)
        amp_ramp_adjusted = []
        for Y in range(l):
            traj = hybridJerk(idxs, rfreq[Y]*1e-6, numOfSamples, a)
            amp_ramp_adjusted.append(interp1d(idxs, 
                np.concatenate([ampAdjuster2d(sfreq[Y]*1e-6 + traj[i], amp_ramp[Y][i]/tot_amp, cal=cal)
                    for i in range(100)]), kind='linear'))

        y = 1./282*0.5*2**16 *np.sum([
            amp_ramp_adjusted[Y](t) * 
            np.sin(2*math.pi*(sfreq[Y]/sampleRate*t + np.cumsum(hybridJerk(t, rfreq[Y]/sampleRate, numOfSamples, a)))
            + freq_phase[Y]) for Y in range(l)], axis=0) 
            
    else: # Hybrid/Minimum jerk
        y  = 1./282*0.5*2**16 *np.sum([amp_ramp[Y]*
            np.sin(2.*math.pi*(1.*sfreq[Y]/sampleRate*t +\
            np.cumsum(hybridJerk(1.*t,1.*(rfreq[Y])/sampleRate,1.*numOfSamples,1.*a))) \
            +freq_phase[Y]) for Y in range(l)],axis=0)

    return y  




def static(centralFreq=170*10**6,numberOfTraps=4,distance=0.329*5,duration = 0.1,tot_amp=10,freq_amp = [1],freq_phase=[0],freqAdjust=True,ampAdjust=True,sampleRate = 625*10**6,umPerMHz =cal_umPerMHz, cal=cal2d):
    """
    centralFreq   : Defined in [MHz]. Accepts int/float/list/numpy.arrays()
    numberOfTraps : Defines the total number of traps including the central frequency.
    distance      : Defines the relative distance between each of the trap in [MICROmeters]. Can accept negative values.
    duration      : Defines the duration of the static trap in [MILLIseconds]. The actual duration is handled by the number of loops.
    tot_amp       : Defines the global amplitude of the sine waves [mV]
    freq_amp      : Defines the individual frequency amplitude as a fraction of the global (ranging from 0 to 1).
    freq_phase    : Defines the individual frequency phase in degrees [deg].
    freqAdjust    : On/Off switch for whether the frequency should be adjusted to full number of cycles [Bool].
    ampAdjust     : Toggle whether to apply a calibration to correct for diffraction efficiency
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
        amps = [ampAdjuster2d(freqs[Y]*10**-6, freq_amp[Y], cal=cal) for Y in range(numberOfTraps)]
        y = 1./282*0.5*2**16*np.sum([amps[Y]*np.sin(2.*np.pi*t*adjFreqs[Y]/sampleRate+ 2*np.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)],axis=0)
        peak, rms = checkWaveformAmp(y)
        # check that the waveform RMS doesn't exceed 200 or the peak amp doesnt exceed 300mV.
        if peak > 300 or rms>200:
            print(' ### Freq amps have been set to '+str(round(1/len(freqs),3)))
            amps = [ampAdjuster2d(freqs[Y]*10**-6, 1/len(freqs), cal=cal) for Y in range(numberOfTraps)]
            y =  1.*tot_amp/282/len(freqs)*0.5*2**16*np.sum([amps[Y]*np.sin(2.*np.pi*t*adjFreqs[Y]/sampleRate+ 2*np.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)],axis=0)

    else:  ### should static trap divide by number of traps?
        y = 1.*tot_amp/282/len(freqs)*0.5*2**16*np.sum([freq_amp[Y]*np.sin(2.*np.pi*t*adjFreqs[Y]/sampleRate+ 2*np.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)],axis=0)
    
    #checkWaveformAmp(y)
    return(y)

def ramp(freqs=[170e6],numberOfTraps=4,distance=0.329*5,duration =0.1,tot_amp=220,startAmp=[1],endAmp=[0],freq_phase=[0],freqAdjust=True,ampAdjust=True,sampleRate = 625*10**6,umPerMHz =cal_umPerMHz, cal=cal2d):
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
    if ampAdjust:
        y = 1./282*0.5*2**16*\
            np.sum([ampAdjuster2d(adjFreqs[Y]*1e-6, np.linspace(startAmp[Y], endAmp[Y], numOfSamples), cal=cal) * 
                np.sin(2.*np.pi*t*adjFreqs[Y]/sampleRate + 2*np.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)],axis=0)
    else:
        y = 1.*tot_amp/282/len(freqs)*0.5*2**16*\
            np.sum([(1.*startAmp[Y] + (1.*endAmp[Y] - 1.*startAmp[Y])*t/numOfSamples) * 
                np.sin(2.*np.pi*t*adjFreqs[Y]/sampleRate + 2*np.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)],axis=0)
    
    return y


def ampModulation(centralFreq=170*10**6,numberOfTraps=4,distance=0.329*5,duration = 0.1,tot_amp=10,freq_amp = [1],mod_freq=100e3,mod_depth=0.2,freq_phase=[0],freqAdjust=True,ampAdjust=True,sampleRate = 625*10**6,umPerMHz =cal_umPerMHz, cal=cal2d):
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
        if (np.size(mod_amp)==1 and mod_amp>1) or any(mod_amp > 1):
            print('WARNING: power calibration overflow: cannot exceed freq_amp > 1')
        return 1./282*0.5*2**16*np.sum([
            ampAdjuster2d(freqs[Y]*10**-6, freq_amp[Y]*(1 + mod_amp), cal=cal
            )*np.sin(2.*np.pi*t*adjFreqs[Y]/sampleRate + 2*np.pi*freq_phase[Y]/360.) for Y in range(numberOfTraps)],axis=0)
    else:
       return 1.*tot_amp/282/len(freqs)*0.5*2**16*np.sum([freq_amp[Y]*(1+mod_amp)*np.sin(2.*np.pi*t*adjFreqs[Y]/sampleRate+ 2*np.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)],axis=0)
    
def switch(centralFreq=170*10**6,numberOfTraps=4,distance=0.329*5,duration=0.1,offt=0.01,tot_amp=10,freq_amp=[1],freq_phase=[0],freqAdjust=True,ampAdjust=True,sampleRate=625*10**6,umPerMHz=cal_umPerMHz,cal=cal2d):
    """
    centralFreq   : Defined in [MHz]. Accepts int/float/list/numpy.arrays()
    numberOfTraps : Defines the total number of traps including the central frequency.
    distance      : Defines the relative distance between each of the trap in [MICROmeters]. Can accept negative values.
    duration      : Defines the duration of the static trap in [MILLIseconds]. The actual duration is handled by the number of loops.
    offt          : Defines the duration for which the trap is off in [MICROseconds]. Should be < duration.
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
    duty = 1-(offt*1e-3/duration) # fraction of duration with trap off
    if duty > 1: duty = 1   # must be between 0 - 1 
    elif duty < 0: duty = 0
    t0 = np.arange(int(duty*0.5*numOfSamples)+1) # initial on period
    t1 = np.arange(int((1-duty*0.5)*numOfSamples), numOfSamples) # final on period
    if ampAdjust ==True:
        try:
            return 1./282*0.5*2**16 * np.concatenate((
                np.sum([ampAdjuster2d(freqs[Y]*10**-6, freq_amp[Y], cal=cal)*np.sin(2.*np.pi*t0*adjFreqs[Y]/sampleRate+ 2*np.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)],axis=0),
                np.zeros(numOfSamples - len(t0) - len(t1)),
                np.sum([ampAdjuster2d(freqs[Y]*10**-6, freq_amp[Y], cal=cal)*np.sin(2.*np.pi*t1*adjFreqs[Y]/sampleRate+ 2*np.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)],axis=0)))
        except ValueError: # if off time = 0
            return 1./282/len(freqs)*0.5*2**16 * np.sum([ampAdjuster2d(freqs[Y]*10**-6, freq_amp[Y], cal=cal)*np.sin(2.*np.pi*np.arange(numOfSamples)*adjFreqs[Y]/sampleRate+ 2*np.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)],axis=0)
    else:
        try: 
            return 1.*tot_amp/282/len(freqs)*0.5*2**16 * np.concatenate((
                np.sum([freq_amp[Y]*np.sin(2.*np.pi*t0*adjFreqs[Y]/sampleRate+ 2*np.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)],axis=0),
                np.zeros(numOfSamples - len(t0) - len(t1)),
                np.sum([freq_amp[Y]*np.sin(2.*np.pi*t1*adjFreqs[Y]/sampleRate+ 2*np.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)],axis=0)))
        except ValueError: # if off time = 0
            return 1./282/len(freqs)*0.5*2**16 * np.sum([freq_amp[Y]*np.sin(2.*np.pi*np.arange(numOfSamples)*adjFreqs[Y]/sampleRate+ 2*np.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)],axis=0)


def sine_offset(mod_freq=170*10**3,duration = 0.1,dc_offset=100,mod_amp=10,sampleRate = 625*10**6):
    """
    mod_freq      : Defined in [kHz]. float value
    duration      : Defines the duration of the static trap in [MILLIseconds]. The actual duration is handled by the number of loops.
    dc_offset     : Amplitude [mV] to modulate around
    mod_amp       : Defines the global amplitude of the sine waves, fraction of DC offset
    sampleRate    : Defines the sample rate by which the data will read [in Hz].
    """
    memBytes = round(sampleRate * (duration*10**-3)/1024) #number of bytes as a multiple of kB
    if memBytes <1:
        memBytes =1
    numOfSamples = int(memBytes*1024) # number of samples    
    t = 2.*np.pi*np.arange(numOfSamples)/sampleRate
    return dc_offset/282.*0.5*2**16 * (1 + mod_amp*np.sin(t*mod_freq))

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

def lenCheck(*args):
    """
    Accepts a set of lists or arrays and test that all arguments have the same length.
    """

    return all(len(args[0])==len(args[x]) for x in range(0,len(args)))
    
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
    """
    FFT plot of the selected action function.
    """
    
    ##fft
    #plt.figure()
    #plt.plot(np.fft.fftfreq(len(r), 1/625e6), np.fft.fft(r))
    
    
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

    # y = moving(135e6, 195e6, 0.1, 1, 220, [1],[1],[0],False,False,625e6)
    # plt.plot(np.fft.fftfreq(np.size(y), 1/625), np.fft.fft(y), label='135 -> 195MHz')
    # plt.xlabel('Frequency (MHz)')
    # y = moving(195e6, 135e6, 0.1, 1, 220, [1],[1],[0],False,False,625e6)
    # plt.plot(np.fft.fftfreq(np.size(y), 1/625), np.fft.fft(y), label='195 -> 135 MHz')
    # plt.legend()
    # plt.show()
    
    dur = 0.1
    y1 = static(100e6,1,0.1,dur,200,[1],[0],False,True,sampleRate = 625*10**6,umPerMHz =cal_umPerMHz)
    y2 = static(100.01e6,1,0.1,dur,200,[1],[0],False,True,sampleRate = 625*10**6,umPerMHz =cal_umPerMHz)
    plt.plot(np.fft.fftfreq(np.size(y1), 1/625), np.fft.fft(y1), label='100 MHz')
    plt.plot(np.fft.fftfreq(np.size(y2), 1/625), np.fft.fft(y2), label='100.01 MHz')
    plt.xlabel('Frequency (MHz)')
    plt.show()