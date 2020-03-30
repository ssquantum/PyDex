"""Networking - Sequence Translator
Stefan Spence 04/10/19

 - translate DExTer sequences to/from XML
The functions here are specific to the format of 
sequences that DExTer generates.

Note: to make it faster we could use xml.dom.minidom 
instead of python dictionaries. Since LabVIEW uses
some unicode characters, would need to parse it like
with open('filename', 'r') as f:
 dm = xml.dom.minidom.parseString(f.read().replace('\n','').replace('\t','').encode('utf-8'))
"""
import xmltodict
import xml.dom.minidom
import xml.parsers.expat
import sys
import numpy as np
from collections import OrderedDict
import logging
import os
import copy
logger = logging.getLogger(__name__)

#### #### DExTer clusters #### ####

def event_list(name='', routinespec=False, indices=[], path=''):
    """Define a dictionary for DExTer's event
    list cluster since it's used several times."""
    return OrderedDict([('Event name',name),
            ('Routine specific event?',routinespec),
            ('Event indices',indices),
            ('Event path',path)])

def header_cluster(skip=False, ename='', hide=False, ID='',
        tsname='', populate=False, tslen=1, tunit=1, dora=0,
        trigger=False, channel=0, av=0, gpibevent=0, gpibon=False):
    """Define a dictionary for DExTer's matrix header
    cluster since it's used several times."""
    return OrderedDict([('Skip Step',skip),
            ('Event name',ename),
            ('Hide event steps',hide),
            ('Event ID',ID),
            ('Time step name',tsname),
            ('Populate multirun',populate),
            ('Time step length',tslen),
            ('Time unit',tunit),
            ('Digital or analogue trigger?',dora),
            ('Trigger this time step?',trigger),
            ('Channel',channel),
            ('Analogue voltage (V)',av),
            ('GPIB event name',gpibevent),
            ('GPIB on/off?',gpibon)])

def channel_names(length, values=None):
    """Define a dictionary for DExTer's channel names cluster
    since it's used several times. Can be initialised with 
    items but take care to give them the right length:
    values = [[hardware IDs],[names]]"""
    if values and len(values[0])==length and len(values[1])==length:
        return OrderedDict([('Hardware ID', values[0]),
                    ('Name', values[1])])
    else:
        return OrderedDict([('Hardware ID', ['']*length),
                    ('Name', ['']*length)])

def analogue_cluster(length, values=None):
    """Define a dictionary for DExTer's analogue channels 
    cluster since it's used several times. Can be 
    initialised with items but take care to give them the 
    right length:
    values = [[voltages],[ramp?]]"""
    if values and len(values[0])==length and len(values[1])==length:
        return OrderedDict([('Voltage', values[0]),
                    ('Ramp?', values[1])])
    else:
        return OrderedDict([('Voltage', [0]*length),
                    ('Ramp?', [False]*length)])

#### Expanding python dictionaries to LabVIEW format ####

def nm_val(dic, key, conv=[]):
    """Return an ordered dictionary with the LV
    (name, val) format.
    dic: the dictionary to take the value from
    key: the key of the dictionary at which value is found
    conv: list of functions to use to convert the value"""
    val = dic[key]
    for f in conv: # apply the functions recursively
        val = f(val)
    return OrderedDict([('Name',key), ('Val',val)])

def mk_dic(typ='Array', name='', size=1, dtyp='Cluster', data=[]):
    """Shorthand for making an ordered dictionary that 
    represents a cluster or array in the LabVIEW format.
    typ: 'Array' if representing an Array, otherwise assume Cluster
    name: the name field of the Cluster/Array
    size: Dimsize or NumElts of the Cluster/Array
    dtyp: the type of the data (e.g. Boolean, Cluster, String)
    data: the data held in the Cluster/Array"""
    return OrderedDict([('Name', name), 
        ('Dimsize' if typ=='Array' else 'NumElts', size),
        (dtyp, data)])

