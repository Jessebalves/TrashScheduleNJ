"""Rahway is checked against the City's 2026 Residential Garbage & Recycling Program mailer."""
import csv
import datetime
import os
import sys
import unittest

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)

import pickup_schedule
from address_lookup import AddressBook

#The mailer's recycling dates (every other Wednesday)
RECYCLING = {
    'A': {1: [14, 28], 2: [11, 25], 3: [11, 25], 4: [8, 22], 5: [6, 20], 6: [3, 17], 7: [1, 15, 29], 8: [12, 26],
          9: [9, 23], 10: [7, 21], 11: [4, 18], 12: [2, 16, 30]},
    'B': {1: [7, 21], 2: [4, 18], 3: [4, 18], 4: [1, 15, 29], 5: [13, 27], 6: [10, 24], 7: [8, 22], 8: [5, 19],
          9: [2, 16, 30], 10: [14, 28], 11: [11, 25], 12: [9, 23]},
}


def day(text):
    return datetime.date.fromisoformat(text)


def pickup_dates(town, zone, stream_id, first, last):
    found = set()
    sunday = pickup_schedule.sunday_of(first)
    while sunday <= last:
        answer = pickup_schedule.week_schedule(town, zone, sunday)
        stream = [s for s in answer['streams'] if s['id'] == stream_id][0]
        for item in answer['days']:
            date = day(item['date'])
            if item['name'] in stream['pickups'] and first <= date <= last:
                found.add(date)
        sunday += datetime.timedelta(days=7)
    return sorted(found)


class RahwaySchedule(unittest.TestCase):
    def setUp(self):
        self.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['rahway']
        self.year = (day('2026-01-01'), day('2026-12-31'))

    def test_every_recycling_date(self):
        for zone, months in RECYCLING.items():
            expected = [datetime.date(2026, m, d) for m, days in sorted(months.items()) for d in days]
            self.assertEqual(pickup_dates(self.town, zone, 'containers', *self.year), expected, zone)

    def test_garbage_twice_a_week(self):
        week = (day('2026-11-15'), day('2026-11-21'))
        self.assertEqual([d.strftime('%a') for d in pickup_dates(self.town, 'A', 'garbage', *week)], ['Mon', 'Thu'])
        self.assertEqual([d.strftime('%a') for d in pickup_dates(self.town, 'B', 'garbage', *week)], ['Tue', 'Fri'])

    def test_the_seven_holidays(self):
        #The mailer: no collection that day, the next one is the next regular day
        a = pickup_dates(self.town, 'A', 'garbage', *self.year)
        b = pickup_dates(self.town, 'B', 'garbage', *self.year)
        for holiday, next_day in (('2026-01-01', '2026-01-05'), ('2026-01-19', '2026-01-22'), ('2026-05-25', '2026-05-28'),
                                  ('2026-09-07', '2026-09-10'), ('2026-11-26', '2026-11-30')):
            self.assertNotIn(day(holiday), a)
            self.assertEqual(min(d for d in a if d > day(holiday)), day(next_day))
        for holiday, next_day in (('2026-07-03', '2026-07-07'), ('2026-12-25', '2026-12-29')):
            self.assertNotIn(day(holiday), b)
            self.assertEqual(min(d for d in b if d > day(holiday)), day(next_day))
        #No bulky waste on Thanksgiving (A) and Christmas (B); no yard waste on Memorial Day (A)
        self.assertNotIn(day('2026-11-26'), pickup_dates(self.town, 'A', 'bulk', *self.year))
        self.assertNotIn(day('2026-12-25'), pickup_dates(self.town, 'B', 'bulk', *self.year))
        self.assertNotIn(day('2026-05-25'), pickup_dates(self.town, 'A', 'yard', *self.year))

    def test_yard_waste_season_on_the_first_day(self):
        a = pickup_dates(self.town, 'A', 'yard', *self.year)
        b = pickup_dates(self.town, 'B', 'yard', *self.year)
        self.assertEqual((a[0], a[-1]), (day('2026-04-06'), day('2026-11-02')))
        self.assertEqual((b[0], b[-1]), (day('2026-04-07'), day('2026-11-03')))

    def test_bulky_waste_on_the_second_day(self):
        week = (day('2026-11-15'), day('2026-11-21'))
        self.assertEqual(pickup_dates(self.town, 'A', 'bulk', *week), [day('2026-11-19')])
        self.assertEqual(pickup_dates(self.town, 'B', 'bulk', *week), [day('2026-11-20')])


