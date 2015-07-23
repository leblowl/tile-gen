from shapely.wkb import loads
import json

from ...Core import KnownUnknown

def update_arc_indexes(geometry, merged_arcs, old_arcs):
    ''' Updated geometry arc indexes, and add arcs to merged_arcs along the way.
    
        Arguments are modified in-place, and nothing is returned.
    '''
    if geometry['type'] in ('Point', 'MultiPoint'):
        return
    
    elif geometry['type'] == 'LineString':
        for (arc_index, old_arc) in enumerate(geometry['arcs']):
            geometry['arcs'][arc_index] = len(merged_arcs)
            merged_arcs.append(old_arcs[old_arc])
    
    elif geometry['type'] == 'Polygon':
        for ring in geometry['arcs']:
            for (arc_index, old_arc) in enumerate(ring):
                ring[arc_index] = len(merged_arcs)
                merged_arcs.append(old_arcs[old_arc])
    
    elif geometry['type'] == 'MultiLineString':
        for part in geometry['arcs']:
            for (arc_index, old_arc) in enumerate(part):
                part[arc_index] = len(merged_arcs)
                merged_arcs.append(old_arcs[old_arc])
    
    elif geometry['type'] == 'MultiPolygon':
        for part in geometry['arcs']:
            for ring in part:
                for (arc_index, old_arc) in enumerate(ring):
                    ring[arc_index] = len(merged_arcs)
                    merged_arcs.append(old_arcs[old_arc])
    
    else:
        raise NotImplementedError("Can't do %s geometries" % geometry['type'])

def get_transform(bounds, size=1024):
    ''' Return a TopoJSON transform dictionary and a point-transforming function.
    
        Size is the tile size in pixels and sets the implicit output resolution.
    '''
    tx, ty = bounds[0], bounds[1]
    sx, sy = (bounds[2] - bounds[0]) / size, (bounds[3] - bounds[1]) / size
    
    def forward(lon, lat):
        ''' Transform a longitude and latitude to TopoJSON integer space.
        '''
        return int(round((lon - tx) / sx)), int(round((lat - ty) / sy))
    
    return dict(translate=(tx, ty), scale=(sx, sy)), forward

def diff_encode(line, transform):
    ''' Differentially encode a shapely linestring or ring.
    '''
    coords = [transform(x, y) for (x, y) in line.coords]
    
    pairs = zip(coords[:], coords[1:])
    diffs = [(x2 - x1, y2 - y1) for ((x1, y1), (x2, y2)) in pairs]
    
    return coords[:1] + [(x, y) for (x, y) in diffs if (x, y) != (0, 0)]

def decode(file):
    ''' Stub function to decode a TopoJSON file into a list of features.
    
        Not currently implemented, modeled on geojson.decode().
    '''
    raise NotImplementedError('topojson.decode() not yet written')

def encode(file, features, bounds):
    ''' Encode a list of (WKB, property dict, id) features into a TopoJSON stream.

        If no id is available, pass in None

        Geometries in the features list are assumed to be unprojected lon, lats.
        Bounds are given in geographic coordinates as (xmin, ymin, xmax, ymax).
    '''
    transform, forward = get_transform(bounds)
    geometries, arcs = list(), list()

    for feature in features:
        wkb, props, fid = feature
        shape = loads(wkb)
        geometry = dict(properties=props)
        geometries.append(geometry)

        if fid is not None:
            geometry['id'] = fid

        if shape.type == 'GeometryCollection':
            geometries.pop()
            continue

        elif shape.type == 'Point':
            geometry.update(dict(type='Point', coordinates=forward(shape.x, shape.y)))
    
        elif shape.type == 'LineString':
            geometry.update(dict(type='LineString', arcs=[len(arcs)]))
            arcs.append(diff_encode(shape, forward))
    
        elif shape.type == 'Polygon':
            geometry.update(dict(type='Polygon', arcs=[]))

            rings = [shape.exterior] + list(shape.interiors)
            
            for ring in rings:
                geometry['arcs'].append([len(arcs)])
                arcs.append(diff_encode(ring, forward))
        
        elif shape.type == 'MultiPoint':
            geometry.update(dict(type='MultiPoint', coordinates=[]))
            
            for point in shape.geoms:
                geometry['coordinates'].append(forward(point.x, point.y))
        
        elif shape.type == 'MultiLineString':
            geometry.update(dict(type='MultiLineString', arcs=[]))
            
            for line in shape.geoms:
                geometry['arcs'].append([len(arcs)])
                arcs.append(diff_encode(line, forward))
        
        elif shape.type == 'MultiPolygon':
            geometry.update(dict(type='MultiPolygon', arcs=[]))
            
            for polygon in shape.geoms:
                rings = [polygon.exterior] + list(polygon.interiors)
                polygon_arcs = []
                
                for ring in rings:
                    polygon_arcs.append([len(arcs)])
                    arcs.append(diff_encode(ring, forward))
            
                geometry['arcs'].append(polygon_arcs)
        
        else:
            raise NotImplementedError("Can't do %s geometries" % shape.type)
    
    result = {
        'type': 'Topology',
        'transform': transform,
        'objects': {
            'vectile': {
                'type': 'GeometryCollection',
                'geometries': geometries
                }
            },
        'arcs': arcs
        }
    
    json.dump(result, file, separators=(',', ':'))

def merge(file, names, inputs, config, coord):
    ''' Retrieve a list of TopoJSON tile responses and merge them into one.
    
        get_tiles() retrieves data and performs basic integrity checks.
    '''
    transforms = [topo['transform'] for topo in inputs]
    unique_xforms = set([tuple(xform['scale'] + xform['translate']) for xform in transforms])
    
    if len(unique_xforms) > 1:
        raise KnownUnknown('%s.merge encountered incompatible transforms: %s' % (__name__, list(unique_xforms)))
    
    output = {
        'type': 'Topology',
        'transform': inputs[0]['transform'],
        'objects': dict(),
        'arcs': list()
        }
    
    for (name, input) in zip(names, inputs):
        for (index, object) in enumerate(input['objects'].values()):
            if len(input['objects']) > 1:
                output['objects']['%(name)s-%(index)d' % locals()] = object
            else:
                output['objects'][name] = object
            
            for geometry in object['geometries']:
                update_arc_indexes(geometry, output['arcs'], input['arcs'])
    
    json.dump(output, file, separators=(',', ':'))
