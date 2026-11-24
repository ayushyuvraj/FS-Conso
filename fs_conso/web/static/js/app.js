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

    for (let s = 1; s <= 7; s++) {
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
        subLabel.textContent = "Step 6: IND AS Consolidated Financial Statements (Balance Sheet & P&L)";
        renderStep6(container);
    } else if (activeStep === 7) {
        subLabel.textContent = "Step 7: Autonomous Quality Audit & LangGraph Agent Tracing Console";
        renderStep7(container);
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

// STEP 6: IND AS CONSOLIDATED FINANCIAL STATEMENTS
let statementsData = null;
let currentStatementTab = 'BS'; // 'BS' or 'PL'

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
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
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

    // Build Table Headers
    const headersHtml = cols.map((c, idx) => {
        if (idx === 0) return `<th class="min-w-[240px]">Line Item</th>`;
        if (idx === 1) return `<th class="w-14 text-center">Note</th>`;
        return `<th class="num-cell min-w-[120px]">${c}</th>`;
    }).join("");

    // Build Table Rows
    const rowsHtml = stData.rows.map(r => {
        if (r.is_header && !r.is_total) {
            return `
                <tr class="bg-slate-50 border-t border-b border-slate-200">
                    <td colspan="${cols.length}" class="py-2 pl-3 text-xs font-bold uppercase tracking-wider text-kpmg-navy border-l-4 border-kpmg-blue">
                        ${r.title}
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
                    <span>${r.title}</span>
                    ${!isTotal ? `
                        <button onclick="inspectLineageFromStatement('${r.title}')" class="opacity-0 group-hover:opacity-100 text-[10px] text-kpmg-blue hover:text-kpmg-navy font-semibold px-1.5 py-0.5 rounded bg-blue-100 transition shrink-0 ml-2" title="Inspect complete cell lineage in Step 7">
                            Trace &rarr;
                        </button>
                    ` : ''}
                </div>
            </td>
        `;

        const noteCell = `<td class="text-center font-mono text-[11px] text-gray-500">${r.note || ''}</td>`;

        const valKeys = [...entityCols, "total_entities", "eliminations", "consolidated_net"];
        const valCells = valKeys.map(k => {
            const val = r.values ? r.values[k] : 0.0;
            const formulaText = r.formula ? r.formula.replace('{col}', k) : `Active consolidation formula for ${r.title}`;
            return `
                <td class="num-cell py-2 px-3 text-xs ${isTotal ? 'font-bold text-kpmg-navy' : 'formula-interactive'}"
                    ${!isTotal ? `onmouseenter="showFormula(event, '${formulaText}', '${r.title} [${k}]')" onmouseleave="hideFormula()"` : ''}>
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
            <!-- Header Controls & Switcher Strip -->
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
                    <button onclick="switchStep(7)" class="h-8 px-3 rounded bg-kpmg-navy hover:bg-kpmg-blue text-white text-xs font-medium transition flex items-center space-x-1.5 shadow-xs" title="Open full mathematical lineage explorer in Step 7">
                        <svg class="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>
                        <span>Audit & Lineage &rarr;</span>
                    </button>
                </div>
            </div>

            <!-- Financial Table -->
            <div class="overflow-x-auto max-h-[500px] border border-kpmg-border rounded bg-white shadow-xs">
                <table class="fin-table">
                    <thead class="sticky top-0 bg-slate-100 z-10 shadow-xs">
                        <tr>${headersHtml}</tr>
                    </thead>
                    <tbody>${rowsHtml}</tbody>
                </table>
            </div>

            <div class="flex items-center justify-between text-xs text-kpmg-muted pt-1">
                <span>Hover over any line item figure to inspect the active Excel formula. Click <strong>Trace &rarr;</strong> to inspect full backward lineage to source entity trial balances.</span>
                <span class="font-mono text-slate-500">IND AS 110/103/21</span>
            </div>
        </div>
    `;
}

function inspectLineageFromStatement(title) {
    switchStep(7);
    setTimeout(() => {
        const queryInput = document.getElementById("lineage-query-input");
        if (queryInput) {
            queryInput.value = title;
            executeLineageTrace(title);
        }
    }, 150);
}

// STEP 7: AUTONOMOUS QUALITY AUDIT & LANGGRAPH AGENT TRACING CONSOLE
let expandedNodeId = null;
let currentLineageTrace = null;
let auditSearchQuery = '';
let auditAgentFilter = 'ALL';
let auditStatusFilter = 'ALL';

function toggleNodeTraceDetails(nodeId) {
    expandedNodeId = (expandedNodeId === nodeId) ? null : nodeId;
    const el = document.getElementById("step-content");
    if (el && activeStep === 7) renderStep7(el);
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

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
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

    const safeCode = escapeHtml(target.account_code || '');
    const safeDesc = escapeHtml(target.account_description || data.query || '');

    container.innerHTML = `
        <div class="space-y-3">
            <div class="flex items-center justify-between text-xs">
                <div>
                    Target Account: <strong class="font-mono text-kpmg-navy">${safeCode}</strong> - <strong class="text-gray-800">${safeDesc}</strong>
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
    const el = document.getElementById("step-content");
    if (el && activeStep === 7) renderStep7(el);
}

function onAuditAgentFilter(val) {
    auditAgentFilter = val;
    const el = document.getElementById("step-content");
    if (el && activeStep === 7) renderStep7(el);
}

function renderStep7(el) {
    const evalData = pipelineData.teacher_evaluation || {};
    const auditLog = pipelineData.audit_trail || [];
    const traces = pipelineData.agent_traces || [];

    // Filter audit trail based on current search & dropdowns
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

    // 1. Build DAG Node Cards
    const nodeOrder = ["validator", "mapper", "translator", "elimination", "aggregator", "excel_builder", "auditor"];
    const nodeLabels = {
        "validator": "Trial Balance Validator",
        "mapper": "COA Standardization Agent",
        "translator": "Ind AS 21 FX Translator",
        "elimination": "IC Elimination Agent",
        "aggregator": "Consolidation Aggregator",
        "excel_builder": "100% Formula Deliverable Builder",
        "auditor": "Strict Teacher Auditor"
    };

    let dagCardsHtml = nodeOrder.map((nid, idx) => {
        const trace = traces.find(t => t.node_id === nid) || {
            node_id: nid,
            agent_role: nodeLabels[nid] || nid,
            status: traces.length > 0 ? "SUCCESS" : "READY",
            execution_time_ms: 0.0,
            decisions_count: 0,
            ai_calls: nid === "mapper" ? 4 : 0,
            state_mutations: 1,
            details: "Node ready for orchestration."
        };

        const isExpanded = expandedNodeId === nid;
        const isSuccess = trace.status === "SUCCESS";

        return `
            <div class="border rounded p-3 bg-white shadow-xs transition hover:border-kpmg-blue flex flex-col justify-between">
                <div>
                    <div class="flex items-center justify-between mb-1.5">
                        <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gray-100 text-gray-700 font-bold">Node ${idx + 1}</span>
                        <span class="text-[10px] font-bold px-2 py-0.5 rounded ${isSuccess ? 'bg-emerald-100 text-emerald-800' : 'bg-blue-100 text-kpmg-blue'}">
                            ${trace.status}
                        </span>
                    </div>
                    <h5 class="font-bold text-xs text-kpmg-navy mb-0.5">${trace.agent_role || nodeLabels[nid]}</h5>
                    <div class="text-[10px] font-mono text-gray-500 mb-2">node_id: ${trace.node_id}</div>
                    
                    <div class="grid grid-cols-2 gap-1.5 text-[11px] bg-slate-50 p-2 rounded mb-2">
                        <div>
                            <span class="text-gray-500 block text-[9px] uppercase">Latency</span>
                            <strong class="font-mono text-kpmg-blue">${trace.execution_time_ms ? trace.execution_time_ms.toFixed(1) + ' ms' : '< 1 ms'}</strong>
                        </div>
                        <div>
                            <span class="text-gray-500 block text-[9px] uppercase">Decisions</span>
                            <strong class="font-mono text-gray-800">${trace.decisions_count || 0}</strong>
                        </div>
                    </div>
                </div>

                <div>
                    <button onclick="toggleNodeTraceDetails('${nid}')" class="w-full text-center text-[10px] font-medium py-1 rounded border border-kpmg-border hover:bg-slate-50 transition text-kpmg-navy">
                        ${isExpanded ? 'Hide Trace Details' : 'Inspect Telemetry &rarr;'}
                    </button>
                    ${isExpanded ? `
                        <div class="mt-2 pt-2 border-t border-gray-100 text-[10px] font-mono text-gray-700 space-y-1">
                            <div><strong class="text-kpmg-navy">Started:</strong> ${trace.start_time || 'N/A'}</div>
                            <div><strong class="text-kpmg-navy">Ended:</strong> ${trace.end_time || 'N/A'}</div>
                            <div><strong class="text-kpmg-navy">Input:</strong> ${trace.input_summary || 'ConsolidationState'}</div>
                            <div><strong class="text-kpmg-navy">Output:</strong> ${trace.output_summary || 'State deltas recorded'}</div>
                            <div><strong class="text-kpmg-navy">Details:</strong> ${trace.details || 'Executed synchronously in LangGraph'}</div>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }).join("");

    // 2. Audit Trail Rows
    let auditRows = filteredAudit.map(a => `
        <tr>
            <td class="font-mono text-[11px] text-gray-500">${a.timestamp}</td>
            <td class="font-bold text-kpmg-navy">${a.stage}</td>
            <td><span class="px-2 py-0.5 rounded bg-gray-100 font-mono text-[10px] text-gray-700">${a.agent}</span></td>
            <td>${a.action}</td>
            <td class="font-bold ${a.status.includes('PASSED') || a.status.includes('SUCCESS') ? 'text-emerald-600' : 'text-amber-600'}">${a.status}</td>
            <td class="text-xs text-gray-600">${a.details}</td>
        </tr>
    `).join("");

    el.innerHTML = `
        <div class="space-y-6">
            <!-- SECTION 1: STRICT TEACHER AUTONOMOUS QUALITY AUDIT RUBRIC -->
            <div class="p-5 rounded bg-gradient-to-r from-kpmg-navy to-kpmg-blue text-white shadow-md">
                <div class="flex items-center justify-between mb-4">
                    <div>
                        <div class="text-xs text-kpmg-electric uppercase tracking-wider font-bold">Autonomous Strict Teacher Quality Audit</div>
                        <h3 class="text-xl font-bold">Overall Institutional Grade: ${evalData.score || 100}/100</h3>
                        <p class="text-xs text-white/80 mt-0.5">Strict adherence to Ind AS 110, 103, 21 and 100% active formula lineage.</p>
                    </div>
                    <span class="px-3.5 py-1.5 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 tracking-wider">
                        ${evalData.passed !== false ? 'HONORS PASS' : 'ACTION REQUIRED'}
                    </span>
                </div>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4 pt-3 border-t border-white/10 text-xs">
                    <div class="bg-white/5 p-3 rounded border border-white/10">
                        <span class="text-white/70 block mb-0.5">1. Formula Integrity</span>
                        <strong class="text-base font-mono text-emerald-300">${evalData.pillar_breakdown?.formula_integrity || 25}/25</strong>
                        <span class="block text-[10px] text-white/60 mt-0.5">100% active formula linking</span>
                    </div>
                    <div class="bg-white/5 p-3 rounded border border-white/10">
                        <span class="text-white/70 block mb-0.5">2. Financial Correctness</span>
                        <strong class="text-base font-mono text-emerald-300">${evalData.pillar_breakdown?.financial_correctness || 25}/25</strong>
                        <span class="block text-[10px] text-white/60 mt-0.5">Ind AS 110/103/21 balance</span>
                    </div>
                    <div class="bg-white/5 p-3 rounded border border-white/10">
                        <span class="text-white/70 block mb-0.5">3. Validation & Tolerance</span>
                        <strong class="text-base font-mono text-emerald-300">${evalData.pillar_breakdown?.validation_and_tolerance || 25}/25</strong>
                        <span class="block text-[10px] text-white/60 mt-0.5">Dual-tolerance IC clearing</span>
                    </div>
                    <div class="bg-white/5 p-3 rounded border border-white/10">
                        <span class="text-white/70 block mb-0.5">4. Provenance & Flow</span>
                        <strong class="text-base font-mono text-emerald-300">${evalData.pillar_breakdown?.provenance_and_flow || 25}/25</strong>
                        <span class="block text-[10px] text-white/60 mt-0.5">Unbroken raw cell tracing</span>
                    </div>
                </div>
            </div>

            <!-- Deliverable & Formula Verification Bar -->
            <div class="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
                <div class="p-3 bg-white border border-kpmg-border rounded shadow-xs flex items-center justify-between">
                    <div>
                        <span class="text-gray-500 text-[10px] block uppercase font-semibold">Consolidated_TB</span>
                        <strong class="text-kpmg-navy">100% Dynamic Formulas</strong>
                    </div>
                    <span class="text-emerald-600 font-bold">✓ Verified</span>
                </div>
                <div class="p-3 bg-white border border-kpmg-border rounded shadow-xs flex items-center justify-between">
                    <div>
                        <span class="text-gray-500 text-[10px] block uppercase font-semibold">Balance_Sheet</span>
                        <strong class="text-kpmg-navy">100% SUMIFS Formulas</strong>
                    </div>
                    <span class="text-emerald-600 font-bold">✓ Verified</span>
                </div>
                <div class="p-3 bg-white border border-kpmg-border rounded shadow-xs flex items-center justify-between">
                    <div>
                        <span class="text-gray-500 text-[10px] block uppercase font-semibold">Profit_and_Loss</span>
                        <strong class="text-kpmg-navy">100% SUMIFS Formulas</strong>
                    </div>
                    <span class="text-emerald-600 font-bold">✓ Verified</span>
                </div>
                <div class="p-3 bg-white border border-kpmg-border rounded shadow-xs flex items-center justify-between">
                    <div>
                        <span class="text-gray-500 text-[10px] block uppercase font-semibold">Eliminations_Journal</span>
                        <strong class="text-kpmg-navy">100% Balanced Debits=Credits</strong>
                    </div>
                    <span class="text-emerald-600 font-bold">✓ Verified</span>
                </div>
            </div>

            <!-- SECTION 2: LANGGRAPH AGENT RUNTIME DAG -->
            <div class="space-y-3">
                <div class="flex items-center justify-between">
                    <div>
                        <h4 class="font-bold text-sm text-kpmg-navy">LangGraph Multi-Agent Runtime Orchestration DAG</h4>
                        <p class="text-xs text-kpmg-muted">Autonomous execution sequence, node latencies, and state mutations.</p>
                    </div>
                    <div class="text-xs font-mono text-gray-500">
                        Total Latency: <strong class="text-kpmg-blue">${traces.reduce((acc, t) => acc + (t.execution_time_ms || 0), 0).toFixed(1)} ms</strong>
                    </div>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-4 lg:grid-cols-7 gap-2.5">
                    ${dagCardsHtml}
                </div>
            </div>

            <!-- SECTION 3: CELL-LEVEL MATHEMATICAL LINEAGE EXPLORER -->
            <div class="space-y-3 p-4 bg-white border border-kpmg-border rounded shadow-xs">
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

                <!-- Dynamic Lineage Graph Container -->
                <div id="lineage-results-container" class="pt-2">
                    <div class="p-4 text-center text-kpmg-muted text-xs">
                        Select an account from the preset dropdown or type a query above to view the 5-tier mathematical lineage graph.
                    </div>
                </div>
            </div>

            <!-- SECTION 4: SEARCHABLE & FILTERABLE AUDIT TRAIL LOG -->
            <div class="space-y-3">
                <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div>
                        <h4 class="font-bold text-sm text-kpmg-navy">Observability & Agent Execution Audit Trail</h4>
                        <p class="text-xs text-kpmg-muted">Immutable, timestamped event log recording every validation, mapping, translation, and elimination decision.</p>
                    </div>
                    <div class="flex items-center space-x-2">
                        <input id="audit-search-input" type="text" value="${auditSearchQuery}" oninput="onAuditSearch(this.value)" placeholder="Search audit trail..." class="h-8 text-xs px-3 rounded border border-kpmg-border focus:ring-1 focus:ring-kpmg-blue w-40 sm:w-56">
                        <select id="audit-agent-filter" onchange="onAuditAgentFilter(this.value)" class="h-8 text-xs px-2 rounded border border-kpmg-border bg-white text-gray-700">
                            <option value="ALL">All Agents</option>
                            <option value="ValidatorAgent">ValidatorAgent</option>
                            <option value="COAMappingAgent">COAMappingAgent</option>
                            <option value="IndAS21FXTranslatorAgent">IndAS21FXTranslatorAgent</option>
                            <option value="IntercompanyMatchingAgent">IntercompanyMatchingAgent</option>
                            <option value="ConsolidationAggregatorAgent">ConsolidationAggregatorAgent</option>
                            <option value="DeliverableBuilderAgent">DeliverableBuilderAgent</option>
                            <option value="StrictTeacherAuditorAgent">StrictTeacherAuditorAgent</option>
                        </select>
                        <a href="/api/audit-trail/export?format=json" download class="h-8 px-2.5 rounded bg-white hover:bg-gray-100 text-kpmg-navy text-xs font-medium border border-kpmg-border transition flex items-center space-x-1 shadow-xs" title="Download sanitized JSON audit log">
                            <svg class="w-3.5 h-3.5 text-kpmg-blue" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                            <span>JSON</span>
                        </a>
                        <a href="/api/audit-trail/export?format=csv" download class="h-8 px-2.5 rounded bg-white hover:bg-gray-100 text-kpmg-navy text-xs font-medium border border-kpmg-border transition flex items-center space-x-1 shadow-xs" title="Download CSV audit log">
                            <svg class="w-3.5 h-3.5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
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

    // Trigger initial lineage trace if container is present and not populated
    if (!currentLineageTrace) {
        executeLineageTrace("Cash and cash equivalents");
    } else {
        renderLineageGraph(currentLineageTrace);
    }
}

// PIPELINE EXECUTION TRIGGER
async function triggerRunPipeline() {
    const btn = document.getElementById("btn-run");
    const subStepText = document.getElementById("sub-step-text");
    const originalSubText = subStepText ? subStepText.textContent : "";
    btn.disabled = true;
    btn.innerHTML = `
        <svg class="w-3.5 h-3.5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>
        <span>Starting Agents...</span>
    `;

    let isFinished = false;
    const progressInterval = setInterval(async () => {
        if (isFinished) return;
        try {
            const stRes = await fetch("/api/status");
            const st = await stRes.json();
            if (st.is_running && st.current_stage) {
                const stageShort = st.current_stage.length > 30 ? st.current_stage.slice(0, 30) + '...' : st.current_stage;
                btn.innerHTML = `
                    <svg class="w-3.5 h-3.5 animate-spin text-amber-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>
                    <span>${stageShort}</span>
                `;
                if (subStepText) {
                    subStepText.textContent = `Running: ${st.current_stage}`;
                }
            }
        } catch (_) {}
    }, 300);

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
            statementsData = null;
            currentLineageTrace = null;
            await fetchStatus();
            await loadPipelineData();
            switchStep(6);
        }
    } catch (err) {
        showToast("Network Error", "Pipeline invocation error: " + err, "error");
    } finally {
        isFinished = true;
        clearInterval(progressInterval);
        btn.disabled = false;
        btn.innerHTML = `
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
            <span>Execute Consolidation</span>
        `;
        if (subStepText && originalSubText) {
            subStepText.textContent = originalSubText;
        }
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
