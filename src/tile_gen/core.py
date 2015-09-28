from ModestMaps.Core import Coordinate
from functools import partial
import tile_gen.util as u
import tile_gen.config as c

config = None

def set_config(config_d):
    global config
    config = c.build(config_d)

def get_tile(layer, z, x, y, ext, ignore_cached = False):
    if layer not in config.layers and layer != 'all': raise ValueError('Layer not found: ' + layer)

    provider = config.provider
    cache    = config.cache
    layers   = config.layers.values() if layer == 'all' else [config.layers[layer]]
    coord    = Coordinate(y, x, z)
    mimetype, format = u.get_type_by_ext(ext)
    render_tile = partial(provider.render_tile, layers, coord, format)

    if cache:
        cache.lock(layer, coord, format)
        try:
            body = cache.read(layer, coord, format) if not ignore_cached else None

            if body is None:
                body = render_tile()
                cache.save(body, layer, coord, format)
        finally:
            cache.unlock(layer, coord, format)
    else:
        body = render_tile()

    return mimetype, body
