"""Unit fixtures only. Counts are synthetic and are not a measurement."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from panel.hora_ingest import IngestError, build_hour, parse_time, to_iso
from panel.publish_hora import encrypt_doc, main

AS = "2099-03-01T12:00:00-07:00"
EPOCH = "2099-03-01T00:00:00-07:00"
SHA = "ab" * 32


def envelope(**overrides):
    doc = {
        "machine": "mac",
        "as_of": AS,
        "generated_at": AS,
        "seq": 1,
        "synthetic": True,
        "brain_epoch_start": EPOCH,
        "brain_sha256": SHA,
        "detector": "ram",
        "source": {"connected": True, "path_label": "runs/standalone/fights.csv"},
        "events": [],
    }
    doc.update(overrides)
    return doc


def fight(**overrides):
    row = {
        "event_id": "e1",
        "machine": "mac",
        "actor_id": 0,
        "role": "eval",
        "clock": "2099-03-01T11:30:00-07:00",
        "stage": 1,
        "status": "finished",
        "won": 1,
        "brain_sha256": SHA,
    }
    row.update(overrides)
    return row


class HourIngestTest(unittest.TestCase):
    def test_clock_is_fixed_utc_minus_7_in_june(self):
        self.assertEqual(to_iso(parse_time("2026-06-15T18:00:00Z")), "2026-06-15T11:00:00-07:00")

    def test_naive_clock_rejected(self):
        with self.assertRaises(IngestError):
            parse_time("2099-03-01T12:00:00")

    def test_real_zero_has_denominator_and_empty_is_null(self):
        doc = build_hour(envelope(events=[
            fight(event_id="a", stage=4, won=0),
            fight(event_id="b", stage=4, actor_id=1, won=0),
        ]))
        row = doc["eval"]["stages"]["4"]
        self.assertEqual(row["state"], "medido")
        self.assertEqual((row["won"], row["lost"], row["finished"], row["pct"]), (0, 2, 2, 0.0))
        self.assertEqual(doc["eval"]["stages"]["5"]["state"], "sin_datos")
        self.assertIsNone(doc["eval"]["stages"]["5"]["pct"])
        self.assertIsNone(doc["eval"]["stages"]["5"]["won"])

    def test_interrupted_and_invalid_are_not_losses(self):
        doc = build_hour(envelope(events=[
            fight(event_id="ok", won=1),
            fight(event_id="cut", status="interrupted", won=0),
            fight(event_id="bad", status="invalid", won=0),
            fight(event_id="crash", status="crash", won=0),
            fight(event_id="mismatch", won=0, rw=2),
        ]))
        row = doc["eval"]["summary_1_10"]
        self.assertEqual((row["won"], row["lost"], row["finished"]), (1, 0, 1))
        self.assertEqual(row["interrupted"], 1)
        self.assertEqual(row["invalid"], 3)

    def test_dedupe_keeps_distinct_fights(self):
        doc = build_hour(envelope(events=[
            fight(event_id="same", won=1),
            fight(event_id="same", won=1),
            fight(event_id="other", actor_id=2, stage=2, won=1),
            fight(event_id=None, won=1, actor_id=3, stage=3),
            fight(event_id=None, won=0, actor_id=4, stage=3),
        ]))
        self.assertEqual(doc["excluded"]["duplicate"], 1)
        self.assertEqual(doc["excluded"]["missing_id"], 2)
        self.assertEqual(doc["eval"]["summary_1_10"]["finished"], 4)

    def test_conflict_does_not_drop_the_first_fight(self):
        doc = build_hour(envelope(events=[
            fight(event_id="x", won=1),
            fight(event_id="x", won=0, stage=2),
        ]))
        self.assertEqual(doc["excluded"]["conflict"], 1)
        self.assertEqual(doc["eval"]["summary_1_10"]["won"], 1)

    def test_roles_stay_separate(self):
        doc = build_hour(envelope(events=[
            fight(event_id="e", role="prueba", won=1),
            fight(event_id="t", role="entrenamiento", actor_id=1, won=0),
            fight(event_id="u", role="desconocido", actor_id=2, won=1),
        ]))
        self.assertEqual(doc["eval"]["summary_1_10"]["finished"], 1)
        self.assertEqual(doc["eval"]["summary_1_10"]["pct"], 100.0)
        self.assertEqual(doc["train"]["summary_1_10"]["pct"], 0.0)
        self.assertEqual(doc["train"]["summary_1_10"]["lost"], 1)
        self.assertEqual(doc["excluded"]["unknown_role"], 1)

    def test_goro_requires_validated_rival_and_rejects_p2_ch_6(self):
        only_guard = build_hour(envelope(events=[
            fight(stage=11, guard="p2_ch=6", rival="goro", rival_validated=True, won=1),
        ]))
        self.assertEqual(only_guard["goro"]["eval"]["state"], "sin_validar")
        self.assertIsNone(only_guard["goro"]["eval"]["pct"])
        self.assertEqual(only_guard["goro"]["eval"]["rejected_not_goro"], 1)
        self.assertEqual(only_guard["eval"]["summary_1_10"]["state"], "sin_datos")

        unvalidated = build_hour(envelope(events=[fight(stage=11, won=0)]))
        self.assertEqual(unvalidated["goro"]["eval"]["state"], "sin_validar")
        self.assertIsNone(unvalidated["goro"]["eval"]["pct"])

        mixed = build_hour(envelope(events=[
            fight(event_id="good", stage=11, rival="goro", rival_validated=True, won=1),
            fight(event_id="bad", stage=11, p2_ch=6, rival="goro", rival_validated=True, won=0),
        ]))
        self.assertEqual(mixed["goro"]["eval"]["state"], "sin_validar")
        self.assertIsNone(mixed["goro"]["eval"]["won"])

        clean = build_hour(envelope(events=[
            fight(event_id="g", stage=11, rival="goro", rival_validated=True, won=0),
        ]))
        self.assertEqual(clean["goro"]["eval"]["state"], "medido")
        self.assertEqual((clean["goro"]["eval"]["won"], clean["goro"]["eval"]["lost"], clean["goro"]["eval"]["finished"]), (0, 1, 1))
        self.assertEqual(clean["eval"]["summary_1_10"]["state"], "sin_datos")

    def test_epoch_window_and_brain_filters(self):
        doc = build_hour(envelope(events=[
            fight(event_id="old", clock="2099-02-28T23:00:00-07:00", won=1),
            fight(event_id="early", clock="2099-03-01T10:59:59-07:00", won=1),
            fight(event_id="edge", clock="2099-03-01T11:00:00-07:00", actor_id=1, won=1),
            fight(event_id="other", brain_sha256="cd" * 32, actor_id=2, won=1),
        ]))
        self.assertEqual(doc["excluded"]["before_epoch"], 1)
        self.assertEqual(doc["excluded"]["outside_window"], 1)
        self.assertEqual(doc["excluded"]["other_brain"], 1)
        self.assertEqual(doc["eval"]["summary_1_10"]["finished"], 1)

    def test_missing_epoch_does_not_invent_a_percent(self):
        doc = build_hour(envelope(brain_epoch_start=None, events=[fight()]))
        self.assertIsNone(doc["brain"]["epoch_start"])
        self.assertEqual(doc["eval"]["summary_1_10"]["state"], "sin_datos")
        self.assertGreater(doc["excluded"]["missing_epoch"], 0)

    def test_actor_ranges_do_not_cross_machines(self):
        mac = build_hour(envelope(events=[
            fight(event_id="m2", actor_id=2, won=1),
            fight(event_id="m22", actor_id=22, won=1),
            fight(event_id="m7", actor_id=7, won=0),
            fight(event_id="frombox", machine="box", actor_id=2, won=1),
        ]))
        self.assertEqual(mac["eval"]["summary_1_10"]["finished"], 2)
        self.assertEqual(mac["excluded"]["legacy_actor"], 1)
        self.assertEqual(mac["excluded"]["wrong_machine"], 1)
        box = build_hour(envelope(
            machine="box",
            source={"connected": True, "path_label": "runs/scorpion/fights.csv"},
            events=[
                fight(event_id="b2", machine="box", actor_id=2, won=1),
                fight(event_id="b12", machine="box", actor_id=12, stage=2, won=1),
                fight(event_id="b1", machine="box", actor_id=1, won=1),
                fight(event_id="b22", machine="box", actor_id=22, won=1),
                fight(event_id="frommac", machine="mac", actor_id=2, won=1),
            ],
        ))
        self.assertEqual(box["machine"], "box")
        self.assertEqual(box["expected_actor_ids"], list(range(2, 13)))
        self.assertEqual(box["eval"]["summary_1_10"]["finished"], 2)
        self.assertEqual(box["excluded"]["out_of_range"], 2)
        self.assertEqual(box["excluded"]["wrong_machine"], 1)
        self.assertEqual(mac["eval"]["summary_1_10"]["won"], 1)
        self.assertEqual(box["eval"]["summary_1_10"]["won"], 2)

    def test_experiment_aggregate_and_lab_event_rejected(self):
        with self.assertRaises(IngestError):
            build_hour({"batches": {"batch1": {}}, "execution_machine": "box", "machine": "box", "as_of": AS})
        doc = build_hour(envelope(events=[{
            "model": "mac", "sha": "0123456789abcdef", "worker": 0, "stage": 11,
            "rw": 2, "rl": 0, "won": 1, "status": "finished",
        }]))
        self.assertEqual(doc["excluded"]["lab_event"], 1)
        self.assertEqual(doc["eval"]["summary_1_10"]["state"], "sin_datos")
        self.assertEqual(doc["goro"]["eval"]["state"], "sin_datos")

    def test_disconnected_source_has_no_percent(self):
        doc = build_hour(envelope(source={"connected": False, "path_label": "runs/standalone/fights.csv"}, events=[fight()]))
        self.assertFalse(doc["source"]["connected"])
        self.assertEqual(doc["eval"]["summary_1_10"]["state"], "sin_datos")

    def test_publish_refuses_synthetic_key_flag_and_hard_reset(self):
        source = Path("panel/publish_hora.py").read_text()
        self.assertNotIn("reset --hard", source)
        self.assertNotIn("git push", source)
        self.assertNotIn("git clean", source)
        script = Path("panel/box_publisher/run_hora.sh").read_text()
        self.assertNotIn("git push", script)
        self.assertNotIn("reset --hard", script)
        self.assertIn("publish_hora.py", script)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "in.json"
            path.write_text(json.dumps(envelope(events=[fight()])), encoding="utf-8")
            code = main(["--machine", "mac", "--source", str(path), "--write-dir", tmp])
            self.assertEqual(code, 1)
            self.assertFalse((Path(tmp) / "data" / "hora_mac.enc.json").exists())
            code = main(["--machine", "mac", "--source", str(path), "--key", "abc"])
            self.assertEqual(code, 2)

    def test_encrypt_roundtrip_matches_the_browser(self):
        doc = build_hour(envelope(synthetic=False, events=[fight()]))
        key = "12" * 32
        payload = encrypt_doc(doc, key)
        with tempfile.TemporaryDirectory() as tmp:
            enc = Path(tmp) / "enc.json"
            enc.write_text(json.dumps(payload), encoding="utf-8")
            script = r"""
