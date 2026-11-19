#!/usr/bin/env python3
"""Build data/aberdeen.csv: every Aberdeen Township (Monmouth County) address range and its section.

Aberdeen collects in two sections (2026 Community Calendar, "Trash & Recycling Pick-Up
Schedule for Single-Family Residences"):
    Section I   Monday & Thursday: Cliffwood Beach, Cliffwood, River Gardens, Oakshades,
                Freneau, Heritage Estates
    Section II  Tuesday & Friday: Strathmore, High School Area, Woodbrook Drive, Randall Way,
                Storyland, Santa Fe, Heather Glen, Clinton Street
The township names neighborhoods only, it publishes no street list. So the sections come from:
  1. Streets checked one by one in the township's Recycle Coach app (SECTION_STREETS, 2026-11-19).
  2. The Census places Cliffwood Beach (Section I) and Strathmore (Section II), and ZIP code
     07721 (Cliffwood, Section I).
  3. Every other house range gets the section of the nearest ranges placed by 1 or 2. It is
     marked to check (Needs_Check) when those neighbors do not all agree.

The house numbers come from the US Census address ranges, kept when the house is inside the
Census boundary of Aberdeen Township. Streets Recycle Coach does not know (NOT_ABERDEEN) are
left out: they are in Matawan or Old Bridge even where the Census map puts them in Aberdeen.
Streets next to those, and Texas Rd on the Old Bridge border, are marked to check.

Condominium and apartment complexes are not collected by the township. The Census does not
say which addresses those are, so they are in the table like any other address; the town
file's notes tell visitors.

This is a developer tool, it is not used by the running website. It needs the `pyshp`
package and three Census TIGER/Line 2025 files:
    https://www2.census.gov/geo/tiger/TIGER2025/ADDRFEAT/tl_2025_34025_addrfeat.zip
    https://www2.census.gov/geo/tiger/TIGER2025/COUSUB/tl_2025_34_cousub.zip
    https://www2.census.gov/geo/tiger/TIGER2025/PLACE/tl_2025_34_place.zip

    python3 tools/build_aberdeen.py <folder with the three unzipped folders>
"""
import collections
import csv
import math
import os
import sys

import shapefile  # pip install pyshp

TOP = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, TOP)

from address_lookup import normalize_street  # noqa: E402

OUT_FILE = os.path.join(TOP, 'data', 'aberdeen.csv')

#Looked up in Recycle Coach, 2026-11-19
SECTION_STREETS = {
    '1': ['WILSON AVE', 'EUCLID AVE', 'SPRINGLAWN AVE', 'MONASTERY LN', 'HARRISON AVE',
          'GERARD AVE', 'BELAIRE DR', 'CLIFFWOOD AVE'],
    '2': ['1ST ST', 'WATER ST', 'LAKE BLVD', 'LENNY CT', 'WHITE OAK LN', 'VAN BRACKLE RD',
          'INVERNESS CT', 'HEATHER GLEN DR', 'CHURCH ST'],
}
#Recycle Coach: not in Aberdeen Township
NOT_ABERDEEN = {'ABERDEEN RD', 'MATAWAN TER', 'FAWN DR', 'GREENWOOD RD', 'OLD BRIDGE MATAWAN RD'}
#Next to the streets above, or on the Old Bridge border: kept, but marked to check
NEAR_NOT_ABERDEEN = {'CROSS RD', 'TREEHAVEN', 'TEXAS RD'}
PLACE_SECTIONS = {'Cliffwood Beach': '1', 'Strathmore': '2'}
ZIP_SECTIONS = {'07721': '1'}
#How many placed neighbors vote on an unplaced house range
NEIGHBORS = 6

LON_SCALE = math.cos(math.radians(40.43))
METERS_PER_DEGREE = 111000
HOUSE_OFFSET = 12 / METERS_PER_DEGREE


def polygon_parts(shape):
    ends = list(shape.parts) + [len(shape.points)]
    return [[(x * LON_SCALE, y) for x, y in shape.points[a:b]] for a, b in zip(ends, ends[1:])]


def inside(parts, point):
    x, y = point
    found = False
    for ring in parts:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                found = not found
    return found


