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
import tile_gen.util as u
import tile_gen.layer
import tile_gen.caches as caches
import tile_gen.geography as geography
from tile_gen.vectiles.server import Provider
from sys import stderr, modules
from json import dumps

class Configuration:
    """ A complete site configuration, with a collection of Layer objects.

        Attributes:

          cache:
            Cache instance, e.g. tile_gen.caches.Disk etc.

          layers:
            Dictionary of layers keyed by name.
    """
    def __init__(self, cache, provider, layers):
        self.cache = cache
        self.provider = provider
        self.layers = layers

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
        raise Exception('Missing required cache name or class: %s' % dumps(cache_dict))

    cache = _class(**kwargs)

    return cache

def parse_provider(provider_dict):
    return Provider(provider_dict.get('dbinfo', {}))

def parse_layer(name, layer_dict):
    projection = layer_dict.get('projection', 'spherical mercator')
    projection = geography.getProjectionByName(projection)
    queries = layer_dict.get('queries', [])

    # TODO: get all arguments to layer & pass in as kwargs

    layer = tile_gen.layer.Layer(name, projection, queries)

    return layer

def parse_layers(layers_dict):
    layers = {}
    for (name, layer_dict) in layers_dict.items():
        layers[name] = parse_layer(name, layer_dict)

    return layers

def build_config(config_dict):
    """ Build a configuration dictionary into a Configuration object.
    """
    cache      = parse_cache(config_dict.get('cache', {}))
    provider   = parse_provider(config_dict.get('provider', {}))
    layers     = parse_layers(config_dict.get('layers', {}))

    return Configuration(cache, provider, layers)
