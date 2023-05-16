"""Analysis helper functions"""

from skimage.filters import threshold_minimum
import numpy as np

def calculate_threshold(counts_data):
    """Automatically choose a threshold based on the counts"""
    try:
        thresh = int(threshold_minimum(np.array(counts_data), 25))
    except (ValueError, RuntimeError, OverflowError):
        try:
            thresh = int(0.5*(max(counts_data) + min(counts_data)))
        except ValueError: # will be triggered if counts_data is empty
            thresh = 1000
    return thresh