rem -- Install the Python environment for PyDex to ensure the right modules are installed
call %ALLUSERSPROFILE%\Anaconda3\Scripts\activate
conda env create -f .\pydexenvironment.yml