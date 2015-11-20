import tile_gen.util as u

class Layer:
    """ A Layer.

        Attributes:

          queries:
            Required list of Postgres queries, one for each zoom level. The
            last query in the list is repeated for higher zoom levels, and null
            queries indicate an empty response.

            Query must use "__geometry__" for a column name. A query may include an
            "__id__" column, which will be used as a feature ID in GeoJSON
            instead of a dynamically-generated hash of the geometry.

          query-fn:
            A function of zoom level that returns a query

          srid:
            Optional numeric SRID used by PostGIS.
            Default 3857.

          dim:
            Height & width of square tile in pixels, as a single integer.

          clip:
            Optional boolean flag determines whether geometries are clipped to
            tile boundaries or returned in full. Default true: clip geometries.

          simplify:
            Optional tolerance(s) for simplifying geometries with PostGIS's
            ST_SimplifyPreserveTopology. Accepts float or array
            of key-value pairs, ex: [[1, 50], [4, 25]], where the keys indicate
            the zoom levels and the values indicate tolerances.
            If a key isn't present, it will search
            for one lesser than or equal to the zoom level requested. If a float
            is supplied, it will use that tolerance for all zoom levels.
            Default: 0.0.

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