const fs = require('fs');
const payload = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const key = Buffer.from(process.argv[3], 'hex');
const iv = Buffer.from(payload.iv, 'base64');
const ct = Buffer.from(payload.ct, 'base64');
(async () => {
  const k = await crypto.subtle.importKey('raw', key, 'AES-GCM', false, ['decrypt']);
  const plain = await crypto.subtle.decrypt({name:'AES-GCM', iv}, k, ct);
  const doc = JSON.parse(Buffer.from(plain).toString());
  if (doc.machine !== 'mac' || doc.visual_validation !== false) process.exit(2);
  if (doc.eval.summary_1_10.finished !== 1) process.exit(3);
  process.exit(0);
})().catch(() => process.exit(1));
"""
            js = Path(tmp) / "dec.js"
            js.write_text(script, encoding="utf-8")
            result = subprocess.run(["node", str(js), str(enc), key], check=False)
            self.assertEqual(result.returncode, 0)

    def test_box_csv_maps_mac_without_double_count_or_goro_percent(self):
        from panel.hora_csv import aggregate_sources
        with tempfile.TemporaryDirectory() as tmp:
            box = Path(tmp) / "fights.csv"
            mac = Path(tmp) / "mac.csv"
            box.write_text(
                "time,actor,role,stage,won,finished,rw,rl\n"
                "2099-03-01 11:10:00,9,train,1,1,1,2,0\n"
                "2099-03-01 11:40:00,9,train,1,1,1,2,0\n"
                "2099-03-01 11:41:00,40,eval,4,0,1,0,2\n"
                "2099-03-01 11:42:00,2,train,11,0,1,0,2\n"
                "2099-03-01 11:43:00,4,train,3,0,0,0,0\n"
                "2099-03-01 11:44:00,22,train,1,1,1,2,0\n",
                encoding="utf-8",
            )
            mac.write_text(
                "time,actor,role,stage,won,finished,rw,rl\n"
                "2099-03-01 11:41:00,0,eval,4,1,1,2,0\n",
                encoding="utf-8",
            )
            config = {
                "timezone_offset": "-07:00",
                "epoch": {"id": "epoch-test", "start": "2099-03-01T11:30:00-07:00"},
                "goro": {"validated": False, "reason": "p2_ch=6"},
                "brain": {"sha256": "ab" * 32},
                "sources": [
                    {
                        "id": "box_fights", "path": str(box), "enabled": True, "confirmed": True, "priority": 1,
                        "maps": [
                            {"raw_from": 2, "raw_to": 12, "execution_machine": "box", "actor_offset": 0},
                            {"raw_from": 40, "raw_to": 47, "execution_machine": "mac", "actor_offset": -40},
                        ],
                    },
                    {
                        "id": "mac_native_fights", "path": str(mac), "enabled": False, "confirmed": False, "priority": 2,
                        "maps": [{"raw_from": 0, "raw_to": 7, "execution_machine": "mac", "actor_offset": 0}],
                    },
                ],
            }
            docs = aggregate_sources(config, parse_time("2099-03-01T12:00:00-07:00"))
            mac_doc, box_doc = docs["mac"], docs["box"]
            self.assertEqual(mac_doc["eval"]["summary_1_10"]["finished"], 1)
            self.assertEqual(mac_doc["eval"]["summary_1_10"]["won"], 0)
            self.assertEqual(mac_doc["goro"]["eval"]["state"], "sin_validar")
            self.assertIsNone(mac_doc["goro"]["eval"]["pct"])
            self.assertEqual(box_doc["train"]["summary_1_10"]["finished"], 1)
            self.assertEqual(box_doc["goro"]["train"]["state"], "sin_validar")
            self.assertIsNone(box_doc["goro"]["train"]["pct"])
            self.assertEqual(box_doc["excluded"]["before_epoch"], 1)
            self.assertGreaterEqual(box_doc["excluded"]["unmapped"], 1)
            health = {row["actor_id"]: row["reporting"] for row in mac_doc["actors"]}
            self.assertEqual(health[0], "ok")
            self.assertEqual(health[1], "sin_reporte")
            self.assertEqual(health[2], "sin_reporte")
            self.assertTrue(all(feed["read"] is False for feed in mac_doc["feeds"] if feed["id"] == "mac_native_fights"))
            self.assertNotIn("retain90", Path("panel/hora_sources.json").read_text())
            self.assertNotIn("status.txt", Path("panel/hora_csv.py").read_text())

    def test_enabled_pair_is_not_summed_and_default_source_is_withheld_without_the_file(self):
        from panel.hora_csv import aggregate_sources, load_sources
        saved = load_sources("panel/hora_sources.json")
        active = [item for item in saved["sources"] if item.get("enabled")]
        self.assertEqual([item["id"] for item in active], ["box_fights"])
        self.assertTrue(active[0]["path"].endswith("runs/scorpion/fights.csv"))
        self.assertEqual(saved["epoch"]["start"], "2026-11-08T16:55:00-07:00")
        self.assertFalse(saved["goro"]["validated"])
        missing = aggregate_sources(saved, parse_time("2099-03-01T12:00:00-07:00"))
        self.assertEqual(missing["mac"]["numbers"], "withheld")
        self.assertEqual(missing["box"]["goro"]["eval"]["state"], "sin_validar")
        self.assertIsNone(missing["mac"]["eval"]["summary_1_10"]["pct"])
        with tempfile.TemporaryDirectory() as tmp:
            box = Path(tmp) / "fights.csv"
            mac = Path(tmp) / "mac.csv"
            box.write_text("time,actor,role,stage,won,finished,rw,rl\n2099-03-01 11:40:00,40,eval,1,1,1,2,0\n", encoding="utf-8")
            mac.write_text("time,actor,role,stage,won,finished,rw,rl\n2099-03-01 11:40:00,0,eval,1,1,1,2,0\n", encoding="utf-8")
            config = {
                "epoch": {"id": "e", "start": "2099-03-01T11:00:00-07:00"},
                "goro": {"validated": False, "reason": "p2_ch=6"},
                "sources": [
                    {"id": "box_fights", "path": str(box), "enabled": True, "confirmed": True, "priority": 1,
                     "maps": [{"raw_from": 40, "raw_to": 47, "execution_machine": "mac", "actor_offset": -40}]},
                    {"id": "mac_native_fights", "path": str(mac), "enabled": True, "confirmed": True, "priority": 2,
                     "maps": [{"raw_from": 0, "raw_to": 7, "execution_machine": "mac", "actor_offset": 0}]},
                ],
            }
            both = aggregate_sources(config, parse_time("2099-03-01T12:00:00-07:00"))
            self.assertEqual(both["mac"]["eval"]["summary_1_10"]["finished"], 1)
            self.assertEqual(both["mac"]["excluded"]["cross_source"], 1)

    def test_old_panel_file_is_not_the_new_page(self):
        index = Path("index.html").read_text()
        self.assertIn("Panel privado", index)
        self.assertNotIn("hora_mac", index)
        self.assertNotIn("hora_box", index)
        page = Path("hora.html").read_text()
        self.assertIn('href="index.html"', page)
        self.assertIn("panel/hora.js", page)
        self.assertIn("MKHora.CADENCE_MS", page)
        self.assertIn("cache:'no-store'", page.replace(" ", ""))
        self.assertIn("data/check.enc.json", page)
        self.assertNotIn("c0ef956f", page)


if __name__ == "__main__":
    unittest.main()
