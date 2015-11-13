from re import compile
from math import pi, log, tan, ceil
import json
from shapely.wkb import loads
from shapely.geometry import asShape
from .ops import transform

float_pat = compile(r'^-?\d+\.\d+(e-?\d+)?$')
charfloat_pat = compile(r'^[\[,\,]-?\d+\.\d+(e-?\d+)?$')

# floating point lat/lon precision for each zoom level, good to ~1/4 pixel.
precisions = [int(ceil(log(1<<zoom + 8+2) / log(10)) - 2) for zoom in range(23)]

def mercator((x, y)):
    ''' Project an (x, y) tuple to spherical mercator.
    '''
    x, y = pi * x/180, pi * y/180
    y = log(tan(0.25 * pi + 0.5 * y))
    return 6378137 * x, 6378137 * y

def write_to_file(file, geojson, zoom):
    ''' Write GeoJSON stream to a file

        Floating point precision in the output is truncated to six digits.
    '''
    encoder = json.JSONEncoder(separators=(',', ':'))
    encoded = encoder.iterencode(geojson)
    flt_fmt = '%%.%df' % precisions[zoom]

    for token in encoded:
        if charfloat_pat.match(token):
            # in python 2.7, we see a character followed by a float literal
            file.write(token[0] + flt_fmt % float(token[1:]))

        elif float_pat.match(token):
            # in python 2.6, we see a simple float literal
            file.write(flt_fmt % float(token))

        else:
            file.write(token)

def decode(file):
    ''' Decode a GeoJSON file into a list of (WKB, property dict) features.
    '''
    data = json.load(file)
    features = []

    for feature in data['features']:
        if feature['type'] != 'Feature':
            continue

        if feature['geometry']['type'] == 'GeometryCollection':
            continue

        prop = feature['properties']
        geom = transform(asShape(feature['geometry']), mercator)
        features.append((geom.wkb, prop))

    return features

def get_feature_layer(features):
    _features = []
    for feature in features:
        wkb, props, fid = feature
        _features.append({
            'id': fid,
            'type': 'Feature',
            'properties': props,
            'geometry': loads(wkb).__geo_interface__
        })

    return {'type': 'FeatureCollection',
            'features': _features}

def encode(file, features, zoom):
    layer = get_feature_layer(features)
    write_to_file(file, layer, zoom)

def merge(file, feature_layers, zoom):
    layers = {x['name']: get_feature_layer(x['features'])
              for x in feature_layers}
    write_to_file(file, layers, zoom)
