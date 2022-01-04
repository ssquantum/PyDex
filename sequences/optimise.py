"""PyDex Optimisation
Stefan Spence 03/12/20

 - Provide a GUI for inputting parameters for optimisation
 - Use M-LOOP to optimise parameters
"""
import os
import sys
import time
import copy
import json
import numpy as np
from collections import OrderedDict
import pyqtgraph as pg
# import mloop.interfaces as mli
# import mloop.controllers as mlc
# import mloop.visualizations as mlv
from PyQt5.QtCore import (pyqtSignal, QItemSelectionModel, QThread, Qt,
    QEventLoop, QTimer)
from PyQt5.QtGui import QDoubleValidator, QIntValidator, QFont
from PyQt5.QtWidgets import (QVBoxLayout, QWidget, QComboBox,
    QLineEdit, QGridLayout, QPushButton, QListWidget, QListWidgetItem, 
    QScrollArea, QLabel, QTableWidget, QTableWidgetItem, QMessageBox,
        QFileDialog, QTextBrowser)
sys.path.append('.')
sys.path.append('..')
from mythread import reset_slot # for dis- and re-connecting slots
from strtypes import error, warning, info
from .imageanalysis.fitCurve import fit
####    ####    ####    ####

# @contextmanager
# def wait_signal(signal, timeout=10000):
#     """Block loop until signal emitted, or timeout (ms) elapses.
#     https://www.jdreaver.com/posts/2014-07-03-waiting-for-signals-pyside-pyqt.html"""
#     loop = QEventLoop()
#     signal.connect(loop.quit)
#     yield
#     if timeout is not None:
#         QTimer.singleShot(timeout, loop.quit)
#     loop.exec_()

# class MLOOPInterface(mli.Interface):
#     opt_params = pyqtSignal(np.ndarray) # the array of optimal values
#     progress = pyqtSignal(str) # string detailing the progress of the optimisation

#     def __init__(self, costfunc, measure):
#         super(CustomInterface,self).__init__()
#         importlib.reload(fitFunctions)
#         self.costfunc = fitFunctions.costfunc

#     def get_next_cost_dict(self,params_dict):
#         """The cost function needs to send our suggested parameters, run the 
#         experiment, then return a cost."""
#         try:
#             cost, uncer = self.costfunc(*params_dict['params']) # Cost from the algorithm 
#             bad = False
#         except Exception as e:
#             error('Exception: '+str(e))
#             cost = -1
#             uncer = 0
#             bad = True
#         return {'cost':cost, 'uncer':uncer, 'bad':bad}

#('Type', strlist), , ('Repeats', int) ('Maximise', BOOL)
# ('Analogue type', strlist), ('Time step name', listlist), 
# ('Analogue channel', listlist), 
# ('Controller type',str), ('Max # runs', int), ('Target cost', float), 
# ('Trust region', float), ('Archive filename', str), 
 # interface = CustomInterface()
        # controller = mlc.create_controller(interface,controller_type = 'neural_net', # 
        #                 max_num_runs = 1000, # these don't include training runs
        #                 target_cost =0.001, # value of the cost function to aim for
        #                 num_params = 3, # detuning, duration, rabi freq
        #                 min_boundary = [0.9,0.1,1], # lower limit on parameters
        #                 max_boundary = [1.1,1.5,400], # upper limit on parameters
        #                 cost_has_noise = False,trust_region = 0.4,
        #                 learner_archive_filename='RSCm-loop_learner_archive.txt')
        # controller.optimize()
        # print('Best parameters found:')
        # print(controller.best_params)
        # with wait_signal(simulator.finished, timeout=10000):
        #     run sim


####    ####    ####    ####

