"""Image Saver
Stefan Spence 09/09/19

 - receive an image array through a signal
 - add the received image array to a list to save
 - run a thread saving images from the list into a dated 
    subdirectory under image_storage_path
 
Assuming that image files are ASCII.
This runs as a QThread in parallel to other tasks
"""
import numpy as np
import os
import sys
import time
try:
    from PyQt4.QtCore import pyqtSignal
except ImportError:
    from PyQt5.QtCore import pyqtSignal
sys.path.append('..')
from mythread import PyDexThread
import logging
logger = logging.getLogger(__name__)

def checkdir(text):
    """Shorthand for extracting a directory from the config file"""
    path = text.split('=')[-1]
    return path if os.path.exists(path) else '.'

####    ####    ####    ####
    
# set up an event handler that is also a QObject through inheritance of QThread
class event_handler(PyDexThread):
    """Save the image array that is passed through a signal to a file.
    
    The event handler responds to a signal by appending the array to a
    list. When the thread is running it will pop images from the list
    and save the image array to a new directory, and then emit a 
    signal to confirm the saving has finished. The Dexter file number 
    and image number should be synced externally.
    Use a config file to load the directories.
    Wait for events and process them with the event_handler.
    Keyword arguments:
        config_file -- the file to load relevant directories from.
        The format is important for reading in the directories.
        image_storage_path    -- directory that new images will 
                be written to.
        dexter_sync_file_name -- absolute path to DExTer currentfile.txt
    """
    event_path = pyqtSignal(str)        # the name of the saved file
    new_im     = pyqtSignal(np.ndarray) # the new incoming image array
            
    def __init__(self, config_file='./config/config.dat'):
        super().__init__()
        self.dfn     = "0"         # dexter file number
        self.imn     = "0"         # ID # for when there are several images in a sequence
        self.nfn     = 0           # number to append to file so as not to overwrite
        self.last_event_path = ""  # last event processed 
        self.t0      = 0           # time at start of event
        self.init_t  = time.time() # time of initiation: use to test how long it takes to realise an event is started
        self.event_t = 0           # time taken to process the last event
        self.end_t   = time.time() # time at end of event
        self.idle_t  = 0           # time between events
        self.write_t = 0           # time taken to watch a file being written
        self.config_fn = config_file  # remember which file was last used for config settings 
        self.reset_dates(config_file) # create the required directories

    def reset_dates(self, config_file='./config/config.dat', 
            date=time.strftime("%d %b %B %Y", time.localtime()).split(" ")):
        # load paths used from config.dat
        self.dirs_dict = self.get_dirs(config_file) # handy dict contains them all
        self.image_storage_path = self.dirs_dict['Image Storage Path: ']
        self.dexter_sync_file_name = self.dirs_dict['Dexter Sync File: ']
        self.results_path = self.dirs_dict['Results Path: ']
        self.sequences_path = self.dirs_dict['Sequences path: ']
        if self.image_storage_path: # =0 if get_dirs couldn't find config.dat, else continue
            # get the date to be used for file labeling
            self.date = date # day short_month long_month year
            datepath = r'\%s\%s\%s'%(self.date[3],self.date[2],self.date[0])
            self.image_storage_path = self.check_path(self.image_storage_path, datepath)
            self.results_path = self.check_path(self.results_path, datepath)
            # self.sequences_path = self.check_path(self.sequences_path, datepath)
        else: logger.warning('Image saver could not load paths from config file: '+config_file)

    def check_path(self, path, datepath):
        """Check if Python has permission to write to the given directory, path.
        If so, make a dated directory from that path."""
        try: # create directory by date if it doesn't already exist
            os.makedirs(path + datepath, exist_ok=True) # requies version > 3.2
            return path + datepath
        except PermissionError as e: 
            logger.warning('Image saver could not create directory: '+
                path +'\nUsing current directory instead\n'+str(e))
            os.makedirs('.' + datepath, exist_ok=True)
            return '.' + datepath

    @staticmethod # static method can be accessed without making an instance of the class
    def get_dirs(config_file='./config/config.dat'):
        """Load the paths used from the config.dat file or prompt user if 
        it can't be found"""
        image_storage_path, dexter_sync_file_name = '', ''
        sequences_path, results_path = '', ''
        # load config file for directories or prompt user if first time setup
        try:
            with open(config_file, 'r') as config_file:
                config_data = config_file.read().split("\n")
        except (FileNotFoundError, OSError):
            print("config.dat file not found. This file is required for directory references.")
            return {'Image Storage Path: ':'', 'Dexter Sync File: ':'','Results Path: ':'', 'Sequences path: ':''}
        for row in config_data:
            if "image storage path" in row:
                image_storage_path = checkdir(row) # where image files are saved
            elif "dexter sync file" in row:
                dexter_sync_file_name = checkdir(row) # where the txt from Dexter with the latest file # is saved
            elif "results path" in row:
                results_path = checkdir(row)   # where csv files and histograms will be saved
            elif 'sequences path' in row:
                sequences_path = checkdir(row) # where sequence xml files will be saved
        return {'Image Storage Path: ':image_storage_path,
                'Dexter Sync File: ':dexter_sync_file_name,
                'Results Path: ':results_path,
                'Sequences path: ':sequences_path}
        
    @staticmethod
    def print_dirs(dict_items):
        """Return a string containing information on the paths used
        dict_items should be the dirs_dict {key:value} dictionary."""
        outstr = '// list of required directories:\n'
        for key, value in dict_items:
            outstr += key + '\n' + value + '\n'
        return outstr
        
    def save_config(self, config_file='./config/config.dat'):
        """Write the directories currently in use into a new config file."""
        outstr = '// list of required directories:\n'
        for key, value in [d for d in self.dirs_dict.values()]:
            outstr += key + '\t = ' + value + '\n'
        with open(config_file, 'w+') as config_file:
            config_file.write(outstr)
        
    def wait_for_file(self, file_name, dt=0.01):
        """Make sure that the file has finished being written by waiting until
        the file size isn't changing anymore"""
        last_file_size = -1
        while last_file_size != os.path.getsize(file_name): 
            last_file_size = os.path.getsize(file_name)
            time.sleep(dt) # deliberately add pause so we don't loop too many times

    def process(self, im_array, label='Im'):
        """On a new image signal being emitted, save it to a file with a 
        synced label into the image storage dir. File name format:
        [label]_[date]_[Dexter file #].asc
        """
        self.t0 = time.time()
        self.idle_t = self.t0 - self.end_t   # duration between end of last event and start of current event
        # copy file with labeling: [label]_[date]_[Dexter file #]
        new_file_name = os.path.join(self.image_storage_path, 
                '_'.join([label, 
                        self.date[0]+self.date[1]+self.date[3], 
                        self.dfn, self.imn]) + '.asc')
        self.write_t = time.time()
        if os.path.isfile(new_file_name): # don't overwrite files
            new_file_name = os.path.join(self.image_storage_path, 
                '_'.join([label, 
                        self.date[0]+self.date[1]+self.date[3], 
                        self.dfn, self.imn, str(self.nfn)]) + '.asc')
            self.nfn += 1 # always a unique number
        out_arr = np.empty((im_array.shape[0],im_array.shape[1]+1))
        out_arr[:,1:] = im_array
        out_arr[:,0]  = np.arange(im_array.shape[0])
        np.savetxt(new_file_name, out_arr, fmt='%s', delimiter=' ')

        self.write_t = time.time() - self.write_t
        self.last_event_path = new_file_name  # update last event path
        self.event_path.emit(new_file_name)  # emit signal
        self.end_t = time.time()       # time at end of current event
        self.event_t = self.end_t - self.t0 # duration of event
