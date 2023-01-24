"""Multi Atom Image Analyser (MAIA)
Dan Ruttley 2023-01-20
Code written to follow PEP8 conventions with max line length 120 characters.

 - receive an image as an array from a pyqtSignal
 - set multiple ROIs on the image and take an integrated count from the pixels
 - manage multiple ROI groups containing different ROIs to store data
 - determine atom presence by comparison with a threshold count
"""

import numpy as np
from PyQt5.QtCore import pyqtSignal, pyqtSlot, QObject, QThread, QTimer, QCoreApplication
import time
from copy import copy,deepcopy
# from queue import Queue
from collections import deque

class MultiAtomImageAnalyser(QObject):
    """Multi Atom Image Analyser (MAIA).

    This class performs analysis on images that are passed through from the 
    Andor camera. It should be run in its own thread to prevent slowdown. 
    Images are added to a FIFO queue which will be processed when resources are available. 
    At the end of a run in the multirun, the MAIA will be given chance to 
    clear the image queue and export data before continuing.

    Keyword arguments:
    results_path  -- directory to save log file and results to.
    im_store_path -- the directory where images are saved.
    name          -- an ID for this window, prepended to saved files.
    im_handler    -- an instance of image_handler
    hist_handler  -- an instance of histo_handler
    edit_ROI      -- whether the user can edit the ROI"""
    event_im = pyqtSignal([np.ndarray, bool]) # [numpy array, include in hists?]

    signal_next_image_num = pyqtSignal(int) # send the image number that will be assigned to the next image to GUI
    signal_file_id = pyqtSignal(int) # send the file ID that will be assigned to the next image to GUI
    signal_draw_image = pyqtSignal([np.ndarray, int]) # used to send image back to GUI for drawing
    signal_status_message = pyqtSignal([str]) # send string back to GUI to display on status bar
    signal_roi_coords = pyqtSignal([list]) # send ROI coords back to the GUI
    signal_num_roi_groups = pyqtSignal(int) # send the number of ROI groups back to the GUI
    signal_num_rois_per_group = pyqtSignal(int) # send the number of ROIs per group back to the GUI
    signal_data_for_stefan = pyqtSignal(list,int) # send the roi counts to the iGUI for forwarding to a STEFAN (counts,stefan_index)

    queue = deque() # Double-ended queue to handle images. Images are processed when ready.
    timer = QTimer() # Timer to trigger the updating of queue events

    def __init__(self, results_path='.', num_roi_groups=2, 
                 num_rois_per_group=3,num_images=2):
        super().__init__()
        # self.set_results_path(results_path)
        self.new_roi_coords = None
        # self.date = time.strftime("%d %b %B %Y", time.localtime()).split(" ") # day short_month long_month year
        self.next_image = 0 # image number to assign the next incoming array to
        self.file_id = 3000 # the file ID to start on. This is iterated once every image cycle.

        self.roi_groups = []
        self.update_num_roi_groups(num_roi_groups)

        self.num_images = None
        self.set_num_images(num_images)
        self.num_rois_per_group = None
        self.update_num_rois_per_group(num_rois_per_group)

        self.user_variable = 0
       
        # self.event_im.connect(self.process_image)
        self.timer.setInterval(10) # go through main loop every 10ms
        self.timer.start()
        self.timer.timeout.connect(self.event_loop)

    @pyqtSlot()
    def event_loop(self):
        """Main function that will be continually triggered for the MAIA to 
        process.
        """
        self.timer.blockSignals(True) # prevent runaway condition if timer adds more events to loop during processing
        QCoreApplication.processEvents() # process all incoming signals before going onto next image
        """ 
        During the processEvents call, all incoming signals will be processed 
        before moving onto the next image. Events processed here include:
            - updating the new ROIs with self.update_roi_coords()
            - recieving new images and adding them to the process queue with self.recieve_image()
            - updating the number of ROI groups with self.update_num_roi_groups()
            - updating the number of ROIs per group with self.update_num_rois_per_group()
        """

        self.process_next_image()

        self.timer.blockSignals(False) # allow the timer to trigger the event loop again

    @pyqtSlot(object, bool)
    def update_roi_coords(self, new_roi_coords, lock_to_group_zero=False):
        """Sets new coordinates for the ROIs. Then sends a signal to the 
        main GUI with the new ROI coordinates.

        Parameters
        ----------
        roi_coords : list of list of list or None
            list of the format [[[x,y,w,h],...],...] where ROI coordinates
            are sorted into their groups. None does not change the ROIs. 
            Default is None.
        lock_to_group_zero : bool
            Whether to lock the geometry of additional ROI groups to group
            zero. Default is False.
        """
        if new_roi_coords != None:
            if lock_to_group_zero:
                x_offsets = [[roi[0]-group[0][0] for roi in group] for group in new_roi_coords]
                y_offsets = [[roi[1]-group[0][1] for roi in group] for group in new_roi_coords]
                offsets = [[list(t) for t in zip(group_x,group_y)] for group_x,group_y in zip(x_offsets,y_offsets)]
                offsets = np.array([[x+[0,0] for x in offsets[0]] for _ in offsets])
                new_roi_coords = [[group[0] for _ in group] for group in new_roi_coords]
                new_roi_coords = list(np.array(offsets)+np.array(new_roi_coords))
            [group.set_roi_coords(coords) for group,coords in zip(self.roi_groups,new_roi_coords)]
        self.send_roi_coords()

    def send_roi_coords(self):
        """Returns the current ROI coordinates back to the GUI."""
        new_roi_coords = [group.get_roi_coords() for group in self.roi_groups]
        self.signal_status_message.emit('Updated ROI coords.: {}'.format(new_roi_coords))
        self.signal_roi_coords.emit(new_roi_coords)
    
    @pyqtSlot(np.ndarray)
    def recieve_image(self,image):
        """Recieves an image from the iGUI and adds it to the processing queue."""
        image_num = self.next_image
        file_id = self.file_id
        self.queue.append([image,file_id,image_num])
        self.signal_status_message.emit('Recieved image {} and placed in queue'.format(image_num))
        self.signal_draw_image.emit(image,image_num)
        self.advance_image_count()
    
    @pyqtSlot()
    def advance_image_count(self):
        """Advances the image count so that the MAIA knows what the next image number is.
        This can either be triggered programatically or by the button on the GUI.
        """
        # self.next_image = (self.next_image+1) % self.num_images
        self.next_image += 1
        if self.next_image >= self.num_images:
            self.next_image = 0
            self.file_id += 1
        self.signal_next_image_num.emit(self.next_image)
        self.signal_file_id.emit(self.file_id)

    @pyqtSlot(object)
    def update_num_roi_groups(self,num_roi_groups):
        """Creates/deletes ROI groups as needed to end up with the specified number.
        ROI data is not cleared when this operation is carried out, so data
        could get out of sync between ROIs in the GUI (but this is represented
        correctly in the data files.)

        Parameters
        ----------
        num_roi_groups : int or None
            The number of ROI groups should contain. If None the number of 
            ROI groups is not changed but the current value is still passed to 
            the iGUI. The default is None.
        """
        # print('MAIA: num roi groups {}'.format(num_roi_groups))
        if num_roi_groups is not None:
            for _ in range(num_roi_groups,len(self.roi_groups)): # delete unneeded ROIs
                self.roi_groups.pop()
            for _ in range(len(self.roi_groups), num_roi_groups): # make new ROIs
                self.roi_groups.append(ROIGroup())
            self.signal_status_message.emit('Updated number of ROI groups to {}'.format(num_roi_groups))
        self.update_num_rois_per_group() # ensures that newly created ROI groups have the right number of ROIs
        num_roi_groups = len(self.roi_groups)
        self.signal_num_roi_groups.emit(num_roi_groups)
        # self.send_roi_coords() # this will be send when updating the number of ROIs per group anyway
    
    def update_num_rois_per_group(self,num_rois_per_group=None):
        """Sets the number of ROIs per ROI group. First the number of ROIs in
        the first group is updated if needed, the all ROI groups are set to 
        have that number of ROIs.
        
        Parameters
        ----------
        num_rois_per_group : int or None
        """
        if num_rois_per_group is not None:
            self.roi_groups[0].set_num_rois(num_rois_per_group)
            self.signal_status_message.emit('Updated number of ROIs/group to {}'.format(num_rois_per_group))
        num_rois_per_group = self.roi_groups[0].get_num_rois()
        for group in self.roi_groups[1:]:
            group.set_num_rois(num_rois_per_group)
        self.signal_num_rois_per_group.emit(num_rois_per_group)
        self.send_roi_coords()

    def process_next_image(self):
        """Move through the next image in the processing queue and processes it."""
        if self.queue:
            [image,file_id,image_num] = self.queue.popleft()
            # print('image_num',image_num)
            # print('next image',self.next_image)
            self.signal_status_message.emit('Started processing image {}'.format(image_num))
            for group in self.roi_groups:
                for roi in group.rois:
                    roi.counts[image_num].append(image[roi.x:roi.x+roi.w,roi.y:roi.y+roi.h].sum())
            self.signal_status_message.emit('Finished processing image {}'.format(image_num))
    
    def get_roi_counts(self):
        """Extracts the ROI counts lists from the ROI objects contained within
        the ROI group objects."""
        counts = [[roi.counts for roi in group.rois] for group in self.roi_groups]
        return counts

    @pyqtSlot(int)
    def recieve_data_request(self,stefan_index):
        """Recieves a data request from the iGUI for data to be passed to the
        STEFANs.
        
        Parameters
        ----------
        stefan_index : int
            The index of the STEFAN that the data should be sent to when it is 
            returned.
        """
        self.signal_status_message.emit('Recieved data request for STEFAN {}'.format(stefan_index))
        counts = self.get_roi_counts()
        self.signal_data_for_stefan.emit(counts,stefan_index)
        self.signal_status_message.emit('Forwarded all data for STEFAN {} to SIMON'.format(stefan_index))
        
    # def set_results_path(self,results_path):
    #     """Sets the results path where data will be outputted in csv files."""
    #     self.results_path = results_path
    
    def set_num_images(self,num_images):
        """Sets the number of images that the MAIA should expect in a 
        sequence."""
        if num_images != self.num_images:
            for group in self.roi_groups:
                group.set_num_images(num_images)
            self.num_images = num_images

    # def get_num_images(self):
    #     """Returns the number of images that the MAIA expects to be passed in
    #     an experimental run."""
    #     pass

    # def get_num_roi_groups(self):
    #     """Returns the number of ROI groups in the MAIA."""
    #     return len(self.roi_groups)

    # def get_num_rois_per_group(self):
    #     """Returns the number of ROIs per group in the MAIA."""
    #     return self.num_rois_per_group

