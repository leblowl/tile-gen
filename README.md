# tile-gen
Experimental Vector Tile Generation

**tile-gen** is built from a copy of [mapzen/TileStache](https://github.com/mapzen/TileStache) & only focuses on vector tile generation.

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
osm2pgsql -c -d osm -S mapzen/vector-datasource/osm2pgsql.style streets.o5m \
--slim -C 24000 --flat-nodes ./tmp --hstore -l
```
