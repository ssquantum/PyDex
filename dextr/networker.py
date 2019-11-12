"""Dextr - communication over the network
Stefan Spence 21/10/19

 - A server that makes TCP connections
 - the server is started by instantiating it and calling start()
 - implement a queue of messages to send, always in the format [enum, 
 message_length, message]
 - when there is a new network connection, send the message at the front of
 the queue. 
 - if the queue is empty, continue looping until there is a message to send.
"""
import socket
import struct
try:
    from PyQt4.QtCore import QThread, pyqtSignal
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal
    
TCP_ENUM = { # enum for DExTer's producer-consumer loop cases
'Initialise': 0,
'Save sequence': 1,
'Load sequence': 2,
'Lock sequence':3, 
'Run sequence':4, 
'Run continuously':5, 
'Multirun run':6, 
'Delete multirun list column':7, 
'Multirun populate values':8, 
'Change multirun index':9, 
'Change multirun analogue type':10, 
'Change multirun type':11, 
'Load event':12, 
'Delete event':13, 
'Move event top':14, 
'Move event bottom':15, 
'Move event up':16, 
'Move event down':17, 
'New routine specific event':18, 
'Convert routine specific event':19, 
'Change timestep':20, 
'Collapse event':21, 
'Load last timestep':22, 
'Panel close':23, 
'Check IOs':24, 
'Run GPIB case':25, 
'TCP read':26, 
'TCP multirun values':27, 
'TCP load sequence':28
}
    
class PyServer(QThread):
    """Create a server that opens a socket to host TCP connections.
    While stop=False the server waits for a connection. Once a connection is
    made, send a message from the queue. If the queue is empty, wait until 
    there is a message in the queue before using the connection.
    port - the unique port number used for the next socket connection."""
    textin = pyqtSignal(str) # received message
    stop   = False           # toggle whether to stop listening
    
    def __init__(self, port=8089):
        super().__init__()
        self.server_address = ('localhost', port)
        self.msg_queue = []
        
    def add_message(self, enum, text, encoding="UTF-8", ):
        """Update the message that will be sent upon the next connection.
        enum - an integer corresponding to the enum for DExTer's producer-
                consumer loop
        text - the message to send as a string."""
        # enum and message length are sent as unsigned long int (4 bytes)
        self.msg_queue.append([struct.pack("!L", int(enum)), # enum 
                                struct.pack("!L", len(text)), # msg length 
                                bytes(text, encoding)]) # message

    def run(self, encoding="UTF-8", buffer_size=1024):
        """Keeps a socket open that waits for new connections. For each new
        connection, open a new socket that sends the following 3 messages:
         1) the enum as a single byte, which will correspond to a command. 
         2) the length of the text string in 3 bytes (i.e. length < 1000).
         3) the text string.
        Then receives a message that is emitted via a pyqtSignal."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(self.server_address)
            s.listen() # start the socket that waits for connections
            while True:
                if self.check_stop():
                    break # toggle
                elif len(self.msg_queue):
                    conn, addr = s.accept() # create a new socket
                    enum, mes_len, message = self.msg_queue.pop(0)
                    with conn:
                        conn.sendall(enum) # send enum
                        conn.sendall(mes_len) # send text length
                        conn.sendall(message) # send text
                        # send signal to listen for message in return
                        self.textin.emit(str(conn.recv(buffer_size), encoding))
            
    def check_stop(self):
        """Check the value of stop - must be a function in order to work in
        a while loop."""
        return self.stop
        
    def reset_stop(self):
        """Reset the stop toggle so that the event loop can run."""
        self.stop = False
    
    def close(self):
        """Stop the event loop safely, ensuring that the sockets are closed.
        Once the thread has stopped, reset the stop toggle so that it 
        doesn't block the thread starting again the next time."""
        while True: # make sure that the slot is only connected once 
            try: self.finished.disconnect(self.check_stop)
            except TypeError: break
        self.finished.connect(self.reset_stop)
        self.stop = True
                            
if __name__ == "__main__":
    ps = PyServer()
    ps.textin.connect(print)
    ps.add_message('0', 'Hello world!')
    ps.start() # will keep running until you call ps.close()