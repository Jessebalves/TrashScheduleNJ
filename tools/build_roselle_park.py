#!/usr/bin/env python3
"""Build data/roselle_park.csv: every Borough of Roselle Park address range and its collection zone.

Roselle Park's 2026 Curbside Collection Calendar splits the borough by Chestnut Street,
like its neighbor Roselle, but with the days the other way round:
    east side   garbage Tuesday & Friday, vegetative waste Thursday, bulk last Friday
    west side   garbage Monday & Thursday, vegetative waste Friday,  bulk last Thursday
Chestnut St itself from Westfield Ave to Grant Ave (the business strip, house numbers
100-299) has garbage four times a week, Monday, Tuesday, Thursday and Friday.

Zones:
    E, W      east and west of Chestnut St
    CE, CW    Chestnut St from Westfield Ave to Grant Ave, odd (east side) and even
              (west side) numbers: garbage four days, the rest by their side

The addresses are the county street list's Roselle Park rows
(data/reference/union_county_street_list_2025.csv). The side of Chestnut St comes from
the US Census address ranges, as in tools/build_roselle.py: every house range is put a
few meters off its street, on its own side, and compared with the line of Chestnut St.

Marked to check (Needs_Check):
  - houses on Chestnut St north of Grant Ave: the calendar does not say which side they
    count as; odd numbers (east side of the street) get E, even numbers W,
  - house numbers the Census does not have, on a street that crosses Chestnut St
    (they get the side of the nearest Census number),
  - streets the Census does not have: they get the side most other streets in the same
    ward and election district have,
  - a row whose E or W in its name disagrees with the side the Census puts it on.

This is a developer tool, it is not used by the running website. It needs the
`pyshp` package and the Census file named in tools/build_kenilworth.py:

    python3 tools/build_roselle_park.py <addrfeat folder>/tl_2025_34039_addrfeat
"""
import collections
import csv
import os
import sys

import shapefile  # pip install pyshp

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.join(HERE, '..')
sys.path.insert(0, TOP)
sys.path.insert(0, HERE)

from address_lookup import normalize_street  # noqa: E402
#The Chestnut St line and the side test are the same as Roselle's
from build_roselle import LON_SCALE, offset_point, side_of_chestnut, read_census as read_roselle_census  # noqa: E402

COUNTY_FILE = os.path.join(TOP, 'data', 'reference', 'union_county_street_list_2025.csv')
OUT_FILE = os.path.join(TOP, 'data', 'roselle_park.csv')
ZIP_CODE = '07204'

#Chestnut St house numbers from Westfield Ave to Grant Ave (Census: the 100 block starts
#at Westfield Ave, Grant Ave is between the 200 and the 300 block)
BUSINESS_STRIP = (100, 299)

#County list spellings that are typing slips -> the street's name
COUNTY_NAMES = {
    'E WESFIELDAV AP 303': 'E WESTFIELD AVE',
    'MAPLE SREET': 'MAPLE ST',
    'WSUMNER AVE': 'W SUMNER AVE',
}


def census_name(full_name):
    """The Census writes "Westfield Ave W" where the county list has "W WESTFIELD AVE"."""
    words = normalize_street(full_name).split()
    if len(words) >= 3 and words[-1] in ('E', 'W'):
        words = [words[-1]] + words[:-1]
    return ' '.join(words)


def read_census(path):
    """Census house ranges in Roselle Park: {name: [(low, high, parity, point)]}."""
    ranges = collections.defaultdict(list)
    for item in shapefile.Reader(path).iterShapeRecords():
        record = item.record.as_dict()
        name = census_name(record['FULLNAME'] or '')
        points = [(x * LON_SCALE, y) for x, y in item.shape.points]
        for side in 'LR':
            low, high = record[side + 'FROMHN'], record[side + 'TOHN']
            if record['ZIP' + side] != ZIP_CODE or not (low.isdigit() and high.isdigit()):
                continue
            low, high = sorted((int(low), int(high)))
            ranges[name].append((low, high, 'E' if low % 2 == 0 else 'O', offset_point(points, side == 'L')))
    return ranges


