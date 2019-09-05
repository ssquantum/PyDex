rem -- set conda and python as environment variables
call %ALLUSERSPROFILE%\Anaconda3\Scripts\activate

rem -- activate the Python environment to load modules
call conda activate saiaenv

rem -- now start SAIA
python main.py

call deactivate