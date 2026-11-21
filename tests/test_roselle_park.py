"""Roselle Park is checked against every date of the borough's 2026 Curbside Collection Calendar."""
import csv
import datetime
import os
import sys
import unittest

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)

import pickup_schedule
from address_lookup import AddressBook


def pickup_dates(town, zone, stream_id, first, last):
    """Every date from first to last the website would mark for one stream."""
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

#The 2026 calendar, month by month (version dated 12-18-2025). Yellow days are west side
#garbage, blue days east side garbage, RP/RB the Wednesday recycling, VE/VW vegetative
#waste (Thursday east, Friday west) and the red-outlined days bulk (Thursday west, Friday east).
CALENDAR = {
    1: dict(west=[5, 8, 12, 15, 19, 22, 26, 29], east=[2, 6, 9, 13, 16, 20, 23, 27, 30],
            paper=[7, 21], containers=[14, 28], bulk=(29, 30)),
    2: dict(west=[2, 5, 9, 12, 16, 19, 23, 26], east=[3, 6, 10, 13, 17, 20, 24, 27],
            paper=[4, 18], containers=[11, 25], bulk=(26, 27)),
    3: dict(west=[2, 5, 9, 12, 16, 19, 23, 26, 30], east=[3, 6, 10, 13, 17, 20, 24, 27, 31],
            paper=[4, 18], containers=[11, 25], bulk=(26, 27)),
    4: dict(west=[2, 6, 9, 13, 16, 20, 23, 27, 30], east=[3, 7, 10, 14, 17, 21, 24, 28],
            paper=[1, 15, 29], containers=[8, 22], bulk=(23, 24)),
    5: dict(west=[4, 7, 11, 14, 18, 21, 28], east=[1, 5, 8, 12, 15, 19, 22, 26, 29],
            paper=[13, 27], containers=[6, 20], bulk=(28, 29)),
    6: dict(west=[1, 4, 8, 11, 15, 18, 22, 25, 29], east=[2, 5, 9, 12, 16, 19, 23, 26, 30],
            paper=[10, 24], containers=[3, 17], bulk=(25, 26)),
    7: dict(west=[2, 6, 9, 13, 16, 20, 23, 27, 30], east=[3, 7, 10, 14, 17, 21, 24, 28, 31],
            paper=[8, 22], containers=[1, 15, 29], bulk=(30, 31)),
    8: dict(west=[3, 6, 10, 13, 17, 20, 24, 27, 31], east=[4, 7, 11, 14, 18, 21, 25, 28],
            paper=[5, 19], containers=[12, 26], bulk=(27, 28)),
    9: dict(west=[3, 10, 14, 17, 21, 24, 28], east=[1, 4, 8, 11, 15, 18, 22, 25, 29],
            paper=[2, 16, 30], containers=[9, 23], bulk=(24, 25)),
    10: dict(west=[1, 5, 8, 12, 15, 19, 22, 26, 29], east=[2, 6, 9, 13, 16, 20, 23, 27, 30],
             paper=[14, 28], containers=[7, 21], bulk=(29, 30)),
    #Monday 11/2 and Tuesday 11/3 (Election Day) are left white on the calendar, with no
    #"H". The website keeps them as normal garbage days (both are in the past already)
    11: dict(west=[2, 5, 9, 12, 16, 19, 23, 30], east=[3, 6, 10, 13, 17, 20, 24, 27],
             paper=[11, 25], containers=[4, 18], bulk=(19, 20)),
    12: dict(west=[3, 7, 10, 14, 17, 21, 24, 28, 31], east=[1, 4, 8, 11, 15, 18, 22, 29],
             paper=[9, 23], containers=[2, 16, 30], bulk=(17, 18)),
}
HOLIDAYS_2026 = ['2026-01-01', '2026-05-25', '2026-09-07', '2026-11-26', '2026-12-25']


def day(text):
    return datetime.date.fromisoformat(text)


def in_month(month, days):
    return [datetime.date(2026, month, d) for d in days]


