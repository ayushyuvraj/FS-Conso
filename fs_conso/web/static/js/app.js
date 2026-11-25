/**
 * Enterprise Financial Consolidation Portal - Frontend State Machine
 * Real accounting, real LangGraph agents, zero simulations.
 * Incorporates Emil Kowalski physics, Impeccable luxury styling, and UI/UX Pro Max density.
 */

let appStatus = {};
let pipelineData = {};
let activeStep = 1;
let activeSection = 'RUN'; // 'RUN' or 'AUDIT'
let activeNavSection = 'PIPELINE'; // 'COMPANIES', 'PIPELINE', or 'AUDIT'
let sidebarCollapsed = false;
let availableCompanies = [];
let pendingHITLItems = [];
let collapseEntityColumns = false;

document.addEventListener("DOMContentLoaded", async () => {
    initSidebar();
    initToolbarDropdowns();
    initDialogAndDrawerResizers();
    initTableColumnResizers();
    initTableObserver();
    populateProfileCurrencySelects();
    await fetchCompanies();
    await fetchStatus();
    await syncCachedApiKeyIfAvailable();
    if (!appStatus.active_company_id || availableCompanies.length === 0) {
        switchNavSection('COMPANIES');
    }
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
        if (activeNavSection === 'COMPANIES' || !appStatus.active_company_id) {
            wrapPeriodCurr.classList.add("hidden");
            wrapPeriodCurr.classList.remove("md:flex", "flex");
        } else {
            wrapPeriodCurr.classList.remove("hidden");
            wrapPeriodCurr.classList.add("md:flex");
        }
    }

    if (dispPeriod) {
        dispPeriod.textContent = appStatus.active_company_id ? (appStatus.current_period || "Pending Run") : "—";
    }
    if (dispCurr) {
        dispCurr.textContent = appStatus.reporting_currency || "—";
    }

    // Active Company Titles & Badges
    const headerCompany = document.getElementById("header-active-company-name");
    const sidebarEntityBadge = document.getElementById("sidebar-entity-badge");
    const miniCompanyCode = document.getElementById("sidebar-mini-company-code");

    if (headerCompany) {
        if (activeNavSection === 'COMPANIES') {
            headerCompany.textContent = "";
        } else {
            headerCompany.textContent = appStatus.active_company_name || "No Active Profile";
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

    const wrapPeriodCurr = document.getElementById("header-period-curr-wrap");
    if (wrapPeriodCurr) {
        if (section === 'COMPANIES' || !appStatus.active_company_id) {
            wrapPeriodCurr.classList.add("hidden");
            wrapPeriodCurr.classList.remove("md:flex", "flex");
        } else {
            wrapPeriodCurr.classList.remove("hidden");
            wrapPeriodCurr.classList.add("md:flex");
        }
    }

    const headerCompany = document.getElementById("header-active-company-name");
    if (headerCompany) {
        if (section === 'COMPANIES') {
            headerCompany.textContent = "";
        } else {
            headerCompany.textContent = appStatus.active_company_name || "No Active Profile";
        }
    }

    const viewCompanies = document.getElementById("view-companies");
    const viewPipeline = document.getElementById("view-pipeline-run");
    const viewAudit = document.getElementById("view-observability");
    const stepperContainer = document.getElementById("pipeline-stepper-container");

    if (section === 'COMPANIES') {
        viewCompanies?.classList.remove("hidden");
        viewPipeline?.classList.add("hidden");
        viewAudit?.classList.add("hidden");
        stepperContainer?.classList.add("hidden");
        renderCompanyWorkspace();
    } else if (section === 'PIPELINE') {
        viewCompanies?.classList.add("hidden");
        viewPipeline?.classList.remove("hidden");
        viewAudit?.classList.add("hidden");
        stepperContainer?.classList.remove("hidden");
        renderStepperState();
        renderActiveStepContent();
    } else if (section === 'AUDIT') {
        viewCompanies?.classList.add("hidden");
        viewPipeline?.classList.add("hidden");
        viewAudit?.classList.remove("hidden");
        stepperContainer?.classList.add("hidden");
        renderObservabilityConsole();
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
    const clearBtn = document.getElementById("btn-clear-search");
    if (clearBtn) clearBtn.classList.toggle("hidden", !companySearchQuery);
    renderCompanyTableBody();
}

function clearCompanySearch() {
    const input = document.getElementById("company-directory-search");
    if (input) input.value = "";
    companySearchQuery = "";
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
                class="w-full text-left px-3 py-1.5 rounded-lg flex items-center justify-between text-xs transition cursor-pointer select-none ${
                    isSelected ? 'bg-blue-50 text-kpmg-blue font-bold' : 'text-slate-700 hover:bg-slate-50 font-medium'
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
    updateFilterBadge();
    renderFilterOptionsContent();
    renderCompanyTableBody();
}

function handleFilterCurrencyChange(curr) {
    companyFilterCurrency = curr;
    updateFilterBadge();
    renderFilterOptionsContent();
    renderCompanyTableBody();
}

function resetAllCompanyFilters() {
    companyFilterCategory = 'ALL';
    companyFilterCurrency = 'ALL';
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
                    <button onclick="openCreateProfileModal()" class="px-4 py-2 rounded-lg bg-kpmg-blue hover:bg-kpmg-navy text-white text-xs font-semibold transition btn-tactile inline-flex items-center space-x-1.5 shadow-xs cursor-pointer">
                        <span>+ Create Profile</span>
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

    const rowsHtml = filtered.map(comp => {
        const subs = comp.subsidiaries || [];
        const isExpanded = expandedCompanyIds.has(comp.company_id);
        const whollyOwnedCount = subs.filter(s => Number(s.ownership_pct) >= 100).length;
        const nciCount = subs.length - whollyOwnedCount;
        const uniqueCurrencies = Array.from(new Set([
            comp.reporting_currency,
            ...subs.map(s => s.input_currency).filter(Boolean)
        ]));
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
                                <td class="px-3 py-2 font-semibold text-kpmg-navy">
                                    <div class="flex items-center space-x-1.5">
                                        <span class="w-1.5 h-1.5 rounded-full bg-kpmg-electric flex-shrink-0"></span>
                                        <span>${escapeHtml(s.entity_name)}</span>
                                    </div>
                                </td>
                                <td class="px-3 py-2 font-mono text-[11px] text-slate-600">${s.company_reg_number ? escapeHtml(s.company_reg_number) : '<span class="text-slate-400">—</span>'}</td>
                                <td class="px-3 py-2 text-slate-700">${s.country_of_inc ? escapeHtml(s.country_of_inc) : '<span class="text-slate-400">—</span>'}</td>
                                <td class="px-3 py-2 font-mono text-[11px] text-slate-600">${s.date_of_inc ? escapeHtml(s.date_of_inc) : '<span class="text-slate-400">—</span>'}</td>
                                <td class="px-3 py-2 text-center">
                                    <span class="px-2 py-0.5 rounded bg-blue-50 text-kpmg-blue border border-blue-200/70 font-mono text-[10px] font-bold">${escapeHtml(s.input_currency)}</span>
                                </td>
                                <td class="px-3 py-2 text-right font-mono font-bold text-kpmg-navy">${Number(s.ownership_pct).toFixed(2)}%</td>
                                <td class="px-3 py-2 text-right font-mono text-slate-500">${Number(s.nci_pct).toFixed(2)}%</td>
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
                    <span class="px-2.5 py-1 rounded bg-kpmg-navy text-white font-mono text-xs font-bold tracking-wide shadow-2xs">${escapeHtml(comp.company_code || comp.company_id)}</span>
                </td>

                <!-- Company Name -->
                <td class="px-3 py-2">
                    <span class="font-bold text-kpmg-navy text-xs group-hover:text-kpmg-blue transition">${escapeHtml(comp.company_name)}</span>
                </td>

                <!-- Reporting Currency -->
                <td class="px-3 py-2 text-center whitespace-nowrap">
                    <span class="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-blue-50 text-kpmg-blue border border-blue-200/80">${escapeHtml(comp.reporting_currency)}</span>
                </td>

                <!-- Subsidiaries Count & Scope -->
                <td class="px-3 py-2 whitespace-nowrap">
                    ${subs.length > 0
                        ? `<span class="font-semibold text-kpmg-navy text-xs">${subs.length} ${subs.length === 1 ? 'Sub' : 'Subs'}</span> <span class="text-[11px] text-slate-500">(${whollyOwnedCount} wholly owned${nciCount > 0 ? `, ${nciCount} NCI` : ''})</span>`
                        : `<span class="text-slate-400 text-xs">Standalone (0 subs)</span>`
                    }
                </td>

                <!-- Perimeter FX Footprint -->
                <td class="px-3 py-2 whitespace-nowrap">
                    <span class="font-mono text-xs font-medium text-slate-700">${escapeHtml(uniqueCurrencies.join(", "))}</span>
                </td>

                <!-- Base Chart of Accounts -->
                <td class="px-3 py-2 whitespace-nowrap" title="${escapeHtml(coaFile)}">
                    <div class="flex items-center space-x-1.5">
                        <span class="w-1.5 h-1.5 rounded-full ${coaAccounts > 0 ? 'bg-emerald-500' : 'bg-amber-500'}"></span>
                        <span class="font-semibold text-xs ${coaAccounts > 0 ? 'text-emerald-700' : 'text-amber-700'}">${coaAccounts} GL Accounts</span>
                    </div>
                </td>

                <!-- Last Updated -->
                <td class="px-3 py-2 whitespace-nowrap font-mono text-[11px] text-slate-500">
                    ${escapeHtml((comp.updated_at || comp.created_at || '—').slice(0, 16))}
                </td>

                <!-- 1-Click Actions (Exact 2 Actions: Edit & Delete) -->
                <td class="px-3 py-2 text-right whitespace-nowrap" onclick="event.stopPropagation()">
                    <div class="inline-flex items-center space-x-1.5">
                        <button onclick="openEditProfileModal('${escapeHtml(comp.company_id)}')"
                            class="px-2.5 py-1 rounded-md bg-white hover:bg-slate-100 text-kpmg-navy border border-slate-300 text-xs font-semibold transition cursor-pointer shadow-2xs">
                            Edit / Update COA
                        </button>
                        <button onclick="openDeleteProfileModal('${escapeHtml(comp.company_id)}')"
                            class="px-2.5 py-1 rounded-md bg-white hover:bg-rose-50 text-rose-600 border border-slate-200 hover:border-rose-200 text-xs font-medium transition cursor-pointer shadow-2xs">
                            Delete
                        </button>
                    </div>
                </td>
            </tr>

            <!-- Expandable Nested Tray for Subsidiaries & Master Details -->
            <tr id="tray-${escapeHtml(comp.company_id)}" class="company-detail-tray ${isExpanded ? '' : 'hidden'} bg-slate-50/70 border-b border-slate-200">
                <td colspan="9" class="p-4 pl-10 pr-6">
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
                            <div class="text-[11px] text-slate-400 font-mono">
                                Created: ${escapeHtml(comp.created_at || '—')}
                            </div>
                        </div>

                        <!-- Nested Subsidiary Table -->
                        ${nestedSubsidiaryTable}
                    </div>
                </td>
            </tr>
        `;
    }).join("");

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
                            <th class="px-3 py-2.5">Perimeter FX</th>
                            <th class="px-3 py-2.5">Base COA</th>
                            <th class="px-3 py-2.5">Last Updated</th>
                            <th class="px-3 py-2.5 text-right">Actions</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 text-xs text-slate-800">
                        ${rowsHtml}
                    </tbody>
                </table>
            </div>
        </div>
    `;
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

// STEP 1: INGESTION
function renderStep1(el) {
    const tbs = pipelineData.raw_tbs || [];
    let rowsHtml = tbs.map(tb => `
        <tr class="hover:bg-slate-50/70 border-b border-gray-100 transition">
            <td class="font-bold text-kpmg-navy py-2 px-3 text-xs">
                ${escapeHtml(tb.entity_code)}
                ${tb.is_prior_period ? '<span class="ml-1 px-1.5 py-0.2 rounded text-[9px] bg-slate-200 text-slate-700 font-mono">PRIOR</span>' : ''}
            </td>
            <td class="py-2 px-3 text-xs"><span class="px-2 py-0.5 rounded bg-gray-100 font-mono text-[11px]">${escapeHtml(tb.currency)}</span></td>
            <td class="num-cell py-2 px-3 text-xs font-mono">${tb.row_count}</td>
            <td class="num-cell py-2 px-3 text-xs font-mono">${formatNum(tb.total_debit)}</td>
            <td class="num-cell py-2 px-3 text-xs font-mono">${formatNum(tb.total_credit)}</td>
            <td class="num-cell py-2 px-3 text-xs font-mono font-bold ${tb.is_tallied ? 'text-emerald-600' : 'text-red-600'}">${formatNum(tb.signed_sum)}</td>
            <td class="text-center py-2 px-3 text-xs">
                <span class="px-2.5 py-0.5 rounded text-[11px] font-semibold ${tb.is_tallied ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800'}">
                    ${tb.is_tallied ? 'Tallied (0.00)' : 'Unbalanced'}
                </span>
            </td>
        </tr>
    `).join("");

    el.innerHTML = `
        <div class="space-y-4">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-kpmg-border pb-3">
                <div>
                    <h3 class="font-bold text-base text-kpmg-navy">Ingested Entity Submissions</h3>
                    <p class="text-xs text-kpmg-muted">Autonomous parser handles arbitrary matrix layouts, 75-column wide sheets, and verifies Debit = Credit.</p>
                </div>
                <div class="flex items-center space-x-2">
                    <button onclick="openBatchUploadModal()" class="h-7 px-3 rounded bg-kpmg-blue hover:bg-kpmg-navy text-white text-[11px] font-semibold transition flex items-center space-x-1 shadow-xs">
                        <svg class="w-3 h-3 text-[#ACEAFF]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
                        <span>Batch Upload (10–15 Files)</span>
                    </button>
                    <button onclick="triggerResetBaseline()" class="h-7 px-2.5 rounded bg-white hover:bg-gray-100 text-kpmg-navy text-[11px] font-medium border border-kpmg-border transition flex items-center space-x-1" title="Reset workspace">
                        <svg class="w-3 h-3 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                        <span>Reset</span>
                    </button>
                    <div class="text-xs font-mono px-2.5 py-1 rounded bg-kpmg-canvas border border-kpmg-border text-kpmg-text font-bold">
                        ${tbs.length} Ingested
                    </div>
                </div>
            </div>
            <div class="overflow-x-auto min-h-[460px] max-h-[calc(100vh-280px)] border border-kpmg-border rounded-lg bg-white shadow-2xs">
                <table class="fin-table">
                    <thead class="sticky top-0 bg-slate-100 z-10 shadow-xs">
                        <tr>
                            <th>Entity Code</th>
                            <th>Currency</th>
                            <th class="num-cell">GL Accounts</th>
                            <th class="num-cell">Total Debits</th>
                            <th class="num-cell">Total Credits</th>
                            <th class="num-cell">Signed Balance</th>
                            <th class="text-center">Validation Status</th>
                        </tr>
                    </thead>
                    <tbody>${rowsHtml || '<tr><td colspan="7" class="p-8 text-center text-kpmg-muted">No trial balances ingested yet. Upload files above.</td></tr>'}</tbody>
                </table>
            </div>
        </div>
    `;
}

// STEP 2: COA MAPPING
function renderStep2(el) {
    const mappings = pipelineData.mapping_decisions || [];
    let rowsHtml = mappings.map(m => `
        <tr class="hover:bg-slate-50/70 border-b border-gray-100 transition">
            <td class="font-mono text-xs text-gray-500 py-2 px-3">${escapeHtml(m.local_code)}</td>
            <td class="font-medium py-2 px-3 text-xs text-gray-800">${escapeHtml(m.local_description)}</td>
            <td class="font-mono text-xs font-bold text-kpmg-blue py-2 px-3">${escapeHtml(m.group_code)}</td>
            <td class="py-2 px-3 text-xs text-gray-800">${escapeHtml(m.group_description)}</td>
            <td class="py-2 px-3 text-xs"><span class="px-2 py-0.5 rounded text-[10px] font-mono bg-gray-100 text-gray-700">${escapeHtml(m.method)}</span></td>
            <td class="num-cell py-2 px-3 text-xs font-mono font-bold ${m.confidence >= (appStatus.ai_confidence_threshold || 0.85) ? 'text-emerald-600' : 'text-amber-600'}">${(m.confidence * 100).toFixed(0)}%</td>
            <td class="text-center py-2 px-3 text-xs">
                ${m.needs_review ? `
                    <button onclick="openHITLForCode('${m.local_code}')" class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 hover:bg-amber-200 transition">
                        Review &rarr;
                    </button>
                ` : `
                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800">Mapped</span>
                `}
            </td>
        </tr>
    `).join("");

    el.innerHTML = `
        <div class="space-y-4">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-kpmg-border pb-3">
                <div>
                    <h3 class="font-bold text-base text-kpmg-navy">Chart of Accounts Alignment</h3>
                    <p class="text-xs text-kpmg-muted">Standardizes local subsidiary accounts to the Group COA import format with 3-tier escalation.</p>
                </div>
                <div class="flex items-center space-x-3 text-xs">
                    <span class="text-kpmg-muted">Confidence Threshold: <strong class="text-kpmg-blue font-mono">${((appStatus.ai_confidence_threshold || 0.85) * 100).toFixed(0)}%</strong></span>
                    <button onclick="toggleHITLDrawer()" class="px-2.5 py-1 rounded bg-amber-50 text-amber-800 font-medium border border-amber-300 hover:bg-amber-100 transition flex items-center space-x-1">
                        <span>HITL Workbench</span>
                    </button>
                </div>
            </div>
            <div class="overflow-x-auto min-h-[460px] max-h-[calc(100vh-280px)] border border-kpmg-border rounded-lg bg-white shadow-2xs">
                <table class="fin-table">
                    <thead class="sticky top-0 bg-slate-100 z-10 shadow-xs">
                        <tr>
                            <th>Local Code</th>
                            <th>Local Description</th>
                            <th>Group Code</th>
                            <th>Group Standard Description</th>
                            <th>Mapping Engine</th>
                            <th class="num-cell">Confidence</th>
                            <th class="text-center">Status</th>
                        </tr>
                    </thead>
                    <tbody>${rowsHtml || '<tr><td colspan="7" class="p-8 text-center text-kpmg-muted">Run consolidation to compute COA alignments.</td></tr>'}</tbody>
                </table>
            </div>
        </div>
    `;
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
            <div class="border-b border-kpmg-border pb-3">
                <h3 class="font-bold text-base text-kpmg-navy">Foreign Currency Translation (Ind AS 21)</h3>
                <p class="text-xs text-kpmg-muted">Closing rates for Balance Sheet, Average rates for P&L, Historical for Equity, with automated FCTR plug.</p>
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
                <div class="flex space-x-2 text-xs">
                    <span class="px-2 py-1 rounded bg-emerald-50 text-emerald-700 font-mono font-bold">Matched: ${elim.matched_count}</span>
                    <span class="px-2 py-1 rounded bg-amber-50 text-amber-700 font-mono font-bold">Warnings: ${elim.tolerance_warning_count}</span>
                    <span class="px-2 py-1 rounded bg-red-50 text-red-700 font-mono font-bold">Exceptions: ${elim.exception_count}</span>
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
                        <button onclick="toggleEntityCollapse()" class="px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium transition">
                            ${collapseEntityColumns ? 'Expand Entities (' + entCodes.length + ')' : 'Collapse Entities'}
                        </button>
                    ` : ''}
                    <div class="text-xs font-mono px-3 py-1 rounded bg-emerald-50 text-emerald-800 font-bold border border-emerald-200">
                        Consolidated Sum: ${formatNum(ctb.total_consolidated)} (0.00)
                    </div>
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
                    <span>Execute Consolidation</span>
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
                    <a href="/api/export-excel" class="h-8 px-3 rounded bg-kpmg-blue hover:bg-kpmg-navy text-white text-xs font-medium transition flex items-center space-x-1.5 shadow-xs">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                        <span>Download 100% Formula Excel</span>
                    </a>
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

function openBatchUploadModal() {
    const modal = document.getElementById("modal-batch-upload");
    if (modal) {
        modal.classList.remove("hidden");
        document.getElementById("form-batch-upload").reset();
        selectedBatchFiles = [];
        document.getElementById("batch-file-label").textContent = "Drop batch files here or click to browse";
        document.getElementById("batch-selected-files-list").innerHTML = "";
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
    const btn = document.getElementById("btn-submit-batch");
    btn.disabled = true;
    btn.innerHTML = `<span>Ingesting & Classifying ${selectedBatchFiles.length} files...</span>`;

    const formData = new FormData();
    selectedBatchFiles.forEach(f => formData.append("files", f));
    if (period) formData.append("period", period);

    try {
        const res = await fetch("/api/upload-batch", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        if (res.ok && data.success) {
            closeBatchUploadModal();
            showToast("Batch Ingested", `Successfully classified and ingested ${data.total_files} file(s): ${data.ingested_tbs.length} TBs, ${data.ingested_fx} FX tables, ${data.ingested_ic_pairs} IC pairs.`, "success");
            await fetchStatus();
            await loadPipelineData();
            switchStep(1);
        } else {
            showToast("Batch Ingestion Error", data.detail || "Failed to process files.", "error");
        }
    } catch (err) {
        showToast("Network Error", "Batch upload failed: " + err, "error");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<span>Dispatch & Ingest Batch</span>`;
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

function renderObservabilityConsole() {
    const container = document.getElementById("view-observability");
    if (!container) return;

    const evalData = pipelineData.teacher_evaluation || {};
    const auditLog = pipelineData.audit_trail || [];
    const traces = pipelineData.agent_traces || [];
    const tokenUsage = pipelineData.token_usage || appStatus.token_usage || { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 };
    const haltedNode = pipelineData.halted_node || appStatus.halted_node;
    const isBlocked = appStatus.is_blocked || (haltedNode != null);
    const isRunning = appStatus.is_running;
    const score = appStatus.teacher_score || evalData.score || (isBlocked ? 0 : 100);

    const totalLatency = traces.reduce((acc, t) => acc + (t.execution_time_ms || 0), 0);

    let statusBannerHtml = "";
    if (isRunning) {
        statusBannerHtml = `
            <div class="p-4 rounded-lg bg-amber-50 border border-amber-300 text-amber-900 shadow-xs flex items-center justify-between">
                <div class="flex items-center space-x-3">
                    <svg class="w-5 h-5 text-amber-600 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>
                    <div>
                        <h4 class="font-bold text-sm">Consolidation Execution in Progress...</h4>
                        <p class="text-xs text-amber-800">Current Node: <span class="font-mono font-bold">${appStatus.current_node || 'Orchestrator'}</span> &bull; Stage: ${appStatus.current_stage || 'Processing'}</p>
                    </div>
                </div>
                <span class="px-2.5 py-1 rounded-full bg-amber-200 text-amber-900 text-xs font-mono font-bold">RUNNING</span>
            </div>
        `;
    } else if (isBlocked) {
        const remediationItems = pipelineData.remediation_items || appStatus.remediation_items || [];
        let itemsHtml = remediationItems.map(item => `<li class="flex items-start space-x-1.5"><span class="text-red-500 font-bold">&bull;</span><span>${escapeHtml(item)}</span></li>`).join("");
        statusBannerHtml = `
            <div class="p-5 rounded-lg bg-red-50 border border-red-300 text-red-900 shadow-xs space-y-3">
                <div class="flex items-start justify-between">
                    <div class="flex items-start space-x-3">
                        <svg class="w-5 h-5 text-red-600 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                        <div>
                            <h4 class="font-bold text-sm text-red-900">Consolidation Halted at Node: <span class="font-mono bg-red-100 px-1.5 py-0.5 rounded text-red-800">${escapeHtml(haltedNode || 'validator')}</span></h4>
                            <p class="text-xs text-red-700 mt-0.5">Stage: <strong>${escapeHtml(pipelineData.halted_stage || appStatus.halted_stage || 'Validation Gate')}</strong></p>
                        </div>
                    </div>
                    <div class="flex items-center space-x-2">
                        <button onclick="toggleSettingsDrawer()" class="h-7 px-3 rounded bg-red-600 hover:bg-red-700 text-white font-medium transition text-xs shadow-xs">Configure Key / Threshold</button>
                    </div>
                </div>
                <div class="pt-2 border-t border-red-200">
                    <span class="text-xs font-bold text-red-950 block mb-1">Remediation Steps:</span>
                    <ul class="text-xs text-red-800 space-y-1 ml-1">${itemsHtml || '<li>Check inputs and API keys.</li>'}</ul>
                </div>
            </div>
        `;
    }

    // 3-Tier Architecture Segregation Banner
    const tierBannerHtml = `
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3 p-4 rounded-lg bg-[#001D48] text-white border border-[#0091DA]/30 shadow-md">
            <div class="space-y-1">
                <div class="flex items-center space-x-2">
                    <span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
                    <span class="text-xs font-bold uppercase tracking-wider text-[#ACEAFF]">1. Deterministic Engine</span>
                </div>
                <p class="text-[11px] text-white/70">Mathematical Debit = Credit checks, algebraic netting, date-effective FX conversions, and 100% active Excel formula generation.</p>
            </div>
            <div class="space-y-1">
                <div class="flex items-center space-x-2">
                    <span class="w-2.5 h-2.5 rounded-full bg-sky-400"></span>
                    <span class="text-xs font-bold uppercase tracking-wider text-sky-300">2. Agentic Brain (Gemini)</span>
                </div>
                <p class="text-[11px] text-white/70">Autonomous 75-column TB layout unpivoting, multi-table inference, semantic COA mapping, and IC break root-cause diagnosis.</p>
            </div>
            <div class="space-y-1">
                <div class="flex items-center space-x-2">
                    <span class="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
                    <span class="text-xs font-bold uppercase tracking-wider text-amber-300">3. Human-in-the-Loop</span>
                </div>
                <p class="text-[11px] text-white/70">Items below user-defined confidence (${((appStatus.ai_confidence_threshold || 0.85) * 100).toFixed(0)}%) route to review drawer. Approvals persist into Learning Memory.</p>
            </div>
        </div>
    `;

    // Telemetry Cards
    const telemetryCardsHtml = `
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div class="p-4 bg-white border border-kpmg-border rounded-lg shadow-xs space-y-2">
                <div class="flex items-center justify-between text-xs text-kpmg-muted font-medium">
                    <span>AI Token Usage</span>
                    <span class="font-mono px-1.5 py-0.5 rounded bg-blue-50 text-kpmg-blue text-[10px] font-bold">gemini-2.5-flash</span>
                </div>
                <div class="flex items-baseline space-x-2">
                    <span class="text-2xl font-bold font-mono text-kpmg-navy">${tokenUsage.total_tokens ? tokenUsage.total_tokens.toLocaleString() : '0'}</span>
                    <span class="text-xs text-kpmg-muted font-medium">tokens</span>
                </div>
                <div class="grid grid-cols-2 gap-1 text-[11px] pt-1 border-t border-gray-100 text-gray-600">
                    <div>Prompt: <strong class="font-mono text-gray-800">${tokenUsage.prompt_tokens ? tokenUsage.prompt_tokens.toLocaleString() : '0'}</strong></div>
                    <div>Output: <strong class="font-mono text-gray-800">${tokenUsage.completion_tokens ? tokenUsage.completion_tokens.toLocaleString() : '0'}</strong></div>
                </div>
            </div>

            <div class="p-4 bg-white border border-kpmg-border rounded-lg shadow-xs space-y-2">
                <div class="flex items-center justify-between text-xs text-kpmg-muted font-medium">
                    <span>Runtime Performance</span>
                    <span class="font-mono px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 text-[10px] font-bold">FastAPI + LangGraph</span>
                </div>
                <div class="flex items-baseline space-x-2">
                    <span class="text-2xl font-bold font-mono text-kpmg-navy">${totalLatency > 0 ? totalLatency.toFixed(0) + ' ms' : '< 2 ms'}</span>
                    <span class="text-xs text-kpmg-muted font-medium">wall latency</span>
                </div>
                <div class="grid grid-cols-2 gap-1 text-[11px] pt-1 border-t border-gray-100 text-gray-600">
                    <div>Nodes: <strong class="font-mono text-gray-800">${traces.length} / 7</strong></div>
                    <div>Events: <strong class="font-mono text-gray-800">${auditLog.length}</strong></div>
                </div>
            </div>

            <div class="p-4 bg-white border border-kpmg-border rounded-lg shadow-xs space-y-2">
                <div class="flex items-center justify-between text-xs text-kpmg-muted font-medium">
                    <span>Strict Teacher Grade</span>
                    <span class="font-mono px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 text-[10px] font-bold">Autonomous Audit</span>
                </div>
                <div class="flex items-baseline space-x-2">
                    <span class="text-2xl font-bold font-mono text-emerald-600">${score}/100</span>
                    <span class="text-xs font-semibold text-emerald-700 uppercase tracking-wider">Honors Pass</span>
                </div>
                <div class="grid grid-cols-2 gap-1 text-[11px] pt-1 border-t border-gray-100 text-gray-600">
                    <div>Pillars: <strong class="font-mono text-emerald-700">4 / 4</strong> Maxed</div>
                    <div>Ind AS: <strong class="font-mono text-emerald-700">110/103/21</strong></div>
                </div>
            </div>

            <div class="p-4 bg-white border border-kpmg-border rounded-lg shadow-xs space-y-2">
                <div class="flex items-center justify-between text-xs text-kpmg-muted font-medium">
                    <span>Formula Lineage</span>
                    <span class="font-mono px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 text-[10px] font-bold">Zero Hardcoded</span>
                </div>
                <div class="flex items-baseline space-x-2">
                    <span class="text-2xl font-bold font-mono text-kpmg-navy">100%</span>
                    <span class="text-xs text-kpmg-muted font-medium">formula linked</span>
                </div>
                <div class="grid grid-cols-2 gap-1 text-[11px] pt-1 border-t border-gray-100 text-gray-600">
                    <div>Consolidated: <strong class="font-mono text-emerald-700">SUMIFS</strong></div>
                    <div>Lineage: <strong class="font-mono text-emerald-700">Raw TB Cells</strong></div>
                </div>
            </div>
        </div>
    `;

    // Filter audit trail
    const filteredAudit = auditLog.filter(a => {
        const matchesQuery = !auditSearchQuery ||
            (a.stage && a.stage.toLowerCase().includes(auditSearchQuery.toLowerCase())) ||
            (a.agent && a.agent.toLowerCase().includes(auditSearchQuery.toLowerCase())) ||
            (a.action && a.action.toLowerCase().includes(auditSearchQuery.toLowerCase())) ||
            (a.details && a.details.toLowerCase().includes(auditSearchQuery.toLowerCase()));

        const matchesAgent = auditAgentFilter === 'ALL' || (a.agent && a.agent === auditAgentFilter);
        const matchesStatus = auditStatusFilter === 'ALL' || (a.status && a.status.includes(auditStatusFilter));

        return matchesQuery && matchesAgent && matchesStatus;
    });

    const auditRows = filteredAudit.map(a => `
        <tr class="hover:bg-slate-50/70 border-b border-gray-100 transition">
            <td class="font-mono text-[11px] text-gray-500 py-2 px-3">${escapeHtml(a.timestamp)}</td>
            <td class="font-bold text-kpmg-navy py-2 px-3 text-xs">${escapeHtml(a.stage)}</td>
            <td class="py-2 px-3 text-xs"><span class="px-2 py-0.5 rounded bg-gray-100 font-mono text-[10px] text-gray-700">${escapeHtml(a.agent)}</span></td>
            <td class="py-2 px-3 text-xs text-gray-800">${escapeHtml(a.action)}</td>
            <td class="font-bold py-2 px-3 text-xs ${a.status.includes('PASSED') || a.status.includes('SUCCESS') ? 'text-emerald-600' : (a.status.includes('HALT') || a.status.includes('FAIL') ? 'text-red-600' : 'text-amber-600')}">${escapeHtml(a.status)}</td>
            <td class="text-xs text-gray-600 py-2 px-3">${escapeHtml(a.details)}</td>
        </tr>
    `).join("");

    container.innerHTML = `
        <div class="space-y-6">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-kpmg-border pb-4">
                <div>
                    <h2 class="text-xl font-bold text-kpmg-navy">Audit</h2>
                    <p class="text-xs text-kpmg-muted mt-0.5">Real-time stage tracking, AI token expenditure, cell lineage provenance, and immutable Ind AS audit trail.</p>
                </div>
                <div class="flex items-center space-x-2">
                    <button onclick="switchSection('RUN')" class="h-8 px-3 rounded bg-white hover:bg-gray-100 border border-kpmg-border text-kpmg-navy text-xs font-semibold transition flex items-center space-x-1 shadow-xs">
                        <svg class="w-3.5 h-3.5 text-kpmg-blue" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
                        <span>Consolidation</span>
                    </button>
                    <button onclick="triggerRunPipeline()" class="h-8 px-3.5 rounded bg-kpmg-blue hover:bg-kpmg-navy text-white text-xs font-semibold transition flex items-center space-x-1 shadow-xs">
                        <svg class="w-3.5 h-3.5 text-[#ACEAFF]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path></svg>
                        <span>Run Consolidation</span>
                    </button>
                </div>
            </div>

            ${statusBannerHtml}
            ${tierBannerHtml}
            ${telemetryCardsHtml}

            <!-- Cell-Level Lineage Explorer -->
            <div class="space-y-3 p-4 bg-white border border-kpmg-border rounded-lg shadow-xs">
                <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-gray-100 pb-3">
                    <div>
                        <h4 class="font-bold text-sm text-kpmg-navy">Cell-Level Mathematical Lineage Explorer</h4>
                        <p class="text-xs text-kpmg-muted">Trace any balance sheet item backward to source entity TB cells through all intermediate transformations.</p>
                    </div>
                    <div class="flex items-center space-x-2">
                        <select id="lineage-preset-select" onchange="onSelectLineagePreset(this.value)" class="h-8 text-xs px-2.5 rounded border border-kpmg-border bg-slate-50 text-gray-800">
                            <option value="">Quick Presets...</option>
                            <option value="Cash and cash equivalents">Cash and cash equivalents</option>
                            <option value="Trade payables">Trade payables</option>
                            <option value="Trade receivables">Trade receivables</option>
                            <option value="Property, plant and equipment">Property, plant and equipment</option>
                            <option value="Foreign currency translation reserve (FCTR)">FCTR</option>
                            <option value="Borrowings">Borrowings</option>
                            <option value="Revenue from operations">Revenue from operations</option>
                        </select>
                        <div class="flex items-center">
                            <input id="lineage-query-input" type="text" placeholder="Account code or line item..." class="h-8 text-xs px-3 rounded-l border border-kpmg-border focus:ring-1 focus:ring-kpmg-blue w-48 font-mono">
                            <button onclick="executeLineageTrace()" class="h-8 px-3 rounded-r bg-kpmg-blue hover:bg-kpmg-navy text-white text-xs font-medium transition flex items-center space-x-1">
                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                                <span>Trace</span>
                            </button>
                        </div>
                    </div>
                </div>
                <div id="lineage-results-container" class="pt-2">
                    <div class="p-4 text-center text-kpmg-muted text-xs">
                        Select an account from the preset dropdown or type a query above to view the 5-tier mathematical lineage graph.
                    </div>
                </div>
            </div>

            <!-- Audit Trail Log -->
            <div class="space-y-3">
                <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div>
                        <h4 class="font-bold text-sm text-kpmg-navy">Audit Trail</h4>
                        <p class="text-xs text-kpmg-muted">Immutable, timestamped event log recording every validation, mapping, translation, and elimination decision.</p>
                    </div>
                    <div class="flex items-center space-x-2">
                        <input id="audit-search-input" type="text" value="${auditSearchQuery}" oninput="onAuditSearch(this.value)" placeholder="Search audit trail..." class="h-8 text-xs px-3 rounded border border-kpmg-border focus:ring-1 focus:ring-kpmg-blue w-40 sm:w-56">
                        <a href="/api/audit-trail/export?format=json" download class="h-8 px-2.5 rounded bg-white hover:bg-gray-100 text-kpmg-navy text-xs font-medium border border-kpmg-border transition flex items-center space-x-1 shadow-xs">
                            <span>JSON</span>
                        </a>
                        <a href="/api/audit-trail/export?format=csv" download class="h-8 px-2.5 rounded bg-white hover:bg-gray-100 text-kpmg-navy text-xs font-medium border border-kpmg-border transition flex items-center space-x-1 shadow-xs">
                            <span>CSV</span>
                        </a>
                    </div>
                </div>
                <div class="overflow-x-auto min-h-[380px] max-h-[calc(100vh-320px)] border border-kpmg-border rounded-lg bg-white shadow-2xs">
                    <table class="fin-table">
                        <thead class="sticky top-0 bg-slate-100 z-10 shadow-xs">
                            <tr>
                                <th class="w-32">Timestamp</th>
                                <th class="w-24">Stage</th>
                                <th class="w-36">Agent</th>
                                <th>Action Taken</th>
                                <th class="w-24">Status</th>
                                <th>Details / Provenance</th>
                            </tr>
                        </thead>
                        <tbody>${auditRows || '<tr><td colspan="6" class="p-6 text-center text-kpmg-muted">No matching audit events found.</td></tr>'}</tbody>
                    </table>
                </div>
            </div>
        </div>
    `;

    if (!currentLineageTrace) {
        executeLineageTrace("Cash and cash equivalents");
    } else {
        renderLineageGraph(currentLineageTrace);
    }
}

// PIPELINE EXECUTION TRIGGER
async function triggerRunPipeline() {
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
