@echo off
rem -- set conda and python as environment variables
call %ALLUSERSPROFILE%\Anaconda3\Scripts\activate

rem -- activate the Python environment to load modules
call conda activate saiaenv

rem -- now run the program
set /p FileToRun=Enter the file to run: 
python %FileToRun%

call deactivate