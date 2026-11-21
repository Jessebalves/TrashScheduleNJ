"""Roselle is checked against the borough's 2026/2027 Sanitation/Recycling Schedule and its flyers."""
import csv
import datetime
import os
import sys
import unittest

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)

import pickup_schedule
from address_lookup import AddressBook

#The 2026 holiday list on the back of the schedule. Its weekdays are last year's
#(it says "Wednesday, January 1, 2026"), the dates are right.
HOLIDAYS_2026 = ['2026-01-01', '2026-01-19', '2026-02-12', '2026-02-16', '2026-04-03', '2026-05-25',
                 '2026-06-19', '2026-07-03', '2026-09-07', '2026-10-12', '2026-11-03', '2026-11-11',
                 '2026-11-26', '2026-11-27', '2026-12-25']


def day(text):
    return datetime.date.fromisoformat(text)


def pickup_dates(town, zone, stream_id, first, last):
    """Every date from first to last the website would mark for one stream."""
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


class RoselleSchedule(unittest.TestCase):
    def setUp(self):
        self.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['roselle']

    def test_holidays(self):
        found = sorted(d.isoformat() for d in pickup_schedule.holidays_in_year(self.town, 2026))
        self.assertEqual(found, HOLIDAYS_2026)

    def test_garbage_by_side_of_chestnut_street(self):
        week = (day('2026-11-15'), day('2026-11-21'))
        self.assertEqual([d.strftime('%a') for d in pickup_dates(self.town, 'E2', 'garbage', *week)], ['Mon', 'Thu'])
        self.assertEqual([d.strftime('%a') for d in pickup_dates(self.town, 'W3', 'garbage', *week)], ['Tue', 'Fri'])

    def test_garbage_skips_thanksgiving_and_the_day_after(self):
        week = (day('2026-11-22'), day('2026-11-28'))
        self.assertEqual(pickup_dates(self.town, 'E1', 'garbage', *week), [day('2026-11-23')])
        self.assertEqual(pickup_dates(self.town, 'W5', 'garbage', *week), [day('2026-11-24')])

    def test_recycling_by_ward(self):
        week = (day('2026-11-15'), day('2026-11-21'))
        for zone, weekday in (('E1', 'Mon'), ('E2', 'Tue'), ('E3', 'Wed'), ('W3', 'Wed'), ('W4', 'Thu'), ('W5', 'Fri')):
            self.assertEqual([d.strftime('%a') for d in pickup_dates(self.town, zone, 'containers', *week)], [weekday])

    def test_recycling_moves_to_the_next_day_on_a_holiday(self):
        #Veterans Day, Wednesday 11/11/2026: the 3rd Ward is picked up on Thursday
        week = (day('2026-11-08'), day('2026-11-14'))
        self.assertEqual(pickup_dates(self.town, 'E3', 'containers', *week), [day('2026-11-12')])

    def test_bulk_first_wednesday_east_third_wednesday_west(self):
        year = (day('2026-01-01'), day('2026-12-31'))
        east = ['2026-03-04', '2026-04-01', '2026-05-06', '2026-06-03', '2026-07-01', '2026-08-05',
                '2026-09-02', '2026-10-07', '2026-11-04']
        west = ['2026-03-18', '2026-04-15', '2026-05-20', '2026-06-17', '2026-07-15', '2026-08-19',
                '2026-09-16', '2026-10-21', '2026-11-18']
        self.assertEqual(pickup_dates(self.town, 'E1', 'bulk', *year), [day(d) for d in east])
        self.assertEqual(pickup_dates(self.town, 'W4', 'bulk', *year), [day(d) for d in west])

    def test_leaves_and_vegetative_waste_seasons(self):
        self.assertEqual(pickup_dates(self.town, 'E1', 'yard', day('2026-01-01'), day('2026-04-30'))[0], day('2026-04-06'))
        self.assertEqual(pickup_dates(self.town, 'W5', 'yard', day('2026-10-01'), day('2026-12-31'))[-1], day('2026-10-30'))
        self.assertEqual(pickup_dates(self.town, 'E2', 'leaves', day('2026-10-01'), day('2026-10-31'))[0], day('2026-10-13'))
        self.assertEqual(pickup_dates(self.town, 'E1', 'leaves', day('2026-10-01'), day('2026-10-31'))[0], day('2026-10-19'))
        #Friday 3/26/2027 is Good Friday, so the last pickup moves to Saturday
        self.assertEqual(pickup_dates(self.town, 'W5', 'leaves', day('2027-03-01'), day('2027-04-30'))[-1], day('2027-03-27'))

    def test_2026_rolls_over_into_2027(self):
        #The borough rarely updates its schedule: the same holidays, weekend ones moved to a weekday
        found = sorted(d.isoformat() for d in pickup_schedule.holidays_in_year(self.town, 2027) if d.weekday() < 5)
        self.assertEqual(len(found), len(HOLIDAYS_2026))
        for holiday in ('2027-03-26', '2027-06-18', '2027-07-05', '2027-11-02', '2027-11-26', '2027-12-24'):
            self.assertIn(holiday, found)
        #Seasons repeat by month
        self.assertEqual(pickup_dates(self.town, 'E1', 'yard', day('2027-03-01'), day('2027-04-30'))[0], day('2027-04-05'))
        self.assertEqual(pickup_dates(self.town, 'W5', 'yard', day('2027-10-01'), day('2027-11-30'))[-1], day('2027-10-29'))
        self.assertEqual(pickup_dates(self.town, 'E1', 'leaves', day('2027-09-01'), day('2027-10-31'))[0], day('2027-10-04'))
        self.assertEqual(pickup_dates(self.town, 'E1', 'leaves', day('2027-04-01'), day('2027-09-30')), [])
        #Christmas (observed) Friday 12/24/2027: no garbage on the west side. 5th Ward recycling
        #cannot go to Saturday (Christmas Day) or Sunday, so it goes to Monday
        week = (day('2027-12-19'), day('2027-12-25'))
        self.assertEqual(pickup_dates(self.town, 'W4', 'garbage', *week), [day('2027-12-21')])
        self.assertEqual(pickup_dates(self.town, 'W5', 'containers', day('2027-12-19'), day('2028-01-01')),
                         [day('2027-12-27'), day('2027-12-31')])


