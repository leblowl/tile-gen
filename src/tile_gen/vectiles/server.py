''' Provider that returns PostGIS vector tiles in GeoJSON or MVT format.

VecTiles is intended for rendering, and returns tiles with contents simplified,
precision reduced and often clipped.
'''

import json
import tile_gen.util as u
import tile_gen.vectiles.mvt as mvt
import tile_gen.vectiles.geojson as geojson
import tile_gen.vectiles.topojson as topojson
from math import pi
from urlparse import urljoin, urlparse
from urllib import urlopen
from os.path import exists
from shapely.wkb import dumps
from shapely.wkb import loads
from psycopg2.extras import RealDictCursor
from psycopg2 import connect
from psycopg2.extensions import TransactionRollbackError
from ModestMaps.Core import Point
from tile_gen.geography import SphericalMercator

tolerances = [6378137 * 2 * pi / (2 ** (zoom + 8)) for zoom in range(22)]

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

def query_columns(dbinfo, srid, query, bounds):
    ''' Get set of column names for query
    '''
    with Connection(dbinfo) as db:
        bbox = 'ST_MakeBox2D(ST_MakePoint(%f, %f), ST_MakePoint(%f, %f))' % bounds
        bbox = 'ST_SetSRID(%s, %d)' % (bbox, srid)

        # newline is important here, to break out of comments.
        db.execute(query.replace('!bbox!', bbox) + '\n LIMIT 0')
        return set(x.name for x in db.description)

def get_features(dbinfo, query, geometry_types, transform_fn, sort_fn):
    features = []

    with Connection(dbinfo) as db:
        db.execute(query)
        for row in db.fetchall():
            assert '__geometry__' in row, 'Missing __geometry__ in feature result'
            assert '__id__' in row, 'Missing __id__ in feature result'

            wkb = bytes(row.pop('__geometry__'))
            id = row.pop('__id__')
            shape = loads(wkb)

            if geometry_types is not None:
                if shape.type not in geometry_types:
                    continue

            props = dict((k, v) for k, v in row.items() if v is not None)

            if transform_fn:
                shape, props, id = transform_fn(shape, props, id)
                wkb = dumps(shape)

            features.append((wkb, props, id))

    if sort_fn:
        features = sort_fn(features)

    return features

def build_query(srid, subquery, subcolumns, bounds, tolerance, is_geo, is_clipped, padding=0, scale=None, simplify_before_intersect=False):
    ''' Build and return an PostGIS query.
    '''

    # bounds argument is a 4-tuple with (xmin, ymin, xmax, ymax).
    bbox = 'ST_MakeBox2D(ST_MakePoint(%.12f, %.12f), ST_MakePoint(%.12f, %.12f))' % (bounds[0] - padding, bounds[1] - padding, bounds[2] + padding, bounds[3] + padding)
    bbox = 'ST_SetSRID(%s, %d)' % (bbox, srid)
    geom = 'q.__geometry__'

    # To get around this, for any given tile bounding box, we find the
    # contained/overlapping geometries and simplify them BEFORE
    # cutting out the precise tile bounding bbox (instead of cutting out the
    # tile and then simplifying everything inside of it, as we do with all of
    # the other layers).

    if simplify_before_intersect:
        # Simplify, then cut tile.

        if tolerance is not None:
            # The problem with simplifying all contained/overlapping geometries
            # for a tile before cutting out the parts that actually lie inside
            # of it is that we might end up simplifying a massive geometry just
            # to extract a small portion of it (think simplifying the border of
            # the US just to extract the New York City coastline). To reduce the
            # performance hit, we actually identify all of the candidate
            # geometries, then cut out a bounding box *slightly larger* than the
            # tile bbox, THEN simplify, and only then cut out the tile itself.
            # This still allows us to perform simplification of the geometry
            # edges outside of the tile, which prevents any seams from forming
            # when we cut it out, but means that we don't have to simplify the
            # entire geometry (just the small bits lying right outside the
            # desired tile).

            simplification_padding = padding + (bounds[3] - bounds[1]) * 0.1
            simplification_bbox = (
                'ST_MakeBox2D(ST_MakePoint(%.12f, %.12f), '
                'ST_MakePoint(%.12f, %.12f))' % (
                    bounds[0] - simplification_padding,
                    bounds[1] - simplification_padding,
                    bounds[2] + simplification_padding,
                    bounds[3] + simplification_padding))
            simplification_bbox = 'ST_SetSrid(%s, %d)' % (
                simplification_bbox, srid)

            geom = 'ST_Intersection(%s, %s)' % (geom, simplification_bbox)
            geom = 'ST_MakeValid(ST_SimplifyPreserveTopology(%s, %.12f))' % (
                geom, tolerance)

        assert is_clipped, 'If simplify_before_intersect=True, ' \
            'is_clipped should be True as well'
        geom = 'ST_Intersection(%s, %s)' % (geom, bbox)

    else:
        # Cut tile, then simplify.

        if is_clipped:
            geom = 'ST_Intersection(%s, %s)' % (geom, bbox)

        if tolerance is not None:
            geom = 'ST_SimplifyPreserveTopology(%s, %.12f)' % (geom, tolerance)

    if is_geo:
        geom = 'ST_Transform(%s, 4326)' % geom

    if scale:
        # scale applies to the un-padded bounds, e.g. geometry in the padding area "spills over" past the scale range
        geom = ('ST_TransScale(%s, %.12f, %.12f, %.12f, %.12f)'
                % (geom, -bounds[0], -bounds[1],
                   scale / (bounds[2] - bounds[0]),
                   scale / (bounds[3] - bounds[1])))

    subquery = subquery.replace('!bbox!', bbox)
    columns = ['q."%s"' % c for c in subcolumns if c not in ('__geometry__', )]

    if '__geometry__' not in subcolumns:
        raise Exception("There's supposed to be a __geometry__ column.")

    if '__id__' not in subcolumns:
        columns.append('Substr(MD5(ST_AsBinary(q.__geometry__)), 1, 10) AS __id__')

    columns = ', '.join(columns)

    return '''SELECT %(columns)s,
                     ST_AsBinary(%(geom)s) AS __geometry__
              FROM (
                %(subquery)s
                ) AS q
              WHERE ST_IsValid(q.__geometry__)
                AND ST_Intersects(q.__geometry__, %(bbox)s)''' \
            % locals()

