"""Linden is checked against the DPW's 2026 calendars for its ten collection districts.

data/reference/linden_2026_calendar.json holds every date of those calendars (made with
tools/linden_calendar.py from the DPW's spreadsheets). Every pickup the website shows in
2026 must be on it, and every date on it must be shown.
"""
import csv
import datetime
import json
import os
import sys
import unittest

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)

import pickup_schedule
from address_lookup import AddressBook

#The calendar's letters and the stream ids in towns/linden.json
CODES = {'S': 'garbage', 'R': 'containers', 'P': 'paper', 'T': 'bulk', 'G': 'yard',
         'B': 'leaves', 'CT': 'christmas_trees'}


def day(text):
    return datetime.date.fromisoformat(text)


def load():
    towns = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))
    with open(os.path.join(TOP, 'data', 'reference', 'linden_2026_calendar.json'), encoding='utf-8') as handle:
        return towns['linden'], json.load(handle)


def shown_2026(town, zone):
    """{date: set of stream ids} the website shows for one district, every week of 2026."""
    shown = {}
    sunday = pickup_schedule.sunday_of(day('2026-01-01'))
    while sunday <= day('2026-12-31'):
        answer = pickup_schedule.week_schedule(town, zone, sunday)
        for item in answer['days']:
            date = day(item['date'])
            if date.year != 2026:
                continue
            for stream in answer['streams']:
                if item['name'] in stream['pickups']:
                    shown.setdefault(date, set()).add(stream['id'])
        sunday += datetime.timedelta(days=7)
    return shown


