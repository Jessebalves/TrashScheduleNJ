"""Kenilworth is checked against the dates printed in the borough's 2026 Information Guide."""
import csv
import datetime
import os
import sys
import unittest

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)

import pickup_schedule
from address_lookup import AddressBook

#Copied from the "2026 Kenilworth DPW Service Dates List" and "Sanitation Holidays"
PAPER = """JAN 13, JAN 27, FEB 10, FEB 24, MAR 10, MAR 24, APR 7, APR 21, MAY 5, MAY 19, JUN 2, JUN 16, JUN 30,
JUL 14, JUL 28, AUG 11, AUG 25, SEP 8, SEP 22, OCT 6, OCT 20, NOV 4, NOV 17, DEC 1, DEC 15, DEC 29"""
CONTAINERS = """JAN 6, JAN 20, FEB 3, FEB 17, MAR 3, MAR 17, MAR 31, APR 14, APR 28, MAY 12, MAY 26, JUN 9, JUN 23,
JUL 7, JUL 21, AUG 4, AUG 18, SEP 1, SEP 15, SEP 29, OCT 13, OCT 27, NOV 10, NOV 24, DEC 8, DEC 22"""
YARD = """JAN 8, JAN 15, JAN 22, JAN 29, FEB 5, FEB 12, FEB 19, FEB 26, MAR 5, MAR 12, MAR 19, MAR 26,
APR 2, APR 9, APR 16, APR 23, APR 30, MAY 7, MAY 14, MAY 21, MAY 28, JUN 4, JUN 11, JUN 18, JUN 25,
JUL 2, JUL 9, JUL 16, JUL 23, JUL 30, AUG 6, AUG 13, AUG 20, AUG 27, SEP 3, SEP 10, SEP 17, SEP 24,
OCT 1, OCT 8, OCT 15, OCT 22"""
HOLIDAYS = "JAN 1, JAN 19, MAY 25, JUL 4, SEP 7, NOV 26, DEC 25"

MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']


def dates(text):
    result = []
    for item in text.replace('\n', ' ').split(','):
        month, day = item.split()
        result.append(datetime.date(2026, MONTHS.index(month) + 1, int(day)))
    return result


def pickup_dates(town, zone, stream_id):
    """Every date in 2026 the website would mark for one stream."""
    found = set()
    sunday = datetime.date(2025, 12, 28)
    while sunday.year < 2027:
        answer = pickup_schedule.week_schedule(town, zone, sunday)
        stream = [s for s in answer['streams'] if s['id'] == stream_id][0]
        for day in answer['days']:
            if day['name'] in stream['pickups'] and day['date'].startswith('2026'):
                found.add(datetime.date.fromisoformat(day['date']))
        sunday += datetime.timedelta(days=7)
    return sorted(found)


class KenilworthSchedule(unittest.TestCase):
    def setUp(self):
        self.town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['kenilworth']

    def test_holidays_match_the_guide(self):
        self.assertEqual(sorted(pickup_schedule.holidays_in_year(self.town, 2026)), dates(HOLIDAYS))

    def test_bottles_and_cans_match_the_guide(self):
        self.assertEqual(pickup_dates(self.town, 'MON_THU', 'containers'), dates(CONTAINERS))

    def test_cardboard_and_paper_match_the_guide(self):
        #NOV 4 is a Wednesday (the day after Election Day) in a list of Tuesdays,
        #the town file carries it as a moved date
        self.assertEqual(pickup_dates(self.town, 'MON_THU', 'paper'), dates(PAPER))

    def test_vegetative_waste_matches_the_guide(self):
        self.assertEqual(pickup_dates(self.town, 'MON_THU', 'yard'), dates(YARD))

    def test_garbage_is_twice_a_week_and_skipped_on_holidays(self):
        for zone, days in (('MON_THU', (0, 3)), ('TUE_FRI', (1, 4)), ('WED_SAT', (2, 5))):
            expected = []
            date = datetime.date(2026, 1, 1)
            while date.year == 2026:
                if date.weekday() in days and date not in dates(HOLIDAYS):
                    expected.append(date)
                date += datetime.timedelta(days=1)
            self.assertEqual(pickup_dates(self.town, zone, 'garbage'), expected, zone)

    def test_thanksgiving_week_says_what_changed(self):
        answer = pickup_schedule.week_schedule(self.town, 'MON_THU', datetime.date(2026, 11, 24))
        self.assertEqual(answer['changes'], [
            "No garbage pickup on Thursday because of Thanksgiving Day. It will be collected on your next regular day."])


class KenilworthAddresses(unittest.TestCase):
    def setUp(self):
        self.book = AddressBook()
        with open(os.path.join(TOP, 'data', 'kenilworth.csv'), newline='', encoding='utf-8') as handle:
            for row in csv.DictReader(handle):
                self.book.add('kenilworth', row['Street_Name'], row['Low_Range'], row['High_Range'],
                              row['Side'], row['ZIP'], row['Zone'], row['Needs_Check'])

    def test_one_address_well_inside_each_route(self):
        #Read off the Sanitation Routes Map
        for number, street, zone in (
                (620, 'Summit Ave', 'MON_THU'),       #south east of the Boulevard
                (640, 'Newark Avenue', 'MON_THU'),
                (20, 'Epping Dr', 'TUE_FRI'),         #the west end
                (350, 'Coolidge Drive', 'TUE_FRI'),   #south of the Boulevard, west of S 20th St
                (50, 'North 10th Street', 'TUE_FRI'), #south of Monroe Ave
                (250, 'N 10th St', 'WED_SAT'),        #north of Monroe Ave
                (300, 'Sheridan Ave', 'WED_SAT'),
                (100, 'N 22nd St', 'WED_SAT'),        #east of N 18th St
        ):
            self.assertEqual(self.book.find('kenilworth', number, street, '07033'),
                             {'zone': zone, 'needs_check': False}, (number, street))

    def test_a_street_on_the_border_is_marked_to_check(self):
        #S 20th St is the line between Tuesday & Friday and Monday & Thursday
        self.assertTrue(self.book.find('kenilworth', 20, 'S 20th St')['needs_check'])
        self.assertTrue(self.book.find('kenilworth', 300, 'Monroe Ave')['needs_check'])


if __name__ == '__main__':
    unittest.main()
