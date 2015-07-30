import json
import tile_gen.core as core
import tile_gen.config as config
import tile_gen.util as util
from ModestMaps.Core import Coordinate

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

    config_dict = json.load(util.open(configpath))
    return config.build_config(config_dict)

def get_tile(layer, z, x, y, ext):
   """ Get a type string and tile binary for a given request layer tile. """

   config = parse_config_file("tilestache.cfg")

   # maybe do some other config checks as before ...
   if layer not in config.layers:
       raise IOError("Layer not found: " + layer)

   tile = config.layers[layer].get_tile(Coordinate(x, y, z), ext, False, False)
   return tile
