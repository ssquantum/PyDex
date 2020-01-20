from networking.networker import PyServer 
from sequences.translator import translate
import json
import time
import os
basesequencepath = "sequences\SequenceFiles\0_17 September 2019_09 30 18.xml"
mloopdictpath = "sequences\mloopdict.json"

mloopdict = json.loads(open(mloopdictpath,'r').read() )

t = translate()
t.load_xml('.\\sequences\\SequenceFiles\\0_17 September 2019_09 30 18.xml')
mloopinputpath = r"C:\Users\Jonathan\Documents\PhD\Experiment\JMMLOOPLabView\MLOOPArea"
loop = True
ps = PyServer()
ps.start()
while loop == True
    if os.path.exists(mloopinputpath+'\exp_input.txt')
        t.mloopmodify(mloopdict,mloopinputpath)
        ps.add_message(25,t.write_to_str())
ps.close()