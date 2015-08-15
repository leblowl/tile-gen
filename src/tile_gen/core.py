from StringIO import StringIO

def render(provider, layer, coord, format):
    """ Render a tile for a coordinate.
    """
    srs = layer.projection.srs
    tile = provider.renderTile(layer.dim, layer.dim, srs, coord)
    return tile

def get_tile(layer, coord, extension, ignore_cached=False):
    """ Get type and tile binary for a given request layer tile.

    Arguments:
    - coord: one ModestMaps.Core.Coordinate corresponding to a single tile.
    - extension: filename extension to choose response type, e.g. "mvt"".
    - ignore_cached: always re-render the tile, whether it's in the cache or not.
    """

    cache = layer.config.cache
    provider = tile_gen.vectiles.server.Provider()
    mimetype, format = provider.getTypeByExtension(extension)

    cache.lock(layer, coord, format)
    body = cache.read(layer, coord, format) if not ignore_cached else None

    if body is None:
        buff = StringIO()
        tile = render(coord, format)
        tile.save(buff, format)
        cache.save(buff.getvalue(), layer, coord, format)

    cache.unlock(layer, coord, format)
    return mimetype, body

def get_tile(coord, extension, ignore_cached=False):
    return get_tile('all', coord, extension, ignore_cached)