class optimise_widget(QWidget):
    """Widget for editing optimisations.

    Keyword arguments:
    mr    -- multirun_widget instance
    """
    request_analysis = pyqtSignal(str) # request an instance of image analysis
    
    def __init__(self, mr):
        super().__init__()
        self.setp = OrderedDict([('measure_prefix','Measure0'), 
            ('Cost Variable', 'Loading probability'), ('Cost Function', 'offGauss'),
            ('Param Labels', ['Param0']), ('Param Mins', [0]), 
            ('Param Maxs', [1]), ('First Params', [1]), 
            ('Param index', 0), ('Analysis Window', 'ROI0_Re_')])
        self.mr = mr # multirun widget
        self.f = fit() # for fitting
        self.hh = None # will contain a histo_handler from an image_analyser
        self.init_UI()  # edit the widgets
       
    def init_UI(self):
        """Initiate widgets"""
        self.widget = QWidget()
        self.widget.layout = QGridLayout()
        self.widget.setLayout(self.widget.layout)
        self.setCentralWidget(self.widget)
        
        #### validators for user input ####
        double_validator = QDoubleValidator() # floats
        int_validator = QIntValidator(0,10000000) # positive integers
        msr_validator = QIntValidator(-1,1000000) # integers >= -1
        nat_validator = QIntValidator(1,10000000) # natural numbers
        col_validator = QIntValidator(1,self.ncols-1) # for number of columns
        
        self.load_measure = QPushButton('Load measure', self)
        self.widget.layout.addWidget(self.load_measure, 0,0, 1,1)
        self.load_measure.clicked.connect(self.)
        
        self.measure_label = QLabel('', self)
        self.widget.layout.addWidget(self.load_measure, 0,1, 1,1)
        
        self.status_label = QTextBrowser() 
        self.widget.layout.addWidget(self.status_label, 1,0, 2,4)
        
        font = QFont()
        font.setPixelSize(14)
        self.varplot_canvas = pg.PlotWidget()
        self.varplot_canvas.getAxis('bottom').tickFont = font
        self.varplot_canvas.getAxis('left').tickFont = font
        self.widget.layout.addWidget(self.varplot_canvas, 6,0, 2,4)
        
        self.var_label = QLabel(self.get_label(), self)
        self.widget.layout.addWidget(self.var_label, 7,1, 1,1)
        
        #listbox.add(fit.fitFuncs)
        
    def display(self, txt):
        """Display message string on text browser."""
        self.status_label.append(time.strftime("%d/%m/%Y %H:%M:%S") + '>> ' + txt)
        
    def get_label(self):
        try:
            return self.setp['Param Labels'][self.setp['Param index']]
        except: return ''
        
    def get_tcp_msg(self, val):
        """Reformat the multirun paramaters into a string to be sent to the AWG, DDS, or SLM"""
        module = ''
        msg = '{0} set_data=['
        if 'AWG' in self.mr.mr_param['Type'][0] and module == 'AWG':
            try: # argument: value
                for n in self.mr.mr_param['Time step name'][0]: # index of chosen AWG channel, segment 
                    for m in self.mr.mr_param['Analogue channel'][0]:
                        msg += '[%s, %s, "%s", %s, %s],'%(n%2, n//2, 
                            self.mr.awg_args[m], val, 
                            self.mr.mr_param['list index'][0])
                module = 'AWG'
            except Exception as e: error('Invalid AWG parameter'+str(e))
        elif 'DDS' in self.mr.mr_param['Type'][0] and module == 'DDS':
            try: # argument: value
                for n in self.mr.mr_param['Time step name'][0]: # index of chosen DDS COM port, profile
                    for m in self.mr.mr_param['Analogue channel'][0]:
                        port = '"P%s"'%(n%9) if (n%9)<8 else '"aux"'
                        msg += '["COM%s", '%((n//9)+7)+port+', "%s", %s],'%(# we use COM7 - COM11
                            self.mr.dds_args[m], val)
                module = 'DDS'
            except Exception as e: error('Invalid DDS parameter\n'+str(e))
        elif 'SLM' in self.mr.mr_param['Type'][0] and module == 'SLM':
            try: # argument: value
                for n in self.mr.mr_param['Time step name'][0]: # index of chosen SLM hologram
                    for m in self.mr.mr_param['Analogue channel'][0]:
                        msg += '[%s,"%s",%s],'%(n, # [holo index, parameter, value]
                            self.mr.slm_args[m], val)
                module = 'SLM'
            except Exception as e: error('Invalid SLM parameter\n'+str(e))
        if len(module): msg = msg[:-1].format(module) + ']'
        else: msg += ']'
        return msg
        
    def get_opt_sequence(self):
        """Edit the sequence with the optimised value."""
        try:
            val = self.f.ps[self.setp['Param index']]
        except IndexError as e:
            error('Could not retrieve best fit param: '+str(f.ps)+'\n'+str(e))
            return ''
        esc = self.mr.tr.get_esc() # shorthand
        num_s = len(esc[2]) - 2 # number of steps
        try:
            if self.mr.mr_param['Type'][0] == 'Time step length':
                for head in [2, 9]:
                    for t in self.mr.mr_param['Time step name'][0]:
                        esc[head][t+2][3][1].text = str(val)
            elif self.mr.mr_param['Type'][0] == 'Analogue voltage':
                for t in self.mr.mr_param['Time step name'][0]:
                    for c in self.mr.mr_param['Analogue channel'][0]:
                        if 'Fast' in self.mr.mr_param['Analogue type'][0]:
                            esc[6][t + c*num_s + 3][3][1].text = str(val)
                        else:
                            esc[11][t + c*num_s + 3][3][1].text = str(val)
            tcpmsg = self.get_tcp_msg('%.4f'%val)
            self.mr.tr.set_routine_name('Fitted ' + self.mr.mr_param['Variable label'] + \
                    ': %.4f'%val
        except IndexError as e:
            error('Multirun failed to edit sequence at ' + self.mr.mr_param['Variable label']
                + '\n' + str(e))
        return (self.mr.tr.write_to_str(), tcpmsg)

    #### save and load parameters ####

    def load_params(self, load_file_name=''):
        """Load the multirun variables array from a file."""
        if not load_file_name:
            load_file_name = self.mr.try_browse(title='Load File', file_type='csv(*.csv);;all (*)', 
                        open_func=QFileDialog.getOpenFileName)
        if load_file_name:
            self.mr.load_mr_params(load_file_name)
            try:
                with open(load_file_name, 'r') as f:
                    _ = f.readline()
                    vals = [x.split(',') for x in f.readline().replace('\n','').split(';')]
                    header = f.readline().replace('\n','').split(';')
                    mr_params = f.readline().split(';')
                    params = json.loads(f.readline())
                    
                for key, val in params.items():
                    self.setp[key] = val
                self.request_analysis.emit(self.setp['Analysis Window'])
            except Exception as e:
                self.display('Failed to load file %s.\n'%load_file_name+str(e))