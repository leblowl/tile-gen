from ModestMaps.Core import Coordinate
import tile_gen.util as u
import tile_gen.config as c
import tile_gen.vectiles.provider as provider

config = c.Configuration('tile-gen.cfg')
provider.init(config.dbinfo)

def get_tile(layer, z, x, y, ext, ignore_cached = False):
    if layer not in config.layers and layer != 'all': raise ValueError('Layer not found: ' + layer)

    cache    = config.cache
    # layers   = [config.layers[layer]] if layer != 'all' else config.layers
    coord    = Coordinate(y, x, z)
    mimetype, format = u.get_type_by_ext(ext)

    cache.lock(layer, coord, format)
    try:
        body = cache.read(layer, coord, format) if not ignore_cached else None

        if body is None:
            if layer == 'all':
                body = provider.render_tiles(config.layers.values(), coord, format)
            else:
                body = provider.render_tile(config.layers[layer], coord, format)
            cache.save(body, layer, coord, format)
    finally:
        cache.unlock(layer, coord, format)

    return mimetype, body
