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
try:
    from PyQt4.QtCore import QThread, pyqtSignal
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal
    
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
        
    def add_message(self, enum, text):
        """Update the message that will be sent upon the next connection.
        enum - a single byte giving an int 0-9 that corresponds to a command
        text - the message to send as a string."""
        textLength = str(len(text))
        # make sure the message length is sent as str of length 3
        self.msg_queue.append(
            [enum, '0'*(3-len(textLength)) + textLength, text])

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
                        conn.sendall(bytes(enum, encoding)) # send enum
                        conn.sendall(bytes(mes_len, encoding)) # send text length
                        conn.sendall(bytes(message, encoding)) # send text
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
        self.stop = True
        while True: # make sure that the slot is only connected once 
            try: self.finished.disconnect(self.check_stop)
            except TypeError: break
        self.finished.connect(self.reset_stop)
                            
if __name__ == "__main__":
    ps = PyServer()
    ps.textin.connect(print)
    ps.add_message('0', 'Hello world!')
    ps.start() # will keep running until you call ps.close()