"""Last-hour native counts for the Mac and Box page.

The page shows only fights each machine played in the last 60 minutes.
It does not accept the two-brain experiment aggregate, and it does not
treat stage 11 as Goro unless the rival was validated. Guard p2_ch=6 is
not Goro.

Absence stays null. Null is not a zero percent.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone

SCHEMA = "mk.panel.hora.v1"
JUAREZ = timezone(timedelta(hours=-7))
WINDOW = timedelta(minutes=60)
EXPECTED = {"mac": list(range(0, 8)), "box": list(range(2, 13))}
NATIVE_PATH = {
    "mac": "runs/standalone/fights.csv",
    "box": "runs/scorpion/fights.csv",
}
LEGACY_MAC = range(20, 37)
_SHA16 = re.compile(r"^[0-9a-fA-F]{16}$")
_SHA64 = re.compile(r"^[0-9a-fA-F]{64}$")


class IngestError(ValueError):
    pass


def parse_time(value):
    """Aware clock as fixed UTC-7. Naive clocks are rejected.

    Ciudad Juárez is shown at UTC-7 all year. Host tzdata still shifts
    America/Ciudad_Juarez in summer, so this does not use that database.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        if re.search(r"[+-]\d{4}$", text):
            text = text[:-2] + ":" + text[-2:]
        if "T" not in text and re.match(r"^\d{4}-\d{2}-\d{2} ", text):
            text = text.replace(" ", "T", 1)
        try:
            dt = datetime.fromisoformat(text)
        except ValueError as exc:
            raise IngestError("reloj no interpretable") from exc
    if dt.tzinfo is None:
        raise IngestError("reloj sin zona horaria")
    return dt.astimezone(JUAREZ)


def to_iso(dt):
    if dt is None:
        return None
    return dt.isoformat(timespec="seconds")


def parse_machine(value):
    if value is None:
        return None
    word = str(value).strip().lower().split()
    if not word:
        return None
    token = word[0].strip("():,")
    return token if token in ("mac", "box") else None


def _as_int(value):
    if isinstance(value, bool) or value is None or value == "":
        raise IngestError("entero")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value.strip())
    raise IngestError("entero")


def _sha(value):
    if value is None or value == "":
        return None
    text = str(value).strip().lower()
    if _SHA64.match(text) or _SHA16.match(text):
        return text
    raise IngestError("sha")


def _same_sha(envelope, event):
    if not envelope or not event:
        return True
    if len(envelope) == len(event):
        return envelope == event
    if len(envelope) == 64 and len(event) == 16:
        return envelope.startswith(event)
    if len(event) == 64 and len(envelope) == 16:
        return event.startswith(envelope)
    return False


def _role(value):
    if value is None or value == "":
        return None
    low = str(value).strip().lower()
    if low in ("eval", "evaluation", "prueba", "pruebas", "evaluación", "evaluacion"):
        return "eval"
    if low in ("train", "training", "entrenamiento"):
        return "train"
    if low in ("practice", "práctica", "practica"):
        return "practice"
    return None


def _status(event):
    raw = event.get("status", event.get("terminal", event.get("result")))
    low = "" if raw is None else str(raw).strip().lower()
    if low in ("finished", "fin", "terminada"):
        return "finished"
    if low in ("interrupted", "interrumpida", "unfinished", "unfinished_timeout", "cutoff", "timeout"):
        return "interrupted"
    if low in ("invalid", "invalida", "inválida", "fault", "crash", "invalid_detector"):
        return "invalid"
    return None


def _win(event):
    won = event.get("won", event.get("win"))
    rw = event.get("rw")
    derived = None
    if rw is not None:
        derived = _as_int(rw) >= 2
    if won is None and derived is None:
        return None
    if won is None:
        return derived
    if won in (1, True, "1"):
        actual = True
    elif won in (0, False, "0"):
        actual = False
    else:
        return None
    if derived is not None and actual != derived:
        return "mismatch"
    return actual


