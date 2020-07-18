import numpy as np
import math
from math import sin
from math import pi
import matplotlib.pyplot as plt

from pyspcm import *
from spcm_tools import *
from spcm_home_functions import *
import sys
import time
import json



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
    return d*(10*(t/T)**3 - 15*(t/T)**4 + 6*(t/T)**5)

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
    if(a==1):
        return d/T*t
    else:
        if(0<=t<=0.5*T*(1.-a)):
            return minJerk(t,2*d/(2+15./4.*a/(1-a)),T*(1-a))
        
        if(0.5*T*(1-a)< t <T-0.5*T*(1-a)):
            return 15.*d/(8*T + 7*T*a)*t + 7*d*(a-1)/(2.*(8+7*a))
        
        if(T-0.5*T*(1.-a)<=t<=T):
            return minJerk(t-(T-T*(1-a)), 2.*d/(2+15./4*a/(1 - a)), T*(1 - a)) + a*T*15./8*8*d/(8*T + 7*T*a)


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
    if(0<=t<=0.5*T*(1.-a)):
        return (8.*d*(t**6 + 3*t**5.*T*(a-1.) +5./2*T**2 * t**4 * (a-1.)**2))/(1.*T**5 * (a-1.)**4 * (8.+7.*a))
    if(0.5*T*(1.-a)< t <T-0.5*T*(1.-a)):
        return 0.5*d*t/(8.+7.*a)*(-7.+7.*a +15./T * t)
    if(T-0.5*T*(1.-a)<=t<=T):
        return 1.*d/(T**5 * (a-1.)**4 * (8.+7.*a))*\
        (8.*t**6 + 120.*t**2 * T**4 * a**2 - 24.* t**5 * T* (1.+a) - \
        80.* t**3 * T**3 *a*(1.+a) +20.*t**4 * T**2 * (1.+4.*a+a**2) + \
        1.*t * T**5 * a *(15.-60.*a +10.*a**2-20.*a**3 + 7.*a**4))
        
        
def moving_old(startFreq, endFreq,sampleRate,duration,a):
    """
    This function applies a chirp on a standard sine function. 
    If a=1, it will perform a linear sweep.
    Otherwise it will perform a hybrid-trajectory (min-jerk + linear).
    The distinction is important because the hybrid-jerk function cannot smoothly transition from hybrid to
    fully linear. 
    The chirp component is introduced as the chirp function shown earlier.
    startFreq  : Initial frequency in Hz
    endFreq    : Final frequency in Hz
    sampleRate : sample rate in Samples per second
    a          : percentage of trajectory being minimum jerk (a=0 is 100% minimum jerk, a=1 is fully linear motion.
    """
    memBytes = math.ceil(sampleRate * (duration*10**-3)/1024) #number of bytes as a multiple of kB
    numOfSamples = memBytes*1024 # number of samples
    t = np.arange(0.,numOfSamples)  
    y = [] #Standard Sine function
    if(a==1):
        for i in range(len(t)):
            y.append(0.25*2**16 *math.sin(2.*math.pi*(1.*startFreq/sampleRate*t[i]+\
            0.5*(endFreq-startFreq)/sampleRate/numOfSamples*t[i]**2 )))
        return y
    else:
        for i in range(len(t)):
            y.append(0.25*2**16 *math.sin(2.*math.pi*(1.*startFreq/sampleRate*t[i]+\
            chirp(1.*t[i],1.*(endFreq-startFreq)/sampleRate,1.*numOfSamples,1.*a) )))
        return y
        
        
        
        
