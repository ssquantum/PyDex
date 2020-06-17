Basic operation
1. Run master.py (for example, by executing run_with_conda.bat).

2. Choose the number of images and number of ROIs in the 'Settings for Image Analysers' window.

3. Set up the parameters for a multirun in the 'Sequence Preview' window.

4. Run the experiment by choosing a command in the 'PyDex Master' window and pressing the go button.

## Description
A master python script manages independent modules for experimental control:
Each module is a Python class that inherits QThread. We use the PyQt signal/slot architecture with TCP communication so that each module can run independently and not hold the other up. 

Included modules:
- Master (master.py runid.py) (on the main thread)
	Initiates all of the modules and provides an interface to display their respective windows or adjust their settings. 

- Networking (networker.py client.py) (server runs on a separate thread, but some functions remain on the main thread)
	Communicates with DExTer: sending commands to run/load sequences and synchronise the run number at the start/end of every run.

- Andorcamera (cameraHandler.py) (runs a separate thread)
	Control the Andor iXon camera using AndorSDK. Initialise the camera with given acquisition settings. Set the camera running so that it takes acquisitions triggered by DExTer, and then emits the acquired image as an array to be processed and saved. 

- Saveimages (imsaver.py) (runs a separate thread)
	Python saves image files with a synchronised run number.

- Imageanalysis (settingsgui.py) (currently runs on main thread - will want to change this in the future. Perhaps run separate   program and communicate by TCP or file creation)
	Single atom image analysis: 1) create histograms, 2) analyse histograms, 3) control settings like the ROI and multirun across histogram producers, 4) check whether atoms were loaded in an ROI and emit a signal that can trigger the experiment

- Monitor (daqgui.py) (runs a separate program, communicates by TCP)
	Takes in the signal from a DAQ to monitor channels like beam powers. 

