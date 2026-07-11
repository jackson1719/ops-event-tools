"""Diff two generations of an event's schedule into ScheduleChange rows.

Panels have no stable ID in the sheet, so identity is inferred by matching in
passes, most-specific first. Duplicate titles (36x "STRIKE") are handled by
multiset matching within each key.

  1. (title, room_number, starts_at)  -> same panel; check cancelled/AV flips
  2. (title, room_number)             -> time_changed
  3. (title, starts_at)               -> room_changed
  4. title, if exactly one on each side -> time + room change
  5. leftovers                         -> removed / added
"""
from collections import defaultdict

from events.models import ScheduleChange


def _fmt(dt, tz):
    return dt.astimezone(tz).strftime("%a %-m/%-d %-I:%M %p")


def _pop_pairs(old, new, key_fn):
    """Yield (old_item, new_item) pairs matched by key_fn; consumes matches."""
    buckets = defaultdict(list)
    for item in old:
        buckets[key_fn(item)].append(item)
    pairs = []
    remaining_new = []
    for item in new:
        bucket = buckets.get(key_fn(item))
        if bucket:
            pairs.append((bucket.pop(), item))
        else:
            remaining_new.append(item)
    remaining_old = [i for bucket in buckets.values() for i in bucket]
    return pairs, remaining_old, remaining_new


def diff_schedules(event, old_items, new_items, synced_at) -> list[ScheduleChange]:
    """old_items: dicts snapshotted before the delete; new_items: unsaved
    ScheduleItem instances about to be bulk_created."""
    tz = event.tz

    def norm_old(d):
        return d

    old = list(old_items)
    new = [
        {
            "title": i.title, "room_name": i.room_name, "room_number": i.room_number,
            "building": i.building, "starts_at": i.starts_at, "ends_at": i.ends_at,
            "is_cancelled": i.is_cancelled, "has_av": i.has_av,
        }
        for i in new_items
    ]

    changes = []

    def room_label(d):
        if d["room_name"] and d["room_number"]:
            return f"{d['room_name']} ({d['room_number']})"
        return d["room_name"] or d["room_number"]

    def record(change_type, d, detail=""):
        changes.append(ScheduleChange(
            event=event,
            change_type=change_type,
            title=d["title"],
            building=d["building"],
            room_label=room_label(d),
            starts_at=d["starts_at"],
            detail=detail,
            synced_at=synced_at,
        ))

    def check_flags(o, n):
        if o["is_cancelled"] != n["is_cancelled"]:
            record("cancelled" if n["is_cancelled"] else "uncancelled", n)
        if o["has_av"] != n["has_av"]:
            record("av_changed", n, f"AV {'added' if n['has_av'] else 'removed'}")

    # Pass 1: exact match
    pairs, old, new = _pop_pairs(old, new, lambda d: (d["title"], d["room_number"], d["starts_at"]))
    for o, n in pairs:
        check_flags(o, n)
        if o["ends_at"] != n["ends_at"]:
            record("time_changed", n, f"End {_fmt(o['ends_at'], tz)} → {_fmt(n['ends_at'], tz)}")

    # Pass 2: same title+room, different time
    pairs, old, new = _pop_pairs(old, new, lambda d: (d["title"], d["room_number"]))
    for o, n in pairs:
        record("time_changed", n, f"{_fmt(o['starts_at'], tz)} → {_fmt(n['starts_at'], tz)}")
        check_flags(o, n)

    # Pass 3: same title+time, different room
    pairs, old, new = _pop_pairs(old, new, lambda d: (d["title"], d["starts_at"]))
    for o, n in pairs:
        record("room_changed", n, f"{room_label(o)} → {room_label(n)}")
        check_flags(o, n)

    # Pass 4: same title, one on each side — moved in both time and room
    old_by_title = defaultdict(list)
    for d in old:
        old_by_title[d["title"]].append(d)
    still_new = []
    for n in new:
        candidates = old_by_title.get(n["title"], [])
        if len(candidates) == 1:
            o = candidates.pop()
            record("time_changed", n,
                   f"{_fmt(o['starts_at'], tz)} @ {room_label(o)} → {_fmt(n['starts_at'], tz)} @ {room_label(n)}")
            check_flags(o, n)
        else:
            still_new.append(n)
    old = [d for lst in old_by_title.values() for d in lst]
    new = still_new

    # Pass 5: leftovers
    for d in old:
        record("removed", d, f"Was {_fmt(d['starts_at'], tz)}")
    for d in new:
        record("added", d, f"{_fmt(d['starts_at'], tz)} - {_fmt(d['ends_at'], tz)}")

    return changes
