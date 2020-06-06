"""Thread Demo
Stefan Spence 06.06.20

Make a class that inherits the PyQt QThread class.
Threads can run in parallel to the main script.
They are useful for running tasks that would hold
up the main program either because they're slow or
must be run continuously. 
"""
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QLabel
import sys
import time
    
class MyThread(QThread):
    """When the thread is started, it will increment
    an integer every second. The value is emitted by
    a pyqtSignal. Threads usually cannot be stopped
    from outside the thread, so in order to tell it
    to stop, it polls the Boolean attribute 'stop'.
    When stop=True, the thread will stop running."""
    stop = False # toggle to stop the thread running
    counter = pyqtSignal(str)

    def __init__(self):
        """Must initiate the parent class.
        Use the thread's 'finished' signal to call
        the reset_stop function when the thread has
        finished."""
        super().__init__() # needed to inherit QThread
        self.i = 0
        # call reset_stop when the thread finished
        self.finished.connect(self.reset_stop)

    def run(self):
        """Run the thread continuously incrementing
        until the stop bool is toggled."""
        while not self.check_stop(): # continue while stop=False
            # increment the counter
            self.i += 1
            self.counter.emit('Counter = '+str(self.i))
            time.sleep(1)

    def check_stop(self):
        """Check the value of stop - must be a function 
        in order to work in a while loop."""
        return self.stop
        
    def reset_stop(self):
        """Reset the stop toggle so that the thread
        can run again next time start() is called."""
        self.stop = False
    
    def close(self):
        """Tell the thread to stop."""
        self.stop = True


# create an instance of the thread
thread = MyThread()
thread.start() # the thread is now running 

print('Thread has started, but the main program continues.')
for i in reversed(range(5)):
    print('Wait %s s before continuing'%i)
    time.sleep(1)

# now we'll create a pop up window to control the thread
# we need to create a QApplication instance for the PyQt
# event queue.
app = QApplication.instance()
standalone = app is None # check if the instance was created
if standalone: # if there isn't an instance, make one
    app = QApplication(sys.argv) 
        
# make a basic display
class PopUpWindow(QMainWindow):
    """A window with a label to display some text,
    a start button, and a stop button."""
    def __init__(self, thread_handle):
        super().__init__() # needed to inherit QMainWindow
        self.thread = thread_handle # make the thread an instance attribute
        # make the display
        self.setWindowTitle('QThread Demonstration')
        self.setGeometry(300, 300, 400, 400) # x, y, width, height
        # automatically placed on the display
        self.label = QLabel('Thread is running' if self.thread.isRunning() else 'Press start to run the thread', self)
        self.label.move(50,50) # position the label in the window
        self.label.resize(200,50) 
        # when the thread signal is emitted, it will update the label text
        self.thread.counter.connect(self.label.setText) 

        # make buttons to control the thread
        start_button = QPushButton('Start', self)
         # when the button is clicked, call start_thread
        start_button.clicked.connect(self.start_thread)
        start_button.move(50,200)
        stop_button = QPushButton('Stop', self)
        # when the button is clicked, call stop_thread
        stop_button.clicked.connect(self.stop_thread) 
        stop_button.move(200, 200)


    # make functions for the buttons to use
    def start_thread(self):
        self.thread.start()
        self.label.setText('Thread has started.')
    def stop_thread(self):
        self.thread.close()
        self.label.setText('Thread has stopped.')

w = PopUpWindow(thread) # pass the thread to a new pop up window
w.show() # make the window pop up
if standalone: 
    sys.exit(app.exec_()) # ends the program when the window is closed