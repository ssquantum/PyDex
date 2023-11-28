"""Simple Thus EFficient ANalysers (STEFANs)
Dan Ruttley 2023-01-24
Code written to follow PEP8 conventions with max line length 120 characters.

STEFANs are simple plotters designed to allow for mid-experiment monitoring of
ROI statistics. Statistics are provided by the Multi Atom Image Analyser (MAIA)
but are processed in the STEFAN thread to prevent delay of image processing in
the MAIA. Statistics will only be reobtained and recalculated on-demand from 
the user to prevent lag.

A STEFAN is actually three seperate (but linked) classes:
    - StefanGUI: the interface presented to the user. This *must* run in the 
                main program thread because it alters pyqt GUI elements.
    - StefanWorker: the behind-the-scenes class which operates in a seperate 
        thread. This class performs the analysis of data. It is only kept when
        data analysis is being performed, otherwise it is destroyed.
    - StefanWorkerSignals: The StefanWorker class inherits from QRunnable so 
        cannot perform signalling. For this reason within it a 
        StefanWorkerSignals object that can perform the signalling.
        (see https://www.pythonguis.com/tutorials/multithreading-pyqt-applications-qthreadpool/)

A StefanGUI object should be created and managed by the iGUI and the StefanGUI 
will then create the corresponding background StefanWorker thread when neeeded. 
The iGUI and StefanGUI will reside in the same thread so can communicate with 
normal Python methods, but StefanGUI <-> Stefanworker communication is 
performed entirely with slots/signals to ensure thread safety.
"""

import numpy as np
from PyQt5.QtCore import (pyqtSignal, pyqtSlot, QObject, QThread, QTimer, 
                          QCoreApplication, QRunnable, QThreadPool, Qt)
from PyQt5.QtGui import (QIcon, QDoubleValidator, QIntValidator, 
        QFont, QRegExpValidator)
from PyQt5.QtWidgets import (QActionGroup, QVBoxLayout, QMenu, 
        QFileDialog, QComboBox, QMessageBox, QLineEdit, QGridLayout, 
        QApplication, QPushButton, QAction, QMainWindow, QWidget,
        QLabel, QTabWidget, QInputDialog, QHBoxLayout, QTableWidget,
        QCheckBox, QFormLayout, QCheckBox, QStatusBar, QButtonGroup,
        QRadioButton)
import pyqtgraph as pg
from datetime import datetime
import time
from roi_colors import get_group_roi_color
from dataanalysis import Analyser
import pickle

double_validator = QDoubleValidator() # floats
int_validator    = QIntValidator()    # integers
int_validator.setBottom(-1) # don't allow -ve numbers lower than -1
non_neg_validator    = QIntValidator()    # integers
non_neg_validator.setBottom(0) # don't allow -ve numbers
nat_validator    = QIntValidator()    # natural numbers 
nat_validator.setBottom(1) # > 0

