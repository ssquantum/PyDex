"""PyDex Monitoring Analysis
Stefan Spence 19/11/20

 - Send results to influxdb 
"""
import os
import sys
sys.path.append('.')
sys.path.append('..')
import time
import numpy as np
try:
    from PyQt4.QtCore import pyqtSignal, QThread
except ImportError:
    from PyQt5.QtCore import pyqtSignal, QThread
from collections import OrderedDict
from strtypes import strlist, listlist, BOOL
import logging
logger = logging.getLogger(__name__)
from networking.client import PyClient


"Lab_Sensors,SOURCE=Arduino Pressure=%s"

129, 234, 190, 191

client.println(F("POST /write?db=arduino HTTP/1.1"));
  client.println(F("Host: 129.234.190.191"));
  client.println(F("User-Agent: PyDex"));
  client.println(F("Connection: close"));
  client.println(F("Content-Type: application/x-www-form-urlencoded"));
  client.print(F("Content-Length: "));
  client.println(dataSize);
  client.println();
  client.println(data);


  while(client.available()) {
   Serial.print((char)client.read());
  } 
  Serial.println();

  client.stop(); 