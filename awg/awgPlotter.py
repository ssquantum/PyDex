"""Stefan Spence 07.07.21
A plotting function for the AWG

AWG functions and their arguments:
static 1:('segment','channel_out','action_val','duration_[ms]','freqs_input_[MHz]','num_of_traps',
                    'distance_[um]','tot_amp_[mV]','freq_amp','freq_phase_[deg]','freq_adjust','amp_adjust'),
moving 2:('segment','channel_out','action_val','duration_[ms]','start_freq_[MHz]','end_freq_[MHz]',"hybridicity",
"tot_amp_[mV]","start_amp","end_amp","freq_phase_[deg]","freq_adjust","amp_adjust"),
ramp 3:('segment','channel_out','action_val','duration_[ms]','freqs_input_[MHz]','num_of_traps','distance_[um]',
'tot_amp_[mV]','start_amp','end_amp','freq_phase_[deg]','freq_adjust','amp_adjust'),
ampMod 4:('segment','channel_out','action_val','duration_[ms]','freqs_input_[MHz]','num_of_traps',
'distance_[um]','tot_amp_[mV]','freq_amp','mod_freq_[kHz]','mod_depth','freq_phase_[deg]','freq_adjust','amp_adjust'),
switch 5:('segment','channel_out','action_val','duration_[ms]','off_time_[us]','freqs_input_[MHz]','num_of_traps',
'distance_[um]','tot_amp_[mV]','freq_amp','freq_phase_[deg]','freq_adjust','amp_adjust'),
offset 6:('segment','channel_out','action_val','duration_[ms]','mod_freq_[kHz]',
'dc_offset_[mV]','mod_depth') """

try:
    from spcm_home_functions import ampAdjuster2d, adjuster
except ImportError:
    import sys
    sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex\awg')
    from spcm_home_functions import ampAdjuster2d, adjuster
import matplotlib.pyplot as plt
import numpy as np
colours = plt.rcParams['axes.prop_cycle'].by_key()['color']
import time

def adj(segment, power, freq=166, tot=220):
    if eval(segment['amp_adjust']):
        return ampAdjuster2d(freq, power)
    else:
        return tot*power

