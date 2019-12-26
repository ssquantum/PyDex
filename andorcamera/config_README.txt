setPointT   -- temperature set point in degrees Celsius. 
coolerMode  -- 1: temperature maintained on camera shutdown
                2: ambient temperature on camera shutdown
shutterMode -- typ=1: TTL high to open shutter
                mod=1: internal shutter permanently open
                mod=2: internal shutter permanently closed
outamp      -- output amplification setting.
                0: electron multiplication
                1: conventional
hsspeed     -- Horizontal shift speed (MHz)
        value - EM mode shift speed - conventional mode shift speed
        0:         17.0                         3.0
        1:         10.0                         1.0
        2:          5.0                         0.08
        3:          1.0 
vsspeed     -- Vertical shift speeds (us / row).
                0: 0.3  
                1: 0.5
                2: 0.9 
                3: 1.7
                4: 3.3 (default)
preampgain  -- Pre-amp gain setting. The value can be 1, 2 or 3. 
            See the system booklet for what these correspond to.
EMgain      -- electron-multiplying gain factor.
ROI         -- Region of Interest on the CCD. A tuple of form:
                (xmin, xmax, ymin, ymax) = (hstart, hend, vstart, vend).
cropMode    -- reduce the active area of the CCD to improve 
                throughput.
                0: off        1: on
readmode    -- 4: imaging readout mode
acqumode    -- Camera acquisition mode
                1: Single Scan
                2: Accumulate
                3. Kinetics
                4: Fast Kinetics 
                5: Run till abort
triggerMode -- Mode for camera triggering
                0: internal
                1: External
                6: External Start
                7: External Exposure (Bulb)
                9: External FVB EM (only valid for EM Newton models)
                10: Software Trigger
                12: External Charge Shifting
frameTransf -- enable/disable frame transfer mode (not compatible
                with external exposure mode).
                0: off        1: on        
fastTrigger -- enable/disable fast external triggering
                0: off        1: on
expTime     -- exposure time when not in external exposure trigger
                mode. Units: seconds.
verbosity   -- True for debugging info
numKin      -- number of scans in kinetic mode.