// ── Advarsler-oversigten (2026-10-06) ───────────────────────────────────────
// Én oversigt med alle advarsler i stedet for en popup pr. type, og en klokke (🔔 + antal)
// i toppen. Vinduet åbner kun af sig selv ved start, når der er NYE advarsler.
// Grupper: Mulig fejl i løn · Kommende ændringer i overenskomst (elevløn + anciennitet) · Øvrige.
// "⚙ Indstillinger": hver bruger vælger selv, hvornår de får besked.

const _ao = { data: null, actions: [] };

function _aoKr(v) { return v == null ? "" : `${v.toFixed(2).replace(".", ",")} kr`; }

async function checkAllAlerts() {
  try {
    _ao.data = await GET("/api/alerts");
    _aoUpdateBell(_ao.data.total);
    // Åbner kun af sig selv, når der er nyt – og brugeren ikke har slået det fra i ⚙ Indstillinger
    if (_ao.data.new_keys.length && _ao.data.auto_open) openAlertsOverview();
  } catch (e) {
    console.error("Advarsler kunne ikke hentes:", e);
  }
}

function _aoUpdateBell(n) {
  const bell = document.getElementById("btn-alerts-bell");
  if (!bell) return;
  bell.style.display = "";
  const c = document.getElementById("alerts-bell-count");
  c.textContent = n;
  c.style.display = n ? "" : "none";
}

async function _aoReload(reopen = true) {
  _ao.data = await GET("/api/alerts");
  _aoUpdateBell(_ao.data.total);
  if (reopen) openAlertsOverview();
}

function _aoModal() {
  let el = document.getElementById("modal-alerts-overview");
  if (!el) {
    el = document.createElement("div");
    el.id = "modal-alerts-overview";
    el.className = "modal-overlay";
    el.innerHTML = `
      <div class="modal" style="width:780px;max-width:96vw">
        <div class="modal-header"><h2 id="ao-title">Advarsler</h2>
          <button class="modal-close" onclick="closeModal('modal-alerts-overview')">&#215;</button></div>
        <div class="modal-body" id="ao-body"></div>
        <div class="modal-footer">
          <span style="flex:1;font-size:12px;color:var(--text-light);align-self:center">
            Lukker du oversigten, kan du åbne den igen via &#128276; øverst til højre.</span>
          <button class="btn btn-secondary" onclick="openAlertSettings()">&#9881; Indstillinger</button>
          <button class="btn btn-secondary" onclick="closeModal('modal-alerts-overview')">Luk</button>
        </div>
      </div>`;
    document.body.appendChild(el);
  }
  return el;
}

function _aoDecision(m) {
  // Fælles dialog for elevløn og anciennitet (static/js/elev.js)
  return _aoDialog(() => openElevDecision({
    kind: m.kind, employee_id: m.employee_id, employee_name: m.employee_name, event_date: m.event_date,
    reason: m.reason, from_type: m.current_type || m.from_type, to_type: m.expected_type || m.to_type,
    effective_from: m.suggested_from || m.effective_from, locked_periods: m.locked_periods || [],
  }, () => _aoReload()));
}

