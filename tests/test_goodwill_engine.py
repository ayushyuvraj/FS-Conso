"""Test suite for Step 5: Goodwill on Consolidation (Ind AS 103 / IFRS 3).

Verifies Level 0 Share Capital calculation, multi-currency conversion, dynamic adjustments (up to 100),
Net Assets calculation, deterministic/LLM/HITL investment matching, Goodwill vs Capital Reserve,
and integration into Step 6 Consolidated TB.
"""

import pytest
from httpx import AsyncClient, ASGITransport

from fs_conso.core.goodwill_engine import GoodwillEngine
from fs_conso.core.aggregator import TBAggregator
from fs_conso.models.coa import ChartOfAccounts, COAItem, AccountClassification
from fs_conso.models.goodwill import GoodwillAdjustmentItem, GoodwillEntityData, GoodwillSchedule
from fs_conso.models.trial_balance import RawTrialBalance, RawTBRow
from fs_conso.core.translator import TranslatedTrialBalance, TranslatedRow
from fs_conso.agent.state import ConsolidationState, MappingDecision
from fs_conso.web.app import app, session


def test_goodwill_share_capital_calculation_from_l0():
    """Verify Share Capital is correctly summed from mapped TB line items."""
    # Mock translated TB with Level 0 account E100101
    trans_row1 = TranslatedRow(
        account_code="E100101",
        account_description="Equity Share Capital - Common",
        category="Equity",
        source_currency="USD",
        source_amount=50000.0,
        rate_applied=83.0,
        rate_type="Historical",
        translated_amount=4150000.0
    )
    trans_row2 = TranslatedRow(
        account_code="E100101",
        account_description="Equity Share Capital - Additional Tranche",
        category="Equity",
        source_currency="USD",
        source_amount=10000.0,
        rate_applied=83.0,
        rate_type="Historical",
        translated_amount=830000.0
    )
    trans_tb = TranslatedTrialBalance(
        entity_code="Sub_1",
        period="31-Mar-2024",
        source_currency="USD",
        reporting_currency="INR",
        rows=[trans_row1, trans_row2]
    )

    state = ConsolidationState(
        company_id="test-co",
        period="31-Mar-2024",
        translated_tbs=[trans_tb],
        mapping_decisions=[
            MappingDecision(
                entity_code="Sub_1",
                local_code="1001",
                local_description="Common Shares",
                group_code="E100101",
                group_description="Equity Share Capital",
                level_0_name="Equity Share Capital",
                confidence=1.0,
                method="DIRECT_CODE_MATCH",
                amount=50000.0
            )
        ]
    )

    amount, name = GoodwillEngine.calculate_share_capital_from_l0("Sub_1", "E100101", state, "INR")
    assert amount == 4980000.0  # 4,150,000 + 830,000
    assert "Share Capital" in name


def test_goodwill_recalculate_positive_goodwill():
    """Verify when Investment > Net Assets, positive Goodwill is recognized."""
    sched = GoodwillSchedule(
        company_id="test-co",
        period="31-Mar-2024",
        reporting_currency="INR",
        parent_entity_code="Company_P",
        entities=["Company_P", "Sub_1"],
        adjustments=[
            GoodwillAdjustmentItem(
                id="adj-1",
                name="Fair Value Uplift",
                amounts_by_entity={"Company_P": 0.0, "Sub_1": 200000.0},
                remarks="Plant & Machinery revaluation"
            )
        ],
        data_by_entity={
            "Company_P": GoodwillEntityData(
                entity_code="Company_P",
                is_parent=True,
                share_capital_amount=10000000.0,
                retained_earnings_amount=5000000.0,
                investment_amount=8000000.0
            ),
            "Sub_1": GoodwillEntityData(
                entity_code="Sub_1",
                is_parent=False,
                share_capital_amount=3000000.0,
                retained_earnings_amount=1000000.0,
                investment_amount=5000000.0  # Investment = 5,000,000; Net Assets = 3M + 200k + 1M = 4,200,000
            )
        }
    )

    res = GoodwillEngine.recalculate_schedule(sched)
    sub_data = res.data_by_entity["Sub_1"]

    # Net Assets = 3,000,000 + 200,000 + 1,000,000 = 4,200,000
    assert sub_data.net_assets_at_acquisition == 4200000.0
    # Goodwill = 5,000,000 - 4,200,000 = 800,000
    assert sub_data.goodwill_amount == 800000.0
    assert sub_data.capital_reserve_amount == 0.0
    assert res.total_goodwill == 800000.0


def test_goodwill_recalculate_capital_reserve_gain():
    """Verify when Net Assets > Investment (bargain purchase), Capital Reserve is recognized."""
    sched = GoodwillSchedule(
        company_id="test-co",
        period="31-Mar-2024",
        reporting_currency="INR",
        parent_entity_code="Company_P",
        entities=["Sub_Bargain"],
        adjustments=[],
        data_by_entity={
            "Sub_Bargain": GoodwillEntityData(
                entity_code="Sub_Bargain",
                is_parent=False,
                share_capital_amount=5000000.0,
                retained_earnings_amount=2000000.0,
                investment_amount=6000000.0  # Investment = 6M; Net Assets = 7M
            )
        }
    )

    res = GoodwillEngine.recalculate_schedule(sched)
    sub_data = res.data_by_entity["Sub_Bargain"]

    assert sub_data.net_assets_at_acquisition == 7000000.0
    assert sub_data.goodwill_amount == 0.0
    # Capital Reserve = 7,000,000 - 6,000,000 = 1,000,000
    assert sub_data.capital_reserve_amount == 1000000.0
    assert res.total_capital_reserve == 1000000.0


