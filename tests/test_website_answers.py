"""Sends requests to the Flask server the way the web page does, without MySQL."""
import os
import sys
import unittest

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)
os.environ['ADDRESS_SOURCE'] = 'csv'

import test_server

test_server.load_everything()


class WebsiteAnswers(unittest.TestCase):
    def setUp(self):
        self.client = test_server.app.test_client()

    def ask(self, **address):
        response = self.client.post('/data', json=address)
        return response.status_code, response.get_json()

    def test_next_week_button_shows_the_holiday(self):
        #Monday 11/16/2026 plus one week is Thanksgiving week
        status, answer = self.ask(house_number='350', street='Coolidge Dr', town='Kenilworth', date='2026-11-16', week=1)
        self.assertEqual(status, 200)
        self.assertEqual(answer['today'], '2026-11-16')
        self.assertEqual(answer['days'][0]['date'], '2026-11-22')
        self.assertEqual([day['holiday'] for day in answer['days']],
                         [None, None, None, None, 'Thanksgiving Day', None, None])
        status, answer = self.ask(house_number='350', street='Coolidge Dr', town='Kenilworth', week='soon')
        self.assertEqual(status, 400)

    def test_elizabeth_address_picked_from_google(self):
        status, answer = self.ask(house_number='142', street='Elm St', town='Elizabeth', zip='07208', date='2026-11-16')
        self.assertEqual(status, 200)
        self.assertEqual(answer['town'], {'id': 'elizabeth', 'name': 'Elizabeth'})
        self.assertEqual(answer['zone'], {'id': '4', 'word': 'Ward', 'label': 'Ward 4'})
        self.assertEqual([s['label'] for s in answer['streams']], ['Paper', 'Metal', 'Garbage'])
        self.assertEqual(answer['streams'][2]['pickups'], ['Tuesday', 'Friday'])
        self.assertEqual(answer['notes'], [])

    def test_old_one_line_address_still_works(self):
        status, answer = self.ask(key='142 elm st 07208')
        self.assertEqual(status, 200)
        self.assertEqual(answer['zone']['id'], '4')

    def test_kenilworth_address(self):
        status, answer = self.ask(house_number='350', street='Coolidge Dr', town='Kenilworth', zip='07033', date='2026-11-17')
        self.assertEqual(status, 200)
        self.assertEqual(answer['zone']['label'], 'Tuesday & Friday')
        pickups = {s['id']: s['pickups'] for s in answer['streams']}
        self.assertEqual(pickups, {'garbage': ['Tuesday', 'Friday'], 'paper': ['Tuesday'], 'containers': [], 'yard': []})

    def test_the_boulevard_goes_by_two_names(self):
        first = self.ask(house_number='150', street='Boulevard', town='Kenilworth', date='2026-06-01')
        second = self.ask(house_number='150', street='Kenilworth Blvd', town='Kenilworth', date='2026-06-01')
        self.assertEqual(first[0], 200)
        self.assertEqual(first, second)

    def test_town_can_come_from_the_zip_code(self):
        status, answer = self.ask(house_number='20', street='Epping Dr', zip='07033')
        self.assertEqual((status, answer['town']['name']), (200, 'Kenilworth'))

    def test_border_address_gets_a_note(self):
        status, answer = self.ask(house_number='20', street='S 20th St', town='Kenilworth', date='2026-06-01')
        self.assertEqual(status, 200)
        self.assertIn('Kenilworth DPW, 908-276-5073', answer['notes'][0])

    def test_schedule_past_the_checked_year_gets_a_note(self):
        status, answer = self.ask(house_number='20', street='Epping Dr', town='Kenilworth', date='2027-02-01')
        self.assertIn('have not checked', answer['notes'][0])

    def test_town_that_is_not_covered(self):
        status, answer = self.ask(house_number='10', street='Main St', town='Cranford', zip='07016')
        self.assertEqual(status, 404)
        self.assertEqual(answer['error'], 'Cranford is not covered yet. The towns we cover are: Elizabeth, Hillside, Kenilworth, Roselle, Union.')

    def test_address_that_is_not_found(self):
        status, answer = self.ask(house_number='10', street='No Such Street', town='Elizabeth')
        self.assertEqual(status, 404)
        self.assertIn('could not find', answer['error'])

    def test_bad_requests_get_a_message_not_a_crash(self):
        for body in ({}, {'key': 'x'}, {'key': 'abc elm st 07208'}, {'key': '142 elm st 0720'},
                     {'house_number': '12B', 'street': 'Elm St', 'town': 'Elizabeth'},
                     {'house_number': '12', 'street': '', 'town': 'Elizabeth'},
                     {'house_number': '12', 'street': 'Elm St', 'town': 'Elizabeth', 'zip': 'abc'},
                     {'house_number': '142', 'street': 'Elm St', 'town': 'Elizabeth', 'date': 'tomorrow'}):
            status, answer = self.ask(**body)
            self.assertEqual(status, 400, body)
            self.assertTrue(answer['error'])
        response = self.client.post('/data', data='not json', content_type='text/plain')
        self.assertEqual(response.status_code, 400)

    def test_config_lists_the_towns(self):
        answer = self.client.get('/config').get_json()
        self.assertEqual(answer['towns'], [{'id': 'elizabeth', 'name': 'Elizabeth'}, {'id': 'hillside', 'name': 'Hillside'},
                                          {'id': 'kenilworth', 'name': 'Kenilworth'}, {'id': 'roselle', 'name': 'Roselle'},
                                          {'id': 'union', 'name': 'Union'}])
        self.assertEqual(answer['googleMapsKey'], os.environ.get('GOOGLE_MAPS_API_KEY', ''))


if __name__ == '__main__':
    unittest.main()
