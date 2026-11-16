#!/usr/bin/env python3
"""Build data/kenilworth.csv: every Kenilworth address range and its garbage route.

Kenilworth publishes its three garbage routes only as a map (the "Sanitation
Routes Map" in the DPW Information Guide), not as a street list. This tool
turns that map into a street list:

  1. It reads the US Census "Address Range-Feature" file for Union County.
     Each record is one block of one street, with the house numbers on the
     left and right side and the position of the block on the map.
  2. It keeps the blocks that are inside the Borough of Kenilworth, using the
     Census boundary of the borough.
  3. It decides which route each side of each block is on, using the same
     boundary streets that are drawn on the borough's map (see zone_at below).

Sides of a block that sit right on a boundary between two routes get a "Y" in
the Needs_Check column, because a map cannot say which truck serves a boundary
street. The website tells those visitors to confirm their days with the DPW.

This is a developer tool, it is not used by the running website. It needs the
`pyshp` package and two downloads from the Census Bureau (public domain):

    pip install pyshp
    https://www2.census.gov/geo/tiger/TIGER2025/ADDRFEAT/tl_2025_34039_addrfeat.zip
    https://www2.census.gov/geo/tiger/TIGER2025/PLACE/tl_2025_34_place.zip

Unzip both, then run:

    python3 tools/build_kenilworth.py <addrfeat folder>/tl_2025_34039_addrfeat \\
                                      <place folder>/tl_2025_34_place
"""
import csv
import math
import os
import sys

import shapefile  # pip install pyshp

ZIP_CODE = '07033'
OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'kenilworth.csv')

#Route names, they match the zone ids in towns/kenilworth.json
MON_THU = 'MON_THU'
TUE_FRI = 'TUE_FRI'
WED_SAT = 'WED_SAT'
SCHOOL_BLOCK = 'SCHOOL_BLOCK'   #see zone_at, never written to the CSV

#One degree of longitude is shorter than one degree of latitude this far north.
#Multiplying longitudes by this makes distances and angles come out right.
LON_SCALE = math.cos(math.radians(40.68))
#How far to step off the middle of the street to land on a house lot (about 15 m)
SIDE_STEP = 0.00014


def to_flat(point):
    """Turn (longitude, latitude) into x, y where both are the same length on the ground."""
    return (point[0] * LON_SCALE, point[1])


class StreetLine:
    """A street used as a boundary on the route map, to ask which side of it a point is on."""

    def __init__(self, records, name, runs):
        #runs is 'east' for a street that runs west to east and 'north' for south to north
        self.segments = []
        for record, points in records:
            if record['FULLNAME'] != name:
                continue
            flat = [to_flat(p) for p in points]
            for a, b in zip(flat, flat[1:]):
                #Point every piece the same way, so that "left" always means the same side
                if (runs == 'east' and b[0] < a[0]) or (runs == 'north' and b[1] < a[1]):
                    a, b = b, a
                self.segments.append((a, b))
        if not self.segments:
            sys.exit("The Census file has no street called " + name)

    def is_left(self, p):
        """True if p is left of the street: north of an 'east' street, west of a 'north' street."""
        best = None
        for a, b in self.segments:
            dx, dy = b[0] - a[0], b[1] - a[1]
            length2 = dx * dx + dy * dy
            if length2 == 0:
                continue
            t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
            cx, cy = a[0] + t * dx, a[1] + t * dy
            distance2 = (p[0] - cx) ** 2 + (p[1] - cy) ** 2
            if best is None or distance2 < best[0]:
                best = (distance2, dx * (p[1] - a[1]) - dy * (p[0] - a[0]))
        return best[1] > 0


def inside(polygon, p):
    """Ray casting test: is point p inside the polygon (a list of points)?"""
    result = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > p[1]) != (yj > p[1]) and p[0] < (xj - xi) * (p[1] - yi) / (yj - yi) + xi:
            result = not result
        j = i
    return result


