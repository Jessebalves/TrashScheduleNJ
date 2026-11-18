#!/usr/bin/env python3
"""Turn Union County's "Find your Ward and District" PDF into a CSV file.

The Union County Board of Elections publishes one list of every street in all
21 towns of the county, with house number ranges, the side of the street, and
the ward and election district. It is linked from "Where do I vote?":

    https://ucnj.org/boe/where-do-i-vote/

It is the street list to start from when a new town is added to the website.
Remember that it says which WARD a house is in. Only some towns (Elizabeth is
one) collect trash by ward, see towns/README.md.

This is a developer tool, it is not used by the running website. It needs the
`pdftotext` program (sudo apt install poppler-utils):

    pdftotext -layout Find-your-Ward-and-District.pdf county.txt
    python3 tools/county_pdf_to_csv.py county.txt data/reference/union_county_street_list_2025.csv
"""
import csv
import re
import sys

#One line of the list: town, street, low number, high number, side, ward, district
LINE = re.compile(r'^(?P<town>\S.*?)\s{2,}(?P<street>\S.*?)\s{2,}(?P<low>\d+)\s+(?P<high>\d+)\s+'
                  r'(?P<side>Even|Odd|All)\s+(?P<ward>\d+)\s+(?P<district>\d+)\s*$')
#When a street name is too long for its column the line is printed as two:
#the town and the street first, the numbers on the next line
FIRST_HALF = re.compile(r'^(?P<town>\S.*?)\s{2,}(?P<street>\S.*?)\s*$')
SECOND_HALF = re.compile(r'^\s+(?P<low>\d+)\s+(?P<high>\d+)\s+(?P<side>Even|Odd|All)\s+(?P<ward>\d+)\s+(?P<district>\d+)\s*$')

SIDES = {'Even': 'E', 'Odd': 'O', 'All': 'B'}
#"Kenilworth Borough" becomes "KENILWORTH"
TOWN_KINDS = (' TOWNSHIP', ' BOROUGH', ' CITY', ' TOWN')


def town_name(text):
    name = text.upper()
    for kind in TOWN_KINDS:
        if name.endswith(kind):
            name = name[:-len(kind)]
    return name


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)

    rows = []
    not_read = []
    waiting = None      #the first half of a line that was printed as two
    with open(sys.argv[1], encoding='utf-8') as handle:
        for line in handle:
            line = line.rstrip('\n')
            text = line.strip()
            if not text or text.startswith(('Page ', 'As of', 'Municipality')) or text == 'County of Union':
                continue
            match = LINE.match(line)
            if match is None and waiting is not None and SECOND_HALF.match(line):
                match = SECOND_HALF.match(line)
                parts = dict(waiting.groupdict(), **match.groupdict())
            elif match is not None:
                parts = match.groupdict()
            else:
                if FIRST_HALF.match(line):
                    waiting = FIRST_HALF.match(line)
                else:
                    not_read.append(line)
                continue
            waiting = None
            rows.append([town_name(parts['town']), parts['street'], int(parts['low']), int(parts['high']),
                         SIDES[parts['side']], int(parts['ward']), int(parts['district'])])

    with open(sys.argv[2], 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['Municipality', 'Street_Name', 'Low_Range', 'High_Range', 'Side', 'Ward', 'District'])
        writer.writerows(rows)

    towns = sorted({row[0] for row in rows})
    print("Wrote %d rows for %d towns to %s" % (len(rows), len(towns), sys.argv[2]))
    for town in towns:
        print("  %-18s %5d rows" % (town, sum(1 for row in rows if row[0] == town)))
    if not_read:
        print("%d lines could not be read:" % len(not_read))
        for line in not_read[:20]:
            print("   ", line.strip())


if __name__ == '__main__':
    main()