def wrap_hf(seq_dict, nsteps, nd, na, up=1):
    """Shorthand to expand the dictionaries required for the header 
    and channels of either the top or bottom half of the sequence.
    seq_dict: the python dictionary which the sequence is stored in
    nsteps: the number of time steps in the sequence
    nd: number of digital channels
    na: number of analogue channels
    up: 1 - the top half (fast channels), 0 - bottom half (slow)."""
    title = 'Sequence header top' if up else 'Sequence header middle'
    speed = 'Fast' if up else 'Slow'
    return (mk_dic('Array', title, nsteps, 'Cluster',
            data=[OrderedDict([
                ('Name','Sequence header cluster'),
                ('NumElts',10),
                ('String',[nm_val(head, key) for key in ['Event name', 'Time step name']]),
                ('DBL', nm_val(head, 'Time step length', [str])),
                ('Cluster', [OrderedDict([('Name', 'Trigger details'),
                        ('NumElts',4),
                        ('DBL', nm_val(head, 'Analogue voltage (V)', [str])),
                        ('EW', OrderedDict([('Name', 'Digital or analogue trigger?'),
                            ('Choice', ['Digital trigger', 'Analogue trigger']),
                            ('Val', str(int(head['Digital or analogue trigger?']))),
                        ])),
                        ('U8', nm_val(head, 'Channel')),
                        ('Boolean', nm_val(head, 'Trigger this time step?', [int, str]))
                    ]),
                    OrderedDict([('Name', 'GPIB routine data'),
                        ('NumElts',2),
                        ('EW', OrderedDict([('Name', 'GPIB event name'),
                            ('Choice', ['Do nothing', 'Initial setup', 'RF ramp 1', 
                                'RF ramp 2', 'RF ramp 3', 'Spin flip', 'RF off', 'Remote']),
                            ('Val', head['GPIB event name'])])),
                        ('Boolean', nm_val(head, 'GPIB on/off?'))
                    ])
                ]),
                ('Boolean', [nm_val(head, key, [int, str]) for key in
                    ['Hide event steps', 'Populate multirun', 'Skip Step']]),
                ('EW', OrderedDict([('Name', 'Time unit'),
                    ('Choice', ['µs', 'ms', 's']),
                    ('Val', head['Time unit'])
                ])),
                ('I32', nm_val(head, 'Event ID'))
            ]) for head in seq_dict['Experimental sequence cluster in'][title]]),
        mk_dic('Array', speed + ' digital channels', [nd, nsteps], 'Boolean',
            data=[OrderedDict([('Name', 'Boolean'),
                ('Val', seq_dict['Experimental sequence cluster in'][speed + ' digital channels'][i][j])
                ]) for j in range(nd) for i in range(nsteps)]),
        mk_dic('Array', speed + ' digital names', nd, 'Cluster',
            [mk_dic('Cluster', 'Channel names', 2, 'String',
                [OrderedDict([('Name', key), ('Val', vals[i])]) for key, vals in seq_dict['Experimental sequence cluster in'][speed + ' digital names'].items()])
            for i in range(len(seq_dict['Experimental sequence cluster in'][speed + ' digital names']['Name']))]),
        mk_dic('Array', speed + ' analogue names', na, 'Cluster',
            [mk_dic('Cluster', 'Channel names', 2, 'String',
                [OrderedDict([('Name', key), ('Val', vals[i])]) for key, vals in seq_dict['Experimental sequence cluster in'][speed + ' analogue names'].items()])
            for i in range(len(seq_dict['Experimental sequence cluster in'][speed + ' analogue names']['Name']))]),
        mk_dic('Array', speed + ' analogue array', [na, nsteps], 'Cluster',
            [OrderedDict([
                ('Name', 'Analogue cluster'),
                ('NumElts', 2),
                ('Boolean', OrderedDict([('Name','Ramp?'), 
                    ('Val',str(int(seq_dict['Experimental sequence cluster in'][speed + ' analogue array'][i]['Ramp?'][j])))])),
                ('DBL',  OrderedDict([('Name','Voltage'), 
                    ('Val',seq_dict['Experimental sequence cluster in'][speed + ' analogue array'][i]['Voltage'][j])]))
            ]) for i in range(na) for j in range(nsteps)]))

