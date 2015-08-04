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
          "metatile": { ... },
          "preview": { ... },
          "projection": ...,
          "stale lock timeout": ...,
          "cache lifespan": ...,
          "write cache": ...,
          "bounds": { ... },
          "maximum cache age": ...,
          "tile height": ...
        }
      }
    }

- "provider" refers to a Provider, explained in detail in TileStache.Providers.
- "metatile" optionally makes it possible for multiple individual tiles to be
  rendered at one time, for greater speed and efficiency. This is commonly used
  for the Mapnik provider. See below for more information on metatiles.
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
- "bounds" is an optional dictionary of six tile boundaries to limit the
  rendered area: low (lowest zoom level), high (highest zoom level), north,
  west, south, and east (all in degrees).
- "maximum cache age" is an optional number of seconds used to control behavior
  of downstream caches. Causes TileStache responses to include Cache-Control
  and Expires HTTP response headers. Useful when TileStache is itself hosted
  behind an HTTP cache such as Squid, Cloudfront, or Akamai.
- "tile height" gives the height of the image tile in pixels. You almost always
  want to leave this at the default value of 256, but you can use a value of 512
  to create double-size, double-resolution tiles for high-density phone screens.

Sample bounds:

    {
        "low": 9, "high": 15,
        "south": 37.749, "west": -122.358,
        "north": 37.860, "east": -122.113
    }

Metatile represents a larger area to be rendered at one time. Metatiles are
represented in the configuration file as a dictionary:

    {
      "rows": 4,
      "columns": 4,
      "buffer": 64
    }

- "rows" and "columns" are the height and width of the metatile measured in
  tiles. This example metatile is four rows tall and four columns wide, so it
  will render sixteen tiles simultaneously.
- "buffer" is a buffer area around the metatile, measured in pixels. This is
  useful for providers with labels or icons, where it's necessary to draw a
  bit extra around the edges to ensure that text is not cut off. This example
  metatile has a buffer of 64 pixels, so the resulting metatile will be 1152
  pixels square: 4 rows x 256 pixels + 2 x 64 pixel buffer.