class ROIGroup():
    """Container ROIGroup class used by the MAIA. This stores multiple ROIs
    in a group for easy duplication and analysis of sets of ROIs.
    """
    def __init__(self, x0 = 0, y0 = 0, num_images = 2, num_rois = 1):
        """Initialises the ROIGroup class.

        Parameters
        ----------
        x0 : int
            Origin of the ROIGroup (position of ROI0 within the group).
        y0 : int
            Origin of the ROIGroup (position of ROI0 within the group).
        num_images : int
            The number of images that each ROI in the group should expect to 
            recieve.
        num_rois : int
            The number of ROIs that should be made when the group is created.
            This can always be modified later.
        """
        self.x0 = x0
        self.y0 = y0
        self.num_images = num_images

        self.rois = []
        self.set_num_rois(num_rois)
        self.set_num_images(num_images)

    def set_num_rois(self,num_rois):
        """Creates/deletes ROIs as needed to end up with the specified number.
        ROI data is not cleared when this operation is carried out, so data
        could get out of sync between ROIs in the GUI (but this is represented
        correctly in the data files.)

        Parameters
        ----------
        num_rois : int
            The number of ROIs this group should contain.
        """
        for _ in range(num_rois,len(self.rois)): # delete unneeded ROIs
            self.rois.pop()
        for _ in range(len(self.rois), num_rois): # make new ROIs
            self.rois.append(ROI(1,1,4,4,num_images=self.num_images))

    def get_num_rois(self):
        return len(self.rois)
    
    def set_num_images(self,num_images):
        """Passes the updated number of images for each ROI to expect to the 
        ROI objects. If this number has changed, the ROI will clear all data.

        Parameters
        ----------
        num_images : int
            Number of images for each ROI to expect.
        """
        for roi in self.rois:
            roi.set_num_images(num_images)

    def get_roi_coords(self):
        """Returns a list of lists containing the coordinates of ROIs in this
        ROIGroup.

        Returns
        -------
        list : list of the format [[[x,y,w,h],...] where ROI coordinates are 
               contained in their own list.
        """
        return [roi.get_coords() for roi in self.rois]

    def set_roi_coords(self,coords):
        """Sets the coordinates for the ROIs in the group.

        Parameters
        ----------
        coords : list of lists
            list of the format [[[x,y,w,h],...] where ROI coordinates are 
            contained in their own list.
        """
        [roi.set_coords(coords) for roi,coords in zip(self.rois,coords)]

