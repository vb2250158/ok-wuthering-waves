"""Optional native per-invocation upper bound; never inferred from must_use."""
import re

SPEND_LIMIT = 'Waveplate Spend Limit'
CURRENT_STATE_INSPECTION = 'Current State Inspection Only'


def read_daily_consumption(boxes, height):
    anchors = [box for box in boxes if re.search(r'(累计|累計)?消耗.*180.*(结晶波片|結晶波片)', str(box.name))]
    counters = [box for box in boxes if re.fullmatch(r'\d{1,3}/180', str(box.name).strip())]
    if len(anchors) != 1 or len(counters) != 1 or type(height) is not int or height <= 0:
        raise ValueError('daily_consumption_missing_or_ambiguous')
    anchor, counter = anchors[0], counters[0]
    if any(not all(hasattr(box, key) for key in ('x', 'y', 'width', 'height')) for box in (anchor, counter)):
        raise ValueError('daily_consumption_coordinates_missing')
    if abs((anchor.y + anchor.height / 2) - (counter.y + counter.height / 2)) > height * .12:
        raise ValueError('daily_consumption_row_mismatch')
    used = int(counter.name.strip().split('/')[0])
    if used > 180:
        raise ValueError('daily_consumption_out_of_range')
    return used


def read_current_stamina(boxes):
    values = []
    for box in boxes or ():
        text = str(box.name).strip()
        if '/' not in text:
            continue
        match = re.fullmatch(r'(\d{1,4})/(\d{1,4})', text)
        if match is None:
            raise ValueError('waveplate_current_unreadable')
        current, maximum = map(int, match.groups())
        if maximum != 240 or not 0 <= current <= maximum:
            raise ValueError('waveplate_current_out_of_range')
        values.append((current, maximum))
    if not values or len(set(values)) != 1:
        raise ValueError('waveplate_current_missing_or_conflicting')
    return values[0][0]


class StaminaBudget:
    def __init__(self, maximum):
        if type(maximum) is not int or not 0 <= maximum <= 10000:
            raise ValueError('waveplate_spend_limit_invalid')
        self.maximum = maximum
        self.reserved = 0

    @property
    def remaining(self):
        return self.maximum - self.reserved

    def reserve(self, once, current):
        if type(once) is not int or once <= 0 or type(current) is not int or current < 0:
            raise ValueError('waveplate_cost_or_current_invalid')
        cost = min(2, self.remaining // once, current // once) * once
        # Reserve before the first reward click. An exception cannot restore
        # authority for a second click whose earlier effect is unknown.
        self.reserved += cost
        return cost


def configured_budget(config):
    value = config.get(SPEND_LIMIT)
    return None if value is None else StaminaBudget(value)
