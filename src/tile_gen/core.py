""" The core class bits of TileStache.

Two important classes can be found here.

Layer represents a set of tiles in TileStache. It keeps references to
providers, projections, a Configuration instance, and other details required
for to the storage and rendering of a tile set. Layers are represented in the
configuration file as a dictionary:

    {
      "cache": ...,
      "layers":
      {
        "example-name":
        {
          "provider": { ... },
          "preview": { ... },
          "projection": ...,
          "stale lock timeout": ...,
          "cache lifespan": ...,
          "write cache": ...,
          "maximum cache age": ...,
          "tile height": ...
        }
      }
    }

- "provider" refers to a Provider, explained in detail in TileStache.Providers.
- "preview" optionally overrides the starting point for the built-in per-layer
  slippy map preview, useful for image-based layers where appropriate.
  See below for more information on the preview.
- "projection" names a geographic projection, explained in TileStache.Geography.
  If omitted, defaults to spherical mercator.
- "stale lock timeout" is an optional number of seconds to wait before forcing
  a lock that might be stuck. This is defined on a per-layer basis, rather than
  for an entire cache at one time, because you may have different expectations
  for the rendering speeds of different layer configurations. Defaults to 15.
- "cache lifespan" is an optional number of seconds that cached tiles should
  be stored. This is defined on a per-layer basis. Defaults to forever if None,
  0 or omitted.
- "write cache" is an optional boolean value to allow skipping cache write
  altogether. This is defined on a per-layer basis. Defaults to true if omitted.
- "maximum cache age" is an optional number of seconds used to control behavior
  of downstream caches. Causes TileStache responses to include Cache-Control
  and Expires HTTP response headers. Useful when TileStache is itself hosted
  behind an HTTP cache such as Squid, Cloudfront, or Akamai.
- "tile height" gives the height of the image tile in pixels. You almost always
  want to leave this at the default value of 256, but you can use a value of 512
  to create double-size, double-resolution tiles for high-density phone screens.
"""

import logging
from StringIO import StringIO
from urlparse import urljoin
from time import time
from PIL import Image
from ModestMaps.Core import Coordinate

_recent_tiles = dict(hash={}, list=[])

def _addRecentTile(layer, coord, format, body, age=300):
    """ Add the body of a tile to _recent_tiles with a timeout.
    """
    key = (layer, coord, format)
    due = time() + age

    _recent_tiles['hash'][key] = body, due
    _recent_tiles['list'].append((key, due))

    logging.debug('TileStache.Core._addRecentTile() added tile to recent tiles: %s', key)

    # now look at the oldest keys and remove them if needed
    for (key, due_by) in _recent_tiles['list']:
        # new enough?
        if time() < due_by:
            break

        logging.debug('TileStache.Core._addRecentTile() removed tile from recent tiles: %s', key)

        try:
            _recent_tiles['list'].remove((key, due_by))
        except ValueError:
            pass

        try:
            del _recent_tiles['hash'][key]
        except KeyError:
            pass

def _getRecentTile(layer, coord, format):
    """ Return the body of a recent tile, or None if it's not there.
    """
    key = (layer, coord, format)
    body, use_by = _recent_tiles['hash'].get(key, (None, 0))

    # non-existent?
    if body is None:
        return None

    # new enough?
    if time() < use_by:
        logging.debug('TileStache.Core._addRecentTile() found tile in recent tiles: %s', key)
        return body

    # too old
    try:
        del _recent_tiles['hash'][key]
    except KeyError:
        pass

    return None

