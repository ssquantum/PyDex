"""Simple Thus EFficient ANalysers (STEFANs)
Dan Ruttley 2023-01-24
Code written to follow PEP8 conventions with max line length 120 characters.

STEFANs are simple plotters designed to allow for mid-experiment monitoring of
ROI statistics. Statistics are provided by the Multi Atom Image Analyser (MAIA)
but are processed in the STEFAN thread to prevent delay of image processing in
the MAIA. Statistics will only be reobtained and recalculated on-demand from 
the user to prevent lag.

A STEFAN is actually two seperate (but linked) classes:
    - STEFAN: the behind-the-scenes class which operates in a seperate thread.
              This class performs the analysis of data.
    - STEFANGUI: the interface presented to the user. This *must* run in the 
                 main program thread because it alters pyqt GUI elements.

A STEFANGUI object should be created and managed by the iGUI and the STEFANGUI 
will then create the corresponding background STEFAN thread. The iGUI and 
STEFANGUI will reside in the same thread so can communicate with normal 
Python code, but STEFANGUI <-> STEFAN communication must be entirely 
slot/signal based to ensure thread safety.
"""

