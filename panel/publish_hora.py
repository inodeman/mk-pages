"""Encrypt one machine's last-hour file for the existing panel key.

Does not train, does not reset a git checkout, and does not push.
The key is read from MK_PANEL_KEY (64 hex characters). It is not an argument.

  MK_PANEL_KEY=... python3 panel/publish_hora.py --sources panel/hora_sources.json --write-dir /path/to/mk-pages

Sin --write-dir solo imprime un resumen, sin victorias.
--source sigue sirviendo para un JSON de una máquina.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import argparse
import base64
import json
from datetime import datetime

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from panel.hora_csv import aggregate_sources, load_sources
from panel.hora_ingest import IngestError, build_hour, parse_machine, parse_time, summary, to_iso


def encrypt_doc(doc, key_hex):
    key = bytes.fromhex(key_hex)
    if len(key) != 32:
        raise IngestError("MK_PANEL_KEY debe ser 32 bytes en hex")
    iv = os.urandom(12)
    raw = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode()
    ct = AESGCM(key).encrypt(iv, raw, None)
    return {
        "v": 2,
        "iv": base64.b64encode(iv).decode(),
        "ct": base64.b64encode(ct).decode(),
        "updated": doc.get("generated_at"),
    }


def stamp(doc, now):
    stamped = dict(doc)
    when = parse_time(now)
    stamped["generated_at"] = to_iso(when)
    stamped["seq"] = int(when.timestamp())
    return stamped


def _publish_sources(args):
    try:
        docs = aggregate_sources(load_sources(args.sources), parse_time(datetime.now().astimezone()))
    except IngestError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    stamped = []
    for machine in ("mac", "box"):
        doc = stamp(docs[machine], parse_time(datetime.now().astimezone()))
        if doc.get("synthetic"):
            print("archivo sintético: no se publica", file=sys.stderr)
            return 1
        print(summary(doc))
        stamped.append((machine, doc))
    if not args.write_dir:
        return 0
    key = os.environ.get("MK_PANEL_KEY", "")
    if not key:
        print("falta MK_PANEL_KEY", file=sys.stderr)
        return 2
    folder = os.path.join(args.write_dir, "data")
    os.makedirs(folder, exist_ok=True)
    for machine, doc in stamped:
        try:
            payload = encrypt_doc(doc, key)
        except (IngestError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        path = os.path.join(folder, "hora_%s.enc.json" % machine)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.write("\n")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(arg == "--key" or arg.startswith("--key=") for arg in argv):
        print("la clave va en MK_PANEL_KEY, no en la línea de comandos", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description="publicar la última hora cifrada")
    parser.add_argument("--machine", choices=("mac", "box"))
    parser.add_argument("--source")
    parser.add_argument("--sources")
    parser.add_argument("--write-dir")
    args = parser.parse_args(argv)
    if bool(args.sources) == bool(args.source):
        print("indica --sources o --source, solo uno", file=sys.stderr)
        return 2
    if args.sources:
        return _publish_sources(args)
    if not args.machine:
        print("falta --machine", file=sys.stderr)
        return 2
    with open(args.source, encoding="utf-8") as handle:
        source = json.load(handle)
    declared = source.get("machine")
    if declared is not None and parse_machine(declared) != args.machine:
        print("el archivo no es de esa máquina", file=sys.stderr)
        return 1
    source = dict(source)
    source["machine"] = args.machine
    try:
        doc = build_hour(source)
    except IngestError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if doc.get("synthetic"):
        print("archivo sintético: no se publica", file=sys.stderr)
        return 1
    doc = stamp(doc, parse_time(datetime.now().astimezone()))
    print(summary(doc))
    if not args.write_dir:
        return 0
    key = os.environ.get("MK_PANEL_KEY", "")
    if not key:
        print("falta MK_PANEL_KEY", file=sys.stderr)
        return 2
    try:
        payload = encrypt_doc(doc, key)
    except (IngestError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    folder = os.path.join(args.write_dir, "data")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "hora_%s.enc.json" % args.machine)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
