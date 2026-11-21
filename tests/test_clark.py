"""Clark is checked against every date of the township's 2026 recycling and bulky pickup schedules."""
import csv
import datetime
import os
import sys
import unittest

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)

import pickup_schedule
from address_lookup import AddressBook

#ourclark.com/175/Recycling-Schedule (updated 12/30/2025): month -> (Zone 1 days, Zone 2 days)
RECYCLING = {1: ([14, 28], [7, 21]), 2: ([11, 25], [4, 18]), 3: ([11, 25], [4, 18]), 4: ([8, 22], [1, 15, 29]),
             5: ([6, 20], [13, 27]), 6: ([3, 17], [10, 24]), 7: ([1, 15, 29], [8, 22]), 8: ([12, 26], [5, 19]),
             9: ([9, 23], [2, 16, 30]), 10: ([7, 21], [14, 28]), 11: ([4, 18], [11, 25]), 12: ([2, 16, 30], [9, 23])}
#ourclark.com/173/Bulky-Pickup: month -> the day each ward's week starts (Ward 1, 2, 3, 4)
BULKY = {3: [2, 9, 16, 23], 4: [6, 13, 20, 27], 5: [4, 11, 18, 26], 6: [1, 8, 15, 22],
         7: [6, 13, 20, 27], 8: [3, 10, 17, 24], 9: [7, 14, 21, 28], 10: [5, 12, 19, 26]}


def pickup_dates(town, zone, stream_id, first, last):
    found = set()
    sunday = pickup_schedule.sunday_of(first)
    while sunday <= last:
        answer = pickup_schedule.week_schedule(town, zone, sunday)
        stream = [s for s in answer['streams'] if s['id'] == stream_id][0]
        for item in answer['days']:
            date = datetime.date.fromisoformat(item['date'])
            if item['name'] in stream['pickups'] and first <= date <= last:
                found.add(date)
        sunday += datetime.timedelta(days=7)
    return sorted(found)


class ClarkSchedule(unittest.TestCase):
    def setUp(self):
        self.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['clark']
        self.year = (datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))

    def test_no_trash_pickup(self):
        self.assertEqual([s['id'] for s in self.town['streams']], ['containers', 'bulk'])
        self.assertIn('does not pick up household trash', self.town['important_notes'][0])

    def test_every_recycling_date(self):
        for zone in self.town['zones']:
            column = 0 if zone.startswith('Z1') else 1
            expected = [datetime.date(2026, m, d) for m, days in sorted(RECYCLING.items()) for d in days[column]]
            self.assertEqual(pickup_dates(self.town, zone, 'containers', *self.year), expected, zone)

    def test_every_bulky_week(self):
        for zone in self.town['zones']:
            ward = int(zone[-1])
            expected = [datetime.date(2026, m, days[ward - 1]) for m, days in sorted(BULKY.items())]
            self.assertEqual(pickup_dates(self.town, zone, 'bulk', *self.year), expected, zone)


class ClarkAddresses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['clark']
        cls.rows = list(csv.DictReader(open(os.path.join(TOP, 'data', 'clark.csv'), newline='', encoding='utf-8')))
        cls.book = AddressBook()
        for row in cls.rows:
            cls.book.add('clark', row['Street_Name'], row['Low_Range'], row['High_Range'],
                         row['Side'], row['ZIP'], row['Zone'], row['Needs_Check'] == 'Y')

    def test_every_zone_is_in_the_rules_file(self):
        self.assertEqual({row['Zone'] for row in self.rows}, set(self.town['zones']))

    def test_most_wards_match_the_county_list(self):
        #The township's ward outlines and the Board of Elections' list agree for nearly every house
        county = {}
        with open(os.path.join(TOP, 'data', 'reference', 'union_county_street_list_2025.csv'), newline='') as handle:
            for row in csv.DictReader(handle):
                if row['Municipality'] == 'CLARK':
                    county[(row['Street_Name'], row['Low_Range'])] = row['Ward']
        same = [county[k] == row['Zone'][-1] for row in self.rows
                for k in [(row['Street_Name'], row['Low_Range'])] if k in county]
        self.assertGreater(sum(same) / len(same), 0.95)

    def test_lookup(self):
        found = self.book.find('clark', 430, 'Westfield Ave', '07066')
        self.assertIsNotNone(found)
        self.assertTrue(found['zone'].startswith('Z'))


if __name__ == '__main__':
    unittest.main()
