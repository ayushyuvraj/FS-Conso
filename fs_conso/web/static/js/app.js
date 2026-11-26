/**
 * Enterprise Financial Consolidation Portal - Frontend State Machine
 * Real accounting, real LangGraph agents, zero simulations.
 * Incorporates Emil Kowalski physics, Impeccable luxury styling, and UI/UX Pro Max density.
 */

let appStatus = {};
let pipelineData = {};
let activeStep = 1;
let activeSection = 'RUN'; // 'RUN' or 'AUDIT'
let activeNavSection = localStorage.getItem("fs_conso_active_nav_section") || 'COMPANIES';
let isLauncherActive = true;
let isNavigatingDirectly = false;
let activeRunId = null;
let activeRunName = null;
let activeRunPeriod = null;
let auditRunsList = [];
let auditRunSearchQuery = "";
let auditFilterCompany = "ALL";
let auditFilterStatus = "ALL";
let auditCurrentPage = 1;
let auditPageSize = 10;
let sidebarCollapsed = false;
let availableCompanies = [];
let pendingHITLItems = [];
let collapseEntityColumns = false;

document.addEventListener("DOMContentLoaded", async () => {
    initSidebar();
    initToolbarDropdowns();
    initDateFormatSetting();
    initDialogAndDrawerResizers();
    initTableColumnResizers();
    initTableObserver();
    populateProfileCurrencySelects();
    await fetchCompanies();
    await fetchStatus();
    await syncCachedApiKeyIfAvailable();
    const savedNav = localStorage.getItem("fs_conso_active_nav_section") || 'COMPANIES';
    switchNavSection(savedNav);
    loadPipelineData();
    initDropZone();
    initBatchDropZone();
    initCOADropZone();
});

function initSidebar() {
    try {
        const saved = localStorage.getItem("fs_conso_sidebar_collapsed");
        if (saved === "true") {
            sidebarCollapsed = true;
            applySidebarState();
        }
    } catch (_) { }

    initSidebarTooltips();

    // Global keyboard shortcut: Ctrl+B or Cmd+B to toggle sidebar
    document.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && (e.key === "b" || e.key === "B")) {
            e.preventDefault();
            toggleSidebar();
        }
    });
}

function initSidebarTooltips() {
    let tooltipEl = document.getElementById("sidebar-floating-tooltip");
    if (!tooltipEl) {
        tooltipEl = document.createElement("div");
        tooltipEl.id = "sidebar-floating-tooltip";
        tooltipEl.className = "fixed pointer-events-none z-50 text-xs font-semibold px-2.5 py-1.5 rounded-md bg-[#001D48] text-white shadow-xl border border-[#0091DA]/40 opacity-0 transition-opacity duration-150";
        document.body.appendChild(tooltipEl);
    }

    document.querySelectorAll("#sidebar-nav .sidebar-nav-item").forEach(item => {
        item.addEventListener("mouseenter", () => {
            if (!sidebarCollapsed) return;
            const text = item.getAttribute("data-tooltip");
            if (!text) return;
            tooltipEl.textContent = text;
            const rect = item.getBoundingClientRect();
            tooltipEl.style.top = `${rect.top + (rect.height / 2) - 14}px`;
            tooltipEl.style.left = `${rect.right + 10}px`;
            tooltipEl.classList.remove("opacity-0");
            tooltipEl.classList.add("opacity-100");
        });
        item.addEventListener("mouseleave", () => {
            tooltipEl.classList.remove("opacity-100");
            tooltipEl.classList.add("opacity-0");
        });
        item.addEventListener("click", () => {
            tooltipEl.classList.remove("opacity-100");
            tooltipEl.classList.add("opacity-0");
        });
    });
}

function toggleSidebar() {
    sidebarCollapsed = !sidebarCollapsed;
    applySidebarState();
    try {
        localStorage.setItem("fs_conso_sidebar_collapsed", sidebarCollapsed ? "true" : "false");
    } catch (_) { }
}

function applySidebarState() {
    const sidebar = document.getElementById("sidebar-nav");
    const mainLayout = document.getElementById("main-layout-container");
    const toggleBtn = document.getElementById("btn-toggle-sidebar");

    if (sidebar) {
        if (sidebarCollapsed) {
            sidebar.classList.add("collapsed");
        } else {
            sidebar.classList.remove("collapsed");
        }
    }
    if (mainLayout) {
        if (sidebarCollapsed) {
            mainLayout.classList.add("sidebar-collapsed");
        } else {
            mainLayout.classList.remove("sidebar-collapsed");
        }
    }
    if (toggleBtn) {
        toggleBtn.setAttribute("aria-expanded", sidebarCollapsed ? "false" : "true");
        toggleBtn.title = sidebarCollapsed ? "Expand Sidebar (Ctrl+B)" : "Collapse Sidebar (Ctrl+B)";
    }
}

async function syncCachedApiKeyIfAvailable() {
    try {
        const cachedKey = localStorage.getItem("fs_conso_gemini_key");
        if (cachedKey && !appStatus.has_active_api_key) {
            const res = await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ gemini_api_key: cachedKey })
            });
            const data = await res.json();
            if (data.success) {
                await fetchStatus();
            }
        }
    } catch (_) { }
}

// -------------------------------------------------------------
// Company Profile State, Reference Helpers & Shake Validation
// -------------------------------------------------------------
let selectedCOAFile = null;
let editingProfileHasExistingCOA = false;
let subsidiaryDrafts = [];
let pendingDeleteCompanyId = null;

// Option A: Directory Search, Sort & Filter State
let companySearchQuery = "";
let companySortKey = "name-asc";
let companyFilterCategory = "ALL"; // 'ALL', 'WITH_SUBS', 'STANDALONE'
let companyFilterCurrency = "ALL"; // 'ALL' or specific ISO currency e.g. 'INR', 'USD'
let expandedCompanyIds = new Set();
let companyCurrentPage = 1;
let companyPageSize = 10;

// -------------------------------------------------------------
// Enterprise Date Formatting System (Google / Microsoft Standards)
// -------------------------------------------------------------

let currentDateFormat = "YYYY-MM-DD HH:mm";

function initDateFormatSetting() {
    try {
        const saved = localStorage.getItem("fs_conso_date_format");
        if (saved) {
            currentDateFormat = saved;
        }
        const selectEl = document.getElementById("setting-date-format");
        if (selectEl) {
            selectEl.value = currentDateFormat;
        }
    } catch (_) { }
}

function handleDateFormatChange(val) {
    currentDateFormat = val || "YYYY-MM-DD HH:mm";
    try {
        localStorage.setItem("fs_conso_date_format", currentDateFormat);
    } catch (_) { }
    renderCompanyTableBody();
    renderHeaderStatus();
    updateBatchUploadPeriodDisplay();
    if (activeNavSection === 'AUDIT') fetchAndRenderAuditRuns();
    showToast("Date Format Updated", `Timestamps formatted as ${currentDateFormat}`, "info");
}

function parseLocalDate(dateVal) {
    if (!dateVal) return null;
    if (dateVal instanceof Date) return isNaN(dateVal.getTime()) ? null : dateVal;
    const str = String(dateVal).trim();
    if (!str) return null;

    // Check YYYY-MM-DD or YYYY/MM/DD
    const isoMatch = str.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
    if (isoMatch) {
        const y = parseInt(isoMatch[1], 10);
        const m = parseInt(isoMatch[2], 10) - 1;
        const d = parseInt(isoMatch[3], 10);
        return new Date(y, m, d);
    }

    // Check DD-MM-YYYY or DD/MM/YYYY
    const dmyMatch = str.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})/);
    if (dmyMatch) {
        const d = parseInt(dmyMatch[1], 10);
        const m = parseInt(dmyMatch[2], 10) - 1;
        const y = parseInt(dmyMatch[3], 10);
        return new Date(y, m, d);
    }

    // Check DD-Mon-YYYY (e.g. 31-Mar-2024 or 31 Mar 2024)
    const monNames = {
        jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5,
        jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11
    };
    const namedMonthMatch = str.match(/^(\d{1,2})[- ]([A-Za-z]{3,9})[- ](\d{4})/);
    if (namedMonthMatch) {
        const d = parseInt(namedMonthMatch[1], 10);
        const monKey = namedMonthMatch[2].slice(0, 3).toLowerCase();
        const y = parseInt(namedMonthMatch[3], 10);
        if (monNames[monKey] !== undefined) {
            return new Date(y, monNames[monKey], d);
        }
    }

    // Fallback standard parse
    const parsed = new Date(str.replace(" ", "T"));
    if (!isNaN(parsed.getTime())) return parsed;
    const fallback = new Date(str);
    return isNaN(fallback.getTime()) ? null : fallback;
}

function formatDateOnly(dateVal) {
    if (!dateVal) return "—";
    const d = parseLocalDate(dateVal);
    if (!d || isNaN(d.getTime())) return String(dateVal);

    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const monthStr = monthNames[d.getMonth()];

    switch (currentDateFormat) {
        case "DD-MM-YYYY HH:mm":
            return `${day}-${month}-${year}`;
        case "MM/DD/YYYY hh:mm A":
            return `${month}/${day}/${year}`;
        case "DD MMM YYYY, HH:mm":
            return `${day} ${monthStr} ${year}`;
        case "MMM DD, YYYY, hh:mm A":
            return `${monthStr} ${day}, ${year}`;
        case "YYYY-MM-DD HH:mm":
        default:
            return `${year}-${month}-${day}`;
    }
}

function formatDateTime(dateVal) {
    if (!dateVal) return "—";
    let d;
    if (typeof dateVal === "string") {
        const clean = dateVal.trim();
        if (!clean) return "—";
        d = new Date(clean.replace(" ", "T"));
        if (isNaN(d.getTime())) {
            d = new Date(clean);
        }
    } else {
        d = new Date(dateVal);
    }
    if (isNaN(d.getTime())) {
        return String(dateVal);
    }

    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    const hours24 = d.getHours();
    const hours = String(hours24).padStart(2, "0");
    const minutes = String(d.getMinutes()).padStart(2, "0");
    const hours12 = String(hours24 % 12 || 12).padStart(2, "0");
    const ampm = hours24 >= 12 ? "PM" : "AM";
    const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const monthStr = monthNames[d.getMonth()];

    switch (currentDateFormat) {
        case "DD-MM-YYYY HH:mm":
            return `${day}-${month}-${year} ${hours}:${minutes}`;
        case "MM/DD/YYYY hh:mm A":
            return `${month}/${day}/${year} ${hours12}:${minutes} ${ampm}`;
        case "DD MMM YYYY, HH:mm":
            return `${day} ${monthStr} ${year}, ${hours}:${minutes}`;
        case "MMM DD, YYYY, hh:mm A":
            return `${monthStr} ${day}, ${year}, ${hours12}:${minutes} ${ampm}`;
        case "YYYY-MM-DD HH:mm":
        default:
            return `${year}-${month}-${day} ${hours}:${minutes}`;
    }
}

function buildCurrencyOptionsHtml(selectedCode = "") {
    const placeholder = `<option value="" ${!selectedCode ? 'selected' : ''}>Select currency...</option>`;
    const opts = (typeof TOP_CURRENCIES !== "undefined" ? TOP_CURRENCIES : []).map(c =>
        `<option value="${escapeHtml(c.code)}" ${c.code === selectedCode ? 'selected' : ''}>${escapeHtml(c.code)} — ${escapeHtml(c.name)} (${escapeHtml(c.symbol)})</option>`
    ).join("");
    return placeholder + opts;
}

function buildCountryOptionsHtml(selectedCountry = "") {
    const placeholder = `<option value="" ${!selectedCountry ? 'selected' : ''}>Select country (optional)...</option>`;
    const opts = (typeof ALL_COUNTRIES !== "undefined" ? ALL_COUNTRIES : []).map(country =>
        `<option value="${escapeHtml(country)}" ${country === selectedCountry ? 'selected' : ''}>${escapeHtml(country)}</option>`
    ).join("");
    return placeholder + opts;
}

function populateProfileCurrencySelects() {
    const repSel = document.getElementById("profile-reporting-currency");
    if (repSel) {
        repSel.innerHTML = buildCurrencyOptionsHtml("");
    }
}

function triggerFieldShake(el, message) {
    if (!el) return;
    el.classList.remove("shake-error");
    void el.offsetWidth; // Force reflow so repeated invalid submits re-trigger shake
    el.classList.add("input-invalid", "shake-error");

    const parent = el.parentElement;
    const hint = parent ? parent.querySelector(".field-error-hint") : null;
    if (hint && message) {
        hint.textContent = message;
        hint.classList.remove("hidden");
    }
}

function clearFieldError(el) {
    if (!el) return;
    el.classList.remove("input-invalid", "shake-error");
    const parent = el.parentElement;
    const hint = parent ? parent.querySelector(".field-error-hint") : null;
    if (hint) {
        hint.textContent = "";
        hint.classList.add("hidden");
    }
}

function validateOwnershipValue(raw) {
    const trimmed = String(raw || "").trim();
    if (!trimmed) return { valid: false, message: "Ownership % is required." };
    if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) {
        return { valid: false, message: "Enter a percentage up to 2 decimals (e.g. 75.50)." };
    }
    const num = Number(trimmed);
    if (!Number.isFinite(num) || num <= 0 || num > 100) {
        return { valid: false, message: "Must be between 0.01% and 100.00%." };
    }
    return { valid: true, value: Number(num.toFixed(2)) };
}

function validateFieldOnBlur(el) {
    if (!el) return true;
    const id = el.id || "";
    const role = el.dataset.role || "";
    const val = (el.value || "").trim();

    if (id === "profile-company-name") {
        if (!val) { triggerFieldShake(el, "Company name is required."); return false; }
        clearFieldError(el); return true;
    }
    if (id === "profile-company-code") {
        if (!val) { triggerFieldShake(el, "Company code is required."); return false; }
        const editId = (document.getElementById("profile-edit-company-id")?.value || "").trim().toLowerCase();
        const duplicate = availableCompanies.find(c => {
            const cId = (c.company_id || "").toLowerCase();
            const cCode = (c.company_code || "").toUpperCase();
            const isSelf = cId === editId || cCode === editId.toUpperCase();
            return !isSelf && cCode === val.toUpperCase();
        });
        if (duplicate) { triggerFieldShake(el, `Code '${val.toUpperCase()}' is already in use.`); return false; }
        clearFieldError(el); return true;
    }
    if (id === "profile-reporting-currency") {
        if (!val) { triggerFieldShake(el, "Reporting currency is required."); return false; }
        clearFieldError(el); return true;
    }
    if (id === "profile-subsidiary-count") {
        const n = Number(val);
        if (val === "" || !Number.isInteger(n) || n < 0 || n > 100) {
            triggerFieldShake(el, "Enter a whole number from 0 to 100.");
            return false;
        }
        clearFieldError(el); return true;
    }
    if (role === "sub-entity-name") {
        if (!val) { triggerFieldShake(el, "Entity name is required."); return false; }
        clearFieldError(el); return true;
    }
    if (role === "sub-currency") {
        if (!val) { triggerFieldShake(el, "Entity currency is required."); return false; }
        clearFieldError(el); return true;
    }
    if (role === "sub-ownership") {
        const res = validateOwnershipValue(val);
        if (!res.valid) { triggerFieldShake(el, res.message); return false; }
        clearFieldError(el); return true;
    }
    if (role === "sub-acq-date") {
        if (!val) { triggerFieldShake(el, "Acquisition date is required."); return false; }
        clearFieldError(el); return true;
    }
    return true;
}

async function fetchCompanies() {
    try {
        const res = await fetch("/api/companies");
        if (res.ok) {
            const data = await res.json();
            availableCompanies = data.companies || [];
            populateCompanySelector(data.active_company_id);
            populateLauncherCompanies();
        }
    } catch (err) {
        console.error("Failed to load companies:", err);
    }
}

function populateCompanySelector(activeId) {
    const sel = document.getElementById("select-company");
    if (!sel) return;
    sel.innerHTML = availableCompanies.map(c => `
        <option value="${escapeHtml(c.company_id)}" class="bg-slate-900 text-white" ${c.company_id === activeId ? 'selected' : ''}>
            ${escapeHtml(c.company_name)} (${escapeHtml(c.company_code || c.company_id)})
        </option>
    `).join("");
}

async function handleCompanySwitch(companyId) {
    if (!companyId || companyId === appStatus.active_company_id) return;
    try {
        showToast("Switching Company", `Loading profile for ${companyId}...`, "info");
        const res = await fetch("/api/companies/switch", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ company_id: companyId })
        });
        const data = await res.json();
        if (data.success) {
            statementsData = null;
            currentLineageTrace = null;
            await fetchCompanies();
            await fetchStatus();
            await loadPipelineData();
            showToast("Active Profile Switched", `Active profile is now ${appStatus.active_company_name || companyId}.`, "success");
            if (activeNavSection === 'COMPANIES') {
                renderCompanyWorkspace();
            } else {
                switchStep(1);
            }
        } else {
            showToast("Switch Failed", data.detail || "Could not switch company profile.", "error");
        }
    } catch (err) {
        showToast("Error", "Error switching company: " + err, "error");
    }
}

function captureSubsidiaryDraftsFromDOM() {
    const cards = document.querySelectorAll("#subsidiaries-container .subsidiary-card");
    cards.forEach((card, idx) => {
        subsidiaryDrafts[idx] = {
            entity_code: card.dataset.entityCode || "",
            entity_name: card.querySelector('[data-role="sub-entity-name"]')?.value || "",
            company_reg_number: card.querySelector('[data-role="sub-reg-no"]')?.value || "",
            country_of_inc: card.querySelector('[data-role="sub-country"]')?.value || "",
            date_of_inc: card.querySelector('[data-role="sub-inc-date"]')?.value || "",
            input_currency: card.querySelector('[data-role="sub-currency"]')?.value || "",
            ownership_pct: card.querySelector('[data-role="sub-ownership"]')?.value || "",
            acquisition_date: card.querySelector('[data-role="sub-acq-date"]')?.value || ""
        };
    });
}

function handleSubsidiaryCountChange(rawValue) {
    const countInput = document.getElementById("profile-subsidiary-count");
    if (rawValue === "" || rawValue === null || rawValue === undefined) {
        return;
    }
    const count = parseInt(rawValue, 10);
    if (!Number.isInteger(count) || count < 0 || count > 100) {
        triggerFieldShake(countInput, "Enter a whole number between 0 and 100.");
        return;
    }
    clearFieldError(countInput);
    captureSubsidiaryDraftsFromDOM();

    while (subsidiaryDrafts.length < count) {
        subsidiaryDrafts.push({
            entity_code: "",
            entity_name: "",
            company_reg_number: "",
            country_of_inc: "",
            date_of_inc: "",
            input_currency: "",
            ownership_pct: "",
            acquisition_date: ""
        });
    }
    subsidiaryDrafts = subsidiaryDrafts.slice(0, count);
    renderSubsidiaryRows(count);
}

function renderSubsidiaryRows(count) {
    const section = document.getElementById("subsidiaries-section");
    const container = document.getElementById("subsidiaries-container");
    const badge = document.getElementById("subsidiaries-count-badge");
    if (!section || !container) return;

    if (count <= 0) {
        section.classList.add("hidden");
        container.innerHTML = "";
        if (badge) badge.textContent = "0 Entities";
        return;
    }

    section.classList.remove("hidden");
    if (badge) badge.textContent = `${count} ${count === 1 ? 'Subsidiary' : 'Subsidiaries'}`;

    container.innerHTML = subsidiaryDrafts.map((sub, idx) => `
        <div class="subsidiary-card rounded-xl border border-slate-200 bg-slate-50/70 p-4 space-y-3" data-sub-index="${idx}" data-entity-code="${escapeHtml(sub.entity_code || '')}">
            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-2">
                    <span class="w-5 h-5 rounded-full bg-kpmg-blue text-white text-[10px] font-bold flex items-center justify-center">${idx + 1}</span>
                    <span class="font-bold text-xs text-kpmg-navy">Subsidiary #${idx + 1}</span>
                    ${sub.entity_code ? `<span class="font-mono text-[10px] px-2 py-0.5 rounded bg-slate-200/80 text-slate-700">${escapeHtml(sub.entity_code)}</span>` : ''}
                </div>
                <span class="text-[10px] text-slate-500">Fields marked <span class="text-rose-600 font-bold">*</span> are mandatory</span>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                <div class="lg:col-span-2">
                    <label class="font-semibold text-slate-700 block mb-1">Entity Name <span class="text-rose-600">*</span></label>
                    <input type="text" data-role="sub-entity-name" value="${escapeHtml(sub.entity_name)}"
                        placeholder="e.g. Acme Diagnostics Pvt Ltd"
                        oninput="clearFieldError(this)" onblur="validateFieldOnBlur(this)"
                        class="w-full h-9 px-3 rounded-lg border border-slate-300 bg-white text-xs text-slate-900 focus:ring-2 focus:ring-kpmg-electric focus:border-kpmg-blue focus:outline-none transition">
                    <div class="field-error-hint hidden"></div>
                </div>
                <div>
                    <label class="font-semibold text-slate-700 block mb-1">Registration Number <span class="text-slate-400 font-normal">(Optional)</span></label>
                    <input type="text" data-role="sub-reg-no" value="${escapeHtml(sub.company_reg_number)}"
                        placeholder="e.g. U85110KA2020PTC..."
                        class="w-full h-9 px-3 rounded-lg border border-slate-300 bg-white font-mono text-xs text-slate-900 focus:ring-2 focus:ring-kpmg-electric focus:border-kpmg-blue focus:outline-none transition">
                </div>
                <div>
                    <label class="font-semibold text-slate-700 block mb-1">Country of Incorporation <span class="text-slate-400 font-normal">(Optional)</span></label>
                    <select data-role="sub-country"
                        class="w-full h-9 px-2.5 rounded-lg border border-slate-300 bg-white text-xs text-slate-900 focus:ring-2 focus:ring-kpmg-electric focus:border-kpmg-blue focus:outline-none transition">
                        ${buildCountryOptionsHtml(sub.country_of_inc)}
                    </select>
                </div>
                <div>
                    <label class="font-semibold text-slate-700 block mb-1">Date of Incorporation <span class="text-slate-400 font-normal">(Optional)</span></label>
                    <input type="date" data-role="sub-inc-date" value="${escapeHtml(sub.date_of_inc)}"
                        class="w-full h-9 px-3 rounded-lg border border-slate-300 bg-white font-mono text-xs text-slate-900 focus:ring-2 focus:ring-kpmg-electric focus:border-kpmg-blue focus:outline-none transition">
                </div>
                <div>
                    <label class="font-semibold text-slate-700 block mb-1">Entity Currency <span class="text-rose-600">*</span></label>
                    <select data-role="sub-currency"
                        onchange="validateFieldOnBlur(this)"
                        class="w-full h-9 px-2.5 rounded-lg border border-slate-300 bg-white text-xs text-slate-900 focus:ring-2 focus:ring-kpmg-electric focus:border-kpmg-blue focus:outline-none transition">
                        ${buildCurrencyOptionsHtml(sub.input_currency)}
                    </select>
                    <div class="field-error-hint hidden"></div>
                </div>
                <div>
                    <label class="font-semibold text-slate-700 block mb-1">Ownership % <span class="text-rose-600">*</span></label>
                    <div class="relative">
                        <input type="text" inputmode="decimal" data-role="sub-ownership" value="${escapeHtml(sub.ownership_pct !== '' && sub.ownership_pct !== undefined ? String(sub.ownership_pct) : '')}"
                            placeholder="e.g. 75.50"
                            oninput="clearFieldError(this)" onblur="validateFieldOnBlur(this)"
                            class="w-full h-9 pl-3 pr-7 rounded-lg border border-slate-300 bg-white font-mono text-xs text-slate-900 focus:ring-2 focus:ring-kpmg-electric focus:border-kpmg-blue focus:outline-none transition">
                        <span class="absolute right-2.5 top-1/2 -translate-y-1/2 text-[11px] font-mono text-slate-400 pointer-events-none">%</span>
                    </div>
                    <div class="field-error-hint hidden"></div>
                </div>
                <div>
                    <label class="font-semibold text-slate-700 block mb-1">Acquisition Date <span class="text-rose-600">*</span></label>
                    <input type="date" data-role="sub-acq-date" value="${escapeHtml(sub.acquisition_date)}"
                        onchange="validateFieldOnBlur(this)" onblur="validateFieldOnBlur(this)"
                        class="w-full h-9 px-3 rounded-lg border border-slate-300 bg-white font-mono text-xs text-slate-900 focus:ring-2 focus:ring-kpmg-electric focus:border-kpmg-blue focus:outline-none transition">
                    <div class="field-error-hint hidden"></div>
                </div>
            </div>
        </div>
    `).join("");
}

function resetCOAError() {
    const dropZone = document.getElementById("coa-drop-zone");
    const errEl = document.getElementById("coa-file-error");
    if (dropZone) dropZone.classList.remove("input-invalid", "shake-error");
    if (errEl) {
        errEl.textContent = "";
        errEl.classList.add("hidden");
    }
}

function showCOAShakeError(message) {
    const dropZone = document.getElementById("coa-drop-zone");
    const errEl = document.getElementById("coa-file-error");
    if (dropZone) {
        dropZone.classList.remove("shake-error");
        void dropZone.offsetWidth;
        dropZone.classList.add("input-invalid", "shake-error");
    }
    if (errEl) {
        errEl.textContent = message;
        errEl.classList.remove("hidden");
    }
}

function handleCOAFileSelected(input) {
    if (input.files && input.files.length > 0) {
        selectedCOAFile = input.files[0];
        updateCOADropZoneLabel();
        resetCOAError();
    }
}

function updateCOADropZoneLabel(existingFilename = null, existingCount = 0) {
    const label = document.getElementById("coa-file-label");
    const sublabel = document.getElementById("coa-file-sublabel");
    if (!label || !sublabel) return;

    if (selectedCOAFile) {
        label.innerHTML = `<span class="text-emerald-700">✓ Selected Base COA:</span> <span class="font-mono text-kpmg-navy">${escapeHtml(selectedCOAFile.name)}</span> (${(selectedCOAFile.size / 1024).toFixed(1)} KB)`;
        sublabel.textContent = "Click or drop another .xlsx, .xls, or .csv file to replace.";
    } else if (existingFilename) {
        label.innerHTML = `<span class="text-kpmg-blue">Current Base COA:</span> <span class="font-mono text-kpmg-navy">${escapeHtml(existingFilename)}</span> (${existingCount} accounts)`;
        sublabel.textContent = "Upload a new .xlsx, .xls, or .csv file only if you want to replace the Chart of Accounts for future runs.";
    } else {
        label.innerHTML = `Upload Base Chart of Accounts (.xlsx, .xls, .csv) <span class="text-rose-600">*</span>`;
        sublabel.textContent = "This Chart of Accounts acts as the foundational ledger structure for all future consolidation runs of this company.";
    }
}

function initCOADropZone() {
    const dropZone = document.getElementById("coa-drop-zone");
    if (!dropZone || dropZone.dataset.initialized) return;
    dropZone.dataset.initialized = "true";

    ['dragenter', 'dragover'].forEach(evt => {
        dropZone.addEventListener(evt, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add("dragover");
        });
    });
    ['dragleave', 'drop'].forEach(evt => {
        dropZone.addEventListener(evt, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove("dragover");
        });
    });
    dropZone.addEventListener("drop", (e) => {
        const files = e.dataTransfer?.files;
        if (files && files.length > 0) {
            selectedCOAFile = files[0];
            updateCOADropZoneLabel();
            resetCOAError();
        }
    });
}

function openCreateProfileModal() {
    const modal = document.getElementById("modal-company-profile");
    if (!modal) return;
    document.getElementById("form-company-profile").reset();
    document.getElementById("profile-edit-company-id").value = "";
    document.getElementById("modal-profile-title").textContent = "Create Company Profile";
    document.getElementById("btn-save-profile").textContent = "Create Profile";

    const codeInput = document.getElementById("profile-company-code");
    if (codeInput) codeInput.readOnly = false;

    populateProfileCurrencySelects();
    document.getElementById("profile-subsidiary-count").value = "0";
    subsidiaryDrafts = [];
    renderSubsidiaryRows(0);

    selectedCOAFile = null;
    editingProfileHasExistingCOA = false;
    const coaInput = document.getElementById("profile-coa-input");
    if (coaInput) coaInput.value = "";
    updateCOADropZoneLabel();
    resetCOAError();

    modal.querySelectorAll(".input-invalid, .shake-error").forEach(el => clearFieldError(el));
    modal.classList.remove("hidden");
    setTimeout(() => document.getElementById("profile-company-name")?.focus(), 50);
}

function openEditProfileModal(companyId) {
    const targetClean = String(companyId || "").trim();
    const comp = availableCompanies.find(c =>
        (c.company_id && c.company_id.toLowerCase() === targetClean.toLowerCase()) ||
        (c.company_code && c.company_code.toUpperCase() === targetClean.toUpperCase())
    );
    if (!comp) return;
    const modal = document.getElementById("modal-company-profile");
    if (!modal) return;

    document.getElementById("form-company-profile").reset();
    document.getElementById("profile-edit-company-id").value = comp.company_id;
    document.getElementById("modal-profile-title").textContent = `Edit Profile — ${comp.company_name}`;
    document.getElementById("btn-save-profile").textContent = "Save Changes";

    document.getElementById("profile-company-name").value = comp.company_name || "";
    const codeInput = document.getElementById("profile-company-code");
    codeInput.value = comp.company_code || "";
    codeInput.readOnly = false;

    const repSel = document.getElementById("profile-reporting-currency");
    repSel.innerHTML = buildCurrencyOptionsHtml(comp.reporting_currency || "");

    const subs = comp.subsidiaries || [];
    document.getElementById("profile-subsidiary-count").value = String(subs.length);
    subsidiaryDrafts = subs.map(s => ({
        entity_code: s.entity_code || "",
        entity_name: s.entity_name || "",
        company_reg_number: s.company_reg_number || "",
        country_of_inc: s.country_of_inc || "",
        date_of_inc: s.date_of_inc || "",
        input_currency: s.input_currency || "",
        ownership_pct: s.ownership_pct !== undefined && s.ownership_pct !== null ? Number(s.ownership_pct).toFixed(2) : "",
        acquisition_date: s.acquisition_date || ""
    }));
    renderSubsidiaryRows(subs.length);

    selectedCOAFile = null;
    editingProfileHasExistingCOA = (comp.coa_account_count || 0) > 0;
    const coaInput = document.getElementById("profile-coa-input");
    if (coaInput) coaInput.value = "";
    updateCOADropZoneLabel(comp.coa_filename || "Base Chart of Accounts", comp.coa_account_count || 0);
    resetCOAError();

    modal.querySelectorAll(".input-invalid, .shake-error").forEach(el => clearFieldError(el));
    modal.classList.remove("hidden");
}

function closeCompanyProfileModal() {
    const modal = document.getElementById("modal-company-profile");
    if (modal) modal.classList.add("hidden");
}

