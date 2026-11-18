#!/usr/bin/env python3
"""Build data/union.csv: every Township of Union address range and its collection zone.

The Township of Union collects in two zones (2026 calendar):
    West Zone, Monday & Thursday   (Stuyvesant Ave to the Springfield border)
    East Zone, Tuesday & Friday    (Stuyvesant Ave to the Elizabeth border)
The township has no wards; its zones are its own and are not the county's
election districts.

Which street is in which zone comes from the DPW's "Collection Routes" street
list (data/reference/union_township_routes_2015.csv, read from
https://www.uniontownship.com/631/Street-Listings-for-Collection). It gives
every street a bulk day (Monday or Tuesday) and a garbage-only day (Thursday or
Friday), so Monday/Thursday streets are the West Zone and Tuesday/Friday streets
the East Zone. It puts each street wholly in one zone.

The house numbers come from the county street list
(data/reference/union_county_street_list_2025.csv). This tool also uses the US
Census address ranges for Union County, to:
  - add streets the route list has but the county list does not,
  - give streets the route list does not have (mostly built after 2015) the zone
    of the streets nearest to them, marked to check,
  - mark to check every listed street whose zone differs from most of the
    streets around it, because the 2015 list may be out of date there.

This is a developer tool, it is not used by the running website. It needs the
`pyshp` package and the Census file named in tools/build_kenilworth.py:

    python3 tools/build_union.py <addrfeat folder>/tl_2025_34039_addrfeat
"""
import collections
import csv
import math
import os
import re
import sys

import shapefile  # pip install pyshp

TOP = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, TOP)

from address_lookup import normalize_street  # noqa: E402

COUNTY_FILE = os.path.join(TOP, 'data', 'reference', 'union_county_street_list_2025.csv')
ROUTES_FILE = os.path.join(TOP, 'data', 'reference', 'union_township_routes_2015.csv')
OUT_FILE = os.path.join(TOP, 'data', 'union.csv')
ZIP_CODES = {'07083', '07088'}    #Union and Vauxhall

#Route list names written differently from the county list (route name -> county names)
ROUTE_NAMES = {
    'ABERDEEN': ['ABERDEEN RD'],
    'APPLETREE LANE': ['APPLE TREE LN'],
    'COLONIAL ROAD WEST': ['COLONIAL RD W'],
    'FREDRICK TERRACE': ['FREDERICK TER'],
    'HUESTON AVENUE': ['HUESTON ST'],
    'HUGENOT AVENUE': ['HUGUENOT AVE'],
    'INDIAN RUN PWAY NO': ['INDIAN RUN PKWY'],
    'INDIAN RUN PWAY SO': ['INDIAN RUN PKWY SOUTH'],
    'KELLER CRECENT': ['KELLER CRES'],
    'LANDSDOWNE AVENUE': ['LANSDOWNE AVE'],
    'MAXWELL STEET': ['MAXWELL ST'],
    'ORCHARD MEADOWS': ['ORCHARD MEADOWS DR N', 'ORCHARD MEADOWS DR S'],
    'OXFORD LAND': ['OXFORD LN'],
    'RAHWAY RVRPARKWAY': ['RAHWAY RIVER PKWY'],
    'REIMER COURT': ['REIMAR CT'],
    'ROSELYN PLLACE': ['ROSELYN PL'],
    'ROUTE 22': ['US 22', 'US HIGHWAY 22 W'],
    'SUMNER AVENUE': ['SUMNER AVE', 'E SUMNER AVE', 'W SUMNER AVE'],
    'SWANSTROM PLACE': ['SWANSTROM PL E'],
    'TRAVERS STEET': ['TRAVERS ST'],
    'UNION CO. PARKWAY': ['UNION COUNTY PKWY'],
}

#County list typos, written to data/union.csv with the right spelling
COUNTY_NAMES = {
    'BASHFORD': 'BASHFORD AVE',
    'BURNETT AVE': 'BURNET AVE',
    'COLONIAL AVE W': 'COLONIAL AVE',
    'COLONIAL RD WEST': 'COLONIAL RD W',
    'FAIRWAY DR SOUTH': 'S FAIRWAY DR',
    'GIRARD PLACE C': 'GIRARD PL',
    'KELLER CRESCENT': 'KELLER CRES',
    'PATRIOT WY': 'PATRIOT WAY',
    'REID SR': 'REID ST',
    'ROSEMONT AVE N': 'ROSEMONT AVE',
    'VANNESS TER': 'VAN NESS TER',
    'VERMELLA WY': 'VERMELLA WAY',
    'WOOLLEY ABE': 'WOOLLEY AVE',
}

#Route list entries that are buildings, not streets
NOT_STREETS = re.compile(r'SCHOOL|H\.S|PLAZA')

#County list names that are not homes the DPW collects from: Kean University
#buildings, and streets of other towns filed under Union
SKIP_COUNTY = re.compile(r'^KEAN COLLEGE|^PO BOX')

SUFFIX_DIRECTIONS = {'NORTH': 'N', 'NO': 'N', 'N': 'N', 'SOUTH': 'S', 'SO': 'S', 'EAST': 'E', 'WEST': 'W'}

#How many nearby streets are asked when a street's zone is checked or guessed
NEIGHBORS = 6

#One degree of longitude is shorter than one degree of latitude this far north
LON_SCALE = math.cos(math.radians(40.69))
METERS_PER_DEGREE = 111000


