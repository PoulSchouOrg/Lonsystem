// ── Fremtidige overenskomstsatser (2026-10-06) ──────────────────────────────
// Stamdata › Overenskomsttyper: boksen "Fremtidige satser" + fælles popup før nye
// satser træder i kraft. Bruger app.js' hjælpere (GET/POST/PATCH/DEL/h/jq/toast).

function _arKr(v) { return v.toFixed(2).replace(".", ",") + " kr"; }

async function loadFutureRates() {
  const tbody = document.getElementById("stamdata-future-rates-tbody");
  if (!tbody) return;
  try {
    const rows = await GET("/api/agreement-rates");
    tbody.innerHTML = rows.length ? rows.map((r, i) => `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
        <td style="padding:10px 14px">${h(r.agreement_type)}</td>
        <td style="padding:10px 14px;text-align:right;font-variant-numeric:tabular-nums">${_arKr(r.hourly_rate)}
          <div style="font-size:12px;color:var(--text-light)">nu ${_arKr(r.current_rate)}</div></td>
        <td style="padding:10px 14px">${dkDate(r.valid_from)}</td>
        <td style="padding:10px 14px;color:var(--text-light)">${h(r.note || "")}</td>
        <td style="padding:10px 14px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px"
                  onclick='openFutureRateModal(${JSON.stringify(r).replace(/'/g, "&#39;")})'>Rediger</button>
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;color:var(--danger);border-color:var(--danger);margin-left:4px"
                  onclick="deleteFutureRate(${r.id}, ${jq(r.agreement_type)}, ${jq(r.valid_from)})">Slet</button>
        </td>
      </tr>`).join("")
      : `<tr><td colspan="5" style="padding:16px;text-align:center;color:var(--text-light)">Ingen fremtidige satser</td></tr>`;
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" style="padding:16px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

async function openFutureRateModal(r) {
  const types = await GET("/api/stamdata/agreement-types");
  let el = document.getElementById("modal-future-rate");
  if (!el) {
    el = document.createElement("div");
    el.id = "modal-future-rate";
    el.className = "modal-overlay";
    el.innerHTML = `
      <div class="modal" style="width:440px;max-width:95vw">
        <div class="modal-header"><h2 id="future-rate-title"></h2>
          <button class="modal-close" onclick="closeModal('modal-future-rate')">&#215;</button></div>
        <div class="modal-body">
          <div class="form-group"><label>Overenskomsttype</label><select id="future-rate-type"></select></div>
          <div class="form-group"><label>Timesats (ny)</label>
            <input type="number" id="future-rate-rate" step="0.01" min="0" placeholder="0.00"></div>
          <div class="form-group"><label>Gælder fra</label><input type="date" id="future-rate-date">
            <div style="font-size:12px;color:var(--text-light);margin-top:4px">
              Ligger datoen inde i en lønperiode, gælder den nye sats hele perioden.</div></div>
          <div class="form-group"><label>Begrundelse (vises i advarslen til lønbogholderen)</label>
            <input type="text" id="future-rate-note" maxlength="300" placeholder="fx Lokal lønaftale 2026"></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" onclick="closeModal('modal-future-rate')">Annuller</button>
          <button class="btn btn-primary" id="future-rate-save">Gem</button>
        </div>
      </div>`;
    document.body.appendChild(el);
  }
  document.getElementById("future-rate-title").textContent = r ? "Rediger fremtidig sats" : "Tilføj fremtidig sats";
  document.getElementById("future-rate-type").innerHTML = types.map(t =>
    `<option value="${t.id}" ${r && r.agreement_type_id === t.id ? "selected" : ""}>${h(t.name)} (nu ${_arKr(t.hourly_rate)})</option>`).join("");
  document.getElementById("future-rate-rate").value = r ? r.hourly_rate : "";
  document.getElementById("future-rate-date").value = r ? r.valid_from : "";
  document.getElementById("future-rate-note").value = r ? (r.note || "") : "";
  document.getElementById("future-rate-save").onclick = async () => {
    const body = {
      agreement_type_id: parseInt(document.getElementById("future-rate-type").value, 10),
      hourly_rate: parseFloat(document.getElementById("future-rate-rate").value),
      valid_from: document.getElementById("future-rate-date").value,
      note: document.getElementById("future-rate-note").value,
    };
    if (isNaN(body.hourly_rate) || !body.valid_from) { toast("Udfyld timesats og dato", "error"); return; }
    try {
      if (r) await PATCH(`/api/agreement-rates/${r.id}`, body);
      else await POST("/api/agreement-rates", body);
      toast("Fremtidig sats gemt");
      closeModal("modal-future-rate");
      await loadStamdataAgreementTypes();
      await loadFutureRates();
    } catch (e) { toast(e.message, "error"); }
  };
  openModal("modal-future-rate");
}

async function deleteFutureRate(id, name, validFrom) {
  if (!confirm(`Slet den fremtidige sats for "${name}" fra ${dkDate(validFrom)}?`)) return;
  try {
    await DEL(`/api/agreement-rates/${id}`);
    toast("Fremtidig sats slettet");
    await loadFutureRates();
  } catch (e) { toast(e.message, "error"); }
}

// ── Popup: nye satser træder snart i kraft ──────────────────────────────────
async function checkRateAlerts() {
  if (!_hasPerm("payroll")) return;
  try {
    const groups = await GET("/api/agreement-rates/alerts");
    if (!groups.length) return;
    const g = groups[0];
    let el = document.getElementById("modal-rate-alert");
    if (!el) {
      el = document.createElement("div");
      el.id = "modal-rate-alert";
      el.className = "modal-overlay";
      el.innerHTML = `
        <div class="modal" style="width:560px;max-width:95vw">
          <div class="modal-header"><h2>&#128176; Nye overenskomstsatser</h2>
            <button class="modal-close" onclick="closeModal('modal-rate-alert')">&#215;</button></div>
          <div class="modal-body" id="rate-alert-body"></div>
          <div class="modal-footer">
            <button class="btn btn-secondary" onclick="closeModal('modal-rate-alert')">Luk</button>
            <button class="btn btn-primary" id="rate-alert-ok">OK</button></div>
        </div>`;
      document.body.appendChild(el);
    }
    document.getElementById("rate-alert-body").innerHTML = `
      <p style="font-size:14px;margin-bottom:8px">Fra <strong>${dkDate(g.valid_from)}</strong> stiger timesatsen for
        følgende overenskomsttyper. Hele lønperioden ${dkPeriod(g.period_start, g.period_end)} får de nye satser.</p>
      ${g.rates.map(r => `
        <div style="border:1px solid var(--border);border-radius:6px;padding:8px 10px;margin-bottom:8px;font-size:13px">
          <strong>${h(r.agreement_type)}</strong>: ${_arKr(r.current_rate)} → <strong>${_arKr(r.new_rate)}</strong>
          ${r.note ? `<div>Begrundelse: ${h(r.note)}</div>` : ""}
          <div style="color:var(--text-light)">${r.employees.length
            ? `Berører ${r.employees.length} medarbejder${r.employees.length === 1 ? "" : "e"}: ${r.employees.map(h).join(", ")}`
            : "Ingen aktive medarbejdere har typen i dag"}</div>
        </div>`).join("")}
      ${groups.length > 1 ? `<p style="font-size:12px;color:var(--text-light);margin-top:8px">+ ${groups.length - 1} flere datoer.</p>` : ""}`;
    document.getElementById("rate-alert-ok").onclick = async () => {
      await POST("/api/agreement-rates/alerts/dismiss", { valid_from: g.valid_from });
      closeModal("modal-rate-alert");
    };
    openModal("modal-rate-alert");
  } catch (e) {
    console.error("Sats-advarsel check fejlede:", e);
  }
}
