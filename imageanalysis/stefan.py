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
                          QCoreApplication, QRunnable, QThreadPool)
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
    
    def __init__(self,imagerGUI,index):
        super().__init__()
        self.name = 'STEFAN {}'.format(index)
        self.index = index
        self.setWindowTitle(self.name)
        self.iGUI = imagerGUI # the parent class of this object. Used to refer to methods in that class.

        self.mode = 'counts'
        self.image = 0
        self.roi = 0

        self.init_UI()
        
        self.threadpool = QThreadPool()
        print("Multithreading with maximum %d threads" % self.threadpool.maxThreadCount())

        # self.init_stefan_thread()

    def init_UI(self):
        self.centre_widget = QWidget()
        self.centre_widget.layout = QVBoxLayout()
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)
        # self.layout = QVBoxLayout()
        # self.setLayout(self.layout)

        layout_mode_select = QHBoxLayout()
        mode_group=QButtonGroup()
        self.button_counts=QRadioButton('plot counts')
        mode_group.addButton(self.button_counts)
        self.button_counts.setChecked(True)
        layout_mode_select.addWidget(self.button_counts)

        self.button_occupancy = QRadioButton('plot occupancy')
        mode_group.addButton(self.button_occupancy)
        self.button_occupancy.setCheckable(False)
        layout_mode_select.addWidget(self.button_occupancy)

        self.centre_widget.layout.addLayout(layout_mode_select)

        layout_graph = QHBoxLayout()
        # self.graph.setBackground(None)
        # self.graph.getAxis('left').setTextPen('k')
        # self.graph.getAxis('bottom').setTextPen('k')
        # self.graph.getAxis('top').setTextPen('k')
        # self.graph.enableAutoRange()
        # self.graph = pg.plot(labels={'left': ('index'), 'bottom': ('counts')})
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
        layout_graph_options.addRow('Image:', self.box_image)

        self.box_roi = QLineEdit()
        self.box_roi.setValidator(int_validator)
        self.box_roi.setText(str(0))
        self.box_roi.editingFinished.connect(self.update_roi)
        self.box_roi.returnPressed.connect(self.request_update)
        layout_graph_options.addRow('ROI:', self.box_roi)

        self.box_post_selection = QLineEdit()
        self.box_post_selection.setText(str(1))
        self.box_post_selection.setEnabled(False)
        layout_graph_options.addRow('Post-selection:', self.box_post_selection)

        self.box_condition = QLineEdit()
        self.box_condition.setText(str(1))
        self.box_condition.setEnabled(False)
        layout_graph_options.addRow('Condition:', self.box_condition)

        layout_graph.addLayout(layout_graph_options)
        self.centre_widget.layout.addLayout(layout_graph)

        self.button_update = QPushButton('Update')
        self.button_update.clicked.connect(self.request_update)
        self.centre_widget.layout.addWidget(self.button_update)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

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

    def request_update(self):
        self.button_update.setEnabled(False)
        self.status_bar_message('Requested MAIA data.')
        self.iGUI.recieve_stefan_data_request(self)

    def update(self,maia_data):
        self.status_bar_message('Recieved MAIA data.')
        print(maia_data)

        if self.mode == 'counts':
            self.name = 'STEFAN {}: counts: Im{} ROI{}'.format(self.index,self.image,self.roi)
        else:
            self.name = 'STEFAN {}'.format(self.index)
        self.setWindowTitle(self.name)

        worker = StefanWorker(maia_data,image=self.image,roi=self.roi) # Any other args, kwargs are passed to the run function
        self.threadpool.start(worker)
        worker.signals.status_bar.connect(self.status_bar_message)
        worker.signals.return_data.connect(self.plot_data)
        # worker.signals.result.connect(self.print_output)
        # worker.signals.finished.connect(self.thread_complete)
        # worker.signals.progress.connect(self.progress_fn)
    
    @pyqtSlot(list)
    def plot_data(self,data):
        print('plot_data')
        # print(data)
        self.graph.clear()
        self.graph.scene().removeItem(self.graph_legend)
        self.graph_legend = self.graph.addLegend()

        for group_num, group in enumerate(data):
            pen = pg.mkPen(color=get_group_roi_color(group_num,self.roi))
            self.graph.plot(np.arange(len(group)),group,pen=pen,name='Group {}'.format(group_num))
        
        self.button_update.setEnabled(True)

class StefanWorker(QRunnable):
    """Worker thread for data analysis for the STEFAN.

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.
    """
    def __init__(self,maia_data,mode='counts',image=0,roi=0,post_selection=None,condition=None):
        super().__init__()
        self.data = maia_data
        self.mode = mode
        self.image = image
        self.roi = roi
        self.post_selection = post_selection
        self.condition = condition

        self.signals = StefanWorkerSignals()

    @pyqtSlot()
    def run(self):
        print('started analysis')
        self.signals.status_bar.emit('STEFANWorker beginning analysis')
        analysed_data = self.analysis()
        self.signals.return_data.emit(analysed_data)
        print('finished analysis')
        time.sleep(0.5) # prevents the thread being closed before data has been sent

    def analysis(self):
        if self.mode == 'counts':
            try:
                data = [group[self.roi][self.image] for group in self.data]
                self.signals.status_bar.emit('STEFANWorker analysis complete')
            except IndexError as e:
                data = [[]]
                self.signals.status_bar.emit('STEFANWorker analysis failed: {}'.format(e))
        else:
            data = [[]]
        return data

class StefanWorkerSignals(QObject):
    """Defines the signals available from a running StefanWorker thread.
    """
    status_bar = pyqtSignal(str)
    return_data = pyqtSignal(list)



