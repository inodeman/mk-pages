"""Read native fights.csv files through a configurable actor map.

One raw row lands on one execution machine. Box actors 40–47 are the Mac's
0–7 seen by the Box learner; they are not counted again as Box. The Mac
standalone CSV is a separate source and is not confirmed while its learner
is stopped. Unconfirmed sources do not produce percentages.
"""

from __future__ import annotations

import csv
import hashlib
import os
from datetime import datetime, timedelta

from panel.hora_ingest import (
    IngestError,
    _blank_acc,
    _goro_row,
    _mode_block,
    _seal_goro,
    build_hour,
    parse_time,
    to_iso,
)

MACHINES = ("mac", "box")


def load_sources(path):
    import json
    with open(path, encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict) or "sources" not in config:
        raise IngestError("el mapa de fuentes no tiene sources")
    return config


def parse_csv_time(value, offset="-07:00"):
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    if text.endswith("Z") or "+" in text[10:] or (len(text) > 19 and text[-6] in "+-"):
        return parse_time(text)
    text = text.split(".", 1)[0]
    if "T" not in text and " " in text:
        text = text.replace(" ", "T", 1)
    return parse_time(text + offset)


def map_actor(raw, rules):
    for rule in rules:
        start = int(rule["raw_from"])
        end = int(rule["raw_to"])
        if start <= raw <= end:
            return rule["execution_machine"], raw + int(rule.get("actor_offset", 0))
    return None, None


def _blank_machine(machine, config, as_of, feeds, note):
    epoch = config.get("epoch") or {}
    start = parse_time(epoch.get("start")) if epoch.get("start") else None
    sha = (config.get("brain") or {}).get("sha256")
    goro_reason = (config.get("goro") or {}).get("reason") or "p2_ch=6"
    window_start = as_of - timedelta(minutes=60)
    eval_block = _mode_block({n: _blank_acc() for n in range(1, 11)})
    train_block = _mode_block({n: _blank_acc() for n in range(1, 11)})
    empty = _goro_row(_blank_acc(), 0, 0)
    return {
        "schema": "mk.panel.hora.v1",
        "synthetic": False,
        "machine": machine,
        "display_name": "Mac" if machine == "mac" else "Box",
        "generated_at": to_iso(as_of),
        "as_of": to_iso(as_of),
        "seq": None,
        "numbers": "withheld",
        "freshness_state": "sin_datos_frescos",
        "window": {"start": to_iso(window_start), "end": to_iso(as_of), "minutes": 60},
        "source": {
            "kind": "native_csv",
            "path_label": None,
            "path_expected": None,
            "connected": any(item.get("present") for item in feeds),
            "confirmed": False,
            "last_fight_at": None,
            "last_fight_in_window": None,
            "error": None,
        },
        "brain": {
            "epoch_id": epoch.get("id"),
            "epoch_start": to_iso(start) if start else epoch.get("start"),
            "sha256": sha,
            "sha16": sha[:16] if isinstance(sha, str) else None,
        },
        "detector": "ram",
        "visual_validation": False,
        "expected_actor_ids": list(range(0, 8)) if machine == "mac" else list(range(2, 13)),
        "eval": eval_block,
        "train": train_block,
        "goro": {
            "eval": _seal_goro(empty, False, goro_reason),
            "train": _seal_goro(dict(empty), False, goro_reason),
        },
        "excluded": {},
        "feeds": feeds,
        "seen_via": [],
        "mapping_note": note,
    }


def _row_event(row, source, config):
    try:
        actor = int(str(row.get("actor", "")).strip())
    except ValueError:
        return None, "rejected"
    machine, mapped = map_actor(actor, source.get("maps") or [])
    if machine is None:
        return None, "unmapped"
    clock = parse_csv_time(row.get("time"), (config.get("timezone_offset") or "-07:00"))
    if clock is None:
        return None, "rejected"
    try:
        stage = int(str(row.get("stage", "")).strip())
    except ValueError:
        return None, "rejected"
    finished_raw = str(row.get("finished", "")).strip()
    if finished_raw not in ("0", "1"):
        return None, "rejected"
    status = "finished" if finished_raw == "1" else "interrupted"
    won_raw = str(row.get("won", "")).strip()
    event = {
        "machine": machine,
        "actor_id": mapped,
        "role": (row.get("role") or "").strip(),
        "clock": to_iso(clock),
        "stage": stage,
        "status": status,
        "version": (str(row.get("version")).strip() if str(row.get("version") or "").strip() else None),
        "source_id": source.get("id"),
        "_priority": int(source.get("priority", 0)),
    }
    if won_raw in ("0", "1"):
        event["won"] = int(won_raw)
    if str(row.get("rw", "")).strip() != "":
        event["rw"] = int(str(row["rw"]).strip())
    if str(row.get("rl", "")).strip() != "":
        event["rl"] = int(str(row["rl"]).strip())
    key = "|".join([
        machine, str(mapped), event["clock"], str(stage), event["role"],
        str(event.get("won", "")), finished_raw, str(event.get("rw", "")), str(event.get("rl", "")),
        str(event.get("version") or ""),
    ])
    event["_key"] = key
    event["event_id"] = hashlib.sha256(key.encode()).hexdigest()[:24]
    return event, None