def route_keys(name):
    """The ways a route list name may be written in the county list, most likely first.

    "ANDREW ST NORTH" -> "N ANDREW ST", "ANDREW ST"
    """
    name = name.replace('TERR.', 'TERRACE').replace('AVE.', 'AVENUE').replace('ST.', 'STREET').rstrip('.')
    words = name.split()
    keys = [normalize_street(name)]
    if len(words) >= 3 and words[-1] in SUFFIX_DIRECTIONS:
        rest = ' '.join(words[:-1])
        keys += [normalize_street(SUFFIX_DIRECTIONS[words[-1]] + ' ' + rest), normalize_street(rest)]
    if words[0] in ('NORTH', 'SOUTH', 'EAST', 'WEST'):
        keys.append(normalize_street(words[0][0] + ' ' + ' '.join(words[1:])))
    return keys


def read_county():
    """County rows for Union, grouped by tidied street name."""
    streets = collections.defaultdict(list)
    with open(COUNTY_FILE, newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            if row['Municipality'] == 'UNION' and not SKIP_COUNTY.search(row['Street_Name']):
                row['Street_Name'] = COUNTY_NAMES.get(row['Street_Name'], row['Street_Name'])
                streets[normalize_street(row['Street_Name'])].append(row)
    return streets


def read_routes(county):
    """Return {tidied county street name: zone} and the route streets the county list lacks."""
    zones, missing = {}, {}
    with open(ROUTES_FILE, newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            name, zone = row['Street'].rstrip('.'), row['Zone']
            if NOT_STREETS.search(name):
                continue
            if name in ROUTE_NAMES:
                keys = [normalize_street(n) for n in ROUTE_NAMES[name]]
            else:
                keys = [next((k for k in route_keys(name) if k in county), None)]
            found = [k for k in keys if k in county]
            for key in found:
                if zones.get(key, zone) != zone:
                    sys.exit(f'{key} is in both zones in the route list')
                zones[key] = zone
            if not found:
                missing[route_keys(name)[-1] if name not in ROUTE_NAMES else keys[0]] = zone
    return zones, missing


def read_census(path):
    """Census blocks in Union's ZIP codes: {tidied name: [(points, ranges)]}."""
    blocks = collections.defaultdict(list)
    for item in shapefile.Reader(path).iterShapeRecords():
        record = item.record.as_dict()
        if not ({record['ZIPL'], record['ZIPR']} & ZIP_CODES):
            continue
        points = [(x * LON_SCALE, y) for x, y in item.shape.points]
        ranges = []
        for side in 'LR':
            low, high = record[side + 'FROMHN'], record[side + 'TOHN']
            if record['ZIP' + side] in ZIP_CODES and low.isdigit() and high.isdigit():
                low, high = sorted((int(low), int(high)))
                ranges.append((low, high, 'E' if low % 2 == 0 else 'O'))
        blocks[normalize_street(record['FULLNAME'] or '')].append((points, ranges))
    return blocks


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1]) * METERS_PER_DEGREE


def nearest_zones(street, zones, blocks):
    """Zones of the NEIGHBORS listed streets that come closest to `street`."""
    mine = [p for points, _ in blocks[street] for p in points]
    sample = mine[::max(1, len(mine) // 30)]
    found = []
    for other, zone in zones.items():
        if other == street or other not in blocks:
            continue
        theirs = [p for points, _ in blocks[other] for p in points]
        theirs = theirs[::max(1, len(theirs) // 30)]
        found.append((min(distance(a, b) for a in sample for b in theirs), zone))
    return collections.Counter(zone for _, zone in sorted(found)[:NEIGHBORS])


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    county = read_county()
    zones, route_only = read_routes(county)
    blocks = read_census(sys.argv[1])

    check, notes = set(), []
    #Listed streets whose neighbors are mostly in the other zone
    for street, zone in sorted(zones.items()):
        if street in blocks:
            votes = nearest_zones(street, zones, blocks)
            if votes[zone] * 2 < sum(votes.values()):
                check.add(street)
                notes.append(f'check  {street}: listed {zone}, nearby streets {dict(votes)}')
    #County streets the route list does not have
    guessed = {}
    for street in sorted(set(county) - set(zones)):
        if street not in blocks:
            notes.append(f'skip   {street}: not on the route list and not on the Census map of Union')
            continue
        votes = nearest_zones(street, zones, blocks)
        guessed[street] = votes.most_common(1)[0][0]
        notes.append(f'guess  {street}: {guessed[street]} from nearby streets {dict(votes)}')

    out = set()
    for street, rows in county.items():
        zone = zones.get(street) or guessed.get(street)
        if zone is None:
            continue
        sure = street in zones and street not in check
        for row in rows:
            out.add((row['Street_Name'], int(row['Low_Range']), int(row['High_Range']), row['Side'], zone, '' if sure else 'Y'))
    #Route streets the county list lacks, with the Census house numbers
    for street, zone in sorted(route_only.items()):
        ranges = [r for _, rs in blocks.get(street, []) for r in rs]
        if not ranges:
            notes.append(f'none   {street}: on the route list, no house numbers known')
            continue
        for low, high, side in ranges:
            out.add((street, low, high, side, zone, ''))
        notes.append(f'census {street}: {zone}, {len(ranges)} ranges from the Census')

    rows = sorted(out)
    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['Municipality', 'Street_Name', 'Low_Range', 'High_Range', 'Side', 'ZIP', 'Zone', 'Needs_Check'])
        for street, low, high, side, zone, flag in rows:
            #No ZIP: Union is split between 07083 and 07088 and a wrong one would hide the row
            writer.writerow(['UNION', street, low, high, side, '', zone, flag])
    print('\n'.join(notes))
    print(f'{len(rows)} rows written to {os.path.normpath(OUT_FILE)}')


if __name__ == '__main__':
    main()
