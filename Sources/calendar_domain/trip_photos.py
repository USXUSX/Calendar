"""Photo-app search shortcut links; never read or transmit photo content."""
import json
from urllib.parse import quote, urlencode


def photo_search_url(trip, *, day=None):
    album = trip.get("photoAlbumName")
    if not album:
        return None
    payload = {"album": album}
    if day is not None:
        payload["date"] = day
    return "shortcuts://run-shortcut?" + urlencode({
        "name": "CAL Trip Photos", "input": "text",
        "text": json.dumps(payload, ensure_ascii=False),
    }, quote_via=quote)