class RahwayAddresses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['rahway']
        cls.rows = list(csv.DictReader(open(os.path.join(TOP, 'data', 'rahway.csv'), newline='', encoding='utf-8')))

    def zones_on(self, street):
        return {row['Zone'] for row in self.rows if row['Street_Name'] == street}

    def test_streets_inside_each_section(self):
        #Streets drawn well inside one section on the mailer's map
        for street in ('W INMAN AVE', 'GROVE ST', 'JAQUES AVE', 'MADISON HILL RD'):
            self.assertEqual(self.zones_on(street), {'A'}, street)
        for street in ('ELIZABETH AVE', 'E SCOTT AVE', 'LAWRENCE ST', 'LEESVILLE AVE', 'W GRAND AVE'):
            self.assertEqual(self.zones_on(street), {'B'}, street)

    def test_recycle_coach(self):
        #Checked in Rahway's Recycle Coach on 2026-11-21 (garbage Mon/Thu = A, Tue/Fri = B)
        book = AddressBook()
        for row in self.rows:
            book.add('rahway', row['Street_Name'], row['Low_Range'], row['High_Range'], row['Side'], row['ZIP'],
                     row['Zone'], row['Needs_Check'] == 'Y')
        checked = [(578, 'W Inman Ave', 'A'), (830, 'Jaques Ave', 'A'), (533, 'E Scott Ave', 'B'),
                   (1652, 'Lawrence St', 'B'), (753, 'Central Ave', 'A'), (405, 'Central Ave', 'B'),
                   (552, 'Bryant St', 'A'), (1265, 'Bryant St', 'B'), (272, 'W Milton Ave', 'A'),
                   (275, 'W Milton Ave', 'B'), (868, 'Main St', 'A'), (855, 'Main St', 'A'),
                   (1319, 'Saint Georges Ave', 'B'), (1459, 'Saint Georges Ave', 'B'), (212, 'E Hazelwood Ave', 'A'),
                   (797, 'E Hazelwood Ave', 'B'), (263, 'E Albert St', 'A'), (157, 'E Stearns St', 'A'),
                   (150, 'E Lake Ave', 'A'), (1001, 'Westfield Ave', 'A'), (853, 'Westfield Ave', 'A'),
                   (1202, 'Broadway', 'A'), (1443, 'Barnhardt Ln', 'B'), (971, 'Ross St', 'B'),
                   #Second round
                   (1131, 'Main St', 'A'), (1030, 'Main St', 'A'), (1047, 'Main St', 'B'),
                   (1286, 'Saint Georges Ave', 'A'), (1500, 'Saint Georges Ave', 'A'),
                   (1219, 'Saint Georges Ave', 'B'), (64, 'W Milton Ave', 'A'), (99, 'W Milton Ave', 'B'),
                   #Third round
                   (1001, 'Main St', 'A'), (1245, 'Main St', 'B'), (65, 'E Milton Ave', 'A'),
                   (80, 'E Milton Ave', 'B')]
        for number, street, zone in checked:
            self.assertEqual(book.find('rahway', number, street, '07065')['zone'], zone, (number, street))

    def test_dividing_streets(self):
        #St Georges Ave: east side (odd) B, west side A; W Milton Ave: north side (odd) B, south side A;
        #Main St up to the 1100 block is A on both sides (the river behind its east side is the line),
        #except 1047; Westfield Ave is inside A
        for row in self.rows:
            low = int(row['Low_Range'])
            if row['Street_Name'] == 'SAINT GEORGES AVE' and 1001 <= low <= 1599:
                self.assertEqual(row['Zone'], 'B' if row['Side'] == 'O' else 'A', row)
            if row['Street_Name'] == 'W MILTON AVE' and low <= 299:
                self.assertEqual(row['Zone'], 'B' if row['Side'] == 'O' else 'A', row)
            if row['Street_Name'] == 'MAIN ST' and low <= 1199 and low != 1047:
                self.assertEqual(row['Zone'], 'A', row)
        self.assertEqual(self.zones_on('WESTFIELD AVE'), {'A'})

    def test_every_zone_is_in_the_rules_file(self):
        self.assertEqual({row['Zone'] for row in self.rows}, set(self.town['zones']))


if __name__ == '__main__':
    unittest.main()
