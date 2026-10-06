// ── Elevløn-trin (2026-10-06) ───────────────────────────────────────────────
// Popups ved trinskift, godkend/behold-dialog, elevoversigt (opstartstjek) og
// advarsel i Lønkørsel. Bruger app.js' hjælpere (GET/POST/api/h/openModal/toast).

const _elevState = { types: [], rateByType: {}, settings: null };

function _elevDk(iso) { return iso ? formatDateShort(iso) : "–"; }
function _elevAddDays(iso, days) {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}
function _elevRate(type) {
  const r = _elevState.rateByType[type];
  return r == null ? "" : ` (${r.toFixed(2).replace(".", ",")} kr/t)`;
}

function _elevModal(id, title, width = 520) {
  let el = document.getElementById(id);
  if (!el) {
    el = document.createElement("div");
    el.id = id;
    el.className = "modal-overlay";
    el.innerHTML = `
      <div class="modal" style="width:${width}px;max-width:95vw">
        <div class="modal-header"><h2></h2>
          <button class="modal-close" onclick="closeModal('${id}')">&#215;</button></div>
        <div class="modal-body"></div>
        <div class="modal-footer"></div>
      </div>`;
    document.body.appendChild(el);
  }
  el.querySelector(".modal-header h2").innerHTML = title;
  return { el, body: el.querySelector(".modal-body"), footer: el.querySelector(".modal-footer") };
}

async function _elevLoadTypes() {
  const types = await GET("/api/employees/agreement-types");
  _elevState.types = types.map(t => t.name);
  _elevState.rateByType = Object.fromEntries(types.map(t => [t.name, t.hourly_rate]));
}

// ── Popups efter login ──────────────────────────────────────────────────────
async function checkElevAlerts() {
  if (!_hasPerm("elev_wage_approve")) return;
  try {
    const data = await GET("/api/elev/alerts");
    const queue = [
      ...data.mismatches.map(m => ({ kind: "mismatch", ...m })),
      ...data.upcoming.map(u => ({ kind: "upcoming", ...u })),
      ...data.applied.map(a => ({ kind: "applied", ...a })),
    ];
    if (!queue.length) return;
    await _elevLoadTypes();
    _elevShowAlert(queue, 0);
  } catch (e) {
    console.error("Elevløn-advarsel check fejlede:", e);
  }
}

function _elevShowAlert(queue, i) {
  const a = queue[i];
  const titles = {
    mismatch: "&#9888; Mulig fejl i elevløn",
    upcoming: "&#127891; Elev går ind i nyt år af lærekontrakten",
    applied:  "&#127891; Ny elevløn er trådt i kraft",
  };
  const m = _elevModal("modal-elev-alert", titles[a.kind], 500);
  const more = queue.length - i - 1;
  let text = "";
  if (a.kind === "mismatch") {
    text = `<p style="font-size:14px;margin-bottom:8px">${h(a.reason)}</p>
      <p style="font-size:13px;color:var(--text-light)">Forventet: <strong>${h(a.expected_type)}</strong>${_elevRate(a.expected_type)}</p>`;
  } else if (a.kind === "upcoming") {
    text = `<p style="font-size:14px;margin-bottom:8px">${h(a.reason)}</p>
      <p style="font-size:13px;color:var(--text-light)">Foreslået: <strong>${h(a.to_type)}</strong>${_elevRate(a.to_type)}
      for hele lønperioden ${_elevDk(a.effective_from)} – ${_elevDk(a.effective_to)}.</p>`;
  } else {
    text = a.took_effect
      ? `<p style="font-size:14px"><strong>${h(a.employee_name)}</strong> har nu <strong>${h(a.to_type)}</strong>${_elevRate(a.to_type)}
         fra lønperioden ${_elevDk(a.effective_from)} – ${_elevDk(a.effective_to)}.</p>`
      : `<p style="font-size:14px">Skiftet for <strong>${h(a.employee_name)}</strong> til <strong>${h(a.to_type)}</strong>
         blev ikke anvendt, fordi overenskomsttypen er ændret manuelt. Tjek medarbejderen.</p>`;
  }
  m.body.innerHTML = text + (more > 0 ? `<p style="font-size:12px;color:var(--text-light);margin-top:8px">+ ${more} flere.</p>` : "");

  const next = () => { closeModal("modal-elev-alert"); if (i + 1 < queue.length) _elevShowAlert(queue, i + 1); };
  m.footer.innerHTML = "";
  const btn = (label, cls, fn) => {
    const b = document.createElement("button");
    b.className = `btn ${cls}`;
    b.textContent = label;
    b.onclick = fn;
    m.footer.appendChild(b);
  };
  btn("Luk", "btn-secondary", next);
  if (a.kind === "upcoming") {
    btn("Påmind mig ikke igen", "btn-secondary", async () => {
      await POST("/api/elev/snooze", { employee_id: a.employee_id, event_date: a.event_date, mode: "never" });
      next();
    });
    btn("Påmind igen", "btn-warning", async () => {
      await POST("/api/elev/snooze", { employee_id: a.employee_id, event_date: a.event_date, mode: "later" });
      next();
    });
  }
  if (a.kind === "applied") {
    btn("OK", "btn-primary", async () => { await POST(`/api/elev/applied/${a.decision_id}/ack`, {}); next(); });
  } else {
    btn("Behandl", "btn-primary", () => {
      closeModal("modal-elev-alert");
      openElevDecision(a.kind === "mismatch"
        ? { employee_id: a.employee_id, employee_name: a.employee_name, event_date: a.event_date,
            reason: a.reason, from_type: a.current_type, to_type: a.expected_type, effective_from: a.period_start }
        : a, () => { if (i + 1 < queue.length) _elevShowAlert(queue, i + 1); });
    });
  }
  openModal("modal-elev-alert");
}