def _guard_not_goro(event):
    p2 = event.get("p2_ch")
    if p2 is not None and str(p2).strip() == "6":
        return True
    guard = event.get("guard")
    if guard is None:
        return False
    text = str(guard).replace(" ", "").lower()
    return "p2_ch=6" in text


def _rival_validated(event):
    flag = event.get("rival_validated")
    if flag not in (True, 1, "1", "true", "si", "sí", "yes"):
        return False
    rival = str(event.get("rival") or event.get("opponent") or "").strip().lower()
    return rival == "goro"


def _is_experiment(doc):
    if not isinstance(doc, dict):
        return False
    if "batches" in doc and ("execution_machine" in doc or "models" in doc):
        return True
    if doc.get("schema") == "mk.panel.experiment.v1":
        return True
    return False


def _is_lab_event(event):
    return isinstance(event, dict) and "model" in event and "machine" not in event and "rw" in event


def _blank_acc():
    return {"won": 0, "lost": 0, "finished": 0, "interrupted": 0, "invalid": 0, "touched": False}


def _row(acc, stage):
    if acc["finished"] <= 0:
        return {
            "stage": stage,
            "state": "sin_datos",
            "won": None,
            "lost": None,
            "finished": None,
            "pct": None,
            "interrupted": acc["interrupted"] or None,
            "invalid": acc["invalid"] or None,
        }
    pct = math.floor((1000 * acc["won"] / acc["finished"]) + 0.5) / 10
    return {
        "stage": stage,
        "state": "medido",
        "won": acc["won"],
        "lost": acc["lost"],
        "finished": acc["finished"],
        "pct": pct,
        "interrupted": acc["interrupted"],
        "invalid": acc["invalid"],
    }


def _add(acc, kind):
    acc["touched"] = True
    if kind == "win":
        acc["won"] += 1
        acc["finished"] += 1
    elif kind == "loss":
        acc["lost"] += 1
        acc["finished"] += 1
    elif kind == "interrupted":
        acc["interrupted"] += 1
    elif kind == "invalid":
        acc["invalid"] += 1


def _mode_block(accs):
    stages = {str(n): _row(accs[n], n) for n in range(1, 11)}
    total = _blank_acc()
    for n in range(1, 11):
        total["won"] += accs[n]["won"]
        total["lost"] += accs[n]["lost"]
        total["finished"] += accs[n]["finished"]
        total["interrupted"] += accs[n]["interrupted"]
        total["invalid"] += accs[n]["invalid"]
        total["touched"] = total["touched"] or accs[n]["touched"]
    return {"stages": stages, "summary_1_10": _row(total, "1-10")}


def _goro_row(acc, unvalidated, rejected):
    if unvalidated or rejected:
        return {
            "state": "sin_validar",
            "won": None,
            "lost": None,
            "finished": None,
            "pct": None,
            "interrupted": None,
            "invalid": None,
            "unvalidated": unvalidated,
            "rejected_not_goro": rejected,
        }
    row = _row(acc, 11)
    row["unvalidated"] = 0
    row["rejected_not_goro"] = 0
    if row["state"] != "medido":
        row["state"] = "sin_datos"
    return row


def _seal_goro(row, validated, reason):
    if validated is not False:
        return row
    sealed = dict(row)
    sealed["state"] = "sin_validar"
    sealed["won"] = None
    sealed["lost"] = None
    sealed["finished"] = None
    sealed["pct"] = None
    sealed["reason"] = reason or "p2_ch=6"
    return sealed


def _event_clock(event):
    return parse_time(event.get("clock", event.get("time", event.get("ts"))))


def _canonical(event):
    keys = (
        "event_id", "machine", "actor_id", "role", "clock", "stage", "status",
        "won", "rw", "rival", "rival_validated", "guard", "p2_ch", "brain_sha256",
    )
    return tuple(event.get(k) for k in keys)


