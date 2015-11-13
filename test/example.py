import jinja2 as j2
import tile_gen.vectiles.transform as transform
import tile_gen.vectiles.sort as sort
import tile_gen.core as core

def get_module(env, template_name):
    return env.get_template(template_name).module

queries_env = j2.Environment(loader=j2.PackageLoader('queries', ''))
roads = get_module(queries_env, 'roads.jinja2').roads
earth = get_module(queries_env, 'earth.jinja2').earth
water = get_module(queries_env, 'water.jinja2').water

core.init_env({"dbinfo": {"user": "zoonmaps",
                     "database": "gis"},
               "layers": {"roads": {"query_fn": roads,
                                    "geometry_types": ["LineString", "MultiLineString"],
                                    "transform_fns": [transform.add_id_to_properties,
                                                      transform.detect_osm_relation,
                                                      transform.road_kind,
                                                      transform.road_classifier,
                                                      transform.road_sort_key,
                                                      transform.road_oneway,
                                                      transform.road_trim_properties,
                                                      transform.remove_feature_id],
                                    "sort_fn": sort.roads},

                          "earth": {"query_fn": earth,
                                    "geometry_types": ["Polygon", "MultiPolygon"],
                                    "transform_fns": [transform.add_id_to_properties,
                                                      transform.detect_osm_relation,
                                                      transform.remove_feature_id],
                                    "sort_fn": sort.earth},

                          "water": {"query_fn": water,
                                    "geometry_types": ["Polygon",
                                                       "MultiPolygon",
                                                       "LineString",
                                                       "MultiLineString"],
                                    "transform_fns": [transform.add_id_to_properties,
                                                      transform.detect_osm_relation,
                                                      transform.remove_feature_id],
                                    "sort_fn": sort.water}}})

# core.get_tile('all', 0, 0, 0, 'mvt')
# core.env.provider.query_bounds(water(0), [0, 0, 1, 1])
# core.env.provider.query_zxy(water(0), 5, 12, 5)