def wrap_sequence(seq_dict):
    """Add all the extra jargon that LabVIEW puts in XML files
    to a dictionary containing the sequence."""
    numsteps = len(seq_dict['Experimental sequence cluster in']['Sequence header top'])
    numevents = len(seq_dict['Event list array in'])
    return OrderedDict([('Cluster', OrderedDict([
            ('Name', 'input cluster'),
            ('NumElts', 4),
            ('Array', mk_dic(typ='Array', name='Event list array in', 
                size=numevents, dtyp='Cluster',
                data=[OrderedDict([
                    ('Name','Event list cluster in'),
                    ('NumElts', 4),
                    ('String', nm_val(event, 'Event name')),
                    ('Array', OrderedDict([
                        ('Name', 'Event indices'),
                        ('Dimsize', len(event['Event indices'])),
                        ('I32', [OrderedDict([
                            ('Name','Numeric Control'),
                            ('Val',x)]) for x in event['Event indices']])
                        ])),
                    ('Path', nm_val(event, 'Event path')),
                    ('Boolean', nm_val(event, 'Routine specific event?', [int, str]))
                    ]) for event in seq_dict['Event list array in']])),
            ('Cluster', mk_dic(typ='Cluster', name='Experimental sequence cluster in', 
                size=10, dtyp='Array',
                data=[*wrap_hf(seq_dict, numsteps, 56, 8, 1),
                    *wrap_hf(seq_dict, numsteps, 48, 32, 0)])),
            ('String', [nm_val(seq_dict, key)
                for key in ['Routine name in', 'Routine description in']])
            ]))
        ])

#### editing XML strings to LabVIEW format ####

def shift(fullstr, i, start, end, match1, match2, single=False):
    """Move the subsection of 'fullstr' between 'start'
    and 'end' (starting the search after index 'i') forward to the 
    position where 'match2' is first found after 'match1'.
    single: True  - only move the first occurrence of the substring
            False - iterate through the whole string.
    Return: (rearranged string, index at end of substring in new position)
    If any of the matching strings are unfound, return:
    (unchanged string, -1)."""
    while i>=0:
        i0 = fullstr.find(start, i) # start of substring
        i1 = fullstr.find(end, i0) # end of substring
        isub = i1 + len(end)
        i2 = fullstr.find(match1, isub) # needed to find new position
        i2 = fullstr.find(match2, i2) # new position
        iend = i2 + len(match2)
        if any(j<0 for j in [i0, i1, i2]) or single:
            break # find() returns -1 if it fails
        else:
            fullstr = fullstr[:i0] + fullstr[isub:iend] + fullstr[i0:isub] + fullstr[iend:]
            i = iend + isub - i0 + 1
    return fullstr

def reformat(xmlstr):
    """LabVIEW is fussy about the order that XML tags appear in.
    So having created the sequence as an XML string, we must now reorder
    parts of it."""
    # move 'Time step name' to below 'GPIB on/off?'
    xmlstr = shift(xmlstr, 0, '<String><Name>Time step name</Name>', 
                '</String>', '<Name>GPIB on/off?</Name>', '</Cluster>')
    # move 'Skip Step' to below 'Event ID'
    xmlstr = shift(xmlstr, 0, '<Boolean><Name>Skip Step</Name>', 
                '</Boolean>', '<I32><Name>Event ID</Name>', '</I32>')
    # move all of 'Sequence header middle' to below 'Slow digital names'
    xmlstr = shift(xmlstr, 0, '<Array><Name>Sequence header middle</Name>', 
        '</Boolean></Cluster></Array>', '<Array><Name>Slow digital names</Name>', '</String></Cluster></Array>')
    return xmlstr

