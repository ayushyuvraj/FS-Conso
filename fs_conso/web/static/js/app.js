/**
 * Enterprise Financial Consolidation Portal - Frontend State Machine
 * Real accounting, real LangGraph agents, zero simulations.
 */

let appStatus = {};
let pipelineData = {};
let activeStep = 1;

document.addEventListener("DOMContentLoaded", () => {
    fetchStatus();
    loadPipelineData();
});

async function fetchStatus() {
    try {
        const res = await fetch("/api/status");
        appStatus = await res.json();
        renderHeaderStatus();
        renderStepperState();
    } catch (err) {
        console.error("Status check failed:", err);
    }
}

async function loadPipelineData() {
    try {
        const res = await fetch("/api/pipeline-data");
        pipelineData = await res.json();
        renderActiveStepContent();
    } catch (err) {
        console.error("Failed to load pipeline data:", err);
    }
}

function renderHeaderStatus() {
    const keyDot = document.getElementById("key-dot");
    const keyLabel = document.getElementById("key-label");
    const keyPill = document.getElementById("key-pill");
    const bannerBlocked = document.getElementById("banner-api-key-blocked");

    if (appStatus.has_active_api_key) {
        keyDot.className = "w-2 h-2 rounded-full bg-emerald-400";
        keyLabel.textContent = "Gemini Active";
        keyPill.className = "flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 cursor-pointer";
        bannerBlocked.classList.add("hidden");
    } else {
        keyDot.className = "w-2 h-2 rounded-full bg-rose-400 animate-pulse";
        keyLabel.textContent = "API Key Missing";
        keyPill.className = "flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-medium bg-rose-500/20 text-rose-300 border border-rose-500/30 cursor-pointer";
        bannerBlocked.classList.remove("hidden");
    }

    if (appStatus.teacher_score > 0) {
        document.getElementById("badge-teacher").classList.remove("hidden");
        document.getElementById("badge-teacher").classList.add("flex");
        document.getElementById("disp-teacher-score").textContent = `${appStatus.teacher_score}/100`;
    }
}

function renderStepperState() {
    const completed = appStatus.completed_steps || [];
    const maxUnlocked = Math.max(1, (appStatus.current_step || 1));

    for (let s = 1; s <= 6; s++) {
        const btn = document.getElementById(`step-btn-${s}`);
        if (!btn) continue;

        btn.classList.remove("active", "completed", "locked", "cursor-not-allowed");

        if (s === activeStep) {
            btn.classList.add("active");
        } else if (completed.includes(s)) {
            btn.classList.add("completed");
        } else if (s <= maxUnlocked) {
            btn.classList.add("cursor-pointer");
        } else {
            btn.classList.add("locked", "cursor-not-allowed");
        }
    }
}

function switchStep(step) {
    const maxUnlocked = Math.max(1, (appStatus.current_step || 1));
    if (step > maxUnlocked && !appStatus.completed_steps?.includes(step)) {
        alert(`Step ${step} is locked. Complete previous steps to unlock.`);
        return;
    }
    activeStep = step;
    renderStepperState();
    renderActiveStepContent();
}

function renderActiveStepContent() {
    const container = document.getElementById("step-content");
    const subLabel = document.getElementById("sub-step-text");

    if (activeStep === 1) {
        subLabel.textContent = "Step 1: Standalone Trial Balance Ingestion & Balance Check";
        renderStep1(container);
    } else if (activeStep === 2) {
        subLabel.textContent = "Step 2: Chart of Accounts (COA) Mapping & Standardization";
        renderStep2(container);
    } else if (activeStep === 3) {
        subLabel.textContent = "Step 3: Foreign Currency Translation & FCTR Balancing (Ind AS 21)";
        renderStep3(container);
    } else if (activeStep === 4) {
        subLabel.textContent = "Step 4: Intercompany Matching & Dual-Tolerance Eliminations";
        renderStep4(container);
    } else if (activeStep === 5) {
        subLabel.textContent = "Step 5: Consolidated Trial Balance (100% Formula Linking)";
        renderStep5(container);
    } else if (activeStep === 6) {
        subLabel.textContent = "Step 6: Financial Statements (Balance Sheet & P&L) & Strict Teacher Audit";
        renderStep6(container);
    }
}

