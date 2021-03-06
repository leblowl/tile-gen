"""
A cache stores static files to speed up future requests.
A few built-in caches are found here, but it's possible to define your
own and pull them in dynamically by class name.

Built-in caches:
- test
- disk

Example built-in cache configuration:

    "cache": {
      "name": "Disk",
      "path": "/tmp/data",
      "umask": "0000"
    }

Example external cache configuration:

    "cache": {
      "class": "Module.Classname",
      "kwargs": {"frob": "yes"}
    }

- The "class" value is split up into module and classname, and dynamically
  included. Exception thrown on failure to include.
- The "kwargs" value is fed to the class constructor as a dictionary of keyword
  args. If your defined class doesn't accept any of these keyword arguments,
  an exception is thrown.

A cache must provide these methods: lock(), unlock(), read(), and save().
Each method accepts three arguments:

- layer: layer name
- coord: single Coordinate that represents a tile.
- format: string like "png" or "jpg" that is used as a filename extension.

The save() method accepts an additional argument before the others:

- body: raw content to save to the cache.
"""

import os
import sys
import time
import gzip
import portalocker
from tempfile import mkstemp
from os.path import isdir, exists, dirname, basename, join as pathjoin

def get_cache_by_name(name):
    if name.lower() == 'disk': return Disk
    else: raise Exception('Unknown cache: %s' % name)

class Disk:
    """ Caches files to disk.

        Example configuration:

            "cache": {
              "name": "Disk",
              "path": "/tmp/stache",
              "umask": "0000",
              "dirs": "portable"
            }

        Extra parameters:
        - path: required local directory path where files should be stored.
        - umask: optional string representation of octal permission mask
          for stored files. Defaults to 0022.
        - dirs: optional string saying whether to create cache directories that
          are safe, portable or quadtile. For an example tile 12/656/1582.png,
          "portable" creates matching directory trees while "safe" guarantees
          directories with fewer files, e.g. 12/000/656/001/582.png.
          Defaults to safe.
        - gzip: optional list of file formats that should be stored in a
          compressed form. Defaults to "txt", "text", "json", and "xml".
          Provide an empty list in the configuration for no compression.

        If your configuration file is loaded from a remote location, e.g.
        "http://example.com/tilestache.cfg", the path *must* be an unambiguous
        filesystem path, e.g. "file:///tmp/cache"
    """
    def __init__(self, path, umask=0022, dirs='safe', gzip='txt text json xml'.split()):
        self.cachepath = path
        self.umask = int(umask)
        self.dirs = dirs
        self.gzip = [format.lower() for format in gzip]

    def _is_compressed(self, format):
        return format.lower() in self.gzip

    def _filepath(self, layer, coord, format):
        l = layer
        z = '%d' % coord.zoom
        e = format.lower()
        e += self._is_compressed(format) and '.gz' or ''

        if self.dirs == 'safe':
            x = '%06d' % coord.column
            y = '%06d' % coord.row

            x1, x2 = x[:3], x[3:]
            y1, y2 = y[:3], y[3:]

            filepath = os.sep.join( (l, z, x1, x2, y1, y2 + '.' + e) )

        elif self.dirs == 'portable':
            x = '%d' % coord.column
            y = '%d' % coord.row

            filepath = os.sep.join( (l, z, x, y + '.' + e) )

        elif self.dirs == 'quadtile':
            pad, length = 1 << 31, 1 + coord.zoom

            # two binary strings, one per dimension
            xs = bin(pad + int(coord.column))[-length:]
            ys = bin(pad + int(coord.row))[-length:]

            # interleave binary bits into plain digits, 0-3.
            # adapted from ModestMaps.Tiles.toMicrosoft()
            dirpath = ''.join([str(int(y+x, 2)) for (x, y) in zip(xs, ys)])

            # built a list of nested directory names and a file basename
            parts = [dirpath[i:i+3] for i in range(0, len(dirpath), 3)]

            filepath = os.sep.join([l] + parts[:-1] + [parts[-1] + '.' + e])

        else:
            raise Exception('Please provide a valid "dirs" parameter to the Disk cache, either "safe", "portable" or "quadtile" but not "%s"' % self.dirs)

        return filepath

    def _fullpath(self, layer, coord, format):
        filepath = self._filepath(layer, coord, format)
        fullpath = pathjoin(self.cachepath, filepath)

        return fullpath

    def _lockpath(self, layer, coord, format):
        return self._fullpath(layer, coord, format) + '.lock'

    def lock(self, layer, coord, format):
        umask_old = os.umask(self.umask)
        path = self._lockpath(layer, coord, format)

        try:
            os.makedirs(os.path.dirname(path), 0777&~self.umask)
        except OSError, e:
            # errno=17 means that parent directories already exist, which is fine
            if e.errno != 17: raise
        finally:
            os.umask(umask_old)

        self.lockfile = open(path, 'w+')
        portalocker.lock(self.lockfile, portalocker.LOCK_EX | portalocker.LOCK_NB)

    def unlock(self, layer, coord, format):
        self.lockfile.close()
        os.remove(self.lockfile.name)
        self.lockfile = None

    def remove(self, layer, coord, format):
        fullpath = self._fullpath(layer, coord, format)

        try:
            os.remove(fullpath)
        except OSError, e:
            # errno=2 means that the file does not exist, which is fine
            if e.errno != 2: raise

    def read(self, layer, coord, format):
        fullpath = self._fullpath(layer, coord, format)

        if not exists(fullpath):
            return None

        if self._is_compressed(format):
            return gzip.open(fullpath, 'r').read()

        else:
            body = open(fullpath, 'rb').read()
            return body

    def save(self, body, layer, coord, format):
        umask_old = os.umask(self.umask)
        fullpath = self._fullpath(layer, coord, format)

        try:
            os.makedirs(dirname(fullpath), 0777&~self.umask)
        except OSError, e:
            if e.errno != 17: raise
        finally:
            os.umask(umask_old)

        suffix = '.' + format.lower()
        suffix += self._is_compressed(format) and '.gz' or ''

        fh, tmp_path = mkstemp(dir=self.cachepath, suffix=suffix)

        if self._is_compressed(format):
            os.close(fh)
            tmp_file = gzip.open(tmp_path, 'w')
            tmp_file.write(body)
            tmp_file.close()
        else:
            os.write(fh, body)
            os.close(fh)

        try:
            os.rename(tmp_path, fullpath)
        except OSError:
            os.unlink(fullpath)
            os.rename(tmp_path, fullpath)

        os.chmod(fullpath, 0666&~self.umask)