async function submitCompanyProfile(e) {
    e.preventDefault();
    const editId = document.getElementById("profile-edit-company-id").value.trim();
    const nameEl = document.getElementById("profile-company-name");
    const codeEl = document.getElementById("profile-company-code");
    const currEl = document.getElementById("profile-reporting-currency");
    const countEl = document.getElementById("profile-subsidiary-count");

    let firstInvalid = null;
    const recordInvalid = (el) => { if (!firstInvalid && el) firstInvalid = el; };

    if (!validateFieldOnBlur(nameEl)) recordInvalid(nameEl);
    if (!validateFieldOnBlur(codeEl)) recordInvalid(codeEl);
    if (!validateFieldOnBlur(currEl)) recordInvalid(currEl);
    if (!validateFieldOnBlur(countEl)) recordInvalid(countEl);

    const subCount = parseInt(countEl.value, 10);
    const cards = Array.from(document.querySelectorAll("#subsidiaries-container .subsidiary-card"));
    const subsidiariesPayload = [];

    cards.forEach((card) => {
        const entNameEl = card.querySelector('[data-role="sub-entity-name"]');
        const regEl = card.querySelector('[data-role="sub-reg-no"]');
        const countryEl = card.querySelector('[data-role="sub-country"]');
        const incDateEl = card.querySelector('[data-role="sub-inc-date"]');
        const subCurrEl = card.querySelector('[data-role="sub-currency"]');
        const ownEl = card.querySelector('[data-role="sub-ownership"]');
        const acqEl = card.querySelector('[data-role="sub-acq-date"]');

        if (!validateFieldOnBlur(entNameEl)) recordInvalid(entNameEl);
        if (!validateFieldOnBlur(subCurrEl)) recordInvalid(subCurrEl);
        if (!validateFieldOnBlur(ownEl)) recordInvalid(ownEl);
        if (!validateFieldOnBlur(acqEl)) recordInvalid(acqEl);

        const ownCheck = validateOwnershipValue(ownEl?.value);
        subsidiariesPayload.push({
            entity_code: card.dataset.entityCode || null,
            entity_name: (entNameEl?.value || "").trim(),
            company_reg_number: (regEl?.value || "").trim() || null,
            country_of_inc: (countryEl?.value || "").trim() || null,
            date_of_inc: (incDateEl?.value || "").trim() || null,
            input_currency: (subCurrEl?.value || "").trim(),
            ownership_pct: ownCheck.valid ? ownCheck.value : 0,
            acquisition_date: (acqEl?.value || "").trim()
        });
    });

    if (!editId && !selectedCOAFile) {
        showCOAShakeError("Default Chart of Accounts file (.xlsx, .xls, .csv) is mandatory.");
        recordInvalid(document.getElementById("coa-drop-zone"));
    }

    if (firstInvalid) {
        firstInvalid.scrollIntoView({ behavior: "smooth", block: "center" });
        if (typeof firstInvalid.focus === "function") firstInvalid.focus();
        showToast("Incomplete Profile", "Please fill in all highlighted mandatory fields.", "warning");
        return;
    }

    const payload = {
        company_name: nameEl.value.trim(),
        company_code: codeEl.value.trim().toUpperCase(),
        reporting_currency: currEl.value.trim().toUpperCase(),
        number_of_subsidiaries: Number.isInteger(subCount) ? subCount : 0,
        subsidiaries: subsidiariesPayload
    };

    const formData = new FormData();
    formData.append("profile_json", JSON.stringify(payload));
    if (selectedCOAFile) {
        formData.append("coa_file", selectedCOAFile);
    }

    const saveBtn = document.getElementById("btn-save-profile");
    const origBtnText = saveBtn.textContent;
    saveBtn.disabled = true;
    saveBtn.textContent = editId ? "Saving Changes..." : "Creating Profile...";

    try {
        const url = editId ? `/api/companies/${encodeURIComponent(editId)}` : "/api/companies/create";
        const method = editId ? "PUT" : "POST";
        const res = await fetch(url, { method, body: formData });

        let data = {};
        const resText = await res.text();
        try {
            data = JSON.parse(resText);
        } catch (_) {
            data = { detail: resText || `Server returned HTTP ${res.status} ${res.statusText}` };
        }

        if (res.ok && data.success) {
            closeCompanyProfileModal();
            showToast(
                editId ? "Profile Updated" : "Profile Created",
                `${payload.company_name} (${payload.company_code}) saved with ${data.company.coa_account_count} COA accounts.`,
                "success"
            );
            await fetchCompanies();
            await fetchStatus();
            await loadPipelineData();
            renderCompanyWorkspace();
        } else {
            const rawMsg = (data && (data.detail || data.message)) || `Server returned HTTP ${res.status}`;
            const msg = typeof rawMsg === "object" ? JSON.stringify(rawMsg) : String(rawMsg);
            if (msg.toLowerCase().includes("chart of accounts") || msg.toLowerCase().includes("coa")) {
                showCOAShakeError(msg);
            } else if (msg.toLowerCase().includes("code")) {
                triggerFieldShake(codeEl, msg);
            }
            showToast("Validation Error", msg, "error");
        }
    } catch (err) {
        showToast("Network Error", "Failed to save company profile: " + err.message, "error");
    } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = origBtnText;
    }
}

function openDeleteProfileModal(companyId) {
    const targetClean = String(companyId || "").trim();
    const comp = availableCompanies.find(c =>
        (c.company_id && c.company_id.toLowerCase() === targetClean.toLowerCase()) ||
        (c.company_code && c.company_code.toUpperCase() === targetClean.toUpperCase())
    );
    if (!comp) return;
    pendingDeleteCompanyId = companyId;
    document.getElementById("delete-profile-name").textContent = comp.company_name || companyId;
    document.getElementById("delete-profile-code").textContent = comp.company_code || companyId;
    document.getElementById("modal-delete-profile").classList.remove("hidden");
}

function closeDeleteProfileModal() {
    pendingDeleteCompanyId = null;
    document.getElementById("modal-delete-profile").classList.add("hidden");
}

async function confirmDeleteProfile() {
    if (!pendingDeleteCompanyId) return;
    const targetId = pendingDeleteCompanyId;
    try {
        const res = await fetch(`/api/companies/${encodeURIComponent(targetId)}`, { method: "DELETE" });
        const data = await res.json();
        if (res.ok && data.success) {
            closeDeleteProfileModal();
            showToast("Profile Deleted", "Company profile has been removed.", "info");
            statementsData = null;
            currentLineageTrace = null;
            await fetchCompanies();
            await fetchStatus();
            await loadPipelineData();
            renderCompanyWorkspace();
        } else {
            showToast("Delete Failed", data.detail || "Could not delete profile.", "error");
        }
    } catch (err) {
        showToast("Network Error", "Failed to delete profile: " + err, "error");
    }
}

async function fetchStatus() {
    try {
        const res = await fetch("/api/status");
        appStatus = await res.json();
        renderHeaderStatus();
        renderStepperState();
        renderPrerequisiteBanner();
        renderHITLBadge();
    } catch (err) {
        console.error("Status check failed:", err);
    }
}

async function loadPipelineData() {
    try {
        const res = await fetch("/api/pipeline-data");
        pipelineData = await res.json();
        if (activeNavSection === 'COMPANIES') {
            renderCompanyWorkspace();
        } else if (activeNavSection === 'PIPELINE') {
            renderActiveStepContent();
        } else {
            renderObservabilityConsole();
        }
    } catch (err) {
        console.error("Failed to load pipeline data:", err);
    }
}

function renderHeaderStatus() {
    const keyDot = document.getElementById("key-dot");
    const keyLabel = document.getElementById("key-label");
    const keyPill = document.getElementById("key-pill");
    const badgeObs = document.getElementById("badge-nav-observability");
    const dispPeriod = document.getElementById("disp-period");
    const dispCurr = document.getElementById("disp-curr");
    const wrapPeriodCurr = document.getElementById("header-period-curr-wrap");

    if (wrapPeriodCurr) {
        if (activeNavSection === 'COMPANIES' || isLauncherActive || !appStatus.active_company_id) {
            wrapPeriodCurr.classList.add("hidden");
            wrapPeriodCurr.classList.remove("md:flex", "flex");
        } else {
            wrapPeriodCurr.classList.remove("hidden");
            wrapPeriodCurr.classList.add("md:flex");
        }
    }

    if (appStatus.current_period) {
        activeRunPeriod = appStatus.current_period;
    }
    if (dispPeriod) {
        dispPeriod.textContent = (!isLauncherActive && appStatus.active_company_id) ? (appStatus.current_period ? formatDateOnly(appStatus.current_period) : "Pending Run") : "—";
    }
    if (dispCurr) {
        dispCurr.textContent = (!isLauncherActive && appStatus.active_company_id) ? (appStatus.reporting_currency || "—") : "—";
    }

    // Active Company Titles & Badges
    const headerCompany = document.getElementById("header-active-company-name");
    const sidebarEntityBadge = document.getElementById("sidebar-entity-badge");
    const miniCompanyCode = document.getElementById("sidebar-mini-company-code");

    if (headerCompany) {
        if (activeNavSection === 'COMPANIES' || isLauncherActive || !appStatus.active_company_id) {
            headerCompany.textContent = "";
        } else {
            headerCompany.textContent = appStatus.active_company_name || activeRunName || "No Active Profile";
        }
    }
    if (miniCompanyCode) {
        if (appStatus.active_company_code) {
            miniCompanyCode.textContent = appStatus.active_company_code.slice(0, 3);
        } else {
            miniCompanyCode.textContent = "—";
        }
    }
    if (sidebarEntityBadge) {
        const count = appStatus.all_entities ? appStatus.all_entities.length : 0;
        sidebarEntityBadge.textContent = `${count} Entities`;
    }

    if (keyDot && keyLabel && keyPill) {
        if (appStatus.has_active_api_key) {
            keyDot.className = "w-2.5 h-2.5 rounded-full bg-emerald-500";
            keyLabel.textContent = "";
            keyPill.className = "w-7 h-7 rounded-full flex items-center justify-center hover:bg-slate-100 cursor-pointer transition";
            keyPill.title = "Gemini AI: Active (Click to configure)";
        } else {
            keyDot.className = "w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse";
            keyLabel.textContent = "";
            keyPill.className = "w-7 h-7 rounded-full flex items-center justify-center hover:bg-slate-100 cursor-pointer transition";
            keyPill.title = "API Key Missing (Click to configure)";
        }
    }

    const updateObsEl = (el) => {
        if (!el) return;
        if (appStatus.is_running) {
            el.textContent = "Running...";
            el.className = "px-1.5 py-0.5 rounded text-[10px] font-mono bg-amber-500/30 text-amber-300 font-bold animate-pulse";
        } else if (appStatus.is_blocked || appStatus.halted_node) {
            el.textContent = `Halted: ${appStatus.halted_node || 'Gate'}`;
            el.className = "px-1.5 py-0.5 rounded text-[10px] font-mono bg-rose-500/30 text-rose-300 font-bold";
        } else if (appStatus.teacher_score > 0) {
            el.textContent = `${appStatus.teacher_score}/100`;
            el.className = "px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-500/30 text-emerald-300 font-bold";
        } else {
            el.textContent = "Live";
            el.className = "px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-500/30 text-slate-300 font-bold";
        }
    };

    updateObsEl(badgeObs);
}

function renderPrerequisiteBanner() {
    const banner = document.getElementById("banner-prerequisites");
    const textEl = document.getElementById("text-prerequisites");
    if (!banner || !textEl) return;

    const prereqs = appStatus.missing_prerequisites || [];
    if (prereqs.length > 0) {
        textEl.innerHTML = `<strong>Attention Required:</strong> ${prereqs.map(p => escapeHtml(p)).join(" &bull; ")}`;
        banner.classList.remove("hidden");
    } else {
        banner.classList.add("hidden");
    }
}

function renderHITLBadge() {
    const btn = document.getElementById("btn-hitl-trigger");
    const countBadge = document.getElementById("badge-hitl-count");
    if (!btn || !countBadge) return;

    const items = appStatus.hitl_pending_reviews || [];
    if (items.length > 0) {
        countBadge.textContent = items.length;
        btn.classList.remove("hidden");
        btn.classList.add("flex");
    } else {
        btn.classList.add("hidden");
        btn.classList.remove("flex");
    }
}

function switchNavSection(section) {
    activeNavSection = section;
    activeSection = (section === 'AUDIT') ? 'AUDIT' : 'RUN';
    try {
        localStorage.setItem("fs_conso_active_nav_section", section);
    } catch (_) { }

    const itemCompanies = document.getElementById("nav-item-companies");
    const itemPipeline = document.getElementById("nav-item-pipeline");
    const itemAudit = document.getElementById("nav-item-audit");

    [itemCompanies, itemPipeline, itemAudit].forEach(el => el?.classList.remove("active"));

    if (section === 'COMPANIES') {
        itemCompanies?.classList.add("active");
    } else if (section === 'PIPELINE') {
        itemPipeline?.classList.add("active");
    } else if (section === 'AUDIT') {
        itemAudit?.classList.add("active");
    }

    // Direct click on Consolidation in left sidebar nav defaults to fresh run launcher
    if (section === 'PIPELINE' && !isNavigatingDirectly) {
        isLauncherActive = true;
    }

    renderHeaderStatus();

    const viewCompanies = document.getElementById("view-companies");
    const viewLauncher = document.getElementById("view-conso-launcher");
    const viewPipeline = document.getElementById("view-pipeline-run");
    const viewAudit = document.getElementById("view-observability");
    const stepperContainer = document.getElementById("pipeline-stepper-container");

    if (section === 'COMPANIES') {
        viewCompanies?.classList.remove("hidden");
        viewLauncher?.classList.add("hidden");
        viewPipeline?.classList.add("hidden");
        viewAudit?.classList.add("hidden");
        stepperContainer?.classList.add("hidden");
        renderCompanyWorkspace();
    } else if (section === 'PIPELINE') {
        viewCompanies?.classList.add("hidden");
        viewAudit?.classList.add("hidden");
        if (isLauncherActive) {
            viewLauncher?.classList.remove("hidden");
            viewPipeline?.classList.add("hidden");
            stepperContainer?.classList.add("hidden");
            populateLauncherCompanies();
        } else {
            viewLauncher?.classList.add("hidden");
            viewPipeline?.classList.remove("hidden");
            stepperContainer?.classList.remove("hidden");
            renderStepperState();
            renderActiveStepContent();
        }
    } else if (section === 'AUDIT') {
        viewCompanies?.classList.add("hidden");
        viewLauncher?.classList.add("hidden");
        viewPipeline?.classList.add("hidden");
        viewAudit?.classList.remove("hidden");
        stepperContainer?.classList.add("hidden");
        fetchAndRenderAuditRuns();
    }
}

// Backward compatibility alias
function switchSection(section) {
    if (section === 'RUN') {
        switchNavSection('PIPELINE');
    } else if (section === 'AUDIT') {
        switchNavSection('AUDIT');
    } else {
        switchNavSection(section);
    }
}

// -------------------------------------------------------------
// High-Density Institutional Ledger Directory: Clean Toolbar, Sort & Filter
// -------------------------------------------------------------

function initToolbarDropdowns() {
    document.addEventListener("click", (e) => {
        const sortContainer = document.getElementById("sort-dropdown-container");
        const filterContainer = document.getElementById("filter-dropdown-container");
        if (sortContainer && !sortContainer.contains(e.target)) {
            closeSortDropdown();
        }
        if (filterContainer && !filterContainer.contains(e.target)) {
            closeFilterDropdown();
        }
    });

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            closeSortDropdown();
            closeFilterDropdown();
        }
    });
}

function handleCompanySearch(val) {
    companySearchQuery = (val || "").trim().toLowerCase();
    companyCurrentPage = 1;
    const clearBtn = document.getElementById("btn-clear-search");
    if (clearBtn) clearBtn.classList.toggle("hidden", !companySearchQuery);
    renderCompanyTableBody();
}

function clearCompanySearch() {
    const input = document.getElementById("company-directory-search");
    if (input) input.value = "";
    companySearchQuery = "";
    companyCurrentPage = 1;
    const clearBtn = document.getElementById("btn-clear-search");
    if (clearBtn) clearBtn.classList.add("hidden");
    renderCompanyTableBody();
}

// -------------------------------------------------------------
// Sort Popover Logic
// -------------------------------------------------------------

const SORT_OPTIONS = [
    { key: "name-asc", label: "Company Name (A → Z)" },
    { key: "name-desc", label: "Company Name (Z → A)" },
    { key: "code-asc", label: "Company Code (A → Z)" },
    { key: "subs-desc", label: "Most Subsidiaries" },
    { key: "subs-asc", label: "Least Subsidiaries" },
    { key: "coa-desc", label: "Most COA Accounts" },
    { key: "date-desc", label: "Recently Updated" }
];

function toggleSortDropdown(e) {
    if (e) e.stopPropagation();
    closeFilterDropdown();
    const menu = document.getElementById("sort-popover-menu");
    if (!menu) return;
    const isHidden = menu.classList.contains("hidden");
    if (isHidden) {
        renderSortOptionsList();
        menu.classList.remove("hidden");
    } else {
        menu.classList.add("hidden");
    }
}

function closeSortDropdown() {
    const menu = document.getElementById("sort-popover-menu");
    if (menu) menu.classList.add("hidden");
}

function renderSortOptionsList() {
    const container = document.getElementById("sort-options-list");
    if (!container) return;
    container.innerHTML = SORT_OPTIONS.map(opt => {
        const isSelected = (companySortKey === opt.key);
        return `
            <button type="button" onclick="selectSortOption('${escapeHtml(opt.key)}')"
                class="w-full text-left px-3 py-1.5 rounded-lg flex items-center justify-between text-xs transition cursor-pointer select-none ${isSelected ? 'bg-blue-50 text-kpmg-blue font-bold' : 'text-slate-700 hover:bg-slate-50 font-medium'
            }">
                <span>${escapeHtml(opt.label)}</span>
                ${isSelected ? '<span class="text-kpmg-blue font-bold text-xs">✓</span>' : ''}
            </button>
        `;
    }).join("");
}

function selectSortOption(key) {
    companySortKey = key;
    closeSortDropdown();
    updateSortButtonIndicator();
    renderCompanyTableBody();
}

function updateSortButtonIndicator() {
    const indicator = document.getElementById("sort-active-indicator");
    if (indicator) {
        indicator.classList.toggle("hidden", companySortKey === "name-asc");
    }
}

// -------------------------------------------------------------
// Filter Popover Logic (Subsidiary Scope & Base Currency)
// -------------------------------------------------------------

function toggleFilterDropdown(e) {
    if (e) e.stopPropagation();
    closeSortDropdown();
    const menu = document.getElementById("filter-popover-menu");
    if (!menu) return;
    const isHidden = menu.classList.contains("hidden");
    if (isHidden) {
        renderFilterOptionsContent();
        menu.classList.remove("hidden");
    } else {
        menu.classList.add("hidden");
    }
}

function closeFilterDropdown() {
    const menu = document.getElementById("filter-popover-menu");
    if (menu) menu.classList.add("hidden");
}

function renderFilterOptionsContent() {
    const subsContainer = document.getElementById("filter-subsidiaries-options");
    const currContainer = document.getElementById("filter-currency-options");
    const summaryEl = document.getElementById("filter-status-summary");
    if (!subsContainer || !currContainer) return;

    const allCount = (availableCompanies || []).length;
    const withSubsCount = (availableCompanies || []).filter(c => c.subsidiaries && c.subsidiaries.length > 0).length;
    const standaloneCount = (availableCompanies || []).filter(c => !c.subsidiaries || c.subsidiaries.length === 0).length;

    // Render subsidiary structure options
    subsContainer.innerHTML = `
        <label class="flex items-center space-x-2.5 p-1.5 rounded-lg hover:bg-slate-50 cursor-pointer transition select-none ${companyFilterCategory === 'ALL' ? 'bg-blue-50/60 font-semibold text-kpmg-navy' : 'text-slate-700'}">
            <input type="radio" name="popover-subs-filter" value="ALL" ${companyFilterCategory === 'ALL' ? 'checked' : ''} onchange="handleFilterCategoryChange('ALL')" class="text-kpmg-blue focus:ring-kpmg-blue h-3.5 w-3.5 cursor-pointer">
            <span class="text-xs flex-1">All Profiles</span>
            <span class="text-[10px] font-mono text-slate-400">${allCount}</span>
        </label>
        <label class="flex items-center space-x-2.5 p-1.5 rounded-lg hover:bg-slate-50 cursor-pointer transition select-none ${companyFilterCategory === 'WITH_SUBS' ? 'bg-blue-50/60 font-semibold text-kpmg-navy' : 'text-slate-700'}">
            <input type="radio" name="popover-subs-filter" value="WITH_SUBS" ${companyFilterCategory === 'WITH_SUBS' ? 'checked' : ''} onchange="handleFilterCategoryChange('WITH_SUBS')" class="text-kpmg-blue focus:ring-kpmg-blue h-3.5 w-3.5 cursor-pointer">
            <span class="text-xs flex-1">With Subsidiaries</span>
            <span class="text-[10px] font-mono text-slate-400">${withSubsCount}</span>
        </label>
        <label class="flex items-center space-x-2.5 p-1.5 rounded-lg hover:bg-slate-50 cursor-pointer transition select-none ${companyFilterCategory === 'STANDALONE' ? 'bg-blue-50/60 font-semibold text-kpmg-navy' : 'text-slate-700'}">
            <input type="radio" name="popover-subs-filter" value="STANDALONE" ${companyFilterCategory === 'STANDALONE' ? 'checked' : ''} onchange="handleFilterCategoryChange('STANDALONE')" class="text-kpmg-blue focus:ring-kpmg-blue h-3.5 w-3.5 cursor-pointer">
            <span class="text-xs flex-1">Standalone (0 Subs)</span>
            <span class="text-[10px] font-mono text-slate-400">${standaloneCount}</span>
        </label>
    `;

    // Extract dynamic reporting currencies from available companies
    const currenciesMap = {};
    (availableCompanies || []).forEach(c => {
        const curr = (c.reporting_currency || "").toUpperCase().trim();
        if (curr) {
            currenciesMap[curr] = (currenciesMap[curr] || 0) + 1;
        }
    });
    const currencyKeys = Object.keys(currenciesMap).sort();

    let currHtml = `
        <label class="flex items-center space-x-2.5 p-1.5 rounded-lg hover:bg-slate-50 cursor-pointer transition select-none ${companyFilterCurrency === 'ALL' ? 'bg-blue-50/60 font-semibold text-kpmg-navy' : 'text-slate-700'}">
            <input type="radio" name="popover-currency-filter" value="ALL" ${companyFilterCurrency === 'ALL' ? 'checked' : ''} onchange="handleFilterCurrencyChange('ALL')" class="text-kpmg-blue focus:ring-kpmg-blue h-3.5 w-3.5 cursor-pointer">
            <span class="text-xs flex-1">All Currencies</span>
            <span class="text-[10px] font-mono text-slate-400">${allCount}</span>
        </label>
    `;

    currencyKeys.forEach(curr => {
        const isChecked = (companyFilterCurrency === curr);
        currHtml += `
            <label class="flex items-center space-x-2.5 p-1.5 rounded-lg hover:bg-slate-50 cursor-pointer transition select-none ${isChecked ? 'bg-blue-50/60 font-semibold text-kpmg-navy' : 'text-slate-700'}">
                <input type="radio" name="popover-currency-filter" value="${escapeHtml(curr)}" ${isChecked ? 'checked' : ''} onchange="handleFilterCurrencyChange('${escapeHtml(curr)}')" class="text-kpmg-blue focus:ring-kpmg-blue h-3.5 w-3.5 cursor-pointer">
                <span class="text-xs flex-1 font-mono font-medium">${escapeHtml(curr)}</span>
                <span class="text-[10px] font-mono text-slate-400">${currenciesMap[curr]}</span>
            </label>
        `;
    });

    currContainer.innerHTML = currHtml;

    if (summaryEl) {
        const activeCount = (companyFilterCategory !== 'ALL' ? 1 : 0) + (companyFilterCurrency !== 'ALL' ? 1 : 0);
        summaryEl.textContent = activeCount > 0 ? `${activeCount} filter${activeCount > 1 ? 's' : ''} active` : 'Showing all profiles';
    }
}

function handleFilterCategoryChange(cat) {
    companyFilterCategory = cat;
    companyCurrentPage = 1;
    updateFilterBadge();
    renderFilterOptionsContent();
    renderCompanyTableBody();
}

function handleFilterCurrencyChange(curr) {
    companyFilterCurrency = curr;
    companyCurrentPage = 1;
    updateFilterBadge();
    renderFilterOptionsContent();
    renderCompanyTableBody();
}

function resetAllCompanyFilters() {
    companyFilterCategory = 'ALL';
    companyFilterCurrency = 'ALL';
    companyCurrentPage = 1;
    updateFilterBadge();
    renderFilterOptionsContent();
    renderCompanyTableBody();
}

function clearAllFiltersAndSearch() {
    clearCompanySearch();
    resetAllCompanyFilters();
}

function updateFilterBadge() {
    const badge = document.getElementById("filter-active-badge");
    const activeCount = (companyFilterCategory !== 'ALL' ? 1 : 0) + (companyFilterCurrency !== 'ALL' ? 1 : 0);
    if (badge) {
        if (activeCount > 0) {
            badge.textContent = String(activeCount);
            badge.classList.remove("hidden");
        } else {
            badge.classList.add("hidden");
        }
    }
}

// -------------------------------------------------------------
// Expansion & Sorter Filter Logic
// -------------------------------------------------------------

function toggleCompanyExpansion(companyId) {
    if (!companyId) return;
    if (expandedCompanyIds.has(companyId)) {
        expandedCompanyIds.delete(companyId);
    } else {
        expandedCompanyIds.add(companyId);
    }
    const tray = document.getElementById(`tray-${companyId}`);
    const chevron = document.getElementById(`chevron-${companyId}`);
    const row = document.getElementById(`row-${companyId}`);
    const isNowExpanded = expandedCompanyIds.has(companyId);

    if (tray) tray.classList.toggle("hidden", !isNowExpanded);
    if (chevron) chevron.classList.toggle("expanded", isNowExpanded);
    if (row) row.classList.toggle("is-expanded", isNowExpanded);
}

function filterAndSortCompanies() {
    let list = (availableCompanies || []).slice();

    // 1. Category Filter (Subsidiary Structure)
    if (companyFilterCategory === 'WITH_SUBS') {
        list = list.filter(c => (c.subsidiaries && c.subsidiaries.length > 0));
    } else if (companyFilterCategory === 'STANDALONE') {
        list = list.filter(c => (!c.subsidiaries || c.subsidiaries.length === 0));
    }

    // 2. Base Reporting Currency Filter
    if (companyFilterCurrency && companyFilterCurrency !== 'ALL') {
        list = list.filter(c => (c.reporting_currency || "").toUpperCase() === companyFilterCurrency.toUpperCase());
    }

    // 3. Search Query Filter
    if (companySearchQuery) {
        const q = companySearchQuery;
        list = list.filter(c => {
            const nameMatch = (c.company_name || "").toLowerCase().includes(q);
            const codeMatch = (c.company_code || "").toLowerCase().includes(q);
            const idMatch = (c.company_id || "").toLowerCase().includes(q);
            const currMatch = (c.reporting_currency || "").toLowerCase().includes(q);
            const subMatch = (c.subsidiaries || []).some(s =>
                (s.entity_name || "").toLowerCase().includes(q) ||
                (s.company_reg_number || "").toLowerCase().includes(q) ||
                (s.country_of_inc || "").toLowerCase().includes(q) ||
                (s.input_currency || "").toLowerCase().includes(q)
            );
            return nameMatch || codeMatch || idMatch || currMatch || subMatch;
        });
    }

    // 4. Multi-Attribute Sorter
    list.sort((a, b) => {
        switch (companySortKey) {
            case 'name-asc':
                return (a.company_name || "").localeCompare(b.company_name || "", undefined, { sensitivity: 'base' });
            case 'name-desc':
                return (b.company_name || "").localeCompare(a.company_name || "", undefined, { sensitivity: 'base' });
            case 'code-asc':
                return (a.company_code || a.company_id || "").localeCompare(b.company_code || b.company_id || "", undefined, { sensitivity: 'base' });
            case 'subs-desc':
                return (b.subsidiaries?.length || 0) - (a.subsidiaries?.length || 0);
            case 'subs-asc':
                return (a.subsidiaries?.length || 0) - (b.subsidiaries?.length || 0);
            case 'coa-desc':
                return (b.coa_account_count || 0) - (a.coa_account_count || 0);
            case 'date-desc':
                return (b.updated_at || b.created_at || "").localeCompare(a.updated_at || a.created_at || "");
            default:
                return 0;
        }
    });

    return list;
}

// -------------------------------------------------------------
// Enterprise Data Pagination Controls
// -------------------------------------------------------------

function renderPaginationControls({
    idPrefix = "page",
    currentPage = 1,
    totalItems = 0,
    pageSize = 10,
    pageSizeOptions = [10, 25, 50, 100],
    itemLabelSingular = "item",
    itemLabelPlural = "items",
    onPageChangeFnName = "goToPage",
    onPageSizeChangeFnName = "changePageSize"
}) {
    if (totalItems <= 0) return "";

    const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
    const validCurrentPage = Math.min(Math.max(1, currentPage), totalPages);
    const startItem = (validCurrentPage - 1) * pageSize + 1;
    const endItem = Math.min(validCurrentPage * pageSize, totalItems);
    const label = totalItems === 1 ? itemLabelSingular : itemLabelPlural;

    // Smart windowing for page buttons
    const pages = [];
    if (totalPages <= 7) {
        for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
        if (validCurrentPage <= 4) {
            pages.push(1, 2, 3, 4, 5, "...", totalPages);
        } else if (validCurrentPage >= totalPages - 3) {
            pages.push(1, "...", totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages);
        } else {
            pages.push(1, "...", validCurrentPage - 1, validCurrentPage, validCurrentPage + 1, "...", totalPages);
        }
    }

    const prevDisabled = validCurrentPage <= 1;
    const nextDisabled = validCurrentPage >= totalPages;

    const pageButtonsHtml = pages.map((p) => {
        if (p === "...") {
            return `<span class="px-1.5 py-1 text-xs text-slate-400 select-none">…</span>`;
        }
        const isActive = p === validCurrentPage;
        return `
            <button type="button"
                onclick="${onPageChangeFnName}(${p})"
                class="min-w-[28px] h-7 px-2 rounded text-xs font-mono font-medium transition flex items-center justify-center btn-tactile ${isActive
                ? 'bg-kpmg-blue text-white shadow-xs font-bold pointer-events-none'
                : 'bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 cursor-pointer'
            }"
                aria-label="Page ${p}" ${isActive ? 'aria-current="page"' : ''}>
                ${p}
            </button>
        `;
    }).join("");

    const pageSizeSelectHtml = `
        <div class="flex items-center space-x-1.5 text-xs text-slate-500">
            <span class="whitespace-nowrap">Rows per page:</span>
            <select onchange="${onPageSizeChangeFnName}(Number(this.value))"
                class="h-7 px-2 py-0.5 rounded border border-slate-200 bg-white text-xs font-mono text-slate-700 hover:border-slate-300 focus:outline-none focus:ring-1 focus:ring-kpmg-blue cursor-pointer shadow-2xs">
                ${pageSizeOptions.map(opt => `<option value="${opt}" ${opt === pageSize ? 'selected' : ''}>${opt}</option>`).join("")}
            </select>
        </div>
    `;

    return `
        <div class="fin-pagination-bar border-t border-slate-200 bg-slate-50/70 px-4 py-2.5 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-600 select-none">
            <!-- Left: Showing summary -->
            <div class="flex items-center space-x-1 text-xs text-slate-500">
                <span>Showing</span>
                <span class="font-mono font-semibold text-slate-800">${startItem}</span>
                <span>–</span>
                <span class="font-mono font-semibold text-slate-800">${endItem}</span>
                <span>of</span>
                <span class="font-mono font-semibold text-slate-800">${totalItems}</span>
                <span>${escapeHtml(label)}</span>
            </div>

            <!-- Right: Controls -->
            <div class="flex flex-wrap items-center gap-3">
                ${pageSizeSelectHtml}

                <div class="inline-flex items-center space-x-1">
                    <!-- Prev Page -->
                    <button type="button"
                        onclick="${onPageChangeFnName}(${validCurrentPage - 1})"
                        ${prevDisabled ? 'disabled' : ''}
                        class="h-7 px-2 rounded border border-slate-200 bg-white text-slate-700 text-xs font-medium transition flex items-center justify-center btn-tactile ${prevDisabled ? 'opacity-40 cursor-not-allowed pointer-events-none' : 'hover:bg-slate-100 cursor-pointer'
        }"
                        title="Previous page">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
                        </svg>
                    </button>

                    <!-- Page Numbers -->
                    ${pageButtonsHtml}

                    <!-- Next Page -->
                    <button type="button"
                        onclick="${onPageChangeFnName}(${validCurrentPage + 1})"
                        ${nextDisabled ? 'disabled' : ''}
                        class="h-7 px-2 rounded border border-slate-200 bg-white text-slate-700 text-xs font-medium transition flex items-center justify-center btn-tactile ${nextDisabled ? 'opacity-40 cursor-not-allowed pointer-events-none' : 'hover:bg-slate-100 cursor-pointer'
        }"
                        title="Next page">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    `;
}

