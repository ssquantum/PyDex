"""Single Atom Comp-Image Analyser
Stefan Spence 23/03/21
For use in a sequence with several ROIs.

 - Create several main.py instances of SAIA to analyse different images 
 in a sequence
 - Display the survival histogram - if there are atoms in all of the 
 first images, then take the second images.
"""
import os
import sys
import time
import numpy as np
import pyqtgraph as pg    # not as flexible as matplotlib but works a lot better with qt
# some python packages use PyQt4, some use PyQt5...
try:
    from PyQt4.QtCore import pyqtSignal 
    from PyQt4.QtGui import (QFont, QLabel, QMessageBox, QPushButton,
        QCheckBox, QComboBox, QLineEdit, QIntValidator, QAction)
except ImportError:
    from PyQt5.QtCore import pyqtSignal
    from PyQt5.QtGui import QFont, QIntValidator
    from PyQt5.QtWidgets import (QLabel, QMessageBox, QPushButton,
        QCheckBox, QComboBox, QLineEdit, QAction)
from maingui import main_window, reset_slot
from compHandler import comp_handler

# main GUI window contains all the widgets                
class compim_window(main_window):
    """GUI window managing several sub-instances of SAIA.

    If an image in set [hists1] contains atoms, use the corresponding image from
    the after histograms. Compare the histograms to find joint recapture.
    Keyword arguments:
    signal        -- the pyqtSignal that is used to trigger updates
    befores       -- list of image_handler from before histograms.
    afters        -- list of image_handler from after histograms.
    names         -- list of string IDs for possible histograms to choose from
    results_path  -- directory to save log file and results to.
    im_store_path -- the directory where images are saved.
    name          -- an ID for this window, prepended to saved files.
    """
    request = pyqtSignal((str, list, list)) # send request for new data
    data = pyqtSignal(list)   # receive new data

    def __init__(self, signal, names, befores=[], afters=[], results_path='.', 
            im_store_path='.', name=''):
        self.event_im = signal # uses the signal from a SAIA instance
        self.names = names
        super().__init__(results_path=results_path, 
                        im_store_path=im_store_path, name=name,
                        hist_handler=comp_handler(befores, afters))
        self.adjust_UI() # adjust widgets from main_window
        self.reset_handlers(befores, afters) # histo_handler replaced with comp_handler
        
    def adjust_UI(self):
        """Edit the widgets created by main_window"""
        self.setWindowTitle(self.name+' - Comp-Image Analyser - ')

        int_validator    = QIntValidator()    # integers
        nat_validator    = QIntValidator()    # natural numbers 
        nat_validator.setBottom(1)

        #### edit menubar
        menubar = self.menuBar()
        menubar.clear()
        
        # histogram menu saves/loads/resets histogram and gives binning options
        hist_menu =  menubar.addMenu('Histogram')
        save_hist = QAction('Save histogram', self) # save current hist to csv
        save_hist.triggered.connect(self.save_hist_data)
        hist_menu.addAction(save_hist)
        reset_hist = QAction('Reset histogram', self) # reset hist without loading new data
        reset_hist.triggered.connect(self.load_empty_hist)
        hist_menu.addAction(reset_hist)
        
        # load plots from log files
        varplot_menu = menubar.addMenu('Plotting')
        load_varplot = QAction('Load from log file', self)
        load_varplot.triggered.connect(self.load_from_log)
        varplot_menu.addAction(load_varplot)

        #### edit settings tab: choose from list of image handlers ####
        settings_grid = self.tabs.widget(0).layout()
        # remove the settings which are redundant
        for i in reversed(range(settings_grid.count())):
            if i > 1:
                widget = settings_grid.itemAt(i).widget()
                settings_grid.removeWidget(widget)
                widget.setParent(None)

        self.before_choice = []
        self.before_cond   = []
        self.after_choice  = []
        self.after_cond    = []
        self.nhist_label = QLabel('# Histograms:')
        settings_grid.addWidget(self.nhist_label, 1,0,1,1)
        self.nhist_edit = QLineEdit('1', self)
        self.nhist_edit.setValidator(nat_validator)
        settings_grid.addWidget(self.nhist_edit, 1,1,1,1)
        self.nhist_edit.editingFinished.connect(self.set_combo_boxes)
        self.natoms_label = QLabel('Load N atoms:', self)
        settings_grid.addWidget(self.natoms_label, 2,0,1,1)
        self.natoms_edit = QLineEdit(self)
        self.natoms_edit.setValidator(int_validator)
        settings_grid.addWidget(self.natoms_edit, 2,1,1,1)
        self.set_combo_boxes()
        reset_combos_button = QPushButton('Apply Changes', self)
        reset_combos_button.clicked.connect(self.request_update)
        reset_combos_button.resize(reset_combos_button.sizeHint())
        settings_grid.addWidget(reset_combos_button, 5,1,1,1)
        
        #### edit histogram tab: 
        hist_grid = self.tabs.widget(1).layout()
        menubar = self.menuBar() # menu selects which histogram to display
        self.hist_choice = QComboBox(self)
        hist_grid.addWidget(self.hist_choice, 8,0, 1,2)
        self.hist_type = QComboBox(self)
        hist_grid.addWidget(self.hist_type, 8,2, 1,2)
        
        #### edit stats tab: display all histogram statistics ####
        self.reset_stat_labels()
        
        # take the threshold from the second image handler
        self.thresh_toggle.setChecked(True)

    #### #### canvas functions #### ####

    def reset_stat_labels(self):
        """When the number of histograms changes, we need to update the labels"""
        stat_grid = self.tabs.widget(2).layout()
        for i in reversed(range(stat_grid.count())):
            if i > 1: # clear all except user variable
                widget = stat_grid.itemAt(i).widget()
                stat_grid.removeWidget(widget)
                widget.setParent(None)
        
        self.stat_labels = {}  # dictionary of stat labels
        for i, label_text in enumerate(self.histo_handler.stats.keys()):
            new_label = QLabel(label_text, self) # description
            stat_grid.addWidget(new_label, i+1,0, 1,1)
            self.stat_labels[label_text] = QLabel('', self) # value
            stat_grid.addWidget(self.stat_labels[label_text], i+1,1, 1,1)
            
        self.stat_update_button = QPushButton('Update statistics', self)
        self.stat_update_button.clicked[bool].connect(self.display_fit)
        stat_grid.addWidget(self.stat_update_button, i+3,0, 1,1)
        add_to_plot = QPushButton('Add to plot', self)
        add_to_plot.clicked[bool].connect(self.add_stats_to_plot)
        stat_grid.addWidget(add_to_plot, i+3,2, 1,1)

        for x in self.plot_labels[:2]:
            x.clear()
            x.addItems(list(self.histo_handler.stats.keys())) 

    def set_logic(self):
        self.histo_handler.c0 = [int(x.isChecked()) for x in self.before_cond]
        self.histo_handler.c1 = [int(x.isChecked()) for x in self.after_cond]

    def set_combo_boxes(self):
        """Make the right number of combo boxes to choose histograms from"""
        try:
            self.nhist = int(self.nhist_edit.text())
        except TypeError:
            self.nhist = 1
            self.nhist_edit.setText('1')
        layout = self.tabs.widget(0).layout()
        for i in range(min(self.nhist, len(self.after_cond))): # update current widgets
            for x in [self.before_choice, self.after_choice]:
                x[i].clear()
                x[i].addItems(self.names)
                x[i].show()
            for x in [self.before_cond, self.after_cond]:
                x[i].show()
            
        for i in range(len(self.after_cond), self.nhist): # add new widgets
            for j, x in enumerate([self.before_choice, self.after_choice]):
                widget = QComboBox(self)
                widget.addItems(self.names)
                # widget.activated[str].connect() 
                layout.addWidget(widget, 1+j*2,i+2,1,1)
                x.append(widget)
            for j, x in enumerate([self.before_cond, self.after_cond]):
                widget = QCheckBox(self)
                widget.setChecked(True)
                widget.stateChanged.connect(self.set_logic)
                layout.addWidget(widget, 2+j*2,i+2,1,1)
                x.append(widget)

        for j in range(self.nhist, len(self.after_cond)): # hide unwanted widgets
            for x in [self.before_choice, self.after_choice, self.before_cond, self.after_cond]:
                x[j].hide()
        
    def reset_handlers(self, befores, afters):
        """Reset which histograms are being used for the analysis
        befores -- image_handlers for the 1st histograms
        afters  -- image_handlers for the 2nd histograms"""
        self.nhist = len(befores) # number of histograms being compared
        self.histo_handler = comp_handler(befores, afters, self.nhist, 
            inp_cond=[x.isChecked() for x in self.before_cond], 
            out_cond=[x.isChecked() for x in self.after_cond])
        self.hist_choice.clear()
        self.hist_choice.addItems([x.name for x in self.histo_handler.afters])
        self.hist_type.clear()
        self.hist_type.addItems(['Survival', 'Condition met'] + ['%s atom'%i for i in range(self.nhist+1)])
        self.reset_stat_labels()
        
    
    def get_histogram(self):
        """Take the histogram from the 'after' images where the 'before' images
        meet the specified condition."""
        try:
            t1 = time.time()
            names = [x.name for x in self.histo_handler.afters]
            ind = names.index(self.hist_choice.currentText())
            hist_type = self.hist_type.currentText()
            if 'Survival' in hist_type:
                hist_type = names[ind] + ' survival'
            incl = np.isin(self.histo_handler.afters[ind].stats['File ID'], self.histo_handler.hist_ids[hist_type])
            for key in self.image_handler.stats.keys():
                self.image_handler.stats[key] = list(np.array(self.histo_handler.afters[ind].stats[key])[incl])
            self.image_handler.ind = self.histo_handler.afters[ind].ind
            self.image_handler.thresh = self.histo_handler.afters[ind].thresh
            t2 = time.time()
            self.int_time = t2 - t1
        except (ValueError, OverflowError, IndexError): t2 = 0 
        return t2

    def request_update(self):
        """Take the values from the comboboxes and ask the settings window 
        to send the appropriate image_handlers"""
        self.request.emit(self.objectName(), [x.currentText() for x in self.before_choice if x.isVisible()], 
            [x.currentText() for x in self.after_choice if x.isVisible()])

    #### #### Overridden display functions #### ####

    def display_fit(self, toggle=True, fit_method='quick'):
        success = self.histo_handler.process(self.stat_labels['User variable'].text(), 
            natoms=int(self.natoms_edit.text()) if self.natoms_edit.text() else -1, include=True)
        if success: 
            for key in self.histo_handler.stats.keys(): # update the text labels
                self.stat_labels[key].setText(str(self.histo_handler.temp_vals[key]))
            self.plot_current_hist(self.image_handler.histogram, self.hist_canvas)
    
    def update_plot(self, im, include=True):
        """Same as update_plot_only."""
        t2 = self.get_histogram()
        self.plot_current_hist(self.image_handler.histogram, self.hist_canvas) # update the displayed plot
        self.plot_time = time.time() - t2

    def update_plot_only(self, im, include=True):
        """Show the histogram on the canvas."""
        t2 = self.get_histogram()
        self.plot_current_hist(self.image_handler.histogram, self.hist_canvas) # update the displayed plot
        self.plot_time = time.time() - t2

    #### #### Overridden save and load functions #### ####

    def check_reset(self):
        """Ask the user if they would like to reset the current data stored"""
        reply = QMessageBox.information(self, 'Confirm Data Replacement',
            "This window does not support this action.")
        return 0

    def load_from_files(self):
        reply = QMessageBox.information(self, 'Load From Files',
            "This window does not support this action.")
        return 0

    def load_from_file_nums(self):
        reply = QMessageBox.information(self, 'Confirm Data Replacement',
            "This window does not support this action.")
        return 0

    def load_from_csv(self, trigger=None):
        """Prompt the user to select a csv file to load histogram data from.
        It must have the specific layout that the image_handler saves in."""
        # if self.check_reset():
        #     before_fn = self.try_browse(title='Select first histogram', file_type='csv(*.csv);;all (*)')
        #     after_fn = self.try_browse(title='Select second histogram', file_type='csv(*.csv);;all (*)')
        #     if before_fn and after_fn:
        #         header = self.ih1.load(before_fn)
        #         header = self.ih2.load(after_fn)
        #         if self.ih1.ind > 0:
        #             self.display_fit(fit_method='quick')

    #### #### Overridden user input functions #### ####

    #### #### toggle functions #### #### 
    