import os
import sys
import __builtin__

def open(filename):
    for path in sys.path:
        path = os.path.join(path, filename)
        if os.path.exists(path):
            return __builtin__.open(path)
    raise IOError('File not found: ' + filename)

def load_class_path(classpath):
    """ Load external class based on a path.
        Example classpath: "Module.Submodule.Classname".
    """
    modname, objname = classpath.rsplit('.', 1)
    __import__(modname)
    module = modules[modname]
    _class = eval(objname, module.__dict__)
    return _class

def get_type_by_ext(self, extension):
    if extension.lower() == 'json':
        return 'application/json', 'JSON'

    elif extension.lower() == 'topojson':
        return 'application/json', 'TopoJSON'

    elif extension.lower() == 'mvt':
        return 'application/x-protobuf', 'MVT'

    else:
        raise ValueError(extension + " is not a valid extension for responses with multiple layers")