def test_deterministic_investment_matching():
    """Verify deterministic investment account searching in Parent TB."""
    parent_tb = TranslatedTrialBalance(
        entity_code="Company_P",
        period="31-Mar-2024",
        rows=[
            TranslatedRow(
                account_code="A110401",
                account_description="Investment in Equity of Sub_1",
                category="Asset",
                source_currency="INR",
                source_amount=4500000.0,
                rate_applied=1.0,
                rate_type="Identity",
                translated_amount=4500000.0
            ),
            TranslatedRow(
                account_code="A120101",
                account_description="Cash and Cash Equivalents",
                category="Asset",
                source_currency="INR",
                source_amount=1000000.0,
                rate_applied=1.0,
                rate_type="Identity",
                translated_amount=1000000.0
            )
        ]
    )

    state = ConsolidationState(
        company_id="test-co",
        translated_tbs=[parent_tb]
    )

    code, name, amt, conf, method, hitl = GoodwillEngine.search_investment_account(
        parent_code="Company_P",
        sub_code="Sub_1",
        sub_name="Subsidiary One Ltd",
        state=state
    )

    assert code == "A110401"
    assert amt == 4500000.0
    assert conf >= 0.85
    assert method == "DETERMINISTIC"
    assert hitl is False


def test_goodwill_posting_into_consolidated_tb():
    """Verify Goodwill and Capital Reserve from schedule post into Step 6 Consolidated TB."""
    coa = ChartOfAccounts()
    coa.add_item(COAItem(account_code="A110301", account_name="Goodwill on Consolidation", account_type=AccountClassification.ASSET))
    coa.add_item(COAItem(account_code="E210103", account_name="Capital Reserve on Consolidation", account_type=AccountClassification.EQUITY))

    sched = GoodwillSchedule(
        company_id="test-co",
        period="31-Mar-2024",
        total_goodwill=750000.0,
        total_capital_reserve=250000.0,
        entities=["Sub_1"],
        data_by_entity={
            "Sub_1": GoodwillEntityData(
                entity_code="Sub_1",
                goodwill_amount=750000.0,
                capital_reserve_amount=250000.0
            )
        }
    )

    conso_tb = TBAggregator.aggregate(
        coa=coa,
        translated_tbs=[],
        goodwill_schedule=sched
    )

    gw_row = next((r for r in conso_tb.rows if r.account_code == "A110301"), None)
    cr_row = next((r for r in conso_tb.rows if r.account_code == "E210103"), None)

    assert gw_row is not None
    assert gw_row.adjustments == 750000.0
    assert gw_row.consolidated_total == 750000.0

    assert cr_row is not None
    assert cr_row.adjustments == -250000.0
    assert cr_row.consolidated_total == -250000.0


@pytest.mark.anyio
async def test_goodwill_api_lifecycle():
    """End-to-end verification of Goodwill API endpoints."""
    session.initialize_company("company-p", load_samples=True)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Fetch initial schedule
        res = await client.get("/api/pipeline/goodwill")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        sched = data["schedule"]
        assert len(sched["entities"]) >= 2

        # 2. Add an adjustment row
        add_res = await client.post("/api/pipeline/goodwill/add-adjustment", json={"name": "PPA Adjustment", "remarks": "PPA Uplift"})
        assert add_res.status_code == 200
        new_sched = add_res.json()["schedule"]
        assert len(new_sched["adjustments"]) >= 2
        new_adj_id = new_sched["adjustments"][-1]["id"]

        # 3. Update adjustment amounts and retained earnings
        first_sub = sched["entities"][1]
        update_payload = {
            "share_capital_l0_codes": {first_sub: "E100101"},
            "retained_earnings": {first_sub: 500000.0},
            "investments": {first_sub: 2500000.0},
            "adjustments": [
                {
                    "id": new_adj_id,
                    "name": "PPA Adjustment",
                    "amounts_by_entity": {first_sub: 150000.0},
                    "remarks": "Updated PPA"
                }
            ]
        }
        up_res = await client.post("/api/pipeline/goodwill/update", json=update_payload)
        assert up_res.status_code == 200
        up_sched = up_res.json()["schedule"]
        assert up_sched["data_by_entity"][first_sub]["retained_earnings_amount"] == 500000.0

        # 4. Confirm schedule
        conf_res = await client.post("/api/pipeline/goodwill/confirm")
        assert conf_res.status_code == 200
        conf_data = conf_res.json()
        assert conf_data["success"] is True
        assert 5 in conf_data["completed_steps"]
        assert conf_data["current_step"] >= 6
