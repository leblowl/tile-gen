# tile-gen
Experimental Vector Tile Generation

**tile-gen** is built from a copy of [mapzen/TileStache](https://github.com/mapzen/TileStache) and only focuses on vector tile generation & caching.

## Installation
```shell
pip install git+https://github.com/leblowl/tile-gen#egg=tile-gen
```
## Data Preparation
#### Postgresql, Planet.osm, & [mapzen/vector-datasource](https://github.com/mapzen/vector-datasource) example
```
wget http://ftp5.gwdg.de/pub/misc/openstreetmap/planet.openstreetmap.org/pbf/planet-latest.osm.pbf
osmconvert planet-latest.osm.pbf -o=planet-latest.o5m
osmfilter planet-latest.o5m --keep="highway= route=road" -o=streets.o5m
osm2pgsql -c -d gis -S mapzen/vector-datasource/osm2pgsql.style streets.o5m \
          -l --slim -C 36000 --flat-nodes node.cache --hstore --number-processes 16
```

## Hacking tile-gen
```shell
git clone https://github.com/zoondka/tile-gen/
cd tile-gen
pip install -e .
```

I'm using a little startup script to help initialize the system path on repl launch.
Installation:
```shell
wget https://gist.githubusercontent.com/leblowl/cbd047c8633d5b321ec7/raw/29ad1d7da6c11a36cd340543a5bd2b59100e3a91/build_init.py
mv build_init.py ~/.config/python
echo -e '\nexport PYTHONSTARTUP=$HOME/.config/python/build_init.py' >> ~/.profile
source ~/.profile
```

Now in the project root, you can run:
```shell
python -i
>>> import tile_gen.app as tile_gen
>>> tile_gen.get_tile('all', 0, 0, 0, 'mvt')
```
