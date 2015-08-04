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
            "metatile": { ... },
            "stale lock timeout": ...,
            "projection": ...
        }
      }
    }

Configuration also supports these additional settings:

- "logging": one of "debug", "info", "warning", "error" or "critical", as
  described in Python's logging module: http://docs.python.org/howto/logging.html

In-depth explanations of the layer components can be found in the module
documentation for TileStache.Providers, TileStache.Core, and TileStache.Geography.
"""

import sys
import logging
import tile_gen.core as core
import tile_gen.caches as caches
import tile_gen.providers as providers
import tile_gen.geography as geography
from sys import stderr, modules
from os.path import realpath, join as pathjoin
from urlparse import urljoin, urlparse
from mimetypes import guess_type
from json import dumps
from ModestMaps.Geo import Location
from ModestMaps.Core import Coordinate

class Configuration:
    """ A complete site configuration, with a collection of Layer objects.

        Attributes:

          cache:
            Cache instance, e.g. TileStache.Caches.Disk etc.
            See TileStache.Caches for details on what makes
            a usable cache.

          layers:
            Dictionary of layers keyed by name.
    """
    def __init__(self, cache):
        self.cache = cache
        self.layers = {}

        # adding custom_layer to extend multiprovider to support comma separated layernames
        self.custom_layer_name = ","
        self.custom_layer_dict = {'provider': {'class': 'tile_gen.vectiles.server.MultiProvider', 'kwargs': {'names': []}}}

class Bounds:
    """ Coordinate bounding box for tiles.
    """
    def __init__(self, upper_left_high, lower_right_low):
        """ Two required Coordinate objects defining tile pyramid bounds.

            Boundaries are inclusive: upper_left_high is the left-most column,
            upper-most row, and highest zoom level; lower_right_low is the
            right-most column, furthest-dwn row, and lowest zoom level.
        """
        self.upper_left_high = upper_left_high
        self.lower_right_low = lower_right_low

    def excludes(self, tile):
        """ Check a tile Coordinate against the bounds, return true/false.
        """
        if tile.zoom > self.upper_left_high.zoom:
            # too zoomed-in
            return True

        if tile.zoom < self.lower_right_low.zoom:
            # too zoomed-out
            return True

        # check the top-left tile corner against the lower-right bound
        _tile = tile.zoomTo(self.lower_right_low.zoom)

        if _tile.column > self.lower_right_low.column:
            # too far right
            return True

        if _tile.row > self.lower_right_low.row:
            # too far down
            return True

        # check the bottom-right tile corner against the upper-left bound
        __tile = tile.right().down().zoomTo(self.upper_left_high.zoom)

        if __tile.column < self.upper_left_high.column:
            # too far left
            return True

        if __tile.row < self.upper_left_high.row:
            # too far up
            return True

        return False

    def __str__(self):
        return 'Bound %s - %s' % (self.upper_left_high, self.lower_right_low)

class BoundsList:
    """ Multiple coordinate bounding boxes for tiles.
    """
    def __init__(self, bounds):
        """ Single argument is a list of Bounds objects.
        """
        self.bounds = bounds

    def excludes(self, tile):
        """ Check a tile Coordinate against the bounds, return false if none match.
        """
        for bound in self.bounds:
            if not bound.excludes(tile):
                return False

        # Nothing worked.
        return True

def build_config(config_dict):
    """ Build a configuration dictionary into a Configuration object.
    """
    cache_dict = config_dict.get('cache', {})
    cache      = parse_config_cache(cache_dict)
    config     = Configuration(cache)

    for (name, layer_dict) in config_dict.get('layers', {}).items():
        config.layers[name] = parse_config_layer(layer_dict, config)

    config.layers[config.custom_layer_name] = parse_config_layer(config.custom_layer_dict, config)

    if 'logging' in config_dict:
        level = config_dict['logging'].upper()

        if hasattr(logging, level):
            logging.basicConfig(level=getattr(logging, level))

    return config

def parse_config_cache(cache_dict):
    if 'name' in cache_dict:
        _class = caches.getCacheByName(cache_dict['name'])
        kwargs = {}

        def add_kwargs(*keys):
            """ Populate named keys in kwargs from cache_dict.
            """
            for key in keys:
                if key in cache_dict:
                    kwargs[key] = cache_dict[key]

        if _class is caches.Test:
            if cache_dict.get('verbose', False):
                kwargs['logfunc'] = lambda msg: stderr.write(msg + '\n')

            if 'umask' in cache_dict:
                kwargs['umask'] = int(cache_dict['umask'], 8)

            add_kwargs('dirs', 'gzip')

        elif _class is caches.Multi:
            kwargs['tiers'] = [parse_config_cache(tier_dict)
                               for tier_dict in cache_dict['tiers']]

        elif _class is caches.Memcache.Cache:
            if 'key prefix' in cache_dict:
                kwargs['key_prefix'] = cache_dict['key prefix']

            add_kwargs('servers', 'lifespan', 'revision')

        elif _class is caches.Redis.Cache:
            if 'key prefix' in cache_dict:
                kwargs['key_prefix'] = cache_dict['key prefix']

            add_kwargs('host', 'port', 'db')

        elif _class is caches.S3.Cache:
            add_kwargs('bucket', 'access', 'secret', 'use_locks', 'path', 'reduced_redundancy')

        else:
            raise Exception('Unknown cache: %s' % cache_dict['name'])

    elif 'class' in cache_dict:
        _class = load_class_path(cache_dict['class'])
        kwargs = cache_dict.get('kwargs', {})
        kwargs = dict( [(str(k), v) for (k, v) in kwargs.items()] )

    else:
        raise Exception('Missing required cache name or class: %s' % dumps(cache_dict))

    cache = _class(**kwargs)

    return cache

def parse_layer_bounds(bounds_dict, projection):
    """
    """
    north, west = bounds_dict.get('north', 89), bounds_dict.get('west', -180)
    south, east = bounds_dict.get('south', -89), bounds_dict.get('east', 180)
    high, low = bounds_dict.get('high', 31), bounds_dict.get('low', 0)

    try:
        ul_hi = projection.locationCoordinate(Location(north, west)).zoomTo(high)
        lr_lo = projection.locationCoordinate(Location(south, east)).zoomTo(low)
    except TypeError:
        raise core.KnownUnknown('Bad bounds for layer, need north, south, east, west, high, and low: ' + dumps(bounds_dict))

    return Bounds(ul_hi, lr_lo)

def parse_config_layer(layer_dict, config):
    """ Used by parseConfigfile() to parse just the layer parts of a config.
    """
    projection = layer_dict.get('projection', 'spherical mercator')
    projection = geography.getProjectionByName(projection)

    #
    # Add cache lock timeouts and preview arguments
    #

    layer_kwargs = {}

    if 'cache lifespan' in layer_dict:
        layer_kwargs['cache_lifespan'] = int(layer_dict['cache lifespan'])

    if 'stale lock timeout' in layer_dict:
        layer_kwargs['stale_lock_timeout'] = int(layer_dict['stale lock timeout'])

    if 'write cache' in layer_dict:
        layer_kwargs['write_cache'] = bool(layer_dict['write cache'])

    if 'maximum cache age' in layer_dict:
        layer_kwargs['max_cache_age'] = int(layer_dict['maximum cache age'])

    if 'bounds' in layer_dict:
        if type(layer_dict['bounds']) is dict:
            layer_kwargs['bounds'] = parse_layer_bounds(layer_dict['bounds'], projection)

        elif type(layer_dict['bounds']) is list:
            bounds = [parse_layer_bounds(b, projection) for b in layer_dict['bounds']]
            layer_kwargs['bounds'] = BoundsList(bounds)

        else:
            raise core.KnownUnknown('Layer bounds must be a dictionary, not: ' + dumps(layer_dict['bounds']))

    if 'tile height' in layer_dict:
        layer_kwargs['tile_height'] = int(layer_dict['tile height'])

    #
    # Do the metatile
    #

    meta_dict = layer_dict.get('metatile', {})
    metatile_kwargs = {}

    for k in ('buffer', 'rows', 'columns'):
        if k in meta_dict:
            metatile_kwargs[k] = int(meta_dict[k])

    metatile = core.Metatile(**metatile_kwargs)

    #
    # Do the provider
    #

    provider_dict = layer_dict['provider']

    if 'name' in provider_dict:
        _class = providers.getProviderByName(provider_dict['name'])
        provider_kwargs = _class.prepareKeywordArgs(provider_dict)

    elif 'class' in provider_dict:
        _class = load_class_path(provider_dict['class'])
        provider_kwargs = provider_dict.get('kwargs', {})
        provider_kwargs = dict( [(str(k), v) for (k, v) in provider_kwargs.items()] )

    else:
        raise Exception('Missing required provider name or class: %s' % dumps(provider_dict))

    layer = core.Layer(config, projection, metatile, **layer_kwargs)
    layer.provider = _class(layer, **provider_kwargs)

    return layer

def load_class_path(classpath):
    """ Load external class based on a path.
        Example classpath: "Module.Submodule.Classname".
    """
    modname, objname = classpath.rsplit('.', 1)
    __import__(modname)
    module = modules[modname]
    _class = eval(objname, module.__dict__)
    return _class
