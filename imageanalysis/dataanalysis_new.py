"""Analyser
Dan Ruttley 2023-01-31
Code written to follow PEP8 conventions with max line length 120 characters.

Class used to analyse data from MAIA. Used in STEFANs in PyDex and outside of
PyDex to analyse MAIA DataFrames.

Data can either be provided in the form of MAIA data (i.e. a list of lists as 
outputted by MAIAs mid-run) or a string linking to a pre-processed DataFrame 
csv that will be read in.
"""

import numpy as np
import pandas as pd
from itertools import chain
from copy import deepcopy
from astropy.stats import binom_conf_interval
from math import floor, log10
import functools
import os
import re
import itertools

import sys
if '.' not in sys.path: sys.path.append('.')
from helpers import calculate_threshold

class MeasureAnalyser():
    """Class to analyse the results of an entire measurement. Makes different
    instances of the Analyser class and then goes through a measure folder to
    extract relevant information."""
    def __init__(self, directory=None,ignore_ids=[],group_by_uv=None):
        self.grouping_uv = group_by_uv
        if directory is not None:
            self.load_from_directory(directory,ignore_ids)
        if self.grouping_uv is not None:
            self.group_by_uv()
            
    def group_by_uv(self):
        grouped_analysers = {}
        for analyser in self.analysers.values():
            uv_val = analyser.get_user_variables()[self.grouping_uv]
            if uv_val not in grouped_analysers:
                grouped_analysers[uv_val] = []
            grouped_analysers[uv_val].append(analyser)
            
        combined_analysers = {}
        
        for uv_val,analysers in grouped_analysers.items():
            aux_dfs = [a.aux_df for a in analysers]
            counts_dfs = [a.counts_df for a in analysers]
                          
            aux_df = aux_dfs[0]
            counts_df = pd.concat(counts_dfs)
            
            combined_analysers[uv_val] = Analyser((aux_df,counts_df))
        
        self.analysers = combined_analysers
    
    def load_from_directory(self,directory,ignore_ids=[]):
        maia_files = [x for x in os.listdir(directory) if x.split('.')[0] == 'MAIA']
        print(maia_files)
        
        self.analysers = {}
        for file in maia_files:
            hist_id = int(file.split('.')[1])
            if not hist_id in ignore_ids:
                self.analysers[hist_id] = Analyser(directory+'\\'+file)
            
    def apply_post_selection_criteria(self,post_selection_string):
        [x.apply_post_selection_criteria(post_selection_string) for x in self.analysers.values()]
        
    def apply_condition_criteria(self,criteria_string):
        [x.apply_condition_criteria(criteria_string) for x in self.analysers.values()]
    
    def get_data(self,groups_for_average=None):
        rows = []
        for hist_id,analyser in self.analysers.items():
            # print(hist_id,analyser)
            # row = pd.DataFrame()
            row = {}
            row['Hist ID'] = hist_id
            
            uvs = analyser.get_user_variables()
            for uv_idx, uv_val in enumerate(uvs):
                row['User variable {}'.format(uv_idx)] = uv_val
            
            post_select_probs_errs = analyser.get_post_selection_probs()
            condition_met_probs_errs = analyser.get_condition_met_probs()
            for group,(ps_prob_err,cm_prob_err) in enumerate(zip(post_select_probs_errs,condition_met_probs_errs)):
                # print(group,ps_prob_err,cm_prob_err)
                for key, val in ps_prob_err.items():
                    row['Group {} PS {}'.format(group,key)] = val
                for key, val in cm_prob_err.items():
                    row['Group {} CM {}'.format(group,key)] = val
            avg_condition_met_probs_errs = analyser.get_avg_condition_met_prob(groups_for_average)
            for key, val in avg_condition_met_probs_errs.items():
                row['Average CM {}'.format(key)] = val
            rows.append(row)
        df = pd.DataFrame(rows)
        df = df.set_index('Hist ID')
        return df
        
    def get_separations(self,**kwargs):
        """Requests that the analysers analyse their counts lists to 
        determine the upper/lower means and the separations that these give.
        """
        data = []
        keys_to_keep = ['threshold', 'mean', 'upper mean', 'lower mean', 'separation']
        
        for hist_id,analyser in self.analysers.items():
            # print(hist_id,analyser)
            analyser_data = {}
            
            row = pd.DataFrame()
            analyser_data['Hist ID'] = hist_id
            
            uvs = analyser.get_user_variables()
            for uv_idx, uv_val in enumerate(uvs):
                analyser_data['User variable {}'.format(uv_idx)] = uv_val
            
            
            separation_data = analyser.get_separations(**kwargs)
            
            for key,value in separation_data.items():
                for keyi in keys_to_keep:
                    analyser_data[key+' '+keyi] = value[keyi]
            data.append(analyser_data)
            
        df = pd.DataFrame(data)
        df = df.set_index('Hist ID')
        return df       

