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
    seq   - an instance of sequencePreviewer.Previewer
    n     - the initial run ID number
    m     - the number of images taken per sequence
    k     - the number of images taken already"""
    im_save = pyqtSignal(np.ndarray) # send an incoming image to saver
    Dxstate = 'unknown' # current state of DExTer

    def __init__(self, camra, saver, saiaw, seq, n=0, m=1, k=0):
        super().__init__()
        self._n = n # the run #
        self._m = m # # images per run
        self._k = k # # images received
        self.cam = camra # Andor camera control
        self.cam.AcquireEnd.connect(self.receive) # receive the most recent image
        self.sv = saver  # image saver
        self.im_save.connect(self.sv.add_item) # separate signal to avoid risk of the slot being disconnected elsewhere
        self.sv.start()  # constantly checks queue, when an image to save is added to the queue, it saves it to a file.
        self.sw = saiaw  # image analysis settings gui
        self.sw.m_changed.connect(self.set_m)
        self.cam.SettingsChanged.connect(self.sw.CCD_stat_edit)
        self.cam.ROIChanged.connect(self.sw.pic_size_text_edit)
        self.seq = seq   # sequence editor
        
        self.server = PyServer(host='') # server will run continuously on a thread
        self.server.dxnum.connect(self.set_n) # signal gives run number
        self.server.start()

        # set a timer to update the dates 1s after midnight:
        t0 = time.localtime()
        QTimer.singleShot((86401 - 3600*t0[3] - 60*t0[4] - t0[5])*1e3, 
            self.reset_dates)
            
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
        """change the Dexter run number to the new value"""
        # if dxn != str(self._n+1):
        #     logger.warning('Lost sync: Dx %s /= master %s'%(dxn, self._n+1))
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
            self.sw.mw[i].event_im.emit(im)
        self._k += 1 # another image was taken

    def unsync_receive(self, im=0):
        """Receive an image array to be saved and analysed.
        Count the number of images taken and use this to set the
        DExTer file number in all associated modules."""
        self.receive(im)
        if self._k % self._m == 0:
            self.server.dxnum.emit(str(self._n + 1)) 
        
    def mr_receive(self, im=0):
        """Receive an image as part of a multirun.
        Update the Dexter file number in all associated modules,
        then send the image array to be saved and analysed."""
        self.sv.dfn = str(self._n) # Dexter file number
        imn = self._k % self._m # ID number of image in sequence
        self.sv.imn = str(imn) 
        self.im_save.emit(im)
        if self.seq.mr.ind % (self.seq.mr.nomit + self.seq.mr.nhist) >= self.seq.mr.nomit:
            for i in self.sw.find(imn):
                self.sw.mw[i].image_handler.fid = self._n
                self.sw.mw[i].event_im.emit(im)
        self._k += 1 # another image was taken

    def reset_dates(self):
        """Make sure that the dates in the image saving and analysis 
        programs are correct."""
        t0 = time.localtime()
        self.sv.date = time.strftime(
                "%d %b %B %Y", t0).split(" ") # day short_month long_month year
        self.sw.reset_dates(self.sv.date)
        QTimer.singleShot((86401 - 3600*t0[3] - 60*t0[4] - t0[5])*1e3, 
            self.reset_dates) # set the next timer to reset dates
    
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


    #### multirun ####
    
    def multirun_go(self, toggle):
        """Initiate the multi-run: omit N files, save a histogram of M files, and
        repeat for the user variables in the list. A new sequence is generated for 
        each multirun run. These are sent via TCP and then run. Once the multirun
        has started it"""
        r = self.seq.mr.ind % (self.seq.mr.nomit + self.seq.mr.nhist) # ID of run in repetition cycle
        if toggle and self.seq.mr.check_table() and self.sw.check_reset():
            for mw in self.sw.mw + self.sw.rw:
                mw.plot_current_hist(mw.image_handler.histogram)
                mw.clear_varplot()
                mw.multirun = True
            remove_slot(self.cam.AcquireEnd, self.receive, False) # only receive if not in '# omit'
            remove_slot(self.cam.AcquireEnd, self.mr_receive, True)
            self.seq.mr.ind = 0 # counter for how far through the multirun we are
            tableitem = self.seq.mr.table.item(self.seq.mr.ind, 0) # returns None if no cell at this index
            self.seq.mr.progress.emit(       # update progress label
                'multirun measure %s: %s: %s, omit %s of %s files, %s of %s histogram files, 0%% complete'%(
                    self.seq.mr.stats['measure'], self.seq.mr.stats['Variable label'], 
                    tableitem.text() if tableitem else '', 0,
                    self.seq.mr.nomit, 0, self.seq.mr.nhist))
            self.seq.mr.mrtr = self.seq.mr.tr.copy() # take the current loaded sequence as the base for the multirun
            # make list of sequences as messages to send and the order:
            self.seq.mr.get_all_sequences()
            # save log file with the parameters used for this multirun:
            os.makedirs(os.path.join(self.sv.results_path, self.seq.mr.stats['measure_prefix']), exist_ok=True)
            self.seq.mr.save_mr_params(os.path.join(self.sv.results_path, os.path.join(self.seq.mr.stats['measure_prefix'],
                self.seq.mr.stats['measure_prefix']+'params.csv')))
            self._k = 0 # reset image per run count
            # insert TCP messages at the front of the queue: once the multirun starts don't interrupt it.
            repeats = self.seq.mr.nomit + self.seq.mr.nhist
            mr_queue = [] # list of TCP messages for the whole multirun
            for v in range(self.seq.mr.nrows): # use different last time step during multirun
                mr_queue += [[TCPENUM['TCP load last time step'], self.seq.mr.stats['Last time step run']+'0'*2000],
                    [TCPENUM['TCP load sequence from string'], self.seq.mr.msglist[v]]] + [
                    [TCPENUM['Run sequence'], 'multirun run '+str(self._n + r + repeats*v)+'\n'+'0'*2000] for r in range(repeats)
                    ] + [[TCPENUM['TCP read'], 'save and reset histogram\n'+'0'*2000]]
            # reset last time step for the last run:
            mr_queue.insert(len(mr_queue) - 2, [TCPENUM['TCP load last time step'], self.seq.mr.stats['Last time step end']+'0'*2000])
            mr_queue += [[TCPENUM['TCP read'], 'confirm last multirun run\n'+'0'*2000], 
                [TCPENUM['TCP read'], 'end multirun '+str(self.seq.mr.stats['measure'])+'\n'+'0'*2000]]
            self.server.priority_messages(mr_queue)
            self.seq.mr.stats['runs included'][0].append(self._n) # keep track of which runs are in the multirun.
        else: # pause the multi-run
            remove_slot(self.cam.AcquireEnd, self.mr_receive, False)
            remove_slot(self.cam.AcquireEnd, self.receive, True) # process every image
            self.server.msg_queue = [] # remove all messages from the queue 
            for mw in self.sw.mw + self.sw.rw:
                mw.multirun = False
            tableitem = self.seq.mr.table.item(self.seq.mr.ind, 0)
            self.seq.mr.progress.emit(       # update progress label
                'STOPPED - multirun measure %s: %s: %s, omit %s of %s files, %s of %s histogram files, %.3g %% complete'%(
                    self.seq.mr.stats['measure'], self.seq.mr.stats['Variable label'], 
                    tableitem.text() if tableitem else '', 
                    r if r < self.seq.mr.nomit else self.seq.mr.nomit, self.seq.mr.nomit,
                    r - self.seq.mr.nomit if r > self.seq.mr.nomit else 0, self.seq.mr.nhist,
                    self.seq.mr.ind / (self.seq.mr.nomit + self.seq.mr.nhist) / self.seq.mr.nrows*100))

    def multirun_resume(self, status):
        """Resume the multi-run where it was left off.
        If the multirun is already running, do nothing."""
        if 'multirun' in status: 
            remove_slot(self.cam.AcquireEnd, self.receive, False) # only receive if not in '# omit'
            remove_slot(self.cam.AcquireEnd, self.mr_receive, True)
            self._k = 0 # reset image per run count
            repeats = self.seq.mr.nomit + self.seq.mr.nhist
            r = self.seq.mr.ind % repeats  # repeat
            v = self.seq.mr.ind // repeats # variable
            if v > self.seq.mr.nrows - 1: v = self.seq.mr.nrows - 1
            mr_queue = [[TCPENUM['TCP load last time step'], self.seq.mr.stats['Last time step run']+'0'*2000],
                [TCPENUM['TCP load sequence from string'], self.seq.mr.msglist[v]]]
            mr_queue += [[TCPENUM['Run sequence'], 'multirun run '+str(self._n + i)+'\n'+'0'*2000] for i in range(v + r + 1, v+1)
                ] + [[TCPENUM['TCP read'], 'save and reset histogram\n'+'0'*2000]]
            for var in range(v, self.seq.mr.nrows):
                mr_queue += [[TCPENUM['TCP load sequence from string'], self.seq.mr.msglist[var]]] + [
                    [TCPENUM['Run sequence'], 'multirun run '+str(self._n + r + repeats*var)+'\n'+'0'*2000] for r in range(repeats)
                    ] + [[TCPENUM['TCP read'], 'save and reset histogram\n'+'0'*2000]]
            mr_queue.insert(len(mr_queue) - 2, [TCPENUM['TCP load last time step'], self.seq.mr.stats['Last time step end']+'0'*2000])
            mr_queue += [[TCPENUM['TCP read'], 'confirm last multirun run\n'+'0'*2000], 
                [TCPENUM['TCP read'], 'end multirun '+str(self.seq.mr.stats['measure'])+'\n'+'0'*2000]]
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
        self._k = 0
        index = self.seq.mr.get_next_index(self.seq.mr.ind)
        r = self.seq.mr.ind % (self.seq.mr.nomit + self.seq.mr.nhist) # repeat
        v = self.seq.mr.ind // (self.seq.mr.nomit + self.seq.mr.nhist) # variable
        if r >= self.seq.mr.nomit: 
            self.seq.mr.stats['runs included'][index].append(self._n) # include this run in the multirun
          
        try:
            uv  = self.seq.mr.table.item(v, 0).text() # get user variable 
        except AttributeError as e: 
            logger.error('Multirun step could not extract user variable from table:\n'+str(e))
            uv = ''
        self.seq.mr.ind += 1
        r = self.seq.mr.ind % (self.seq.mr.nomit + self.seq.mr.nhist)
        self.seq.mr.progress.emit(       # update progress label
            'multirun measure %s: %s: %s, omit %s of %s files, %s of %s histogram files, %.3g %% complete'%(
                self.seq.mr.stats['measure'], self.seq.mr.stats['Variable label'], uv, 
                r if r < self.seq.mr.nomit else self.seq.mr.nomit, self.seq.mr.nomit, 
                r - self.seq.mr.nomit if r > self.seq.mr.nomit else 0, self.seq.mr.nhist, 
                self.seq.mr.ind / (self.seq.mr.nomit + self.seq.mr.nhist) / self.seq.mr.nrows*100))
                
    def multirun_savehist(self, msg):
        """end of histogram: fit, save, and reset --- check this doesn't miss an image if there's lag"""
        v = self.seq.mr.ind // (self.seq.mr.nomit + self.seq.mr.nhist) - 1 # previous variable
        try:
            prv = self.seq.mr.table.item(v, 0).text() # get user variable from the previous row
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
                    'Histogram data in '+ self.seq.mr.stats['measure_prefix']+'\\'+mw.name + 
                    str(v+self.seq.mr.stats['1st hist ID']) + '.csv')
        # save and reset the histograms, make sure to do reimage windows first!
        for mw in self.sw.rw + self.sw.mw: 
            mw.save_hist_data(save_file_name=os.path.join(
                self.sv.results_path, os.path.join(self.seq.mr.stats['measure_prefix'], mw.name + 
                    str(v+self.seq.mr.stats['1st hist ID']) + '.csv')), confirm=False) # save histogram
            mw.image_handler.reset_arrays() # clear histogram
        
    def multirun_end(self, msg):
        """At the end of the multirun, save the plot data and reset"""
        for mw in self.sw.rw + self.sw.mw:
            mw.save_varplot(save_file_name=os.path.join(
                self.sv.results_path, os.path.join(self.seq.mr.stats['measure_prefix'], 
                    mw.name + str(self.seq.mr.stats['measure_prefix']) + '.dat')), 
                confirm=False) # save measure file
            # reconnect previous signals
            mw.set_bins() # reconnects signal with given histogram binning settings
            mw.multirun = False
        # suggest new multirun measure ID and prefix
        self.seq.mr.measures['measure'].setText(str(self.seq.mr.stats['measure']+1))
        self.seq.mr.measures['measure_prefix'].setText('Measure'+str(self.seq.mr.stats['measure']+1)+'_')  
        self.multirun_go(False) # reconnect signals
        self.seq.mr.ind = 0
        # save over log file with the parameters used for this multirun (now including run numbers):
        self.seq.mr.save_mr_params(os.path.join(self.sv.results_path, os.path.join(self.seq.mr.stats['measure_prefix'],
            self.seq.mr.stats['measure_prefix']+'params.csv')))