class LindenSchedule(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.town, cls.calendar = load()

    def test_every_date_of_every_district(self):
        for zone, dates in self.calendar['districts'].items():
            published = {}
            for text, codes in dates.items():
                if text.startswith('2026'):
                    published[day(text)] = {CODES[c] for c in codes}
            shown = shown_2026(self.town, zone)
            for date in sorted(set(published) | set(shown)):
                with self.subTest(district=zone, date=date.isoformat()):
                    self.assertEqual(shown.get(date, set()), published.get(date, set()))

    def test_holidays(self):
        for text in self.calendar['holidays']:
            self.assertIsNotNone(pickup_schedule.holiday_name(self.town, day(text)), text)
        ours = pickup_schedule.holidays_in_year(self.town, 2026)
        self.assertEqual(sorted(d.isoformat() for d in ours),
                         [t for t in self.calendar['holidays'] if t.startswith('2026')])

    def test_thanksgiving_moves_garbage_both_ways(self):
        #District 1 picks up the day before, District 4 the day after. Recycle Coach shows
        #Wednesday, Nov 25 garbage for 709 Roselle St (District 3, same days as 1), 2026-11-19
        week = pickup_schedule.week_schedule(self.town, '1', day('2026-11-22'))
        garbage = [s for s in week['streams'] if s['id'] == 'garbage'][0]
        self.assertEqual(garbage['pickups'], ['Wednesday'])
        self.assertIn('Garbage moves from Thursday to Wednesday because of Thanksgiving.', week['changes'])
        week = pickup_schedule.week_schedule(self.town, '4', day('2026-11-22'))
        garbage = [s for s in week['streams'] if s['id'] == 'garbage'][0]
        self.assertEqual(garbage['pickups'], ['Friday'])

    def test_a_monday_holiday_names_itself_on_the_moved_days(self):
        #Labor Day: District 4's bottles and cans go Tuesday -> Wednesday, garbage Thursday -> Friday
        upcoming = pickup_schedule.upcoming(self.town, '4', day('2026-09-06'), count=3)
        messages = [n['message'] for n in upcoming['notices']]
        self.assertIn('Bottles & Cans moves from Tuesday, Sep 8 to Wednesday, Sep 9 because of Labor Day.', messages)
        self.assertIn('Garbage moves from Thursday, Sep 10 to Friday, Sep 11 because of Labor Day.', messages)

    def test_new_years_eve_pickup_for_new_years_day(self):
        #Jan 1, 2027 is a Friday: Districts 5-7 pick up garbage on Thursday, Dec 31
        week = pickup_schedule.week_schedule(self.town, '6', day('2026-12-27'))
        garbage = [s for s in week['streams'] if s['id'] == 'garbage'][0]
        self.assertEqual(garbage['pickups'], ['Thursday'])

    def test_upcoming_lists_grass_and_leaves_apart(self):
        #Oct 22 is the Thursday with both grass and leaves for the Monday districts
        upcoming = pickup_schedule.upcoming(self.town, '2', day('2026-10-22'), count=1)
        first = upcoming['pickups'][0]
        self.assertEqual(first['date'], '2026-10-22')
        self.assertEqual([s['id'] for s in first['streams']], ['yard', 'leaves'])

    def test_checked_through(self):
        self.assertEqual(self.town['checked_through'], '2026-12-31')


class DatesOption(unittest.TestCase):

    def test_dates_and_dates_by_zone(self):
        stream = {'id': 'x', 'label': 'X', 'dates': ['2026-05-06']}
        self.assertTrue(pickup_schedule.is_scheduled(stream, 'a', day('2026-05-06')))
        self.assertFalse(pickup_schedule.is_scheduled(stream, 'a', day('2026-05-13')))
        stream = {'id': 'x', 'label': 'X', 'dates_by_zone': {'a': ['2026-05-06']}}
        self.assertTrue(pickup_schedule.is_scheduled(stream, 'a', day('2026-05-06')))
        self.assertFalse(pickup_schedule.is_scheduled(stream, 'b', day('2026-05-06')))

    def test_moved_dates_by_zone(self):
        town = {'holidays': [{'name': 'Good Friday', 'date': '2026-04-03'}]}
        stream = {'moved_dates_by_zone': {'a': {'2026-04-02': '2026-04-01'}}}
        self.assertEqual(pickup_schedule.resolve_pickup(town, stream, day('2026-04-02'), 'a'),
                         (day('2026-04-01'), 'Good Friday'))
        self.assertEqual(pickup_schedule.resolve_pickup(town, stream, day('2026-04-02'), 'b'),
                         (day('2026-04-02'), None))


#Checked by the site owner in Linden's Recycle Coach on 2026-11-19. In the first 20, most are places where
#the DPW map and the wards disagree (the map was right every time); Raritan Rd and
#Hillcrest Ter are the map's own "District 10" note; the rest are borders and controls.
RECYCLE_COACH = [
    (25, 'Hillcrest Ter', '10'), (41, 'Raritan Rd', '10'), (2506, 'Dewitt Ter', '9'),
    (1209, 'Thelma Ter', '10'), (908, 'Baldwin Ave', '3'), (1006, 'Wheatsheaf Rd', '3'),
    (1110, 'Debra Dr', '1'), (1606, 'Westover Rd', '1'), (409, 'Hagel Ave', '8'),
    (315, 'Cranford Ave', '5'), (308, 'Chandler Ave', '5'), (632, 'Tuxedo Pl', '8'),
    (709, 'Roselle St', '3'), (1110, 'Roselle St', '4'), (914, 'Orchard Ter', '1'),
    (1013, 'Dewitt Ter', '10'), (1701, 'Clinton St', '7'), (3008, 'Tremley Point Rd', '7'),
    (700, 'Carnegie St', '4'), (2704, 'Verona Ave', '10'),
    #Second round, addresses marked "please confirm" (and Park Ave), not used to tune the tool
    (25, 'W Curtis St', '2'), (1617, 'Dewitt Ter', '10'), (939, 'N Wood Ave', '1'), (638, 'Park Ave', '8'),
    (1840, 'Windsor Rd', '10'), (309, 'Morristown Rd', '10'), (315, 'Princeton Rd', '10'),
    (607, 'Bower St', '4'), (14, 'Melrose Ter', '9'), (1723, 'Grier Ave', '8'), (615, 'Chandler Ave', '5'),
    (112, 'Jones Pl', '1'),
    #Third round: streets split by side, the map's number circles, streets not on the Census map
    (206, 'W Curtis St', '1'), (305, 'Park Ave', '5'), (1021, 'N Stiles St', '1'), (1100, 'N Stiles St', '1'),
    (30, 'E Curtis St', '3'), (510, 'Harrison Pl', '4'), (183, 'Donald Ave', '8'), (230, 'Jones Pl', '1'),
]


class LindenAddresses(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.book = AddressBook()
        with open(os.path.join(TOP, 'data', 'linden.csv'), newline='', encoding='utf-8') as handle:
            for row in csv.DictReader(handle):
                cls.book.add('linden', row['Street_Name'], row['Low_Range'], row['High_Range'],
                             row['Side'], row['ZIP'], row['Zone'], row['Needs_Check'] == 'Y')

    def test_recycle_coach_answers(self):
        for number, street, district in RECYCLE_COACH:
            with self.subTest(address='%d %s' % (number, street)):
                found = self.book.find('linden', number, street, '07036')
                self.assertIsNotNone(found)
                self.assertEqual(found['zone'], district)

    def test_newark_ave_is_not_in_linden(self):
        #The county list has one 718 Newark Ave under Linden; it is in another town
        self.assertIsNone(self.book.find('linden', 718, 'Newark Ave', '07036'))

    def test_saint_and_mc_spellings(self):
        #The Census (and so data/linden.csv) says "Saint Georges" and "McCandless";
        #visitors and Google say "St Georges", the county list "Mc Candless"
        for street in ('W St Georges Ave', 'W Saint Georges Avenue', 'West St. Georges Ave'):
            self.assertIsNotNone(self.book.find('linden', 1150, street, '07036'), street)
        for street in ('McCandless St', 'Mc Candless St'):
            self.assertIsNotNone(self.book.find('linden', 1108, street, '07036'), street)

    def test_every_zone_is_in_the_rules_file(self):
        town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['linden']
        zones = {row[4] for rows in self.book.streets.values() for row in rows}
        self.assertEqual(zones, set(town['zones']))


if __name__ == '__main__':
    unittest.main()
