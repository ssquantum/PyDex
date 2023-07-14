@echo on
title DDS3 console
call "C:\Users\Lab\Anaconda3\Scripts\activate.bat"
cd /d "Z:\Tweezer\Code\Python 3.5\PyDex\dds"
call conda activate pydexenv
call python dds3gui.py