def _read_csv(path):
    if not path or not os.path.isfile(path):
        return [], None, False, None
    newest = None
    rows = []
    try:
        with open(path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                rows.append(row)
                try:
                    clock = parse_csv_time(row.get("time"))
                except IngestError:
                    clock = None
                if clock is not None and (newest is None or clock > newest):
                    newest = clock
    except OSError as exc:
        return [], None, False, str(exc)[:160]
    return rows, newest, True, None


def _actor_health(machine, events, start_iso, end_iso):
    expected = list(range(0, 8)) if machine == "mac" else list(range(2, 13))
    start = parse_time(start_iso)
    end = parse_time(end_iso)
    seen = set()
    for event in events:
        clock = parse_time(event.get("clock"))
        if clock is not None and start <= clock <= end:
            seen.add(event.get("actor_id"))
    return [{"actor_id": actor, "reporting": "ok" if actor in seen else "sin_reporte"} for actor in expected]


def aggregate_sources(config, now=None):
    if now is None:
        now = datetime.now().astimezone()
    as_of = parse_time(now)
    epoch = config.get("epoch") or {}
    goro = config.get("goro") or {}
    note = config.get("mapping_note") or ""
    brain = config.get("brain") or {}
    feeds = []
    chosen = {}
    dupes = 0
    unmapped = 0
    for source in config.get("sources") or []:
        enabled = source.get("enabled", True)
        maps_to = sorted({rule.get("execution_machine") for rule in source.get("maps") or []})
        if not enabled:
            feeds.append({
                "id": source.get("id"),
                "path": source.get("path"),
                "present": None,
                "read": False,
                "confirmed": False,
                "newest_at": None,
                "note": source.get("note"),
                "error": None,
                "maps_to": maps_to,
            })
            continue
        rows, newest, present, error = _read_csv(source.get("path"))
        feeds.append({
            "id": source.get("id"),
            "path": source.get("path"),
            "present": present,
            "read": True,
            "confirmed": bool(source.get("confirmed")),
            "newest_at": to_iso(newest),
            "note": source.get("note"),
            "error": error,
            "maps_to": maps_to,
        })
        if not source.get("confirmed") or not present:
            continue
        for row in rows:
            try:
                event, flag = _row_event(row, source, config)
            except (IngestError, ValueError):
                unmapped += 0
                continue
            if flag == "unmapped":
                unmapped += 1
                continue
            if event is None:
                continue
            key = event["_key"]
            current = chosen.get(key)
            if current is None:
                chosen[key] = event
            else:
                dupes += 1
                if event["_priority"] > current["_priority"]:
                    chosen[key] = event
    by_machine = {name: [] for name in MACHINES}
    for event in chosen.values():
        by_machine[event["machine"]].append(event)
    live_targets = set()
    for source, feed in zip(config.get("sources") or [], feeds):
        if source.get("enabled", True) and source.get("confirmed") and feed.get("present"):
            live_targets.update(feed.get("maps_to") or [])
    docs = {}
    for machine in MACHINES:
        events = []
        for event in by_machine[machine]:
            item = {k: v for k, v in event.items() if not k.startswith("_")}
            events.append(item)
        if machine not in live_targets:
            doc = _blank_machine(machine, config, as_of, feeds, note)
        else:
            doc = build_hour({
                "machine": machine,
                "as_of": to_iso(as_of),
                "generated_at": to_iso(as_of),
                "brain_epoch_start": epoch.get("start"),
                "epoch_id": epoch.get("id"),
                "brain_sha256": brain.get("sha256"),
                "goro": goro,
                "goro_validated": goro.get("validated", False),
                "goro_reason": goro.get("reason"),
                "detector": "ram",
                "source": {
                    "connected": True,
                    "path_label": ", ".join(sorted({ev["source_id"] for ev in events})) or None,
                    "confirmed": True,
                },
                "events": events,
            })
            doc["excluded"]["cross_source"] = dupes if machine == "mac" else 0
            doc["excluded"]["unmapped"] = unmapped if machine == "box" else 0
        doc["feeds"] = feeds
        doc["mapping_note"] = note
        doc["clock_basis"] = config.get("clock_basis")
        doc["seen_via"] = sorted({event["source_id"] for event in events})
        if doc.get("numbers") == "published":
            doc["actors"] = _actor_health(machine, events, doc["window"]["start"], doc["window"]["end"])
            paths = [item.get("path") for item in feeds if item.get("read") and item.get("present") and machine in (item.get("maps_to") or [])]
            if paths:
                doc["source"]["path_label"] = paths[0] if len(paths) == 1 else ", ".join(paths)
        newest_feed = None
        for feed in feeds:
            if machine in (feed.get("maps_to") or []) and feed.get("newest_at"):
                if newest_feed is None or feed["newest_at"] > newest_feed:
                    newest_feed = feed["newest_at"]
        if doc["numbers"] == "withheld":
            doc["source"]["last_fight_at"] = newest_feed
            doc["source"]["confirmed"] = False
        docs[machine] = doc
    return docs