class Connection:
    ''' Context manager for Postgres connections.
    '''
    def __init__(self, dbinfo):
        self.dbinfo = dbinfo

    def __enter__(self):
        conn = connect(**self.dbinfo)
        conn.set_session(readonly=True, autocommit=True)
        self.db = conn.cursor(cursor_factory=RealDictCursor)
        return self.db

    def __exit__(self, type, value, traceback):
        self.db.connection.close()

class EmptyResponse:
    def __init__(self, bounds):
        self.bounds = bounds

    def save(self, out, format):
        if format == 'MVT':
            mvt.encode(out, [], None)

        elif format == 'JSON':
            geojson.encode(out, [], 0)

        elif format == 'TopoJSON':
            ll = SphericalMercator().projLocation(Point(*self.bounds[0:2]))
            ur = SphericalMercator().projLocation(Point(*self.bounds[2:4]))
            topojson.encode(out, [], (ll.lon, ll.lat, ur.lon, ur.lat))

        else:
            raise ValueError(format + " is not supported")

class Response:
    def __init__(self, dbinfo, layer, query, columns, bounds, tolerance, coord):
        self.dbinfo = dbinfo
        self.bounds = bounds
        self.coord = coord
        self.zoom = coord.zoom
        self.layer_name = layer.name
        self.geometry_types = layer.geometry_types
        self.transform_fn = layer.transform_fn
        self.sort_fn = layer.sort_fn

        srid = layer.srid
        clip = layer.clip
        simplify_before_intersect = layer.simplify_before_intersect

        geo_query = build_query(srid, query, columns, bounds, tolerance, True, clip, simplify_before_intersect=simplify_before_intersect)
        mvt_query = build_query(srid, query, columns, bounds, tolerance, False, clip, mvt.padding * tolerances[coord.zoom], mvt.extents, simplify_before_intersect=simplify_before_intersect)
        self.query = dict(TopoJSON=geo_query, JSON=geo_query, MVT=mvt_query)

    def save(self, out, format):
        features = get_features(self.dbinfo, self.query[format], self.geometry_types, self.transform_fn, self.sort_fn)

        if format == 'MVT':
            mvt.encode(out, features, self.coord, self.layer_name)

        elif format == 'JSON':
            geojson.encode(out, features, self.zoom)

        elif format == 'TopoJSON':
            ll = SphericalMercator().projLocation(Point(*self.bounds[0:2]))
            ur = SphericalMercator().projLocation(Point(*self.bounds[2:4]))
            topojson.encode(out, features, (ll.lon, ll.lat, ur.lon, ur.lat))

        else:
            raise ValueError(format + " is not supported")