// ── Godkend / behold-dialog ─────────────────────────────────────────────────
// s: {employee_id, employee_name, event_date, reason, from_type, to_type, effective_from}
async function openElevDecision(s, onDone) {
  if (!_elevState.types.length) await _elevLoadTypes();
  const m = _elevModal("modal-elev-decision", "Elevløn: godkend ændring", 560);
  const periods = [0, 14, 28, 42].map(d => _elevAddDays(s.effective_from, d));
  m.body.innerHTML = `
    <p style="font-size:14px;margin-bottom:12px">${h(s.reason || "")}</p>
    <table style="width:100%;font-size:13px;margin-bottom:12px">
      <tr><td style="color:var(--text-light);width:140px">Nuværende</td>
          <td><strong>${h(s.from_type || "")}</strong>${_elevRate(s.from_type)}</td></tr>
      <tr><td style="color:var(--text-light)">Foreslået</td>
          <td><strong>${h(s.to_type || "")}</strong>${_elevRate(s.to_type)}</td></tr>
    </table>
    <div class="form-group"><label>Ny overenskomsttype</label>
      <select id="elev-dec-type">${_elevState.types.map(t =>
        `<option value="${h(t)}" ${t === s.to_type ? "selected" : ""}>${h(t)}${_elevRate(t)}</option>`).join("")}</select></div>
    <div class="form-group"><label>Gælder fra lønperioden (hele perioden)</label>
      <select id="elev-dec-period">${periods.map(p =>
        `<option value="${p}">${_elevDk(p)} – ${_elevDk(_elevAddDays(p, 13))}</option>`).join("")}</select></div>
    <div class="form-group"><label>Bemærkning (påkrævet ved "Behold nuværende")</label>
      <textarea id="elev-dec-note" rows="2" style="width:100%"></textarea></div>`;
  m.footer.innerHTML = `
    <button class="btn btn-secondary" id="elev-dec-cancel">Annullér</button>
    <button class="btn btn-warning" id="elev-dec-keep">Behold nuværende</button>
    <button class="btn btn-primary" id="elev-dec-approve">Godkend</button>`;
  const send = async (decision) => {
    const body = {
      employee_id: s.employee_id, event_date: s.event_date, decision,
      to_type: decision === "approve" ? document.getElementById("elev-dec-type").value : s.to_type,
      effective_from: document.getElementById("elev-dec-period").value,
      note: document.getElementById("elev-dec-note").value,
    };
    if (decision === "keep" && !body.note.trim()) { toast("Skriv hvorfor satsen bevares", "error"); return; }
    try {
      await POST("/api/elev/decisions", body);
      toast(decision === "approve" ? "Ændringen er godkendt" : "Nuværende sats bevares");
      closeModal("modal-elev-decision");
      if (onDone) onDone();
    } catch (e) { toast(e.message, "error"); }
  };
  document.getElementById("elev-dec-cancel").onclick = () => { closeModal("modal-elev-decision"); if (onDone) onDone(); };
  document.getElementById("elev-dec-keep").onclick = () => send("keep");
  document.getElementById("elev-dec-approve").onclick = () => send("approve");
  openModal("modal-elev-decision");
}

