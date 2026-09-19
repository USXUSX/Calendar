"""Owner-local home settings; no personal defaults in source or samples."""
import copy
import json
from .errors import ValidationError
from Sources.place_acquisition import valid_field


def read_home(root):
    path = root / 'settings' / 'home.json'
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        raise ValidationError('自宅の共通設定 settings/home.json を確認してください。') from error
    if (not isinstance(value, dict) or not valid_field('address', value.get('address'))
            or not valid_field('location', value.get('location'))
            or (value.get('googlePlaceId') is not None and
                (not isinstance(value['googlePlaceId'], str) or not value['googlePlaceId'].strip()))):
        raise ValidationError('自宅の共通設定には住所と正しい緯度・経度が必要です。')
    return dict(address=value['address'].strip(), location=value['location'],
                googlePlaceId=value.get('googlePlaceId'))


def apply_place(place, home):
    result = copy.deepcopy(place)
    if home and isinstance(result, dict) and isinstance(result.get('name'), str) and result['name'].strip() == '自宅':
        result.update(copy.deepcopy(home))
    return result


def apply_home(trip, home):
    result = copy.deepcopy(trip)
    if home and isinstance(result, dict) and isinstance(result.get('places'), list):
        result['places'] = [apply_place(place, home) for place in result['places']]
    return result