#### Removing unnecessary data from dictionary translated from XML ####

def get_ev_inds(event_array):
    """Return a list of the event indices for a given event
    seq_dict['LVData']['Cluster']['Array']['Cluster'][i]['Array']['I32']
    this function is needed since if there are more than one indices then
    it returns a list, but if there's only one then it's a dict."""
    if type(event_array) == list:
        return [x['Val'] for x in event_array]
    elif type(event_array) == OrderedDict:
        return [event_array['Val']]
    else: return []

def find_item(list_dicts, item_name):
    """Find the index in the list of dictionaries which has a
    'Name' item with value item_name"""
    for d in list_dicts:
        if d['Name'] == item_name:
            return d

def strip_hf(seq_arrays, up=1):
    """Shorthand to strip and reformat the dictionaries required for the header 
    and channels of either the top or bottom half of the sequence.
    seq_arrays: the list of arrays giving headers, channels, and names;
        seq_dict['LVData']['Cluster']['Cluster']['Array']
    up: 1 - the top half (fast channels), 0 - bottom half (slow)."""
    title = 'Sequence header top' if up else 'Sequence header middle'
    speed = 'Fast' if up else 'Slow'
    nsteps= len(find_item(seq_arrays, title)['Cluster']) # number of timesteps
    nd = len(find_item(seq_arrays, speed+' digital names')['Cluster']) # number of digital channels
    na = len(find_item(seq_arrays, speed+' analogue names')['Cluster']) # number of analogue channels
    return ((title,[
        header_cluster(skip=find_item(head['Boolean'], 'Skip Step')['Val'], 
            ename=find_item(head['String'], 'Event name')['Val'], 
            hide=find_item(head['Boolean'], 'Hide event steps')['Val'], 
            ID=head['I32']['Val'], 
            tsname=find_item(head['String'], 'Time step name')['Val'], 
            populate=find_item(head['Boolean'], 'Populate multirun')['Val'], 
            tslen=head['DBL']['Val'], 
            tunit=head['EW']['Val'], 
            dora=head['Cluster'][0]['EW']['Val'],
            trigger=head['Cluster'][0]['Boolean']['Val'], 
            channel=head['Cluster'][0]['U8']['Val'], 
            av=head['Cluster'][0]['DBL']['Val'], 
            gpibevent=head['Cluster'][1]['EW']['Val'], 
            gpibon=head['Cluster'][1]['Boolean']['Val']
        ) for head in find_item(seq_arrays, title)['Cluster']]),
        (speed + ' digital channels', list(map(list, zip(*# reshape flattened list of digital channels
            np.reshape([x['Val'] for x in find_item(seq_arrays, speed + ' digital channels')['Boolean']], (nd, nsteps)))))),
        (speed + ' digital names', channel_names(nd, 
            list(map(list, zip(*[ # transpose list
                [find_item(cl['String'], 'Hardware ID')['Val'], 
                find_item(cl['String'], 'Name')['Val']] 
                for cl in find_item(seq_arrays, speed+' digital names')['Cluster']]))))),
        (speed + ' analogue names', channel_names(na, 
            list(map(list, zip(*[ # transpose list
                [find_item(cl['String'], 'Hardware ID')['Val'], 
                find_item(cl['String'], 'Name')['Val']] 
                for cl in find_item(seq_arrays, speed+' analogue names')['Cluster']]))))),
        (speed + ' analogue array', [analogue_cluster(nsteps, list(map(list, zip(*[ # transpose list
                [cl['DBL']['Val'], cl['Boolean']['Val']] # note this is the opposite order because of transpose
                for cl in find_item(seq_arrays, speed + ' analogue array')['Cluster'][nsteps*i:nsteps*(i+1)]])))) for i in range(na)]))