// ── Elevoversigt (opstartstjek + indstillinger) ─────────────────────────────
const _ELEV_STATUS = {
  ok: "&#10004; Passer",
  afviger: '<span style="color:var(--danger)">&#10008; Afviger</span>',
  voksenelev: "Voksenelev (almindelig løn)",
  ingen_trin: "Ingen trin",
  uden_for_kontrakt: "Uden for kontrakten",
};

async function openElevOverview() {
  try {
    await _elevLoadTypes();
    const data = await GET("/api/elev/overview");
    _elevState.settings = data.settings;
    _elevState.overviewPeriodStart = data.period_start;
    const m = _elevModal("modal-elev-overview", "Elevoversigt", 1000);
    const s = data.settings;
    const canEdit = _hasPerm("stamdata");
    const rows = data.rows.map(r => {
      const action = r.scheduled
        ? `Planlagt: ${h(r.scheduled.to_type)} fra ${_elevDk(r.scheduled.effective_from)}
           <button class="btn btn-secondary" style="padding:2px 8px;font-size:12px" onclick="cancelElevDecision(${r.scheduled.id})">Annullér</button>`
        : r.next_change
          ? `${_elevDk(r.next_change.event_date)} → ${h(r.next_change.to_type)}
             <button class="btn btn-primary" style="padding:2px 8px;font-size:12px" onclick='_elevDecideFromRow(${JSON.stringify(r).replace(/'/g, "&#39;")}, "next")'>Behandl</button>`
          : "";
      const fix = r.status === "afviger"
        ? ` <button class="btn btn-warning" style="padding:2px 8px;font-size:12px" onclick='_elevDecideFromRow(${JSON.stringify(r).replace(/'/g, "&#39;")}, "fix")'>Ret / behold</button>` : "";
      return `<tr>
        <td>${h(r.employee_name)}<br><span style="color:var(--text-light)">${h(r.employee_number)}</span></td>
        <td>${_elevDk(r.elev_start_date)} – ${_elevDk(r.elev_end_date)}</td>
        <td>${h(r.current_type)}${r.type_unknown ? ' <span style="color:var(--danger)">(findes ikke i Stamdata)</span>' : ""}</td>
        <td>${h(r.expected_type || "–")}</td>
        <td>${_ELEV_STATUS[r.status] || ""}${fix}</td>
        <td>${action}</td></tr>`;
    }).join("");
    m.body.innerHTML = `
      ${data.missing_step_types.length ? `<div class="alert-banner mb-16"><span class="icon">⚠️</span><div class="text">
        Overenskomsttyper mangler i Stamdata: ${data.missing_step_types.map(h).join(", ")}</div></div>` : ""}
      ${!s.enabled ? `<div class="alert-banner mb-16"><span class="icon">&#128270;</span><div class="text">
        <h4>Gennemgå oversigten før advarslerne starter</h4>
        Tjek at start-/slutdatoer og overenskomsttyper er rigtige. Ret afvigelser, og tryk så
        "Oversigten er gennemgået".</div></div>` : ""}
      <p style="font-size:13px;color:var(--text-light);margin-bottom:8px">
        Aktuel lønperiode ${_elevDk(data.period_start)} – ${_elevDk(data.period_end)}.
        Trinnet regnes baglæns fra slutdatoen; skifter eleven trin inde i en lønperiode, gælder den nye sats hele perioden.</p>
      <table class="grid-table" style="width:100%;font-size:13px">
        <thead><tr><th>Elev</th><th>Lærekontrakt</th><th>Overenskomsttype nu</th><th>Forventet</th><th>Status</th><th>Næste skift</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="6">Ingen aktive elever.</td></tr>'}</tbody>
      </table>
      <h3 style="font-size:14px;margin:16px 0 8px">Indstillinger for advarsler</h3>
      <div class="form-row">
        <div class="form-group"><label>Varsel (dage før lønperioden med skiftet)</label>
          <input type="number" id="elev-set-notice" min="1" max="365" value="${s.notice_days}" ${canEdit ? "" : "disabled"}></div>
        <div class="form-group"><label>Påmind igen (dage før)</label>
          <select id="elev-set-remind-never" ${canEdit ? "" : "disabled"}>
            <option value="days" ${s.remind_days != null ? "selected" : ""}>Antal dage</option>
            <option value="never" ${s.remind_days == null ? "selected" : ""}>Aldrig</option></select>
          <input type="number" id="elev-set-remind" min="0" max="365" value="${s.remind_days ?? 7}"
                 ${canEdit ? "" : "disabled"} style="${s.remind_days == null ? "display:none" : ""}"></div>
      </div>`;
    m.footer.innerHTML = `
      <button class="btn btn-secondary" onclick="closeModal('modal-elev-overview')">Luk</button>
      ${canEdit ? '<button class="btn btn-secondary" id="elev-set-save">Gem indstillinger</button>' : ""}
      ${!s.enabled && _hasPerm("elev_wage_approve") ? '<button class="btn btn-primary" id="elev-enable">Oversigten er gennemgået</button>' : ""}`;
    const never = document.getElementById("elev-set-remind-never");
    never.onchange = () => {
      document.getElementById("elev-set-remind").style.display = never.value === "never" ? "none" : "";
    };
    const save = document.getElementById("elev-set-save");
    if (save) save.onclick = async () => {
      try {
        await api("PUT", "/api/elev/settings", {
          notice_days: parseInt(document.getElementById("elev-set-notice").value, 10),
          remind_days: never.value === "never" ? null : parseInt(document.getElementById("elev-set-remind").value, 10),
        });
        toast("Indstillinger gemt");
      } catch (e) { toast(e.message, "error"); }
    };
    const enable = document.getElementById("elev-enable");
    if (enable) enable.onclick = async () => {
      if (data.rows.some(r => r.status === "afviger") &&
          !confirm("Der er stadig afvigelser. Start advarslerne alligevel?")) return;
      await POST("/api/elev/enable", {});
      toast("Elevløn-advarsler er slået til");
      openElevOverview();
    };
    openModal("modal-elev-overview");
  } catch (e) { toast(e.message, "error"); }
}