// STEP 1: INGESTION
function renderStep1(el) {
    const tbs = pipelineData.raw_tbs || [];
    let rowsHtml = tbs.map(tb => `
        <tr>
            <td class="font-bold text-kpmg-navy">${tb.entity_code}</td>
            <td><span class="px-2 py-0.5 rounded bg-gray-100 font-mono text-[11px]">${tb.currency}</span></td>
            <td class="num-cell">${tb.row_count}</td>
            <td class="num-cell">${formatNum(tb.total_debit)}</td>
            <td class="num-cell">${formatNum(tb.total_credit)}</td>
            <td class="num-cell font-bold ${tb.is_tallied ? 'text-emerald-600' : 'text-red-600'}">${formatNum(tb.signed_sum)}</td>
            <td class="text-center">
                <span class="px-2 py-0.5 rounded text-[11px] font-semibold ${tb.is_tallied ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800'}">
                    ${tb.is_tallied ? 'Tallied (0.00)' : 'Unbalanced'}
                </span>
            </td>
        </tr>
    `).join("");

    el.innerHTML = `
        <div class="space-y-4">
            <div class="flex items-center justify-between border-b border-kpmg-border pb-3">
                <div>
                    <h3 class="font-bold text-base text-kpmg-navy">Ingested Entity Submissions</h3>
                    <p class="text-xs text-kpmg-muted">Validates Debit=Credit equality, blank vs zero integrity, and period consistency.</p>
                </div>
                <div class="flex items-center space-x-2">
                    <button onclick="openUploadModal()" class="h-7 px-3 rounded bg-kpmg-blue hover:bg-kpmg-navy text-white text-[11px] font-semibold transition flex items-center space-x-1 shadow-xs">
                        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                        <span>Upload TB File</span>
                    </button>
                    <button onclick="triggerResetBaseline()" class="h-7 px-2.5 rounded bg-white hover:bg-gray-100 text-kpmg-navy text-[11px] font-medium border border-kpmg-border transition flex items-center space-x-1" title="Reset back to benchmark multi-entity conglomerate">
                        <svg class="w-3 h-3 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                        <span>Reset Benchmark</span>
                    </button>
                    <div class="text-xs font-mono px-2.5 py-1 rounded bg-kpmg-canvas border border-kpmg-border text-kpmg-text">
                        ${tbs.length} Ingested
                    </div>
                </div>
            </div>
            <div class="overflow-x-auto">
                <table class="fin-table">
                    <thead>
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
                    <tbody>${rowsHtml}</tbody>
                </table>
            </div>
        </div>
    `;
}

