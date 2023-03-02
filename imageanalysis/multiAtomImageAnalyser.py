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
import os
from copy import copy,deepcopy
# from queue import Queue
from collections import deque
from skimage.filters import threshold_minimum
from dataanalysis import Analyser

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
    signal_num_images = pyqtSignal(int) # sends the number of images back to the GUI
    signal_roi_coords = pyqtSignal([list]) # send ROI coords back to the GUI
    signal_num_roi_groups = pyqtSignal(int) # send the number of ROI groups back to the GUI
    signal_num_rois_per_group = pyqtSignal(int) # send the number of ROIs per group back to the GUI
    signal_data_for_stefan = pyqtSignal(list,int) # send the roi counts to the iGUI for forwarding to a STEFAN (counts,stefan_index)
    signal_data_for_tv = pyqtSignal(list) # send the threshold data to the iGUI for forwarding to the TV
    signal_results_path = pyqtSignal(str) # send the results path to the iGUI
    signal_hist_id = pyqtSignal(int) # send the hist ID to the iGUI
    signal_user_variables = pyqtSignal(list) # send the user variables back to the iGUI
    signal_measure_prefix = pyqtSignal(str) # send the measure prefix to the iGUI
    signal_finished_saving = pyqtSignal() # lets the MAIA unlock the multirun queue when it has finished saving data
    signal_emccd_bias = pyqtSignal(int) # sends the EMCCD bias to the iGUI
    signal_state = pyqtSignal(dict,str) # the state and filename to save it in. Either connects to the iGUI or the rest of PyDex.

    queue = deque() # Double-ended queue to handle images. Images are processed when ready.
    timer = QTimer() # Timer to trigger the updating of queue events

    def __init__(self, results_path='.', num_roi_groups=2, 
                 num_rois_per_group=3,num_images=2):
        super().__init__()
        # most of these settings get overwritten by the iGUI when initalised, but they are here just to prevent errors 
        # if this class is run independently
        self.new_roi_coords = None
        self.next_image = 0 # image number to assign the next incoming array to
        self.file_id = 3000 # the file ID to start on. This is iterated once every image cycle.
        self.should_save = False # whether MAIA should save the data on the next iteration of the event loop
        self.emccd_bias = 0

        self.roi_groups = []
        self.num_images = num_images

        self.copy_im_threshs = [None for _ in range(num_images)]
        print('copy_im_threads',self.copy_im_threshs)

        self.update_num_images(self.num_images)
        self.update_num_roi_groups(num_roi_groups)

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

        self.process_next_image() # processes one image from the queue if it is not empty
        self.save() # only saves data if queue is empty and self.should_save = True

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
        if (new_roi_coords != None) or (lock_to_group_zero):
            if new_roi_coords == None:
                new_roi_coords = self.get_roi_coords()
            if lock_to_group_zero:
                x_offsets = [[roi[0]-group[0][0] for roi in group] for group in new_roi_coords]
                y_offsets = [[roi[1]-group[0][1] for roi in group] for group in new_roi_coords]
                offsets = [[list(t) for t in zip(group_x,group_y)] for group_x,group_y in zip(x_offsets,y_offsets)]
                offsets = np.array([[x+[0,0] for x in offsets[0]] for _ in offsets])
                new_roi_coords = [[group[0] for _ in group] for group in new_roi_coords]
                new_roi_coords = (np.array(offsets)+np.array(new_roi_coords)).tolist() # convert to list because np arrays not serializable when saving state in .jsons
            self.set_roi_coords(new_roi_coords)
        self.send_roi_coords()

    def get_roi_coords(self):
        """Gets the ROI coords from the ROIgroups."""
        return [group.get_roi_coords() for group in self.roi_groups]

    def set_roi_coords(self,new_roi_coords):
        """Sets the ROI coords from a list of new ROI coords by passing the 
        coords through to the relevant ROIgroups.
        
        Parameters
        ----------
        new_roi_coords : list
            List of ROI coords [[[x,y,w,h],...]] for each ROI, sorted by group.
        """
        [group.set_roi_coords(coords) for group,coords in zip(self.roi_groups,new_roi_coords)]

    def send_roi_coords(self):
        """Returns the current ROI coordinates back to the GUI."""
        new_roi_coords = [group.get_roi_coords() for group in self.roi_groups]
        self.signal_status_message.emit('Updated ROI coords.: {}'.format(new_roi_coords))
        self.signal_roi_coords.emit(new_roi_coords)

    @pyqtSlot(str)
    def update_results_path(self,results_path):
        self.results_path = results_path
        self.signal_results_path.emit(results_path)
        self.signal_status_message.emit('Set results path to {}'.format(self.results_path))
    
    @pyqtSlot(int)
    def update_hist_id(self,hist_id):
        self.hist_id = hist_id
        self.signal_hist_id.emit(hist_id)
        self.signal_status_message.emit('Set hist. ID to {}'.format(self.hist_id))

    @pyqtSlot(int)
    def update_file_id(self,file_id):
        self.file_id = file_id
        self.signal_file_id.emit(file_id)
        self.signal_status_message.emit('Set file ID to {}'.format(self.file_id))

    @pyqtSlot(list)
    def update_user_variables(self,user_variables):
        self.user_variables = [float(x) for x in user_variables]
        self.signal_user_variables.emit(self.user_variables)
        self.signal_status_message.emit('Set user variables to {}'.format(self.user_variables))

    @pyqtSlot(str)
    def update_measure_prefix(self,measure_prefix):
        self.measure_prefix = measure_prefix
        self.signal_measure_prefix.emit(measure_prefix)
        self.signal_status_message.emit('Set measure prefix to {}'.format(self.measure_prefix))

    @pyqtSlot(np.ndarray,object,object)
    def recieve_image(self,image,file_id=None,image_num=None):
        """Recieves an image from the iGUI and adds it to the processing queue.
        If the file_id and image num are set then these will be added to the
        queue along with the image and used to set the values for the next 
        image.
        """
        if file_id is None:
            file_id = self.file_id
        if image_num is None:
            image_num = self.next_image
        self.queue.append([image,file_id,image_num])
        self.signal_status_message.emit('Recieved ID {} Im {} and placed in queue'.format(file_id,image_num))
        self.signal_draw_image.emit(image,image_num)
        self.advance_image_count(file_id,image_num)
    
    @pyqtSlot(object,object)
    def advance_image_count(self,file_id=None,image_num=None):
        """Advances the image count so that the MAIA knows what the next image number is.
        This can either be triggered programatically or by the button on the GUI.
        If the file ID and image number are manually specified, then these 
        values will be used to update the next image.
        """
        # self.next_image = (self.next_image+1) % self.num_images
        if file_id is not None:
            self.file_id = file_id
        if image_num is None:
            self.next_image += 1
        else:
            self.next_image = image_num + 1
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
                self.roi_groups.append(ROIGroup(num_images=self.num_images))
            self.signal_status_message.emit('Updated number of ROI groups to {}'.format(num_roi_groups))
        self.update_num_rois_per_group() # ensures that newly created ROI groups have the right number of ROIs
        num_roi_groups = len(self.roi_groups)
        self.signal_num_roi_groups.emit(num_roi_groups)
        # self.send_roi_coords() # this will be send when updating the number of ROIs per group anyway
    
    @pyqtSlot(object)
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
            self.signal_status_message.emit('Started processing ID {} Im {}'.format(file_id,image_num))
            image = image - self.emccd_bias # don't edit in place because this seemed to cause an issue with images not showing in GUI. Maybe not thread safe?
            # print('image min',np.min(image))
            # print('image max',np.max(image))
            image_num_too_big = False
            for group in self.roi_groups:
                for roi in group.rois:
                    try:
                        roi.counts[image_num][file_id] = image[roi.x:roi.x+roi.w,roi.y:roi.y+roi.h].sum()
                    except IndexError: # image_num was not valid for the number of images that MAIA is expecting
                        image_num_too_big = True
            if image_num_too_big:
                self.signal_status_message.emit('Image number {} is greater than max expected images, so this image has been ignored (most likely cause is rearrangement toggle).')
            self.signal_status_message.emit('Finished processing ID {} Im {}'.format(file_id,image_num))
            self.calculate_thresholds()

    def get_roi_counts(self):
        """Extracts the ROI counts lists from the ROI objects contained within
        the ROI group objects."""
        counts = [[roi.counts for roi in group.rois] for group in self.roi_groups]
        return counts

    def get_roi_thresholds(self):
        """Extracts the ROI counts lists from the ROI objects contained within
        the ROI group objects."""
        thresholds = [group.get_threshold_data() for group in self.roi_groups]
        return thresholds

    def calculate_thresholds(self):
        """Calculates the thresholds for ROIs that have Autothresh enabled. 
        This uses the same method as the old code with the exception of not 
        requiring that the threshold be positive. This will be performed after 
        every image for ROIs that need it."""
        
        for group in self.roi_groups:
            for roi in group.rois:
                for image in range(len(roi.counts)):
                    # print(roi.autothreshs)
                    # print('image',image)
                    if roi.autothreshs[image]:
                        values = np.fromiter(roi.counts[image].values(), dtype=float)
                        roi.thresholds[image] = self.calculate_threshold(values)

        for image, im_copy in enumerate(self.copy_im_threshs): # copy values from a different image and set to manual thresh if needed
            if im_copy is not None:
                for group in self.roi_groups:
                    for roi in group.rois:
                        roi.autothreshs[image] = False
                        roi.thresholds[image] = roi.thresholds[im_copy]

    def calculate_threshold(self,counts_data):
        """Automatically choose a threshold based on the counts"""
        try:
            thresh = int(threshold_minimum(np.array(counts_data), 25))
        except (ValueError, RuntimeError, OverflowError):
            try:
                thresh = int(0.5*(max(counts_data) + min(counts_data)))
            except ValueError: # will be triggered if counts_data is empty
                thresh = 1000
        return thresh

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
        data = self.get_analyser_data()
        self.signal_data_for_stefan.emit(data,stefan_index)
        self.signal_status_message.emit('Forwarded all data for STEFAN {} to SIMON'.format(stefan_index))
    
    def get_analyser_data(self):
        """Prepares the MAIA data in the format expected by the Analysers 
        used by the STEFANs and when exporting the data."""
        counts = self.get_roi_counts()
        thresholds = self.get_roi_thresholds()
        roi_coords = self.get_roi_coords()
        return [counts,thresholds,roi_coords]

    # def set_results_path(self,results_path):
    #     """Sets the results path where data will be outputted in csv files."""
    #     self.results_path = results_path
    
    @pyqtSlot(object)
    def update_num_images(self,num_images):
        """Sets the number of images that the MAIA should expect in a 
        sequence."""
        if (num_images != None) and (num_images != self.num_images):
            for group in self.roi_groups:
                group.set_num_images(num_images)

            for _ in range(num_images,len(self.copy_im_threshs)): # delete unneeded copy im data
                self.copy_im_threshs.pop()
            for _ in range(len(self.copy_im_threshs), num_images): # make new copy im data
                self.copy_im_threshs.append(None)

            self.next_image = 0
            self.num_images = num_images
            self.signal_status_message.emit('Set number of images to {}'.format(self.num_images))
        self.signal_next_image_num.emit(self.next_image)
        self.signal_num_images.emit(self.num_images)

    @pyqtSlot(object)
    def update_emccd_bias(self,emccd_bias):
        """Sets the EMCCD bias that the MAIA should subtract from all recieved 
        images."""
        if (emccd_bias != None):
            self.emccd_bias = emccd_bias
            self.signal_status_message.emit('Set EMCCD bias to {}'.format(self.emccd_bias))
        self.signal_emccd_bias.emit(self.emccd_bias)

    @pyqtSlot()
    def recieve_tv_data_request(self):
        self.signal_status_message.emit('Recieved Threshold Viewer data request')
        tv_data = self.get_roi_thresholds()
        self.signal_data_for_tv.emit([tv_data,self.copy_im_threshs])
        self.signal_status_message.emit('Sent Threshold Viewer data to SIMON')
    
    @pyqtSlot(list)
    def recieve_tv_threshold_data(self,threshold_viewer_data):
        """Recieves threhold data from the Threshold Viewer to update the 
        ROIs with."""
        self.signal_status_message.emit('Recieved threshold data from Threshold Viewer')
        
        threshold_data = threshold_viewer_data[0]
        copy_im_threshs = threshold_viewer_data[1]

        # First check that the threshold data is of the correct format.
        if len(threshold_data) != len(self.roi_groups):
            self.signal_status_message.emit('Threshold Viewer data did not have the correct number of ROI groups. Ignoring.')
            return
        elif len(threshold_data[0]) != len(self.roi_groups[0].rois):
            self.signal_status_message.emit('Threshold Viewer data did not have the correct number of ROIs/group. Ignoring.')
            return
        elif len(threshold_data[0][0]) != self.num_images:
            self.signal_status_message.emit('Threshold Viewer data did not have the correct number of images. Ignoring.')
            return
        
        # Now apply the data to the ROIs and recalculate any thresholds that need to be recalculated.
        for group, group_thresh in zip(self.roi_groups,threshold_data):
            group.set_threshold_data(group_thresh)

        self.copy_im_threshs = []
        for image, im_copy in enumerate(copy_im_threshs):
            try:
                im_copy = int(im_copy)
                if image == im_copy:
                    self.copy_im_threshs.append(None) # don't let an image reference itself
                else:
                    self.copy_im_threshs.append(int(im_copy))
            except (TypeError, ValueError):
                self.copy_im_threshs.append(None)

        self.calculate_thresholds()

        # Send updated data back to TV.
        self.recieve_tv_data_request()

    @pyqtSlot(object)
    def request_save(self,hist_id):
        """Sets the flag self.should_save to true, which will result in the 
        data being saved when the image queue is empty.
        
        Parameters
        ----------
        hist_id : int or None
            The file ID to save the data to. MAIA _should_ already know this,
            but this can be respecified to ensure that nothing gets out of
            sync.
        """
        self.should_save = True
        self.update_hist_id(hist_id)
        self.signal_status_message.emit('Recieved save request')

    def save(self):
        """Saves the current ROI data to the path specified by the results 
        path and hist ID. This function actually saves the data; during a
        multirun the request_save function should be used to set the flag
        self.should_save to true, but this will only be done once the image 
        queue is empty."""
        if (self.should_save) and (not self.queue): # only save if should_save is True and queue is empty
            self.signal_status_message.emit('Beginning save process')
            filename = self.results_path+'\MAIA.{}.csv'.format(self.hist_id)
            if os.path.exists(filename):
                self.signal_status_message.emit('Filename {} already exists!'.format(filename))
                files = [f for f in os.listdir(self.results_path) if os.path.isfile(os.path.join(self.results_path, f))]
                files = [f for f in files if 'MAIA.' in f]
                hist_ids = [int(f.split('MAIA.')[1].split('.csv')[0]) for f in files]
                max_hist_id = max(hist_ids)
                self.update_hist_id(max_hist_id+1)
                self.signal_status_message.emit('To avoid data overwrite, hist_id has been set to {}'.format(max_hist_id+1))
                filename = self.results_path+'\MAIA.{}.csv'.format(self.hist_id)
            data = self.get_analyser_data()
            self.signal_status_message.emit('Extracted analyser data')
            analyser = Analyser(data)
            additional_data = self.get_user_variable_dict()
            additional_data['Hist ID'] = self.hist_id
            additional_data['EMCCD bias'] = self.emccd_bias
            additional_data['copy_im_threshs'] = self.copy_im_threshs
            self.signal_status_message.emit('Created Analyser, requesting data save')
            try:
                analyser.save_data(filename,additional_data)
                self.signal_status_message.emit('Saved data to {}'.format(filename))
                self.clear()
                self.should_save = False
                # self.signal_status_message.emit('Sleeping for 10s before unlocking queue (for testing)')
                # time.sleep(10)
                self.signal_status_message.emit('Unlocking multirun queue')
                self.signal_finished_saving.emit()
            except PermissionError:
                self.signal_status_message.emit('Could not save data to {} due to PermissionError. Data has not been cleared. Will keep retrying.'.format(filename))

    def get_user_variable_dict(self):
        """Converts the list of user variables to a dict to be saved with the 
        rest of the output data."""
        user_variable_keys = ['User variable {}'.format(i) for i in range(len(self.user_variables))]
        return dict(zip(user_variable_keys, self.user_variables))

    def clear(self):
        """Clears the counts data stored in the ROIs."""
        [group.clear() for group in self.roi_groups]

    @pyqtSlot()
    def clear_data_and_queue(self):
        self.queue.clear()
        self.clear()
        self.signal_status_message.emit('Cleared data and image queue')

    @pyqtSlot(dict,str)
    def get_state(self,params,filename):
        """Gets the MAIA state and then emits the state and the filename it
        should be stored in.
        
        Parameters
        ----------
        params : dict
            The parameter dictionary to save the state to. This should already
            contain some values from the iGUI, such as STEFAN behaviour and 
            display image number.
        filename : str
            The path to the file that the state should be stored in. This
            will be passed back to the saving function.
        """
        params['roi_coords'] = self.get_roi_coords()
        params['copy_im_threshs'] = self.copy_im_threshs
        params['thresholds'] = self.get_roi_thresholds()
        params['emccd_bias'] = self.emccd_bias
        params['num_images'] = self.num_images
        self.signal_status_message.emit('Prepared state params {}'.format(params))
        self.signal_state.emit(params,filename)

    @pyqtSlot(dict)
    def set_state(self,params):
        """Sets the MAIA state from a params file."""
        self.update_emccd_bias(params['emccd_bias'])
        self.update_num_images(params['num_images'])
        self.make_rois_from_lists(params['roi_coords'],params['thresholds'])
        try: # add things here that don't exist in old state files (different try/except for each)
            self.copy_im_threshs = params['copy_im_threshs']
        except KeyError:
            self.copy_im_threshs = [None for _ in range(self.num_images)]

    def make_rois_from_lists(self,roi_coords,thresholds):
        """Makes the ROI groups and ROIs from a list of ROI coords."""
        self.update_num_roi_groups(len(roi_coords)) # num images set here
        self.update_num_rois_per_group(len(roi_coords[0]))
        self.update_roi_coords(roi_coords)
        self.recieve_tv_threshold_data([thresholds,self.copy_im_threshs])

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
        self.num_images = num_images

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

    def get_threshold_data(self):
        """Returns a list of lists containing the threshold data of ROIs in 
        this ROIGroup. See ROI.get_threshold_data() for format.

        Returns
        -------
        list : list of threshold data
        """
        return [roi.get_threshold_data() for roi in self.rois]

    def set_threshold_data(self,threshold_data):
        """Applies a list of lists containing the threshold data of ROIs in 
        this ROIGroup. See ROI.set_threshold_data() for format.

        Parameters
        ----------
        threshold_data : list 
            list of threshold data for this ROI group
        """
        for roi, roi_thresh in zip(self.rois,threshold_data):
            roi.set_threshold_data(roi_thresh)

    def clear(self):
        """Clears the counts data stored in the ROIs."""
        [roi.clear() for roi in self.rois]

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
        self.plot = plot
        self.default_threshold = threshold
        self.default_autothresh = autothresh

        self.counts = [{}] # List to store the counts in. Each element is the dictionary for each image. Key is the file ID.
        self.thresholds = []
        self.autothreshs = []
        
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
            self.counts = [{} for _ in range(num_images)]

            for _ in range(num_images,len(self.thresholds)): # delete unneeded thresholds
                self.thresholds.pop()
            for _ in range(len(self.thresholds), num_images): # make new thresholds
                self.thresholds.append(self.default_threshold)

            for _ in range(num_images,len(self.autothreshs)): # delete unneeded autothreshs
                self.autothreshs.pop()
            for _ in range(len(self.autothreshs), num_images): # make new autothreshs
                self.autothreshs.append(self.default_autothresh)

            self.num_images = num_images
        
    def clear(self):
        """Deletes all current counts data stored in the ROI.
        """
        self.counts = [{} for _ in range(len(self.counts))]

    def get_threshold_data(self):
        """Returns the thresholds of the ROI alongside whether the thresholds are
        automatic or not.

        Returns
        -------
        list : list of the format [[Im0 thresh, Im0 autothresh], [Im1 thresh, Im1 autothresh], ...]
        """
        return [list(x) for x in list(zip(self.thresholds,self.autothreshs))]

    def set_threshold_data(self,threshold_data):
        """Sets the thresholds of the images in the ROI alongside whether they
        are Autothreshing or not.
        
        Parameters
        ----------
        threshold_data : list
            List of the format [[Im0 thresh, Im0 autothresh], [Im1 thresh, Im1 autothresh], ...]
        """
        [self.thresholds, self.autothreshs] = np.array(threshold_data).T.tolist()

    def calculate_occupancy(self):
        """Processess the counts and determines if the roi was occupied or
        unoccupied for each image.
        
        Returns
        -------
        list of list
            Same format as the ROI.counts list but in binary occupations.
        """
        # TODO will need to be fixed now that using a dict and changed thresholds
        self.occupancy = [list(x > self.t for x in y) for y in self.counts]
        return self.occupancy