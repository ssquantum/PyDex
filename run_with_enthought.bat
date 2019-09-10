rem -- This file runs a python script using the Enthought python executable
@echo off
set /p FileToRun=Enter the file to run: 
%LOCALAPPDATA%\Enthought\Canopy\edm\envs\User\python.exe %FileToRun%