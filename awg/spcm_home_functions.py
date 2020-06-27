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
    nCycles = round(requested_freq/samplerate*memSamples)
    newFreq = round(nCycles*samplerate/memSamples)
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
        
        
def moving(startFreq, endFreq,sampleRate,duration,a):
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
        
        
        
        
def moving2(startFreq, endFreq,staticFreq,sampleRate,duration,a):
    """
    Identical to the moving function above. The only difference is that it also applies the adjuster function
    to ensure that the starting and end frequencies are as close as possible to the frequencies needed
    to complete full cycles.
    startFreq  : Initial frequency in Hz
    endFreq    : Final frequency in Hz
    sampleRate : sample rate in Samples per second
    duration   : duration of chirp in ms. It automatically calculates the adequate number of samples needed. 
    a          : percentage of trajectory being minimum jerk (a=0 is 100% minimum jerk, a=1 is fully linear motion.
    """
    memBytes = math.ceil(sampleRate * (duration*10**-3)/1024) #number of bytes as a multiple of kB
    numOfSamples = memBytes*1024 # number of samples
    sfreq=adjuster(startFreq,sampleRate,numOfSamples)
    ffreq =adjuster(endFreq,sampleRate,numOfSamples)
    rfreq=adjuster((ffreq-sfreq),sampleRate,numOfSamples)
    statfreq = adjuster(staticFreq,sampleRate,numOfSamples)

      
    y = [] #Standard Sine function
    if(a==1):
        for i in range(numOfSamples):
            y.append(0.25*2**16 *(math.sin(2.*math.pi*(1.*sfreq/sampleRate*i+\
            0.5*(rfreq)/sampleRate/numOfSamples*i**2 ))+math.sin(2.*math.pi*(i)*statfreq/sampleRate)))
        return y
    else:
        for i in range(numOfSamples):
            y.append(0.25*2**16 *(math.sin(2.*math.pi*(1.*sfreq/sampleRate*i+\
            chirp(1.*i,1.*(rfreq)/sampleRate,1.*numOfSamples,1.*a) ))+math.sin(2.*math.pi*(i)*statfreq/sampleRate)))
        return y
        
def moving3(startFreq, endFreq,sampleRate,numOfSamples,a):
    """
    Identical to the moving function moving2. The difference being that it accepts number of samples rather than duration.
    startFreq    : Initial frequency in Hz
    endFreq      : Final frequency in Hz
    sampleRate   : sample rate in Samples per second
    numOfSamples : number of samples to be used for the full trajectory.
    a            : percentage of trajectory being minimum jerk (a=0 is 100% minimum jerk, a=1 is fully linear motion.
    """

    sfreq=adjuster(startFreq,sampleRate,numOfSamples)       # adjusted starting frequency
    ffreq =adjuster(endFreq,sampleRate,numOfSamples)        # adjusted end frequency
    rfreq=adjuster((ffreq-sfreq),sampleRate,numOfSamples)   # adjusted relative frequency

    t = np.arange(0.,numOfSamples)  
    y = [] #Standard Sine function
    if(a==1):
        for i in range(len(t)):
            y.append(0.25*2**16 *math.sin(2.*math.pi*(1.*sfreq/sampleRate*t[i]+\
            0.5*(rfreq)/sampleRate/numOfSamples*t[i]**2 )))
        return y
    else:
        for i in range(len(t)):
            y.append(0.25*2**16 *math.sin(2.*math.pi*(1.*sfreq/sampleRate*t[i]+\
            chirp(1.*t[i],1.*(rfreq)/sampleRate,1.*numOfSamples,1.*a) )))
        return y  
        
def static(centralFreq=170*10**6,numberOfTraps=4,distance=1.645,duration = 0.1,sampleRate = 625*10**6,umPerMHz =0.329):
    """
    centralFreq   : Defined in [MHz]. Subsequent frequencies will appear in increasing order.
    numberOfTraps : Defines the total number of traps including the central frequency.
    distance      : Defines the relative distance between each of the trap in [MICROmeters].
    
    """
    separation = distance/umPerMHz *10**6
    freqs = np.arange(centralFreq,centralFreq+numberOfTraps*separation,separation)
    #freqs = [170*10**6,175*10**6,180*10**6,185*10**6]
    #print(freqs)
    memBytes = math.floor(sampleRate * (duration*10**-3)/1024) #number of bytes as a multiple of kB
    numOfSamples = memBytes*1024 # number of samples
    adjFreqs = []
    for freq in freqs:
         adjFreqs.append(adjuster(freq,sampleRate,numOfSamples))
    #print(adjFreqs) 
    y = [] #Standard Sine function
    for i in range(numOfSamples):
        y.append(1/len(freqs)*0.5*2**16*sum(math.sin(2.*math.pi*(i)*freq/sampleRate) for freq in adjFreqs))
    return y
    
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
        y.append(0.25*2**16*((startAmp + (endAmp - startAmp)*i/numOfSamples)*math.sin(2.*math.pi*(i)*adj/sampleRate)+math.sin(2.*math.pi*(i)*adj2/sampleRate)))
    return y
    


"""
length = 100
fig1, ax1 = plt.subplots()
r=static(170*10**6,2,1.645,0.02)#ramp(100000,200000)#moving2(1, 200,100,10000,0.1,0)
ax1.plot(np.arange(0,length),r[:length])
fig1.show()

"""

    
       
    
        