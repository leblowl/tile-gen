import mapbox_vector_tile

# coordindates are scaled to this range within tile
extents = 4096

# tiles are padded by this number of pixels for the current zoom level
padding = 0

def decode(file):
    tile = file.read()
    data = mapbox_vector_tile.decode(tile)
    return data # print data or write to file?

def encode(file, name, features):
    layers = [get_feature_layer(name, features)]
    data = mapbox_vector_tile.encode(layers)
    file.write(data)

def merge(file, feature_layers):
    layers = map(lambda x : get_feature_layer(x['name'], x['features']), feature_layers)
    data = mapbox_vector_tile.encode(layers)
    file.write(data)

def get_feature_layer(name, features):
    _features = []

    for feature in features:
        wkb, props, fid = feature
        _features.append({
            'geometry': wkb,
            'properties': props,
            'id': fid,
        })

    return {
        'name': name or '',
        'features': _features
    }