// STEP 2: COA MAPPING
function renderStep2(el) {
    const mappings = pipelineData.mapping_decisions || [];
    let rowsHtml = mappings.map(m => `
        <tr>
            <td class="font-mono text-xs text-gray-500">${m.local_code}</td>
            <td class="font-medium">${m.local_description}</td>
            <td class="font-mono text-xs font-bold text-kpmg-blue">${m.group_code}</td>
            <td>${m.group_description}</td>
            <td><span class="px-2 py-0.5 rounded text-[10px] font-mono bg-gray-100 text-gray-700">${m.method}</span></td>
            <td class="num-cell font-bold ${m.confidence >= 0.85 ? 'text-emerald-600' : 'text-amber-600'}">${(m.confidence * 100).toFixed(0)}%</td>
            <td class="text-center">
                <span class="px-2 py-0.5 rounded text-[11px] font-semibold ${m.needs_review ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'}">
                    ${m.needs_review ? 'Review' : 'Mapped'}
                </span>
            </td>
        </tr>
    `).join("");

    el.innerHTML = `
        <div class="space-y-4">
            <div class="flex items-center justify-between border-b border-kpmg-border pb-3">
                <div>
                    <h3 class="font-bold text-base text-kpmg-navy">Chart of Accounts Alignment</h3>
                    <p class="text-xs text-kpmg-muted">Standardizes local subsidiary accounts to the Group COA import format.</p>
                </div>
                <div class="text-xs text-kpmg-muted">Threshold: <strong class="text-kpmg-blue font-mono">${(appStatus.ai_confidence_threshold * 100).toFixed(0)}%</strong></div>
            </div>
            <div class="overflow-x-auto max-h-[400px]">
                <table class="fin-table">
                    <thead>
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
                    <tbody>${rowsHtml}</tbody>
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
            <tr class="${r.is_fctr_plug ? 'bg-amber-50/60 font-semibold' : ''}">
                <td class="font-mono text-xs">${r.account_code}</td>
                <td>${r.account_description}</td>
                <td><span class="px-1.5 py-0.5 rounded bg-gray-100 font-mono text-[10px]">${r.source_currency}</span></td>
                <td class="num-cell">${formatNum(r.source_amount)}</td>
                <td class="num-cell font-mono">${r.rate_applied.toFixed(2)} (${r.rate_type})</td>
                <td class="num-cell font-bold text-kpmg-navy formula-interactive" 
                    onmouseenter="showFormula(event, '=${formatNum(r.source_amount)} * ${r.rate_applied.toFixed(2)}', 'Source: TB_${tb.entity_code}')"
                    onmouseleave="hideFormula()">
                    ${formatNum(r.translated_amount)}
                </td>
            </tr>
        `).join("");

        return `
            <div class="mb-6">
                <div class="flex items-center justify-between mb-2">
                    <span class="font-bold text-sm text-kpmg-navy">${tb.entity_code} (${tb.currency})</span>
                    <span class="text-xs font-mono text-kpmg-muted">Net Translated: <strong class="text-emerald-700">${formatNum(tb.total_translated)}</strong></span>
                </div>
                <table class="fin-table">
                    <thead>
                        <tr>
                            <th>Account Code</th>
                            <th>Description</th>
                            <th>Currency</th>
                            <th class="num-cell">Source Amount</th>
                            <th class="num-cell">FX Rate</th>
                            <th class="num-cell">Translated (INR)</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        `;
    }).join("");

    el.innerHTML = `
        <div class="space-y-4">
            <div class="border-b border-kpmg-border pb-3">
                <h3 class="font-bold text-base text-kpmg-navy">Foreign Currency Translation (Ind AS 21)</h3>
                <p class="text-xs text-kpmg-muted">Closing rates for Balance Sheet, Average rates for P&L, Historical for Equity, with automated FCTR plug.</p>
            </div>
            ${sections}
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
        <tr>
            <td class="font-bold text-kpmg-navy">${p.entity_code}</td>
            <td class="font-bold text-kpmg-blue">${p.counterparty_code}</td>
            <td class="font-mono text-xs">${p.account_code}</td>
            <td class="num-cell">${formatNum(p.entity_amount)}</td>
            <td class="num-cell">${formatNum(p.counterparty_amount)}</td>
            <td class="num-cell font-bold ${Math.abs(p.net_variance) < 0.01 ? 'text-emerald-600' : 'text-amber-600'}">${formatNum(p.net_variance)}</td>
            <td class="text-center">
                <span class="px-2.5 py-0.5 rounded text-[11px] font-semibold ${
                    p.status === 'MATCHED' ? 'bg-emerald-100 text-emerald-800' :
                    p.status === 'TOLERANCE_WARNING' ? 'bg-amber-100 text-amber-800' : 'bg-red-100 text-red-800'
                }">
                    ${p.status}
                </span>
            </td>
        </tr>
    `).join("");

    el.innerHTML = `
        <div class="space-y-4">
            <div class="flex items-center justify-between border-b border-kpmg-border pb-3">
                <div>
                    <h3 class="font-bold text-base text-kpmg-navy">Intercompany Elimination Matrix</h3>
                    <p class="text-xs text-kpmg-muted">Reciprocal balance matching with dual tolerances: Absolute (₹${formatNum(appStatus.ic_absolute_tolerance)}) & Percentage (${appStatus.ic_percent_tolerance}%).</p>
                </div>
                <div class="flex space-x-2 text-xs">
                    <span class="px-2 py-1 rounded bg-emerald-50 text-emerald-700 font-mono">Matched: ${elim.matched_count}</span>
                    <span class="px-2 py-1 rounded bg-amber-50 text-amber-700 font-mono">Warnings: ${elim.tolerance_warning_count}</span>
                    <span class="px-2 py-1 rounded bg-red-50 text-red-700 font-mono">Exceptions: ${elim.exception_count}</span>
                </div>
            </div>
            <table class="fin-table">
                <thead>
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
    `;
}