def read_county():
    """Roselle Park rows of the county list: [(name, low, high, side, ward, district)]."""
    rows = []
    with open(COUNTY_FILE, newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            if row['Municipality'] == 'ROSELLE PARK':
                #The county list too has a few "WESTFIELD AVE W"
                name = census_name(row['Street_Name'])
                rows.append((COUNTY_NAMES.get(name, name), int(row['Low_Range']), int(row['High_Range']),
                             row['Side'], row['Ward'], row['District']))
    return rows


def chestnut_rows(low, high, side):
    """A Chestnut St row cut into (low, high, side, zone, check) by side of the street and the strip."""
    out = []
    for parity, where in (('O', 'E'), ('E', 'W')):
        if side not in (parity, 'B'):
            continue
        for s_low, s_high, strip in ((low, min(high, BUSINESS_STRIP[1]), True),
                                     (max(low, BUSINESS_STRIP[1] + 1), high, False)):
            if s_low > s_high:
                continue
            if strip and s_low < BUSINESS_STRIP[0]:
                continue
            out.append((s_low, s_high, parity, ('C' + where) if strip else where, not strip))
    return out


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    census = read_census(sys.argv[1])
    _, line = read_roselle_census(sys.argv[1])
    if len(line) < 10:
        sys.exit('Chestnut St was not found on the Census map')
    #Every side each street is seen on
    street_sides = {name: {side_of_chestnut(r[3], line)[0] for r in found} for name, found in census.items()}

    out, notes, unplaced = [], [], []
    placed = collections.defaultdict(collections.Counter)
    for name, low, high, side, ward, district in read_county():
        if name == 'CHESTNUT ST':
            for s_low, s_high, s_side, zone, check in chestnut_rows(low, high, side):
                out.append((name, s_low, s_high, s_side, zone, check))
            continue
        found = [r for r in census.get(name, []) if r[0] <= high and low <= r[1] and side in (r[2], 'B')]
        if found:
            sides = {side_of_chestnut(r[3], line)[0] for r in found}
            if len(sides) > 1:
                #Not expected off Chestnut St: keep the row whole, on the side most of it is on
                counts = collections.Counter(side_of_chestnut(r[3], line)[0] for r in found)
                where, check = counts.most_common(1)[0][0], True
                notes.append(f'mixed  {name} {low}-{high}: {dict(counts)}')
            else:
                where, check = sides.pop(), False
        elif len(street_sides.get(name, ())) == 1:
            #A house number the Census does not have, on a street wholly on one side
            where, check = next(iter(street_sides[name])), False
        elif street_sides.get(name):
            candidates = [(min(abs(low - r[0]), abs(low - r[1])), r) for r in census[name]]
            where = side_of_chestnut(min(candidates, key=lambda c: c[0])[1][3], line)[0]
            check = True
            notes.append(f'near   {name} {low}-{high}: {where} from the nearest Census number')
        else:
            unplaced.append((name, low, high, side, ward, district))
            continue
        words = name.split()
        if len(words) >= 3 and words[0] in ('E', 'W') and words[0] != where:
            check = True
            notes.append(f'name   {name} {low}-{high}: the Census puts it on the {where} side')
        out.append((name, low, high, side, where, check))
        placed[(ward, district)][where] += 1

    for name, low, high, side, ward, district in unplaced:
        counts = placed[(ward, district)]
        words = name.split()
        if len(words) >= 3 and words[0] in ('E', 'W'):
            where = words[0]
            notes.append(f'prefix {name} {low}-{high}: not on the Census map, {where} from its name')
        elif counts:
            where = counts.most_common(1)[0][0]
            notes.append(f'guess  {name} {low}-{high}: {where}, from ward {ward} district {district} {dict(counts)}')
        else:
            notes.append(f'skip   {name} {low}-{high}: not on the Census map, no other street in ward {ward} district {district}')
            continue
        out.append((name, low, high, side, where, True))

    rows = sorted(set(out))
    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['Municipality', 'Street_Name', 'Low_Range', 'High_Range', 'Side', 'ZIP', 'Zone', 'Needs_Check'])
        for name, low, high, side, zone, check in rows:
            writer.writerow(['ROSELLE PARK', name, low, high, side, ZIP_CODE, zone, 'Y' if check else ''])
    print('\n'.join(notes))
    zones = collections.Counter(r[4] for r in rows)
    print(f'{len(rows)} rows written to {os.path.normpath(OUT_FILE)}, '
          f'{sum(1 for r in rows if r[5])} to check; by zone: {dict(sorted(zones.items()))}')


if __name__ == '__main__':
    main()
