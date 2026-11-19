# Towns

Every town the website covers has two files:

| File | What is in it |
|---|---|
| `towns/<town>.json` | The rules: pickup types, days, holidays, notes |
| `data/<town>.csv` | The addresses: which zone each stretch of each street is in |

A **zone** is whatever the town uses to decide pickup days. Elizabeth uses its six wards, Hillside its two districts, Kenilworth three garbage routes, Union an East and a West zone. Roselle splits two ways, garbage by the side of Chestnut St and recycling by ward, so its zones are both together (`E3` is east of Chestnut St in the 3rd Ward). Aberdeen (Monmouth County) has two sections. A town with one schedule for everybody has a single zone.

After changing either file, run the tests (`python3 -m unittest discover tests`) and then `sudo ./install.sh` to put the change on the server.

## Adding a town: checklist

1. Find the town's own schedule (calendar, guide, service-date list) and write the rules file.
2. Collect the town's public statements for residents and put them in `notes` (the new design shows them under "From your town"): when to put things out, how to prepare recyclables, bulk and appliance rules and fees, yard waste, leaves and Christmas trees, drop-off yard hours, the holiday rule. Set `contact` to the office residents should call, and list every source with the date it was checked.
3. Check every date the town publishes (each stream, holidays, moved pickups) against what the website shows, and put them in `tests/test_<town>.py`.
4. Build `data/<town>.csv` (see "Where to get the addresses"), run the tests, then `sudo ./install.sh`.

## The rules file

```json
{
    "id": "kenilworth",
    "name": "Kenilworth",
    "other_names": ["Kenilworth Borough"],
    "zip_codes": ["07033"],
    "zone_word": "Garbage route",
    "zones": {"MON_THU": "Monday & Thursday", "TUE_FRI": "Tuesday & Friday"},
    "street_names": {"KENILWORTH BLVD": "BOULEVARD"},
    "holidays": [ ... ],
    "streams": [ ... ],
    "checked_through": "2026-12-31",
    "contact": "Kenilworth DPW, 908-276-5073",
    "notes": ["Put everything at the curb after 5 pm the night before pickup."],
    "sources": ["where the rules came from"]
}
```

- `name` and `other_names` are matched against the town Google Maps gives for an address.
- `zip_codes` are only used to guess the town when no town name was given.
- `zone_word` and `zones` are what the visitor is shown ("Garbage route: Monday & Thursday").
- `street_names` (optional) is for a street that goes by two names: the name on the left is looked up as the name on the right.
- `checked_through` (optional) is the last date the rules were checked against the town's own calendar. After it, the website tells visitors to confirm their days with `contact`.

### Holidays

A date that is the same every year, or the nth weekday of a month (`-1` is the last one):

```json
{"name": "Christmas Day", "month": 12, "day": 25},
{"name": "Labor Day", "month": 9, "weekday": "Monday", "nth": 1},
{"name": "Memorial Day", "month": 5, "weekday": "Monday", "nth": -1}
```

A holiday that is only on one year's calendar, like Christmas Eve when Christmas falls on a Saturday:

```json
{"name": "Christmas Eve", "date": "2027-12-24"}
```

### Streams

One entry for each row of the table, in the order they should be shown.

```json
{
    "id": "garbage",
    "label": "Garbage",
    "days_by_zone": {"MON_THU": ["Monday", "Thursday"], "TUE_FRI": ["Tuesday", "Friday"]},
    "on_holiday": "skip"
},
{
    "id": "paper",
    "label": "Cardboard & Paper",
    "days": ["Tuesday"],
    "every_other_week_from": "2026-01-13",
    "moved_dates": {"2026-11-03": "2026-11-04"},
    "on_holiday": "skip"
}
```

| Setting | Meaning |
|---|---|
| `days` | Pickup days, the same for the whole town |
| `days_by_zone` | Pickup days for each zone, use this instead of `days` |
| `every_other_week_from` | Leave out for every week. For every other week, any one date that is a pickup day |
| `every_other_week_from_by_zone` | The same for each zone, when zones take turns, like Aberdeen's two sections |
| `first_date`, `last_date` | Optional. The stream only runs between these dates, like yard waste |
| `months` | Optional. The stream only runs in these months (1 to 12) every year, like Roselle's bulk pickup, which stops in winter |
| `nth_in_month` | Optional. Only these weeks of the month: `[1]` is the first of `days` in the month, `[1, 3]` the first and third, `[-1]` the last |
| `nth_in_month_by_zone` | The same for each zone, use this instead of `nth_in_month` |
| `moved_dates` | Optional. Single pickups the town moved to another date |
| `on_holiday` | `"next_day"`: the pickup moves to the day after (past any holiday right after it, and never to a Sunday). `"skip"`: no pickup, it waits for the next regular day |

## The address file

```
Municipality,Street_Name,Low_Range,High_Range,Side,ZIP,Zone,Needs_Check
KENILWORTH,COOLIDGE DR,300,398,E,07033,TUE_FRI,
KENILWORTH,S 20TH ST,1,99,O,07033,TUE_FRI,Y
```

- `Municipality` is the town's `name` in capitals.
- `Side` is `E` for even house numbers, `O` for odd, `B` for both.
- `ZIP` may be left empty.
- `Zone` is one of the ids under `zones` in the rules file.
- `Needs_Check` is `Y` for a stretch you are not sure about, for example a street that is the border between two routes. The website gives the answer and asks the visitor to confirm it with the town.

Street names can be written any way (`Elm Street`, `ELM ST`), they are tidied when they are read.

## Where to get the addresses

- `data/reference/union_county_street_list_2025.csv` has every street in all 21 Union County towns with its ward and election district. It was made from the Board of Elections' "Find your Ward and District" PDF with `tools/county_pdf_to_csv.py`. For a town that collects by ward, or that has one schedule for everybody, this list is all that is needed.
- A town that prints a street list for each zone, like Hillside, needs the county list plus that street list. `tools/build_hillside.py` is the example; it also cuts streets that are split between two zones.
- A town whose street list is old or incomplete, like Union's 2015 route list, can use the Census map to fill the gaps: `tools/build_union.py` gives unlisted streets the zone of their neighbors and marks listed streets whose neighbors disagree, both as `Needs_Check`.
- A town that splits on a street, like Roselle (east and west of Chestnut St), can use the Census map to put each house on its side of that street: `tools/build_roselle.py`.
- A town outside Union County has no county street list. `tools/build_aberdeen.py` takes the house numbers from the Census address ranges inside the town's Census boundary, and the zones from streets checked in the town's own lookup (Recycle Coach), Census neighborhood places and the nearest checked streets.
- A town that only publishes a map of its routes needs the map turned into a street list. `tools/build_kenilworth.py` does this for Kenilworth from US Census street data and is the example to copy.
