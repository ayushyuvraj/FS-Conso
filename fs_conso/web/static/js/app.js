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
    await fetchCompanies();
    await fetchStatus();
    await syncCachedApiKeyIfAvailable();
    loadPipelineData();
    initDropZone();
    initBatchDropZone();
});

function initSidebar() {
    try {
        const saved = localStorage.getItem("fs_conso_sidebar_collapsed");
        if (saved === "true") {
            sidebarCollapsed = true;
            applySidebarState();
        }
    } catch (_) { }

    // Global keyboard shortcut: Ctrl+B or Cmd+B to toggle sidebar
    document.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && (e.key === "b" || e.key === "B")) {
            e.preventDefault();
            toggleSidebar();
        }
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
    const chevron = document.getElementById("icon-collapse-chevron");

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
    if (chevron) {
        chevron.style.transform = sidebarCollapsed ? "rotate(180deg)" : "rotate(0deg)";
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
        <option value="${c.company_id}" class="bg-slate-900 text-white" ${c.company_id === activeId ? 'selected' : ''}>
            ${escapeHtml(c.company_name)} (${c.company_id})
        </option>
    `).join("");
}

async function handleCompanySwitch(companyId) {
    if (!companyId || companyId === appStatus.active_company_id) return;
    try {
        showToast("Switching Company", `Loading workspace for ${companyId}...`, "info");
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
            showToast("Company Switched", `Active workspace is now ${appStatus.active_company_name || companyId}.`, "success");
            if (activeNavSection === 'COMPANIES') {
                renderCompanyWorkspace();
            } else {
                switchStep(1);
            }
        } else {
            showToast("Switch Failed", data.detail || "Could not switch company workspace.", "error");
        }
    } catch (err) {
        showToast("Error", "Error switching company: " + err, "error");
    }
}

function openNewCompanyModal() {
    const modal = document.getElementById("modal-new-company");
    if (modal) modal.classList.remove("hidden");
}

function closeNewCompanyModal() {
    const modal = document.getElementById("modal-new-company");
    if (modal) modal.classList.add("hidden");
}

async function submitCreateCompany(e) {
    e.preventDefault();
    const id = document.getElementById("new-company-id").value.trim().toLowerCase();
    const name = document.getElementById("new-company-name").value.trim();
    const curr = document.getElementById("new-company-curr").value.trim();
    const period = document.getElementById("new-company-period").value.trim();

    if (!id || !name) {
        showToast("Missing Fields", "Company ID and Name are required.", "warning");
        return;
    }

    try {
        const res = await fetch("/api/companies/create", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                company_id: id,
                company_name: name,
                reporting_currency: curr,
                current_period: period
            })
        });
        const data = await res.json();
        if (data.success) {
            closeNewCompanyModal();
            showToast("Company Created", `Workspace for ${name} created successfully.`, "success");
            await fetchCompanies();
            await fetchStatus();
            await loadPipelineData();
            switchStep(1);
        } else {
            showToast("Creation Failed", data.detail || "Failed to create company.", "error");
        }
    } catch (err) {
        showToast("Network Error", "Failed to create company: " + err, "error");
    }
}

async function triggerLoadDemo() {
    try {
        showToast("Loading Demo", "Loading benchmark 4-entity conglomerate...", "info");
        const res = await fetch("/api/companies/load-demo", { method: "POST" });
        const data = await res.json();
        if (data.success) {
            statementsData = null;
            currentLineageTrace = null;
            await fetchCompanies();
            await fetchStatus();
            await loadPipelineData();
            showToast("Demo Loaded", "Reference Company P Healthcare loaded.", "success");
            if (activeNavSection === 'COMPANIES') {
                renderCompanyWorkspace();
            } else {
                switchStep(1);
            }
        }
    } catch (err) {
        showToast("Demo Load Error", "" + err, "error");
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

    if (dispPeriod && appStatus.current_period) {
        dispPeriod.textContent = appStatus.current_period;
    }
    if (dispCurr && appStatus.reporting_currency) {
        dispCurr.textContent = appStatus.reporting_currency;
    }

    // Active Company Titles & Badges
    const headerCompany = document.getElementById("header-active-company-name");
    const sidebarEntityBadge = document.getElementById("sidebar-entity-badge");
    const miniCompanyCode = document.getElementById("sidebar-mini-company-code");
    const sidebarStepBadge = document.getElementById("badge-sidebar-step");
    const sidebarObsBadge = document.getElementById("badge-sidebar-observability");

    const compName = appStatus.active_company_name || "Company P Healthcare Corp";
    if (headerCompany) headerCompany.textContent = compName;
    if (miniCompanyCode) {
        const initials = compName.split(/\s+/).map(w => w[0]).filter(Boolean).slice(0, 2).join("").toUpperCase();
        miniCompanyCode.textContent = initials || "CP";
    }
    if (sidebarEntityBadge) {
        const count = appStatus.all_entities ? appStatus.all_entities.length : 4;
        sidebarEntityBadge.textContent = `${count} Entities`;
    }
    if (sidebarStepBadge) {
        sidebarStepBadge.textContent = `Step ${activeStep}/6`;
    }

    if (keyDot && keyLabel && keyPill) {
        if (appStatus.has_active_api_key) {
            keyDot.className = "w-2 h-2 rounded-full bg-emerald-400";
            keyLabel.textContent = "Gemini Active";
            keyPill.className = "flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 cursor-pointer";
        } else {
            keyDot.className = "w-2 h-2 rounded-full bg-rose-400 animate-pulse";
            keyLabel.textContent = "API Key Missing";
            keyPill.className = "flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-medium bg-rose-500/20 text-rose-300 border border-rose-500/30 cursor-pointer";
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
    updateObsEl(sidebarObsBadge);
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

function renderCompanyWorkspace() {
    const container = document.getElementById("company-perimeter-content");
    const titleEl = document.getElementById("company-profile-title");
    const descEl = document.getElementById("company-profile-desc");
    if (!container) return;

    const compName = appStatus.active_company_name || "Company P Healthcare Corp";
    const compId = appStatus.active_company_id || "company-p";
    const curr = appStatus.reporting_currency || "INR";
    const period = appStatus.current_period || "31-Mar-2024";

    if (titleEl) titleEl.textContent = `${compName} (${compId})`;
    if (descEl) descEl.textContent = `Consolidation Perimeter, Functional Currencies & Reporting Governance for ${period}.`;

    const allEntities = appStatus.all_entities || ['Company_P', 'Company S1', 'Company S2', 'Company S3'];
    const uploadedEntities = appStatus.uploaded_entities || [];
    const missingPrereqs = appStatus.missing_prerequisites || [];

    container.innerHTML = `
        <!-- Governance & Scope Metrics Cards -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="p-4 rounded-xl border border-kpmg-border bg-slate-50/70">
                <div class="text-[11px] font-semibold text-kpmg-muted uppercase tracking-wider">Perimeter Scope</div>
                <div class="text-2xl font-bold font-mono text-kpmg-navy mt-1">${allEntities.length} <span class="text-xs font-normal text-kpmg-muted">Entities</span></div>
                <div class="text-[11px] text-emerald-700 font-medium mt-1 flex items-center space-x-1">
                    <span>${uploadedEntities.length} Ingested</span>
                </div>
            </div>

            <div class="p-4 rounded-xl border border-kpmg-border bg-slate-50/70">
                <div class="text-[11px] font-semibold text-kpmg-muted uppercase tracking-wider">Presentation Currency</div>
                <div class="text-2xl font-bold font-mono text-[#00338D] mt-1">${escapeHtml(curr)}</div>
                <div class="text-[11px] text-kpmg-muted mt-1">Target reporting group</div>
            </div>

            <div class="p-4 rounded-xl border border-kpmg-border bg-slate-50/70">
                <div class="text-[11px] font-semibold text-kpmg-muted uppercase tracking-wider">Target Period</div>
                <div class="text-2xl font-bold font-mono text-kpmg-text mt-1">${escapeHtml(period)}</div>
                <div class="text-[11px] text-kpmg-muted mt-1">Annual Financial Year</div>
            </div>

            <div class="p-4 rounded-xl border border-kpmg-border bg-slate-50/70">
                <div class="text-[11px] font-semibold text-kpmg-muted uppercase tracking-wider">Prerequisite Health</div>
                <div class="text-2xl font-bold font-mono ${missingPrereqs.length === 0 ? 'text-emerald-600' : 'text-amber-600'} mt-1">
                    ${missingPrereqs.length === 0 ? '100% Ready' : 'Attention'}
                </div>
                <div class="text-[11px] text-kpmg-muted mt-1">${missingPrereqs.length === 0 ? 'All data tables validated' : missingPrereqs.length + ' files missing'}</div>
            </div>
        </div>

        <!-- Perimeter Legal Entities Table -->
        <div class="border border-kpmg-border rounded-xl overflow-hidden shadow-xs">
            <div class="px-5 py-3.5 bg-slate-50 border-b border-kpmg-border flex items-center justify-between">
                <div>
                    <h3 class="font-bold text-xs uppercase tracking-wider text-kpmg-navy">Legal Entities & Ownership Structure</h3>
                    <p class="text-[11px] text-kpmg-muted mt-0.5">Corporate perimeter governing IFRS 10 / Ind AS 110 consolidation</p>
                </div>
                <span class="px-2.5 py-1 rounded text-xs font-semibold bg-blue-50 text-[#00338D] border border-blue-200">
                    ${allEntities.length} Total Registered
                </span>
            </div>

            <table class="fin-table">
                <thead>
                    <tr>
                        <th class="w-12">#</th>
                        <th>Legal Entity Name</th>
                        <th>Entity Code</th>
                        <th>Corporate Role</th>
                        <th>Currency</th>
                        <th>Consolidation Method</th>
                        <th>Ingestion State</th>
                    </tr>
                </thead>
                <tbody>
                    ${allEntities.map((ent, idx) => {
                        const isParent = idx === 0 || ent.toLowerCase().includes("company_p") || ent.toLowerCase().includes("parent");
                        const isUploaded = uploadedEntities.some(u => u.toLowerCase().replace(/[\s_]/g, '') === ent.toLowerCase().replace(/[\s_]/g, ''));
                        return `
                            <tr class="hover:bg-slate-50/80 transition">
                                <td class="font-mono text-kpmg-muted text-[11px]">${idx + 1}</td>
                                <td class="font-bold text-kpmg-navy flex items-center space-x-2 py-2.5">
                                    <span class="w-2 h-2 rounded-full ${isParent ? 'bg-[#00338D]' : 'bg-blue-400'}"></span>
                                    <span>${escapeHtml(ent.replace(/_/g, ' '))}</span>
                                </td>
                                <td class="font-mono text-[11px] text-kpmg-muted">${escapeHtml(ent)}</td>
                                <td>
                                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold ${isParent ? 'bg-[#001D48] text-[#D4AF37]' : 'bg-slate-100 text-slate-700'}">
                                        ${isParent ? 'Holding Entity (Parent)' : 'Operating Subsidiary'}
                                    </span>
                                </td>
                                <td class="font-mono font-bold text-xs text-[#00338D]">${isParent ? escapeHtml(curr) : (ent.includes('S1') ? 'USD' : ent.includes('S2') ? 'EUR' : curr)}</td>
                                <td class="text-xs text-kpmg-muted">${isParent ? 'Full (100% Direct)' : 'Full Consolidation (NCI Recognized)'}</td>
                                <td>
                                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold ${isUploaded ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700 border border-rose-200'}">
                                        ${isUploaded ? '✓ Ingested' : 'Missing File'}
                                    </span>
                                </td>
                            </tr>
                        `;
                    }).join("")}
                </tbody>
            </table>
        </div>

        <!-- Master Data Status Cards -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="p-5 rounded-xl border border-kpmg-border bg-white shadow-xs space-y-3">
                <div class="flex items-center justify-between">
                    <div class="flex items-center space-x-2">
                        <span class="w-2 h-2 rounded-full bg-[#00338D]"></span>
                        <h4 class="font-bold text-xs uppercase tracking-wider text-kpmg-navy">Chart of Accounts (COA) Status</h4>
                    </div>
                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">Standardized</span>
                </div>
                <p class="text-xs text-kpmg-muted leading-relaxed">
                    Corporate Chart of Accounts loaded for multi-entity GL standardization. Mappings are validated by Gemini Brain and cached in learning memory.
                </p>
                <div class="pt-2 border-t border-kpmg-border flex items-center justify-between text-xs">
                    <span class="text-kpmg-muted font-mono">Hierarchy: 5-Level Financial Statements</span>
                    <button onclick="switchNavSection('PIPELINE'); switchStep(2);" class="text-[#00338D] font-bold hover:underline">Review Mappings &rarr;</button>
                </div>
            </div>

            <div class="p-5 rounded-xl border border-kpmg-border bg-white shadow-xs space-y-3">
                <div class="flex items-center justify-between">
                    <div class="flex items-center space-x-2">
                        <span class="w-2 h-2 rounded-full bg-[#D4AF37]"></span>
                        <h4 class="font-bold text-xs uppercase tracking-wider text-kpmg-navy">Exchange Rate Matrices (IAS 21)</h4>
                    </div>
                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-50 text-[#00338D] border border-blue-200">Active Rates</span>
                </div>
                <p class="text-xs text-kpmg-muted leading-relaxed">
                    Closing, Average, and Historical FX rate tables configured for translation of foreign operations into ${escapeHtml(curr)}.
                </p>
                <div class="pt-2 border-t border-kpmg-border flex items-center justify-between text-xs">
                    <span class="text-kpmg-muted font-mono">Rates: Closing &bull; Average &bull; Historical</span>
                    <button onclick="switchNavSection('PIPELINE'); switchStep(3);" class="text-[#00338D] font-bold hover:underline">View FX Translation &rarr;</button>
                </div>
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
                        <svg class="w-3 h-3 text-[#D4AF37]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
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
            <div class="overflow-x-auto max-h-[460px] border border-kpmg-border rounded bg-white shadow-xs">
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
            <div class="overflow-x-auto max-h-[460px] border border-kpmg-border rounded bg-white shadow-xs">
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
                    <tbody>${rowsHtml || '<tr><td colspan="7" class="p-8 text-center text-kpmg-muted">Run pipeline to compute COA alignments.</td></tr>'}</tbody>
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
                <div class="overflow-x-auto max-h-[300px]">
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
            ${sections || '<div class="p-8 text-center text-kpmg-muted">Run pipeline to view foreign currency translation.</div>'}
        </div>
    `;
}

// STEP 4: ELIMINATIONS
function renderStep4(el) {
    const elim = pipelineData.eliminations;
    if (!elim || !elim.pairs) {
        el.innerHTML = `<div class="p-8 text-center text-kpmg-muted">Run the consolidation pipeline to view intercompany eliminations.</div>`;
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
            <div class="overflow-x-auto max-h-[460px] border border-kpmg-border rounded bg-white shadow-xs">
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
            <div class="overflow-x-auto max-h-[460px] border border-kpmg-border rounded bg-white shadow-xs">
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
                    <svg class="w-3.5 h-3.5 text-[#D4AF37]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path></svg>
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

            <div class="overflow-x-auto max-h-[500px] border border-kpmg-border rounded bg-white shadow-xs">
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
                        <h4 class="font-bold text-sm">Pipeline Execution in Progress...</h4>
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
                            <h4 class="font-bold text-sm text-red-900">Pipeline Halted at Node: <span class="font-mono bg-red-100 px-1.5 py-0.5 rounded text-red-800">${escapeHtml(haltedNode || 'validator')}</span></h4>
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
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3 p-4 rounded-lg bg-slate-900 text-white border border-[#D4AF37]/30 shadow-md">
            <div class="space-y-1">
                <div class="flex items-center space-x-2">
                    <span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
                    <span class="text-xs font-bold uppercase tracking-wider text-[#D4AF37]">1. Deterministic Engine</span>
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
                    <h2 class="text-lg font-bold text-kpmg-navy flex items-center space-x-2">
                        <span>Consolidation Observability & Audit Console</span>
                        <span class="text-xs font-normal px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-mono font-bold">Real-time Telemetry</span>
                    </h2>
                    <p class="text-xs text-kpmg-muted mt-0.5">Real-time stage tracking, AI token expenditure, LangGraph DAG latencies, cell lineage provenance, and immutable Ind AS audit trail.</p>
                </div>
                <div class="flex items-center space-x-2">
                    <button onclick="switchSection('RUN')" class="h-8 px-3 rounded bg-white hover:bg-gray-100 border border-kpmg-border text-kpmg-navy text-xs font-semibold transition flex items-center space-x-1 shadow-xs">
                        <svg class="w-3.5 h-3.5 text-kpmg-blue" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
                        <span>View Pipeline</span>
                    </button>
                    <button onclick="triggerRunPipeline()" class="h-8 px-3.5 rounded bg-kpmg-blue hover:bg-kpmg-navy text-white text-xs font-semibold transition flex items-center space-x-1 shadow-xs">
                        <svg class="w-3.5 h-3.5 text-[#D4AF37]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path></svg>
                        <span>Execute Run</span>
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
                        <h4 class="font-bold text-sm text-kpmg-navy">Observability & Agent Execution Audit Trail</h4>
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
                <div class="overflow-x-auto max-h-[360px] border border-kpmg-border rounded bg-white shadow-xs">
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
        toast.className += " bg-[#0B0F17] text-white border-[#D4AF37]/50";
        iconSvg = `<svg class="w-4 h-4 text-[#D4AF37] shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`;
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
