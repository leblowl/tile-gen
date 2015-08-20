import os
import sys
import __builtin__
from sys import  modules

def open(filename):
    if filename:
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

def get_type_by_ext(ext):
    if ext.lower() == 'json':
        return 'application/json', 'JSON'

    elif ext.lower() == 'topojson':
        return 'application/json', 'TopoJSON'

    elif ext.lower() == 'mvt':
        return 'application/x-protobuf', 'MVT'

    else:
        raise ValueError(ext + " is not a valid extension")

def bounds(projection, coord):
    ll = projection.coordinateProj(coord.down())
    ur = projection.coordinateProj(coord.right())
    return ll.x, ll.y, ur.x, ur.y

def comp(*functions):
    return functools.reduce(lambda f, g: lambda x: f(g(x)), functions, lambda x: x)
