from ModestMaps.Core import Point, Coordinate
from ModestMaps.Geo import deriveTransformation, MercatorProjection, LinearProjection, Location
from math import log as _log, pi as _pi

class SphericalMercator(MercatorProjection):
    """ Spherical mercator projection for most commonly-used web map tile scheme.
    """
    srs = '+proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0 +k=1.0 +units=m +nadgrids=@null +wktext +no_defs +over'

    def __init__(self):
        pi = _pi

        # Transform from raw mercator projection to tile coordinates
        t = deriveTransformation(-pi, pi, 0, 0, pi, pi, 1, 0, -pi, -pi, 0, 1)

        MercatorProjection.__init__(self, 0, t)

    def coordinateProj(self, coord):
        """ Convert from Coordinate object to a Point object in EPSG:900913
        """
        # the zoom at which we're dealing with meters on the ground
        diameter = 2 * _pi * 6378137
        zoom = _log(diameter) / _log(2)
        coord = coord.zoomTo(zoom)

        # global offsets
        point = Point(coord.column, coord.row)
        point.x = point.x - diameter/2
        point.y = diameter/2 - point.y

        return point

    def projCoordinate(self, point):
        """ Convert from Point object in EPSG:900913 to a Coordinate object
        """
        # the zoom at which we're dealing with meters on the ground
        diameter = 2 * _pi * 6378137
        zoom = _log(diameter) / _log(2)

        # global offsets
        coord = Coordinate(point.y, point.x, zoom)
        coord.column = coord.column + diameter/2
        coord.row = diameter/2 - coord.row

        return coord

    def locationProj(self, location):
        """ Convert from Location object to a Point object in EPSG:900913
        """
        return self.coordinateProj(self.locationCoordinate(location))

    def projLocation(self, point):
        """ Convert from Point object in EPSG:900913 to a Location object
        """
        return self.coordinateLocation(self.projCoordinate(point))

class WGS84(LinearProjection):
    """ Unprojected projection for the other commonly-used web map tile scheme.
    """
    srs = '+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs'

    def __init__(self):
        p = _pi

        # Transform from geography in radians to tile coordinates
        t = deriveTransformation(-p, p/2, 0, 0, p, p/2, 2, 0, -p, -p/2, 0, 1)

        LinearProjection.__init__(self, 0, t)

    def coordinateProj(self, coord):
        """ Convert from Coordinate object to a Point object in EPSG:4326
        """
        return self.locationProj(self.coordinateLocation(coord))

    def projCoordinate(self, point):
        """ Convert from Point object in EPSG:4326 to a Coordinate object
        """
        return self.locationCoordinate(self.projLocation(point))

    def locationProj(self, location):
        """ Convert from Location object to a Point object in EPSG:4326
        """
        return Point(location.lon, location.lat)

    def projLocation(self, point):
        """ Convert from Point object in EPSG:4326 to a Location object
        """
        return Location(point.y, point.x)

projections = {3857: SphericalMercator(),
               900913: SphericalMercator(),
               4326: WGS84()}

def get_projection(srid):
    """ Retrieve a projection object by srid.
    """
    return projections[srid]