def build_hour(doc):
    if not isinstance(doc, dict):
        raise IngestError("el paquete no es un objeto")
    if _is_experiment(doc):
        raise IngestError("el panel de la última hora no acepta el agregado de experimento")
    machine = parse_machine(doc.get("machine"))
    if machine is None:
        raise IngestError("machine mac o box")
    as_of = parse_time(doc.get("as_of"))
    if as_of is None:
        raise IngestError("falta as_of")
    generated = parse_time(doc.get("generated_at")) if doc.get("generated_at") else None
    wall = as_of - WINDOW
    epoch = None
    brain = doc.get("brain") if isinstance(doc.get("brain"), dict) else {}
    epoch_raw = doc.get("brain_epoch_start", brain.get("epoch_start"))
    if epoch_raw:
        epoch = parse_time(epoch_raw)
    start = max(wall, epoch) if epoch is not None else wall
    envelope_sha = _sha(doc.get("brain_sha256", brain.get("sha256")))
    source = doc.get("source") if isinstance(doc.get("source"), dict) else {}
    if "connected" in source and isinstance(source.get("connected"), bool):
        connected = source["connected"]
    elif "connected" in doc and isinstance(doc.get("connected"), bool):
        connected = doc["connected"]
    else:
        connected = None
    path = source.get("path_label") or doc.get("path_label")
    if isinstance(path, str):
        path = path.strip()[:180]
    else:
        path = None
    detector = doc.get("detector") or source.get("detector")
    if isinstance(detector, str):
        detector = detector.strip()[:40]
    else:
        detector = None
    seq = doc.get("seq")
    if seq is not None:
        seq = _as_int(seq)

    excluded = {
        "duplicate": 0,
        "conflict": 0,
        "out_of_range": 0,
        "legacy_actor": 0,
        "wrong_machine": 0,
        "before_epoch": 0,
        "outside_window": 0,
        "other_brain": 0,
        "unknown_role": 0,
        "rejected": 0,
        "missing_id": 0,
        "missing_epoch": 0,
        "lab_event": 0,
        "practice": 0,
    }
    goro_validated = doc.get("goro_validated", True)
    modes = {"eval": {n: _blank_acc() for n in range(1, 11)}, "train": {n: _blank_acc() for n in range(1, 11)}}
    goro = {
        "eval": {"acc": _blank_acc(), "unvalidated": 0, "rejected": 0},
        "train": {"acc": _blank_acc(), "unvalidated": 0, "rejected": 0},
    }
    last_clock = None
    seen = {}
    events = doc.get("events") or []
    if not isinstance(events, list):
        raise IngestError("events no es una lista")
    count_fights = connected is not False and epoch is not None

    for event in events:
        if not isinstance(event, dict):
            excluded["rejected"] += 1
            continue
        if _is_lab_event(event):
            excluded["lab_event"] += 1
            continue
        eid = event.get("event_id")
        if eid:
            body = _canonical(event)
            if eid in seen:
                if seen[eid] != body:
                    excluded["conflict"] += 1
                else:
                    excluded["duplicate"] += 1
                continue
            seen[eid] = body
        else:
            excluded["missing_id"] += 1
        try:
            ev_machine = parse_machine(event.get("machine")) if event.get("machine") is not None else machine
            actor = _as_int(event.get("actor_id", event.get("actor", event.get("emulator"))))
            clock = _event_clock(event)
            stage = _as_int(event.get("stage", event.get("nivel")))
            status = _status(event)
            if clock is None or status is None or stage < 1 or stage > 11:
                raise IngestError("evento")
        except IngestError:
            excluded["rejected"] += 1
            continue
        if ev_machine != machine:
            excluded["wrong_machine"] += 1
            continue
        if machine == "mac" and actor in LEGACY_MAC:
            excluded["legacy_actor"] += 1
            continue
        if actor not in EXPECTED[machine]:
            excluded["out_of_range"] += 1
            continue
        event_sha = None
        try:
            event_sha = _sha(event.get("brain_sha256") or event.get("sha"))
        except IngestError:
            excluded["rejected"] += 1
            continue
        if not _same_sha(envelope_sha, event_sha):
            excluded["other_brain"] += 1
            continue
        if last_clock is None or clock > last_clock:
            last_clock = clock
        if epoch is not None and clock < epoch:
            excluded["before_epoch"] += 1
            continue
        if epoch is None:
            excluded["missing_epoch"] += 1
            continue
        if clock < start or clock > as_of:
            excluded["outside_window"] += 1
            continue
        if not count_fights:
            continue
        role = _role(event.get("role", event.get("mode", event.get("modo"))))
        if role == "practice":
            excluded["practice"] += 1
            continue
        if role is None:
            excluded["unknown_role"] += 1
            continue
        if status == "finished":
            won = _win(event)
            if won is True:
                kind = "win"
            elif won is False:
                kind = "loss"
            else:
                kind = "invalid"
        elif status == "interrupted":
            kind = "interrupted"
        else:
            kind = "invalid"
        if stage == 11:
            slot = goro[role]
            if goro_validated is False or _guard_not_goro(event) or not _rival_validated(event):
                if _guard_not_goro(event):
                    slot["rejected"] += 1
                else:
                    slot["unvalidated"] += 1
                continue
            _add(slot["acc"], kind)
            continue
        _add(modes[role][stage], kind)

    declared_last = None
    if source.get("last_fight_at") or doc.get("source_last_fight_at"):
        declared_last = parse_time(source.get("last_fight_at") or doc.get("source_last_fight_at"))
    last_fight = declared_last or last_clock
    in_window = None
    if last_fight is not None:
        in_window = start <= last_fight <= as_of
    if connected is None:
        connected = True if events else False
    return {
        "schema": SCHEMA,
        "synthetic": bool(doc.get("synthetic")),
        "machine": machine,
        "display_name": "Mac" if machine == "mac" else "Box",
        "generated_at": to_iso(generated),
        "as_of": to_iso(as_of),
        "seq": seq,
        "window": {"start": to_iso(start), "end": to_iso(as_of), "minutes": 60},
        "source": {
            "kind": "native_csv",
            "path_label": path,
            "path_expected": NATIVE_PATH[machine],
            "connected": connected,
            "last_fight_at": to_iso(last_fight),
            "last_fight_in_window": in_window,
            "error": source.get("error") if isinstance(source.get("error"), str) else None,
        },
        "brain": {
            "epoch_id": doc.get("epoch_id"),
            "epoch_start": to_iso(epoch),
            "sha256": envelope_sha,
            "sha16": envelope_sha[:16] if envelope_sha else None,
        },
        "numbers": "published",
        "freshness_state": "publicado",
        "detector": detector,
        "visual_validation": False,
        "expected_actor_ids": EXPECTED[machine],
        "eval": _mode_block(modes["eval"]),
        "train": _mode_block(modes["train"]),
        "goro": {
            "eval": _seal_goro(_goro_row(goro["eval"]["acc"], goro["eval"]["unvalidated"], goro["eval"]["rejected"]), goro_validated, doc.get("goro_reason")),
            "train": _seal_goro(_goro_row(goro["train"]["acc"], goro["train"]["unvalidated"], goro["train"]["rejected"]), goro_validated, doc.get("goro_reason")),
        },
        "excluded": excluded,
    }


def summary(doc):
    """Operator line without win counts."""
    return (
        "machine={m} as_of={a} epoch={e} connected={c} goro={g} numbers={n} synthetic={s}".format(
            m=doc.get("machine"),
            a=doc.get("as_of"),
            e=(doc.get("brain") or {}).get("epoch_start"),
            c=(doc.get("source") or {}).get("connected"),
            g=(doc.get("goro") or {}).get("eval", {}).get("state"),
            n=doc.get("numbers"),
            s=str(bool(doc.get("synthetic"))).lower(),
        )
    )
