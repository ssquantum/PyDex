"""Single Atom Image Analysis
Stefan Spence 12/04/19

 - watch the image_read_path directory for new images
 - save the new image with label into a dated subdirectory under image_storage_path
 - delete the original file so that a new file with the same name can be created
 
Assuming that image files are ASCII

watchdog creates an observer that waits for file creation events
the observer must be initiated and shut down properly to ensure that there isn't
one running behind the scenes which might overwrite previously saved files.
"""
import numpy as np
import os
import time
import shutil
try:
    from PyQt4.QtCore import QThread, pyqtSignal, QEvent
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal, QEvent
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

####    ####    ####    ####
    
# set up an event handler that is also a QObject through inheritance of QThread
class system_event_handler(FileSystemEventHandler, QThread):
    """Define how the watchdog should respond to events.
    
    The event handler responds to file creation events and emits the path
    to the file as a signal. When a file creation event is noticed, the
    on_created() function should be triggered, which waits for a file to
    finishing being written to, produces a synchronised label for it, copies
    it to a new directory, deletes the old file, and then emits the new file
    name as a signal.
    Keyword arguments:
    image_storage_path    -- the directory to save the new images to
    dexter_sync_file_name -- the absolute path to the file with the DExTer sync number
    date                  -- today's date in string format [day][short month][year]
    """
    event_path = pyqtSignal(str)
    
    def __init__(self, image_storage_path, dexter_sync_file_name, date):
        super().__init__()
        self.dfn = ""              # dexter file number
        self.last_event_path = ""  # last event processed 
        self.image_storage_path = image_storage_path  # directory where we copy images to
        self.dexter_sync_file_name = dexter_sync_file_name # path to file where dexter syncs its file #
        self.date = date           # today's date
        self.init_t = time.time()  # time of initiation: use to test how long it takes to realise an event is started
        self.event_t = 0           # time taken to process the last event
        self.end_t = time.time()   # time at end of event
        self.idle_t  = 0           # time between events
        self.write_t = 0           # time taken to watch a file being written
        self.copy_t  = 0           # time taken to watch a file being copied 
        self.nfn     = 0           # number to append to file so as not to overwrite
        self.species = 'Cs-133'    # atomic species to label files with
        
    def wait_for_file(self, file_name, dt=0.01):
        """Make sure that the file has finished being written by waiting until
        the file size isn't changing anymore"""
        last_file_size = -1
        while last_file_size != os.path.getsize(file_name): 
            last_file_size = os.path.getsize(file_name)
            time.sleep(dt) # deliberately add pause so we don't loop too many times
            
    def sync_dexter(self, dt=1e-3):
        """Get the Dexter file number from the dexter_sync_file_name file
        Check if the file is empty (usually means it's being written)
        and wait until it's finished being written to"""
        new_dfn = '' # sometimes Dexter hasn't finished writing to file, we should wait til it has.
        while new_dfn == '': # note: this usually takes about 10 ms.
            with open(self.dexter_sync_file_name, 'r') as sync_file:
                new_dfn = sync_file.read()
            if new_dfn != '':
                if self.dfn != str(int(new_dfn)):
                    self.dfn = str(int(new_dfn))
                else: # sometimes Dexter hasn't updated the file number yet
                    self.dfn = str(int(new_dfn)+1)
                break
            time.sleep(dt) # deliberately add pause so we don't loop too many times
    
    def on_created(self, event):
        """On a new image being written, save the file with a synced label into the 
        image storage dir"""
        t0 = time.time()
        self.idle_t = t0 - self.end_t   # duration between end of last event and start of current event
        self.wait_for_file(event.src_path) # wait until file has been written        
        self.write_t = time.time() - t0
        # get Dexter file number  
        self.sync_dexter()
        # copy file with labeling: [species]_[date]_[Dexter file #] ---- this will overwrite if file already exists
        new_file_name = os.path.join(self.image_storage_path, self.species)+'_'+self.date+'_'+self.dfn+'.'+event.src_path.split(".")[-1]
        self.copy_t = time.time()
        if os.path.isfile(new_file_name): # don't overwrite files
            new_file_name = os.path.join(self.image_storage_path, self.species)+'_'+self.date+'_'+self.dfn+'_'+str(self.nfn)+'.'+event.src_path.split(".")[-1]
            self.nfn += 1 # always a unique number
        try:
            shutil.copyfile(event.src_path, new_file_name)
        except PermissionError:
            print("WARNING: added a pause because python tried to access the file before the other program had let go")
            time.sleep(0.2)
            shutil.copyfile(event.src_path, new_file_name)

        self.wait_for_file(new_file_name) # wait until file has been copied
        self.copy_t = time.time() - self.copy_t
        try:
            os.remove(event.src_path)  # delete the old file so that we can see a new created file event
        except PermissionError:
            print("WARNING: added a pause because python tried to access the file before the other program had let go")
            time.sleep(0.5)
            os.remove(event.src_path)

        self.last_event_path = new_file_name  # update last event path
        self.event_path.emit(new_file_name)  # emit signal
        self.end_t = time.time()       # time at end of current event
        self.event_t = self.end_t - t0 # duration of event
        
####    ####    ####    ####   