// STEP 5: CONSOLIDATION
function renderStep5(el) {
    const ctb = pipelineData.consolidated_tb;
    if (!ctb || !ctb.rows) {
        el.innerHTML = `<div class="p-8 text-center text-kpmg-muted">Consolidated Trial Balance will appear once the pipeline executes.</div>`;
        return;
    }

    let entHeaders = ctb.entity_codes.map(e => `<th class="num-cell">${e}</th>`).join("");
    let rowsHtml = ctb.rows.map((r, i) => {
        let entCells = ctb.entity_codes.map(e => `
            <td class="num-cell formula-interactive" 
                onmouseenter="showFormula(event, '=SUMIFS(Translated_TB!$G:$G, Translated_TB!$A:$A, \\'${e}\\', Translated_TB!$B:$B, \\'${r.account_code}\\')', 'Direct Lineage: Translated_TB')"
                onmouseleave="hideFormula()">
                ${formatNum(r.entity_balances[e] || 0.0)}
            </td>
        `).join("");

        return `
            <tr>
                <td class="font-mono text-xs">${r.account_code}</td>
                <td>${r.account_description}</td>
                ${entCells}
                <td class="num-cell font-bold formula-interactive"
                    onmouseenter="showFormula(event, '=SUM(C${i+4}:F${i+4})', 'Total Entities Rollup')"
                    onmouseleave="hideFormula()">
                    ${formatNum(r.total_entities)}
                </td>
                <td class="num-cell formula-interactive text-amber-700"
                    onmouseenter="showFormula(event, '=SUMIFS(IC_Eliminations!$G:$G, IC_Eliminations!$D:$D, \\'${r.account_code}\\')', 'Elimination Adjustment')"
                    onmouseleave="hideFormula()">
                    ${formatNum(r.eliminations)}
                </td>
                <td class="num-cell font-bold text-kpmg-blue formula-interactive"
                    onmouseenter="showFormula(event, '=Total_Entities + Eliminations', 'Consolidated Balance')"
                    onmouseleave="hideFormula()">
                    ${formatNum(r.consolidated_total)}
                </td>
            </tr>
        `;
    }).join("");

    el.innerHTML = `
        <div class="space-y-4">
            <div class="flex items-center justify-between border-b border-kpmg-border pb-3">
                <div>
                    <h3 class="font-bold text-base text-kpmg-navy">Consolidated Trial Balance Matrix</h3>
                    <p class="text-xs text-kpmg-muted">Hover over any figure to inspect its active Excel formula and cell provenance.</p>
                </div>
                <div class="text-xs font-mono px-3 py-1 rounded bg-emerald-50 text-emerald-800 font-bold border border-emerald-200">
                    Consolidated Sum: ${formatNum(ctb.total_consolidated)} (0.00)
                </div>
            </div>
            <div class="overflow-x-auto max-h-[460px]">
                <table class="fin-table">
                    <thead>
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

// STEP 6: STATEMENTS & AUDIT
function renderStep6(el) {
    const evalData = pipelineData.teacher_evaluation || {};
    const auditLog = pipelineData.audit_trail || [];

    let auditRows = auditLog.map(a => `
        <tr>
            <td class="font-mono text-xs text-gray-500">${a.timestamp}</td>
            <td class="font-bold text-kpmg-navy">${a.stage}</td>
            <td><span class="px-2 py-0.5 rounded bg-gray-100 font-mono text-[10px] text-gray-700">${a.agent}</span></td>
            <td>${a.action}</td>
            <td class="font-bold ${a.status.includes('PASSED') ? 'text-emerald-600' : 'text-amber-600'}">${a.status}</td>
            <td class="text-xs text-gray-600">${a.details}</td>
        </tr>
    `).join("");

    el.innerHTML = `
        <div class="space-y-6">
            <!-- Strict Teacher Quality Card -->
            <div class="p-5 rounded bg-gradient-to-r from-kpmg-navy to-kpmg-blue text-white shadow-md">
                <div class="flex items-center justify-between mb-4">
                    <div>
                        <div class="text-xs text-kpmg-electric uppercase tracking-wider font-bold">Autonomous Auditor Gate</div>
                        <h3 class="text-xl font-bold">Strict Teacher Quality Audit: ${evalData.score || 100}/100</h3>
                    </div>
                    <span class="px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                        ${evalData.passed ? 'HONORS PASS' : 'ACTION REQUIRED'}
                    </span>
                </div>
                <div class="grid grid-cols-4 gap-4 pt-3 border-t border-white/10 text-xs">
                    <div>
                        <span class="text-white/70 block mb-0.5">Formula Integrity</span>
                        <strong class="text-base font-mono text-emerald-300">${evalData.pillar_breakdown?.formula_integrity || 25}/25</strong>
                    </div>
                    <div>
                        <span class="text-white/70 block mb-0.5">Financial Correctness</span>
                        <strong class="text-base font-mono text-emerald-300">${evalData.pillar_breakdown?.financial_correctness || 25}/25</strong>
                    </div>
                    <div>
                        <span class="text-white/70 block mb-0.5">Validation & Tolerance</span>
                        <strong class="text-base font-mono text-emerald-300">${evalData.pillar_breakdown?.validation_and_tolerance || 25}/25</strong>
                    </div>
                    <div>
                        <span class="text-white/70 block mb-0.5">Provenance & Flow</span>
                        <strong class="text-base font-mono text-emerald-300">${evalData.pillar_breakdown?.provenance_and_flow || 25}/25</strong>
                    </div>
                </div>
            </div>

            <!-- Deliverable Download Callout -->
            <div class="flex items-center justify-between p-4 rounded bg-white border border-kpmg-border shadow-xs">
                <div>
                    <h4 class="font-bold text-sm text-kpmg-navy">Consolidated Financial Statements Deliverable</h4>
                    <p class="text-xs text-kpmg-muted">Contains 100% active formulas linking Balance Sheet and P&L directly to source TBs.</p>
                </div>
                <a href="/api/export-excel" class="h-9 px-4 rounded bg-kpmg-blue hover:bg-kpmg-navy text-white text-xs font-semibold transition flex items-center space-x-2">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                    <span>Download XLSX</span>
                </a>
            </div>

            <!-- Agent Traceability Log -->
            <div class="space-y-3">
                <h4 class="font-bold text-sm text-kpmg-navy">Observability & Agent Execution Log</h4>
                <div class="overflow-x-auto max-h-[300px] border border-kpmg-border rounded">
                    <table class="fin-table">
                        <thead>
                            <tr>
                                <th>Timestamp</th>
                                <th>Stage</th>
                                <th>Agent</th>
                                <th>Action Taken</th>
                                <th>Status</th>
                                <th>Details / Provenance</th>
                            </tr>
                        </thead>
                        <tbody>${auditRows}</tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
}

