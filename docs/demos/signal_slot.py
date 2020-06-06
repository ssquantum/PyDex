"""Signal - Slot Demo
Stefan Spence 06.06.20

Create a PyQt Object that has a signal.
The signal must belong to a class that inherits
a PyQt class.
The signal can be connected to slots that are
executed when the signal is emitted.
"""
from PyQt5.QtCore import QObject, pyqtSignal

# create a class to contain the signal
class MyClass(QObject): # inherits QObject
    """The signal must be a class attribute, 
    defined before the __init__ function, as
    opposed to an instance attribute that is
    defined in the __init__ function.
    Signals are bound to a specified type of
    data.
    Any class that inherite a PyQt class must
    initiate the parent class as well."""
    signal = pyqtSignal(str, int) # can emit a string and an integer

    def __init__(self):
        super().__init__() # needed to inherit QObject
        self.i = 0

    def reset(self):
        self.i = 0

    def increment(self):
        """Simple function just adds 1 to i
        every time it's called. Emit the
        signal when i == 3."""
        self.i += 1
        if self.i == 3:
            self.signal.emit('We reached i = ', self.i)


# the signal can be connected to any number of slots
# in order to use the signal, we must make an instance
# of the class
c = MyClass()
c.signal.connect(print)

# the slot will be called when the signal is emitted:
for i in range(4):
    print(i)
    c.increment()

# we can connect several slots at the same time
c.reset()
c.signal.connect(c.reset) # reset i=0 when the signal is emitted
for i in range(8):
    print(i)
    c.increment()