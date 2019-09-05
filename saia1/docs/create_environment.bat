rem -- Install the Python environment for SAIA to ensure the right modules are installed
call %ALLUSERSPROFILE%\Anaconda3\Scripts\activate
conda env create -f .\saiaenvironment.yml