"""Elizabeth must keep working exactly as it did before other towns were added.

Run all the tests from the top folder of the project:

    python3 -m unittest discover tests
"""
import csv
import datetime
import os
import sys
import unittest

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)

import pickup_schedule
from address_lookup import AddressBook, normalize_street


def load_book():
    book = AddressBook()
    with open(os.path.join(TOP, 'data', 'elizabeth.csv'), newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        book.add('elizabeth', row['Street_Name'], row['Low_Range'], row['High_Range'],
                 row['Side'], row['ZIP'], row['Zone'], row['Needs_Check'])
    return book, rows


def old_website_week(ward, today):
    """What the first version of index.js marked with an X, written out again here
    on its own so that the new code is checked against the old rules.

    Returns {'paper': [...], 'metal': [...], 'garbage': [...]} with day numbers, Sunday = 0.
    """
    sunday = today - datetime.timedelta(days=(today.weekday() + 1) % 7)
    week = [sunday + datetime.timedelta(days=n) for n in range(7)]

    def holiday(date):
        month, day, weekday = date.month, date.day, (date.weekday() + 1) % 7
        if (month, day) in ((1, 1), (7, 4), (12, 25)):
            return True
        if month == 5 and weekday == 1 and day > 24:        #last Monday of May
            return True
        if month == 9 and weekday == 1 and day <= 7:        #first Monday of September
            return True
        if month == 11 and weekday == 4 and 22 <= day <= 28:  #fourth Thursday of November
            return True
        return False

    marked_h = [holiday(date) for date in week]

    def mark(day):
        #An X goes on the day, or on the day after when the day is a holiday
        return day + 1 if marked_h[day] else day

    #Paper and metal take turns on Wednesday. The week of Sunday December 31st 2023 was a metal week.
    weeks = (sunday - datetime.date(2023, 12, 31)).days // 7
    paper_week = weeks % 2 != 0
    garbage_days = (1, 4) if ward < 4 else (2, 5)
    return {
        'paper': [mark(3)] if paper_week else [],
        'metal': [] if paper_week else [mark(3)],
        'garbage': [mark(day) for day in garbage_days],
    }


class ElizabethAddresses(unittest.TestCase):
    def test_every_row_of_the_table_gives_its_own_ward(self):
        book, rows = load_book()
        self.assertEqual(len(rows), 1445)
        for row in rows:
            for number in (int(row['Low_Range']), int(row['High_Range'])):
                found = book.find('elizabeth', number, row['Street_Name'], row['ZIP'])
                self.assertEqual(found, {'zone': row['Zone'], 'needs_check': False, 'zip': row['ZIP']}, row)

    def test_street_names_can_be_written_in_different_ways(self):
        book, _ = load_book()
        for text in ('elm st', 'Elm Street', 'ELM ST.', ' elm   street '):
            self.assertEqual(book.find('elizabeth', 142, text, '07208')['zone'], '4', text)
        self.assertEqual(normalize_street('North Broad Street'), 'N BROAD ST')
        self.assertEqual(normalize_street('North Ave'), 'NORTH AVE')
        self.assertEqual(normalize_street('1st Avenue'), normalize_street('FIRST AVE'))
        self.assertEqual(normalize_street('Bayway Terr.'), 'BAYWAY TER')

    def test_wrong_zip_code_or_unknown_street_is_not_found(self):
        book, _ = load_book()
        self.assertIsNone(book.find('elizabeth', 142, 'Elm St', '07033'))
        self.assertIsNone(book.find('elizabeth', 142, 'No Such St', '07208'))
        self.assertIsNone(book.find('kenilworth', 142, 'Elm St', '07208'))

    def test_zip_code_may_be_left_out(self):
        book, _ = load_book()
        self.assertEqual(book.find('elizabeth', 142, 'Elm St')['zone'], '4')


class ElizabethSchedule(unittest.TestCase):
    def test_every_day_of_six_years_matches_the_old_website(self):
        town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['elizabeth']
        today = datetime.date(2024, 1, 1)
        while today <= datetime.date(2029, 12, 31):
            for ward in (1, 2, 3, 4, 5, 6):
                expected = old_website_week(ward, today)
                answer = pickup_schedule.week_schedule(town, str(ward), today)
                for stream in answer['streams']:
                    days = [pickup_schedule.DAY_NAMES.index(name) for name in stream['pickups']]
                    self.assertEqual(days, expected[stream['id']], (today, ward, stream['id']))
            today += datetime.timedelta(days=1)

    def test_thanksgiving_week_2026(self):
        town = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))['elizabeth']
        answer = pickup_schedule.week_schedule(town, '1', datetime.date(2026, 11, 23))
        garbage = [s for s in answer['streams'] if s['id'] == 'garbage'][0]
        self.assertEqual(garbage['pickups'], ['Monday', 'Friday'])
        self.assertEqual([d['holiday'] for d in answer['days']], [None, None, None, None, 'Thanksgiving', None, None])
        self.assertEqual(answer['changes'], ['Garbage moves from Thursday to Friday because of Thanksgiving.'])


if __name__ == '__main__':
    unittest.main()
