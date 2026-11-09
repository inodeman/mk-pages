/* Última hora: Mac y Box en una página. Sin cifras de experimento. */
(function () {
  var CADENCE_MS = 300000;
  var STALE_MS = 600000;
  var OFFSET = 7 * 60 * 60 * 1000;

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"]/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch];
    });
  }

  function pad(n) {
    return String(n).padStart(2, "0");
  }

  function formatJuarez(ms) {
    if (!isFinite(ms)) return null;
    var d = new Date(ms - OFFSET);
    return (
      d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate()) +
      " " + pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes()) + ":" + pad(d.getUTCSeconds()) +
      " (UTC−7)"
    );
  }

  function freshness(iso, now) {
    if (!iso) return { state: "no_data", age_s: null };
    var ms = Date.parse(iso);
    if (!isFinite(ms)) return { state: "no_data", age_s: null };
    var age = now - ms;
    if (age < -120000) return { state: "no_data", age_s: age / 1000 };
    if (age > STALE_MS) return { state: "stale", age_s: age / 1000 };
    return { state: "fresh", age_s: age / 1000 };
  }

  function publicationFresh(doc, now) {
    if (!doc) return { state: "no_data" };
    var generated = freshness(doc.generated_at, now);
    var asOf = freshness(doc.as_of, now);
    if (generated.state === "no_data" || asOf.state === "no_data") return { state: "no_data" };
    if (generated.state === "stale" || asOf.state === "stale") return { state: "stale" };
    return { state: "fresh" };
  }

  function emptySession() {
    return { mac: { count: 0, lastMark: null }, box: { count: 0, lastMark: null } };
  }

  function observeOne(state, doc, now) {
    state = state || { count: 0, lastMark: null };
    if (!doc || doc.synthetic) return state;
    if (publicationFresh(doc, now).state !== "fresh") return state;
    var mark = String(doc.generated_at) + "/" + String(doc.seq == null ? "" : doc.seq);
    if (mark !== state.lastMark) {
      state = { count: state.count + 1, lastMark: mark };
    }
    return state;
  }

  function observe(session, docs, now) {
    session = session || emptySession();
    return {
      mac: observeOne(session.mac, docs && docs.mac, now),
      box: observeOne(session.box, docs && docs.box, now)
    };
  }

  function nodata(label) {
    return '<span class="nodata">' + esc(label || "Sin datos") + "</span>";
  }

  function pctCell(block, fresh) {
    if (!fresh || fresh.state !== "fresh") return nodata("Sin datos");
    if (!block || block.state !== "medido" || block.pct == null || !(block.finished > 0) || block.won == null || block.lost == null) {
      return nodata("Sin datos");
    }
    var extra = "";
    var notes = [];
    if (block.interrupted > 0) notes.push(block.interrupted + " interrumpidas");
    if (block.invalid > 0) notes.push(block.invalid + " inválidas");
    if (notes.length) extra = ' <small class="mu">(' + esc(notes.join(", ")) + ", no son derrotas)</small>";
    return esc(Number(block.pct).toFixed(1)) + " % (" + esc(block.won) + " v / " + esc(block.lost) + " d / " + esc(block.finished) + " terminadas)" + extra;
  }

  function goroCell(block, fresh) {
    if (!fresh || fresh.state !== "fresh") return nodata("Sin datos");
    if (!block || block.state === "sin_datos" || !block.state) return nodata("Sin datos");
    if (block.state !== "medido") {
      var note = "";
      if (block.reason) note += " " + block.reason + ".";
      if (block.rejected_not_goro > 0) note += " p2_ch distinto de 7 no es Goro.";
      if (block.unvalidated > 0) note += " Hay etapa 11 sin rival validado.";
      return nodata("SIN VALIDAR") + (note ? ' <small class="mu">' + esc(note.trim()) + "</small>" : "");
    }
    var extra = "";
    if (block.unvalidated > 0) extra += " Hay etapa 11 sin validar que no entra.";
    if (block.rejected_not_goro > 0) extra += " p2_ch distinto de 7 no entra.";
    return pctCell(block, fresh) + (extra ? ' <small class="mu">' + esc(extra.trim()) + "</small>" : "");
  }

  function when(iso) {
    if (!iso) return nodata("Sin datos");
    var ms = Date.parse(iso);
    if (!isFinite(ms)) return nodata("Sin datos");
    return esc(formatJuarez(ms));
  }

  function excludedLine(doc) {
    var ex = doc.excluded || {};
    var parts = [];
    if (ex.legacy_actor) parts.push(ex.legacy_actor + " ids antiguos 20–36");
    if (ex.out_of_range) parts.push(ex.out_of_range + " fuera de rango");
    if (ex.wrong_machine) parts.push(ex.wrong_machine + " de la otra máquina");
    if (ex.before_epoch) parts.push(ex.before_epoch + " anteriores a la época");
    if (ex.other_brain) parts.push(ex.other_brain + " de otro cerebro");
    if (ex.other_lineage) parts.push(ex.other_lineage + " de un linaje anterior, no son este resultado");
    if (ex.outside_window) parts.push(ex.outside_window + " fuera de la hora");
    if (ex.duplicate) parts.push(ex.duplicate + " duplicados");
    if (ex.unknown_role) parts.push(ex.unknown_role + " sin rol");
    if (ex.missing_epoch) parts.push("sin época, no se atribuyen");
    if (ex.lab_event) parts.push(ex.lab_event + " de experimento, no entran");
    if (!parts.length) return "";
    return '<p class="mu">No contados: ' + esc(parts.join(" · ")) + ".</p>";
  }

  function actorHealth(doc) {
    var rows = doc.actors || [];
    if (!rows.length) return "";
    var missing = rows.filter(function (row) { return row.reporting === "sin_reporte"; });
    if (!missing.length) return "<p>Actores con registros en la ventana: " + esc(rows.map(function (row) { return row.actor_id; }).join(", ")) + ".</p>";
    return "<p>Sin reporte: " + esc(missing.map(function (row) { return row.actor_id; }).join(", ")) + ". No es un porcentaje.</p>";
  }

  function table(doc, fresh) {
    var evals = doc.eval || {};
    var train = doc.train || {};
    var rows = "";
    for (var n = 1; n <= 10; n++) {
      var key = String(n);
      rows += "<tr><td>" + n + "</td><td>" + pctCell((evals.stages || {})[key], fresh) + "</td><td>" + pctCell((train.stages || {})[key], fresh) + "</td></tr>";
    }
    rows += '<tr><th>1–10</th><td>' + pctCell(evals.summary_1_10, fresh) + "</td><td>" + pctCell(train.summary_1_10, fresh) + "</td></tr>";
    var goro = doc.goro || {};
    rows += "<tr><th>Goro</th><td>" + goroCell(goro.eval, fresh) + "</td><td>" + goroCell(goro.train, fresh) + "</td></tr>";
    return '<table><tr><th>Etapa</th><th>Evaluación (pruebas)</th><th>Entrenamiento</th></tr>' + rows + "</table>";
  }

  function machine(doc, id, session, now) {
    var name = id === "box" ? "Box" : "Mac";
    var expected = id === "box" ? "2–12" : "0–7";
    var head = '<section class="card" data-machine="' + id + '"><h2>' + name + "</h2>";
    var hint = id === "mac"
      ? "Actores 0–7, leídos como 40–47 en el CSV de la Box (nativo = id − 40). El CSV de la Mac no se suma."
      : "Actores 2–12 del mismo CSV de la Box. 40–47 no entran en esta columna.";
    if (!doc) {
      return head + '<p class="nodata">Sin datos</p><p class="mu">No hay data/hora_' + id + ".enc.json publicado.</p><p class=\"mu\">" + hint + "</p></section>";
    }
    if (doc.synthetic) {
      return head + '<p class="nodata">Sin datos</p><p class="mu">El archivo está marcado como sintético y no se muestra como medición.</p></section>';
    }
    var fresh = publicationFresh(doc, now);
    var banner = "";
    if (fresh.state === "stale") banner = '<p class="warn">Dato viejo. Los porcentajes quedan en Sin datos hasta una publicación nueva. Recargar el navegador no la crea.</p>';
    if (fresh.state === "no_data") banner = '<p class="warn">Sin fecha de publicación usable. Porcentajes en Sin datos.</p>';
    var seen = session && session[id] ? session[id].count : 0;
    var proof = seen >= 2
      ? "Ciclo de esta sesión: 2 publicaciones distintas."
      : "Publicaciones distintas y frescas en esta sesión: " + seen + " de 2. Hace falta otra publicación real.";
    var source = doc.source || {};
    var brain = doc.brain || {};
    var last = when(source.last_fight_at);
    if (source.last_fight_at && source.last_fight_in_window === false) last += ' <small class="mu">(fuera de esta hora)</small>';
    return head + banner +
      "<p>" + esc(proof) + "</p>" +
      "<p>Fuente: " + (source.path_label ? esc(source.path_label) : nodata("Sin datos")) +
      " · conectada: " + (source.connected === true ? "sí" : source.connected === false ? "no" : nodata("Sin datos")) + "</p>" +
      "<p>Última pelea: " + last + "</p>" +
      "<p>Actualización: " + when(doc.generated_at) + "</p>" +
      "<p>Ventana: " + when(doc.window && doc.window.start) + " → " + when(doc.window && doc.window.end) + "</p>" +
      "<p>Época del cerebro: " + (brain.epoch_id ? esc(brain.epoch_id) + " · " : "") + when(brain.epoch_start) + (brain.live_version_min != null ? " · versión viva &gt;= " + esc(brain.live_version_min) : "") + "</p>" +
      "<p>SHA: " + (brain.sha16 ? "<code>" + esc(brain.sha16) + "</code>" : nodata("Sin datos")) + "</p>" +
      "<p>Detector: " + esc(doc.detector || "Sin datos") + ". Esta página no certifica validación visual.</p>" +
      (doc.clock_basis ? "<p class=\"mu\">" + esc(doc.clock_basis) + "</p>" : "") +
      actorHealth(doc) +
      table(doc, fresh) +
      excludedLine(doc) +
      '<p class="mu">' + hint + "</p></section>";
  }

  function render(model) {
    var now = model.now;
    var session = model.session || emptySession();
    return '<div class="grid">' +
      machine(model.mac, "mac", session, now) +
      machine(model.box, "box", session, now) +
      "</div>";
  }

  globalThis.MKHora = {
    CADENCE_MS: CADENCE_MS,
    STALE_MS: STALE_MS,
    formatJuarez: formatJuarez,
    freshness: freshness,
    publicationFresh: publicationFresh,
    emptySession: emptySession,
    observe: observe,
    render: render
  };
})();