def strip_sequence(seq_dict):
    """Remove all the extra jargon that LabVIEW puts in XML files
    from a dictionary containing the experimental sequence."""
    routine_ind = 0 if seq_dict['LVData']['Cluster']['String'][0]['Name'] == 'Routine name in' else 1
    return OrderedDict([
            ('Event list array in',[event_list(name=ev['String']['Val'],
                    routinespec=ev['Boolean']['Val'], 
                    indices=get_ev_inds(ev['Array']['I32']),
                    path=ev['Path']['Val']) 
                for ev in seq_dict['LVData']['Cluster']['Array']['Cluster']]),
            ('Routine name in', seq_dict['LVData']['Cluster']['String'][routine_ind]['Val']),
            ('Routine description in', seq_dict['LVData']['Cluster']['String'][int(not routine_ind)]['Val']),
            ('Experimental sequence cluster in', OrderedDict([
                *strip_hf(seq_dict['LVData']['Cluster']['Cluster']['Array'], up=1),
                *strip_hf(seq_dict['LVData']['Cluster']['Cluster']['Array'], up=0)]))])

#### #### Convert xml <-> python dict #### ####

class translate:
    """Write DExTer sequences to XML files.
    Facilitate editing of several variables quickly.
    A sequence has a fixed number of events, num_e,
    which give a total number of time steps, num_s.
    If fname is a file containing a sequence in XML
    format, then it will be loaded.
    Functions are provided to create a multirun.

    The format is:
     - event list array
     - experimental sequence cluster:
        headers, channels, and channel names
     - routine name
     - routine description
    """
    def __init__(self, fname='', num_e=1, num_s=1):
        self.nfd = 56 # number of fast digital channels
        self.nfa = 8  # number of fast analogue
        self.nsd = 48 # number of slow digital
        self.nsa = 32 # number of slow analogue
        self.seq_dic = OrderedDict([
            ('Event list array in',[event_list()]*num_e),
            ('Routine name in', ''),
            ('Routine description in', ''),
            ('Experimental sequence cluster in', OrderedDict([
                ('Sequence header top',[header_cluster()]*num_s),
                ('Fast digital names',channel_names(self.nfd)),
                ('Fast digital channels',[[False]*self.nfd]*num_s),
                ('Fast analogue names',channel_names(self.nfa)),
                ('Fast analogue array',[analogue_cluster(num_s)]*self.nfa),
                ('Sequence header middle',[header_cluster()]*num_s),
                ('Slow digital names',channel_names(self.nsd)),
                ('Slow digital channels',[[False]*self.nsd]*num_s),
                ('Slow analogue names',channel_names(self.nsa)),
                ('Slow analogue array',[analogue_cluster(num_s)]*self.nsa)])
            )])
        self.seq_txt = ''
        self.write_to_str() # also store sequence as string for quick reference
        if fname:
            self.load_xml(fname)

    def write_to_file(self, fname='sequence_example.xml'):
        """Write the current sequence in the dictionary
        format to an XML file with name fname."""
        with open(fname, 'w+') as f:
            xmlstr = reformat(xmltodict.unparse(wrap_sequence(self.seq_dic)))
            dom = xml.dom.minidom.parseString(xmlstr)
            f.write(dom.toprettyxml().replace('<Val/>', '<Val></Val>').replace('<?xml version="1.0" ?>\n',
'<?xml version="1.0" standalone="yes" ?>\n<LVData xmlns="http://www.ni.com/LVData">\n<Version>12.0.1f5</Version>') 
                + "</LVData>")
        
    def write_to_str(self):
        """Store the current sequence in the dictionary
        in XML string format specified by LabVIEW and
        return this string."""
        self.seq_txt = reformat(xmltodict.unparse(wrap_sequence(self.seq_dic))).replace(
                            '<?xml version="1.0" encoding="utf-8"?>\n', '')
        return self.seq_txt

    def load_xml(self, fname='sequence_example.xml'):
        """Load a sequence as a dictionary from an xml file."""
        try:
            with open(fname, 'r') as f:
                whole_dict = xmltodict.parse(f.read())
                self.seq_dic = strip_sequence(whole_dict)
                self.write_to_str()
        except (FileNotFoundError, xml.parsers.expat.ExpatError) as e: 
            logger.error('Translator could not load sequence:\n'+str(e))

    def add_event(self, idx=None, event_name=event_list(), 
            header_top=header_cluster(), fd=[False]*56,
            fa=analogue_cluster(8), header_mid=header_cluster(),
            sd=[False]*48, sa=analogue_cluster(32)):
        """Append a new event with the given values at the given
        index.
        idx        -- the index to insert at. Defualt appends at end.
        event_name -- Event list with name, bool, indices, path
        header_top -- header cluster for fast channels
        fd         -- fast digitial channels
        fa         -- fast analogue channels
        header_mid -- header cluster for slow channels
        sd         -- slow digital channels
        sa         -- slow analogue channels."""
        if idx == None:
            idx = len(self.seq_dic['Event list array in'])
        self.seq_dic['Event list array in'].insert(idx, event_name)
        esc = self.seq_dic['Experimental sequence cluster in'] # shorthand
        esc['Sequence header top'].insert(idx, header_top)
        esc['Fast digital channels'].insert(idx, fd)
        esc['Fast analogue array'].insert(idx, fa)
        esc['Sequence header middle'].insert(idx, header_mid)
        esc['Slow digital channels'].insert(idx, sd)
        esc['Slow analogue array'].insert(idx, sa)
        
    def copy(self):
        """Create a copy of this translate object"""
        t = translate()
        t.nfd = self.nfd # number of fast digital channels
        t.nfa = self.nfa # number of fast analogue
        t.nsd = self.nsd # number of slow digital
        t.nsa = self.nsa # number of slow analogue
        t.seq_dic = copy.deepcopy(self.seq_dic) # need deep copy of dict because values are mutable
        t.write_to_str()
        return t
        
    def mloopmodify(self, mloopdict,mlooppath):
        """
        Modify the cluster based on parameters read from mloop txt file, interpreted by mloopdict nested dictionary struct

        Supports two types of paramter, specified by the 'type' string

        'timestep'  : Use the number as the length of a timestep
        'slowanalouge': Use the number as a Voltage. This has aditional arguments
            "timestep" : list of timestep numbers over which to modify the volatage
            "channel name" : Name of the slow analouge to modify


        """
        esc = self.seq_dic['Experimental sequence cluster in'] # shorthand
        #Read exp_input.txt
        mloopinputpath = mlooppath+'\exp_input.txt'
        if os.path.exists(mloopinputpath):
            with open(mloopinputpath, 'r') as f:
                newstr = ''.join((ch if ch in '0123456789.-e' else ' ') for ch in f.read().replace(" ",""))
                params = [float(i) for i in newstr.split()]
                print(params)
            os.remove(mloopinputpath)
        #insert data
        i = 0
        for key in mloopdict.keys():
            
            print(key)
            #Current Mloop Parameter
            parameter = mloopdict[key] 
            parameter['value'] = params[i]
            i += 1
            #Timestep
            if parameter['type'] == 'timestep':

                print('timestep '+str(parameter['timestep'])+' length '+str(parameter['value']))
                #Update esc with new timestep time
                for position in ['top', 'middle']:
                    esc['Sequence header '+position][parameter['timestep']]['Time step length'] = parameter['value']
            #Slow Analogue
            if parameter['type'] == 'slowanalogue':
                print('channel '+parameter['channelname']+' value '+str(parameter['value']))
                channel = esc['Slow analogue names']['Name'].index(parameter['channelname'])
                for timestep in parameter['timestep']:
                    esc['Slow analogue array'][channel]['Voltage'][timestep] = parameter['value']
                    print(timestep)

    # extra functions for checking the sequence is correct format?

    # @staticmethod
    # def get_mr_xml_str(mr_array, anlogue_options, change_type, 
    #                     analogue_channel, time_step):
    #     """Convert the multirun array of values, along with the
    #     selected channels, into an XML string to send to DExTer"""