def moving(startFreq, endFreq,staticFreq,duration,a,tot_amp,freq_amp,freq_phase,freq_adjust,sampleRate):
    """
    Identical to the moving function above. The only difference is that it also applies the adjuster function
    to ensure that the starting and end frequencies are as close as possible to the frequencies needed
    to complete full cycles.
    startFreq  : Initial frequency in Hz
    endFreq    : Final frequency in Hz
    duration   : duration of chirp in ms. It automatically calculates the adequate number of samples needed. 
    a          : percentage of trajectory being minimum jerk (a=0 is 100% minimum jerk, a=1 is fully linear motion.
    tot_amp    : global amplitude control over all frequencies
    freq_amp   : list for individual amplitude control
    freq_phase : list for individual phase control
    freq_adjust: Boolean for frequency correction
    
    sampleRate : sample rate in Samples per second
    """
    Samplerounding = 1024
    
    memBytes = math.ceil(sampleRate * (duration*10**-3)/Samplerounding) #number of bytes as a multiple of kB
    numOfSamples = memBytes*1024 # number of samples
    
    if freq_adjust == True:
        sfreq    = adjuster(startFreq,sampleRate,numOfSamples)
        ffreq    = adjuster(endFreq,sampleRate,numOfSamples)
        rfreq    = adjuster((ffreq-sfreq),sampleRate,numOfSamples)
        statfreq = adjuster(staticFreq,sampleRate,numOfSamples)
    else:
        sfreq    = startFreq
        ffreq    = endFreq
        rfreq    = (ffreq-sfreq)
        statfreq = staticFreq
      
    y = [] #Standard Sine function
    if(a==1):
        for i in range(numOfSamples):
            y.append(tot_amp/282*0.25*2**16 *(freq_amp[0]*math.sin(2.*math.pi*(1.*sfreq/sampleRate*i+\
            0.5*(rfreq)/sampleRate/numOfSamples*i**2)+freq_phase[0]) + freq_amp[1]*math.sin(2.*math.pi*(i)*statfreq/sampleRate+freq_phase[1]))) 
        return y
    else:
        for i in range(numOfSamples):
            y.append(0.25*2**16 *(math.sin(2.*math.pi*(1.*sfreq/sampleRate*i+\
            chirp(1.*i,1.*(rfreq)/sampleRate,1.*numOfSamples,1.*a) ))+math.sin(2.*math.pi*(i)*statfreq/sampleRate)))
        return y
        
def moving2(startFreqs, endFreqs, amps, a=1, duration=110, totAmp=220, phases=[], freqAdjust=True, sampleRate=625e6, rounding=1):
    """
    Sweep a list of frequencies from startFreqs to endFreqs. Can be linear or min jerk sweep.
    startFreqs  : Initial frequencies in Hz
    endFreqs    : Final frequency in Hz
    amps        : fractional amplitude for each frequency
    sampleRate  : sample rate in Samples per second
    duration    : duration of chirp in ms. It automatically calculates the adequate number of samples needed. 
    a           : percentage of trajectory being minimum jerk (a=0 is 100% minimum jerk, a=1 is fully linear motion.
    totAmp      : total combined peak amplitude [mV]
    freqAdjust  : whether to round the frequencies to try and make them complete a full number of cycles
    rounding    : round the samples to a certain number of bytes 
    """
    memBytes = round(sampleRate * (duration*10**-3)/rounding) #number of bytes as a multiple of kB
    numOfSamples = memBytes*rounding # number of samples
    nTraps = len(startFreqs)
    if len(phases) != nTraps:
      phases = [0]*nTraps
    if len(endFreqs) < nTraps:
        endFreqs += startFreqs[len(endFreqs):]
    if len(amps) < nTraps:
        amps += [1]*(nTraps - len(amps))
    if freqAdjust:
        startFreqs = adjuster(np.array(startFreqs),sampleRate,numOfSamples) # start 
        endFreqs = adjuster(np.array(endFreqs),sampleRate,numOfSamples)  # end
    
    stepFreqs = adjuster((startFreqs-endFreqs),sampleRate,numOfSamples) # step
    phases = 2*math.pi*np.array(phases)/360 # convert to radians
    
    y = [] #Standard Sine function
    if a == 1:
        for i in range(numOfSamples):
            y.append( totAmp/282 * 0.5*2**16 / nTraps * sum(
                amps[Y] * math.sin(
                    2.*math.pi*i*startFreqs[Y]/sampleRate + 0.5*stepFreqs[Y]/sampleRate/numOfSamples*i**2 + phases[Y]) 
                        for Y in range(nTraps)))
    else:
        for i in range(numOfSamples):
            y.append( totAmp/282 * 0.5*2**16 / nTraps * sum(
                amps[Y] * math.sin(
                    2.*math.pi*i*startFreqs[Y]/sampleRate + chirp(1.*i, 1.*stepFreqs[Y]/sampleRate, 1.*numOfSamples, 1.*a) + phases[Y])
                        for Y in range(nTraps)))
    return y
        