async function openAlertsOverview() {
  if (!_ao.data) _ao.data = await GET("/api/alerts");
  const g = _ao.data.groups;
  _aoModal();
  _ao.actions = [];
  const other = g.other.map(o => {
    const ok = ["OK", "btn-primary", () => _aoPost("/api/alerts/ok", { keys: [o.key] })];
    const go = _hasPerm("view_employees") ? [["Gå til medarbejder", "btn-secondary", () => _aoGoto(o.employee_id)]] : [];
    if (o.type === "rates") {
      return _aoRow(`Nye satser fra ${dkDate(o.valid_from)}`,
        o.rates.map(x => `${h(x.agreement_type)}: ${_aoKr(x.current_rate)} → <strong>${_aoKr(x.new_rate)}</strong>`
          + (x.note ? ` <span style="color:var(--text-light)">(${h(x.note)})</span>` : "")).join("<br>")
        + `<br>Hele lønperioden ${dkPeriod(o.period_start, o.period_end)} får de nye satser.`, [ok]);
    }
    if (o.type === "p56_upcoming") return _aoRow(o.employee_name, `§56-aftalen udløber ${dkDate(o.paragraf_56_end_date)}.`, [...go, ok]);
    if (o.type === "p56_expired") return _aoRow(o.employee_name,
      `§56-aftalen er automatisk deaktiveret, da slutdatoen (${dkDate(o.paragraf_56_end_date)}) er overskredet.`, [...go, ok]);
    return _aoRow(o.employee_name, `${h(o.label)} den ${dkDate(o.event_date)}.`, [...go, ok]);
  });
  const sections = [
    _aoGroup("error", "&#9888;", "Mulig fejl i løn", g.mismatches.map(m => _aoRow(m.employee_name, h(m.reason),
      [["Behandl", "btn-primary", () => _aoDecision(m)]],
      (m.locked_periods || []).map(l => "&#128274; " + h(l.text)).join("<br>"), m.claimed_by))),
    _aoGroup("raise", "&#128200;", "Kommende ændringer i overenskomst", [
      // Ingen "Påmind mig ikke igen": lønstigninger skal behandles (Behold kræver bemærkning i dialogen)
      ...g.raises.map(u => _aoRow(u.employee_name, h(u.reason), [
        ["Påmind igen", "btn-secondary", () => _aoPost("/api/elev/snooze",
          { employee_id: u.employee_id, event_date: u.event_date, mode: "later" })],
        ["Behandl", "btn-primary", () => _aoDecision(u)],
      ], "", u.claimed_by)),
      ...g.applied.map(a => _aoRow(a.employee_name, a.took_effect
          ? `Har nu <strong>${h(a.to_type)}</strong> fra lønperioden ${dkPeriod(a.effective_from, a.effective_to)}.`
          : `Skiftet til <strong>${h(a.to_type)}</strong> blev ikke anvendt, fordi typen er ændret manuelt. Tjek medarbejderen.`,
        [["OK", "btn-primary", () => _aoPost(`/api/elev/applied/${a.decision_id}/ack`, {})]])),
    ]),
    _aoGroup("other", "&#128276;", "Øvrige", other),
  ];
  document.getElementById("ao-title").textContent = `Advarsler (${_ao.data.total})`;
  document.getElementById("ao-body").innerHTML = sections.join("") ||
    `<div class="ao-empty">Ingen advarsler &#10004;</div>`;
  openModal("modal-alerts-overview");
  // Det brugeren nu har set, åbner ikke vinduet af sig selv igen ved næste start
  const keys = Object.values(g).flat().map(i => i.key);
  if (keys.length) POST("/api/alerts/seen", { keys }).catch(() => {});
}

function _aoGroup(cls, icon, title, rows) {
  if (!rows.length) return "";
  return `<div class="ao-grp ao-${cls}"><h3>${icon} ${title} <span class="ao-n">${rows.length}</span></h3>${rows.join("")}</div>`;
}

function _aoRow(who, what, actions, extra = "", claimedBy = null) {
  const btns = claimedBy ? "" : actions.map(([label, cls, fn]) => {
    _ao.actions.push(fn);
    return `<button class="btn ${cls}" onclick="_aoRun(${_ao.actions.length - 1})">${label}</button>`;
  }).join("");
  const lock = claimedBy ? `<div class="ao-lock">&#128274; Behandles af ${h(claimedBy)}</div>` : "";
  return `<div class="ao-row"><div class="ao-txt"><div class="ao-who">${h(who)}</div><div class="ao-what">${what}</div>
    ${extra ? `<div class="ao-extra">${extra}</div>` : ""}${lock}</div><div class="ao-acts">${btns}</div></div>`;
}

async function _aoRun(i) {
  try { await _ao.actions[i](); } catch (e) { toast(e.message, "error"); }
}

async function _aoPost(url, body) {
  await POST(url, body);
  await _aoReload();
}

function _aoDialog(open) {
  closeModal("modal-alerts-overview");   // dialogen skal ligge øverst
  return open();
}

