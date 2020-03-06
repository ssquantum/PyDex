#### PyDex ####
Version 0.0
A master python script manages independent modules for experimental control:
A master python script manages independent modules for experimental control:

Each module is a Python class that inherits QThread. We use the PyQt signal/slot architecture with TCP communication so that each module can run independently and not hold the other up. 

Included modules:
	• Master (on the main thread)
	Initiates all of the modules and provides an interface to display their respective windows or adjust their settings. 
	• Networking (server runs on a separate thread, but some functions remain on the main thread)
	Communicates with DExTer: sending commands to run/load sequences and synchronise the run number at the start/end of every run.
	• Andorcamera (runs a separate thread)
	Control the Andor iXon camera using AndorSDK. Initialise the camera with given acquisition settings. Set the camera running so that it takes acquisitions triggered by DExTer, and then emits the acquired image as an array to be processed and saved. 
	• Saveimages (runs a separate thread)
	Python saves image files with a synchronised run number.
	• Imageanalysis (currently runs on main thread - will want to change this in the future. Perhaps run separate   program and communicate by TCP or file creation)
	Single atom image analysis: 1) create histograms, 2) analyse histograms, 3) control settings like the ROI and multirun across histogram producers, 4) emit signal of whether there was an atom or not to monitor, and 5) emit signal of the background outside the ROI
	• Monitor
	Takes in the signal from a DAQ to monitor channels like beam powers. Responds to signals of atom presence to and background level to guess if the lasers are still locked.
	• Sequences (on the main thread but is only really used when the experiment isn't running)
	Facilitate the creation of sequences for an experiment, choose parameters to create a multirun, design experiments that optimise common parameters
	
Master
A master script manages the independent modules:
	• Initiates camera, image saver, image analysis, and sequences and passes them to the networking manager; runid
	• Displays current run number and status
	• Allows the user to check the status of the individual modules and display their windows
	• Allows the user to choose commands to send to DExTer
	Command	Description
	Run sequence	execute the sequence that is currently loaded into DExTer once. Only one 'Run sequence' command can be queued at a time, so the 'Go' button will be disabled. If DExTer doesn't finish the run, then reset the TCP server to enable the 'Go' button again.
	Multirun run	execute the multirun using the parameters stated in the sequence previewer's 'Multirun' tab. This queues up a list of run commands
	Pause multirun	removes the queue of multirun commands waiting to be sent over TCP, so the multirun will pause after the next run
	Resume multirun	adds the queue of multirun commands back into the networker to be sent over TCP
	Cancel multirun	removes the queue of multirun commands and resets the counters so keeping track of the multirun's progress
	TCP load sequence	Sends the absolute path displayed in the 'DExTer sequence file' line edit to DExTer, which subsequently tries to load the sequence from that file location
	TCP load sequence from string	Sends the sequence displayed in the Sequence Previewer window to DExTer as an XML string to be loaded into DExTer
	Cancel Python mode	Sends the text 'python mode off' to DExTer, which allows it to exit python mode and therefore unfreezes the GUI
	Start acquisition	Starts the camera acquisition. This is designed for unsync mode so that you can use the DExTer GUI but still receive and process images
		
	• Upon receiving the return message from DExTer, Master interprets it and executes the appropriate function.
		○ Note that using a message queue means some parameters could have changed by the time the command is executed.
	• In a sequence:
		○ Initiates the camera acquisition (for several images in one sequence, assume they come chronologically)
		○ DExTer saves the sequence in its sequence log
		○ Sends message to run sequence and receives current run number in return: set state as 'running'
		○ Queue message 'TCP read' that will be sent when DExTer opens the connection after the sequence
		○ DExTer triggers the camera to take an image (or several images if re-imaging)
		○ The camera manager sends a signal with the image array to the image saver and to the image analysis
		○ Image analysis processes the image, image saver saves the image (separate threads)
		○ Send a signal of whether there was an atom or not and the image background level to monitor module (not yet implemented)
		○ DExTer opens connection and receives 'TCP read' command so that checks that run is finished: set state 'idle'

	
Networking 
TCP messages
To facilitate communication and data processing, fix TCP message format:
Python -> LabVIEW:
	• Enum: 4 bytes 32-bit integer. Enum for DExTer's producer-consumer loop
	• Text length: 4 bytes 32-bit integer. Giving the length of the message to follow so that we know how many bytes to receive (up to 2^31).
	• Text: string. the message 
LabVIEW -> Python:
	• DExTer run number: 4 byte 32-bit unsigned long integer 
	• Message: A string of length up to buffer_size of bytes (default 1024)
		○ DExTer echoes back the last python message

TCP Communication for a DExTer run/multirun:
	1. Python command: load sequence
		a. DExTer confirms sequence is loaded and returns run number.
		b. Python could save the sequence but DExTer already does, and we don’t need duplicates.
	2. Python internal: start acquisition
		a. Start the camera acquisition and give it time to initialise
	3. Python command: single run
		a. DExTer confirms run/multirun has started (set state 'running')
		b. Repeat for multirun
	4. Python command: 'TCP read' with message 'run finished'
		a. DExTer confirms run/multirun has ended (set state 'idle')

Server/client model:
Server hosted by the master python script:
	+ can queue up commands to send
	+ master can receive messages from modules at any time
	- master can't check status of module at any time because the module might be busy
	- the message received from DExTer is an echo of the message just sent, so a second command it required to check the progress
	
The time taken to send a TCP message depends on the size of the string sent. It is found that strings with length < 1455 characters take a minimum of 200ms to send. For lengths above 1455 characters, the time taken increases as a function of the string length. Therefore we choose a minimum string length of 2000 characters by padding short messages with zeros.
	
Experimental sequence XML <-> dictionary
In order to edit sequences in python and LabVIEW, we choose the XML format that can be accessed by both and is clear to read.
Functions in the translator.py script allow to convert from XML to a python dictionary, which is much less verbose and much easier to edit.
In Python the sequence is stored in an ordered dictionary where the keys correspond to the names of the clusters/arrays in DExTer. Note: the fast digital channels are stored in lists of lists with shape (# steps, # channels), but the analogue channels are stored in transposed lists of dictionaries of lists with shape (# channels, {voltage:[# steps], ramp?:[# steps]})

Andor camera
We use an Andor iXon Ultra 897 EMCCD (SN: 11707). It comes with Andor SDK written in C to control the camera. Python wrapper functions are found in AndorFunctions.py.
We use the SDK to create a basic operation of the camera:
	• Create a cameraHandler.camera() instance to connect to the camera. This is a subclass of QThread so that the acquisition of the camera can run independently. Upon initialising:
		○ Load the C functions from the Andor SDK
		○ Connect to the camera over USB
		○ Connect the SDK's driver event to a windows event - this notifies at different stages of acquisition.
		○ Set the acquisition settings by loading in a config file (see config_README.txt)
	• To take a series of images, call start(). Assuming that the camera is in 'run till abort' mode this will:
		○ Start a camera acquisition, which primes the camera ready to trigger an exposure.
		○ Waits until an exposure is completed (so it must run on a separate thread, otherwise it would be blocking)
		○ Retrieves the latest image from the camera buffer (it shouldn't miss any, so there should only be one image in the buffer. This can be checked by calling EmptyBuffer()).
		○ Emits the retrieved image as a numpy array.
		○ This repeats until the Andor SDK function AbortAcquisition() is called, or an error means that the camera state is no longer 'DRV_ACQUIRING'.
	• If you don’t want to use the 'run till abort' mode and are taking a known number of acquisitions, it may be easier to use the TakeAcquisitions() function.
	• The SafeShutdown() function ensures that the camera state is safe before turning it off:
		○ Temperature kept at the setpoint after turning it off
		○ Shutter closed
		○ EM gain reset (since high EM gains give ageing)
		○ Reset windows event
	• The recommended acquisition settings are:
Setting 	Set value	Meaning
Crop mode	0	off
Isolated crop mode type	0	Default: high speed
Read mode	4	Image
Acquisition mode	5	Run till abort
Trigger mode	7	External exposure*
Frame transfer	0	Off
Fast trigger	0	Off (only available for the external trigger mode)
* Being in external exposure mode means that the external trigger pulse defines the start and the duration of the exposure. It also means that there are keep clean cycles between exposures, which reduces background.
		○ With these settings the readout time (which defines the minimum possible time between taking exposures) is decided by the size of the ROI. It is therefore recommended to use the smallest ROI possible:
ROI size	Minimum duration between exposures (ms) (5MHz readout rate)	Software-computed readout time (ms)
32x32	11 	6.927
64x64	15	10.34
128x128	22	17.57
256x256	36	32.03
512x512	75	60.96
		○ To reduce noise on the acquired image, use:
			§ Conventional mode, 0.08MHz readout rate, preamp gain setting 3
		○ Sometimes noise will be sacrificed for the sake of faster readout rate or larger signal:
			§ EM gain mode, 5MHz readout rate, preamp gain setting 3, then apply EM gain as needed
			§ See the separate document EMCCD_noise_summary.pdf for more details

Save images
Save a numpy array to a file that is named with a timestap, file ID number (synchronised with the run number), and image ID number (denoting the order of images in the sequence).
The file name follows the syntax: [label]_[day month year]_[file #]_[Im #].asc
Load the directories of where to save files to from a config file.
This class inherits PyDexThread which itself inherits QThread. When the thread is started it runs like:
	1. Check the queue for an image to save.
		○ When an image is taken, it should be passed by pyqtSignal to the instance of the imsaver.event_handler() using the inherited add_item() function to append it at the end of the queue.
	2. Process the image at the front of the queue.
		○ Save it to a file with the appropriate name.
	3. Loop continuously as long as the thread is running.
		○ Stop the thread by calling the inherited close() function.

Image Analysis: SAIA
Single atom image analysis: create histograms from collections to images, collect statistics from images and histograms.

A generic Analysis class is used to standardise the structure that all analyses will take. It provides a structure of:
	• Properties:
		○ Stats (from an image or from a histogram) - stored as ordered dictionary of lists for clarity and speed.
		○ Types (one for each stat) - stored as ordered dictionary for clarity.
	• Methods:
		○ Process (quickly take stats from a given image/histogram)
		○ Save
		○ Load 
		○ Reset_arrays
	
A settings GUI controls the ROIs, bias offset, etc. for all instances. This main window manages all of the other analysis windows.
	• Load previous settings from a default config file that is updated when the program is closed.
	• Produce analysis windows for analysing images:
		○ Main windows 
			§ These receive a set image during a sequence and process the counts in a set ROI
			§ A unique name is given to each main window to prevent overwriting files. By default this is set as:
				□ ROI[ROI index].Im[image index].
				□ ROI index is set for the first m windows, where m is the number of images per sequence. e.g. if 2 images are taken in a sequence, the first two main windows will be ROI0, then the two windows after that will be ROI1, etc.
				□ Image index counts where the image comes in the sequence. e.g. if 2 images are taken in a sequence, they will be indexed as Im0 and Im1.
		○ Re-image windows 
			§ use the histograms from two main windows. If there was a count above threshold present in the first main window, then the corresponding image in the second main window (identified by file ID) is included in the re-image histogram.
	• Allow the user to choose settings that apply to all analysis windows:
	Setting	Description
	Number of images per run	How many images will be taken in a single run of the experimental sequence.
	Number of image analysers	Number of main windows to open which will receive and process images.
	Image indices for analysers	List of comma-separated indices dictating which image is sent to which analyser, e.g. 0,0,1 would assign the first window Im0, second window also Im0, and the third window Im1.
	Histogram indices for re-imaging	List of semicolon-separated indices dictating which main windows the re-image windows will use, e.g. 0,1;2,3 would create two re-image windows. The first would use main windows 0 and 1, the second would use 2 and 3.
	Image size in pixels	The incoming image is expected to be a nxn array of this many pixels.
	EMCCD bias offset	The number of counts to subtract from all images to account for the bias offset.
	User variable	Sets the 'User variable' setting in all of the analysis windows, used for assigning the independent variable in a plot of histograms results.
	• Reset the analysis windows and connect their signals to receive the appropriate images 
	• Keep a default config file to load previous settings
	• Provide a convenience button to fit, save, and reset the histograms in all analysis windows. Starts by fitting the main window histograms, then fitting and saving the re-image windows, then it can save and reset the main windows.

Region of Interest (ROI)
For separate images we might want a different ROI if the atom is in a different position.
Within one image we might want several ROIs if there are several atoms.
The ROI is defined by a mask applied to the image. The mask is an array with the same dimensions as the image containing elements with values between 0-1. For a square ROI this just sets the pixels outside of the ROI to zero. 
The ROI can be chosen by:
	• Individually setting it on each Single Atom Image Analyser window
	• Setting all of the windows to use the same ROI as the first Analyser
	• Choosing a square grid from the settings window:
	
		○ Divide the area of the image equally between Analysers using it.
		○ Factorise the area into a width and a height that are as close to square as possible.
		○ Make a grid of these areas covering the image, and assign areas to the Analysers in turn.
	• Choosing to fit 2D Gaussian masks to an image (probably wants to be an average image).
	• Independent component analysis of a set of images containing an array of atoms.

Single Atom Image Analysis (SAIA)

	• maingui.main_window(): GUI for a single histogram of a given ROI for a given image in a sequence
	• reimage.reim_window(): GUI for calculating survival probability
	• imageHandler.image_handler() inherits Analysis class: creates the histogram for a given ROI for a given image in the sequence.
	• histoHandler.histo_handler() inherits Analysis class: for collections of histograms in a multirun that build up a plot.
	Fit a function to the histogram in order to determine statistics like the mean count, standard deviation, ratio of counts in each peak (loading probability), etc.
	
An image from the camera is passed as a numpy array. We make sure not to edit the array in place as it might need to be processed by several analysers. For example, subtracting the bias offset from the array would affect all image analysers using that image, so instead a copy of the array is made by each image_handler.

Data format
Use lists to store the integrated counts and other statistics from a collection of images. Append another value for each image. This is the fastest method given that we can't fix the size of the list.

Images
ASCII file with the first column as the row number 
Histograms 
csv with the first 3 rows as a header containing the last calculated fit and column headings 
Measure file
Text file with the first 3 rows as a header containing column headings, then rows are appended for each histogram saved.
Andor config settings
Text file with ordered rows for each setting
Image saving directory settings
Text file with text labels indicating each setting

Monitor

Sequences
DExTer sequences were originally stored in binary .seq files. Since these are inaccessible to Python, we choose .xml format instead. These can be converted to python dictionaries which are much simpler to edit, after several long functions reformatting the structure. A generic sequence has the format:
	• ('Event list array in', [{'Event name', 'Routine specific event?', 'Event indices', 'Event path'}]*number_of_events )
	• ('Routine name in', ''),
	• ('Routine description in', ''),
	• ('Experimental sequence cluster in', 
		('Sequence header top', [header_cluster]*number_of_steps),
		('Fast digital names', [{'Hardware ID', 'Name'}]*number_of_fast_digital_channels),
		('Fast digital channels', [[Bool]*number_of_fast_digital_channels]*number_of_steps),
		('Fast analogue names', [{'Hardware ID', 'Name'}]*number_of_fast_analogue_channels),
		('Fast analogue array', [[{'Voltage', 'Ramp?'}]*number_of_steps]
												*number_of_fast_analogue_channels),
		('Sequence header middle', [header cluster]*number_of_steps),
		('Slow digital names', [{'Hardware ID', 'Name'}]*number_of_slow_digital_channels),
		('Slow digital channels', [[Bool]*number_of_slow_digital_channels]*number_of_steps),
		('Slow analogue names', [{'Hardware ID', 'Name'}]*number_of_slow_analogue_channels),
		('Slow analogue array', [[{'Voltage', 'Ramp?'}]*number_of_steps]
												*number_of_slow_analogue_channels))

Note that the order of indexing between digital and analogue channels is transposed.

	• Translator
		○ Converts sequences XML <-> python dictionary
	• Sequence Previewer
		○ Uses the translator to display a sequence.
		○ Gives a GUI for creating a multirun from an array of variables

Multirun 
A multirun is a series of runs, changing a list of variables in the sequence. The format is as follows:
	• Load the base sequence into the sequence previewer
	• Create a list of variables to change:
		○ For all variables:
			§ Variable label used to identify the multirun (what variable you're changing for the experiment)
			§ Number of runs to omit before starting the histogram 
			§ Number of runs in a histogram 
		○ For each variable (a column in the table of values):
			§ Type: 'Time step length' or 'Analogue channel'
			§ List of time steps to change
			§ Analogue type: 'Fast analogues' or 'Slow analogues' (*)
			§ List of analogue channels to change (*)
			§ List of variables to assign to the given channels in the given time steps, one for each run in the multirun.
	(*) only needed if the type is 'Analogue channel'
	• You can change the end step that is used while the multirun is running. This allows you to make use of the ~100ms dead time while DExTer processes after a run. During the multirun the last time step will be taken from the text edit 'Running:', then after the multirun the last time step will be reset to the one in 'End:'.
	• Check that the variables list is valid (no empty spots, number of rows is divisible by # omitted + # in hist)
	• Start a multirun using the command from the master window. The number of runs per histogram in the multirun is given by the number of rows in the table of variables. The total number of runs is this multiplied by the number of repeats.
		○ Since there could be a queue of commands sent to DExTer, the master waits for confirmation before connecting the slots
			§ Send a message 'start measure '… to confirm DExTer is ready to start the multirun
		○ Load the last time step for running the multirun.
		○ Update the sequence and then add a single run to the queue:
			i. Receive message 'start measure' command by TCP
			ii. Send message to load the new sequence 
			iii. Send message to run the new sequence (since the first base sequence is already loaded - run it before editing it)
			iv. Run the sequence for the given number of omits and repeats
			v. Save and reset the histogram
			vi. Change the channels/timesteps in the sequence specified by the list of variables
			vii. Repeat from step ii.
		○ Send 'confirm last multirun run' command with 'TCP read' enum.
		○ Send 'end multirun' command with 'TCP read' enum and receive the 'confirm last multirun run' message.
		○ Save a multirun parameters file with the variable list and associated run numbers. Save the plot data from each of the image analysis windows. Reset the signals to show that the multirun has finished.

#####  SAIA1  ##### - image analysis
**** Version 1.3 ****
Produces histograms for an image containing a either single atom or none.
**** ****	
	• Note that the image size in pixels must be set before any images are processed. 
		○ If the image size is known, type it into the 'Image size in pixels:' text edit
		○ The image size can also be taken from an image file by clicking 'Load size from image'
		○ The 'Get ROI from image' button implicitly gets the image size and then centres the ROI on the max intensity pixel
	
	• For the current histogram there are several binning options:
Automatic Binning (Default)	the number of bins is taken to be 17 + 5e-5 * N^2 + 20 * ((max-min)/max)^2, where N is the number of images in the histogram and max/min are the extreme counts in the histogram.
Manual	When the Max, Min, and #Bins text edits are populated, the histogram will be set with those limits. Otherwise do automatic binning.
No Display	Images will still be processed, but the histogram will not be replotted (speeds up processing)
No Update	Images are not processed for the histogram

	• Selecting 'Auto-Display Last Image' plots a 2D colourmap of the image file last processed.
		○ This can take up to 1s for 512x512 images and so causes lag if file events occur faster than this.
		○ The user can set an ROI by clicking 'ROI' and then dragging the box:
			§ Dragging from the box area translates the box
			§ The top left circle can be used to rotate the box
			§ The bottom right square can be used to resize the box
		○ The ROI can also be set by the text inputs in the settings tab (all must be filled in before there is any change)
		○ The ROI can be centred on the max pixel in an image by clicking 'Get ROI from image'
		○ Changing the ROI by either of these ways sets the region of the image that is processed, and this will be retained until the settings are next changed. 

We will take fluorescence images of atoms in the tweezer from the Andor camera (512x512, well-depth 180,000 e-)
We want a program that will real-time readout the integrated counts from the image and display a graph which identifies images with or without single atoms in.

Results structure
	• An image is processed by saving a copy to the image storage path then calculating:
File #	Taken from currentfile.txt
Integrated counts in ROI	User sets ROI, sum the counts in all of the pixels
Atom detected	Counts // threshold. This is greater than zero if an atom is detected
Max count	Search for the maximum value in the loaded image array
(replaced with ROI centre count)	(replace with the pixel value at the centre of the ROI)
	
xc	x-position of max count (in pixels)
yc	y-position of max count (in pixels)
Mean count	Take the mean of the image outside of the ROI to estimate background
Standard deviation	Take the standard deviation of the image outside of the ROI
The integrated count is added to the current histogram and the rest of the information is stored in an array
These are also the column headings when the histogram is saved.
	
	• The histogram statistics are analysed and displayed in the 'Histogram Statistics', they will be appended to a log file when the histogram csv is saved. The log file contains the following columns:
Hist ID	Increments by one every time a line is appended to the log file
Start File #	The file number for the first image in the histogram
End File #	The file number for the last image in the histogram
User variable	Variable set by the user, must be a float
Images processed	Number of images processed in the current histogram
No atoms (V2)	Number of images where both ROIs are empty
Single atom (V2)	Number of images where one ROI has an atom, but the other is empty
Both atoms (V2)	Number of images where both ROIs contain an atom
Loading probability	Ratio of images with counts above threshold to total images processed
Error in loading probability	From binomial confidence interval of threshold compared to peaks
Background peak count	Fitted position of the background peak in counts
Background peak width	Fitted width of the background peak in counts
sqrt(Nr^2 + Nbg)			Estimate of the background width - readout noise + Poisson contribution
Error in Background peak count	standard error: background peak width / sqrt(number of images used to fit the peak)
Background mean	Mean of integrated counts from images below threshold
Background standard deviation	Standard deviation of integrated counts from images below threshold
Signal peak count	Fitted position of the atom peak in counts
Signal peak width	Fitted width of the atom peak in counts
sqrt(Nr^2 + Ns)	Estimate of the signal width - readout noise + Poisson contribution
Error in Signal peak count	standard error: signal peak width / sqrt(number of images used to fit the peak)
Signal mean	Mean of integrated counts from images above threshold
Signal standard deviation	Standard deviation of integrated counts from images above threshold
Separation	Signal peak count - background peak count
Error in Separation	Signal peak count - background peak count
Fidelity	The probability of not assigning false positives or false negatives
Error in fidelity	By using the peak widths as measures of their uncertainty
S/N	Separation / sqrt((fitted background width)^2 + (fitted signal width)^2)
Error in S/N	Propagated error from the separation and the error in the widths 1/sqrt(2N-2)
Threshold	Mean of background and signal peak counts

	• Each time a line is appended to the log file, the data will also be added to arrays which can be accessed in the 'Plotting' tab.
The 'Plotting' can display any of the variables that are stored in the log file. 
	
Peak calculations
There are several different ways to estimate the background and signal peak centres and widths and therefore calculate the threshold:
Update statistics 	Quick estimate: uses scipy.signal.find_peaks - quite good at finding peaks but the width is unreliable
Get best fit	Use a threshold to split the histogram into background and single atom peaks, then fit Gaussian curves to get the mean and standard deviation. Use the fitted curves to set the threshold at the closest point above the background peak where the fidelity is > 0.9999, or if that is not possible, then where the fidelity is maximum.
Fit background	Assume that there is only one peak in the histogram corresponding to the background. Fit a single Gaussian.
	
	
	• Any of the plots can be saved by right clicking on the plot area and selecting 'Export…'
Under 'Item to export' make sure to select 'Entire Scene', otherwise it will not save.

Fitting

Each peak is fit with a Gaussian. From that fit, we get a width, which is the standard deviation.

The fitting function is y=Aexp⁡(−(2(x−µ)^2)/w^2 )   where µ is the mean count, w is the 1/e2 width, and σ=w/2 is the standard deviation.

Threshold Calculations
There are several ways to set the threshold determining the presence of an atom:
	1) A set number of standard deviations above the background peak - so you have a set statistical confidence of it not assigning a false positive
	2) The mean of the two peaks - a quick way to assign the threshold that doesn't depend on peak widths
	3) Maximise the fidelity - minimise the probability of false positives and false negatives, requires good estimates of both peak widths
	4) Receiver operating characteristic - minimise false positive rate, maximise true positive rate
	
We use option 3) in order to correctly assign as many images as possible.

Fidelity calculations
The fidelity measures how accurately we can determine if we have detected an atom. It is defined as follows:

F=1 −P("false positives" )−P("false negatives)

To determine P(false positives) and P(false negatives), the cumulative distribution function is used such that the Gaussian fits are integrated above and below the threshold.

P(false positives)=1 − CDF(μ_bk,σ_bk,threshold)
P(false negatives)=CDF(μ_atom,σ_atom,threshold)

The threshold is set by iteratively maximising the fidelity. The threshold is chosen at the point above background which first maximises the fidelity, to a precision of 3 decimal places. This is either the position closest to the background peak where the fidelity is > 0.9999, or if this is not possible, the position between the peaks where the fidelity is maximised.

The shaded region below threshold is the probability of false negatives (there are also false negatives due to the integrated counts from an atom being below threshold in an image. For example, if the atom escapes the trap during an imaging probe pulse it might not emit enough photons to be detected). The shaded region above threshold is the probability of false positives.


Loading Probability Calculations
The loading probability is simply the number of counts above threshold over the total number of counts.
The error on the loading probability is estimated using the binomial confidence interval (http://docs.astropy.org/en/stable/api/astropy.stats.binom_conf_interval.html).
Assuming a Binomial distribution this is the 1-sigma confidence interval for getting natom counts out of a total of N images.

Settings Tab
These settings must be chosen before the program can run.
Image size in pixels	The program needs to know the size of the array that it will get from the .asc file that the image is saved as. If the setting is too small, it will not load the whole image. If the setting is too high, it will spit out an error and potentially crash.
Load size from image	If you don't know the image size, use this button to select an image and calculate the image size.
Get ROI from image	Implements 'Load size from image' and then sets the centre of the ROI at the maximum intensity pixel in the image.
ROI x_c	Horizontal coordinate of the centre of the ROI
ROI y_c	Vertical coordinate of the centre of the ROI
ROI size	Width of the ROI - the ROI encompasses a square covering the coordinates (in pixels)
	x_c - size//2 : x_c + size//2, y_c - size//2 : y_c + size//2
EMCCD bias offset	The EMCCD applies a numerical offset to the number of counts to make sure that there are never negative counts. This is subtracted from the background/signal counts in order to estimate their widths in sqrt(Nr^2 + N).
EMCCD read-out noise	When the EMCCD reads out there is some electronic noise added, which is assumed to be Gaussian distributed. The supplied setting is the standard deviation of that noise.
Config File	Path to the config file which contains the Image storage path, Log file path, Dexter sync file, Image read path, and Results path (see above). The format of this file is important.


Multirun Tab
Settings for automatically taking a series of histograms in a measure.
Measure prefix	An ID for the measure. This will be the prefix for all of the histogram csv files, and the name of the log file saved at the end.
User variable	The user sets the variables associated with each histogram. The number of histograms in one measure (collection) is set by the length of the list of user variables. The multi-run process will repeat this many times. The list of user variables is displayed underneath and can be reset with the 'Clear list' button.
	To enter a list of variables you can input in the format 'start, stop, step, repeats'.
Current list	Displays the list of user variables that will be used when the multi-run is started
Omit the first N files	Sometimes we may want to run the experiment several times before taking data (e.g. for the AOMs to warm up). Therefore, save the first N files but don't process them to include in the histogram.
number of files in the histogram	For each of the user variables in the list, after omitting the set number of files, make a histogram of # files and save a .csv file in the chosen directory.
Choose directory to save to	The directory to save the histogram .csv files as they are created, and the log file when it's done.
Current progress	Display the current status of the multi-run:
	User variable: __, omit __ of __ files, __ of __ histogram files, __ % complete.
Start/Abort	Start the multi-run if it's not running using the above settings. This button starts from the beginning. If it is running, stop it and return the dir_watcher to its previous state (determined by the histogram binning settings). The position in the multi-run is not reset, so it can be resumed.
Resume	Start the multi-run from where it left off.

Histogram Tab
Display the current histogram. The performance is defined by the Histogram -> Binning options:
Automatic Binning (Default)	Numpy decides the binning automatically
Manual	When the Max, Min, and #Bins text edits are populated, the histogram will be set with those limits. Otherwise choose the min and max counts as the limits, and the number of bins is taken to be 17 + 5e-5 * N^2 + 20 * ((max-min)/max)^2, where N is the number of images in the histogram and max/min are the extreme counts in the histogram.
No Display	The directory watcher will still run and files will still be processed, but the histogram will not be replotted (speeds up processing)
No Update	The directory watcher still runs, so files are saved/moved, but not processed for the histogram

Histogram Statistics Tab
Display all of the calculated values for the current histogram
Update statistics 	Quick estimate: uses scipy.signal.find_peaks - quite good at finding peaks but the width is unreliable
Get best fit	Use a threshold to split the histogram into background and single atom peaks, then fit Gaussian curves to get the mean and standard deviation. Use the fitted curves to set the threshold at the closest point above the background peak where the fidelity is > 0.9999, or if that is not possible, then where the fidelity is maximum.
Fit background	Assume that there is only one peak in the histogram corresponding to the background. Fit a single Gaussian.

The 'Add to plot' button appends the displayed values to the stored array used for the plotting tab. It also appends the displayed values to the log file.

Image Tab
Display one of the images. The ROI is highlighted, and can be dragged to adjust the position. The diamond in the top right corner allows the size of the ROI to be adjusted.
The intensity scale is set to the maximum and minimum in the loaded image.
'Auto-display last image'	Displays images as they are processed

Plotting Tab
Make a graph of any of the histogram statistics plotted against each other.
There is a text box supplied along the x-axis in case the user would like to supply their own axis label.
Clear plot	Reset the arrays storing the histogram statistics data so that the plot is emptied. This data is not lost since it is saved in the log file.
Save plot data	Save the arrays of histogram statistics used in the current plot to a new measure file in the same format as the log file.


Output:
	• A directory with subdirectories ordered by date storing all of the labelled image files
	• A real-time display of the histogram 
	• A summary (log) file with histogram data:
		○ Essential: files included, so that they can be re-analysed at a later date. Columns are:
			§ File label (dexter #)
			§ Integrated counts
			§ Variable (if possible - taken from dexter multirun)