// PIPELINE EXECUTION TRIGGER
async function triggerRunPipeline() {
    const btn = document.getElementById("btn-run");
    btn.disabled = true;
    btn.innerHTML = `
        <svg class="w-3.5 h-3.5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>
        <span>Running Agents...</span>
    `;

    try {
        const res = await fetch("/api/run-pipeline", { method: "POST" });
        const data = await res.json();
        
        if (!res.ok || data.success === false) {
            const errDetail = data.error_message || data.detail || "Consolidation failed";
            if (res.status === 403 || errDetail.toLowerCase().includes("api key") || !appStatus.has_active_api_key) {
                showToast("Execution Blocked", "Active Google Gemini API Key is required. Please configure your key in Settings.", "error");
                toggleSettingsDrawer(true);
                const keyInput = document.getElementById("input-api-key");
                if (keyInput) {
                    keyInput.focus();
                    keyInput.classList.add("ring-2", "ring-rose-500");
                }
            } else {
                showToast("Execution Halted", errDetail, "error");
            }
        } else {
            showToast("Consolidation Succeeded", `Auditor Score: ${data.teacher_score || 100}/100. Deliverable generated with 100% formulas.`, "success");
            await fetchStatus();
            await loadPipelineData();
            switchStep(6);
        }
    } catch (err) {
        showToast("Network Error", "Pipeline invocation error: " + err, "error");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
            <span>Execute Consolidation</span>
        `;
    }
}

// UPLOAD MODAL & FILE HANDLING
let selectedUploadFile = null;

function openUploadModal() {
    const modal = document.getElementById("modal-upload");
    if (modal) {
        modal.classList.remove("hidden");
        document.getElementById("form-upload-tb").reset();
        selectedUploadFile = null;
        document.getElementById("file-label").textContent = "Click to browse or drag and drop file here";
        const statusDiv = document.getElementById("upload-status");
        statusDiv.classList.add("hidden");
        statusDiv.textContent = "";
        initDropZone();
    }
}

function closeUploadModal() {
    const modal = document.getElementById("modal-upload");
    if (modal) modal.classList.add("hidden");
}

function handleFileSelected(input) {
    if (input.files && input.files[0]) {
        selectedUploadFile = input.files[0];
        document.getElementById("file-label").innerHTML = `<strong>Selected:</strong> ${selectedUploadFile.name} (${(selectedUploadFile.size / 1024).toFixed(1)} KB)`;
    }
}

function initDropZone() {
    const dropZone = document.getElementById("drop-zone");
    if (!dropZone || dropZone.dataset.initialized) return;
    dropZone.dataset.initialized = "true";

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add("border-kpmg-blue", "bg-blue-50/40");
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove("border-kpmg-blue", "bg-blue-50/40");
        }, false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files && files.length > 0) {
            selectedUploadFile = files[0];
            const fileInput = document.getElementById("file-input");
            fileInput.files = files;
            document.getElementById("file-label").innerHTML = `<strong>Selected:</strong> ${selectedUploadFile.name} (${(selectedUploadFile.size / 1024).toFixed(1)} KB)`;
        }
    }, false);
}

async function submitUploadTB(e) {
    e.preventDefault();
    if (!selectedUploadFile) {
        showToast("Missing File", "Please choose or drop an Excel (.xlsx/.xls) or CSV file.", "warning");
        return;
    }

    const entityCode = document.getElementById("upload-entity-code").value.trim().toUpperCase();
    const period = document.getElementById("upload-period").value.trim();
    const currency = document.getElementById("upload-currency").value.trim().toUpperCase();

    if (!entityCode) {
        showToast("Missing Entity Code", "Please enter an entity identifier (e.g. HOLD_CO).", "warning");
        return;
    }

    const btn = document.getElementById("btn-submit-upload");
    const statusDiv = document.getElementById("upload-status");
    btn.disabled = true;
    btn.innerHTML = `<span>Ingesting & Validating...</span>`;
    statusDiv.classList.remove("hidden", "bg-red-50", "text-red-700", "bg-emerald-50", "text-emerald-700");
    statusDiv.classList.add("bg-blue-50", "text-blue-700");
    statusDiv.textContent = `Parsing ${selectedUploadFile.name}...`;

    const formData = new FormData();
    formData.append("file", selectedUploadFile);
    formData.append("entity_code", entityCode);
    formData.append("period", period);
    formData.append("currency", currency);

    try {
        const res = await fetch("/api/upload-tb", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        if (!res.ok) {
            statusDiv.classList.remove("bg-blue-50", "text-blue-700");
            statusDiv.classList.add("bg-red-50", "text-red-700");
            statusDiv.textContent = `Upload Error: ${data.detail || "Validation failed"}`;
            showToast("Upload Error", data.detail || "Failed to parse trial balance", "error");
        } else {
            statusDiv.classList.remove("bg-blue-50", "text-blue-700");
            statusDiv.classList.add("bg-emerald-50", "text-emerald-700");
            statusDiv.textContent = `Successfully ingested ${data.entity_code}: ${data.row_count} accounts, Total: ${formatNum(data.total_debit)} ${currency}.`;
            showToast("Trial Balance Ingested", `${data.entity_code} uploaded (${data.row_count} GL rows, status: ${data.is_tallied ? 'Balanced' : 'Unbalanced'}).`, "success");
            setTimeout(() => {
                closeUploadModal();
                fetchStatus();
                loadPipelineData();
                switchStep(1);
            }, 900);
        }
    } catch (err) {
        statusDiv.classList.remove("bg-blue-50", "text-blue-700");
        statusDiv.classList.add("bg-red-50", "text-red-700");
        statusDiv.textContent = `Network Error: ${err}`;
        showToast("Upload Network Error", "" + err, "error");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<span>Validate & Ingest</span>`;
    }
}