- Sequences and Multirun (sequencePreviewer.py) (on the main thread but is only really used when the experiment isn't running)
	Facilitate the creation of sequences for an experiment, choose parameters to create a multirun, design experiments that optimise common parameters

- Atom checker (atomChecker.py) (on the main thread, takes images in place of the image analysis)
	Create ROIs on an image and compare them to threshold. When all of the ROIs are occupied, send a trigger. The idea is that you could trigger the experiment once all of the tweezers are loaded.
	
### Master
A master script manages the independent modules:

- Initiates camera, image saver, image analysis, and sequences and passes them to the networking manager; runid

- Displays current run number and status

- Allows the user to check the status of the individual modules and display their windows

- Allows the user to choose commands to send to DExTer

Command	Description

*Run sequence* Execute the sequence that is currently loaded into DExTer once. Only one 'Run sequence' command can be queued at a time, so the 'Go' button will be disabled. If DExTer doesn't finish the run, then reset the TCP server to enable the 'Go' button again.

*Multirun run* Add the multirun parameters stated in the sequence previewer's 'Multirun' tab to a queue of multiruns. When DExTer receives this message, start the multirun by creating the directory and queueing up a list of load sequence/run sequence commands.
	
*Pause multirun* removes the queue of multirun commands waiting to be sent over TCP, so the multirun will pause after the next run. Also empties the queue of multiruns.

*Resume multirun* Recreates the list of load sequence/run sequence commands to pick up the multirun where it was left off.

*Cancel multirun* removes the queue of multirun commands and resets the counters keeping track of the multirun's progress. Also empties the queue of multiruns.

*TCP load sequence*	Sends the absolute path displayed in the 'DExTer sequence file' line edit to DExTer, which subsequently tries to load the sequence from that file location.

*TCP load sequence from string*	Sends the sequence displayed in the Sequence Previewer window to DExTer as an XML string to be loaded into DExTer.

*Cancel Python mode* Sends the text 'python mode off' to DExTer, which allows it to exit python mode and therefore unfreezes the GUI.

*Start acquisition*	Starts the camera acquisition. This is designed for unsync mode so that you can use the DExTer GUI but still receive and process images.

*Save DExTer sequence*	Tells DExTer to save the sequence that is currently displayed on its UI to an XML log file which is labelled with the current run number, dated, and time-stamped.

*Resync DExTer*	Send DExTer a message so that it can respond with the current run number.
		
- Upon receiving the return message from DExTer, Master interprets it and executes the appropriate function.
	- Note that using a message queue means some parameters could have changed by the time the command is executed.
	
- To run a sequence:

	- Initiates the camera acquisition (for several images in one sequence, assume they come chronologically)

		- If it's just a single run, tell DExTer to save the sequence in its sequence log 

	- Sends message to run sequence and receives current run number in return: set state as 'running'

	- Queue message 'TCP read' that will be sent when DExTer opens the connection after the sequence

	- DExTer triggers the camera to take an image (or several images if re-imaging)

	- The camera manager sends a signal with the image array to the image saver and to the image analysis

	- Image analysis processes the image, image saver saves the image (separate threads)

	- Send a signal of whether there was an atom or not and the image background level to monitor module (not yet implemented)

	- DExTer opens connection and receives 'TCP read' command to check that the run is finished: set state 'idle'


Module Communication
A modular architecture is employed whereby each part has a level of independence. The monitor and DExTer run as separate programs and communicate by TCP. The Master, Image Analysis, Sequences and Multirun, and Atom Checker all run on the main thread. Their scripts are imported into the Master which sets them going and passes data between them using the PyQt signal-slot architecture. The TCP Networker, Andor Camera, and Saving Images all run on separate threads initiated by the Master, and communicate by the PyQt signal-slot architecture. 

PyQt Signal-Slot Architecture
A signal is defined to have a certain data type. When the signal is emitted, it passes data between modules or functions. A signal is connected to a slot, which is a function or method that takes the data as its input. The power of signals and slots is in the PyQt event queue. When one function emits a signal, it releases responsibility and continue with another task. On the other hand, the slot is activated as soon as the signal is received. This means you don't have to poll the signal with a for loop or a while loop - the slot is triggered by the arrival of the signal. Common signals used in PyDex are user input; typing into a textbox or clicking a button. These are usually connected to slots that convert the input into the right data type and store it. The image acquired by the camera is also emitted as a signal, but the slots can be dynamically changed between Image Analysis and the Atom Checker.

## Networking 
TCP messages
To facilitate communication and data processing, fix TCP message format:
### Python -> LabVIEW:

- Enum: 4 bytes 32-bit integer. Enum for DExTer's producer-consumer loop

- Text length: 4 bytes 32-bit integer. Giving the length of the message to follow so that we know how many bytes to receive (up to 2^31).

- Text: string. the message 

### LabVIEW -> Python:

- DExTer run number: 4 byte 32-bit unsigned long integer 

- Message: A string of length up to buffer_size of bytes (default 1024)

	- DExTer echoes back the last python message. The master script responds to this message.

### TCP Communication for a DExTer run/multirun:

1. Python command: load sequence
	
	a. DExTer confirms sequence is loaded and returns run number.

2. Python internal: start acquisition
	
	a. Start the camera acquisition and give it time to initialise.
	
	b. Queue up commands telling DExTer to (1) save the sequence (2) run the sequence (3) confirm it's finished. In a multirun the sequences are only saved once by python at the very start of the multirun.
	
3. Python command: single run

	a. DExTer confirms run/multirun has started (set state 'running')

	b. Repeat for multirun
	
4. Python command: 'TCP read' with message 'run finished'
	
	a. DExTer confirms run/multirun has ended (set state 'idle')

### Server/client model:
Server hosted by the master python script. Pros and cons: 
	
\+ can queue up commands to send
	
\+ master can receive messages from modules at any time

\- master can't check status of module at any time because the module might be busy

\- the message received from DExTer is an echo of the message just sent, so a second command it required to check the progress
	
The time taken to send a TCP message depends on the size of the string sent. It is found that strings with length < 1455 characters take a minimum of 200ms to send. For lengths above 1455 characters, the time taken increases as a function of the string length. Therefore we choose a minimum string length of 2000 characters by padding short messages with zeros.

So synchronisation between the DExTer and Python run number is retained every time a message is sent. 
In between these synchronisation messages, PyDex will count the number of images received. The number of images per sequence is stated by the user, and it is assumed that this number of images will be received, then there will be another synchronisation message.
	
### Experimental sequence XML <-> dictionary

In order to edit sequences in python and LabVIEW, we choose the XML format that can be accessed by both and is clear to read.
Functions in the translator.py script allow to convert from XML to a python dictionary, which is much less verbose and much easier to edit.
In Python the sequence is stored in an ordered dictionary where the keys correspond to the names of the clusters/arrays in DExTer. Note: the fast digital channels are stored in lists of lists with shape (# steps, # channels), but the analogue channels are stored in transposed lists of dictionaries of lists with shape (# channels, {voltage:(# steps), ramp?:(# steps)})

## Andor camera
We use an Andor iXon Ultra 897 EMCCD (SN: 11707). It comes with Andor SDK written in C to control the camera. Python wrapper functions are found in AndorFunctions.py.
We use the SDK to create a basic operation of the camera:

- Create a cameraHandler.camera() instance to connect to the camera. This is a subclass of QThread so that the acquisition of the camera can run independently. Upon initialising:
	- Load the C functions from the Andor SDK
	- Connect to the camera over USB
	- Connect the SDK's driver event to a windows event - this notifies at different stages of acquisition.
	- Set the acquisition settings by loading in a config file (see config_README.txt)

- To take a series of images, call start(). Assuming that the camera is in 'run till abort' mode this will:
	- Start a camera acquisition, which primes the camera ready to trigger an exposure.
	- Waits until an exposure is completed (so it must run on a separate thread, otherwise it would be blocking)
	- Retrieves the latest image from the camera buffer (it shouldn't miss any, so there should only be one image in the buffer. This can be checked by calling EmptyBuffer()).
	- Emits the retrieved image as a numpy array.
	- This repeats until the Andor SDK function AbortAcquisition() is called, or an error means that the camera state is no longer 'DRV_ACQUIRING'.

- If you don’t want to use the 'run till abort' mode and are taking a known number of acquisitions, it may be easier to use the TakeAcquisitions() function.

- The SafeShutdown() function ensures that the camera state is safe before turning it off:
	- Temperature kept at the setpoint after turning it off
	- Shutter closed
	- EM gain reset (since high EM gains give ageing)
	- Reset windows event

- The recommended acquisition settings are:

| Setting |	Set value |	Meaning|
| ------ | ----| -------|
|Crop mode|	0	|off|
|Isolated crop mode type|	0	|Default: high speed|
|Read mode|	4|	Image|
|Acquisition mode|	5|	Run till abort
|Trigger mode	|7|	External exposure*
|Frame transfer	|0|	Off|
|Fast trigger	|0|	Off (only available for the external trigger mode)|

* Being in external exposure mode means that the external trigger pulse defines the start and the duration of the exposure. It also means that there are keep clean cycles between exposures, which reduces background.
	- With these settings the readout time (which defines the minimum possible time between taking exposures) is decided by the size of the ROI. It is therefore recommended to use the smallest ROI possible:

|ROI size|	Minimum duration between exposures (ms) (5MHz readout rate)|	Software-computed readout time (ms)|
|-------|---|------|
|32x32	|11| 	6.927|
|64x64	|15|	10.34|
|128x128	|22|	17.57|
|256x256	|36|	32.03|
|512x512|75|	60.96|
	
- To reduce noise on the acquired image, use:
    - Conventional mode, 0.08MHz readout rate, preamp gain setting 3
- Sometimes noise will be sacrificed for the sake of faster readout rate or larger signal:
		- EM gain mode, 5MHz readout rate, preamp gain setting 3, then apply EM gain as needed
	- See the separate document EMCCD_noise_summary.pdf for more details

Note that there is a time delay associated with changing the camera acquisition mode of up to 500ms. The camera will not respond to external triggers within this period of time.

### Save images

Save a numpy array to a file that is named with a timestap, file ID number (synchronised with the run number), and image ID number (denoting the order of images in the sequence).
The file name follows the syntax: (label)_(day month year)_(file #)_(Im #).asc
Load the directories of where to save files to from a config file.
This class inherits PyDexThread which itself inherits QThread. When the thread is started it runs like:

1. Check the queue for an image to save.
	- When an image is taken, it should be passed by pyqtSignal to the instance of the imsaver.event_handler() using the inherited add_item() function to append it at the end of the queue.
	
2. Process the image at the front of the queue.
	- Save it to a file with the appropriate name.
	
3. Loop continuously as long as the thread is running.
	- Stop the thread by calling the inherited close() function.

## Image Analysis: SAIA
Single atom image analysis: create histograms from collections to images, collect statistics from images and histograms.

- maingui.main_window(): GUI for a single histogram of a given ROI for a given image in a sequence

- reimage.reim_window(): GUI for calculating survival probability

- atomChecker.atom_window(): GUI for analysing when multiple ROIs in an image are loaded with atoms

- roiHandler.roi_handler(): make collections of ROIs and process images to determine if they contain atoms

- imageHandler.image_handler() inherits Analysis class: creates the histogram for a given ROI for a given image in the sequence.

- histoHandler.histo_handler() inherits Analysis class: for collections of histograms in a multirun that build up a plot.
	Fit a function to the histogram in order to determine statistics like the mean count, standard deviation, ratio of counts in each peak (loading probability), etc.


A generic Analysis class is used to standardise the structure that all analyses will take. It provides a structure of:

- Properties:
	- Stats (from an image or from a histogram) - stored as ordered dictionary of lists for clarity and speed.
	- Types (one for each stat) - stored as ordered dictionary for clarity.

- Methods:
	- Process (quickly take stats from a given image/histogram)
	- Save
	- Load 
	- Reset_arrays
	
A settings GUI controls the ROIs, bias offset, etc. for all instances. This main window manages all of the other analysis windows.

- Load previous settings from a default config file that is updated when the program is closed.

- Produce analysis windows for analysing images:

	- Main windows 

	- These receive a set image during a sequence and process the counts in a single ROI
	
		- A unique name is given to each main window to prevent overwriting files. By default this is set as:
			- ROI(ROI index).Im(image index).
			- ROI index is set for the first m windows, where m is the number of images per sequence. e.g. if 2 images are taken in a sequence, the first two main windows will be ROI0, then the two windows after that will be ROI1, etc.
			- Image index counts where the image comes in the sequence. e.g. if 2 images are taken in a sequence, they will be indexed as Im0 and Im1.

	- Re-image windows 

		- use the histograms from two main windows. If there was a count above threshold present in the first main window, then the corresponding image in the second main window (identified by file ID) is included in the re-image histogram.

- Allow the user to choose settings that apply to all analysis windows:
	
	Setting	Description
	
	*Number of images per run*	How many images will be taken in a single run of the experimental sequence.
	
	*Number of image analysers*	Number of main windows to open which will receive and process images.
	
	*Image indices for analysers*	List of comma-separated indices dictating which image is sent to which analyser, e.g. 0,0,1 would assign the first window Im0, second window also Im0, and the third window Im1.
	
	*Histogram indices for re-imaging*	List of semicolon-separated indices dictating which main windows the re-image windows will use, e.g. 0,1;2,3 would create two re-image windows. The first would use main windows 0 and 1, the second would use 2 and 3.
	Image size in pixels	The incoming image is expected to be a nxn array of this many pixels.
	
	*EMCCD bias offset*	The number of counts to subtract from all images to account for the bias offset.
	
	*User variable*	Sets the 'User variable' setting in all of the analysis windows, used for assigning the independent variable in a plot of histograms results.

- Reset the analysis windows and connect their signals to receive the appropriate images 

- Keep a default config file to load previous settings

- Provide a convenience button to fit, save, and reset the histograms in all analysis windows. Starts by fitting the main window histograms, then fitting and saving the re-image windows, then it can save and reset the main windows.


### Region of Interest (ROI)
Within one image we might want several ROIs if there are several atoms.
For the main windows we decide to have the same ROI for all images in a sequence. If a different ROI is required, then 1create another set of image analysis windows analysing the same images.
The ROI is defined by a mask applied to the image. The mask is an array with the same dimensions as the image containing elements with values between 0-1. For a square ROI this just sets the pixels outside of the ROI to zero. 
The integrated counts in an ROI are calculated by summing the values of the image multiplied by the mask.
The ROI can be chosen by:

- Typing the desired ROI centre and size into the table of ROIs in the Settings window

- Dragging the ROI displayed in the Settings window

- Setting all of the windows to use the same ROI as the first Analyser

- Choosing a square grid from the settings window:

	- Divide the area of the image equally between Analysers using it.
	- Factorise the area into a width and a height that are as close to square as possible.
	- Make a grid of these areas covering the image, and assign areas to the Analysers in turn.

- Choosing to fit 2D Gaussian masks to an image (probably wants to be an average image).

### Data format
An image from the camera is passed as a numpy array. We make sure not to edit the array in place as it might need to be processed by several analysers. For example, subtracting the bias offset from the array would affect all image analysers using that image, so instead a copy of the array is made by each image_handler.

Use lists to store the integrated counts and other statistics from a collection of images. Append another value for each image. This is the fastest method given that we can't fix the size of the list.

### Images
ASCII file with the first column as the row number 
Histograms 
csv with the first 3 rows as a header containing the last calculated fit and column headings 
Measure file
Text file with the first 3 rows as a header containing column headings, then rows are appended for each histogram saved.
Andor config settings
Text file with ordered rows for each setting
Image saving directory settings
Text file with text labels indicating each setting

### Monitor
The user can control: Number of input channels and their settings, acquisition duration, sample rate, trigger settings, digital or analogue?, channel to trigger from, trigger level for analogue, rising or falling edge, start/stop - whether to acquire when the trigger arrives.

Each channel requires:
*Virtual channel name* 	unique, set by DAQ, e.g. 'Dev1/ai0'	str

*Channel label*	Chosen by user, for display	str

*Analogue offset*	Allows different signals to be plotted together	float

*Voltage range*	Scale the input voltage range	enum

*Acquire?*	Whether to acquire from this channel	bool

*Plot?*	Whether to display this channel on the live plot	bool

Default settings are loaded from a local file 'daqconfig.dat' on start-up. The current settings are saved to this file when the program is closed.

### Setting	Explanation
Default 

*config_file*	The relative or absolute path for the config settings file	daqconfig.dat

*trace_file*	The name to give csv files storing the trace	DAQtrace.csv

*graph_file*	The name to give csv files storing the graph data	DAQgraph.csv

*save_dir*	The directory to save trace and graph csv files to	
*Working directory* n	
*Run number*	0
*Sample rate (kS/s)*	The sample rate to apply to DAQ acquisitions in units of kS/s	250

*Duration (ms)*	The time to acquire for in units of ms	500

*Trigger Channel*	The physical AI or DI channel to trigger off	Dev1/PFI0

*Trigger Level (V)*	If an analogue trigger is used, the voltage at which to trigger	1.0

*Trigger Edge*	Whether to trigger on the rising or falling edge	Rising

*channels*	A list of data for active channels: label, scale, offset, range, acquire?, plot?	()

A real-time updated plot of the most recent acquisition. You can zoom in on the axes using the mouse scroll wheel.
The trace data can be loaded from or saved to a csv file using the File menubar.

User defines a slice of the trace to select. 
When activated, record an average of the slice for each trace acquired and build up a plot.
This allows you to monitor fluctuations over several experimental runs.
The slice will be displayed in the trace tab so that it is clear which part of the trace is selected.
Each time a trace is taken, the data point stores: run number (synchronised with PyDex via TCP), mean value, standard deviation
In order to make sure that there are the same number of data points for each channel, when a new slice is added the previously recorded data will be discarded.
The data acquired by the DAQ is returned as a list of measurements, one for each channel.

The plan is that a trace will be saved as representative of a multirun. When PyDex starts a multirun it will send the commands to the monitor:
- Start a triggered acquisition task, a digital trigger from DExTer will be connected to a DAQ digital in.
- Trigger an acquisition for every experimental run in the multirun
- Every time a histogram is saved, save a representative trace to the multirun folder as DAQtrace.csv(and png?)
- Choose slices of the trace to take an average (e.g. tweezer power during imaging step). For each run, save the slice average and build up values. These will be displayed in the graph tab, and saved at the end of the multirun as DAQgraph.csv

## Sequences
DExTer sequences were originally stored in binary .seq files. Since these are inaccessible to Python, we choose .xml format instead. These can be converted to python dictionaries which are much simpler to edit, after several long functions reformatting the structure. A generic sequence has the format:

- ('Event list array in', ({'Event name', 'Routine specific event?', 'Event indices', 'Event path'})*number_of_events )

- ('Routine name in', ''),

- ('Routine description in', ''),

- ('Experimental sequence cluster in', 
		('Sequence header top', (header_cluster)*number_of_steps),
		('Fast digital names', ({'Hardware ID', 'Name'})*number_of_fast_digital_channels),
		('Fast digital channels', ((Bool)*number_of_fast_digital_channels)*number_of_steps),
		('Fast analogue names', ({'Hardware ID', 'Name'})*number_of_fast_analogue_channels),
		('Fast analogue array', (({'Voltage', 'Ramp?'})*number_of_steps)
												*number_of_fast_analogue_channels),
		('Sequence header middle', (header cluster)*number_of_steps),
		('Slow digital names', ({'Hardware ID', 'Name'})*number_of_slow_digital_channels),
		('Slow digital channels', ((Bool)*number_of_slow_digital_channels)*number_of_steps),
		('Slow analogue names', ({'Hardware ID', 'Name'})*number_of_slow_analogue_channels),
		('Slow analogue array', (({'Voltage', 'Ramp?'})*number_of_steps)
												*number_of_slow_analogue_channels))

Note that the order of indexing between digital and analogue channels is transposed.

- Translator
	- Converts sequences XML <-> python dictionary

- Sequence Previewer
	- Uses the translator to display a sequence.
	- Gives a GUI for creating a multirun from an array of variables

## Multirun 
A multirun is a series of runs, changing a list of variables in the sequence. The format is as follows:

- Load the base sequence into the sequence previewer

- Create a list of variables to change:

	- For all variables:
		- Variable label used to identify the multirun (what variable you're changing for the experiment)
		- Number of runs to omit before starting the histogram 
		- Number of runs in a histogram 
	
	- For each variable (a column in the table of values):
		- Type: 'Time step length' or 'Analogue channel'
		- List of time steps to change
		- Analogue type: 'Fast analogues' or 'Slow analogues' (*)
		- List of analogue channels to change (*)
		- List of variables to assign to the given channels in the given time steps, one for each run in the multirun.
	(*) only needed if the type is 'Analogue channel'

- You can change the end step that is used while the multirun is running. This allows you to make use of the ~100ms dead time while DExTer processes after a run. During the multirun the last time step will be taken from the text edit 'Running:', then after the multirun the last time step will be reset to the one in 'End:'.

- Check that the variables list is valid (no empty spots, number of rows is divisible by # omitted + # in hist)

- Start a multirun using the command from the master window. The number of runs per histogram in the multirun is given by the number of rows in the table of variables. The total number of runs is this multiplied by the number of repeats.

	- Create the sequences that will be used in the multirun. Save them to the measure folder along with the multirun parameters. Check if the measure has already been used (whether files will be overwritten when saving histograms).

	- Since there could be a queue of commands sent to DExTer, the master waits for confirmation before connecting the slots
		- Send a message 'start measure '… to confirm DExTer is ready to start the multirun

	- Load the last time step for running the multirun.

	- Queue up a list of commands:
		
		i. Send message to load the new sequence 
		
		ii. Send message to run the new sequence for the given number of omits and repeats
		
		iii. Save and reset the histogram
		
		iv. Repeat 

	- Before the final run, change the last time step to make sure the multirun ends on that step.

	- Send 'confirm last multirun run' command with 'TCP read' enum.

	- Send 'end multirun' command with 'TCP read' enum and receive the 'confirm last multirun run' message.

	- Save a multirun parameters file with the variable list and associated run numbers. Save the plot data from each of the image analysis windows. Reset the signals to show that the multirun has finished.

You can queue up multiruns: the parameters displayed in the multirun editor are saved to a list and to a file when the master window passes the command to run a multirun. You can use the display to create another multirun.


## Atom Checker
The aim of this window is to analyse images taken while loading optical tweezers and trigger an experiment to start when the desired number of ROIs have been filled.
This mode is enabled by toggling the "Run settings > Trigger on atoms loaded" option in the Master window.
For the trigger to work, the sequence must have a software trigger in it. In DExTer the software trigger is a digital trigger on channel 0.

- ROIs are defined by the following coordinates:
	xc	Central pixel along the horizontal axis of the image
	yc	Central pixel along the vertical axis of the image
	width	Size of the ROI along the horizontal axis
	height	Size of the ROI along the vertical axis
	threshold	The threshold in counts that distinguishes between atom or background in an image
	automatic	A toggle for whether the threshold should be specified by the user or set automatically

- An image is displayed with the ROIs, which can be dragged to change their position. Plots are displayed with the counts from previous images and the threshold that divides atom from background.

- When the experimental sequence starts and the atom checker is enabled, the camera acquisition is started. DExTer can then send a pulse sequence to the camera trigger to take images continuously. These are sent to the Atom Checker instead of Image Analysis.

	- When all of the ROIs in an image have counts above threshold, a signal is emitted. 

	- The signal triggers a TCP message telling DExTer to continue the sequence. When the message is confirmed, the subsequent images are sent to the Image Analysis instead of the Atom Checker.

	- The timeout gives the duration in seconds to check for atoms before triggering the experiment anyway. The default timeout of 0 waits indefinitely.