class StefanGUI(QMainWindow):
    """Interface to interact with the Stefan. This runs in the main GUI thread
    but the data analysis is performed in the separate Stefan class.
    """
    
    def __init__(self,imagerGUI,index,show_options=True):
        super().__init__()
        self.name = 'STEFAN {}'.format(index)
        self.index = index
        self.setWindowTitle(self.name)
        self.iGUI = imagerGUI # the parent class of this object. Used to refer to methods in that class.
        self.show_options = show_options # show the STEFAN options in the GUI. False when used in ALEX.

        self.mode = 'counts'
        self.xmode = 'file_id'

        self.init_UI()

        # Set the values used in the Stefan to the default values populated in self.init_UI()
        self.update_image_num()
        self.update_roi()
        self.update_post_selection()
        self.update_condition()
        
        self.threadpool = QThreadPool()
        print("Multithreading with maximum %d threads" % self.threadpool.maxThreadCount())

        # self.init_stefan_thread()

    def init_UI(self):
        self.centre_widget = QWidget()
        self.centre_widget.layout = QVBoxLayout()
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)

        layout_xmode_select = QHBoxLayout()
        layout_xmode_select.addWidget(QLabel('x axis:'))
        self.xmode_group=QButtonGroup() # need to use self so that the group is not cleared from memory
        self.button_file_id=QRadioButton('plot File ID')
        self.xmode_group.addButton(self.button_file_id)
        self.button_file_id.setChecked(True)
        layout_xmode_select.addWidget(self.button_file_id)
        self.button_group = QRadioButton('plot group')
        self.xmode_group.addButton(self.button_group)
        layout_xmode_select.addWidget(self.button_group)

        if self.show_options:
            self.centre_widget.layout.addLayout(layout_xmode_select)

        layout_mode_select = QHBoxLayout()
        layout_mode_select.addWidget(QLabel('y axis:'))
        self.mode_group=QButtonGroup()
        self.button_counts=QRadioButton('plot counts')
        self.mode_group.addButton(self.button_counts)
        self.button_counts.setChecked(True)
        layout_mode_select.addWidget(self.button_counts)
        self.button_occupancy = QRadioButton('plot occupancy')
        self.mode_group.addButton(self.button_occupancy)
        layout_mode_select.addWidget(self.button_occupancy)

        if self.show_options:
            self.centre_widget.layout.addLayout(layout_mode_select)

        layout_graph = QHBoxLayout()
        self.graph = pg.PlotWidget() # need to use PlotWidget rather than just plot in this version of pyqtgraph
        self.graph.setBackground('w')
        self.graph_legend = self.graph.addLegend()
        self.graph_lines = []
        
        layout_graph.addWidget(self.graph)
        layout_graph_options = QFormLayout()

        self.box_image = QLineEdit()
        self.box_image.setValidator(non_neg_validator)
        self.box_image.setText(str(0))
        self.box_image.editingFinished.connect(self.update_image_num)
        self.box_image.returnPressed.connect(self.request_update)
        if self.show_options:
            layout_graph_options.addRow('Image:', self.box_image)

        self.box_roi = QLineEdit()
        self.box_roi.setValidator(int_validator)
        self.box_roi.setText(str(0))
        self.box_roi.editingFinished.connect(self.update_roi)
        self.box_roi.returnPressed.connect(self.request_update)
        if self.show_options:
            layout_graph_options.addRow('ROI:', self.box_roi)

        self.box_post_selection = QLineEdit()
        self.box_post_selection.setText('[11],[xx]')
        self.box_post_selection.setEnabled(False)
        self.box_post_selection.editingFinished.connect(self.update_post_selection)
        self.box_post_selection.returnPressed.connect(self.request_update)
        if self.show_options:
            layout_graph_options.addRow('Post-selection:', self.box_post_selection)

        self.box_condition = QLineEdit()
        self.box_condition.setText('[xx],[11]')
        self.box_condition.setEnabled(False)
        self.box_condition.editingFinished.connect(self.update_condition)
        self.box_condition.returnPressed.connect(self.request_update)
        if self.show_options:
            layout_graph_options.addRow('Condition:', self.box_condition)

        self.stats_label = QLabel()
        layout_graph_options.addRow(self.stats_label)

        layout_graph.addLayout(layout_graph_options)
        
        self.centre_widget.layout.addLayout(layout_graph)

        self.button_update = QPushButton('Update')
        self.button_update.clicked.connect(self.request_update)

        if self.show_options:
            self.centre_widget.layout.addWidget(self.button_update)

        self.button_counts.toggled.connect(self.change_mode)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def change_mode(self,mode=None):
        if mode == 'counts':
            self.button_counts.setChecked(True)
        elif mode == 'occupancy':
            self.button_occupancy.setChecked(True)

        if self.button_counts.isChecked():
            self.mode = 'counts'
            self.box_image.setEnabled(True)
            self.box_roi.setEnabled(True)
            self.box_post_selection.setEnabled(False)
            self.box_condition.setEnabled(False)
        else: # assume occupancy button is pressed if the counts button isn't
            self.mode = 'occupancy'
            self.box_image.setEnabled(False)
            self.box_roi.setEnabled(False)
            self.box_post_selection.setEnabled(True)
            self.box_condition.setEnabled(True)

    def init_stefan_thread(self):
        self.stefan_thread = QThread()
        self.stefan = StefanWorker()
        self.stefan.moveToThread(self.stefan_thread)

        ## iGUI and MAIA communicate over signals and slots to ensure thread
        ## safety so connect the signals and slots here before starting the 
        ## MAIA.
        ## See https://stackoverflow.com/questions/35527439/
        
        # Start MAIA thread
        self.stefan_thread.start()

    @pyqtSlot(str)
    def status_bar_message(self,message):
        self.status_bar.setStyleSheet('background-color : #CCDDAA')
        time_str = datetime.now().strftime('%H:%M:%S')
        self.status_bar.showMessage('{}: {}'.format(time_str,message))

    def update_roi(self):
        new_roi = int(self.box_roi.text())
        self.roi = new_roi

    def update_image_num(self):
        new_image_num = int(self.box_image.text())
        self.image = new_image_num

    def update_post_selection(self):
        self.post_selection = self.box_post_selection.text()

    def update_condition(self):
        self.condition = self.box_condition.text()

    def request_update(self):
        self.button_update.setEnabled(False)
        self.status_bar_message('Requested MAIA data.')
        self.iGUI.recieve_stefan_data_request(self)

    def update(self,maia_data):
        self.status_bar_message('Recieved MAIA data.')
        # pickle.dump(maia_data,open('sample_maia_data.p','wb'))

        if self.button_counts.isChecked():
            self.mode = 'counts'
            self.name = 'STEFAN {}: counts: Im{} ROI{}'.format(self.index,self.image,self.roi)
        else:
            self.mode = 'occupancy'
            self.name = 'STEFAN {}: occupancy'.format(self.index)
        
        if self.button_file_id.isChecked():
            self.xmode = 'file_id'
        else:
            self.xmode = 'group'

        self.setWindowTitle(self.name)

        worker = StefanWorker(maia_data,mode=self.mode,xmode=self.xmode,image=self.image,roi=self.roi,
                              post_selection=self.post_selection, condition=self.condition)
        worker.signals.status_bar.connect(self.status_bar_message)
        worker.signals.return_data.connect(self.plot_data)
        self.threadpool.start(worker)
        # worker.signals.result.connect(self.print_output)
        # worker.signals.finished.connect(self.thread_complete)
        # worker.signals.progress.connect(self.progress_fn)
    
    @pyqtSlot(list,str,str,str)
    def plot_data(self,data,label,mode,xmode):
        """Recieves fully processed data from the worker to display on the 
        plot.
        
        Parameters
        ----------
        data : list
            list of the form [[[group0x,group0y],[group1x,group1y],...]]
            Multiple datasets can be included in this list to plot them on the
            same graph.
        label : string
            string to be shown in the STEFAN stats pane
        """
        self.change_mode(mode)
        self.xmode = xmode

        self.graph.clear()
        self.graph.scene().removeItem(self.graph_legend)
        self.graph_legend = self.graph.addLegend()

        if self.xmode == 'group': # expect data to be of the format [above_threshold_data,below_threshold_data,threshold_data]
            [above_threshold_data,below_threshold_data,threshold_data] = data
            for group_num, [above_threshs,below_threshs,threshold_data] in enumerate(zip(above_threshold_data,below_threshold_data,threshold_data)):
                self.graph.plot(*above_threshs,pen=pg.mkPen(None),symbolBrush=get_group_roi_color(group_num,self.roi),symbol='o')
                self.graph.plot(*below_threshs,pen=pg.mkPen(None),symbolBrush=get_group_roi_color(group_num,self.roi),symbol='x')
                self.graph.plot(*threshold_data,pen=pg.mkPen(color=get_group_roi_color(group_num,self.roi),style=Qt.DashLine))
        else:
            for data_num, dataset in enumerate(data):
                for group_num, group in enumerate(dataset):
                    pen = pg.mkPen(color=get_group_roi_color(group_num,self.roi))
                    # print('group',group)
                    [x,y] = group # allow for multiple things to be plotted per group
                    if data_num == 0:
                        self.graph.plot(x,y,pen=pen,name='Group {}'.format(group_num),symbol='x')
                    else:
                        self.graph.plot(x,y,pen=pen,symbol='x')
        self.stats_label.setText(label)
        
        self.button_update.setEnabled(True)