async function _aoGoto(employeeId) {
  closeModal("modal-alerts-overview");
  setView("employees");
  await loadEmployees();
  openEditEmployee(employeeId);
}

// ── ⚙ Indstillinger (personlige) ────────────────────────────────────────────
async function openAlertSettings() {
  const s = await GET("/api/alerts/settings");
  let el = document.getElementById("modal-alert-settings");
  if (!el) {
    el = document.createElement("div");
    el.id = "modal-alert-settings";
    el.className = "modal-overlay";
    el.innerHTML = `
      <div class="modal" style="width:520px;max-width:95vw">
        <div class="modal-header"><h2>&#9881; Indstillinger for advarsler</h2>
          <button class="modal-close" onclick="closeModal('modal-alert-settings')">&#215;</button></div>
        <div class="modal-body" id="as-body"></div>
        <div class="modal-footer">
          <button class="btn btn-secondary" onclick="closeModal('modal-alert-settings')">Annuller</button>
          <button class="btn btn-primary" id="as-save">Gem</button>
        </div>
      </div>`;
    document.body.appendChild(el);
  }
  const num = (id, v, max) => `<input type="number" id="${id}" min="1" max="${max}" value="${v ?? ""}" style="width:80px">`;
  document.getElementById("as-body").innerHTML = `
    <p style="font-size:13px;color:var(--text-light);margin-bottom:12px">Indstillingerne gælder kun for dig.</p>
    <div class="form-group"><label style="display:flex;gap:8px;align-items:center">
      <input type="checkbox" id="as-auto" ${s.auto_open ? "checked" : ""}>
      Åbn Advarsler automatisk ved start, når der er nye advarsler</label>
      <div style="font-size:12px;color:var(--text-light);margin-top:2px">Slået fra: advarslerne vises kun i &#128276;.</div></div>
    ${s.sections.raises ? `
      <h3 style="font-size:14px;margin-bottom:8px">&#128200; Kommende ændringer i overenskomst</h3>
      <div class="form-group"><label>Første besked (dage før lønperioden med stigningen)</label>${num("as-rn", s.raise_notice_days, 365)}</div>
      <div class="form-group"><label>Påmind igen (dage før) – tom = aldrig</label>${num("as-rr", s.raise_remind_days, 365)}</div>` : ""}
    ${s.sections.other ? `
      <h3 style="font-size:14px;margin:12px 0 8px">&#128276; Øvrige (nye satser, §56, mærkedage)</h3>
      <div class="form-group"><label>Første besked (dage før, højst 30)</label>${num("as-o1", s.other_first_days, 30)}</div>
      <div class="form-group"><label>Anden besked (dage før) – tom = ingen</label>${num("as-o2", s.other_second_days, 30)}</div>
      <div class="form-group"><label style="display:flex;gap:8px;align-items:center">
        <input type="checkbox" id="as-od" ${s.other_on_day ? "checked" : ""}> Besked på dagen</label></div>` : ""}
    ${!s.sections.raises && !s.sections.other ? "<p>Din rolle giver ingen advarsler.</p>" : ""}`;
  const val = (id, fallback) => {
    const input = document.getElementById(id);
    if (!input) return fallback;
    return input.value === "" ? null : parseInt(input.value, 10);
  };
  document.getElementById("as-save").onclick = async () => {
    try {
      await api("PUT", "/api/alerts/settings", {
        raise_notice_days: val("as-rn", s.raise_notice_days),
        raise_remind_days: val("as-rr", s.raise_remind_days),
        other_first_days: val("as-o1", s.other_first_days),
        other_second_days: val("as-o2", s.other_second_days),
        other_on_day: document.getElementById("as-od") ? document.getElementById("as-od").checked : s.other_on_day,
        auto_open: document.getElementById("as-auto").checked,
      });
      toast("Indstillinger gemt");
      closeModal("modal-alert-settings");
      await _aoReload(document.getElementById("modal-alerts-overview")?.classList.contains("open"));
    } catch (e) { toast(e.message, "error"); }
  };
  openModal("modal-alert-settings");
}
