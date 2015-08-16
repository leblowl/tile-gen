from StringIO import StringIO
from ModestMaps.Core import Coordinate
import json
import tile_gen.config as config
import tile_gen.util as u

env = None
provider = None

def init(dbinfo):
    env = config.build_config(json.load(util.open("tilestache.cfg")))
    provider = tile_gen.vectiles.server.Provider(dbinfo)

def get_tile(layer, z, x, y, ext, ignore_cached=False):
    if layer not in env.layers: raise IOError("Layer not found: " + layer)

    cache = env.cache
    layer = env.layers[layer]
    coord = Coordinate(y, x, z)
    mimetype, format = u.get_type_by_ext(extension)

    cache.lock(layer, coord, format)
    body = cache.read(layer, coord, format) if not ignore_cached else None

    if body is None:
        buff = StringIO()
        tile = provider.render_tile(layer, coord)
        tile.save(buff, format)
        cache.save(buff.getvalue(), layer, coord, format)

    cache.unlock(layer, coord, format)
    return mimetype, body