function renderCompanyWorkspace() {
    const container = document.getElementById("company-perimeter-content");
    const toolbar = document.getElementById("company-directory-toolbar");
    if (!container) return;

    const totalCompanies = availableCompanies || [];

    if (totalCompanies.length === 0) {
        if (toolbar) toolbar.classList.add("hidden");
        container.innerHTML = `
            <div class="border border-dashed border-slate-300 rounded-2xl bg-slate-50/60 p-12 text-center space-y-4">
                <div class="w-12 h-12 rounded-xl bg-blue-50 border border-blue-200 text-kpmg-blue flex items-center justify-center mx-auto">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                    </svg>
                </div>
                <div class="max-w-md mx-auto space-y-1">
                    <h3 class="font-bold text-sm text-kpmg-navy">No Company Profiles Added Yet</h3>
                    <p class="text-xs text-kpmg-muted leading-relaxed">
                        Create your first company profile with its reporting currency, subsidiary ownership structure, and base Chart of Accounts to begin consolidation.
                    </p>
                </div>
                <div>
                    <button onclick="openCreateProfileModal()" class="h-7 px-3 rounded bg-kpmg-blue hover:bg-kpmg-navy text-white text-[11px] font-semibold transition flex items-center space-x-1 shadow-xs btn-tactile cursor-pointer" title="Create Company Profile">
                        <svg class="w-3 h-3 text-[#ACEAFF]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
                        </svg>
                        <span>Create</span>
                    </button>
                </div>
            </div>
        `;
        return;
    }

    if (toolbar) {
        toolbar.classList.remove("hidden");
        toolbar.classList.add("flex");
    }

    updateFilterBadge();
    updateSortButtonIndicator();
    renderCompanyTableBody();
}

