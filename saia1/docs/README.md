**** Version 1.3 ****
Produces histograms for an image containing a either single atom or none.
**** ****

How to run Single Atom Image Analysis (SAIA):
	• Start the file: 
		○ Execute run_with_enthought.bat   --- a windows batch file with a hardcoded link to the Enthought python executable
		○ Execute run_with_conda.bat           --- activate the Anaconda environment (you must first create the saiaenvironment, which can be done using create_environment.bat) and run using Anaconda.
		○ Or run from a python distribution (e.g.  python main.py)
		
	• A window pops up showing the loaded file config and asking to start the directory watcher
		○ 'Yes' will start the directory watcher to process file creation events from a directory.
		○ 'No' starts up the program without the directory watcher (it can be initiated later)
Image storage path	Where SAIA will save images to (in subdirectories by date)
Log file path	Where SAIA will save log files to (in subdirectories by date, collects histogram statistics)
Dexter sync file	Absolute path to the file where Dexter stores the current file number
Image read path	Absolute path to the folder where Andor will save new image files to (note that no other file creation events should occur in this folder, or they will be processed by the directory watcher as well)
Results path	The default location to open the file browser for saving csv files
	
	• Note that the image size in pixels must be set before any images are processed. 
		○ If the image size is known, type it into the 'Image size in pixels:' text edit
		○ The image size can also be taken from an image file by clicking 'Load size from image'
		○ The 'Get ROI from image' button implicitly gets the image size and then centres the ROI on the max intensity pixel
		
	• There are several running modes:
		○ Active directory watcher (real time processing of images straight after the file is saved to the image read path. Copies then deletes images)
		○ Passive directory watcher (real time processing of images straight after the file is saved to the image read path. Doesn't alter the file)
		○ Load data from csv (the format is: file#, counts, atom detected?, max count, pixel x position, pixel y position, mean count, standard deviation)
		○ Load data from a selection of image files
		○ No Update histogram binning (directory watcher still saves/moves image files, but they are not processed for the histogram)
		
	• Note that when loading in new data it will use the current ROI settings on display. It will ask whether you want to clear the current array, which will prevent mixing of data with different ROI settings.
	
	• For the current histogram there are several binning options:
Automatic Binning (Default)	the number of bins is taken to be 17 + 5e-5 * N^2 + 20 * ((max-min)/max)^2, where N is the number of images in the histogram and max/min are the extreme counts in the histogram.
Manual	When the Max, Min, and #Bins text edits are populated, the histogram will be set with those limits. Otherwise do automatic binning.
No Display	The directory watcher will still run and files will still be processed, but the histogram will not be replotted (speeds up processing)
No Update	The directory watcher still runs, so files are saved/moved, but not processed for the histogram

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
# files in the histogram	For each of the user variables in the list, after omitting the set number of files, make a histogram of # files and save a .csv file in the chosen directory.
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



Experimental Procedure:
	• Make a Rb MOT, load a Rb atom in its tweezer 
	• Take an image to confirm Rb was loaded (save to Rb image directory) - process with SAIA 1.0
	• Make a Cs MOT, load a Cs atom in its tweezer 
	• Take an image of both atoms (save to different image read path) - process with SAIA 2.0
	• Experiment (vary hold time?)
	• Final image to check if atoms are still trapped (save to another different image path) - process with a different SAIA 2.0
Note that running several SAIA programs at the same time will require them all to have different directories where images are saved to/loaded from.

For any experiment you should make a record of the camera settings (screenshot), the ROI used, and any relevant Dexter parameters.

Possible Architectures
Original method:
	Experiment run by Dexter in loop -> Andor running in loop receives trigger (saves images) -> Python runs a loop checking for file changes -> python processes the new file, then plots a histogram
	Needs several threads to run in parallel – a directory watcher to notice created files, and a graph plotter to process the data. Working version using pyqt

Andor Trigger Method 1:
	Experiment run by Dexter in loop -> Andor running in loop receives trigger (saves images) -> triggers Python with TTL to process new image file
	Maybe Python only updates the histogram every [x] number of runs? Python still needs to run continuously waiting for a trigger from Andor if we want it to retain data, but is told when files are saved rather than having to watch and wait.
	Python could send a trigger to start the next Dexter run
	
Andor Trigger Method 2:
	Experiment run by Dexter in a loop -> Andor running in loop receives trigger (saves images with Dexter file #) 
	Python script runs independently analysing files. Since Andor would save separate files with their Dexter label, then if python lags behind it will not lose sync. This requires Andor staying in sync with the Dexter file #
	
Dexter Saves Method:
	Write a .vi in LabView that gets Dexter to control the camera instead of Andor SDK. Then Dexter can save the files with its Dexter file # and we have no problem with syncing. Analysing the data can then be done separately with no time pressure. The Strontium project already do this with their MPD SPC3 SPAD.
	This is the ideal method that will be implemented at some point.

Input:
Andor saves an image to a set directory as it's running. 
Background subtraction is probably not necessary since it would just shift the histogram along the x axis.
The Andor camera will be set to take an image of a Region of Interest (ROI) around the atom.
The Andor camera can also bin pixels to combine their counts (eg. 4x4 pixel array -> 1 binned pixel) but we might do this binning in post-processing.

Original Method:
1) scan Andor output directory for presence of a new file (dir watcher)
	Wait until file has finished being written
2) save the image with a new label (dir watcher emits signal to dir watcher: on_created)
	[species]_[date]_[dexter file #]
	^requires synchronisation with dexter for file #. Might be slow over the network, or if the network drops then it goes out of sync.
	For multiruns we can get the file numbers from Dexter's outputted measure file
	Wait until file has finished being copied
	Then delete the old image file so that a new one can be saved with the same name.
3) load image (dir watcher emits signal to image handler)
	• Takes 10 - 50 ms but will miss files and crash with an exception is the rate is too fast (works for 0.5s delays but crashes for 0 delay)
4) Find the position of the atom. Not really necessary if we've already selected an ROI.
	• Fit a Gaussian (should only be over a couple of pixels, fitting makes it slower...)
	• Locate the brightest pixel
