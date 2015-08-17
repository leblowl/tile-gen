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

import tile_gen.util as u
import tile_gen.geography as geo

def make_transform_fn(transform_fns):
    if not transform_fns:
        return None

    def transform_fn(shape, properties, fid):
        for fn in transform_fns:
            shape, properties, fid = fn(shape, properties, fid)
        return shape, properties, fid
    return transform_fn

def resolve_transform_fns(fn_dotted_names):
    if not fn_dotted_names:
        return None
    return map(u.load_class_path, fn_dotted_names)

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
    def __init__(self, name, projection='spherical mercator', queries=[],
                 srid=900913, dim=256, clip=True, simplify=1.0,
                 geometry_types=None, transform_fns=None, sort_fn=None):

        self.name = name
        self.projection = geo.getProjectionByName(projection)
        self.queries = []
        self.columns = {}
        for query in queries:
            if query:
                try:
                    query = u.open(query).read()
                except IOError:
                    pass

            self.queries.append(query)

        self.srid = int(srid)
        self.dim = dim
        self.clip = clip
        self.simplify = float(simplify)
        self.geometry_types = None if geometry_types is None else set(geometry_types)
        self.transform_fn_names = transform_fns
        self.transform_fn = make_transform_fn(resolve_transform_fns(transform_fns))
        if sort_fn:
            self.sort_fn_name = sort_fn
            self.sort_fn = u.load_class_path(sort_fn)
        else:
            self.sort_fn_name = None
            self.sort_fn = None
