// Fælles lønperiode-vælger (2026-10-07, ønsket af lønkontoret).
// Aktiviteter, Lønkørsel, Lønafregning og Fraværsoversigt viser altid samme lønperiode
// (state.currentPeriodStart): skiftes perioden på én fane, følger de andre med.
// Lønafregning og Fraværsoversigt kan skifte til "Vælg datoer" (frit Fra/Til, fx et helt år);
// det gælder indtil "Tilbage til lønperiode" eller til siden genindlæses.

const _RANGE_VIEWS = {
  "payroll-settlement": { from: "settlement-from-dp", to: "settlement-to-dp", notice: "settlement-range-notice",
                          load: () => loadPayrollSettlement() },
  "absence-overview":   { from: "absence-from-dp",    to: "absence-to-dp",    notice: "absence-range-notice",
                          load: () => loadAbsenceOverview() },
};
const _rangeMode = { "payroll-settlement": "period", "absence-overview": "period" };

function _periodText() {
  const p = state.periodInfo?.period;
  if (!p) return "";
  const fmt = iso => new Date(iso + "T00:00:00")
    .toLocaleDateString("da-DK", { day: "numeric", month: "short", year: "numeric" });
  return `${fmt(p.start_date)} – ${fmt(p.end_date)}`;
}

// Kaldes fra renderPeriodBar(), så alle faners periodetekst opdateres samtidig
function renderPeriodSwitches() {
  const text = _periodText();
  document.querySelectorAll("[data-period-label]").forEach(el => { el.textContent = text; });
}

async function movePeriod(direction) {
  const p = state.periodInfo;
  if (!p) return;
  await loadPeriodInfo(direction === "prev" ? p.prev_period_start : p.next_period_start);
  setView(state.currentView);   // genindlæs fanen man står på
}

// Kaldes først i loadPayrollSettlement/loadAbsenceOverview: i lønperiode-tilstand
// sættes Fra/Til altid til den valgte lønperiode.
function usePeriodRange(view) {
  const cfg = _RANGE_VIEWS[view];
  const p = state.periodInfo?.period;
  if (!cfg || _rangeMode[view] !== "period" || !p) return;
  setDatePicker(cfg.from, p.start_date);
  setDatePicker(cfg.to, p.end_date);
}

function setRangeMode(view, mode) {
  if (_rangeMode[view] === mode) return;
  _rangeMode[view] = mode;
  _applyRangeMode(view);
  _RANGE_VIEWS[view].load();
}

function _applyRangeMode(view) {
  const custom = _rangeMode[view] === "custom";
  const root = document.querySelector(`.view[data-view="${view}"]`);
  if (!root) return;
  root.querySelectorAll("[data-range-mode] button").forEach(b =>
    b.classList.toggle("active", b.dataset.mode === _rangeMode[view]));
  root.querySelector("[data-period-switch]")?.classList.toggle("hidden", custom);
  root.querySelector("[data-range-dates]")?.classList.toggle("hidden", !custom);
  document.getElementById(_RANGE_VIEWS[view].notice)?.classList.toggle("hidden", !custom);
}

function initPeriodSwitches() {
  document.addEventListener("click", e => {
    const move = e.target.closest("[data-period-move]");
    if (move) { movePeriod(move.dataset.periodMove); return; }
    const modeBtn = e.target.closest("[data-range-mode] button");
    if (modeBtn) setRangeMode(modeBtn.closest("[data-range-mode]").dataset.rangeMode, modeBtn.dataset.mode);
  });
  Object.entries(_RANGE_VIEWS).forEach(([view, cfg]) => {
    // Valgte datoer vises med det samme (ingen "Opdater" nødvendig)
    [cfg.from, cfg.to].forEach(id =>
      document.getElementById(id)?.querySelector(".dp-val")?.addEventListener("change", () => {
        const from = readDatePicker(cfg.from), to = readDatePicker(cfg.to);
        if (from && to && from <= to) cfg.load();
      }));
    _applyRangeMode(view);
  });
}
