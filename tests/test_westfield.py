"""Westfield is checked against every date of the town's 2026 Curbside Recycling Schedule."""
import csv
import datetime
import os
import sys
import unittest

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)

import pickup_schedule
from address_lookup import AddressBook

#The 2026 Collection Schedule table (mailer dated 12-11-2025): zone -> month -> days.
#Holiday weeks: the holiday's zone and the later zones that week are one day later
#(Zone 4 on Friday 1/2 and Zone 5 on Saturday 1/3; Zones 6-10 on 5/26-5/30; Zones 1-5 on
#9/8-9/12; Zones 9 and 10 on 11/27-11/28; Zone 10 on Saturday 12/26).
SCHEDULE = {
    '1': {1: [12, 26], 2: [9, 23], 3: [9, 23], 4: [6, 20], 5: [4, 18], 6: [1, 15, 29], 7: [13, 27], 8: [10, 24],
          9: [8, 21], 10: [5, 19], 11: [2, 16, 30], 12: [14, 28]},
    '2': {1: [13, 27], 2: [10, 24], 3: [10, 24], 4: [7, 21], 5: [5, 19], 6: [2, 16, 30], 7: [14, 28], 8: [11, 25],
          9: [9, 22], 10: [6, 20], 11: [3, 17], 12: [1, 15, 29]},
    '3': {1: [14, 28], 2: [11, 25], 3: [11, 25], 4: [8, 22], 5: [6, 20], 6: [3, 17], 7: [1, 15, 29], 8: [12, 26],
          9: [10, 23], 10: [7, 21], 11: [4, 18], 12: [2, 16, 30]},
    '4': {1: [2, 15, 29], 2: [12, 26], 3: [12, 26], 4: [9, 23], 5: [7, 21], 6: [4, 18], 7: [2, 16, 30], 8: [13, 27],
          9: [11, 24], 10: [8, 22], 11: [5, 19], 12: [3, 17, 31]},
    '5': {1: [3, 16, 30], 2: [13, 27], 3: [13, 27], 4: [10, 24], 5: [8, 22], 6: [5, 19], 7: [3, 17, 31], 8: [14, 28],
          9: [12, 25], 10: [9, 23], 11: [6, 20], 12: [4, 18]},
    '6': {1: [5, 19], 2: [2, 16], 3: [2, 16, 30], 4: [13, 27], 5: [11, 26], 6: [8, 22], 7: [6, 20], 8: [3, 17, 31],
          9: [14, 28], 10: [12, 26], 11: [9, 23], 12: [7, 21]},
    '7': {1: [6, 20], 2: [3, 17], 3: [3, 17, 31], 4: [14, 28], 5: [12, 27], 6: [9, 23], 7: [7, 21], 8: [4, 18],
          9: [1, 15, 29], 10: [13, 27], 11: [10, 24], 12: [8, 22]},
    '8': {1: [7, 21], 2: [4, 18], 3: [4, 18], 4: [1, 15, 29], 5: [13, 28], 6: [10, 24], 7: [8, 22], 8: [5, 19],
          9: [2, 16, 30], 10: [14, 28], 11: [11, 25], 12: [9, 23]},
    '9': {1: [8, 22], 2: [5, 19], 3: [5, 19], 4: [2, 16, 30], 5: [14, 29], 6: [11, 25], 7: [9, 23], 8: [6, 20],
          9: [3, 17], 10: [1, 15, 29], 11: [12, 27], 12: [10, 24]},
    '10': {1: [9, 23], 2: [6, 20], 3: [6, 20], 4: [3, 17], 5: [1, 15, 30], 6: [12, 26], 7: [10, 24], 8: [7, 21],
           9: [4, 18], 10: [2, 16, 30], 11: [13, 28], 12: [11, 26]},
}


def pickup_dates(town, zone, first, last):
    """Every recycling date from first to last the website would mark."""
    found = set()
    sunday = pickup_schedule.sunday_of(first)
    while sunday <= last:
        answer = pickup_schedule.week_schedule(town, zone, sunday)
        for item in answer['days']:
            date = datetime.date.fromisoformat(item['date'])
            if item['name'] in answer['streams'][0]['pickups'] and first <= date <= last:
                found.add(date)
        sunday += datetime.timedelta(days=7)
    return sorted(found)