class ROI():
    """Container ROI class used by the MAIA. This class should perform no 
    analysis and should only be used to easily store and retrieve data. It will
    be run in the same thread as the MAIA.
    """
    def __init__(self, x, y, width, height, threshold=1000, autothresh = True,
                 plot = True, num_images=1):
        self.x = x
        self.y = y
        self.w = width
        self.h = height
        self.t = threshold
        self.autothresh = autothresh
        self.plot = plot

        self.counts = [[]] # List to store the counts in. Each element is the list for each image.
        self.num_images = None
        self.set_num_images(num_images)

    def get_coords(self):
        """Returns the coordinates of the ROI.

        Returns
        -------
        list : list containing the coordinates of the ROI in the form [x,y,w,h]
        """
        return [self.x,self.y,self.w,self.h]
    
    def set_coords(self,coords):
        """Set the coordinates defining the position of the ROI.

        Parameters
        ----------
        coords : list
            list containing the coordinates of the ROI in the form [x,y,w,h]
        """
        [self.x,self.y,self.w,self.h] = coords

    def set_num_images(self,num_images):
        """Creates the correct number of elements in the counts list to 
        reflect the number of images set. Data is deleted if the number of 
        images is changed to avoid things going out of sync.
        
        Parameters
        ----------
        num_images : int
            The number of images the roi should expect to recieve in a sequence.
        """
        if num_images != self.num_images:
            self.counts = [[] for _ in range(num_images)]
            self.num_images = num_images
        
    def clear_data(self):
        """Deletes all current counts data stored in the ROI.
        """
        self.counts = [[] for _ in range(len(self.counts))]

    def calculate_occupancy(self):
        """Processess the counts and determines if the roi was occupied or
        unoccupied for each image.
        
        Returns
        -------
        list of list
            Same format as the ROI.counts list but in binary occupations.
        """
        self.occupancy = [list(x > self.t for x in y) for y in self.counts]
        return self.occupancy
    
    def add_counts(self, counts, image):
        """Adds a counts value to the corresponding list in the `counts` 
        attribute which is a list of lists.
        
        Parameters
        ----------
        counts : int
            The number of counts to store in the list.
            
        image : int
            The image number that the counts corresponds to. This is checked 
            against the `next_image` attribute, and nothing will be stored if 
            this does not match to prevent the images getting out of sync."""
        
        if image == self.next_image:
            self.counts[image].append(counts)
            self.next_image = (self.next_image+1)%self.num_images
        else:
            print('ignoring counts because next_image is {}'.format(self.next_image))