class WeekOfTheMonth(unittest.TestCase):
    def test_last_and_first(self):
        stream = {'days': ['Thursday'], 'nth_in_month': [-1]}
        self.assertTrue(pickup_schedule.is_scheduled(stream, 'x', day('2026-11-26')))
        self.assertFalse(pickup_schedule.is_scheduled(stream, 'x', day('2026-11-19')))
        stream = {'days': ['Wednesday'], 'nth_in_month_by_zone': {'a': [1]}, 'months': [11]}
        self.assertTrue(pickup_schedule.is_scheduled(stream, 'a', day('2026-11-04')))
        self.assertFalse(pickup_schedule.is_scheduled(stream, 'a', day('2026-11-11')))
        self.assertFalse(pickup_schedule.is_scheduled(stream, 'b', day('2026-11-04')))
        self.assertFalse(pickup_schedule.is_scheduled(stream, 'a', day('2026-12-02')))


class RoselleAddresses(unittest.TestCase):
    def setUp(self):
        self.book = AddressBook()
        with open(os.path.join(TOP, 'data', 'roselle.csv'), newline='', encoding='utf-8') as handle:
            for row in csv.DictReader(handle):
                self.book.add('roselle', row['Street_Name'], row['Low_Range'], row['High_Range'],
                              row['Side'], row['ZIP'], row['Zone'], row['Needs_Check'] == 'Y')

    def zone(self, number, street):
        found = self.book.find('roselle', number, street, '07203')
        return found and (found['zone'], found['needs_check'])

    def test_streets_east_and_west_of_chestnut(self):
        self.assertEqual(self.zone(507, 'East 3rd Avenue'), ('E1', False))
        self.assertEqual(self.zone(437, 'E 5th Ave'), ('E2', False))
        self.assertEqual(self.zone(111, 'E 1st Ave'), ('E3', False))
        self.assertEqual(self.zone(123, 'W 1st Ave'), ('W4', False))
        self.assertEqual(self.zone(146, 'W 9th Ave'), ('W3', False))
        self.assertEqual(self.zone(249, 'West 7th Avenue'), ('W5', False))

    def test_chestnut_street_itself_is_split_by_side_and_checked(self):
        self.assertEqual(self.zone(519, 'Chestnut St'), ('E3', True))
        self.assertEqual(self.zone(520, 'Chestnut St'), ('W3', True))

    def split(self, number, street, location=None):
        """(zone, needs check, street matched, how) for an address that may lack its E or W."""
        town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['roselle']
        found = self.book.find_on_split_street('roselle', number, street, '07203', town['direction_split'], location)
        return found and (found['zone'], found['needs_check'], found['street'], found['how'])

    def test_avenue_without_e_or_w_found_by_the_house_number(self):
        #145 is only on E 7th Ave, 147 only on W 7th Ave
        self.assertEqual(self.split(145, '7th Ave'), ('E3', False, 'E 7TH AVE', 'number'))
        self.assertEqual(self.split(147, '7th Ave'), ('W3', False, 'W 7TH AVE', 'number'))
        #West 5th Ave is "5th Ave" in the county list: 124 is only on E 5th Ave, 120 only on the west part
        self.assertEqual(self.split(124, 'Fifth Avenue'), ('E3', False, 'E 5TH AVE', 'number'))
        self.assertEqual(self.split(120, '5th Ave'), ('W3', False, '5TH AVE', 'number'))

    def test_avenue_without_e_or_w_found_by_the_map_location(self):
        #152 is on both parts. Points on the 100 blocks, from the Census map
        west, east = (40.6524, -74.2634), (40.6528, -74.2603)
        self.assertEqual(self.split(152, '7th Ave', west), ('W3', False, 'W 7TH AVE', 'location'))
        self.assertEqual(self.split(152, '7th Ave', east), ('E3', False, 'E 7TH AVE', 'location'))
        self.assertEqual(self.split(437, '5th Ave', (40.6547, -74.2520)), ('E2', False, 'E 5TH AVE', 'location'))
        #Right next to Chestnut St (at 7th Ave) it is checked
        self.assertEqual(self.split(152, '7th Ave', (40.65261, -74.26180)), ('E3', True, 'E 7TH AVE', 'location'))

    def test_avenue_without_e_or_w_and_no_location_is_west_and_checked(self):
        self.assertEqual(self.split(152, '7th Ave'), ('W3', True, 'W 7TH AVE', 'default'))
        self.assertEqual(self.split(437, '5th Ave'), ('W5', True, '5TH AVE', 'default'))
        #Not on either part: the nearest west stretch
        self.assertEqual(self.split(150, '7th Ave'), ('W3', True, 'W 7TH AVE', 'default'))

    def test_e_or_w_given_is_used(self):
        self.assertEqual(self.split(152, 'E 7th Ave'), ('E3', False, 'E 7TH AVE', 'given'))
        self.assertEqual(self.split(152, 'West 7th Avenue'), ('W3', False, 'W 7TH AVE', 'given'))
        #"W 5th Ave" is "5TH AVE" in the table
        self.assertEqual(self.split(127, 'W 5th Ave'), ('W3', False, '5TH AVE', 'given'))
        self.assertEqual(self.split(127, 'E 5th Ave'), ('E3', False, 'E 5TH AVE', 'given'))
        #The location does not overrule an E or W that was given
        self.assertEqual(self.split(152, 'W 7th Ave', (40.6528, -74.2603)), ('W3', False, 'W 7TH AVE', 'given'))

    def test_streets_without_an_east_and_west_part_are_left_to_find(self):
        self.assertIsNone(self.split(519, 'Chestnut St'))
        self.assertIsNone(self.split(111, 'E Ninety St'))

    def test_every_zone_is_in_the_rules_file(self):
        town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['roselle']
        zones = {row[4] for rows in self.book.streets.values() for row in rows}
        self.assertEqual(zones, set(town['zones']))


if __name__ == '__main__':
    unittest.main()