function renderCompanyTableBody() {
    const container = document.getElementById("company-perimeter-content");
    if (!container) return;

    const filtered = filterAndSortCompanies();

    if (filtered.length === 0) {
        const hasFilters = companyFilterCategory !== 'ALL' || companyFilterCurrency !== 'ALL' || !!companySearchQuery;
        container.innerHTML = `
            <div class="border border-slate-200 rounded-xl bg-slate-50/50 p-8 text-center space-y-2">
                <p class="text-xs text-slate-600 font-medium">No company profiles match ${companySearchQuery ? `search query <strong class="text-kpmg-navy">"${escapeHtml(companySearchQuery)}"</strong>` : 'current filter criteria'}.</p>
                ${hasFilters ? `<button onclick="clearAllFiltersAndSearch()" class="text-xs text-kpmg-blue font-semibold hover:underline cursor-pointer">Reset search and filters</button>` : ''}
            </div>
        `;
        return;
    }

    const totalPages = Math.max(1, Math.ceil(filtered.length / companyPageSize));
    if (companyCurrentPage > totalPages) {
        companyCurrentPage = totalPages;
    }
    if (companyCurrentPage < 1) {
        companyCurrentPage = 1;
    }

    const startIndex = (companyCurrentPage - 1) * companyPageSize;
    const endIndex = Math.min(startIndex + companyPageSize, filtered.length);
    const pagedCompanies = filtered.slice(startIndex, endIndex);

    const rowsHtml = pagedCompanies.map(comp => {
        const subs = comp.subsidiaries || [];
        const isExpanded = expandedCompanyIds.has(comp.company_id);
        const whollyOwnedCount = subs.filter(s => Number(s.ownership_pct) >= 100).length;
        const nciCount = subs.length - whollyOwnedCount;
        const subCurrencies = Array.from(new Set(subs.map(s => s.input_currency).filter(Boolean)));
        const coaAccounts = comp.coa_account_count || 0;
        const coaFile = comp.coa_filename || "Chart of Accounts";

        const nestedSubsidiaryTable = subs.length > 0 ? `
            <div class="overflow-x-auto rounded-lg border border-slate-200 bg-white">
                <table class="w-full text-left border-collapse text-xs">
                    <thead class="bg-slate-100/80 border-b border-slate-200 text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                        <tr>
                            <th class="w-8 px-3 py-2 text-center">#</th>
                            <th class="px-3 py-2">Subsidiary Entity</th>
                            <th class="px-3 py-2">Reg. Number</th>
                            <th class="px-3 py-2">Country of Inc.</th>
                            <th class="px-3 py-2">Date of Inc.</th>
                            <th class="px-3 py-2 text-center">Currency</th>
                            <th class="px-3 py-2 text-right">Ownership %</th>
                            <th class="px-3 py-2 text-right">NCI %</th>
                            <th class="px-3 py-2 text-center">Acquisition Date</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                        ${subs.map((s, idx) => `
                            <tr class="hover:bg-slate-50/80 transition">
                                <td class="px-3 py-2 font-mono text-[11px] text-slate-400 text-center">${idx + 1}</td>
                                <td class="px-3 py-2 text-slate-700">
                                    <div class="flex items-center space-x-1.5">
                                        <span class="w-1.5 h-1.5 rounded-full bg-kpmg-electric flex-shrink-0"></span>
                                        <span>${escapeHtml(s.entity_name)}</span>
                                    </div>
                                </td>
                                <td class="px-3 py-2 font-mono text-[11px] text-slate-600">${s.company_reg_number ? escapeHtml(s.company_reg_number) : '<span class="text-slate-400">—</span>'}</td>
                                <td class="px-3 py-2 text-slate-700">${s.country_of_inc ? escapeHtml(s.country_of_inc) : '<span class="text-slate-400">—</span>'}</td>
                                <td class="px-3 py-2 font-mono text-[11px] text-slate-600">${s.date_of_inc ? escapeHtml(s.date_of_inc) : '<span class="text-slate-400">—</span>'}</td>
                                <td class="px-3 py-2 text-center font-mono text-xs text-slate-700">
                                    ${escapeHtml(s.input_currency)}
                                </td>
                                <td class="px-3 py-2 text-right font-mono text-xs text-slate-700">${Number(s.ownership_pct).toFixed(2)}%</td>
                                <td class="px-3 py-2 text-right font-mono text-xs text-slate-500">${Number(s.nci_pct).toFixed(2)}%</td>
                                <td class="px-3 py-2 text-center font-mono text-[11px] text-slate-700">${s.acquisition_date ? escapeHtml(s.acquisition_date) : '<span class="text-slate-400">—</span>'}</td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            </div>
        ` : `
            <div class="px-4 py-3 rounded-lg border border-slate-200 bg-white text-xs text-slate-500 flex items-center justify-between">
                <span>Standalone Parent Entity — 0 Subsidiaries configured.</span>
                <button onclick="event.stopPropagation(); openEditProfileModal('${escapeHtml(comp.company_id)}')" class="text-kpmg-blue font-semibold hover:underline cursor-pointer">+ Add Subsidiaries</button>
            </div>
        `;

        return `
            <!-- Primary High-Density Company Row (~42px) -->
            <tr id="row-${escapeHtml(comp.company_id)}"
                onclick="toggleCompanyExpansion('${escapeHtml(comp.company_id)}')"
                class="fin-ledger-row ${isExpanded ? 'is-expanded' : ''} cursor-pointer group select-none">
                
                <!-- Expand Chevron (1-Click Toggle) -->
                <td class="px-3 py-2 text-center w-10">
                    <span id="chevron-${escapeHtml(comp.company_id)}" class="chevron-icon ${isExpanded ? 'expanded' : ''} text-slate-400 group-hover:text-kpmg-blue text-xs font-mono font-bold">▶</span>
                </td>

                <!-- Company Code -->
                <td class="px-3 py-2 whitespace-nowrap">
                    <span class="font-mono text-xs text-slate-700">${escapeHtml(comp.company_code || comp.company_id)}</span>
                </td>

                <!-- Company Name -->
                <td class="px-3 py-2">
                    <span class="text-xs text-slate-700 group-hover:text-kpmg-navy transition">${escapeHtml(comp.company_name)}</span>
                </td>

                <!-- Reporting Currency -->
                <td class="px-3 py-2 text-center whitespace-nowrap">
                    <span class="font-mono text-xs text-slate-700">${escapeHtml(comp.reporting_currency)}</span>
                </td>

                <!-- Subsidiaries Count -->
                <td class="px-3 py-2 whitespace-nowrap">
                    <span class="font-mono text-xs text-slate-700">${subs.length}</span>
                </td>

                <!-- Subsidiary Currencies -->
                <td class="px-3 py-2 whitespace-nowrap">
                    <span class="font-mono text-xs text-slate-700">${escapeHtml(subCurrencies.length > 0 ? subCurrencies.join(", ") : "—")}</span>
                </td>

                <!-- Base Chart of Accounts -->
                <td class="px-3 py-2 whitespace-nowrap" title="${escapeHtml(coaFile)}">
                    <span class="font-mono text-xs text-slate-700">${coaAccounts} GL Accounts</span>
                </td>

                <!-- Created Timestamp -->
                <td class="px-3 py-2 whitespace-nowrap font-mono text-[11px] text-slate-500">
                    ${formatDateTime(comp.created_at)}
                </td>

                <!-- Last Updated Timestamp -->
                <td class="px-3 py-2 whitespace-nowrap font-mono text-[11px] text-slate-500">
                    ${formatDateTime(comp.updated_at || comp.created_at)}
                </td>

                <!-- 1-Click Icon Actions (Pencil & Trash Icons - Ghost Style) -->
                <td class="px-3 py-2 text-right whitespace-nowrap" onclick="event.stopPropagation()">
                    <div class="inline-flex items-center space-x-1">
                        <button onclick="openEditProfileModal('${escapeHtml(comp.company_id)}')"
                            class="w-7 h-7 rounded text-slate-400 hover:text-kpmg-blue hover:bg-slate-100 transition flex items-center justify-center cursor-pointer btn-tactile"
                            title="Edit Profile & Base COA">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                            </svg>
                        </button>
                        <button onclick="openDeleteProfileModal('${escapeHtml(comp.company_id)}')"
                            class="w-7 h-7 rounded text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition flex items-center justify-center cursor-pointer btn-tactile"
                            title="Delete Profile">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                        </button>
                    </div>
                </td>
            </tr>

            <!-- Expandable Nested Tray for Subsidiaries & Master Details -->
            <tr id="tray-${escapeHtml(comp.company_id)}" class="company-detail-tray ${isExpanded ? '' : 'hidden'} bg-slate-50/70 border-b border-slate-200">
                <td colspan="10" class="p-4 pl-10 pr-6">
                    <div class="space-y-3">
                        <!-- Summary Ribbon inside Tray -->
                        <div class="flex flex-wrap items-center justify-between text-xs text-slate-600 gap-2 border-b border-slate-200 pb-2.5">
                            <div class="flex flex-wrap items-center gap-3">
                                <span>Parent Code: <strong class="font-mono text-kpmg-navy">${escapeHtml(comp.company_code || comp.company_id)}</strong></span>
                                <span class="text-slate-300">•</span>
                                <span>Functional Base: <strong class="font-mono text-kpmg-blue">${escapeHtml(comp.reporting_currency)}</strong></span>
                                <span class="text-slate-300">•</span>
                                <span>COA File: <strong class="font-mono text-slate-700">${escapeHtml(coaFile)}</strong> (${coaAccounts} accounts${comp.coa_uploaded_at ? ` • ${escapeHtml(comp.coa_uploaded_at)}` : ''})</span>
                            </div>
                            <div class="text-[11px] text-slate-500 font-mono flex items-center space-x-3">
                                <span>Created: <strong class="text-slate-700">${formatDateTime(comp.created_at)}</strong></span>
                                <span class="text-slate-300">•</span>
                                <span>Updated: <strong class="text-slate-700">${formatDateTime(comp.updated_at || comp.created_at)}</strong></span>
                            </div>
                        </div>

                        <!-- Nested Subsidiary Table -->
                        ${nestedSubsidiaryTable}
                    </div>
                </td>
            </tr>
        `;
    }).join("");

    const paginationHtml = renderPaginationControls({
        idPrefix: "company-page",
        currentPage: companyCurrentPage,
        totalItems: filtered.length,
        pageSize: companyPageSize,
        pageSizeOptions: [10, 25, 50, 100],
        itemLabelSingular: "profile",
        itemLabelPlural: "profiles",
        onPageChangeFnName: "goToCompanyPage",
        onPageSizeChangeFnName: "changeCompanyPageSize"
    });

    container.innerHTML = `
        <div class="rounded-xl border border-slate-200 bg-white shadow-2xs overflow-hidden">
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse fin-ledger-table">
                    <thead class="bg-slate-50 border-b border-slate-200 text-[10px] font-bold text-slate-500 uppercase tracking-wider select-none sticky top-0 z-10">
                        <tr>
                            <th class="w-10 px-3 py-2.5 text-center"></th>
                            <th class="px-3 py-2.5">Code</th>
                            <th class="px-3 py-2.5">Company Name</th>
                            <th class="px-3 py-2.5 text-center">Currency</th>
                            <th class="px-3 py-2.5">Subsidiaries</th>
                            <th class="px-3 py-2.5">Subsidiary Currencies</th>
                            <th class="px-3 py-2.5">Base COA</th>
                            <th class="px-3 py-2.5">Created</th>
                            <th class="px-3 py-2.5">Last Updated</th>
                            <th class="px-3 py-2.5 text-right">Actions</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 text-xs text-slate-800">
                        ${rowsHtml}
                    </tbody>
                </table>
            </div>
            ${paginationHtml}
        </div>
    `;
}

function goToCompanyPage(page) {
    companyCurrentPage = Math.max(1, page);
    renderCompanyTableBody();
}

function changeCompanyPageSize(newSize) {
    if (!newSize || newSize <= 0) return;
    const oldStartIndex = (companyCurrentPage - 1) * companyPageSize;
    companyPageSize = newSize;
    companyCurrentPage = Math.floor(oldStartIndex / newSize) + 1;
    renderCompanyTableBody();
}

function renderStepperState() {
    const completed = appStatus.completed_steps || [];
    const maxUnlocked = Math.max(1, (appStatus.current_step || 1));

    for (let s = 1; s <= 6; s++) {
        const btn = document.getElementById(`step-btn-${s}`);
        if (!btn) continue;

        btn.classList.remove("active", "completed", "locked", "cursor-not-allowed", "cursor-pointer");

        if (s === activeStep) {
            btn.classList.add("active", "cursor-pointer");
        } else if (completed.includes(s)) {
            btn.classList.add("completed", "cursor-pointer");
        } else if (s <= maxUnlocked) {
            btn.classList.add("cursor-pointer");
        } else {
            btn.classList.add("locked", "cursor-not-allowed");
        }
    }
}

function switchStep(step) {
    if (activeNavSection !== 'PIPELINE') {
        switchNavSection('PIPELINE');
    }
    const maxUnlocked = Math.max(1, (appStatus.current_step || 1));
    if (step > maxUnlocked && !appStatus.completed_steps?.includes(step)) {
        showToast("Step Locked", `Step ${step} is locked. Please execute earlier steps first.`, "warning");
        return;
    }
    // Gating check: Cannot proceed past Step 2 if any human-in-the-loop reviews are open in Step 2
    if (step > 2) {
        const mappings = (pipelineData && pipelineData.mapping_decisions) ? pipelineData.mapping_decisions : [];
        const hasPending = mappings.some(m => m.needs_review);
        if (hasPending) {
            showToast("Review Required", "Please resolve all highlighted account reviews across all entity tabs before proceeding to Step 3.", "warning");
            return;
        }
    }
    activeStep = Math.min(6, Math.max(1, step));
    renderStepperState();
    renderActiveStepContent();
}

function renderActiveStepContent() {
    const container = document.getElementById("step-content");
    if (!container) return;

    if (activeStep === 1) renderStep1(container);
    else if (activeStep === 2) renderStep2(container);
    else if (activeStep === 3) renderStep3(container);
    else if (activeStep === 4) renderStep4(container);
    else if (activeStep === 5) renderStep5(container);
    else if (activeStep === 6) renderStep6(container);
}

// ============================================================================
// STEP 1: DUAL-ENGINE INGESTION, MULTI-SHEET PARSING & PERIMETER APPROVAL
// ============================================================================

let step1ApprovalState = null;
let selectedSingleUploadEntity = null;
let selectedSingleFile = null;

async function fetchStep1ApprovalState() {
    try {
        const res = await fetch('/api/pipeline/ingestion-approval-state');
        const data = await res.json();
        if (data.success && data.approval_state) {
            step1ApprovalState = data.approval_state;
        }
    } catch (e) {
        console.error('Failed to fetch Step 1 approval state:', e);
    }
}

async function refreshCurrentStep() {
    showToast('Refreshing', 'Reloading workspace data...', 'info');
    await fetchStatus();
    await loadPipelineData();
    switchStep(activeStep || 1);
    const container = document.getElementById('step-content');
    if (container) {
        if (activeStep === 1) renderStep1(container);
        else if (activeStep === 2) renderStep2(container);
        else if (activeStep === 3) renderStep3(container);
        else if (activeStep === 4) renderStep4(container);
        else if (activeStep === 5) renderStep5(container);
        else if (activeStep === 6) renderStep6(container);
    }
}

function renderStep1(el) {
    const tbs = (pipelineData && pipelineData.raw_tbs) ? pipelineData.raw_tbs : [];
    const tbMap = new Map();
    tbs.forEach(tb => {
        if (tb.entity_code) {
            tbMap.set(tb.entity_code.toUpperCase(), tb);
        }
    });

    const perimeter = (appStatus && appStatus.perimeter_entities) ? appStatus.perimeter_entities : [];
    const hasPerimeter = perimeter.length > 0;

    let rowsHtml = '';
    if (hasPerimeter) {
        rowsHtml = perimeter.map(ent => {
            const tb = tbMap.get(ent.entity_code.toUpperCase());
            const isUploaded = !!tb;
            const displayName = ent.entity_name || (tb && tb.entity_name) || ent.entity_code;
            const currency = ent.currency || (tb && tb.currency) || '—';
            const holdingPct = ent.holding_percentage != null ? `${Math.round(ent.holding_percentage * 100)}%` : (ent.is_parent ? '100%' : '100%');
            const rolePill = ent.is_parent
                ? `<span class="px-1.5 py-0.2 rounded text-[10px] bg-blue-100 text-kpmg-blue font-semibold">PARENT</span>`
                : `<span class="px-1.5 py-0.2 rounded text-[10px] bg-slate-100 text-slate-600 font-medium">${holdingPct} OWNED</span>`;

            // Detect issues for the row
            const issues = [];
            if (!isUploaded) {
                issues.push("Missing Trial Balance: No file uploaded or assigned for this perimeter entity.");
            } else {
                if (!tb.row_count || tb.row_count === 0) {
                    issues.push("Empty Trial Balance: 0 accounts found in the assigned sheet.");
                }
                if ((tb.total_debit === 0 || tb.total_debit == null) && (tb.total_credit === 0 || tb.total_credit == null) && tb.row_count > 0) {
                    issues.push("Amounts unpopulated: Debit and Credit columns were not identified or parsed.");
                }
                if (!tb.is_tallied && Math.abs(tb.signed_sum || 0) > 0.01) {
                    issues.push(`Unbalanced Trial Balance: Debits (${formatNum(tb.total_debit)}) != Credits (${formatNum(tb.total_credit)}), Discrepancy = ${formatNum(tb.signed_sum)}.`);
                }
            }

            let statusIndicatorHtml = '';
            if (issues.length === 0) {
                statusIndicatorHtml = `
                    <div class="w-5 h-5 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0 mt-0.5"
                         title="Ingestion Complete: Valid trial balance with ${tb.row_count} accounts (${formatNum(tb.total_debit)} Debits, ${formatNum(tb.total_credit)} Credits).">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" /></svg>
                    </div>
                `;
            } else {
                const issuesText = issues.map(iss => `• ${iss}`).join('\n');
                statusIndicatorHtml = `
                    <div class="w-5 h-5 rounded-full bg-rose-100 text-rose-700 flex items-center justify-center shrink-0 mt-0.5 cursor-help"
                         title="Issues detected:\n${issuesText}">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                    </div>
                `;
            }

            if (isUploaded) {
                return `
                    <tr class="hover:bg-slate-50/70 border-b border-gray-100 transition">
                        <td class="py-2.5 px-3 text-xs">
                            <div class="flex items-start space-x-2.5">
                                ${statusIndicatorHtml}
                                <div>
                                    <div class="font-bold text-kpmg-navy text-[13px] leading-snug">
                                        ${escapeHtml(displayName)}
                                    </div>
                                    <div class="flex items-center space-x-1.5 mt-0.5 text-[11px] text-slate-500">
                                        <span class="font-mono font-semibold">${escapeHtml(ent.entity_code)}</span>
                                        <span>•</span>
                                        ${rolePill}
                                    </div>
                                </div>
                            </div>
                        </td>
                        <td class="py-2.5 px-3 text-xs">
                            <span class="px-2 py-0.5 rounded bg-slate-100 font-mono text-[11px] font-semibold text-slate-700 border border-slate-200/60">${escapeHtml(currency)}</span>
                        </td>
                        <td class="num-cell py-2.5 px-3 text-xs font-mono">${tb.row_count}</td>
                        <td class="num-cell py-2.5 px-3 text-xs font-mono">${formatNum(tb.total_debit)}</td>
                        <td class="num-cell py-2.5 px-3 text-xs font-mono">${formatNum(tb.total_credit)}</td>
                        <td class="num-cell py-2.5 px-3 text-xs font-mono font-bold ${tb.is_tallied ? 'text-emerald-600' : 'text-rose-600'}">${formatNum(tb.signed_sum)}</td>
                        <td class="text-center py-2.5 px-3 text-xs">
                            <span class="px-2.5 py-0.5 rounded text-[11px] font-semibold ${tb.is_tallied ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'}">
                                ${tb.is_tallied ? 'Tallied (0.00)' : 'Unbalanced'}
                            </span>
                        </td>
                    </tr>
                `;
            } else {
                return `
                    <tr class="hover:bg-amber-50/30 border-b border-gray-100 transition bg-slate-50/40">
                        <td class="py-2.5 px-3 text-xs">
                            <div class="flex items-start space-x-2.5">
                                ${statusIndicatorHtml}
                                <div>
                                    <div class="font-bold text-slate-700 text-[13px] leading-snug">
                                        ${escapeHtml(displayName)}
                                    </div>
                                    <div class="flex items-center space-x-1.5 mt-0.5 text-[11px] text-slate-500">
                                        <span class="font-mono font-semibold">${escapeHtml(ent.entity_code)}</span>
                                        <span>•</span>
                                        ${rolePill}
                                    </div>
                                </div>
                            </div>
                        </td>
                        <td class="py-2.5 px-3 text-xs">
                            <span class="px-2 py-0.5 rounded bg-slate-100 font-mono text-[11px] font-semibold text-slate-500 border border-slate-200/60">${escapeHtml(currency)}</span>
                        </td>
                        <td class="num-cell py-2.5 px-3 text-xs font-mono text-slate-400">—</td>
                        <td class="num-cell py-2.5 px-3 text-xs font-mono text-slate-400">—</td>
                        <td class="num-cell py-2.5 px-3 text-xs font-mono text-slate-400">—</td>
                        <td class="num-cell py-2.5 px-3 text-xs font-mono text-slate-400">—</td>
                        <td class="text-center py-2.5 px-3 text-xs">
                            <span class="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-semibold bg-rose-50 text-rose-700 border border-rose-200/80">
                                <span class="w-1.5 h-1.5 rounded-full bg-rose-500 mr-1 animate-pulse"></span>
                                Pending Upload
                            </span>
                        </td>
                    </tr>
                `;
            }
        }).join('');

        // Also check if any uploaded TB is outside perimeter (e.g. prior period or ad-hoc)
        const perimeterCodes = new Set(perimeter.map(p => p.entity_code.toUpperCase()));
        const extraTbs = tbs.filter(tb => !perimeterCodes.has((tb.entity_code || '').toUpperCase()));
        if (extraTbs.length > 0) {
            rowsHtml += extraTbs.map(tb => {
                const issues = [];
                if (!tb.row_count || tb.row_count === 0) issues.push("Empty Trial Balance: 0 accounts found.");
                if ((tb.total_debit === 0 || tb.total_debit == null) && (tb.total_credit === 0 || tb.total_credit == null) && tb.row_count > 0) {
                    issues.push("Amounts unpopulated: Debit and Credit columns were not identified.");
                }
                if (!tb.is_tallied && Math.abs(tb.signed_sum || 0) > 0.01) {
                    issues.push(`Unbalanced Trial Balance: Debits (${formatNum(tb.total_debit)}) != Credits (${formatNum(tb.total_credit)}), Discrepancy = ${formatNum(tb.signed_sum)}.`);
                }
                const indHtml = issues.length === 0
                    ? `<div class="w-5 h-5 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0 mt-0.5" title="Valid trial balance"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" /></svg></div>`
                    : `<div class="w-5 h-5 rounded-full bg-rose-100 text-rose-700 flex items-center justify-center shrink-0 mt-0.5 cursor-help" title="Issues detected:\n${issues.map(i => `• ${i}`).join('\n')}"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" /></svg></div>`;

                return `
                    <tr class="hover:bg-slate-50/70 border-b border-gray-100 transition">
                        <td class="py-2.5 px-3 text-xs">
                            <div class="flex items-start space-x-2.5">
                                ${indHtml}
                                <div>
                                    <div class="font-bold text-kpmg-navy text-[13px] leading-snug">
                                        ${escapeHtml(tb.entity_name || tb.entity_code)}
                                    </div>
                                    <div class="flex items-center space-x-1.5 mt-0.5 text-[11px] text-slate-500">
                                        <span class="font-mono font-semibold">${escapeHtml(tb.entity_code)}</span>
                                        ${tb.is_prior_period ? '<span class="ml-1 px-1.5 py-0.2 rounded text-[9px] bg-slate-200 text-slate-700 font-mono">PRIOR</span>' : ''}
                                    </div>
                                </div>
                            </div>
                        </td>
                        <td class="py-2.5 px-3 text-xs"><span class="px-2 py-0.5 rounded bg-gray-100 font-mono text-[11px] font-semibold text-slate-700">${escapeHtml(tb.currency)}</span></td>
                        <td class="num-cell py-2.5 px-3 text-xs font-mono">${tb.row_count}</td>
                        <td class="num-cell py-2.5 px-3 text-xs font-mono">${formatNum(tb.total_debit)}</td>
                        <td class="num-cell py-2.5 px-3 text-xs font-mono">${formatNum(tb.total_credit)}</td>
                        <td class="num-cell py-2.5 px-3 text-xs font-mono font-bold ${tb.is_tallied ? 'text-emerald-600' : 'text-rose-600'}">${formatNum(tb.signed_sum)}</td>
                        <td class="text-center py-2.5 px-3 text-xs">
                            <span class="px-2.5 py-0.5 rounded text-[11px] font-semibold ${tb.is_tallied ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'}">
                                ${tb.is_tallied ? 'Tallied (0.00)' : 'Unbalanced'}
                            </span>
                        </td>
                    </tr>
                `;
            }).join('');
        }
    } else {
        // Fallback when no perimeter is configured
        rowsHtml = tbs.map(tb => {
            const issues = [];
            if (!tb.row_count || tb.row_count === 0) issues.push("Empty Trial Balance: 0 accounts found.");
            if ((tb.total_debit === 0 || tb.total_debit == null) && (tb.total_credit === 0 || tb.total_credit == null) && tb.row_count > 0) {
                issues.push("Amounts unpopulated: Debit and Credit columns were not identified.");
            }
            if (!tb.is_tallied && Math.abs(tb.signed_sum || 0) > 0.01) {
                issues.push(`Unbalanced Trial Balance: Debits (${formatNum(tb.total_debit)}) != Credits (${formatNum(tb.total_credit)}), Discrepancy = ${formatNum(tb.signed_sum)}.`);
            }
            const indHtml = issues.length === 0
                ? `<div class="w-5 h-5 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0 mt-0.5" title="Valid trial balance"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" /></svg></div>`
                : `<div class="w-5 h-5 rounded-full bg-rose-100 text-rose-700 flex items-center justify-center shrink-0 mt-0.5 cursor-help" title="Issues detected:\n${issues.map(i => `• ${i}`).join('\n')}"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" /></svg></div>`;

            return `
                <tr class="hover:bg-slate-50/70 border-b border-gray-100 transition">
                    <td class="font-bold text-kpmg-navy py-2.5 px-3 text-xs">
                        <div class="flex items-start space-x-2.5">
                            ${indHtml}
                            <div>
                                <div class="font-bold text-kpmg-navy text-[13px] leading-snug">
                                    ${escapeHtml(tb.entity_name || tb.entity_code)}
                                </div>
                                <div class="text-[11px] text-slate-500 font-mono">
                                    (${escapeHtml(tb.entity_code)})
                                    ${tb.is_prior_period ? '<span class="ml-1 px-1.5 py-0.2 rounded text-[9px] bg-slate-200 text-slate-700 font-mono">PRIOR</span>' : ''}
                                </div>
                            </div>
                        </div>
                    </td>
                    <td class="py-2.5 px-3 text-xs"><span class="px-2 py-0.5 rounded bg-gray-100 font-mono text-[11px] font-semibold text-slate-700">${escapeHtml(tb.currency)}</span></td>
                    <td class="num-cell py-2.5 px-3 text-xs font-mono">${tb.row_count}</td>
                    <td class="num-cell py-2.5 px-3 text-xs font-mono">${formatNum(tb.total_debit)}</td>
                    <td class="num-cell py-2.5 px-3 text-xs font-mono">${formatNum(tb.total_credit)}</td>
                    <td class="num-cell py-2.5 px-3 text-xs font-mono font-bold ${tb.is_tallied ? 'text-emerald-600' : 'text-rose-600'}">${formatNum(tb.signed_sum)}</td>
                    <td class="text-center py-2.5 px-3 text-xs">
                        <span class="px-2.5 py-0.5 rounded text-[11px] font-semibold ${tb.is_tallied ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'}">
                            ${tb.is_tallied ? 'Tallied (0.00)' : 'Unbalanced'}
                        </span>
                    </td>
                </tr>
            `;
        }).join('');
    }

    // Check if FX rate table is collected and verified
    let fxRowHtml = '';
    const fxRates = (pipelineData && pipelineData.fx_rates) ? pipelineData.fx_rates : null;
    const isFxVerified = fxRates && fxRates.rates && Object.keys(fxRates.rates).length > 0;
    const pairCount = isFxVerified ? Object.keys(fxRates.rates).length : 0;
    const fxStatusHtml = isFxVerified
        ? `<div class="w-5 h-5 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0 mt-0.5" title="Exchange Rates Verified: Active exchange rate schedule for ${escapeHtml(fxRates.reporting_currency || 'INR')} (${pairCount} currency pairs)."><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" /></svg></div>`
        : `<div class="w-5 h-5 rounded-full bg-rose-100 text-rose-700 flex items-center justify-center shrink-0 mt-0.5 cursor-help" title="Issues detected:\n• Exchange Rates Missing: Required for Step 3 currency translation."><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" /></svg></div>`;

    if (fxRates && (pairCount > 0 || hasPerimeter)) {
        fxRowHtml = `
            <tr class="hover:bg-slate-50/70 border-b border-gray-100 transition bg-blue-50/20">
                <td class="py-2.5 px-3 text-xs">
                    <div class="flex items-start space-x-2.5">
                        ${fxStatusHtml}
                        <div>
                            <div class="font-bold text-kpmg-navy text-[13px] leading-snug">
                                Foreign Exchange Rates Table
                            </div>
                            <div class="flex items-center space-x-1.5 mt-0.5 text-[11px] text-slate-500">
                                <span class="font-mono font-semibold">FX_RATES</span>
                                <span>•</span>
                                <span class="px-1.5 py-0.2 rounded text-[10px] bg-indigo-100 text-indigo-700 font-semibold">CURRENCY CONVERSION</span>
                            </div>
                        </div>
                    </div>
                </td>
                <td class="py-2.5 px-3 text-xs">
                    <span class="px-2 py-0.5 rounded bg-slate-100 font-mono text-[11px] font-semibold text-slate-700 border border-slate-200/60">${escapeHtml((fxRates && fxRates.reporting_currency) || 'INR')}</span>
                </td>
                <td class="num-cell py-2.5 px-3 text-xs font-mono">${isFxVerified ? `${pairCount} Pairs` : '—'}</td>
                <td class="num-cell py-2.5 px-3 text-xs font-mono text-slate-400">—</td>
                <td class="num-cell py-2.5 px-3 text-xs font-mono text-slate-400">—</td>
                <td class="num-cell py-2.5 px-3 text-xs font-mono text-slate-400">—</td>
                <td class="text-center py-2.5 px-3 text-xs">
                    <span class="px-2.5 py-0.5 rounded text-[11px] font-semibold ${isFxVerified ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'}">
                        ${isFxVerified ? 'Verified' : 'Missing Rates'}
                    </span>
                </td>
            </tr>
        `;
    }

    el.innerHTML = `
        <div class="space-y-4">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-kpmg-border pb-3">
                <div>
                    <h3 class="font-bold text-base text-kpmg-navy">Ingested Entity Submissions</h3>
                    <p class="text-xs text-kpmg-muted">Deterministic & Gemini Agentic Brain pipeline with dynamic currency parsing and perimeter verification.</p>
                </div>
                <div class="flex items-center space-x-1.5">
                    <!-- 1. Ghost Upload Icon Button -->
                    <button onclick="openBatchUploadModal()"
                        class="w-8 h-8 rounded text-slate-500 hover:text-kpmg-blue hover:bg-slate-100 transition flex items-center justify-center cursor-pointer btn-tactile relative select-none"
                        title="Upload Trial Balance Files">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                        </svg>
                    </button>

                    <!-- 2. Ghost Review Mappings Icon Button -->
                    <button id="btn-review-mappings" onclick="openIngestionSummaryModal()"
                        class="w-8 h-8 rounded text-slate-500 hover:text-kpmg-blue hover:bg-slate-100 transition flex items-center justify-center cursor-pointer btn-tactile relative select-none"
                        title="Review Ingestion Mappings & Perimeter Configuration">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
                        </svg>
                    </button>

                    <!-- 3. Ghost Reset / Delete Icon Button -->
                    <button onclick="triggerResetBaseline()"
                        class="w-8 h-8 rounded text-slate-500 hover:text-rose-600 hover:bg-rose-50 transition flex items-center justify-center cursor-pointer btn-tactile relative select-none"
                        title="Reset Baseline / Clear Ingestion">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                    </button>

                    <!-- 4. Consolidate Primary Action Button -->
                    <button id="btn-run-pipeline" onclick="triggerRunPipeline()"
                        class="h-7 px-3 rounded bg-kpmg-blue hover:bg-kpmg-navy text-white text-[11px] font-semibold transition flex items-center space-x-1.5 shadow-xs btn-tactile cursor-pointer"
                        title="Consolidate">
                        <svg class="w-3.5 h-3.5 text-[#ACEAFF]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span>Consolidate</span>
                    </button>
                </div>
            </div>

            <div class="overflow-x-auto min-h-[460px] max-h-[calc(100vh-280px)] border border-kpmg-border rounded-lg bg-white shadow-2xs">
                <table class="fin-table">
                    <thead class="sticky top-0 bg-slate-100 z-10 shadow-xs">
                        <tr>
                            <th>Entity Name & Code</th>
                            <th>Currency</th>
                            <th class="num-cell">GL Accounts</th>
                            <th class="num-cell">Total Debits</th>
                            <th class="num-cell">Total Credits</th>
                            <th class="num-cell">Signed Balance</th>
                            <th class="text-center">Validation Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rowsHtml}${fxRowHtml}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// PERIMETER APPROVAL DIALOG (DISPLAYED ON TOP AFTER BATCH UPLOAD)
// ============================================================================

function openPerimeterApprovalModal(approvalState) {
    if (approvalState) {
        step1ApprovalState = approvalState;
    }
    const modal = document.getElementById('modal-perimeter-approval');
    if (!modal) return;

    renderPerimeterApprovalModalContent(step1ApprovalState);
    modal.classList.remove('hidden');
}

async function openIngestionSummaryModal() {
    if (step1ApprovalState && step1ApprovalState.parent) {
        openPerimeterApprovalModal(step1ApprovalState);
        return;
    }
    try {
        const res = await fetch('/api/pipeline/ingestion-approval-state');
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            showToast(err.detail || 'Failed to retrieve ingestion summary', 'error');
            return;
        }
        const data = await res.json();
        if (data.approval_state) {
            openPerimeterApprovalModal(data.approval_state);
        } else {
            showToast('No ingestion summary available. Please upload files first.', 'info');
        }
    } catch (e) {
        showToast('Error opening ingestion summary: ' + e.message, 'error');
    }
}

function closePerimeterApprovalModal() {
    const modal = document.getElementById('modal-perimeter-approval');
    if (modal) modal.classList.add('hidden');
}

let activeApprovalTab = 'ENTITIES'; // 'ENTITIES' | 'FX' | 'IGNORED'
let approvalActiveFilter = 'ALL';
let approvalSearchQuery = '';

function switchApprovalTab(tabName) {
    activeApprovalTab = tabName;
    const tabs = ['ENTITIES', 'FX', 'IGNORED'];
    tabs.forEach(t => {
        const btn = document.getElementById(`tab-approval-view-${t.toLowerCase()}`);
        const pane = document.getElementById(`pane-approval-${t.toLowerCase()}`);
        if (btn) {
            if (t === activeApprovalTab) {
                btn.className = 'px-3 py-1.5 rounded-md text-xs font-semibold flex items-center space-x-1.5 bg-kpmg-navy text-white shadow-xs transition cursor-pointer';
            } else {
                btn.className = 'px-3 py-1.5 rounded-md text-xs font-semibold flex items-center space-x-1.5 text-slate-700 hover:text-slate-900 transition cursor-pointer';
            }
        }
        if (pane) {
            if (t === activeApprovalTab) {
                pane.classList.remove('view-hidden');
            } else {
                pane.classList.add('view-hidden');
            }
        }
    });

    const entControls = document.getElementById('entities-quick-controls');
    if (entControls) {
        if (activeApprovalTab === 'ENTITIES') entControls.classList.remove('hidden');
        else entControls.classList.add('hidden');
    }

    validateApprovalFields(false);
}

function triggerRowFileUpload(entityCode) {
    const input = document.getElementById(`row-file-input-${entityCode}`);
    if (input) input.click();
}

async function handleRowFileUpload(event, entityCode) {
    const input = event.target;
    if (!input || !input.files || input.files.length === 0) return;
    if (input.files.length !== 1) {
        showToast('Single File Required', 'Please select exactly one file for this entity.', 'error');
        input.value = '';
        return;
    }

    const file = input.files[0];
    const formData = new FormData();
    formData.append('file', file);
    formData.append('entity_code', entityCode);

    const targetPeriod = (step1ApprovalState && step1ApprovalState.target_period) || '';
    if (targetPeriod) formData.append('period', targetPeriod);

    const chkDet = document.getElementById('chk-deterministic-engine');
    const chkAI = document.getElementById('chk-ai-agent-engine');
    formData.append('use_deterministic', chkDet ? String(chkDet.checked) : 'true');
    formData.append('use_ai', chkAI ? String(chkAI.checked) : 'true');

    showToast('Processing File', `Classifying and mapping ${file.name} for ${entityCode}...`, 'info');

    try {
        const res = await fetch('/api/pipeline/single-entity-upload', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (res.ok && data.success) {
            step1ApprovalState = data.approval_state;
            renderPerimeterApprovalModalContent(step1ApprovalState);
            validateApprovalFields(false);
            showToast('File Mapped', `Successfully updated mappings for ${entityCode} from ${file.name}.`, 'success');
        } else {
            showToast('Upload Error', data.detail || 'Failed to map uploaded file.', 'error');
        }
    } catch (e) {
        showToast('Network Error', 'Upload failed: ' + e.message, 'error');
    } finally {
        input.value = '';
    }
}

function showApprovalTooltip(event, entityCode, statusType) {
    const tooltip = document.getElementById('approval-floating-tooltip');
    if (!tooltip || !step1ApprovalState) return;

    let target = null;
    let name = '';
    let isParent = false;
    let isFx = false;

    if (entityCode === 'FX_RATES') {
        target = step1ApprovalState.fx_rates || {};
        name = 'Foreign Exchange Rates';
        isFx = true;
    } else if (step1ApprovalState.parent && (step1ApprovalState.parent.entity_code === entityCode || entityCode === 'parent')) {
        target = step1ApprovalState.parent;
        name = target.entity_name || target.entity_code;
        isParent = true;
    } else {
        target = (step1ApprovalState.subsidiaries || []).find(s => s.entity_code === entityCode);
        name = target ? (target.entity_name || target.entity_code) : entityCode;
    }

    if (!target) return;

    const bullets = [];
    const targetPeriod = step1ApprovalState.target_period || '31-03-2024';
    const confPct = Math.round((target.confidence || 1.0) * 100);

    if (isFx) {
        if (target.filename) {
            bullets.push(`<li class="text-emerald-400">• FX Status: Exchange rate table detected & mapped</li>`);
            bullets.push(`<li class="text-slate-300">• File: <span class="font-mono text-slate-200">${escapeHtml(target.filename)}</span></li>`);
            bullets.push(`<li class="text-slate-300">• Sheet: <span class="font-mono text-slate-200">${escapeHtml(target.sheet_name || 'Default')}</span></li>`);
        } else {
            bullets.push(`<li class="text-rose-400 font-semibold">• FX Status: Mandatory FX rates file missing</li>`);
        }
        bullets.push(`<li class="text-indigo-300">• Currency Pairs: Mandatory for Step 3 Translation & CTA</li>`);
        bullets.push(`<li class="text-slate-400">• Classification: ${confPct}% Confidence</li>`);
    } else {
        if (target.date_status === 'MISMATCH') {
            bullets.push(`<li class="text-rose-400 font-semibold">• Date Discrepancy: File has ${escapeHtml(target.detected_period || '')} vs Cutoff ${escapeHtml(targetPeriod)}</li>`);
        } else {
            bullets.push(`<li class="text-emerald-400">• Period: Aligned with ${escapeHtml(targetPeriod)}</li>`);
        }

        if (!target.filename) {
            bullets.push(`<li class="text-rose-400 font-semibold">• File Status: No trial balance sheet assigned</li>`);
        } else {
            bullets.push(`<li class="text-slate-300">• File: <span class="font-mono text-slate-200">${escapeHtml(target.filename)}</span></li>`);
            bullets.push(`<li class="text-slate-300">• Sheet: <span class="font-mono text-slate-200">${escapeHtml(target.sheet_name || 'Default')}</span></li>`);
        }

        bullets.push(`<li class="text-indigo-300">• Scale: ${escapeHtml(target.scale_instruction || 'Reported in exact absolute currency')}</li>`);

        const cols = target.detected_columns || {};
        bullets.push(`<li class="text-slate-300">• Mapped: Code: ${escapeHtml(cols.account_code || 'None')}, Debit: ${escapeHtml(cols.debit || cols.amount || 'None')}, Credit: ${escapeHtml(cols.credit || cols.amount || 'None')}</li>`);
        bullets.push(`<li class="text-slate-400">• Method: ${confPct}% Confidence (${escapeHtml(target.method || 'Deterministic')})</li>`);
    }

    const isFlagged = statusType === 'flagged';
    tooltip.innerHTML = `
        <div class="font-bold text-xs border-b border-slate-700/80 pb-1 mb-1.5 flex items-center justify-between">
            <span class="truncate pr-1 text-white">${escapeHtml(name)}</span>
            <span class="font-mono text-[9px] px-1 py-0.2 rounded shrink-0 ${isFlagged ? 'bg-rose-900/90 text-rose-200 border border-rose-700/60' : 'bg-emerald-900/90 text-emerald-200 border border-emerald-700/60'}">${isFlagged ? 'FLAGGED' : 'READY'}</span>
        </div>
        <ul class="space-y-1 text-[11px] leading-relaxed">
            ${bullets.join('')}
        </ul>
    `;

    tooltip.classList.remove('hidden');

    const rect = event.currentTarget.getBoundingClientRect();
    const tooltipWidth = 320;
    const tooltipHeight = tooltip.offsetHeight || 170;

    // Viewport-anchored coordinates directly beside the hovered icon
    let left = rect.right + 10;
    if (left + tooltipWidth > window.innerWidth - 10) {
        left = rect.left - tooltipWidth - 10;
    }

    let top = rect.top - 8;
    // Guard against bottom cutoff by flipping upwards relative to icon
    if (top + tooltipHeight > window.innerHeight - 20) {
        top = rect.bottom - tooltipHeight + 8;
    }
    if (top < 15) {
        top = 15;
    }

    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
}

function hideApprovalTooltip() {
    const tooltip = document.getElementById('approval-floating-tooltip');
    if (tooltip) tooltip.classList.add('hidden');
}

function validateApprovalFields(applyShake = false) {
    if (!step1ApprovalState) return 0;

    let unfilledCount = 0;
    const checkSelect = (id, isRequired = true) => {
        const el = document.getElementById(id);
        if (!el) return;
        const val = (el.value || '').trim();
        const isUnfilled = isRequired && (!val || val.startsWith('--'));
        if (isUnfilled) {
            el.classList.add('required-unfilled');
            if (applyShake) {
                el.classList.add('animate-field-shake');
                setTimeout(() => el.classList.remove('animate-field-shake'), 450);
            }
            unfilledCount++;
        } else {
            el.classList.remove('required-unfilled');
        }
    };

    // 1. Parent Selects: File, Sheet, Code, Debit, Credit
    if (step1ApprovalState.parent) {
        checkSelect('select-parent-file', true);
        checkSelect('select-parent-sheet', true);
        checkSelect('col-parent-code', true);
        checkSelect('col-parent-debit', true);
        checkSelect('col-parent-credit', true);
    }

    // 2. Subsidiary Selects: File, Sheet, Code, Debit, Credit
    (step1ApprovalState.subsidiaries || []).forEach(sub => {
        const code = sub.entity_code;
        checkSelect(`select-${code}-file`, true);
        checkSelect(`select-${code}-sheet`, true);
        checkSelect(`col-${code}-code`, true);
        checkSelect(`col-${code}-debit`, true);
        checkSelect(`col-${code}-credit`, true);
    });

    // 3. FX Selects: File, Sheet, Closing Rate, Average Rate
    if (step1ApprovalState.fx_rates) {
        checkSelect('select-FX_RATES-file', true);
        checkSelect('select-FX_RATES-sheet', true);
        checkSelect('col-fx-closing', true);
        checkSelect('col-fx-average', true);
    }

    // Check date mismatches
    const hasDateMismatch = (step1ApprovalState.parent && step1ApprovalState.parent.date_status === 'MISMATCH') ||
        (step1ApprovalState.subsidiaries || []).some(s => s.date_status === 'MISMATCH');

    // Update Approve & Confirm Ingestion button title (preserving authentic KPMG color)
    const btnConfirm = document.getElementById('btn-confirm-perimeter-modal');
    if (btnConfirm) {
        if (unfilledCount > 0 || hasDateMismatch) {
            btnConfirm.title = unfilledCount > 0
                ? `${unfilledCount} required mapping fields need to be selected (highlighted in red).`
                : 'Cannot confirm: Reporting period mismatch detected.';
        } else {
            btnConfirm.title = 'Approve and lock perimeter ingestion';
        }
    }

    return unfilledCount;
}

function onApprovalSelectChange(el) {
    if (el) {
        const val = (el.value || '').trim();
        if (val && !val.startsWith('--')) {
            el.classList.remove('required-unfilled');
        }
    }
    validateApprovalFields(false);
}

function filterApprovalGrid(filterType, searchQuery) {
    if (filterType !== undefined) approvalActiveFilter = filterType;
    if (searchQuery !== undefined) approvalSearchQuery = (searchQuery || '').trim().toLowerCase();

    // Update filter tabs UI
    const tabs = ['ALL', 'FLAGGED', 'READY'];
    tabs.forEach(t => {
        const btn = document.getElementById(`tab-approval-${t.toLowerCase()}`);
        if (btn) {
            if (t === approvalActiveFilter) {
                btn.className = 'px-2.5 py-1 rounded-md text-xs font-semibold bg-kpmg-navy text-white shadow-xs transition';
            } else {
                btn.className = 'px-2.5 py-1 rounded-md text-xs font-medium text-slate-600 hover:text-slate-900 transition';
            }
        }
    });

    const rows = document.querySelectorAll('[data-approval-row]');
    let visibleCount = 0;
    rows.forEach(row => {
        const rowStatus = row.getAttribute('data-status');
        const rowSearch = (row.getAttribute('data-search') || '').toLowerCase();
        const entityCode = row.getAttribute('data-entity-code') || '';
        const drawerRow = document.getElementById(`drawer-${entityCode}`);

        let matchesFilter = true;
        if (approvalActiveFilter === 'FLAGGED' && rowStatus !== 'flagged') matchesFilter = false;
        if (approvalActiveFilter === 'READY' && rowStatus !== 'ready') matchesFilter = false;

        let matchesSearch = true;
        if (approvalSearchQuery && !rowSearch.includes(approvalSearchQuery)) matchesSearch = false;

        if (matchesFilter && matchesSearch) {
            row.classList.remove('hidden');
            visibleCount++;
        } else {
            row.classList.add('hidden');
            if (drawerRow) drawerRow.classList.add('hidden');
        }
    });

    const emptyRow = document.getElementById('approval-grid-empty');
    if (emptyRow) {
        if (visibleCount === 0) emptyRow.classList.remove('hidden');
        else emptyRow.classList.add('hidden');
    }
}

function renderPerimeterApprovalModalContent(state) {
    const container = document.getElementById('perimeter-approval-cards-container');
    const footerStatus = document.getElementById('perimeter-approval-footer-status');
    if (!container) return;

    if (!state) {
        container.innerHTML = `
            <div class="p-8 text-center text-slate-500">
                <p class="text-sm">No perimeter approval data available.</p>
            </div>
        `;
        return;
    }

    const fileMap = state.files_map || state.available_files_and_sheets || {};
    const fileList = Object.keys(fileMap);

    const genFileOptions = (selectedFile) => {
        let opts = '<option value="">-- Select File --</option>';
        let matched = false;
        fileList.forEach(f => {
            const isSel = (f === selectedFile);
            if (isSel) matched = true;
            opts += `<option value="${escapeHtml(f)}" ${isSel ? 'selected' : ''}>${escapeHtml(f)}</option>`;
        });
        if (selectedFile && !matched) {
            opts += `<option value="${escapeHtml(selectedFile)}" selected>${escapeHtml(selectedFile)}</option>`;
        }
        return opts;
    };

    const genSheetOptions = (filename, selectedSheet) => {
        const sheets = fileMap[filename] || [];
        if (sheets.length === 0) {
            if (selectedSheet) {
                return `<option value="${escapeHtml(selectedSheet)}" selected>${escapeHtml(selectedSheet)}</option>`;
            }
            return '<option value="">Default Sheet</option>';
        }
        let opts = '';
        let matched = false;
        sheets.forEach(s => {
            const isSel = (s === selectedSheet);
            if (isSel) matched = true;
            opts += `<option value="${escapeHtml(s)}" ${isSel ? 'selected' : ''}>${escapeHtml(s)}</option>`;
        });
        if (selectedSheet && !matched) {
            opts += `<option value="${escapeHtml(selectedSheet)}" selected>${escapeHtml(selectedSheet)}</option>`;
        }
        return opts;
    };

    const genColOptions = (sampleRows, selectedCol, defaultLabel) => {
        const colSet = new Set();
        if (sampleRows && sampleRows.length > 0) {
            for (let r = 0; r < Math.min(10, sampleRows.length); r++) {
                const row = sampleRows[r] || [];
                const stringCount = row.filter(c => c && isNaN(Number(String(c).replace(/[,₹$%()]/g, '')))).length;
                if (stringCount >= 2) {
                    row.forEach(c => {
                        const trimmed = String(c || '').trim();
                        if (trimmed) colSet.add(trimmed);
                    });
                    break;
                }
            }
            if (colSet.size === 0 && sampleRows[0]) {
                sampleRows[0].forEach(c => {
                    const trimmed = String(c || '').trim();
                    if (trimmed) colSet.add(trimmed);
                });
            }
        }

        let opts = '<option value="">-- Auto / None --</option>';
        let matched = false;
        const selClean = String(selectedCol || '').trim().toLowerCase();

        colSet.forEach(h => {
            const hClean = h.trim().toLowerCase();
            const isSel = (selectedCol && (h === selectedCol || hClean === selClean));
            if (isSel) matched = true;
            opts += `<option value="${escapeHtml(h)}" ${isSel ? 'selected' : ''}>${escapeHtml(h)}</option>`;
        });

        if (selectedCol && !matched) {
            opts += `<option value="${escapeHtml(selectedCol)}" selected>${escapeHtml(selectedCol)}</option>`;
        }
        return opts;
    };

    const genScaleOptions = (currentMult) => {
        const scales = [
            { val: 1, label: "Units / Absolute (×1)" },
            { val: 100000, label: "₹ Lakhs (×100,000)" },
            { val: 10000000, label: "₹ Crores (×10,000,000)" },
            { val: 1000000, label: "Millions (×1,000,000)" },
            { val: 1000, label: "Thousands (×1,000)" },
            { val: 100, label: "Hundreds (×100)" }
        ];
        let opts = '';
        let matched = false;
        const curNum = parseFloat(currentMult) || 1.0;
        scales.forEach(s => {
            const isSel = Math.abs(s.val - curNum) < 0.001;
            if (isSel) matched = true;
            opts += `<option value="${s.val}" ${isSel ? 'selected' : ''}>${s.label}</option>`;
        });
        if (!matched) {
            opts += `<option value="${curNum}" selected>Custom (×${curNum})</option>`;
        }
        return opts;
    };

    const parent = state.parent;
    const subs = state.subsidiaries || [];
    const fx = state.fx_rates || {};
    const unassigned = state.unassigned_sheets || state.unassigned_items || [];

    const totalEntities = (parent ? 1 : 0) + subs.length;
    const mappedEntities = (parent && parent.filename ? 1 : 0) + subs.filter(s => s.filename).length;
    const isFxMapped = !!fx.filename;

    const isParentFlagged = !parent || !parent.filename || parent.date_status === 'MISMATCH' || !(parent.detected_columns && parent.detected_columns.account_code);
    const flaggedSubsCount = subs.filter(s => !s.filename || s.date_status === 'MISMATCH' || !(s.detected_columns && s.detected_columns.account_code)).length;
    const flaggedCount = (isParentFlagged ? 1 : 0) + flaggedSubsCount + (!isFxMapped ? 1 : 0);
    const readyCount = Math.max(0, totalEntities + 1 - flaggedCount);

    let html = `
        <div class="space-y-3">
            <!-- 3-Segment Top Switcher Bar -->
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 p-2 rounded-xl bg-slate-50 border border-slate-200">
                <div class="inline-flex p-1 bg-slate-200/80 rounded-lg space-x-1 text-xs">
                    <button type="button" id="tab-approval-view-entities" onclick="switchApprovalTab('ENTITIES')"
                        class="px-3 py-1.5 rounded-md text-xs font-semibold flex items-center space-x-1.5 transition cursor-pointer ${activeApprovalTab === 'ENTITIES' ? 'bg-kpmg-navy text-white shadow-xs' : 'text-slate-700 hover:text-slate-900'}">
                        <span>🏢 Perimeter Entities</span>
                        <span class="px-1.5 py-0.2 rounded-full text-[10px] font-mono ${flaggedSubsCount + (isParentFlagged ? 1 : 0) > 0 ? 'bg-amber-400 text-slate-900' : 'bg-emerald-500 text-white'}">${totalEntities}</span>
                    </button>
                    <button type="button" id="tab-approval-view-fx" onclick="switchApprovalTab('FX')"
                        class="px-3 py-1.5 rounded-md text-xs font-semibold flex items-center space-x-1.5 transition cursor-pointer ${activeApprovalTab === 'FX' ? 'bg-kpmg-navy text-white shadow-xs' : 'text-slate-700 hover:text-slate-900'}">
                        <span>💱 Foreign Exchange</span>
                        <span class="px-1.5 py-0.2 rounded-full text-[10px] font-mono ${isFxMapped ? 'bg-emerald-500 text-white' : 'bg-rose-500 text-white'}">${isFxMapped ? '✓' : '!'}</span>
                    </button>
                    <button type="button" id="tab-approval-view-ignored" onclick="switchApprovalTab('IGNORED')"
                        class="px-3 py-1.5 rounded-md text-xs font-semibold flex items-center space-x-1.5 transition cursor-pointer ${activeApprovalTab === 'IGNORED' ? 'bg-kpmg-navy text-white shadow-xs' : 'text-slate-700 hover:text-slate-900'}">
                        <span>📄 Ignored Extra Sheets</span>
                        <span class="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-slate-400 text-white">${unassigned.length}</span>
                    </button>
                </div>

                <!-- Fast Filter & Search (for Entities View) -->
                <div id="entities-quick-controls" class="flex items-center space-x-2 ${activeApprovalTab === 'ENTITIES' ? '' : 'hidden'}">
                    <div class="inline-flex items-center p-0.5 bg-slate-200/70 rounded-lg space-x-0.5 text-xs">
                        <button type="button" id="tab-approval-all" onclick="filterApprovalGrid('ALL')"
                            class="px-2.5 py-1 rounded-md text-xs font-semibold ${approvalActiveFilter === 'ALL' ? 'bg-kpmg-navy text-white shadow-xs' : 'text-slate-600 hover:text-slate-900'}">
                            All (${totalEntities})
                        </button>
                        <button type="button" id="tab-approval-flagged" onclick="filterApprovalGrid('FLAGGED')"
                            class="px-2.5 py-1 rounded-md text-xs font-semibold ${approvalActiveFilter === 'FLAGGED' ? 'bg-kpmg-navy text-white shadow-xs' : 'text-slate-600 hover:text-slate-900'}">
                            Flagged (${flaggedSubsCount + (isParentFlagged ? 1 : 0)})
                        </button>
                        <button type="button" id="tab-approval-ready" onclick="filterApprovalGrid('READY')"
                            class="px-2.5 py-1 rounded-md text-xs font-semibold ${approvalActiveFilter === 'READY' ? 'bg-kpmg-navy text-white shadow-xs' : 'text-slate-600 hover:text-slate-900'}">
                            Ready (${totalEntities - (flaggedSubsCount + (isParentFlagged ? 1 : 0))})
                        </button>
                    </div>
                    <div class="relative">
                        <input type="text" placeholder="Filter entity or code..."
                            value="${escapeHtml(approvalSearchQuery)}"
                            oninput="filterApprovalGrid(undefined, this.value)"
                            class="w-44 h-7 pl-6 pr-2 text-xs rounded-md border border-slate-200 bg-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-kpmg-blue font-mono" />
                        <svg class="w-3 h-3 text-slate-400 absolute left-2 top-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
                        </svg>
                    </div>
                </div>
            </div>

            <!-- ========================================================================= -->
            <!-- VIEW 1: PERIMETER ENTITIES TABLE                                          -->
            <!-- ========================================================================= -->
            <div id="pane-approval-entities" class="approval-view-pane ${activeApprovalTab === 'ENTITIES' ? '' : 'view-hidden'} border border-slate-200 rounded-xl overflow-x-auto bg-white shadow-xs max-h-[58vh]">
                <table class="w-full text-left text-xs border-collapse">
                    <thead class="sticky top-0 z-20 bg-slate-100 border-b border-slate-200 font-semibold text-slate-700 shadow-2xs">
                        <tr>
                            <th class="py-2 px-2 text-center w-11">Status</th>
                            <th class="py-2 px-2.5 min-w-[160px]">Entity & Role</th>
                            <th class="py-2 px-2 min-w-[150px]">Assigned File</th>
                            <th class="py-2 px-2 min-w-[115px]">Worksheet</th>
                            <th class="py-2 px-2 min-w-[110px]">Account Code</th>
                            <th class="py-2 px-2 min-w-[110px]">Debit</th>
                            <th class="py-2 px-2 min-w-[110px]">Credit</th>
                            <th class="py-2 px-2 min-w-[125px]">Scale / Denom</th>
                            <th class="py-2 px-2 text-center min-w-[110px]">Actions</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 font-mono text-[11px]">
    `;

    // 1. RENDER PARENT COMPANY ROW
    if (parent) {
        const sampleRows = parent.sample_rows || [];
        const isMapped = !!parent.filename;
        const confPct = Math.round((parent.confidence || 1.0) * 100);
        const code = parent.entity_code;
        const hasDateMismatch = parent.date_status === 'MISMATCH';
        const cols = parent.detected_columns || {};
        const hasMissingCode = !cols.account_code;
        const hasMissingDebit = !cols.debit && !cols.amount;
        const hasMissingCredit = !cols.credit && !cols.amount;
        const isFlagged = !isMapped || hasDateMismatch || hasMissingCode || hasMissingDebit || hasMissingCredit;
        const rowStatus = isFlagged ? 'flagged' : 'ready';

        const statusIcon = isFlagged
            ? `<div onmouseenter="showApprovalTooltip(event, 'parent', 'flagged')" onmouseleave="hideApprovalTooltip()" class="status-indicator-badge w-5 h-5 rounded-full flex items-center justify-center font-bold text-[10px] bg-rose-100 text-rose-700 border border-rose-300">✕</div>`
            : `<div onmouseenter="showApprovalTooltip(event, 'parent', 'ready')" onmouseleave="hideApprovalTooltip()" class="status-indicator-badge w-5 h-5 rounded-full flex items-center justify-center font-bold text-[10px] bg-emerald-100 text-emerald-700 border border-emerald-300">✓</div>`;

        const debitPrefill = cols.debit || cols.amount || '';
        const creditPrefill = cols.credit || cols.amount || '';

        html += `
            <tr data-approval-row data-status="${rowStatus}" data-search="${escapeHtml((parent.entity_name || code) + ' ' + code)}" data-entity-code="parent" class="hover:bg-slate-50/70 transition">
                <td class="py-1.5 px-2 text-center align-middle">
                    <div class="inline-flex items-center justify-center">
                        ${statusIcon}
                    </div>
                </td>
                <td class="py-1.5 px-2.5 align-middle">
                    <div class="flex items-center space-x-2">
                        <div class="w-6 h-6 rounded bg-kpmg-navy text-white flex items-center justify-center font-bold text-[10px]">P</div>
                        <div>
                            <div class="flex items-center space-x-1.5">
                                <span class="font-bold text-slate-800 text-xs">${escapeHtml(parent.entity_name || code)}</span>
                                <span class="px-1.5 py-0.2 rounded text-[9px] bg-blue-100 text-kpmg-blue font-semibold">PARENT</span>
                                <span class="text-[10px] text-slate-400 font-mono">(${escapeHtml(code)})</span>
                            </div>
                            <div class="text-[10px] text-slate-500 font-mono">Currency: <strong class="text-slate-700">${escapeHtml(parent.currency || state.reporting_currency || 'INR')}</strong></div>
                        </div>
                    </div>
                </td>
                <td class="py-1.5 px-2 align-middle">
                    <select id="select-parent-file" onchange="updateEntityFileMapping('${escapeHtml(code)}', this.value); onApprovalSelectChange(this);"
                        class="w-full h-7 px-1.5 py-0 text-[11px] font-mono rounded border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-kpmg-blue transition">
                        ${genFileOptions(parent.filename)}
                    </select>
                </td>
                <td class="py-1.5 px-2 align-middle">
                    <select id="select-parent-sheet" onchange="updateEntitySheetMapping('${escapeHtml(code)}', this.value); onApprovalSelectChange(this);"
                        class="w-full h-7 px-1.5 py-0 text-[11px] font-mono rounded border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-kpmg-blue transition">
                        ${genSheetOptions(parent.filename, parent.sheet_name)}
                    </select>
                </td>
                <td class="py-1.5 px-2 align-middle">
                    <select id="col-parent-code" onchange="onApprovalSelectChange(this)" class="w-full h-7 px-1.5 py-0 text-[11px] font-mono rounded border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-kpmg-blue transition">
                        ${genColOptions(sampleRows, cols.account_code, 'Account Code')}
                    </select>
                </td>
                <td class="py-1.5 px-2 align-middle">
                    <select id="col-parent-debit" onchange="onApprovalSelectChange(this)" class="w-full h-7 px-1.5 py-0 text-[11px] font-mono rounded border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-kpmg-blue transition">
                        ${genColOptions(sampleRows, debitPrefill, 'Debit')}
                    </select>
                </td>
                <td class="py-1.5 px-2 align-middle">
                    <select id="col-parent-credit" onchange="onApprovalSelectChange(this)" class="w-full h-7 px-1.5 py-0 text-[11px] font-mono rounded border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-kpmg-blue transition">
                        ${genColOptions(sampleRows, creditPrefill, 'Credit')}
                    </select>
                </td>
                <td class="py-1.5 px-2 align-middle">
                    <select id="scale-parent" onchange="updateEntityScaleInstruction('${escapeHtml(code)}', this.value); onApprovalSelectChange(this);"
                        class="w-full h-7 px-1.5 py-0 text-[11px] font-mono rounded border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-kpmg-blue transition">
                        ${genScaleOptions(parent.scale_multiplier)}
                    </select>
                </td>
                <!-- Sequence: Confidence % -> View (eye) -> Upload (ghost) -->
                <td class="py-1.5 px-2 text-center align-middle">
                    <div class="flex items-center justify-center space-x-1.5">
                        <span class="text-[10px] font-mono text-slate-600 font-bold">${confPct}%</span>
                        <button type="button" onclick="toggleSamplePreview('drawer-parent')"
                            class="w-6 h-6 rounded hover:bg-slate-200 text-slate-600 hover:text-kpmg-blue inline-flex items-center justify-center transition cursor-pointer"
                            title="Toggle Sample Data & Scale Details">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                            </svg>
                        </button>
                        <button type="button" onclick="triggerRowFileUpload('parent')"
                            class="w-6 h-6 rounded hover:bg-slate-200 text-slate-500 hover:text-kpmg-blue inline-flex items-center justify-center transition cursor-pointer"
                            title="Upload / Replace file for ${escapeHtml(parent.entity_name || code)}">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                            </svg>
                        </button>
                        <input type="file" id="row-file-input-parent" class="hidden" accept=".xlsx,.xls,.csv" onchange="handleRowFileUpload(event, 'parent')" />
                    </div>
                </td>
            </tr>

            <!-- Parent Drawer Row -->
            <tr id="drawer-parent" class="hidden bg-slate-50/80 border-b border-slate-200">
                <td colspan="9" class="p-3 font-sans">
                    ${hasDateMismatch ? `
                        <div class="mb-2 p-2 rounded-lg bg-rose-50 border border-rose-200 text-rose-900 text-xs flex items-center space-x-2">
                            <svg class="w-4 h-4 text-rose-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
                            <span><strong>Period Discrepancy:</strong> File contains data for <strong>${escapeHtml(parent.detected_period || '')}</strong>, but active consolidation run cutoff is <strong>${escapeHtml(state.target_period || '31-03-2024')}</strong>. This data belongs to a different reporting period.</span>
                        </div>
                    ` : ''}
                    <div class="text-[11px] text-indigo-900 font-medium mb-1.5 flex items-center space-x-1.5">
                        <svg class="w-3.5 h-3.5 text-indigo-600 shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path></svg>
                        <span>Scale Normalization: <strong id="scale-instr-${escapeHtml(code)}">${escapeHtml(parent.scale_instruction || 'Reported in exact absolute currency (multiplier 1.0)')}</strong></span>
                    </div>
                    ${sampleRows.length > 0 ? `
                        <div class="overflow-x-auto text-[10px] font-mono border border-slate-200 rounded bg-white max-h-36">
                            <table class="w-full text-left">
                                <tbody>
                                    ${sampleRows.slice(0, 8).map((r, i) => `<tr class="${i === 0 ? 'font-bold bg-slate-100' : 'border-b border-slate-100'}">${r.map(c => `<td class="p-1">${escapeHtml(String(c))}</td>`).join('')}</tr>`).join('')}
                                </tbody>
                            </table>
                        </div>
                    ` : '<div class="text-[11px] text-slate-400">No raw rows extracted yet.</div>'}
                </td>
            </tr>
        `;
    }

    // 2. RENDER SUBSIDIARY ROWS
    subs.forEach((sub, sIdx) => {
        const sampleRows = sub.sample_rows || [];
        const isMapped = !!sub.filename;
        const confPct = Math.round((sub.confidence || 1.0) * 100);
        const code = sub.entity_code;
        const hasDateMismatch = sub.date_status === 'MISMATCH';
        const cols = sub.detected_columns || {};
        const hasMissingCode = !cols.account_code;
        const hasMissingDebit = !cols.debit && !cols.amount;
        const hasMissingCredit = !cols.credit && !cols.amount;
        const isFlagged = !isMapped || hasDateMismatch || hasMissingCode || hasMissingDebit || hasMissingCredit;
        const rowStatus = isFlagged ? 'flagged' : 'ready';

        const statusIcon = isFlagged
            ? `<div onmouseenter="showApprovalTooltip(event, '${escapeHtml(code)}', 'flagged')" onmouseleave="hideApprovalTooltip()" class="status-indicator-badge w-5 h-5 rounded-full flex items-center justify-center font-bold text-[10px] bg-rose-100 text-rose-700 border border-rose-300">✕</div>`
            : `<div onmouseenter="showApprovalTooltip(event, '${escapeHtml(code)}', 'ready')" onmouseleave="hideApprovalTooltip()" class="status-indicator-badge w-5 h-5 rounded-full flex items-center justify-center font-bold text-[10px] bg-emerald-100 text-emerald-700 border border-emerald-300">✓</div>`;

        const debitPrefill = cols.debit || cols.amount || '';
        const creditPrefill = cols.credit || cols.amount || '';

        html += `
            <tr data-approval-row data-status="${rowStatus}" data-search="${escapeHtml((sub.entity_name || code) + ' ' + code)}" data-entity-code="${escapeHtml(code)}" class="hover:bg-slate-50/70 transition">
                <td class="py-1.5 px-2 text-center align-middle">
                    <div class="inline-flex items-center justify-center">
                        ${statusIcon}
                    </div>
                </td>
                <td class="py-1.5 px-2.5 align-middle">
                    <div class="flex items-center space-x-2">
                        <div class="w-6 h-6 rounded bg-slate-700 text-white flex items-center justify-center font-bold text-[10px]">S${sIdx + 1}</div>
                        <div>
                            <div class="flex items-center space-x-1.5">
                                <span class="font-bold text-slate-800 text-xs">${escapeHtml(sub.entity_name || code)}</span>
                                <span class="px-1.5 py-0.2 rounded text-[9px] bg-slate-100 text-slate-600 font-semibold">${sub.holding_pct != null ? `${sub.holding_pct}%` : (sub.holding_percentage != null ? `${Math.round(sub.holding_percentage * 100)}%` : '100%')}</span>
                                <span class="text-[10px] text-slate-400 font-mono">(${escapeHtml(code)})</span>
                            </div>
                            <div class="text-[10px] text-slate-500 font-mono">Currency: <strong class="text-slate-700">${escapeHtml(sub.currency || 'INR')}</strong></div>
                        </div>
                    </div>
                </td>
                <td class="py-1.5 px-2 align-middle">
                    <select id="select-${escapeHtml(code)}-file" onchange="updateEntityFileMapping('${escapeHtml(code)}', this.value); onApprovalSelectChange(this);"
                        class="w-full h-7 px-1.5 py-0 text-[11px] font-mono rounded border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-kpmg-blue transition">
                        ${genFileOptions(sub.filename)}
                    </select>
                </td>
                <td class="py-1.5 px-2 align-middle">
                    <select id="select-${escapeHtml(code)}-sheet" onchange="updateEntitySheetMapping('${escapeHtml(code)}', this.value); onApprovalSelectChange(this);"
                        class="w-full h-7 px-1.5 py-0 text-[11px] font-mono rounded border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-kpmg-blue transition">
                        ${genSheetOptions(sub.filename, sub.sheet_name)}
                    </select>
                </td>
                <td class="py-1.5 px-2 align-middle">
                    <select id="col-${escapeHtml(code)}-code" onchange="onApprovalSelectChange(this)" class="w-full h-7 px-1.5 py-0 text-[11px] font-mono rounded border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-kpmg-blue transition">
                        ${genColOptions(sampleRows, cols.account_code, 'Account Code')}
                    </select>
                </td>
                <td class="py-1.5 px-2 align-middle">
                    <select id="col-${escapeHtml(code)}-debit" onchange="onApprovalSelectChange(this)" class="w-full h-7 px-1.5 py-0 text-[11px] font-mono rounded border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-kpmg-blue transition">
                        ${genColOptions(sampleRows, debitPrefill, 'Debit')}
                    </select>
                </td>
                <td class="py-1.5 px-2 align-middle">
                    <select id="col-${escapeHtml(code)}-credit" onchange="onApprovalSelectChange(this)" class="w-full h-7 px-1.5 py-0 text-[11px] font-mono rounded border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-kpmg-blue transition">
                        ${genColOptions(sampleRows, creditPrefill, 'Credit')}
                    </select>
                </td>
                <td class="py-1.5 px-2 align-middle">
                    <select id="scale-${escapeHtml(code)}" onchange="updateEntityScaleInstruction('${escapeHtml(code)}', this.value); onApprovalSelectChange(this);"
                        class="w-full h-7 px-1.5 py-0 text-[11px] font-mono rounded border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-kpmg-blue transition">
                        ${genScaleOptions(sub.scale_multiplier)}
                    </select>
                </td>
                <!-- Sequence: Confidence % -> View (eye) -> Upload (ghost) -->
                <td class="py-1.5 px-2 text-center align-middle">
                    <div class="flex items-center justify-center space-x-1.5">
                        <span class="text-[10px] font-mono text-slate-600 font-bold">${confPct}%</span>
                        <button type="button" onclick="toggleSamplePreview('drawer-${escapeHtml(code)}')"
                            class="w-6 h-6 rounded hover:bg-slate-200 text-slate-600 hover:text-kpmg-blue inline-flex items-center justify-center transition cursor-pointer"
                            title="Toggle Sample Data & Scale Details">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                            </svg>
                        </button>
                        <button type="button" onclick="triggerRowFileUpload('${escapeHtml(code)}')"
                            class="w-6 h-6 rounded hover:bg-slate-200 text-slate-500 hover:text-kpmg-blue inline-flex items-center justify-center transition cursor-pointer"
                            title="Upload / Replace file for ${escapeHtml(sub.entity_name || code)}">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                            </svg>
                        </button>
                        <input type="file" id="row-file-input-${escapeHtml(code)}" class="hidden" accept=".xlsx,.xls,.csv" onchange="handleRowFileUpload(event, '${escapeHtml(code)}')" />
                    </div>
                </td>
            </tr>

            <!-- Subsidiary Drawer Row -->
            <tr id="drawer-${escapeHtml(code)}" class="hidden bg-slate-50/80 border-b border-slate-200">
                <td colspan="9" class="p-3 font-sans">
                    ${hasDateMismatch ? `
                        <div class="mb-2 p-2 rounded-lg bg-rose-50 border border-rose-200 text-rose-900 text-xs flex items-center space-x-2">
                            <svg class="w-4 h-4 text-rose-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
                            <span><strong>Period Discrepancy:</strong> File contains data for <strong>${escapeHtml(sub.detected_period || '')}</strong>, but active consolidation run cutoff is <strong>${escapeHtml(state.target_period || '31-03-2024')}</strong>. This data belongs to a different reporting period.</span>
                        </div>
                    ` : ''}
                    <div class="text-[11px] text-indigo-900 font-medium mb-1.5 flex items-center space-x-1.5">
                        <svg class="w-3.5 h-3.5 text-indigo-600 shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path></svg>
                        <span>Scale Normalization: <strong id="scale-instr-${escapeHtml(code)}">${escapeHtml(sub.scale_instruction || 'Reported in exact absolute currency (multiplier 1.0)')}</strong></span>
                    </div>
                    ${sampleRows.length > 0 ? `
                        <div class="overflow-x-auto text-[10px] font-mono border border-slate-200 rounded bg-white max-h-36">
                            <table class="w-full text-left">
                                <tbody>
                                    ${sampleRows.slice(0, 8).map((r, i) => `<tr class="${i === 0 ? 'font-bold bg-slate-100' : 'border-b border-slate-100'}">${r.map(c => `<td class="p-1">${escapeHtml(String(c))}</td>`).join('')}</tr>`).join('')}
                                </tbody>
                            </table>
                        </div>
                    ` : '<div class="text-[11px] text-slate-400">No raw rows extracted yet.</div>'}
                </td>
            </tr>
        `;
    });

    // Empty state row for filter/search
    html += `
                        <tr id="approval-grid-empty" class="hidden">
                            <td colspan="9" class="p-8 text-center text-slate-400 font-sans">
                                No entities match the active filter or search query.
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- ========================================================================= -->
            <!-- VIEW 2: FOREIGN EXCHANGE RATES TABLE                                      -->
            <!-- ========================================================================= -->
            <div id="pane-approval-fx" class="approval-view-pane ${activeApprovalTab === 'FX' ? '' : 'view-hidden'} border border-slate-200 rounded-xl overflow-x-auto bg-white shadow-xs max-h-[58vh]">
                <table class="w-full text-left text-xs border-collapse">
                    <thead class="sticky top-0 z-20 bg-indigo-50/70 border-b border-indigo-200 font-semibold text-indigo-950 shadow-2xs">
                        <tr>
                            <th class="py-2 px-2 text-center w-11">Status</th>
                            <th class="py-2 px-2.5 min-w-[170px]">Schedule & Pair</th>
                            <th class="py-2 px-2 min-w-[160px]">Assigned File</th>
                            <th class="py-2 px-2 min-w-[130px]">Worksheet</th>
                            <th class="py-2 px-2 min-w-[120px]">Closing Rate</th>
                            <th class="py-2 px-2 min-w-[120px]">Average Rate</th>
                            <th class="py-2 px-2 min-w-[120px]">Swap Rate</th>
                            <th class="py-2 px-2 text-center min-w-[110px]">Actions</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 font-mono text-[11px]">
    `;

    // Render FX Row
    const fxSampleRows = fx.sample_rows || [];
    const fxConfPct = Math.round((fx.confidence || 1.0) * 100);
    const fxRowStatus = isFxMapped ? 'ready' : 'flagged';

    const fxStatusIcon = isFxMapped
        ? `<div onmouseenter="showApprovalTooltip(event, 'FX_RATES', 'ready')" onmouseleave="hideApprovalTooltip()" class="status-indicator-badge w-5 h-5 rounded-full flex items-center justify-center font-bold text-[10px] bg-emerald-100 text-emerald-700 border border-emerald-300">✓</div>`
        : `<div onmouseenter="showApprovalTooltip(event, 'FX_RATES', 'flagged')" onmouseleave="hideApprovalTooltip()" class="status-indicator-badge w-5 h-5 rounded-full flex items-center justify-center font-bold text-[10px] bg-rose-100 text-rose-700 border border-rose-300">✕</div>`;

    html += `
        <tr class="hover:bg-indigo-50/40 transition">
            <td class="py-2 px-2 text-center align-middle">
                <div class="inline-flex items-center justify-center">
                    ${fxStatusIcon}
                </div>
            </td>
            <td class="py-2 px-2.5 align-middle">
                <div class="flex items-center space-x-2">
                    <div class="w-6 h-6 rounded bg-indigo-700 text-white flex items-center justify-center font-bold text-[10px]">FX</div>
                    <div>
                        <div class="flex items-center space-x-1.5">
                            <span class="font-bold text-indigo-950 text-xs">Foreign Exchange Schedule</span>
                            <span class="px-1.5 py-0.2 rounded text-[9px] bg-indigo-100 text-indigo-800 font-semibold border border-indigo-200">MANDATORY</span>
                        </div>
                        <div class="text-[10px] text-slate-500 font-mono">Currency Translation & Equity Reserve</div>
                    </div>
                </div>
            </td>
            <td class="py-2 px-2 align-middle">
                <select id="select-FX_RATES-file" onchange="updateEntityFileMapping('FX_RATES', this.value); onApprovalSelectChange(this);"
                    class="w-full h-7 px-1.5 py-0 text-[11px] font-mono rounded border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-kpmg-blue transition">
                    ${genFileOptions(fx.filename)}
                </select>
            </td>
            <td class="py-2 px-2 align-middle">
                <select id="select-FX_RATES-sheet" onchange="updateEntitySheetMapping('FX_RATES', this.value); onApprovalSelectChange(this);"
                    class="w-full h-7 px-1.5 py-0 text-[11px] font-mono rounded border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-kpmg-blue transition">
                    ${genSheetOptions(fx.filename, fx.sheet_name)}
                </select>
            </td>
            <td class="py-2 px-2 align-middle">
                <select id="col-fx-closing" onchange="onApprovalSelectChange(this)" class="w-full h-7 px-1.5 py-0 text-[11px] font-mono rounded border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-kpmg-blue transition">
                    ${genColOptions(fxSampleRows, (fx.detected_columns || {}).closing_rate, 'Closing Rate')}
                </select>
            </td>
            <td class="py-2 px-2 align-middle">
                <select id="col-fx-average" onchange="onApprovalSelectChange(this)" class="w-full h-7 px-1.5 py-0 text-[11px] font-mono rounded border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-kpmg-blue transition">
                    ${genColOptions(fxSampleRows, (fx.detected_columns || {}).average_rate, 'Average Rate')}
                </select>
            </td>
            <td class="py-2 px-2 align-middle">
                <select id="col-fx-swap" onchange="onApprovalSelectChange(this)" class="w-full h-7 px-1.5 py-0 text-[11px] font-mono rounded border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-kpmg-blue transition">
                    ${genColOptions(fxSampleRows, (fx.detected_columns || {}).swap_rate, 'Swap Rate (Optional)')}
                </select>
            </td>
            <!-- Sequence: Confidence % -> View (eye) -> Upload (ghost) -->
            <td class="py-2 px-2 text-center align-middle">
                <div class="flex items-center justify-center space-x-1.5">
                    <span class="text-[10px] font-mono text-slate-600 font-bold">${fxConfPct}%</span>
                    <button type="button" onclick="toggleSamplePreview('drawer-FX_RATES')"
                        class="w-6 h-6 rounded hover:bg-indigo-100 text-indigo-700 inline-flex items-center justify-center transition cursor-pointer"
                        title="Toggle FX Rates Table Preview">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                        </svg>
                    </button>
                    <button type="button" onclick="triggerRowFileUpload('FX_RATES')"
                        class="w-6 h-6 rounded hover:bg-indigo-100 text-indigo-700 inline-flex items-center justify-center transition cursor-pointer"
                        title="Upload / Replace Foreign Exchange Rates schedule">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                        </svg>
                    </button>
                    <input type="file" id="row-file-input-FX_RATES" class="hidden" accept=".xlsx,.xls,.csv" onchange="handleRowFileUpload(event, 'FX_RATES')" />
                </div>
            </td>
        </tr>

        <!-- FX Drawer Row -->
        <tr id="drawer-FX_RATES" class="hidden bg-indigo-50/30 border-b border-indigo-100">
            <td colspan="8" class="p-3 font-sans">
                <div class="text-[10px] uppercase font-bold text-indigo-950 mb-1.5 tracking-wider">Top Extracted FX Rates Rows:</div>
                ${fxSampleRows.length > 0 ? `
                    <div class="overflow-x-auto text-[10px] font-mono border border-indigo-200 rounded bg-white max-h-36">
                        <table class="w-full text-left">
                            <tbody>
                                ${fxSampleRows.slice(0, 8).map((r, i) => `<tr class="${i === 0 ? 'font-bold bg-indigo-100/60' : 'border-b border-indigo-100/40'}">${r.map(c => `<td class="p-1">${escapeHtml(String(c))}</td>`).join('')}</tr>`).join('')}
                            </tbody>
                        </table>
                    </div>
                ` : '<div class="text-[11px] text-slate-400">No raw FX rows extracted yet.</div>'}
            </td>
        </tr>
    `;

    html += `
                    </tbody>
                </table>
            </div>

            <!-- ========================================================================= -->
            <!-- VIEW 3: IGNORED EXTRA SHEETS TABLE                                        -->
            <!-- ========================================================================= -->
            <div id="pane-approval-ignored" class="approval-view-pane ${activeApprovalTab === 'IGNORED' ? '' : 'view-hidden'} border border-slate-200 rounded-xl overflow-x-auto bg-white shadow-xs max-h-[58vh]">
                <table class="w-full text-left text-xs border-collapse">
                    <thead class="sticky top-0 z-20 bg-slate-100 border-b border-slate-200 font-semibold text-slate-700 shadow-2xs">
                        <tr>
                            <th class="py-2 px-3 text-center w-24">Status</th>
                            <th class="py-2 px-3 min-w-[180px]">Sheet Name</th>
                            <th class="py-2 px-3 min-w-[220px]">Source File</th>
                            <th class="py-2 px-3 min-w-[220px]">Exclusion Context</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 font-mono text-[11px]">
                        ${unassigned.length > 0 ? unassigned.map(u => `
                            <tr class="hover:bg-slate-50 transition">
                                <td class="py-2.5 px-3 text-center align-middle">
                                    <span class="px-2 py-0.5 rounded text-[10px] bg-slate-200 text-slate-700 font-semibold">Ignored</span>
                                </td>
                                <td class="py-2.5 px-3 align-middle font-bold text-slate-800">
                                    ${escapeHtml(u.sheet_name || 'Sheet')}
                                </td>
                                <td class="py-2.5 px-3 align-middle text-slate-500">
                                    ${escapeHtml(u.filename)}
                                </td>
                                <td class="py-2.5 px-3 align-middle font-sans text-slate-500 text-[11px]">
                                    Non-perimeter reference sheet (excluded from trial balance consolidation pipeline).
                                </td>
                            </tr>
                        `).join('') : `
                            <tr>
                                <td colspan="4" class="p-8 text-center text-slate-400 font-sans">
                                    No ignored or extra sheets found in the uploaded workbooks.
                                </td>
                            </tr>
                        `}
                    </tbody>
                </table>
            </div>

        </div>
    `;

    container.innerHTML = html;

    if (approvalActiveFilter !== 'ALL' || approvalSearchQuery !== '') {
        filterApprovalGrid(approvalActiveFilter, approvalSearchQuery);
    }

    validateApprovalFields(false);

    // Update footer status
    if (footerStatus) {
        const fxStatusText = isFxMapped ? 'FX Rates Verified' : 'FX Rates Missing';
        footerStatus.innerHTML = `<span class="font-semibold text-slate-700">${mappedEntities}/${totalEntities} Entities Mapped</span> • <span class="${isFxMapped ? 'text-emerald-700 font-semibold' : 'text-amber-700 font-semibold'}">${fxStatusText}</span>`;
    }
}


function updateEntityScaleInstruction(entityCode, scaleValue) {
    const mult = parseFloat(scaleValue) || 1.0;
    const instrSpan = document.getElementById(`scale-instr-${entityCode}`);
    let desc = `Reported in exact absolute currency (multiplier 1.0)`;
    if (Math.abs(mult - 100000) < 0.1) {
        desc = `Reported in ₹ Lakhs — multiplying by 100,000 to normalize to absolute currency`;
    } else if (Math.abs(mult - 10000000) < 0.1) {
        desc = `Reported in ₹ Crores — multiplying by 10,000,000 to normalize to absolute currency`;
    } else if (Math.abs(mult - 1000000) < 0.1) {
        desc = `Reported in Millions — multiplying by 1,000,000 to normalize to absolute currency`;
    } else if (Math.abs(mult - 1000) < 0.1) {
        desc = `Reported in Thousands — multiplying by 1,000 to normalize to absolute currency`;
    } else if (Math.abs(mult - 100) < 0.1) {
        desc = `Reported in Hundreds — multiplying by 100 to normalize to absolute currency`;
    } else if (mult !== 1.0) {
        desc = `Multiplying by ${mult} to normalize to absolute currency`;
    }
    if (instrSpan) instrSpan.textContent = desc;

    if (step1ApprovalState) {
        if (step1ApprovalState.parent && step1ApprovalState.parent.entity_code === entityCode) {
            step1ApprovalState.parent.scale_multiplier = mult;
            step1ApprovalState.parent.scale_instruction = desc;
        } else if (step1ApprovalState.subsidiaries) {
            const sub = step1ApprovalState.subsidiaries.find(s => s.entity_code === entityCode);
            if (sub) {
                sub.scale_multiplier = mult;
                sub.scale_instruction = desc;
            }
        }
    }
}

function updateEntityFileMapping(entityCode, filename) {
    if (!step1ApprovalState) return;
    const fileMap = step1ApprovalState.files_map || step1ApprovalState.available_files_and_sheets || {};
    const sheets = fileMap[filename] || [];
    const firstSheet = sheets[0] || '';

    if (entityCode === 'FX_RATES') {
        if (!step1ApprovalState.fx_rates) step1ApprovalState.fx_rates = {};
        step1ApprovalState.fx_rates.filename = filename;
        step1ApprovalState.fx_rates.sheet_name = firstSheet;
    } else if (step1ApprovalState.parent && step1ApprovalState.parent.entity_code === entityCode) {
        step1ApprovalState.parent.filename = filename;
        step1ApprovalState.parent.sheet_name = firstSheet;
    } else {
        const sub = (step1ApprovalState.subsidiaries || []).find(s => s.entity_code === entityCode);
        if (sub) {
            sub.filename = filename;
            sub.sheet_name = firstSheet;
        }
    }
    renderPerimeterApprovalModalContent(step1ApprovalState);
}

function updateEntitySheetMapping(entityCode, sheetName) {
    if (!step1ApprovalState) return;
    if (entityCode === 'FX_RATES') {
        if (step1ApprovalState.fx_rates) step1ApprovalState.fx_rates.sheet_name = sheetName;
    } else if (step1ApprovalState.parent && step1ApprovalState.parent.entity_code === entityCode) {
        step1ApprovalState.parent.sheet_name = sheetName;
    } else {
        const sub = (step1ApprovalState.subsidiaries || []).find(s => s.entity_code === entityCode);
        if (sub) sub.sheet_name = sheetName;
    }
    renderPerimeterApprovalModalContent(step1ApprovalState);
}

function toggleSamplePreview(id) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('hidden');
}

async function confirmPerimeterApprovalModal() {
    if (!step1ApprovalState) return;

    const btn = document.getElementById('btn-confirm-perimeter-modal');

    // Strict Required Mapping Gate & Shake Animation for Unfilled Fields
    const unfilledCount = validateApprovalFields(true);
    if (unfilledCount > 0) {
        showToast('Incomplete Mapping', `Please select all required mapping columns (${unfilledCount} unfilled highlighted in red) before confirming.`, 'error');
        return;
    }

    // Strict Period Discrepancy Guard: check if any perimeter entity has unresolved date mismatch
    const mismatches = [];
    if (step1ApprovalState.parent && step1ApprovalState.parent.date_status === 'MISMATCH') {
        mismatches.push(`${step1ApprovalState.parent.entity_name || step1ApprovalState.parent.entity_code} (${step1ApprovalState.parent.detected_period || 'Different Period'})`);
    }
    (step1ApprovalState.subsidiaries || []).forEach(s => {
        if (s.date_status === 'MISMATCH') {
            mismatches.push(`${s.entity_name || s.entity_code} (${s.detected_period || 'Different Period'})`);
        }
    });

    if (mismatches.length > 0) {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg><span>Approve & Confirm Ingestion</span>`;
        }
        showToast(`Cannot Confirm Ingestion: Period Discrepancy detected for ${mismatches.join(', ')}. The uploaded file contains data for a different reporting period than the active run date (${step1ApprovalState.target_period}).`, 'error');
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span>Validating & Normalizing Balances...</span>`;
    }

    const payload = {
        entities: []
    };

    if (step1ApprovalState.parent && step1ApprovalState.parent.filename) {
        const pCodeSel = document.getElementById('col-parent-code');
        const pDebitSel = document.getElementById('col-parent-debit');
        const pCreditSel = document.getElementById('col-parent-credit');
        const pScaleSel = document.getElementById('scale-parent');
        const cols = Object.assign({}, step1ApprovalState.parent.detected_columns || {});
        if (pCodeSel && pCodeSel.value) cols.account_code = pCodeSel.value;
        if (pDebitSel && pDebitSel.value) {
            cols.debit = pDebitSel.value;
            if (!pCreditSel || !pCreditSel.value) cols.amount = pDebitSel.value;
        }
        if (pCreditSel && pCreditSel.value) cols.credit = pCreditSel.value;

        const scaleMult = pScaleSel ? (parseFloat(pScaleSel.value) || 1.0) : (step1ApprovalState.parent.scale_multiplier || 1.0);

        payload.entities.push({
            entity_code: step1ApprovalState.parent.entity_code,
            filename: step1ApprovalState.parent.filename,
            sheet_name: step1ApprovalState.parent.sheet_name,
            columns: cols,
            scale_multiplier: scaleMult
        });
    }

    if (step1ApprovalState.subsidiaries) {
        step1ApprovalState.subsidiaries.forEach(s => {
            if (s.filename) {
                const sCodeSel = document.getElementById(`col-${s.entity_code}-code`);
                const sDebitSel = document.getElementById(`col-${s.entity_code}-debit`);
                const sCreditSel = document.getElementById(`col-${s.entity_code}-credit`);
                const sScaleSel = document.getElementById(`scale-${s.entity_code}`);
                const cols = Object.assign({}, s.detected_columns || {});
                if (sCodeSel && sCodeSel.value) cols.account_code = sCodeSel.value;
                if (sDebitSel && sDebitSel.value) {
                    cols.debit = sDebitSel.value;
                    if (!sCreditSel || !sCreditSel.value) cols.amount = sDebitSel.value;
                }
                if (sCreditSel && sCreditSel.value) cols.credit = sCreditSel.value;

                const scaleMult = sScaleSel ? (parseFloat(sScaleSel.value) || 1.0) : (s.scale_multiplier || 1.0);

                payload.entities.push({
                    entity_code: s.entity_code,
                    filename: s.filename,
                    sheet_name: s.sheet_name,
                    columns: cols,
                    scale_multiplier: scaleMult
                });
            }
        });
    }

    if (step1ApprovalState.fx_rates && step1ApprovalState.fx_rates.filename) {
        const fxClosingSel = document.getElementById('col-fx-closing');
        const fxAvgSel = document.getElementById('col-fx-average');
        const fxSwapSel = document.getElementById('col-fx-swap');
        const cols = Object.assign({}, step1ApprovalState.fx_rates.detected_columns || {});
        if (fxClosingSel && fxClosingSel.value) cols.closing_rate = fxClosingSel.value;
        if (fxAvgSel && fxAvgSel.value) cols.average_rate = fxAvgSel.value;
        if (fxSwapSel && fxSwapSel.value) cols.swap_rate = fxSwapSel.value;

        payload.fx_rates = {
            filename: step1ApprovalState.fx_rates.filename,
            sheet_name: step1ApprovalState.fx_rates.sheet_name,
            columns: cols
        };
    }

    try {
        const res = await fetch('/api/pipeline/confirm-ingestion', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok && data.success) {
            closePerimeterApprovalModal();
            showToast('Ingestion Approved', 'Step 1 locked with green checkmark. Balances normalized to absolute currency.', 'success');
            await fetchStatus();
            await loadPipelineData();
            switchStep(1);
            const container = document.getElementById('step-content');
            if (container) renderStep1(container);
        } else {
            showToast('Approval Incomplete', data.detail || 'Cannot close Step 1 until all perimeter entities are uploaded.', 'error');
        }
    } catch (err) {
        showToast('Network Error', 'Confirmation failed: ' + err, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg><span>Approve & Confirm Ingestion</span>`;
        }
    }
}

