import json
import tile_gen.core as core
import tile_gen.config as config
import tile_gen.util as util
from ModestMaps.Core import Coordinate

def parse_config_file(configpath):
    config_dict = json.load(util.open(configpath))
    return config.build_config(config_dict)

def get_tile(layer, z, x, y, ext):
   config = parse_config_file("tilestache.cfg")

   if layer not in config.layers: raise IOError("Layer not found: " + layer)

   tile = core.get_tile(config.layers[layer], Coordinate(y, x, z), ext)
   return tile
