"""
A layer represents a set of tiles:

    {
      "cache": ...,
      "layers":
      {
        "example-layer-name":
        {
          "projection": ...,
          "tile height": ...
        }
      }
    }

- "projection" names a geographic projection, explained in TileStache.Geography.
  If omitted, defaults to spherical mercator.
- "tile height" gives the height of the image tile in pixels. You almost always
  want to leave this at the default value of 256, but you can use a value of 512
  to create double-size, double-resolution tiles for high-density phone screens.
"""

class Layer:
    """ A Layer.

        Required attributes:

          config:
            Configuration instance, see Config module.

          projection:
            Geographic projection, see Geography module.

        Optional attributes:

          write_cache:
            Allow skipping cache write altogether, default true.

          dim:
            Height & width of square tile in pixels, as a single integer.
    """
    def __init__(self, config, projection, dim=256):
        self.config = config
        self.projection = projection
        self.dim = dim

    def name(self):
        for (name, layer) in self.config.layers.items():
            if layer is self:
                return name

        return None
