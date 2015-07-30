from setuptools import setup

setup(name = 'tile-gen',
      version = '0.1.0',
      classifiers = ['Programming Language :: Python :: 2.7'],
      packages = ['tile_gen', 'tile_gen.vectiles'],
      package_dir = {'tile_gen': 'src/tile_gen'},
      install_requires = ['mapbox-vector-tile==0.0.10',
                          'ModestMaps==1.4.6',
                          'Pillow==2.9.0',
                          'protobuf==2.6.1',
                          'psycopg2==2.6.1',
                          'Shapely==1.5.9',
                          'StreetNames==0.1.5'])
