/* SYNTHETIC display checks. These numbers are not a measurement. */
const fs = require("fs");
const vm = require("vm");
const { execFileSync } = require("child_process");

const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync("panel/hora.js", "utf8"), sandbox);
const MK = sandbox.MKHora;

function assert(cond, message) {
  if (!cond) {
    console.error(message);
    process.exit(1);
  }
}

assert(MK.CADENCE_MS === 300000, "cadence");
assert(MK.STALE_MS === 600000, "stale window");
assert(MK.formatJuarez(Date.parse("2026-11-08T14:52:02Z")) === "2026-11-08 07:52:02 (UTC−7)", "november");
assert(MK.formatJuarez(Date.parse("2026-06-15T18:00:00Z")) === "2026-06-15 11:00:00 (UTC−7)", "june stays UTC-7");

const now = Date.parse("2099-03-01T12:00:00-07:00");
const fresh = {
  schema: "mk.panel.hora.v1",
  synthetic: false,
  machine: "mac",
  generated_at: "2099-03-01T12:00:00-07:00",
  as_of: "2099-03-01T12:00:00-07:00",
  seq: 1,
  window: { start: "2099-03-01T11:00:00-07:00", end: "2099-03-01T12:00:00-07:00", minutes: 60 },
  source: { path_label: "runs/standalone/fights.csv", connected: true, last_fight_at: "2099-03-01T11:50:00-07:00", last_fight_in_window: true },
  brain: { epoch_start: "2099-03-01T00:00:00-07:00", sha16: "abababababababab" },
  detector: "ram",
  visual_validation: false,
  eval: {
    stages: { "4": { state: "medido", won: 0, lost: 2, finished: 2, pct: 0, interrupted: 0, invalid: 0 } },
    summary_1_10: { state: "medido", won: 0, lost: 2, finished: 2, pct: 0, interrupted: 1, invalid: 0 }
  },
  train: { stages: {}, summary_1_10: { state: "sin_datos", won: null, lost: null, finished: null, pct: null } },
  goro: {
    eval: { state: "sin_validar", pct: null, won: null, rejected_not_goro: 1, unvalidated: 0 },
    train: { state: "sin_datos", pct: null }
  },
  excluded: { legacy_actor: 2 }
};

const html = MK.render({ now, mac: fresh, box: null, session: MK.emptySession() });
assert(html.includes("0.0 % (0 v / 2 d / 2 terminadas)"), "measured zero keeps denominator");
assert(html.includes("1 interrumpidas"), "interrupted stays out of the losses");
assert(html.includes("SIN VALIDAR"), "goro unvalidated");
assert(html.includes("distinto de 7"), "guard note");
assert(html.includes("Sin datos"), "box and empty cells");
assert(html.includes('data-machine="mac"') && html.includes('data-machine="box"'), "both machines");
assert(html.includes("2 ids antiguos"), "legacy ids are not remapped");
assert(html.includes("no certifica validación visual"), "no global visual claim");

const staleDoc = Object.assign({}, fresh, { generated_at: "2099-03-01T10:00:00-07:00" });
const staleHtml = MK.render({ now, mac: staleDoc, box: null, session: MK.emptySession() });
assert(staleHtml.includes("Dato viejo"), "stale banner");
assert(!staleHtml.includes("0.0 %"), "stale zero is not shown as a percent");
assert(staleHtml.includes("Sin datos"), "stale rates");

const syntheticHtml = MK.render({ now, mac: Object.assign({}, fresh, { synthetic: true }), box: null, session: MK.emptySession() });
assert(syntheticHtml.includes("sintético"), "synthetic banner");
assert(!syntheticHtml.includes("0.0 %"), "synthetic numbers hidden");

let session = MK.emptySession();
session = MK.observe(session, { mac: fresh, box: null }, now);
session = MK.observe(session, { mac: fresh, box: null }, now);
assert(session.mac.count === 1, "repeat fetch is not a second publication");
const second = Object.assign({}, fresh, { generated_at: "2099-03-01T12:05:00-07:00", seq: 2 });
session = MK.observe(session, { mac: second, box: null }, Date.parse("2099-03-01T12:05:00-07:00"));
assert(session.mac.count === 2, "second fresh publication counts");
session = MK.observe(session, { mac: staleDoc, box: null }, now);
assert(session.mac.count === 2, "stale file does not count");

const built = execFileSync("python3", ["-c", `
import json
from panel.hora_ingest import build_hour
print(json.dumps(build_hour({
  "machine": "box",
  "synthetic": False,
  "as_of": "2099-03-01T12:00:00-07:00",
  "generated_at": "2099-03-01T12:00:00-07:00",
  "seq": 3,
  "brain_epoch_start": "2099-03-01T00:00:00-07:00",
  "detector": "ram",
  "source": {"connected": True, "path_label": "runs/scorpion/fights.csv"},
  "events": [
    {"event_id":"b","machine":"box","actor_id":2,"role":"eval","clock":"2099-03-01T11:10:00-07:00","stage":1,"status":"finished","won":1},
    {"event_id":"m","machine":"mac","actor_id":2,"role":"eval","clock":"2099-03-01T11:10:00-07:00","stage":1,"status":"finished","won":1}
  ]
})))
`], { encoding: "utf8" });
const box = JSON.parse(built);
const both = MK.render({ now, mac: null, box, session: MK.emptySession() });
assert(both.includes("100.0 % (1 v / 0 d / 1 terminadas)"), "box native count");
assert(box.excluded.wrong_machine === 1, "mac feed excluded from box");
assert(!both.slice(both.indexOf('data-machine="box"')).includes("2 v"), "mac win was not added");
console.log("display ok");
