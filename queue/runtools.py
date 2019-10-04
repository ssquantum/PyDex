"""Queue
Stefan Spence 04/10/19

 - control the run number
 - translate DExTer sequences to/from json
"""
import time

class runnum:
    """Take ownership of the run number that is
    synchronised between modules of PyDex."""
    def __init__(start=0):
        self._n   = start # the run #
        self.lock = 0     # run # locked
        self.rlog = []    # log failed requests to change run num

    def increase(label=''):
        """Request to increase the run #. This is only
        possible if lock is False. Else, the time and 
        label are recorded in the request log."""
        if not self.lock:
            self._n += 1
        else: self.rlog.append(label+' '+time.strftime("%x %X"))