class RoselleParkSchedule(unittest.TestCase):
    def setUp(self):
        self.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['roselle_park']

    def month(self, zone, stream_id, month):
        first = datetime.date(2026, month, 1)
        last = (first + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)
        return pickup_dates(self.town, zone, stream_id, first, last)

    def test_holidays(self):
        found = sorted(d.isoformat() for d in pickup_schedule.holidays_in_year(self.town, 2026))
        self.assertEqual(found, HOLIDAYS_2026)

    def test_every_garbage_day(self):
        for month, cal in CALENDAR.items():
            self.assertEqual(self.month('W', 'garbage', month), in_month(month, cal['west']), month)
            self.assertEqual(self.month('E', 'garbage', month), in_month(month, cal['east']), month)
            #Chestnut St from Westfield Ave to Grant Ave: both
            self.assertEqual(self.month('CE', 'garbage', month), sorted(in_month(month, cal['west'] + cal['east'])), month)

    def test_every_recycling_day(self):
        for month, cal in CALENDAR.items():
            for zone in ('E', 'W', 'CW'):
                self.assertEqual(self.month(zone, 'paper', month), in_month(month, cal['paper']), month)
                self.assertEqual(self.month(zone, 'containers', month), in_month(month, cal['containers']), month)

    def test_every_bulk_day(self):
        for month, cal in CALENDAR.items():
            west, east = cal['bulk']
            self.assertEqual(self.month('W', 'bulk', month), in_month(month, [west]), month)
            self.assertEqual(self.month('CW', 'bulk', month), in_month(month, [west]), month)
            self.assertEqual(self.month('E', 'bulk', month), in_month(month, [east]), month)
            self.assertEqual(self.month('CE', 'bulk', month), in_month(month, [east]), month)

    def test_vegetative_waste_april_to_december(self):
        year = (day('2026-01-01'), day('2026-12-31'))
        east = pickup_dates(self.town, 'E', 'yard', *year)
        west = pickup_dates(self.town, 'W', 'yard', *year)
        #Every Thursday / Friday from April 1, Thanksgiving and Christmas skipped
        self.assertEqual((east[0], east[-1]), (day('2026-04-02'), day('2026-12-31')))
        self.assertEqual((west[0], west[-1]), (day('2026-04-03'), day('2026-12-18')))
        self.assertNotIn(day('2026-11-26'), east)
        self.assertIn(day('2026-11-27'), west)
        #40 Thursdays and 39 Fridays from April 2 on, less Thanksgiving and Christmas
        self.assertEqual((len(east), len(west)), (39, 38))
        self.assertEqual(pickup_dates(self.town, 'CW', 'yard', *year), west)


class RoselleParkAddresses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['roselle_park']
        cls.book = AddressBook()
        with open(os.path.join(TOP, 'data', 'roselle_park.csv'), newline='', encoding='utf-8') as handle:
            for row in csv.DictReader(handle):
                cls.book.add('roselle_park', row['Street_Name'], row['Low_Range'], row['High_Range'],
                             row['Side'], row['ZIP'], row['Zone'], row['Needs_Check'] == 'Y')

    def zone(self, number, street, location=None):
        found = self.book.find_on_split_street('roselle_park', number, street, '07204',
                                               self.town['direction_split'], location)
        found = found or self.book.find('roselle_park', number, street, '07204')
        return found and (found['zone'], found['needs_check'])

    def test_streets_east_and_west_of_chestnut(self):
        self.assertEqual(self.zone(322, 'W Clay Ave'), ('W', False))
        self.assertEqual(self.zone(322, 'West Clay Avenue'), ('W', False))
        self.assertEqual(self.zone(15, 'E Westfield Ave'), ('E', False))

    def test_chestnut_street(self):
        #Westfield Ave to Grant Ave: four days a week, the rest by the side of the street
        self.assertEqual(self.zone(116, 'Chestnut St'), ('CW', False))
        self.assertEqual(self.zone(127, 'Chestnut St'), ('CE', False))
        self.assertEqual(self.zone(401, 'Chestnut St'), ('E', True))
        self.assertEqual(self.zone(416, 'Chestnut St'), ('W', True))

    def test_every_zone_is_in_the_rules_file(self):
        zones = {row[4] for rows in self.book.streets.values() for row in rows}
        self.assertEqual(zones, set(self.town['zones']))

    def test_every_e_or_w_street_is_on_its_side(self):
        for (town_id, name), rows in self.book.streets.items():
            words = name.split()
            if len(words) >= 3 and words[0] in ('E', 'W'):
                self.assertEqual({row[4] for row in rows}, {words[0]}, name)


if __name__ == '__main__':
    unittest.main()
