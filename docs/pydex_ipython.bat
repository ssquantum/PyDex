@echo off
rem -- set conda and python as environment variables. Check if python is installed for all users first.
if EXIST %ALLUSERSPROFILE%\Anaconda3 ( 
	call %ALLUSERSPROFILE%\Anaconda3\Scripts\activate
) else ( 
	call %USERPROFILE%\Anaconda3\Scripts\activate
)

rem -- activate the Python environment to load modules
call conda activate pydexenv

rem -- now start the monitoring program in a separate shell, and the main PyDex script in this shell
ipython -i -c "run importrun.py"

conda deactivate