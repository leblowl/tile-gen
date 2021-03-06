from setuptools import Command, setup
import sys, os, os.path as path, code

env = {'source_paths': ['src', 'test']}

def init_env(env):
  for path in env.get('source_paths'):
    sys.path.append(os.path.abspath(path))

class Repl(Command):
  description = "Launch repl for dev"
  user_options = []

  def initialize_options(self):
    pass

  def finalize_options(self):
    pass

  def run(self):
    code.interact(local=globals())

init_env(env)
setup(name = 'tile-gen',
      version = '0.1.0',
      classifiers = ['Programming Language :: Python :: 2.7'],
      packages = ['tile_gen', 'tile_gen.vectiles'],
      package_dir = {'tile_gen': 'src/tile_gen'},
      install_requires = ['mapbox-vector-tile==0.0.10',
                          'ModestMaps==1.4.6',
                          'Pillow==2.9.0',
                          'portalocker==0.5.4',
                          'protobuf==2.6.1',
                          'psycopg2==2.6.1',
                          'Shapely==1.5.9',
                          'StreetNames==0.1.5'],
      cmdclass = {"repl": Repl})
