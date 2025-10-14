"""Dextr - task managing for PyDex
Stefan Spence 11/10/19

 - control the run number ID for experimental runs
 - emit signals between modules when images are taken
 - keep other modules synchronised
"""
import time
import os
import numpy as np
import logging
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, pyqtSlot
from PyQt5.QtWidgets import QMessageBox
from networker import PyServer, reset_slot, TCPENUM
from client import PyClient
import sys
if '..' not in sys.path: sys.path.append('..')
from strtypes import error, warning, info
from imageanalysis.imagerGUI import ImagerGUI

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
    check - an instance of atomChecker.alex
    seq   - an instance of sequencePreviewer.Previewer
    n     - the initial run ID number
    m     - the number of images taken per sequence
    k     - the number of images taken already"""
    im_save = pyqtSignal(object) # send an incoming image to saver
    Dxstate = 'unknown' # current state of DExTer
    signal_emccd_bias = pyqtSignal(int) # # sends the EMCCD bias to the iGUI

    def __init__(self, camra, saver, check, seq, n=0, m=1, k=0, dev_mode=False):
        super().__init__()
        self.iGUI = ImagerGUI()  # ImagerGUI managing the Multi-Atom Image Analyser (MAIA)
        self.iGUI.maia.signal_num_images.connect(self.set_m)
        self.iGUI.update_num_images(m) # updating the number of images in the iGUI also sets self._n due to connection above
        self.iGUI.signal_set_rearr_images.connect(self.set_rearr_images)
        self.iGUI.update_rearr_images()

        self._n = n # # images per run
        self._k = k # # images received
        self.next_mr = [] # queue of messages for the next multirun
        self.hist_id = 0 # hist id to save the next MR file to
        self.mr_paused = False # whether the current multirun has been paused
        self.cam = camra # Andor camera control
        self.cam.AcquireEnd.connect(self.receive) # receive the most recent image
        self.sv = saver  # image saver
        self.im_save.connect(self.sv.add_item) # separate signal to avoid risk of the slot being disconnected elsewhere

        self.sv.start()  # constantly checks queue, when an image to save is added to the queue, it saves it to a file.

        # self.sw.m_changed.connect(self.set_m)
        # self.sw.CCD_stat_edit(self.cam.emg, self.cam.pag, self.cam.Nr, True) # give image analysis the camera settings
        # self.sw.reset_analyses() # make sure the loaded config settings are applied
        # self.cam.SettingsChanged.connect(self.sw.CCD_stat_edit)
        # self.cam.ROIChanged.connect(self.sw.cam_pic_size_changed) # triggers pic_size_text_edit()
        
        self.check = check  # atom checker for ROIs, trigger experiment
        self.check.signal_rearr_strings.connect(self.send_rearr_msgs)
        self.iGUI.maia.signal_emccd_bias.connect(self.update_emccd_bias)

        # for rh in self.check.rh.values():
        #     self.cam.ROIChanged.connect(rh.cam_pic_size_changed)
        #     
        # self.check.roi_values.connect(self.sw.set_rois)
        self.seq = seq   # sequence editor
        
        self.server = PyServer(host='', port=8620, name='DExTer', verbosity=1) # server will run continuously on a thread
        # self.server.dxnum.connect(self.set_n) # signal gives run number
        reset_slot(self.server.dxnum,self.set_n,True) # signal gives run number (this is deactivated during a MR)

        self.iGUI.maia.signal_finished_saving.connect(self.server.unpause) # lets MAIA unlock multirun after it has finished saving
        self.server.start()
        if self.server.isRunning():
            self.server.add_message(TCPENUM['TCP read'], 'Sync DExTer run number\n'+'0'*2000)

        self.trigger = PyServer(host='', port=8621, name='Dx SFTWR TRIGGER') # software trigger using TCP
        self.trigger.start()
        self.monitor = PyServer(host='', port=8622, name='DAQ') # monitor program runs separately
        self.monitor.start()
        self.monitor.add_message(self._n, 'resync run number')
        self.awgtcp1 = PyServer(host='', port=8623, name='AWG1') # AWG program runs separately
        self.awgtcp1.start()
        self.ddstcp1 = PyServer(host='', port=8624, name='DDS1') # DDS program runs separately
        self.ddstcp1.start()
        self.seqtcp = PyServer(host='', port=8625, name='BareDExTer') # Sequence viewer in seperate instance of LabVIEW
        self.seqtcp.start()
        self.slmtcp = PyServer(host='', port=8627, name='SLM') # SLM program runs separately
        self.slmtcp.start()
        self.rfsoctcp = PyServer(host='', port=8636, name='RFSOC') # RFSOC program runs separately
        self.rfsoctcp.start()
        if not dev_mode:
            self.client = PyClient(host='129.234.190.235', port=8626, name='AWG1 recv') # incoming from AWG
            self.clien2 = PyClient(host='129.234.190.233', port=8629, name='AWG2 recv') # incoming from AWG2\
            self.clien3 = PyClient(host='129.234.190.234', port=8639, name='AWG3 recv') # incoming from AWG2\
            self.clientmwg_wftk = PyClient(host='129.234.190.235', port=8632, name='MW recv (WFTK)') # incoming from MW generator (WFTK) control
            self.clientmwg_anritsu = PyClient(host='129.234.190.235', port=8635, name='MW recv (Anritsu)') # incoming from MW generator (Anritsu) control
        else:
            self.client = PyClient(host='localhost', port=8626, name='AWG1 recv') # incoming from AWG
            self.clien2 = PyClient(host='localhost', port=8629, name='AWG2 recv') # incoming from AWG2
            self.clien3 = PyClient(host='localhost', port=8639, name='AWG3 recv') # incoming from AWG2
            self.clientmwg_wftk = PyClient(host='localhost', port=8632, name='MW recv (WFTK)') # incoming from MW generator (WFTK) control
            self.clientmwg_anritsu = PyClient(host='localhost', port=8635, name='MW recv (Anritsu)') # incoming from MW generator (Anritsu) control
        self.client.start()
        self.client.textin.connect(self.add_mr_msgs) # msg from AWG starts next multirun step
        self.clien2.start()
        self.clien2.textin.connect(self.add_mr_msgs) # msg from AWG starts next multirun step
        self.clien3.start()
        self.clien3.textin.connect(self.add_mr_msgs) # msg from AWG starts next multirun step
        self.clientmwg_wftk.start()
        self.clientmwg_wftk.textin.connect(self.add_mr_msgs) # msg from MW generator control starts next multirun step
        self.clientmwg_anritsu.start()
        self.clientmwg_anritsu.textin.connect(self.add_mr_msgs) # msg from MW generator control (Anritsu) starts next multirun step

        self.awgtcp2 = PyServer(host='', port=8628, name='AWG2') # AWG program runs separately
        self.awgtcp2.start()
        self.awgtcp3 = PyServer(host='', port=8637, name='AWG3') # AWG program runs separately
        self.awgtcp3.start()
        self.ddstcp2 = PyServer(host='', port=8630, name='DDS2') # DDS program runs separately
        self.ddstcp2.start()
        self.mwgtcp_wftk = PyServer(host='', port=8631, name='MWG (WFTK)') # MW generator (WFTK) control program runs separately
        self.mwgtcp_wftk.start()
        self.ddstcp3 = PyServer(host='', port=8633, name='DDS3') # DDS program runs separately
        self.ddstcp3.start()
        self.mwgtcp_anritsu = PyServer(host='', port=8634, name='MWG (Anritsu)') # MW generator (Anritsu) control program runs separately
        self.mwgtcp_anritsu.start()
        self.server_list = [self.server, self.trigger, self.monitor, self.awgtcp1, self.ddstcp1, 
                self.slmtcp, self.rfsoctcp, self.seqtcp, self.awgtcp2, self.awgtcp3, self.ddstcp2, self.mwgtcp_wftk, self.ddstcp3,
                self.mwgtcp_anritsu]
        
    def reset_server(self, force=False):
        """Check if the server is running. If it is, don't do anything, unless 
        force=True, then stop and restart the server. If the server isn't 
        running, then start it."""
        for server in self.server_list:
            if server.isRunning():
                if force:
                    server.close()
                    server.clear_queue()
                    time.sleep(0.1) # give time for it to close
                    server.start()
            else: server.start()
            
    def set_n(self, dxn):
        """Change the Dexter run number to the new value.
        If it's during a multirun, check that the right number of 
        images were taken in the last run."""
        if self._k != self._m and self.seq.mr.ind > 1 and self._k > 0:
            warning('Run %s took %s / %s images.'%(self._n, self._k, self._m))
        self._n = int(dxn)
        self.iGUI.set_file_id(self._n)
        self._k = 0 # reset image count --- each run should start with im0
    
    @pyqtSlot(int)
    def set_m(self, newm=None):
        """Change the number of images per run.
        
        Parameters
        ----------
        newm : int or None
            The new number of images to set in the run. If None the value from
            MAIA is requested which will then retrigger this function with 
            the updated value.
        """
        if newm is None:
            self.iGUI.update_num_images() # ask the iGUI to find out the number of images. 
                                          # This function will then be retriggered with an int when the MAIA checks.
            return
        self._m = int(newm)

    @pyqtSlot(list)
    def set_rearr_images(self, rearr_images):
        """Gets the rearrangement images from the iGUI and updates the list
        that is used to decide which images are sent to the rearrangement
        handler."""
        self.rearr_images = rearr_images
        logging.debug('Controller: set rearrangement images to {}'.format(rearr_images))

    @pyqtSlot(int)
    def update_emccd_bias(self,emccd_bias):
        """Sets the EMCCD bias from MAIA that should be subtracted from all 
        recieved images."""
        self.emccd_bias = emccd_bias
        logging.debug('Controller recieved new EMCCD bias of {} from MAIA'.format(self.emccd_bias))

    def receive(self, im=0):
        """Update the Dexter file number in all associated modules,
        then send the image array to be saved and analysed."""
        logging.debug('Controller recieved image outside of a multirun')
        im, imn = self.process_image_pre_iGUI(im)
        self.iGUI.recieve_image(im,self._n,imn) # the images File ID and image num are specified here when added to the MAIA queue.
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
        logging.debug('Controller recieved image as part of a multirun')
        im, imn = self.process_image_pre_iGUI(im)
        if self.seq.mr.ind % (self.seq.mr.mr_param['# omitted'] + self.seq.mr.mr_param['# in hist']) >= self.seq.mr.mr_param['# omitted']:
            self.iGUI.recieve_image(im,self._n,imn) # the images File ID and image num are specified here when added to the MAIA queue. Pass imn to compensate for rearrangement.
        self._k += 1 # another image was taken
        if self._k >= self._m: # iterate to the next file ID if all images have been taken
            self.set_n(str(self._n+1))

    def process_image_pre_iGUI(self, im=0):
        """Helper function that processes the images before sending to the
        iGUI. This combines two functions that were previously redefined
        for image processing inside/outside a multirun."""
        im = im - self.emccd_bias # don't edit in place because this seemed to cause an issue with images not showing in GUI. Maybe not thread safe?
        self.sv.dfn = str(self._n) # Dexter file number     
        imn = self._k % self._m # ID number of image in sequence
        logging.debug('Image ID numbers are: k = {}, n = {}, m  = {}, imn {}:'.format(
                self._k,self._n,self._m,imn))
        if imn in self.rearr_images: # if this image is a rearrangement image then send it to ALEX asap
            logging.debug('This is a rearrangement image so sending to ALEX.')
            ih_num = self.rearr_images.index(imn)
            logging.debug('ALEX image handler ID is {}'.format(ih_num))
            self.check.recieve_image(im,ih_num,self._n)
        self.sv.imn = str(imn)
        logging.debug('Passing image to image saver.')
        self.im_save.emit([im,self._n,imn])
        return im, imn

    def check_receive(self, im=0):
        """Receive image for atom checker, don't save but just pass on"""
        self.check.event_im.emit(im)

    def reset_dates(self, t0):
        """Make sure that the dates in the image saving and analysis 
        programs are correct."""
        date = time.strftime("%d %b %B %Y", t0).split(" ")
        self.sv.reset_dates(date)
        return ' '.join([date[0]] + date[2:])
    
    #### atom checker ####

    @pyqtSlot(list)
    def send_rearr_msgs(self,messages):
        """Function called when ALEX wants to send a rearrangement string to
        the AWG consoles."""
        for awgtcp, msg in zip([self.awgtcp1,self.awgtcp2, self.awgtcp3],messages):
            awgtcp.priority_messages([(self._n, 'rearrange='+msg+'#'*2000)])
        
    def atomcheck_go(self, toggle=True):
        """Disconnect camera images from analysis, start the camera
        acquisition and redirect the images to the atom checker."""
        if self.cam.initialised > 1:
            self.check.checking = True
            self.trigger.start() # start server for TCP to send msg when atoms loaded
            # redirect images from analysis to atom checker
            reset_slot(self.cam.AcquireEnd, self.receive, False)
            reset_slot(self.cam.AcquireEnd, self.mr_receive, False)
            reset_slot(self.cam.AcquireEnd, self.check_receive, True)
            # still in external exposure trigger - DExTer will send the trigger pulses
            self.cam.start() # run till abort keeps taking images
            if self.check.timer.t0 > 0: # if timeout is set, set a timer
                self.check.timer.singleShot(int(self.check.timer.t0*1e3), self.check.send_trigger)

    #### multirun ####

    def get_params(self, v, module='AWG1'):
        """Reformat the multirun paramaters into a string to be sent to the AWG, DDS, SLM, or MWG"""
        msg = module+' set_data=['
        col = -1  # in case the for loop doesn't execute
        for col in range(len(self.seq.mr.mr_param['Type'])):
            if 'AWG1' in self.seq.mr.mr_param['Type'][col] and module == 'AWG1':
                try: # argument: value
                    for n in self.seq.mr.mr_param['Time step name'][col]: # index of chosen AWG channel, segment 
                        for m in self.seq.mr.mr_param['Analogue channel'][col]:
                            msg += '[%s, %s, "%s", %s, %s],'%(n%2, n//2, 
                                self.seq.mr.awg_args[m], self.seq.mr.mr_vals[v][col], 
                                self.seq.mr.mr_param['list index'][col])
                except Exception as e: error('Invalid AWG parameter at (%s, %s)\n'%(v,col)+str(e))
            elif 'AWG2' in self.seq.mr.mr_param['Type'][col] and module == 'AWG2':
                try: # argument: value
                    for n in self.seq.mr.mr_param['Time step name'][col]: # index of chosen AWG channel, segment 
                        for m in self.seq.mr.mr_param['Analogue channel'][col]:
                            msg += '[%s, %s, "%s", %s, %s],'%(n%2, n//2, 
                                self.seq.mr.awg_args[m], self.seq.mr.mr_vals[v][col], 
                                self.seq.mr.mr_param['list index'][col])
                except Exception as e: error('Invalid AWG parameter at (%s, %s)\n'%(v,col)+str(e))
            elif 'AWG3' in self.seq.mr.mr_param['Type'][col] and module == 'AWG3':
                try: # argument: value
                    for n in self.seq.mr.mr_param['Time step name'][col]: # index of chosen AWG channel, segment 
                        for m in self.seq.mr.mr_param['Analogue channel'][col]:
                            msg += '[%s, %s, "%s", %s, %s],'%(n%2, n//2, 
                                self.seq.mr.awg_args[m], self.seq.mr.mr_vals[v][col], 
                                self.seq.mr.mr_param['list index'][col])
                except Exception as e: error('Invalid AWG parameter at (%s, %s)\n'%(v,col)+str(e))
            elif 'DDS1' in self.seq.mr.mr_param['Type'][col] and module == 'DDS1':
                try: # argument: value
                    for n in self.seq.mr.mr_param['Time step name'][col]: # index of chosen DDS COM port, profile
                        for m in self.seq.mr.mr_param['Analogue channel'][col]:
                            port = '"P%s"'%(n%9) if (n%9)<8 else '"aux"'
                            msg += '["COM%s", '%((n//9)+7)+port+', "%s", %s],'%(# we use COM7 - COM11
                                self.seq.mr.dds_args[m], 
                                self.seq.mr.mr_vals[v][col])
                except Exception as e: error('Invalid DDS parameter at (%s, %s)\n'%(v,col)+str(e))
            elif 'DDS2' in self.seq.mr.mr_param['Type'][col] and module == 'DDS2':
                try: # argument: value
                    for n in self.seq.mr.mr_param['Time step name'][col]: # index of chosen DDS COM port, profile
                        for m in self.seq.mr.mr_param['Analogue channel'][col]:
                            profile = '"P%s"'%(n%9) if (n%9)<8 else '"aux"'
                            msg += '["%s", '%(n//9+1)+profile+', "%s", %s],'%(# don't specify COM port
                                self.seq.mr.dds_args[m], 
                                self.seq.mr.mr_vals[v][col])
                except Exception as e: error('Invalid DDS parameter at (%s, %s)\n'%(v,col)+str(e))
            elif 'DDS3' in self.seq.mr.mr_param['Type'][col] and module == 'DDS3':
                try: # argument: value
                    for n in self.seq.mr.mr_param['Time step name'][col]: # index of chosen DDS COM port, profile
                        for m in self.seq.mr.mr_param['Analogue channel'][col]:
                            profile = '"P%s"'%(n%9) if (n%9)<8 else '"aux"'
                            msg += '["%s", '%(n//9+1)+profile+', "%s", %s],'%(# don't specify COM port
                                self.seq.mr.dds_args[m], 
                                self.seq.mr.mr_vals[v][col])
                except Exception as e: error('Invalid DDS parameter at (%s, %s)\n'%(v,col)+str(e))
            elif 'SLM' in self.seq.mr.mr_param['Type'][col] and module == 'SLM':
                try: # argument: value
                    for n in self.seq.mr.mr_param['Time step name'][col]: # index of chosen SLM hologram
                        for m in self.seq.mr.mr_param['Analogue channel'][col]:
                            msg += '[%s,"%s",%s],'%(n, # [holo index, parameter, value]
                                self.seq.mr.slm_args[m], 
                                self.seq.mr.mr_vals[v][col])
                except Exception as e: error('Invalid SLM parameter at (%s, %s)\n'%(v,col)+str(e))
            elif 'RFSOC' in self.seq.mr.mr_param['Type'][col] and module == 'RFSOC':
                try: # argument: value
                    for n in self.seq.mr.mr_param['Time step name'][col]: # index of chosen pulse
                        for m in self.seq.mr.mr_param['Analogue channel'][col]:
                            msg += '[%s,"%s",%s],'%(n, # [PulseIndex, parameter, value]
                                self.seq.mr.rfsoc_args[m], 
                                self.seq.mr.mr_vals[v][col])
                except Exception as e: error('Invalid RFSOC parameter at (%s, %s)\n'%(v,col)+str(e))
            elif 'MWG (WFTK)' in self.seq.mr.mr_param['Type'][col] and module == 'MWG (WFTK)':
                try: # argument: value
                    for n in self.seq.mr.mr_param['Time step name'][col]: # COM port for MWG to edit
                        for m in self.seq.mr.mr_param['Analogue channel'][col]:
                            msg += '["%s","%s",%s,%s],'%( # [COM port, parameter, value, tone index]
                                self.seq.mr.mwg_wftk_coms[n], 
                                self.seq.mr.mwg_wftk_args[m], 
                                self.seq.mr.mr_vals[v][col],
                                self.seq.mr.mr_param['list index'][col])
                except Exception as e: error('Invalid MWG (WFTK) parameter at (%s, %s)\n'%(v,col)+str(e))
            elif 'MWG (Anritsu)' in self.seq.mr.mr_param['Type'][col] and module == 'MWG (Anritsu)':
                try: # argument: value
                    for n in self.seq.mr.mr_param['Time step name'][col]: # tone to edit on MWG (Anritsu)
                        for m in self.seq.mr.mr_param['Analogue channel'][col]:
                            msg += '["%s","%s",%s,%s],'%( # [Tone index, parameter, value, N/A]
                                self.seq.mr.mwg_anritsu_tones[n], 
                                self.seq.mr.mwg_anritsu_args[m], 
                                self.seq.mr.mr_vals[v][col],
                                self.seq.mr.mr_param['list index'][col])
                except Exception as e: error('Invalid MWG (Anritsu) parameter at (%s, %s)\n'%(v,col)+str(e))
        if col > -1: msg = msg[:-1] + ']'
        else: msg += ']'
        return msg
    
    def multirun_go(self, toggle, stillrunning=False):
        """Initiate the multi-run: omit N files, save a histogram of M files, and
        repeat for the user variables in the list. A new sequence is generated for 
        each multirun run. These are sent via TCP and then run. Once the multirun
        has started it"""
        r = self.seq.mr.ind % (self.seq.mr.mr_param['# omitted'] + self.seq.mr.mr_param['# in hist']) # ID of run in repetition cycle
        if toggle: # and self.sw.check_reset() < now will auto reset (so you can queue up multiruns)
            try: # take the multirun parameters from the queue (they're added to the queue in master.py)
                self.seq.mr.mr_param, self.seq.mr.mrtr, self.seq.mr.mr_vals, self.seq.mr.appending = self.seq.mr.mr_queue.pop(0) # parameters, sequence, values, whether to append
            except IndexError as e:
                error('runid.py could not start multirun because no multirun was queued.\n'+str(e))
                return 0
            
            self.iGUI.add_request_to_queue('clear') # clear the MAIA data before another MR begins. The clear command will be added to the queue so no images are skipped.
            results_path = os.path.join(self.sv.results_path, self.seq.mr.mr_param['measure_prefix'])
            reset_slot(self.cam.AcquireEnd, self.receive, False) # only receive if not in '# omit'
            reset_slot(self.cam.AcquireEnd, self.mr_receive, True)
            self.seq.mr.ind = 0 # counter for how far through the multirun we are
            self._k = 0 # reset image per run count
            try:
                uv = self.seq.mr.mr_vals[0][0]
            except IndexError: uv = 'IndexError'
            self.seq.mr.progress.emit(       # update progress label
                'multirun measure %s: %s: %s, omit %s of %s files, %s of %s histogram files, 0%% complete'%(
                    self.seq.mr.mr_param['measure'], self.seq.mr.mr_param['Variable label'], 
                    uv, 0, self.seq.mr.mr_param['# omitted'], 0, self.seq.mr.mr_param['# in hist']))
            # make the directories
            try:
                os.makedirs(results_path, exist_ok=True)
                os.makedirs(os.path.join(results_path, 'sequences'), exist_ok=True)
                # save sequences and make list of messages to send and the order:
                self.seq.mr.mrtr.write_to_file(os.path.join(results_path, 'sequences', self.seq.mr.mr_param['measure_prefix'] + '_base.xml'))
                self.seq.mr.get_all_sequences(save_dir=os.path.join(results_path, 'sequences'))
                self.seq.mr.save_mr_params(os.path.join(results_path, self.seq.mr.mr_param['measure_prefix'] + 
                    'params' + str(self.seq.mr.mr_param['1st hist ID']) + '.csv'))
                self.iGUI.set_results_path(results_path)
                self.iGUI.set_measure_prefix(str(self.seq.mr.mr_param['measure_prefix']))
            except FileNotFoundError as e:
                error('Multirun could not start because of invalid directory %s\n'%results_path+str(e))
                return 0
            # tell the monitor program to save results to the new directory
            self.monitor.add_message(self._n, results_path+'=save_dir')
            self.monitor.add_message(self._n, 'start')
            # insert TCP messages at the front of the queue: once the multirun starts don't interrupt it.
            repeats = self.seq.mr.mr_param['# omitted'] + self.seq.mr.mr_param['# in hist']
            # list of TCP messages for the whole multirun
            # save AWG, DDS, and SLM params
            self.awgtcp1.priority_messages([[self._n, 'save='+os.path.join(results_path,'AWG1param'+str(self.seq.mr.mr_param['1st hist ID'])+'.txt')]])
            self.awgtcp2.priority_messages([[self._n, 'save='+os.path.join(results_path,'AWG2param'+str(self.seq.mr.mr_param['1st hist ID'])+'.txt')]])
            self.awgtcp3.priority_messages([[self._n, 'save='+os.path.join(results_path,'AWG3param'+str(self.seq.mr.mr_param['1st hist ID'])+'.txt')]])
            self.ddstcp1.priority_messages([[self._n, 'save_all='+os.path.join(results_path,'DDS1param'+str(self.seq.mr.mr_param['1st hist ID'])+'.txt')]])
            self.ddstcp2.priority_messages([[self._n, 'save_all='+os.path.join(results_path,'DDS2param'+str(self.seq.mr.mr_param['1st hist ID'])+'.txt')]])
            self.ddstcp3.priority_messages([[self._n, 'save_all='+os.path.join(results_path,'DDS3param'+str(self.seq.mr.mr_param['1st hist ID'])+'.txt')]])
            self.slmtcp.priority_messages([[self._n, 'save_all='+os.path.join(results_path,'SLMparam'+str(self.seq.mr.mr_param['1st hist ID'])+'.txt')]])
            self.rfsoctcp.priority_messages([[self._n, 'save_all='+os.path.join(results_path,'RFSOCparam'+str(self.seq.mr.mr_param['1st hist ID'])+'.txt')]])
            self.mwgtcp_wftk.priority_messages([[self._n, 'save_all='+os.path.join(results_path,'MWG_WFTK_param'+str(self.seq.mr.mr_param['1st hist ID'])+'.txt')]])
            self.mwgtcp_anritsu.priority_messages([[self._n, 'save_all='+os.path.join(results_path,'MWG_Anritsu_param'+str(self.seq.mr.mr_param['1st hist ID'])+'.txt')]])
            mr_queue = []
            #print('make msg')
            for v in range(len(self.seq.mr.mr_vals)): # use different last time step during multirun
                module_msgs = {'AWG1':'', 'AWG2':'', 'AWG3':'', 'DDS1':'', 'DDS2':'', 'DDS3':'', 'SLM':'', 'RFSOC':'', 
                               'MWG (WFTK)':'', 'MWG (Anritsu)':''}
                for key in module_msgs.keys():
                    if any(key in x for x in self.seq.mr.mr_param['Type']): # send parameters by TCP
                        module_msgs[key] = self.get_params(v, key)
                pausemsg = '0'*2000
                if module_msgs['AWG1']: pausemsg = 'pause for AWG1' + pausemsg
                if module_msgs['AWG2']: pausemsg = 'pause for AWG2' + pausemsg
                if module_msgs['AWG3']: pausemsg = 'pause for AWG3' + pausemsg
                if module_msgs['MWG (WFTK)']: pausemsg = 'pause for MWG (WFTK)' + pausemsg
                if module_msgs['MWG (Anritsu)']: pausemsg = 'pause for MWG (Anritsu)' + pausemsg
                mr_queue += [
                    [TCPENUM['TCP read'], module_msgs['AWG1']+'||||||||'+'0'*2000], # set AWG parameters
                    [TCPENUM['TCP read'], module_msgs['AWG2']+'||||||||'+'0'*2000], # set AWG parameters
                    [TCPENUM['TCP read'], module_msgs['AWG3']+'||||||||'+'0'*2000], # set AWG parameters
                    [TCPENUM['TCP read'], module_msgs['DDS1']+'||||||||'+'0'*2000], # set DDS parameters
                    [TCPENUM['TCP read'], module_msgs['DDS2']+'||||||||'+'0'*2000], # set DDS parameters
                    [TCPENUM['TCP read'], module_msgs['DDS3']+'||||||||'+'0'*2000], # set DDS parameters
                    [TCPENUM['TCP read'], module_msgs['SLM']+'||||||||'+'0'*2000], # set SLM parameters
                    [TCPENUM['TCP read'], module_msgs['RFSOC']+'||||||||'+'0'*2000], # set RFSOC parameters
                    [TCPENUM['TCP read'], module_msgs['MWG (WFTK)']+'||||||||'+'0'*2000], # set MWG (WFTK) parameters
                    [TCPENUM['TCP read'], module_msgs['MWG (Anritsu)']+'||||||||'+'0'*2000], # set MWG (Anritsu) parameters
                    [TCPENUM['TCP load last time step'], self.seq.mr.mr_param['Last time step run']+'0'*2000],
                    [TCPENUM['TCP load sequence from string'], self.seq.mr.msglist[v]],
                    [TCPENUM['TCP read'], pausemsg]] + [
                    [TCPENUM['Run sequence'], 'multirun run '+str(self._n + r + repeats*v)+'\n'+'0'*2000] for r in range(repeats)
                    ] + [[TCPENUM['TCP read'], 'save and reset histogram\n'+'0'*2000]]
            # reset last time step for the last run:
            mr_queue.insert(len(mr_queue) - 2, [TCPENUM['TCP load last time step'], self.seq.mr.mr_param['Last time step end']+'0'*2000])
            mr_queue += [[TCPENUM['TCP read'], 'confirm last multirun run\n'+'0'*2000], 
                [TCPENUM['TCP read'], 'end multirun '+str(self.seq.mr.mr_param['measure'])+'\n'+'0'*2000]]
            self.next_mr = mr_queue
            self.add_mr_msgs()
            self.seq.mr.mr_param['runs included'][0].append(self._n) # keep track of which runs are in the multirun.
        else: # pause the multi-run
            reset_slot(self.cam.AcquireEnd, self.mr_receive, False)
            reset_slot(self.cam.AcquireEnd, self.receive, True) # process every image
            if stillrunning: self.next_mr = self.server.get_queue() # save messages to reinsert when resume
            self.server.clear_queue()
            if any('AWG1' in x for x in self.seq.mr.mr_param['Type']):
                self.awgtcp1.add_message(self._n, 'AWG1 load='+os.path.join(self.sv.results_path, # reset AWG parameters
                    self.seq.mr.mr_param['measure_prefix'],'AWG1param'+str(self.seq.mr.mr_param['1st hist ID'])+'.txt'))
            if any('AWG2' in x for x in self.seq.mr.mr_param['Type']):
                self.awgtcp2.add_message(self._n, 'AWG2 load='+os.path.join(self.sv.results_path, # reset AWG parameters
                    self.seq.mr.mr_param['measure_prefix'],'AWG2param'+str(self.seq.mr.mr_param['1st hist ID'])+'.txt'))
            if any('AWG3' in x for x in self.seq.mr.mr_param['Type']):
                self.awgtcp3.add_message(self._n, 'AWG3 load='+os.path.join(self.sv.results_path, # reset AWG parameters
                    self.seq.mr.mr_param['measure_prefix'],'AWG3param'+str(self.seq.mr.mr_param['1st hist ID'])+'.txt'))
            if any('SLM' in x for x in self.seq.mr.mr_param['Type']):
                self.slmtcp.add_message(self._n, 'load_all='+os.path.join(self.sv.results_path, # reset SLM parameters
                    self.seq.mr.mr_param['measure_prefix'],'SLMparam'+str(self.seq.mr.mr_param['1st hist ID'])+'.txt'))
            if any('RFSOC' in x for x in self.seq.mr.mr_param['Type']):
                self.rfsoctcp.add_message(self._n, 'load_all='+os.path.join(self.sv.results_path, # reset SLM parameters
                    self.seq.mr.mr_param['measure_prefix'],'RFSOCparam'+str(self.seq.mr.mr_param['1st hist ID'])+'.txt'))
            if any('MWG (WFTK)' in x for x in self.seq.mr.mr_param['Type']):
                self.mwgtcp_wftk.add_message(self._n, 'load_all='+os.path.join(self.sv.results_path, # reset MWG parameters
                    self.seq.mr.mr_param['measure_prefix'],'MWG_WFTK_param'+str(self.seq.mr.mr_param['1st hist ID'])+'.txt'))
            if any('MWG (Anritsu)' in x for x in self.seq.mr.mr_param['Type']):
                self.mwgtcp_anritsu.add_message(self._n, 'load_all='+os.path.join(self.sv.results_path, # reset MWG parameters
                    self.seq.mr.mr_param['measure_prefix'],'MWG_Anritsu_param'+str(self.seq.mr.mr_param['1st hist ID'])+'.txt'))
            try:
                self.cam.AF.AbortAcquisition()
            except Exception:
                error('Failed to abort camera acquisition.')
            self.seq.mr.multirun = stillrunning
            if not stillrunning: 
                self.seq.mr.ind = 0
                self._k = 0
                # for mw in self.sw.mw + self.sw.rw:
                #     mw.multirun = ''
            status = ' paused.' if stillrunning else ' ended.'
            self.mr_paused = stillrunning
            text = 'STOPPED. Multirun measure %s: %s is'%(self.seq.mr.mr_param['measure'], self.seq.mr.mr_param['Variable label'])
            self.seq.mr.progress.emit(text+status)
            self.server.add_message(TCPENUM['Run sequence'], text+status) # a final run, needed to trigger the AWG to start.

    def add_mr_msgs(self):
        """Add the next set of multirun messages to the queue to send to DExTer.
        Gets triggered by the AWG1, AWG2, and MWG TCP clients."""
        if self.seq.mr.multirun:
            self.server.unlockq()
            for i in range(len(self.next_mr)):
                enum, text = self.next_mr.pop(0)
                if 'pause for AWG' in text:
                    self.seq.mr.progress.emit('Waiting for AWG...')
                    self.server.lockq()
                    break
                elif 'pause for MWG' in text:
                    self.seq.mr.progress.emit('Waiting for MWG...')
                    self.server.lockq()
                    break
                else:
                    self.server.add_message(enum, text)
                
    def skip_mr_hist(self):
        """Remove the TCP messages for the current histogram so that MR skips it"""
        try:
            queue = self.server.get_queue()
            self.server.clear_queue()
            for i, item in enumerate(queue): # find the end of the histogram
                if 'save and reset histogram' in item[1]:
                    break
            self.next_mr = [[TCPENUM['TCP read'], '||||||||'+'0'*2000]] + queue[i+1:]
            self.seq.mr.progress.emit('Waiting for MAIA to finish processing queue...')
            self.server.pause() # server is paused to allow MAIA to go through the queue and finish analysing all the images before continuing
            self.iGUI.save(self.hist_id) # iGUI still saves the output of the hists so that we can skip if something looks clear already
            r = self.seq.mr.ind % (self.seq.mr.mr_param['# omitted'] + self.seq.mr.mr_param['# in hist'])
            self.seq.mr.ind += self.seq.mr.mr_param['# omitted'] + self.seq.mr.mr_param['# in hist'] - r
            self.add_mr_msgs()
        except IndexError as e: error('Failed to skip histogram. IndexError:\n'+str(e))

    def multirun_resume(self, status):
        """Resume the multi-run where it was left off.
        If the multirun is already running, do nothing."""
        if self.mr_paused: 
            self.mr_paused = False
            reset_slot(self.cam.AcquireEnd, self.receive, False) # only receive if not in '# omit'
            reset_slot(self.cam.AcquireEnd, self.mr_receive, True)
            self._k = 0 # reset image per run count
            self.add_mr_msgs() # the messages were already stored in next_mr
            
    def multirun_step(self, msg):
        """Update the status label for the multirun
        The data for the run is received and processed when the command for the 
        next run is being sent, so the histogram is saved, fitted, and reset
        based on the run number +1."""
        self.monitor.add_message(self._n, 'update run number')
        r = self.seq.mr.ind % (self.seq.mr.mr_param['# omitted'] + self.seq.mr.mr_param['# in hist']) # repeat
        if r == 0:
            self.iGUI.add_request_to_queue('clear') # clear MAIA data at the start of a new run
        elif r == 1:
            self.monitor.add_message(self._n, 'set fadelines') # keep the trace from the start of the histogram
        v = self.seq.mr.get_next_index(self.seq.mr.ind) # variable
        try:
            # if r >= self.seq.mr.mr_param['# omitted']: 
            #     self.seq.mr.mr_param['runs included'][v].append(self._n) # include this run in the multirun
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
        self.iGUI.set_measure_prefix(self.seq.mr.mr_param['measure_prefix'])
        self.hist_id = v+self.seq.mr.mr_param['1st hist ID']
        self.iGUI.set_hist_id(self.hist_id)
        self.iGUI.set_user_variables(self.seq.mr.mr_vals[v])
                
    def multirun_save(self, msg):
        """end of histogram: fit, save, and reset --- check this doesn't miss an image if there's lag"""
        v = self.seq.mr.ind // (self.seq.mr.mr_param['# omitted'] + self.seq.mr.mr_param['# in hist']) - 1 # previous variable
        try:
            prv = self.seq.mr.mr_vals[v][0] # get user variable from the previous row
        except AttributeError as e:     
            error('Multirun step could not extract user variable from table at row %s.\n'%v+str(e))
            prv = ''

        # save data
        self.seq.mr.progress.emit('Waiting for MAIA to finish processing queue...')
        self.server.pause() # server is paused to allow MAIA to go through the queue and finish analysing all the images before continuing
        self.iGUI.save(self.hist_id) # server will be unpaused at the end of a successful save (see self.iGUI.maia.save())
        self.iGUI.update_all_stefans() # update all the open STEFANs at the end of a multirun before the data is cleared. This command sends requests to MAIA that will be handled before it clears data.
        
    def multirun_end(self, msg):
        """At the end of the multirun, save the plot data and reset"""
        self.monitor.add_message(self._n, 'DAQtrace.csv=trace_file')
        self.monitor.add_message(self._n, 'save trace') # get the monitor to save the last acquired trace
        self.monitor.add_message(self._n, 'save graph') # get the monitor to save the graph  
        self.monitor.add_message(self._n, 'stop') # stop monitoring
        self.multirun_go(False) # reconnect signals
        self.seq.mr.ind = 0
        # save over log file with the parameters used for this multirun (now including run numbers):
        self.seq.mr.save_mr_params(os.path.join(self.sv.results_path, os.path.join(self.seq.mr.mr_param['measure_prefix'],
            self.seq.mr.mr_param['measure_prefix'] + 'params' + str(self.seq.mr.mr_param['1st hist ID']) + '.csv')))
        self.seq.mr.progress.emit(       # update progress label
            'Finished measure %s: %s.'%(self.seq.mr.mr_param['measure'], self.seq.mr.mr_param['Variable label']))
        self.seq.mr.multirun = False
        for server in self.server_list[2:]:
                server.clear_queue() # otherwise messages to save params build up