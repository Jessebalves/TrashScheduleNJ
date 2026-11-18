"""Works out one week of pickups for a town and a zone.

Each town is described by a file in the towns/ folder, see towns/README.md.
The file lists the town's holidays and its "streams" (garbage, paper, ...).
For every stream it says which days it is picked up, whether it is picked up
every week or every other week, and what happens on a holiday.

Nothing in this file talks to MySQL or to Flask, so it can be tested on its own.
"""
import datetime
import json
import os

#A week on the website runs from Sunday to Saturday
DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']


def parse_date(text):
    """Turn "2026-01-13" into a date."""
    return datetime.date.fromisoformat(text)


def day_name(date):
    """Monday is 0 for Python, Sunday is 0 in DAY_NAMES."""
    return DAY_NAMES[(date.weekday() + 1) % 7]


def sunday_of(date):
    """The Sunday that starts the week a date is in."""
    return date - datetime.timedelta(days=(date.weekday() + 1) % 7)


def load_towns(folder):
    """Read every towns/*.json file. Returns a dictionary of town id -> town."""
    towns = {}
    for file_name in sorted(os.listdir(folder)):
        if not file_name.endswith('.json'):
            continue
        with open(os.path.join(folder, file_name), encoding='utf-8') as handle:
            town = json.load(handle)
        towns[town['id']] = town
    return towns


def find_town(towns, name='', zip_code=''):
    """Find a town by its name ("Kenilworth", "Kenilworth Borough") or, failing that, by ZIP code.

    A ZIP code only decides the town when exactly one town uses it.
    """
    wanted = ' '.join(str(name or '').upper().replace('.', ' ').split())
    if wanted:
        for town in towns.values():
            names = [town['id'], town['name']] + town.get('other_names', [])
            if wanted in [n.upper() for n in names]:
                return town
        #A name was given and it is not one of ours: do not guess from the ZIP code
        return None
    matches = [town for town in towns.values() if zip_code and zip_code in town.get('zip_codes', [])]
    return matches[0] if len(matches) == 1 else None


def holidays_in_year(town, year):
    """Return the town's holidays for one year as a dictionary of date -> name.

    A holiday is written in the town file in one of two ways:
        {"name": "Christmas Day", "month": 12, "day": 25}
        {"name": "Labor Day", "month": 9, "weekday": "Monday", "nth": 1}
    nth counts from the start of the month, -1 means the last one of the month.
    """
    holidays = {}
    for holiday in town.get('holidays', []):
        month = holiday['month']
        if 'day' in holiday:
            date = datetime.date(year, month, holiday['day'])
        else:
            matching = []
            date = datetime.date(year, month, 1)
            while date.month == month:
                if day_name(date) == holiday['weekday']:
                    matching.append(date)
                date += datetime.timedelta(days=1)
            nth = holiday['nth']
            date = matching[nth - 1] if nth > 0 else matching[nth]
        holidays[date] = holiday['name']
    return holidays


def holiday_name(town, date):
    """The name of the holiday on a date, or None."""
    return holidays_in_year(town, date.year).get(date)


def is_scheduled(stream, zone_id, date):
    """Is this stream normally picked up on this date, before holidays are looked at?"""
    if 'days_by_zone' in stream:
        days = stream['days_by_zone'].get(zone_id, [])
    else:
        days = stream['days']
    if day_name(date) not in days:
        return False

    #Some streams only run for part of the year, like yard waste
    if 'first_date' in stream and date < parse_date(stream['first_date']):
        return False
    if 'last_date' in stream and date > parse_date(stream['last_date']):
        return False

    #Every other week: count whole weeks from a date that is known to be a pickup
    #day. Counting from one fixed date keeps the pattern right across New Year.
    if 'every_other_week_from' in stream:
        start = sunday_of(parse_date(stream['every_other_week_from']))
        weeks = (sunday_of(date) - start).days // 7
        if weeks % 2 != 0:
            return False
    return True


def resolve_pickup(town, stream, date):
    """Where a regular pickup on `date` really happens, after moved dates and holidays.

    Returns (actual_date, why):
        (date, None)                     a normal pickup
        (other_date, "moved")            the town moved this one pickup (moved_dates)
        (other_date, <holiday name>)     on_holiday "next_day": moved past the holiday
        (None, <holiday name>)           on_holiday "skip": no pickup this time
    """
    moved_to = stream.get('moved_dates', {}).get(date.isoformat())
    if moved_to is not None:
        return parse_date(moved_to), 'moved'
    holiday = holiday_name(town, date)
    if holiday is None:
        return date, None
    if stream.get('on_holiday') == 'next_day':
        moved = date + datetime.timedelta(days=1)
        while holiday_name(town, moved) is not None:
            moved += datetime.timedelta(days=1)
        return moved, holiday
    return None, holiday


