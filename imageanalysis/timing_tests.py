import numpy as np
import time
from multiAtomImageAnalyser import ROI, ROIGroup

#%% Test slicing arrays to take ROIs

# Generate the initial image and 4 ROI groups with 4 ROIs each
image = np.random.rand(100,100)*1000

roi_groups = [ROIGroup() for _ in range(4)]
[group.set_num_rois(4) for group in roi_groups]

for group in roi_groups:
    for roi in group.rois:
        roi.x = np.random.randint(10,90)
        roi.y = np.random.randint(10,90)

roi_coords = [group.get_roi_coords() for group in roi_groups]
print('roi_coords =',roi_coords)


# Test behaviour 1 where we just loop over each roi
iterations = 1000
start_time = time.perf_counter_ns()
for _ in range(iterations):
    for group in roi_groups:
        for roi in group.rois:
            roi.counts[0].append(image[roi.x:roi.x+roi.w,roi.y:roi.y+roi.h].sum())
end_time = time.perf_counter_ns()
time_per_iteration = (end_time - start_time)/iterations
print('time_per_iteration = {:.1f} ms'.format(time_per_iteration/1e6))


