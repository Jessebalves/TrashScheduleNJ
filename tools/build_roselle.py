#!/usr/bin/env python3
"""Build data/roselle.csv: every Borough of Roselle address range and its collection zone.

Roselle's 2026/2027 Sanitation/Recycling Schedule splits the borough two ways:
    Garbage and bulk:      by the side of Chestnut Street ("Chestnut Street is the
                           dividing factor"). East side Monday & Thursday, bulk on the
                           1st Wednesday; west side Tuesday & Friday, bulk on the 3rd.
    Recycling, leaves and  by ward: 1st ward Monday ... 5th ward Friday.
    vegetative waste:
So a zone is the side and the ward together: "E3" is east of Chestnut St in the 3rd ward.

The wards come from the county street list
(data/reference/union_county_street_list_2025.csv, the Board of Elections' list).
The side of Chestnut St comes from the US Census address ranges: every house range
is put a few meters off its street, on its own side, and compared with the line of
Chestnut St (extended past its ends with the Chestnut St segments in Roselle Park
and Linden).

Marked to check (Needs_Check):
  - houses south of where Chestnut St ends (near St Georges Ave) and close to its extended line,
  - houses on Chestnut St itself: the schedule does not say which side they count as;
    they get the side of the street they are on (odd numbers east, even numbers west),
  - house numbers the Census does not have, on a street that crosses Chestnut St,
  - streets the Census does not have at all: they get the side most other streets
    in the same ward and election district have.

This is a developer tool, it is not used by the running website. It needs the
`pyshp` package and the Census file named in tools/build_kenilworth.py:

    python3 tools/build_roselle.py <addrfeat folder>/tl_2025_34039_addrfeat
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

COUNTY_FILE = os.path.join(TOP, 'data', 'reference', 'union_county_street_list_2025.csv')
OUT_FILE = os.path.join(TOP, 'data', 'roselle.csv')
ZIP_CODE = '07203'

#County list spellings -> the Census names to look the street up under, in order.
#The first name is also the one written to data/roselle.csv.
#"1 2 MYRTLE ST" is a half number ("114 1/2 Myrtle St") that lost its slash.
COUNTY_NAMES = {
    '1 2 E 1ST AVE': ['E 1ST AVE'],
    '1 2 E 9TH AVE': ['E 9TH AVE', '9TH AVE'],
    '1 2 MORRIS ST': ['MORRIS ST'],
    '1 2 MYRTLE ST': ['MYRTLE ST'],
    '12 TH AVE': ['E 12TH AVE', '12TH AVE'],
    'E 12 TH AVE': ['E 12TH AVE', '12TH AVE'],
    'E 11 TH AVE': ['E 11TH AVE'],
    'EAS 5TH AVE': ['E 5TH AVE'],
    'W 2ND ST': ['W 2ND AVE'],
    #In ward 4, which is all west of Chestnut St
    '1ST AVE': ['W 1ST AVE'],
    '7TH AVE': ['E 7TH AVE', 'W 7TH AVE'],
    'C LILY CT': ['LILY CT'],
    'LILLY CT': ['LILY CT'],
    'GREENWAY BOULAVARD': ['GREENWAY BLVD'],
    'PARK VIEW DR': ['PARKVIEW DR'],
    'PARVIEW DR': ['PARKVIEW DR'],
    'E GARDEN DR': ['GARDEN DR'],
    'SAINT GEORGE AVE': ['SAINT GEORGES AVE', 'E SAINT GEORGES AVE'],
    'ST GEORGE AVE': ['SAINT GEORGES AVE', 'E SAINT GEORGES AVE'],
    'E SAINT GEORGE AVE': ['E SAINT GEORGES AVE', 'SAINT GEORGES AVE'],
    'E ST GEORGE AVE': ['E SAINT GEORGES AVE', 'SAINT GEORGES AVE'],
    'E ST GEORGES AVE': ['E SAINT GEORGES AVE', 'SAINT GEORGES AVE'],
}

#One degree of longitude is shorter than one degree of latitude this far north
LON_SCALE = math.cos(math.radians(40.65))
METERS_PER_DEGREE = 111000
#How far off the middle of the street a house is put, in degrees of latitude
HOUSE_OFFSET = 12 / METERS_PER_DEGREE
#Past the south end of Chestnut St, houses closer than this to its extended line (meters) are checked
NEAR_END = 150
#Chestnut St segments outside Roselle used to extend its line (Roselle Park, Linden)
CHESTNUT_LON = (-74.275, -74.25)


def lookup_names(county_name):
    """The Census names to try for a county list street name."""
    if county_name in COUNTY_NAMES:
        return COUNTY_NAMES[county_name]
    words = county_name.split()
    names = [county_name]
    #"W 5TH AVE" is "5th Ave" on parts of the Census map
    if len(words) >= 3 and words[0] in ('E', 'W'):
        names.append(' '.join(words[1:]))
    return names


def read_county():
    """Roselle rows of the county list: [(name, low, high, side, ward, district)]."""
    rows = []
    with open(COUNTY_FILE, newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            if row['Municipality'] == 'ROSELLE':
                rows.append((normalize_street(row['Street_Name']), int(row['Low_Range']), int(row['High_Range']),
                             row['Side'], row['Ward'], row['District']))
    return rows


def offset_point(points, left):
    """The middle of a street segment, moved HOUSE_OFFSET to its left or right side."""
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    half = sum(lengths) / 2
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if half <= length and length > 0:
            t = half / length
            x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            dx, dy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
            #Left of the direction of travel is (-dy, dx)
            sign = 1 if left else -1
            return x - sign * dy * HOUSE_OFFSET, y + sign * dx * HOUSE_OFFSET
        half -= length
    return points[len(points) // 2]


def read_census(path):
    """Census house ranges in Roselle and the line of Chestnut St.

    Returns ({tidied name: [(low, high, parity, point)]}, [Chestnut St points, north to south]).
    """
    ranges = collections.defaultdict(list)
    chestnut = []
    for item in shapefile.Reader(path).iterShapeRecords():
        record = item.record.as_dict()
        name = normalize_street(record['FULLNAME'] or '')
        points = [(x * LON_SCALE, y) for x, y in item.shape.points]
        if name == 'CHESTNUT ST' and all(CHESTNUT_LON[0] < x < CHESTNUT_LON[1] for x, _ in item.shape.points):
            chestnut.append(points)
        for side in 'LR':
            low, high = record[side + 'FROMHN'], record[side + 'TOHN']
            if record['ZIP' + side] != ZIP_CODE or not (low.isdigit() and high.isdigit()):
                continue
            low, high = sorted((int(low), int(high)))
            ranges[name].append((low, high, 'E' if low % 2 == 0 else 'O', offset_point(points, side == 'L')))
    #Chestnut St runs roughly north to south: one line of points from north to south
    line = sorted({p for segment in chestnut for p in segment}, key=lambda p: -p[1])
    return ranges, line


def side_of_chestnut(point, line):
    """'E' or 'W': which side of Chestnut St a point is on, and how far from it in meters."""
    x, y = point
    #The two line points around this latitude, or the end segment past either end
    for a, b in zip(line, line[1:]):
        if b[1] <= y <= a[1]:
            break
    else:
        a, b = (line[0], line[1]) if y > line[0][1] else (line[-2], line[-1])
    t = (y - a[1]) / (b[1] - a[1]) if b[1] != a[1] else 0
    line_x = a[0] + (b[0] - a[0]) * t
    return ('E' if x > line_x else 'W'), abs(x - line_x) * METERS_PER_DEGREE


def parity_matches(side, parity):
    return side == 'B' or side == parity


def place_row(name, low, high, side, ward, district, census, line, street_sides, out, notes, unplaced):
    """Give one county list row its zone, adding the result to out (or to unplaced)."""
    names = [n for n in lookup_names(name) if n in census]
    #"W 5TH AVE" falls back to "5TH AVE" only when the Census has no "W 5TH AVE" at all;
    #"E 9TH AVE" and "9TH AVE" are two streets
    if name in census and name not in COUNTY_NAMES:
        names = [name]
    out_name = (names or lookup_names(name))[0]
    #The first name that has these house numbers: "E 1ST AVE" and "1ST AVE" are two streets
    found = []
    for n in names:
        found = [(n, r) for r in census[n] if r[0] <= high and low <= r[1] and parity_matches(side, r[2])]
        if found:
            names = [n]
            break
    if found:
        #Cut the county range where the Census ranges change side
        pieces = collections.defaultdict(list)
        for n, (c_low, c_high, parity, point) in found:
            pieces[side_of_chestnut(point, line)[0]].append((max(low, c_low), min(high, c_high), parity))
        #Past the south end of Chestnut St its line is only extended, so ask to confirm
        check = name == 'CHESTNUT ST' or any(r[3][1] < line[-1][1] and side_of_chestnut(r[3], line)[1] < NEAR_END
                                             for _, r in found)
        if len(pieces) == 1:
            [(where, _)] = pieces.items()
            out.append((out_name, low, high, side, where + ward, check))
        else:
            for where, spans in pieces.items():
                #A "both sides" row on Chestnut St is cut into its odd and its even houses
                for s_low, s_high, parity in spans:
                    out.append((out_name, s_low, s_high, parity if side == 'B' else side, where + ward, check))
            notes.append(f'split  {name} {low}-{high}: {dict(pieces)}')
        return
    names = names[:1]
    sides = set().union(*(street_sides[n] for n in names)) if names else set()
    if len(sides) == 1:
        #A house number the Census does not have, on a street wholly on one side
        out.append((out_name, low, high, side, sides.pop() + ward, name == 'CHESTNUT ST'))
    elif sides:
        #Nearest Census number on the same street
        candidates = [(min(abs(low - r[0]), abs(low - r[1])), r) for n in names for r in census[n]]
        _, nearest = min(candidates, key=lambda c: c[0])
        where = side_of_chestnut(nearest[3], line)[0]
        out.append((out_name, low, high, side, where + ward, True))
        notes.append(f'near   {name} {low}-{high}: {where}, from Census {nearest[0]}-{nearest[1]}')
    else:
        unplaced.append((name, low, high, side, ward, district))


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    county = read_county()
    census, line = read_census(sys.argv[1])
    if len(line) < 10:
        sys.exit('Chestnut St was not found on the Census map')

    #Every side each street is seen on, to know which streets cross Chestnut St
    street_sides = {name: {side_of_chestnut(r[3], line)[0] for r in found} for name, found in census.items()}

    out, notes, unplaced = [], [], []
    #Sides placed so far in each (ward, election district)
    placed = collections.defaultdict(collections.Counter)
    #(ward, district) of each row in out, by position
    districts = []
    for name, low, high, side, ward, district in county:
        before = len(out)
        place_row(name, low, high, side, ward, district, census, line, street_sides, out, notes, unplaced)
        placed[(ward, district)].update(row[4][0] for row in out[before:])
        districts += [(ward, district)] * (len(out) - before)

    #A row on the other side from nearly all of its election district may be on a street
    #the Census names the same way as another one ("1ST AVE" for "W 1ST AVE")
    for n, (row, key) in enumerate(zip(out, districts)):
        counts = placed[key]
        if not row[5] and counts[row[4][0]] * 10 < sum(counts.values()):
            out[n] = row[:5] + (True,)
            notes.append(f'odd    {row[0]} {row[1]}-{row[2]}: {row[4]}, ward {key[0]} district {key[1]} is {dict(counts)}')

    #Streets not on the Census map: the side most others in their ward and district are on
    for name, low, high, side, ward, district in unplaced:
        counts = placed[(ward, district)]
        if not counts:
            notes.append(f'skip   {name} {low}-{high}: not on the Census map, no other street in ward {ward} district {district}')
            continue
        where = counts.most_common(1)[0][0]
        out.append((lookup_names(name)[0], low, high, side, where + ward, True))
        notes.append(f'guess  {name} {low}-{high}: {where}, from ward {ward} district {district} {dict(counts)}')

    rows = sorted(set(out))
    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['Municipality', 'Street_Name', 'Low_Range', 'High_Range', 'Side', 'ZIP', 'Zone', 'Needs_Check'])
        for name, low, high, side, zone, check in rows:
            writer.writerow(['ROSELLE', name, low, high, side, ZIP_CODE, zone, 'Y' if check else ''])
    print('\n'.join(notes))
    zones = collections.Counter(r[4] for r in rows)
    print(f'{len(rows)} rows written to {os.path.normpath(OUT_FILE)}, '
          f'{sum(1 for r in rows if r[5])} to check; by zone: {dict(sorted(zones.items()))}')


if __name__ == '__main__':
    main()
