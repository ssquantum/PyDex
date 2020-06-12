"""Mutable Types Demo
Stefan Spence 12.06.20

The handling of memory in Python is largely
hidden from the user. Usually this allows 
for blissful ignorance. In the following 
cases, one must use caution.

Useful reading:
https://www.programiz.com/python-programming/global-local-nonlocal-variables
https://medium.com/@meghamohan/mutable-and-immutable-side-of-python-c2145cf72747
"""
import numpy as np
from copy import deepcopy

print("""Most variables in python are immutable.
When you assign a variable, it is assigned a 
portion of memory, and given a unique ID.""")
var = 1
print("var = ", str(var))
print("id = ", str(id(var)))
var = 2
print("var = ", str(var))
print("id = ", str(id(var)))
print("""When you change a variable, you're 
actually creating a new variable, as you can
see by the different ID: it's referencing a
different portion of memory.
Best practice in python is to use local 
variables wherever possible. Global 
variables can lead to confusion with 
namespaces (several objects with the same
name).

But there are some important exceptions:
lists, sets, dictionaries, and numpy arrays
are all mutable types. With these, you can
reference the same portion of memory.
Make a copy of a dictionary""")
list1 = list(range(10))
dict1 = {'item1':list1, 'item2':2}
dict2 = dict1
dict2['item1'][1] = -1
print("""Changing an item in a copy of a 
dictionary also changes the original
dictionary.""")
print(dict1 == dict2)
dict2['item2'] = -5
print(dict1 == dict2)
print("""If you use the dict.copy() function
then immutable variables can be reassigned,
but if you change a mutable variable it will 
still affect the original copy.""")
dict3 = dict1.copy()
dict3['item2'] = -5
print(dict1 == dict3)
dict3['item1'][1] = -1
print(dict1 == dict3)
print("""The solution is to use a deepcopy.""")
dict4 = deepcopy(dict1)
dict4['item1'][1] = 500
print(dict1 == dict4)

print("A demonstration with numpy arrays:")
def increment(arr):
    arr += 1
    return arr

print("""immutable types are passed by value""")
var1 = 1
increment(var1)
print(var1)

print("""mutable types are passed by reference""")
arr1 = np.array([1])
arr2 = arr1
arr3 = arr1.copy()
increment(arr2)
print(arr1)
print(arr2)
print(arr3)