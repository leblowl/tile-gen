import json
import shapely.wkb
import tile_gen.util as u
import tile_gen.vectiles.mvt as mvt
import tile_gen.vectiles.geojson as geojson
from tile_gen.geography import SphericalMercator
from ModestMaps.Core import Coordinate
from StringIO import StringIO
from math import pi
from psycopg2.extras import RealDictCursor
from psycopg2 import connect
from ModestMaps.Core import Point

def get_tolerance(simplify, zoom):
    return (simplify[max(filter(lambda k : k <= zoom, simplify.keys()))]
            if isinstance(simplify, dict) else simplify)

def pad(bounds, padding):
    return (bounds[0] - padding,
            bounds[1] - padding,
            bounds[2] + padding,
            bounds[3] + padding)

def st_bbox(bounds, srid):
    return 'ST_MakeEnvelope({xmin}, {ymin}, {xmax}, {ymax}, {srid})' \
           .format(xmin=bounds[0],
                   ymin=bounds[1],
                   xmax=bounds[2],
                   ymax=bounds[3],
                   srid=srid)

def st_simplify(geom, tolerance, bounds, srid=3857):
    padding = (bounds[3] - bounds[1]) * 0.1
    geom = 'ST_Intersection(%s, %s)' % (geom, st_bbox(pad(bounds, padding), srid))

    return 'ST_MakeValid(ST_SimplifyPreserveTopology(%s, %.12f))' % (geom, tolerance)

def st_scale(geom, bounds, scale):
    xmax = scale / (bounds[2] - bounds[0])
    ymax = scale / (bounds[3] - bounds[1])

    return ('ST_TransScale(%s, %.12f, %.12f, %.12f, %.12f)'
            % (geom, -bounds[0], -bounds[1], xmax, ymax))

def build_bbox_query(subquery, bounds, geom='q.__geometry__', srid=3857):
    query = '''SELECT *, ST_AsBinary(%(geom)s) AS __geometry__
               FROM (%(query)s) AS q''' % {'geom': geom,
                                           'query': subquery}
    default_bbox_filter = ' WHERE ST_Intersects(q.__geometry__, %(bbox)s)'
    bbox_token = '!bbox!'
    bbox = st_bbox(bounds, srid)

    return (query.replace(bbox_token, bbox)
            if bbox_token in query
            else query + default_bbox_filter % {'bbox': bbox})

def build_query(query, bounds, srid=3857, tolerance=0, is_geo=False, is_clipped=True, scale=4096):
    bbox = st_bbox(bounds, srid)
    geom = 'q.__geometry__'

    if tolerance > 0: geom = st_simplify(geom, tolerance, bounds, srid)
    if is_clipped: geom = 'ST_Intersection(%s, %s)' % (geom, bbox)
    if is_geo: geom = 'ST_Transform(%s, 4326)' % geom
    if scale: geom = st_scale(geom, bounds, scale)

    return build_bbox_query(query, bounds, geom, srid)

def get_query(layer, coord, bounds, format):
    query = (layer.query_fn(coord.zoom)
             if layer.query_fn
             else u.xs_get(layer.queries, coord.zoom, layer.queries[-1]))

    if not query: return None
    else:
        srid = layer.srid
        tolerance = get_tolerance(layer.simplify, coord.zoom)
        clip = layer.clip

        geo_query = build_query(query, bounds, srid, tolerance, True, clip)
        mvt_query = build_query(query, bounds, srid, tolerance, False, clip)
        return {'JSON': geo_query, 'MVT': mvt_query}[format]

def encode(out, name, features, coord, bounds, format):
    if format == 'MVT':
        mvt.encode(out, name, features)
    elif format == 'JSON':
        geojson.encode(out, features, coord.zoom)
    else:
        raise ValueError(format + ' is not supported')

def merge(out, feature_layers, coord, format):
    if format == 'MVT':
        mvt.merge(out, feature_layers)
    elif format == 'JSON':
        geojson.merge(out, feature_layers, coord.zoom)
    else:
        raise ValueError(format + ' is not supported')

class Provider:
    def __init__(self, dbinfo):
        conn = connect(**dbinfo)
        conn.set_session(readonly=True, autocommit=True)
        self.db = conn.cursor(cursor_factory=RealDictCursor)

    def query_bounds(self, query, bounds, srid=3857):
        query = build_bbox_query(query, bounds, 'q.__geometry__', srid)
        self.db.execute(query)

        return self.db.fetchall()

    def query_zxy(self, query, z, x, y, srid=3857):
        return self.query_bounds(query, u.bounds(z, x, y, srid), srid)

    def pr_query(self, query, z, x, y, srid=3857):
        print(build_bbox_query(query, u.bounds(z, x, y, srid), 'q.__geometry__', srid))

    def explain_analyze_query(self, query, z, x, y, srid=3857):
        query = build_bbox_query(query, u.bounds(z, x, y, srid), 'q.__geometry__', srid)
        query = 'EXPLAIN ANALYZE ' + query
        self.db.execute(query)

        return self.db.fetchall()

    def query(self, query, geometry_types, transform_fn, sort_fn):
        features = []

        self.db.execute(query)
        for row in self.db.fetchall():
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

    def get_features(self, layer, coord, bounds, format):
        query = get_query(layer, coord, bounds, format)
        geometry_types = layer.geometry_types
        transform_fn = layer.transform_fn
        sort_fn = layer.sort_fn

        return ([] if not query
                else self.query(query, geometry_types, transform_fn, sort_fn))

    def get_feature_layer(self, layer, coord, format):
        bounds = u._bounds(coord, layer.srid)
        features = self.get_features(layer, coord, bounds, format)
        return {'name': layer.name, 'features': features}

    def render_tile(self, lols, coord, format):
        buff = StringIO()

        if type(lols) is list:
            get_feature_layer = lambda l : self.get_feature_layer(l, coord, format)
            feature_layers = map(get_feature_layer, lols)
            merge(buff, feature_layers, coord, format)
        else:
            bounds = u._bounds(coord, lols.srid)
            features = self.get_features(lols, coord, bounds, format)
            encode(buff, lols.name, features, coord, bounds, format)

        return buff.getvalue()
