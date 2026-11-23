"""Automated tests for Intercompany Eliminations & Tolerances."""

import pytest
from fs_conso.core.elimination_engine import IntercompanyEliminationEngine
from fs_conso.models.elimination import EliminationStatus

def test_intercompany_eliminations_and_tolerances():
    engine = IntercompanyEliminationEngine(abs_tolerance=1000.0, pct_tolerance=0.01)
    raw_pairs = [
        # Exactly matched pair
        ("Sub_1", "Sub_2", "120400", "320300", 50000.0, -50000.0),
        # Within tolerance (diff = 50.0 <= 1000.0) -> Warning
        ("Sub_1", "Sub_2", "120400", "320300", 50000.0, -49950.0),
        # Exceeds tolerance (diff = 5000.0 > 1000.0) -> Exception
        ("Sub_1", "Sub_2", "120400", "320300", 50000.0, -45000.0),
    ]

    res = engine.process_intercompany_pairs(raw_pairs)
    assert res.matched_count == 1
    assert res.tolerance_warning_count == 1
    assert res.exception_count == 1
    assert res.pairs[0].evaluate_status(1000.0, 0.01) == EliminationStatus.MATCHED
    assert res.pairs[1].evaluate_status(1000.0, 0.01) == EliminationStatus.TOLERANCE_WARNING
    assert res.pairs[2].evaluate_status(1000.0, 0.01) == EliminationStatus.EXCEPTION