def plot_playback(data):
    """Display the timed sequence on a plot. Produces a Frequency and Amplitude plot
    of the consecutive segments for each channel."""
    sample_rate = data['properties']['card_settings']['sample_rate_Hz']
    for chan in eval(data['properties']['card_settings']['active_channels']):
        fig0 = plt.figure(2*chan)
        ax0  = fig0.add_subplot(111)
        ax0.set_ylabel('Frequency (MHz)')
        ax0.set_xlabel('Step Duration (ms)')
        fig1 = plt.figure(2*chan+1)
        ax1  = fig1.add_subplot(111)
        ax1.set_ylabel('Amplitude (mV)')
        ax1.set_xlabel('Step Duration (ms)')
        j = 0 # which step comes next
        m = 0 # add in extra points
        prev_steps = set([0])
        xlabels = []
        for i in range(len(data['steps'])):
            step = data['steps']['step_%s'%j]
            j = step['next_step']
            seg = data['segments']['segment_%s'%step['segment_value']]['channel_%s'%chan]
            action_type = seg['action_code']
            print(', '.join(map(str, [i, j, action_type])))
            i += m
            if 'static' in action_type: 
                step['num_of_loops'] = 1 # duration is of all the loops for static trap
            for n in range(step['num_of_loops']):
                xlabels.append(str(seg['duration_[ms]']))
                # freq
                if any(x in action_type for x in ['static', 'ramp', 'ampMod', 'switch']):
                    freqs_input = np.array(eval(seg['freqs_input_[MHz]']))
                    N = len(freqs_input)
                    fadjust = seg['freq_adjust']
                    tot_amp = seg['tot_amp_[mV]']
                    if eval(fadjust):
                        freqs_input = adjuster(freqs_input*1e6, sample_rate, seg['num_of_samples'])
                    ax0.set_prop_cycle(color=colours)
                    ax0.plot([[i]*N, [i+1]*N], [freqs_input]*2)
                    # amp - would be faster to use arrays but difficult with power calibration
                    if 'static' in action_type or 'switch' in action_type:
                        for k, amp in enumerate(eval(seg['freq_amp'])):
                            amp = adj(seg, amp, freqs_input[k], tot_amp)
                            if 'switch' in action_type:
                                ax1.plot([i,i+0.3,i+0.3,i+0.7,i+0.7,i+1], [amp,amp,0,0,amp,amp], color=colours[k])
                                plt.text(i+0.32, 150, str(seg['off_time_[us]'])+'$\mu$s')
                            else: 
                                ax1.plot([i, i+1], [amp]*2, color=colours[k])
                    elif 'ramp' in action_type:
                        for k, (a0, a1) in enumerate(zip(eval(seg['start_amp']), eval(seg['end_amp']))):
                            ax1.plot([i, i+1], [adj(seg, y, freqs_input[k], tot_amp) for y in [a0, a1]], color=colours[k])
                    elif 'ampMod' in action_type:
                        x = np.linspace(i,i+1,357)
                        for k, amp in enumerate(eval(seg['freq_amp'])):
                            ax1.plot(x, adj(seg, amp, freqs_input[k], seg['tot_amp_[mV]']) * (1+seg['mod_depth']*np.sin((x-i)*2*np.pi*seg['num_of_samples']*1e3*seg['mod_freq_[kHz]']/sample_rate)), color=colours[k])    
                elif 'moving' in action_type:
                    start_freq = eval(seg['start_freq_[MHz]'])
                    end_freq = eval(seg['end_freq_[MHz]'])
                    for k, (a0, a1, f0, f1) in enumerate(zip(eval(seg['start_amp']), eval(seg['end_amp']), start_freq, end_freq)):
                        ax0.plot([i, i+1], [f0, f1], color=colours[k])
                        ax1.plot([i, i+1], [adj(seg, a, f, seg['tot_amp_[mV]']) for a,f in [(a0,f0), (a1,f1)]], color=colours[k])
                elif 'offset' in action_type:
                    ax0.plot([i, i+1], [0]*2, c=colours[0])
                    x = np.linspace(i,i+1,357)
                    ax1.plot(x, seg['dc_offset_[mV]'] * (1+seg['mod_depth']*np.sin((x-i)*2*np.pi*seg['num_of_samples']*seg['mod_freq_[kHz]']*1e3/sample_rate)), c=colours[0])

            if step['condition'] == 1: # wait for trigger
                m += 1
                ax0.text(i+1.1, np.mean(ax0.get_ylim()), '...')
                ax1.text(i+1.1, np.mean(ax1.get_ylim()), '...')
                xlabels.append('wait')
            
            if j in prev_steps: # return to start
                break
            prev_steps.add(j)
        
        y0, y1 = ax0.get_ylim()
        N = len(xlabels)
        ax0.plot([np.arange(N)+1]*2, [[y0]*N,[y1]*N], 'k--', alpha=0.4)
        y0, y1 = ax1.get_ylim()
        ax1.plot([np.arange(N)+1]*2, [[y0]*N,[y1]*N], 'k--', alpha=0.4)

        ax0.set_xticks(np.arange(N)+0.5)
        ax0.set_xticklabels(xlabels)
        ax1.set_xticks(np.arange(N)+0.5)
        ax1.set_xticklabels(xlabels)
                        
    plt.show()

if __name__ == "__main__":
    import json
    t0 = time.time()
    with open(r'Z:\Tweezer\Experimental Results\2021\July\07\Measure19\AWGparam0.txt') as f:
        filedata = json.load(f)
    t1 = time.time()
    print(t1 - t0)
    plt.style.use('DUdefault')
    plot_playback(filedata)
    # print(time.time() - t1)