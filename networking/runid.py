"""Dextr - task managing for PyDex
Stefan Spence 11/10/19

 - control the run number ID for experimental runs
 - emit signals between modules when images are taken
 - keep other modules synchronised
"""
import time
import numpy as np
try:
    from PyQt4.QtCore import QThread, pyqtSignal, QTimer
    from PyQt4.QtGui import QMessageBox
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal, QTimer
    from PyQt5.QtWidgets import QMessageBox
from networker import PyServer
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
    n     - the initial run ID number
    m     - the number of images taken per sequence
    k     - the number of images taken already"""
    im_save = pyqtSignal(np.ndarray) # send an incoming image to saver
    Dxstate = 'unknown' # current state of DExTer

    def __init__(self, camra, saver, saiaw, n=0, m=1, k=0):
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
        
        self.server = PyServer() # server will run continuously on a thread
        self.server.dxnum.connect(self.set_n) # signal gives run number
        # self.server.textin.connect(self.read_Dx_msg) 

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

    def reset_dates(self):
        """Make sure that the dates in the image saving and analysis 
        programs are correct."""
        t0 = time.localtime()
        self.sv.date = time.strftime(
                "%d %b %B %Y", t0).split(" ") # day short_month long_month year
        for sw in self.sw:
            sw.date = self.sv.date
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
        for sw in self.sw:
            if sw.image_handler.fid != self._n:
                checks.append('Lost sync: Image analysis # %s /= run # %s'%(
                            sw.image_handler.fid, self._n))
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
            for sw in self.sw:
                sw.image_handler.fid = self._n
            self._k = self._n * self._m # number images that should've been taken
            return checks