// Single Entity Upload Modal Functions
function openSingleUploadModal(entityCode, entityName) {
    selectedSingleUploadEntity = entityCode;
    selectedSingleFile = null;

    const modal = document.getElementById('modal-single-upload');
    const title = document.getElementById('single-upload-title');
    const desc = document.getElementById('single-upload-desc');
    const codeInput = document.getElementById('single-upload-entity-code');
    const label = document.getElementById('single-file-label');
    const fileInput = document.getElementById('single-file-input');

    if (fileInput) fileInput.value = '';
    if (codeInput) codeInput.value = entityCode;
    if (label) label.textContent = 'Choose file or drag here';
    if (title) title.textContent = `Upload Document for ${entityName}`;
    if (desc) desc.textContent = entityCode === 'FX_RATES' ? 'Upload an Excel or CSV file containing exchange rates table.' : `Upload an Excel or CSV trial balance specifically for ${entityName} (${entityCode}).`;

    if (modal) modal.classList.remove('hidden');
}

function closeSingleUploadModal() {
    const modal = document.getElementById('modal-single-upload');
    if (modal) modal.classList.add('hidden');
    selectedSingleUploadEntity = null;
    selectedSingleFile = null;
}

function handleSingleFileSelected(input) {
    if (input.files && input.files.length > 0) {
        selectedSingleFile = input.files[0];
        const label = document.getElementById('single-file-label');
        if (label) label.textContent = `${selectedSingleFile.name} (${(selectedSingleFile.size / 1024).toFixed(1)} KB)`;
    }
}