class StefanWorker(QRunnable):
    """Worker thread for data analysis for the STEFAN.

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.
    """
    def __init__(self,maia_data,mode='counts',xmode='file_id',image=0,roi=0,post_selection=None,condition=None):
        """Initialise the worker object.

        Parameters
        ----------
        maia_data : list
            MAIA data that is passed to the StefanWorker for analysis. This 
            data is in the raw MAIA data format that data is stored in 
            mid-run; it has not yet been formatted in a DataFrame.

            The list should be of the format [counts,threshold_data] where 
            counts is the list returned by maia.get_roi_counts() and the 
            threshold_data is the list returned by maia.get_roi_thresholds() 
            (this list also includes the Autothresh information).

            As this is the mid-run MAIA data format, counts data has not yet 
            been converted into occupancy data. If this is needed then the 
            StefanWorker must perform this calculation to prevent MAIA having 
            to work on this during a run. 
        mode : ['counts','occupancy'], optional
            The mode of the StefanWorker. This can either be 'counts' to have 
            the worker just display the counts for a single ROI in each group, 
            or 'occupancy' if more complex post-selection analysis is required. 
            By default 'counts'
        xmode : ['file_id','group'], optional
            The xmode of the StefanWorker. This can either be 'file_id' to have 
            the worker produce data to be plotted with the file ID on the 
            xaxis with the groups as different lines, or the xaxis to be the
            groups with data scattered around the group point.
            By default 'file_id'
        image : int, optional
            The index of the images that the StefanWorker should analyse. Only 
            used if the mode is 'counts'. By default 0
        roi : int, optional
            The index of the ROI that the StefanWorker should analyse. Only 
            used if mode is 'counts'. By default 0
        post_selection : list or None, optional
            List of strings describing the post-selection parameters used by 
            the StefanWorker. Only used if the mode is 'occupancy'. By default 
            None, which will apply no post-selection criteria.
        condition : list or None, optional
            List of strings describing the condition parameters used by the
            StefanWorker. Only used if the mode is 'occupancy'. By default None
            None, which will apply no condition criteria (i.e. all events will
            match the condition).
        """
        super().__init__()
        self.data = maia_data
        self.mode = mode
        self.xmode = xmode
        self.image = image
        self.roi = roi
        self.post_selection = post_selection
        self.condition = condition

        self.group_spread = 0.3 # amount that points are spread out +/- their group number
        self.occupancy_spread = 0.3 # amount that points are spread out +/- their occupancy

        self.signals = StefanWorkerSignals()

    @pyqtSlot()
    def run(self):
        self.signals.status_bar.emit('STEFANWorker beginning analysis')
        analysed_data, analysis_string, analysis_mode, analysis_xmode = self.analysis()
        self.signals.return_data.emit(analysed_data,analysis_string,analysis_mode,analysis_xmode)
        time.sleep(0.5) # prevents the thread being closed before data has been sent

    def analysis(self):
        """Returns data to the STEFAN to be plotted. The val is what should be
        shown in the STEFAN statistics pane.
        
        The data list is set when the worker class is initialised; for details
        of its format see the `self.__init__()` docstring.

        Returns
        -------
        list : list of data to be plotted in the form [[[group0x,group0y],[group1x,...],...]].
               Multiple dataset can be plotted on a single graph; this is 
               passed to the Stefan by passing multiple datasets in the list.
        str : string that should be displayed in the STEFAN stats page.
        """
        counts, thresholds_and_autothreshs, roi_coords = self.data
        data = [[[[],[]]]]
        string = ''
        if self.mode == 'counts':
            try:
                group_dicts = [group[self.roi][self.image] for group in counts]
                counts_data = [list(zip(*sorted(group.items()))) for group in group_dicts] # sort to make sure plot is in order
                counts_data = [np.asarray(x) for x in counts_data]
                thresholds = [group[self.roi][self.image][0] for group in thresholds_and_autothreshs]
                threshold_plotting_data = []
                for group_num, (group, threshold) in enumerate(zip(counts_data,thresholds)):
                    xmin = min(group[0])
                    xmax = max(group[0])
                    thresholdx = [xmin,xmax]
                    thresholdy = [threshold,threshold]
                    threshold_plotting_data.append([thresholdx,thresholdy])
                    loading_prob = (group[1] > threshold).sum()/len(group[1])
                    string += 'Group {} LP = {:.3f}\n'.format(group_num,loading_prob)
                data = [counts_data,threshold_plotting_data]
                self.signals.status_bar.emit('STEFANWorker analysis complete')
            except IndexError as e: # no data has been collected yet
                self.signals.status_bar.emit('STEFANWorker analysis failed: {}'.format(e))
        else:
            print('Analysis mode occupancy')
            print('Post selection', self.post_selection)
            print('Condition', self.condition)

            analyser = Analyser(self.data)
            post_select_probs_errs = analyser.apply_post_selection_criteria(self.post_selection)
            condition_probs_errs = analyser.apply_condition_criteria(self.condition)
            data[0] = np.array(analyser.get_condition_met_plotting_data())
            for group_num, (post_select_prob_err,condition_prob_err) in enumerate(zip(post_select_probs_errs,condition_probs_errs)):
                post_select_prob_err_string = analyser.uncert_to_str(post_select_prob_err['probability'],post_select_prob_err['error in probability']) 
                condition_prob_err_string = analyser.uncert_to_str(condition_prob_err['probability'],condition_prob_err['error in probability']) 
                string += 'Group {}: PS = {}; CM = {}\n'.format(group_num,post_select_prob_err_string,condition_prob_err_string)
            avg_condition_met_probs_errs = analyser.get_avg_condition_met_prob()
            condition_prob_err_string = analyser.uncert_to_str(avg_condition_met_probs_errs['probability'],avg_condition_met_probs_errs['error in probability']) 
            string += '\nAverage CM = {}\n'.format(condition_prob_err_string)

        print(data)
        if self.xmode == 'group':
            # sort data based on whether it is above or below threshold
            try:
                above_threshold_data = []
                below_threshold_data = []
                threshold_data = []
                if self.mode == 'counts':
                    for group, [group_counts_data,group_threshold_data] in enumerate(zip(data[0],data[1])):
                        group_threshold_data[0] = [group-0.5,group+0.5] # change x to be around the group
                        threshold = group_threshold_data[1][0]
                        above_counts = group_counts_data[1][group_counts_data[1]>threshold]
                        below_counts = group_counts_data[1][group_counts_data[1]<threshold]
                        
                        above_threshold_data.append([np.random.uniform(low=group-self.group_spread, high=group+self.group_spread, size=(len(above_counts),)),above_counts])
                        below_threshold_data.append([np.random.uniform(low=group-self.group_spread, high=group+self.group_spread, size=(len(below_counts),)),below_counts])
                        threshold_data.append(group_threshold_data)

                else: # mode is occupancy so just set the 'threshold' to 0.5 as data is binary
                    for group, group_occupancy_data in enumerate(data[0]):
                        group_threshold_data = [[group-0.5,group+0.5],[0.5,0.5]] # change x to be around the group
                        threshold = group_threshold_data[1][0]
                        above_counts = group_occupancy_data[1][group_occupancy_data[1]>threshold]
                        below_counts = group_occupancy_data[1][group_occupancy_data[1]<threshold]
                        
                        above_threshold_data.append([np.random.uniform(low=group-self.group_spread, high=group+self.group_spread, size=(len(above_counts),)),
                                                     np.random.uniform(low=1-self.occupancy_spread, high=1, size=(len(above_counts),))])
                        below_threshold_data.append([np.random.uniform(low=group-self.group_spread, high=group+self.group_spread, size=(len(below_counts),)),
                                                     np.random.uniform(low=0, high=0+self.occupancy_spread, size=(len(below_counts),))])
                        threshold_data.append(group_threshold_data)

                data = [above_threshold_data,below_threshold_data,threshold_data]

            except IndexError:
                data = [[[],[]],[[],[]],[[],[]]] # no data yet

        print(string)
        return data, string, self.mode, self.xmode

class StefanWorkerSignals(QObject):
    """Defines the signals available from a running StefanWorker thread.
    """
    status_bar = pyqtSignal(str)
    return_data = pyqtSignal(list,str,str,str)