5) Integrate the atom signal into a count
6) determine whether a single atom is present through reference to a threshold count
	Need some way to estimate parameters of peaks to separate them 
	The separation between peaks (1 atom, 2 atoms, etc) should be the same
	Could estimate threshold as:   
		○ midway between peaks 
		○ The middle of the gap between peaks
		○ Where there is maximum curvature (not robust)
		○ A set number of standard deviations above background (this method is used since it fixes our statistical confidence in the atom signal)
7) plot the integrated count in a histogram (image handler emits signal to histogram plotter)
	Preferably real-time but if that's too slow then every 100 shots or so.
	Would also be good to display the image but again might be too slow for each shot.
	Takes 10 - 50 ms (including loading image)
8) use the histogram to update threshold values (contained in the image handler)
	might need upper bound for two atoms trapped as well as lower bound for no atoms trapped
9) save the histogram with references to the image files so that the data can be re-analysed later as well
	Preferably also storing the input parameters, where available (dexter measure file saves input parameters for a multirun)
	10) Collect histogram statistics in a log file and add them to a plot each time a histogram is saved

Output:
	• A directory with subdirectories ordered by date storing all of the labelled image files
	• A real-time display of the histogram 
	• A summary (log) file with histogram data:
		○ Essential: files included, so that they can be re-analysed at a later date. Columns are:
			§ File label (dexter #)
			§ Integrated counts
			§ Variable (if possible - taken from dexter multirun)


Side tasks and notes:
	• Test the camera computing speed – how fast can it output files? It's faster with just an ROI
	• Will need to test timings: how fast can you process an image? How fast can you plot? How fast does the experiment run? How fast does the andor camera output the file? How fast are files saved? How fast can they be accessed over the network?
	• Long term stability - will it go out of sync if the network goes down?
	• Simulate acquiring an image using the red guide beam
		○ randomly fire/don't fire the AOM (requires an analog channel) – then we can test the success rate of identifying an 'atom'
		○ Set the exposure to the anticipated experimental value (20ms) and include MOT beams etc. To simulate experimental background.
	• Different ways to trigger; in order to time the imaging we need a trigger sent from the andor software (TTL)
		○ We can connect a TTL to python from Andor and from python to dexter via USB.
		○ After Andor camera script runs -> TTL to python 
		○ After python script runs -> TTL to dexter
		○ Then the next dexter experimental run could be started without losing sync (but has to wait)
	• We could measure one of the TTL channels on an oscilloscope, get the time between its triggers and subtract off the duration of the python script and the experiment duration. This would give us the time from camera trigger to python script starting (which is taking the images then saving the files).
		○ However this might not include the time that windows processes files after Andor tells them to be saved
		○ Further, subtracting similar numbers increases the relative numerical error
	• we could send an auxout TTL from the camera after the images have been taken to give readout speed. Then after the files have been saved to test that duration.


Timing for the image analysis program:
	• Time to update plot (2s between image creation): 3 – 4 ms
	• Time to make histogram (2s between image creation): 2 – 230 ms
	• Time to copy file: (2s between image creation): 8 – 12 ms (sometimes tries to access an empty file because the copying isn't finished)
Updated timings:
	• Plotting: 10-15ms
	• Make histogram: 
		○ 250-350ms while live plotting (512x512) (probably because of lag from interface)
		○ 10ms while live plotting (64x64)
	• File copying event: 
		○ Occasionally seen to take 200-300ms when there is lag from live plotting
		○ 1-4ms while live plotting (64x64) and (512x512)
		○ wrote a function to wait until the previous file has been written:
			○ Up to 250 ms between noticing file creation event and the image file being written (done by Andor)
			○ Up to 12 ms copying the file to the new folder
		
	

Timing for the camera:
	• Time to take images (readout - change with ROI?): 512x512 – 800ms, 64x64 - 300ms
	• Time to save images: 4ms


Debugging:
	• Care had to be taken to ensure that the directory watcher was stopped when the program was closed, otherwise its thread would keep running in the background which could cause overwriting of files.
	• It was found that when the directory watcher triggered on file modified events, it would recognise several events for the same image being saved (i.e. for one experimental run it would try and save the image up to 8 times). Particularly problematic was that the first of these would be before the Dexter sync file had been updated, and so it would overwrite the file with the previous Dexter number as well as writing to the current one.
		○ This was solved by making adding some delays and making the directory watcher trigger on file creation events only, then delete the file after a copy has been saved
	• Sometimes when the experiment is running fast the dir watcher processes the file event before Dexter has changed the current file number. This causes python to go out of sync and could possibly overwrite the previous file.

Future Developments:
	• Set several ROIs and make one of a set of TTLs high if an atom is detected in a particular ROI. Could be used as a trigger for the next Dexter run
	• Decluttering the display of a single image (removing histogram at the side)
	• Fix the intensity and zoom of an image for comparison when new images come in

Python script can read in/out TTL through USB
Use to check timings like an oscilloscope
Dexter can wait for a TTL signal from python