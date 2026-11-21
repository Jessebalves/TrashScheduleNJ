"""Prints the town files' maintainer reminders that are due today (see towns/README.md)."""
import datetime
import os
import sys
import unittest
import warnings

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)

import pickup_schedule


class Reminders(unittest.TestCase):
    def test_due_reminders_are_shown(self):
        towns = pickup_schedule.load_towns(os.path.join(TOP, 'towns'))
        for town in towns.values():
            for reminder in town.get('reminders', []):
                pickup_schedule.parse_date(reminder['from'])
                self.assertTrue(reminder['message'].strip(), town['id'])
        for name, message in pickup_schedule.due_reminders(towns, datetime.date.today()):
            warnings.warn('REMINDER (%s): %s' % (name, message))


if __name__ == '__main__':
    unittest.main()