"""

import logging
from StringIO import StringIO
from urlparse import urljoin
from time import time
import Image
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

class Metatile:
    """ Some basic characteristics of a metatile.

        Properties:
        - rows: number of tile rows this metatile covers vertically.
        - columns: number of tile columns this metatile covers horizontally.
        - buffer: pixel width of outer edge.
    """
    def __init__(self, buffer=0, rows=1, columns=1):
        assert rows >= 1
        assert columns >= 1
        assert buffer >= 0

        self.rows = rows
        self.columns = columns
        self.buffer = buffer

    def isForReal(self):
        """ Return True if this is really a metatile with a buffer or multiple tiles.

            A default 1x1 metatile with buffer=0 is not for real.
        """
        return self.buffer > 0 or self.rows > 1 or self.columns > 1

    def firstCoord(self, coord):
        """ Return a new coordinate for the upper-left corner of a metatile.

            This is useful as a predictable way to refer to an entire metatile
            by one of its sub-tiles, currently needed to do locking correctly.
        """
        return self.allCoords(coord)[0]

    def allCoords(self, coord):
        """ Return a list of coordinates for a complete metatile.

            Results are guaranteed to be ordered left-to-right, top-to-bottom.
        """
        rows, columns = int(self.rows), int(self.columns)

        # upper-left corner of coord's metatile
        row = rows * (int(coord.row) / rows)
        column = columns * (int(coord.column) / columns)

        coords = []

        for r in range(rows):
            for c in range(columns):
                coords.append(Coordinate(row + r, column + c, coord.zoom))

        return coords

class Layer:
    """ A Layer.

        Required attributes:

          provider:
            Render provider, see Providers module.

          config:
            Configuration instance, see Config module.

          projection:
            Geographic projection, see Geography module.

          metatile:
            Some information for drawing many tiles at once.

        Optional attributes:

          stale_lock_timeout:
            Number of seconds until a cache lock is forced, default 15.

          cache_lifespan:
            Number of seconds that cached tiles should be stored, default 15.

          write_cache:
            Allow skipping cache write altogether, default true.

          bounds:
            Instance of Config.Bounds for limiting rendered tiles.

          max_cache_age:
            Number of seconds that tiles from this layer may be cached by downstream clients.

          tile_height:
            Height of tile in pixels, as a single integer. Tiles are generally
            assumed to be square, and Layer.render() will respond with an error
            if the rendered image is not this height.
    """
    def __init__(self, config, projection, metatile, cache_lifespan=None, stale_lock_timeout=15, write_cache=True, max_cache_age=None, bounds=None, tile_height=256):
        self.provider = None
        self.config = config
        self.projection = projection
        self.metatile = metatile
        self.stale_lock_timeout = stale_lock_timeout
        self.cache_lifespan = cache_lifespan
        self.write_cache = write_cache
        self.max_cache_age = max_cache_age
        self.bounds = bounds
        self.dim = tile_height

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
                lockCoord = None

                if (not suppress_cache_write) and self.write_cache:
                    # We may need to write a new tile, so acquire a lock.
                    lockCoord = self.metatile.firstCoord(coord)
                    cache.lock(self, lockCoord, format)

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
                if lockCoord:
                    # Always clean up a lock when it's no longer being used.
                    cache.unlock(self, lockCoord, format)

        _addRecentTile(self, coord, format, body)
        logging.info('TileStache.Core.Layer.getTileResponse() %s/%d/%d/%d.%s via %s in %.3f',
                     self.name(), coord.zoom, coord.column, coord.row, extension, orig, time() - start_time)

        return mimetype, body

    def doMetatile(self):
        """ Return True if we have a real metatile and the provider is OK with it.
        """
        return self.metatile.isForReal() and hasattr(self.provider, 'renderArea')

    def render(self, coord, format):
        """ Render a tile for a coordinate, return PIL Image-like object.

            Perform metatile slicing here as well, if required, writing the
            full set of rendered tiles to cache as we go.

            Note that metatiling and pass-through mode of a Provider
            are mutually exclusive options
        """
        if self.bounds and self.bounds.excludes(coord):
            raise NoTileLeftBehind(Image.new('RGB', (self.dim, self.dim), (0x99, 0x99, 0x99)))

        srs = self.projection.srs
        xmin, ymin, xmax, ymax = self.envelope(coord)
        width, height = self.dim, self.dim

        provider = self.provider
        metatile = self.metatile
        pass_through = provider.pass_through if hasattr(provider, 'pass_through') else False


        if self.doMetatile():

            if pass_through:
                raise KnownUnknown('Your provider is configured for metatiling and pass_through mode. That does not work')

            # adjust render size and coverage for metatile
            xmin, ymin, xmax, ymax = self.metaEnvelope(coord)
            width, height = self.metaSize(coord)

            subtiles = self.metaSubtiles(coord)

        if self.doMetatile() or hasattr(provider, 'renderArea'):
            # draw an area, defined in projected coordinates
            tile = provider.renderArea(width, height, srs, xmin, ymin, xmax, ymax, coord.zoom)

        elif hasattr(provider, 'renderTile'):
            # draw a single tile
            width, height = self.dim, self.dim
            tile = provider.renderTile(width, height, srs, coord)

        else:
            raise KnownUnknown('Your provider lacks renderTile and renderArea methods.')

        if not hasattr(tile, 'save'):
            raise KnownUnknown('Return value of provider.renderArea() must act like an image; e.g. have a "save" method.')

        if hasattr(tile, 'size') and tile.size[1] != height:
            raise KnownUnknown('Your provider returned the wrong image size: %s instead of %d pixels tall.' % (repr(tile.size), self.dim))

        if self.doMetatile():
            # tile will be set again later
            tile, surtile = None, tile

            for (other, x, y) in subtiles:
                buff = StringIO()
                bbox = (x, y, x + self.dim, y + self.dim)
                subtile = surtile.crop(bbox)
                subtile.save(buff, format)
                body = buff.getvalue()

                if self.write_cache:
                    self.config.cache.save(body, self, other, format)

                if other == coord:
                    # the one that actually gets returned
                    tile = subtile

                _addRecentTile(self, other, format, body)

        return tile

    def envelope(self, coord):
        """ Projected rendering envelope (xmin, ymin, xmax, ymax) for a Coordinate.
        """
        ul = self.projection.coordinateProj(coord)
        lr = self.projection.coordinateProj(coord.down().right())

        return min(ul.x, lr.x), min(ul.y, lr.y), max(ul.x, lr.x), max(ul.y, lr.y)

    def metaEnvelope(self, coord):
        """ Projected rendering envelope (xmin, ymin, xmax, ymax) for a metatile.
        """
        # size of buffer expressed as fraction of tile size
        buffer = float(self.metatile.buffer) / self.dim

        # full set of metatile coordinates
        coords = self.metatile.allCoords(coord)

        # upper-left and lower-right expressed as fractional coordinates
        ul = coords[0].left(buffer).up(buffer)
        lr = coords[-1].right(1 + buffer).down(1 + buffer)

        # upper-left and lower-right expressed as projected coordinates
        ul = self.projection.coordinateProj(ul)
        lr = self.projection.coordinateProj(lr)

        # new render area coverage in projected coordinates
        return min(ul.x, lr.x), min(ul.y, lr.y), max(ul.x, lr.x), max(ul.y, lr.y)

    def metaSize(self, coord):
        """ Pixel width and height of full rendered image for a metatile.
        """
        # size of buffer expressed as fraction of tile size
        buffer = float(self.metatile.buffer) / self.dim

        # new master image render size
        width = int(self.dim * (buffer * 2 + self.metatile.columns))
        height = int(self.dim * (buffer * 2 + self.metatile.rows))

        return width, height

    def metaSubtiles(self, coord):
        """ List of all coords in a metatile and their x, y offsets in a parent image.
        """
        subtiles = []

        coords = self.metatile.allCoords(coord)

        for other in coords:
            r = other.row - coords[0].row
            c = other.column - coords[0].column

            x = c * self.dim + self.metatile.buffer
            y = r * self.dim + self.metatile.buffer

            subtiles.append((other, x, y))

        return subtiles

    def getTypeByExtension(self, extension):
        """ Get mime-type and PIL format by file extension.
        """
        if hasattr(self.provider, 'getTypeByExtension'):
            return self.provider.getTypeByExtension(extension)
        else:
            raise KnownUnknown('Unknown extension in configuration: "%s"' % extension)

class KnownUnknown(Exception):
    """ There are known unknowns. That is to say, there are things that we now know we don't know.

        This exception gets thrown in a couple places where common mistakes are made.
    """
    pass

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
