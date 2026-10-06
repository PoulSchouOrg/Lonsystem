// ── Elevløn-trin (2026-10-06) ───────────────────────────────────────────────
// Popups ved trinskift, godkend/behold-dialog, elevoversigt (opstartstjek) og
// advarsel i Lønkørsel. Bruger app.js' hjælpere (GET/POST/api/h/openModal/toast).

const _elevState = { types: [], rateByType: {}, settings: null };

function _elevDk(iso) { return iso ? formatDateShort(iso) : "–"; }
// Datoer skrevet ud i tekst, så de ikke ligner klokkeslæt: "21. september til 4. oktober 2026"
const _DK_MONTHS = ["januar", "februar", "marts", "april", "maj", "juni", "juli", "august",
                    "september", "oktober", "november", "december"];
function dkDate(iso) {
  if (!iso) return "–";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${d}. ${_DK_MONTHS[m - 1]} ${y}`;
}
function dkPeriod(startIso, endIso) {
  const [y1, m1, d1] = startIso.slice(0, 10).split("-").map(Number);
  const y2 = Number(endIso.slice(0, 4));
  return `${d1}. ${_DK_MONTHS[m1 - 1]}${y1 !== y2 ? " " + y1 : ""} til ${dkDate(endIso)}`;
}
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
        <div class="modal-footer" style="flex-wrap:wrap"></div>
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
  const m = _elevModal("modal-elev-alert", titles[a.kind], 600);
  const more = queue.length - i - 1;
  let text = "";
  if (a.kind === "mismatch") {
    text = `<p style="font-size:14px;margin-bottom:8px">${h(a.reason)}</p>
      <p style="font-size:13px;color:var(--text-light)">Forventet: <strong>${h(a.expected_type)}</strong>${_elevRate(a.expected_type)}</p>`;
  } else if (a.kind === "upcoming") {
    text = `<p style="font-size:14px;margin-bottom:8px">${h(a.reason)}</p>
      <p style="font-size:13px;color:var(--text-light)">Foreslået: <strong>${h(a.to_type)}</strong>${_elevRate(a.to_type)}.</p>`;
  } else {
    text = a.took_effect
      ? `<p style="font-size:14px"><strong>${h(a.employee_name)}</strong> har nu <strong>${h(a.to_type)}</strong>${_elevRate(a.to_type)}
         fra lønperioden ${dkPeriod(a.effective_from, a.effective_to)}.</p>`
      : `<p style="font-size:14px">Skiftet for <strong>${h(a.employee_name)}</strong> til <strong>${h(a.to_type)}</strong>
         blev ikke anvendt, fordi overenskomsttypen er ændret manuelt. Tjek medarbejderen.</p>`;
  }
  if (a.claimed_by) {
    text += `<p style="font-size:13px;color:var(--warning);margin-top:8px">&#128274; Behandles af
      <strong>${h(a.claimed_by)}</strong> (siden kl. ${a.claimed_at.slice(11, 16).replace(":", ".")}).</p>`;
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
    if (!a.claimed_by) btn("Behandl", "btn-primary", () => {
      closeModal("modal-elev-alert");
      openElevDecision(a.kind === "mismatch"
        ? { employee_id: a.employee_id, employee_name: a.employee_name, event_date: a.event_date,
            reason: a.reason, from_type: a.current_type, to_type: a.expected_type,
            effective_from: a.suggested_from, locked_periods: a.locked_periods }
        : a, () => { if (i + 1 < queue.length) _elevShowAlert(queue, i + 1); });
    });
  }
  openModal("modal-elev-alert");
}

// ── Godkend / behold-dialog ─────────────────────────────────────────────────
// s: {employee_id, employee_name, event_date, reason, from_type, to_type, effective_from}
async function openElevDecision(s, onDone) {
  try {
    await POST("/api/elev/claim", { employee_id: s.employee_id, event_date: s.event_date });
  } catch (e) {
    toast(e.message, "error");          // fx "Behandles allerede af LB (siden kl. 10.42)"
    if (onDone) onDone();
    return;
  }
  if (!_elevState.types.length) await _elevLoadTypes();
  const m = _elevModal("modal-elev-decision", "Lønstigning: godkend ændring", 560);
  const periods = [0, 14, 28, 42].map(d => _elevAddDays(s.effective_from, d));
  m.body.innerHTML = `
    <p style="font-size:14px;margin-bottom:12px">${h(s.reason || "")}</p>
    ${(s.locked_periods || []).length ? `<div class="alert-banner mb-16"><span class="icon">&#128274;</span><div class="text">
      <h4>Efterregulering</h4>${s.locked_periods.map(b => h(b.text)).join("<br>")}
      <br>Beløbet skal efterreguleres i Danløn. Det skrives i loggen, når du godkender.</div></div>` : ""}
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
        `<option value="${p}">${dkPeriod(p, _elevAddDays(p, 13))}</option>`).join("")}</select></div>
    <div class="form-group"><label>Bemærkning (påkrævet ved "Behold nuværende")</label>
      <textarea id="elev-dec-note" rows="2" style="width:100%"></textarea></div>`;
  m.footer.innerHTML = `
    <button class="btn btn-secondary" id="elev-dec-cancel">Annullér</button>
    <button class="btn btn-warning" id="elev-dec-keep">Behold nuværende</button>
    <button class="btn btn-primary" id="elev-dec-approve">Godkend</button>`;
  const send = async (decision) => {
    const body = {
      kind: s.kind || "elev", employee_id: s.employee_id, event_date: s.event_date, decision,
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
  const release = () => POST("/api/elev/claim/release", { employee_id: s.employee_id, event_date: s.event_date })
    .catch(() => {});
  document.getElementById("elev-dec-cancel").onclick = () => {
    release();
    closeModal("modal-elev-decision");
    if (onDone) onDone();
  };
  m.el.querySelector(".modal-close").onclick = document.getElementById("elev-dec-cancel").onclick;
  m.el._onClose = document.getElementById("elev-dec-cancel").onclick;   // klik udenfor = Annullér (frigiver låsen)
  document.getElementById("elev-dec-keep").onclick = () => send("keep");
  document.getElementById("elev-dec-approve").onclick = () => send("approve");
  openModal("modal-elev-decision");
}

// ── Lønkørsel: mulige fejl ──────────────────────────────────────────────────
function renderElevWarnings(container, warnings) {
  if (!warnings || !warnings.length) return;
  const el = document.createElement("div");
  el.className = "alert-banner mb-16";
  el.innerHTML = `<span class="icon">⚠️</span><div class="text"><h4>Mulig fejl i elevløn (${warnings.length})</h4>
    ${warnings.map(w => h(w.reason) + (w.locked_periods || []).map(l => "<br>&#128274; " + h(l.text)).join("")).join("<br>")}
    <br>Ret eller bevar satsen via "Behandl" i advarslen. Eksporten er ikke blokeret.</div>`;
  container.appendChild(el);
}

// ── Medarbejderformularen: "LB behandler elevløn for denne medarbejder" ──────
async function showElevClaimNote(employeeId) {
  const el = document.getElementById("emp-elev-claim-note");
  if (!el) return;
  el.style.display = "none";
  if (!employeeId) return;
  try {
    const claims = await GET(`/api/elev/claims/${employeeId}`);
    if (!claims.length) return;
    const c = claims[0];
    el.innerHTML = `<span class="icon">&#128274;</span><div class="text">
      <strong>${h(c.initials)}</strong> behandler elevløn for denne medarbejder (siden kl.
      ${c.claimed_at.slice(11, 16).replace(":", ".")}). Vent med at ændre lærekontraktens datoer.</div>`;
    el.style.display = "";
  } catch (e) { /* noten er kun information */ }
}
