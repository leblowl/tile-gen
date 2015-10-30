import json
import shapely.wkb
import tile_gen.util as u
import tile_gen.vectiles.mvt as mvt
import tile_gen.vectiles.geojson as geojson
import tile_gen.vectiles.topojson as topojson
from tile_gen.geography import SphericalMercator
from ModestMaps.Core import Coordinate
from StringIO import StringIO
from math import pi
from psycopg2.extras import RealDictCursor
from psycopg2 import connect
from ModestMaps.Core import Point

tolerances = [6378137 * 2 * pi / (2 ** (zoom + 8)) for zoom in range(22)]

def get_tolerance(layer, coord): return layer.simplify * tolerances[coord.zoom]

def pad(bounds, padding):
    bounds[0] -= padding
    bounds[1] -= padding
    bounds[2] += padding
    bounds[3] += padding

    return bounds

def st_bbox(bounds, srid):
    return 'ST_MakeEnvelope({xmin}, {ymin}, {xmax}, {ymax}, {srid})' \
           .format(xmin=bounds[0],
                   ymin=bounds[1],
                   xmax=bounds[2],
                   ymax=bounds[3],
                   srid=srid)

def st_simplify(geom, tolerance, bounds, srid=900913):
    padding = (bounds[3] - bounds[1]) * 0.1
    geom = 'ST_Intersection(%s, %s)' % (geom, st_bbox(pad(bounds, padding), srid))

    return 'ST_MakeValid(ST_SimplifyPreserveTopology(%s, %.12f))' % (geom, tolerance)

def st_scale(geom, bounds, scale):
    xmax = scale / (bounds[2] - bounds[0])
    ymax = scale / (bounds[3] - bounds[1])

    return ('ST_TransScale(%s, %.12f, %.12f, %.12f, %.12f)'
            % (geom, -bounds[0], -bounds[1], xmax, ymax))

def build_bbox_query(query, bounds, geom='q.__geometry__', srid=900913):
    bbox = st_bbox(bounds, srid)

    return '''SELECT *, ST_AsBinary(%(geom)s) AS __geometry__
              FROM (%(query)s) AS q
              WHERE ST_Intersects(q.__geometry__, %(bbox)s)''' % {'geom': geom,
                                                                  'query': query,
                                                                  'bbox': bbox}

def build_query(query, bounds, srid=900913, tolerance=0, is_geo=False, is_clipped=True, scale=4096):
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
        tolerance = get_tolerance(layer, coord)
        clip = layer.clip

        # maybe keep geo in spherical mercator if possible to unify the building of queries
        geo_query = build_query(query, bounds, srid, tolerance, True, clip)
        mvt_query = build_query(query, bounds, srid, tolerance, False, clip)
        return {'JSON': geo_query, 'TopoJSON': geo_query, 'MVT': mvt_query}[format]

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

def merge(out, layers, feature_layers, coord, format):
    if format == 'MVT':
        mvt.merge(out, feature_layers)
    else:
        names = map(lambda x : x.name, layers)
        tiles = map(lambda x : json.loads(render_tile(x, coord, format)), layers)

        if format == 'TopoJSON':
            topojson.merge(out, names, tiles)
        elif format == 'JSON':
            geojson.merge(out, names, tiles, coord.zoom)
        else:
            raise ValueError(format + " is not supported for responses with multiple layers")

class Provider:
    def __init__(self, dbinfo):
        conn = connect(**dbinfo)
        conn.set_session(readonly=True, autocommit=True)
        self.db = conn.cursor(cursor_factory=RealDictCursor)

    def query_bounds(self, query, bounds, srid=900913):
        query = build_bbox_query(query, bounds, 'q.__geometry__', srid)
        self.db.execute(query)

        return self.db.fetchall()

    def query_zxy(self, query, z, x, y, srid=900913):
        return self.query_bounds(query, u.bounds(z, x, y, srid), srid)

    def pr_query(self, query, z, x, y, srid=900913):
        print(build_bbox_query(query, u.bounds(z, x, y, srid), 'q.__geometry__', srid))

    def explain_analyze_query(self, query, z, x, y, srid=900913):
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

    def render_tile(self, lols, coord, format):
        buff = StringIO()

        if type(lols) is list:
            def get_feature_layer(layer):
                bounds = u._bounds(coord, layer.srid)
                features = self.get_features(layer, coord, bounds, format)
                return {'name': layer.name, 'features': features}

            merge(buff, lols, map(get_feature_layer, lols), coord, format)
        else:
            bounds = u._bounds(coord, lols.srid)
            features = self.get_features(lols, coord, bounds, format)
            encode(buff, lols.name, features, coord, bounds, format)

        return buff.getvalue()
