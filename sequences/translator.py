"""Networking - Sequence Translator
Stefan Spence 19/02/21

 - translate DExTer sequences to/from XML
The functions here are specific to the format of 
sequences that DExTer generates.
"""
import lxml
from lxml import etree
import sys
import logging
import os
import copy
logger = logging.getLogger(__name__)

#### #### dictionary of indexes in tree #### ####
tdict = { # i: time step, j: channel
'Event list array in':2,
    'Event name':2,    # e.g. tree[1][2][i+2][2][1].text
    'Event indices':3,
    'Event path':4,
    'Routine specific event?':5,
'Experimental sequence cluster in':3,
    'Sequence header top':2, 
        # 'Event name':2, # no duplicates
        'Time step length':3, # tree[1][3][2][i+2][3][1].text 
        'Trigger details':4, 
            'Analogue voltage (V)':2, 
            'Digital or analogue trigger?':3, 
            'Channel':4, 
            'Trigger this time step?':5,
        'GPIB routine data':5, 
            'GPIB event name':2, 
            'GPIB on/off?':3,
        'Time step name':6, 
        'Hide event steps':7, 
        'Populate multirun':8, 
        'Time unit':9, 
        'Event ID':10, 
        'Skip Step':11,
    'Fast digital channels':3, # tree[1][3][3][i*56+j*num_steps+3][1].text
    'Fast digital names':4, 
    'Fast analogue names':5, 
    'Fast analogue array':6,   # ramp: tree[1][3][6][i*8+j*num_steps+3][2][1].text, voltage: tree[1][3][6][i*8+j*num_steps+3][3][1].text
    'Slow digital channels':7, # tree[1][3][7][i*48+j*num_steps+3][1].text
    'Slow digital names':8, 
    'Sequence header middle':9, 
    'Slow analogue names':10, 
    'Slow analogue array':11,  # ramp: tree[1][3][11][i*32+j*num_steps+3][2][1].text, voltage: tree[1][3][11][i*32+j*num_steps+3][3][1].text
'Routine name in':4,           # tree[1][4][1].text
'Routine description in': 5,
}

#### #### dummy empty sequence #### ####
root = etree.Element('{http://www.ni.com/LVData}LVData')
a = etree.SubElement(root, 'branch')
a = etree.SubElement(root, 'branch')
for i in range(8):
    b = etree.SubElement(a, 'sequence')
    for j in range(8):
        c = etree.SubElement(b, 'cluster')
        for k in range(14):
            d = etree.SubElement(c, '{http://www.ni.com/LVData}I32')
            for k in range(14):
                e = etree.SubElement(d, '{http://www.ni.com/LVData}I32')
                for l in range(4):
                    f = etree.SubElement(e, '{http://www.ni.com/LVData}I32')
                    for m in range(2):
                        g = etree.SubElement(f, '{http://www.ni.com/LVData}I32')
for e in root.iter():
    e.text = '0'


#### #### Convert xml <-> element tree #### ####

class translate:
    """Write DExTer sequences to XML files.
    Facilitate editing of several variables quickly.
    A sequence has a fixed number of events, num_e,
    which give a total number of time steps, num_s.
    If fname is a file containing a sequence in XML
    format, then it will be loaded."""
    def __init__(self, fname='', num_e=1, num_s=1):
        self.nfd = 56 # number of fast digital channels
        self.nfa = 8  # number of fast analogue
        self.nsd = 48 # number of slow digital
        self.nsa = 32 # number of slow analogue
        self.parser = etree.XMLParser(encoding='cp1252')
        self.seq_tree = root
        self.seq_txt = ''
        if fname:
            self.load_xml(fname)

    def write_to_file(self, fname='sequence_example.xml'):
        """Write the current sequence in the dictionary
        format to an XML file with name fname."""
        try:
            with open(fname, 'w+') as f:
                f.write(self.seq_txt)
        except (FileNotFoundError, OSError) as e: 
            logger.error('Translator could not save sequence:\n'+str(e))
            
    def write_to_str(self):
        """Store the current sequence in the dictionary
        in XML string format specified by LabVIEW and
        return this string."""
        try:
            self.seq_txt = '<?xml version="1.0" standalone="yes" ?>\n' + etree.tostring(
                self.seq_tree, encoding='cp1252', method='html').decode('cp1252')
        except TypeError as e:
            logger.error('Translator could not write sequence to str\n'+str(e))
            self.seq_txt = ''
        return self.seq_txt

    def setup_multirun(self):
        """In order for DExTer to accept changes to the sequence, all
        events must be routine specific and populate multirun true."""
        for event in self.seq_tree[1][2][2:]: # 'Event list array in'
            event[5][1].text = '1' # 'Routine sepecific event?'
        for head in [2, 9]: # 'Sequence header top', 'Sequence header middle'
            for step in self.seq_tree[1][3][head][2:]: 
                step[8][1].text = '1' # 'Populate multirun'
                
    def load_xml(self, fname='./sequences/SequenceFiles/empty.xml'):
        """Load a sequence as a dictionary from an xml file."""
        try:
            self.seq_tree = etree.parse(fname, parser=self.parser).getroot()
            for e in self.seq_tree.iter():
                if e.text == None:
                    e.text = ''
            self.setup_multirun()
            self.write_to_str()
        except (FileNotFoundError, OSError) as e: 
            logger.error('Translator could not load sequence:\n'+str(e))

    def load_xml_str(self, text=""):
        """Load a sequence as a dictionary from an xml string."""
        try:
            self.seq_tree = etree.fromstring(text, parser=self.parser)
            for e in self.seq_tree.iter():
                if e.text == None:
                    e.text = ''
            self.setup_multirun()
            self.write_to_str()
        except (lxml.etree.XMLSyntaxError) as e: 
            logger.error('Translator could not load sequence:\n'+str(e))
    
    def copy(self):
        """Create a copy of this translate object"""
        t = translate()
        t.nfd = self.nfd # number of fast digital channels
        t.nfa = self.nfa # number of fast analogue
        t.nsd = self.nsd # number of slow digital
        t.nsa = self.nsa # number of slow analogue
        t.seq_tree = copy.deepcopy(self.seq_tree) # need deep copy of dict because values are mutable
        # t.write_to_str()
        return t