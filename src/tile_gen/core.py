from StringIO import StringIO
from ModestMaps.Core import Coordinate
import json
import tile_gen.config as c
import tile_gen.util as u

config = c.build_config(json.load(u.open("tilestache.cfg")))

def get_tile(layer, z, x, y, ext, ignore_cached = False):
    if layer not in config.layers: raise IOError("Layer not found: " + layer)

    cache    = config.cache
    provider = config.provider
    layer    = config.layers[layer]
    coord    = Coordinate(y, x, z)
    mimetype, format = u.get_type_by_ext(ext)

    cache.lock(layer, coord, format)
    try:
        body = cache.read(layer, coord, format) if not ignore_cached else None

        if body is None:
            buff = StringIO()
            tile = provider.render_tile(layer, coord)
            tile.save(buff, format)
            cache.save(buff.getvalue(), layer, coord, format)
    finally:
        cache.unlock(layer, coord, format)

    return mimetype, body
