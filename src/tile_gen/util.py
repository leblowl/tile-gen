import os
import sys
import __builtin__

def open(filename):
    for path in sys.path:
        path = os.path.join(path, filename)
        if os.path.exists(path):
            return __builtin__.open(path)
    raise IOError('File not found: ' + filename)

def get_type_by_ext(self, extension):
    if extension.lower() == 'json':
        return 'application/json', 'JSON'

    elif extension.lower() == 'topojson':
        return 'application/json', 'TopoJSON'

    elif extension.lower() == 'mvt':
        return 'application/x-protobuf', 'MVT'

    else:
        raise ValueError(extension + " is not a valid extension for responses with multiple layers")
