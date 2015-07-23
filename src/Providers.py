""" The provider bits of TileStache.

A Provider is the part of TileStache that actually renders imagery. A few default
providers are found here, but it's possible to define your own and pull them into
TileStache dynamically by class name.

Built-in providers:
- vector (TileStache.Vector.Provider)

Example built-in provider, for JSON configuration file:

    "layer-name": {
        "provider": {"name": "mapnik", "mapfile": "style.xml"},
        ...
    }

Example external provider, for JSON configuration file:

    "layer-name": {
        "provider": {"class": "Module:Classname", "kwargs": {"frob": "yes"}},
        ...
    }

- The "class" value is split up into module and classname, and dynamically
  included. If this doesn't work for some reason, TileStache will fail loudly
  to let you know.
- The "kwargs" value is fed to the class constructor as a dictionary of keyword
  args. If your defined class doesn't accept any of these keyword arguments,
  TileStache will throw an exception.

A provider must offer one of two methods for rendering map areas.

The renderTile() method draws a single tile at a time, and has these arguments:

- width, height: in pixels
- srs: projection as Proj4 string.
  "+proj=longlat +ellps=WGS84 +datum=WGS84" is an example,
  see http://spatialreference.org for more.
- coord: Coordinate object representing a single tile.

The renderArea() method draws a variably-sized area, and is used when drawing
metatiles. It has these arguments:

- width, height: in pixels
- srs: projection as Proj4 string.
  "+proj=longlat +ellps=WGS84 +datum=WGS84" is an example,
  see http://spatialreference.org for more.
- xmin, ymin, xmax, ymax: coordinates of bounding box in projected coordinates.
- zoom: zoom level of final map. Technically this can be derived from the other
  arguments, but that's a hassle so we'll pass it in explicitly.

A provider may offer a method for custom response type, getTypeByExtension().
This method accepts a single argument, a filename extension string (e.g. "png",
"json", etc.) and returns a tuple with twon strings: a mime-type and a format.
Note that for image and non-image tiles alike, renderArea() and renderTile()
methods on a provider class must return a object with a save() method that
can accept a file-like object and a format name, e.g. this should word:

    provder.renderArea(...).save(fp, "TEXT")

... if "TEXT" is a valid response format according to getTypeByExtension().

Non-image providers and metatiles do not mix.

For an example of a non-image provider, see TileStache.Vector.Provider.
"""

import os
import logging

from StringIO import StringIO
from string import Template
import urllib2
import urllib

try:
    from PIL import Image
except ImportError:
    # On some systems, PIL.Image is known as Image.
    import Image

import ModestMaps
from ModestMaps.Core import Point, Coordinate

import Geography

# This import should happen inside getProviderByName(), but when testing
# on Mac OS X features are missing from output. Wierd-ass C libraries...
try:
    import Vector
except ImportError:
    pass

def getProviderByName(name):
    """ Retrieve a provider object by name.

        Raise an exception if the name doesn't work out.
    """

    if name.lower() == 'vector':
        from . import Vector
        return Vector.Provider

    raise Exception('Unknown provider name: "%s"' % name)

class Verbatim:
    ''' Wrapper for PIL.Image that saves raw input bytes if modes and formats match.
    '''
    def __init__(self, bytes):
        self.buffer = StringIO(bytes)
        self.format = None
        self._image = None

        #
        # Guess image format based on magic number, if possible.
        # http://www.astro.keele.ac.uk/oldusers/rno/Computing/File_magic.html
        #
        magic = {
            '\x89\x50\x4e\x47': 'PNG',
            '\xff\xd8\xff\xe0': 'JPEG',
            '\x47\x49\x46\x38': 'GIF',
            '\x47\x49\x46\x38': 'GIF',
            '\x4d\x4d\x00\x2a': 'TIFF',
            '\x49\x49\x2a\x00': 'TIFF'
            }

        if bytes[:4] in magic:
            self.format = magic[bytes[:4]]

        else:
            self.format = self.image().format

    def image(self):
        ''' Return a guaranteed instance of PIL.Image.
        '''
        if self._image is None:
            self._image = Image.open(self.buffer)

        return self._image

    def convert(self, mode):
        if mode == self.image().mode:
            return self
        else:
            return self.image().convert(mode)

    def crop(self, bbox):
        return self.image().crop(bbox)

    def save(self, output, format):
        if format == self.format:
            output.write(self.buffer.getvalue())
        else:
            self.image().save(output, format)
