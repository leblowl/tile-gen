# tile-gen
Experimental Vector Tile Generation

**tile-gen** is built from a copy of [mapzen/TileStache](https://github.com/mapzen/TileStache) and only focuses on vector tile generation & caching.

## Installation
```shell
pip install git+https://github.com/leblowl/tile-gen#egg=tile-gen
```
## Data Preparation
##### Postgresql, Planet.osm, & [zoondka/vector-datasource](https://github.com/zoondka/vector-datasource) example
```shell
wget http://ftp5.gwdg.de/pub/misc/openstreetmap/planet.openstreetmap.org/pbf/planet-latest.osm.pbf

osmconvert planet-latest.osm.pbf -o=planet-latest.o5m

osmfilter planet-latest.o5m --keep="highway=motorway =trunk =primary =secondary =tertiary =unclassified =residential =service =*_link =living_street =road =track =path route=road" -o=streets.o5m

osmconvert streets.o5m -o=streets.osm.pbf

cd vector-datasource
./jj2.py imposm3-roads.jinja2 > imposm3-roads.json
imposm3 import -mapping imposm3-roads.json -connection "postgis:///gis?host=/var/run/postgresql" -read "/path/to/streets.osm.pbf" -write -optimize
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
>>> execfile('test/example.py')
>>> core.get_tile('all', 0, 0, 0, 'mvt')
>>> core.env.provider.query_zxy("select way as __geometry__ from osm_roads_z5", 5, 5, 12)
>>> core.env.provider.explain_analyze_query("select way as __geometry__ from osm_roads_z5", 5, 5, 12)
```