def static(centralFreq=170*10**6,numberOfTraps=4,distance=0.329*5,duration = 0.1,tot_amp=10,
    freq_amp = [1],freq_phase=[0],freqAdjust=True,sampleRate = 625*10**6,umPerMHz =0.329, rounding=1):
    """
    centralFreq     : Defined in [MHz]. Subsequent frequencies will appear in increasing order.
    numberOfTraps   : Defines the total number of traps including the central frequency.
    distance        : Defines the relative distance between each of the trap in [MICROmeters].
    duration        : Defines the duration of the static trap in [MILLIseconds]. The actual duration is handled by the number of loops.
    tot_amp         : combined peak amplitude [mV]
    freq_amp        : Creates a list of fractional amplitudes for each frequency/trap generated. 
    freq_phase      : List of phases constants for each frequency
    freqAdjust      : whether to adjust the frequencies to try and make them complete full cycles
    sampleRate      : number of samples processed per second
    umPerMHz        : conversion between distance atoms move in the cell and frequencies sent to AOD [microns / MHz]
    rounding        : round the number of samples to a certain number of bytes
    """
    adjFreqs, numOfSamples, numberOfTraps, separation = staticFreqs(centralFreq, numberOfTraps, distance, duration, freqAdjust, sampleRate, umPerMHz, rounding)
    
    # freq_amp, freq_phase, adjFreqs = map(np.array, [freq_amp, freq_phase, adjFreqs])
    # t = np.arange(numOfSamples)
    # return list(tot_amp/282/numberOfTraps*0.5*2**16 * np.sum(
    #       [freq_amp[Y]*math.sin(2.*math.pi*(i)*adjFreqs[Y]/sampleRate + 2*math.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)], axis=0))
    y = [] #Standard Sine function
    for i in range(numOfSamples):
        y.append(tot_amp/282/numberOfTraps*0.5*2**16*sum(freq_amp[Y]*math.sin(2.*math.pi*(i)*adjFreqs[Y]/sampleRate + 2*math.pi*freq_phase[Y]/360) for Y in range(numberOfTraps)))
    return y

def staticFreqs(centralFreq=170*10**6,numberOfTraps=4,distance=0.329*5,duration = 0.1,freqAdjust=True,sampleRate = 625*10**6,umPerMHz =0.329, rounding=1):
    """Get the frequencies used for static traps
    centralFreq     : Defined in [MHz]. Subsequent frequencies will appear in increasing order.
    numberOfTraps   : Defines the total number of traps including the central frequency.
    distance        : Defines the relative distance between each of the trap in [MICROmeters].
    duration        : Defines the duration of the static trap in [MILLIseconds]. The actual duration is handled by the number of loops.
    freqAdjust      : whether to adjust the frequencies to try and make them complete full cycles
    sampleRate      : number of samples processed per second
    umPerMHz        : conversion between distance atoms move in the cell and frequencies sent to AOD [microns / MHz]
    rounding        : round the number of samples to a certain number of bytes
    """
    if type(centralFreq)==list:
        freqs = centralFreq
        numberOfTraps = len(freqs)
    else:
        separation = distance/umPerMHz *10**6
        freqs = np.linspace(centralFreq,centralFreq+numberOfTraps*separation,numberOfTraps, endpoint=False)
    
    numOfSamples = rounding * round(sampleRate * (duration*10**-3) / rounding) #number of bytes as a multiple of kB
    if numOfSamples <1:
        numOfSamples = 1
        
    if freqAdjust == True:
        adjFreqs = np.zeros(numberOfTraps)
        for i, freq in enumerate(freqs):
            adjFreqs[i] = adjuster(freq,sampleRate,numOfSamples)
    else:
        adjFreqs = freqs
    
    return adjFreqs, numOfSamples, numberOfTraps, separation
    