class WestfieldSchedule(unittest.TestCase):
    def setUp(self):
        self.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['westfield']

    def test_recycling_is_the_only_pickup(self):
        self.assertEqual([s['id'] for s in self.town['streams']], ['containers'])
        self.assertIn('does not pick up household trash', self.town['important_notes'][0])

    def test_every_2026_date(self):
        year = (datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
        for zone, months in SCHEDULE.items():
            expected = [datetime.date(2026, month, d) for month, days in sorted(months.items()) for d in days]
            self.assertEqual(pickup_dates(self.town, zone, *year), expected, 'Zone ' + zone)

    def test_holiday_week_is_explained(self):
        answer = pickup_schedule.week_schedule(self.town, '8', datetime.date(2026, 5, 25))
        self.assertEqual(answer['streams'][0]['pickups'], ['Thursday'])
        self.assertIn('Memorial Day', ' '.join(answer['changes']))


class WestfieldAddresses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['westfield']
        cls.book = AddressBook()
        cls.rows = []
        with open(os.path.join(TOP, 'data', 'westfield.csv'), newline='', encoding='utf-8') as handle:
            for row in csv.DictReader(handle):
                cls.rows.append(row)
                cls.book.add('westfield', row['Street_Name'], row['Low_Range'], row['High_Range'],
                             row['Side'], row['ZIP'], row['Zone'], row['Needs_Check'] == 'Y')

    def zones_on(self, street):
        return {row['Zone'] for row in self.rows if row['Street_Name'] == street}

    def test_north_and_south_of_the_railroad(self):
        #North Ave runs along the north side of the railroad, South Ave along the south side
        self.assertTrue(self.zones_on('N AVE W') | self.zones_on('N AVE E') <= {'1', '2', '3', '4', '5'})
        self.assertTrue(self.zones_on('S AVE W') | self.zones_on('S AVE E') <= {'6', '7', '8', '9', '10'})

    def test_streets_the_zone_lines_run_along(self):
        #The mailer's map: Prospect St between 4 and 5 north of Dudley Ave (Zone 1 south of it),
        #even numbers on the Zone 4 side; E Broad St between 2 and 3; Grove St between 8 and 9
        self.assertEqual(self.zones_on('PROSPECT ST'), {'1', '4', '5'})
        for row in self.rows:
            if row['Street_Name'] == 'PROSPECT ST' and 500 <= int(row['Low_Range']) <= 1212:
                self.assertEqual(row['Zone'], '4' if row['Side'] == 'E' else '5', row)
        self.assertTrue({'2', '3'} <= self.zones_on('E BROAD ST'))
        self.assertEqual(self.zones_on('W GROVE ST'), {'8', '9'})

    def test_every_zone_is_in_the_rules_file(self):
        self.assertEqual({row['Zone'] for row in self.rows}, set(self.town['zones']))

    def test_recycle_coach(self):
        #Checked in Westfield's Recycle Coach on 2026-11-21 (207 Eton Pl first read as Zone 1, rechecked: Zone 9)
        checked = [(207, 'Eton Pl', '9'), (901, 'Coolidge St', '2'), (416, 'N Chestnut St', '3'), (618, 'Cumberland St', '6'),
                   (827, 'Knollwood Ter', '7'), (201, 'Wyoming St', '10'), (811, 'Tice Pl', '9'),
                   (101, 'Cambridge Rd', '9'), (503, 'Carleton Rd', '8'), (110, 'Gallows Hill Rd', '2'),
                   (114, 'Gallows Hill Rd', '2'), (413, 'W Grove St', '9'), (414, 'W Grove St', '8'),
                   (115, 'Roger Ave', '9'), (122, 'Roger Ave', '10'), (1011, 'Rahway Ave', '9'),
                   (1016, 'Rahway Ave', '7'), (645, 'Shackamaxon Dr', '7'), (644, 'Shackamaxon Dr', '6'),
                   (139, 'N Euclid Ave', '1'), (144, 'N Euclid Ave', '3'), (617, 'E Broad St', '3'),
                   (618, 'E Broad St', '1'), (519, 'Mountain Ave', '4'), (526, 'Mountain Ave', '3')]
        for number, street, zone in checked:
            self.assertEqual(self.book.find('westfield', number, street, '07090')['zone'], zone, (number, street))

    def test_w_grove_st(self):
        #Google says "W Grove St"; the county list mostly says "Grove St"
        self.assertEqual(self.book.find('westfield', 432, 'W Grove St', '07090')['zone'], '8')
        self.assertFalse(any(row['Street_Name'] == 'GROVE ST' for row in self.rows))

    def test_lookup(self):
        found = self.book.find('westfield', 425, 'E Broad St', '07090')
        self.assertIn(found['zone'], ('1', '2', '3'))


if __name__ == '__main__':
    unittest.main()
