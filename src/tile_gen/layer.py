import tile_gen.util as u

class Layer:
    """ A Layer.

        Attributes:

          queries:
            Required list of Postgres queries, one for each zoom level. The
            last query in the list is repeated for higher zoom levels, and null
            queries indicate an empty response.

            Query must use "__geometry__" for a column name, and must be in
            spherical mercator (900913) projection. A query may include an
            "__id__" column, which will be used as a feature ID in GeoJSON
            instead of a dynamically-generated hash of the geometry. A query
            can additionally be a file name or URL, interpreted relative to
            the location of the TileStache config file.

            If the query contains the token "!bbox!", it will be replaced with
            a constant bounding box geomtry like this:
            "ST_SetSRID(ST_MakeBox2D(ST_MakePoint(x, y), ST_MakePoint(x, y)), <srid>)"

            This behavior is modeled on Mapnik's similar bbox token feature:
            https://github.com/mapnik/mapnik/wiki/PostGIS#bbox-token

          srid:
            Optional numeric SRID used by PostGIS for spherical mercator.
            Default 900913.

          dim:
            Height & width of square tile in pixels, as a single integer.

          clip:
            Optional boolean flag determines whether geometries are clipped to
            tile boundaries or returned in full. Default true: clip geometries.

          simplify:
            Optional floating point number of pixels to simplify all geometries.
            Useful for creating double resolution (retina) tiles set to 0.5, or
            set to 0.0 to prevent any simplification. Default 1.0.

          geometry_types:
            Optional list of geometry types that constrains the results of what
            kind of features are returned.

          transform_fns:
            Optional list of transformation functions. It will be
            passed a shapely object, the properties dictionary, and
            the feature id. The function should return a tuple
            consisting of the new shapely object, properties
            dictionary, and feature id for the feature.

          sort_fn:
            Optional function that will be used to sort features
            fetched from the database.
    """
    def __init__(self, name, queries=[], query_fn=None,
                 srid=3857, dim=256, clip=True, simplify=0.0,
                 geometry_types=None, transform_fns=None, sort_fn=None):

        self.name = name
        self.queries = map(u.read_query, queries)
        self.query_fn = query_fn
        self.srid = int(srid)
        self.dim = dim
        self.clip = clip
        self.simplify = dict(simplify) if isinstance(simplify, list) else float(simplify)
        self.geometry_types = None if geometry_types is None else set(geometry_types)
        self.transform_fn = u.compt(*transform_fns)
        self.sort_fn = sort_fn
