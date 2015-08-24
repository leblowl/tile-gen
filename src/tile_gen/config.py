""" The configuration bits of tile-gen.

tile-gen configuration is stored in JSON files, and is composed of two main
top-level sections: "cache" and "layers". There are examples of both in this
minimal sample configuration:

    {
      "cache": {"name": "Test"},
      "layers": {
        "example": {
            "provider": {"class": "tile_gen.vectiles.server.Provider",
                         ...
                         ...
        }
      }
    }

The contents of the "cache" section are described in greater detail in the
TileStache.Caches module documentation. Here is a different sample:

    "cache": {
      "name": "Disk",
      "path": "/tmp/stache",
      "umask": "0000"
    }

The "layers" section is a dictionary of layer names. Example:

    {
      "cache": ...,
      "layers":
      {
        "example-layer-name":
        {
            "provider": { ... },
            "stale lock timeout": ...,
            "projection": ...
        }
      }
    }
"""

import sys
import json
import tile_gen.util as u
import tile_gen.layer
import tile_gen.caches as caches
import tile_gen.vectiles.provider as provider
from sys import stderr

class Configuration:
    def __init__(self, path):
        config = json.load(u.open(path))

        self.dbinfo     = config.get('provider', {}).get('dbinfo', {})
        self.cache      = parse_cache(config.get('cache', {}))
        self.layers     = parse_layers(config.get('layers', {}))

def parse_cache(cache_dict):
    if 'name' in cache_dict:
        _class = caches.get_cache_by_name(cache_dict['name'])
        kwargs = {}

        def add_kwargs(*keys):
            for key in keys:
                if key in cache_dict:
                    kwargs[key] = cache_dict[key]

        if _class is caches.Test:
            if cache_dict.get('verbose', False):
                kwargs['logfunc'] = lambda msg: stderr.write(msg + '\n')

        elif _class is caches.Disk:
            kwargs['path'] = cache_dict['path']

            if 'umask' in cache_dict:
                kwargs['umask'] = int(cache_dict['umask'], 8)

            add_kwargs('dirs', 'gzip')

        else:
            raise Exception('Unknown cache: %s' % cache_dict['name'])

    elif 'class' in cache_dict:
        _class = u.load_class_path(cache_dict['class'])
        kwargs = cache_dict.get('kwargs', {})
        kwargs = dict( [(str(k), v) for (k, v) in kwargs.items()] )

    else:
        raise Exception('Missing required cache name or class: %s' % json.dumps(cache_dict))

    cache = _class(**kwargs)

    return cache

def parse_layer(name, layer_dict):
    return tile_gen.layer.Layer(name, **layer_dict)

def parse_layers(layers_dict):
    layers = {}
    for (name, layer_dict) in layers_dict.items():
        layers[name] = parse_layer(name, layer_dict)

    return layers
