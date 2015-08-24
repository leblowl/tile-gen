''' Provider that returns PostGIS vector tiles in GeoJSON or MVT format.

VecTiles is intended for rendering, and returns tiles with contents simplified,
precision reduced and often clipped.
'''

import json
import shapely.wkb
import tile_gen.util as u
import tile_gen.vectiles.mvt as mvt
import tile_gen.vectiles.geojson as geojson
import tile_gen.vectiles.topojson as topojson
from tile_gen.geography import SphericalMercator
from StringIO import StringIO
from math import pi
from psycopg2.extras import RealDictCursor
from psycopg2 import connect
from ModestMaps.Core import Point

tolerances = [6378137 * 2 * pi / (2 ** (zoom + 8)) for zoom in range(22)]
db = None

def init(dbinfo):
    global db
    conn = connect(**dbinfo)
    conn.set_session(readonly=True, autocommit=True)
    db = conn.cursor(cursor_factory=RealDictCursor)

def tolerance(layer, coord):
    return layer.simplify * tolerances[coord.zoom]

def get_columns(srid, query, bounds):
    ''' Get set of column names for query
    '''

    bbox = 'ST_MakeBox2D(ST_MakePoint(%f, %f), ST_MakePoint(%f, %f))' % bounds
    bbox = 'ST_SetSRID(%s, %d)' % (bbox, srid)

    # newline is important here, to break out of comments.
    db.execute(query.replace('!bbox!', bbox) + '\n LIMIT 0')
    return set(x.name for x in db.description)

def get_features(query, geometry_types, transform_fn, sort_fn):
    features = []

    db.execute(query)
    for row in db.fetchall():
        assert '__geometry__' in row, 'Missing __geometry__ in feature result'
        assert '__id__' in row, 'Missing __id__ in feature result'

        wkb = bytes(row.pop('__geometry__'))
        id = row.pop('__id__')
        shape = shapely.wkb.loads(wkb)

        if geometry_types is not None:
            if shape.type not in geometry_types:
                continue

        props = dict((k, v) for k, v in row.items() if v is not None)

        if transform_fn:
            shape, props, id = transform_fn(shape, props, id)
            wkb = shapely.wkb.dumps(shape)

        features.append((wkb, props, id))

    if sort_fn:
        features = sort_fn(features)

    return features

def build_query(srid, subquery, subcolumns, bounds, tolerance, is_geo, is_clipped, padding=0, scale=None):
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
        simplification_bbox = 'ST_SetSrid(%s, %d)' % (simplification_bbox, srid)

        geom = 'ST_Intersection(%s, %s)' % (geom, simplification_bbox)
        geom = 'ST_MakeValid(ST_SimplifyPreserveTopology(%s, %.12f))' % (geom, tolerance)

        if is_clipped:
            geom = 'ST_Intersection(%s, %s)' % (geom, bbox)

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

def query_features(layer, coord, bounds, format):
    srid = layer.srid
    query = layer.queries[coord.zoom]
    columns = get_columns(srid, query, bounds)
    tolerance = tolerance(layer, coord)
    clip = layer.clip
    mvt_padding = mvt.padding * tolerances[coord.zoom]

    geo_query = build_query(srid, query, columns, bounds, tolerance, True, clip)
    mvt_query = build_query(srid, query, columns, bounds, tolerance, False, clip, mvt_padding, mvt.extents)
    queries = {'JSON':      geo_query,
               'TopoJSON':  geo_query,
               'MVT':       mvt_query}

    geometry_types = layer.geometry_types
    transform_fn = layer.transform_fn
    sort_fn = layer.sort_fn

    return get_features(queries[format], geometry_types, transform_fn, sort_fn)

def encode(out, name, features, coord, bounds, format):
    if format == 'MVT':
        mvt.encode(out, name, features)

    elif format == 'JSON':
        geojson.encode(out, features, coord.zoom)

    elif format == 'TopoJSON':
        ll = SphericalMercator().projLocation(Point(*bounds[0:2]))
        ur = SphericalMercator().projLocation(Point(*bounds[2:4]))
        topojson.encode(out, features, (ll.lon, ll.lat, ur.lon, ur.lat))

    else:
        raise ValueError(format + " is not supported")

def render_tile(layer, coord, format):
    buff = StringIO()
    bounds = u.bounds(layer.projection, coord)
    features = query_features(layer, coord, bounds, format)
    print(features)
    encode(buff, layer.name, features, coord, bounds, format)
    return buff.getvalue()

def merge(out, layers, coord, format):
    names = map(lambda x : x.name, layers)
    tiles = map(u.comp(render_tile, json.loads), layers)

    if format == 'TopoJSON':
        topojson.merge(out, names, tiles)
    elif format == 'JSON':
        geojson.merge(out, names, tiles, coord.zoom)
    elif format == 'MVT':
        feature_layers = []

        for layer in layers:
            bounds = u.bounds(layer.projection, coord)
            features = query_features(layer, coord, bounds, format)

            feature_layers.append({'name': layer.name,
                                   'features': features})
        mvt.merge(out, feature_layers, self.coord)

    else:
        raise ValueError(format + " is not supported for responses with multiple layers")

def render_tiles(layers, coord, format):
    buff = StringIO()
    tile = merge(buff, layers, coord, format)
    return buff.getvalue()

def render_empty_tile(out, format, bounds):
    if format == 'MVT':
        mvt.encode(out, None, [])

    elif format == 'JSON':
        geojson.encode(out, [], 0)

    elif format == 'TopoJSON':
        ll = SphericalMercator().projLocation(Point(*bounds[0:2]))
        ur = SphericalMercator().projLocation(Point(*bounds[2:4]))
        topojson.encode(out, [], (ll.lon, ll.lat, ur.lon, ur.lat))

    else:
        raise ValueError(format + " is not supported")