# set up a separate event handler that reads in new files but doesn't copy or delete
class silent_event_handler(system_event_handler):
    """Define how the watchdog should respond to events.
    
    The event handler responds to file creation events and emits the path
    to the file as a signal. This silent event handler does not copy or delete
    files, merely emit the event path.
    Keyword arguments:
    image_storage_path    -- the directory to save the new images to
    dexter_sync_file_name -- the absolute path to the file with the DExTer sync number
    date                  -- today's date in string format [day][short month][year]
    """
    event_path = pyqtSignal(str)
    
    def __init__(self, image_storage_path, dexter_sync_file_name, date):
        # same init as the base system event handler
        system_event_handler.__init__(self, image_storage_path, dexter_sync_file_name, date)   
    
    def on_created(self, event):
        """On a new image being written, save the file with a synced label into the 
        image storage dir"""
        t0 = time.time()
        self.idle_t = t0 - self.end_t # duration between end of last event and start of current event
        self.wait_for_file(event.src_path) # wait until file has been written        
        self.write_t = time.time() - t0
        self.last_event_path = event.src_path  # update last event path
        self.event_path.emit(event.src_path)  # emit signal
        self.end_t = time.time()       # time at end of current event
        self.event_t = self.end_t - t0 # duration of event

####    ####    ####    ####   
    
# setup up a watcher to detect changes in the image read directory
class dir_watcher(QThread):
    """Watches a directory to detect changes in the files present
    
    Sets up the relevant directories in a dictionary so that they're
    easily referenced. Use a config file to load the directories.
    Initiate an observer that watches for file creation events and
    processes them with the chosen event_handler, which can be 
    actively moving files, or passively reading in the event path.
    Keyword arguments:
    config_file -- the file to load relevant directories from.
        The format is important for reading in the directories.
        image_storage_path    -- directory that new images will 
                be written to.
        log_file_path         -- directory to save log files to.
        dexter_sync_file_name -- absolute path to DExTer currentfile.txt
        image_read_path       -- directory that new image creation
                events will occur in.
        results_path          -- directory for results to be stored in
    """
    def __init__(self, config_file='./config/config.dat', active=True):
        super().__init__()
        # load paths used from config.dat
        self.dirs_dict = self.get_dirs(config_file)  # handy dict contains them all
        self.image_storage_path = self.dirs_dict['Image Storage Path: ']
        self.log_file_path = self.dirs_dict['Log File Path: ']
        self.dexter_sync_file_name = self.dirs_dict['Dexter Sync File: ']
        self.image_read_path = self.dirs_dict['Image Read Path: ']
        self.results_path = self.dirs_dict['Results Path: ']
        if self.image_storage_path: # =0 if get_dirs couldn't find config.dat, else continue
            # create the watchdog object
            self.observer = Observer()
            # get the date to be used for file labeling
            self.date = time.strftime("%d %b %B %Y", time.localtime()).split(" ") # day short_month long_month year
            self.image_storage_path += r'\%s\%s\%s'%(self.date[3],self.date[2],self.date[0])
            if active: # active event handler copies then deletes new files
                self.event_handler = system_event_handler(self.image_storage_path, 
                                self.dexter_sync_file_name, self.date[0]+self.date[1]+self.date[3])
            else: # passive event handler just emits the event path
                self.event_handler = silent_event_handler(self.image_storage_path, 
                                self.dexter_sync_file_name, self.date[0]+self.date[1]+self.date[3])
            # create image storage directory by date if it doesn't already exist
            os.makedirs(self.image_storage_path, exist_ok=True) # requies version > 3.2
            # initiate observer, don't recursively search directories within the image_read_path
            self.observer.schedule(self.event_handler, self.image_read_path, recursive=False)
            self.observer.start()
    
    @staticmethod # static method can be accessed without making an instance of the class
    def get_dirs(config_file='./config/config.dat'):
        """Load the paths used from the config.dat file or prompt user if 
        it can't be found"""
        # load config file for directories or prompt user if first time setup
        try:
            with open(config_file, 'r') as config_file:
                config_data = config_file.read().split("\n")
        except FileNotFoundError:
            print("config.dat file not found. This file is required for directory references.")
            return {'Image Storage Path: ':'', 'Log File Path: ':'', 'Dexter Sync File: ':'', 
                    'Image Read Path: ':'', 'Results Path: ':''}
                
        for row in config_data:
            if "image storage path" in row:
                image_storage_path = row.split('--')[-1] # where image files are saved
            elif "log file path" in row:
                log_file_path = row.split('--')[-1]      # where dat files of saved data and log files are saved
            elif "dexter sync file" in row:
                dexter_sync_file_name = row.split('--')[-1]   # where the txt from Dexter with the latest file # is saved
            elif "image read path" in row:
                image_read_path = row.split('--')[-1]    # where camera images are stored just after acquisition
            elif "results path" in row:
                results_path = row.split('--')[-1]       # default folder to save histogram csv files to
                
        if os.path.split(dexter_sync_file_name)[0] == image_read_path:
            print("WARNING: The directory watcher acts on all file change events, so the Dexter sync file path and image read path must be different.")
        return {'Image Storage Path: ':image_storage_path, 'Log File Path: ':log_file_path, 
                'Dexter Sync File: ':dexter_sync_file_name, 'Image Read Path: ':image_read_path, 
                'Results Path: ':results_path}
        
    @staticmethod
    def print_dirs(dict_items):
        """Return a string containing information on the paths used
        dict_items should be the dirs_dict {key:value} dictionary."""
        outstr = '// list of required directories for SAIA\n'
        for key, value in dict_items:
            outstr += key + '\n' + value + '\n'
        return outstr
    
    def run(self):
        pass
        
    def save_config(self, config_file='./config/config.dat'):
        """Write the directories currently in use into a new config file."""
        outstr = '// list of required directories for SAIA\n'
        for key, value in [d for d in self.dirs_dict.values()]:
            outstr += key + '\t\t--' + value + '\n'
        with open(config_file, 'w+') as config_file:
            config_file.write(outstr)
  
