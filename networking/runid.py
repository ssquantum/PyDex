"""Dextr - task managing for PyDex
Stefan Spence 11/10/19

 - control the run number ID for experimental runs
 - emit signals between modules when images are taken
 - keep other modules synchronised
"""
import time
import os
import numpy as np
try:
    from PyQt4.QtCore import QThread, pyqtSignal, QTimer
    from PyQt4.QtGui import QMessageBox
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal, QTimer
    from PyQt5.QtWidgets import QMessageBox
from networker import PyServer, remove_slot, TCPENUM
import logging
logger = logging.getLogger(__name__)

class runnum(QThread):
    """Take ownership of the run number that is
    synchronised between modules of PyDex.
    By running this on a separated thread the 
    main GUI should not freeze up. PyQt signal/slot
    architecture has a queue in the eventloop to 
    ensure function requests are not missed.
    keyword arguments:
    camra - an instance of ancam.cameraHandler.camera
    saver - an instance of savim.imsaver.event_handler
    saiaw - an instance of settingsgui.settings_window
    check - an instance of atomChecker.atom_window
    seq   - an instance of sequencePreviewer.Previewer
    n     - the initial run ID number
    m     - the number of images taken per sequence
    k     - the number of images taken already"""
    im_save = pyqtSignal(np.ndarray) # send an incoming image to saver
    Dxstate = 'unknown' # current state of DExTer

    def __init__(self, camra, saver, saiaw, check, seq, n=0, m=1, k=0):
        super().__init__()
        self._n = n # the run number
        self._m = m # # images per run
        self._k = k # # images received
        self.multirun = False # status of whether in multirun or not
        self.cam = camra # Andor camera control
        self.cam.AcquireEnd.connect(self.receive) # receive the most recent image
        self.sv = saver  # image saver
        self.im_save.connect(self.sv.add_item) # separate signal to avoid risk of the slot being disconnected elsewhere
        self.sv.start()  # constantly checks queue, when an image to save is added to the queue, it saves it to a file.
        self.sw = saiaw  # image analysis settings gui
        self.sw.m_changed.connect(self.set_m)
        self.sw.CCD_stat_edit(self.cam.emg, self.cam.pag, self.cam.Nr, True) # give image analysis the camera settings
        self.cam.SettingsChanged.connect(self.sw.CCD_stat_edit)
        self.cam.ROIChanged.connect(self.sw.cam_pic_size_changed) # triggers pic_size_text_edit()
        self.check = check  # atom checker for ROIs, trigger experiment
        self.check.rh.shape = (self.sw.stats['pic_width'], self.sw.stats['pic_height'])
        self.check.nrois_edit.setText(str(len(self.sw.stats['ROIs'])))
        self.cam.ROIChanged.connect(self.check.rh.cam_pic_size_changed)
        self.check.rh.resize_rois(self.sw.stats['ROIs'])
        self.sw.bias_changed.connect(self.check.rh.set_bias)
        self.check.roi_values.connect(self.sw.set_rois)
        self.seq = seq   # sequence editor
        
        self.server = PyServer(host='') # server will run continuously on a thread
        self.server.dxnum.connect(self.set_n) # signal gives run number
        self.server.start()

        self.trigger = PyServer(host='', port=8088) # software trigger using TCP
            
    def reset_server(self, force=False):
        """Check if the server is running. If it is, don't do anything, unless 
        force=True, then stop and restart the server. If the server isn't 
        running, then start it."""
        if self.server.isRunning():
            if force:
                self.server.msg_queue = []
                self.server.close()
                self.server.start()
        else: self.server.start()
            
    def set_n(self, dxn):
        """Change the Dexter run number to the new value.
        If it's during a multirun, check that the right number of 
        images were taken in the last run."""
        self._n = int(dxn)
    
    def set_m(self, newm):
        """Change the number of images per run"""
        if newm > 0:
            self._m = int(newm)
        elif newm == 0:
            self._m = 2

    def receive(self, im=0):
        """Update the Dexter file number in all associated modules,
        then send the image array to be saved and analysed."""
        self.sv.dfn = str(self._n) # Dexter file number
        imn = self._k % self._m # ID number of image in sequence
        self.sv.imn = str(imn) 
        self.im_save.emit(im)
        for i in self.sw.find(imn): # find the histograms that use this image
            self.sw.mw[i].image_handler.fid = self._n
            # (array, False if too many images were taken or if we're checking for atoms)
            self.sw.mw[i].event_im.emit(im, self._k < self._m and not self.check.checking)
        self._k += 1 # another image was taken

    def unsync_receive(self, im=0):
        """Receive an image array to be saved and analysed.
        Count the number of images taken and use this to set the
        DExTer file number in all associated modules."""
        self.receive(im)
        if self._k % self._m == 0:
            self._k = 0
            self.server.dxnum.emit(str(self._n + 1)) 
        
    def mr_receive(self, im=0):
        """Receive an image as part of a multirun.
        Update the Dexter file number in all associated modules,
        then send the image array to be saved and analysed."""
        self.sv.dfn = str(self._n) # Dexter file number
        imn = self._k % self._m # ID number of image in sequence
        self.sv.imn = str(imn) 
        self.im_save.emit(im)
        if self.seq.mr.ind % (self.seq.mr.mr_param['# omitted'] + self.seq.mr.mr_param['# in hist']) >= self.seq.mr.mr_param['# omitted']:
            for i in self.sw.find(imn):
                self.sw.mw[i].image_handler.fid = self._n
                self.sw.mw[i].event_im.emit(im, self._k < self._m and not self.check.checking)
        self._k += 1 # another image was taken

    def check_receive(self, im=0):
        """Receive image for atom checker, don't save but just pass on"""
        self.check.event_im.emit(im)

    def reset_dates(self, t0):
        """Make sure that the dates in the image saving and analysis 
        programs are correct."""
        date = time.strftime("%d %b %B %Y", t0).split(" ")
        self.sv.reset_dates(self.sv.config_fn, date=date)
        self.sw.reset_dates(date)
        return ' '.join([date[0]] + date[2:])
    
    def synchronise(self, option='', verbose=0):
        """Check the run number in each of the associated modules.
        option: 'reset' = if out of sync, reset to master's run #
                'popup' = if out of sync, create pop-up dialog
                    to ask the user whether to reset."""
        checks = []
        if self.sv.dfn != str(self._n):
            checks.append('Lost sync: Image saver # %s /= run # %s'%(
                                self.sv.dfn, self._n))
        for mw in self.sw.mw:
            if mw.image_handler.fid != self._n:
                checks.append('Lost sync: Image analysis # %s /= run # %s'%(
                            mw.image_handler.fid, self._n))
        for rw in self.sw.rw:
            if (rw.ih1.fid != self._n or rw.ih2.fid != self._n):
                checks.append('Lost sync: Re-image windows # %s, %s /= run # %s'%(
                            rw.ih1.fid, rw.ih2.fid, self._n))
        # if self._k != self._n*self._m + self._k % self._m:
        #     checks.append('Lost sync: %s images taken in %s runs'%(
        #             self._k, self._n))
        # also check synced with DExTer

        if verbose:
            for message in checks:
                print(message)

        if option == 'popup':
            reply = QMessageBox.question(self, 'Confirm Reset',
            "\n".join(checks) + \
            "Do you want to resynchronise the run # to %s?"%self._n, 
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                return checks
        if option == 'reset' or (option == 'popup' and reply == QMessageBox.Yes):
            self.sv.dfn = str(self._n)
            for mw in self.sw.mw:
                mw.image_handler.fid = self._n
            for rw in self.sw.rw:
                rw.ih1.fid = self._n
                rw.ih2.fid = self._n
            self._k = self._n * self._m # number images that should've been taken
        return checks

    #### atom checker ####

    def atomcheck_go(self, toggle=True, dt=100e-3):
        """Disconnect camera images from analysis, change the camera mode
        to internal trigger and redirect the images to the atom checker.
        dt: time between camera exposures (seconds). Exposure time is set
            by the camera config file."""
        if self.cam.initialised > 1:
            if self.cam.AF.GetStatus() == 'DRV_ACQUIRING':
                self.cam.AF.AbortAcquisition() # abort the previous acquisition
            self.check.checking = True
            self.trigger.msg_queue = [] # in case there was a previous trigger that wasn't sent
            self.trigger.start() # start server for TCP to send msg when atoms loaded
            # redirect images from analysis to atom checker
            remove_slot(self.cam.AcquireEnd, self.receive, False)
            remove_slot(self.cam.AcquireEnd, self.mr_receive, False)
            remove_slot(self.cam.AcquireEnd, self.check_receive, True)
            # set camera to take an exposure every dt seconds
            self.cam.AF.SetKineticCycleTime(dt) # time waiting between exposures
            self.cam.AF.SetTriggerMode(0) # internal trigger

            self.cam.start() # run till abort keeps taking images
            if self.check.timer.t0 > 0: # if timeout is set, set a timer
                self.check.timer.singleShot(self.check.timer.t0*1e3, self.check.send_trigger)

    #### multirun ####
    
    def multirun_go(self, toggle):
        """Initiate the multi-run: omit N files, save a histogram of M files, and
        repeat for the user variables in the list. A new sequence is generated for 
        each multirun run. These are sent via TCP and then run. Once the multirun
        has started it"""
        r = self.seq.mr.ind % (self.seq.mr.mr_param['# omitted'] + self.seq.mr.mr_param['# in hist']) # ID of run in repetition cycle
        if toggle: # and self.sw.check_reset() < now will auto reset (so you can queue up multiruns)
            try: # take the multirun parameters from the queue (they're added to the queue in master.py)
                self.seq.mr.mr_param, self.seq.mr.mrtr, self.seq.mr.mr_vals = self.seq.mr.mr_queue.pop(0) # parameters, sequence, values
            except IndexError as e:
                logger.error('runid.py could not start multirun because no multirun was queued.\n'+str(e))
                return 0
                
            results_path = os.path.join(self.sv.results_path, self.seq.mr.mr_param['measure_prefix'])
            if os.path.isdir(results_path) and self.seq.mr.mr_param['1st hist ID'] == 0: 
                # this measure exists, check if user wants to overwrite
                reply = QMessageBox.question(self.seq.mr, 'Confirm Overwrite',
                    "Results path already exists, do you want to overwrite the files?\n"+results_path,
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply == QMessageBox.No:
                    self.multirun = False
                    return 0
            remove_slot(self.cam.AcquireEnd, self.receive, False) # only receive if not in '# omit'
            remove_slot(self.cam.AcquireEnd, self.mr_receive, True)
            self.seq.mr.ind = 0 # counter for how far through the multirun we are
            self._k = 0 # reset image per run count
            try:
                uv = self.seq.mr.mr_vals[0][0]
            except IndexError: uv = 'IndexError'
            self.seq.mr.progress.emit(       # update progress label
                'multirun measure %s: %s: %s, omit %s of %s files, %s of %s histogram files, 0%% complete'%(
                    self.seq.mr.mr_param['measure'], self.seq.mr.mr_param['Variable label'], 
                    uv, 0, self.seq.mr.mr_param['# omitted'], 0, self.seq.mr.mr_param['# in hist']))
            # save log file with the parameters used for this multirun:
            os.makedirs(results_path, exist_ok=True)
            # save sequences and make list of messages to send and the order:
            self.seq.mr.mrtr.write_to_file(os.path.join(results_path, self.seq.mr.mr_param['measure_prefix'] + '_base.xml'))
            self.seq.mr.get_all_sequences(save_dir=results_path)
            self.seq.mr.save_mr_params(os.path.join(results_path, self.seq.mr.mr_param['measure_prefix'] + 
                'params' + str(self.seq.mr.mr_param['1st hist ID']) + '.csv'))
            for mw in self.sw.mw + self.sw.rw:
                mw.image_handler.reset_arrays() # gets rid of old data
                mw.histo_handler.bf = None
                mw.plot_current_hist(mw.image_handler.histogram, mw.hist_canvas)
                mw.clear_varplot()
                mw.multirun = True
                log_file_path = os.path.join(results_path, 
                    mw.name + str(self.seq.mr.mr_param['measure_prefix']) + '.dat')
                if not os.path.isfile(log_file_path):# start measure file, stores plot data
                    mw.save_varplot(save_file_name=log_file_path, confirm=False) 
            
            # insert TCP messages at the front of the queue: once the multirun starts don't interrupt it.
            repeats = self.seq.mr.mr_param['# omitted'] + self.seq.mr.mr_param['# in hist']
            mr_queue = [] # list of TCP messages for the whole multirun
            for v in range(len(self.seq.mr.mr_vals)): # use different last time step during multirun
                mr_queue += [[TCPENUM['TCP load last time step'], self.seq.mr.mr_param['Last time step run']+'0'*2000],
                    [TCPENUM['TCP load sequence from string'], self.seq.mr.msglist[v]]] + [
                    [TCPENUM['Run sequence'], 'multirun run '+str(self._n + r + repeats*v)+'\n'+'0'*2000] for r in range(repeats)
                    ] + [[TCPENUM['TCP read'], 'save and reset histogram\n'+'0'*2000]]
            # reset last time step for the last run:
            mr_queue.insert(len(mr_queue) - 2, [TCPENUM['TCP load last time step'], self.seq.mr.mr_param['Last time step end']+'0'*2000])
            mr_queue += [[TCPENUM['TCP read'], 'confirm last multirun run\n'+'0'*2000], 
                [TCPENUM['TCP read'], 'end multirun '+str(self.seq.mr.mr_param['measure'])+'\n'+'0'*2000]]
            for enum, text in mr_queue:
                self.server.add_message(enum, text)
            self.seq.mr.mr_param['runs included'][0].append(self._n) # keep track of which runs are in the multirun.
        else: # pause the multi-run
            remove_slot(self.cam.AcquireEnd, self.mr_receive, False)
            remove_slot(self.cam.AcquireEnd, self.receive, True) # process every image
            self.server.msg_queue = [] # remove all messages from the queue 
            self.cam.AF.AbortAcquisition()
            for mw in self.sw.mw + self.sw.rw:
                mw.multirun = False
            self.multirun = False
            self.seq.mr.progress.emit('STOPPED. Multirun has been interrupted.')

    def multirun_resume(self, status):
        """Resume the multi-run where it was left off.
        If the multirun is already running, do nothing."""
        if 'multirun' in status: 
            remove_slot(self.cam.AcquireEnd, self.receive, False) # only receive if not in '# omit'
            remove_slot(self.cam.AcquireEnd, self.mr_receive, True)
            self._k = 0 # reset image per run count
            repeats = self.seq.mr.mr_param['# omitted'] + self.seq.mr.mr_param['# in hist']
            r = self.seq.mr.ind % repeats  # repeat
            v = self.seq.mr.ind // repeats # variable
            nrows = len(self.seq.mr.mr_vals)
            if v > nrows - 1: v = nrows - 1
            # finish this histogram
            mr_queue = [[TCPENUM['TCP load last time step'], self.seq.mr.mr_param['Last time step run']+'0'*2000],
                [TCPENUM['TCP load sequence from string'], self.seq.mr.msglist[v]]]
            mr_queue += [[TCPENUM['Run sequence'], 'multirun run '+str(self._n + i)+'\n'+'0'*2000] for i in range(repeats - r + 1)
                ] + [[TCPENUM['TCP read'], 'save and reset histogram\n'+'0'*2000]]
            for var in range(v+1, nrows): # add the rest of the multirun
                mr_queue += [[TCPENUM['TCP load sequence from string'], self.seq.mr.msglist[var]]] + [
                    [TCPENUM['Run sequence'], 'multirun run '+str(self._n + r + repeats*var)+'\n'+'0'*2000] for r in range(repeats)
                    ] + [[TCPENUM['TCP read'], 'save and reset histogram\n'+'0'*2000]]
            mr_queue.insert(len(mr_queue) - 2, [TCPENUM['TCP load last time step'], self.seq.mr.mr_param['Last time step end']+'0'*2000])
            mr_queue += [[TCPENUM['TCP read'], 'confirm last multirun run\n'+'0'*2000], 
                [TCPENUM['TCP read'], 'end multirun '+str(self.seq.mr.mr_param['measure'])+'\n'+'0'*2000]]
            self.server.priority_messages(mr_queue) # adds at front of queue
            
    def multirun_step(self, msg):
        """Execute a single run as part of a multirun.
        For the first '# omit' runs, only save the files.
        Then for '# hist' runs, add files to histogram.
        The data for the run is received and processed when the command for the 
        next run is being sent, so the histogram is saved, fitted, and reset
        based on the run number +1.
        repeat this for the user variables in the multirun list,
        then return to normal operation as set by the histogram binning"""
        if self._k != self._m:
            logger.warning('Run %s took %s / %s images.'%(self._n, self._k, self._m))
        self._k = 0
        r = self.seq.mr.ind % (self.seq.mr.mr_param['# omitted'] + self.seq.mr.mr_param['# in hist']) # repeat
        v = self.seq.mr.get_next_index(self.seq.mr.ind) # variable
        try:
            if r >= self.seq.mr.mr_param['# omitted']: 
                self.seq.mr.mr_param['runs included'][v].append(self._n) # include this run in the multirun
            uv = self.seq.mr.mr_vals[v][0] # get user variable 
        except IndexError: 
            if v == len(self.seq.mr.mr_vals):
                uv = self.seq.mr.mr_vals[v-1][0] # get user variable 
            else: uv = 'IndexError'
        self.seq.mr.ind += 1
        r = self.seq.mr.ind % (self.seq.mr.mr_param['# omitted'] + self.seq.mr.mr_param['# in hist'])
        self.seq.mr.progress.emit(       # update progress label
            'multirun measure %s: %s: %s, omit %s of %s files, %s of %s histogram files, %.3g %% complete'%(
                self.seq.mr.mr_param['measure'], self.seq.mr.mr_param['Variable label'], uv, 
                r if r < self.seq.mr.mr_param['# omitted'] else self.seq.mr.mr_param['# omitted'], self.seq.mr.mr_param['# omitted'], 
                r - self.seq.mr.mr_param['# omitted'] if r > self.seq.mr.mr_param['# omitted'] else 0, self.seq.mr.mr_param['# in hist'], 
                self.seq.mr.ind / (self.seq.mr.mr_param['# omitted'] + self.seq.mr.mr_param['# in hist']) / len(self.seq.mr.mr_vals)*100))
                
    def multirun_savehist(self, msg):
        """end of histogram: fit, save, and reset --- check this doesn't miss an image if there's lag"""
        v = self.seq.mr.ind // (self.seq.mr.mr_param['# omitted'] + self.seq.mr.mr_param['# in hist']) - 1 # previous variable
        try:
            prv = self.seq.mr.mr_vals[v][0] # get user variable from the previous row
        except AttributeError as e:     
            logger.error('Multirun step could not extract user variable from table at row %s.\n'%v+str(e))
            prv = ''
        # get best fit on histograms, doing reimage last since their fits depend on the main hists
        for mw in self.sw.mw + self.sw.rw: 
            mw.var_edit.setText(prv) # also updates histo_handler temp vals
            mw.set_user_var() # just in case not triggered by the signal
            mw.bins_text_edit(text='reset') # set histogram bins 
            success = mw.display_fit(fit_method='check action') # get best fit
            if not success:                   # if fit fails, use peak search
                mw.display_fit(fit_method='quick')
                logger.warning('\nMultirun run %s fitting failed. '%self._n +
                    'Histogram data in '+ self.seq.mr.mr_param['measure_prefix']+'\\'+mw.name + 
                    str(v+self.seq.mr.mr_param['1st hist ID']) + '.csv')
            # append histogram stats to measure log file:
            with open(os.path.join(self.sv.results_path, os.path.join(
                    self.seq.mr.mr_param['measure_prefix'], 
                    mw.name + str(self.seq.mr.mr_param['measure_prefix']) + '.dat')), 'a') as f:
                f.write(','.join(list(map(str, mw.histo_handler.temp_vals.values()))) + '\n')
        # save and reset the histograms, make sure to do reimage windows first!
        for mw in self.sw.rw + self.sw.mw: 
            mw.save_hist_data(save_file_name=os.path.join(
                self.sv.results_path, os.path.join(self.seq.mr.mr_param['measure_prefix'], mw.name + 
                    str(v+self.seq.mr.mr_param['1st hist ID']) + '.csv')), confirm=False) # save histogram
            mw.image_handler.reset_arrays() # clear histogram
        
    def multirun_end(self, msg):
        """At the end of the multirun, save the plot data and reset"""
        for mw in self.sw.rw + self.sw.mw:
            # reconnect previous signals
            mw.set_bins() # reconnects signal with given histogram binning settings
            mw.display_fit() # display the empty histograms
            mw.multirun = False
        self.multirun_go(False) # reconnect signals
        self.seq.mr.ind = 0
        # save over log file with the parameters used for this multirun (now including run numbers):
        self.seq.mr.save_mr_params(os.path.join(self.sv.results_path, os.path.join(self.seq.mr.mr_param['measure_prefix'],
            self.seq.mr.mr_param['measure_prefix'] + 'params' + str(self.seq.mr.mr_param['1st hist ID']) + '.csv')))
        self.seq.mr.progress.emit(       # update progress label
            'Finished measure %s: %s.'%(self.seq.mr.mr_param['measure'], self.seq.mr.mr_param['Variable label']))
        self.multirun = False