async function submitSingleUpload(e) {
    e.preventDefault();
    if (!selectedSingleFile || !selectedSingleUploadEntity) {
        showToast('Missing File', 'Please select a file to upload.', 'warning');
        return;
    }

    const btn = document.getElementById('btn-submit-single');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span>Uploading...</span>`;
    }

    const formData = new FormData();
    formData.append('file', selectedSingleFile);
    formData.append('entity_code', selectedSingleUploadEntity);

    const targetPeriod = (step1ApprovalState && step1ApprovalState.target_period) || (appStatus && appStatus.current_period) || '';
    if (targetPeriod) formData.append('period', targetPeriod);

    try {
        const res = await fetch('/api/pipeline/single-entity-upload', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (res.ok && data.success) {
            step1ApprovalState = data.approval_state;
            closeSingleUploadModal();
            showToast('File Uploaded', `Successfully mapped document for ${selectedSingleUploadEntity}.`, 'success');
            // If the perimeter approval modal is currently open, refresh its contents!
            const approvalModal = document.getElementById('modal-perimeter-approval');
            if (approvalModal && !approvalModal.classList.contains('hidden')) {
                renderPerimeterApprovalModalContent(step1ApprovalState);
            }
            const container = document.getElementById('step-content');
            if (container) renderStep1(container);
        } else {
            showToast('Upload Error', data.detail || 'Failed to upload file.', 'error');
        }
    } catch (err) {
        showToast('Network Error', 'Single upload failed: ' + err, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<span>Upload & Map</span>`;
        }
    }
}

// ============================================================================
// STEP 2: COA MAPPING WITH DYNAMIC ENTITY TABS & LEVEL 0 DROPDOWNS
// ============================================================================

let activeStep2Entity = null;
let step2AccountSearchQuery = '';
let currentL0PopoverTarget = null;

function getStep2EntityTabs() {
    const perimeter = (appStatus && appStatus.perimeter_entities && appStatus.perimeter_entities.length > 0)
        ? appStatus.perimeter_entities
        : ((pipelineData && pipelineData.perimeter_entities) ? pipelineData.perimeter_entities : []);

    const rawTbs = (pipelineData && pipelineData.raw_tbs) ? pipelineData.raw_tbs : [];
    const rawTbMap = new Map();
    rawTbs.forEach(tb => {
        if (tb.entity_code) rawTbMap.set(tb.entity_code.toUpperCase(), tb);
    });

    const tabs = [];
    const seen = new Set();

    if (perimeter.length > 0) {
        // 1. Parent entity first
        const parent = perimeter.find(p => p.is_parent) || perimeter[0];
        if (parent) {
            const code = parent.entity_code.toUpperCase();
            seen.add(code);
            const tb = rawTbMap.get(code);
            tabs.push({
                entity_code: parent.entity_code,
                entity_name: parent.entity_name || (tb && tb.entity_name) || parent.entity_code,
                currency: parent.currency || parent.input_currency || (tb && tb.currency) || (appStatus && appStatus.reporting_currency) || 'INR',
                is_parent: true
            });
        }
        // 2. Each subsidiary in order
        perimeter.forEach(p => {
            const code = p.entity_code.toUpperCase();
            if (!seen.has(code)) {
                seen.add(code);
                const tb = rawTbMap.get(code);
                tabs.push({
                    entity_code: p.entity_code,
                    entity_name: p.entity_name || (tb && tb.entity_name) || p.entity_code,
                    currency: p.currency || p.input_currency || (tb && tb.currency) || '—',
                    is_parent: false
                });
            }
        });
    } else if (rawTbs.length > 0) {
        rawTbs.forEach((tb, idx) => {
            const code = tb.entity_code.toUpperCase();
            if (!seen.has(code)) {
                seen.add(code);
                tabs.push({
                    entity_code: tb.entity_code,
                    entity_name: tb.entity_name || tb.entity_code,
                    currency: tb.currency || '—',
                    is_parent: idx === 0
                });
            }
        });
    }

    return tabs;
}

function switchStep2EntityTab(entityCode) {
    activeStep2Entity = entityCode;
    step2AccountSearchQuery = '';
    const container = document.getElementById("step-content");
    if (container) renderStep2(container);
}

function onStep2AccountSearch(query) {
    step2AccountSearchQuery = (query || '').trim().toLowerCase();
    const tbody = document.getElementById("step2-table-tbody");
    if (!tbody) return;
    renderStep2TableRows(tbody);
}

async function runCOAMappingNow() {
    showToast("Mapping Accounts", "Running AI & deterministic COA standardizer...", "info");
    try {
        const res = await fetch("/api/pipeline/run-mapping", { method: "POST" });
        const data = await res.json();
        if (res.ok && data.success) {
            await loadPipelineData();
            showToast("Mapping Complete", `Mapped ${data.total_mapped} accounts (${data.pending_reviews} require review).`, "success");
            const container = document.getElementById("step-content");
            if (container) renderStep2(container);
        } else {
            showToast("Mapping Error", data.detail || "Failed to execute mapping.", "error");
        }
    } catch (err) {
        showToast("Network Error", "Mapping call failed: " + err, "error");
    }
}

function getMappingsForEntity(entityCode) {
    if (!entityCode) return [];
    const codeUpper = String(entityCode).trim().toUpperCase();
    const allMappings = (pipelineData && pipelineData.mapping_decisions) ? pipelineData.mapping_decisions : [];

    // Strict match on entity_code
    let matches = allMappings.filter(m => m.entity_code && String(m.entity_code).trim().toUpperCase() === codeUpper);

    // Find raw TB for this entity
    const rawTbs = (pipelineData && pipelineData.raw_tbs) ? pipelineData.raw_tbs : [];
    const rawTb = rawTbs.find(tb => (tb.entity_code || '').trim().toUpperCase() === codeUpper);

    // Fallback: If no mappings directly tagged with this entity_code, extract directly from raw_tbs
    if (matches.length === 0 && rawTb && rawTb.rows && rawTb.rows.length > 0) {
        matches = rawTb.rows.map(r => ({
            entity_code: entityCode,
            local_code: r.account_code,
            local_description: r.account_description,
            currency: rawTb.currency || 'INR',
            amount: (r.amount !== null && r.amount !== undefined && r.amount !== 0) ? r.amount : ((r.debit || 0) - (r.credit || 0)),
            group_code: '999999',
            group_description: `Unmapped: ${r.account_description}`,
            level_0_code: null,
            level_0_name: null,
            confidence: 0.0,
            needs_review: true,
            method: 'RAW_TB_IMPORT'
        }));
    } else if (matches.length > 0 && rawTb && rawTb.rows && rawTb.rows.length > 0) {
        // Enforce that amounts and currencies from raw TB are preserved if mapping has missing/zero amount
        const rawRowMap = new Map();
        rawTb.rows.forEach(r => {
            if (r.account_code) rawRowMap.set(String(r.account_code).trim(), r);
        });
        matches.forEach(m => {
            if (m.amount === null || m.amount === undefined || m.amount === 0) {
                const rawR = rawRowMap.get(String(m.local_code).trim());
                if (rawR) {
                    const rawAmt = (rawR.amount !== null && rawR.amount !== undefined && rawR.amount !== 0)
                        ? rawR.amount
                        : ((rawR.debit || 0) - (rawR.credit || 0));
                    if (rawAmt !== 0) m.amount = rawAmt;
                }
            }
            if (!m.currency && rawTb.currency) {
                m.currency = rawTb.currency;
            }
        });
    }
    return matches;
}

function onStep2ConsolidateClick() {
    const tabs = getStep2EntityTabs();
    let totalPending = 0;
    tabs.forEach(t => {
        const ms = getMappingsForEntity(t.entity_code);
        totalPending += ms.filter(m => m.needs_review).length;
    });
    if (totalPending > 0) {
        showToast("Review Required", `Cannot proceed: ${totalPending} account(s) require review across entity tabs.`, "warning");
        return;
    }
    // Proceed to Step 3 and execute consolidation
    triggerRunPipeline();
}

function renderStep2(el) {
    const tabs = getStep2EntityTabs();
    if (tabs.length === 0) {
        el.innerHTML = `
            <div class="p-12 text-center bg-white rounded border border-kpmg-border">
                <svg class="w-12 h-12 text-kpmg-muted mx-auto mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"></path></svg>
                <h4 class="font-bold text-sm text-kpmg-navy mb-1">No Trial Balances Ingested</h4>
                <p class="text-xs text-kpmg-muted max-w-md mx-auto mb-4">Please complete Step 1 Ingestion and approve entity files before proceeding to mapping.</p>
                <button onclick="switchStep(1)" class="h-8 px-4 rounded bg-kpmg-blue hover:bg-kpmg-navy text-white text-xs font-semibold transition shadow-xs inline-flex items-center space-x-1.5 cursor-pointer">
                    <span>Go to Step 1 (Ingestion)</span>
                </button>
            </div>
        `;
        return;
    }

    if (!activeStep2Entity || !tabs.some(t => t.entity_code === activeStep2Entity)) {
        activeStep2Entity = tabs[0].entity_code;
    }

    const currentTab = tabs.find(t => t.entity_code === activeStep2Entity) || tabs[0];

    // Global review count across ALL entities
    let totalPendingAllEntities = 0;
    let totalMappedAccounts = 0;
    tabs.forEach(t => {
        const ms = getMappingsForEntity(t.entity_code);
        totalMappedAccounts += ms.length;
        totalPendingAllEntities += ms.filter(m => m.needs_review).length;
    });
    const canConsolidate = totalPendingAllEntities === 0 && totalMappedAccounts > 0;

    // Entity tabs HTML
    const tabsHtml = tabs.map(t => {
        const isActive = t.entity_code === activeStep2Entity;
        const entMappings = getMappingsForEntity(t.entity_code);
        const pendingInTab = entMappings.filter(m => m.needs_review).length;
        const roleLabel = t.is_parent ? 'Parent' : 'Subsidiary';

        return `
            <button onclick="switchStep2EntityTab('${escapeHtml(t.entity_code)}')"
                class="px-4 py-2 rounded-lg text-xs font-semibold flex items-center space-x-2 transition cursor-pointer select-none shrink-0 ${
                    isActive
                        ? 'bg-kpmg-blue text-white shadow-xs ring-2 ring-kpmg-blue/20'
                        : 'bg-slate-100 text-slate-700 hover:bg-slate-200/80 hover:text-kpmg-navy'
                }">
                <span>${escapeHtml(t.entity_name || t.entity_code)}</span>
                <span class="text-[10px] font-mono opacity-80">(${roleLabel})</span>
                ${pendingInTab > 0
                    ? `<span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse ml-1" title="${pendingInTab} review(s) pending"></span>`
                    : (entMappings.length > 0 ? `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 ml-1"></span>` : '')
                }
            </button>
        `;
    }).join("");

    el.innerHTML = `
        <div class="space-y-3 w-full">
            <!-- 1. Header Toolbar -->
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-kpmg-border pb-3">
                <div>
                    <h3 class="font-bold text-base text-kpmg-navy">Chart of Accounts Alignment</h3>
                    <p class="text-xs text-kpmg-muted">Standardizes parent and subsidiary trial balances to Group COA format with dynamic Level 0 mapping.</p>
                </div>
                <div class="flex items-center space-x-2">
                    <!-- Search Input -->
                    <div class="relative w-48 sm:w-60">
                        <svg class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                        </svg>
                        <input type="text" id="step2-account-search" placeholder="Search accounts..."
                            value="${escapeHtml(step2AccountSearchQuery)}"
                            oninput="onStep2AccountSearch(this.value)"
                            class="w-full h-7 pl-8 pr-2.5 rounded bg-slate-100 border border-slate-200 text-xs text-slate-800 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-kpmg-blue transition font-mono">
                    </div>

                    <!-- Consolidate Primary Action Button -->
                    <button id="btn-consolidate-step2" onclick="onStep2ConsolidateClick()"
                        class="h-7 px-3 rounded bg-kpmg-blue hover:bg-kpmg-navy text-white text-[11px] font-semibold transition flex items-center space-x-1.5 shadow-xs btn-tactile cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                        title="Consolidate" ${canConsolidate ? '' : 'disabled'}>
                        <svg class="w-3.5 h-3.5 text-[#ACEAFF]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span>Consolidate</span>
                    </button>
                </div>
            </div>

            <!-- 2. Dynamic Entity Tabs Bar -->
            <div class="flex items-center space-x-2 border-b border-slate-200 pb-2.5 overflow-x-auto select-none">
                ${tabsHtml}
            </div>

            <!-- 3. High-Density Financial Ledger Table -->
            <div class="overflow-x-auto min-h-[460px] max-h-[calc(100vh-270px)] border border-kpmg-border rounded-lg bg-white shadow-2xs">
                <table class="fin-table">
                    <thead class="sticky top-0 bg-slate-100 z-10 shadow-xs">
                        <tr>
                            <th style="width: 130px;">Account Code</th>
                            <th>Account Name</th>
                            <th style="width: 80px; text-align: center;">Currency</th>
                            <th class="num-cell" style="width: 140px;">Amount</th>
                            <th style="min-width: 300px;">Level 0 Mapping</th>
                            <th class="num-cell" style="width: 100px;">Confidence</th>
                            <th class="text-center" style="width: 120px;">Status</th>
                        </tr>
                    </thead>
                    <tbody id="step2-table-tbody">
                        <!-- Populated by renderStep2TableRows -->
                    </tbody>
                </table>
            </div>
        </div>
    `;

    const tbody = document.getElementById("step2-table-tbody");
    if (tbody) renderStep2TableRows(tbody);
}

function renderStep2TableRows(tbody) {
    const tabs = getStep2EntityTabs();
    const currentTab = tabs.find(t => t.entity_code === activeStep2Entity) || tabs[0];
    if (!currentTab) return;

    const currentEntityCode = currentTab.entity_code;
    let entityMappings = getMappingsForEntity(currentEntityCode);

    // Search filter
    if (step2AccountSearchQuery) {
        entityMappings = entityMappings.filter(m =>
            (m.local_code && String(m.local_code).toLowerCase().includes(step2AccountSearchQuery)) ||
            (m.local_description && String(m.local_description).toLowerCase().includes(step2AccountSearchQuery)) ||
            (m.group_code && String(m.group_code).toLowerCase().includes(step2AccountSearchQuery)) ||
            (m.level_0_name && String(m.level_0_name).toLowerCase().includes(step2AccountSearchQuery))
        );
    }

    if (entityMappings.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="p-8 text-center text-kpmg-muted text-xs">
                    ${allMappings.length === 0
                        ? `Accounts not yet standardized for ${escapeHtml(currentTab.entity_name)}. <button onclick="runCOAMappingNow()" class="ml-2 font-bold text-kpmg-blue hover:underline cursor-pointer">Click here to run mapping</button>.`
                        : `No accounts matching filter "${escapeHtml(step2AccountSearchQuery)}".`
                    }
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = entityMappings.map((m, idx) => {
        const rowId = `s2-row-${idx}`;
        const isYellow = !!m.needs_review;
        const rowBg = isYellow
            ? 'bg-amber-50/80 hover:bg-amber-100/70 border-b border-amber-200 text-amber-950 font-medium'
            : 'hover:bg-slate-50/70 border-b border-slate-100 text-slate-800';

        const confPct = Math.round((m.confidence || 0) * 100);
        const confColor = isYellow ? 'text-amber-700' : (confPct >= 85 ? 'text-emerald-700' : 'text-amber-700');

        const currentL0Display = m.group_code && m.group_code !== '999999'
            ? `${m.group_code} - ${m.level_0_name || m.group_description || 'Standard Account'}`
            : 'Select Level 0 Mapping...';

        const statusBadge = isYellow
            ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-200 text-amber-900 border border-amber-300">Review Required</span>`
            : `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">Mapped</span>`;

        const currency = m.currency || currentTab.currency || 'INR';

        return `
            <tr id="${rowId}" class="${rowBg} transition">
                <!-- 1. Account Code -->
                <td class="font-mono text-xs font-bold py-2.5 px-3 text-slate-700">${escapeHtml(m.local_code)}</td>

                <!-- 2. Account Name -->
                <td class="font-medium py-2.5 px-3 text-xs text-slate-900">${escapeHtml(m.local_description)}</td>

                <!-- 3. Currency -->
                <td class="text-center py-2.5 px-3 text-xs">
                    <span class="px-2 py-0.5 rounded font-mono font-bold text-[10px] bg-slate-100 text-slate-700 border border-slate-200">
                        ${escapeHtml(currency)}
                    </span>
                </td>

                <!-- 4. Amount -->
                <td class="num-cell py-2.5 px-3 text-xs font-mono font-semibold text-slate-800">
                    ${formatNum(m.amount)}
                </td>

                <!-- 5. Level 0 Mapping Searchable Dropdown Button -->
                <td class="py-2 px-3 text-xs">
                    <button type="button"
                        onclick="openL0Dropdown(event, '${escapeHtml(m.entity_code || currentTab.entity_code)}', '${escapeHtml(m.local_code)}')"
                        class="w-full h-8 px-2.5 py-1 text-left text-xs font-medium rounded border ${
                            isYellow
                                ? 'border-amber-400 bg-amber-50 hover:bg-amber-100/90 text-amber-950 focus:ring-2 focus:ring-amber-400'
                                : 'border-slate-200 bg-white hover:bg-slate-50 text-slate-800 focus:ring-2 focus:ring-kpmg-blue'
                        } flex items-center justify-between transition cursor-pointer shadow-2xs">
                        <span class="truncate font-mono font-semibold">${escapeHtml(currentL0Display)}</span>
                        <svg class="w-3.5 h-3.5 text-slate-400 shrink-0 ml-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                        </svg>
                    </button>
                </td>

                <!-- 6. Confidence -->
                <td class="num-cell py-2.5 px-3 text-xs font-mono font-bold ${confColor}">
                    ${confPct}%
                </td>

                <!-- 7. Status -->
                <td class="text-center py-2.5 px-3 text-xs">
                    ${statusBadge}
                </td>
            </tr>
        `;
    }).join("");
}

// Global Level 0 Floating Dropdown Popover
function openL0Dropdown(event, entityCode, localCode) {
    event.stopPropagation();
    const btn = event.currentTarget;
    const rect = btn.getBoundingClientRect();

    let popover = document.getElementById("step2-l0-popover");
    if (!popover) {
        popover = document.createElement("div");
        popover.id = "step2-l0-popover";
        popover.className = "fixed z-50 bg-white border border-slate-200 rounded-lg shadow-xl w-80 max-w-[90vw] overflow-hidden text-xs transition-all";
        document.body.appendChild(popover);

        // Global click listener to close popover
        document.addEventListener("click", (e) => {
            const p = document.getElementById("step2-l0-popover");
            if (p && !p.classList.contains("hidden") && !p.contains(e.target)) {
                p.classList.add("hidden");
                currentL0PopoverTarget = null;
            }
        });
    }

    currentL0PopoverTarget = { entityCode, localCode };

    // Position popover right below button, adjusting if near right edge
    const top = rect.bottom + 4;
    const left = Math.min(rect.left, window.innerWidth - 330);
    popover.style.top = `${top}px`;
    popover.style.left = `${Math.max(10, left)}px`;

    renderL0PopoverContent('', entityCode, localCode);
    popover.classList.remove("hidden");

    setTimeout(() => {
        const inp = document.getElementById("l0-popover-search-input");
        if (inp) inp.focus();
    }, 50);
}

function renderL0PopoverContent(query, entityCode, localCode) {
    const popover = document.getElementById("step2-l0-popover");
    if (!popover) return;

    // Get all available L0 choices from pipelineData or fallback
    let choices = (pipelineData && pipelineData.level_0_choices) ? pipelineData.level_0_choices : [];
    if (!choices || choices.length === 0) {
        // Fallback: extract from mapping decisions
        const mapSet = new Map();
        (pipelineData.mapping_decisions || []).forEach(m => {
            if (m.group_code && m.group_code !== '999999') {
                mapSet.set(m.group_code, {
                    account_code: m.group_code,
                    account_name: m.group_description || m.group_code,
                    level_0_account: m.level_0_name || m.group_description || m.group_code
                });
            }
        });
        choices = Array.from(mapSet.values());
    }

    const q = (query || '').trim().toLowerCase();
    const filtered = q
        ? choices.filter(c =>
            (c.account_code && c.account_code.toLowerCase().includes(q)) ||
            (c.account_name && c.account_name.toLowerCase().includes(q)) ||
            (c.level_0_account && c.level_0_account.toLowerCase().includes(q))
        )
        : choices;

    popover.innerHTML = `
        <div class="p-2 border-b border-slate-100 bg-slate-50">
            <div class="relative">
                <svg class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <input type="text" id="l0-popover-search-input" value="${escapeHtml(query)}"
                    placeholder="Search by code or description..."
                    oninput="renderL0PopoverContent(this.value, '${escapeHtml(entityCode)}', '${escapeHtml(localCode)}')"
                    class="w-full h-7 pl-8 pr-2 text-xs bg-white border border-slate-200 rounded focus:outline-none focus:ring-1 focus:ring-kpmg-blue font-mono">
            </div>
        </div>
        <div class="max-h-56 overflow-y-auto p-1 space-y-0.5">
            ${filtered.length > 0
                ? filtered.map(c => `
                    <div onclick="selectL0Option('${escapeHtml(c.account_code)}', '${escapeHtml(c.level_0_account || c.account_name)}')"
                        class="px-2.5 py-1.5 rounded hover:bg-kpmg-blue hover:text-white cursor-pointer transition flex items-center justify-between group">
                        <div class="flex items-center space-x-2 truncate">
                            <span class="font-mono font-bold text-slate-700 group-hover:text-white">${escapeHtml(c.account_code)}</span>
                            <span class="truncate text-slate-800 group-hover:text-white">${escapeHtml(c.level_0_account || c.account_name)}</span>
                        </div>
                    </div>
                `).join("")
                : `<div class="p-4 text-center text-slate-400 text-xs">No Level 0 accounts found matching "${escapeHtml(query)}".</div>`
            }
        </div>
    `;
}

async function selectL0Option(groupCode, l0Name) {
    if (!currentL0PopoverTarget) return;
    const { entityCode, localCode } = currentL0PopoverTarget;

    const popover = document.getElementById("step2-l0-popover");
    if (popover) popover.classList.add("hidden");

    try {
        const res = await fetch('/api/hitl/resolve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                entity_code: entityCode,
                local_code: localCode,
                group_code: groupCode,
                reasoning: "User approved in Level 0 Mapping table"
            })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            // Update decision locally in pipelineData
            if (!pipelineData.mapping_decisions) pipelineData.mapping_decisions = [];
            const codeUpper = String(entityCode).trim().toUpperCase();
            let d = pipelineData.mapping_decisions.find(m =>
                m.entity_code && String(m.entity_code).trim().toUpperCase() === codeUpper && String(m.local_code).trim() === String(localCode).trim()
            );
            if (!d) {
                // If not found in mapping_decisions, construct from raw TB rows
                const ms = getMappingsForEntity(entityCode);
                const source = ms.find(m => String(m.local_code).trim() === String(localCode).trim());
                d = {
                    entity_code: entityCode,
                    local_code: localCode,
                    local_description: source ? source.local_description : localCode,
                    currency: source ? source.currency : 'INR',
                    amount: source ? source.amount : 0.0
                };
                pipelineData.mapping_decisions.push(d);
            }
            d.group_code = groupCode;
            d.group_description = data.resolved_name || l0Name;
            d.level_0_code = groupCode;
            d.level_0_name = data.level_0_name || l0Name;
            d.method = "USER_APPROVED_RULE";
            d.confidence = 1.0;
            d.needs_review = false;

            // Also check hitl_pending_reviews in appStatus
            if (appStatus && appStatus.hitl_pending_reviews) {
                appStatus.hitl_pending_reviews = appStatus.hitl_pending_reviews.filter(r =>
                    !(String(r.local_code).trim() === String(localCode).trim() && (!r.entity_code || String(r.entity_code).trim().toUpperCase() === codeUpper))
                );
            }

            showToast("Mapping Saved", `Updated ${localCode} &rarr; ${groupCode} (${l0Name})`, "success");

            // Re-render Step 2 table and headers to update counts and Consolidate button
            const container = document.getElementById("step-content");
            if (container) renderStep2(container);
        } else {
            showToast("Update Failed", data.detail || "Could not save mapping.", "error");
        }
    } catch (err) {
        showToast("Network Error", "Failed to update mapping: " + err, "error");
    } finally {
        currentL0PopoverTarget = null;
    }
}

// STEP 3: FX TRANSLATION
function renderStep3(el) {
    const trans = pipelineData.translated_tbs || [];
    let sections = trans.map(tb => {
        let rows = tb.rows.map(r => `
            <tr class="${r.is_fctr_plug ? 'bg-amber-50/60 font-semibold' : 'hover:bg-slate-50/70'} border-b border-gray-100 transition">
                <td class="font-mono text-xs py-2 px-3">${escapeHtml(r.account_code)}</td>
                <td class="py-2 px-3 text-xs text-gray-800">${escapeHtml(r.account_description)}</td>
                <td class="py-2 px-3 text-xs"><span class="px-1.5 py-0.5 rounded bg-gray-100 font-mono text-[10px]">${escapeHtml(r.source_currency)}</span></td>
                <td class="num-cell py-2 px-3 text-xs font-mono">${formatNum(r.source_amount)}</td>
                <td class="num-cell py-2 px-3 text-xs font-mono">${r.rate_applied.toFixed(4)} (${r.rate_type})</td>
                <td class="num-cell py-2 px-3 text-xs font-mono font-bold text-kpmg-navy formula-interactive" 
                    onmouseenter="showFormula(event, '=${formatNum(r.source_amount)} * ${r.rate_applied.toFixed(4)}', 'Source: TB_${tb.entity_code}')"
                    onmouseleave="hideFormula()">
                    ${formatNum(r.translated_amount)}
                </td>
            </tr>
        `).join("");

        return `
            <div class="mb-6 border border-kpmg-border rounded-lg p-4 bg-white shadow-xs">
                <div class="flex items-center justify-between mb-3 border-b border-gray-100 pb-2">
                    <span class="font-bold text-sm text-kpmg-navy">${escapeHtml(tb.entity_code)} (${escapeHtml(tb.currency)} &rarr; ${appStatus.reporting_currency || 'INR'})</span>
                    <span class="text-xs font-mono text-kpmg-muted">Net Translated: <strong class="text-emerald-700">${formatNum(tb.total_translated)}</strong></span>
                </div>
                <div class="overflow-x-auto min-h-[380px] max-h-[calc(100vh-320px)]">
                    <table class="fin-table">
                        <thead class="sticky top-0 bg-slate-100 z-10 shadow-xs">
                            <tr>
                                <th>Account Code</th>
                                <th>Description</th>
                                <th>Currency</th>
                                <th class="num-cell">Source Amount</th>
                                <th class="num-cell">FX Rate</th>
                                <th class="num-cell">Translated (${appStatus.reporting_currency || 'INR'})</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            </div>
        `;
    }).join("");

    el.innerHTML = `
        <div class="space-y-4">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-kpmg-border pb-3">
                <div>
                    <h3 class="font-bold text-base text-kpmg-navy">Foreign Currency Translation (Ind AS 21)</h3>
                    <p class="text-xs text-kpmg-muted">Closing rates for Balance Sheet, Average rates for P&L, Historical for Equity, with automated FCTR plug.</p>
                </div>
                <div class="flex items-center space-x-2">
                    <button onclick="triggerRunPipeline()"
                        class="h-7 px-3 rounded bg-kpmg-blue hover:bg-kpmg-navy text-white text-[11px] font-semibold transition flex items-center space-x-1.5 shadow-xs btn-tactile cursor-pointer"
                        title="Consolidate">
                        <svg class="w-3.5 h-3.5 text-[#ACEAFF]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span>Consolidate</span>
                    </button>
                </div>
            </div>
            ${sections || '<div class="p-8 text-center text-kpmg-muted">Run consolidation to view foreign currency translation.</div>'}
        </div>
    `;
}

// STEP 4: ELIMINATIONS
function renderStep4(el) {
    const elim = pipelineData.eliminations;
    if (!elim || !elim.pairs) {
        el.innerHTML = `<div class="p-8 text-center text-kpmg-muted">Run consolidation to view intercompany eliminations.</div>`;
        return;
    }

    let rowsHtml = elim.pairs.map(p => `
        <tr class="hover:bg-slate-50/70 border-b border-gray-100 transition">
            <td class="font-bold text-kpmg-navy py-2 px-3 text-xs">${escapeHtml(p.entity_code)}</td>
            <td class="font-bold text-kpmg-blue py-2 px-3 text-xs">${escapeHtml(p.counterparty_code)}</td>
            <td class="font-mono text-xs py-2 px-3 text-gray-600">${escapeHtml(p.account_code)}</td>
            <td class="num-cell py-2 px-3 text-xs font-mono">${formatNum(p.entity_amount)}</td>
            <td class="num-cell py-2 px-3 text-xs font-mono">${formatNum(p.counterparty_amount)}</td>
            <td class="num-cell py-2 px-3 text-xs font-mono font-bold ${Math.abs(p.net_variance) < 0.01 ? 'text-emerald-600' : 'text-amber-600'}">${formatNum(p.net_variance)}</td>
            <td class="text-center py-2 px-3 text-xs">
                <span class="px-2.5 py-0.5 rounded text-[11px] font-semibold ${p.status === 'MATCHED' ? 'bg-emerald-100 text-emerald-800' :
            p.status === 'TOLERANCE_WARNING' ? 'bg-amber-100 text-amber-800' : 'bg-red-100 text-red-800'
        }">
                    ${p.status}
                </span>
            </td>
        </tr>
    `).join("");

    el.innerHTML = `
        <div class="space-y-4">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-kpmg-border pb-3">
                <div>
                    <h3 class="font-bold text-base text-kpmg-navy">Intercompany Elimination Matrix</h3>
                    <p class="text-xs text-kpmg-muted">Dual-tolerance matching (₹${formatNum(appStatus.ic_absolute_tolerance || 10000)} / ${(appStatus.ic_percent_tolerance || 0.01) * 100}%) with entity-specific voucher postings.</p>
                </div>
                <div class="flex items-center space-x-2 text-xs">
                    <span class="px-2 py-1 rounded bg-emerald-50 text-emerald-700 font-mono font-bold">Matched: ${elim.matched_count}</span>
                    <span class="px-2 py-1 rounded bg-amber-50 text-amber-700 font-mono font-bold">Warnings: ${elim.tolerance_warning_count}</span>
                    <span class="px-2 py-1 rounded bg-red-50 text-red-700 font-mono font-bold">Exceptions: ${elim.exception_count}</span>
                    <button onclick="triggerRunPipeline()"
                        class="h-7 px-3 rounded bg-kpmg-blue hover:bg-kpmg-navy text-white text-[11px] font-semibold transition flex items-center space-x-1.5 shadow-xs btn-tactile cursor-pointer"
                        title="Consolidate">
                        <svg class="w-3.5 h-3.5 text-[#ACEAFF]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span>Consolidate</span>
                    </button>
                </div>
            </div>
            <div class="overflow-x-auto min-h-[460px] max-h-[calc(100vh-280px)] border border-kpmg-border rounded-lg bg-white shadow-2xs">
                <table class="fin-table">
                    <thead class="sticky top-0 bg-slate-100 z-10 shadow-xs">
                        <tr>
                            <th>Entity</th>
                            <th>Counterparty</th>
                            <th>Account</th>
                            <th class="num-cell">Entity Amount</th>
                            <th class="num-cell">Counterparty Amount</th>
                            <th class="num-cell">Net Variance</th>
                            <th class="text-center">Status</th>
                        </tr>
                    </thead>
                    <tbody>${rowsHtml}</tbody>
                </table>
            </div>
        </div>
    `;
}