function _elevDecideFromRow(r, mode) {
  const s = mode === "fix"
    ? { employee_id: r.employee_id, employee_name: r.employee_name,
        event_date: r.expected_event_date,
        reason: `${r.employee_name} har '${r.current_type}', men forventet er '${r.expected_type}'.`,
        from_type: r.current_type, to_type: r.expected_type }
    : { employee_id: r.employee_id, employee_name: r.employee_name, event_date: r.next_change.event_date,
        reason: `${r.employee_name} går ind i et nyt år af sin lærekontrakt den ${_elevDk(r.next_change.event_date)}.`,
        from_type: r.current_type, to_type: r.next_change.to_type, effective_from: r.next_change.effective_from };
  if (!s.effective_from) s.effective_from = _elevState.overviewPeriodStart || new Date().toISOString().slice(0, 10);
  openElevDecision(s, openElevOverview);
}

async function cancelElevDecision(id) {
  if (!confirm("Annullér den planlagte ændring?")) return;
  try {
    await DEL(`/api/elev/decisions/${id}`);
    toast("Ændringen er annulleret");
    openElevOverview();
  } catch (e) { toast(e.message, "error"); }
}

// ── Lønkørsel: mulige fejl ──────────────────────────────────────────────────
function renderElevWarnings(container, warnings) {
  if (!warnings || !warnings.length) return;
  const el = document.createElement("div");
  el.className = "alert-banner mb-16";
  el.innerHTML = `<span class="icon">⚠️</span><div class="text"><h4>Mulig fejl i elevløn (${warnings.length})</h4>
    ${warnings.map(w => h(w.reason)).join("<br>")}
    <br><a href="#" onclick="openElevOverview();return false">Åbn elevoversigten</a> for at rette eller bevare satsen.
    Eksporten er ikke blokeret.</div>`;
  container.appendChild(el);
}