class MultiResponse:
    def __init__(self, config, names, coord, ignore_cached_sublayers):
        self.config = config
        self.names = names
        self.coord = coord
        self.ignore_cached_sublayers = ignore_cached_sublayers

    def save(self, out, format):
        if format == 'TopoJSON':
            topojson.merge(out, self.names, self.get_tiles(format), self.config, self.coord)

        elif format == 'JSON':
            geojson.merge(out, self.names, self.get_tiles(format), self.config, self.coord)

        elif format == 'MVT':
            feature_layers = []
            layers = [self.config.layers[name] for name in self.names]
            for layer in layers:
                width, height = layer.dim, layer.dim
                tile = layer.provider.renderTile(width, height, layer.projection.srs, self.coord)
                if isinstance(tile,EmptyResponse): continue
                feature_layers.append({'name': layer.name, 'features': get_features(tile.dbinfo, tile.query["MVT"], layer.provider.geometry_types, layer.provider.transform_fn, layer.provider.sort_fn)})
            mvt.merge(out, feature_layers, self.coord)

        else:
            raise ValueError(format + " is not supported for responses with multiple layers")

    def get_tiles(self, format):
        unknown_layers = set(self.names) - set(self.config.layers.keys())

        if unknown_layers:
            raise Exception("%s.get_tiles didn't recognize %s when trying to load %s." % (__name__, ', '.join(unknown_layers), ', '.join(self.names)))

        layers = [self.config.layers[name] for name in self.names]
        mimes, bodies = zip(*[getTile(layer, self.coord, format.lower(), self.ignore_cached_sublayers, self.ignore_cached_sublayers) for layer in layers])
        bad_mimes = [(name, mime) for (mime, name) in zip(mimes, self.names) if not mime.endswith('/json')]

        if bad_mimes:
            raise Exception('%s.get_tiles encountered a non-JSON mime-type in %s sub-layer: "%s"' % ((__name__, ) + bad_mimes[0]))

        tiles = map(json.loads, bodies)
        bad_types = [(name, topo['type']) for (topo, name) in zip(tiles, self.names) if topo['type'] != ('FeatureCollection' if (format.lower()=='json') else 'Topology')]

        if bad_types:
            raise Exception('%s.get_tiles encountered a non-%sCollection type in %s sub-layer: "%s"' % ((__name__, ('Feature' if (format.lower()=='json') else 'Topology'), ) + bad_types[0]))

        return tiles


class Provider:
    ''' VecTiles provider for PostGIS data sources.

        Parameters:

          dbinfo:
            Required dictionary of Postgres connection parameters. Should
            include some combination of 'host', 'user', 'password', and 'database'.

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

          clip:
            Optional boolean flag determines whether geometries are clipped to
            tile boundaries or returned in full. Default true: clip geometries.

          srid:
            Optional numeric SRID used by PostGIS for spherical mercator.
            Default 900913.

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
    '''

    def __init__(self, dbinfo):
        self.dbinfo = dbinfo

    def render_tile(self, layer, coord):
        ll = layer.projection.coordinateProj(coord.down())
        ur = layer.projection.coordinateProj(coord.right())
        bounds = ll.x, ll.y, ur.x, ur.y
        tolerance = layer.simplify * tolerances[coord.zoom]
        query = layer.queries[coord.zoom]

        if not query: return EmptyResponse(bounds)

        if query not in layer.columns:
            layer.columns[query] = query_columns(self.dbinfo, layer.srid, query, bounds)

        return Response(self.dbinfo, layer, query, layer.columns[query], bounds, tolerance, coord)

class MultiProvider:
    ''' VecTiles provider to gather PostGIS tiles into a single multi-response.

        Returns a MultiResponse object for GeoJSON or TopoJSON requests.

        names:
          List of names of vector-generating layers from elsewhere in config.

        ignore_cached_sublayers:
          True if cache provider should not save intermediate layers
          in cache.
    '''
    def __init__(self, layer, names, ignore_cached_sublayers=False):
        self.layer = layer
        self.names = names
        self.ignore_cached_sublayers = ignore_cached_sublayers

    def __call__(self, layer, names, ignore_cached_sublayers=False):
        self.layer = layer
        self.names = names
        self.ignore_cached_sublayers = ignore_cached_sublayers

    def render_tile(self, layer, coord):
        return MultiResponse(layer.config, self.names, coord, self.ignore_cached_sublayers)