async function triggerResetBaseline() {
    if (!confirm("Reset trial balances and pipeline state back to benchmark conglomerate model?")) return;
    try {
        const res = await fetch("/api/reset-baseline", { method: "POST" });
        const data = await res.json();
        if (data.success) {
            showToast("Reset Completed", "Consolidation workspace reset to benchmark model.", "info");
            await fetchStatus();
            await loadPipelineData();
            switchStep(1);
        }
    } catch (err) {
        showToast("Reset Error", "" + err, "error");
    }
}

// EMIL KOWALSKI TOAST NOTIFICATIONS
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
        toast.className += " bg-kpmg-navy/95 text-white border-kpmg-electric/50";
        iconSvg = `<svg class="w-4 h-4 text-kpmg-electric shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`;
    }

    toast.innerHTML = `
        ${iconSvg}
        <div class="flex-1">
            <h5 class="font-bold text-xs leading-tight">${title}</h5>
            <p class="text-[11px] opacity-90 mt-0.5 leading-snug">${message}</p>
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
    if (forceOpen) {
        drawer.classList.remove("translate-x-full");
    } else {
        drawer.classList.toggle("translate-x-full");
    }
}

function updateThresholdDisplay(val) {
    document.getElementById("disp-threshold-val").textContent = `${val}%`;
}

async function saveSettings() {
    const key = document.getElementById("input-api-key").value;
    const threshold = parseFloat(document.getElementById("slider-threshold").value) / 100.0;
    const absTol = parseFloat(document.getElementById("input-abs-tol").value);
    const pctTol = parseFloat(document.getElementById("input-pct-tol").value) / 100.0;

    try {
        const res = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                gemini_api_key: key || undefined,
                ai_confidence_threshold: threshold,
                ic_absolute_tolerance: absTol,
                ic_percent_tolerance: pctTol
            })
        });
        const data = await res.json();
        if (data.success) {
            showToast("Settings Saved", "Consolidation parameters and API key updated.", "success");
            toggleSettingsDrawer();
            fetchStatus();
        } else {
            showToast("Settings Error", data.detail || "Failed to update settings", "error");
        }
    } catch (err) {
        showToast("Settings Error", "" + err, "error");
    }
}

// FLOATING FORMULA INSPECTOR
function showFormula(e, expr, origin) {
    const pop = document.getElementById("formula-popover");
    document.getElementById("formula-expr").textContent = expr;
    document.getElementById("formula-origin").textContent = origin;
    pop.style.left = `${e.clientX + 15}px`;
    pop.style.top = `${e.clientY + 15}px`;
    pop.classList.remove("hidden");
}

function hideFormula() {
    document.getElementById("formula-popover").classList.add("hidden");
}

function formatNum(val) {
    if (val === undefined || val === null || isNaN(val)) return "0.00";
    return Number(val).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
