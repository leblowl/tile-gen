import os
import sys
import __builtin__

def open(filename):
    for path in sys.path:
        path = os.path.join(path, filename)
        if os.path.exists(path):
            return __builtin__.open(path)
    raise IOError('File not found: ' + filename)