def week_schedule(town, zone_id, today):
    """Return the pickups for the Sunday to Saturday week that `today` is in.

    The result is a dictionary that is sent to the web page as it is:
        today        "2026-11-16"
        days         7 entries: {"name": "Sunday", "date": "2026-11-15", "holiday": None or its name}
        streams      one entry per stream: {"id", "label", "pickups": ["Monday", "Thursday"]}
        changes      sentences about pickups that a holiday moved or cancelled this week
    """
    week_start = sunday_of(today)
    week = [week_start + datetime.timedelta(days=n) for n in range(7)]

    days = [{'name': day_name(date), 'date': date.isoformat(), 'holiday': holiday_name(town, date)}
            for date in week]
    streams = []
    changes = []

    for stream in town['streams']:
        pickups = set()
        #Start a week early: a pickup moved off last Saturday lands on this Sunday
        for n in range(-7, 7):
            date = week_start + datetime.timedelta(days=n)
            if not is_scheduled(stream, zone_id, date):
                continue
            moved, why = resolve_pickup(town, stream, date)
            if why is None:
                pickups.add(date)
            #A town sometimes moves a single pickup, the town file lists those
            elif why == 'moved':
                pickups.add(moved)
                if date in week or moved in week:
                    changes.append("%s moves from %s to %s this week." % (
                        stream['label'], day_name(date), day_name(moved)))
            elif moved is not None:
                holiday = why
                pickups.add(moved)
                if date in week or moved in week:
                    changes.append("%s moves from %s to %s because of %s." % (
                        stream['label'], day_name(date), day_name(moved), holiday))
            else:
                holiday = why
                #'skip': there is no pickup, it is collected on the next regular day
                if date in week:
                    changes.append("No %s pickup on %s because of %s. It will be collected on your next regular day." % (
                        stream['label'].lower(), day_name(date), holiday))

        streams.append({
            'id': stream['id'],
            'label': stream['label'],
            'pickups': [day_name(date) for date in week if date in pickups],
        })

    return {'today': today.isoformat(), 'days': days, 'streams': streams, 'changes': changes}


MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
               'August', 'September', 'October', 'November', 'December']


def long_date(date):
    """2026-11-26 -> "Thursday, Nov 26"."""
    return "%s, %s %d" % (day_name(date), MONTH_NAMES[date.month - 1][:3], date.day)


def upcoming(town, zone_id, today, count=4, max_days=182):
    """The next `count` pickup days from `today` on (today included), for the new website design.

    Returns a dictionary that is sent to the web page as it is:
        pickups   [{"date", "day", "holiday", "streams": [{"id", "label", "moved"}]}]
                  one entry per date that has at least one pickup, earliest first.
                  "moved" is true when a holiday or the town moved that pickup there.
        notices   [{"date", "new_date", "holiday", "message"}] the holiday changes and
                  moved pickups between today and the last of those pickups.
                  new_date is None when the pickup is skipped.
    """
    by_date = {}
    notices = []
    #Start a week early: a pickup moved off a past day can land on today or later
    first = today - datetime.timedelta(days=7)
    last = today + datetime.timedelta(days=max_days)
    date = first
    while date <= last:
        for stream in town['streams']:
            if not is_scheduled(stream, zone_id, date):
                continue
            actual, why = resolve_pickup(town, stream, date)
            if actual is not None and today <= actual <= last:
                streams = by_date.setdefault(actual, [])
                streams.append({'id': stream['id'], 'label': stream['label'], 'moved': why is not None})
            if why is None:
                continue
            if actual is None:
                if date < today:
                    continue
                message = "No %s pickup on %s because of %s. It will be collected on your next regular day." % (
                    stream['label'].lower(), long_date(date), why)
            elif actual < today:
                continue
            elif why == 'moved':
                message = "%s moves from %s to %s." % (stream['label'], long_date(date), long_date(actual))
            else:
                message = "%s moves from %s to %s because of %s." % (
                    stream['label'], long_date(date), long_date(actual), why)
            notices.append({'date': date.isoformat(), 'new_date': actual.isoformat() if actual else None,
                            'holiday': None if why == 'moved' else why, 'message': message})
        date += datetime.timedelta(days=1)

    #Keep the streams in the order of the town file
    order = {stream['id']: n for n, stream in enumerate(town['streams'])}
    pickups = []
    for date in sorted(by_date)[:count]:
        pickups.append({'date': date.isoformat(), 'day': day_name(date), 'holiday': holiday_name(town, date),
                        'streams': sorted(by_date[date], key=lambda s: order[s['id']])})

    #Only the changes up to the last pickup shown matter to the visitor
    if pickups:
        end = pickups[-1]['date']
        notices = [n for n in notices if n['date'] <= end]
    else:
        notices = []
    notices.sort(key=lambda n: n['date'])
    return {'pickups': pickups, 'notices': notices}
