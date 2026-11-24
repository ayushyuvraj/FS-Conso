"""Consolidated Trial Balance Aggregator & Acquisition Accounting Engine."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from fs_conso.core.translator import TranslatedRow, TranslatedTrialBalance
from fs_conso.models.coa import AccountClassification, ChartOfAccounts
from fs_conso.models.elimination import EliminationVoucher
from fs_conso.models.entity import EntityHierarchy


class ConsolidatedTBRow(BaseModel):
    account_code: str
    account_description: str
    # Standalone entity balances in presentation currency: { "Company_S1": 500000.0, "Company_P": ... }
    entity_balances: Dict[str, float] = Field(default_factory=dict)
    # Individual entity elimination allocations: { "Company_S1": -100000.0, "Company_S2": 100000.0 }
    entity_eliminations: Dict[str, float] = Field(default_factory=dict)
    total_entities: float = 0.0
    eliminations: float = 0.0
    adjustments: float = 0.0
    consolidated_total: float = 0.0

    def __init__(self, **data):
        if "entity_translated_amounts" in data and "entity_balances" not in data:
            data["entity_balances"] = data["entity_translated_amounts"]
        if "consolidated_net" in data and "consolidated_total" not in data:
            data["consolidated_total"] = data["consolidated_net"]
        if "eliminations_total" in data and "eliminations" not in data:
            data["eliminations"] = data["eliminations_total"]
        super().__init__(**data)

    @property
    def entity_translated_amounts(self) -> Dict[str, float]:
        return self.entity_balances

    @property
    def eliminations_total(self) -> float:
        return self.eliminations

    @property
    def consolidated_net(self) -> float:
        return self.consolidated_total


ConsolidatedRow = ConsolidatedTBRow


class AcquisitionAccountingResult(BaseModel):
    """Details of Ind AS 103 / IFRS 3 Acquisition Accounting."""
    goodwill_total: float = 0.0
    capital_reserve_total: float = 0.0
    nci_equity_total: float = 0.0
    nci_profit_total: float = 0.0
    details_by_sub: Dict[str, Dict[str, float]] = Field(default_factory=dict)


class ConsolidatedTrialBalance(BaseModel):
    period: str
    currency: str = "INR"
    entity_codes: List[str] = Field(default_factory=list)
    rows: List[ConsolidatedTBRow] = Field(default_factory=list)
    acquisition_accounting: Optional[AcquisitionAccountingResult] = None

    @property
    def total_consolidated(self) -> float:
        return round(sum(r.consolidated_total for r in self.rows), 2)

    @property
    def is_tallied(self) -> bool:
        return abs(self.total_consolidated) < 0.01


class TBAggregator:
    """Aggregates translated entity TBs and intercompany eliminations into Consolidated TB
    and computes Ind AS 103 Acquisition Accounting.
    """

    @staticmethod
    def calculate_acquisition_accounting(
        holding_percentage: float,
        consideration_paid: float,
        net_assets_at_acquisition: float
    ) -> tuple:
        """Computes Goodwill, Capital Reserve, and NCI under Ind AS 103 / IFRS 3."""
        holding_ratio = holding_percentage / 100.0 if holding_percentage > 1.0 else holding_percentage
        nci_ratio = max(0.0, 1.0 - holding_ratio)
        parent_share_net_assets = round(net_assets_at_acquisition * holding_ratio, 2)
        nci_val = round(net_assets_at_acquisition * nci_ratio, 2)
        diff = round(consideration_paid - parent_share_net_assets, 2)
        goodwill = max(0.0, diff)
        capital_reserve = max(0.0, -diff)
        return goodwill, capital_reserve, nci_val

    @classmethod
    def aggregate(
        cls,
        coa: ChartOfAccounts,
        translated_tbs: List[TranslatedTrialBalance],
        elimination_vouchers: Optional[List[EliminationVoucher]] = None,
        period: str = "31-Mar-2024",
        currency: str = "INR",
        entity_hierarchy: Optional[EntityHierarchy] = None
    ) -> ConsolidatedTrialBalance:
        entity_codes = [tb.entity_code for tb in translated_tbs]
        all_accounts: Dict[str, str] = {}

        # 1. Collect all active accounts from TBs
        for tb in translated_tbs:
            for r in tb.rows:
                all_accounts[r.account_code] = r.account_description

        # Ensure Goodwill, NCI, and FCTR standard accounts exist in map
        all_accounts["A110301"] = "Goodwill on Consolidation"
        all_accounts["E210301"] = "Non-Controlling Interests (NCI)"
        all_accounts["O620102"] = "Foreign Currency Translation Differences (FCTR)"

        # 2. Compute elimination impacts and entity-specific allocations
        elim_map: Dict[str, float] = {}
        entity_elim_map: Dict[str, Dict[str, float]] = {}  # { acc_code: { entity_code: elim_amount } }

        if elimination_vouchers:
            for v in elimination_vouchers:
                # Debit account adjustment
                elim_map[v.debit_account] = elim_map.get(v.debit_account, 0.0) + v.eliminated_amount
                # Credit account adjustment
                elim_map[v.credit_account] = elim_map.get(v.credit_account, 0.0) - v.eliminated_amount

                # Entity-specific allocations
                for ent, alloc in v.entity_allocations.items():
                    target_acc = v.debit_account if alloc > 0 else v.credit_account
                    if target_acc not in entity_elim_map:
                        entity_elim_map[target_acc] = {}
                    entity_elim_map[target_acc][ent] = round(
                        entity_elim_map[target_acc].get(ent, 0.0) + alloc, 2
                    )

        # 3. Ind AS 103 Acquisition Accounting (Goodwill, Capital Reserve, NCI)
        acq_result = AcquisitionAccountingResult()
        if entity_hierarchy:
            for ent_code in entity_codes:
                legal_ent = entity_hierarchy.get_entity(ent_code)
                if legal_ent and not legal_ent.is_parent:
                    holding = legal_ent.holding_percentage
                    nci_pct = legal_ent.nci_percentage
                    
                    # Calculate sub equity (Share Capital + Retained Earnings)
                    sub_tb = next((t for t in translated_tbs if t.entity_code == ent_code), None)
                    if sub_tb:
                        sub_equity = sum(
                            abs(r.translated_amount) for r in sub_tb.rows
                            if coa.get_item(r.account_code) and coa.get_item(r.account_code).account_type == AccountClassification.EQUITY
                        )
                        nci_val = round(sub_equity * nci_pct, 2)
                        acq_result.nci_equity_total += nci_val
                        acq_result.details_by_sub[ent_code] = {
                            "holding_percentage": holding,
                            "nci_percentage": nci_pct,
                            "sub_equity": sub_equity,
                            "nci_equity": nci_val
                        }

        # 4. Build Consolidated Rows in sorted Group COA order
        sorted_codes = sorted(
            all_accounts.keys(),
            key=lambda c: (coa.get_item(c).fs_statement if coa.get_item(c) else "ZZ", c)
        )
        rows: List[ConsolidatedTBRow] = []

        for code in sorted_codes:
            desc = all_accounts[code]
            ent_bals: Dict[str, float] = {}
            for tb in translated_tbs:
                ent_bals[tb.entity_code] = round(
                    sum(r.translated_amount for r in tb.rows if r.account_code == code), 2
                )

            tot_ent = round(sum(ent_bals.values()), 2)
            elim = round(elim_map.get(code, 0.0), 2)
            adj = 0.0
            conso_tot = round(tot_ent + elim + adj, 2)

            # Build individual entity elimination allocations for this account
            ent_elims = {ent: entity_elim_map.get(code, {}).get(ent, 0.0) for ent in entity_codes}

            rows.append(ConsolidatedTBRow(
                account_code=code,
                account_description=desc,
                entity_balances=ent_bals,
                entity_eliminations=ent_elims,
                total_entities=tot_ent,
                eliminations=elim,
                adjustments=adj,
                consolidated_total=conso_tot
            ))

        return ConsolidatedTrialBalance(
            period=period,
            currency=currency,
            entity_codes=entity_codes,
            rows=rows,
            acquisition_accounting=acq_result
        )

ConsolidationAggregator = TBAggregator
