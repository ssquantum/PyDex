"""Networking - Sequence Translator
Stefan Spence 13/10/19

 - Edit experimental sequences using python dictionaries
 - This is only faster than DExTer's GUI if you're editing 
multiple channels at the same time.
"""
import sys
from lxml import etree
sys.path.append('') # otherwise cwd isn't in sys.path 
from translator import translate, tdict

import time
t = translate()
t0 = time.time()
t.load_xml(r'Z:\Tweezer\Experimental Results\2022\January\11\Measure4\sequences\Measure4_2.xml')
t1 = time.time()

            
esc = t.get_esc() # shorthand
num_s = len(esc[tdict.get('Sequence header top')]) - 2 # total number of timesteps
total_duration = 0 # duration of sequence in ms
units = [1e-3, 1, 1e3]
for timestep in range(num_s):
    step = esc[2][timestep+2]
    unit = units[int(step[9][-1].text)]
    total_duration += eval(step[3][1].text) * unit
    
print('the sequence lasts ', total_duration, ' ms')