def static2(centralFreq=170*10**6,numberOfTraps=4,distance=1.645,numOfSamples = 64*1024,sampleRate = 625*10**6,umPerMHz =0.329):
    """
    centralFreq   : Defined in [MHz]. Subsequent frequencies will appear in increasing order.
    numberOfTraps : Defines the total number of traps including the central frequency.
    distance      : Defines the relative distance between each of the trap in [MICROmeters].
    
    """
    separation = distance/umPerMHz *10**6
    freqs = np.arange(centralFreq,centralFreq+numberOfTraps*separation,separation)
    adjFreqs = []
    for freq in freqs:
         adjFreqs.append(adjuster(freq,sampleRate,numOfSamples))
    #print(adjFreqs) 
    y = [] #Standard Sine function
    for i in range(numOfSamples):
        y.append(1/len(freqs)*0.5*2**16*sum(math.sin(2.*math.pi*(i)*freq/sampleRate) for freq in adjFreqs))
    return y

def ramp(freq=170*10**6,freq2 =180*10**6,startAmp=1,endAmp=0,duration =0.1,sampleRate= 625*10**6):
    """
    freq     : Defined in [MHz]. Subsequent frequencies will appear in increasing order
    startAmp : 
    """
    memBytes = math.ceil(sampleRate * (duration*10**-3)/1024) #number of bytes as a multiple of kB
    numOfSamples = memBytes*1024 # number of samples
    
    adj  = adjuster(freq,sampleRate,numOfSamples)
    adj2 = adjuster(freq2,sampleRate,numOfSamples)
    y=[]
    for i in range(numOfSamples):
        #y.append(0.5*2**16*((startAmp + (endAmp - startAmp)/numOfSamples*i)*math.sin(2.*math.pi*(i)*adj/sampleRate)))
        y.append(220/282*0.25*2**16*((startAmp + (endAmp - startAmp)*i/numOfSamples)*math.sin(2.*math.pi*(i)*adj/sampleRate)+math.sin(2.*math.pi*(i)*adj2/sampleRate)))
    return y
    



# (centralFreq,numberOfTraps,distance.329*5,duration ,tot_amp,freq_amp = [1],freq_phase=[0],sampleRate = 625*10**6,umPerMHz =0.329)

if __name__ == "__main__":
   
    template = static(170e6,2,-8.5,0.02,220,[1,0],[0,0],True,625*10**6)
    # template   = moving(1, 10,10,1000,1,200,[1,0.1],[0,0],False,100)
    # template = moving2(170e6, 175e6,190e6,625e6,0.12,1)
    # template = ramp(200e6,freq2 =100*10**6,startAmp=1,endAmp=0,duration =0.2,sampleRate= 625*10**6)
    
    r = template 
    length = 1000 # len(r)
    
    fig1,axs = plt.subplots(2,1)
    axs[0].plot(np.arange(0,length),r[:length])
    #axs[0].set_ylim([-0.1,1.1])
    axs[0].set_xlabel("Number of Samples (First " +str(length)+ ")")
    axs[0].set_ylabel("Amplitude , arb")
    
    axs[1].plot(np.arange(0,length),r[-length:])
    axs[1].set_xlabel("Number of Samples (Last " +str(length)+ ")")
    axs[1].set_ylabel("Amplitude, arb")
    fig1.tight_layout(pad=3.0)
    
    ##fft
    plt.figure()
    plt.plot(np.fft.fftfreq(len(r), 1/625e6), np.fft.fft(r))
