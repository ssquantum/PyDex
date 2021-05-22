"""
Vincent Brooks 17/05/2021
Additional function for rearrangment. Tidier to have them in this sub-script and import

Functions:
    fstring: converts a list of frequencies (floats) into a string, e.g [160.,170.,180.] -> '012'
    flist: inverse of fstring: given string of occupancies '0124', slice and return initial/target array 
    convertBinartOccupancy: convert a string e.g. 01011 from PyDex into a string of occupied sites, e.g. '134'
"""


def fstring(self, freqs):
    """Convert a list [150, 160, 170]~MHz to '012' """
    idxs = [a for (a, b) in enumerate(freqs)]   
    return("".join([str(int) for int in idxs]) )
    
def flist(self, fstring, freq_list):
    """Given a string of e.g. '0123' and an array (initial/target), convert this to a list of freqs
        Args: 
            fstring   - string of integer numbers from 0 to 9 in ascending order.
            freq_list - array of freqs (either initial or target) which get sliced depending on fstring supplied
                
        e.g. if fstring = 0134 and freq_list = [190.,180.,170.,160.,150.],
            will return [190.,180.,160.,150.]
        
        """
    idxs = [int(i) for i in list(fstring)]
    
    return [freq_list[k] for k in idxs]     #   returns list of frequencies

def convertBinaryOccupancy(self, occupancyStr = '11010'):
    """Convert the string of e.g 010101 received from pyDex image analysis to 
    a string of occupied sites """
    occupied = ''
    for i in range(len(occupancyStr)):  # convert string of e.g. '00101' to '13'
        if occupancyStr[i] == '1': 
            occupied += str(i)
    if occupied == '':    # deal with the case of zero atoms being loaded
        occupied += '0'
    
    return occupied
