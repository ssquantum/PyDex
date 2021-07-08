"""networker - communication over TCP
Stefan Spence 21/10/19

 - A server that makes TCP connections
 - the server is started by instantiating it and calling start()
 - implement a queue of messages to send, always in the format [enum, 
 message_length, message]
 - when there is a new network connection, send the message at the front of
 the queue. 
 - if the queue is empty, continue looping until there is a message to send.
 - Note: LabVIEW uses MBCS encoding of bytes to strings.
"""
import socket
import struct
import time
try:
    from PyQt4.QtCore import QThread, pyqtSignal
    from PyQt4.QtGui import QApplication
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal
    from PyQt5.QtWidgets import QApplication 
import sys
if '..' not in sys.path: sys.path.append('..')
from strtypes import error, warning, info

TCPENUM = { # enum for DExTer's producer-consumer loop cases
'Initialise': 0,
'Save sequence': 1,
'Load sequence': 2,
'Lock sequence':3, 
'Run sequence':4, 
'Run continuously':5, 
'Multirun run':6, 
'Multirun populate values':7, 
'Change multirun analogue type':8, 
'Change multirun type':9, 
'Load event':10, 
'Delete event':11, 
'Move event top':12, 
'Move event bottom':13, 
'Move event up':14, 
'Move event down':15, 
'New routine specific event':16, 
'Convert routine specific event':17, 
'Change timestep':18, 
'Collapse event':19, 
'Load last timestep':20, 
'Panel close':21, 
'Check IOs':22, 
'Run GPIB case':23, 
'TCP read':24, 
'TCP load sequence from string':25, 
'TCP load sequence':26,
'TCP load last time step':27
}

def reset_slot(signal, slot, reconnect=True):
    """Make sure all instances of slot are disconnected
    from signal. Prevents multiple connections to the same 
    slot. If reconnect=True, then reconnect slot to signal."""
    while True: # make sure that the slot is only connected once 
        try: signal.disconnect(slot)
        except TypeError: break
    if reconnect: signal.connect(slot)
    
