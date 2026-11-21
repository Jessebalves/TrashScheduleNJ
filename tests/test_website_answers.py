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
        #From the city's 2026 calendar, shown under "From your town"
        self.assertIn('after 6:00 PM', answer['notes'][0])

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

    def test_roselle_avenue_without_e_or_w(self):
        #Google gave "152 7th Ave", a house number on both E and W 7th Ave
        address = dict(house_number='152', street='7th Ave', town='Roselle', zip='07203', date='2026-11-16')
        status, answer = self.ask(location={'lat': 40.6528, 'lng': -74.2603}, **address)
        self.assertEqual((status, answer['zone']['id'], answer['address']['street']), (200, 'E3', 'E 7th Ave'))
        self.assertEqual(answer['streams'][0]['pickups'], ['Monday', 'Thursday'])
        self.assertNotIn('East and a West part', ' '.join(answer['notes']))
        status, answer = self.ask(location={'lat': 40.6524, 'lng': -74.2634}, **address)
        self.assertEqual((answer['zone']['id'], answer['address']['street']), ('W3', 'W 7th Ave'))
        #Typed in, or a location that is no use: the west part, with a note
        for location in (None, {'lat': 'x', 'lng': 1}, {'lat': 400, 'lng': 0}, 'here'):
            status, answer = self.ask(location=location, **address)
            self.assertEqual((status, answer['zone']['id'], answer['address']['street']), (200, 'W3', 'W 7th Ave'))
            self.assertIn('East and a West part', answer['notes'][0])
        status, answer = self.ask(key='152 7th Ave 07203')
        self.assertEqual(answer['zone']['id'], 'W3')
        #With the E or W, as before
        status, answer = self.ask(house_number='152', street='E 7th Ave', town='Roselle')
        self.assertNotIn('East and a West part', ' '.join(answer['notes']))
        self.assertEqual((answer['zone']['id'], answer['address'].get('street')), ('E3', None))
        #West 5th Ave is "5th Ave" in the county list
        status, answer = self.ask(key='127 W 5th Ave 07203')
        self.assertEqual((status, answer['zone']['id']), (200, 'W3'))

    def test_roselle_park_is_not_roselle(self):
        #Google's "322 W Clay Ave, Roselle Park, NJ 07204": west of Chestnut St, Monday & Thursday
        status, answer = self.ask(house_number='322', street='W Clay Ave', town='Roselle Park', zip='07204', date='2026-11-16')
        self.assertEqual((status, answer['town']['id'], answer['zone']['id']), (200, 'roselle_park', 'W'))
        self.assertEqual(answer['streams'][0]['pickups'], ['Monday', 'Thursday'])
        status, answer = self.ask(key='322 W Clay Ave 07204')
        self.assertEqual(answer['town']['id'], 'roselle_park')
        status, answer = self.ask(house_number='322', street='W Clay Ave', town='Roselle', zip='07203')
        self.assertEqual(status, 404)

    def test_cranford_recycling_only_with_a_bold_note(self):
        status, answer = self.ask(house_number='20', street='Hollywood Ave', town='Cranford', zip='07016', date='2026-11-16')
        self.assertEqual((status, answer['zone']['id']), (200, 'ST'))
        self.assertEqual([s['id'] for s in answer['streams']], ['containers'])
        self.assertEqual(answer['streams'][0]['pickups'], ['Tuesday'])
        #The private hauler note comes first and is marked to be shown in bold
        self.assertEqual(answer['notes'][0], answer['important_notes'][0])
        self.assertIn('private hauler', answer['important_notes'][0])
        status, answer = self.ask(house_number='20', street='Hollywood Ave', town='Cranford', date='2027-02-01')
        self.assertIn('private hauler', answer['notes'][0])
        self.assertIn('have not checked', answer['notes'][1])
        #Other towns have none
        status, answer = self.ask(house_number='142', street='Elm St', town='Elizabeth')
        self.assertEqual(answer['important_notes'], [])

    def test_street_with_or_without_its_direction(self):
        status, answer = self.ask(house_number='432', street='W Grove St', town='Westfield', zip='07090')
        self.assertEqual((status, answer['zone']['id']), (200, '8'))
        status, answer = self.ask(house_number='432', street='Grove St', town='Westfield', zip='07090')
        self.assertEqual((status, answer['zone']['id']), (200, '8'))
        #The county list has some of N Scotch Plains Ave as plain "Scotch Plains Ave"
        status, answer = self.ask(house_number='450', street='Scotch Plains Ave', town='Westfield', zip='07090')
        self.assertEqual(status, 200)

    def test_street_name_with_or_without_spaces(self):
        #Google: "Mae Belle Dr"; the county list and the Census: "Maebelle Dr"
        status, answer = self.ask(house_number='32', street='Mae Belle Dr', town='Clark', zip='07066')
        self.assertEqual((status, answer['zone']['id']), (200, 'Z1W4'))

    def test_town_that_is_not_covered(self):
        status, answer = self.ask(house_number='10', street='Main St', town='Summit', zip='07901')
        self.assertEqual(status, 404)
        self.assertEqual(answer['error'], 'Summit is not covered yet. The towns we cover are: Aberdeen, Clark, Cranford, Elizabeth, Hillside, Kenilworth, Linden, Rahway, Roselle, Roselle Park, Union, Westfield.')

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
        self.assertEqual(answer['towns'], [{'id': 'aberdeen', 'name': 'Aberdeen'}, {'id': 'clark', 'name': 'Clark'}, {'id': 'cranford', 'name': 'Cranford'}, {'id': 'elizabeth', 'name': 'Elizabeth'}, {'id': 'hillside', 'name': 'Hillside'},
                                          {'id': 'kenilworth', 'name': 'Kenilworth'}, {'id': 'linden', 'name': 'Linden'}, {'id': 'rahway', 'name': 'Rahway'}, {'id': 'roselle', 'name': 'Roselle'}, {'id': 'roselle_park', 'name': 'Roselle Park'},
                                          {'id': 'union', 'name': 'Union'}, {'id': 'westfield', 'name': 'Westfield'}])
        self.assertEqual(answer['googleMapsKey'], os.environ.get('GOOGLE_MAPS_API_KEY', ''))


if __name__ == '__main__':
    unittest.main()
