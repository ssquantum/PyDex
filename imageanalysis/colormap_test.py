import matplotlib.pyplot as plt
from matplotlib.cm import get_cmap
from matplotlib.colors import rgb2hex

def get_group_roi_color(group_index,roi_index,max_roi_index=5):
    cmaps = ['Reds','Blues','Greens','Oranges','Purples','BuGn','RdPu']
    cmap = get_cmap(cmaps[group_index%len(cmaps)])
    color_code = (roi_index/max_roi_index)%1*(-0.8)+0.8
    return rgb2hex(cmap(color_code),keep_alpha=False)
    # return cmap(color_code).to_hex()
    
    
color = get_group_roi_color(1,2)
plt.scatter([1],[1],color=color)

for group in range(10):
    for roi in range(10):
        plt.scatter([roi],[group],color=get_group_roi_color(group,roi))