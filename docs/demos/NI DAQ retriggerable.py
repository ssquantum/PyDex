import nidaqmx as ni
import time

tai = ni.Task()
tai.ai_channels.add_ai_voltage_chan('Dev2/ai1')# , terminal_config=ni.constants.TerminalConfiguration.DIFFERENTIAL)
tai.timing.cfg_samp_clk_timing(1e3, source='/Dev2/Ctr0InternalOutput',sample_mode = ni.constants.AcquisitionType.CONTINUOUS, samps_per_chan=1010)
tco = ni.Task()
tco.co_channels.add_co_pulse_chan_freq('/Dev2/ctr0', freq=1e3, idle_state=ni.constants.Level.LOW)
# finite samples, samples per channel
tco.timing.cfg_implicit_timing(sample_mode=ni.constants.AcquisitionType.FINITE, samps_per_chan=10)
tco.triggers.start_trigger.cfg_dig_edge_start_trig('/Dev2/PFI0', trigger_edge=ni.constants.Edge.RISING)
tco.triggers.start_trigger.retriggerable = True

def cback(*args): 
    print(tai.read(10))
    return 1

tai.register_every_n_samples_acquired_into_buffer_event(10, cback)

tco.start()
tai.start()
time.sleep(10)
tco.close()
tai.close()
device = ni.system.device.Device("Dev2")
device.reset_device()
