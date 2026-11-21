#!/usr/bin/env python3
"""Build data/clark.csv: every Township of Clark address range, its recycling zone and its ward.

Clark does not collect household trash (residents hire private haulers). The township
picks up recycling every other Wednesday in two zones, and bulky items one week a month
(March to October) in each of its four wards. So a zone here is both: "Z1W3" is recycling
Zone 1 in Ward 3.

The zone and ward outlines come from the township's own online map (its "Recycling Zones"
and "Ward Boundaries" layers), saved in data/reference/clark_zones_wards_2026.geojson.
Each house of the county street list (the Board of Elections' list) is put on its Census
block side, 15 meters back from the street, and looked up in those outlines.

Marked to check (Needs_Check):
  - houses within 15 meters of a zone or ward line, or outside both outlines (given the
    nearest), so the answer could be the other side,
  - house numbers the Census does not have (the nearest Census number on the same street),
  - streets the Census does not have (the zone and ward most other houses in the same
    ward and election district are in),
  - houses whose ward on the township's map is not the county list's ward.

This is a developer tool, it is not used by the running website. It needs `pyshp` and
the Census file named in tools/build_kenilworth.py:

    python3 tools/build_clark.py <addrfeat folder>/tl_2025_34039_addrfeat
"""
import collections
import csv
import json
import math
import os
import sys

import shapefile  # pip install pyshp

TOP = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, TOP)

from address_lookup import normalize_street  # noqa: E402

COUNTY_FILE = os.path.join(TOP, 'data', 'reference', 'union_county_street_list_2025.csv')
AREAS_FILE = os.path.join(TOP, 'data', 'reference', 'clark_zones_wards_2026.geojson')
OUT_FILE = os.path.join(TOP, 'data', 'clark.csv')
ZIP_CODE = '07066'

SETBACK = 15   #meters from the street line to a house
NEAR_LINE = 15  #a house this close to a zone or ward line is marked to check

LAT0, LON0 = 40.62, -74.31
KX, KY = 111320 * math.cos(math.radians(LAT0)), 110950


def to_meters(lon, lat):
    return ((lon - LON0) * KX, (lat - LAT0) * KY)


def read_areas():
    """{'recycling_zone': {value: [ring]}, 'ward': {value: [ring]}}, rings in meters."""
    areas = collections.defaultdict(lambda: collections.defaultdict(list))
    with open(AREAS_FILE, encoding='utf-8') as handle:
        for feature in json.load(handle)['features']:
            geometry = feature['geometry']
            polygons = geometry['coordinates'] if geometry['type'] == 'MultiPolygon' else [geometry['coordinates']]
            for polygon in polygons:
                for ring in polygon:
                    areas[feature['properties']['layer']][feature['properties']['value']].append(
                        [to_meters(x, y) for x, y in ring])
    return areas


def inside(rings, p):
    """Even-odd rule over all rings (holes included)."""
    result = False
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            if (y1 > p[1]) != (y2 > p[1]) and p[0] < x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1):
                result = not result
    return result


def distance_to_rings(rings, p):
    best = math.inf
    for ring in rings:
        for a, b in zip(ring, ring[1:] + ring[:1]):
            length = math.dist(a, b)
            if length == 0:
                continue
            t = max(0, min(1, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / length ** 2))
            best = min(best, math.dist(p, (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)))
    return best


def area_of(layer, p):
    """(value, check) of the area p is in; outside every area: the nearest, checked."""
    found = [value for value, rings in layer.items() if inside(rings, p)]
    distances = {value: distance_to_rings(rings, p) for value, rings in layer.items()}
    if len(found) == 1:
        others = [d for value, d in distances.items() if value != found[0]]
        #Near the line between two areas (the town border is not a line between areas)
        return found[0], distances[found[0]] < NEAR_LINE and bool(others) and min(others) < NEAR_LINE * 2
    nearest = min(distances, key=distances.get)
    return nearest, True


