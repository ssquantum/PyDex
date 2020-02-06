# M LOOP with DexTeR
## shady code brought to you by Jonathan 

Using pydex, we can communicate with dexter in a simple way without ever needing to alter the labview code. One application of this is to allow for optimisiation of the experiment via tools such as mloop 

This implementation uses a structure as shown is this diagram:
![mloopflow](docs\mloopflow.png)
# How to run

1. Setup Experiment as per normal
2. Launch Dexter 1.3 Microscope Edition and JM version of image analyser. Make sure some atoms are present and imaging etc is nominal
3. Save the current dexter sequence to the shared directory, as **mloopsequence.xml** 
4. Configure the two config files: exp_input is instructions for mloop, **i.e. the bounds on parameters** mloopdict tells python *which parameter to vary*
5. Run the **mloop.bat** file. This will launch the python parts in seperate command prompt windows.
6. Now press python mode. If everything is working you should see a message on the TCP box. If you are happy to proceed open the communicator terminal and press *enter* 
7. M-LOOP will now run the experiment. Once finished safely exit python mode by typing *c* then *enter* into the communicator terminal.



# Editing mloop behaviour

Change exp_config.txt, and mloopdict.json to edit which variables are being optimised, and over what range. 
## Parameters
**mloopdict.json** is a special text file which stores the python dict, and looks like:

```json
{"Param 1": 
    {"type": "timestep", "timestep": 0, "value": 0},
 "Param 2": {"type": "slowanalogue", "timestep": [12, 13, 14], "channelname": "E/W shims (X)", "value": 0}}
 ```
Copy this syntax, varying the objects after the ":" to change the type and timestep of your parameter.

Currently these two options are the only types of parameter supported. let me know if you can think of another which would be useful. 

## Ranges and optimisation
**exp_config.txt** Controls M-LOOP. It is important that you keep the layout the same (i.e. the line spaces) and only change things on the right hand side of equals signs. I've highlighted below the most important section:

```
#Parameter settings
num_params = 2                #number of parameters
min_boundary = [-1,-1]        #minimum boundary
max_boundary = [1,1]          #maximum boundary
first_params = [0.5,0.5]      #first parameters to try
trust_region = 0.4         	#maximum % move distance from best params

#Halting conditions
max_num_runs = 1000                       #maximum number of runs
max_num_runs_without_better_params = 50  
target_cost = 0.01           

To change cost function change mloopoutput.m Currently it is set to maximise atom number. 
```
**Note** the boundrys are in format ``` min_boundary = [min 1, min2] max_boundary = [max 1,max 2]```

The other parts are to do with the algorithm mloop uses, and how it stores data. These are doumented at https://m-loop.readthedocs.io/en/latest/examples.html

# Code documentation

## M-LOOP
see https://m-loop.readthedocs.io/en/latest/install.html

M-LOOP communicates by writing files in the dir that you run it in. The directory is set by the batch file. 

## PyDex

mloopcommunicator is a script written in the PyDEX API, which
1. Sets up a TCP server for communication with Dexter
2. loops looking for a exp_input from mloop, then reads this using the translator libary of pydex
3. Using translator.mloopmodify() interprets exp_input based on the mloopdict.json configuration file
4. Sends on a modified dexter sequence to be run by dexter

The script contains ***hardcoded paths*** which must be correct for things to work. 


### translator.translate.mloopmodify
Modifies the experimental sequence based on parameters read from mloop txt file, interpreted by mloopdict nested dictionary. 

Supports two types of paramter, specified by the 'type' string. This is case sensitive. 

1. 'timestep'  : Use the number as the length of a timestep
2. 'slowanalogue': Use the number as a Voltage. This has aditional arguments
            "timestep" : list of timestep numbers over which to modify the volatage
            "channel name" : Name of the slow analouge to modift


## MATLAB 

The cost function from the anayled images is provided by mloopoutput.m 

This script is run immeadiately after ana_sp1. 

