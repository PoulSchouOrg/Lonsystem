/* ── Lønsystem frontend ── */
"use strict";

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
const h = escapeHtml;

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  currentView: "activities",
  currentPeriodStart: null,
  periodInfo: null,
  activities: [],
  employees: [],
  vehicles: [],
  agreementTypes: [],
  agreementKinds: [],
  absenceTypes: [],
  selectedActivityId: null,
  currentUser: null,       // { id, name, initials, role, email, permissions }
  roles: [],               // { id, name, display_name, is_system, permissions[] }
  usersAdminTab: "users",  // aktiv fane i users-admin view
  vehiclesTab: "vognpark", // aktiv fane i Vognpark-view ("vognpark" | "all")
  holidays: [],            // { date: "YYYY-MM-DD", name: string, half_day_from: string|null }
  dispatcherGroups: [],    // { id, name, description }
  positions: [],           // { id, name } – stillinger (Stamdata → Stillinger)
  employeeSort: { key: "name", dir: 1 },  // sortering i medarbejder-tabelvisningen
  autoApprovalEnabled: true, // global til/fra-kontakt, hentet ved app-bootstrap
  vagtplan: {
    weekStart: null,       // ISO date (Monday) of the first of the 4 displayed weeks
    activities: [],
    comments: [],
    groupFilterIds: null,  // null = alle grupper; annet: array of selected dispatcher_group ids
  },
  dagsplan: {
    date: null,
    data: null,
    tab: "plan",
  },
};

const PERMISSION_LABELS = {
  payroll:             "Lønkørsel",
  absence_overview:    "Fraværsoversigt",
  import_ddd:          "Importer .ddd",
  user_management:     "Brugerstyring",
  reopen_period:       "Åbn låst lønperiode",
  stamdata:            "Stamdata",
  view_employees:      "Se medarbejdere",
  manage_employees:    "Tilføj medarbejdere",
  view_vehicles:       "Se vognpark",
  manage_vehicles:     "Tilføj vogn",
  manage_holidays:     "Administrér helligdage",
  anciennitet_alert:   "Anciennitetsvarsel",
  paragraf_56_alert:   "§56-advarsel",
  approve_activities:  "Godkend aktiviteter",
  edit_activities:     "Redigér aktiviteter",
  auto_approve_manual_activities: "Auto-godkend ved oprettelse",
  manage_auto_approval: "Slå auto-godkendelse til/fra",
  view_calendar:       "Se aktivitetskalender",
  manage_employee_supplements: "Administrér medarbejdertillæg",
  toggle_springer:     "Sæt springertillæg",
  toggle_payroll_ready: "Sæt klar til løn",
  vagtplan_view:       "Se vagtplan",
  vagtplan_edit_own:   "Redigér egen linje i vagtplan",
  vagtplan_edit_all:   "Redigér alle linjer i vagtplan",
  payroll_settlement_view:   "Lønafregning (se)",
  payroll_settlement_export: "Lønafregning (eksport)",
  dagsplan_view:       "Se dagsplan",
  dagsplan_edit:       "Redigere dagsplan",
  view_cpr:            "Se CPR-nummer",
  jubilee_alert:       "Jubilæumsadvarsel",
  elev_alert:          "Elevadvarsel",
  elev_wage_approve:   "Godkend elevlønændring",
  birthday_alert:      "Fødselsdagsadvarsel",
  employee_table_view: "Tabelvisning af medarbejdere",
  employee_export:     "Eksportér medarbejderregister",
};

const PERMISSION_DESCRIPTIONS = {
  payroll:             "Adgang til at køre og eksportere lønkørsel (Danløn CSV) for en periode.",
  absence_overview:    "Adgang til fraværsoversigt-fanen, som viser fraværstyper på tværs af medarbejdere.",
  import_ddd:          "Kan importere .ddd-filer (tachograf-data fra chaufførkort/køretøjer).",
  user_management:     "Adgang til Brugerstyring – oprette/redigere brugere og roller.",
  reopen_period:       "Kan genåbne en allerede lukket/afregnet lønperiode.",
  stamdata:            "Adgang til Stamdata-siden (overenskomster, satser, løntypekoder m.m.).",
  view_employees:      "Kan se medarbejderlisten og deres stamdata.",
  manage_employees:    "Kan oprette og redigere medarbejdere.",
  view_vehicles:       "Kan se vognparkens registreringsnumre/vognnumre.",
  manage_vehicles:     "Kan tilføje og redigere køretøjer i vognparken.",
  manage_employee_supplements: "Kan administrere faste tillæg pr. medarbejder.",
  manage_holidays:     "Kan tilføje, redigere og slette helligdage i kalenderen.",
  anciennitet_alert:   "Ser advarsel når en medarbejders anciennitet nærmer sig en løn-relevant grænse (fx sygdom med løn).",
  paragraf_56_alert:   "Ser advarsel om §56-aftaler der kræver opmærksomhed.",
  approve_activities:  "Kan godkende, deaktivere/slette og genåbne aktiviteter, samt bruge knappen \"Autogodkend aktiviteter\".",
  edit_activities:     "Kan oprette aktiviteter/fravær og rette dem (tider, pauser, vognnummer, km, split, ret til andet arbejde) i Aktivitetsoversigten.",
  auto_approve_manual_activities: "Aktiviteter brugeren selv opretter manuelt i aktivitetsoversigten, bliver godkendt automatisk med det samme. Uafhængig af den globale auto-godkendelses-kontakt (Stamdata).",
  manage_auto_approval: "Kan slå den globale auto-godkendelse til/fra i Stamdata. Styrer kun DDD-import og bulk-knappen \"Autogodkend aktiviteter\" (baseret på medarbejderens historiske mønster) – påvirker ikke manuel oprettelse.",
  view_calendar:       "Kan se aktivitetsoversigten/-kalenderen.",
  toggle_springer:     "Kan sætte/fjerne springertillæg-markering på en medarbejders linje.",
  toggle_payroll_ready: "Kan sætte/fjerne \"Klar til løn\"-markering på en medarbejders linje i aktivitetsoversigten (bruges kun til filteret).",
  vagtplan_view:       "Kan se vagtplanen.",
  vagtplan_edit_own:   "Kan redigere egen linje i vagtplanen.",
  vagtplan_edit_all:   "Kan redigere alle medarbejderes linjer i vagtplanen.",
  payroll_settlement_view:   "Kan se lønafregningsoversigten.",
  payroll_settlement_export: "Kan eksportere lønafregningen.",
  dagsplan_view:       "Kan se Dagsplan-siden (vogn-/chauffør-fordeling og materielt fravær), read-only.",
  dagsplan_edit:       "Kan redigere Dagsplan-tildelinger, afkrydse \"informeret\", og melde/fjerne materielt fravær på vogne.",
  view_cpr:            "Kan se hele CPR-nummeret. Uden rettigheden vises de sidste fire cifre som ****.",
  jubilee_alert:       "Får en popup en måned før en medarbejders 25-, 40- og 50-års jubilæum.",
  elev_alert:          "Får en popup en måned før en elevs slutdato.",
  elev_wage_approve:   "Ser elevoversigten, får besked når en elev skifter løntrin, og godkender eller afviser ændringen. Popups kun når rettigheden er sat på rollen.",
  birthday_alert:      "Får en popup en måned før en medarbejders runde fødselsdag (10, 20, 30 …).",
  employee_table_view: "Kan skifte medarbejderregisteret til tabelvisning.",
  employee_export:     "Kan eksportere medarbejderregisterets tabel til Excel.",
};

let manualPauses = [];
let _resizeSegState = null;
let _pauseEditState = null; // { mode: "create"|"activity", idx, activityId? }
let _absenceConflictConfirmed = false;
let _manualActivityContext = { vagtplan: false };

const WEEKDAYS = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"];
const TYPE_LABELS = { normal: "Normal tid" };
const ABSENCE_LABELS = {};  // value → UPPERCASE label for grid badges
const ABSENCE_TYPES = new Set();

// ── API helpers ────────────────────────────────────────────────────────────
async function api(method, path, body = null) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  if (res.status === 401) {
    showLoginOverlay();
    throw new Error("Ikke logget ind");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const msg = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
    const error = new Error(msg);
    error.status = res.status;
    throw error;
  }
  if (res.status === 204) return null;
  return res.json();
}
const GET   = (p)    => api("GET",    p);
const POST  = (p, b) => api("POST",   p, b);
const PATCH = (p, b) => api("PATCH",  p, b);
const DEL   = (p)    => api("DELETE", p);

// downloadFile: kalder et POST-endpoint der returnerer en fil (CSV/Excel/PDF/ZIP)
// og udløser en almindelig browser-download af svaret – i stedet for at bede
// serveren gemme filen et sted på disken (se aftale 2026-09-09: den gamle
// "gem i mappe"-flow gemte fejlagtigt på SERVERENS disk, ikke brugerens).
async function downloadFile(path, body, fallbackFilename) {
  const opts = { method: "POST", headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  if (res.status === 401) {
    showLoginOverlay();
    throw new Error("Ikke logget ind");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const msg = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
    const error = new Error(msg);
    error.status = res.status;
    throw error;
  }
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") || "";
  const match = /filename="?([^";]+)"?/i.exec(cd);
  const filename = match ? match[1] : fallbackFilename;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  return { filename, headers: res.headers };
}
// jq: JSON.stringify der er sikker til brug i onclick="..." HTML-attributter
const jq = x => JSON.stringify(x).replace(/"/g, "&quot;");

// Naturlig sortering af navne med tal: 0, 00, 000, 1, 2 … 10 (ikke 1, 10, 2). Kortest først ved samme talværdi.
const _naturalCollator = new Intl.Collator("da", { numeric: true, sensitivity: "base" });
const naturalCompare = (a, b) => _naturalCollator.compare(a, b) || a.length - b.length || (a < b ? -1 : a > b ? 1 : 0);

// ── UI helpers ─────────────────────────────────────────────────────────────
function toast(msg, type = "info") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById("toast-container").appendChild(el);
  setTimeout(() => el.remove(), 4000);
}
function setLoading(on) {
  document.getElementById("loading-overlay").classList.toggle("open", on);
}
function openModal(id) {
  const modal = document.getElementById(id);
  modal.classList.add("open");
  modal.querySelector(".modal-body")?.scrollTo(0, 0);
}
function closeModal(id) { document.getElementById(id).classList.remove("open"); }
function closeAllModals() {
  document.querySelectorAll(".modal-overlay").forEach(m => m.classList.remove("open"));
}

// ── Navigation ─────────────────────────────────────────────────────────────
const _scrollByView = {};
function setView(view) {
  // Hver fane åbner, hvor man forlod den (lodret scroll-position)
  const scroller = document.querySelector(".main-content");
  if (state.currentView) _scrollByView[state.currentView] = scroller.scrollTop;
  state.currentView = view;
  // Fanen huskes i adressen (#fane), så en genindlæsning bliver på samme fane
  try { history.replaceState(null, "", "#" + view); } catch (_) {}
  document.querySelectorAll(".sidebar-item").forEach(el =>
    el.classList.toggle("active", el.dataset.view === view));
  document.querySelectorAll(".view").forEach(el =>
    el.classList.toggle("hidden", el.dataset.view !== view));

  let loading;
  if (view === "activities")        loading = loadActivities();
  if (view === "employees")         loading = loadEmployees();
  if (view === "payroll")           loading = loadPayrollPreview();
  if (view === "payroll-settlement") loading = loadPayrollSettlement();
  if (view === "absence-overview")  loading = loadAbsenceOverview();
  if (view === "vehicles")          loading = loadVehicles();
  if (view === "employee-supplements") loading = loadEmployeeSupplementsView();
  if (view === "users-admin")       loading = loadUsersAdminView();
  if (view === "stamdata")          loading = loadStamdata();
  if (view === "vagtplan")          loading = loadVagtplan();
  if (view === "dagsplan")          loading = loadDagsplan();
  Promise.resolve(loading).finally(() => { scroller.scrollTop = _scrollByView[view] || 0; });
}

const DAYS_PER_VAGTPLAN_VIEW = 21; // 3 uger: forrige, nuværende, næste

function _mondayOf(d) {
  const copy = new Date(d);
  const dow = (copy.getDay() + 6) % 7; // 0=Mandag
  copy.setDate(copy.getDate() - dow);
  return copy;
}

// Default-vindue: ugen før den nuværende, så nuværende uge lander i midten af
// de 3 viste uger (forrige/nuværende/næste).
function _vagtplanDefaultWeekStart() {
  const monday = _mondayOf(new Date());
  monday.setDate(monday.getDate() - 7);
  return monday;
}

function _isoOfDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function _vagtplanDays() {
  const start = new Date(state.vagtplan.weekStart + "T00:00:00");
  const days = [];
  for (let i = 0; i < DAYS_PER_VAGTPLAN_VIEW; i++) {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    days.push(d);
  }
  return days;
}

async function loadVagtplan() {
  if (!state.vagtplan.weekStart) {
    state.vagtplan.weekStart = _isoOfDate(_vagtplanDefaultWeekStart());
  }
  setLoading(true);
  try {
    const days = _vagtplanDays();
    const dateFrom = _isoOfDate(days[0]);
    const dateTo = _isoOfDate(days[days.length - 1]);
    const [activities, comments] = await Promise.all([
      GET(`/api/activities?date_from=${dateFrom}&date_to=${dateTo}`),
      GET(`/api/vagtplan-comments?date_from=${dateFrom}&date_to=${dateTo}`),
      loadHolidaysForPeriod(dateFrom, dateTo),
    ]);
    state.vagtplan.activities = activities.filter(a => a.activity_type !== "normal" && !a.hidden_from_vagtplan);
    state.vagtplan.comments = comments;
    fillVagtplanGroupFilter();
    fillVagtplanEmployeeFilter();
    renderVagtplanTable();
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

function navigateVagtplan(direction) {
  const start = new Date(state.vagtplan.weekStart + "T00:00:00");
  start.setDate(start.getDate() + (direction === "prev" ? -7 : 7));
  state.vagtplan.weekStart = _isoOfDate(start);
  loadVagtplan();
}

function jumpToVagtplanToday() {
  state.vagtplan.weekStart = _isoOfDate(_vagtplanDefaultWeekStart());
  loadVagtplan();
}

// Valgt dato fra kalenderen: ugen der indeholder datoen bliver den FØRSTE af de 3 viste uger.
function jumpToVagtplanDate(dateIso) {
  state.vagtplan.weekStart = _isoOfDate(_mondayOf(new Date(dateIso + "T00:00:00")));
  loadVagtplan();
}

// 📅-knappen åbner systemets egen kalender med ugenummer-kolonne (browserens
// datovælger kan ikke vise ugenumre). Klik på en dato eller et ugenummer → den uge
// bliver den første af de 3 viste.
function _initVagtplanCalendar() {
  const btn = document.getElementById("btn-vagtplan-calendar");
  buildDatePicker("vagtplan-date-picker", "", { weeks: true });
  const wrap = document.getElementById("vagtplan-date-picker");
  wrap.style.cssText = "position:relative;display:inline-block;margin-left:8px;";
  const display = wrap.querySelector(".dp-display");
  display.style.display = "none";
  wrap.prepend(btn);
  btn.addEventListener("click", e => {
    e.stopPropagation();
    const iso = state.vagtplan.weekStart || _isoOfDate(new Date());
    wrap.querySelector(".dp-val").value = iso;
    wrap.querySelector(".dp-year-sel").value = parseInt(iso.slice(0, 4), 10);
    wrap.querySelector(".dp-month-sel").value = parseInt(iso.slice(5, 7), 10) - 1;
    _dpRenderGrid(wrap, parseInt(iso.slice(0, 4), 10), parseInt(iso.slice(5, 7), 10) - 1,
                  parseInt(iso.slice(0, 4), 10), parseInt(iso.slice(5, 7), 10) - 1, parseInt(iso.slice(8, 10), 10));
    display.click();
  });
  wrap.querySelector(".dp-val").addEventListener("change", e => {
    if (e.target.value) jumpToVagtplanDate(e.target.value);
  });
}

async function openVagtplanCommentModal(commentId) {
  const c = state.vagtplan.comments.find(x => x.id === commentId);
  if (!c) return;
  const emp = state.employees.find(e => e.id === c.employee_id);
  document.getElementById("vagtplan-comment-id").value = c.id;
  document.getElementById("vagtplan-comment-info").textContent =
    `${emp ? emp.name : "Ukendt medarbejder"} – ${formatDate(c.date)}`;
  document.getElementById("vagtplan-comment-text").value = c.text;
  const seriesEl = document.getElementById("vagtplan-comment-series");
  seriesEl.innerHTML = "";
  openModal("modal-vagtplan-comment");
  if (c.series_id) {
    try {
      const series = await GET(`/api/vagtplan-series/${c.series_id}`);
      seriesEl.innerHTML = _renderSeriesSection(series, c.date, _hasVagtplanEditAccess(emp));
    } catch (e) { /* serien kunne ikke hentes – sektionen udelades */ }
  }
}

async function confirmVagtplanComment() {
  const id = document.getElementById("vagtplan-comment-id").value;
  const c = state.vagtplan.comments.find(x => x.id === parseInt(id));
  if (!c) return;
  const text = document.getElementById("vagtplan-comment-text").value.trim();
  if (!text) { toast("Skriv en kommentar", "error"); return; }
  try {
    await POST("/api/vagtplan-comments", { employee_id: c.employee_id, date: c.date, text });
    toast("Kommentar opdateret", "success");
    closeModal("modal-vagtplan-comment");
    await loadVagtplan();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteVagtplanComment() {
  const id = document.getElementById("vagtplan-comment-id").value;
  if (!id) return;
  try {
    await DEL(`/api/vagtplan-comments/${id}`);
    toast("Kommentar slettet", "success");
    closeModal("modal-vagtplan-comment");
    await loadVagtplan();
  } catch (e) { toast(e.message, "error"); }
}

async function openVagtplanTomorrowModal() {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  while (tomorrow.getDay() === 0 || tomorrow.getDay() === 6) {
    tomorrow.setDate(tomorrow.getDate() + 1);
  }
  const iso = _isoOfDate(tomorrow);

  document.getElementById("vagtplan-tomorrow-title").textContent =
    `Fravær i morgen – ${tomorrow.toLocaleDateString("da-DK", { day: "numeric", month: "short", year: "numeric" })}`;

  // Samme filtre som selve griddet (disponentgruppe + medarbejder), så modalen kun
  // viser de medarbejdere brugeren aktuelt har valgt at se.
  const empFilter = document.getElementById("vagtplan-filter-employee")?.value || "";
  const groupIds = state.vagtplan.groupFilterIds; // null = alle
  let visibleEmps = state.employees.filter(e => e.active);
  if (groupIds) visibleEmps = visibleEmps.filter(e => e.dispatcher_group && groupIds.includes(e.dispatcher_group.id));
  if (empFilter) visibleEmps = visibleEmps.filter(e => e.id === parseInt(empFilter));
  visibleEmps = visibleEmps.filter(_matchesVagtplanSearch);
  const visibleEmpIds = new Set(visibleEmps.map(e => e.id));

  let activities = [], comments = [];
  try {
    [activities, comments] = await Promise.all([
      GET(`/api/activities?date_from=${iso}&date_to=${iso}`),
      GET(`/api/vagtplan-comments?date_from=${iso}&date_to=${iso}`),
    ]);
  } catch (e) { toast(e.message, "error"); return; }
  activities = activities.filter(a => a.activity_type !== "normal" && !a.hidden_from_vagtplan && visibleEmpIds.has(a.employee_id));
  comments = comments.filter(c => visibleEmpIds.has(c.employee_id));

  const rows = [];
  for (const a of activities) {
    rows.push({ name: a.employee_name, text: ABSENCE_LABELS[a.activity_type] || a.activity_type });
  }
  for (const c of comments) {
    const emp = state.employees.find(e => e.id === c.employee_id);
    if (emp) rows.push({ name: emp.name, text: c.text });
  }
  rows.sort((x, y) => x.name.localeCompare(y.name, "da"));

  const body = document.getElementById("vagtplan-tomorrow-body");
  body.innerHTML = rows.length === 0
    ? `<tr><td colspan="2" style="padding:16px 4px;color:var(--text-light)">Ingen fravær eller kommentarer registreret i morgen</td></tr>`
    : rows.map(r => `<tr><td style="padding:6px 4px;border-bottom:1px solid var(--border)">${h(r.name)}</td><td style="padding:6px 4px;border-bottom:1px solid var(--border)">${h(r.text)}</td></tr>`).join("");

  openModal("modal-vagtplan-tomorrow");
}

// Spejler backend (_has_vagtplan_edit_access): 'alle linjer', eller 'egen linje' når
// medarbejderens initialer matcher den indloggede brugers. Tjekkes før opret-modalen
// åbnes, så fejlen ikke først kommer ved "Opret".
function _hasVagtplanEditAccess(emp) {
  if (_hasPerm("vagtplan_edit_all")) return true;
  if (!emp || !_hasPerm("vagtplan_edit_own")) return false;
  const own = (state.currentUser?.initials || "").trim().toLowerCase();
  return !!emp.initials && emp.initials.trim().toLowerCase() === own;
}

// Søgefeltet i Vagtplan: del af navn eller lønnr. (gælder sammen med de øvrige filtre).
function _matchesVagtplanSearch(emp) {
  const query = (document.getElementById("vagtplan-search")?.value || "").toLowerCase().trim();
  if (!query) return true;
  return emp.name.toLowerCase().includes(query) || String(emp.employee_number).toLowerCase().includes(query);
}

function renderVagtplanTable() {
  const days = _vagtplanDays();
  const empFilter = document.getElementById("vagtplan-filter-employee")?.value || "";
  const groupIds = state.vagtplan.groupFilterIds; // null = alle

  const fmt = d => new Date(d).toLocaleDateString("da-DK", { day: "numeric", month: "short", year: "numeric" });
  document.getElementById("vagtplan-period-label").textContent =
    `${fmt(days[0])} – ${fmt(days[days.length - 1])}`;

  // Header: uge-nummer-række (7 kolonner pr. uge) + dag-række
  const head = document.getElementById("vagtplan-grid-head");
  let weekRow = `<th></th>`;
  for (let w = 0; w < DAYS_PER_VAGTPLAN_VIEW / 7; w++) {
    weekRow += `<th colspan="7" style="text-align:center">Uge ${isoWeekNumber(days[w * 7])}</th>`;
  }
  const todayIso = _isoOfDate(new Date());
  let dayRow = `<th>Chauffør</th>` + days.map(d => {
    const iso = _isoOfDate(d);
    const cls = iso === todayIso ? "today" : "";
    // Helligdage markeres som i Aktivitetsoversigten (renderActivitiesTable).
    const hol  = state.holidays.find(x => x.date === iso);
    const bg   = hol ? (cls === "today" ? `background:#056a10;border-bottom:3px solid var(--accent);` : `background:#056a10;`) : "";
    const half = hol?.half_day_from
      ? `<span style="font-size:10px;display:block;color:#fff;margin-top:1px">½ fra ${hol.half_day_from}</span>`
      : "";
    const tip  = hol ? `title="${h(hol.name)}"` : "";
    return `<th class="${cls}" style="${bg}" ${tip}>
      <span class="day-name">${DAY_NAMES[(d.getDay() + 6) % 7]}</span>
      <span class="day-date">${String(d.getDate()).padStart(2, "0")}-${String(d.getMonth() + 1).padStart(2, "0")}</span>
      ${half}
    </th>`;
  }).join("");
  head.innerHTML = `<tr>${weekRow}</tr><tr>${dayRow}</tr>`;
  // Begge header-rækker er sticky: datorækken placeres lige under ugenummer-rækken,
  // så ugenummeret også bliver stående ved scroll.
  const weekRowHeight = head.rows[0].getBoundingClientRect().height;
  head.style.setProperty("--vagtplan-week-row-h", `${weekRowHeight}px`);

  // Gruppér: employee_id -> dato-ISO -> { activities: [...], comment: {...}|null }
  const byEmpDay = {};
  for (const a of state.vagtplan.activities) {
    const iso = a.start_time.slice(0, 10);
    ((byEmpDay[a.employee_id] ??= {})[iso] ??= { activities: [], comment: null }).activities.push(a);
  }
  for (const c of state.vagtplan.comments) {
    const entry = (byEmpDay[c.employee_id] ??= {})[c.date] ??= { activities: [], comment: null };
    entry.comment = c;
  }

  let emps = state.employees.filter(e => e.active);
  if (groupIds) emps = emps.filter(e => e.dispatcher_group && groupIds.includes(e.dispatcher_group.id));
  if (empFilter) emps = emps.filter(e => e.id === parseInt(empFilter));
  emps = emps.filter(_matchesVagtplanSearch);
  emps.sort((x, y) => x.name.localeCompare(y.name, "da"));

  const body = document.getElementById("vagtplan-grid-body");
  if (emps.length === 0) {
    body.innerHTML = `<tr><td colspan="${DAYS_PER_VAGTPLAN_VIEW + 1}" class="empty-state"><div class="icon">📋</div><h3>Ingen medarbejdere</h3></td></tr>`;
    return;
  }

  body.innerHTML = "";
  for (const emp of emps) {
    let cells = `<td class="emp-cell${empCellHighlight(emp)}" title="${h(emp.name)} (lønnr. ${h(emp.employee_number)})">${h(emp.name)}</td>`;
    for (const d of days) {
      const iso = _isoOfDate(d);
      const entry = byEmpDay[emp.id]?.[iso];
      const weekend = d.getDay() === 0 || d.getDay() === 6;
      const badges = (entry?.activities || []).map(a => renderCellActivity(a, "full")).join("");
      const commentHtml = entry?.comment
        ? `<span class="vagtplan-comment-text" data-comment-id="${entry.comment.id}" title="${h(entry.comment.text)}">${h(entry.comment.text)}</span>`
        : "";
      cells += `<td class="${weekend ? "weekend" : ""}" data-emp-id="${emp.id}" data-date="${iso}">${badges}${commentHtml}</td>`;
    }
    const tr = document.createElement("tr");
    tr.innerHTML = cells;
    body.appendChild(tr);
  }

  body.querySelectorAll(".time-badge").forEach(el => {
    el.addEventListener("click", () => openActivityDetail(parseInt(el.dataset.id)));
  });
  body.querySelectorAll(".vagtplan-comment-text").forEach(el => {
    el.addEventListener("click", e => {
      e.stopPropagation();
      openVagtplanCommentModal(parseInt(el.dataset.commentId));
    });
  });
  body.querySelectorAll("td[data-emp-id]").forEach(td => {
    td.addEventListener("click", e => {
      if (e.target.closest(".time-badge") || e.target.closest(".vagtplan-comment-text")) return;
      const emp = state.employees.find(x => x.id === parseInt(td.dataset.empId));
      if (!_hasVagtplanEditAccess(emp)) {
        toast("Ingen redigeringsret til Vagtplan for denne medarbejder", "error");
        return;
      }
      openManualActivityModal(parseInt(td.dataset.empId), td.dataset.date, { vagtplan: true });
    });
  });
}

// ── Dagsplan ─────────────────────────────────────────────────────────────
const _canEditDagsplan = () => state.currentUser?.permissions?.includes("dagsplan_edit");

function switchDagsplanTab(tab) {
  state.dagsplan.tab = tab;
  document.getElementById("ds-pane-plan").style.display = tab === "plan" ? "" : "none";
  document.getElementById("ds-pane-absence").style.display = tab === "absence" ? "" : "none";
  const planBtn = document.getElementById("ds-tab-plan");
  const absBtn = document.getElementById("ds-tab-absence");
  planBtn.style.borderBottomColor = tab === "plan" ? "var(--primary)" : "transparent";
  planBtn.style.color = tab === "plan" ? "var(--primary)" : "var(--text-light)";
  absBtn.style.borderBottomColor = tab === "absence" ? "var(--primary)" : "transparent";
  absBtn.style.color = tab === "absence" ? "var(--primary)" : "var(--text-light)";
  if (tab === "absence") loadDagsplanAbsences();
}

function fillDagsplanFilters() {
  const groupSel = document.getElementById("dagsplan-filter-dispatcher-group");
  if (groupSel) {
    const current = groupSel.value;
    groupSel.innerHTML = `<option value="">Alle afdelinger</option>` + state.dispatcherGroups
      .map(g => `<option value="${g.id}">${h(g.name)}</option>`).join("");
    groupSel.value = current;
  }
  const empSel = document.getElementById("dagsplan-filter-employee");
  if (empSel) {
    const current = empSel.value;
    empSel.innerHTML = `<option value="">Alle medarbejdere</option>` + state.employees
      .filter(e => e.active).sort((a, b) => a.name.localeCompare(b.name, "da"))
      .map(e => `<option value="${e.id}">${h(e.name)}</option>`).join("");
    empSel.value = current;
  }
}

async function loadDagsplan() {
  if (!state.dagsplan.date) state.dagsplan.date = _isoOfDate(new Date());
  if (!state.vehicles.length) { try { state.vehicles = await GET("/api/vehicles"); } catch (_) {} }
  if (!state.dispatcherGroups.length) { try { state.dispatcherGroups = await GET("/api/employees/dispatcher-groups"); } catch (_) {} }
  fillDagsplanFilters();
  await _refreshDagsplanData();
  if (state.dagsplan.tab === "absence") await loadDagsplanAbsences();
}

async function _refreshDagsplanData() {
  setDatePicker("dagsplan-date-picker", state.dagsplan.date);
  document.getElementById("dagsplan-title").textContent =
    `Dagsplan – d. ${formatDate(state.dagsplan.date + "T00:00:00")}`;
  setLoading(true);
  try {
    const groupId = document.getElementById("dagsplan-filter-dispatcher-group")?.value || "";
    const empId = document.getElementById("dagsplan-filter-employee")?.value || "";
    const qs = new URLSearchParams({ date: state.dagsplan.date });
    if (groupId) qs.set("dispatcher_group_id", groupId);
    if (empId) qs.set("employee_id", empId);
    state.dagsplan.data = await GET(`/api/dagsplan?${qs.toString()}`);
    renderDagsplanMain();
    renderDagsplanEmployees();
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

function navigateDagsplan(deltaDays) {
  const d = new Date(state.dagsplan.date + "T00:00:00");
  d.setDate(d.getDate() + deltaDays);
  state.dagsplan.date = _isoOfDate(d);
  loadDagsplan();
}

function jumpToDagsplanToday() {
  state.dagsplan.date = _isoOfDate(new Date());
  loadDagsplan();
}

function renderDagsplanMain() {
  const body = document.getElementById("dagsplan-main-body");
  const canEdit = _canEditDagsplan();
  const rows = state.dagsplan.data?.vehicles || [];

  const vehicleRowClass = v => {
    if (v.absent) return "dagsplan-vehicle-absent"; // vognen selv er materielt fraværende - højeste prioritet
    if (!v.employee_id) return "dagsplan-vehicle-none";
    const empStatus = state.dagsplan.data?.employees?.find(e => e.employee_id === v.employee_id)?.status;
    // Chaufførens farve i tabel 2 skal afspejles her (samme forrang: gul > rød > grøn).
    // En Fast-bil-chauffør med fravær skrives stadig på sin faste vogn, men rødt.
    if (empStatus === "comment_only") return "dagsplan-vehicle-comment-only";
    if (empStatus === "absent") return "dagsplan-vehicle-absent";
    return "dagsplan-vehicle-assigned";
  };
  let html = rows.map(v => `
    <tr data-vehicle-id="${v.vehicle_id}" class="${vehicleRowClass(v)}">
      <td>${h(v.vehicle_number)}</td>
      <td>${h(v.description || "")}</td>
      <td>
        <div style="position:relative;display:flex;align-items:center;gap:4px">
          <input type="text" class="ds-chauffeur-input" data-vehicle-id="${v.vehicle_id}"
                 value="${h(v.employee_name || "")}" autocomplete="off" ${canEdit ? "" : "disabled"}
                 placeholder="Vælg chauffør…" style="width:100%;padding:4px 6px">
          ${v.mismatch_vehicle_number ? `<span title="vognnummer i løn: ${h(v.mismatch_vehicle_number)}" style="color:var(--warning)">&#9888;</span>` : ""}
        </div>
      </td>
      <td><input type="text" class="ds-task-input" data-vehicle-id="${v.vehicle_id}" value="${h(v.task || "")}" ${canEdit ? "" : "disabled"} style="width:100%;padding:4px 6px"></td>
      <td style="text-align:center"><input type="checkbox" class="ds-informed-input" data-vehicle-id="${v.vehicle_id}" ${v.informed ? "checked" : ""} ${canEdit ? "" : "disabled"}></td>
    </tr>`).join("");

  // Samme farvelogik som de rigtige vogne ovenfor - blot uden "absent"
  // (materielt fravær giver ikke mening for en EKSTRA-plads, som ikke er en rigtig vogn).
  const extraRowClass = row => {
    if (!row.employee_id) return "dagsplan-vehicle-none";
    const empStatus = state.dagsplan.data?.employees?.find(e => e.employee_id === row.employee_id)?.status;
    if (empStatus === "comment_only") return "dagsplan-vehicle-comment-only";
    if (empStatus === "absent") return "dagsplan-vehicle-absent";
    return "dagsplan-vehicle-assigned";
  };
  const extraRows = state.dagsplan.data?.extra_rows || [];
  html += extraRows.map(row => `
    <tr data-extra-idx="${row.slot}" class="${extraRowClass(row)}">
      <td>EKSTRA</td>
      <td></td>
      <td>
        <input type="text" class="ds-chauffeur-input" data-extra-idx="${row.slot}"
               value="${h(row.employee_name || "")}" autocomplete="off" ${canEdit ? "" : "disabled"}
               placeholder="Vælg chauffør…" style="width:100%;padding:4px 6px">
      </td>
      <td><input type="text" class="ds-task-input" data-extra-idx="${row.slot}" value="${h(row.task || "")}" ${canEdit ? "" : "disabled"} style="width:100%;padding:4px 6px"></td>
      <td style="text-align:center"><input type="checkbox" class="ds-informed-input" data-extra-idx="${row.slot}" ${row.informed ? "checked" : ""} ${canEdit ? "" : "disabled"}></td>
    </tr>`).join("");

  body.innerHTML = html || `<tr><td colspan="5" class="empty-state"><div class="icon">🚛</div><h3>Ingen vogne</h3></td></tr>`;

  body.querySelectorAll(".ds-chauffeur-input").forEach(el => {
    el.addEventListener("focus", () => _renderDagsplanChauffeurResults(el));
    el.addEventListener("input", () => _renderDagsplanChauffeurResults(el));
    el.addEventListener("blur", () => {
      // Et klik på et forslag i dropdownen udløser allerede sit eget gem
      // (via mousedown, som forhindrer denne blur i at ske for det tilfælde).
      // Denne håndterer i stedet: feltet slettet uden at vælge "— Ingen —"
      // (skal tælle som at fjerne chaufføren), eller et fuldt navn skrevet
      // uden at klikke i listen (skal stadig gemmes hvis det matcher præcist).
      const val = el.value.trim();
      if (val === "") {
        _saveDagsplanRow(el.dataset, null);
        return;
      }
      const match = state.employees.find(e => e.active && e.name.toLowerCase() === val.toLowerCase());
      if (match) {
        _saveDagsplanRow(el.dataset, match.id);
      } else {
        renderDagsplanMain(); // ufuldstændig/ugyldig indtastning - gendan den gemte værdi
      }
    });
  });
  body.querySelectorAll(".ds-task-input").forEach(el => {
    el.addEventListener("blur", () => _saveDagsplanRow(el.dataset));
  });
  body.querySelectorAll(".ds-informed-input").forEach(el => {
    el.addEventListener("change", () => _saveDagsplanRow(el.dataset));
  });
}

function _renderDagsplanChauffeurResults(inputEl) {
  const dropdown = document.getElementById("dagsplan-chauffeur-dropdown");
  const q = inputEl.value.toLowerCase().trim();
  const matches = state.employees.filter(e => e.active && (!q || e.name.toLowerCase().includes(q)))
    .sort((a, b) => a.name.localeCompare(b.name, "da"));
  const noneRow = `<div class="ds-chauffeur-item" data-id="" data-name="" style="padding:8px 10px;cursor:pointer;font-size:13px;color:var(--text-light)">— Ingen —</div>`;
  const rows = matches.map(e => `<div class="ds-chauffeur-item" data-id="${e.id}" data-name="${h(e.name)}" style="padding:8px 10px;cursor:pointer;font-size:13px">${h(e.name)}</div>`).join("");
  dropdown.innerHTML = noneRow + (rows || `<div style="padding:8px 10px;color:var(--text-light);font-size:13px">Ingen medarbejdere fundet</div>`);
  // position:fixed - rect er allerede i viewport-koordinater, som fixed
  // positionering bruger direkte. Ingen scrollX/scrollY-tillæg (det ville
  // kun være korrekt for position:absolute), og ingen afhængighed af den
  // positionerede forælders egen scroll-tilstand (som ellers giver en
  // helt forkert placering, når tabellen selv scroller internt).
  const rect = inputEl.getBoundingClientRect();
  const dropdownHeight = 220; // matcher max-height i CSS'en
  const opensUpward = rect.bottom + dropdownHeight > window.innerHeight && rect.top > dropdownHeight;
  dropdown.style.left = `${rect.left}px`;
  dropdown.style.top = opensUpward ? "" : `${rect.bottom}px`;
  dropdown.style.bottom = opensUpward ? `${window.innerHeight - rect.top}px` : "";
  dropdown.style.width = `${rect.width}px`;
  dropdown.style.display = "block";
  dropdown.querySelectorAll(".ds-chauffeur-item").forEach(el => {
    el.addEventListener("mouseover", () => el.style.background = "var(--bg)");
    el.addEventListener("mouseout", () => el.style.background = "");
    el.addEventListener("mousedown", (e) => {
      e.preventDefault(); // undgå at inputtets blur lukker dropdownen før klikket når frem
      inputEl.value = el.dataset.name;
      dropdown.style.display = "none";
      _saveDagsplanRow(inputEl.dataset, el.dataset.id ? parseInt(el.dataset.id) : null);
    });
  });
}

document.addEventListener("click", (e) => {
  if (!e.target.closest("#dagsplan-chauffeur-dropdown, .ds-chauffeur-input")) {
    const dropdown = document.getElementById("dagsplan-chauffeur-dropdown");
    if (dropdown) dropdown.style.display = "none";
  }
});

async function _saveDagsplanRow(dataset, explicitEmployeeId) {
  const isExtra = dataset.extraIdx !== undefined;
  const endpoint = isExtra ? "/api/dagsplan/extra-assignment" : "/api/dagsplan/assignment";
  const row = document.querySelector(
    isExtra ? `tr[data-extra-idx="${dataset.extraIdx}"]` : `tr[data-vehicle-id="${dataset.vehicleId}"]`
  );
  const currentEmployeeId = isExtra
    ? (state.dagsplan.data?.extra_rows?.find(r => r.slot === parseInt(dataset.extraIdx))?.employee_id ?? null)
    : (state.dagsplan.data?.vehicles?.find(v => v.vehicle_id === parseInt(dataset.vehicleId))?.employee_id ?? null);
  const employeeId = explicitEmployeeId !== undefined ? explicitEmployeeId : currentEmployeeId;
  const body = {
    date: state.dagsplan.date,
    employee_id: employeeId,
    task: row.querySelector(".ds-task-input").value || null,
    informed: row.querySelector(".ds-informed-input").checked,
    ...(isExtra ? { slot: parseInt(dataset.extraIdx) } : { vehicle_id: parseInt(dataset.vehicleId) }),
  };
  try {
    await PATCH(endpoint, body);
    await _refreshDagsplanData();
  } catch (e) {
    if (e.status === 409) {
      if (window.confirm(e.message)) {
        try {
          await PATCH(endpoint, { ...body, force: true });
          await _refreshDagsplanData();
          return;
        } catch (e2) { toast(e2.message, "error"); return; }
      }
      renderDagsplanMain(); // fortryd - gendan feltets oprindelige værdi
      renderDagsplanEmployees();
      return;
    }
    toast(e.message, "error");
  }
}

function renderDagsplanEmployees() {
  const body = document.getElementById("dagsplan-employees-body");
  const rows = state.dagsplan.data?.employees || [];
  const classFor = status => ({
    assigned: "dagsplan-emp-assigned",
    absent: "dagsplan-emp-absent",
    comment_only: "dagsplan-emp-comment-only",
    none: "dagsplan-emp-none",
  }[status] || "");
  // EKSTRA-tildelinger (og "Fast bil"/rigtige vogne) er allerede indregnet i
  // e.status af serveren (get_dagsplan) - ingen klient-side farvelogik nødvendig her.
  body.innerHTML = rows.map(e => `
    <tr class="${classFor(e.status)}">
      <td>${h(e.employee_name)}</td>
      <td>${e.absence_text ? h(TYPE_LABELS[e.absence_text] || e.absence_text) : ""}</td>
    </tr>`).join("") || `<tr><td colspan="2" class="empty-state"><div class="icon">👤</div><h3>Ingen medarbejdere</h3></td></tr>`;
}

async function loadDagsplanAbsences() {
  try {
    const list = await GET(`/api/vehicle-absences?date=${state.dagsplan.date}`);
    renderDagsplanAbsences(list);
  } catch (e) { toast(e.message, "error"); }
}

function renderDagsplanAbsences(list) {
  const body = document.getElementById("dagsplan-absence-body");
  const canEdit = _canEditDagsplan();
  body.innerHTML = list.map(a => `
    <tr>
      <td>${h(a.vehicle_number)}</td>
      <td>${formatDate(a.date_from + "T00:00:00")}${a.date_to ? " – " + formatDate(a.date_to + "T00:00:00") : ""}</td>
      <td>${h(a.comment)}</td>
      <td>${canEdit ? `<button class="btn btn-danger btn-sm" onclick="deleteVehicleAbsence(${a.id})">Slet</button>` : ""}</td>
    </tr>`).join("") || `<tr><td colspan="4" class="empty-state"><div class="icon">🚛</div><h3>Intet meldt fravær</h3></td></tr>`;
}

function openReportVehicleAbsenceModal() {
  document.getElementById("va-vehicle-search").value = "";
  document.getElementById("va-vehicle-id").value = "";
  document.getElementById("va-vehicle-dropdown").style.display = "none";
  buildDatePicker("va-date-from", state.dagsplan.date);
  buildDatePicker("va-date-to", "");
  document.getElementById("va-comment").value = "";
  openModal("modal-vehicle-absence");
}

function _renderVaVehicleSearchResults(query) {
  const dropdown = document.getElementById("va-vehicle-dropdown");
  const q = query.trim().toUpperCase();
  const matches = state.vehicles.filter(v =>
    v.vehicle_number.toUpperCase().includes(q) || v.registration_number.toUpperCase().includes(q));
  dropdown.innerHTML = matches.map(v => `
    <div class="va-vehicle-item" data-id="${v.id}" data-num="${h(v.vehicle_number)}" style="padding:8px 10px;cursor:pointer;font-size:13px">
      ${h(v.vehicle_number)} <span style="color:var(--text-light)">– ${h(v.registration_number)}</span>
    </div>`).join("") || `<div style="padding:8px 10px;color:var(--text-light);font-size:13px">Ingen køretøjer fundet</div>`;
  dropdown.querySelectorAll(".va-vehicle-item").forEach(el => {
    el.addEventListener("mouseover", () => el.style.background = "var(--bg)");
    el.addEventListener("mouseout", () => el.style.background = "");
    el.addEventListener("click", () => {
      document.getElementById("va-vehicle-search").value = el.dataset.num;
      document.getElementById("va-vehicle-id").value = el.dataset.id;
      dropdown.style.display = "none";
    });
  });
  dropdown.style.display = "block";
}
document.getElementById("va-vehicle-search")?.addEventListener("input", function () { _renderVaVehicleSearchResults(this.value); });
document.getElementById("va-vehicle-search")?.addEventListener("focus", function () { _renderVaVehicleSearchResults(this.value); });
document.addEventListener("click", (e) => {
  if (!e.target.closest("#va-vehicle-search, #va-vehicle-dropdown")) {
    const dropdown = document.getElementById("va-vehicle-dropdown");
    if (dropdown) dropdown.style.display = "none";
  }
});

async function confirmVehicleAbsence() {
  const vehicleId = document.getElementById("va-vehicle-id").value;
  const dateFrom = readDatePicker("va-date-from");
  const dateTo = readDatePicker("va-date-to");
  const comment = document.getElementById("va-comment").value.trim();
  if (!vehicleId) { toast("Vælg en vogn", "error"); return; }
  if (!dateFrom) { toast("Angiv fra-dato", "error"); return; }
  if (!comment) { toast("Angiv en kommentar", "error"); return; }
  try {
    await POST("/api/vehicle-absences", {
      vehicle_id: parseInt(vehicleId), date_from: dateFrom, date_to: dateTo || null, comment,
    });
    toast("Materielt fravær meldt", "success");
    closeModal("modal-vehicle-absence");
    await loadDagsplanAbsences();
    await _refreshDagsplanData();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteVehicleAbsence(id) {
  try {
    await DEL(`/api/vehicle-absences/${id}`);
    toast("Fravær fjernet", "success");
    await loadDagsplanAbsences();
    await _refreshDagsplanData();
  } catch (e) { toast(e.message, "error"); }
}

// ── Period navigation ──────────────────────────────────────────────────────
async function loadPeriodInfo(periodStart = null) {
  const qs = periodStart ? `?period_start=${periodStart}` : "";
  const data = await GET(`/api/activities/period-info${qs}`);
  state.periodInfo = data;
  state.currentPeriodStart = data.period.start_date;
  renderPeriodBar();
}

function renderPeriodBar() {
  const p = state.periodInfo;
  if (!p) return;
  const fmt = iso => new Date(iso + "T00:00:00")
    .toLocaleDateString("da-DK", { day: "numeric", month: "short", year: "numeric" });
  document.getElementById("period-label").textContent =
    `${fmt(p.period.start_date)} – ${fmt(p.period.end_date)}`;
  document.getElementById("stat-pending").textContent  = `${p.period.pending} afventer`;
  document.getElementById("stat-approved").textContent = `${p.period.approved} godkendt`;
  document.getElementById("stat-deact").textContent    = `${p.period.deactivated} deaktiveret`;
  setDatePicker("period-date-picker", p.period.start_date);
  updateStatChipActive();
  renderPeriodSwitches();   // samme periode på Lønkørsel/Lønafregning/Fraværsoversigt (period_bar.js)
}

function updateStatChipActive() {
  const cur = document.getElementById("filter-status")?.value || "all";
  const map = { "stat-pending": "pending", "stat-approved": "approved", "stat-deact": "deactivated" };
  Object.entries(map).forEach(([id, val]) => {
    document.getElementById(id)?.classList.toggle("active", cur === val);
  });
}

function toggleStatFilter(status) {
  const sel = document.getElementById("filter-status");
  if (!sel) return;
  sel.value = (sel.value === status) ? "all" : status;
  updateStatChipActive();
  renderActivitiesTable();
}


async function navigatePeriod(direction) {
  const p = state.periodInfo;
  if (!p) return;
  const iso = direction === "prev" ? p.prev_period_start : p.next_period_start;
  await loadPeriodInfo(iso);
  await loadActivities();
}

async function jumpToDate(iso) {
  if (!iso) return;
  await loadPeriodInfo(iso);
  await loadActivities();
}

// ── Activities view ────────────────────────────────────────────────────────
async function loadHolidaysForPeriod(startDate, endDate) {
  const startYear = parseInt(startDate.substring(0, 4));
  const endYear   = parseInt(endDate.substring(0, 4));
  try {
    if (startYear === endYear) {
      state.holidays = await GET(`/api/stamdata/holidays?year=${startYear}`);
    } else {
      const [a, b] = await Promise.all([
        GET(`/api/stamdata/holidays?year=${startYear}`),
        GET(`/api/stamdata/holidays?year=${endYear}`),
      ]);
      state.holidays = [...a, ...b];
    }
  } catch (_) {
    state.holidays = [];
  }
}

async function loadActivities() {
  setLoading(true);
  try {
    if (!state.periodInfo) await loadPeriodInfo();
    const p = state.periodInfo.period;
    await Promise.all([
      GET(`/api/activities?period_start=${state.currentPeriodStart}`).then(a => { state.activities = a; }),
      loadHolidaysForPeriod(p.start_date, p.end_date),
      GET(`/api/activities/springer-flags?pay_period_id=${p.id}`).then(r => { state.springerFlags = r; }),
      GET(`/api/activities/payroll-ready-flags?pay_period_id=${p.id}`).then(r => { state.payrollReadyFlags = r; }),
    ]);
    renderActivitiesTable();
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

const DAY_NAMES = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"];

function renderActivitiesTable() {
  const p = state.periodInfo?.period;
  if (!p) return;

  const statusFilter = document.getElementById("filter-status")?.value || "all";
  const empFilter = document.getElementById("filter-employee")?.value || "";
  const groupFilter = document.getElementById("filter-dispatcher-group")?.value || "";
  const readyFilter = document.getElementById("filter-payroll-ready")?.value || "";

  const activities = state.activities.filter(a => {
    // Splittede aktiviteter er erstattet af deres to dele – vis kun delene
    // (gælder også når en del selv splittes yderligere: kun de endelige dele vises).
    if (a.has_split_children) return false;
    if (statusFilter !== "all" && a.status !== statusFilter) return false;
    if (empFilter && a.employee_id !== parseInt(empFilter)) return false;
    if (groupFilter) {
      const emp = state.employees.find(e => e.id === a.employee_id);
      if (!emp || !_empInGroup(emp, groupFilter)) return false;
    }
    return true;
  });

  // Periodens 14 dage
  const days = [];
  const start = new Date(p.start_date + "T00:00:00");
  for (let i = 0; i < 14; i++) {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    days.push(d);
  }
  const todayIso = new Date().toISOString().slice(0, 10);
  const isoOf = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

  // Header
  const head = document.getElementById("grid-head");
  head.innerHTML = `<tr>
    <th>Chauffør</th>
    ${days.map(d => {
      const iso  = isoOf(d);
      const hol  = state.holidays.find(x => x.date === iso);
      const cls  = iso === todayIso ? "today" : "";
      const bg   = hol ? (cls === "today" ? `background:#056a10;border-bottom:3px solid var(--accent);` : `background:#056a10;`) : "";
      const half = hol?.half_day_from
        ? `<span style="font-size:10px;display:block;color:#fff;margin-top:1px">½ fra ${hol.half_day_from}</span>`
        : "";
      const tip  = hol ? `title="${hol.name.replace(/"/g, '&quot;')}"` : "";
      return `<th class="${cls}" style="${bg}" ${tip}>
        <span class="day-name">${DAY_NAMES[(d.getDay() + 6) % 7]}</span>
        <span class="day-date">${String(d.getDate()).padStart(2, "0")}-${String(d.getMonth() + 1).padStart(2, "0")}-${d.getFullYear()}</span>
        ${half}
      </th>`;
    }).join("")}
  </tr>`;

  // Helper: er datoen søndag eller helligdag? (bestemmer om aktivitet splittes)
  const _isAbsDay = iso => {
    const d = new Date(iso + "T00:00:00");
    if (d.getDay() === 0) return true;
    return (state.holidays || []).some(h => h.date === iso);
  };
  const _fmtLocal = dt => {
    const p = n => String(n).padStart(2, "0");
    return `${dt.getFullYear()}-${p(dt.getMonth()+1)}-${p(dt.getDate())}T${p(dt.getHours())}:${p(dt.getMinutes())}:${p(dt.getSeconds())}`;
  };

  // Gruppér aktiviteter: employee_id -> dato-ISO -> [{a, role}]
  // Kørsels-aktiviteter der starter på søn/helligdag splittes ved midnat
  // (afspejler lønberegningens _split_into_day_pieces-logik)
  const byEmpDay = {};
  for (const a of activities) {
    const startDate = a.start_time.slice(0, 10);
    const endDate   = a.end_time.slice(0, 10);
    (byEmpDay[a.employee_id] ??= {})[startDate] ??= [];
    if (endDate !== startDate && a.activity_type === "normal" && _isAbsDay(startDate)) {
      let cur = new Date(a.start_time);
      const endDt = new Date(a.end_time);
      while (cur < endDt) {
        const midnight = new Date(cur.getFullYear(), cur.getMonth(), cur.getDate() + 1);
        const pieceEnd = endDt < midnight ? endDt : midnight;
        const piece = { ...a, start_time: _fmtLocal(cur), end_time: _fmtLocal(pieceEnd), _orig_id: a.id };
        const pieceDate = _fmtLocal(cur).slice(0, 10);
        (byEmpDay[a.employee_id][pieceDate] ??= []).push({a: piece, role: "piece"});
        cur = midnight;
      }
    } else if (endDate !== startDate) {
      byEmpDay[a.employee_id][startDate].push({a, role: "start"});
      (byEmpDay[a.employee_id][endDate] ??= []).push({a, role: "end"});
    } else {
      byEmpDay[a.employee_id][startDate].push({a, role: "full"});
    }
  }

  // Rækker: medarbejdere (filtreret hvis valgt), sorteret efter navn
  let emps = state.employees.filter(e => e.active && _empHasVisibleGroup(e));
  if (groupFilter) emps = emps.filter(e => _empInGroup(e, groupFilter));
  if (empFilter) emps = emps.filter(e => e.id === parseInt(empFilter));
  if (readyFilter) {
    const wantReady = readyFilter === "ready";
    emps = emps.filter(e => (state.payrollReadyFlags?.[e.id] === true) === wantReady);
  }
  emps.sort((x, y) => x.name.localeCompare(y.name, "da"));

  const body = document.getElementById("grid-body");
  body.innerHTML = "";

  if (emps.length === 0) {
    body.innerHTML = `<tr><td colspan="15" class="empty-state"><div class="icon">📋</div><h3>Ingen medarbejdere</h3></td></tr>`;
    return;
  }

  const canToggleSpringer = state.currentUser?.permissions?.includes("toggle_springer");
  const canToggleReady = state.currentUser?.permissions?.includes("toggle_payroll_ready");
  const periodLocked = p.status === "closed";

  for (const emp of emps) {
    const tr = document.createElement("tr");
    const springerChecked = state.springerFlags?.[emp.id] === true;
    const springerDisabledAttr = (!canToggleSpringer || periodLocked) ? "disabled" : "";
    const readyChecked = state.payrollReadyFlags?.[emp.id] === true;
    const readyDisabledAttr = (!canToggleReady || periodLocked) ? "disabled" : "";
    let cells = `<td class="emp-cell${empCellHighlight(emp)}" title="${h(emp.name)} (lønnr. ${h(emp.employee_number)})">
      ${h(emp.name)}
      <label class="springer-flag-label">
        <input type="checkbox" class="springer-flag-checkbox" data-emp-id="${emp.id}"
          ${springerChecked ? "checked" : ""} ${springerDisabledAttr}> Springertillæg
      </label>
      <label class="springer-flag-label">
        <input type="checkbox" class="payroll-ready-checkbox" data-emp-id="${emp.id}"
          ${readyChecked ? "checked" : ""} ${readyDisabledAttr}> Klar til løn
      </label>
    </td>`;
    for (const d of days) {
      const iso = isoOf(d);
      const acts = (byEmpDay[emp.id]?.[iso] || [])
        .sort((x, y) => {
          const tx = x.role === "end" ? x.a.end_time : x.a.start_time;
          const ty = y.role === "end" ? y.a.end_time : y.a.start_time;
          return tx.localeCompare(ty);
        });
      const weekend = d.getDay() === 0 || d.getDay() === 6;
      cells += `<td class="${weekend ? "weekend" : ""}" data-emp-id="${emp.id}" data-date="${iso}">${acts.map(({a, role}) => renderCellActivity(a, role)).join("")}</td>`;
    }
    tr.innerHTML = cells;
    body.appendChild(tr);
  }

  // Klik på badge -> detalje
  body.querySelectorAll(".time-badge").forEach(el => {
    el.addEventListener("click", () => openActivityDetail(parseInt(el.dataset.id)));
  });

  // Enkelt klik på celle -> opret aktivitet for medarbejder + dag
  body.querySelectorAll("td[data-emp-id]").forEach(td => {
    td.addEventListener("click", e => {
      if (e.target.closest(".time-badge")) return;
      if (!_hasPerm("edit_activities")) return;
      openManualActivityModal(parseInt(td.dataset.empId), td.dataset.date);
    });
  });

  // Springertillæg-flueben
  body.querySelectorAll(".springer-flag-checkbox").forEach(el => {
    el.addEventListener("change", async e => {
      e.stopPropagation();
      const checked = el.checked;
      try {
        await POST("/api/activities/springer-flag", {
          employee_id: parseInt(el.dataset.empId),
          pay_period_id: p.id,
          enabled: checked,
        });
        // Opdatér den lokale cache med det samme, så en senere fuld gentegning
        // af tabellen (fx efter oprettelse af en aktivitet via refreshActivities())
        // ikke overskriver brugerens seneste ændring med den forældede værdi fra
        // sidste periode-indlæsning.
        state.springerFlags = { ...(state.springerFlags || {}), [parseInt(el.dataset.empId)]: checked };
      } catch (err) {
        el.checked = !checked;
        toast(err.message, "error");
      }
    });
    el.addEventListener("click", e => e.stopPropagation());
  });

  // "Klar til løn"-flueben (påvirker kun filteret filter-payroll-ready)
  body.querySelectorAll(".payroll-ready-checkbox").forEach(el => {
    el.addEventListener("change", async e => {
      e.stopPropagation();
      const checked = el.checked;
      try {
        await POST("/api/activities/payroll-ready-flag", {
          employee_id: parseInt(el.dataset.empId),
          pay_period_id: p.id,
          enabled: checked,
        });
        // Samme cache-opdatering som for springertillæg (se ovenfor).
        state.payrollReadyFlags = { ...(state.payrollReadyFlags || {}), [parseInt(el.dataset.empId)]: checked };
        // Er filteret "Klar til løn"/"Ikke klar til løn" aktivt, skal linjen straks forsvinde.
        if (readyFilter) renderActivitiesTable();
      } catch (err) {
        el.checked = !checked;
        toast(err.message, "error");
      }
    });
    el.addEventListener("click", e => e.stopPropagation());
  });
}

function renderCellActivity(a, role = "full") {
  const k = a.is_manual ? "(K) " : "";
  const warn = a.status === "approved" ? "" : (a.is_under_4h ? " ❗" : (a.is_over_12h ? " ⚠️" : ""));
  const incomplete = a.is_likely_incomplete
    ? `<span class="incomplete-mark" title="Filen ser ud til at være hentet midt i vagten (0 km registreret eller unormalt kort vagt, og dagen slutter ikke i hvil) – resten af dagen mangler formentlig. Hent en ny fil senere og importér igen.">✕</span>`
    : "";
  // Split-delenes automatiske kommentar ("Split: første/anden del") tæller ikke som en kommentar
  const commentText = (a.comment || "").trim();
  const isSplitAutoComment = commentText === "Split: første del" || commentText === "Split: anden del";
  const note = (commentText && !isSplitAutoComment)
    ?`<span class="comment-note" title="Kommentar: ${h(a.comment)}"></span>`
    : "";
  if (a.activity_type !== "normal") {
    return `<div class="badge-group">
      <span class="time-badge absence ${a.status}" data-id="${a.id}" title="${TYPE_LABELS[a.activity_type]} – ${statusLabel(a.status)}">${ABSENCE_LABELS[a.activity_type] || a.activity_type}${note}</span>
    </div>`;
  }
  const pctD = pct(a.driving_pct), pctW = pct(a.other_work_pct), pctAv = pct(a.availability_time_pct);
  const pctHasData = pctD > 0 || pctW > 0 || pctAv > 0;
  const pctR = Math.max(0, 100 - pctD - pctW - pctAv);
  const pctInfo = pctHasData
    ? ` — Kørsel ${fmtPct(pctD)}% / Andet arbejde ${fmtPct(pctW)}% / Rådighed ${fmtPct(pctAv)}% / Pause ${fmtPct(pctR)}%`
    : "";
  const title = `${a.employee_name}: ${formatTime(a.start_time)}–${formatTime(a.end_time)} (${formatDuration(a.duration_minutes)}, pause ${formatDuration(a.pause_minutes || 0)}) – ${statusLabel(a.status)}${a.is_manual ? " – manuel" : ""}${pctInfo}`;
  const autoCls = (a.status === "approved" && a.auto_approved) ? " auto-approved" : "";
  const autoSuffix = (a.status === "approved" && a.auto_approved) ? `<span class="auto-dot" title="Auto-godkendt"></span>` : "";
  if (role === "start") {
    return `<div class="badge-group">
      <span class="time-badge ${a.status}${autoCls}" data-id="${a.id}" title="${title}">${k}${formatTime(a.start_time)}${warn}${autoSuffix}${incomplete}</span>
    </div>`;
  }
  if (role === "end") {
    return `<div class="badge-group">
      <span class="time-badge ${a.status}${autoCls}" data-id="${a.id}" title="${title}">${k}${formatTime(a.end_time)}${autoSuffix}${incomplete}</span>
    </div>`;
  }
  if (role === "piece") {
    const id = a._orig_id ?? a.id;
    return `<div class="badge-group">
      <span class="time-badge time-badge-stacked ${a.status}${autoCls}" data-id="${id}" title="${title}">
        <span class="time-line">${k}${formatTime(a.start_time)}${warn}</span>
        <span class="time-line">${formatTime(a.end_time)}${autoSuffix}${incomplete}</span>
      </span>
    </div>`;
  }
  return `<div class="badge-group">
    <span class="time-badge time-badge-stacked ${a.status}${autoCls}" data-id="${a.id}" title="${title}">
      <span class="time-line">${k}${formatTime(a.start_time)}${warn}</span>
      <span class="time-line">${formatTime(a.end_time)}${autoSuffix}${incomplete}</span>
      ${note}
    </span>
  </div>`;
}

function renderPctBar(a) {
  const d = pct(a.driving_pct), w = pct(a.other_work_pct), av = pct(a.availability_time_pct);
  const r = Math.max(0, 100 - d - w - av);
  return `<div class="pct-bar" title="Kørsel ${fmtPct(d)}% / Arbejde ${fmtPct(w)}% / Rådighed ${fmtPct(av)}% / Pause ${fmtPct(r)}%">
    <div class="pct-driving" style="width:${d}%"></div>
    <div class="pct-work" style="width:${w}%"></div>
    <div class="pct-avail" style="width:${av}%"></div>
    <div class="pct-rest" style="width:${r}%"></div>
  </div>`;
}
function pct(v) { return v ? parseFloat(v) : 0; }
function fmtPct(v) { return v.toFixed(2); }

// Fravær i en låst lønperiode må hverken slettes eller deaktiveres (håndhæves også i backend).
// Aktiviteter og fravær i en låst lønperiode må hverken deaktiveres eller slettes
// (håndhæves også i backend).
function _removalLocked(a) {
  return !!a && a.period_closed;
}

function _hasPerm(p) {
  return (state.currentUser?.permissions || []).includes(p);
}

// Spejler backend (_require_activity_permission): den generelle rettighed, eller en
// aktivitet oprettet fra Vagtplanen for en bruger med redigeringsret i Vagtplanen
// (backend afgør den endelige ret til netop den medarbejders linje).
function _canActivity(a, perm) {
  if (_hasPerm(perm)) return true;
  return !!a && a.source === "vagtplan" && (_hasPerm("vagtplan_edit_all") || _hasPerm("vagtplan_edit_own"));
}

// Kan aktiviteten ikke redigeres (låst periode eller mangler 'Redigér aktiviteter')?
function _editLocked(a) {
  return !a || a.period_closed || !_canActivity(a, "edit_activities");
}

function renderActionBtns(a) {
  const btns = [];
  if (!_canActivity(a, "approve_activities")) return "";
  if (a.status === "pending") {
    btns.push(`<button class="btn btn-success btn-sm" onclick="quickApprove(${a.id})">✓ Godkend</button>`);
    if (!_removalLocked(a)) btns.push(`<button class="btn btn-danger btn-sm" onclick="quickDeactivate(${a.id})">✗</button>`);
  } else if (!a.period_closed) {
    // Aktiviteter og fravær i en låst lønperiode må ikke genåbnes (håndhæves også i backend).
    btns.push(`<button class="btn btn-secondary btn-sm" onclick="quickReopen(${a.id})">↩ Genåbn</button>`);
  }
  return btns.join("");
}

async function quickApprove(id) {
  state.selectedActivityId = id;
  openApproveModal();
}
async function quickDeactivate(id) {
  state.selectedActivityId = id;
  openDeactivateModal();
}
async function quickReopen(id) {
  try {
    await POST(`/api/activities/${id}/reopen`);
    toast("Aktivitet genåbnet");
    await refreshActivities();
  } catch (e) { toast(e.message, "error"); }
}
async function bulkAutoApprove() {
  const params = state.currentPeriodStart ? `?period_start=${state.currentPeriodStart}` : '';
  const res = await POST(`/api/activities/auto-approve-pending${params}`, {});
  if (res) {
    toast(`Auto-godkendt: ${res.approved} aktiviteter. Flagget til gennemgang: ${res.flagged}.`);
    const btn = document.getElementById("btn-auto-approve");
    if (btn) btn.innerHTML = '<span class="auto-dot"></span>Autogodkendte';
    await refreshActivities();
  }
}
async function refreshActivities() {
  state.activities = await GET(`/api/activities?period_start=${state.currentPeriodStart}`);
  await loadPeriodInfo(state.currentPeriodStart);
  renderActivitiesTable();
}

// Opdaterer én aktivitet i state og gentegner med det samme, uden at vente på
// en fuld genindlæsning fra serveren (undgår synlig forsinkelse efter godkend/deaktiver/genåbn).
// Aktiviteten kan høre til Aktivitetsoversigtens periode ELLER Vagtplans (potentielt
// anderledes) datointerval – opdater den rigtige liste og gentegn kun den synlige visning.
function applyActivityLocally(updated) {
  if (!updated) return;
  // Aktivitetsoversigtens periode (14 dage) og Vagtplans vindue (3 uger) overlapper
  // ofte i dato, så den samme aktivitet kan ligge i BEGGE lister samtidig – opdatér
  // dem alle steder den findes, og gentegn kun den visning der rent faktisk er
  // synlig. Tidligere returnerede funktionen så snart den fandt aktiviteten i
  // state.activities, uden at røre state.vagtplan.activities – hvis man sad i
  // Vagtplan og godkendte/deaktiverede/genåbnede en aktivitet, der TILFÆLDIGVIS
  // også lå cachet i Aktivitetsoversigtens liste, blev Vagtplan-griddet aldrig
  // gentegnet, og badge-farven virkede "fastfrosset" indtil næste fulde genindlæsning.
  let foundAnywhere = false;
  const idx = state.activities.findIndex(x => x.id === updated.id);
  if (idx !== -1) {
    state.activities[idx] = updated;
    foundAnywhere = true;
  }
  const vIdx = state.vagtplan.activities.findIndex(x => x.id === updated.id);
  if (vIdx !== -1) {
    state.vagtplan.activities[vIdx] = updated;
    foundAnywhere = true;
  }
  if (!foundAnywhere) state.activities.push(updated);
  if (state.currentView === "vagtplan") renderVagtplanTable();
  else renderActivitiesTable();
}

// Aktiviteten kan være indlæst i Aktivitetsoversigtens periode (state.activities) eller
// kun i Vagtplans (potentielt anderledes) datointerval (state.vagtplan.activities) – slå op i begge.
function _findLoadedActivity(id) {
  return state.activities.find(x => x.id === id) || state.vagtplan.activities.find(x => x.id === id);
}

// ── Activity detail modal ──────────────────────────────────────────────────
async function openActivityDetail(id) {
  const modalEl = document.getElementById("modal-activity");
  const reopeningSameActivity = modalEl.classList.contains("open") && state.selectedActivityId === id;
  let preservedEdits = null;
  if (reopeningSameActivity) {
    preservedEdits = {
      start: readDatetimePicker("edit-start"),
      end: readDatetimePicker("edit-end"),
      vehicle: document.getElementById("edit-vehicle")?.value,
      kmStart: document.getElementById("edit-km-start")?.value,
      kmEnd: document.getElementById("edit-km-end")?.value,
      salt: document.getElementById("edit-salt")?.checked,
      dob: document.getElementById("edit-dob")?.checked,
    };
  }
  state.selectedActivityId = id;
  const a = _findLoadedActivity(id);
  if (!a) return;

  let absencePeriod = null;
  if (a.absence_group_id) {
    try {
      const group = await GET(`/api/activities/absence-group/${a.absence_group_id}`);
      const groupDates = group.map(g => g.start_time.slice(0, 10)).sort();
      absencePeriod = {
        groupId: a.absence_group_id,
        start: groupDates[0],
        end: groupDates[groupDates.length - 1],
      };
    } catch (e) { /* gruppen kunne ikke hentes – periode-sektionen udelades, enkeltdags-redigering virker stadig */ }
  }

  let seriesHtml = "";
  if (a.series_id) {
    try {
      const series = await GET(`/api/vagtplan-series/${a.series_id}`);
      const emp = state.employees.find(e => e.id === a.employee_id);
      const canEdit = _hasVagtplanEditAccess(emp) && !a.period_closed;
      seriesHtml = _renderSeriesSection(series, a.start_time.slice(0, 10), canEdit);
    } catch (e) { /* serien kunne ikke hentes – sektionen udelades */ }
  }

  document.getElementById("modal-activity-title").textContent =
    `${a.employee_name} – ${formatDate(a.start_time)}`;

  let d = pct(a.driving_pct), w = pct(a.other_work_pct), av = pct(a.availability_time_pct);
  let r, effektivLabel = "Kørsel";
  const hasSegmentData = d > 0 || w > 0 || av > 0;
  if (!hasSegmentData) {
    const totalMs = new Date(a.end_time) - new Date(a.start_time);
    let pauseMs = 0;
    for (const [ps, pe] of (a.pause_intervals || [])) {
      const s = Math.max(new Date(a.start_time).getTime(), new Date(ps).getTime());
      const e = Math.min(new Date(a.end_time).getTime(), new Date(pe).getTime());
      if (e > s) pauseMs += (e - s);
    }
    r = totalMs > 0 ? (pauseMs / totalMs) * 100 : 0;
    d = Math.max(0, 100 - r);
    effektivLabel = "Effektiv tid";
  } else {
    r = Math.max(0, 100 - d - w - av);
  }

  document.getElementById("modal-activity-body").innerHTML = `
    ${seriesHtml}
    ${absencePeriod && !_editLocked(a) ? `
    <div class="form-group" id="absence-period-section" style="margin-bottom:14px;padding:10px;background:var(--bg);border-radius:var(--radius)">
      <label style="font-weight:500;font-size:12px;text-transform:uppercase;color:var(--text-light);margin-bottom:6px;display:block">Fraværsperiode</label>
      <div class="form-row" style="margin-bottom:8px">
        <div class="form-group" style="min-width:0">
          <label>Fra dato</label>
          <input type="date" id="edit-period-start" value="${absencePeriod.start}">
        </div>
        <div class="form-group" style="min-width:0">
          <label>Til dato</label>
          <input type="date" id="edit-period-end" value="${absencePeriod.end}">
        </div>
      </div>
      <button type="button" class="btn btn-secondary" onclick="saveAbsencePeriodDates('${absencePeriod.groupId}')" style="font-size:13px;padding:5px 14px">Gem periodedatoer</button>
    </div>` : ""}
    <div class="detail-grid">
      ${a.vehicle_uses && a.vehicle_uses.length ? ""
        : `<div class="detail-item"><label>Vogn nr.</label><span>${a.vehicle_number || "–"}</span></div>`}
      <div class="detail-item"><label>KM start</label><span>${a.km_start != null ? a.km_start + " km" : "–"}</span></div>
      <div class="detail-item"><label>KM slut</label><span>${a.km_end != null ? a.km_end + " km" : "–"}</span></div>
      <div class="detail-item"><label>Salttillæg</label><span>${a.salt_supplement ? "Ja" : "Nej"}</span></div>
      <div class="detail-item"><label>Status</label><span class="badge badge-${a.status}">${statusLabel(a.status)}</span></div>
      <div class="detail-item"><label>Kort</label><span>${a.employee_number}</span></div>
      <div class="detail-item"><label>Type</label><span>${TYPE_LABELS[a.activity_type] || a.activity_type}</span></div>
      <div class="detail-item"><label>Start</label><span>${formatDateTime(a.start_time)}</span></div>
      <div class="detail-item"><label>Slut</label><span>${formatDateTime(a.end_time)}</span></div>
      <div class="detail-item"><label>Sum, effektiv tid</label><span>${formatDuration(a.duration_minutes)}</span></div>
      <div class="detail-item"><label>Sum, pause</label><span>${formatDuration(Math.round((new Date(a.end_time) - new Date(a.start_time)) / 60000) - a.duration_minutes)}</span></div>
      <div class="detail-item"><label>Oprettet af</label><span>${a.source === "vagtplan" ? "Vagtplan" : (a.is_manual ? (a.created_by || "Manuelt") : "System")}</span></div>
      ${(a.auto_approval_flags && a.auto_approval_flags.length > 0) ? `<div class="auto-approval-flags"><strong>Afvigelser registreret (ikke auto-godkendt):</strong><ul>${a.auto_approval_flags.map(f => `<li>${h(f)}</li>`).join('')}</ul></div>` : ""}
      ${a.status === "approved" && a.approved_by ? `<div class="detail-item"><label>Godkendt af</label><span>${h(a.approved_by)}</span></div>` : ""}
      ${a.status === "deactivated" && (a.deactivated_by || a.approved_by) ? `<div class="detail-item"><label>Deaktiveret af</label><span>${h(a.deactivated_by || a.approved_by)}</span></div>` : ""}
      ${a.updated_by ? `<div class="detail-item"><label>Ændret af</label><span>${h(a.updated_by)}</span></div>` : ""}
    </div>

    <div class="form-row" style="margin-bottom:14px">
      <div class="form-group" style="min-width:0">
        <label>Ret starttid</label>
        <div class="dt-picker" id="edit-start"></div>
      </div>
      <div class="form-group" style="min-width:0">
        <label>Ret sluttid</label>
        <div class="dt-picker" id="edit-end"></div>
      </div>
    </div>
    ${a.vehicle_uses && a.vehicle_uses.length
      // Vagt kørt i flere biler (fra .ddd): kun visning, vognnummeret kan ikke
      // ændres manuelt (bekræftet af bruger 2026-09-30). Tom værdi = uændret.
      ? `<input type="hidden" id="edit-vehicle" value="">`
      : `<div class="form-group" style="margin-bottom:14px">
      <label>Vogn nr.</label>
      <select id="edit-vehicle">
        <option value="">– Ingen –</option>
        ${state.vehicles.slice().sort((va,vb) => va.vehicle_number.localeCompare(vb.vehicle_number,"da",{numeric:true})).map(v => `<option value="${v.vehicle_number}" ${a.vehicle_number === v.vehicle_number ? "selected" : ""}>${v.vehicle_number} (${v.registration_number})</option>`).join("")}
      </select>
    </div>`}
    <div class="form-row" style="margin-bottom:14px">
      <div class="form-group" style="min-width:0">
        <label>KM start</label>
        <input type="number" id="edit-km-start" min="0" value="${a.km_start != null ? a.km_start : ""}">
      </div>
      <div class="form-group" style="min-width:0">
        <label>KM slut</label>
        <input type="number" id="edit-km-end" min="0" value="${a.km_end != null ? a.km_end : ""}">
      </div>
    </div>
    ${a.vehicle_uses && a.vehicle_uses.length ? `
    <div class="form-group" style="margin-bottom:14px">
      <label>Biler på vagten</label>
      <div style="font-size:14px;line-height:1.6">${a.vehicle_uses.map(u =>
        `${h(u.vehicle_number || "–")} (${h(u.registration)}) ${formatTime(u.start)}–${formatTime(u.end)}`).join("<br>")}</div>
    </div>` : ""}
    <div class="form-group" style="margin-bottom:14px">
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:500">
        <input type="checkbox" id="edit-salt" ${a.salt_supplement ? "checked" : ""} ${a.status !== "pending" ? "disabled" : ""} style="width:16px;height:16px;cursor:${a.status !== 'pending' ? 'not-allowed' : 'pointer'}">
        Salttillæg
      </label>
    </div>
    ${(a.activity_type === "overnatning" || a.activity_type === "dob_overnatning") ? `
    <div class="form-group" style="margin-bottom:14px">
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:500">
        <input type="checkbox" id="edit-dob" ${a.activity_type === "dob_overnatning" ? "checked" : ""} ${a.status !== "pending" ? "disabled" : ""} style="width:16px;height:16px;cursor:${a.status !== 'pending' ? 'not-allowed' : 'pointer'}">
        DOB
      </label>
    </div>` : ""}

    <div>
      <label style="font-weight:500;font-size:12px;text-transform:uppercase;color:var(--text-light);margin-bottom:6px;display:block">Aktivitetsfordeling</label>
      <div class="pct-bar" style="height:16px">
        <div class="pct-driving" style="width:${d}%"></div>
        <div class="pct-work" style="width:${w}%"></div>
        <div class="pct-avail" style="width:${av}%"></div>
        <div class="pct-rest" style="width:${r}%"></div>
      </div>
      <div class="pct-legend">
        <div class="pct-legend-item"><span class="pct-dot" style="background:#2563eb"></span>${effektivLabel} ${fmtPct(d)}%</div>
        ${!hasSegmentData ? "" : `<div class="pct-legend-item"><span class="pct-dot" style="background:#059669"></span>Andet arbejde ${fmtPct(w)}%</div>
        <div class="pct-legend-item"><span class="pct-dot" style="background:#d97706"></span>Rådighedstid ${fmtPct(av)}%</div>`}
        <div class="pct-legend-item"><span class="pct-dot" style="background:#9ca3af"></span>Pause ${fmtPct(r)}%</div>
      </div>
    </div>

    ${renderSegmentTable(a)}
    ${(!a.segments || !a.segments.length) ? `
    <div class="form-group mt-16">
      <label style="font-weight:500;font-size:12px;text-transform:uppercase;color:var(--text-light)">Pauser (fratrækkes i tidsrummet de afholdes)</label>
      ${(a.pause_intervals && a.pause_intervals.length) ? `
      <div style="font-size:13px;padding:4px 8px;background:var(--bg);border-radius:4px">
        ${a.pause_intervals.map((p, i) => `
          <div style="display:flex;align-items:center;gap:6px;padding:4px 0;border-bottom:1px solid var(--border,#e5e7eb)">
            <span style="flex:1">${formatTime(p[0])} – ${formatTime(p[1])}</span>
            ${_editLocked(a) ? "" : `<button class="act-pause-edit-btn" data-idx="${i}" data-id="${a.id}" style="font-size:11px;padding:2px 7px;cursor:pointer">Ret</button>
            <button class="act-pause-del-btn" data-idx="${i}" data-id="${a.id}" style="background:none;border:none;color:var(--danger);cursor:pointer;font-size:16px;line-height:1;padding:0 2px">&times;</button>`}
          </div>
        `).join("")}
      </div>` : ""}
      ${a.status === "pending" && !_editLocked(a) ? `
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">
        <button type="button" class="btn btn-secondary act-pause-add-btn" data-id="${a.id}" style="font-size:13px;padding:5px 14px">+ Tilføj pause</button>
        <button type="button" class="btn btn-secondary act-pause-suggest-btn" data-id="${a.id}" data-start="12:00" data-end="12:30" style="font-size:13px;padding:5px 14px">12:00–12:30</button>
        <button type="button" class="btn btn-secondary act-pause-suggest-btn" data-id="${a.id}" data-start="12:00" data-end="12:45" style="font-size:13px;padding:5px 14px">12:00–12:45</button>
      </div>` : ""}
    </div>` : ""}
    ${a.is_under_4h ? `<div class="alert-banner mt-16"><span class="icon">⚠️</span><div class="text"><h4>Under 4 timer</h4>Angiv begrundelse ved godkendelse (overenskomst: minimum 4 timer medmindre andet er aftalt).</div></div>` : ""}
    ${a.is_over_12h ? `<div class="alert-banner mt-16" style="background:#fef2f2;border-color:#fca5a5"><span class="icon">🔴</span><div class="text"><h4>Over 12 timer</h4>Usædvanlig lang aktivitet – kontroller om korrekt.</div></div>` : ""}
    ${a.comment ? `<div class="form-group mt-16"><label>Kommentar</label><div style="padding:8px;background:var(--bg);border-radius:4px;font-size:13px">${h(a.comment)}</div></div>` : ""}
  `;

  // Byg datetime-pickers efter innerHTML er sat
  buildDatetimePicker("edit-start", a.start_time.slice(0, 16));
  buildDatetimePicker("edit-end",   a.end_time.slice(0, 16));

  if (preservedEdits) {
    if (preservedEdits.start) setDatetimePicker("edit-start", preservedEdits.start);
    if (preservedEdits.end)   setDatetimePicker("edit-end", preservedEdits.end);
    const vehicleEl = document.getElementById("edit-vehicle");
    if (vehicleEl && preservedEdits.vehicle != null) vehicleEl.value = preservedEdits.vehicle;
    const kmStartEl = document.getElementById("edit-km-start");
    if (kmStartEl && preservedEdits.kmStart != null) kmStartEl.value = preservedEdits.kmStart;
    const kmEndEl = document.getElementById("edit-km-end");
    if (kmEndEl && preservedEdits.kmEnd != null) kmEndEl.value = preservedEdits.kmEnd;
    const saltEl = document.getElementById("edit-salt");
    if (saltEl && preservedEdits.salt != null) saltEl.checked = preservedEdits.salt;
    const dobEl = document.getElementById("edit-dob");
    if (dobEl && preservedEdits.dob != null) dobEl.checked = preservedEdits.dob;
  }

  const footer = document.getElementById("modal-activity-footer");
  footer.innerHTML = "";
  // Låst lønperiode: ingen ændringer overhovedet – kun Godkend (for evt. afventende)
  // og Luk vises. Håndhæves også i backend.
  const locked = a.period_closed;
  // Rettigheder (håndhæves også i backend): 'Redigér aktiviteter' styrer ret/fortryd/
  // split, 'Godkend aktiviteter' styrer godkend/deaktiver/genåbn.
  const editLocked = _editLocked(a);
  const canApprove = _canActivity(a, "approve_activities");
  // Fortryd-knapper
  if (!editLocked && a.is_edited) {
    footer.innerHTML += `<button class="btn btn-warning" onclick="undoEdit()" title="Gendan de oprindelige tider">↩ Fortryd tidsændring</button>`;
  }
  if (!editLocked && (a.has_split_children || a.parent_activity_id)) {
    footer.innerHTML += `<button class="btn btn-warning" onclick="undoSplit()" title="Slet delene og gendan den originale aktivitet">↩ Fortryd split</button>`;
  }
  if (!editLocked) footer.innerHTML += `<button class="btn btn-secondary" onclick="saveActivityTimes()">💾 Gem ændringer</button>`;
  if (a.status === "pending") {
    if (!editLocked) footer.innerHTML += `<button class="btn btn-warning" onclick="openSplitModal()">✂️ Split</button>`;
    if (canApprove && !_removalLocked(a)) footer.innerHTML += `<button class="btn btn-danger" onclick="modalDeactivate()">✗ Deaktiver</button>`;
    if (canApprove) footer.innerHTML += `<button class="btn btn-success" onclick="openApproveModal()">✓ Godkend</button>`;
  } else {
    if (!editLocked && a.status === "deactivated") footer.innerHTML += `<button class="btn btn-warning" onclick="openSplitModal()">✂️ Split</button>`;
    if (!locked && canApprove) footer.innerHTML += `<button class="btn btn-secondary" onclick="modalReopen()">↩ Genåbn</button>`;
  }
  footer.innerHTML += `<button class="btn btn-secondary" onclick="closeModal('modal-activity')">Luk</button>`;

  // Saks-knapper i hændelsestabellen
  document.querySelectorAll("#modal-activity-body .seg-split-btn").forEach(btn => {
    btn.addEventListener("click", () => splitAtSegment(btn.dataset.splitAt));
  });
  document.querySelectorAll("#modal-activity-body .seg-correct-btn").forEach(btn => {
    btn.addEventListener("click", () => correctSegment(parseInt(btn.dataset.id), parseInt(btn.dataset.idx)));
  });
  document.querySelectorAll("#modal-activity-body .seg-revert-btn").forEach(btn => {
    btn.addEventListener("click", () => correctSegment(parseInt(btn.dataset.id), parseInt(btn.dataset.idx), true));
  });
  document.querySelectorAll("#modal-activity-body .seg-resize-btn").forEach(btn => {
    btn.addEventListener("click", () => openResizeSegment(parseInt(btn.dataset.id), parseInt(btn.dataset.idx)));
  });
  document.querySelectorAll("#modal-activity-body .act-pause-edit-btn").forEach(btn => {
    btn.addEventListener("click", () => openActivityPauseEdit(parseInt(btn.dataset.id), parseInt(btn.dataset.idx)));
  });
  document.querySelectorAll("#modal-activity-body .act-pause-del-btn").forEach(btn => {
    btn.addEventListener("click", () => deleteActivityPause(parseInt(btn.dataset.id), parseInt(btn.dataset.idx)));
  });
  document.querySelectorAll("#modal-activity-body .act-pause-add-btn").forEach(btn => {
    btn.addEventListener("click", () => openActivityPauseAdd(parseInt(btn.dataset.id)));
  });
  document.querySelectorAll("#modal-activity-body .act-pause-suggest-btn").forEach(btn => {
    btn.addEventListener("click", () => addActivityPauseSuggestion(parseInt(btn.dataset.id), btn.dataset.start, btn.dataset.end));
  });

  openModal("modal-activity");
  document.getElementById("modal-activity-body").scrollTop = 0;
}

const SEGMENT_LABELS = {
  rest: "Pause", availability: "Rådighed", work: "Andet arbejde", driving: "Kørsel",
};
const SEGMENT_ICONS = {
  rest: "☕", availability: "⏳", work: "📦", driving: "🚚",
};

function renderSegmentTable(a) {
  if (!a.segments || a.segments.length === 0) return "";
  // Låst lønperiode eller ingen 'Redigér aktiviteter': ingen ret/tilpas/gendan/split-
  // knapper (håndhæves også i backend).
  const locked = _editLocked(a);
  const hasCorrectable = !locked && a.segments.some(seg => seg[2] === "rest" && seg.length < 4);
  // Saksen vises ikke på første linje (split ved aktivitetens start giver ingen mening)
  const rows = a.segments.map((seg, idx) => {
    const [s, e, name, correctedFrom] = seg;
    const mins = Math.round((new Date(e) - new Date(s)) / 60000);
    const h = Math.floor(mins / 60), m = mins % 60;
    const canSplit = idx > 0 && !locked;
    const isCorrected = correctedFrom !== undefined;
    const rowBg = name === "rest" ? `style="background:#d4edcc;"` : "";
    const tilrettet = isCorrected ? "Ja" : (a.is_edited ? "Ja" : "Nej");
    let retBtns = "";
    if (locked) {
      retBtns = "";
    } else if (name === "rest" && !isCorrected) {
      retBtns = `<div style="display:flex;flex-direction:column;gap:3px;align-items:flex-start">
        <button class="seg-correct-btn" data-idx="${idx}" data-id="${a.id}" style="font-size:11px;padding:2px 7px;cursor:pointer" title="Ret til 'Andet arbejde'">Ret til andet arbejde</button>
        <button class="seg-resize-btn" data-idx="${idx}" data-id="${a.id}" style="font-size:11px;padding:2px 7px;cursor:pointer" title="Tilpas pauselængde">Tilpas</button>
      </div>`;
    } else if (isCorrected) {
      retBtns = `<button class="seg-revert-btn" data-idx="${idx}" data-id="${a.id}" style="font-size:11px;padding:2px 7px;cursor:pointer" title="Gendan til '${SEGMENT_LABELS[correctedFrom] || correctedFrom}'">Gendan</button>`;
    }
    return `<tr ${rowBg}>
      <td>${formatDateTime(s)}</td>
      <td>${SEGMENT_LABELS[name] || name}</td>
      <td>${h} t. ${m} m.</td>
      <td style="text-align:center">${retBtns}</td>
      <td>${tilrettet}</td>
      <td style="text-align:center">${SEGMENT_ICONS[name] || ""}</td>
      <td style="text-align:center">${canSplit
        ? `<button class="seg-split-btn" data-split-at="${s}" title="Split aktiviteten her (kl. ${formatTime(s)})">✂️</button>`
        : ""}</td>
    </tr>`;
  }).join("");
  return `
  <div class="mt-16">
    ${hasCorrectable ? `<button class="btn btn-success" onclick="correctAllSegments(${a.id})" style="margin-bottom:8px">Al pause til andet arbejde</button>` : ""}
    <label style="font-weight:500;font-size:12px;text-transform:uppercase;color:var(--text-light);margin-bottom:6px;display:block">Detaljeret information om dagen</label>
    <div style="max-height:260px;overflow-y:auto;border:1px solid var(--border);border-radius:var(--radius)">
      <table style="font-size:12px">
        <thead>
          <tr><th>Dato og tid</th><th>Status</th><th>Forbrugt tid</th><th>Ret</th><th>Tilrettet</th><th>Type</th><th style="width:36px"></th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  </div>`;
}

async function correctSegment(activityId, segIdx, revert = false) {
  try {
    const updated = await POST(`/api/activities/${activityId}/correct-segment`, { segment_index: segIdx, revert });
    state.activities = state.activities.map(a => a.id === updated.id ? updated : a);
    const body = document.getElementById("modal-activity-body");
    const scrollTop = body ? body.scrollTop : 0;
    openActivityDetail(activityId);
    if (body) body.scrollTop = scrollTop;
    renderActivitiesTable();
    toast(revert ? "Segment gendannet" : "Linje rettet til 'Andet arbejde'", "success");
  } catch (e) { toast(e.message, "error"); }
}

async function correctAllSegments(activityId) {
  try {
    const updated = await POST(`/api/activities/${activityId}/correct-all-segments`);
    state.activities = state.activities.map(a => a.id === updated.id ? updated : a);
    const body = document.getElementById("modal-activity-body");
    const scrollTop = body ? body.scrollTop : 0;
    openActivityDetail(activityId);
    if (body) body.scrollTop = scrollTop;
    renderActivitiesTable();
    toast("Alle pauselinjer rettet til 'Andet arbejde'", "success");
  } catch (e) { toast(e.message, "error"); }
}

function openResizeSegment(activityId, segIdx) {
  const a = state.activities.find(x => x.id === activityId);
  if (!a) return;
  const seg = a.segments[segIdx];
  if (!seg) return;

  _resizeSegState = {
    activityId,
    segIdx,
    segStart: seg[0],
    segEnd: seg[1],
    nextSeg: a.segments[segIdx + 1] || null,
  };

  const segLabel = SEGMENT_LABELS[seg[2]] || seg[2];
  const next = _resizeSegState.nextSeg;
  const nextInfo = next
    ? `Næste: ${SEGMENT_LABELS[next[2]] || next[2]} (${next[0].slice(11, 16)}–${next[1].slice(11, 16)})`
    : "Ingen næste segment";
  document.getElementById("resize-seg-info").innerHTML =
    `<strong>${segLabel}</strong> &nbsp; ${_resizeSegState.segStart.slice(11, 16)}–${_resizeSegState.segEnd.slice(11, 16)}<br>` +
    `<span style="color:var(--text-light);font-size:12px">${nextInfo}</span>`;

  buildDatetimePicker("resize-seg-end", seg[1].slice(0, 16));
  _stackDatetimePicker("resize-seg-end");
  document.getElementById("resize-seg-preview").innerHTML = "";

  document.getElementById("resize-seg-end").querySelectorAll("input").forEach(inp => {
    inp.addEventListener("input", updateResizePreview);
    inp.addEventListener("change", updateResizePreview);
  });

  openModal("modal-resize-segment");
}

function updateResizePreview() {
  if (!_resizeSegState) return;
  const preview = document.getElementById("resize-seg-preview");
  const newEndIso = readDatetimePicker("resize-seg-end");
  if (!newEndIso) { preview.innerHTML = ""; return; }

  const newEnd = newEndIso + ":00";
  const { segStart, segEnd, nextSeg } = _resizeSegState;

  if (newEnd <= segStart) {
    preview.style.color = "var(--danger)";
    preview.textContent = `Sluttid skal være efter starttid (${segStart.slice(11, 16)})`;
    return;
  }
  if (newEnd === segEnd) {
    preview.style.color = "var(--text-light)";
    preview.textContent = "Ingen ændring";
    return;
  }

  const diffMs = new Date(newEnd) - new Date(segEnd);
  const absDiffMin = Math.round(Math.abs(diffMs) / 60000);

  if (diffMs < 0) {
    preview.style.color = "var(--primary)";
    preview.textContent =
      `Pausen forkortes med ${absDiffMin} min. ` +
      `De resterende ${absDiffMin} min tilføjes som 'Andet arbejde' (${newEnd.slice(11, 16)}–${segEnd.slice(11, 16)}).`;
  } else {
    if (!nextSeg) {
      preview.style.color = "var(--danger)";
      preview.textContent = "Der er intet næste segment – pausen kan ikke forlænges.";
      return;
    }
    const nextEnd = nextSeg[1];
    if (newEnd >= nextEnd) {
      preview.style.color = "var(--danger)";
      preview.textContent =
        `Ny sluttid (${newEnd.slice(11, 16)}) overstiger næste segments sluttid (${nextEnd.slice(11, 16)}).`;
      return;
    }
    preview.style.color = "";
    const nextLabel = SEGMENT_LABELS[nextSeg[2]] || nextSeg[2];
    preview.textContent =
      `Pausen forlænges med ${absDiffMin} min. ` +
      `Næste segment (${nextLabel}) forkortes: ${nextSeg[0].slice(11, 16)}–${nextSeg[1].slice(11, 16)} → ${newEnd.slice(11, 16)}–${nextEnd.slice(11, 16)}.`;
  }
}

async function confirmResizeSegment() {
  if (!_resizeSegState) return;
  const newEndIso = readDatetimePicker("resize-seg-end");
  if (!newEndIso) { toast("Angiv ny sluttid", "error"); return; }

  const newEnd = newEndIso + ":00";
  const { activityId, segIdx, segStart, segEnd } = _resizeSegState;
  if (newEnd <= segStart) { toast("Sluttid skal være efter starttid", "error"); return; }
  if (newEnd === segEnd) { toast("Ingen ændring", "error"); return; }

  try {
    const updated = await POST(`/api/activities/${activityId}/resize-segment`, {
      segment_index: segIdx,
      new_end_iso: newEndIso,
    });
    state.activities = state.activities.map(a => a.id === updated.id ? updated : a);
    closeModal("modal-resize-segment");
    const body = document.getElementById("modal-activity-body");
    const scrollTop = body ? body.scrollTop : 0;
    openActivityDetail(activityId);
    if (body) body.scrollTop = scrollTop;
    renderActivitiesTable();
    toast("Pauselængde tilpasset", "success");
  } catch (e) { toast(e.message, "error"); }
}

function splitAtSegment(isoTime) {
  openSplitModal();
  setDatetimePicker("split-at", isoTime.slice(0, 16));
}

async function undoEdit() {
  if (!confirm("Fortryd tidsændringer og gendan de oprindelige tider?")) return;
  try {
    const updated = await POST(`/api/activities/${state.selectedActivityId}/undo-edit`);
    toast("Tidsændringer fortrudt – originale tider gendannet", "success");
    closeAllModals();
    applyActivityLocally(updated);
    refreshActivities().catch(() => {});
  } catch (e) { toast(e.message, "error"); }
}

async function undoSplit() {
  if (!confirm("Fortryd split? Delene slettes, og den originale aktivitet gendannes som afventende.")) return;
  try {
    await POST(`/api/activities/${state.selectedActivityId}/undo-split`);
    toast("Split fortrudt – original aktivitet gendannet", "success");
    closeAllModals();
    await refreshActivities();
  } catch (e) { toast(e.message, "error"); }
}

async function saveAbsencePeriodDates(groupId) {
  const newStart = document.getElementById("edit-period-start").value;
  const newEnd   = document.getElementById("edit-period-end").value;
  if (!newStart || !newEnd) { toast("Angiv fra- og til-dato", "error"); return; }
  if (newEnd < newStart) { toast("Til dato skal være på eller efter fra dato", "error"); return; }

  let group;
  try {
    group = await GET(`/api/activities/absence-group/${groupId}`);
  } catch (e) { toast(e.message, "error"); return; }

  const empId = group[0].employee_id;
  const groupType = group[0].activity_type;
  const isCountBased = groupType === "overnatning" || groupType === "dob_overnatning";
  const existingDates = group.map(g => g.start_time.slice(0, 10));
  const newDates = isCountBased ? getAllDates(newStart, newEnd) : getWeekdayDates(newStart, newEnd);
  const toRemove = existingDates.filter(d => !newDates.includes(d));
  const toAdd    = newDates.filter(d => !existingDates.includes(d));

  if (toRemove.length === 0 && toAdd.length === 0) { toast("Ingen ændringer i perioden", "warning"); return; }

  if (toAdd.length > 0) {
    const conflicts = isCountBased
      ? toAdd.filter(iso =>
          state.activities.some(a =>
            a.employee_id === empId &&
            a.status !== "deactivated" &&
            new Date(iso + "T00:00:00") < new Date(a.end_time) &&
            new Date(iso + "T23:59:59") > new Date(a.start_time)
          )
        )
      : toAdd.filter(iso =>
          state.activities.some(a =>
            a.employee_id === empId &&
            a.activity_type === "normal" &&
            a.start_time.slice(0, 10) === iso &&
            a.status !== "deactivated"
          )
        );
    if (conflicts.length > 0) {
      const dateList = conflicts.map(d => { const [y,m,day]=d.split("-"); return `${day}-${m}-${y}`; }).join(", ");
      const msg = isCountBased
        ? `Der er allerede registreret ${conflicts.length > 1 ? "aktiviteter" : "en aktivitet"} følgende dag${conflicts.length>1?"e":""}:\n${dateList}\n\nVil du alligevel udvide perioden til at inkludere den/dem?`
        : `Der er allerede registreret kørsel på følgende dag${conflicts.length>1?"e":""}:\n${dateList}\n\nVil du alligevel udvide fraværsperioden til at inkludere den/dem?`;
      if (!window.confirm(msg)) return;
    }
  }

  const fmt = d => { const [y,m,day]=d.split("-"); return `${day}-${m}-${y}`; };
  const parts = [
    toRemove.length > 0 ? `${toRemove.length} dag${toRemove.length>1?"e":""} slettes permanent: ${toRemove.map(fmt).join(", ")}` : null,
    toAdd.length > 0 ? `${toAdd.length} dag${toAdd.length>1?"e":""} oprettes: ${toAdd.map(fmt).join(", ")}` : null,
  ].filter(Boolean).join("\n");
  if (!window.confirm(`${parts}\n\nFortsæt?`)) return;

  try {
    const result = await PATCH(`/api/activities/absence-group/${groupId}`, {
      new_start_date: newStart,
      new_end_date: newEnd,
    });
    toast("Fraværsperiode opdateret", "success");
    if (result.skipped && result.skipped.length > 0) {
      toast(`${result.skipped.length} dag${result.skipped.length>1?"e":""} sprunget over – ingen garanterede timer: ${result.skipped.map(fmt).join(", ")}`, "warning");
    }
    closeAllModals();
    await refreshActivities();
    if (state.currentView === "vagtplan") await loadVagtplan();
  } catch (e) { toast(e.message, "error"); }
}

async function saveActivityTimes() {
  const start = readDatetimePicker("edit-start");
  const end   = readDatetimePicker("edit-end");
  if (!start || !end) { toast("Angiv start- og sluttid", "error"); return; }
  const dobCb = document.getElementById("edit-dob");
  if (!dobCb && new Date(end) <= new Date(start)) { toast("Sluttid skal være efter starttid", "error"); return; }
  const vehicleNum = document.getElementById("edit-vehicle")?.value || null;
  const kmStartVal = document.getElementById("edit-km-start")?.value;
  const kmEndVal   = document.getElementById("edit-km-end")?.value;
  const saltVal    = document.getElementById("edit-salt")?.checked ?? false;

  const a = _findLoadedActivity(state.selectedActivityId);
  const payload = {
    start_time: start + ":00",
    end_time: end + ":00",
    vehicle_number: vehicleNum || null,
    km_start: kmStartVal !== "" && kmStartVal != null ? parseInt(kmStartVal) : null,
    km_end:   kmEndVal   !== "" && kmEndVal   != null ? parseInt(kmEndVal)   : null,
    salt_supplement: saltVal,
  };
  if (dobCb) payload.activity_type = dobCb.checked ? "dob_overnatning" : "overnatning";

  // Spørg om pausedatoer skal følge med, hvis startdatoen ændres
  if (a && a.pause_intervals && a.pause_intervals.length) {
    const oldDateStr = a.start_time.slice(0, 10);
    const newDateStr = start.slice(0, 10);
    if (oldDateStr !== newDateStr) {
      const dayDiff = Math.round(
        (new Date(newDateStr + "T00:00:00") - new Date(oldDateStr + "T00:00:00"))
        / 86400000
      );
      const svar = confirm(
        `Startdatoen er ændret fra ${oldDateStr} til ${newDateStr}.\n` +
        `Vil du også flytte pauserne ${dayDiff > 0 ? "frem" : "tilbage"} med ${Math.abs(dayDiff)} dag${Math.abs(dayDiff) !== 1 ? "e" : ""}?`
      );
      if (svar) {
        payload.pause_intervals = a.pause_intervals.map(([ps, pe]) => [
          _shiftIsoByDays(ps, dayDiff),
          _shiftIsoByDays(pe, dayDiff),
        ]);
      }
    }
  }

  try {
    const updated = await PATCH(`/api/activities/${state.selectedActivityId}`, payload);
    toast("Ændringer gemt", "success");
    applyActivityLocally(updated);
    openActivityDetail(state.selectedActivityId);
    refreshActivities().catch(() => {});
  } catch (e) { toast(e.message, "error"); }
}

function _shiftIsoByDays(isoStr, days) {
  const d = new Date(isoStr.slice(0, 10) + "T00:00:00");
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10) + isoStr.slice(10);
}

function openApproveModal() {
  const a = _findLoadedActivity(state.selectedActivityId);
  if (!a) return;
  document.getElementById("approve-comment").value = "";
  document.getElementById("approve-comment-required").classList.toggle("hidden", !a.is_under_4h);
  const lbl = document.getElementById("approve-user-label");
  if (lbl) lbl.textContent = state.currentUser ? `Godkendes af: ${state.currentUser.name} (${state.currentUser.initials})` : "";
  openModal("modal-approve");
}

async function confirmApprove() {
  const comment = document.getElementById("approve-comment").value.trim();
  const a = _findLoadedActivity(state.selectedActivityId);
  if (a?.is_under_4h && !comment) { toast("Angiv begrundelse for aktivitet under 4 timer", "error"); return; }

  try {
    // Gem vognnummer, km og salttillæg inden godkendelse
    const vehicleNum = document.getElementById("edit-vehicle")?.value;
    const kmStartVal = document.getElementById("edit-km-start")?.value;
    const kmEndVal   = document.getElementById("edit-km-end")?.value;
    const saltVal    = document.getElementById("edit-salt")?.checked ?? false;
    const dobCb      = document.getElementById("edit-dob");
    // I en låst lønperiode kan aktiviteten ikke rettes – spring gem-trinnet over.
    if (vehicleNum !== undefined && !_editLocked(a)) {
      const patchBody = {
        vehicle_number: vehicleNum || null,
        km_start: kmStartVal !== "" && kmStartVal != null ? parseInt(kmStartVal) : null,
        km_end:   kmEndVal   !== "" && kmEndVal   != null ? parseInt(kmEndVal)   : null,
        salt_supplement: saltVal,
      };
      if (dobCb) patchBody.activity_type = dobCb.checked ? "dob_overnatning" : "overnatning";
      await PATCH(`/api/activities/${state.selectedActivityId}`, patchBody);
    }
    const updated = await POST(`/api/activities/${state.selectedActivityId}/approve`,
      { comment: comment || null });
    toast("Aktivitet godkendt", "success");
    closeAllModals();
    applyActivityLocally(updated);
    refreshActivities().catch(() => {});
  } catch (e) { toast(e.message, "error"); }
}

async function modalDeactivate() {
  openDeactivateModal();
}

function openDeactivateModal() {
  document.getElementById("deactivate-comment").value = "";
  document.getElementById("deactivate-hide-vagtplan").checked = false;
  const a = _findLoadedActivity(state.selectedActivityId);
  if (_removalLocked(a)) { toast("Aktiviteter og fravær i en låst lønperiode kan ikke fjernes", "error"); return; }
  const canDeleteEntirely = a && (a.activity_type !== "normal" || a.is_manual);
  document.getElementById("deactivate-hide-vagtplan-group").style.display = canDeleteEntirely ? "" : "none";
  if (canDeleteEntirely) {
    document.getElementById("deactivate-delete-label-text").textContent = a.activity_type === "normal"
      ? "Slet aktiviteten helt (fjernes permanent fra Aktivitetsoversigt)"
      : "Slet aktiviteten helt (fjernes permanent fra både Vagtplan og Aktivitetsoversigt)";
  }
  const lbl = document.getElementById("deactivate-user-label");
  if (lbl) lbl.textContent = state.currentUser ? `Deaktiveres af: ${state.currentUser.name} (${state.currentUser.initials})` : "";
  openModal("modal-deactivate");
}

async function confirmDeactivate() {
  const comment = document.getElementById("deactivate-comment").value.trim();
  const deleteEntirely = document.getElementById("deactivate-hide-vagtplan").checked;
  try {
    if (deleteEntirely) {
      const id = state.selectedActivityId;
      await DEL(`/api/activities/${id}`);
      const idx = state.activities.findIndex(x => x.id === id);
      if (idx !== -1) state.activities.splice(idx, 1);
      const vIdx = state.vagtplan.activities.findIndex(x => x.id === id);
      if (vIdx !== -1) state.vagtplan.activities.splice(vIdx, 1);
      toast("Aktivitet slettet");
      closeAllModals();
      if (state.currentView === "vagtplan") renderVagtplanTable();
      else renderActivitiesTable();
      refreshActivities().catch(() => {});
      return;
    }
    const updated = await POST(`/api/activities/${state.selectedActivityId}/deactivate`,
      { comment: comment || null });
    applyActivityLocally(updated);
    toast("Aktivitet deaktiveret");
    closeAllModals();
    refreshActivities().catch(() => {});
  } catch (e) { toast(e.message, "error"); }
}
async function modalReopen() {
  try {
    const updated = await POST(`/api/activities/${state.selectedActivityId}/reopen`);
    toast("Aktivitet genåbnet");
    closeAllModals();
    applyActivityLocally(updated);
    refreshActivities().catch(() => {});
  } catch (e) { toast(e.message, "error"); }
}

// ── Split modal ────────────────────────────────────────────────────────────
function openSplitModal() {
  const a = _findLoadedActivity(state.selectedActivityId);
  if (!a) return;
  document.getElementById("split-activity-info").textContent =
    `${a.employee_name}: ${formatDateTime(a.start_time)} – ${formatDateTime(a.end_time)}`;
  const midMs = (new Date(a.start_time).getTime() + new Date(a.end_time).getTime()) / 2;
  const mid = new Date(midMs);
  const midIso = mid.getFullYear() + "-" +
    String(mid.getMonth()+1).padStart(2,"0") + "-" +
    String(mid.getDate()).padStart(2,"0") + "T" +
    String(mid.getHours()).padStart(2,"0") + ":" +
    String(mid.getMinutes()).padStart(2,"0");
  buildDatetimePicker("split-at", midIso);
  state.splitMin = a.start_time.slice(0, 16);
  state.splitMax = a.end_time.slice(0, 16);
  openModal("modal-split");
}

async function confirmSplit() {
  const splitAt = readDatetimePicker("split-at");
  if (!splitAt) { toast("Angiv splitpunkt", "error"); return; }
  if (splitAt <= state.splitMin || splitAt >= state.splitMax) {
    toast("Splitpunktet skal ligge mellem start- og sluttid", "error"); return;
  }
  try {
    await POST(`/api/activities/${state.selectedActivityId}/split`, { split_at: splitAt + ":00" });
    toast("Aktivitet splittet", "success");
    closeAllModals();
    await refreshActivities();
  } catch (e) { toast(e.message, "error"); }
}

// ── Datetime picker helpers ────────────────────────────────────────────────
function _dtOptions(max) {
  return Array.from({length: max}, (_, i) => {
    const v = String(i).padStart(2, "0");
    return `<option value="${v}">${v}</option>`;
  }).join("");
}

function _stackDatetimePicker(id) {
  const el = document.getElementById(id);
  if (!el) return;
  const dateEl = el.querySelector(".dt-date");
  const timeEl = el.querySelector(".dt-time");
  if (!dateEl || !timeEl) return;
  el.style.cssText = "display:flex;flex-direction:column;gap:6px;";
  dateEl.style.width = "100%";
  const timeRow = document.createElement("div");
  timeRow.style.cssText = "display:flex;align-items:center;gap:6px;";
  timeRow.append(timeEl);
  el.append(timeRow);
}

function buildDatetimePicker(id, isoValue) {
  const el = document.getElementById(id);
  if (!el) return;
  const date = isoValue ? isoValue.slice(0, 10) : "";
  const time = isoValue ? isoValue.slice(11, 16) : "06:00";
  const S = "padding:8px 10px;border:1px solid var(--border);border-radius:var(--radius);font-size:13px;background:var(--surface);color:var(--text);box-sizing:border-box;";
  const N = `${S}width:110px;flex:0 0 110px;`;
  el.style.cssText = "display:flex;align-items:center;gap:6px;flex-wrap:nowrap;";
  el.innerHTML = `
    <input type="date" class="dt-date" value="${date}" style="${S}flex:1 1 0;min-width:0;">
    <input type="time" class="dt-time" value="${time}" style="${N}">
  `;
}

function readDatetimePicker(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  const date = el.querySelector(".dt-date")?.value;
  const time = el.querySelector(".dt-time")?.value;
  return date ? `${date}T${time || "00:00"}` : null;
}

function setDatetimePicker(id, isoValue) {
  const el = document.getElementById(id);
  if (!el || !isoValue) return;
  el.querySelector(".dt-date").value = isoValue.slice(0, 10);
  el.querySelector(".dt-time").value = isoValue.slice(11, 16);
}

// ── Date picker (årstal-dropdown + kalender) ───────────────────────────────
const _DP_MONTHS = ["Januar","Februar","Marts","April","Maj","Juni",
                    "Juli","August","September","Oktober","November","December"];
const _DP_DAYS   = ["Ma","Ti","On","To","Fr","Lø","Sø"];

// opts.weeks: vis en ugenummer-kolonne til venstre for datoerne (bruges i Vagtplan).
function buildDatePicker(containerId, initialValue, opts = {}) {
  const wrap = document.getElementById(containerId);
  if (!wrap) return;
  if (opts.weeks) wrap.dataset.weeks = "1";
  else delete wrap.dataset.weeks;

  const iso = initialValue || "";
  let selY = null, selM = null, selD = null;
  if (iso.length >= 10) {
    selY = parseInt(iso.slice(0, 4), 10);
    selM = parseInt(iso.slice(5, 7), 10) - 1;
    selD = parseInt(iso.slice(8, 10), 10);
  }
  const today  = new Date();
  const viewY  = (selY && selY <= 2100) ? selY : today.getFullYear();
  const viewM  = (selM !== null && selY && selY <= 2100) ? selM : today.getMonth();

  const yearOpts = Array.from({length: 151}, (_, i) => 1950 + i).map(y =>
    `<option value="${y}"${y === viewY ? " selected" : ""}>${y}</option>`).join("");
  const monthOpts = _DP_MONTHS.map((m, i) =>
    `<option value="${i}"${i === viewM ? " selected" : ""}>${m}</option>`).join("");

  let displayVal = "";
  if (iso === "9999-12-31") displayVal = "31-12-9999";
  else if (iso.length >= 10)
    displayVal = `${iso.slice(8,10)}-${iso.slice(5,7)}-${iso.slice(0,4)}`;

  const S = "padding:7px 10px;border:1px solid var(--border);border-radius:var(--radius);font-size:13px;background:var(--surface);color:var(--text);";
  const BTN = "border:none;background:var(--bg);border-radius:4px;padding:4px 9px;cursor:pointer;font-size:13px;color:var(--text);";

  wrap.style.cssText = "position:relative;display:block;";
  wrap.innerHTML = `
    <input type="text" class="dp-display" readonly placeholder="Vælg dato"
      value="${displayVal}"
      style="${S}width:100%;box-sizing:border-box;cursor:pointer;">
    <input type="hidden" class="dp-val" value="${iso}">
    <div class="dp-popup" style="display:none;position:fixed;z-index:10000;
      background:white;border:1px solid var(--border);border-radius:8px;
      box-shadow:0 6px 24px rgba(0,0,0,0.18);padding:12px;width:${_dpPopupWidth(wrap)}px;">
      <div style="display:flex;align-items:center;gap:4px;margin-bottom:10px;">
        <button type="button" class="dp-prev" style="${BTN}">&#9664;</button>
        <select class="dp-month-sel" style="${S}flex:1;padding:4px 6px;">${monthOpts}</select>
        <select class="dp-year-sel"  style="${S}flex:0 0 72px;padding:4px 6px;">${yearOpts}</select>
        <button type="button" class="dp-next" style="${BTN}">&#9654;</button>
      </div>
      <div class="dp-grid"></div>
    </div>`;

  _dpRenderGrid(wrap, viewY, viewM, selY, selM, selD);
  _dpBindEvents(wrap);
}

function _dpPopupWidth(wrap) {
  return wrap.dataset.weeks ? 300 : 264;
}

function _dpRenderGrid(wrap, viewY, viewM, selY, selM, selD) {
  const grid  = wrap.querySelector(".dp-grid");
  const today = new Date(); today.setHours(0,0,0,0);
  const weeks = !!wrap.dataset.weeks;
  const HEAD = "font-size:11px;color:#888;font-weight:600;padding:3px 0;";
  let html = `<div style="display:grid;grid-template-columns:${weeks ? "34px " : ""}repeat(7,1fr);gap:1px;text-align:center;">`;
  if (weeks) html += `<div style="${HEAD}">Uge</div>`;
  _DP_DAYS.forEach(d => {
    html += `<div style="${HEAD}">${d}</div>`;
  });
  const dayBtn = d => {
    const dt  = new Date(viewY, viewM, d);
    const iso = `${viewY}-${String(viewM+1).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
    const isSel  = (selY===viewY && selM===viewM && selD===d);
    const isTod  = (dt.getTime()===today.getTime());
    const isWEnd = (dt.getDay()===0 || dt.getDay()===6);
    let bg = "transparent", fg = isWEnd ? "#999" : "var(--text)", fw = "normal";
    if (isTod && !isSel) { bg="#EBF4FF"; fg="#1a6fbf"; }
    if (isSel)           { bg="#1a6fbf"; fg="white"; fw="600"; }
    return `<button type="button" data-iso="${iso}"
      style="border:none;background:${bg};color:${fg};font-weight:${fw};
        border-radius:4px;padding:5px 0;cursor:pointer;font-size:13px;width:100%;">${d}</button>`;
  };
  const firstDay = new Date(viewY, viewM, 1).getDay();
  const offset   = firstDay === 0 ? 6 : firstDay - 1;
  const dim = new Date(viewY, viewM + 1, 0).getDate();
  if (weeks) {
    // Én række pr. uge: ugenummer (klik = ugens mandag) + 7 dage; dage uden for måneden er tomme.
    for (let first = 1 - offset; first <= dim; first += 7) {
      const monday = new Date(viewY, viewM, first);
      html += `<button type="button" data-iso="${_isoOfDate(monday)}" title="Uge ${isoWeekNumber(monday)}"
        style="border:none;background:#d4edcc;color:#317423;font-weight:600;border-radius:4px;
          padding:5px 0;cursor:pointer;font-size:12px;width:100%;">${isoWeekNumber(monday)}</button>`;
      for (let d = first; d < first + 7; d++) html += (d >= 1 && d <= dim) ? dayBtn(d) : `<div></div>`;
    }
  } else {
    for (let i = 0; i < offset; i++) html += `<div></div>`;
    for (let d = 1; d <= dim; d++) html += dayBtn(d);
  }
  html += `</div>`;
  grid.innerHTML = html;
}

function _dpBindEvents(wrap) {
  const display  = wrap.querySelector(".dp-display");
  const popup    = wrap.querySelector(".dp-popup");
  const valInput = wrap.querySelector(".dp-val");
  const yearSel  = wrap.querySelector(".dp-year-sel");
  const monthSel = wrap.querySelector(".dp-month-sel");

  function selParts() {
    const v = valInput.value;
    if (!v || v.length < 10) return [null, null, null];
    return [parseInt(v.slice(0,4),10), parseInt(v.slice(5,7),10)-1, parseInt(v.slice(8,10),10)];
  }
  function rerender() {
    const [sy,sm,sd] = selParts();
    _dpRenderGrid(wrap, parseInt(yearSel.value,10), parseInt(monthSel.value,10), sy, sm, sd);
  }

  display.addEventListener("click", e => {
    e.stopPropagation();
    const isOpen = popup.style.display !== "none";
    document.querySelectorAll(".dp-popup").forEach(p => p.style.display = "none");
    if (!isOpen) {
      const rect = wrap.getBoundingClientRect();
      const popW = _dpPopupWidth(wrap);
      let left = rect.left;
      if (left + popW > window.innerWidth - 8) left = window.innerWidth - popW - 8;
      popup.style.left = left + "px";
      popup.style.top   = "-9999px";
      popup.style.display = "block";
      const popH = popup.offsetHeight;
      const fitsBelow = rect.bottom + 4 + popH <= window.innerHeight - 8;
      const top = fitsBelow
        ? rect.bottom + 4
        : Math.max(8, rect.top - popH - 4);
      popup.style.top = top + "px";
    }
  });

  popup.addEventListener("click",  e => e.stopPropagation());
  yearSel.addEventListener("change",  rerender);
  monthSel.addEventListener("change", rerender);

  wrap.querySelector(".dp-prev").addEventListener("click", e => {
    e.stopPropagation();
    let m = parseInt(monthSel.value,10)-1, y = parseInt(yearSel.value,10);
    if (m < 0) { m=11; y--; }
    monthSel.value=m; yearSel.value=y; rerender();
  });
  wrap.querySelector(".dp-next").addEventListener("click", e => {
    e.stopPropagation();
    let m = parseInt(monthSel.value,10)+1, y = parseInt(yearSel.value,10);
    if (m>11) { m=0; y++; }
    monthSel.value=m; yearSel.value=y; rerender();
  });

  wrap.querySelector(".dp-grid").addEventListener("click", e => {
    const btn = e.target.closest("button[data-iso]");
    if (!btn) return;
    const iso = btn.dataset.iso;
    valInput.value = iso;
    const [y,m,d] = [parseInt(iso.slice(0,4),10), parseInt(iso.slice(5,7),10)-1, parseInt(iso.slice(8,10),10)];
    display.value = `${String(d).padStart(2,"0")}-${String(m+1).padStart(2,"0")}-${y}`;
    popup.style.display = "none";
    rerender();
    valInput.dispatchEvent(new Event("change"));
  });
}

document.addEventListener("click", () =>
  document.querySelectorAll(".dp-popup").forEach(p => p.style.display = "none"));

function readDatePicker(id) {
  return document.getElementById(id)?.querySelector(".dp-val")?.value || "";
}

function setDatePicker(id, iso) {
  const wrap = document.getElementById(id);
  if (!wrap) return;
  const valInput = wrap.querySelector(".dp-val");
  const display  = wrap.querySelector(".dp-display");
  if (!valInput || !display) return;
  valInput.value = iso || "";
  if (!iso || iso.length < 10) { display.value = ""; return; }
  if (iso === "9999-12-31") { display.value = "31-12-9999"; return; }
  display.value = `${iso.slice(8,10)}-${iso.slice(5,7)}-${iso.slice(0,4)}`;
  const y = parseInt(iso.slice(0,4),10);
  const m = parseInt(iso.slice(5,7),10)-1;
  const d = parseInt(iso.slice(8,10),10);
  const yearSel  = wrap.querySelector(".dp-year-sel");
  const monthSel = wrap.querySelector(".dp-month-sel");
  if (yearSel && y <= 2100) { yearSel.value = y; monthSel.value = m; _dpRenderGrid(wrap, y, m, y, m, d); }
}

// ── Manual activity ────────────────────────────────────────────────────────
function badgeLabel(label) {
  const s = label.toUpperCase();
  if (s.length <= 9) return s;
  return s.slice(0, 7).replace(/[\s.\-]+$/, '') + '..';
}

async function loadAbsenceTypes() {
  try {
    const types = await GET("/api/activities/absence-types");
    state.absenceTypes = types;
    ABSENCE_TYPES.clear();
    const sel = document.getElementById("manual-type");
    sel.innerHTML = "";
    const allTypes = [{ value: "normal", label: "Normal tid" }, { value: "overnatning", label: "Overnatning" }, ...types];
    allTypes.sort((a, b) => a.label.localeCompare(b.label, "da")).forEach(t => {
      TYPE_LABELS[t.value] = t.label;
      if (t.value !== "normal") {
        ABSENCE_LABELS[t.value] = badgeLabel(t.label);
        ABSENCE_TYPES.add(t.value);
      }
      const opt = document.createElement("option");
      opt.value = t.value;
      opt.textContent = t.label;
      sel.appendChild(opt);
    });
    TYPE_LABELS["dob_overnatning"] = "DOB Overnatning";
    ABSENCE_LABELS["dob_overnatning"] = badgeLabel("DOB Overnatning");
    ABSENCE_TYPES.add("dob_overnatning");
  } catch (e) { console.error("loadAbsenceTypes fejlede:", e); }
}

function isoWeekNumber(d) {
  // Regner udelukkende i UTC (ingen lokal-tid-aritmetik), så sommertidsskiftet i
  // marts/oktober ikke stjæler/tilføjer en time og forskyder ugenummeret – det
  // skete tidligere for enhver dato efter forårets skift, fordi datodifferencen
  // blev udregnet i lokal tid (fx 17-08-2026 gav uge 33 i stedet for korrekt 34).
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = (date.getUTCDay() + 6) % 7; // 0 = mandag
  date.setUTCDate(date.getUTCDate() - dayNum + 3); // torsdag i denne uge (ISO 8601-definitionen)
  const firstThursday = new Date(Date.UTC(date.getUTCFullYear(), 0, 4));
  const firstThursdayDayNum = (firstThursday.getUTCDay() + 6) % 7;
  firstThursday.setUTCDate(firstThursday.getUTCDate() - firstThursdayDayNum + 3);
  return 1 + Math.round((date - firstThursday) / 604800000);
}

function updateManualTypeVisibility() {
  const type = document.getElementById("manual-type").value;
  const tilDatoVal = document.getElementById("manual-til-dato")?.value || "";
  const isFerie        = (type === "ferie" || type === "selvbetalt_fridag" || type === "loen_andet_sted_fra" || type === "eksport");
  const isSygdom       = (type === "sygdom" || type === "barn_1sygedag" || type === "paragraf_56_syg" || type === "graviditetsbetinget_sygdom");
  // Kursus/Skole fungerer præcis som afspadsering (garanterede timer pr. dag i en periode, frie tider på én dag).
  const isAfspadsering = (type === "afspadsering" || type === "skole_kursus");
  // Afspadsering er kun dato-kun/periode-visuelt når "Til dato" er udfyldt – enkelt dag beholder redigerbar start-/sluttid (delvis dag).
  const isAfspadseringPeriode = isAfspadsering && !!tilDatoVal;
  const isFeriefri     = (type === "feriefri");
  const isBarsel       = (type === "barsel");
  const isOvernatning  = (type === "overnatning");
  const isCommentOnly  = (type === "__none__");
  const isDateOnly     = isFerie || isSygdom || isFeriefri || isBarsel || isOvernatning || isAfspadseringPeriode;
  const isAbsence      = ABSENCE_TYPES.has(type);
  const isRangeType    = type === "ferie" || type === "selvbetalt_fridag" || type === "loen_andet_sted_fra" || type === "eksport" || isFeriefri || isBarsel || type === "sygdom" || type === "paragraf_56_syg" || type === "graviditetsbetinget_sygdom" || isAfspadseringPeriode || isOvernatning;
  const tilDatoFieldVisible = isRangeType || isAfspadsering;

  // "Ingen (kun kommentar)" skal kun vise Medarbejder + Type + Vagtplan-kommentar –
  // resten af felterne er irrelevante, når der ikke oprettes en rigtig aktivitet.
  document.getElementById("manual-start-group").style.display   = isCommentOnly ? "none" : "";
  document.getElementById("manual-comment-group").style.display = isCommentOnly ? "none" : "";
  document.getElementById("manual-normal-fields").style.display = (isAbsence || isCommentOnly) ? "none" : "";
  document.getElementById("manual-end-group").style.display     = (isDateOnly || isCommentOnly) ? "none" : "";
  document.getElementById("manual-reg-group").style.display     = isCommentOnly ? "none" : "";
  if (isCommentOnly) {
    document.getElementById("manual-reg").value = "";
    document.getElementById("manual-reg-hint").textContent = "";
  }
  document.getElementById("manual-barsel-group").style.display  = isBarsel ? "" : "none";
  document.getElementById("manual-dob-group").style.display     = isOvernatning ? "" : "none";
  if (!isOvernatning) document.getElementById("manual-dob").checked = false;

  // Skjul/vis tidsfeltet i startpickeren (kun dato for ferie og sygdom)
  const startEl = document.getElementById("manual-start");
  if (startEl) {
    const timeEl = startEl.querySelector(".dt-time");
    if (timeEl) timeEl.style.display = isDateOnly ? "none" : "";
    startEl.style.maxWidth = isDateOnly ? "220px" : "";
  }

  // Skift label Starttid ↔ Fra dato / Dato
  const lbl = document.querySelector("#manual-start-group label");
  if (lbl) lbl.innerHTML = isRangeType
    ? `Fra dato <span style="color:var(--danger)">*</span>`
    : isDateOnly
      ? `Dato <span style="color:var(--danger)">*</span>`
      : `Starttid <span style="color:var(--danger)">*</span>`;

  if (isAbsence) {
    ["manual-loading", "manual-unloading", "manual-km-start", "manual-km-end"].forEach(id => {
      document.getElementById(id).value = "";
    });
    document.getElementById("manual-salt").checked = false;
  }
  // Gentagelse (Vagtplan): kun startdato – ingen til-dato, sluttid, pauser eller klokkeslæt.
  // Startdatoen vises også ved "Ingen (kun kommentar)", da den er seriens start.
  const repeatOn = _isRepeatOn();
  document.getElementById("manual-til-dato-group").style.display = (tilDatoFieldVisible && !repeatOn) ? "" : "none";
  if (!tilDatoFieldVisible || repeatOn) document.getElementById("manual-til-dato").value = "";
  const pauseSection = document.getElementById("manual-pause-section");
  if (pauseSection) pauseSection.style.display = (isDateOnly || isCommentOnly || repeatOn) ? "none" : "";
  // "Overnatning"-fluebenet under Pauser findes kun for Normal tid.
  const overnightAllowed = type === "normal" && !repeatOn;
  document.getElementById("manual-overnight-group").style.display = overnightAllowed ? "" : "none";
  if (!overnightAllowed) _resetManualOvernight();
  if (repeatOn) {
    document.getElementById("manual-end-group").style.display = "none";
    document.getElementById("manual-start-group").style.display = "";
    const timeEl = document.getElementById("manual-start")?.querySelector(".dt-time");
    if (timeEl) timeEl.style.display = "none";
    const startLbl = document.querySelector("#manual-start-group label");
    if (startLbl) startLbl.innerHTML = `Startdato <span style="color:var(--danger)">*</span>`;
  }

  if (isFerie)        applyFerieDefaults();
  if (isSygdom)       applySygdomDefaults();
  if (isAfspadsering) applyAfspadseringDefaults();
  if (isFeriefri)     applyFeriefriDefaults();
  if (isBarsel) {
    applySygdomDefaults();
    applyBarselTerminsdatoDefault();
  }
  applyAbsenceVehicleDefault();
  applyDagsplanVehicleDefault();
}

// Foreslår medarbejderens "Vognnummer ved fravær" ved fraværsregistrering.
// Disponentgruppens vogn bruges IKKE som fallback. Overskriver ikke et
// allerede udfyldt felt.
function applyAbsenceVehicleDefault() {
  const type = document.getElementById("manual-type").value;
  if (type === "overnatning" || !ABSENCE_TYPES.has(type)) return;
  const regField = document.getElementById("manual-reg");
  if (regField.value.trim()) return;
  const empId = parseInt(document.getElementById("manual-employee").value);
  const emp = state.employees.find(e => e.id === empId);
  const vehicleNumber = emp?.absence_vehicle_number;
  if (vehicleNumber) {
    regField.value = vehicleNumber;
    _updateManualRegHint(); // kun hint - IKKE _renderManualRegDropdown, feltet er allerede udfyldt korrekt
    document.getElementById("manual-reg-dropdown").style.display = "none";
  }
}

// Foreslår vognnummeret fra Dagsplanens tildeling (eller medarbejderens
// "Fast bil") for "normal tid"-aktiviteter, dvs. samme kilde som
// autoudfyldningen på serveren i create_manual_activity(). Overskriver ikke
// et allerede udfyldt felt. Kræver dagsplan_view - fejler brugeren ikke
// permission, forbliver feltet blot tomt (kan stadig udfyldes manuelt).
async function applyDagsplanVehicleDefault() {
  const type = document.getElementById("manual-type").value;
  if (type !== "normal") return;
  const regField = document.getElementById("manual-reg");
  if (regField.value.trim()) return;
  const empId = parseInt(document.getElementById("manual-employee").value);
  const dateStr = document.getElementById("manual-start")?.querySelector(".dt-date")?.value;
  if (!empId || !dateStr) return;
  try {
    const data = await GET(`/api/dagsplan?date=${dateStr}&employee_id=${empId}`);
    const match = data.vehicles.find(v => v.employee_id === empId);
    if (match && !regField.value.trim()) {
      regField.value = match.vehicle_number;
      _updateManualRegHint(); // kun hint - IKKE _renderManualRegDropdown, feltet er allerede udfyldt korrekt
      document.getElementById("manual-reg-dropdown").style.display = "none";
    }
  } catch (_) { /* ingen dagsplan_view-adgang eller ingen tildeling - lad feltet være tomt */ }
}

// Foreslår medarbejderens seneste registrerede terminsdato ved oprettelse af en ny barsel-aktivitet.
// force=true overskriver et allerede udfyldt felt (bruges ved skift af medarbejder).
function applyBarselTerminsdatoDefault(force = false) {
  const field = document.getElementById("manual-terminsdato");
  if (!field) return;
  if (!force && field.value) return;
  const empId = parseInt(document.getElementById("manual-employee").value);
  const emp = state.employees.find(e => e.id === empId);
  field.value = (emp && emp.terminsdato) || "";
}

function applyFerieDefaults() {
  const empId = parseInt(document.getElementById("manual-employee").value);
  const dateStr = document.getElementById("manual-start")?.querySelector(".dt-date")?.value;
  if (!empId || !dateStr) return;

  const emp = state.employees.find(e => e.id === empId);
  if (!emp || !emp.work_schedule) return;

  const d = new Date(dateStr + "T12:00:00");
  const weekNum = isoWeekNumber(d);
  const key = weekNum % 2 === 0 ? "even" : "odd";
  const weekdayIdx = (d.getDay() + 6) % 7;
  const hours = emp.work_schedule[key]?.[weekdayIdx] ?? 0;

  // Fallback til 7,4 timer hvis ingen normaltid på dagen
  const effectiveHours = hours > 0 ? hours : 7.4;
  const totalMinutes = Math.round(effectiveHours * 60);
  const endH = 6 + Math.floor(totalMinutes / 60);
  const endM = totalMinutes % 60;
  const endHH = String(endH).padStart(2, "0") + ":" + String(endM).padStart(2, "0");

  setDatetimePicker("manual-start", dateStr + "T06:00");
  setDatetimePicker("manual-end",   dateStr + "T" + endHH);
}

function applySygdomDefaults() {
  const empId = parseInt(document.getElementById("manual-employee").value);
  const dateStr = document.getElementById("manual-start")?.querySelector(".dt-date")?.value;
  if (!empId || !dateStr) return;

  const emp = state.employees.find(e => e.id === empId);
  if (!emp || !emp.work_schedule) return;

  const d = new Date(dateStr + "T12:00:00");
  const weekNum = isoWeekNumber(d);
  const key = weekNum % 2 === 0 ? "even" : "odd";
  const weekdayIdx = (d.getDay() + 6) % 7;
  const hours = emp.work_schedule[key]?.[weekdayIdx] ?? 0;

  const effectiveHours = hours > 0 ? hours : 7.4;
  const totalMinutes = Math.round(effectiveHours * 60);
  const endH = 6 + Math.floor(totalMinutes / 60);
  const endM = totalMinutes % 60;
  const endHH = String(endH).padStart(2, "0") + ":" + String(endM).padStart(2, "0");

  setDatetimePicker("manual-start", dateStr + "T06:00");
  setDatetimePicker("manual-end",   dateStr + "T" + endHH);
}

function applyAfspadseringDefaults() {
  const empId = parseInt(document.getElementById("manual-employee").value);
  const dateStr = document.getElementById("manual-start")?.querySelector(".dt-date")?.value;
  if (!empId || !dateStr) return;

  const emp = state.employees.find(e => e.id === empId);
  const d = new Date(dateStr + "T12:00:00");
  const key = isoWeekNumber(d) % 2 === 0 ? "even" : "odd";
  const weekdayIdx = (d.getDay() + 6) % 7;
  const hours = emp?.work_schedule?.[key]?.[weekdayIdx] ?? 0;

  if (hours <= 0) {
    toast("Ingen garanterede timer på denne dag – angiv tid manuelt", "warning");
    return;
  }

  const totalMinutes = Math.round(hours * 60);
  const endH = String(6 + Math.floor(totalMinutes / 60)).padStart(2, "0");
  const endM = String(totalMinutes % 60).padStart(2, "0");

  setDatetimePicker("manual-start", dateStr + "T06:00");
  setDatetimePicker("manual-end",   dateStr + "T" + endH + ":" + endM);
}

function applyFeriefriDefaults() {
  const dateStr = document.getElementById("manual-start")?.querySelector(".dt-date")?.value;
  if (!dateStr) return;
  // Altid 7,4 timer fra 06:00 – uanset medarbejderens normale tid
  const totalEndMin = 6 * 60 + Math.round(7.4 * 60);  // 06:00 + 7h24m = 13:24
  const endH = String(Math.floor(totalEndMin / 60)).padStart(2, "0");
  const endM = String(totalEndMin % 60).padStart(2, "0");
  setDatetimePicker("manual-start", dateStr + "T06:00");
  setDatetimePicker("manual-end",   dateStr + "T" + endH + ":" + endM);
}

function renderManualPauses() {
  const list = document.getElementById("manual-pauses-list");
  if (!list) return;
  if (!manualPauses.length) { list.innerHTML = ""; return; }
  list.innerHTML = manualPauses.map((p, i) => `
    <div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--bg);border-radius:4px;margin-bottom:4px;font-size:13px">
      <span style="font-weight:600;min-width:56px;color:var(--primary)">Pause ${i + 1}</span>
      <span>${p[0].slice(8,10)}.${p[0].slice(5,7)} ${p[0].slice(11,16)} – ${p[1].slice(8,10)}.${p[1].slice(5,7)} ${p[1].slice(11,16)}</span>
      <button type="button" onclick="editManualPause(${i})" style="margin-left:auto;font-size:11px;padding:2px 7px;cursor:pointer">Ret</button>
      <button type="button" onclick="deleteManualPause(${i})" style="background:none;border:none;color:var(--danger);cursor:pointer;font-size:18px;line-height:1;padding:0">&times;</button>
    </div>
  `).join("");
}

function addManualPause() {
  const startIso = readDatetimePicker("manual-start");
  if (!startIso) { toast("Angiv starttidspunkt for aktiviteten først", "error"); return; }
  _pauseEditState = { mode: "create", idx: null };
  const n = manualPauses.length + 1;
  document.getElementById("pause-modal-title").textContent = "Pause " + n;
  const dateStr = startIso.slice(0, 10);
  buildDatetimePicker("pause-start", dateStr + "T00:00");
  buildDatetimePicker("pause-end",   dateStr + "T00:00");
  _stackDatetimePicker("pause-start");
  _stackDatetimePicker("pause-end");
  openModal("modal-pause");
}

function _validateAndStoreManualPause(startIso, endIso) {
  const actStart = readDatetimePicker("manual-start");
  const actEnd   = readDatetimePicker("manual-end");
  if (actStart && startIso < actStart) {
    toast(`Pausen starter (${startIso.slice(11, 16)}) før vagten begynder (${actStart.slice(11, 16)})`, "error");
    return false;
  }
  if (actEnd && endIso > actEnd) {
    toast(`Pausen slutter (${endIso.slice(11, 16)}) efter vagten er slut (${actEnd.slice(11, 16)})`, "error");
    return false;
  }
  const entry = [startIso + ":00", endIso + ":00"];
  if (_pauseEditState?.idx != null) {
    manualPauses[_pauseEditState.idx] = entry;
  } else {
    manualPauses.push(entry);
  }
  renderManualPauses();
  return true;
}

function confirmPause() {
  const startIso = readDatetimePicker("pause-start");
  const endIso   = readDatetimePicker("pause-end");
  if (!startIso || !endIso) { toast("Angiv både start- og sluttidspunkt for pausen", "error"); return; }
  if (endIso <= startIso) { toast("Sluttidspunkt skal være efter starttidspunkt", "error"); return; }
  if (_pauseEditState?.mode === "activity") {
    _confirmActivityPauseEdit(startIso, endIso);
    return;
  }
  if (_validateAndStoreManualPause(startIso, endIso)) {
    closeModal("modal-pause");
  }
}

function addPauseSuggestion(startHHMM, endHHMM) {
  const actStartIso = readDatetimePicker("manual-start");
  if (!actStartIso) { toast("Angiv starttidspunkt for aktiviteten først", "error"); return; }
  const dateStr = actStartIso.slice(0, 10);
  _pauseEditState = { mode: "create", idx: null };
  _validateAndStoreManualPause(dateStr + "T" + startHHMM, dateStr + "T" + endHHMM);
}

function deleteManualPause(idx) {
  manualPauses.splice(idx, 1);
  renderManualPauses();
}

function editManualPause(idx) {
  _pauseEditState = { mode: "create", idx };
  const p = manualPauses[idx];
  document.getElementById("pause-modal-title").textContent = `Ret pause ${idx + 1}`;
  buildDatetimePicker("pause-start", p[0].slice(0, 16));
  buildDatetimePicker("pause-end",   p[1].slice(0, 16));
  _stackDatetimePicker("pause-start");
  _stackDatetimePicker("pause-end");
  openModal("modal-pause");
}

function openActivityPauseEdit(actId, idx) {
  const a = state.activities.find(x => x.id === actId);
  if (!a || !a.pause_intervals) return;
  const p = a.pause_intervals[idx];
  if (!p) return;
  _pauseEditState = { mode: "activity", activityId: actId, idx };
  document.getElementById("pause-modal-title").textContent = `Ret pause ${idx + 1}`;
  buildDatetimePicker("pause-start", p[0].slice(0, 16));
  buildDatetimePicker("pause-end",   p[1].slice(0, 16));
  _stackDatetimePicker("pause-start");
  _stackDatetimePicker("pause-end");
  openModal("modal-pause");
}

function openActivityPauseAdd(actId) {
  const a = state.activities.find(x => x.id === actId);
  if (!a) return;
  _pauseEditState = { mode: "activity", activityId: actId, idx: null };
  const n = (a.pause_intervals ? a.pause_intervals.length : 0) + 1;
  document.getElementById("pause-modal-title").textContent = "Pause " + n;
  const dateStr = a.start_time.slice(0, 10);
  buildDatetimePicker("pause-start", dateStr + "T00:00");
  buildDatetimePicker("pause-end",   dateStr + "T00:00");
  _stackDatetimePicker("pause-start");
  _stackDatetimePicker("pause-end");
  openModal("modal-pause");
}

function addActivityPauseSuggestion(actId, startHHMM, endHHMM) {
  const a = state.activities.find(x => x.id === actId);
  if (!a) return;
  const dateStr = a.start_time.slice(0, 10);
  _pauseEditState = { mode: "activity", activityId: actId, idx: null };
  _confirmActivityPauseEdit(dateStr + "T" + startHHMM, dateStr + "T" + endHHMM);
}

async function _confirmActivityPauseEdit(startIso, endIso) {
  const { activityId, idx } = _pauseEditState;
  const a = state.activities.find(x => x.id === activityId);
  if (!a) return;
  if (startIso < a.start_time.slice(0, 16)) {
    toast(`Pausen starter (${startIso.slice(11, 16)}) før vagten begynder (${a.start_time.slice(11, 16)})`, "error");
    return;
  }
  if (endIso > a.end_time.slice(0, 16)) {
    toast(`Pausen slutter (${endIso.slice(11, 16)}) efter vagten er slut (${a.end_time.slice(11, 16)})`, "error");
    return;
  }
  const newPauses = idx == null
    ? [...(a.pause_intervals || []), [startIso + ":00", endIso + ":00"]]
    : a.pause_intervals.map((p, i) => i === idx ? [startIso + ":00", endIso + ":00"] : p);
  try {
    const updated = await PATCH(`/api/activities/${activityId}`, { pause_intervals: newPauses });
    state.activities = state.activities.map(x => x.id === activityId ? updated : x);
    closeModal("modal-pause");
    const body = document.getElementById("modal-activity-body");
    const scrollTop = body ? body.scrollTop : 0;
    openActivityDetail(activityId);
    if (body) body.scrollTop = scrollTop;
    renderActivitiesTable();
    toast(idx == null ? "Pause tilføjet" : "Pause opdateret", "success");
  } catch (e) { toast(e.message || "Fejl ved opdatering af pause", "error"); }
}

async function deleteActivityPause(actId, idx) {
  const a = state.activities.find(x => x.id === actId);
  if (!a) return;
  const newPauses = a.pause_intervals.filter((_, i) => i !== idx);
  try {
    const updated = await PATCH(`/api/activities/${actId}`, { pause_intervals: newPauses });
    state.activities = state.activities.map(x => x.id === actId ? updated : x);
    const body = document.getElementById("modal-activity-body");
    const scrollTop = body ? body.scrollTop : 0;
    openActivityDetail(actId);
    if (body) body.scrollTop = scrollTop;
    renderActivitiesTable();
    toast("Pause slettet", "success");
  } catch (e) { toast(e.message || "Fejl ved sletning af pause", "error"); }
}

function _updateManualRegHint() {
  const field = document.getElementById("manual-reg");
  const reg = field.value.trim().toUpperCase();
  field.value = reg;
  const hint = document.getElementById("manual-reg-hint");
  if (!reg) { hint.textContent = ""; return; }
  const v = state.vehicles.find(x =>
    x.registration_number.toUpperCase() === reg ||
    x.vehicle_number.toUpperCase() === reg
  );
  if (v) {
    hint.textContent = `Vogn nr. ${v.vehicle_number} – reg. ${v.registration_number} fundet`;
    hint.style.color = "var(--success, #059669)";
  } else {
    hint.textContent = "Registreringsnummer/vognnummer ikke fundet i Vognpark";
    hint.style.color = "var(--danger, #dc2626)";
  }
}

let _manualRegHighlightIndex = -1;

function _renderManualRegDropdown(query) {
  const dropdown = document.getElementById("manual-reg-dropdown");
  const q = query.trim().toUpperCase();
  const matches = !q ? state.vehicles : state.vehicles.filter(v =>
    v.vehicle_number.toUpperCase().includes(q) || v.registration_number.toUpperCase().includes(q)
  );
  _manualRegHighlightIndex = -1;
  dropdown.innerHTML = matches.length
    ? matches.map(v => `
        <div class="vehicle-search-item" data-num="${h(v.vehicle_number)}"
             style="padding:8px 10px;cursor:pointer;font-size:13px">
          ${h(v.vehicle_number)} <span style="color:var(--text-light)">– ${h(v.registration_number)}</span>
        </div>`).join("")
    : `<div style="padding:8px 10px;color:var(--text-light);font-size:13px">Ingen køretøjer fundet</div>`;
  dropdown.querySelectorAll(".vehicle-search-item").forEach((el, idx) => {
    el.addEventListener("mouseover", () => _setManualRegHighlight(idx));
    el.addEventListener("mouseout",  () => _setManualRegHighlight(-1));
    el.addEventListener("click", () => _selectManualRegVehicle(el.dataset.num));
  });
  dropdown.style.display = "block";
}

function _setManualRegHighlight(index) {
  const dropdown = document.getElementById("manual-reg-dropdown");
  const items = dropdown.querySelectorAll(".vehicle-search-item[data-num]");
  items.forEach((el, i) => { el.style.background = i === index ? "var(--bg)" : ""; });
  _manualRegHighlightIndex = index;
}

function _moveManualRegHighlight(delta) {
  const dropdown = document.getElementById("manual-reg-dropdown");
  const items = dropdown.querySelectorAll(".vehicle-search-item[data-num]");
  if (!items.length) return;
  let next = _manualRegHighlightIndex + delta;
  if (next < 0) next = items.length - 1;
  if (next >= items.length) next = 0;
  _setManualRegHighlight(next);
  items[next].scrollIntoView({ block: "nearest" });
}

function _selectManualRegHighlighted() {
  const dropdown = document.getElementById("manual-reg-dropdown");
  const items = dropdown.querySelectorAll(".vehicle-search-item[data-num]");
  if (_manualRegHighlightIndex >= 0 && items[_manualRegHighlightIndex]) {
    _selectManualRegVehicle(items[_manualRegHighlightIndex].dataset.num);
    return true;
  }
  return false;
}

function _selectManualRegVehicle(vehicleNumber) {
  document.getElementById("manual-reg").value = vehicleNumber;
  document.getElementById("manual-reg-dropdown").style.display = "none";
  _updateManualRegHint();
}

document.addEventListener("click", (e) => {
  if (!e.target.closest("#manual-reg, #manual-reg-dropdown")) {
    const dropdown = document.getElementById("manual-reg-dropdown");
    if (dropdown) dropdown.style.display = "none";
  }
});

// ── Gentagelse i Vagtplan (spec 2026-10-07) ─────────────────────────────────
const _WEEKDAY_NAMES_DA = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"];

function _isRepeatOn() {
  return _manualActivityContext.vagtplan && document.getElementById("manual-repeat").checked;
}

// Spejler calculators/recurrence.py:describe() for månedligt mønster.
function _monthlyLabel(dateIso) {
  if (!dateIso) return "";
  const d = new Date(dateIso + "T12:00:00");
  const nth = Math.floor((d.getDate() - 1) / 7) + 1;
  const day = _WEEKDAY_NAMES_DA[(d.getDay() + 6) % 7];
  return nth >= 5 ? `Sidste ${day} i måneden` : `Hver ${nth}. ${day} i måneden`;
}

function _manualStartDateIso() {
  return document.getElementById("manual-start")?.querySelector(".dt-date")?.value || "";
}

function _updateRepeatUi() {
  const on = _isRepeatOn();
  document.getElementById("manual-repeat-fields").style.display = on ? "" : "none";
  const freq = document.querySelector('input[name="manual-repeat-freq"]:checked').value;
  document.getElementById("manual-repeat-weekdays").style.display = freq === "weekly" ? "flex" : "none";
  document.getElementById("manual-repeat-interval-row").style.display = freq === "weekly" ? "flex" : "none";
  const lbl = document.getElementById("manual-repeat-monthly-label");
  lbl.style.display = freq === "monthly" ? "" : "none";
  lbl.textContent = _monthlyLabel(_manualStartDateIso());
  const startIso = _manualStartDateIso();
  const endDate = document.getElementById("manual-repeat-end-date");
  endDate.min = startIso;
  if (startIso) {
    const max = new Date(startIso + "T12:00:00");
    max.setFullYear(max.getFullYear() + 1);
    endDate.max = _isoOfDate(max);
  }
  updateManualTypeVisibility();
}

// Forvælg startdatoens ugedag (kun når ingen ugedag er valgt endnu).
function _preselectRepeatWeekday() {
  const iso = _manualStartDateIso();
  const boxes = [...document.querySelectorAll(".manual-repeat-wd")];
  if (!iso || boxes.some(b => b.checked)) return;
  const idx = (new Date(iso + "T12:00:00").getDay() + 6) % 7;
  boxes[idx].checked = true;
}

function _readRepeatRule() {
  const freq = document.querySelector('input[name="manual-repeat-freq"]:checked').value;
  const weekdays = [...document.querySelectorAll(".manual-repeat-wd:checked")].map(b => parseInt(b.value));
  if (freq === "weekly" && weekdays.length === 0) { toast("Vælg mindst én ugedag", "error"); return null; }
  const end_mode = document.querySelector('input[name="manual-repeat-end"]:checked').value;
  const interval = parseInt(document.getElementById("manual-repeat-interval").value);
  if (freq === "weekly" && !(interval >= 1 && interval <= 4)) { toast("Hver N. uge skal være 1–4", "error"); return null; }
  const rule = { freq, weekdays: freq === "weekly" ? weekdays : [], week_interval: freq === "weekly" ? interval : 1,
                 end_mode, end_count: null, end_date: null };
  if (end_mode === "count") {
    const n = parseInt(document.getElementById("manual-repeat-count").value);
    if (!(n >= 1 && n <= 100)) { toast("Antal gentagelser skal være 1–100", "error"); return null; }
    rule.end_count = n;
  } else {
    const d = document.getElementById("manual-repeat-end-date").value;
    if (!d) { toast("Angiv slutdato for gentagelsen", "error"); return null; }
    rule.end_date = d;
  }
  return rule;
}

async function _createVagtplanSeries(empId, actType, startDate) {
  const rule = _readRepeatRule();
  if (!rule) return;
  const commentText = document.getElementById("manual-vagtplan-comment").value.trim() || null;
  const isCommentOnly = actType === "__none__";
  if (isCommentOnly && !commentText) { toast("Skriv en kommentar", "error"); return; }
  let vehicleNumber = null;
  if (!isCommentOnly && actType !== "overnatning") {
    const regInput = document.getElementById("manual-reg").value.trim().toUpperCase();
    if (!regInput) { toast("Registreringsnummer / Vognnummer er påkrævet", "error"); return; }
    const v = state.vehicles.find(x => x.registration_number.toUpperCase() === regInput || x.vehicle_number.toUpperCase() === regInput);
    if (!v) { openModal("modal-reg-error"); return; }
    vehicleNumber = v.vehicle_number;
  }
  const terminsdato = document.getElementById("manual-terminsdato").value || null;
  if (actType === "barsel" && !terminsdato) { toast("Angiv terminsdato for barsel", "error"); return; }
  const payload = {
    employee_id: empId,
    activity_type: isCommentOnly ? null : actType,
    comment_text: commentText,
    vehicle_number: vehicleNumber,
    terminsdato,
    start_date: startDate,
    ...rule,
  };
  const fmt = d => { const [y, m, day] = d.split("-"); return `${day}-${m}-${y}`; };
  let preview;
  try { preview = await POST("/api/vagtplan-series/preview", payload); }
  catch (e) { toast(e.message, "error"); return; }
  if (preview.locked_dates.length) {
    toast(`Kan ikke oprette – lønperioden er låst for: ${preview.locked_dates.map(fmt).join(", ")}`, "error");
    return;
  }
  const lines = [`${preview.description}: ${preview.dates.length} forekomster (${fmt(preview.dates[0])} – ${fmt(preview.dates[preview.dates.length - 1])}).`];
  if (preview.driving_conflicts.length) lines.push(`Der er registreret kørsel på: ${preview.driving_conflicts.map(fmt).join(", ")}.`);
  if (preview.comment_conflicts.length) lines.push(`Der findes allerede en kommentar på: ${preview.comment_conflicts.map(fmt).join(", ")} – den overskrives ikke.`);
  if (preview.skipped_no_hours.length) lines.push(`Springes over (ingen garanterede timer): ${preview.skipped_no_hours.map(fmt).join(", ")}.`);
  if (!window.confirm(lines.join("\n\n") + "\n\nOpret gentagelsen?")) return;
  try {
    const res = await POST("/api/vagtplan-series", payload);
    toast(`${res.created} forekomster oprettet`, "success");
    closeModal("modal-manual-activity");
    await loadVagtplan();
  } catch (e) { toast(e.message, "error"); }
}

function _renderSeriesSection(series, occurrenceDate, canEdit) {
  const isCount = series.end_mode === "count";
  const countVal = series.occurrence_count;
  const dateVal = series.end_date || series.last_date || "";
  const maxD = new Date(series.start_date + "T12:00:00");
  maxD.setFullYear(maxD.getFullYear() + 1);
  const controls = canEdit ? `
      <div style="display:flex;flex-direction:column;gap:6px;margin:8px 0">
        <label style="display:flex;align-items:center;gap:6px">
          <input type="radio" name="series-end-mode" value="count" ${isCount ? "checked" : ""}> Efter
          <input type="number" id="series-end-count" min="1" max="100" value="${countVal}" style="width:70px"> gange
        </label>
        <label style="display:flex;align-items:center;gap:6px">
          <input type="radio" name="series-end-mode" value="date" ${isCount ? "" : "checked"}> Den
          <input type="date" id="series-end-date" value="${dateVal}" min="${series.first_date || series.start_date}" max="${_isoOfDate(maxD)}" style="width:170px">
        </label>
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        <button type="button" class="btn btn-secondary" style="font-size:13px;padding:5px 14px" onclick="saveSeriesEnd(${series.id})">Gem for serien</button>
        <button type="button" class="btn btn-secondary" style="font-size:13px;padding:5px 14px" onclick="deleteSeriesOccurrence(${series.id}, '${occurrenceDate}')">Slet denne forekomst</button>
        <button type="button" class="btn btn-danger" style="font-size:13px;padding:5px 14px" onclick="deleteWholeSeries(${series.id})">Slet hele serien</button>
      </div>` : "";
  return `
    <div class="form-group" id="series-section" style="margin-bottom:14px;padding:10px;background:var(--bg);border-radius:var(--radius)">
      <label style="font-weight:500;font-size:12px;text-transform:uppercase;color:var(--text-light);margin-bottom:6px;display:block">Gentagelse</label>
      <div style="font-size:13px">${h(series.description)} – ${series.occurrence_count} forekomster (${formatDate(series.first_date)} – ${formatDate(series.last_date)})</div>
      ${controls}
    </div>`;
}

async function _afterSeriesChange() {
  closeAllModals();
  if (state.currentView === "vagtplan") await loadVagtplan();
  else await refreshActivities();
}

async function saveSeriesEnd(seriesId) {
  const mode = document.querySelector('input[name="series-end-mode"]:checked')?.value;
  const body = { end_mode: mode, end_count: null, end_date: null };
  if (mode === "count") {
    const n = parseInt(document.getElementById("series-end-count").value);
    if (!(n >= 1 && n <= 100)) { toast("Antal gentagelser skal være 1–100", "error"); return; }
    body.end_count = n;
  } else {
    const d = document.getElementById("series-end-date").value;
    if (!d) { toast("Angiv slutdato", "error"); return; }
    body.end_date = d;
  }
  try {
    const r = await PATCH(`/api/vagtplan-series/${seriesId}`, body);
    toast(`Gentagelse opdateret – ${r.added} tilføjet, ${r.removed} fjernet`, "success");
    if (r.skipped_comments.length) toast(`Kommentar ikke oprettet (findes allerede) på ${r.skipped_comments.length} dag(e)`, "warning");
    if (r.skipped_no_hours.length) toast(`${r.skipped_no_hours.length} dag(e) sprunget over – ingen garanterede timer`, "warning");
    await _afterSeriesChange();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteSeriesOccurrence(seriesId, dateIso) {
  if (!window.confirm(`Slet forekomsten d. ${formatDate(dateIso)}?`)) return;
  try {
    await DEL(`/api/vagtplan-series/${seriesId}/occurrences/${dateIso}`);
    toast("Forekomst slettet", "success");
    await _afterSeriesChange();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteWholeSeries(seriesId) {
  if (!window.confirm("Slet hele serien? Alle forekomster slettes permanent (undtagen i låste lønperioder).")) return;
  try {
    const r = await DEL(`/api/vagtplan-series/${seriesId}`);
    const kept = r.kept_locked + r.kept_split;
    toast(kept ? `${r.deleted} forekomster slettet – ${kept} er bevaret (låst lønperiode eller splittet)` : `${r.deleted} forekomster slettet`, "success");
    await _afterSeriesChange();
  } catch (e) { toast(e.message, "error"); }
}

async function openManualActivityModal(empId = null, dateIso = null, opts = {}) {
  // Klik på en dato i en låst lønperiode: advar FØR modalen åbnes (tjekkes igen ved gem).
  if (dateIso && await _rejectIfLockedDates([dateIso])) return;
  _manualActivityContext = { vagtplan: !!opts.vagtplan };
  document.getElementById("manual-employee").innerHTML =
    state.employees.filter(e => e.active)
      .slice().sort((a, b) => a.name.localeCompare(b.name, "da"))
      .map(e => `<option value="${e.id}">${h(e.name)} (${h(e.employee_number)})</option>`).join("");
  buildDatetimePicker("manual-start", null);
  buildDatetimePicker("manual-end",   null);
  ["manual-loading", "manual-unloading", "manual-comment", "manual-vagtplan-comment", "manual-km-start", "manual-km-end"]
    .forEach(id => document.getElementById(id).value = "");
  document.getElementById("manual-reg").value = "";
  document.getElementById("manual-reg-hint").textContent = "";
  document.getElementById("manual-salt").checked = false;
  document.getElementById("manual-dob").checked = false;
  _resetManualOvernight();
  document.getElementById("manual-add-overnight").onchange = _onManualOvernightToggle;
  document.getElementById("modal-manual-overnight")._onClose = cancelManualOvernight;
  document.getElementById("manual-vagtplan-comment-group").style.display = _manualActivityContext.vagtplan ? "" : "none";
  document.getElementById("manual-repeat-group").style.display = _manualActivityContext.vagtplan ? "" : "none";
  document.getElementById("manual-repeat").checked = false;
  // Valgmulighederne vises kun når Gentagelse er afkrydset – skjul rester fra sidste åbning.
  document.getElementById("manual-repeat-fields").style.display = "none";
  document.querySelector('input[name="manual-repeat-freq"][value="weekly"]').checked = true;
  document.querySelector('input[name="manual-repeat-end"][value="count"]').checked = true;
  document.getElementById("manual-repeat-count").value = "4";
  document.getElementById("manual-repeat-interval").value = "1";
  document.getElementById("manual-repeat-end-date").value = "";
  document.querySelectorAll(".manual-repeat-wd").forEach(b => b.checked = false);
  document.getElementById("manual-repeat").onchange = () => { _preselectRepeatWeekday(); _updateRepeatUi(); };
  document.querySelectorAll('input[name="manual-repeat-freq"]').forEach(r => r.onchange = _updateRepeatUi);

  const typeSelect = document.getElementById("manual-type");
  const existingNoneOpt = typeSelect.querySelector('option[value="__none__"]');
  if (_manualActivityContext.vagtplan && !existingNoneOpt) {
    const opt = document.createElement("option");
    opt.value = "__none__";
    opt.textContent = "Ingen (kun kommentar)";
    typeSelect.insertBefore(opt, typeSelect.firstChild);
  } else if (!_manualActivityContext.vagtplan && existingNoneOpt) {
    existingNoneOpt.remove();
  }
  // "Normal tid" er en kørselsregistrering og skal ikke kunne oprettes fra Vagtplan.
  const normalOpt = typeSelect.querySelector('option[value="normal"]');
  if (normalOpt) normalOpt.hidden = _manualActivityContext.vagtplan;
  document.getElementById("manual-reg").oninput = function () {
    _updateManualRegHint();
    _renderManualRegDropdown(this.value);
  };
  document.getElementById("manual-reg").onfocus = function () {
    _renderManualRegDropdown(this.value);
  };
  document.getElementById("manual-reg").onkeydown = function (e) {
    const dropdown = document.getElementById("manual-reg-dropdown");
    if (dropdown.style.display !== "block") return;
    if (e.key === "Tab" || e.key === "ArrowDown") {
      e.preventDefault();
      _moveManualRegHighlight(e.shiftKey ? -1 : 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      _moveManualRegHighlight(-1);
    } else if (e.key === "Enter") {
      if (_selectManualRegHighlighted()) e.preventDefault();
    } else if (e.key === "Escape") {
      dropdown.style.display = "none";
    }
  };
  document.getElementById("manual-type").value = _manualActivityContext.vagtplan ? "ferie" : "normal";
  document.getElementById("manual-terminsdato").value = "";
  document.getElementById("manual-til-dato").value = "";
  manualPauses = [];
  renderManualPauses();
  updateManualTypeVisibility();

  document.getElementById("manual-type").onchange = updateManualTypeVisibility;
  document.getElementById("manual-til-dato").onchange = updateManualTypeVisibility;
  // "Til dato"-kalenderen skal åbne ved startdatoen i stedet for dags dato – min sættes
  // lige før kalenderen åbnes, så den altid følger den aktuelle startdato.
  document.getElementById("manual-til-dato").onmousedown =
  document.getElementById("manual-til-dato").onfocus = function () {
    this.min = document.getElementById("manual-start")?.querySelector(".dt-date")?.value || "";
  };
  document.getElementById("manual-employee").onchange = () => {
    const t = document.getElementById("manual-type").value;
    if (t === "ferie" || t === "selvbetalt_fridag" || t === "loen_andet_sted_fra" || t === "eksport") applyFerieDefaults();
    if (t === "sygdom" || t === "barn_1sygedag" || t === "paragraf_56_syg" || t === "barsel") applySygdomDefaults();
    if (t === "afspadsering" || t === "skole_kursus") applyAfspadseringDefaults();
    if (t === "feriefri")                           applyFeriefriDefaults();
    if (t === "barsel")                             applyBarselTerminsdatoDefault(true);
    document.getElementById("manual-reg").value = "";
    document.getElementById("manual-reg-hint").textContent = "";
    applyAbsenceVehicleDefault();
    applyDagsplanVehicleDefault();
  };
  // Lyt på dato-ændring inde i dt-picker containeren
  document.getElementById("manual-start").addEventListener("change", (e) => {
    // Kun dato-skift skal udløse standardtider – ellers nulstilles en manuelt
    // rettet starttid (fx delvis afspadseringsdag) straks tilbage til 06:00.
    if (e.target.classList.contains("dt-time")) return;
    const t = document.getElementById("manual-type").value;
    if (t === "ferie" || t === "selvbetalt_fridag" || t === "loen_andet_sted_fra" || t === "eksport") applyFerieDefaults();
    if (t === "sygdom" || t === "barn_1sygedag" || t === "paragraf_56_syg" || t === "barsel") applySygdomDefaults();
    if (t === "afspadsering" || t === "skole_kursus") applyAfspadseringDefaults();
    if (t === "feriefri")                           applyFeriefriDefaults();
    if (t === "normal") {
      const startDate = document.getElementById("manual-start")?.querySelector(".dt-date")?.value;
      const endDateEl = document.getElementById("manual-end")?.querySelector(".dt-date");
      if (startDate && endDateEl) endDateEl.value = startDate;
      applyDagsplanVehicleDefault();
    }
    if (_isRepeatOn()) _updateRepeatUi();
  });

  if (empId) document.getElementById("manual-employee").value = empId;
  if (dateIso) {
    setDatetimePicker("manual-start", dateIso + "T06:00");
    setDatetimePicker("manual-end",   dateIso + "T06:00");
  }
  // Genkør type-afhængige standardværdier nu hvor medarbejder+dato er udfyldt
  // (relevant for Vagtplans "ferie"-default, som skal kende dato/medarbejder for at beregne timer).
  // Vognnummerfeltet nulstilles først: det første kald ovenfor kørte før medarbejderen var valgt
  // og kan have udfyldt feltet ud fra den alfabetisk første medarbejders disponentgruppe.
  document.getElementById("manual-reg").value = "";
  document.getElementById("manual-reg-hint").textContent = "";
  updateManualTypeVisibility();
  openModal("modal-manual-activity");
}

// ── Overnatning tilknyttet ny Normal tid-aktivitet ─────────────────────────
// Valget gemmes her og oprettes først sammen med aktiviteten (confirmManualActivity).
let _manualOvernight = null; // { from, to, dob, empId }

function _resetManualOvernight() {
  _manualOvernight = null;
  document.getElementById("manual-add-overnight").checked = false;
  document.getElementById("manual-overnight-summary").textContent = "";
}

function _onManualOvernightToggle() {
  if (!this.checked) { _resetManualOvernight(); return; }
  const startDate = document.getElementById("manual-start")?.querySelector(".dt-date")?.value || "";
  document.getElementById("manual-overnight-from").value = startDate;
  document.getElementById("manual-overnight-to").value = "";
  document.getElementById("manual-overnight-dob").checked = false;
  openModal("modal-manual-overnight");
}

function cancelManualOvernight() {
  closeModal("modal-manual-overnight");
  _resetManualOvernight();
}

function _manualOvernightDates(o) {
  return o.to ? getAllDates(o.from, o.to) : [o.from];
}

// Advarer hvis medarbejderen allerede har en (DOB-)overnatning på en af datoerne.
// Returnerer true hvis der kan fortsættes.
async function _confirmExistingOvernights(empId, dates) {
  // Overnatninger gemmes som start=slut=00:00, så de kun fanges af intervalfilteret
  // når søgningen starter dagen før.
  const dayBefore = new Date(dates[0] + "T12:00:00");
  dayBefore.setDate(dayBefore.getDate() - 1);
  let acts;
  try {
    acts = await GET(`/api/activities?employee_id=${empId}&date_from=${dayBefore.toISOString().slice(0, 10)}&date_to=${dates[dates.length - 1]}`);
  } catch (e) { toast(e.message, "error"); return false; }
  const hits = acts.filter(a =>
    (a.activity_type === "overnatning" || a.activity_type === "dob_overnatning") &&
    a.status !== "deactivated" &&
    dates.includes(a.start_time.slice(0, 10))
  );
  if (!hits.length) return true;
  const fmt = d => { const [y, m, day] = d.split("-"); return `${day}-${m}-${y}`; };
  const lines = hits.map(a => `• ${fmt(a.start_time.slice(0, 10))}: ${TYPE_LABELS[a.activity_type] || a.activity_type}`).join("\n");
  return window.confirm(`Advarsel: Der er allerede oprettet overnatning på:\n\n${lines}\n\nVil du stadig tilføje overnatning?`);
}

async function confirmManualOvernight() {
  const from = document.getElementById("manual-overnight-from").value;
  const to   = document.getElementById("manual-overnight-to").value;
  const dob  = document.getElementById("manual-overnight-dob").checked;
  if (!from) { toast("Angiv dato for overnatningen", "error"); return; }
  if (to && to < from) { toast("Til dato skal være på eller efter fra dato", "error"); return; }
  const empId = parseInt(document.getElementById("manual-employee").value);
  const o = { from, to: to || "", dob, empId };
  if (!(await _confirmExistingOvernights(empId, _manualOvernightDates(o)))) return;
  _manualOvernight = o;
  const fmt = d => { const [y, m, day] = d.split("-"); return `${day}-${m}-${y}`; };
  document.getElementById("manual-overnight-summary").textContent =
    `(${fmt(from)}${o.to ? " – " + fmt(o.to) : ""}${dob ? ", DOB" : ""})`;
  closeModal("modal-manual-overnight");
}

function confirmAbsenceConflict() {
  _absenceConflictConfirmed = true;
  closeModal("modal-absence-conflict");
  confirmManualActivity();
}

function _genGroupId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Fallback for ikke-sikre kontekster (fx almindelig http:// på LAN, hvor
  // crypto.randomUUID() ikke er tilgængelig) – kun brugt til at gruppere
  // aktiviteter oprettet i samme kald, ikke som kryptografisk nøgle.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    const v = c === "x" ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

function getWeekdayDates(from, to) {
  const dates = [];
  const d = new Date(from + "T12:00:00");
  const end = new Date(to  + "T12:00:00");
  while (d <= end) {
    if (d.getDay() !== 0 && d.getDay() !== 6) dates.push(d.toISOString().slice(0, 10));
    d.setDate(d.getDate() + 1);
  }
  return dates;
}

function getAllDates(from, to) {
  const dates = [];
  const d = new Date(from + "T12:00:00");
  const end = new Date(to  + "T12:00:00");
  while (d <= end) {
    dates.push(d.toISOString().slice(0, 10));
    d.setDate(d.getDate() + 1);
  }
  return dates;
}

// dates: dagen (enkeltdag) eller listen af dage hvor der faktisk blev oprettet fravær
// (periode). Ved en periode får hver dag kommentaren; dage der allerede har en
// Vagtplan-kommentar springes over (bekræftet af bruger 2026-10-08).
async function _afterManualActivitySaved(empId, dates) {
  if (_manualActivityContext.vagtplan) {
    const text = document.getElementById("manual-vagtplan-comment").value.trim();
    const list = (Array.isArray(dates) ? dates : [dates]).filter(Boolean).sort();
    if (text && empId && list.length) {
      let targets = list, skipped = [];
      if (list.length > 1) {
        try {
          const existing = await GET(`/api/vagtplan-comments?date_from=${list[0]}&date_to=${list[list.length - 1]}&employee_id=${empId}`);
          const have = new Set(existing.map(c => c.date));
          targets = list.filter(d => !have.has(d));
          skipped = list.filter(d => have.has(d));
        } catch (e) {
          toast(`Fravær oprettet, men kommentarer kunne ikke gemmes: ${e.message}`, "warning");
          targets = [];
        }
      }
      let failed = 0, lastError = "";
      for (const d of targets) {
        try { await POST("/api/vagtplan-comments", { employee_id: empId, date: d, text }); }
        catch (e) { failed++; lastError = e.message; }
      }
      const fmt = d => { const [y, m, day] = d.split("-"); return `${day}-${m}-${y}`; };
      if (failed) toast(`Fravær oprettet, men kommentar kunne ikke gemmes på ${failed} dag(e): ${lastError}`, "warning");
      if (skipped.length) toast(`Kommentar ikke oprettet (findes allerede) på: ${skipped.map(fmt).join(", ")}`, "warning");
    }
    await loadVagtplan();
  } else {
    await refreshActivities();
  }
}

let _paragraf56SygdomResolve = null;

function _confirmParagraf56SygdomOverride(emp) {
  return new Promise(resolve => {
    _paragraf56SygdomResolve = resolve;
    document.getElementById("paragraf56-sygdom-confirm-body").innerHTML =
      `<p style="font-size:14px">Medarbejder <strong>${h(emp.name)}</strong> har en aktiv §56-aftale. ` +
      `Skal aktiviteten oprettes som almindelig sygdom, eller ændres til §56 syg?</p>`;
    openModal("modal-paragraf56-sygdom-confirm");
  });
}

function _resolveParagraf56SygdomChoice(choice) {
  closeModal("modal-paragraf56-sygdom-confirm");
  if (_paragraf56SygdomResolve) {
    const r = _paragraf56SygdomResolve;
    _paragraf56SygdomResolve = null;
    r(choice);
  }
}

// Afviser oprettelse hvis en af datoerne ligger i en låst lønperiode (håndhæves også i
// backend). Tjekkes FØR noget oprettes, så en periode over flere dage ikke oprettes halvt.
async function _rejectIfLockedDates(dates) {
  if (!dates.length) return false;
  const sorted = dates.slice().sort();
  let locked;
  try {
    locked = await GET(`/api/activities/locked-dates?date_from=${sorted[0]}&date_to=${sorted[sorted.length - 1]}`);
  } catch (e) { toast(e.message, "error"); return true; }
  const hits = sorted.filter(d => locked.includes(d));
  if (!hits.length) return false;
  const fmt = d => { const [y, m, day] = d.split("-"); return `${day}-${m}-${y}`; };
  toast(`Kan ikke oprette – lønperioden er låst for: ${hits.map(fmt).join(", ")}`, "error");
  return true;
}

async function confirmManualActivity() {
  if (document.getElementById("manual-type").value === "sygdom") {
    const empForCheck = state.employees.find(e => e.id === parseInt(document.getElementById("manual-employee").value));
    if (empForCheck?.paragraf_56) {
      const choice = await _confirmParagraf56SygdomOverride(empForCheck);
      if (choice === "cancel") return;
      if (choice === "switch") document.getElementById("manual-type").value = "paragraf_56_syg";
    }
  }
  const start   = readDatetimePicker("manual-start");
  const end     = readDatetimePicker("manual-end");
  const actType = document.getElementById("manual-type").value;
  const tilDato = document.getElementById("manual-til-dato").value;
  const empId   = parseInt(document.getElementById("manual-employee").value);

  if (_isRepeatOn()) {
    const startDate = _manualStartDateIso();
    if (!startDate) { toast("Angiv startdato", "error"); return; }
    await _createVagtplanSeries(empId, actType, startDate);
    return;
  }

  if (_manualActivityContext.vagtplan && actType === "__none__") {
    const dateIso = document.getElementById("manual-start")?.querySelector(".dt-date")?.value;
    const text = document.getElementById("manual-vagtplan-comment").value.trim();
    if (!dateIso) { toast("Angiv dato", "error"); return; }
    if (!text) { toast("Skriv en kommentar", "error"); return; }
    try {
      await POST("/api/vagtplan-comments", { employee_id: empId, date: dateIso, text });
      toast("Kommentar gemt", "success");
      closeModal("modal-manual-activity");
      await loadVagtplan();
    } catch (e) { toast(e.message, "error"); }
    return;
  }

  if (actType === "overnatning") {
    if (!start) { toast("Angiv dato for overnatningen", "error"); return; }
    const isDob = document.getElementById("manual-dob").checked;
    const fra = start.slice(0, 10);

    if (!tilDato) {
      // ── Enkeltdag: uændret adfærd ────────────────────────────────────────
      if (await _rejectIfLockedDates([fra])) return;
      const timeStr = fra + "T00:00:00";
      try {
        await POST("/api/activities", {
          employee_id: empId,
          activity_type: isDob ? "dob_overnatning" : "overnatning",
          start_time: timeStr,
          end_time:   timeStr,
          source: _manualActivityContext.vagtplan ? "vagtplan" : undefined,
        });
        toast(isDob ? "DOB-overnatning oprettet" : "Overnatning oprettet", "success");
        closeModal("modal-manual-activity");
        await _afterManualActivitySaved(empId, fra);
      } catch (e) { toast(e.message, "error"); }
      return;
    }

    // ── Periode: én aktivitet pr. kalenderdag ────────────────────────────
    if (tilDato < fra) { toast("Til dato skal være på eller efter fra dato", "error"); return; }
    const dates = getAllDates(fra, tilDato);
    if (await _rejectIfLockedDates(dates)) return;

    const allOverlaps = [];
    for (const iso of dates) {
      const hits = state.activities.filter(a => {
        if (a.employee_id !== empId) return false;
        if (a.status === "deactivated") return false;
        return new Date(iso + "T00:00:00") < new Date(a.end_time) &&
               new Date(iso + "T23:59:59") > new Date(a.start_time);
      });
      allOverlaps.push(...hits.map(h => ({ iso, act: h })));
    }
    if (allOverlaps.length > 0) {
      const lines = allOverlaps.slice(0, 5).map(o =>
        `• ${o.iso}: ${TYPE_LABELS[o.act.activity_type] || o.act.activity_type} ${formatTime(o.act.start_time)}–${formatTime(o.act.end_time)}`
      );
      if (allOverlaps.length > 5) lines.push(`  … og ${allOverlaps.length - 5} mere`);
      if (!window.confirm(`Advarsel: ${allOverlaps.length} overlappende aktiviteter i perioden:\n\n${lines.join("\n")}\n\nVil du stadig oprette alle overnatninger?`)) return;
    }

    const absenceGroupId = _genGroupId();
    let created = 0;
    try {
      for (const iso of dates) {
        const timeStr = iso + "T00:00:00";
        await POST("/api/activities", {
          employee_id: empId,
          activity_type: isDob ? "dob_overnatning" : "overnatning",
          start_time: timeStr,
          end_time:   timeStr,
          absence_group_id: absenceGroupId,
          source: _manualActivityContext.vagtplan ? "vagtplan" : undefined,
        });
        created++;
      }
      toast(`${created} ${isDob ? "DOB-overnatning" : "overnatning"}${created === 1 ? "" : "er"} oprettet`, "success");
      closeModal("modal-manual-activity");
      await _afterManualActivitySaved(empId, dates);
    } catch (e) { toast(e.message, "error"); }
    return;
  }

  const _RANGE_TYPES = ["ferie", "selvbetalt_fridag", "loen_andet_sted_fra", "eksport", "feriefri", "barsel", "sygdom", "paragraf_56_syg", "graviditetsbetinget_sygdom", "skole_kursus", "afspadsering"];
  const isRange = _RANGE_TYPES.includes(actType) && !!tilDato;

  if (!start || (!isRange && !end)) {
    const msg = (actType === "ferie" || actType === "selvbetalt_fridag" || actType === "loen_andet_sted_fra" || actType === "eksport" || actType === "feriefri" || actType === "barsel") ? "Angiv dato for fraværsdagen"
              : (actType === "sygdom" || actType === "barn_1sygedag" || actType === "paragraf_56_syg") ? "Angiv dato for sygedagen"
              : "Angiv start- og sluttid";
    toast(msg, "error");
    return;
  }
  if (!isRange && new Date(end) <= new Date(start)) { toast("Sluttid skal være efter starttid", "error"); return; }
  if (!isRange && await _rejectIfLockedDates([start.slice(0, 10)])) return;

  const terminsdato = document.getElementById("manual-terminsdato").value || null;
  if (actType === "barsel" && !terminsdato) {
    toast("Angiv terminsdato for barsel", "error");
    return;
  }

  const regInput = document.getElementById("manual-reg").value.trim().toUpperCase();
  if (!regInput) {
    toast("Registreringsnummer / Vognnummer er påkrævet", "error");
    document.getElementById("manual-reg").focus();
    return;
  }
  const foundVehicle = state.vehicles.find(x =>
    x.registration_number.toUpperCase() === regInput ||
    x.vehicle_number.toUpperCase() === regInput
  );
  if (!foundVehicle) {
    openModal("modal-reg-error");
    return;
  }

  // ── Advarsel: fravær på dag med kørsel ───────────────────────────────────
  if (ABSENCE_TYPES.has(actType) && !_absenceConflictConfirmed) {
    const datesToCheck = isRange
      ? getWeekdayDates(start.slice(0, 10), tilDato)
      : [start.slice(0, 10)];
    const conflicts = datesToCheck.filter(date =>
      state.activities.some(a =>
        a.employee_id === empId &&
        a.activity_type === "normal" &&
        a.start_time.slice(0, 10) === date &&
        a.status !== "deactivated"
      )
    );
    if (conflicts.length > 0) {
      const dateList = conflicts.map(d => {
        const [y, m, day] = d.split("-");
        return `${day}-${m}-${y}`;
      }).join(", ");
      document.getElementById("absence-conflict-msg").innerHTML =
        `Der er allerede registreret kørsel på følgende dag${conflicts.length > 1 ? "e" : ""}:<br><strong>${dateList}</strong><br><br>Vil du alligevel registrere fraværet?`;
      openModal("modal-absence-conflict");
      return;
    }
  }
  _absenceConflictConfirmed = false;

  // ── Periodetilstand: opret én aktivitet per hverdag ──────────────────────
  if (isRange) {
    const fra = start.slice(0, 10);
    if (tilDato < fra) { toast("Til dato skal være på eller efter fra dato", "error"); return; }
    const dates = getWeekdayDates(fra, tilDato);
    if (dates.length === 0) { toast("Ingen hverdage i den valgte periode", "error"); return; }
    if (await _rejectIfLockedDates(dates)) return;

    // Overlapscheck for alle dage i perioden
    const allOverlaps = [];
    for (const iso of dates) {
      const hits = state.activities.filter(a => {
        if (a.employee_id !== empId) return false;
        if (a.status === "deactivated") return false;
        return new Date(iso + "T00:00:00") < new Date(a.end_time) &&
               new Date(iso + "T23:59:59") > new Date(a.start_time);
      });
      allOverlaps.push(...hits.map(h => ({ iso, act: h })));
    }
    if (allOverlaps.length > 0) {
      const lines = allOverlaps.slice(0, 5).map(o =>
        `• ${o.iso}: ${TYPE_LABELS[o.act.activity_type] || o.act.activity_type} ${formatTime(o.act.start_time)}–${formatTime(o.act.end_time)}`
      );
      if (allOverlaps.length > 5) lines.push(`  … og ${allOverlaps.length - 5} mere`);
      if (!window.confirm(`Advarsel: ${allOverlaps.length} overlappende aktiviteter i perioden:\n\n${lines.join("\n")}\n\nVil du stadig oprette alle aktiviteter?`)) return;
    }

    const emp = state.employees.find(e => e.id === empId);
    let created = 0;
    const createdDates = [];
    const skippedNoHours = [];
    const absenceGroupId = _genGroupId();
    try {
      for (const iso of dates) {
        let hours = 7.4;
        if (actType === "afspadsering" || actType === "skole_kursus") {
          const d = new Date(iso + "T12:00:00");
          const key = isoWeekNumber(d) % 2 === 0 ? "even" : "odd";
          const idx = (d.getDay() + 6) % 7;
          hours = emp?.work_schedule?.[key]?.[idx] ?? 0;
          if (hours <= 0) { skippedNoHours.push(iso); continue; }
        } else if (actType !== "feriefri" && emp?.work_schedule) {
          const d = new Date(iso + "T12:00:00");
          const key = isoWeekNumber(d) % 2 === 0 ? "even" : "odd";
          const idx = (d.getDay() + 6) % 7;
          const sched = emp.work_schedule[key]?.[idx] ?? 0;
          hours = sched > 0 ? sched : 7.4;
        }
        const mins = Math.round(hours * 60);
        const endH = String(6 + Math.floor(mins / 60)).padStart(2, "0");
        const endM = String(mins % 60).padStart(2, "0");
        await POST("/api/activities", {
          employee_id: empId,
          activity_type: actType,
          start_time:   iso + "T06:00:00",
          end_time:     iso + "T" + endH + ":" + endM + ":00",
          terminsdato:  terminsdato,
          vehicle_number: foundVehicle?.vehicle_number || null,
          absence_group_id: absenceGroupId,
          source: _manualActivityContext.vagtplan ? "vagtplan" : undefined,
        });
        created++;
        createdDates.push(iso);
      }
      if (actType === "barsel" && terminsdato && emp) emp.terminsdato = terminsdato;
      if (created > 0)
        toast(`${created} ${created === 1 ? "aktivitet oprettet" : "aktiviteter oprettet"}`, "success");
      if (skippedNoHours.length > 0) {
        const labels = skippedNoHours.map(d => { const [y,m,day]=d.split("-"); return `${day}-${m}-${y}`; }).join(", ");
        toast(`${skippedNoHours.length} dag${skippedNoHours.length>1?"e":""} sprunget over – ingen garanterede timer: ${labels}`, "warning");
      }
      if (created === 0 && skippedNoHours.length === 0) toast("Ingen aktiviteter oprettet", "warning");
      closeModal("modal-manual-activity");
      await _afterManualActivitySaved(empId, createdDates);
    } catch (e) { toast(e.message, "error"); }
    return;
  }

  // ── Enkeltdag: eksisterende overlapscheck + POST ─────────────────────────
  const newStart = new Date(start + ":00");
  const newEnd   = new Date(end   + ":00");
  const overlapping = state.activities.filter(a => {
    if (a.employee_id !== empId) return false;
    if (a.status === "deactivated") return false;
    return newStart < new Date(a.end_time) && newEnd > new Date(a.start_time);
  });
  if (overlapping.length > 0) {
    const lines = overlapping.map(a =>
      `• ${TYPE_LABELS[a.activity_type] || a.activity_type}: ${formatTime(a.start_time)}–${formatTime(a.end_time)}`
    ).join("\n");
    const noun = overlapping.length === 1 ? "en eksisterende aktivitet" : `${overlapping.length} eksisterende aktiviteter`;
    if (!window.confirm(`Advarsel: Der er ${noun} der overlapper med det valgte tidsrum:\n\n${lines}\n\nVil du stadig oprette aktiviteten?`)) return;
  }

  // Tilknyttet overnatning (kun Normal tid) – tjekkes før noget oprettes.
  const overnight = (actType === "normal" && _manualOvernight) ? _manualOvernight : null;
  const overnightDates = overnight ? _manualOvernightDates(overnight) : [];
  if (overnight) {
    if (await _rejectIfLockedDates(overnightDates)) return;
    // Medarbejderen er skiftet efter pop-uppen blev bekræftet → advar igen for den nye.
    if (overnight.empId !== empId && !(await _confirmExistingOvernights(empId, overnightDates))) return;
  }

  try {
    await POST("/api/activities", {
      employee_id: empId,
      activity_type: actType,
      start_time: start + ":00",
      end_time: end + ":00",
      terminsdato: terminsdato,
      loading_minutes: parseInt(document.getElementById("manual-loading").value) || null,
      unloading_minutes: parseInt(document.getElementById("manual-unloading").value) || null,
      comment: document.getElementById("manual-comment").value || null,
      vehicle_number: foundVehicle?.vehicle_number || null,
      km_start: parseInt(document.getElementById("manual-km-start").value) || null,
      km_end:   parseInt(document.getElementById("manual-km-end").value)   || null,
      salt_supplement: document.getElementById("manual-salt").checked,
      pause_intervals: manualPauses,
      source: _manualActivityContext.vagtplan ? "vagtplan" : undefined,
    });
    if (actType === "barsel" && terminsdato) {
      const emp = state.employees.find(e => e.id === empId);
      if (emp) emp.terminsdato = terminsdato;
    }
    if (overnight) {
      const overnightType = overnight.dob ? "dob_overnatning" : "overnatning";
      const groupId = overnightDates.length > 1 ? _genGroupId() : undefined;
      let createdOvernights = 0;
      try {
        for (const iso of overnightDates) {
          await POST("/api/activities", {
            employee_id: empId,
            activity_type: overnightType,
            start_time: iso + "T00:00:00",
            end_time:   iso + "T00:00:00",
            absence_group_id: groupId,
            source: _manualActivityContext.vagtplan ? "vagtplan" : undefined,
          });
          createdOvernights++;
        }
        toast(`Aktivitet og ${createdOvernights === 1 ? (overnight.dob ? "DOB-overnatning" : "overnatning") : `${createdOvernights} ${overnight.dob ? "DOB-overnatninger" : "overnatninger"}`} oprettet`, "success");
      } catch (e) {
        toast(`Aktivitet oprettet, men overnatning kunne ikke oprettes (${createdOvernights} af ${overnightDates.length} oprettet): ${e.message}`, "warning");
      }
    } else {
      toast("Aktivitet oprettet", "success");
    }
    closeModal("modal-manual-activity");
    await _afterManualActivitySaved(empId, start.slice(0, 10));
  } catch (e) { toast(e.message, "error"); }
}

// ── Employees ──────────────────────────────────────────────────────────────
async function loadEmployees() {
  setLoading(true);
  try {
    const showInactive = document.getElementById("show-inactive")?.checked;
    const [emps] = await Promise.all([GET(`/api/employees?active_only=${!showInactive}`), loadPositions()]);
    state.employees = emps;
    fillEmployeePositionFilter();
    renderEmployeeList();
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

function fillEmployeePositionFilter() {
  const sel = document.getElementById("employee-filter-position");
  if (!sel) return;
  const cur = sel.value;
  sel.innerHTML = `<option value="">Alle stillinger</option><option value="none">Ingen stilling</option>` +
    (state.positions || []).map(p => `<option value="${p.id}">${h(p.name)}</option>`).join("");
  if ([...sel.options].some(o => o.value === cur)) sel.value = cur;
}

// Telefonsøgning: mellemrum, bindestreger og +45/0045 ignoreres
function _normalizePhone(s) {
  let d = String(s || "").replace(/\D/g, "");
  if (d.startsWith("0045")) d = d.slice(4);
  else if (d.length === 10 && d.startsWith("45")) d = d.slice(2);
  return d;
}

function _boolFilter(id, value) {
  const v = document.getElementById(id)?.value || "";
  return v === "" || (v === "1") === !!value;
}

function _filteredEmployees() {
  const query = (document.getElementById("employee-search")?.value || "").toLowerCase().trim();
  const phoneQuery = _normalizePhone(query);
  let emps = state.employees;
  if (query) {
    emps = emps.filter(e =>
      e.name.toLowerCase().includes(query) ||
      String(e.employee_number).toLowerCase().includes(query) ||
      (phoneQuery.length >= 3 && [e.phone, e.mobile].some(p => _normalizePhone(p).includes(phoneQuery)))
    );
  }
  const groupFilter = document.getElementById("employee-filter-dispatcher-group")?.value || "";
  if (groupFilter === "none") emps = emps.filter(e => !e.dispatcher_group);
  else if (groupFilter) emps = emps.filter(e => e.dispatcher_group?.id === parseInt(groupFilter));
  const posFilter = document.getElementById("employee-filter-position")?.value || "";
  if (posFilter === "none") emps = emps.filter(e => !e.position_id);
  else if (posFilter) emps = emps.filter(e => e.position_id === parseInt(posFilter));
  emps = emps.filter(e =>
    _boolFilter("employee-filter-personaleforening", e.personaleforening) &&
    _boolFilter("employee-filter-natarbejde", e.natarbejde_tillaeg) &&
    _boolFilter("employee-filter-elev", isElev(e)));
  return emps;
}

const _EMP_TABLE_COLUMNS = [
  { key: "employee_number", label: "Lønnummer", value: e => e.employee_number, sort: e => e.employee_number },
  { key: "name",            label: "Navn",      value: e => e.name, sort: e => e.name },
  { key: "fuldloennet",     label: "Fuldlønnet", value: e => e.fuldloennet ? "✓" : "–", sort: e => e.fuldloennet ? 1 : 0 },
  { key: "natarbejde",      label: "Natarbejdetillæg", value: e => e.natarbejde_tillaeg ? "✓" : "–", sort: e => e.natarbejde_tillaeg ? 1 : 0 },
  { key: "position",        label: "Stilling",  value: e => e.position_name || "", sort: e => e.position_name || "" },
  { key: "group",           label: "Disponentgruppe", value: e => e.dispatcher_group?.name || "", sort: e => e.dispatcher_group?.name || "" },
  { key: "hire_date",       label: "Ansættelsesdato", value: e => formatDateShort(e.hire_date), sort: e => e.hire_date },
  { key: "phone",           label: "Telefon",   value: e => e.phone || "", sort: e => e.phone || "" },
  { key: "mobile",          label: "Mobil",     value: e => e.mobile || "", sort: e => e.mobile || "" },
  { key: "email",           label: "Email",     value: e => e.email || "", sort: e => e.email || "" },
  { key: "elev",            label: "Elev",
    value: e => isElev(e) ? `Ja (${formatDateShort(e.elev_start_date)}–${formatDateShort(e.elev_end_date)})` : "Nej",
    sort: e => isElev(e) ? (e.elev_end_date || "") : "" },
];

function _employeeViewMode() {
  if (!_hasPerm("employee_table_view")) return "list";
  try { return localStorage.getItem("employeeViewMode") === "table" ? "table" : "list"; }
  catch (_) { return "list"; }
}

function toggleEmployeeView() {
  const next = _employeeViewMode() === "table" ? "list" : "table";
  try { localStorage.setItem("employeeViewMode", next); } catch (_) {}
  renderEmployeeList();
}

function sortEmployeeTable(key) {
  const cur = state.employeeSort || { key: "name", dir: 1 };
  state.employeeSort = { key, dir: cur.key === key ? -cur.dir : 1 };
  renderEmployeeList();
}

function _sortedForTable(emps) {
  const { key, dir } = state.employeeSort || { key: "name", dir: 1 };
  const col = _EMP_TABLE_COLUMNS.find(c => c.key === key) || _EMP_TABLE_COLUMNS[1];
  return emps.slice().sort((a, b) => {
    const va = col.sort(a), vb = col.sort(b);
    const cmp = typeof va === "number" ? va - vb : naturalCompare(String(va), String(vb));
    return cmp * dir;
  });
}

function renderEmployeeList() {
  const container = document.getElementById("employee-list");
  container.innerHTML = "";
  const mode = _employeeViewMode();
  const toggleBtn = document.getElementById("btn-employee-view-toggle");
  if (toggleBtn) toggleBtn.textContent = mode === "table" ? "Liste" : "Tabel";
  const exportBtn = document.getElementById("btn-employee-export");
  if (exportBtn) exportBtn.style.display = mode === "table" && _hasPerm("employee_export") ? "" : "none";

  const emps = _filteredEmployees();
  if (emps.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="icon">👤</div><h3>Ingen medarbejdere</h3></div>`;
    return;
  }
  const canEdit = _hasPerm("manage_employees");

  if (mode === "table") {
    const sorted = _sortedForTable(emps);
    const { key, dir } = state.employeeSort || { key: "name", dir: 1 };
    container.innerHTML = `
      <div style="overflow-x:auto">
        <table class="emp-table">
          <thead><tr>${_EMP_TABLE_COLUMNS.map(c =>
            `<th onclick="sortEmployeeTable(${jq(c.key)})">${h(c.label)}${c.key === key ? (dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead>
          <tbody>${sorted.map(e => `
            <tr class="${isElev(e) ? "elev-row" : ""}" ${canEdit ? `onclick="openEditEmployee(${e.id})"` : ""}>
              ${_EMP_TABLE_COLUMNS.map(c => `<td>${h(c.value(e))}</td>`).join("")}
            </tr>`).join("")}
          </tbody>
        </table>
      </div>`;
    return;
  }

  for (const e of emps.slice().sort((a, b) => a.name.localeCompare(b.name, "da"))) {
    const initials = `${e.first_name[0] || ""}${e.last_name[0] || ""}`.toUpperCase();
    const avatarStyle = isElev(e) ? "background:#e0a800" : (e.afloeser ? "background:var(--accent)" : "");
    const div = document.createElement("div");
    div.className = "emp-card";
    div.style.cursor = "pointer";
    div.innerHTML = `
      <div class="emp-avatar" style="${avatarStyle}">${h(initials)}</div>
      <div class="emp-info">
        <div class="emp-name">${h(e.name)}</div>
        <div class="emp-sub">Lønnr. ${h(e.employee_number)}${e.position_name ? ` · ${h(e.position_name)}` : ""}</div>
      </div>
      ${e.active ? "" : `<span class="badge" style="background:#fee2e2;color:#dc2626">Inaktiv</span>`}
      ${canEdit ? `<button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); openEditEmployee(${e.id})">Rediger</button>` : ""}
    `;
    div.addEventListener("click", () => { if (canEdit) openEditEmployee(e.id); });
    container.appendChild(div);
  }
}

async function exportEmployeesXlsx() {
  const ids = _sortedForTable(_filteredEmployees()).map(e => e.id);
  if (!ids.length) { toast("Ingen medarbejdere at eksportere", "error"); return; }
  try {
    await downloadFile("/api/employees/export-xlsx", { employee_ids: ids }, "Medarbejderregister.xlsx");
  } catch (e) { toast(e.message, "error"); }
}

function openParagraf56ListModal() {
  const groupFilter = document.getElementById("employee-filter-dispatcher-group")?.value || "";
  let emps = state.employees.filter(e => e.active && e.paragraf_56);
  if (groupFilter === "none") {
    emps = emps.filter(e => !e.dispatcher_group);
  } else if (groupFilter) {
    emps = emps.filter(e => e.dispatcher_group?.id === parseInt(groupFilter));
  }
  emps = emps.slice().sort((a, b) => a.name.localeCompare(b.name, "da"));
  const body = document.getElementById("paragraf56-list-body");
  body.innerHTML = emps.length === 0
    ? `<tr><td colspan="3" style="padding:16px 4px;color:var(--text-light)">Ingen medarbejdere med igangværende §56 i denne afdeling</td></tr>`
    : emps.map(e => `
        <tr>
          <td style="padding:6px 4px;border-bottom:1px solid var(--border)">${h(e.name)}</td>
          <td style="padding:6px 4px;border-bottom:1px solid var(--border)">${formatDateShort(e.paragraf_56_start_date)}</td>
          <td style="padding:6px 4px;border-bottom:1px solid var(--border)">${formatDateShort(e.paragraf_56_end_date)}</td>
        </tr>`).join("");
  openModal("modal-paragraf56-list");
}

const DEFAULT_SCHEDULE = [7.5, 7.5, 7.5, 7.5, 7, 0, 0]; // man-tor, fre, lør, søn

function _hoursFromTimes(startVal, endVal) {
  if (!startVal || !endVal) return null;
  const [sh, sm] = startVal.split(":").map(Number);
  const [eh, em] = endVal.split(":").map(Number);
  let mins = (eh * 60 + em) - (sh * 60 + sm);
  if (mins < 0) mins += 24 * 60; // arbejdstid over midnat
  return Math.round((mins / 60) * 100) / 100;
}

function _scheduleRowCell(prefix, day, hours) {
  return `
    <td>
      <div style="display:flex;align-items:center;gap:6px">
        <input type="number" step="0.1" min="0" max="24" class="sched-${prefix}" data-day="${day}" value="${hours}" style="width:70px"> t
      </div>
      <div style="display:flex;align-items:center;gap:4px;margin-top:4px;font-size:12px;color:var(--text-light)">
        <input type="time" class="sched-${prefix}-start" data-day="${day}" style="width:88px">
        –
        <input type="time" class="sched-${prefix}-end" data-day="${day}" style="width:88px">
      </div>
    </td>`;
}

function buildScheduleTable(schedule) {
  const tbody = document.querySelector("#schedule-table tbody");
  tbody.innerHTML = "";
  for (let i = 0; i < 7; i++) {
    const def = DEFAULT_SCHEDULE[i];
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${WEEKDAYS[i]}</td>
      ${_scheduleRowCell("even", i, schedule?.even?.[i] ?? def)}
      ${_scheduleRowCell("odd", i, schedule?.odd?.[i] ?? def)}
    `;
    tbody.appendChild(tr);
  }
  document.querySelectorAll("#schedule-table .sched-even, #schedule-table .sched-odd").forEach(el =>
    el.addEventListener("input", _updateScheduleTotals));
  ["even", "odd"].forEach(prefix => {
    document.querySelectorAll(`#schedule-table .sched-${prefix}-start, #schedule-table .sched-${prefix}-end`).forEach(el => {
      el.addEventListener("input", () => {
        const day = el.dataset.day;
        const startEl = document.querySelector(`.sched-${prefix}-start[data-day="${day}"]`);
        const endEl   = document.querySelector(`.sched-${prefix}-end[data-day="${day}"]`);
        const hours = _hoursFromTimes(startEl.value, endEl.value);
        if (hours !== null) {
          document.querySelector(`.sched-${prefix}[data-day="${day}"]`).value = hours;
          _updateScheduleTotals();
        }
      });
    });
  });
  _updateScheduleTotals();
}

function _updateScheduleTotals() {
  const sum = cls => [...document.querySelectorAll(cls)].reduce((s, el) => s + (parseFloat(el.value) || 0), 0);
  document.getElementById("sched-even-total").textContent = fmtHours(sum(".sched-even"));
  document.getElementById("sched-odd-total").textContent  = fmtHours(sum(".sched-odd"));
}

function readScheduleTable() {
  const even = [], odd = [];
  ["even", "odd"].forEach(prefix => {
    const target = prefix === "even" ? even : odd;
    for (let day = 0; day < 7; day++) {
      const startEl = document.querySelector(`.sched-${prefix}-start[data-day="${day}"]`);
      const endEl   = document.querySelector(`.sched-${prefix}-end[data-day="${day}"]`);
      const fromTimes = _hoursFromTimes(startEl.value, endEl.value);
      const numEl = document.querySelector(`.sched-${prefix}[data-day="${day}"]`);
      target.push(fromTimes !== null ? fromTimes : (parseFloat(numEl.value) || 0));
    }
  });
  return { even, odd };
}

async function loadAgreementTypes() {
  if (state.agreementTypes.length) return;
  state.agreementTypes = await GET("/api/employees/agreement-types");
}

function fillAgreementTypeSelect(selected = null) {
  const sel = document.getElementById("emp-agreement-type");
  const placeholder = selected ? "" : `<option value="">[Vælg overenskomsttype]</option>`;
  sel.innerHTML = placeholder + state.agreementTypes
    .map(t => `<option value="${t.name}" ${t.name === selected ? "selected" : ""}>${t.name} (${t.hourly_rate.toFixed(2)} kr)</option>`)
    .join("");
}

async function loadAgreementKinds() {
  state.agreementKinds = await GET("/api/employees/agreement-kinds");
}

function fillAgreementKindSelect(selected = null) {
  const sel = document.getElementById("emp-agreement-kind");
  const placeholder = selected ? "" : `<option value="">[Vælg aftale]</option>`;
  sel.innerHTML = placeholder + state.agreementKinds
    .map(k => `<option value="${k.key}" ${k.key === selected ? "selected" : ""}>${h(k.label)}</option>`)
    .join("");
  onAgreementKindChange();
}

function onParagraf56Change() {
  const checked = document.getElementById("emp-paragraf56").checked;
  document.getElementById("emp-paragraf56-dates").style.display = checked ? "" : "none";
}

function onFastBilChange() {
  const checked = document.getElementById("emp-fast-bil").checked;
  document.getElementById("emp-fast-bil-vehicle-row").style.display = checked ? "" : "none";
}

function _renderEmpFastBilVehicleResults(query) {
  const dropdown = document.getElementById("emp-fast-bil-vehicle-dropdown");
  const q = query.trim().toUpperCase();
  const matches = state.vehicles.filter(v =>
    v.vehicle_number.toUpperCase().includes(q) || v.registration_number.toUpperCase().includes(q));
  dropdown.innerHTML = matches.map(v => `
    <div class="emp-fbv-item" data-id="${v.id}" data-num="${h(v.vehicle_number)}" style="padding:8px 10px;cursor:pointer;font-size:13px">
      ${h(v.vehicle_number)} <span style="color:var(--text-light)">– ${h(v.registration_number)}</span>
    </div>`).join("") || `<div style="padding:8px 10px;color:var(--text-light);font-size:13px">Ingen køretøjer fundet</div>`;
  _empFastBilHighlightIndex = -1;
  dropdown.querySelectorAll(".emp-fbv-item").forEach((el, idx) => {
    el.addEventListener("mouseover", () => _setEmpFastBilHighlight(idx));
    el.addEventListener("mouseout", () => _setEmpFastBilHighlight(-1));
    el.addEventListener("click", () => _selectEmpFastBilVehicle(el));
  });
  dropdown.style.display = "block";
}

let _empFastBilHighlightIndex = -1;

function _setEmpFastBilHighlight(index) {
  const items = document.querySelectorAll("#emp-fast-bil-vehicle-dropdown .emp-fbv-item");
  items.forEach((el, i) => { el.style.background = i === index ? "var(--bg)" : ""; });
  _empFastBilHighlightIndex = index;
}

function _moveEmpFastBilHighlight(delta) {
  const items = document.querySelectorAll("#emp-fast-bil-vehicle-dropdown .emp-fbv-item");
  if (!items.length) return;
  let next = _empFastBilHighlightIndex + delta;
  if (next < 0) next = items.length - 1;
  if (next >= items.length) next = 0;
  _setEmpFastBilHighlight(next);
  items[next].scrollIntoView({ block: "nearest" });
}

function _selectEmpFastBilVehicle(el) {
  document.getElementById("emp-fast-bil-vehicle-search").value = el.dataset.num;
  document.getElementById("emp-fast-bil-vehicle-id").value = el.dataset.id;
  document.getElementById("emp-fast-bil-vehicle-dropdown").style.display = "none";
}

document.getElementById("emp-fast-bil-vehicle-search")?.addEventListener("input", function () { _renderEmpFastBilVehicleResults(this.value); });
document.getElementById("emp-fast-bil-vehicle-search")?.addEventListener("focus", function () { _renderEmpFastBilVehicleResults(this.value); });
document.getElementById("emp-fast-bil-vehicle-search")?.addEventListener("keydown", function (e) {
  const dropdown = document.getElementById("emp-fast-bil-vehicle-dropdown");
  if (dropdown.style.display !== "block") return;
  if (e.key === "Tab" || e.key === "ArrowDown") {
    e.preventDefault();
    _moveEmpFastBilHighlight(e.shiftKey ? -1 : 1);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    _moveEmpFastBilHighlight(-1);
  } else if (e.key === "Enter") {
    const items = dropdown.querySelectorAll(".emp-fbv-item");
    if (_empFastBilHighlightIndex >= 0 && items[_empFastBilHighlightIndex]) {
      e.preventDefault();
      _selectEmpFastBilVehicle(items[_empFastBilHighlightIndex]);
    }
  } else if (e.key === "Escape") {
    dropdown.style.display = "none";
  }
});
document.addEventListener("click", (e) => {
  if (!e.target.closest("#emp-fast-bil-vehicle-search, #emp-fast-bil-vehicle-dropdown")) {
    const dropdown = document.getElementById("emp-fast-bil-vehicle-dropdown");
    if (dropdown) dropdown.style.display = "none";
  }
});

// "Vognnummer ved fravær" – søgbar vogn fra Vognpark. Skrives der i feltet
// uden at vælge en vogn i listen, nulstilles det skjulte id, så feltet
// tæller som ikke-udfyldt ved gem.
let _empAbsenceVehicleHighlightIndex = -1;

function _renderEmpAbsenceVehicleResults(query) {
  const dropdown = document.getElementById("emp-absence-vehicle-dropdown");
  const q = query.trim().toUpperCase();
  const matches = state.vehicles.filter(v =>
    v.vehicle_number.toUpperCase().includes(q) || v.registration_number.toUpperCase().includes(q));
  dropdown.innerHTML = matches.map(v => `
    <div class="emp-abv-item" data-id="${v.id}" data-num="${h(v.vehicle_number)}" style="padding:8px 10px;cursor:pointer;font-size:13px">
      ${h(v.vehicle_number)} <span style="color:var(--text-light)">– ${h(v.registration_number)}</span>
    </div>`).join("") || `<div style="padding:8px 10px;color:var(--text-light);font-size:13px">Ingen køretøjer fundet</div>`;
  _empAbsenceVehicleHighlightIndex = -1;
  dropdown.querySelectorAll(".emp-abv-item").forEach((el, idx) => {
    el.addEventListener("mouseover", () => _setEmpAbsenceVehicleHighlight(idx));
    el.addEventListener("mouseout", () => _setEmpAbsenceVehicleHighlight(-1));
    el.addEventListener("click", () => _selectEmpAbsenceVehicle(el));
  });
  dropdown.style.display = "block";
}

function _setEmpAbsenceVehicleHighlight(index) {
  const items = document.querySelectorAll("#emp-absence-vehicle-dropdown .emp-abv-item");
  items.forEach((el, i) => { el.style.background = i === index ? "var(--bg)" : ""; });
  _empAbsenceVehicleHighlightIndex = index;
}

function _moveEmpAbsenceVehicleHighlight(delta) {
  const items = document.querySelectorAll("#emp-absence-vehicle-dropdown .emp-abv-item");
  if (!items.length) return;
  let next = _empAbsenceVehicleHighlightIndex + delta;
  if (next < 0) next = items.length - 1;
  if (next >= items.length) next = 0;
  _setEmpAbsenceVehicleHighlight(next);
  items[next].scrollIntoView({ block: "nearest" });
}

function _selectEmpAbsenceVehicle(el) {
  document.getElementById("emp-absence-vehicle-search").value = el.dataset.num;
  document.getElementById("emp-absence-vehicle-id").value = el.dataset.id;
  document.getElementById("emp-absence-vehicle-dropdown").style.display = "none";
}

document.getElementById("emp-absence-vehicle-search")?.addEventListener("input", function () {
  document.getElementById("emp-absence-vehicle-id").value = "";
  _renderEmpAbsenceVehicleResults(this.value);
});
document.getElementById("emp-absence-vehicle-search")?.addEventListener("focus", function () { _renderEmpAbsenceVehicleResults(this.value); });
document.getElementById("emp-absence-vehicle-search")?.addEventListener("keydown", function (e) {
  const dropdown = document.getElementById("emp-absence-vehicle-dropdown");
  if (dropdown.style.display !== "block") return;
  if (e.key === "Tab" || e.key === "ArrowDown") {
    e.preventDefault();
    _moveEmpAbsenceVehicleHighlight(e.shiftKey ? -1 : 1);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    _moveEmpAbsenceVehicleHighlight(-1);
  } else if (e.key === "Enter") {
    const items = dropdown.querySelectorAll(".emp-abv-item");
    if (_empAbsenceVehicleHighlightIndex >= 0 && items[_empAbsenceVehicleHighlightIndex]) {
      e.preventDefault();
      _selectEmpAbsenceVehicle(items[_empAbsenceVehicleHighlightIndex]);
    }
  } else if (e.key === "Escape") {
    dropdown.style.display = "none";
  }
});
document.addEventListener("click", (e) => {
  if (!e.target.closest("#emp-absence-vehicle-search, #emp-absence-vehicle-dropdown")) {
    const dropdown = document.getElementById("emp-absence-vehicle-dropdown");
    if (dropdown) dropdown.style.display = "none";
  }
});

const FUNKTIONAER = "funktionaer";
let _empOriginalKind = null;   // aftaletype ved åbning af modalen (null = ny medarbejder)

// Navnecellens markering: elev (gul) vinder over afløser (grøn)
function empCellHighlight(emp) {
  if (isElev(emp)) return " elev-highlight";
  return emp.afloeser ? " afloeser-highlight" : "";
}

function isElev(e) {
  return !!e.elev && e.agreement_kind !== FUNKTIONAER;
}

function onAgreementKindChange() {
  const key = document.getElementById("emp-agreement-kind").value;
  const kind = state.agreementKinds.find(k => k.key === key);
  const requires = kind ? kind.requires_agreement_type : true;
  document.getElementById("emp-agreement-type-required-star").style.display = requires ? "" : "none";

  document.getElementById("emp-agreement-type-group").style.display = requires ? "" : "none";
  if (!requires) document.getElementById("emp-agreement-type").value = "";

  // Felter der ikke gælder for typen skjules kun – værdierne bevares (spec 3.3)
  const isFunktionaer = key === FUNKTIONAER;
  document.getElementById("emp-card-group").style.display = isFunktionaer ? "none" : "";
  document.getElementById("emp-initials-star").style.display = isFunktionaer ? "" : "none";
  document.getElementById("emp-email-label").textContent = isFunktionaer ? "Email (Poulschou)" : "Email (Privat)";
  document.querySelectorAll("#modal-employee .emp-driver-only").forEach(el => {
    el.style.display = isFunktionaer ? "none" : "";
  });
  if (!isFunktionaer) {
    onFastBilChange();
  }
  onElevChange();

  const isNewEmployee = !document.getElementById("emp-id").value;
  if (isNewEmployee && isFunktionaer) {
    const sel = document.getElementById("emp-dispatcher-group");
    if (!sel.value) {
      const kontorGroup = state.dispatcherGroups.find(g => /^0\b/.test(g.name.trim()) && /kontor/i.test(g.name));
      if (kontorGroup) sel.value = String(kontorGroup.id);
    }
  }
}

function onElevChange() {
  const isFunktionaer = document.getElementById("emp-agreement-kind").value === FUNKTIONAER;
  const checked = document.getElementById("emp-elev").checked;
  document.getElementById("emp-elev-dates").style.display = checked && !isFunktionaer ? "" : "none";
}

async function loadPositions() {
  try { state.positions = await GET("/api/employees/positions"); }
  catch (_) { state.positions = state.positions || []; }
}

function fillPositionSelect(selectedId = null) {
  const sel = document.getElementById("emp-position");
  sel.innerHTML = `<option value="">[Vælg stilling]</option>` + (state.positions || [])
    .map(p => `<option value="${p.id}" ${p.id === selectedId ? "selected" : ""}>${h(p.name)}</option>`)
    .join("");
}

async function checkEmployeeNumber() {
  const input = document.getElementById("emp-number");
  const err = document.getElementById("emp-number-error");
  const number = input.value.trim();
  err.style.display = "none";
  if (!number) return true;
  const id = document.getElementById("emp-id").value;
  try {
    const qs = new URLSearchParams({ number });
    if (id) qs.set("exclude_id", id);
    const r = await GET(`/api/employees/check-number?${qs}`);
    if (r.taken) {
      err.textContent = `Lønnummer ${number} bruges allerede af ${r.employee_name}`;
      err.style.display = "";
      return false;
    }
  } catch (_) { /* serveren afviser alligevel en dublet ved gem */ }
  return true;
}

async function _loadEmpCvrDropdown(selectedCvr) {
  const group = document.getElementById("emp-cvr-group");
  const sel   = document.getElementById("emp-cvr");
  try {
    const rows = await GET("/api/stamdata/cvr-numbers");
    if (rows.length < 2) { group.style.display = "none"; return; }
    const defaultRow = rows.find(r => r.is_default);
    const current = selectedCvr || (defaultRow ? defaultRow.cvr_number : rows[0].cvr_number);
    sel.innerHTML = rows.map(r =>
      `<option value="${h(r.cvr_number)}" ${r.cvr_number === current ? "selected" : ""}>${h(r.cvr_number)}${r.company_name ? " – " + h(r.company_name) : ""}</option>`
    ).join("");
    group.style.display = "";
  } catch (_) { group.style.display = "none"; }
}

function fillDispatcherGroupSelect(selectedId = null) {
  const sel = document.getElementById("emp-dispatcher-group");
  sel.innerHTML = `<option value="">— Ingen —</option>` + state.dispatcherGroups
    .map(g => `<option value="${g.id}" ${g.id === selectedId ? "selected" : ""}>${h(g.name)}</option>`)
    .join("");
}

async function openNewEmployeeModal() {
  await loadAgreementTypes();
  await loadAgreementKinds();
  await loadPositions();
  if (!state.vehicles.length) { try { state.vehicles = await GET("/api/vehicles"); } catch (_) {} }
  document.getElementById("emp-modal-title").textContent = "Opret medarbejder";
  document.getElementById("emp-save-btn").textContent = "Opret";
  document.getElementById("emp-id").value = "";
  ["emp-number","emp-card","emp-initials","emp-firstname","emp-lastname","emp-address","emp-postal",
   "emp-email","emp-phone","emp-mobile","emp-cpr"].forEach(id => document.getElementById(id).value = "");
  fillAgreementKindSelect();
  fillAgreementTypeSelect();
  fillDispatcherGroupSelect(null);
  buildDatePicker("emp-hire", "");
  buildDatePicker("emp-termination", "9999-12-31");
  document.getElementById("emp-active").checked = true;
  document.getElementById("emp-fuldloennet").checked = true;
  document.getElementById("emp-paragraf56").checked = false;
  buildDatePicker("emp-paragraf56-start", "");
  buildDatePicker("emp-paragraf56-end", "");
  onParagraf56Change();
  document.getElementById("emp-afloeser").checked = false;
  document.getElementById("emp-ot-extra-alle-timer").checked = false;
  document.getElementById("emp-fast-bil").checked = false;
  document.getElementById("emp-fast-bil-vehicle-row").style.display = "none";
  document.getElementById("emp-fast-bil-vehicle-search").value = "";
  document.getElementById("emp-fast-bil-vehicle-id").value = "";
  document.getElementById("emp-absence-vehicle-search").value = "";
  document.getElementById("emp-absence-vehicle-id").value = "";
  _empOriginalKind = null;
  fillPositionSelect(null);
  buildDatePicker("emp-seniority", "");
  document.getElementById("emp-cpr-hint").style.display = "none";
  document.getElementById("emp-personaleforening").checked = true;
  document.getElementById("emp-elev").checked = false;
  document.getElementById("emp-voksenelev").checked = false;
  document.getElementById("emp-natarbejde").checked = false;
  buildDatePicker("emp-elev-start", "");
  buildDatePicker("emp-elev-end", "");
  document.getElementById("emp-number-error").style.display = "none";
  try {
    const { suggestion } = await GET("/api/employees/next-employee-number");
    document.getElementById("emp-number").value = suggestion;
  } catch (_) { /* forslag er en hjælp – modalen virker uden */ }
  onAgreementKindChange();
  buildScheduleTable(null);
  await _loadEmpCvrDropdown(null);
  document.getElementById("emp-active-supplement").value = "";
  showElevClaimNote(null);
  openModal("modal-employee");
}

async function openEditEmployee(id) {
  await loadAgreementTypes();
  await loadAgreementKinds();
  await loadPositions();
  if (!state.vehicles.length) { try { state.vehicles = await GET("/api/vehicles"); } catch (_) {} }
  const e = state.employees.find(x => x.id === id);
  if (!e) return;
  document.getElementById("emp-modal-title").textContent = "Rediger medarbejder";
  document.getElementById("emp-save-btn").textContent = "Opdater";
  document.getElementById("emp-id").value = e.id;
  document.getElementById("emp-number").value = e.employee_number;
  document.getElementById("emp-card").value = e.tachograph_card_number || "";
  document.getElementById("emp-initials").value = e.initials || "";
  document.getElementById("emp-firstname").value = e.first_name;
  document.getElementById("emp-lastname").value = e.last_name;
  document.getElementById("emp-address").value = e.address || "";
  document.getElementById("emp-postal").value = e.postal_code || "";
  document.getElementById("emp-email").value = e.email || "";
  document.getElementById("emp-phone").value = e.phone || "";
  document.getElementById("emp-mobile").value = e.mobile || "";
  fillAgreementKindSelect(e.agreement_kind);
  fillAgreementTypeSelect(e.agreement_type);
  fillDispatcherGroupSelect(e.dispatcher_group?.id ?? null);
  buildDatePicker("emp-hire", e.hire_date);
  buildDatePicker("emp-termination", e.termination_date);
  document.getElementById("emp-active").checked = e.active;
  document.getElementById("emp-fuldloennet").checked = e.fuldloennet;
  document.getElementById("emp-paragraf56").checked = e.paragraf_56;
  buildDatePicker("emp-paragraf56-start", e.paragraf_56_start_date || "");
  buildDatePicker("emp-paragraf56-end", e.paragraf_56_end_date || "");
  onParagraf56Change();
  document.getElementById("emp-afloeser").checked = e.afloeser;
  document.getElementById("emp-ot-extra-alle-timer").checked = e.ot_extra_alle_timer;
  document.getElementById("emp-fast-bil").checked = e.fast_bil;
  document.getElementById("emp-fast-bil-vehicle-row").style.display = e.fast_bil ? "" : "none";
  document.getElementById("emp-fast-bil-vehicle-search").value = e.fast_bil_vehicle_number || "";
  document.getElementById("emp-fast-bil-vehicle-id").value = e.fast_bil_vehicle_id || "";
  document.getElementById("emp-absence-vehicle-search").value = e.absence_vehicle_number || "";
  document.getElementById("emp-absence-vehicle-id").value = e.absence_vehicle_id || "";
  _empOriginalKind = e.agreement_kind;
  fillPositionSelect(e.position_id ?? null);
  buildDatePicker("emp-seniority", e.seniority_date || "");
  document.getElementById("emp-cpr").value = e.cpr_number || "";
  document.getElementById("emp-cpr-hint").style.display = (e.cpr_number || "").endsWith("****") ? "" : "none";
  document.getElementById("emp-personaleforening").checked = e.personaleforening;
  document.getElementById("emp-elev").checked = e.elev;
  document.getElementById("emp-voksenelev").checked = !!e.voksenelev;
  document.getElementById("emp-natarbejde").checked = e.natarbejde_tillaeg;
  buildDatePicker("emp-elev-start", e.elev_start_date || "");
  buildDatePicker("emp-elev-end", e.elev_end_date || "");
  document.getElementById("emp-number-error").style.display = "none";
  onAgreementKindChange();
  buildScheduleTable(e.work_schedule);
  await _loadEmpCvrDropdown(e.cvr_number || null);
  if (state.currentUser?.permissions?.includes("manage_employee_supplements")) {
    try {
      // Flere aktive tillæg summeres (samme regel som lønberegningen)
      const supplements = await GET(`/api/employee-supplements/active/${id}`);
      const total = supplements.reduce((sum, s) => sum + s.value, 0);
      document.getElementById("emp-active-supplement").value = supplements.length ? `${total.toFixed(2)} kr/t` : "";
    } catch (_) {
      document.getElementById("emp-active-supplement").value = "";
    }
  }
  showElevClaimNote(id);   // static/js/elev.js
  openModal("modal-employee");
}

async function confirmEmployee() {
  const id = document.getElementById("emp-id").value;
  const body = {
    employee_number: document.getElementById("emp-number").value.trim(),
    tachograph_card_number: document.getElementById("emp-card").value.trim() || null,
    initials: document.getElementById("emp-initials").value.trim().toUpperCase() || null,
    first_name: document.getElementById("emp-firstname").value.trim(),
    last_name: document.getElementById("emp-lastname").value.trim(),
    address: document.getElementById("emp-address").value.trim() || null,
    postal_code: document.getElementById("emp-postal").value.trim() || null,
    email: document.getElementById("emp-email").value.trim() || null,
    phone: document.getElementById("emp-phone").value.trim() || null,
    mobile: document.getElementById("emp-mobile").value.trim() || null,
    agreement_kind: document.getElementById("emp-agreement-kind").value,
    agreement_type: document.getElementById("emp-agreement-type").value,
    dispatcher_group_id: document.getElementById("emp-dispatcher-group").value
      ? parseInt(document.getElementById("emp-dispatcher-group").value) : null,
    cvr_number: document.getElementById("emp-cvr-group").style.display !== "none"
      ? (document.getElementById("emp-cvr").value || null)
      : null,
    fuldloennet: document.getElementById("emp-fuldloennet").checked,
    active: document.getElementById("emp-active").checked,
    hire_date: readDatePicker("emp-hire"),
    termination_date: readDatePicker("emp-termination") || "9999-12-31",
    work_schedule: readScheduleTable(),
    paragraf_56: document.getElementById("emp-paragraf56").checked,
    paragraf_56_start_date: document.getElementById("emp-paragraf56").checked
      ? readDatePicker("emp-paragraf56-start") : null,
    paragraf_56_end_date: document.getElementById("emp-paragraf56").checked
      ? readDatePicker("emp-paragraf56-end") : null,
    afloeser: document.getElementById("emp-afloeser").checked,
    ot_extra_alle_timer: document.getElementById("emp-ot-extra-alle-timer").checked,
    fast_bil: document.getElementById("emp-fast-bil").checked,
    fast_bil_vehicle_id: document.getElementById("emp-fast-bil-vehicle-id").value
      ? parseInt(document.getElementById("emp-fast-bil-vehicle-id").value) : null,
    absence_vehicle_id: document.getElementById("emp-absence-vehicle-id").value
      ? parseInt(document.getElementById("emp-absence-vehicle-id").value) : null,
    position_id: document.getElementById("emp-position").value
      ? parseInt(document.getElementById("emp-position").value) : null,
    seniority_date: readDatePicker("emp-seniority") || null,
    cpr_number: document.getElementById("emp-cpr").value.trim() || null,
    personaleforening: document.getElementById("emp-personaleforening").checked,
    elev: document.getElementById("emp-elev").checked,
    elev_start_date: document.getElementById("emp-elev").checked ? (readDatePicker("emp-elev-start") || null) : null,
    elev_end_date: document.getElementById("emp-elev").checked ? (readDatePicker("emp-elev-end") || null) : null,
    voksenelev: document.getElementById("emp-elev").checked && document.getElementById("emp-voksenelev").checked,
    natarbejde_tillaeg: document.getElementById("emp-natarbejde").checked,
  };
  const isFunktionaer = body.agreement_kind === FUNKTIONAER;
  const missing = [];
  if (!body.employee_number) missing.push("Lønnummer");
  if (!body.first_name) missing.push("Fornavn");
  if (!body.last_name) missing.push("Efternavn");
  if (!body.hire_date) missing.push("Ansættelsesdato");
  if (!body.position_id) missing.push("Stilling");
  if (!body.email) missing.push("Email");
  if (isFunktionaer && !body.initials) missing.push("Initialer");
  if (!isFunktionaer && !body.tachograph_card_number) missing.push("Førerkortnummer");
  if (missing.length) {
    toast(`Udfyld: ${missing.join(", ")}`, "error");
    return;
  }
  if (!body.absence_vehicle_id) {
    toast("Vælg et vognnummer ved fravær fra listen", "error");
    return;
  }
  if (body.cpr_number && !body.cpr_number.endsWith("****") && !/^\d{6}-\d{4}$/.test(body.cpr_number)) {
    toast("CPR-nummer skal have formatet ddmmåå-xxxx", "error");
    return;
  }
  if (body.paragraf_56 && (!body.paragraf_56_start_date || !body.paragraf_56_end_date)) {
    toast("Udfyld start- og slutdato for §56", "error");
    return;
  }
  if (body.paragraf_56 && body.paragraf_56_end_date < body.paragraf_56_start_date) {
    toast("§56 slutdato skal være efter startdato", "error");
    return;
  }
  if (!isFunktionaer && body.elev && (!body.elev_start_date || !body.elev_end_date)) {
    toast("Udfyld start- og slutdato for elev", "error");
    return;
  }
  if (!isFunktionaer && body.elev && body.elev_end_date < body.elev_start_date) {
    toast("Elev slutdato skal være efter startdato", "error");
    return;
  }
  if (!(await checkEmployeeNumber())) {
    toast("Lønnummeret er allerede i brug", "error");
    return;
  }

  // Skift fra chauffør til funktionær med skjulte markeringer: spørg pr. markering (spec 3.3)
  const switchedToOffice = isFunktionaer && _empOriginalKind !== FUNKTIONAER;
  const hiddenFlags = [
    ["afloeser", "Afløser"], ["fast_bil", "Fast bil"], ["ot_extra_alle_timer", "Særaftale: Øvrig overtid for alle timer"],
  ].filter(([key]) => body[key]);
  if (switchedToOffice && hiddenFlags.length) {
    _showEmpHiddenFlags(id, body, hiddenFlags);
    return;
  }
  await _continueSaveEmployee(id, body);
}

async function _continueSaveEmployee(id, body) {
  if (!id) {
    try {
      const all = await GET("/api/employees?active_only=false");
      const nameMatches = all.filter(e =>
        e.first_name.trim().toLowerCase() === body.first_name.toLowerCase() &&
        e.last_name.trim().toLowerCase() === body.last_name.toLowerCase());
      const cardMatches = body.tachograph_card_number
        ? all.filter(e => (e.tachograph_card_number || "").trim().toLowerCase() === body.tachograph_card_number.toLowerCase())
        : [];
      if (nameMatches.length || cardMatches.length) {
        _showEmployeeDuplicateWarning(body, nameMatches, cardMatches);
        return;
      }
    } catch (_) { /* duplikat-tjek må ikke blokere oprettelse hvis den fejler */ }
  }
  await _saveEmployee(id, body);
}

async function _saveEmployee(id, body) {
  try {
    if (id) {
      await PATCH(`/api/employees/${id}`, body);
      toast("Medarbejder opdateret", "success");
    } else {
      await POST("/api/employees", body);
      toast("Medarbejder oprettet", "success");
    }
    closeModal("modal-employee");
    await loadEmployees();
    fillEmployeeFilter();
  } catch (e) { toast(e.message, "error"); }
}

let _pendingHiddenFlags = null;

function _showEmpHiddenFlags(id, body, flags) {
  _pendingHiddenFlags = { id, body, flags };
  const name = `${body.first_name} ${body.last_name}`;
  document.getElementById("emp-hidden-flags-body").innerHTML = `
    <p style="font-size:14px;margin-bottom:12px">
      <strong>${h(name)}</strong> har stadig følgende markeringer fra chauffør-tiden. Vælg for hver, om den skal beholdes eller fjernes.
    </p>
    ${flags.map(([key, label]) => `
      <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-top:1px solid var(--border)">
        <span style="font-size:13px">${h(label)}</span>
        <span style="display:flex;gap:14px;font-size:13px">
          <label style="display:flex;gap:4px;align-items:center;cursor:pointer"><input type="radio" name="hf-${key}" value="keep" checked> Behold</label>
          <label style="display:flex;gap:4px;align-items:center;cursor:pointer"><input type="radio" name="hf-${key}" value="remove"> Fjern</label>
        </span>
      </div>`).join("")}
  `;
  openModal("modal-emp-hidden-flags");
}

async function confirmEmpHiddenFlags() {
  if (!_pendingHiddenFlags) return;
  const { id, body, flags } = _pendingHiddenFlags;
  for (const [key] of flags) {
    if (document.querySelector(`input[name="hf-${key}"]:checked`)?.value === "remove") {
      body[key] = false;
      if (key === "fast_bil") body.fast_bil_vehicle_id = null;
    }
  }
  _pendingHiddenFlags = null;
  closeModal("modal-emp-hidden-flags");
  await _continueSaveEmployee(id, body);
}

let _pendingEmployeeBody = null;

function _showEmployeeDuplicateWarning(body, nameMatches, cardMatches) {
  _pendingEmployeeBody = body;
  const parts = [];
  if (cardMatches.length) {
    parts.push(`<p>Førerkortnummeret <b>${h(body.tachograph_card_number)}</b> er allerede registreret på: <b>${cardMatches.map(e => h(e.name)).join(", ")}</b>. Det kan ikke bruges igen.</p>`);
  }
  if (nameMatches.length) {
    parts.push(`<p>Der findes allerede en medarbejder med navnet <b>${h(body.first_name)} ${h(body.last_name)}</b>: <b>${nameMatches.map(e => h(e.name + " (" + e.employee_number + ")")).join(", ")}</b>.</p>`);
  }
  document.getElementById("emp-duplicate-warning-body").innerHTML = parts.join("");
  document.getElementById("btn-emp-duplicate-ok").style.display = cardMatches.length ? "none" : "";
  openModal("modal-emp-duplicate-warning");
}

function empDuplicateChange() {
  closeModal("modal-emp-duplicate-warning");
  _pendingEmployeeBody = null;
}

async function empDuplicateIgnore() {
  const body = _pendingEmployeeBody;
  closeModal("modal-emp-duplicate-warning");
  _pendingEmployeeBody = null;
  if (body) await _saveEmployee("", body);
}

// ── Anciennitet popup ──────────────────────────────────────────────────────
async function dismissAnciennitetsAlert(employeeId) {
  try {
    await POST(`/api/employees/${employeeId}/dismiss-anciennitet`, {});
  } catch (e) {
    console.error("Kunne ikke gemme afvisning af anciennitetsadvarsel:", e);
  }
  closeModal("modal-anciennitet");
}

async function checkAnciennitetsAlerts() {
  if (!state.currentUser?.permissions?.includes("anciennitet_alert")) return;
  try {
    // Serveren filtrerer allerede afviste medarbejdere fra (employees.anciennitet_dismissed_at),
    // se GET /api/employees/anciennitet-alerts – ingen klient-side dismiss-liste nødvendig.
    const alerts = await GET("/api/employees/anciennitet-alerts");
    if (alerts.length === 0) return;
    const a = alerts[0];
    document.getElementById("anciennitet-body").innerHTML = `
      <p style="font-size:14px;margin-bottom:8px">
        Medarbejder <strong>${h(a.employee_name)} (${h(a.employee_number)})</strong> har ny anciennitetsstatus.
      </p>
      <p style="font-size:13px;color:var(--text-light)">
        Ansat ${formatDateShort(a.hire_date)} – ${a.months_employed} måneder.
        ${a.suggested_agreement_type ? `Foreslået overenskomsttype: <strong>${a.suggested_agreement_type}</strong>` : ""}
      </p>
      ${alerts.length > 1 ? `<p style="font-size:12px;color:var(--text-light);margin-top:8px">+ ${alerts.length - 1} flere medarbejdere med ny anciennitetsstatus.</p>` : ""}
    `;
    document.getElementById("btn-goto-employee").onclick = async () => {
      closeModal("modal-anciennitet");
      setView("employees");
      await loadEmployees();
      openEditEmployee(a.employee_id);
    };
    document.getElementById("btn-anciennitet-done").onclick = () => dismissAnciennitetsAlert(a.employee_id);
    openModal("modal-anciennitet");
  } catch (e) {
    console.error("Anciennitet check fejlede:", e);
  }
}

// ── §56-advarsel popup ──────────────────────────────────────────────────────
async function dismissParagraf56Alert(employeeId, alertType) {
  try {
    await POST(`/api/employees/${employeeId}/dismiss-paragraf56-alert`, { alert_type: alertType });
  } catch (e) {
    console.error("Kunne ikke gemme afvisning af §56-advarsel:", e);
  }
  closeModal("modal-paragraf56-alert");
}

async function checkParagraf56Alerts() {
  if (!state.currentUser?.permissions?.includes("paragraf_56_alert")) return;
  try {
    const { upcoming, expired } = await GET("/api/employees/paragraf56-alerts");
    const alertType = expired.length ? "expired" : "upcoming";
    const alerts = expired.length ? expired : upcoming;
    if (alerts.length === 0) return;
    const a = alerts[0];
    document.getElementById("paragraf56-alert-title").innerHTML = alertType === "expired"
      ? "&#9888; §56 automatisk deaktiveret"
      : "&#128197; §56 udløber snart";
    document.getElementById("paragraf56-alert-body").innerHTML = alertType === "expired"
      ? `
        <p style="font-size:14px;margin-bottom:8px">
          Medarbejder <strong>${h(a.employee_name)} (${h(a.employee_number)})</strong>s §56-aftale er automatisk
          deaktiveret, da slutdatoen (${formatDateShort(a.paragraf_56_end_date)}) er overskredet.
        </p>
        ${alerts.length > 1 ? `<p style="font-size:12px;color:var(--text-light);margin-top:8px">+ ${alerts.length - 1} flere medarbejdere.</p>` : ""}
      `
      : `
        <p style="font-size:14px;margin-bottom:8px">
          Medarbejder <strong>${h(a.employee_name)} (${h(a.employee_number)})</strong>s §56-aftale udløber
          ${formatDateShort(a.paragraf_56_end_date)}.
        </p>
        ${alerts.length > 1 ? `<p style="font-size:12px;color:var(--text-light);margin-top:8px">+ ${alerts.length - 1} flere medarbejdere.</p>` : ""}
      `;
    document.getElementById("btn-goto-employee-paragraf56").onclick = async () => {
      closeModal("modal-paragraf56-alert");
      setView("employees");
      await loadEmployees();
      openEditEmployee(a.employee_id);
    };
    document.getElementById("btn-paragraf56-alert-done").onclick = () => dismissParagraf56Alert(a.employee_id, alertType);
    openModal("modal-paragraf56-alert");
  } catch (e) {
    console.error("§56-advarsel check fejlede:", e);
  }
}

// ── Jubilæum / elev / fødselsdag ───────────────────────────────────────────
const _MILESTONE_TITLES = {
  birthday: "&#127874; Rund fødselsdag",
  jubilee:  "&#127942; Jubilæum",
  elev:     "&#127891; Elevtid slutter",
};

async function dismissMilestoneAlert(employeeId, alertKey) {
  try {
    await POST(`/api/employees/${employeeId}/dismiss-milestone-alert`, { alert_key: alertKey });
  } catch (e) {
    console.error("Kunne ikke gemme afvisning af advarsel:", e);
  }
  closeModal("modal-milestone-alert");
}

async function checkMilestoneAlerts() {
  if (!["birthday_alert", "jubilee_alert", "elev_alert"].some(_hasPerm)) return;
  try {
    const alerts = await GET("/api/employees/milestone-alerts");
    if (alerts.length === 0) return;
    const a = alerts[0];
    document.getElementById("milestone-alert-title").innerHTML = _MILESTONE_TITLES[a.kind] || "&#128197; Mærkedag";
    document.getElementById("milestone-alert-body").innerHTML = `
      <p style="font-size:14px;margin-bottom:8px">
        Medarbejder <strong>${h(a.employee_name)} (${h(a.employee_number)})</strong> ${h(a.label)}
        den ${formatDateShort(a.event_date)}.
      </p>
      ${alerts.length > 1 ? `<p style="font-size:12px;color:var(--text-light);margin-top:8px">+ ${alerts.length - 1} flere.</p>` : ""}
    `;
    document.getElementById("btn-goto-employee-milestone").onclick = async () => {
      closeModal("modal-milestone-alert");
      setView("employees");
      await loadEmployees();
      openEditEmployee(a.employee_id);
    };
    // "Luk" afviser advarslen præcis som "OK" – den kommer ikke igen for denne bruger
    document.getElementById("btn-milestone-alert-ok").onclick = () => dismissMilestoneAlert(a.employee_id, a.alert_key);
    document.getElementById("btn-milestone-alert-close").onclick = () => dismissMilestoneAlert(a.employee_id, a.alert_key);
    openModal("modal-milestone-alert");
  } catch (e) {
    console.error("Mærkedags-advarsel check fejlede:", e);
  }
}

// ── Vehicles ────────────────────────────────────────────────────────────────
let _editingVehicleId = null;

async function loadVehicles() {
  setLoading(true);
  try {
    state.vehicles = await GET("/api/vehicles");
    if (!state.dispatcherGroups.length) { try { state.dispatcherGroups = await GET("/api/employees/dispatcher-groups"); } catch (_) {} }
    switchVehiclesTab(state.vehiclesTab || "vognpark");
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

function fillVehicleDispatcherGroupSelect(selectedId = null) {
  const sel = document.getElementById("vehicle-dispatcher-group");
  sel.innerHTML = `<option value="">— Ingen —</option>` + state.dispatcherGroups
    .map(g => `<option value="${g.id}" ${g.id === selectedId ? "selected" : ""}>${h(g.name)}</option>`)
    .join("");
}

function switchVehiclesTab(tab) {
  state.vehiclesTab = tab;
  ["vognpark", "all"].forEach(t => {
    const btn = document.getElementById(`veh-tab-${t}`);
    if (btn) {
      btn.style.borderBottomColor = t === tab ? "var(--primary)" : "transparent";
      btn.style.color             = t === tab ? "var(--primary)" : "var(--text-light)";
      btn.style.fontWeight        = t === tab ? "700" : "600";
    }
  });
  renderVehicleList();
}

function renderVehicleList() {
  const query = (document.getElementById("vehicle-search")?.value || "").toLowerCase().trim();
  const container = document.getElementById("vehicle-list");
  container.innerHTML = "";
  let vehicles = state.vehicles;
  if (state.vehiclesTab === "vognpark") {
    vehicles = vehicles.filter(v => v.vognpark);
  }
  if (query) {
    vehicles = vehicles.filter(v =>
      v.registration_number.toLowerCase().includes(query) ||
      String(v.vehicle_number).toLowerCase().includes(query)
    );
  }
  if (vehicles.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="icon">🚛</div><h3>Ingen vogne</h3></div>`;
    return;
  }
  vehicles = vehicles.slice().sort((a, b) =>
    String(a.vehicle_number ?? "").localeCompare(String(b.vehicle_number ?? ""), "da", { numeric: true })
  );
  for (const v of vehicles) {
    const initials = v.registration_number.slice(0, 2).toUpperCase();
    const div = document.createElement("div");
    div.className = "emp-card";
    div.style.cursor = "pointer";
    div.innerHTML = `
      <div class="emp-avatar">${initials}</div>
      <div class="emp-info">
        <div class="emp-name">${v.registration_number}</div>
        <div class="emp-sub">Vognnr. ${v.vehicle_number}</div>
      </div>
      ${state.currentUser?.permissions?.includes("manage_vehicles") ? `<button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); openEditVehicle(${v.id})">Rediger</button>` : ""}
    `;
    div.addEventListener("click", () => {
      if (state.currentUser?.permissions?.includes("manage_vehicles")) openEditVehicle(v.id);
    });
    container.appendChild(div);
  }
}

function openNewVehicleModal() {
  _editingVehicleId = null;
  document.getElementById("vehicle-modal-title").textContent = "Opret vogn";
  document.getElementById("vehicle-reg").value = "";
  document.getElementById("vehicle-num").value = "";
  document.getElementById("vehicle-description").value = "";
  document.getElementById("vehicle-vognpark").checked = false;
  fillVehicleDispatcherGroupSelect(null);
  document.getElementById("vehicle-fast-bil-group").style.display = "none"; // vognen findes ikke endnu - kan ikke være nogens Fast bil
  document.getElementById("vehicle-delete-btn").classList.add("hidden");
  openModal("modal-vehicle");
}

function openEditVehicle(id) {
  const v = state.vehicles.find(x => x.id === id);
  if (!v) return;
  _editingVehicleId = id;
  document.getElementById("vehicle-modal-title").textContent = "Rediger vogn";
  document.getElementById("vehicle-reg").value = v.registration_number;
  document.getElementById("vehicle-num").value = v.vehicle_number;
  document.getElementById("vehicle-description").value = v.description || "";
  document.getElementById("vehicle-vognpark").checked = v.vognpark;
  fillVehicleDispatcherGroupSelect(v.dispatcher_group_id);
  document.getElementById("vehicle-fast-bil-group").style.display = "";
  document.getElementById("vehicle-fast-bil-employee").value = v.fast_bil_employee_name || "—";
  document.getElementById("vehicle-delete-btn").classList.remove("hidden");
  openModal("modal-vehicle");
}

async function saveVehicle() {
  const reg = document.getElementById("vehicle-reg").value.trim();
  const num = document.getElementById("vehicle-num").value.trim();
  if (!reg || !num) { toast("Udfyld begge felter", "error"); return; }
  const body = {
    registration_number: reg,
    vehicle_number: num,
    description: document.getElementById("vehicle-description").value.trim() || null,
    vognpark: document.getElementById("vehicle-vognpark").checked,
    dispatcher_group_id: document.getElementById("vehicle-dispatcher-group").value
      ? parseInt(document.getElementById("vehicle-dispatcher-group").value) : null,
  };
  try {
    if (_editingVehicleId) {
      await PATCH(`/api/vehicles/${_editingVehicleId}`, body);
      toast("Vogn opdateret", "success");
    } else {
      await POST("/api/vehicles", body);
      toast("Vogn oprettet", "success");
    }
    closeModal("modal-vehicle");
    await loadVehicles();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteVehicle() {
  if (!_editingVehicleId) return;
  const v = state.vehicles.find(x => x.id === _editingVehicleId);
  if (!confirm(`Slet vogn ${v?.registration_number}?`)) return;
  try {
    await api("DELETE", `/api/vehicles/${_editingVehicleId}`);
    toast("Vogn slettet", "success");
    closeModal("modal-vehicle");
    await loadVehicles();
  } catch (e) { toast(e.message, "error"); }
}


// ── Import ─────────────────────────────────────────────────────────────────
function _setImportBtnsDisabled(on) {
  ["btn-import-ddd-input"].forEach(id => {
    const b = document.getElementById(id);
    if (b) b.disabled = on;
  });
}

// Vagte der afventer bekræftelse (lukket lønperiode) – opbevarer den funktion,
// der genimporterer med allow_closed_period=true, indtil brugeren har svaret.
let _pendingClosedPeriod = null;

async function _handleImportResult(result, reimportWithClosedPeriod) {
  if (result.closed_period_candidates?.length) {
    const rows = result.closed_period_candidates.map(c => `
      <div style="margin-bottom:10px;font-size:13px;line-height:1.5">
        <b>${h(c.employee)}</b>: ${formatDateTime(c.start_time)} &rarr; ${formatDateTime(c.end_time)}<br>
        <span style="color:var(--text-light)">Lukket periode: ${formatDate(c.period_start)} – ${formatDate(c.period_end)}</span>
      </div>`).join("");
    document.getElementById("closed-period-count").textContent = result.closed_period_candidates.length;
    document.getElementById("closed-period-list").innerHTML = rows;
    _pendingClosedPeriod = { result, reimportWithClosedPeriod };
    openModal("modal-closed-period-confirm");
    return;
  }
  _showImportResult(result);
}

async function confirmImportClosedPeriod(allow) {
  const pending = _pendingClosedPeriod;
  _pendingClosedPeriod = null;
  closeModal("modal-closed-period-confirm");
  if (!pending) return;

  if (!allow) {
    // Nej: vagterne importeres ikke – husk afvisningen, så de springes over
    // automatisk (uden ny bekræftelse) ved fremtidige genimporter af filen.
    try {
      await POST("/api/decline-closed-period-import", {
        items: pending.result.closed_period_candidates.map(c => ({
          employee_id: c.employee_id, start_time: c.start_time, end_time: c.end_time,
        })),
      });
    } catch (e) {
      toast("Kunne ikke gemme afvisningen: " + e.message, "error");
    }
    _showImportResult({ ...pending.result, declined_closed_period: pending.result.closed_period_candidates.length });
    return;
  }

  _setImportBtnsDisabled(true);
  try {
    const result = await pending.reimportWithClosedPeriod();
    _showImportResult(result);
  } catch (e) {
    toast(e.message, "error");
  } finally {
    _setImportBtnsDisabled(false);
  }
}

function _showImportResult(result) {
  const msg = `Importeret: ${result.imported} aktivitet${result.imported !== 1 ? "er" : ""}.` +
    (result.skipped ? ` Sprunget over: ${result.skipped}.` : "") +
    (result.declined_closed_period ? ` Afvist (lukket periode): ${result.declined_closed_period}.` : "") +
    (result.files_processed !== undefined ? ` Filer behandlet: ${result.files_processed}.` : "") +
    (result.errors?.length ? ` Fejl: ${result.errors.join("; ")}` : "");
  document.getElementById("import-result").textContent = msg;

  const allClean = !result.skipped && !result.errors?.length && !result.zero_activity_files?.length
    && !result.declined_closed_period;
  const body = document.getElementById("import-result-modal-body");

  if (allClean) {
    body.innerHTML = `
      <div style="text-align:center;padding:16px 0">
        <div style="font-size:40px;line-height:1;margin-bottom:10px">&#9989;</div>
        <div style="font-size:16px;font-weight:600;color:var(--primary)">Importering succesfuld</div>
        <div style="color:var(--text-light);margin-top:6px">
          ${result.imported} aktivitet${result.imported !== 1 ? "er" : ""} importeret fra
          ${result.files_processed} fil${result.files_processed !== 1 ? "er" : ""}.
        </div>
      </div>`;
  } else {
    const rowStyle = "margin-bottom:12px;font-size:13px;line-height:1.5";
    const rows = [];
    rows.push(`<div style="${rowStyle}"><b>Filer behandlet:</b> ${result.files_processed}</div>`);
    rows.push(`<div style="${rowStyle}"><b>Importeret:</b> ${result.imported}</div>`);
    if (result.updated) {
      rows.push(`<div style="${rowStyle}"><b>Opdateret (km-data udfyldt):</b> ${result.updated}</div>`);
    }
    if (result.skipped_unknown_card) {
      rows.push(`<div style="${rowStyle};color:var(--danger)">
        <b>Sprunget over – ukendt førerkortnummer (${result.skipped_unknown_card}):</b><br>
        ${(result.unknown_cards || []).map(h).join(", ")}<br>
        <span style="font-weight:400">Kontrollér at kortnummeret er registreret korrekt på medarbejderen i Stamdata (de første 14 tegn, uden udskiftnings-/fornyelsescifre).</span>
      </div>`);
    }
    if (result.skipped_duplicate) {
      rows.push(`<div style="${rowStyle}"><b>Sprunget over – allerede importeret:</b> ${result.skipped_duplicate}</div>`);
    }
    if (result.skipped_declined) {
      rows.push(`<div style="${rowStyle}"><b>Sprunget over – tidligere afvist (lukket periode):</b> ${result.skipped_declined}</div>`);
    }
    if (result.skipped_conflict) {
      rows.push(`<div style="${rowStyle};color:var(--danger)">
        <b>Kunne IKKE rettes – kolliderer med en anden aktivitet (${result.skipped_conflict}):</b><br>
        <span style="font-weight:400">Der findes en anden, allerede gemt aktivitet for samme medarbejder på nøjagtig samme starttidspunkt – formentlig en ældre duplikat-aktivitet, der skal ryddes op manuelt. Se detaljer i hændelsesloggen.</span>
      </div>`);
    }
    if (result.declined_closed_period) {
      rows.push(`<div style="${rowStyle}"><b>Ikke importeret – lukket lønperiode (afvist):</b> ${result.declined_closed_period}</div>`);
    }
    if (result.zero_activity_files?.length) {
      rows.push(`<div style="${rowStyle}">
        <b>Fil(er) uden aktiviteter (${result.zero_activity_files.length}):</b><br>
        ${result.zero_activity_files.map(h).join(", ")}
      </div>`);
    }
    if (result.errors?.length) {
      rows.push(`<div style="${rowStyle};color:var(--danger)">
        <b>Fejl (${result.errors.length}):</b>
        <ul style="margin:4px 0 0 18px">${result.errors.map(e => `<li>${h(e)}</li>`).join("")}</ul>
      </div>`);
    }
    body.innerHTML = rows.join("");
  }
  openModal("modal-import-result");
}

async function importDddInputFolder() {
  _setImportBtnsDisabled(true);
  document.getElementById("import-result").textContent = "Tjekker ddd_input-mappen (inkl. undermapper)...";
  try {
    const result = await POST("/api/import-ddd", {});
    await _handleImportResult(result, () =>
      POST("/api/import-ddd?allow_closed_period=true", {}));
  } catch (e) {
    toast(e.message, "error");
    document.getElementById("import-result").textContent = "Fejl: " + e.message;
  } finally { _setImportBtnsDisabled(false); }
}

// ── Payroll ────────────────────────────────────────────────────────────────
async function loadPayrollPreview() {
  setLoading(true);
  try {
    const qs = state.currentPeriodStart ? `?period_start=${state.currentPeriodStart}` : "";
    const data = await GET(`/api/payroll/preview${qs}`);
    renderPayrollPreview(data);
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

function renderPayrollPreview(data) {
  const container = document.getElementById("payroll-preview-container");
  container.innerHTML = "";
  state.payrollData = data;
  state.hasUnresolvedPending = !!data.has_unresolved_pending;
  state.periodClosed = data.period_status === "closed";
  const koerLoenBtn = document.getElementById("btn-koer-loen");
  if (koerLoenBtn) koerLoenBtn.classList.toggle("btn-muted", state.hasUnresolvedPending || state.periodClosed);

  if (data.period_status === "closed") {
    const closedWarn = document.createElement("div");
    closedWarn.className = "alert-banner mb-16";
    closedWarn.innerHTML = `<span class="icon">🔒</span><div class="text"><h4>Perioden er låst</h4>Lønnen er allerede kørt for denne periode. Åbn perioden igen under Administration, hvis der skal foretages ændringer.</div>`;
    container.appendChild(closedWarn);
  }

  if (data.has_unresolved_pending) {
    const warn = document.createElement("div");
    warn.className = "alert-banner mb-16";
    warn.innerHTML = `<span class="icon">⚠️</span><div class="text"><h4>Afventende aktiviteter</h4>Der er aktiviteter, der afventer handling. Før lønnen kan køres, skal alle aktiviteter enten godkendes eller deaktiveres. Kun godkendte aktiviteter tæller med i lønnen.</div>`;
    container.appendChild(warn);
  }

  data.employees.sort((a, b) => (a.employee_name || "").localeCompare(b.employee_name || "", "da"));
  let any = false;
  for (const emp of data.employees) {
    if (emp.activity_count === 0 && emp.afspadsering_hours === 0) continue;
    any = true;
    // Regnes i backend præcis som Lønafregningens total (inkl. ferie og afspadsering).
    const grandTotalKr = emp.grand_total_kr;
    const el = document.createElement("div");
    el.className = "payroll-employee";
    el.innerHTML = `
      <div class="payroll-emp-header">
        <div class="emp-avatar" style="width:34px;height:34px;font-size:13px">${h(emp.employee_name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase())}</div>
        <div class="payroll-emp-info">
          <h3>${h(emp.employee_name)}</h3>
          <div class="emp-meta">${h(emp.employee_number)} · ${h(emp.agreement_type)}</div>
        </div>
        <button class="btn btn-sm payroll-proeve-btn" onclick="proevekoersel(${emp.employee_id})">📊 Prøvekørsel</button>
        <button class="btn btn-sm btn-secondary" onclick="downloadTimeseddel(${emp.employee_id})" title="Download PDF-timeseddel" style="padding:5px 10px">⬇ PDF</button>
        <button class="btn btn-sm btn-primary" onclick="sendTimeseddel(${emp.employee_id})" title="Send timeseddel til medarbejder" style="padding:5px 10px;background:#317423;border-color:#317423">✉ Send</button>
      </div>
      <div class="payroll-col-header">
        <div></div>
        <div>Antal</div>
        <div>Antal (tt.mm)</div>
        <div>Sats</div>
        <div>DKK</div>
      </div>
      <div class="payroll-rows">
        ${payrollRow("Normal tid", emp.normal_hours, emp.hourly_rates?.normal ?? emp.hourly_rate)}
        ${payrollRow("Springertillæg", emp.springer_enabled ? emp.normal_hours : 0, emp.springer_rate)}
        ${payrollRow("Overtid 1 time før", emp.ot_before_hours, emp.ot_rates?.["Overtid 1 time før"])}
        ${payrollRow("Overtid 1-3 timer efter", (emp.ot_13_hours || 0) + (emp.sh_kode8_hours || 0), emp.ot_rates?.["Overtid 1-3 timer efter"])}
        ${payrollRow("Øvrig overtid", (emp.ot_extra_hours || 0) + (emp.sh_kode9_hours || 0), emp.ot_rates?.["Øvrigt overtid"])}
        ${payrollRow("Søgnehelligdag", emp.sh_fuldloennet_hours, emp.hourly_rates?.sh_fuldloennet ?? emp.hourly_rate)}
        ${payrollRow("SH-Udbetaling", emp.sh_timeloennet_hours, emp.hourly_rates?.sh_timeloennet ?? emp.hourly_rate)}
        ${payrollRowSalt("Salttillæg", emp.salt_hours, emp.salt_rate, emp.salt_kr)}
        ${payrollRowOvernight("Overnatning", emp.overnight_count, emp.overnight_rate, emp.overnight_kr)}
        ${payrollRowOvernight("DOB Overnatning", emp.dob_overnight_count, emp.dob_overnight_rate, emp.dob_overnight_kr)}
        ${payrollRow("Ferie", emp.ferie_hours, emp.hourly_rates?.ferie ?? emp.hourly_rate)}
        ${payrollRow("Afspadsering", emp.afspadsering_hours, emp.hourly_rates?.afspadsering ?? emp.hourly_rate)}
        ${payrollRow("Sygdom med løn", emp.sygdom_hours, emp.hourly_rates?.sygdom ?? emp.hourly_rate)}
        ${payrollRow("§56 syg", emp.paragraf_56_syg_hours, emp.dagpenge_sats)}
        ${payrollRow("Barn 1.sygedag", emp.barn_1sygedag_u_loen_hours, emp.dagpenge_sats)}
        ${payrollRow("Feriefri", emp.feriefri_hours, emp.hourly_rates?.feriefri ?? emp.hourly_rate)}
        ${payrollRow("Barsel", emp.barsel_hours, emp.hourly_rates?.barsel ?? emp.hourly_rate)}
        ${payrollRow("Kursus/Skole", emp.skole_kursus_hours, emp.hourly_rates?.skole_kursus ?? emp.hourly_rate)}
        <div class="payroll-row total">
          <div>I alt</div>
          <div>${fmtHours(emp.total_hours)}</div>
          <div>${fmtHoursHM(emp.total_hours)}</div>
          <div></div>
          <div class="text-right">${fmtKr(grandTotalKr)}</div>
        </div>
      </div>`;
    container.appendChild(el);
  }
  if (!any) {
    container.innerHTML += `<div class="empty-state"><div class="icon">💰</div><h3>Ingen godkendte aktiviteter i perioden</h3></div>`;
  }
}

function payrollRow(label, hours, rate = null) {
  if (!hours || hours < 0.001) return "";
  const kr = rate != null ? hours * rate : null;
  return `<div class="payroll-row">
    <div class="label">${label}</div>
    <div>${fmtHours(hours)}</div>
    <div>${fmtHoursHM(hours)}</div>
    <div style="color:var(--text-light);font-size:12px">${rate != null ? rate.toFixed(2) + " kr/t" : ""}</div>
    <div class="text-right">${kr != null ? fmtKr(kr) : ""}</div>
  </div>`;
}

function payrollRowSalt(label, hours, rate, kr) {
  if (!hours || hours < 0.001) return "";
  return `<div class="payroll-row">
    <div class="label">${label}</div>
    <div>${fmtHours(hours)}</div>
    <div>${fmtHoursHM(hours)}</div>
    <div style="color:var(--text-light);font-size:12px">${rate != null ? rate.toFixed(2) + " kr/t" : ""}</div>
    <div class="text-right">${fmtKr(kr)}</div>
  </div>`;
}

function payrollRowOvernight(label, count, rate, kr) {
  if (!count || count < 1) return "";
  return `<div class="payroll-row">
    <div class="label">${label}</div>
    <div>${count} gang${count !== 1 ? "e" : ""}</div>
    <div></div>
    <div style="color:var(--text-light);font-size:12px">${rate != null ? rate.toFixed(2) + " kr/gang" : ""}</div>
    <div class="text-right">${fmtKr(kr)}</div>
  </div>`;
}

function downloadTimeseddel(employeeId) {
  const periodStart = state.currentPeriodStart;
  if (!periodStart) { toast("Vælg en lønperiode først", "error"); return; }
  const url = `/api/timeseddel/${employeeId}/pdf?period_start=${periodStart}`;
  window.open(url, "_blank");
}

async function sendTimeseddel(employeeId) {
  const periodStart = state.currentPeriodStart;
  if (!periodStart) { toast("Vælg en lønperiode først", "error"); return; }
  const empData = (state.payrollData?.employees || []).find(e => e.employee_id === employeeId);
  const employeeName = empData?.employee_name || `medarbejder ${employeeId}`;
  if (!confirm(`Send timeseddel til ${employeeName}?`)) return;
  setLoading(true);
  try {
    const res = await POST(`/api/timeseddel/${employeeId}/send?period_start=${periodStart}`, {});
    toast(`Timeseddel sendt til ${res.sent_to}`, "success");
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

async function proevekoersel(employeeId = null) {
  state.proevekoerselEmployeeId = employeeId;
  document.getElementById("proeve-result").textContent = "";
  openModal("modal-proevekoersel");
}

async function confirmProevekoersel() {
  setLoading(true);
  try {
    const result = await downloadFile("/api/payroll/proevekoersel-gem", {
      period_start: state.currentPeriodStart || null,
      employee_id: state.proevekoerselEmployeeId || null,
    }, "proevekoersel.xlsx");
    toast(`Prøvekørsel downloadet: ${result.filename}`, "success");
    closeModal("modal-proevekoersel");
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

async function exportCsv() {
  if (state.periodClosed) {
    toast("Lønperioden er allerede låst – lønnen er allerede kørt for denne periode.", "error");
    return;
  }
  if (state.hasUnresolvedPending) {
    toast("Lønnen kan ikke køres – der er aktiviteter, der afventer handling. Godkend eller deaktiver dem først.", "error");
    return;
  }
  const p = state.periodInfo?.period;
  const fmt = iso => new Date(iso + "T00:00:00").toLocaleDateString("da-DK", { day: "numeric", month: "long", year: "numeric" });
  const periodTxt = p ? `${fmt(p.start_date)} – ${fmt(p.end_date)}` : "den aktuelle periode";
  document.getElementById("csv-confirm-text").innerHTML =
    `Er du sikker på, at du vil låse lønperioden <strong>${periodTxt}</strong>?<br><br>` +
    `Når perioden er låst, kan der ikke foretages flere ændringer i den. CSV-filen til Danløn downloades til din computer.`;
  document.getElementById("csv-result").textContent = "";
  openModal("modal-csv");
}

async function confirmExportCsv() {
  setLoading(true);
  try {
    const result = await downloadFile("/api/payroll/export-csv", {
      period_start: state.currentPeriodStart || null,
    }, "danloen.csv");
    toast(`Danløn CSV downloadet: ${result.filename}`, "success");
    closeModal("modal-csv");
    await loadPeriodInfo(state.currentPeriodStart);
    await loadActivities();
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

// ── Lønafregning ─────────────────────────────────────────────────────────
function fillSettlementDispatcherGroupFilter() {
  const sel = document.getElementById("settlement-filter-dispatcher-group");
  if (!sel) return;
  const cur = sel.value;
  const visibleGroups = (state.dispatcherGroups || []).filter(g => g.visible_in_activity_overview);
  sel.innerHTML = `<option value="">Alle disponentgrupper</option>` +
    visibleGroups.map(g => `<option value="${g.id}">${h(g.name)}</option>`).join("");
  if (visibleGroups.find(g => String(g.id) === cur)) sel.value = cur;
}

function fillSettlementEmployeeFilter() {
  const sel = document.getElementById("settlement-filter-employee");
  if (!sel) return;
  const cur = sel.value;
  const groupFilter = document.getElementById("settlement-filter-dispatcher-group")?.value || "";
  let visible = (state.employees || []).filter(_empHasVisibleGroup);
  if (groupFilter) visible = visible.filter(e => _empInGroup(e, groupFilter));
  const placeholder = groupFilter ? "Alle i disponentgruppen" : "Alle medarbejdere";
  sel.innerHTML = `<option value="">${placeholder}</option>` +
    visible.slice().sort((a, b) => a.name.localeCompare(b.name, "da"))
      .map(e => `<option value="${e.id}">${h(e.name)} (${h(e.employee_number)})</option>`).join("");
  if (visible.find(e => String(e.id) === cur)) sel.value = cur;
}

function settlementDispatcherGroupFilterChanged() {
  fillSettlementEmployeeFilter();
  loadPayrollSettlement();
}

async function loadPayrollSettlement() {
  // Fra/Til følger den valgte lønperiode, medmindre "Vælg datoer" er slået til (period_bar.js)
  usePeriodRange("payroll-settlement");
  setLoading(true);
  try {
    fillSettlementDispatcherGroupFilter();
    fillSettlementEmployeeFilter();
    const p = new URLSearchParams();
    const from = readDatePicker("settlement-from-dp");
    const to   = readDatePicker("settlement-to-dp");
    if (from && to) { p.set("date_from", from); p.set("date_to", to); }
    const employeeId = document.getElementById("settlement-filter-employee")?.value;
    const groupId = document.getElementById("settlement-filter-dispatcher-group")?.value;
    if (employeeId) p.set("employee_id", employeeId);
    else if (groupId) p.set("dispatcher_group_id", groupId);
    const qs = p.toString() ? `?${p.toString()}` : "";
    const data = await GET(`/api/payroll-settlement/preview${qs}`);
    renderPayrollSettlement(data);
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

function fmtHM(hours) {
  const totalMinutes = Math.round((hours || 0) * 60);
  const hh = Math.floor(totalMinutes / 60), mm = totalMinutes % 60;
  return `${hh}:${String(mm).padStart(2, "0")}`;
}

function fmtDecimalComma(v) {
  return (v || 0).toFixed(2).replace(".", ",");
}

function renderPayrollSettlement(data) {
  // period_status er "closed"/"open" når det viste interval matcher en hel
  // lønperiode præcist, ellers null (frit interval – altid eksporterbart,
  // bekræftet af bruger 2026-09-04).
  state.settlementPeriodStatus = data.period_status;

  const container = document.getElementById("settlement-preview-container");
  container.innerHTML = "";

  if (data.period_status === "open") {
    const info = document.createElement("div");
    info.className = "alert-banner mb-16";
    info.innerHTML = `<span class="icon">ℹ️</span><div class="text"><h4>Perioden er ikke låst endnu</h4>Eksport kræver, at lønnen er kørt for perioden under Lønkørsel (administratorer kan eksportere alligevel).</div>`;
    container.appendChild(info);
  } else if (data.period_status === null) {
    const info = document.createElement("div");
    info.className = "alert-banner mb-16";
    info.innerHTML = `<span class="icon">ℹ️</span><div class="text"><h4>Frit datointerval</h4>Intervallet matcher ikke en hel lønperiode – eksport er altid tilladt for netop dette interval.</div>`;
    container.appendChild(info);
  }

  const t = data.page_totals;
  const settlementLineItems = [
    ["Grundtimeløn inkl. tillæg", t.grundtimeloen_incl_tillaeg_kr],
    ["Overtid Timen før", t.ot_before_kr],
    ["Overtid 1-3 time efter", t.ot_13_kr],
    ["Øvrig overtid", t.ot_extra_kr],
  ];
  const gange = n => `${n} gang${n !== 1 ? "e" : ""}`;
  const settlementAbsenceItems = [
    ["Salttillæg", t.salt_kr],
    [`Overnatning (${gange(t.overnight_count)})`, t.overnight_kr],
    [`DOB Overnatning (${gange(t.dob_overnight_count)})`, t.dob_overnight_kr],
    ["Sygdom", t.sygdom_kr],
    ["Sygdom u. 8 uger", t.sygdom_u_8_uger_kr],
    ["Barn 1.sygedag", t.barn_1sygedag_kr],
    ["Barn 1.sygedag u. 8 uger", t.barn_1sygedag_u_8_uger_kr],
    ["Graviditetsbetinget sygdom", t.graviditetsbetinget_sygdom_kr],
    ["§56 syg", t.paragraf_56_syg_kr],
    ["Barsel", t.barsel_kr],
    ["Feriefri", t.feriefri_kr],
    ["Ferie", t.ferie_kr],
    ["Skole/kursus", t.skole_kursus_kr],
    ["Afspadsering", t.afspadsering_kr],
  ];
  const settlementRow = ([label, kr]) =>
    `<div class="payroll-row"><div class="label">${h(label)}</div><div></div><div></div><div class="text-right">${fmtKr(kr)}</div></div>`;
  const totalCard = document.createElement("div");
  totalCard.className = "payroll-employee";
  totalCard.innerHTML = `
    <div class="payroll-emp-header"><div class="payroll-emp-info"><h3>Total sum for perioden</h3></div></div>
    <div class="payroll-rows">
      ${settlementLineItems.filter(([, kr]) => kr > 0).map(settlementRow).join("")}
      <div class="payroll-row total"><div>Total uden fravær</div><div></div><div></div><div class="text-right">${fmtKr(t.total_excl_absence_kr)}</div></div>
      ${settlementAbsenceItems.filter(([, kr]) => kr > 0).map(settlementRow).join("")}
      <div class="payroll-row total"><div>Total sum for denne periode</div><div></div><div></div><div class="text-right">${fmtKr(t.total_kr)}</div></div>
    </div>`;
  container.appendChild(totalCard);

  if (data.employees.length === 0) {
    container.innerHTML += `<div class="empty-state"><div class="icon">🧾</div><h3>Ingen aktive medarbejdere</h3></div>`;
    return;
  }

  for (const emp of data.employees) {
    const el = document.createElement("div");
    el.className = "payroll-employee";
    const headlineParts = [`${h(emp.agreement_type)} (${emp.agreement_rate.toFixed(2)} kr/t)`];
    if (emp.personal_supplement_rate > 0) {
      headlineParts.push(`Personligt tillæg: ${emp.personal_supplement_rate.toFixed(2)} kr/t`);
    }
    if (emp.springer_enabled) {
      headlineParts.push(`Springertillæg: ${emp.springer_rate.toFixed(2)} kr/t`);
    }
    // Tyk linje over første række i hver ny uge (mandag) – kun visning, CSV uændret
    const dayRows = emp.days.map((day, i) => {
      const vognnummer = day.absence_type || day.vehicle_number || "";
      const newWeek = i > 0 && day.date !== emp.days[i - 1].date
        && new Date(day.date + "T12:00:00").getDay() === 1;
      return `<tr${newWeek ? ' class="week-start"' : ""}>
        <td>${formatDate(day.date)}</td>
        <td class="num">${fmtHM(day.normal)}</td>
        <td class="num">${fmtHM(day.ot_before)}</td>
        <td class="num">${fmtHM(day.ot_13)}</td>
        <td class="num">${fmtHM(day.ot_extra)}</td>
        <td class="num">${fmtDecimalComma(day.total_hours)}</td>
        <td class="num">${fmtKr(day.total_kr)}</td>
        <td>${h(vognnummer)}</td>
        <td class="num">${fmtKr(day.total_kr)}</td>
      </tr>`;
    }).join("");
    // Kun visning (2026-10-07): summer de viste (afrundede) dagsværdier, så totalen
    // stemmer med kolonnen. CSV-eksporten bygges på serveren og påvirkes ikke.
    const sumHM = key => emp.days.reduce((s, d) => s + Math.round((d[key] || 0) * 60), 0) / 60;
    const sumTotalHours = emp.days.reduce((s, d) => s + Math.round((d.total_hours || 0) * 100), 0) / 100;
    el.innerHTML = `
      <div class="payroll-emp-header">
        <div class="emp-avatar" style="width:34px;height:34px;font-size:13px">${h(emp.employee_name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase())}</div>
        <div class="payroll-emp-info">
          <h3>${h(emp.employee_name)}</h3>
          <div class="emp-meta">${h(emp.employee_number)} · ${headlineParts.map(h).join(" · ")}</div>
        </div>
      </div>
      <div style="overflow-x:auto">
        <table class="settlement-table">
          <thead><tr>
            <th>Dato</th><th class="num">Normal timer</th><th class="num">Overtid 1 time før</th>
            <th class="num">Overtid 1-3 timer efter</th><th class="num">Øvrig overtid</th><th class="num">Total tid</th>
            <th class="num">Total i kr.</th><th>Vognnummer</th><th class="num">Beløb</th>
          </tr></thead>
          <tbody>
            ${dayRows}
            <tr class="settlement-total-row">
              <td>Total</td>
              <td class="num">${fmtHM(sumHM("normal"))}</td>
              <td class="num">${fmtHM(sumHM("ot_before"))}</td>
              <td class="num">${fmtHM(sumHM("ot_13"))}</td>
              <td class="num">${fmtHM(sumHM("ot_extra"))}</td>
              <td class="num">${fmtDecimalComma(sumTotalHours)}</td>
              <td class="num">${fmtKr(emp.total_kr)}</td><td></td><td class="num">${fmtKr(emp.total_kr)}</td>
            </tr>
          </tbody>
        </table>
      </div>`;
    container.appendChild(el);
  }
}

async function exportSettlementCsv() {
  const isAdmin = state.currentUser?.role === "admin";
  // Et frit interval uden eksakt periodematch (period_status === null) er
  // altid eksporterbart – kun en eksakt matchet, ULÅST periode blokerer
  // ikke-admin (bekræftet af bruger 2026-09-04).
  if (state.settlementPeriodStatus === "open" && !isAdmin) {
    toast("Lønperioden skal være låst, før den kan eksporteres. Kør løn under Lønkørsel-fanen først.", "error");
    return;
  }
  document.getElementById("settlement-csv-result").textContent = "";
  openModal("modal-settlement-csv");
}

async function confirmExportSettlementCsv() {
  setLoading(true);
  try {
    const body = {};
    const from = readDatePicker("settlement-from-dp");
    const to   = readDatePicker("settlement-to-dp");
    if (from && to) { body.date_from = from; body.date_to = to; }
    const employeeId = document.getElementById("settlement-filter-employee")?.value;
    const groupId = document.getElementById("settlement-filter-dispatcher-group")?.value;
    if (employeeId) body.employee_id = parseInt(employeeId);
    else if (groupId) body.dispatcher_group_id = parseInt(groupId);
    const result = await downloadFile("/api/payroll-settlement/export-csv", body, "lonafregning.csv");
    toast(`Lønafregning downloadet: ${result.filename}`, "success");
    closeModal("modal-settlement-csv");
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

// ── Absence Overview ──────────────────────────────────────────────────────
async function loadAbsenceOverview() {
  usePeriodRange("absence-overview");   // se period_bar.js
  setLoading(true);
  try {
    const from = readDatePicker("absence-from-dp");
    const to   = readDatePicker("absence-to-dp");
    const qs   = (from && to) ? `?date_from=${from}&date_to=${to}` : "";
    const data = await GET(`/api/absence-overview/data${qs}`);
    window._absenceOverviewData = data;
    renderAbsenceOverview(data);
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

function renderAbsenceOverview(data) {
  const container = document.getElementById("absence-overview-container");
  container.innerHTML = "";

  const emps = (data.employees || []).slice().sort(
    (a, b) => (a.employee_name || "").localeCompare(b.employee_name || "", "da")
  );

  if (emps.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="icon">📅</div><h3>Ingen fravær i valgt periode</h3></div>`;
    return;
  }

  for (const emp of emps) {
    const absences = Object.entries(emp.absences || {});
    if (absences.length === 0) continue;
    absences.sort((a, b) => a[1].label.localeCompare(b[1].label, "da"));

    const totalHours = absences.reduce((s, [, v]) => s + v.hours, 0);
    const totalDays  = absences.reduce((s, [, v]) => s + v.days,  0);

    const rows = absences.map(([, ainfo]) => `
      <div class="payroll-row">
        <div class="label">${ainfo.label}</div>
        <div>${ainfo.days} dag${ainfo.days !== 1 ? "e" : ""}</div>
        <div>${(ainfo.rate || 0) > 0 ? fmtKr(ainfo.rate) + "/t" : ""}</div>
        <div class="text-right">${fmtHours(ainfo.hours)}</div>
      </div>`).join("");

    const initials = emp.employee_name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase();
    const el = document.createElement("div");
    el.className = "payroll-employee";
    el.innerHTML = `
      <div class="payroll-emp-header">
        <div class="emp-avatar" style="width:34px;height:34px;font-size:13px">${initials}</div>
        <div class="payroll-emp-info">
          <h3>${h(emp.employee_name)}</h3>
          <div class="emp-meta">${h(emp.employee_number)}</div>
        </div>
      </div>
      <div class="payroll-col-header">
        <div>Fraværstype</div>
        <div>Dage</div>
        <div>Sats</div>
        <div class="text-right">Timer</div>
      </div>
      <div class="payroll-rows">
        ${rows}
        <div class="payroll-row total">
          <div>I alt</div>
          <div>${totalDays} dag${totalDays !== 1 ? "e" : ""}</div>
          <div></div>
          <div class="text-right">${fmtHours(totalHours)}</div>
        </div>
      </div>`;
    container.appendChild(el);
  }
}

async function exportAbsencePerEmployee() {
  // Reset modal
  document.querySelector('input[name="emp-export-scope"][value="all"]').checked = true;
  empExportScopeChanged();

  // Fetch options and populate dropdowns
  try {
    const opts = await GET("/api/absence-overview/employee-options");

    const grpSel = document.getElementById("emp-export-group-select");
    grpSel.innerHTML = "";
    (opts.dispatcher_groups || []).forEach(g => {
      const o = document.createElement("option");
      o.value = g.id; o.textContent = g.name;
      grpSel.appendChild(o);
    });

    const empSel = document.getElementById("emp-export-employee-select");
    empSel.innerHTML = "";
    (opts.employees || []).forEach(e => {
      const o = document.createElement("option");
      o.value = e.id; o.textContent = e.name;
      empSel.appendChild(o);
    });
  } catch (err) { toast("Kunne ikke hente medarbejdere: " + err.message, "error"); return; }

  openModal("modal-export-per-employee");
}

function empExportScopeChanged() {
  const scope = document.querySelector('input[name="emp-export-scope"]:checked').value;
  document.getElementById("emp-export-group-row").style.display    = scope === "group"    ? "" : "none";
  document.getElementById("emp-export-employee-row").style.display = scope === "employee" ? "" : "none";
}

function doExportPerEmployee() {
  const from  = readDatePicker("absence-from-dp");
  const to    = readDatePicker("absence-to-dp");
  const scope = document.querySelector('input[name="emp-export-scope"]:checked').value;
  const p = new URLSearchParams();
  if (from && to) { p.set("date_from", from); p.set("date_to", to); }
  if (scope === "group") {
    p.set("dispatcher_group_id", document.getElementById("emp-export-group-select").value);
  } else if (scope === "employee") {
    p.set("employee_id", document.getElementById("emp-export-employee-select").value);
  }
  const qs = p.toString() ? "?" + p.toString() : "";
  window.location.href = `/api/absence-overview/export-per-employee${qs}`;
  closeModal("modal-export-per-employee");
}

function exportAbsencePerType() {
  const list = document.getElementById("export-type-list");
  list.innerHTML = "";
  const allCb = document.getElementById("export-type-all");
  allCb.checked = true;

  const types = (window._absenceOverviewData || {}).absence_types || [];
  types.forEach(t => {
    const lbl = document.createElement("label");
    lbl.style.cssText = "display:flex;align-items:center;gap:8px;cursor:pointer";
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.value = t.value; cb.checked = true;
    cb.style.cssText = "width:15px;height:15px;cursor:pointer";
    cb.addEventListener("change", exportTypeCbChanged);
    lbl.appendChild(cb);
    lbl.appendChild(document.createTextNode(t.label));
    list.appendChild(lbl);
  });
  openModal("modal-export-per-type");
}

function exportTypeAllChanged() {
  const checked = document.getElementById("export-type-all").checked;
  document.querySelectorAll("#export-type-list input[type=checkbox]")
    .forEach(cb => { cb.checked = checked; });
}

function exportTypeCbChanged() {
  const all = [...document.querySelectorAll("#export-type-list input[type=checkbox]")];
  document.getElementById("export-type-all").checked = all.every(cb => cb.checked);
}

function doExportPerType() {
  const from   = readDatePicker("absence-from-dp");
  const to     = readDatePicker("absence-to-dp");
  const allCb  = document.getElementById("export-type-all");
  const selected = [...document.querySelectorAll("#export-type-list input[type=checkbox]:checked")]
    .map(cb => cb.value);

  const p = new URLSearchParams();
  if (from && to) { p.set("date_from", from); p.set("date_to", to); }
  if (!allCb.checked && selected.length > 0) {
    selected.forEach(v => p.append("absence_type", v));
  }
  const qs = p.toString() ? "?" + p.toString() : "";
  window.location.href = `/api/absence-overview/export-per-type${qs}`;
  closeModal("modal-export-per-type");
}

// ── Auth ───────────────────────────────────────────────────────────────────
function showLoginOverlay() {
  const el = document.getElementById("login-overlay");
  el.style.display = "flex";
  document.getElementById("login-error").style.display = "none";
  document.getElementById("login-initials").value = "";
  document.getElementById("login-password").value = "";
  setTimeout(() => document.getElementById("login-initials").focus(), 50);
}

function hideLoginOverlay() {
  document.getElementById("login-overlay").style.display = "none";
}

async function doLogin() {
  const initials = document.getElementById("login-initials").value.trim().toUpperCase();
  const password = document.getElementById("login-password").value;
  if (!initials || !password) {
    showLoginError("Angiv initialer og adgangskode");
    return;
  }
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ initials, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const msg = typeof err.detail === "string" ? err.detail : "Login mislykkedes";
      showLoginError(msg);
      return;
    }
    const user = await res.json();
    state.currentUser = user;
    hideLoginOverlay();
    applyRoleVisibility();
    updateHeaderUser();
    await loadApp();
  } catch (e) {
    showLoginError("Netværksfejl – prøv igen");
  }
}

function showLoginError(msg) {
  const el = document.getElementById("login-error");
  el.textContent = msg;
  el.style.display = "block";
  const card = document.getElementById("login-card");
  card.classList.remove("login-shake");
  void card.offsetWidth; // reflow for at genstartte animationen
  card.classList.add("login-shake");
  card.addEventListener("animationend", () => card.classList.remove("login-shake"), { once: true });
}

async function doLogout() {
  const userName = state.currentUser?.name || "";
  try { await api("POST", "/api/auth/logout", {}); } catch {}

  const farewell = document.createElement("div");
  farewell.style.cssText = "position:fixed;inset:0;background:#317423;z-index:10000;display:flex;align-items:center;justify-content:center;transition:opacity .35s";
  farewell.innerHTML = `<p style="color:#fff;font-size:30px;font-weight:700;margin:0;letter-spacing:.5px">På gensyn${userName ? ", " + h(userName) : ""}!</p>`;
  document.body.appendChild(farewell);

  await new Promise(r => setTimeout(r, 2000));

  // Nulstil state og vis login mens farewell-overlay stadig dækker (z-index 10000)
  state.currentUser = null;
  showLoginOverlay();
  document.getElementById("header-user").style.display = "none";
  document.getElementById("btn-logout").style.display = "none";

  // Fade det grønne overlay ud – afslører login-skærmen, ikke appen
  farewell.style.opacity = "0";
  await new Promise(r => setTimeout(r, 350));
  farewell.remove();
}

function applyRoleVisibility() {
  const perms = state.currentUser?.permissions || [];
  document.querySelectorAll("[data-perm-require]").forEach(el => {
    el.style.display = perms.includes(el.dataset.permRequire) ? "" : "none";
  });
  // Skjul en menugruppe helt, hvis brugeren ikke har adgang til nogen af dens punkter.
  document.querySelectorAll(".sidebar-section").forEach(section => {
    const items = [...section.querySelectorAll(".sidebar-item")];
    section.style.display = items.some(el => el.style.display !== "none") ? "" : "none";
  });
}

function _roleDisplayName(roleName) {
  const r = state.roles.find(r => r.name === roleName);
  return r ? r.display_name : roleName;
}

function updateHeaderUser() {
  const u = state.currentUser;
  if (!u) return;
  const label = _roleDisplayName(u.role);
  document.getElementById("header-user").textContent = `${u.name} (${label})`;
  document.getElementById("header-user").style.display = "";
  document.getElementById("btn-logout").style.display = "";
}

async function doSSOLogin() {
  if (!window.msal || !ENTRA_TENANT_ID || !ENTRA_CLIENT_ID) return;
  const btn = document.getElementById("btn-sso-login");
  if (btn) { btn.disabled = true; btn.style.opacity = "0.6"; }
  try {
    const msalInstance = new msal.PublicClientApplication({
      auth: {
        clientId: ENTRA_CLIENT_ID,
        authority: `https://login.microsoftonline.com/${ENTRA_TENANT_ID}`,
        redirectUri: window.location.origin,
      },
      cache: { cacheLocation: "sessionStorage" },
    });
    const result = await msalInstance.loginPopup({
      scopes: ["openid", "profile", "email"],
    });
    const res = await fetch("/api/auth/sso", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: result.idToken }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showLoginError(typeof err.detail === "string" ? err.detail : "SSO fejlede – er din Entra-konto tilknyttet en bruger i systemet?");
      return;
    }
    const user = await res.json();
    state.currentUser = user;
    hideLoginOverlay();
    applyRoleVisibility();
    updateHeaderUser();
    await loadApp();
  } catch (e) {
    const code = String(e?.errorCode || e?.message || "");
    if (!code.includes("user_cancelled") && !code.includes("interaction_in_progress")) {
      showLoginError("Microsoft-login fejlede – prøv igen");
    }
  } finally {
    if (btn) { btn.disabled = false; btn.style.opacity = "1"; }
  }
}

async function attemptSSO() {
  if (!window.msal || !ENTRA_TENANT_ID || !ENTRA_CLIENT_ID) return false;
  try {
    const msalInstance = new msal.PublicClientApplication({
      auth: {
        clientId: ENTRA_CLIENT_ID,
        authority: `https://login.microsoftonline.com/${ENTRA_TENANT_ID}`,
        redirectUri: window.location.origin,
      },
      cache: { cacheLocation: "sessionStorage" },
    });
    let result;
    const accounts = msalInstance.getAllAccounts();
    if (accounts.length > 0) {
      result = await msalInstance.acquireTokenSilent({
        account: accounts[0],
        scopes: ["openid", "profile", "email"],
      });
    } else {
      result = await msalInstance.ssoSilent({
        scopes: ["openid", "profile", "email"],
      });
    }
    const res = await fetch("/api/auth/sso", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: result.idToken }),
    });
    if (!res.ok) return false;
    const user = await res.json();
    state.currentUser = user;
    hideLoginOverlay();
    updateHeaderUser();
    applyRoleVisibility();
    return true;
  } catch {
    return false;
  }
}

async function initAuth() {
  try {
    const user = await fetch("/api/auth/me").then(r => r.ok ? r.json() : null);
    if (user) {
      state.currentUser = user;
      hideLoginOverlay();
      applyRoleVisibility();
      updateHeaderUser();
      return true;
    }
  } catch {}
  const ssoOk = await attemptSSO();
  if (ssoOk) return true;
  showLoginOverlay();
  return false;
}

// ── Administration ─────────────────────────────────────────────────────────
function switchAdminTab(tab) {
  ["users", "period", "log"].forEach(t => {
    document.getElementById(`admin-pane-${t}`).style.display = t === tab ? "" : "none";
    const btn = document.getElementById(`admin-tab-${t}`);
    btn.style.background = t === tab ? "var(--primary)" : "var(--bg)";
    btn.style.color = t === tab ? "#fff" : "var(--text)";
  });
  if (tab === "users") loadUsersTable();
  if (tab === "log") loadAuditLog();
}

async function openAdminModal() {
  const p = state.periodInfo?.period;
  const fmt = iso => new Date(iso + "T00:00:00").toLocaleDateString("da-DK", { day: "numeric", month: "long", year: "numeric" });
  const periodTxt = p ? `${fmt(p.start_date)} – ${fmt(p.end_date)}` : "den aktuelle periode";
  document.getElementById("admin-period-text").innerHTML =
    `Vil du åbne lønperioden <strong>${periodTxt}</strong> igen?`;
  document.getElementById("admin-result").textContent = "";
  switchAdminTab("period");
  openModal("modal-admin");
}

async function loadUsersTable() {
  if (!state.roles.length) {
    try { state.roles = await GET("/api/roles"); } catch {}
  }
  try {
    const users = await GET("/api/users");
    const tbody = document.getElementById("users-table-body");
    if (!users.length) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--text-light)">Ingen brugere</td></tr>`;
      return;
    }
    tbody.innerHTML = users.map(u => `
      <tr style="border-bottom:1px solid var(--border);${!u.active ? "opacity:.55" : ""}">
        <td style="padding:8px 10px">${h(u.name)}</td>
        <td style="padding:8px 10px;font-weight:600">${h(u.initials)}</td>
        <td style="padding:8px 10px">${h(u.email || "")}</td>
        <td style="padding:8px 10px">${_roleDisplayName(u.role)}</td>
        <td style="padding:8px 10px">
          <span style="padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;
            background:${u.active ? "#d4edcc" : "#eee"};color:${u.active ? "#317423" : "#888"}">
            ${u.active ? "Aktiv" : "Inaktiv"}
          </span>
        </td>
        <td style="padding:8px 10px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" onclick="openEditUserModal(${u.id})" style="font-size:12px;padding:4px 8px">Rediger</button>
          ${u.id !== state.currentUser?.id ? `
          <button class="btn btn-${u.active ? "danger" : "primary"}" onclick="toggleUserActive(${u.id},${u.active})"
                  style="font-size:12px;padding:4px 8px;margin-left:4px">
            ${u.active ? "Deaktiver" : "Aktiver"}
          </button>` : ""}
        </td>
      </tr>`).join("");
  } catch (e) { toast(e.message, "error"); }
}

async function loadAuditLog() {
  try {
    const entries = await GET("/api/users/audit-log");
    const actionLabels = {
      approve: "Godkendt", deactivate: "Deaktiveret", reopen: "Genåbnet",
      split: "Splittet", create_activity: "Oprettet aktivitet", update_activity: "Opdateret aktivitet",
      payroll_run: "Løn kørt", create_user: "Bruger oprettet", update_user: "Bruger opdateret",
      delete_user: "Bruger slettet",
    };
    const tbody = document.getElementById("audit-log-body");
    if (!entries.length) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:20px;color:var(--text-light)">Ingen hændelser</td></tr>`;
      return;
    }
    tbody.innerHTML = entries.map(e => {
      const ts = e.timestamp ? new Date(e.timestamp).toLocaleString("da-DK") : "";
      return `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:6px 10px">${ts}</td>
        <td style="padding:6px 10px;font-weight:600">${h(e.user_initials || "")}</td>
        <td style="padding:6px 10px">${h(actionLabels[e.action] || e.action)}</td>
        <td style="padding:6px 10px;color:var(--text-light)">${h(e.details || "")}</td>
      </tr>`;
    }).join("");
  } catch (e) { toast(e.message, "error"); }
}

async function _populateRoleDropdown(selectId, selectedValue) {
  try {
    if (!state.roles.length) state.roles = await GET("/api/roles");
    const sel = document.getElementById(selectId);
    sel.innerHTML = state.roles.map(r =>
      `<option value="${r.name}"${r.name === selectedValue ? " selected" : ""}>${r.display_name}</option>`
    ).join("");
  } catch {
    const sel = document.getElementById(selectId);
    if (sel) sel.innerHTML = `<option value="${selectedValue || ""}">${selectedValue || "Fejl"}</option>`;
  }
}

let _editUserId = null;
async function openCreateUserModal() {
  _editUserId = null;
  document.getElementById("user-form-title").textContent = "Opret bruger";
  document.getElementById("user-form-id").value = "";
  document.getElementById("user-form-name").value = "";
  document.getElementById("user-form-initials").value = "";
  document.getElementById("user-form-email").value = "";
  document.getElementById("user-form-password").value = "";
  document.getElementById("user-form-password-label").innerHTML = "Adgangskode <span style='color:var(--danger)'>*</span>";
  document.getElementById("user-form-password-hint").style.display = "none";
  await _populateRoleDropdown("user-form-role", "lonbogholder");
  openModal("modal-user-form");
}

async function openEditUserModal(userId) {
  try {
    const users = await GET("/api/users");
    const u = users.find(x => x.id === userId);
    if (!u) return;
    _editUserId = userId;
    document.getElementById("user-form-title").textContent = "Rediger bruger";
    document.getElementById("user-form-id").value = u.id;
    document.getElementById("user-form-name").value = u.name;
    document.getElementById("user-form-initials").value = u.initials;
    document.getElementById("user-form-email").value = u.email || "";
    document.getElementById("user-form-password").value = "";
    document.getElementById("user-form-password-label").textContent = "Ny adgangskode";
    document.getElementById("user-form-password-hint").style.display = "";
    await _populateRoleDropdown("user-form-role", u.role);
    openModal("modal-user-form");
  } catch (e) { toast(e.message, "error"); }
}

async function submitUserForm() {
  const name = document.getElementById("user-form-name").value.trim();
  const initials = document.getElementById("user-form-initials").value.trim().toUpperCase();
  const email = document.getElementById("user-form-email").value.trim();
  const role = document.getElementById("user-form-role").value;
  const password = document.getElementById("user-form-password").value;

  if (!name || !initials) { toast("Navn og initialer er påkrævet", "error"); return; }
  if (!_editUserId && !password) { toast("Adgangskode er påkrævet", "error"); return; }

  try {
    if (_editUserId) {
      const body = { name, initials, email, role };
      if (password) body.password = password;
      await api("PATCH", `/api/users/${_editUserId}`, body);
      toast("Bruger opdateret");
    } else {
      await api("POST", "/api/users", { name, initials, email, role, password });
      toast("Bruger oprettet", "success");
    }
    closeModal("modal-user-form");
    refreshUserViews();
  } catch (e) { toast(e.message, "error"); }
}

async function toggleUserActive(userId, currentlyActive) {
  try {
    await api("PATCH", `/api/users/${userId}`, { active: !currentlyActive });
    toast(currentlyActive ? "Bruger deaktiveret" : "Bruger aktiveret");
    refreshUserViews();
  } catch (e) { toast(e.message, "error"); }
}

function refreshUserViews() {
  if (state.currentView === "users-admin") {
    if (state.usersAdminTab === "users") loadUsersInAdminView();
    else if (state.usersAdminTab === "roles") loadRolesAdminView();
  }
  if (document.getElementById("modal-admin")?.classList.contains("open")) loadUsersTable();
}

function switchUsersAdminTab(tab) {
  state.usersAdminTab = tab;
  ["users", "roles", "log"].forEach(t => {
    const pane = document.getElementById(`ua-pane-${t}`);
    const btn  = document.getElementById(`ua-tab-${t}`);
    if (pane) pane.style.display = t === tab ? "" : "none";
    if (btn) {
      btn.style.borderBottomColor = t === tab ? "var(--primary)" : "transparent";
      btn.style.color = t === tab ? "var(--primary)" : "var(--text-light)";
      btn.style.fontWeight = t === tab ? "700" : "600";
    }
  });
  const btnUsers = document.getElementById("btn-admin-users-create");
  const btnRoles = document.getElementById("btn-admin-roles-create");
  if (btnUsers) btnUsers.style.display = tab === "users" ? "" : "none";
  if (btnRoles) btnRoles.style.display = tab === "roles" ? "" : "none";

  if (tab === "roles") loadRolesAdminView();
  if (tab === "log")   loadAuditLogView();
}

async function loadUsersAdminView() {
  if (!state.roles.length) {
    try { state.roles = await GET("/api/roles"); } catch {}
  }
  if (!state.usersAdminTab) state.usersAdminTab = "users";
  switchUsersAdminTab(state.usersAdminTab);
  if (state.usersAdminTab === "users") await loadUsersInAdminView();
}

async function loadUsersInAdminView() {
  const tbody = document.getElementById("users-admin-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="6" style="padding:24px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    const users = await GET("/api/users");
    if (!users.length) {
      tbody.innerHTML = `<tr><td colspan="6" style="padding:24px;text-align:center;color:var(--text-light)">Ingen brugere oprettet endnu</td></tr>`;
      return;
    }
    tbody.innerHTML = users.map((u, i) => `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"};${!u.active ? "opacity:.5" : ""}">
        <td style="padding:11px 14px">${h(u.name)}</td>
        <td style="padding:11px 14px;font-weight:600;font-family:monospace">${h(u.initials)}</td>
        <td style="padding:11px 14px;color:var(--text-light)">${h(u.email || "—")}</td>
        <td style="padding:11px 14px">${_roleDisplayName(u.role)}</td>
        <td style="padding:11px 14px">
          <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;
            background:${u.active ? "#d4edcc" : "#eee"};color:${u.active ? "#317423" : "#999"}">
            ${u.active ? "Aktiv" : "Inaktiv"}
          </span>
        </td>
        <td style="padding:11px 14px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" onclick="openEditUserModal(${u.id})"
                  style="font-size:13px;padding:5px 12px">✏️ Rediger</button>
          ${u.id !== state.currentUser?.id ? `
          <button class="btn btn-${u.active ? "danger" : "primary"}"
                  onclick="toggleUserActive(${u.id}, ${u.active})"
                  style="font-size:13px;padding:5px 12px;margin-left:6px">
            ${u.active ? "Deaktiver" : "Aktiver"}
          </button>` : `<span style="font-size:12px;color:var(--text-light);margin-left:8px">(dig selv)</span>`}
        </td>
      </tr>`).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" style="padding:24px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

// ── Roller-admin ────────────────────────────────────────────────────────────
async function loadRolesAdminView() {
  const tbody = document.getElementById("roles-admin-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="4" style="padding:24px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    state.roles = await GET("/api/roles");
    if (!state.roles.length) {
      tbody.innerHTML = `<tr><td colspan="4" style="padding:24px;text-align:center;color:var(--text-light)">Ingen roller</td></tr>`;
      return;
    }
    tbody.innerHTML = state.roles.map((r, i) => {
      const effectivePerms = r.is_system ? Object.keys(PERMISSION_LABELS) : (r.permissions || []);
      const chips = effectivePerms.map(p =>
        `<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;background:#d4edcc;color:#317423;margin:2px">${PERMISSION_LABELS[p] || p}</span>`
      ).join("") || `<span style="font-size:12px;color:var(--text-light)">Ingen rettigheder</span>`;
      const systemBadge = r.is_system
        ? `<span style="font-size:10px;background:#e0e0e0;color:#555;padding:1px 6px;border-radius:8px;margin-left:6px;font-family:sans-serif">system</span>` : "";
      return `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
        <td style="padding:11px 14px;font-family:monospace;font-weight:600">${r.name}${systemBadge}</td>
        <td style="padding:11px 14px">${r.display_name}</td>
        <td style="padding:11px 14px">${chips}</td>
        <td style="padding:11px 14px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" onclick="openEditRoleModal(${r.id})"
                  style="font-size:13px;padding:5px 12px">✏️ Rediger</button>
          ${!r.is_system ? `
          <button class="btn btn-danger" onclick="deleteRole(${r.id}, '${r.display_name.replace(/'/g, "\\'")}' )"
                  style="font-size:13px;padding:5px 12px;margin-left:6px">🗑 Slet</button>` : ""}
        </td>
      </tr>`;
    }).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="4" style="padding:24px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

let _editRoleId = null;

function openCreateRoleModal() {
  _editRoleId = null;
  document.getElementById("role-form-title").textContent = "Opret rolle";
  document.getElementById("role-form-id").value = "";
  document.getElementById("role-form-name").value = "";
  document.getElementById("role-form-name").disabled = false;
  document.getElementById("role-form-name-hint").style.display = "";
  document.getElementById("role-form-display").value = "";
  _renderPermCheckboxes([], false);
  openModal("modal-role-form");
}

function openEditRoleModal(roleId) {
  const role = state.roles.find(r => r.id === roleId);
  if (!role) return;
  _editRoleId = roleId;
  document.getElementById("role-form-title").textContent = `Rediger: ${role.display_name}`;
  document.getElementById("role-form-id").value = role.id;
  document.getElementById("role-form-name").value = role.name;
  document.getElementById("role-form-name").disabled = true;
  document.getElementById("role-form-name-hint").style.display = "none";
  document.getElementById("role-form-display").value = role.display_name;
  _renderPermCheckboxes(role.permissions || [], role.is_system);
  openModal("modal-role-form");
}

function _renderPermCheckboxes(selectedPerms, isSystem) {
  const effectivePerms = isSystem ? Object.keys(PERMISSION_LABELS) : selectedPerms;
  document.getElementById("role-form-permissions").innerHTML =
    Object.entries(PERMISSION_LABELS).map(([key, label]) => `
      <label style="display:flex;align-items:center;gap:10px;cursor:${isSystem ? "default" : "pointer"};font-size:14px">
        <input type="checkbox" value="${key}" ${effectivePerms.includes(key) ? "checked" : ""}
               ${isSystem ? "disabled" : ""}
               style="width:15px;height:15px;accent-color:var(--primary);cursor:${isSystem ? "default" : "pointer"}">
        ${label}
        <span title="${h(PERMISSION_DESCRIPTIONS[key] || "")}"
              style="display:inline-flex;align-items:center;justify-content:center;width:14px;height:14px;border-radius:50%;border:1px solid var(--border);color:var(--text-light);font-size:10px;font-style:italic;font-family:serif;cursor:help;flex-shrink:0">i</span>
      </label>`).join("") +
    (isSystem ? `<p style="font-size:12px;color:var(--text-light);margin-top:8px;font-style:italic">Systemrollers rettigheder kan ikke ændres</p>` : "");
}

async function submitRoleForm() {
  const display = document.getElementById("role-form-display").value.trim();
  const name    = document.getElementById("role-form-name").value.trim();
  if (!display) { toast("Visningsnavn er påkrævet", "error"); return; }
  if (!_editRoleId && !name) { toast("Rollenavn er påkrævet", "error"); return; }
  if (!_editRoleId && !/^[a-z0-9_]+$/.test(name)) {
    toast("Rollenavn: kun små bogstaver, tal og underscore", "error"); return;
  }
  const permissions = [...document.querySelectorAll("#role-form-permissions input:checked")].map(cb => cb.value);
  try {
    if (_editRoleId) {
      await api("PATCH", `/api/roles/${_editRoleId}`, { display_name: display, permissions });
      toast("Rolle opdateret");
    } else {
      await api("POST", "/api/roles", { name, display_name: display, permissions });
      toast("Rolle oprettet", "success");
    }
    closeModal("modal-role-form");
    state.roles = [];
    loadRolesAdminView();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteRole(roleId, displayName) {
  if (!confirm(`Vil du slette rollen "${displayName}"?\nDette kan ikke fortrydes.`)) return;
  try {
    await api("DELETE", `/api/roles/${roleId}`);
    toast(`Rollen "${displayName}" er slettet`);
    state.roles = [];
    loadRolesAdminView();
  } catch (e) { toast(e.message, "error"); }
}

// ── Stamdata ────────────────────────────────────────────────────────────────

function switchStamdataTab(tab) {
  ["agreement", "overtime", "supplement", "paytype", "absence", "cvr", "holiday", "dispatcher", "agreementkind", "position", "autoapproval"].forEach(t => {
    const pane = document.getElementById(`sd-pane-${t}`);
    const btn  = document.getElementById(`sd-tab-${t}`);
    if (pane) pane.style.display = t === tab ? "" : "none";
    if (btn) {
      btn.style.borderBottomColor = t === tab ? "var(--primary)" : "transparent";
      btn.style.color             = t === tab ? "var(--primary)" : "var(--text-light)";
      btn.style.fontWeight        = t === tab ? "700" : "600";
    }
  });
  document.getElementById("btn-stamdata-add-agreement").style.display  = tab === "agreement"  ? "" : "none";
  document.getElementById("btn-stamdata-add-overtime").style.display   = tab === "overtime"   ? "" : "none";
  document.getElementById("btn-stamdata-add-supplement").style.display = tab === "supplement" ? "" : "none";
  document.getElementById("btn-stamdata-add-paytype").style.display    = tab === "paytype"    ? "" : "none";
  document.getElementById("btn-stamdata-add-absence").style.display    = tab === "absence"    ? "" : "none";
  document.getElementById("btn-stamdata-add-cvr").style.display        = tab === "cvr"        ? "" : "none";
  document.getElementById("btn-stamdata-add-holiday").style.display    = tab === "holiday"    ? "" : "none";
  document.getElementById("btn-stamdata-add-dispatcher").style.display = tab === "dispatcher" ? "" : "none";
  document.getElementById("btn-stamdata-add-agreementkind").style.display = tab === "agreementkind" ? "" : "none";
  document.getElementById("btn-stamdata-add-position").style.display = tab === "position" ? "" : "none";
}

async function loadStamdata() {
  switchStamdataTab("agreement");
  await Promise.all([
    loadStamdataAgreementTypes(),
    loadStamdataOvertimeRates(),
    loadStamdataSupplements(),
    loadStamdataPayTypes(),
    loadStamdataAbsenceTypes(),
    loadStamdataCvrNumbers(),
    loadStamdataHolidays(),
    loadStamdataDispatcherGroups(),
    loadStamdataAgreementKinds(),
    loadStamdataPositions(),
    loadStamdataAutoApproval(),
  ]);
}

async function loadStamdataAutoApproval() {
  const badge = document.getElementById("auto-approval-status-badge");
  const btn = document.getElementById("btn-toggle-auto-approval");
  if (!badge || !btn) return;
  try {
    const settings = await GET("/api/auto-approval/settings");
    state.autoApprovalEnabled = settings.enabled;
    renderAutoApprovalStatus();
  } catch (e) {
    badge.textContent = "Kunne ikke hente status";
  }
}

function renderAutoApprovalStatus() {
  const badge = document.getElementById("auto-approval-status-badge");
  const btn = document.getElementById("btn-toggle-auto-approval");
  if (!badge || !btn) return;
  if (state.autoApprovalEnabled) {
    badge.textContent = "Slået til";
    badge.className = "stat-chip approved";
    btn.textContent = "Slå fra";
    btn.className = "btn btn-danger";
  } else {
    badge.textContent = "Slået fra";
    badge.className = "stat-chip deact";
    btn.textContent = "Slå til";
    btn.className = "btn btn-success";
  }
}

async function toggleAutoApproval() {
  const newValue = !state.autoApprovalEnabled;
  try {
    const result = await POST("/api/auto-approval/settings", { enabled: newValue });
    state.autoApprovalEnabled = result.enabled;
    renderAutoApprovalStatus();
    applyAutoApprovalVisibility();
    toast(state.autoApprovalEnabled ? "Auto-godkendelse slået til" : "Auto-godkendelse slået fra");
  } catch (e) { toast(e.message, "error"); }
}

async function loadStamdataAgreementTypes() {
  const tbody = document.getElementById("stamdata-agreement-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="3" style="padding:20px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    const rows = await GET("/api/stamdata/agreement-types");
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="3" style="padding:20px;text-align:center;color:var(--text-light)">Ingen overenskomsttyper oprettet endnu</td></tr>`;
      return;
    }
    loadFutureRates();   // static/js/agreement_rates.js
    tbody.innerHTML = rows.map((r, i) => `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
        <td style="padding:10px 14px">${h(r.name)}</td>
        <td style="padding:10px 14px;text-align:right;font-variant-numeric:tabular-nums">${r.hourly_rate.toFixed(2).replace(".", ",")} kr</td>
        <td style="padding:10px 14px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px"
                  onclick="openStamdataAgreementModal(${r.id}, ${jq(r.name)}, ${r.hourly_rate})">Rediger</button>
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;color:var(--danger);border-color:var(--danger);margin-left:4px"
                  onclick="deleteStamdataAgreement(${r.id}, ${jq(r.name)})">Slet</button>
        </td>
      </tr>`).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="3" style="padding:20px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

async function loadStamdataOvertimeRates() {
  const tbody = document.getElementById("stamdata-overtime-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="3" style="padding:20px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    const rows = await GET("/api/stamdata/overtime-rates");
    state.stamdataOvertimeRates = rows;
    tbody.innerHTML = rows.map((r, i) => `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
        <td style="padding:10px 14px">${h(r.label)}</td>
        <td style="padding:10px 14px;text-align:right;font-variant-numeric:tabular-nums">${r.rate.toFixed(2).replace(".", ",")} kr</td>
        <td style="padding:10px 14px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px"
                  onclick="openStamdataRateModal(${r.id}, ${jq(r.label)}, ${r.rate}, 'overtime')">Rediger</button>
          ${r.is_user_created ? `<button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;color:var(--danger);border-color:var(--danger);margin-left:4px"
                  onclick="deleteStamdataRate(${r.id}, ${jq(r.label)}, 'overtime')">Slet</button>` : ""}
        </td>
      </tr>`).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="3" style="padding:20px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

async function loadStamdataSupplements() {
  const tbody = document.getElementById("stamdata-supplement-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="3" style="padding:20px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    const rows = await GET("/api/stamdata/supplements");
    state.stamdataSupplements = rows;
    tbody.innerHTML = rows.map((r, i) => `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
        <td style="padding:10px 14px">${h(r.label)}</td>
        <td style="padding:10px 14px;text-align:right;font-variant-numeric:tabular-nums">${r.rate.toFixed(2).replace(".", ",")} kr</td>
        <td style="padding:10px 14px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px"
                  onclick="openStamdataRateModal(${r.id}, ${jq(r.label)}, ${r.rate}, 'supplement')">Rediger</button>
          ${r.is_user_created ? `<button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;color:var(--danger);border-color:var(--danger);margin-left:4px"
                  onclick="deleteStamdataRate(${r.id}, ${jq(r.label)}, 'supplement')">Slet</button>` : ""}
        </td>
      </tr>`).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="3" style="padding:20px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

function _rateSourceLabel(rateSrc) {
  if (!rateSrc || rateSrc === "hourly") return "Timesats";
  const sepIdx = rateSrc.indexOf(":");
  if (sepIdx === -1) return rateSrc; // gammel fast værdi (ikke migreret, eller ukendt) – vis rå streng
  const kind = rateSrc.slice(0, sepIdx);
  const id = parseInt(rateSrc.slice(sepIdx + 1));
  const list = kind === "overtime" ? state.stamdataOvertimeRates : state.stamdataSupplements;
  const row = list?.find(r => r.id === id);
  return row ? row.label : rateSrc;
}

async function loadStamdataPayTypes() {
  const tbody = document.getElementById("stamdata-paytype-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="7" style="padding:20px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    const rows = await GET("/api/stamdata/pay-types");
    tbody.innerHTML = rows.map((r, i) => {
      const badge = (v, yes, no) => v
        ? `<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;background:#d4edcc;color:#317423">${yes}</span>`
        : `<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;background:#fee2e2;color:#b71c1c">${no}</span>`;
      const qtyLabel = r.csv_quantity_type === "count" ? "Antal" : "Timer";
      const rateLabel = _rateSourceLabel(r.csv_rate_source);
      return `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
        <td style="padding:10px 14px">${h(r.label)}</td>
        <td style="padding:10px 14px;text-align:center;font-family:monospace;font-weight:600">${h(r.danloen_code) || '<span style="color:var(--text-light);font-style:italic;font-weight:400">ikke sat</span>'}</td>
        <td style="padding:10px 14px;text-align:center">${badge(r.include_in_csv, "Ja", "Nej")}</td>
        <td style="padding:10px 14px;text-align:center;font-size:12px">${h(qtyLabel)}</td>
        <td style="padding:10px 14px;text-align:center;font-size:12px">${h(rateLabel)}</td>
        <td style="padding:10px 14px;text-align:center">${badge(r.csv_include_rate, "Ja", "Nej")}</td>
        <td style="padding:10px 14px;text-align:center">${badge(r.csv_include_total, "Ja", "Nej")}</td>
        <td style="padding:10px 14px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px"
                  onclick="openStamdataPayTypeModal(${r.id}, ${jq(r.label)}, ${jq(r.danloen_code)}, ${r.include_in_csv}, ${jq(r.csv_quantity_type)}, ${jq(r.csv_rate_source)}, ${r.csv_include_rate}, ${r.csv_include_total})">Rediger</button>
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;color:var(--danger);border-color:var(--danger);margin-left:4px"
                  onclick="deleteStamdataPayType(${r.id}, ${jq(r.label)})">Slet</button>
        </td>
      </tr>`;
    }).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" style="padding:20px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

function openStamdataAgreementModal(id, name, rate) {
  document.getElementById("stamdata-agreement-id").value   = id   || "";
  document.getElementById("stamdata-agreement-name").value = name || "";
  document.getElementById("stamdata-agreement-rate").value = rate !== undefined ? rate : "";
  document.getElementById("stamdata-agreement-title").textContent =
    id ? "Rediger overenskomsttype" : "Tilføj overenskomsttype";
  openModal("modal-stamdata-agreement");
}

async function confirmStamdataAgreement() {
  const id   = document.getElementById("stamdata-agreement-id").value;
  const name = document.getElementById("stamdata-agreement-name").value.trim();
  const rate = parseFloat(document.getElementById("stamdata-agreement-rate").value);
  if (!name || isNaN(rate)) { toast("Udfyld navn og timesats", "error"); return; }
  try {
    if (id) {
      await PATCH(`/api/stamdata/agreement-types/${id}`, { name, hourly_rate: rate });
      toast("Overenskomsttype opdateret");
    } else {
      await POST("/api/stamdata/agreement-types", { name, hourly_rate: rate });
      toast("Overenskomsttype oprettet");
    }
    closeModal("modal-stamdata-agreement");
    await loadStamdataAgreementTypes();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteStamdataAgreement(id, name) {
  if (!confirm(`Slet overenskomsttypen "${name}"?`)) return;
  try {
    await DEL(`/api/stamdata/agreement-types/${id}`);
    toast("Overenskomsttype slettet");
    await loadStamdataAgreementTypes();
  } catch (e) { toast(e.message, "error"); }
}

function openStamdataRateModal(id, label, rate, type) {
  document.getElementById("stamdata-rate-id").value = id;
  document.getElementById("stamdata-rate-type").value = type;
  document.getElementById("stamdata-rate-label-display").textContent = label;
  document.getElementById("stamdata-rate-value").value = rate;
  document.getElementById("stamdata-rate-title").textContent =
    type === "overtime" ? "Rediger overtidssats" : "Rediger tillægssats";
  openModal("modal-stamdata-rate");
}

async function confirmStamdataRate() {
  const id   = document.getElementById("stamdata-rate-id").value;
  const type = document.getElementById("stamdata-rate-type").value;
  const rate = parseFloat(document.getElementById("stamdata-rate-value").value);
  if (isNaN(rate)) { toast("Ugyldig sats", "error"); return; }
  const url = type === "overtime"
    ? `/api/stamdata/overtime-rates/${id}`
    : `/api/stamdata/supplements/${id}`;
  try {
    await PATCH(url, { rate });
    toast("Sats opdateret");
    closeModal("modal-stamdata-rate");
    if (type === "overtime") await loadStamdataOvertimeRates();
    else                     await loadStamdataSupplements();
  } catch (e) { toast(e.message, "error"); }
}

function _buildRateSourceOptions(selectId, selectedValue) {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  let optionsHtml = `<option value="hourly">Timesats (overenskomst)</option>`;
  if (state.stamdataOvertimeRates?.length) {
    optionsHtml += `<optgroup label="Overtidssatser">` +
      state.stamdataOvertimeRates.map(r => `<option value="overtime:${r.id}">${h(r.label)}</option>`).join("") +
      `</optgroup>`;
  }
  if (state.stamdataSupplements?.length) {
    optionsHtml += `<optgroup label="Tillæg">` +
      state.stamdataSupplements.map(r => `<option value="supplement:${r.id}">${h(r.label)}</option>`).join("") +
      `</optgroup>`;
  }
  sel.innerHTML = optionsHtml;
  sel.value = selectedValue || "hourly";
}

function openStamdataPayTypeModal(id, label, code, inCsv, qtyType, rateSrc, incRate, incTotal) {
  document.getElementById("stamdata-paytype-id").value = id;
  document.getElementById("stamdata-paytype-label").value = label || "";
  document.getElementById("stamdata-paytype-code").value = code || "";
  document.getElementById("stamdata-paytype-incsv").checked = !!inCsv;
  document.getElementById("stamdata-paytype-qtytype").value = qtyType || "hours";
  _buildRateSourceOptions("stamdata-paytype-ratesrc", rateSrc);
  document.getElementById("stamdata-paytype-incrate").checked = incRate !== false;
  document.getElementById("stamdata-paytype-inctotal").checked = !!incTotal;
  openModal("modal-stamdata-paytype");
}

async function confirmStamdataPayType() {
  const id       = document.getElementById("stamdata-paytype-id").value;
  const label    = document.getElementById("stamdata-paytype-label").value.trim();
  const code     = document.getElementById("stamdata-paytype-code").value.trim();
  const inCsv    = document.getElementById("stamdata-paytype-incsv").checked;
  const qtyType  = document.getElementById("stamdata-paytype-qtytype").value;
  const rateSrc  = document.getElementById("stamdata-paytype-ratesrc").value;
  const incRate  = document.getElementById("stamdata-paytype-incrate").checked;
  const incTotal = document.getElementById("stamdata-paytype-inctotal").checked;
  if (!label) { toast("Type må ikke være tom", "error"); return; }
  try {
    await PATCH(`/api/stamdata/pay-types/${id}`, {
      label, danloen_code: code, include_in_csv: inCsv,
      csv_quantity_type: qtyType, csv_rate_source: rateSrc,
      csv_include_rate: incRate, csv_include_total: incTotal,
    });
    toast("Løntypekode opdateret");
    closeModal("modal-stamdata-paytype");
    await loadStamdataPayTypes();
  } catch (e) { toast(e.message, "error"); }
}

function openNewRateModal(type) {
  document.getElementById("new-rate-type").value = type;
  document.getElementById("new-rate-title").textContent =
    type === "overtime" ? "Opret ny overtidssats" : "Opret nyt tillæg";
  document.getElementById("new-rate-label").value = "";
  document.getElementById("new-rate-value").value = "";
  openModal("modal-stamdata-new-rate");
}

async function confirmNewRate() {
  const type  = document.getElementById("new-rate-type").value;
  const label = document.getElementById("new-rate-label").value.trim();
  const rate  = parseFloat(document.getElementById("new-rate-value").value);
  if (!label) { toast("Betegnelse er påkrævet", "error"); return; }
  if (isNaN(rate) || rate <= 0) { toast("Sats skal være større end 0", "error"); return; }
  const url = type === "overtime" ? "/api/stamdata/overtime-rates" : "/api/stamdata/supplements";
  try {
    await POST(url, { label, rate });
    closeModal("modal-stamdata-new-rate");
    toast("Sats oprettet");
    if (type === "overtime") await loadStamdataOvertimeRates();
    else                     await loadStamdataSupplements();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteStamdataRate(id, label, type) {
  if (!confirm(`Slet "${label}"?`)) return;
  const url = type === "overtime"
    ? `/api/stamdata/overtime-rates/${id}`
    : `/api/stamdata/supplements/${id}`;
  try {
    await DEL(url);
    toast("Slettet");
    if (type === "overtime") await loadStamdataOvertimeRates();
    else                     await loadStamdataSupplements();
  } catch (e) { toast(e.message, "error"); }
}

function openNewPayTypeModal() {
  document.getElementById("new-paytype-label").value = "";
  document.getElementById("new-paytype-code").value  = "";
  document.getElementById("new-paytype-incsv").checked = true;
  document.getElementById("new-paytype-qtytype").value = "hours";
  _buildRateSourceOptions("new-paytype-ratesrc", "hourly");
  document.getElementById("new-paytype-incrate").checked = true;
  document.getElementById("new-paytype-inctotal").checked = false;
  openModal("modal-stamdata-new-paytype");
}

async function confirmNewPayType() {
  const label    = document.getElementById("new-paytype-label").value.trim();
  const code     = document.getElementById("new-paytype-code").value.trim();
  const inCsv    = document.getElementById("new-paytype-incsv").checked;
  const qtyType  = document.getElementById("new-paytype-qtytype").value;
  const rateSrc  = document.getElementById("new-paytype-ratesrc").value;
  const incRate  = document.getElementById("new-paytype-incrate").checked;
  const incTotal = document.getElementById("new-paytype-inctotal").checked;
  if (!label) { toast("Betegnelse er påkrævet", "error"); return; }
  try {
    await POST("/api/stamdata/pay-types", {
      label, danloen_code: code, include_in_csv: inCsv,
      csv_quantity_type: qtyType, csv_rate_source: rateSrc,
      csv_include_rate: incRate, csv_include_total: incTotal,
    });
    closeModal("modal-stamdata-new-paytype");
    toast("Løntypekode oprettet");
    await loadStamdataPayTypes();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteStamdataPayType(id, label) {
  if (!confirm(`Slet "${label}"?`)) return;
  try {
    await DEL(`/api/stamdata/pay-types/${id}`);
    toast("Slettet");
    await loadStamdataPayTypes();
  } catch (e) { toast(e.message, "error"); }
}

// ── Fraværstyper (stamdata) ─────────────────────────────────────────────────

async function loadStamdataAbsenceTypes() {
  const tbody = document.getElementById("stamdata-absence-tbody");
  if (!tbody) return;
  try {
    const rows = await GET("/api/stamdata/absence-types");
    tbody.innerHTML = rows.map(r => `
      <tr style="border-bottom:1px solid var(--border);background:#fff">
        <td style="padding:10px 14px">${h(r.label)}</td>
        <td style="padding:10px 14px;font-family:monospace;font-size:12px;color:var(--text-light)">${h(r.normalized_key)}</td>
        <td style="padding:10px 14px;text-align:center">
          <span style="display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;
                       background:${r.is_active ? "var(--light-tint)" : "#f5f5f5"};
                       color:${r.is_active ? "var(--primary)" : "var(--text-light)"}">
            ${r.is_active ? "Aktiv" : "Inaktiv"}
          </span>
        </td>
        <td style="padding:10px 14px;text-align:center">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;margin-right:4px"
                  onclick="openStamdataAbsenceModal(${r.id},${jq(r.label)},${r.is_active},${r.is_user_created})">Rediger</button>
          <button class="btn btn-danger" style="font-size:12px;padding:4px 10px"
                  onclick="deleteStamdataAbsence(${r.id},${jq(r.label)})">Slet</button>
        </td>
      </tr>`).join("");
  } catch (e) { tbody.innerHTML = `<tr><td colspan="4" style="padding:24px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`; }
}

function openStamdataAbsenceModal(id, label, isActive, isUserCreated) {
  document.getElementById("stamdata-absence-id").value = id || "";
  document.getElementById("stamdata-absence-label").value = label || "";
  document.getElementById("stamdata-absence-active").checked = isActive !== false;
  const keyGroup = document.getElementById("stamdata-absence-key-group");
  if (id) {
    keyGroup.style.display = "none";
  }
  document.getElementById("stamdata-absence-title").textContent = id ? "Rediger fraværstype" : "Ny fraværstype";
  openModal("modal-stamdata-absence");
}

async function confirmStamdataAbsence() {
  const id      = document.getElementById("stamdata-absence-id").value;
  const label   = document.getElementById("stamdata-absence-label").value.trim();
  const active  = document.getElementById("stamdata-absence-active").checked;
  if (!label) { toast("Betegnelse er påkrævet", "error"); return; }
  try {
    if (id) {
      await PATCH(`/api/stamdata/absence-types/${id}`, { label, is_active: active });
      toast("Fraværstype opdateret");
    } else {
      await POST("/api/stamdata/absence-types", { label, is_active: active });
      toast("Fraværstype oprettet");
    }
    closeModal("modal-stamdata-absence");
    await loadStamdataAbsenceTypes();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteStamdataAbsence(id, label) {
  if (!confirm(`Slet fraværstypen "${label}"?`)) return;
  try {
    await DEL(`/api/stamdata/absence-types/${id}`);
    toast("Fraværstype slettet");
    await loadStamdataAbsenceTypes();
  } catch (e) { toast(e.message, "error"); }
}

// ── Stillinger (stamdata) ─────────────────────────────────────────────────

async function loadStamdataPositions() {
  const tbody = document.getElementById("stamdata-position-tbody");
  if (!tbody) return;
  try {
    const rows = await GET("/api/stamdata/positions");
    tbody.innerHTML = rows.length ? rows.map(r => `
      <tr style="border-bottom:1px solid var(--border);background:#fff">
        <td style="padding:10px 14px">${h(r.name)}</td>
        <td style="padding:10px 14px;text-align:center">${r.employee_count}</td>
        <td style="padding:10px 14px;text-align:center">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;margin-right:4px"
                  onclick="openStamdataPositionModal(${r.id},${jq(r.name)})">Rediger</button>
          <button class="btn btn-danger" style="font-size:12px;padding:4px 10px"
                  onclick="deleteStamdataPosition(${r.id},${jq(r.name)})">Slet</button>
        </td>
      </tr>`).join("")
      : `<tr><td colspan="3" style="padding:24px;text-align:center;color:var(--text-light)">Ingen stillinger endnu</td></tr>`;
  } catch (e) { tbody.innerHTML = `<tr><td colspan="3" style="padding:24px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`; }
}

function openStamdataPositionModal(id, name) {
  document.getElementById("stamdata-position-id").value = id || "";
  document.getElementById("stamdata-position-name").value = name || "";
  document.getElementById("stamdata-position-title").textContent = id ? "Rediger stilling" : "Ny stilling";
  openModal("modal-stamdata-position");
}

async function confirmStamdataPosition() {
  const id = document.getElementById("stamdata-position-id").value;
  const name = document.getElementById("stamdata-position-name").value.trim();
  if (!name) { toast("Navn er påkrævet", "error"); return; }
  try {
    if (id) {
      await PATCH(`/api/stamdata/positions/${id}`, { name });
      toast("Stilling opdateret");
    } else {
      await POST("/api/stamdata/positions", { name });
      toast("Stilling oprettet");
    }
    closeModal("modal-stamdata-position");
    await loadStamdataPositions();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteStamdataPosition(id, name) {
  if (!confirm(`Slet stillingen "${name}"?`)) return;
  try {
    await DEL(`/api/stamdata/positions/${id}`);
    toast("Stilling slettet");
    await loadStamdataPositions();
  } catch (e) { toast(e.message, "error"); }
}

// ── Aftaletyper (stamdata) ────────────────────────────────────────────────

async function loadStamdataAgreementKinds() {
  const tbody = document.getElementById("stamdata-agreementkind-tbody");
  if (!tbody) return;
  try {
    const rows = await GET("/api/stamdata/agreement-kinds");
    const badge = (v, yes, no) => v
      ? `<span style="color:var(--primary);font-weight:600">${yes}</span>`
      : `<span style="color:var(--text-light)">${no}</span>`;
    tbody.innerHTML = rows.map(r => `
      <tr style="border-bottom:1px solid var(--border);background:#fff">
        <td style="padding:10px 14px">${h(r.label)}</td>
        <td style="padding:10px 14px;text-align:center">
          <span style="display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;
                       background:${r.is_user_created ? "var(--light-tint)" : "#f5f5f5"};
                       color:${r.is_user_created ? "var(--primary)" : "var(--text-light)"}">
            ${r.is_user_created ? "Brugeroprettet" : "System"}
          </span>
        </td>
        <td style="padding:10px 14px;text-align:center">${badge(r.requires_agreement_type, "Ja", "Nej")}</td>
        <td style="padding:10px 14px;text-align:center">${badge(r.is_active, "Aktiv", "Inaktiv")}</td>
        <td style="padding:10px 14px;text-align:center">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;margin-right:4px"
                  onclick="openStamdataAgreementKindModal(${r.id},${jq(r.label)},${r.is_active},${r.requires_agreement_type},${r.is_user_created})">Rediger</button>
          ${r.is_user_created
            ? `<button class="btn btn-danger" style="font-size:12px;padding:4px 10px"
                       onclick="deleteStamdataAgreementKind(${r.id},${jq(r.label)})">Slet</button>`
            : ""}
        </td>
      </tr>`).join("");
  } catch (e) { tbody.innerHTML = `<tr><td colspan="5" style="padding:24px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`; }
  // Ny/ændret aftaletype skal med det samme kunne vælges i medarbejder-modalen
  try {
    state.agreementKinds = await GET("/api/employees/agreement-kinds");
  } catch (_) {}
}

function openStamdataAgreementKindModal(id, label, isActive, requiresAgreementType, isUserCreated) {
  document.getElementById("stamdata-agreementkind-id").value = id || "";
  document.getElementById("stamdata-agreementkind-label").value = label || "";
  document.getElementById("stamdata-agreementkind-active").checked = isActive !== false;
  document.getElementById("stamdata-agreementkind-requires").checked = requiresAgreementType !== false;
  document.getElementById("stamdata-agreementkind-title").textContent = id ? "Rediger aftaletype" : "Ny aftaletype";
  openModal("modal-stamdata-agreementkind");
}

async function confirmStamdataAgreementKind() {
  const id       = document.getElementById("stamdata-agreementkind-id").value;
  const label    = document.getElementById("stamdata-agreementkind-label").value.trim();
  const active   = document.getElementById("stamdata-agreementkind-active").checked;
  const requires = document.getElementById("stamdata-agreementkind-requires").checked;
  if (!label) { toast("Betegnelse er påkrævet", "error"); return; }
  try {
    if (id) {
      await PATCH(`/api/stamdata/agreement-kinds/${id}`, { label, is_active: active, requires_agreement_type: requires });
      toast("Aftaletype opdateret");
    } else {
      await POST("/api/stamdata/agreement-kinds", { label, requires_agreement_type: requires });
      toast("Aftaletype oprettet");
    }
    closeModal("modal-stamdata-agreementkind");
    await loadStamdataAgreementKinds();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteStamdataAgreementKind(id, label) {
  if (!confirm(`Slet aftaletypen "${label}"?`)) return;
  try {
    await DEL(`/api/stamdata/agreement-kinds/${id}`);
    toast("Aftaletype slettet");
    await loadStamdataAgreementKinds();
  } catch (e) { toast(e.message, "error"); }
}

// ── Disponentgrupper (stamdata) ──────────────────────────────────────────────

async function loadStamdataDispatcherGroups() {
  const tbody = document.getElementById("stamdata-dispatcher-tbody");
  if (!tbody) return;
  try {
    const rows = await GET("/api/stamdata/dispatcher-groups");
    rows.sort((a, b) => naturalCompare(a.name, b.name));
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-light)">Ingen disponentgrupper oprettet endnu</td></tr>`;
      return;
    }
    const badge = (v, yes, no) => v
      ? `<span style="color:var(--primary);font-weight:600">${yes}</span>`
      : `<span style="color:var(--text-light)">${no}</span>`;
    tbody.innerHTML = rows.map(r => `
      <tr style="border-bottom:1px solid var(--border);background:#fff">
        <td style="padding:10px 14px">${h(r.name)}</td>
        <td style="padding:10px 14px;color:var(--text-light)">${h(r.description || "")}</td>
        <td style="padding:10px 14px;text-align:center">${r.employee_count}</td>
        <td style="padding:10px 14px;text-align:center">${h(r.vehicle_number || "–")}</td>
        <td style="padding:10px 14px;text-align:center">${badge(r.visible_in_activity_overview, "Ja", "Nej")}</td>
        <td style="padding:10px 14px;text-align:center">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;margin-right:4px"
                  onclick="openStamdataDispatcherModal(${r.id},${jq(r.name)},${jq(r.description || "")},${r.visible_in_activity_overview},${r.vehicle_id || "null"},${jq(r.vehicle_number || "")})">Rediger</button>
          <button class="btn btn-danger" style="font-size:12px;padding:4px 10px"
                  onclick="deleteStamdataDispatcher(${r.id},${jq(r.name)},${r.employee_count})">Slet</button>
        </td>
      </tr>`).join("");
  } catch (e) { tbody.innerHTML = `<tr><td colspan="6" style="padding:24px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`; }
  // Ny/ændret gruppe kan påvirke medarbejder-modal og filtre
  try {
    state.dispatcherGroups = await GET("/api/employees/dispatcher-groups");
    fillDispatcherGroupFilter();
    fillEmployeeDispatcherGroupFilter();
    fillEmployeeFilter();
  } catch (_) {}
  // Medarbejdernes indlejrede dispatcher_group (inkl. vognnummer) skal genindlæses,
  // ellers forbliver fx vognnummer-autoudfyldningen ved fravær forældet indtil en sideopdatering.
  try {
    state.employees = await GET("/api/employees");
  } catch (_) {}
}

function _renderVehicleSearchResults(query) {
  const dropdown = document.getElementById("stamdata-dispatcher-vehicle-dropdown");
  const q = query.trim().toUpperCase();
  const matches = !q ? state.vehicles : state.vehicles.filter(v =>
    v.vehicle_number.toUpperCase().includes(q) || v.registration_number.toUpperCase().includes(q)
  );
  const noneRow = `<div class="vehicle-search-item" data-id="" data-num=""
       style="padding:8px 10px;cursor:pointer;font-size:13px;color:var(--text-light)">— Intet køretøj —</div>`;
  const rows = matches.length
    ? matches.map(v => `
        <div class="vehicle-search-item" data-id="${v.id}" data-num="${h(v.vehicle_number)}"
             style="padding:8px 10px;cursor:pointer;font-size:13px">
          ${h(v.vehicle_number)} <span style="color:var(--text-light)">– ${h(v.registration_number)}</span>
        </div>`).join("")
    : `<div style="padding:8px 10px;color:var(--text-light);font-size:13px">Ingen køretøjer fundet</div>`;
  dropdown.innerHTML = noneRow + rows;
  dropdown.querySelectorAll(".vehicle-search-item[data-id]").forEach(el => {
    el.addEventListener("mouseover", () => el.style.background = "var(--bg)");
    el.addEventListener("mouseout",  () => el.style.background = "");
    el.addEventListener("click", () => _selectVehicleForDispatcherGroup(el.dataset.id, el.dataset.num));
  });
  dropdown.style.display = "block";
}

function _selectVehicleForDispatcherGroup(id, vehicleNumber) {
  document.getElementById("stamdata-dispatcher-vehicle-search").value = vehicleNumber || "";
  document.getElementById("stamdata-dispatcher-vehicle-id").value = id || "";
  document.getElementById("stamdata-dispatcher-vehicle-dropdown").style.display = "none";
}

document.addEventListener("click", (e) => {
  if (!e.target.closest("#stamdata-dispatcher-vehicle-search, #stamdata-dispatcher-vehicle-dropdown")) {
    const dropdown = document.getElementById("stamdata-dispatcher-vehicle-dropdown");
    if (dropdown) dropdown.style.display = "none";
  }
});

function openStamdataDispatcherModal(id, name, description, visible, vehicleId, vehicleNumber) {
  document.getElementById("stamdata-dispatcher-id").value = id || "";
  document.getElementById("stamdata-dispatcher-name").value = name || "";
  document.getElementById("stamdata-dispatcher-description").value = description || "";
  document.getElementById("stamdata-dispatcher-visible").checked = id ? !!visible : true;
  document.getElementById("stamdata-dispatcher-vehicle-search").value = vehicleNumber || "";
  document.getElementById("stamdata-dispatcher-vehicle-id").value = vehicleId || "";
  document.getElementById("stamdata-dispatcher-vehicle-dropdown").style.display = "none";
  document.getElementById("stamdata-dispatcher-title").textContent = id ? "Rediger disponentgruppe" : "Ny disponentgruppe";
  openModal("modal-stamdata-dispatcher");
}

document.getElementById("stamdata-dispatcher-vehicle-search")?.addEventListener("input", function () {
  _renderVehicleSearchResults(this.value);
});
document.getElementById("stamdata-dispatcher-vehicle-search")?.addEventListener("focus", function () {
  _renderVehicleSearchResults(this.value);
});

async function confirmStamdataDispatcher() {
  const id   = document.getElementById("stamdata-dispatcher-id").value;
  const name = document.getElementById("stamdata-dispatcher-name").value.trim();
  const description = document.getElementById("stamdata-dispatcher-description").value.trim();
  const visible = document.getElementById("stamdata-dispatcher-visible").checked;
  const vehicleIdRaw = document.getElementById("stamdata-dispatcher-vehicle-id").value;
  const vehicle_id = vehicleIdRaw ? parseInt(vehicleIdRaw) : null;
  if (!name) { toast("Navn er påkrævet", "error"); return; }
  try {
    if (id) {
      await PATCH(`/api/stamdata/dispatcher-groups/${id}`, { name, description, visible_in_activity_overview: visible, vehicle_id });
      toast("Disponentgruppe opdateret");
    } else {
      await POST("/api/stamdata/dispatcher-groups", { name, description, visible_in_activity_overview: visible, vehicle_id });
      toast("Disponentgruppe oprettet");
    }
    closeModal("modal-stamdata-dispatcher");
    await loadStamdataDispatcherGroups();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteStamdataDispatcher(id, name, employeeCount) {
  const warn = employeeCount ? `\n${employeeCount} medarbejder(e) er tilknyttet og vil miste denne gruppe.` : "";
  if (!confirm(`Slet disponentgruppen "${name}"?${warn}`)) return;
  try {
    await DEL(`/api/stamdata/dispatcher-groups/${id}`);
    toast("Disponentgruppe slettet");
    await loadStamdataDispatcherGroups();
    await loadEmployees();
  } catch (e) { toast(e.message, "error"); }
}

// ── CVR-numre (stamdata) ─────────────────────────────────────────────────────

async function loadStamdataCvrNumbers() {
  const tbody = document.getElementById("stamdata-cvr-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="4" style="padding:20px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    const rows = await GET("/api/stamdata/cvr-numbers");
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="4" style="padding:20px;text-align:center;color:var(--text-light)">Ingen CVR-numre oprettet endnu</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map((r, i) => `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
        <td style="padding:10px 14px;font-family:monospace">${h(r.cvr_number)}</td>
        <td style="padding:10px 14px">${h(r.company_name)}</td>
        <td style="padding:10px 14px;text-align:center">
          ${r.is_default
            ? `<span style="background:var(--primary);color:#fff;padding:2px 10px;border-radius:12px;font-size:12px">Standard</span>`
            : `<button class="btn btn-secondary" style="font-size:12px;padding:4px 10px"
                       onclick="setDefaultCvr(${r.id})">Sæt som standard</button>`}
        </td>
        <td style="padding:10px 14px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px"
                  onclick="openEditCvrModal(${r.id}, ${jq(r.cvr_number)}, ${jq(r.company_name)})">Rediger</button>
          ${!r.is_default
            ? `<button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;color:var(--danger);border-color:var(--danger);margin-left:4px"
                       onclick="deleteStamdataCvr(${r.id}, ${jq(r.cvr_number)})">Slet</button>`
            : ""}
        </td>
      </tr>
    `).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="4" style="padding:20px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

function openNewCvrModal() {
  document.getElementById("stamdata-cvr-id").value      = "";
  document.getElementById("stamdata-cvr-number").value  = "";
  document.getElementById("stamdata-cvr-company").value = "";
  document.getElementById("stamdata-cvr-title").textContent = "Opret CVR nummer";
  openModal("modal-stamdata-cvr");
}

function openEditCvrModal(id, cvrNumber, companyName) {
  document.getElementById("stamdata-cvr-id").value      = id;
  document.getElementById("stamdata-cvr-number").value  = cvrNumber;
  document.getElementById("stamdata-cvr-company").value = companyName;
  document.getElementById("stamdata-cvr-title").textContent = "Rediger CVR nummer";
  openModal("modal-stamdata-cvr");
}

async function confirmStamdataCvr() {
  const id      = document.getElementById("stamdata-cvr-id").value;
  const cvr     = document.getElementById("stamdata-cvr-number").value.trim();
  const company = document.getElementById("stamdata-cvr-company").value.trim();
  if (!cvr) { toast("CVR-nummer er påkrævet", "error"); return; }
  try {
    if (id) {
      await PATCH(`/api/stamdata/cvr-numbers/${id}`, { cvr_number: cvr, company_name: company });
      toast("CVR nummer opdateret");
    } else {
      await POST("/api/stamdata/cvr-numbers", { cvr_number: cvr, company_name: company });
      toast("CVR nummer oprettet");
    }
    closeModal("modal-stamdata-cvr");
    await loadStamdataCvrNumbers();
  } catch (e) { toast(e.message, "error"); }
}

async function setDefaultCvr(id) {
  try {
    await POST(`/api/stamdata/cvr-numbers/${id}/set-default`, {});
    toast("Standard CVR opdateret");
    await loadStamdataCvrNumbers();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteStamdataCvr(id, label) {
  if (!confirm(`Slet CVR-nummeret "${label}"?`)) return;
  try {
    await DEL(`/api/stamdata/cvr-numbers/${id}`);
    toast("CVR nummer slettet");
    await loadStamdataCvrNumbers();
  } catch (e) { toast(e.message, "error"); }
}

// ── Helligdage (stamdata) ────────────────────────────────────────────────────

async function loadStamdataHolidays() {
  const tbody = document.getElementById("stamdata-holiday-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    const rows = await GET("/api/stamdata/holidays");
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-light)">Ingen helligdage oprettet endnu</td></tr>`;
      return;
    }
    const fmtDate = iso => { const [y,m,d] = iso.split("-"); return `${d}-${m}-${y}`; };
    tbody.innerHTML = rows.map((r, i) => `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
        <td style="padding:10px 14px;font-variant-numeric:tabular-nums">${fmtDate(r.date)}</td>
        <td style="padding:10px 14px">${h(r.name)}</td>
        <td style="padding:10px 14px;text-align:center">${r.half_day_from ? h(r.half_day_from) : "—"}</td>
        <td style="padding:10px 14px;text-align:center">
          <span style="font-size:12px;padding:2px 8px;border-radius:12px;background:${r.is_auto_generated ? "var(--bg)" : "#d4edcc"};color:var(--text-light)">
            ${r.is_auto_generated ? "Auto" : "Manuel"}
          </span>
        </td>
        <td style="padding:10px 14px;text-align:center">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;color:var(--danger);border-color:var(--danger)"
                  onclick="deleteHoliday(${r.id}, ${jq(r.date)})">Slet</button>
        </td>
      </tr>
    `).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

function openNewHolidayModal() {
  buildDatePicker("holiday-date-picker", "");
  document.getElementById("holiday-name").value = "";
  document.getElementById("holiday-halfday-check").checked = false;
  document.getElementById("holiday-halfday-group").style.display = "none";
  document.getElementById("holiday-halfday-from").value = "12:00";
  openModal("modal-stamdata-holiday");
}

async function confirmNewHoliday() {
  const dateVal  = readDatePicker("holiday-date-picker");
  const name     = document.getElementById("holiday-name").value.trim();
  const isHalf   = document.getElementById("holiday-halfday-check").checked;
  const halfFrom = isHalf ? document.getElementById("holiday-halfday-from").value.trim() : null;
  if (!dateVal || !name) { toast("Udfyld dato og navn", "error"); return; }
  try {
    await POST("/api/stamdata/holidays", { date: dateVal, name, half_day_from: halfFrom });
    toast("Helligdag oprettet");
    closeModal("modal-stamdata-holiday");
    await loadStamdataHolidays();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteHoliday(id, label) {
  if (!confirm(`Slet helligdagen "${label}"?`)) return;
  try {
    await DEL(`/api/stamdata/holidays/${id}`);
    toast("Helligdag slettet");
    await loadStamdataHolidays();
  } catch (e) { toast(e.message, "error"); }
}

async function generateHolidaysForYear() {
  const year = parseInt(document.getElementById("holiday-gen-year").value);
  if (!year || year < 2020 || year > 2100) { toast("Angiv et gyldigt årstal (2020–2100)", "error"); return; }
  try {
    const res = await POST(`/api/stamdata/holidays/generate/${year}`, {});
    toast(`${res.added} helligdage tilføjet for ${year}`);
    await loadStamdataHolidays();
  } catch (e) { toast(e.message, "error"); }
}

// ── Hændelseslog ────────────────────────────────────────────────────────────
const ACTION_LABELS = {
  login:           { label: "Login",                    color: "#317423", bg: "#d4edcc" },
  approve:         { label: "Aktivitet godkendt",       color: "#1565c0", bg: "#dbeafe" },
  deactivate:      { label: "Aktivitet deaktiveret",    color: "#b71c1c", bg: "#fee2e2" },
  reopen_activity: { label: "Aktivitet genåbnet",       color: "#7b1fa2", bg: "#f3e8ff" },
  split:           { label: "Aktivitet splittet",       color: "#e65100", bg: "#fff3e0" },
  create_activity: { label: "Aktivitet oprettet",       color: "#00695c", bg: "#e0f2f1" },
  update_activity: { label: "Aktivitet ændret",         color: "#424242", bg: "#f5f5f5" },
  payroll_run:     { label: "Løn kørt",                 color: "#317423", bg: "#d4edcc" },
  reopen_period:   { label: "Lønperiode genåbnet",      color: "#e65100", bg: "#fff3e0" },
  create_user:     { label: "Bruger oprettet",          color: "#1565c0", bg: "#dbeafe" },
  update_user:     { label: "Bruger opdateret",         color: "#424242", bg: "#f5f5f5" },
  role_change:     { label: "Rolle ændret",             color: "#7b1fa2", bg: "#f3e8ff" },
  delete_user:     { label: "Bruger slettet",           color: "#b71c1c", bg: "#fee2e2" },
  create_role:     { label: "Rolle oprettet",           color: "#1565c0", bg: "#dbeafe" },
  update_role:     { label: "Rolle opdateret",          color: "#424242", bg: "#f5f5f5" },
  delete_role:     { label: "Rolle slettet",            color: "#b71c1c", bg: "#fee2e2" },
  stamdata_create: { label: "Stamdata oprettet",        color: "#00695c", bg: "#e0f2f1" },
  stamdata_update: { label: "Stamdata opdateret",       color: "#424242", bg: "#f5f5f5" },
  stamdata_delete: { label: "Stamdata slettet",         color: "#b71c1c", bg: "#fee2e2" },
  ddd_import:      { label: "DDD-import",               color: "#317423", bg: "#d4edcc" },
  employee_supplement_create: { label: "Tillæg oprettet", color: "#00695c", bg: "#e0f2f1" },
  employee_supplement_end:    { label: "Tillæg afsluttet", color: "#b71c1c", bg: "#fee2e2" },
};

let _auditLogEntries = [];

async function loadAuditLogView() {
  const tbody = document.getElementById("audit-log-view-body");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="4" style="padding:30px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    _auditLogEntries = await GET("/api/users/audit-log?limit=500");
    _renderAuditLog(_auditLogEntries);
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="4" style="padding:30px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

function filterAuditLog() {
  const q = (document.getElementById("log-filter-input")?.value || "").toLowerCase();
  const filtered = q ? _auditLogEntries.filter(e =>
    (e.user_initials || "").toLowerCase().includes(q) ||
    (ACTION_LABELS[e.action]?.label || e.action || "").toLowerCase().includes(q) ||
    (e.details || "").toLowerCase().includes(q)
  ) : _auditLogEntries;
  _renderAuditLog(filtered);
}

function _renderAuditLog(entries) {
  const tbody = document.getElementById("audit-log-view-body");
  if (!tbody) return;
  if (!entries.length) {
    tbody.innerHTML = `<tr><td colspan="4" style="padding:30px;text-align:center;color:var(--text-light)">Ingen hændelser fundet</td></tr>`;
    return;
  }
  tbody.innerHTML = entries.map((e, i) => {
    const ts   = e.timestamp ? new Date(e.timestamp).toLocaleString("da-DK") : "—";
    const meta = ACTION_LABELS[e.action] || { label: e.action, color: "#555", bg: "#eee" };
    return `<tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
      <td style="padding:10px 12px;white-space:nowrap;color:var(--text-light);font-size:12px">${ts}</td>
      <td style="padding:10px 12px;font-weight:700;font-family:monospace">${h(e.user_initials || "—")}</td>
      <td style="padding:10px 12px">
        <span style="display:inline-block;padding:3px 10px;border-radius:10px;font-size:12px;font-weight:600;
                     color:${meta.color};background:${meta.bg}">${h(meta.label)}</span>
      </td>
      <td style="padding:10px 12px;color:var(--text-light);font-size:13px">${h(e.details || "—")}</td>
    </tr>`;
  }).join("");
}

async function confirmReopenPeriod() {
  setLoading(true);
  try {
    await POST(`/api/payroll/reopen-period?period_start=${state.currentPeriodStart || ""}`, {});
    toast("Lønperioden er åbnet igen.", "success");
    closeModal("modal-admin");
    await loadPeriodInfo(state.currentPeriodStart);
    await loadActivities();
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

// ── PDF timesedler ─────────────────────────────────────────────────────────
async function openPdfModal() {
  const p = state.periodInfo?.period;
  if (p) {
    document.getElementById("pdf-from").value = p.start_date;
    document.getElementById("pdf-to").value = p.end_date;
  }
  const sel = document.getElementById("pdf-employee");
  sel.innerHTML = `<option value="">Alle medarbejdere</option>` +
    state.employees.filter(e => e.active)
      .slice().sort((a, b) => a.name.localeCompare(b.name, "da"))
      .map(e => `<option value="${e.id}">${h(e.name)} (${h(e.employee_number)})</option>`).join("");
  document.getElementById("pdf-result").textContent = "";
  openModal("modal-pdf");
}

async function generatePdfs() {
  const from = document.getElementById("pdf-from").value;
  const to = document.getElementById("pdf-to").value;
  if (!from || !to) { toast("Angiv fra- og til-dato", "error"); return; }
  const empId = document.getElementById("pdf-employee").value;
  setLoading(true);
  try {
    const result = await downloadFile("/api/payroll/pdf-timesedler", {
      from_date: from, to_date: to,
      employee_id: empId ? parseInt(empId) : null,
    }, "timesedler.zip");
    const createdCount = result.headers.get("X-Created-Count") || "0";
    const skippedCount = parseInt(result.headers.get("X-Skipped-Count") || "0", 10);
    const msg = `${createdCount} PDF'er downloadet` +
      (skippedCount ? ` (${skippedCount} sprunget over uden aktiviteter)` : "");
    toast(msg, "success");
    closeModal("modal-pdf");
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

async function sendAllTimesedler() {
  const from = document.getElementById("pdf-from").value;
  const to   = document.getElementById("pdf-to").value;
  const empId = document.getElementById("pdf-employee").value;
  if (!from || !to) { toast("Angiv fra- og til-dato", "error"); return; }

  const empName = empId
    ? (state.employees.find(e => e.id === parseInt(empId))?.name || "den valgte medarbejder")
    : "alle medarbejdere";
  if (!confirm(`Send timesedler til ${empName} for perioden ${from} – ${to}?`)) return;

  setLoading(true);
  try {
    const result = await POST("/api/timeseddel/send-all", {
      from_date: from,
      to_date: to,
      employee_id: empId ? parseInt(empId) : null,
    });
    let msg = `${result.sent.length} timeseddel${result.sent.length !== 1 ? "er" : ""} sendt`;
    if (result.skipped_no_email.length)       msg += `, ${result.skipped_no_email.length} uden e-mail`;
    if (result.skipped_no_activities.length)  msg += `, ${result.skipped_no_activities.length} uden godkendte aktiviteter`;
    if (result.skipped_funktionaer?.length)   msg += `, ${result.skipped_funktionaer.length} funktionær${result.skipped_funktionaer.length !== 1 ? "er" : ""} sprunget over`;
    if (result.failed.length)                 msg += `, ${result.failed.length} fejlede`;
    toast(msg, result.failed.length ? "error" : "success");
    if (!result.failed.length) closeModal("modal-pdf");
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

// ── Helpers ────────────────────────────────────────────────────────────────
function formatDate(iso) {
  return iso ? new Date(iso).toLocaleDateString("da-DK", { day: "2-digit", month: "2-digit", year: "numeric" }) : "–";
}
function formatDateShort(iso) {
  if (!iso) return "–";
  const d = new Date(iso + (iso.length <= 10 ? "T00:00:00" : ""));
  return d.toLocaleDateString("da-DK", { day: "numeric", month: "short", year: "numeric" });
}
function formatTime(iso) {
  return iso ? new Date(iso).toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" }) : "–";
}
function formatDateTime(iso) {
  if (!iso) return "–";
  const d = new Date(iso);
  return d.toLocaleDateString("da-DK", { day: "2-digit", month: "2-digit" }) + " " +
         d.toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" });
}
function formatDuration(minutes) {
  return `${Math.floor(minutes / 60)}t ${(minutes % 60).toString().padStart(2, "0")}m`;
}
function fmtHours(h) { return `${h.toFixed(2)} t`; }
function fmtHoursHM(h) {
  const totalMinutes = Math.round(h * 60);
  const hh = Math.floor(totalMinutes / 60);
  const mm = totalMinutes % 60;
  return `${hh}t ${mm.toString().padStart(2, "0")}m`;
}
function fmtKr(v) {
  return v.toLocaleString("da-DK", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " kr";
}
function statusLabel(s) {
  return { pending: "Afventer", approved: "Godkendt", deactivated: "Deaktiveret" }[s] || s;
}

function _empInGroup(emp, groupId) {
  return String(emp.dispatcher_group?.id) === String(groupId);
}

function _empHasVisibleGroup(emp) {
  return !!emp.dispatcher_group?.visible_in_activity_overview;
}

function fillDispatcherGroupFilter() {
  const sel = document.getElementById("filter-dispatcher-group");
  if (!sel) return;
  const cur = sel.value;
  const visibleGroups = state.dispatcherGroups.filter(g => g.visible_in_activity_overview);
  sel.innerHTML = `<option value="">Alle afdelinger</option>` +
    visibleGroups.map(g => `<option value="${g.id}">${h(g.name)}</option>`).join("");
  if (visibleGroups.find(g => String(g.id) === cur)) sel.value = cur;
}

function fillEmployeeDispatcherGroupFilter() {
  const sel = document.getElementById("employee-filter-dispatcher-group");
  if (!sel) return;
  const cur = sel.value;
  const sorted = state.dispatcherGroups.slice().sort((a, b) => naturalCompare(a.name, b.name));
  sel.innerHTML = `<option value="">Alle afdelinger</option>` +
    `<option value="none">Ingen gruppe</option>` +
    sorted.map(g => `<option value="${g.id}">${h(g.name)}</option>`).join("");
  if ([...sel.options].some(o => o.value === cur)) sel.value = cur;
}

function fillEmployeeFilter() {
  const sel = document.getElementById("filter-employee");
  const cur = sel.value;
  const groupFilter = document.getElementById("filter-dispatcher-group")?.value || "";
  let visible = state.employees.filter(e => _empHasVisibleGroup(e));
  if (groupFilter) visible = visible.filter(e => _empInGroup(e, groupFilter));
  const placeholder = groupFilter ? "Alle i afdelingen" : "Alle medarbejdere";
  sel.innerHTML = `<option value="">${placeholder}</option>` +
    visible.slice().sort((a, b) => a.name.localeCompare(b.name, "da"))
      .map(e => `<option value="${e.id}">${h(e.name)} (${h(e.employee_number)})</option>`).join("");
  if (visible.find(e => String(e.id) === cur)) sel.value = cur;
}

function fillVagtplanGroupFilter() {
  const container = document.getElementById("vagtplan-group-filter");
  if (!container) return;
  if (state.vagtplan.groupFilterIds === null) {
    state.vagtplan.groupFilterIds = state.dispatcherGroups.map(g => g.id); // default: alle valgt
  }
  const allSelected = state.vagtplan.groupFilterIds.length === state.dispatcherGroups.length;
  const selectedCount = state.vagtplan.groupFilterIds.length;
  const label = allSelected ? "Alle afdelinger" : `${selectedCount} afdeling${selectedCount === 1 ? "" : "er"}`;
  container.innerHTML = `
    <button type="button" class="btn btn-secondary" id="vagtplan-group-filter-btn" style="width:180px;text-align:left">${h(label)} ▾</button>
    <div id="vagtplan-group-filter-panel" style="display:none;position:absolute;top:100%;left:0;z-index:50;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:10px;margin-top:4px;min-width:220px;box-shadow:0 4px 12px rgba(0,0,0,.12)">
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:14px;font-weight:600;padding:3px 0 8px;margin-bottom:6px;border-bottom:1px solid var(--border)">
        <input type="checkbox" class="vagtplan-group-all-checkbox" ${allSelected ? "checked" : ""}
               style="width:15px;height:15px;accent-color:var(--primary);cursor:pointer">
        Alle afdelinger
      </label>
      ${state.dispatcherGroups.map(g => `
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:14px;padding:3px 0">
          <input type="checkbox" class="vagtplan-group-checkbox" value="${g.id}"
                 ${state.vagtplan.groupFilterIds.includes(g.id) ? "checked" : ""}
                 style="width:15px;height:15px;accent-color:var(--primary);cursor:pointer">
          ${h(g.name)}
        </label>`).join("")}
    </div>`;

  const btn = document.getElementById("vagtplan-group-filter-btn");
  const panel = document.getElementById("vagtplan-group-filter-panel");
  btn.addEventListener("click", e => {
    e.stopPropagation();
    panel.style.display = panel.style.display === "none" ? "block" : "none";
  });

  function _applyGroupFilterChange(newIds) {
    state.vagtplan.groupFilterIds = newIds;
    fillVagtplanGroupFilter(); // opdater knap-label + afkrydsninger
    document.getElementById("vagtplan-group-filter-panel").style.display = "block"; // hold åben under multi-valg
    fillVagtplanEmployeeFilter();
    renderVagtplanTable();
  }

  container.querySelector(".vagtplan-group-all-checkbox").addEventListener("change", () => {
    _applyGroupFilterChange(state.dispatcherGroups.map(g => g.id));
  });
  container.querySelectorAll(".vagtplan-group-checkbox").forEach(cb => {
    cb.addEventListener("change", () => {
      // Første klik på en enkelt afdeling, mens "alle" er valgt, isolerer til kun denne –
      // efterfølgende klik lægger til/fjerner normalt.
      if (allSelected) {
        _applyGroupFilterChange([parseInt(cb.value)]);
      } else {
        _applyGroupFilterChange(
          [...container.querySelectorAll(".vagtplan-group-checkbox:checked")].map(x => parseInt(x.value))
        );
      }
    });
  });
}

// Luk disponentgruppe-panelet ved klik udenfor – bindes én gang (ikke i
// fillVagtplanGroupFilter, som kan kaldes mange gange og ellers ville hobe
// dublet-listeners op på document).
document.addEventListener("click", e => {
  if (!e.target.closest("#vagtplan-group-filter")) {
    const panel = document.getElementById("vagtplan-group-filter-panel");
    if (panel) panel.style.display = "none";
  }
});

function fillVagtplanEmployeeFilter() {
  const sel = document.getElementById("vagtplan-filter-employee");
  if (!sel) return;
  const cur = sel.value;
  const groupIds = state.vagtplan.groupFilterIds;
  let visible = state.employees.filter(e => e.active);
  if (groupIds) visible = visible.filter(e => e.dispatcher_group && groupIds.includes(e.dispatcher_group.id));
  sel.innerHTML = `<option value="">Alle medarbejdere</option>` +
    visible.slice().sort((a, b) => a.name.localeCompare(b.name, "da"))
      .map(e => `<option value="${e.id}">${h(e.name)} (${h(e.employee_number)})</option>`).join("");
  if (visible.find(e => String(e.id) === cur)) sel.value = cur;
}

// ── Startup ────────────────────────────────────────────────────────────────
async function loadApp() {
  try {
    [state.employees, state.vehicles, state.dispatcherGroups] = await Promise.all([
      GET("/api/employees"),
      GET("/api/vehicles"),
      GET("/api/employees/dispatcher-groups"),
    ]);
    fillDispatcherGroupFilter();
    fillEmployeeDispatcherGroupFilter();
    fillEmployeeFilter();
  } catch (e) { console.error(e); }

  try {
    const settings = await GET("/api/auto-approval/settings");
    state.autoApprovalEnabled = settings.enabled;
  } catch (e) { console.error(e); }
  applyAutoApprovalVisibility();

  await loadAbsenceTypes();
  // Lønperioden hentes før første fane, så alle faner (ikke kun Aktiviteter) kender den
  try { if (!state.periodInfo) await loadPeriodInfo(); } catch (e) { console.error(e); }
  await setView(_startView());
  // Alle advarsler i én oversigt (static/js/alerts_overview.js) i stedet for en popup pr. type
  await checkAllAlerts();
}

// Første menupunkt brugeren har adgang til – Aktiviteter hvis 'Se aktivitetskalender',
// ellers det første synlige punkt (rettighederne håndhæves også i backend).
function _firstPermittedView() {
  if (_hasPerm("view_calendar")) return "activities";
  for (const el of document.querySelectorAll(".sidebar-item[data-view]")) {
    const section = el.closest(".sidebar-section[data-perm-require]");
    if (section && !_hasPerm(section.dataset.permRequire)) continue;
    if (el.dataset.permRequire && !_hasPerm(el.dataset.permRequire)) continue;
    if (el.dataset.view !== "activities") return el.dataset.view;
  }
  return "activities";
}

// Fanen fra adressen (#fane) hvis brugeren har adgang til den, ellers første tilladte
function _startView() {
  const wanted = decodeURIComponent(location.hash.slice(1));
  for (const el of document.querySelectorAll(".sidebar-item[data-view]")) {
    if (el.dataset.view !== wanted) continue;
    const section = el.closest(".sidebar-section[data-perm-require]");
    if (section && !_hasPerm(section.dataset.permRequire)) break;
    if (el.dataset.permRequire && !_hasPerm(el.dataset.permRequire)) break;
    if (wanted === "activities" && !_hasPerm("view_calendar")) break;
    return wanted;
  }
  return _firstPermittedView();
}

function applyAutoApprovalVisibility() {
  const btn = document.getElementById("btn-auto-approve");
  if (btn) btn.style.display = state.autoApprovalEnabled && _hasPerm("approve_activities") ? "" : "none";
}

async function init() {
  document.querySelectorAll(".sidebar-item").forEach(el =>
    el.addEventListener("click", () => setView(el.dataset.view)));

  document.getElementById("btn-prev-period").addEventListener("click", () => navigatePeriod("prev"));
  document.getElementById("btn-next-period").addEventListener("click", () => navigatePeriod("next"));
  document.getElementById("btn-prev-vagtplan").addEventListener("click", () => navigateVagtplan("prev"));
  document.getElementById("btn-next-vagtplan").addEventListener("click", () => navigateVagtplan("next"));
  document.getElementById("btn-vagtplan-today").addEventListener("click", () => jumpToVagtplanToday());
  _initVagtplanCalendar();
  document.getElementById("vagtplan-filter-employee").addEventListener("change", () => renderVagtplanTable());
  document.getElementById("vagtplan-search").addEventListener("input", () => renderVagtplanTable());
  buildDatePicker("period-date-picker", "");
  document.getElementById("period-date-picker").style.width = "150px";
  document.getElementById("period-date-picker").querySelector(".dp-val").addEventListener("change", e => jumpToDate(e.target.value));
  buildDatePicker("absence-from-dp", "");
  buildDatePicker("absence-to-dp", "");
  buildDatePicker("settlement-from-dp", "");
  buildDatePicker("settlement-to-dp", "");
  initPeriodSwitches();
  document.getElementById("filter-status").addEventListener("change", () => { updateStatChipActive(); renderActivitiesTable(); });
  document.getElementById("filter-employee").addEventListener("change", renderActivitiesTable);
  document.getElementById("filter-dispatcher-group").addEventListener("change", () => { fillEmployeeFilter(); renderActivitiesTable(); });
  document.getElementById("filter-payroll-ready").addEventListener("change", renderActivitiesTable);
  document.getElementById("settlement-filter-dispatcher-group")?.addEventListener("change", settlementDispatcherGroupFilterChanged);
  document.getElementById("settlement-filter-employee")?.addEventListener("change", loadPayrollSettlement);
  document.getElementById("stat-pending") ?.addEventListener("click", () => toggleStatFilter("pending"));
  document.getElementById("stat-approved")?.addEventListener("click", () => toggleStatFilter("approved"));
  document.getElementById("stat-deact")   ?.addEventListener("click", () => toggleStatFilter("deactivated"));
  document.getElementById("show-inactive")?.addEventListener("change", loadEmployees);
  document.getElementById("employee-search")?.addEventListener("input", renderEmployeeList);
  document.getElementById("employee-filter-dispatcher-group")?.addEventListener("change", renderEmployeeList);
  ["employee-filter-position", "employee-filter-personaleforening", "employee-filter-natarbejde", "employee-filter-elev"]
    .forEach(id => document.getElementById(id)?.addEventListener("change", renderEmployeeList));
  document.getElementById("vehicle-search")?.addEventListener("input", renderVehicleList);
  document.getElementById("supplement-employee-search")?.addEventListener("input", renderSupplementEmployeeList);

  // Klik på den mørke baggrund lukker vinduet – men kun hvis musen også blev TRYKKET ned på
  // baggrunden. Ellers lukkede vinduet (og input gik tabt), når man markerede tekst i et felt
  // og slap musen uden for vinduet (2026-10-06). Lyttes på dokumentet, så det også gælder
  // vinduer der oprettes senere (fx Advarsler). Har vinduet en _onClose, bruges den i stedet.
  let pressedOverlay = null;
  document.addEventListener("mousedown", e => {
    pressedOverlay = e.target.classList?.contains("modal-overlay") ? e.target : null;
  });
  document.addEventListener("click", e => {
    const overlay = e.target;
    if (overlay.classList?.contains("modal-overlay") && overlay === pressedOverlay) {
      if (overlay._onClose) overlay._onClose();
      else overlay.classList.remove("open");
    }
    pressedOverlay = null;
  });

  const loggedIn = await initAuth();
  if (loggedIn) await loadApp();
}

document.addEventListener("DOMContentLoaded", init);

// ── Employee supplements ────────────────────────────────────────────────────
state.selectedSupplementEmployeeId = null;

async function loadEmployeeSupplementsView() {
  state.employees = await GET("/api/employees?active_only=false");
  renderSupplementEmployeeList();
}

function renderSupplementEmployeeList() {
  const query = (document.getElementById("supplement-employee-search")?.value || "").toLowerCase().trim();
  const container = document.getElementById("supplement-employee-list");
  container.innerHTML = "";
  let emps = state.employees;
  if (query) {
    emps = emps.filter(e =>
      e.name.toLowerCase().includes(query) ||
      String(e.employee_number).toLowerCase().includes(query)
    );
  }
  emps = emps.slice().sort((a, b) => a.name.localeCompare(b.name, "da"));
  if (emps.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="icon">👤</div><h3>Ingen medarbejdere</h3></div>`;
    return;
  }
  for (const e of emps) {
    const initials = `${e.first_name[0] || ""}${e.last_name[0] || ""}`.toUpperCase();
    const div = document.createElement("div");
    div.className = "emp-card";
    div.style.cursor = "pointer";
    div.innerHTML = `
      <div class="emp-avatar">${h(initials)}</div>
      <div class="emp-info">
        <div class="emp-name">${h(e.name)}</div>
        <div class="emp-sub">Lønnr. ${h(e.employee_number)}</div>
      </div>
    `;
    div.addEventListener("click", () => selectSupplementEmployee(e.id, e.name));
    container.appendChild(div);
  }
}

function selectSupplementEmployee(employeeId, employeeName) {
  state.selectedSupplementEmployeeId = employeeId;
  document.getElementById("supplement-detail-name").textContent = employeeName;
  buildDatePicker("supplement-from-dp", "");
  buildDatePicker("supplement-to-dp", "");
  loadSupplementDetail();
  openModal("modal-supplement-detail");
}

async function loadSupplementDetail() {
  const employeeId = state.selectedSupplementEmployeeId;
  if (!employeeId) return;
  const tbody = document.getElementById("supplement-detail-tbody");
  tbody.innerHTML = `<tr><td colspan="8" style="padding:30px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  const from = readDatePicker("supplement-from-dp");
  const to = readDatePicker("supplement-to-dp");
  let qs = `employee_id=${employeeId}`;
  if (from) qs += `&from=${from}`;
  if (to) qs += `&to=${to}`;
  try {
    const rows = await GET(`/api/employee-supplements?${qs}`);
    if (rows.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="padding:24px;text-align:center;color:var(--text-light)">Ingen tillæg fundet</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map(r => `
      <tr style="border-bottom:1px solid var(--border);background:#fff">
        <td style="padding:10px 14px;font-weight:600;color:${r.is_active ? "var(--approved)" : "var(--danger)"}">${r.is_active ? "Aktiv" : (r.deactivated ? "Afsluttet" : "Inaktiv")}</td>
        <td style="padding:10px 14px">${h(r.employee_number)}</td>
        <td style="padding:10px 14px">${h(r.name)}</td>
        <td style="padding:10px 14px">${h(r.type)}</td>
        <td style="padding:10px 14px">${formatDateShort(r.start_date)}</td>
        <td style="padding:10px 14px">${r.end_date === "9999-12-31" ? "–" : formatDateShort(r.end_date)}</td>
        <td style="padding:10px 14px;text-align:right">${r.value.toFixed(2)} kr</td>
        <td style="padding:10px 14px;text-align:center">${r.end_date === "9999-12-31" ? `<button class="btn btn-danger" style="font-size:12px;padding:4px 10px" onclick="endSupplement(${r.id})">Afslut</button>` : ""}</td>
      </tr>`).join("");
  } catch (e) { toast(e.message, "error"); }
}

async function endSupplement(id) {
  if (!confirm("Afslut dette tillæg? Dags dato bliver sidste dag, tillægget gælder. Det tæller stadig med for de dage, hvor det har været gyldigt.")) return;
  try {
    await POST(`/api/employee-supplements/${id}/end`, {});
    toast("Tillæg afsluttet", "success");
    await loadSupplementDetail();
  } catch (e) { toast(e.message, "error"); }
}

function openAddSupplementModal() {
  const sel = document.getElementById("supplement-employee-select");
  sel.innerHTML = state.employees
    .slice().sort((a, b) => a.name.localeCompare(b.name, "da"))
    .map(e => `<option value="${e.id}">${h(e.name)} (Lønnr. ${h(e.employee_number)})</option>`).join("");
  if (state.selectedSupplementEmployeeId) sel.value = state.selectedSupplementEmployeeId;
  document.getElementById("supplement-value").value = "";
  buildDatePicker("supplement-start-dp", new Date().toISOString().slice(0, 10));
  openModal("modal-supplement");
}

function openAddSupplementFromDetail() {
  closeModal("modal-supplement-detail");
  openAddSupplementModal();
}

async function confirmAddSupplement() {
  const employeeId = parseInt(document.getElementById("supplement-employee-select").value);
  const startDate = readDatePicker("supplement-start-dp");
  const value = parseFloat(document.getElementById("supplement-value").value);
  if (!employeeId || !startDate || !value || value <= 0) {
    toast("Udfyld medarbejder, startdato og en positiv værdi", "error");
    return;
  }
  try {
    await POST("/api/employee-supplements", { employee_id: employeeId, start_date: startDate, value });
    toast("Tillæg oprettet", "success");
    closeModal("modal-supplement");
    if (state.selectedSupplementEmployeeId === employeeId) {
      await loadSupplementDetail();
      openModal("modal-supplement-detail");
    }
  } catch (e) { toast(e.message, "error"); }
}
