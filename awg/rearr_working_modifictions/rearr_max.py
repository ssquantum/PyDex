"""
17/05/2021
Test script for rearrangement function where instead of 

"""

from itertools import combinations   # returns tuple of combinations
from scipy.special import comb      # calculates value of nCr

class rearrange():
    def __init__(self):
        self.initial_freqs = [190, 180, 170, 140, 120]
        self.target_freqs = [190, 180, 170, 140, 130]
        self.movesDict = {}
        self.segmentCounter = 0

    def fstring(self, freqs):
        """Convert a list [170., 160., 150. ]~MHz to a string '012' 
           Args:
              freqs  -  list of frequencies
        """
        idxs = [a for (a, b) in enumerate(freqs)]   
        return("".join([str(int) for int in idxs]) )
    
    def flist(self, fstring, array='initial'):
        """Given a string of e.g. '0123' and an array (initial/target), convert this to a list of freqs
           Args: 
               fstring  - string of integer numbers from 0 to 9 in ascending order.
               array    - either 'initial' or 'target' so that it knows which frequency list to slice.
                  
           e.g. if fstring = 0134 and self.initial_freqs = [190.,180.,170.,160.,150.],
                will return [190.,180.,160.,150.]
           
            """
        idxs = [int(i) for i in list(fstring)]
        
        if array == 'target':
            fs = self.target_freqs 
        else:
            fs = self.initial_freqs
        
        return [fs[k] for k in idxs]     #   returns list of frequencies

    def calculateAllMoves(self):
        """Given the initial and target frequencies, calculate all the possible moves
            from start array to target array"""
        
        
        start_key = self.fstring(self.initial_freqs) # Static array at initial trap freqs 
        #self.createRearrSegment(start_key+'si')
        
        req_n_segs = 10
        for j in range(len(start_key)):
            nloaded = len(start_key)-j
            c = comb(len(start_key), nloaded)
            print(nloaded, c)
            req_n_segs += c + 1
        print(req_n_segs)

        for j in range(len(start_key)):
            
            nloaded = len(start_key)-j    # if rearrMode = EXACT, nloaded = self.len(target_freqs) ??? 
            
            end_key = self.fstring(self.target_freqs[:j+1])  # Static array at target trap freqs
            self.createRearrSegment(end_key+'st')
            
            for x in combinations(start_key, nloaded):   #  for each of the possible number of traps being loaded
               # print(x, self.fstring([1]*nloaded))      # Calculate moves to go from e.g. 3 loaded -> 3 loaded, 2 loaded -> 2 loaded etc. 
                self.createRearrSegment(''.join(x)+'m'+''.join(self.fstring([1]*nloaded)))
                pass
        print(self.segmentCounter)
        
                
      #  for key, value in self.movesDict.items():
       #     print(value, ' : ', key)
   
    def createRearrSegment(self, key):
        if 's' in key:
            
            if 'si' in key:                # Initial array of static traps
                fs = self.flist(key.partition('s')[0], 'initial')
            elif 'st' in key:              # Target array of static traps
                fs = self.flist(key.partition('s')[0], 'target')
        
        elif 'm' in key: # Move from initial array to target array of static traps
            
            f1 = self.flist(key.partition('m')[0], 'initial')
            f2 = self.flist(key.partition('m')[2], 'target')
            print(key.partition('m'))

                
        
        self.movesDict[key] = self.segmentCounter
        self.segmentCounter+=1
        

            
                        
                                                
if __name__ == '__main__':
    r = rearrange()
    r.calculateAllMoves()
    
    
    
    
    
    
    
    
    
    
    