"""
A provider is the part that actually does the rendering. A few default
providers are found here, but it's possible to define your own and pull
them in dynamically by class name.

Built-in providers:
- vectiles (tile_gen.vectiles.server.Provider)

Example built-in provider configuration:

    "layer-name": {
        "provider": {"name": "vectiles"},
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

A provider may offer a method for custom response type, getTypeByExtension().
This method accepts a single argument, a filename extension string (e.g. "png",
"json", etc.) and returns a tuple with twon strings: a mime-type and a format.
Note that for image and non-image tiles alike, renderArea() and renderTile()
methods on a provider class must return a object with a save() method that
can accept a file-like object and a format name, e.g. this should word:

    provder.renderArea(...).save(fp, "TEXT")

"""

import tile_gen.vectiles

def get_provider_by_name(name):
    """ Retrieve a provider object by name.

        Raise an exception if the name doesn't work out.
    """

    if name.lower() == 'vectiles':
        return tile_gen.vectiles.server.Provider
    elif name.lower() == 'vectiles_multi':
        return tile_gen.vectiles.server.MultiProvider

    raise Exception('Unknown provider name: "%s"' % name)