def middle_of(points):
    """Return the point halfway along a line and the direction the line runs there."""
    flat = [to_flat(p) for p in points]
    lengths = [math.dist(a, b) for a, b in zip(flat, flat[1:])]
    target = sum(lengths) / 2
    for (a, b), length in zip(zip(flat, flat[1:]), lengths):
        if length > 0 and target <= length:
            t = target / length
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])), ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
        target -= length
    return flat[0], (1.0, 0.0)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)

    #-------------------------------------------------------------- read the files
    reader = shapefile.Reader(sys.argv[1])
    records = []
    for record, shape in zip(reader.iterRecords(), reader.iterShapes()):
        record = record.as_dict()
        if ZIP_CODE in (record['ZIPL'], record['ZIPR']):
            records.append((record, shape.points))

    borough = None
    places = shapefile.Reader(sys.argv[2])
    for record, shape in zip(places.iterRecords(), places.iterShapes()):
        if record.as_dict()['NAMELSAD'] == 'Kenilworth borough':
            borough = [to_flat(p) for p in shape.points]
    if borough is None:
        sys.exit("Kenilworth borough was not found in the place file")

    #---------------------------------------------------- the boundaries on the map
    boulevard = StreetLine(records, 'Boulevard', 'east')
    monroe = StreetLine(records, 'Monroe Ave', 'east')
    north_14th = StreetLine(records, 'N 14th St', 'north')
    north_18th = StreetLine(records, 'N 18th St', 'north')
    south_20th = StreetLine(records, 'S 20th St', 'north')

    def zone_at(p):
        """The route for a point, read off the 2026 Sanitation Routes Map.

        South of the Boulevard: Tuesday & Friday west of S 20th St,
                                Monday & Thursday east of it.
        North of Monroe Ave:    Wednesday & Saturday.
        Between the two:        Tuesday & Friday west of N 14th St,
                                Wednesday & Saturday east of N 18th St.
        The block in between (N 14th to N 18th) holds the two schools and has
        lines of all three colours around it on the map, see below.
        """
        if not boulevard.is_left(p):
            return TUE_FRI if south_20th.is_left(p) else MON_THU
        if monroe.is_left(p):
            return WED_SAT
        if north_14th.is_left(p):
            return TUE_FRI
        if not north_18th.is_left(p):
            return WED_SAT
        return SCHOOL_BLOCK

    #A lot on the school block gets the colour of the line drawn along the
    #street it faces. Monroe Ave has a blue and a purple line there, blue is
    #used because the rest of Monroe Ave is blue. These rows always get Needs_Check=Y.
    school_block_frontage = {
        'N 14TH ST': TUE_FRI, 'BOULEVARD': TUE_FRI,
        'N 18TH ST': WED_SAT, 'MONROE AVE': WED_SAT,
    }

    #------------------------------------------------------- one row per block side
    rows = []
    for record, points in records:
        name = record['FULLNAME'].upper()
        middle, direction = middle_of(points)
        #Left of the direction of travel is the direction turned a quarter turn anticlockwise
        left = (middle[0] - direction[1] * SIDE_STEP, middle[1] + direction[0] * SIDE_STEP)
        right = (middle[0] + direction[1] * SIDE_STEP, middle[1] - direction[0] * SIDE_STEP)
        for here, across, letter in ((left, right, 'L'), (right, left, 'R')):
            low, high = record[letter + 'FROMHN'], record[letter + 'TOHN']
            parity = record['PARITY' + letter]
            if record['ZIP' + letter] != ZIP_CODE or not (low.isdigit() and high.isdigit()):
                continue
            if parity not in ('O', 'E', 'B') or not inside(borough, here):
                continue
            zone, other = zone_at(here), zone_at(across)
            check = zone != other
            if zone == SCHOOL_BLOCK:
                zone = school_block_frontage.get(name, WED_SAT)
                check = True
            low, high = sorted((int(low), int(high)))
            rows.append([name, low, high, parity, zone, 'Y' if check else ''])

    #Corrections to the Census file, found by reading the result street by street
    for row in rows:
        #This range is attached to a block near N 18th St in the Census file. The
        #200s of Washington Ave are at its west end, south of Monroe Ave.
        if row[:4] == ['WASHINGTON AVE', 200, 258, 'E']:
            row[4], row[5] = TUE_FRI, ''
    #The Census file lists some streets under two names. Keep the one the borough
    #uses, towns/kenilworth.json sends the other spelling to it.
    #  - "Boulevard" is also listed as "Kenilworth Blvd", with only some blocks
    #  - the south half of Michigan Ave is listed as plain "Michigan Ave"
    rows = [row for row in rows if row[0] != 'KENILWORTH BLVD']
    for row in rows:
        if row[0] == 'MICHIGAN AVE':
            row[0] = 'S MICHIGAN AVE'

    #Two short streets at the south west edge are on the county's street list for
    #Kenilworth but have another town's ZIP code in the Census file. On the map
    #they are inside the Tuesday & Friday line. Marked to check.
    for name in ('ARBOR ST', 'HEMLOCK DR'):
        rows.append([name, 1, 99, 'B', TUE_FRI, 'Y'])

    #Blocks that follow on from each other on the same route become one row
    rows.sort()
    merged = []
    for row in rows:
        last = merged[-1] if merged else None
        if last and last[0] == row[0] and last[3:] == row[3:] and row[1] <= last[2] + 2:
            last[2] = max(last[2], row[2])
        elif row not in merged:
            merged.append(row)

    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['Municipality', 'Street_Name', 'Low_Range', 'High_Range', 'Side', 'ZIP', 'Zone', 'Needs_Check'])
        for name, low, high, parity, zone, check in merged:
            writer.writerow(['KENILWORTH', name, low, high, parity, ZIP_CODE, zone, check])

    print("Wrote %d rows to %s" % (len(merged), os.path.normpath(OUT_FILE)))
    for zone in (MON_THU, TUE_FRI, WED_SAT):
        print("  %-8s %4d rows" % (zone, sum(1 for row in merged if row[4] == zone)))
    print("  to check with the DPW: %d rows" % sum(1 for row in merged if row[5]))


if __name__ == '__main__':
    main()
