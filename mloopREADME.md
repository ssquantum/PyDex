# M LOOP with DexTeR
## shady code brought to you by Jonathan 

Using pydex, we can communicate with dexter in a simple way without ever needing to alter the labview code. One application of this is to allow for optimisiation of the experiment via tools such as mloop 

This implementation uses a structure as shown is this diagram:
![mloopflow](docs\mloopflow.png)
# How to use

Start sequence: Order important!!

## M-LOOP 

Launch mloop in a command prompt by typing

```bash
cd (directory mloop will use to communicate)  
M-LOOP
```

## PyDex

Run the mloopcommunicator script in a pydex enviroment. 

## MATLAB

Launch the imageanalyser.m and engage autoload. Make sure dexter run number is ok 

## Dexter
Launch terminal, engage python mode

## Editing mloop behaviour

Change exp_config.txt, and mloopdict.json to edit which variables are being optimised, and over what range. 
The mloopdict stores the python dict which should look like this:

```json
{"Param 1": 
    {"type": "timestep", "timestep": 0, "value": 0},
 "Param 2": {"type": "slowanalogue", "timestep": [12, 13, 14], "channelname": "E/W shims (X)", "value": 0}}
 ```
Currently these are the only types of parameter supported. let me know if you can think of another which would be useful. 

To change cost function change mloopoutput.m Currently it is set to maximise OD

# Code doc

## MLOOP
see https://m-loop.readthedocs.io/en/latest/install.html

## PyDex

mloopcommunicator is a script written in the PyDEX API, which
1. Sets up a TCP server for communication with Dexter
2. loops looking for a exp_input from mloop, then reads this using the translator libary of pydex
3. Using translator.mloopmodify() interprets exp_input based on the mloopdict.json configuration file
4. Sends on a modified dexter sequence to be run by dexter

The script contains ***hardcoded paths*** which must be correct for things to work. 


### translator.translate.mloopmodify
Modify the cluster based on parameters read from mloop txt file,interpreted by mloopdict nested dictionary. 

Supports two types of paramter, specified by the 'type' string. This is case sensitive. 

1. 'timestep'  : Use the number as the length of a timestep
2. 'slowanalogue': Use the number as a Voltage. This has aditional arguments
            "timestep" : list of timestep numbers over which to modify the volatage
            "channel name" : Name of the slow analouge to modift


## MATLAB 

The cost function from the anayled images is provided by mloopoutput.m 

This script is run immeadiately after ana_sp1. 

