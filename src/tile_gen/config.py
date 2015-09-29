import sys
import json
import tile_gen.util as u
import tile_gen.layer as layer
import tile_gen.caches as caches
import tile_gen.vectiles.provider as provider
from sys import stderr

def build_cache(cache_d):
    _class, kwargs = None, {}

    if 'name' in cache_d:
        _class = caches.get_cache_by_name(cache_d['name'])
        if _class is caches.Disk:
            kwargs = u.select_keys(cache_d, ['umask', 'path', 'dirs', 'gzip'])

    elif 'class' in cache_d:
        _class = u.load_class_path(cache_d['class'])
        kwargs = cache_d.get('kwargs', {})

    return _class(**kwargs) if _class else None

def build_layer(name, layer_d): return layer.Layer(name, **layer_d)

def build_layers(layers_d):
    return {k: build_layer(k, v) for k, v in layers_d.iteritems()}

class Config:
    def __init__(self, config_d):
        self.provider = provider.Provider(config_d.get('dbinfo', {}))
        self.cache    = build_cache(config_d.get('cache', {}))
        self.layers   = build_layers(config_d.get('layers', {}))
