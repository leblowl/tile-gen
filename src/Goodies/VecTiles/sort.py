# sort functions to apply to features


def _sort_features_by_key(features, key):
    features.sort(key=key)
    return features


def _by_feature_property(property_name):
    def _feature_sort_by_property(feature):
        wkb, properties, fid = feature
        return properties.get(property_name)
    return _feature_sort_by_property


_by_feature_id = _by_feature_property('id')


def _sort_by_area_then_id(features):
    features.sort(key=_by_feature_id)
    features.sort(key=_by_feature_property('area'), reverse=True)
    return features


def _by_scalerank(feature):
    wkb, properties, fid = feature
    value_for_none = 1000
    scalerank = properties.get('scalerank', value_for_none)
    return scalerank


def _by_population(feature):
    wkb, properties, fid = feature
    value_for_none = -1000
    population = properties.get('population', value_for_none)
    return population


def _sort_by_scalerank_then_population(features):
    features.sort(key=_by_population, reverse=True)
    features.sort(key=_by_scalerank)
    return features


def buildings(features):
    return _sort_by_area_then_id(features)


def earth(features):
    return _sort_features_by_key(features, _by_feature_id)


def landuse(features):
    return _sort_by_area_then_id(features)


def places(features):
    return _sort_by_scalerank_then_population(features)


def pois(features):
    return _sort_features_by_key(features, _by_feature_id)


def roads(features):
    return _sort_features_by_key(features, _by_feature_property('sort_key'))


def water(features):
    return _sort_by_area_then_id(features)


def transit(features):
    return _sort_features_by_key(features, _by_feature_id)
