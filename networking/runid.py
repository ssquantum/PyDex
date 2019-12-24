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
        self.im_save.connect(self.sv.add_item) # separate signal to avoid interfering
        self.sw = saiaw  # image analysis settings gui
        self.sw.m_changed.connect(self.set_m)
        self.seq = seq   # sequence editor
        
        self.server = PyServer() # server will run continuously on a thread
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
        self.sw.mw[imn].image_handler.fid = self._n
        self.sw.mw[imn].event_im.emit(im)
        self._k += 1 # another image was taken

    def mr_receive(self, im=0):
        """Receive an image as part of a multirun.
        Update the Dexter file number in all associated modules,
        then send the image array to be saved and analysed."""
        self.sv.dfn = str(self._n) # Dexter file number
        imn = self._k % self._m # ID number of image in sequence
        self.sv.imn = str(imn) 
        self.im_save.emit(im)
        if self.seq.mr.ind % (self.seq.mr.nomit + self.seq.mr.nhist) >= self.seq.mr.nomit:
            self.sw.mw[imn].image_handler.fid = self._n
            self.sw.mw[imn].event_im.emit(im)
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
        if self._k != self._n*self._m + self._k % self._m:
            checks.append('Lost sync: %s images taken in %s runs'%(
                    self._k, self._n))
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
            self.seq.mr.progress.emit(       # update progress label
                'multirun measure %s: %s: %s, omit %s of %s files, %s of %s histogram files, 0%% complete'%(
                    self.seq.mr.stats['measure'], self.seq.mr.stats['Variable label'], 
                    self.seq.mr.table.item(self.seq.mr.ind, 0).text(), 0,
                    self.seq.mr.nomit, 0, self.seq.mr.nhist))
            self.seq.mr.mrtr = self.seq.mr.tr # take the current loaded sequence as the base for the multirun
            # make list of sequences as messages to send and the order:
            self.seq.mr.get_all_sequences()
            # insert TCP messages at the front of the queue: once the multirun don't interrupt it.
            self.server.priority_messages([[TCPENUM['TCP load sequence from string'], self.seq.mr.msglist[self.seq.mr.get_next_index(self.seq.mr.ind)]], 
                    [TCPENUM['Run sequence'], 'multirun run '+str(self._n)]])
            self.seq.mr.rnums.append(self._n) # keep track of which runs are in the multirun.
        else: # pause the multi-run
            remove_slot(self.cam.AcquireEnd, self.mr_receive, False)
            remove_slot(self.cam.AcquireEnd, self.receive, True) # process every image
            try:
                for i in range(len(self.server.msg_queue)): # remove the multirun from the message queue.
                    if bytes('multirun run '+str(self._n), 'mbcs') in self.server.msg_queue[i][2]:
                        self.server.msg_queue.pop(i) 
                        break
            except IndexError as e: logger.error('Pause multirun: failed to remove commands from message queue.\n'+str(e))
            self.seq.mr.progress.emit(       # update progress label
                'STOPPED - multirun measure %s: %s: %s, omit %s of %s files, %s of %s histogram files, %.3g %% complete'%(
                    self.seq.mr.stats['measure'], self.seq.mr.stats['Variable label'], 
                    self.seq.mr.table.item(self.seq.mr.ind, 0).text(), 
                    r if r < self.seq.mr.nomit else self.seq.mr.nomit, self.seq.mr.nomit,
                    r - self.seq.mr.nomit if r > self.seq.mr.nomit else 0, self.seq.mr.nhist,
                    self.seq.mr.ind / (self.seq.mr.nomit + self.seq.mr.nhist) / self.seq.mr.nrows*100))

    def multirun_resume(self, status):
        """Resume the multi-run where it was left off.
        If the multirun is already running, do nothing."""
        if not 'multirun' in status: 
            remove_slot(self.cam.AcquireEnd, self.receive, False) # only receive if not in '# omit'
            remove_slot(self.cam.AcquireEnd, self.mr_receive, True)
            self.server.priority_messages([[TCPENUM['TCP load sequence from string'], self.seq.mr.msglist[self.seq.mr.get_next_index(self.seq.mr.ind)]],
                [TCPENUM['Run sequence'], 'multirun run '+str(self._n)]]) # adds at front of queue
            self.server.priority_message()
            
    def multirun_step(self, msg):
        """Execute a single run as part of a multirun.
        For the first '# omit' runs, only save the files.
        Then for '# hist' runs, add files to histogram.
        Then save, process, and reset the histogram.
        repeat this for the user variables in the multirun list,
        then return to normal operation as set by the histogram binning"""
        index = self.seq.mr.get_next_index(self.seq.mr.ind)
        r = self.seq.mr.ind % (self.seq.mr.nomit + self.seq.mr.nhist)
        v = self.seq.mr.ind // (self.seq.mr.nomit + self.seq.mr.nhist)
        
        if r >= self.seq.mr.nomit: 
            self.seq.mr.stats['runs included'][index].append(self._n) # include this run in the multirun
        
        self.seq.mr.progress.emit(       # update progress label
            'multirun measure %s: %s: %s, omit %s of %s files, %s of %s histogram files, %.3g %% complete'%(
                self.seq.mr.stats['measure'], self.seq.mr.stats['Variable label'], 
                self.seq.mr.table.item(self.seq.mr.ind, 0).text(), 
                r if r < self.seq.mr.nomit else self.seq.mr.nomit, self.seq.mr.nomit, 
                r - self.seq.mr.nomit if r > self.seq.mr.nomit else 0, self.seq.mr.nhist, 
                self.seq.mr.ind / (self.seq.mr.nomit + self.seq.mr.nhist) / self.seq.mr.nrows*100))
                
        # end of histogram: fit, save, and reset  --- could we send the command for the next run first to increase the duty cycle?
        if self.seq.mr.ind > 0 and r == 0:
            uv = self.seq.mr.table.item(self.seq.mr.ind, 0).text() # get user variable
            for mw in self.sw.rw + self.sw.mw: # make sure to do reimage windows first!
                mw.var_edit.setText(uv) # also updates histo_handler temp vals
                mw.bins_text_edit(text='reset') # set histogram bins 
                success = mw.update_fit(fit_method='check action') # get best fit
                if not success:                   # if fit fails, use peak search
                    mw.histo_handler.process(self.image_handler, uv, 
                        fix_thresh=self.thresh_toggle.isChecked(), method='quick')
                    logger.warning('\nMultirun run %s fitting failed. '%self._n +
                        'Histogram data in '+ mw.name + self.seq.mr.stats['measure_prefix']
                        + str(v) + '.csv')
                mw.save_hist_data(save_file_name=os.path.join(
                    self.sv.results_path, mw.name + self.seq.mr.stats['measure_prefix'] 
                    + str(v) + '.csv'), confirm=False) # save histogram
                mw.image_handler.reset_arrays() # clear histogram
        
        self.seq.mr.ind += 1
        if self.seq.mr.ind < self.seq.mr.nrows:
            newindex = self.seq.mr.get_next_index(self.seq.mr.ind)
            if index != newindex: # sequence will change
                msgs = [[TCPENUM['TCP load sequence from string'], self.seq.mr.msglist[newindex]]]
            else: msgs = []
            msgs.append([TCPENUM['Run sequence'], 'multirun run '+str(self._n)])
            self.server.priority_messages(msgs)
        else: # end of multirun:
            for mw in self.sw.rw + self.sw.mw:
                mw.save_varplot(save_file_name=os.path.join(
                    self.sv.results_path, mw.name + self.seq.mr.stats['measure_prefix'] + '.dat'), 
                    confirm=False) # save measure file
                # reconnect previous signals
                mw.set_bins() # reconnects signal with given histogram binning settings
            # suggest new multirun measure ID and prefix
            self.seq.mr.measures['measure'].setText(str(self.seq.mr.stats['measure']+1))
            self.seq.mr.measures['measure_prefix'].setText(str(self.seq.mr.stats['measure']+1)+'_')  
            self.multirun_go(False) # reconnect signals
            self.seq.mr.ind = 0
            self.server.priority_messages([[TCPENUM['TCP read'], 'end multirun '+str(self.seq.mr.stats['measure'])]])
            # save log file with the parameters used for this multirun:
            self.seq.mr.save_mr_params(os.path.join(self.sv.results_path, self.seq.mr.stats['measure_prefix']+'params.log'))