class Analyser():
    def __init__(self, maia_data):
        if type(maia_data) == list: # data comes directly from MAIA
            self.convert_maia_data_to_df(maia_data)
        elif type(maia_data) == tuple: # tuple with aux_df and counts_df to populate with
            self.load_dfs_manually(*maia_data)
        else: # maia_data is a string with a dataframe format
            self.load_dfs_from_file(maia_data)
        self.split_counts_df_by_roi_group()
    
    def convert_maia_data_to_df(self,maia_data):
        """Converts MAIA data to a DataFrame for further analysis. During this 
        process the occupancy for each ROI is calculated with the threshold data.
    
        Parameters
        ----------
        maia_data : _type_
            _description_
        """
        # convert counts data into a dataframe
        counts = maia_data[0]
        num_images = len(counts[0][0])
        num_rois_per_group = len(counts[0])
        num_roi_groups = len(counts)
    
        counts = list(chain.from_iterable(counts))
        counts = sum(counts, [])
        counts_dict = {}
        roi_names = []
        for group in range(num_roi_groups):
            for roi in range(num_rois_per_group):
                for image in range(num_images):
                    roi_names.append('ROI{}:{} Im{}'.format(group,roi,image))
    
        counts_df_columns = [x+' counts' for x in roi_names]
        for roi_dict, name in zip(counts,counts_df_columns):
            counts_dict[name] = roi_dict
        counts_df = pd.DataFrame.from_records(counts_dict)
        counts_df.index.names = ['File ID']
    
        # convert threshold data into a separate dataframe
        thresholds = maia_data[1]
        thresholds = [x[0] for x in list(chain.from_iterable(chain.from_iterable(thresholds)))]
        threshold_df_columns = [x+' threshold' for x in roi_names]
        threshold_df = pd.DataFrame([thresholds],columns=threshold_df_columns)
        
        roi_coords = maia_data[2]
        roi_coords = [x for x in list(chain.from_iterable(chain.from_iterable(roi_coords)))]
        roi_df_cols_base = []
        for group in range(num_roi_groups):
            for roi in range(num_rois_per_group):
                    roi_df_cols_base.append('ROI{}:{}'.format(group,roi))
        roi_df_cols = list(chain.from_iterable([[x+label for label in [' x',' y',' w',' h']] for x in roi_df_cols_base]))
        roi_coords_df = pd.DataFrame([roi_coords],columns=roi_df_cols)
        
    
        # use threshold data to calculate occupancy
        counts_df_occupancy_columns = [x+' occupancy' for x in roi_names]
        for occupancy_col, counts_col, thresh_col in zip(counts_df_occupancy_columns,counts_df_columns,threshold_df_columns):
            # print(occupancy_col, counts_col, thresh_col)
            counts_df[occupancy_col] = np.where(counts_df[counts_col] > threshold_df[thresh_col][0],True,False)
        
        self.num_images = num_images
        self.num_rois_per_group = num_rois_per_group
        self.num_roi_groups = num_roi_groups
        self.counts_df = counts_df
        self.aux_df = pd.concat([threshold_df,roi_coords_df],axis=1)
        
    def load_dfs_from_file(self,filename):
        print(filename)
        self.aux_df = pd.read_csv(filename,nrows=1)
        self.counts_df = pd.read_csv(filename,skiprows=2,index_col='File ID')
        self.populate_values_from_dfs()
    
    def load_dfs_manually(self,aux_df,counts_df):
        self.aux_df = aux_df
        self.counts_df = counts_df
        self.populate_values_from_dfs()
    
    def populate_values_from_dfs(self):
        roi_names = [x[:-7] for x in self.counts_df.columns if ' counts' in x]
        
        roi_groups = set([int(x.split(':')[0].split('ROI')[1]) for x in roi_names])
        self.num_roi_groups = len(roi_groups)
        
        rois = set([int(x.split(':')[1].split()[0]) for x in roi_names])
        self.num_rois_per_group = len(rois)
        
        images = set([int(x.split('Im')[1]) for x in roi_names])
        self.num_images = len(images)
    
    def save_data(self,filename,additional_data={}):
        """Takes the data in the analyser and saves it as the .csv files 
        exported from PyDex. This is the function that the MAIA uses to save 
        the data.
        
        Parameters
        ----------
        filename : str
            The filename to save the .csv to.
        additional_data : dict
            Any additional data to be saved to the .csv (e.g. user variables).
            This data will be added to the aux_df dataframe to appear in
            the top row of the output file.
        """
        print('=== save data to filename ===')
        print(filename)
        
        additional_data['Start File ID'] = self.counts_df.index.min()
        additional_data['End File ID'] = self.counts_df.index.max()
        
        for key in additional_data: additional_data[key] = [additional_data[key]] # each entry needs to be in a list to be convert to df
        additional_df = pd.DataFrame.from_dict(additional_data)
        aux_output_df = pd.concat([additional_df,self.aux_df],axis=1)
        
        # might have PermissionError: in PyDex this handling has been moved to MAIA so that it doesn't delete the data if it can't save
        os.makedirs(os.path.dirname(filename),exist_ok=True)
        
        with open(filename, 'w') as f:
            aux_output_df.to_csv(f,index=False,line_terminator='\n')
        with open(filename, 'a') as f:
            self.counts_df.to_csv(f,index=True,line_terminator='\n')
            
    def split_counts_df_by_roi_group(self):
        self.counts_df_split_by_roi_group = []
        for roi_group in range(self.num_roi_groups):
            col_names = [x for x in self.counts_df if 'ROI{}'.format(roi_group) in x]
            group_df = self.counts_df[col_names]
            self.counts_df_split_by_roi_group.append(group_df)
    
    def apply_post_selection_criteria(self,post_selection_string):
        """
        Applies the post-selection criteria for this analyser. Post-selection
        criteria specified in a string in the form '[1xx1],[0x1x]' etc where
        each entry in the brakets specifies a given image and the entries 
        within the brakets specify the ROIs in a given group.
        """
        post_selection_permutations = self.get_criteria_permutations(post_selection_string)

        ps_counts_df_split_by_roi_groups = []

        for permutation in post_selection_permutations:
            post_selection_criteria = self.convert_criteria_string_to_list(permutation)
            post_selection_column_keys = self.convert_criteria_list_to_column_keys(post_selection_criteria)
            
            ps_counts_df_split_by_roi_groups.append([self.get_post_selected_dataframe(x,post_selection_column_keys,group_num) for group_num, x in enumerate(self.counts_df_split_by_roi_group)])
            
            # print(post_select_probs_errs)
        ps_counts_df_split_by_roi_groups = list(map(list, zip(*ps_counts_df_split_by_roi_groups))) # now each entry is list of permutations for each ROI

        self.ps_counts_df_split_by_roi_group = [pd.concat(x).drop_duplicates().reset_index(drop=True) for x in ps_counts_df_split_by_roi_groups]
        post_select_probs_errs = self.get_post_selection_probs()
        return post_select_probs_errs
    
    def get_post_selection_probs(self):
        """Calculate the probability that post-selection criteria were met for
        each ROI group."""
        return [self.binomial_confidence_interval(len(x),len(y)) for x,y in zip(self.ps_counts_df_split_by_roi_group,self.counts_df_split_by_roi_group)]
        
    def apply_condition_criteria(self,condition_criteria_string):
        condition_permutations = self.get_criteria_permutations(condition_criteria_string)

        conditions_met_all_permutations = []

        for permutation in condition_permutations:
            condition_criteria = self.convert_criteria_string_to_list(permutation)
            condition_column_keys = self.convert_criteria_list_to_column_keys(condition_criteria)
            
            try:
                [self.calculate_condition_met(x,condition_column_keys,group_num) for group_num, x in enumerate(self.ps_counts_df_split_by_roi_group)]
                conditions_met_all_permutations.append([list(x['condition met']) for x in self.ps_counts_df_split_by_roi_group])
            except AttributeError: # post-selection criteria has not been applied
                self.apply_post_selection_criteria('') # apply no post-selection criteria
                [self.calculate_condition_met(x,condition_column_keys,group_num) for group_num, x in enumerate(self.ps_counts_df_split_by_roi_group)]
                conditions_met_all_permutations.append([list(x['condition met']) for x in self.ps_counts_df_split_by_roi_group])
        
        conditions_met_all_permutations = list(map(list, zip(*conditions_met_all_permutations))) # transpose so each entry is list of condition met for each ROI group
        # print(len(conditions_met_all_permutations[0]))
        for df, conditions_met in zip(self.ps_counts_df_split_by_roi_group,conditions_met_all_permutations):
            df['condition met'] = np.sum(conditions_met,axis=0).astype(bool)       
        return self.get_condition_met_probs()
    
    def get_condition_met_probs(self):
        """Calculate the probability that condition met criteria were met for
        each ROI group."""
        return [self.binomial_confidence_interval(x['condition met'].sum(), len(x)) for x in self.ps_counts_df_split_by_roi_group]
        
    def get_avg_condition_met_prob(self,groups_to_use=None):
        """Calculate the average condition met prob across all ROI groups."""
        conditions_met = 0
        total = 0
        for group, x in enumerate(self.ps_counts_df_split_by_roi_group):
            if (groups_to_use is not None) and (group not in groups_to_use):
                continue
            conditions_met += x['condition met'].sum()
            total += len(x)
        return self.binomial_confidence_interval(conditions_met, total)
    
    def get_criteria_permutations(self,criterias_string):
        splits = criterias_string.split(',')
        
        criteria = []
        
        for split in splits:
            if '{' in split:
                # print(split)
                res = re.findall(r'\{.*?\}', split)
                if len(res) != 1:
                    raise Exception('Maximum 1 {} per image')
                subsplits = res[0][1:-1].split('][')
                subsplits = [x.replace('[','').replace(']','') for x in subsplits]
                criteria.append(subsplits)
            else:
                split = split.replace('[','')
                split = split.replace(']','')
                criteria.append([split])
            
        criteria_permutations =  [s for s in itertools.product(*criteria)]
        criteria_strings = []
        for criteria in criteria_permutations:
            criteria_string = ''
            for image_criteria in criteria:
                criteria_string += ('['+image_criteria+'],')
            criteria_strings.append(criteria_string[:-1])
        
        return criteria_strings

    def convert_criteria_string_to_list(self,criterias_string):
        """Converts a string such as that got from a STEFAN to a list of 
        strings used in the rest of the analyser.
        """
        split_string = criterias_string.split(',')
        criteria = []
        for criteria_string in split_string:
            criteria_string = criteria_string.replace('[','')
            criteria_string = criteria_string.replace(']','')
            criteria.append(criteria_string)
        return criteria
    
    def convert_criteria_list_to_column_keys(self,criteria):
        """Converts a list of criteria for separate images to a list containing
        the column names and True/False based on criteria. The ROI group name 
        is not added so that this can be added later based on the specific 
        group.
        """
        criteria_column_keys = []
        for image_num, image_criteria in enumerate(criteria):
            for roi_num, char in enumerate(image_criteria):
                column_name = ':{} Im{} occupancy'.format(roi_num,image_num)
                if char == '1':
                    criteria_column_keys.append([column_name,True])
                elif char == '0':
                    criteria_column_keys.append([column_name,False])
        return criteria_column_keys
    
    def construct_condition(self, df, column, operation, criteria): 
        return operation(df[column],criteria)
    
    def apply_criteria_to_df(self,df,column_keys,group_num):
        column_keys = deepcopy(column_keys)
        for criteria in column_keys:
            criteria[0] = 'ROI{}'.format(group_num) + criteria[0]
        try:
            conditions = [self.construct_condition(df,x[0],np.equal,x[1]) for x in column_keys]
        except KeyError as e: # an invalid ROI was specified to have a condition, so return an empty df
            print('Invalid key in criteria: {}'.format(e))
            return False
        # print('len conditions',len(conditions))
        if len(conditions) > 1:
            condition = functools.reduce(np.logical_and, conditions)
            # print(condition)
        else:
            try:
                condition = conditions[0]
            except IndexError: # there are no post-selection criteria
                # print('No criteria specified')
                return False
        return condition
    
    def get_post_selected_dataframe(self,counts_df,post_selection_column_keys,group_num):
        condition = self.apply_criteria_to_df(counts_df,post_selection_column_keys,group_num)
        if condition is False:
            # print('Post selection failed')
            return counts_df.copy()
        
        ps_counts_df = counts_df[condition].copy() # copy to prevent slicing issues
        return ps_counts_df    

    def calculate_condition_met(self,counts_df,condition_column_keys,group_num):
        condition = self.apply_criteria_to_df(counts_df,condition_column_keys,group_num)
        if condition is False:
            # print('Condition calculation failed')
            counts_df['condition met'] = True # no condition has been applied so just report True
            return counts_df
        
        counts_df['condition met'] = condition
    
    def binomial_confidence_interval(self,num_successes,num_events):
        """Calculates the binomial confidence interval for a number of 
        successes for a given number of events.
        
        Returns
        -------
        float : success probability
        float : error in success probability
        float : upper error in success probability
        float : lower error in success probability
        """
        if num_events == 0:
            LP,eLPi,uperr,loerr = 0.5,0.5,0.5,0.5
        else:
            LP = num_successes/num_events
            conf = binom_conf_interval(num_successes, num_events, interval='jeffreys')
            uperr = conf[1] - LP # 1 sigma confidence above mean
            loerr = LP - conf[0] # 1 sigma confidence below mean
            eLPi = (uperr+loerr)/2
        result = {}
        result['successes'] = num_successes
        result['events'] = num_events
        result['probability'] = LP
        result['error in probability'] = eLPi
        result['upper error in probability'] = uperr
        result['lower error in probability'] = loerr
        return result
    
    def get_condition_met_plotting_data(self):
        """Returns data in the format needed for STEFAN plotting. Groups of 
        [x,y] values are returned for each ROI group where the x value is the 
        File ID and the y value is either condition met or not for each 
        File ID."""
        return [[list(x.index),list(x['condition met'].astype(int))] for x in self.ps_counts_df_split_by_roi_group]

    def uncert_to_str(self,val,err):
        prec = floor(log10(err))
        err = round(err/10**prec)*10**prec
        val = round(val/10**prec)*10**prec
        if prec > 0:
            valerr = '{:.0f}({:.0f})'.format(val,err)
        else:
            valerr = '{:.{prec}f}({:.0f})'.format(val,err*10**-prec,prec=-prec)
        return valerr
    
    def get_user_variables(self):
        """Gets the user variables from the aux df. These will only be present
        if loading a .csv saved after a multirun run. The user variables are 
        sorted to ensure they are returned in order."""
        user_variable_idx = [int(x.split()[-1]) for x in self.aux_df.columns if 'User variable' in x]
        user_variable_idx.sort()
        
        user_variable_vals = []
        user_variable_vals = [float(self.aux_df['User variable {}'.format(x)][0]) for x in user_variable_idx]
        
        return user_variable_vals
    
    def get_separations(self,autothresh=True,**kwargs):
        """Analyses the counts data to find the separation between events where 
        atoms are and are not present in a particular image.
        
        Parameters
        ----------
        autothresh : bool [NOT CURRENTLY IMPLEMENTED]
            Whether or not the autothresh should be reapplied to the histogram
            before the separation is calculated. The default is True.
        """
        roi_names = [x[:-7] for x in self.counts_df.columns if ' counts' in x]
        # print(roi_names)
        counts = [self.counts_df[x+' counts'] for x in roi_names]
        threshs = [self.aux_df[x+' threshold'].iloc[0] for x in roi_names]
        
        separation_data = {}
        for name in roi_names:
            roi_data = {}
            roi_data['counts'] = np.array(self.counts_df[name+' counts'])
            if autothresh:
                roi_data['threshold'] = calculate_threshold(roi_data['counts'])
            else:
                roi_data['threshold'] = self.aux_df[name+' threshold'].iloc[0]
            roi_data['mean'] = np.mean(roi_data['counts'])
            roi_data['upper mean'] = np.mean(roi_data['counts'][roi_data['counts'] > roi_data['threshold']])
            roi_data['lower mean'] = np.mean(roi_data['counts'][roi_data['counts'] < roi_data['threshold']])
            roi_data['separation'] = roi_data['upper mean'] - roi_data['lower mean']
            separation_data[name] = roi_data
        return separation_data

