# tile-gen
Experimental Vector Tile Generation

**tile-gen** is built from a copy of [mapzen/TileStache](https://github.com/mapzen/TileStache) and only focuses on vector tile generation & caching.

## Installation
```shell
pip install git+https://github.com/leblowl/tile-gen#egg=tile-gen
```
## Data Preparation
##### Postgresql, Planet.osm, & [mapzen/vector-datasource](https://github.com/mapzen/vector-datasource) example
```
wget http://ftp5.gwdg.de/pub/misc/openstreetmap/planet.openstreetmap.org/pbf/planet-latest.osm.pbf
osmconvert planet-latest.osm.pbf -o=planet-latest.o5m
osmfilter planet-latest.o5m --keep="highway= route=road" -o=streets.o5m
osm2pgsql -c -d gis -S mapzen/vector-datasource/osm2pgsql.style streets.o5m \
          -l --slim -C 36000 --flat-nodes node.cache --hstore --number-processes 16
```

## Hacking tile-gen
##### Installation
```shell
git clone https://github.com/zoondka/tile-gen/ && cd tile-gen
pip install -e .
```
##### REPL
```shell
python setup.py repl
>>> import tile_gen.app as tile_gen
>>> tile_gen.get_tile('all', 0, 0, 0, 'mvt')
```