class Layer:
    """ A Layer.

        Required attributes:

          provider:
            Render provider, see Providers module.

          config:
            Configuration instance, see Config module.

          projection:
            Geographic projection, see Geography module.

        Optional attributes:

          stale_lock_timeout:
            Number of seconds until a cache lock is forced, default 15.

          cache_lifespan:
            Number of seconds that cached tiles should be stored, default 15.

          write_cache:
            Allow skipping cache write altogether, default true.

          max_cache_age:
            Number of seconds that tiles from this layer may be cached by downstream clients.

          dim:
            Height & width of square tile in pixels, as a single integer.
    """
    def __init__(self, config, projection, cache_lifespan=None, stale_lock_timeout=15, write_cache=True, max_cache_age=None, dim=256):
        self.provider = None
        self.config = config
        self.projection = projection
        self.cache_lifespan = cache_lifespan
        self.stale_lock_timeout = stale_lock_timeout
        self.write_cache = write_cache
        self.max_cache_age = max_cache_age
        self.dim = dim

    def name(self):
        """ Figure out what I'm called, return a name if there is one.

            Layer names are stored in the Configuration object, so
            config.layers must be inspected to find a matching name.
        """
        for (name, layer) in self.config.layers.items():
            if layer is self:
                return name

        return None

    def get_tile(self, coord, extension, ignore_cached=False, suppress_cache_write=False):
        """ Get type and tile binary for a given request layer tile.

            Arguments:
            - coord: one ModestMaps.Core.Coordinate corresponding to a single tile.
            - extension: filename extension to choose response type, e.g. "mvt"".
            - ignore_cached: always re-render the tile, whether it's in the cache or not.
            - suppress_cache_write: don't save the tile to the cache
        """

        start_time = time()
        cache = self.config.cache
        mimetype, format = self.getTypeByExtension(extension)

        if ignore_cached:
            body = _getRecentTile(self, coord, format)
            orig = 'recent'
        else:
            try:
                body = cache.read(self, coord, format)
            except TheTileLeftANote, e:
                body = e.content
            orig = 'cache'

        if body is None:
            try:
                if (not suppress_cache_write) and self.write_cache:
                    # We may need to write a new tile, so acquire a lock.
                    cache.lock(self, coord, format)

                if not ignore_cached:
                    # There's a chance that some other process has
                    # written the tile while the lock was being acquired.
                    body = cache.read(self, coord, format)
                    orig = 'cache'

                if body is None:
                    buff = StringIO()

                    try:
                        tile = self.render(coord, format)
                        save = True
                    except NoTileLeftBehind, e:
                        tile = e.tile
                        save = False

                    if suppress_cache_write or (not self.write_cache):
                        save = False

                    save_kwargs = {}

                    tile.save(buff, format, **save_kwargs)
                    body = buff.getvalue()

                    if save: cache.save(body, self, coord, format)
                    orig = 'rendered'

            except TheTileLeftANote, e:
                body = e.content

            finally:
                cache.unlock(self, coord, format)

        _addRecentTile(self, coord, format, body)
        logging.info('TileStache.Core.Layer.getTileResponse() %s/%d/%d/%d.%s via %s in %.3f',
                     self.name(), coord.zoom, coord.column, coord.row, extension, orig, time() - start_time)

        return mimetype, body

    def render(self, coord, format):
        """ Render a tile for a coordinate, return PIL Image-like object.
        """
        srs = self.projection.srs
        width, height = self.dim, self.dim
        provider = self.provider

        if hasattr(provider, 'renderTile'):
            tile = provider.renderTile(width, height, srs, coord)
        else:
            raise Exception('Provider missing renderTile method.')

        if not hasattr(tile, 'save'):
            raise Exception('Tile missing save method.')

        if hasattr(tile, 'size') and tile.size[1] != height:
            raise Exception('Your provider returned the wrong image size: %s instead of %d pixels tall.' % (repr(tile.size), self.dim))

        return tile

    def envelope(self, coord):
        """ Projected rendering envelope (xmin, ymin, xmax, ymax) for a Coordinate.
        """
        ul = self.projection.coordinateProj(coord)
        lr = self.projection.coordinateProj(coord.down().right())

        return min(ul.x, lr.x), min(ul.y, lr.y), max(ul.x, lr.x), max(ul.y, lr.y)

    def getTypeByExtension(self, extension):
        """ Get mime-type and PIL format by file extension.
        """
        if hasattr(self.provider, 'getTypeByExtension'):
            return self.provider.getTypeByExtension(extension)
        else:
            raise Exception('Unknown extension in configuration: "%s"' % extension)

class NoTileLeftBehind(Exception):
    """ Leave no tile in the cache.

        This exception can be thrown in a provider to signal to
        TileStache.getTile() that the result tile should be returned,
        but not saved in a cache. Useful in cases where a full tileset
        is being rendered for static hosting, and you don't want millions
        of identical ocean tiles.

        The one constructor argument is an instance of PIL.Image or
        some other object with a save() method, as would be returned
        by provider renderArea() or renderTile() methods.
    """
    def __init__(self, tile):
        self.tile = tile
        Exception.__init__(self, tile)

class TheTileLeftANote(Exception):
    """ A tile exists, but it shouldn't be returned to the client. Headers
        and/or a status code are provided in its stead.

        This exception can be thrown in a provider or a cache to signal to
        upstream servers where a tile can be found or to clients that a tile
        is empty (or solid).
    """
    def __init__(self, headers=None, status_code=200, content='', emit_content_type=True):
        self.headers = headers
        self.status_code = status_code
        self.content = content
        self.emit_content_type = bool(emit_content_type)

        Exception.__init__(self, self.headers, self.status_code,
                           self.content, self.emit_content_type)
