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

def get_tolerance(layer, coord):
    return layer.simplify * tolerances[coord.zoom]

def st_bbox(bounds, padding, srid):
    return 'ST_MakeEnvelope({xmin}, {ymin}, {xmax}, {ymax}, {srid})' \
           .format(xmin=bounds[0] - padding,
                   ymin=bounds[1] - padding,
                   xmax=bounds[2] + padding,
                   ymax=bounds[3] + padding,
                   srid=srid)

def build_query(srid, subquery, bounds, tolerance, is_geo, is_clipped, padding=0, scale=None):
    ''' Build and return an PostGIS query.
    '''

    bbox = st_bbox(bounds, padding, srid)
    geom = 'q.__geometry__'

    if tolerance > 0:
        simplification_padding = padding + (bounds[3] - bounds[1]) * 0.1
        simplification_bbox = st_bbox(bounds, simplification_padding, srid)

        geom = 'ST_Intersection(%s, %s)' % (geom, simplification_bbox)
        geom = 'ST_MakeValid(ST_SimplifyPreserveTopology(%s, %.12f))' % (geom, tolerance)

    if is_clipped:
        geom = 'ST_Intersection(%s, %s)' % (geom, bbox)

    if is_geo:
        geom = 'ST_Transform(%s, 4326)' % geom

    if scale:
        # scale applies to the un-padded bounds
        # e.g. geometry in the padding area "spills over" past the scale range
        geom = ('ST_TransScale(%s, %.12f, %.12f, %.12f, %.12f)'
                % (geom, -bounds[0], -bounds[1],
                   scale / (bounds[2] - bounds[0]),
                   scale / (bounds[3] - bounds[1])))

    subquery = subquery.replace('!bbox!', bbox)

    return '''SELECT *, ST_AsBinary(%(geom)s) AS __geometry__
              FROM (%(subquery)s) AS q
              WHERE ST_Intersects(q.__geometry__, %(bbox)s)''' % locals()

def query_features(query, geometry_types, transform_fn, sort_fn):
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

def get_features(layer, coord, bounds, format):
    query = u.xs_get(layer.queries, coord.zoom, layer.queries[-1])
    if not query: return []
    else:
        srid = layer.srid
        tolerance = get_tolerance(layer, coord)
        clip = layer.clip
        mvt_padding = mvt.padding * tolerances[coord.zoom]

        geo_query = build_query(srid, query, bounds, tolerance, True, clip)
        mvt_query = build_query(srid, query, bounds, tolerance, False, clip, mvt_padding, mvt.extents)
        queries = {'JSON': geo_query, 'TopoJSON': geo_query, 'MVT': mvt_query}
        geometry_types = layer.geometry_types
        transform_fn = layer.transform_fn
        sort_fn = layer.sort_fn

        return query_features(queries[format], geometry_types, transform_fn, sort_fn)

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

def merge(out, layers, coord, format):
    if format == 'MVT':
        def get_feature_layer(layer):
            bounds = u.bounds(layer.projection, coord)
            features = get_features(layer, coord, bounds, format)
            return {'name': layer.name, 'features': features}

        mvt.merge(out, map(get_feature_layer, layers))
    else:
        names = map(lambda x : x.name, layers)
        tiles = map(lambda x : json.loads(render_tile(x, coord, format)), layers)

        if format == 'TopoJSON':
            topojson.merge(out, names, tiles)
        elif format == 'JSON':
            geojson.merge(out, names, tiles, coord.zoom)
        else:
            raise ValueError(format + " is not supported for responses with multiple layers")

def render_tile(lols, coord, format):
    buff = StringIO()

    if type(lols) is list:
        merge(buff, lols, coord, format)
    else:
        bounds = u.bounds(lols.projection, coord)
        features = get_features(lols, coord, bounds, format)
        encode(buff, lols.name, features, coord, bounds, format)

    return buff.getvalue()