def offset_point(points, left):
    """The middle of a street segment, moved HOUSE_OFFSET to its left or right side."""
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    half = sum(lengths) / 2
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if half <= length and length > 0:
            t = half / length
            dx, dy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
            sign = 1 if left else -1
            return (a[0] + (b[0] - a[0]) * t - sign * dy * HOUSE_OFFSET,
                    a[1] + (b[1] - a[1]) * t + sign * dx * HOUSE_OFFSET)
        half -= length
    return points[len(points) // 2]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    folder = sys.argv[1]
    cousub = shapefile.Reader(os.path.join(folder, 'tl_2025_34_cousub', 'tl_2025_34_cousub'))
    township = [polygon_parts(item.shape) for item in cousub.iterShapeRecords()
                if item.record['COUNTYFP'] == '025' and item.record['NAME'] == 'Aberdeen'][0]
    place = shapefile.Reader(os.path.join(folder, 'tl_2025_34_place', 'tl_2025_34_place'))
    places = {item.record['NAME']: polygon_parts(item.shape) for item in place.iterShapeRecords()
              if item.record['NAME'] in PLACE_SECTIONS}
    by_street = {street: section for section, streets in SECTION_STREETS.items() for street in streets}

    #(street, low, high, side, zip, point, section or None, how)
    ranges, skipped = [], collections.Counter()
    addrfeat = shapefile.Reader(os.path.join(folder, 'tl_2025_34025_addrfeat', 'tl_2025_34025_addrfeat'))
    for item in addrfeat.iterShapeRecords():
        record = item.record.as_dict()
        street = normalize_street(record['FULLNAME'] or '')
        if not street:
            continue
        points = [(x * LON_SCALE, y) for x, y in item.shape.points]
        for side in 'LR':
            low, high = record[side + 'FROMHN'], record[side + 'TOHN']
            if not (low.isdigit() and high.isdigit()):
                continue
            point = offset_point(points, side == 'L')
            if not inside(township, point):
                continue
            if street in NOT_ABERDEEN:
                skipped[street] += 1
                continue
            low, high = sorted((int(low), int(high)))
            zip_code = record['ZIP' + side]
            section, how = by_street.get(street), 'checked'
            if section is None:
                section = next((s for name, s in PLACE_SECTIONS.items() if inside(places[name], point)), None)
                how = 'place'
            if section is None and zip_code in ZIP_SECTIONS:
                section, how = ZIP_SECTIONS[zip_code], 'zip'
            ranges.append([street, low, high, 'E' if low % 2 == 0 else 'O', zip_code, point, section, how])

    placed = [r for r in ranges if r[6] is not None]
    notes = collections.defaultdict(collections.Counter)
    for r in ranges:
        if r[6] is not None:
            continue
        nearest = sorted(placed, key=lambda p: math.dist(p[5], r[5]))[:NEIGHBORS]
        votes = collections.Counter(p[6] for p in nearest)
        r[6] = votes.most_common(1)[0][0]
        r[7] = 'nearest' if len(votes) == 1 else 'check'
        notes[r[0]][r[7] + ' ' + r[6]] += 1

    rows = sorted({(r[0], r[1], r[2], r[3], '', r[6], r[7] == 'check' or r[0] in NEAR_NOT_ABERDEEN)
                   for r in ranges})
    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['Municipality', 'Street_Name', 'Low_Range', 'High_Range', 'Side', 'ZIP', 'Zone', 'Needs_Check'])
        for street, low, high, side, zip_code, section, check in rows:
            #No ZIP: Aberdeen's postal ZIPs (07747, 07735, 07721) cross its sections and the
            #Census ZIP is not always the postal one, and a wrong one would hide the row
            writer.writerow(['ABERDEEN', street, low, high, side, '', section, 'Y' if check else ''])

    for street, counts in sorted(notes.items()):
        print(f'{street:28s} {dict(counts)}')
    print('left out (not Aberdeen):', dict(skipped))
    how = collections.Counter(r[7] for r in ranges)
    print(f'{len(rows)} rows written to {os.path.normpath(OUT_FILE)}; by section '
          f'{dict(collections.Counter(r[5] for r in rows))}; how: {dict(how)}')


if __name__ == '__main__':
    main()
