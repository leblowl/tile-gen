import os.path
import re
from sys import stdout
from StringIO import StringIO
from os.path import dirname, join as pathjoin, realpath
from datetime import datetime, timedelta
from urlparse import urljoin, urlparse
from wsgiref.headers import Headers
from urllib import urlopen
from os import getcwd
from time import time
import httplib
import logging
from json import load as json_load
from ModestMaps.Core import Coordinate
import Core
import Config

# dictionary of configuration objects for requestLayer().
_previous_configs = {}

# regular expression for PATH_INFO
_pathinfo_pat = re.compile(r'^/?(?P<l>\w.+)/(?P<z>\d+)/(?P<x>-?\d+)/(?P<y>-?\d+)\.(?P<e>\w+)$')
_preview_pat = re.compile(r'^/?(?P<l>\w.+)/(preview\.html)?$')

# symbol used to separate layers when specifying more than one layer
_delimiter = ','

def getTile(layer, coord, extension, ignore_cached=False, suppress_cache_write=False):
    ''' Get a type string and tile binary for a given request layer tile.

        This function is documented as part of TileStache's public API:
            http://tilestache.org/doc/#tilestache-gettile

        Arguments:
        - layer: instance of Core.Layer to render.
        - coord: one ModestMaps.Core.Coordinate corresponding to a single tile.
        - extension: filename extension to choose response type, e.g. "png" or "jpg".
        - ignore_cached: always re-render the tile, whether it's in the cache or not.
        - suppress_cache_write: don't save the tile to the cache

        This is the main entry point, after site configuration has been loaded
        and individual tiles need to be rendered.
    '''
    status_code, headers, body = layer.getTileResponse(coord, extension, ignore_cached, suppress_cache_write)
    mime = headers.get('Content-Type')

    return mime, body

def unknownLayerMessage(config, unknown_layername):
    """ A message that notifies that the given layer is unknown and lists out the known layers.
    """
    return '"%s" is not a layer I know about. \nHere are some that I do know about: \n %s.' % (unknown_layername, '\n '.join(sorted(config.layers.keys())))

def getPreview(layer):
    """ Get a type string and dynamic map viewer HTML for a given layer.
    """
    return 200, Headers([('Content-Type', 'text/html')]), Core._preview(layer)

def parseConfigfile(configpath):
    """ Parse a configuration file and return a Configuration object.

        Configuration file is formatted as JSON with two sections, "cache" and "layers":

          {
            "cache": { ... },
            "layers": {
              "layer-1": { ... },
              "layer-2": { ... },
              ...
            }
          }

        The full path to the file is significant, used to
        resolve any relative paths found in the configuration.

        See the Caches module for more information on the "caches" section,
        and the Core and Providers modules for more information on the
        "layers" section.
    """
    config_dict = json_load(urlopen(configpath))

    scheme, host, path, p, q, f = urlparse(configpath)

    if scheme == '':
        scheme = 'file'
        path = realpath(path)

    dirpath = '%s://%s%s' % (scheme, host, dirname(path).rstrip('/') + '/')

    return Config.buildConfiguration(config_dict, dirpath)

def splitPathInfo(pathinfo):
    """ Converts a PATH_INFO string to layer name, coordinate, and extension parts.

        Example: "/layer/0/0/0.png", leading "/" optional.
    """
    if pathinfo == '/':
        return None, None, None

    if _pathinfo_pat.match(pathinfo or ''):
        path = _pathinfo_pat.match(pathinfo)
        layer, row, column, zoom, extension = [path.group(p) for p in 'lyxze']
        coord = Coordinate(int(row), int(column), int(zoom))

    elif _preview_pat.match(pathinfo or ''):
        path = _preview_pat.match(pathinfo)
        layer, extension = path.group('l'), 'html'
        coord = None

    else:
        raise Core.KnownUnknown('Bad path: "%s". I was expecting something more like "/example/0/0/0.png"' % pathinfo)

    return layer, coord, extension

def mergePathInfo(layer, coord, extension):
    """ Converts layer name, coordinate and extension back to a PATH_INFO string.

        See also splitPathInfo().
    """
    z = coord.zoom
    x = coord.column
    y = coord.row

    return '/%(layer)s/%(z)d/%(x)d/%(y)d.%(extension)s' % locals()

def isValidLayer(layer, config):
    if not layer:
        return False
    if (layer not in config.layers):
        if (layer.find(_delimiter) != -1):
            multi_providers = list(ll for ll in config.layers if hasattr(config.layers[ll].provider, 'names'))
            for l in layer.split(_delimiter):
                if ((l not in config.layers) or (l in multi_providers)):
                    return False
            return True
        return False
    return True

def requestLayer(config, path_info):
    """ Return a Layer.

        Requires a configuration and PATH_INFO (e.g. "/example/0/0/0.png").

        Config parameter can be a file path string for a JSON configuration file
        or a configuration object with 'cache', 'layers', and 'dirpath' properties.
    """
    if type(config) in (str, unicode):
        #
        # Should be a path to a configuration file we can load;
        # build a tuple key into previously-seen config objects.
        #
        key = hasattr(config, '__hash__') and (config, getcwd())

        if key in _previous_configs:
            config = _previous_configs[key]

        else:
            config = parseConfigfile(config)

            if key:
                _previous_configs[key] = config

    else:
        assert hasattr(config, 'cache'), 'Configuration object must have a cache.'
        assert hasattr(config, 'layers'), 'Configuration object must have layers.'
        assert hasattr(config, 'dirpath'), 'Configuration object must have a dirpath.'

    # ensure that path_info is at least a single "/"
    path_info = '/' + (path_info or '').lstrip('/')

    if path_info == '/':
        return Core.Layer(config, None, None)

    layername = splitPathInfo(path_info)[0]

    if not isValidLayer(layername, config):
        raise Core.KnownUnknown(unknownLayerMessage(config, layername))

    custom_layer = layername.find(_delimiter)!=-1

    if custom_layer:
        # we can't just assign references, because we get identity problems
        # when tilestache tries to look up the layer's name, which won't match
        # the list of names in the provider
        provider_names = layername.split(_delimiter)
        custom_layer_obj = config.layers[config.custom_layer_name]
        config.layers[layername] = clone_layer(custom_layer_obj, provider_names)

    return config.layers[layername]


def clone_layer(layer, provider_names):
    from TileStache.Core import Layer
    copy = Layer(
        layer.config,
        layer.projection,
        layer.metatile,
        layer.stale_lock_timeout,
        layer.cache_lifespan,
        layer.write_cache,
        layer.allowed_origin,
        layer.max_cache_age,
        layer.redirects,
        layer.preview_lat,
        layer.preview_lon,
        layer.preview_zoom,
        layer.preview_ext,
        layer.bounds,
        layer.dim,
        )
    copy.provider = layer.provider
    copy.provider(copy, provider_names)
    return copy