class PyServer(QThread):
    """Create a server that opens a socket to host TCP connections.
    While stop=False the server waits for a connection. Once a connection is
    made, send a message from the queue. If the queue is empty, wait until 
    there is a message in the queue before using the connection.
    host - a string giving either the internet domain hostname, or the 
        IPv4 address. 'localhost' uses the computer running this script. 
    port - the unique port number used for the next socket connection."""
    textin = pyqtSignal(str) # received text
    dxnum  = pyqtSignal(str) # received run number, synchronised with DExTer
    stop   = False           # toggle whether to stop listening
    connected = False        # whether a TCP connection is currently active
    
    def __init__(self, host='localhost', port=8089, name=''):
        super().__init__()
        self._name = name
        self.server_address = (host, port)
        self.__mq = []
        self.__lock  = False # message queue is locked
        self.ts = {label:[time.time()] for label in ['start', 'connect', 'waiting', 
            'sent', 'received', 'disconnect']}
        self.app = QApplication.instance() # the main application that's running

    def lockq(self):
        """Lock the msg queue and add to reserve instead."""
        self.__lock = True

    def unlockq(self):
        """Unlock the msg queue and add all the msgs from reserve"""
        self.__lock = False

    def add_message(self, enum, text, encoding="mbcs"):
        """Append a message to the queue that will be sent by TCP connection.
        enum - (int) corresponding to the enum for DExTer's producer-
                consumer loop.
        text - (str) the message to send.
        enum and message length are sent as unsigned long int (4 bytes)."""
        if not self.__lock:
            self.__mq.append([struct.pack("!L", int(enum)), # enum 
                                struct.pack("!L", len(bytes(text, encoding))), # msg length 
                                bytes(text, encoding)]) # message
       
    def priority_messages(self, message_list, encoding="mbcs"):
        """Add messages to the start of the message queue.
        message_list - list of [enum (int), text(str)] pairs."""
        self.__mq = [[struct.pack("!L", int(enum)), # enum 
                            struct.pack("!L", len(bytes(text, encoding))), # msg length 
                            bytes(text, encoding)] for enum, text in message_list] + self.__mq
        
    def get_queue(self):
        """Return a list of the queued messages."""
        return [(str(int.from_bytes(enum, 'big')), int.from_bytes(tlen, 'big'), 
                str(text, 'mbcs')) for enum, tlen, text in self.__mq]
                        
    def clear_queue(self):
        """Remove all of the messages from the queue."""
        reset_slot(self.textin, self.clear_queue, False) # only trigger clear_queue once
        self.__mq = []
        self.unlockq()

    def run(self, encoding="mbcs"):
        """Keeps a socket open that waits for new connections. For each new
        connection, open a new socket that sends the following 3 messages:
         1) the enum as int32 (4 bytes), which will correspond to a command. 
         2) the length of the text string as int32 (4 bytes).
         3) the text string.
        Then receives:
         1) the run number as int32 (4 bytes).
         2) the length of the message to come as int32 (4 bytes).
         3) the sent message as str."""
        self.ts['start'] = time.time() 
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try: 
                s.bind(self.server_address)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # reuse addresses if they're in time_wait
                # start the socket that waits for connections
                s.listen(0) # only allow one connection at a time
            except OSError as e:
                error('Failed to start server %s at address: '%self._name + 
                    ', '.join(map(str, self.server_address)) + '\n' + str(e))
                reset_slot(self.finished, self.reset_stop)
                self.stop = True # stop the thread running
            while True:
                self.app.processEvents() # hopefully helps prevent GUI lag
                if self.check_stop():
                    break # toggle
                elif len(self.__mq):
                    conn, addr = s.accept() # create a new socket
                    self.connected = True
                    with conn: # close the connection after this code is executed:
                        try:
                            enum, mes_len, message = self.__mq.pop(0)
                            self.ts['connect'].append(time.time())
                            self.ts['waiting'].append(time.time() - self.ts['disconnect'][-1])
                            try:
                                conn.sendall(enum) # send enum
                                conn.sendall(mes_len) # send text length
                                conn.sendall(message) # send text
                            except (ConnectionResetError, ConnectionAbortedError) as e:
                                self.__mq.insert(0, [enum, mes_len, message]) # check this doesn't infinitely add the message back
                                error('Python server %s: client terminated connection before message was sent.'%self._name +
                                    ' Re-inserting message at front of queue.\n'+str(e))
                            self.ts['sent'].append(time.time() - self.ts['connect'][-1])
                            try:
                                # receive current run number from DExTer as 4 bytes
                                self.dxnum.emit(str(int.from_bytes(conn.recv(4), 'big'))) # long int
                                # receive message from DExTer
                                buffer_size = int.from_bytes(conn.recv(4), 'big')
                                self.textin.emit(str(conn.recv(buffer_size), encoding))
                            except (ConnectionResetError, ConnectionAbortedError) as e:
                                warning('Python server %s: client terminated connection before receive.\n'%self._name+str(e))
                            self.ts['received'].append(time.time() - self.ts['connect'][-1] - self.ts['sent'][-1])
                            self.ts['disconnect'].append(time.time())
                        except IndexError as e: 
                            error('Server %s msg queue was emptied before msg could be sent.\n'%self._name+str(e))
                    self.connected = False
                        
    def save_times(self):
        """Print the timings between messages."""
        with open('networker_timings.txt', 'w') as f:
            f.write('waiting, sent, received\n')
            for i in range(len(self.ts['sent'])):
                f.write(','.join(['%.4g'%(self.ts[key][i]*1e3) for key in ['waiting', 'sent', 'received']])+'\n')

    def check_stop(self):
        """Check the value of stop - must be a function in order to work in
        a while loop."""
        return self.stop
        
    def reset_stop(self):
        """Reset the stop toggle so that the event loop can run."""
        self.stop = False
    
    def close(self, args=None):
        """Stop the event loop safely, ensuring that the sockets are closed.
        Once the thread has stopped, reset the stop toggle so that it 
        doesn't block the thread starting again the next time."""
        reset_slot(self.finished, self.reset_stop, True)
        self.stop = True
                            
if __name__ == "__main__":
    import sys
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
        
    try:
        from PyQt4.QtGui import QWidget
    except ImportError:
        from PyQt5.QtWidgets import QWidget
    
    ps = PyServer()
    ps.textin.connect(print)
    ps.add_message('24', 'Hello world!')
    reset_slot(ps.dxnum, ps.close, True) # close server after message
    ps.start() # will keep running until you call ps.close()
    w = QWidget()
    w.setWindowTitle('Server is runnning')
    w.show()
    if standalone: 
        sys.exit(app.exec_()) # ends the program when the widget is closed