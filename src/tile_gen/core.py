from ModestMaps.Core import Coordinate
from functools import partial
import tile_gen.util as u
import tile_gen.config as c

env = None

def init_env(config_d):
    global env
    env = c.Config(config_d)

def get_tile(layer, z, x, y, ext, ignore_cached = False):
    if layer not in env.layers and layer != 'all': raise ValueError('Layer not found: ' + layer)

    provider = env.provider
    cache    = env.cache
    layers   = env.layers.values() if layer == 'all' else [env.layers[layer]]
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

def query(layer, z, x, y, ext):
    layer = env.layers[layer]
    coord = Coordinate(y, x, z)
    bounds = u.bounds(layer.projection, coord)
    mimetype, format = u.get_type_by_ext(ext)

    return env.provider.get_features(layer, coord, bounds, format)

def get_query(layer, z, x, y, ext):
    layer = env.layers[layer]
    coord = Coordinate(y, x, z)
    bounds = u.bounds(layer.projection, coord)
    mimetype, format = u.get_type_by_ext(ext)

    return env.provider.get_query(layer, coord, bounds, format)

def explain_analyze_query(layer, z, x, y, ext):
    query = 'explain analyze ' + get_query(layer, z, x, y, ext)