if __name__ == '__main__':
    import time
    import pickle
    import matplotlib.pyplot as plt
    
    """
    maia_data = pickle.load(open("sample_maia_data.p", "rb" ))
    
    # iterations = 10
    # start = time.perf_counter()
    # for _ in range(iterations):
    #     analyser = Analyser(maia_data)
    # end = time.perf_counter()
    # print('time/iteration = {:.3f} s'.format((end-start)/iterations))
    
    analyser = Analyser(maia_data)
    start = time.perf_counter()
    test = analyser.apply_post_selection_criteria('[111],[1xx]')
    condition_probs_errs = analyser.apply_condition_criteria('[xx],[11]')
    plotting_data = analyser.get_condition_met_plotting_data()
    end = time.perf_counter()
    print('time = {:.3f} s'.format((end-start)))
    post_selected = analyser.ps_counts_df_split_by_roi_group
    
    counts = maia_data[0]
    num_images = len(counts[0][0])
    num_rois_per_group = len(counts[0])
    num_roi_groups = len(counts)

    counts = list(chain.from_iterable(counts))
    counts = sum(counts, [])
    counts_dict = {}
    roi_names = []
    for group in range(num_roi_groups):
        for roi in range(num_rois_per_group):
            for image in range(num_images):
                roi_names.append('ROI{}:{} Im{}'.format(group,roi,image))
    
    roi_coords = maia_data[2]
    roi_coords = [x for x in list(chain.from_iterable(chain.from_iterable(roi_coords)))]
    roi_df_cols_base = []
    for group in range(num_roi_groups):
        for roi in range(num_rois_per_group):
                roi_df_cols_base.append('ROI{}:{}'.format(group,roi))
    roi_df_cols = list(chain.from_iterable([[x+label for label in [' x',' y',' w',' h']] for x in roi_df_cols_base]))
    roi_coords_df = pd.DataFrame([roi_coords],columns=roi_df_cols)
    
    test = {1:1,2:2,3:3}
    for k in test: test[k] = [test[k]]
    """
    
    directory = r"Z:\Tweezer\Experimental Results\2023\January\31\Measure1"
    measure_analyser = MeasureAnalyser(directory,ignore_ids=list(range(10,1000)),group_by_uv=0)
    analysers = measure_analyser.analysers
    measure_analyser.apply_post_selection_criteria('')
    measure_analyser.apply_condition_criteria('[1x]')
    df = measure_analyser.get_data()
    plt.scatter(df['User variable 0'],df['Group 2 CM probability'])
    plt.show()
    
    # directory = r"Z:\Tweezer\Experimental Results\2023\January\31\Measure1"
    # measure_analyser = MeasureAnalyser(directory)
    # analysers = measure_analyser.analysers
    # # measure_analyser.apply_post_selection_criteria('')
    # measure_analyser.apply_condition_criteria('[1x]')
    # sep_df = measure_analyser.get_separations()
    # plt.scatter(sep_df['User variable 0'],sep_df['ROI0:1 Im0_separation'])
    # plt.xlabel('user variable 0')
    # plt.ylabel('separation')
    # plt.show()