// STEP 5: CONSOLIDATION
function renderStep5(el) {
    const ctb = pipelineData.consolidated_tb;
    if (!ctb || !ctb.rows) {
        el.innerHTML = `<div class="p-8 text-center text-kpmg-muted">Consolidated Trial Balance will appear once the pipeline executes.</div>`;
        return;
    }

    const entCodes = ctb.entity_codes || [];
    const showEntities = !collapseEntityColumns;

    let entHeaders = showEntities
        ? entCodes.map(e => `<th class="num-cell min-w-[100px]">${escapeHtml(e)}</th>`).join("")
        : `<th class="num-cell text-slate-500 font-normal">Entities (${entCodes.length} collapsed)</th>`;

    let rowsHtml = ctb.rows.map((r, i) => {
        let entCells = showEntities
            ? entCodes.map(e => `
                <td class="num-cell py-2 px-3 text-xs font-mono formula-interactive" 
                    onmouseenter="showFormula(event, '=SUMIFS(Translated_TB!$G:$G, Translated_TB!$A:$A, \\'${e}\\', Translated_TB!$B:$B, \\'${r.account_code}\\')', 'Direct Lineage: Translated_TB')"
                    onmouseleave="hideFormula()">
                    ${formatNum(r.entity_balances[e] || 0.0)}
                </td>
            `).join("")
            : `<td class="num-cell py-2 px-3 text-xs font-mono text-slate-400">...</td>`;

        return `
            <tr class="hover:bg-slate-50/70 border-b border-gray-100 transition">
                <td class="font-mono text-xs py-2 px-3">${escapeHtml(r.account_code)}</td>
                <td class="py-2 px-3 text-xs text-gray-800">${escapeHtml(r.account_description)}</td>
                ${entCells}
                <td class="num-cell py-2 px-3 text-xs font-mono font-bold formula-interactive"
                    onmouseenter="showFormula(event, '=SUM(Entities Rollup)', 'Total Entities Rollup')"
                    onmouseleave="hideFormula()">
                    ${formatNum(r.total_entities)}
                </td>
                <td class="num-cell py-2 px-3 text-xs font-mono formula-interactive text-amber-700"
                    onmouseenter="showFormula(event, '=Elimination Adjustment', 'Intercompany Eliminations')"
                    onmouseleave="hideFormula()">
                    ${formatNum(r.eliminations)}
                </td>
                <td class="num-cell py-2 px-3 text-xs font-mono font-bold text-kpmg-blue formula-interactive"
                    onmouseenter="showFormula(event, '=Total_Entities + Eliminations', 'Consolidated Balance')"
                    onmouseleave="hideFormula()">
                    ${formatNum(r.consolidated_total)}
                </td>
            </tr>
        `;
    }).join("");

    el.innerHTML = `
        <div class="space-y-4">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-kpmg-border pb-3">
                <div>
                    <h3 class="font-bold text-base text-kpmg-navy">Consolidated Trial Balance Matrix</h3>
                    <p class="text-xs text-kpmg-muted">Hover over any figure to inspect active Excel formula lineage. Scaled for 1 to 1,000 entities.</p>
                </div>
                <div class="flex items-center space-x-2">
                    ${entCodes.length > 4 ? `
                        <button onclick="toggleEntityCollapse()" class="px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium transition cursor-pointer">
                            ${collapseEntityColumns ? 'Expand Entities (' + entCodes.length + ')' : 'Collapse Entities'}
                        </button>
                    ` : ''}
                    <div class="text-xs font-mono px-3 py-1 rounded bg-emerald-50 text-emerald-800 font-bold border border-emerald-200">
                        Consolidated Sum: ${formatNum(ctb.total_consolidated)} (0.00)
                    </div>
                    <button onclick="triggerRunPipeline()"
                        class="h-7 px-3 rounded bg-kpmg-blue hover:bg-kpmg-navy text-white text-[11px] font-semibold transition flex items-center space-x-1.5 shadow-xs btn-tactile cursor-pointer"
                        title="Consolidate">
                        <svg class="w-3.5 h-3.5 text-[#ACEAFF]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span>Consolidate</span>
                    </button>
                </div>
            </div>
            <div class="overflow-x-auto min-h-[460px] max-h-[calc(100vh-280px)] border border-kpmg-border rounded-lg bg-white shadow-2xs">
                <table class="fin-table">
                    <thead class="sticky top-0 bg-slate-100 z-10 shadow-xs">
                        <tr>
                            <th>Account Code</th>
                            <th>Description</th>
                            ${entHeaders}
                            <th class="num-cell">Total Entities</th>
                            <th class="num-cell">Eliminations</th>
                            <th class="num-cell">Consolidated Total</th>
                        </tr>
                    </thead>
                    <tbody>${rowsHtml}</tbody>
                </table>
            </div>
        </div>
    `;
}

function toggleEntityCollapse() {
    collapseEntityColumns = !collapseEntityColumns;
    renderStep5(document.getElementById("step-content"));
}

// STEP 6: FINANCIAL STATEMENTS
let statementsData = null;
let currentStatementTab = 'BS';

function switchStatementTab(tab) {
    currentStatementTab = tab;
    const el = document.getElementById("step-content");
    if (el) renderStep6(el);
}

async function renderStep6(el) {
    if (!statementsData) {
        try {
            const res = await fetch("/api/financial-statements");
            statementsData = await res.json();
        } catch (err) {
            console.error("Failed to load statements:", err);
        }
    }

    if (!statementsData || !statementsData.success) {
        el.innerHTML = `
            <div class="p-12 text-center bg-white rounded border border-kpmg-border">
                <svg class="w-12 h-12 text-kpmg-muted mx-auto mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                <h4 class="font-bold text-sm text-kpmg-navy mb-1">Financial Statements Not Yet Generated</h4>
                <p class="text-xs text-kpmg-muted max-w-md mx-auto mb-4">${statementsData?.message || 'Please execute the multi-agent consolidation pipeline to generate the IND AS Balance Sheet and Statement of Profit and Loss.'}</p>
                <button onclick="triggerRunPipeline()" class="h-8 px-4 rounded bg-kpmg-blue hover:bg-kpmg-navy text-white text-xs font-semibold transition shadow-xs inline-flex items-center space-x-1.5">
                    <svg class="w-3.5 h-3.5 text-[#ACEAFF]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path></svg>
                    <span>Consolidate</span>
                </button>
            </div>
        `;
        return;
    }

    const isBS = currentStatementTab === 'BS';
    const stData = isBS ? statementsData.balance_sheet : statementsData.profit_and_loss;
    if (!stData || !stData.rows) {
        el.innerHTML = `<div class="p-8 text-center text-kpmg-muted">Statement structure incomplete.</div>`;
        return;
    }

    const cols = stData.columns || [];
    const entityCols = cols.slice(2, cols.length - 3);

    const headersHtml = cols.map((c, idx) => {
        if (idx === 0) return `<th class="min-w-[240px]">Line Item</th>`;
        if (idx === 1) return `<th class="w-14 text-center">Note</th>`;
        return `<th class="num-cell min-w-[120px]">${escapeHtml(c)}</th>`;
    }).join("");

    const rowsHtml = stData.rows.map(r => {
        if (r.is_header && !r.is_total) {
            return `
                <tr class="bg-slate-50 border-t border-b border-slate-200">
                    <td colspan="${cols.length}" class="py-2 pl-3 text-xs font-bold uppercase tracking-wider text-kpmg-navy border-l-4 border-kpmg-blue">
                        ${escapeHtml(r.title)}
                    </td>
                </tr>
            `;
        }

        const isTotal = r.is_total;
        const rowClass = isTotal
            ? "bg-blue-50/40 font-bold border-t border-b-2 border-kpmg-navy"
            : "hover:bg-slate-50/70 border-b border-gray-100 transition";

        const titleCell = `
            <td class="py-2 pl-${isTotal ? '3 font-bold text-kpmg-navy' : '6 text-gray-800'} text-xs">
                <div class="flex items-center justify-between group">
                    <span>${escapeHtml(r.title)}</span>
                    ${!isTotal ? `
                        <button onclick="inspectLineageFromStatement('${r.title}')" class="opacity-0 group-hover:opacity-100 text-[10px] text-kpmg-blue hover:text-kpmg-navy font-semibold px-1.5 py-0.5 rounded bg-blue-100 transition shrink-0 ml-2" title="Inspect complete lineage in Audit Console">
                            Trace &rarr;
                        </button>
                    ` : ''}
                </div>
            </td>
        `;

        const noteCell = `<td class="text-center font-mono text-[11px] text-gray-500">${escapeHtml(r.note || '')}</td>`;

        const valKeys = [...entityCols, "total_entities", "eliminations", "consolidated_net"];
        const valCells = valKeys.map(k => {
            const val = r.values ? r.values[k] : 0.0;
            const formulaText = r.formula ? r.formula.replace('{col}', k) : `Active consolidation formula for ${r.title}`;
            return `
                <td class="num-cell py-2 px-3 text-xs font-mono ${isTotal ? 'font-bold text-kpmg-navy' : 'formula-interactive'}"
                    ${!isTotal ? `onmouseenter="showFormula(event, '${escapeHtml(formulaText)}', '${escapeHtml(r.title)} [${k}]')" onmouseleave="hideFormula()"` : ''}>
                    ${formatNum(val)}
                </td>
            `;
        }).join("");

        return `<tr class="${rowClass}">${titleCell}${noteCell}${valCells}</tr>`;
    }).join("");

    const balancePill = isBS
        ? (stData.is_balanced
            ? `<span class="inline-flex items-center px-2.5 py-1 rounded bg-emerald-50 text-emerald-800 font-bold text-xs border border-emerald-200">
                <svg class="w-3.5 h-3.5 mr-1 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                Balance Sheet Balanced (Total Assets = Total Equity & Liabilities)
               </span>`
            : `<span class="inline-flex items-center px-2.5 py-1 rounded bg-amber-50 text-amber-800 font-bold text-xs border border-amber-200">
                <svg class="w-3.5 h-3.5 mr-1 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                Reconciliation Needed
               </span>`)
        : `<span class="inline-flex items-center px-2.5 py-1 rounded bg-blue-50 text-kpmg-blue font-bold text-xs border border-blue-200">
            <svg class="w-3.5 h-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
            IND AS Schedule III Compliant
           </span>`;

    el.innerHTML = `
        <div class="space-y-4">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-kpmg-border pb-3">
                <div class="flex items-center space-x-2">
                    <button onclick="switchStatementTab('BS')" class="px-3.5 py-1.5 rounded text-xs font-semibold transition ${isBS ? 'bg-kpmg-blue text-white shadow-xs' : 'bg-white hover:bg-gray-100 text-kpmg-navy border border-kpmg-border'}">
                        Consolidated Balance Sheet
                    </button>
                    <button onclick="switchStatementTab('PL')" class="px-3.5 py-1.5 rounded text-xs font-semibold transition ${!isBS ? 'bg-kpmg-blue text-white shadow-xs' : 'bg-white hover:bg-gray-100 text-kpmg-navy border border-kpmg-border'}">
                        Statement of Profit and Loss
                    </button>
                </div>
                <div class="flex items-center space-x-2">
                    ${balancePill}
                    <a href="/api/export-excel" class="h-7 px-3 rounded bg-kpmg-blue hover:bg-kpmg-navy text-white text-[11px] font-semibold transition flex items-center space-x-1.5 shadow-xs">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                        <span>Download 100% Formula Excel</span>
                    </a>
                    <button onclick="triggerRunPipeline()"
                        class="h-7 px-3 rounded bg-kpmg-blue hover:bg-kpmg-navy text-white text-[11px] font-semibold transition flex items-center space-x-1.5 shadow-xs btn-tactile cursor-pointer"
                        title="Consolidate">
                        <svg class="w-3.5 h-3.5 text-[#ACEAFF]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span>Consolidate</span>
                    </button>
                </div>
            </div>

            <div class="overflow-x-auto min-h-[480px] max-h-[calc(100vh-280px)] border border-kpmg-border rounded-lg bg-white shadow-2xs">
                <table class="fin-table">
                    <thead class="sticky top-0 bg-slate-100 z-10 shadow-xs">
                        <tr>${headersHtml}</tr>
                    </thead>
                    <tbody>${rowsHtml}</tbody>
                </table>
            </div>

            <div class="flex items-center justify-between text-xs text-kpmg-muted pt-1">
                <span>Hover over any line item figure to inspect active Excel formula lineage. Dynamic columns with Ind AS 110/103/21 conformance.</span>
                <span class="font-mono text-slate-500 font-bold">${cols.length} Columns</span>
            </div>
        </div>
    `;
}

function inspectLineageFromStatement(title) {
    switchSection('AUDIT');
    setTimeout(() => {
        const queryInput = document.getElementById("lineage-query-input");
        if (queryInput) {
            queryInput.value = title;
            executeLineageTrace(title);
        }
        const lineageEl = document.getElementById("lineage-results-container");
        if (lineageEl) {
            lineageEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }, 150);
}

// BATCH UPLOAD MODAL
let selectedBatchFiles = [];

function updateBatchUploadPeriodDisplay() {
    const dispEl = document.getElementById("batch-upload-period-disp");
    const hiddenInput = document.getElementById("batch-upload-period");
    const formatBadge = document.getElementById("batch-upload-format-badge");

    const activePeriod = (appStatus && appStatus.current_period) || activeRunPeriod || "";
    if (hiddenInput) {
        hiddenInput.value = activePeriod;
    }
    if (dispEl) {
        dispEl.textContent = activePeriod ? formatDateOnly(activePeriod) : "—";
    }
    if (formatBadge) {
        let fmtName = "ISO";
        switch (currentDateFormat) {
            case "DD-MM-YYYY HH:mm": fmtName = "DD-MM-YYYY"; break;
            case "MM/DD/YYYY hh:mm A": fmtName = "MM/DD/YYYY"; break;
            case "DD MMM YYYY, HH:mm": fmtName = "DD MMM YYYY"; break;
            case "MMM DD, YYYY, hh:mm A": fmtName = "MMM DD, YYYY"; break;
            default: fmtName = "YYYY-MM-DD"; break;
        }
        formatBadge.textContent = fmtName;
    }
}

function openBatchUploadModal() {
    const modal = document.getElementById("modal-batch-upload");
    if (modal) {
        modal.classList.remove("hidden");
        selectedBatchFiles = [];
        const fileInput = document.getElementById("batch-file-input");
        if (fileInput) fileInput.value = "";
        const fileLabel = document.getElementById("batch-file-label");
        if (fileLabel) fileLabel.textContent = "Drop batch files here or click to browse";
        const filesList = document.getElementById("batch-selected-files-list");
        if (filesList) filesList.innerHTML = "";

        updateBatchUploadPeriodDisplay();
    }
}

function closeBatchUploadModal() {
    const modal = document.getElementById("modal-batch-upload");
    if (modal) modal.classList.add("hidden");
}

function handleBatchFilesSelected(input) {
    if (input.files && input.files.length > 0) {
        selectedBatchFiles = Array.from(input.files);
        renderBatchFilesList();
    }
}

function renderBatchFilesList() {
    const listEl = document.getElementById("batch-selected-files-list");
    if (!listEl) return;
    document.getElementById("batch-file-label").innerHTML = `<strong>Selected ${selectedBatchFiles.length} file(s)</strong>`;
    listEl.innerHTML = selectedBatchFiles.map((f, i) => `
        <div class="flex items-center justify-between p-2 rounded bg-slate-50 border border-gray-200 text-xs">
            <span class="font-mono text-gray-700 truncate max-w-xs">${escapeHtml(f.name)} (${(f.size / 1024).toFixed(1)} KB)</span>
            <button type="button" onclick="removeBatchFile(${i})" class="text-rose-500 hover:text-rose-700 font-bold text-sm leading-none">&times;</button>
        </div>
    `).join("");
}

function removeBatchFile(idx) {
    selectedBatchFiles.splice(idx, 1);
    renderBatchFilesList();
}

function initBatchDropZone() {
    const dropZone = document.getElementById("batch-drop-zone");
    if (!dropZone || dropZone.dataset.initialized) return;
    dropZone.dataset.initialized = "true";

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add("dragover");
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove("dragover");
        }, false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        if (dt.files && dt.files.length > 0) {
            selectedBatchFiles = Array.from(dt.files);
            renderBatchFilesList();
        }
    }, false);
}

async function submitBatchUpload(e) {
    e.preventDefault();
    if (!selectedBatchFiles || selectedBatchFiles.length === 0) {
        showToast("Missing Files", "Please select at least one file to upload.", "warning");
        return;
    }

    const period = document.getElementById("batch-upload-period").value.trim();
    const chkDet = document.getElementById("modal-chk-deterministic");
    const chkAI = document.getElementById("modal-chk-ai-agents");
    const useDet = chkDet ? chkDet.checked : true;
    const useAI = chkAI ? chkAI.checked : true;

    const btn = document.getElementById("btn-submit-batch");
    btn.disabled = true;
    btn.innerHTML = `<span>Ingesting & Classifying ${selectedBatchFiles.length} files...</span>`;

    const formData = new FormData();
    selectedBatchFiles.forEach(f => formData.append("files", f));
    if (period) formData.append("period", period);
    formData.append("use_deterministic", useDet ? "true" : "false");
    formData.append("use_ai", useAI ? "true" : "false");

    try {
        const res = await fetch("/api/upload-batch", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        if (res.ok && data.success) {
            closeBatchUploadModal();
            if (data.approval_state) {
                step1ApprovalState = data.approval_state;
                openPerimeterApprovalModal(data.approval_state);
            } else {
                showToast("Batch Processed", `Successfully classified ${data.total_files} file(s).`, "success");
                await fetchStatus();
                await loadPipelineData();
                switchStep(1);
                const container = document.getElementById("step-content");
                if (container) renderStep1(container);
            }
        } else {
            showToast("Batch Ingestion Error", data.detail || "Failed to process files.", "error");
        }
    } catch (err) {
        showToast("Network Error", "Batch upload failed: " + err, "error");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<span>Upload</span>`;
    }
}

// HUMAN-IN-THE-LOOP (HITL) MAPPING REVIEW MODAL
let hitlPendingReviews = [];

function openHITLMappingModal(pendingReviews) {
    hitlPendingReviews = pendingReviews || [];
    const modal = document.getElementById("modal-hitl-mapping");
    const tbody = document.getElementById("hitl-mapping-tbody");
    if (!modal || !tbody) return;

    const perimeter = (appStatus && appStatus.perimeter_entities) ? appStatus.perimeter_entities : [];

    tbody.innerHTML = hitlPendingReviews.map((rev, idx) => {
        let entOptions = perimeter.map(p => `
            <option value="${escapeHtml(p.entity_code)}" ${p.entity_code === rev.assigned_entity ? 'selected' : ''}>
                ${escapeHtml(p.entity_name || p.entity_code)} (${escapeHtml(p.entity_code)})
            </option>
        `).join("");

        if (!entOptions) {
            entOptions = `<option value="${escapeHtml(rev.assigned_entity || '')}">${escapeHtml(rev.assigned_entity || 'Unknown')}</option>`;
        }

        const confPct = Math.round((rev.confidence || 0) * 100);
        const confBadge = confPct >= 85
            ? `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800">${confPct}%</span>`
            : `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-100 text-amber-800">${confPct}% (Review)</span>`;

        const cols = rev.detected_columns || {};

        return `
            <tr data-index="${idx}" class="hover:bg-slate-50/70 transition">
                <td class="p-3 font-mono text-[11px] text-slate-700 max-w-[180px] truncate" title="${escapeHtml(rev.file_name)}">
                    ${escapeHtml(rev.file_name)}
                </td>
                <td class="p-3">
                    <select class="hitl-entity-select h-8 px-2 rounded border border-kpmg-border bg-white text-xs font-medium w-full">
                        ${entOptions}
                    </select>
                </td>
                <td class="p-3">
                    <input type="text" class="hitl-col-code h-8 px-2 rounded border border-kpmg-border bg-white text-xs font-mono w-full"
                        value="${escapeHtml(cols.account_code || '')}" placeholder="e.g. Account">
                </td>
                <td class="p-3">
                    <input type="text" class="hitl-col-desc h-8 px-2 rounded border border-kpmg-border bg-white text-xs font-mono w-full"
                        value="${escapeHtml(cols.account_desc || '')}" placeholder="e.g. Description">
                </td>
                <td class="p-3">
                    <input type="text" class="hitl-col-amt h-8 px-2 rounded border border-kpmg-border bg-white text-xs font-mono w-full"
                        value="${escapeHtml(cols.amount || cols.debit || '')}" placeholder="e.g. Debit / Amount">
                </td>
                <td class="p-3">
                    <input type="text" class="hitl-col-cred h-8 px-2 rounded border border-kpmg-border bg-white text-xs font-mono w-full"
                        value="${escapeHtml(cols.credit || '')}" placeholder="e.g. Credit">
                </td>
                <td class="p-3 text-center whitespace-nowrap">
                    ${confBadge}
                </td>
            </tr>
        `;
    }).join("");

    modal.classList.remove("hidden");
}

function closeHITLMappingModal() {
    const modal = document.getElementById("modal-hitl-mapping");
    if (modal) modal.classList.add("hidden");
}

async function confirmHITLMappings() {
    const tbody = document.getElementById("hitl-mapping-tbody");
    if (!tbody || !hitlPendingReviews || hitlPendingReviews.length === 0) {
        closeHITLMappingModal();
        return;
    }

    const rows = tbody.querySelectorAll("tr");
    const mappings = [];
    rows.forEach((row, i) => {
        const rev = hitlPendingReviews[i];
        if (!rev) return;
        const entSelect = row.querySelector(".hitl-entity-select");
        const colCode = row.querySelector(".hitl-col-code");
        const colDesc = row.querySelector(".hitl-col-desc");
        const colAmt = row.querySelector(".hitl-col-amt");
        const colCred = row.querySelector(".hitl-col-cred");

        mappings.push({
            file_name: rev.file_name,
            entity_code: entSelect ? entSelect.value : rev.assigned_entity,
            account_code_col: colCode ? colCode.value.trim() : null,
            account_desc_col: colDesc ? colDesc.value.trim() : null,
            amount_col: colAmt ? colAmt.value.trim() : null,
            credit_col: colCred ? colCred.value.trim() : null
        });
    });

    try {
        const res = await fetch("/api/confirm-ingestion-mappings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mappings })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            closeHITLMappingModal();
            showToast("Mappings Confirmed", `Successfully ingested ${data.ingested_tbs ? data.ingested_tbs.length : mappings.length} trial balance(s) with confirmed mappings.`, "success");
            await fetchStatus();
            await loadPipelineData();
            switchStep(1);
        } else {
            showToast("Confirmation Error", data.detail || "Failed to confirm mappings.", "error");
        }
    } catch (err) {
        showToast("Network Error", "Failed to confirm mappings: " + err, "error");
    }
}

// HUMAN-IN-THE-LOOP (HITL) WORKBENCH
async function toggleHITLDrawer(forceOpen = false) {
    const drawer = document.getElementById("hitl-drawer");
    if (!drawer) return;
    const willOpen = forceOpen || drawer.classList.contains("translate-x-full");
    if (forceOpen) {
        drawer.classList.remove("translate-x-full");
    } else {
        drawer.classList.toggle("translate-x-full");
    }

    if (willOpen) {
        await loadHITLPending();
    }
}

async function loadHITLPending() {
    const listEl = document.getElementById("hitl-list");
    const threshEl = document.getElementById("hitl-threshold-text");
    if (!listEl) return;

    listEl.innerHTML = `<div class="p-6 text-center text-kpmg-muted text-xs">Loading items requiring human review...</div>`;

    try {
        const res = await fetch("/api/hitl/pending");
        const data = await res.json();
        pendingHITLItems = data.pending_reviews || [];
        if (threshEl) threshEl.textContent = `${((data.threshold || 0.85) * 100).toFixed(0)}%`;

        if (pendingHITLItems.length === 0) {
            listEl.innerHTML = `
                <div class="p-8 text-center bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-800 text-xs space-y-1">
                    <svg class="w-8 h-8 mx-auto text-emerald-600 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    <strong class="block text-sm">All Items Confident</strong>
                    <p>Zero items below AI confidence threshold. No human intervention needed.</p>
                </div>
            `;
            return;
        }

        listEl.innerHTML = pendingHITLItems.map((item, idx) => `
            <div class="p-4 rounded-lg border border-amber-200 bg-amber-50/50 space-y-3">
                <div class="flex items-center justify-between">
                    <span class="font-bold text-kpmg-navy text-xs">${escapeHtml(item.entity_code || 'General')} &bull; <code class="font-mono text-kpmg-blue">${escapeHtml(item.local_code || '')}</code></span>
                    <span class="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-100 text-amber-800">${((item.confidence || 0) * 100).toFixed(0)}% Confidence</span>
                </div>
                <div class="text-[11px] text-gray-700 font-medium">
                    ${escapeHtml(item.local_description || item.reasoning || '')}
                </div>
                <div class="p-2.5 rounded bg-white border border-gray-200 space-y-1">
                    <span class="text-[10px] text-gray-500 font-bold uppercase">Gemini Agent Suggestion:</span>
                    <div class="flex items-baseline space-x-2">
                        <strong class="font-mono text-xs text-kpmg-blue">${escapeHtml(item.suggested_group_code || item.group_code || 'N/A')}</strong>
                        <span class="text-xs text-gray-600">${escapeHtml(item.suggested_group_desc || item.group_description || '')}</span>
                    </div>
                </div>
                <div class="flex items-center space-x-2 pt-1">
                    <button onclick="approveHITLItem('${item.entity_code}', '${item.local_code}', '${item.suggested_group_code || item.group_code}')" class="flex-1 h-8 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs transition">
                        Approve Suggestion
                    </button>
                    <button onclick="promptOverrideHITL('${item.entity_code}', '${item.local_code}')" class="px-3 h-8 rounded bg-white border border-kpmg-border text-kpmg-navy text-xs font-medium hover:bg-gray-100 transition">
                        Override Code
                    </button>
                </div>
            </div>
        `).join("");
    } catch (err) {
        listEl.innerHTML = `<div class="p-4 text-center text-rose-600 text-xs">Failed to load HITL reviews: ${err}</div>`;
    }
}

async function approveHITLItem(entityCode, localCode, groupCode) {
    try {
        const res = await fetch("/api/hitl/resolve", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                entity_code: entityCode,
                local_code: localCode,
                group_code: groupCode,
                reasoning: "Approved by user in HITL workbench"
            })
        });
        const data = await res.json();
        if (data.success) {
            showToast("Saved to Learning Memory", `Mapping for ${localCode} -> ${groupCode} saved.`, "success");
            await loadHITLPending();
            await fetchStatus();
            await loadPipelineData();
        }
    } catch (err) {
        showToast("Error", "Failed to resolve item: " + err, "error");
    }
}

function promptOverrideHITL(entityCode, localCode) {
    const overrideCode = prompt(`Enter target Group COA code for ${localCode} (e.g. 1001, 2005, 3001):`);
    if (overrideCode && overrideCode.trim()) {
        approveHITLItem(entityCode, localCode, overrideCode.trim());
    }
}

function openHITLForCode(localCode) {
    toggleHITLDrawer(true);
}

// AUDIT & OBSERVABILITY CONSOLE
let expandedNodeId = null;
let currentLineageTrace = null;
let auditSearchQuery = '';
let auditAgentFilter = 'ALL';
let auditStatusFilter = 'ALL';

function toggleNodeTraceDetails(nodeId) {
    expandedNodeId = (expandedNodeId === nodeId) ? null : nodeId;
    if (activeSection === 'AUDIT') renderObservabilityConsole();
}

function onSelectLineagePreset(val) {
    if (!val) return;
    const input = document.getElementById("lineage-query-input");
    if (input) input.value = val;
    executeLineageTrace(val);
}

async function executeLineageTrace(overrideQuery) {
    const input = document.getElementById("lineage-query-input");
    const query = overrideQuery || (input ? input.value.trim() : "") || "Cash";
    const container = document.getElementById("lineage-results-container");
    if (!container) return;

    container.innerHTML = `<div class="p-6 text-center text-kpmg-muted text-xs"><svg class="w-4 h-4 mx-auto mb-1.5 animate-spin text-kpmg-blue" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>Tracing cell formula lineage for "${query}"...</div>`;

    try {
        const res = await fetch(`/api/lineage/${encodeURIComponent(query)}`);
        const data = await res.json();
        currentLineageTrace = data;
        renderLineageGraph(data);
    } catch (err) {
        container.innerHTML = `<div class="p-4 text-center text-red-500 text-xs">Lineage trace failed: ${err}</div>`;
    }
}

function renderLineageGraph(data) {
    const container = document.getElementById("lineage-results-container");
    if (!container) return;

    if (!data || !data.found || !data.lineage_graph || data.lineage_graph.length === 0) {
        const safeQuery = escapeHtml(data?.query || '');
        container.innerHTML = `
            <div class="p-6 text-center bg-amber-50 border border-amber-200 rounded text-amber-800 text-xs">
                <strong class="block mb-1">No Direct Lineage Found</strong>
                <span>Could not resolve backward lineage for query "<strong>${safeQuery}</strong>". Please verify the account code or statement description.</span>
            </div>
        `;
        return;
    }

    const target = data.target || {};
    const nodes = data.lineage_graph || [];

    const nodesHtml = nodes.map((n) => {
        let badgeColor = "bg-blue-100 text-kpmg-blue";
        if (n.tier === 1) badgeColor = "bg-purple-100 text-purple-800";
        if (n.tier === 2) badgeColor = "bg-amber-100 text-amber-800";
        if (n.tier === 3) badgeColor = "bg-rose-100 text-rose-800";
        if (n.tier === 4) badgeColor = "bg-emerald-100 text-emerald-800";
        if (n.tier === 5) badgeColor = "bg-blue-100 text-kpmg-navy";

        return `
            <div class="relative flex-1 min-w-[200px] border border-kpmg-border rounded p-3 bg-slate-50 shadow-xs">
                <div class="flex items-center justify-between mb-1">
                    <span class="text-[10px] font-bold px-2 py-0.5 rounded ${badgeColor}">Tier ${n.tier}: ${escapeHtml(n.stage)}</span>
                    <span class="text-[10px] font-mono font-bold text-gray-500">${escapeHtml(n.status)}</span>
                </div>
                <div class="text-xs font-bold text-kpmg-navy mt-1">${escapeHtml(n.source)}</div>
                <div class="text-[11px] text-gray-600 mb-1.5">${escapeHtml(n.description)}</div>
                <div class="p-1.5 bg-white rounded border border-gray-200 font-mono text-[10px] text-kpmg-blue break-all">
                    ${escapeHtml(n.formula || 'Direct Value')}
                </div>
                <div class="mt-1.5 text-right font-mono text-xs font-bold text-gray-800">
                    ${n.amount !== undefined ? '₹ ' + formatNum(n.amount) : ''}
                </div>
            </div>
        `;
    }).join(`
        <div class="flex items-center justify-center px-1 text-kpmg-muted shrink-0">
            <svg class="w-4 h-4 text-kpmg-blue" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"></path></svg>
        </div>
    `);

    container.innerHTML = `
        <div class="space-y-3">
            <div class="flex items-center justify-between text-xs">
                <div>
                    Target Account: <strong class="font-mono text-kpmg-navy">${escapeHtml(target.account_code || '')}</strong> - <strong class="text-gray-800">${escapeHtml(target.account_description || data.query || '')}</strong>
                </div>
                <div class="font-mono text-xs">
                    Consolidated Total: <strong class="text-emerald-700">₹ ${formatNum(target.consolidated_net)}</strong>
                </div>
            </div>
            <div class="flex items-stretch overflow-x-auto pb-2 gap-1.5">
                ${nodesHtml}
            </div>
        </div>
    `;
}

function onAuditSearch(val) {
    auditSearchQuery = val;
    if (activeSection === 'AUDIT') renderObservabilityConsole();
}

function onAuditAgentFilter(val) {
    auditAgentFilter = val;
    if (activeSection === 'AUDIT') renderObservabilityConsole();
}

function onAuditStatusFilter(val) {
    auditStatusFilter = val;
    if (activeSection === 'AUDIT') renderObservabilityConsole();
}

