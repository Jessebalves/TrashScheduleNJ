#!/usr/bin/env python3
"""Turn the City of Linden's district collection calendars into one JSON file.

Linden's Department of Public Works publishes one calendar per collection district
(1 to 10) every year, as a spreadsheet and a PDF, in a public Google Drive folder that
is linked from https://linden-nj.gov/directory/recycling/ ("2026 Garbage Disposal
Schedules"). The spreadsheets are in its "Spreadsheets" subfolder, named
"DISTRICT 1 - Collection Schedule 2026.xlsx" and so on. Use those, the PDFs lose the
layout.

Each spreadsheet is a year of month grids. A day holds its date number, or the letters
of what is collected that day, which then stand in place of the number:
    S  green cart, garbage            R  blue cart, bottles and cans
    P  brown cart, paper/cardboard    T  bulk trash and yard waste
    G  bagged grass                   B  bagged leaves
    CT Christmas trees                Holiday: DPW closed
">" and "<" mark a pickup a holiday moved; "move" and "Passover" are notes. The date of
a cell with letters is worked out from its row and column.

Writes {"year", "source", "districts": {"1": {"2026-01-05": ["P"], ...}}, "holidays": [...]}.
towns/linden.json is written by hand from this file, and tests/test_linden.py checks the
two against each other, date by date.

This is a developer tool, it is not used by the running website. It needs openpyxl
(sudo apt install python3-openpyxl):

    python3 tools/linden_calendar.py 2026 <folder with the 10 .xlsx files> data/reference/linden_2026_calendar.json
"""
import datetime
import json
import os
import re
import sys
import warnings

import openpyxl

MONTHS = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST',
          'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER']
CODES = {'S', 'R', 'P', 'T', 'G', 'B', 'CT'}


def read_calendar(path, year):
    """Return ({date: [codes]}, {holiday dates}) for one district's spreadsheet."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        sheet = openpyxl.load_workbook(path).worksheets[0]
    cells = {(c.row, c.column): c.value for row in sheet.iter_rows() for c in row
             if c.value not in (None, '')}
    pickups, holidays = {}, set()
    for (head_row, head_col), value in cells.items():
        if not (isinstance(value, str) and value.strip().upper() in MONTHS):
            continue
        month = MONTHS.index(value.strip().upper()) + 1
        #The grid starts at the "Sun" heading under the month name. In some sheets
        #it is one column right of the name, so the name's column cannot be trusted.
        for col in range(head_col, head_col + 4):
            if str(cells.get((head_row + 1, col), '')).strip().upper() == 'SUN':
                head_col = col
                break
        else:
            sys.exit('%s: no "Sun" heading under %s' % (path, value.strip()))
        sunday = None
        #The weekday names are on the row under the month name, the weeks after that
        for row in range(head_row + 2, head_row + 9):
            week = [cells.get((row, head_col + n)) for n in range(7)]
            if any(isinstance(v, str) and v.strip().upper() in MONTHS for v in week):
                break
            if all(v is None for v in week):
                continue
            #The legend line under a row of months
            if isinstance(week[0], str) and '=' in week[0] and len(week[0]) > 25:
                break
            #Each row is the week after the row above it. The first row's week comes from
            #a date number on it: it may be a last day of the month before (June's grid
            #starts with May 31). The date numbers on later rows are checked against it.
            numbers = [(n, int(v)) for n, v in enumerate(week) if isinstance(v, (int, float))]
            if sunday is None:
                if numbers:
                    n, number = numbers[0]
                    this_month, this_year = month, year
                    if number > 20:
                        this_month, this_year = (month - 1, year) if month > 1 else (12, year - 1)
                    sunday = datetime.date(this_year, this_month, number) - datetime.timedelta(days=n)
                else:
                    first = datetime.date(year, month, 1)
                    sunday = first - datetime.timedelta(days=(first.weekday() + 1) % 7)
            else:
                sunday += datetime.timedelta(days=7)
            for n, number in numbers:
                if (sunday + datetime.timedelta(days=n)).day != number:
                    sys.exit('%s: %s, row %d: day %d is not where it should be' % (path, value.strip(), row, number))
            for n, v in enumerate(week):
                if not isinstance(v, str):
                    continue
                date = sunday + datetime.timedelta(days=n)
                if 'HOLIDAY' in v.upper():
                    holidays.add(date.isoformat())
                    continue
                codes = [c.strip() for c in re.sub(r'[<>]', '', v).upper().split('/')]
                codes = [c for c in codes if c in CODES]
                if codes:
                    pickups.setdefault(date.isoformat(), [])
                    pickups[date.isoformat()] += [c for c in codes if c not in pickups[date.isoformat()]]
    return pickups, holidays


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    year, folder, out_path = int(sys.argv[1]), sys.argv[2], sys.argv[3]
    districts, holidays = {}, set()
    for name in sorted(os.listdir(folder)):
        match = re.search(r'DISTRICT\s*(\d+)', name, re.I)
        if not (match and name.lower().endswith('.xlsx')):
            continue
        pickups, days_off = read_calendar(os.path.join(folder, name), year)
        districts[match.group(1)] = dict(sorted(pickups.items()))
        holidays |= days_off
        print('District %s: %d pickup days, %d holidays' % (match.group(1), len(pickups), len(days_off)))
    if len(districts) != 10:
        sys.exit('Expected 10 district calendars, found %d' % len(districts))
    result = {
        'year': year,
        'source': 'City of Linden DPW, "DISTRICT n - Collection Schedule %d" spreadsheets, '
                  'linked from https://linden-nj.gov/directory/recycling/' % year,
        'codes': {'S': 'garbage', 'R': 'bottles and cans', 'P': 'paper and cardboard',
                  'T': 'bulk trash and yard waste', 'G': 'bagged grass', 'B': 'bagged leaves',
                  'CT': 'Christmas trees'},
        'holidays': sorted(holidays),
        'districts': {k: districts[k] for k in sorted(districts, key=int)},
    }
    with open(out_path, 'w', encoding='utf-8') as handle:
        json.dump(result, handle, indent=1)
        handle.write('\n')
    print('Wrote', out_path)


if __name__ == '__main__':
    main()
