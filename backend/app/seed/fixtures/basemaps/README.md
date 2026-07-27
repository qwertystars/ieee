# PMTiles Basemap — Rivertown Demo Region

This directory should contain a pre-generated PMTiles basemap for the Rivertown
demo region. The PMTiles file is generated from an OpenStreetMap extract using
[tippecanoe](https://github.com/felt/tippecanoe).

## Generation

```bash
# 1. Download OSM extract for the Rivertown region (bbox: 72.83,19.04,72.93,19.12)
#    Using Geofabrik or Overpass API:
wget https://download.geofabrik.de/asia/india/western-latest.osm.pbf

# 2. Clip to Rivertown bbox using osmium:
osmium extract --bbox=72.83,19.04,72.93,19.12 western-latest.osm.pbf -o rivertown.osm.pbf

# 3. Generate PMTiles with tippecanoe:
tippecanoe --output=rivertown.pmtiles \
  --minimum-zoom=0 --maximum-zoom=14 \
  --layer=roads --layer=buildings --layer=water --layer=landuse \
  --drop-densest-as-needed --extend-zooms-if-still-dropping \
  rivertown.osm.pbf

# 4. Copy to frontend:
cp rivertown.pmtiles ../../../frontend/public/basemaps/rivertown.pmtiles
```

## Note

The PMTiles file is NOT included in the seed package because:
1. tippecanoe may not be installed on all systems
2. The OSM extract requires internet access (violates the "no internet" seed constraint)
3. The file is large (~5-50MB depending on zoom levels)

The frontend map system (T34) falls back to an OSM raster tile source when
PMTiles is not available. Generate and place the file at
`frontend/public/basemaps/rivertown.pmtiles` for offline basemap support.