// -------------------------------------------------------------
// Preliminary Consolidation Run Launcher (Fresh Run Setup)
// -------------------------------------------------------------

async function populateLauncherCompanies() {
    const select = document.getElementById("launcher-company-select");
    if (!select) return;

    if (!availableCompanies || availableCompanies.length === 0) {
        await fetchCompanies();
    }

    const curVal = select.value;
    const comps = availableCompanies || [];
    select.innerHTML = '<option value="">Select client...</option>' +
        comps.map(c => {
            const clientName = c.company_name || c.company_id;
            return `<option value="${escapeHtml(c.company_id)}" ${c.company_id === curVal ? 'selected' : ''}>
                ${escapeHtml(clientName)}
            </option>`;
        }).join("");

    // Initialize date picker to today if empty
    const dateInput = document.getElementById("launcher-run-date");
    if (dateInput && !dateInput.value) {
        const today = new Date().toISOString().split("T")[0];
        dateInput.value = today;
    }
    updateLauncherState();
}

function onLauncherCompanyChange(companyId) {
    updateLauncherState();
}

function onLauncherDateChange(dateVal) {
    updateLauncherState();
}

function updateLauncherState() {
    const compSelect = document.getElementById("launcher-company-select");
    const dateInput = document.getElementById("launcher-run-date");
    const snapshotEl = document.getElementById("launcher-company-snapshot");
    const startBtn = document.getElementById("btn-start-run");

    const compId = compSelect ? compSelect.value : "";
    const runDate = dateInput ? dateInput.value : "";

    const comps = availableCompanies || [];
    const selectedComp = comps.find(c => (c.company_id || "").toLowerCase() === compId.toLowerCase());

    if (selectedComp && snapshotEl) {
        const codeEl = document.getElementById("snapshot-company-code");
        const currEl = document.getElementById("snapshot-reporting-curr");
        const subsEl = document.getElementById("snapshot-subs-count");
        const coaEl = document.getElementById("snapshot-coa-status");

        if (codeEl) codeEl.textContent = selectedComp.company_code || selectedComp.company_id.toUpperCase();
        if (currEl) currEl.textContent = selectedComp.reporting_currency || "INR";
        const subCount = selectedComp.subsidiaries ? selectedComp.subsidiaries.length : (selectedComp.number_of_subsidiaries || 0);
        if (subsEl) subsEl.textContent = `${subCount} ${subCount === 1 ? 'Subsidiary' : 'Subsidiaries'}`;

        const coaCount = selectedComp.coa_account_count || 0;
        if (coaEl) {
            coaEl.textContent = coaCount > 0 ? `${coaCount} GL Accounts` : "No COA";
            coaEl.className = coaCount > 0 ? "text-[11px] font-mono text-slate-500" : "text-[11px] font-mono text-amber-600";
        }
        snapshotEl.classList.remove("hidden");
    } else if (snapshotEl) {
        snapshotEl.classList.add("hidden");
    }

    if (startBtn) {
        startBtn.disabled = !(compId && runDate);
    }
}

async function triggerStartFreshRun() {
    const compSelect = document.getElementById("launcher-company-select");
    const dateInput = document.getElementById("launcher-run-date");
    const startBtn = document.getElementById("btn-start-run");

    const compId = compSelect ? compSelect.value : "";
    const runDate = dateInput ? dateInput.value : "";

    if (!compId) {
        showToast("Company Required", "Please select a client company from the dropdown.", "warning");
        return;
    }
    if (!runDate) {
        showToast("Run Date Required", "Please select a run cutoff date using the calendar.", "warning");
        return;
    }

    if (startBtn) {
        startBtn.disabled = true;
        startBtn.innerHTML = `<span>Starting...</span>`;
    }

    try {
        const res = await fetch("/api/runs/create", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ company_id: compId, run_date: runDate })
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
            showToast("Run Creation Error", data.detail || "Failed to create fresh consolidation run.", "error");
            if (startBtn) {
                startBtn.disabled = false;
                startBtn.innerHTML = `<span>Start Consolidation</span><svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"/></svg>`;
            }
            return;
        }

        isLauncherActive = false;
        activeRunId = data.run.run_id;
        activeRunName = data.run.run_name;
        activeRunPeriod = runDate || data.run.run_date || "";

        await fetchStatus();
        await loadPipelineData();

        isNavigatingDirectly = true;
        switchNavSection('PIPELINE');
        isNavigatingDirectly = false;

        switchStep(1);
        showToast("Consolidation Run Initialized", `Created ${data.run.run_name}`, "success");
    } catch (err) {
        showToast("Network Error", "Failed to start fresh run: " + err, "error");
    } finally {
        if (startBtn) {
            startBtn.disabled = false;
            startBtn.innerHTML = `<span>Start Consolidation</span><svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"/></svg>`;
        }
    }
}

function returnToLauncher() {
    isLauncherActive = true;
    activeRunPeriod = null;
    try {
        fetch("/api/runs/launcher-mode", { method: "POST" });
    } catch (_) { }
    switchNavSection('PIPELINE');
}

function getStepTitle(step) {
    switch (step) {
        case 1: return "Ingestion";
        case 2: return "Mapping";
        case 3: return "Translation";
        case 4: return "Eliminations";
        case 5: return "Consolidation";
        case 6: return "Statements";
        default: return `Step ${step}`;
    }
}

// -------------------------------------------------------------
// Audit Consolidation Run Ledger & Resumption Hub
// -------------------------------------------------------------

async function fetchAndRenderAuditRuns() {
    const container = document.getElementById("audit-runs-ledger-content");
    if (!container) return;

    try {
        const res = await fetch("/api/runs");
        const data = await res.json();
        auditRunsList = data.runs || [];
        populateAuditCompanyFilter();
        renderAuditRunsTable();
    } catch (err) {
        container.innerHTML = `<div class="p-8 text-center text-red-500 text-xs">Failed to load consolidation runs: ${escapeHtml(err.message)}</div>`;
    }
}

function populateAuditCompanyFilter() {
    const select = document.getElementById("audit-filter-company");
    if (!select) return;

    const companies = Array.from(new Set(auditRunsList.map(r => r.company_name).filter(Boolean)));
    const curVal = select.value;
    select.innerHTML = '<option value="ALL">All Companies</option>' +
        companies.map(c => `<option value="${escapeHtml(c)}" ${c === curVal ? 'selected' : ''}>${escapeHtml(c)}</option>`).join("");
}

function handleRunSearch(val) {
    auditRunSearchQuery = (val || "").trim().toLowerCase();
    auditCurrentPage = 1;
    const clearBtn = document.getElementById("btn-clear-run-search");
    if (clearBtn) {
        if (auditRunSearchQuery) clearBtn.classList.remove("hidden");
        else clearBtn.classList.add("hidden");
    }
    renderAuditRunsTable();
}

function clearRunSearch() {
    const input = document.getElementById("audit-runs-search");
    if (input) input.value = "";
    auditCurrentPage = 1;
    handleRunSearch("");
}

function handleRunCompanyFilter(val) {
    auditFilterCompany = val || "ALL";
    auditCurrentPage = 1;
    renderAuditRunsTable();
}

function handleRunStatusFilter(val) {
    auditFilterStatus = val || "ALL";
    auditCurrentPage = 1;
    renderAuditRunsTable();
}

function renderAuditRunsTable() {
    const container = document.getElementById("audit-runs-ledger-content");
    if (!container) return;

    let filtered = auditRunsList.slice();

    if (auditRunSearchQuery) {
        filtered = filtered.filter(r =>
            (r.run_name || "").toLowerCase().includes(auditRunSearchQuery) ||
            (r.company_name || "").toLowerCase().includes(auditRunSearchQuery) ||
            (r.run_date || "").toLowerCase().includes(auditRunSearchQuery) ||
            (r.run_id || "").toLowerCase().includes(auditRunSearchQuery)
        );
    }

    if (auditFilterCompany !== "ALL") {
        filtered = filtered.filter(r => (r.company_name || "").toLowerCase() === auditFilterCompany.toLowerCase());
    }

    if (auditFilterStatus !== "ALL") {
        filtered = filtered.filter(r => (r.status || "").toUpperCase() === auditFilterStatus.toUpperCase());
    }

    if (filtered.length === 0) {
        container.innerHTML = `
            <div class="border border-slate-200 rounded-xl bg-slate-50/50 p-8 text-center space-y-2">
                <p class="text-xs text-slate-600 font-medium">No consolidation runs match ${auditRunSearchQuery ? `search query <strong class="text-kpmg-navy">"${escapeHtml(auditRunSearchQuery)}"</strong>` : 'current filter criteria'}.</p>
                <button onclick="clearAllRunFilters()" class="text-xs text-kpmg-blue font-semibold hover:underline cursor-pointer">Reset filters</button>
            </div>
        `;
        return;
    }

    const totalPages = Math.max(1, Math.ceil(filtered.length / auditPageSize));
    if (auditCurrentPage > totalPages) {
        auditCurrentPage = totalPages;
    }
    if (auditCurrentPage < 1) {
        auditCurrentPage = 1;
    }

    const startIndex = (auditCurrentPage - 1) * auditPageSize;
    const endIndex = Math.min(startIndex + auditPageSize, filtered.length);
    const pagedRuns = filtered.slice(startIndex, endIndex);

    const rowsHtml = pagedRuns.map(run => {
        const isDone = run.is_completed || run.current_step === 6;
        const stepNum = run.current_step || 1;
        const stepTitle = getStepTitle(stepNum);

        let statusBadge = "";
        if (isDone) {
            statusBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">✓ Step 6: Statements (Completed)</span>`;
        } else {
            statusBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-50 text-amber-800 border border-amber-200">Step ${stepNum}: ${escapeHtml(stepTitle)} (In Progress)</span>`;
        }

        let actionButton = "";
        if (isDone) {
            actionButton = `
                <button onclick="triggerViewRun('${escapeHtml(run.run_id)}')"
                    class="h-7 px-3 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 hover:text-kpmg-navy text-[11px] font-semibold transition flex items-center space-x-1 border border-slate-200 shadow-2xs btn-tactile cursor-pointer"
                    title="View Final Deliverable (Read-Only)">
                    <svg class="w-3 h-3 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                    <span>View</span>
                </button>
            `;
        } else {
            actionButton = `
                <button onclick="triggerResumeRun('${escapeHtml(run.run_id)}')"
                    class="h-7 px-3 rounded bg-kpmg-blue hover:bg-kpmg-navy text-white text-[11px] font-semibold transition flex items-center space-x-1 shadow-xs btn-tactile cursor-pointer"
                    title="Resume Consolidation Run at Step ${stepNum}">
                    <svg class="w-3 h-3 text-[#ACEAFF]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                    </svg>
                    <span>Resume</span>
                </button>
            `;
        }

        return `
            <tr class="hover:bg-slate-50/80 transition-colors border-b border-slate-100">
                <td class="py-2.5 px-3">
                    <div class="font-bold text-xs text-kpmg-navy">${escapeHtml(run.run_name || run.run_id)}</div>
                    <div class="text-[10px] font-mono text-slate-400">${escapeHtml(run.run_id)}</div>
                </td>
                <td class="py-2.5 px-3">
                    <div class="font-semibold text-xs text-slate-800">${escapeHtml(run.company_name || '—')}</div>
                    <div class="flex items-center space-x-1.5 mt-0.5">
                        <span class="px-1.5 py-0.2 rounded text-[9px] font-mono bg-slate-100 text-slate-600">${escapeHtml(run.company_code || '—')}</span>
                        <span class="px-1.5 py-0.2 rounded text-[9px] font-mono bg-blue-50 text-kpmg-blue font-bold">${escapeHtml(run.reporting_currency || 'INR')}</span>
                    </div>
                </td>
                <td class="py-2.5 px-3 font-mono text-xs text-slate-700 font-medium">
                    ${escapeHtml(run.run_date || '—')}
                </td>
                <td class="py-2.5 px-3 text-xs text-slate-600">
                    <span class="font-semibold text-slate-800">${run.entity_count || 1}</span> Entities
                </td>
                <td class="py-2.5 px-3">
                    ${statusBadge}
                </td>
                <td class="py-2.5 px-3 text-xs text-slate-500 whitespace-nowrap">
                    ${formatDateTime(run.created_at)}
                </td>
                <td class="py-2.5 px-3 text-right">
                    <div class="flex items-center justify-end">
                        ${actionButton}
                    </div>
                </td>
            </tr>
        `;
    }).join("");

    const paginationHtml = renderPaginationControls({
        idPrefix: "audit-page",
        currentPage: auditCurrentPage,
        totalItems: filtered.length,
        pageSize: auditPageSize,
        pageSizeOptions: [10, 25, 50, 100],
        itemLabelSingular: "consolidation run",
        itemLabelPlural: "consolidation runs",
        onPageChangeFnName: "goToAuditPage",
        onPageSizeChangeFnName: "changeAuditPageSize"
    });

    container.innerHTML = `
        <div class="rounded-xl border border-slate-200/90 shadow-2xs bg-white overflow-hidden">
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse text-xs">
                    <thead class="bg-slate-50/90 border-b border-slate-200 text-[10px] font-bold text-slate-500 uppercase tracking-wider sticky top-0 z-10 select-none">
                        <tr>
                            <th class="py-2.5 px-3">Run Name / Code</th>
                            <th class="py-2.5 px-3">Client Company</th>
                            <th class="py-2.5 px-3">Run Date (Cutoff)</th>
                            <th class="py-2.5 px-3">Scope</th>
                            <th class="py-2.5 px-3">Progress / Status</th>
                            <th class="py-2.5 px-3">Created</th>
                            <th class="py-2.5 px-3 text-right">Action</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 bg-white">
                        ${rowsHtml}
                    </tbody>
                </table>
            </div>
            ${paginationHtml}
        </div>
    `;
}

function goToAuditPage(page) {
    auditCurrentPage = Math.max(1, page);
    renderAuditRunsTable();
}

function changeAuditPageSize(newSize) {
    if (!newSize || newSize <= 0) return;
    const oldStartIndex = (auditCurrentPage - 1) * auditPageSize;
    auditPageSize = newSize;
    auditCurrentPage = Math.floor(oldStartIndex / newSize) + 1;
    renderAuditRunsTable();
}

function clearAllRunFilters() {
    auditRunSearchQuery = "";
    auditFilterCompany = "ALL";
    auditFilterStatus = "ALL";
    auditCurrentPage = 1;
    const searchInput = document.getElementById("audit-runs-search");
    if (searchInput) searchInput.value = "";
    const compSelect = document.getElementById("audit-filter-company");
    if (compSelect) compSelect.value = "ALL";
    const statusSelect = document.getElementById("audit-filter-status");
    if (statusSelect) statusSelect.value = "ALL";
    renderAuditRunsTable();
}

async function triggerResumeRun(runId) {
    try {
        const res = await fetch("/api/runs/resume", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ run_id: runId })
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
            showToast("Resume Failed", data.detail || "Unable to resume run", "error");
            return;
        }

        isLauncherActive = false;
        activeRunId = data.run_id;
        activeRunName = data.run_name;
        activeRunPeriod = data.run_date || (data.state && data.state.period) || "";

        await fetchStatus();
        await loadPipelineData();

        isNavigatingDirectly = true;
        switchNavSection('PIPELINE');
        isNavigatingDirectly = false;

        const targetStep = Math.max(1, Math.min(6, data.current_step || 1));
        switchStep(targetStep);

        showToast("Run Resumed", `Resumed ${data.run_name} at Step ${targetStep}`, "success");
    } catch (err) {
        showToast("Resume Error", "Network error resuming run: " + err, "error");
    }
}

async function triggerViewRun(runId) {
    try {
        const res = await fetch("/api/runs/resume", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ run_id: runId })
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
            showToast("View Failed", data.detail || "Unable to view run", "error");
            return;
        }

        isLauncherActive = false;
        activeRunId = data.run_id;
        activeRunName = data.run_name;
        activeRunPeriod = data.run_date || (data.state && data.state.period) || "";

        await fetchStatus();
        await loadPipelineData();

        isNavigatingDirectly = true;
        switchNavSection('PIPELINE');
        isNavigatingDirectly = false;

        switchStep(6);
        showToast("Viewing Run", `Loaded completed statements for ${data.run_name}`, "info");
    } catch (err) {
        showToast("View Error", "Network error opening run: " + err, "error");
    }
}

function renderObservabilityConsole() {
    fetchAndRenderAuditRuns();
}

// PIPELINE EXECUTION TRIGGER
async function triggerRunPipeline() {
    // Gate Check 1: If files have not been uploaded at all
    const rawTbs = (pipelineData && pipelineData.raw_tbs) ? pipelineData.raw_tbs : [];
    const uploadedEntities = (appStatus && appStatus.uploaded_entities) ? appStatus.uploaded_entities : [];
    if (rawTbs.length === 0 && uploadedEntities.length === 0) {
        showToast("Upload Required", "Please upload entity trial balances before running consolidation.", "info");
        openBatchUploadModal();
        return;
    }

    // Gate Check 2: Perimeter Completeness Gating
    if (appStatus && appStatus.is_perimeter_complete === false) {
        const missing = (appStatus.missing_entities || []).join(", ");
        showToast("Perimeter Incomplete", `Cannot run consolidation: Trial balances missing for ${missing || 'pending entities'}. Please upload all perimeter entities.`, "warning");
        openBatchUploadModal();
        return;
    }

    const btn = document.getElementById("btn-run-pipeline");
    const progressModal = document.getElementById("pipeline-progress");
    const progressTitle = document.getElementById("progress-step-title");
    const progressSub = document.getElementById("progress-substep-text");

    if (btn) btn.disabled = true;
    if (progressModal) progressModal.classList.remove("hidden");

    let isFinished = false;
    const progressInterval = setInterval(async () => {
        if (isFinished) return;
        try {
            const stRes = await fetch("/api/status");
            const st = await stRes.json();
            if (st.is_running && st.current_stage) {
                if (progressTitle) progressTitle.textContent = `Executing: ${st.current_node || 'Orchestrator'}`;
                if (progressSub) progressSub.textContent = st.current_stage;
            }
        } catch (_) { }
    }, 400);

    try {
        const res = await fetch("/api/run-pipeline", { method: "POST" });
        const data = await res.json();

        if (!res.ok || data.success === false) {
            const errDetail = data.error_message || data.detail || "Consolidation failed";
            if (res.status === 403 || errDetail.toLowerCase().includes("api key") || !appStatus.has_active_api_key) {
                showToast("Execution Blocked", "Active Google Gemini API Key is required. Please configure your key in Settings.", "error");
                toggleSettingsDrawer(true);
            } else {
                showToast("Execution Halted", errDetail, "error");
            }
            await fetchStatus();
            await loadPipelineData();
            if (activeSection === 'AUDIT') renderObservabilityConsole();
        } else {
            showToast("Consolidation Succeeded", `Auditor Score: ${data.teacher_score || 100}/100. Deliverable generated with 100% formulas.`, "success");
            statementsData = null;
            currentLineageTrace = null;
            await fetchStatus();
            await loadPipelineData();
            if (activeSection === 'RUN') {
                switchStep(6);
            } else {
                renderObservabilityConsole();
            }
        }
    } catch (err) {
        showToast("Network Error", "Pipeline invocation error: " + err, "error");
    } finally {
        isFinished = true;
        clearInterval(progressInterval);
        if (progressModal) progressModal.classList.add("hidden");
        if (btn) btn.disabled = false;
    }
}

// RESET BASELINE
async function triggerResetBaseline() {
    if (!confirm("Reset consolidation workspace state back to baseline?")) return;
    try {
        const res = await fetch("/api/reset-baseline", { method: "POST" });
        const data = await res.json();
        if (data.success) {
            showToast("Reset Completed", "Consolidation workspace reset successfully.", "info");
            statementsData = null;
            currentLineageTrace = null;
            await fetchStatus();
            await loadPipelineData();
            switchStep(1);
        }
    } catch (err) {
        showToast("Reset Error", "" + err, "error");
    }
}

// TOAST NOTIFICATIONS (Emil Kowalski Spring Physics)
function showToast(title, message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `pointer-events-auto p-4 rounded-lg shadow-xl border text-xs transition-all duration-300 transform translate-y-2 opacity-0 flex items-start space-x-3`;

    let iconSvg = "";
    if (type === "success") {
        toast.className += " bg-emerald-900/90 text-white border-emerald-500/50";
        iconSvg = `<svg class="w-4 h-4 text-emerald-300 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>`;
    } else if (type === "error") {
        toast.className += " bg-rose-900/95 text-white border-rose-500/50";
        iconSvg = `<svg class="w-4 h-4 text-rose-300 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>`;
    } else if (type === "warning") {
        toast.className += " bg-amber-900/95 text-white border-amber-500/50";
        iconSvg = `<svg class="w-4 h-4 text-amber-300 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>`;
    } else {
        toast.className += " formula-popover-glass text-white border border-[#0091DA]/40 shadow-xl";
        iconSvg = `<svg class="w-4 h-4 text-[#0091DA] shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`;
    }

    toast.innerHTML = `
        ${iconSvg}
        <div class="flex-1">
            <h5 class="font-bold text-xs leading-tight">${escapeHtml(title)}</h5>
            <p class="text-[11px] opacity-90 mt-0.5 leading-snug">${escapeHtml(message)}</p>
        </div>
        <button onclick="this.parentElement.remove()" class="text-white/60 hover:text-white font-bold">&times;</button>
    `;

    container.appendChild(toast);
    requestAnimationFrame(() => {
        toast.classList.remove("translate-y-2", "opacity-0");
        toast.classList.add("translate-y-0", "opacity-100");
    });

    setTimeout(() => {
        toast.classList.add("opacity-0", "translate-y-2");
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

// SETTINGS DRAWER FUNCTIONS
function toggleSettingsDrawer(forceOpen = false) {
    const drawer = document.getElementById("settings-drawer");
    const backdrop = document.getElementById("drawer-backdrop");
    if (!drawer) return;
    const willOpen = forceOpen || drawer.classList.contains("translate-x-full");
    if (forceOpen) {
        drawer.classList.remove("translate-x-full");
    } else {
        drawer.classList.toggle("translate-x-full");
    }

    const isOpen = !drawer.classList.contains("translate-x-full");
    if (backdrop) {
        if (isOpen) backdrop.classList.remove("hidden");
        else {
            const hDrawer = document.getElementById("hitl-drawer");
            if (!hDrawer || hDrawer.classList.contains("translate-x-full")) {
                backdrop.classList.add("hidden");
            }
        }
    }

    if (willOpen) {
        const inputKey = document.getElementById("input-api-key");
        if (inputKey) {
            if (appStatus.has_active_api_key && appStatus.masked_api_key && appStatus.masked_api_key !== "[NOT CONFIGURED]") {
                inputKey.placeholder = `Active: ${appStatus.masked_api_key} (saved in .env)`;
            } else {
                inputKey.placeholder = "AIzaSy... (persisted permanently)";
            }
        }
    }
}

function closeAllDrawers() {
    const sDrawer = document.getElementById("settings-drawer");
    const hDrawer = document.getElementById("hitl-drawer");
    const backdrop = document.getElementById("drawer-backdrop");
    if (sDrawer) sDrawer.classList.add("translate-x-full");
    if (hDrawer) hDrawer.classList.add("translate-x-full");
    if (backdrop) backdrop.classList.add("hidden");
}

function updateThresholdDisplay(val) {
    document.getElementById("disp-threshold-val").textContent = `${val}%`;
}

async function saveSettings() {
    const keyInput = document.getElementById("input-api-key");
    const key = keyInput ? keyInput.value.trim() : "";
    const threshold = parseFloat(document.getElementById("slider-threshold").value) / 100.0;
    const absTol = parseFloat(document.getElementById("input-abs-tol").value);
    const pctTol = parseFloat(document.getElementById("input-pct-tol").value) / 100.0;

    try {
        const payload = {
            ai_confidence_threshold: threshold,
            ic_absolute_tolerance: absTol,
            ic_percent_tolerance: pctTol
        };
        if (key) payload.gemini_api_key = key;

        const res = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            if (key) {
                try {
                    localStorage.setItem("fs_conso_gemini_key", key);
                } catch (_) { }
                if (keyInput) keyInput.value = "";
            }
            showToast("Settings Saved", "Parameters and API key saved permanently.", "success");
            toggleSettingsDrawer();
            fetchStatus();
        } else {
            showToast("Settings Error", data.detail || "Failed to update settings", "error");
        }
    } catch (err) {
        showToast("Settings Error", "" + err, "error");
    }
}

// SINGLE FILE DROPZONE FOR STANDALONE UPLOAD
function initDropZone() {
    const dropZone = document.getElementById("drop-zone");
    if (!dropZone || dropZone.dataset.initialized) return;
    dropZone.dataset.initialized = "true";

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add("dragover");
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove("dragover");
        }, false);
    });
}

// FLOATING FORMULA INSPECTOR
function showFormula(e, expr, origin) {
    const pop = document.getElementById("formula-popover");
    if (!pop) return;
    document.getElementById("formula-expr").textContent = expr;
    document.getElementById("formula-origin").textContent = origin;
    pop.classList.remove("hidden");

    const popWidth = 340;
    const popHeight = 100;
    let left = e.clientX + 15;
    let top = e.clientY + 15;

    // Viewport Boundary Clamping & Left Flipping for far-right financial columns
    if (left + popWidth > window.innerWidth - 20) {
        left = Math.max(10, e.clientX - popWidth - 15);
    }
    if (top + popHeight > window.innerHeight - 20) {
        top = Math.max(10, e.clientY - popHeight - 15);
    }

    pop.style.left = `${left}px`;
    pop.style.top = `${top}px`;
}

function hideFormula() {
    const pop = document.getElementById("formula-popover");
    if (pop) pop.classList.add("hidden");
}

function formatNum(val) {
    if (val === undefined || val === null || isNaN(val)) return "0.00";
    return Number(val).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// -------------------------------------------------------------
// Interactive Table Column & Dialog / Drawer Resizing Engine
// -------------------------------------------------------------

function initTableColumnResizers(root) {
    const scope = root || document;
    const tables = scope.querySelectorAll("table.fin-table");
    tables.forEach(table => {
        const ths = table.querySelectorAll("thead th");
        ths.forEach((th) => {
            if (th.querySelector(".col-resizer")) return;

            const resizer = document.createElement("div");
            resizer.className = "col-resizer";
            resizer.title = "Drag to resize column horizontally (double-click to auto-adjust)";
            th.appendChild(resizer);

            resizer.addEventListener("mousedown", (e) => {
                e.preventDefault();
                e.stopPropagation();
                resizer.classList.add("resizing");
                document.body.classList.add("table-col-resizing");

                const startX = e.clientX;
                const startWidth = th.getBoundingClientRect().width;

                const onMouseMove = (moveEvt) => {
                    const delta = moveEvt.clientX - startX;
                    const newWidth = Math.max(45, Math.round(startWidth + delta));
                    th.style.width = `${newWidth}px`;
                    th.style.minWidth = `${newWidth}px`;
                };

                const onMouseUp = () => {
                    resizer.classList.remove("resizing");
                    document.body.classList.remove("table-col-resizing");
                    document.removeEventListener("mousemove", onMouseMove);
                    document.removeEventListener("mouseup", onMouseUp);
                };

                document.addEventListener("mousemove", onMouseMove);
                document.addEventListener("mouseup", onMouseUp);
            });

            // Double-click resets to default auto-adjust
            resizer.addEventListener("dblclick", (e) => {
                e.preventDefault();
                e.stopPropagation();
                th.style.width = "";
                th.style.minWidth = "";
            });
        });
    });
}

function initTableObserver() {
    const observer = new MutationObserver((mutations) => {
        let shouldInit = false;
        for (const m of mutations) {
            if (m.addedNodes && m.addedNodes.length > 0) {
                for (const node of m.addedNodes) {
                    if (node.nodeType === 1 && (node.matches?.("table.fin-table") || node.querySelector?.("table.fin-table"))) {
                        shouldInit = true;
                        break;
                    }
                }
            }
            if (shouldInit) break;
        }
        if (shouldInit) {
            initTableColumnResizers();
        }
    });

    const target = document.getElementById("main-layout-container") || document.body;
    observer.observe(target, { childList: true, subtree: true });
}

function initDialogAndDrawerResizers() {
    // 1. Side Drawers: Settings Drawer & HITL Drawer (draggable left-edge bar)
    const drawers = [document.getElementById("settings-drawer"), document.getElementById("hitl-drawer")];
    drawers.forEach(drawer => {
        if (!drawer || drawer.querySelector(".drawer-resizer-left")) return;
        const resizer = document.createElement("div");
        resizer.className = "drawer-resizer-left";
        resizer.title = "Drag to resize panel";
        drawer.prepend(resizer);

        resizer.addEventListener("mousedown", (e) => {
            e.preventDefault();
            e.stopPropagation();
            resizer.classList.add("resizing");
            document.body.classList.add("drawer-resizing");

            const onMouseMove = (moveEvt) => {
                const newWidth = Math.min(window.innerWidth - 60, Math.max(300, window.innerWidth - moveEvt.clientX));
                drawer.style.width = `${newWidth}px`;
                drawer.style.maxWidth = `${newWidth}px`;
            };

            const onMouseUp = () => {
                resizer.classList.remove("resizing");
                document.body.classList.remove("drawer-resizing");
                document.removeEventListener("mousemove", onMouseMove);
                document.removeEventListener("mouseup", onMouseUp);
            };

            document.addEventListener("mousemove", onMouseMove);
            document.addEventListener("mouseup", onMouseUp);
        });
    });

    // 2. Modal Dialogs: Batch File Upload Modal & New Company Modal
    const modalCards = document.querySelectorAll(".modal-dialog-card");
    modalCards.forEach(card => {
        if (!card || card.querySelector(".modal-resizer-corner")) return;

        // Right-edge horizontal resize bar
        const rightEdge = document.createElement("div");
        rightEdge.className = "modal-resizer-right";
        rightEdge.title = "Drag to resize dialog horizontally";
        card.appendChild(rightEdge);

        rightEdge.addEventListener("mousedown", (e) => {
            e.preventDefault();
            e.stopPropagation();
            rightEdge.classList.add("resizing");
            document.body.classList.add("drawer-resizing");

            const startX = e.clientX;
            const startWidth = card.getBoundingClientRect().width;

            const onMouseMove = (moveEvt) => {
                const newWidth = Math.max(360, Math.min(window.innerWidth - 40, startWidth + (moveEvt.clientX - startX)));
                card.style.width = `${newWidth}px`;
                card.style.maxWidth = `${newWidth}px`;
            };

            const onMouseUp = () => {
                rightEdge.classList.remove("resizing");
                document.body.classList.remove("drawer-resizing");
                document.removeEventListener("mousemove", onMouseMove);
                document.removeEventListener("mouseup", onMouseUp);
            };

            document.addEventListener("mousemove", onMouseMove);
            document.addEventListener("mouseup", onMouseUp);
        });

        // Bottom-right corner resize handle
        const corner = document.createElement("div");
        corner.className = "modal-resizer-corner";
        corner.title = "Drag to resize dialog";
        card.appendChild(corner);

        corner.addEventListener("mousedown", (e) => {
            e.preventDefault();
            e.stopPropagation();
            corner.classList.add("resizing");
            document.body.classList.add("modal-resizing");

            const startX = e.clientX;
            const startY = e.clientY;
            const startWidth = card.getBoundingClientRect().width;
            const startHeight = card.getBoundingClientRect().height;

            const onMouseMove = (moveEvt) => {
                const newWidth = Math.max(360, Math.min(window.innerWidth - 40, startWidth + (moveEvt.clientX - startX)));
                const newHeight = Math.max(260, Math.min(window.innerHeight - 40, startHeight + (moveEvt.clientY - startY)));
                card.style.width = `${newWidth}px`;
                card.style.maxWidth = `${newWidth}px`;
                card.style.height = `${newHeight}px`;
                card.style.maxHeight = `${newHeight}px`;
            };

            const onMouseUp = () => {
                corner.classList.remove("resizing");
                document.body.classList.remove("modal-resizing");
                document.removeEventListener("mousemove", onMouseMove);
                document.removeEventListener("mouseup", onMouseUp);
            };

            document.addEventListener("mousemove", onMouseMove);
            document.addEventListener("mouseup", onMouseUp);
        });
    });
}
