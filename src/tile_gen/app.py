from os.path import dirname, join as pathjoin, realpath
from urlparse import urlparse
from ModestMaps.Core import Coordinate
import os
import sys
import json
import __builtin__
import tile_gen.core as core
import tile_gen.config as config

def open(filename):
    for path in sys.path:
        path = os.path.join(path, filename)
        print(path)
        if os.path.exists(path):
            return __builtin__.open(path)
    raise IOError('File not found: ' + filename)

def parse_config_file(configpath):
    """ Parse a configuration file and return a Configuration object.

        Configuration file is formatted as JSON with two sections, "cache" and "layers":

          {
            "cache": { ... },
            "layers": {
              "layer-1": { ... },
              "layer-2": { ... },
              ...
            }
          }

        The full path to the file is significant, used to
        resolve any relative paths found in the configuration.

        See the Caches module for more information on the "caches" section,
        and the Core and Providers modules for more information on the
        "layers" section.
    """

    config_dict = json.load(open(configpath))

    scheme, host, path, p, q, f = urlparse(configpath)

    if scheme == '':
        scheme = 'file'
        path = realpath(path)

    dirpath = '%s://%s%s' % (scheme, host, dirname(path).rstrip('/') + '/')

    return config.buildConfiguration(config_dict, dirpath)

def get_tile(layer, z, x, y, ext):
   """ Get a type string and tile binary for a given request layer tile. """

   config = parse_config_file("tilestache.cfg")

   # maybe do some other config checks as before
   if layer not in config.layers:
       raise IOError("Layer not found: " + layer)

   tile = config.layers[layer].getTileResponse(Coordinate(x, y, z), ext, False, False)
   return tile