def read_census(path):
    """{name: [(low, high, parity, line, is left)]} for the Census ranges in Clark."""
    sides = collections.defaultdict(list)
    for item in shapefile.Reader(path).iterShapeRecords():
        record = item.record.as_dict()
        points = [to_meters(x, y) for x, y in item.shape.points]
        name = normalize_street(record['FULLNAME'] or '')
        for side in 'LR':
            low, high = record[side + 'FROMHN'], record[side + 'TOHN']
            if record['ZIP' + side] != ZIP_CODE or not (low.isdigit() and high.isdigit()):
                continue
            low, high = sorted((int(low), int(high)))
            sides[name].append((low, high, 'E' if low % 2 == 0 else 'O', points, side == 'L'))
    return sides


def read_county():
    rows = []
    with open(COUNTY_FILE, newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            if row['Municipality'] == 'CLARK':
                rows.append((normalize_street(row['Street_Name']), int(row['Low_Range']), int(row['High_Range']),
                             row['Side'], row['Ward'], row['District']))
    return rows


def along(points, fraction, left, setback):
    """The point `fraction` of the way along a line, `setback` meters to one side."""
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    goal = sum(lengths) * fraction
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if goal <= length and length > 0:
            t = goal / length
            dx, dy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
            sign = 1 if left else -1
            return (a[0] + (b[0] - a[0]) * t - sign * dy * setback, a[1] + (b[1] - a[1]) * t + sign * dx * setback)
        goal -= length
    return points[-1]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    areas = read_areas()
    sides = read_census(sys.argv[1])

    out, notes, unplaced = [], [], []
    placed = collections.defaultdict(collections.Counter)
    ward_differs = collections.Counter()
    for name, low, high, side, ward, district in read_county():
        found = [s for s in sides.get(name, []) if s[0] <= high and low <= s[1] and side in (s[2], 'B')]
        check_all = False
        if not found and sides.get(name):
            nearest = min(sides[name], key=lambda s: (min(abs(low - s[0]), abs(low - s[1])), s[2] != side))
            found, check_all = [nearest], True
            notes.append(f'near   {name} {low}-{high}: nearest Census numbers {nearest[0]}-{nearest[1]}')
        if not found:
            unplaced.append((name, low, high, side, ward, district))
            continue
        for c_low, c_high, parity, points, left in found:
            s_low, s_high = (max(low, c_low), min(high, c_high)) if not check_all else (low, high)
            middle = (s_low + s_high) / 2
            fraction = 0.5 if c_high == c_low else max(0.0, min(1.0, (middle - c_low) / (c_high - c_low)))
            p = along(points, fraction, left, SETBACK)
            zone, zone_check = area_of(areas['recycling_zone'], p)
            map_ward, ward_check = area_of(areas['ward'], p)
            check = zone_check or ward_check or check_all
            if map_ward != ward:
                ward_differs[(name, ward, map_ward)] += 1
                check = True
            row_side = side if side != 'B' else ('B' if check_all else parity)
            key = 'Z%sW%s' % (zone, map_ward)
            out.append((name, s_low, s_high, row_side, key, check))
            placed[(ward, district)][key] += 1

    for name, low, high, side, ward, district in unplaced:
        counts = placed[(ward, district)]
        if not counts:
            notes.append(f'skip   {name} {low}-{high}: not on the Census map, no other street in ward {ward} district {district}')
            continue
        key = counts.most_common(1)[0][0]
        out.append((name, low, high, side, key, True))
        notes.append(f'guess  {name} {low}-{high}: {key}, from ward {ward} district {district} {dict(counts)}')
    for (name, ward, map_ward), n in sorted(ward_differs.items()):
        notes.append(f'ward   {name}: county list ward {ward}, township map ward {map_ward} ({n} rows, map used)')

    rows = sorted(set(out))
    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['Municipality', 'Street_Name', 'Low_Range', 'High_Range', 'Side', 'ZIP', 'Zone', 'Needs_Check'])
        for name, low, high, side, zone, check in rows:
            writer.writerow(['CLARK', name, low, high, side, ZIP_CODE, zone, 'Y' if check else ''])
    print('\n'.join(notes))
    counts = collections.Counter(r[4] for r in rows)
    print(f'{len(rows)} rows written to {os.path.normpath(OUT_FILE)}, {sum(1 for r in rows if r[5])} to check; '
          f'by zone: {dict(sorted(counts.items()))}')


if __name__ == '__main__':
    main()
