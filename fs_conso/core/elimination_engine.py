"""Intercompany matching & elimination engine."""

from typing import List, Tuple
from pydantic import BaseModel, Field

from fs_conso.config import config
from fs_conso.models.elimination import EliminationPair, EliminationStatus, EliminationVoucher

class EliminationResult(BaseModel):
    pairs: List[EliminationPair] = Field(default_factory=list)
    vouchers: List[EliminationVoucher] = Field(default_factory=list)
    total_eliminated: float = 0.0
    total_variance: float = 0.0
    matched_count: int = 0
    tolerance_warning_count: int = 0
    exception_count: int = 0

class IntercompanyEliminationEngine:
    """Matches intercompany transactions and generates balanced elimination vouchers."""

    def __init__(self, abs_tolerance: float = 10000.0, pct_tolerance: float = 0.01):
        self.abs_tolerance = abs_tolerance
        self.pct_tolerance = pct_tolerance

    def process_intercompany_pairs(
        self,
        raw_pairs: List[Tuple[str, str, str, str, float, float]]
    ) -> EliminationResult:
        """Processes list of reciprocal transactions:

        (entity, counterparty, entity_acc, cp_acc, entity_amt, cp_amt)
        """
        pairs: List[EliminationPair] = []
        vouchers: List[EliminationVoucher] = []
        tot_elim = 0.0
        tot_var = 0.0
        n_matched = 0
        n_warning = 0
        n_exc = 0

        for idx, (ent, cp, ent_acc, cp_acc, ent_amt, cp_amt) in enumerate(raw_pairs, start=1):
            pair = EliminationPair(
                entity_code=ent,
                counterparty_code=cp,
                account_code=ent_acc,
                account_description=f"IC between {ent} and {cp}",
                entity_amount=ent_amt,
                counterparty_amount=cp_amt
            )
            status = pair.evaluate_status(self.abs_tolerance, self.pct_tolerance)
            pairs.append(pair)

            if status == EliminationStatus.MATCHED:
                n_matched += 1
            elif status == EliminationStatus.TOLERANCE_WARNING:
                n_warning += 1
            else:
                n_exc += 1

            elim_amt = min(abs(ent_amt), abs(cp_amt))
            variance = pair.net_variance
            tot_elim += elim_amt
            tot_var += abs(variance)

            voucher = EliminationVoucher(
                voucher_id=f"ELIM_{idx:03d}",
                entity_code=ent,
                counterparty_code=cp,
                debit_account=cp_acc if ent_amt > 0 else ent_acc,
                credit_account=ent_acc if ent_amt > 0 else cp_acc,
                eliminated_amount=round(elim_amt, 2),
                variance_amount=round(variance, 2),
                status=status
            )
            vouchers.append(voucher)

        return EliminationResult(
            pairs=pairs,
            vouchers=vouchers,
            total_eliminated=round(tot_elim, 2),
            total_variance=round(tot_var, 2),
            matched_count=n_matched,
            tolerance_warning_count=n_warning,
            exception_count=n_exc
        )
