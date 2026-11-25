import pytest
import io
import pandas as pd
from fastapi.testclient import TestClient

from fs_conso.models.company import CompanyProfile
from fs_conso.models.entity import EntityHierarchy, LegalEntity
from fs_conso.models.trial_balance import RawTrialBalance, RawTBRow
from fs_conso.core.file_classifier import FileClassifier, ClassifiedFile
from fs_conso.core.file_parser import FlexibleTBParser
from fs_conso.web.app import app, session, company_manager


@pytest.fixture
def sample_hierarchy():
    hierarchy = EntityHierarchy(
        parent_code="P",
        reporting_currency="INR"
    )
    hierarchy.add_entity(LegalEntity(
        entity_code="P",
        entity_name="Acme Parent Corp",
        country_of_inc="India",
        input_currency="INR",
        holding_percentage=1.0,
        consolidation_method="Full Consolidation"
    ))
    hierarchy.add_entity(LegalEntity(
        entity_code="S1",
        entity_name="Acme Sub One Limited",
        country_of_inc="India",
        input_currency="INR",
        holding_percentage=0.8,
        parent_entity_code="P",
        consolidation_method="Full Consolidation"
    ))
    hierarchy.add_entity(LegalEntity(
        entity_code="S2",
        entity_name="Acme US LLC",
        country_of_inc="USA",
        input_currency="USD",
        holding_percentage=1.0,
        parent_entity_code="P",
        consolidation_method="Full Consolidation"
    ))
    return hierarchy


class TestAgenticIngestion:

    def test_dynamic_currency_aware_column_parsing(self, sample_hierarchy):
        """Verify that when multiple amount columns exist, the entity's functional currency selects the right column."""
        parser = FlexibleTBParser()
        
        # Test DataFrame with both INR and USD amount columns
        df = pd.DataFrame({
            "Account": ["1000", "2000"],
            "Description": ["Cash and Equivalents", "Accounts Payable"],
            "Amount_INR": [50000.0, -50000.0],
            "Amount_USD": [600.0, -600.0]
        })
        
        # For Parent (INR functional currency), should pick Amount_INR
        tb_inr = parser.parse_dataframe(df, entity_code="P", entity_name="Acme Parent Corp", currency="INR")
        assert tb_inr.entity_code == "P"
        assert tb_inr.entity_name == "Acme Parent Corp"
        assert tb_inr.currency == "INR"
        assert tb_inr.total_debit == 50000.0
        assert tb_inr.total_credit == 50000.0
        assert abs(tb_inr.total_debit - tb_inr.total_credit) < 0.01
        assert "INR" in tb_inr.detected_columns.get("amount", "").upper()

        # For S2 (USD functional currency), should pick Amount_USD
        tb_usd = parser.parse_dataframe(df, entity_code="S2", entity_name="Acme US LLC", currency="USD")
        assert tb_usd.entity_code == "S2"
        assert tb_usd.currency == "USD"
        assert tb_usd.total_debit == 600.0
        assert tb_usd.total_credit == 600.0
        assert abs(tb_usd.total_debit - tb_usd.total_credit) < 0.01
        assert "USD" in tb_usd.detected_columns.get("amount", "").upper()

    def test_arbitrary_column_ordering_and_extra_columns(self):
        """Verify parsing when GL code is in a non-standard column and debit/credit columns are separated."""
        parser = FlexibleTBParser()

        # Shuffled columns: Col A is Notes, Col B is Credit, Col C is Region, Col D is Desc, Col E is Debit, Col F is Code
        df = pd.DataFrame({
            "Notes": ["N1", "N2", "N3"],
            "Credit_Amt": [0.0, 75000.0, 25000.0],
            "Region": ["North", "South", "East"],
            "Account_Title": ["Operating Revenue", "Trade Payables", "Retained Earnings"],
            "Debit_Amt": [100000.0, 0.0, 0.0],
            "GL_Code": ["1010", "2010", "3010"]
        })

        tb = parser.parse_dataframe(df, entity_code="S1", currency="INR")
        assert tb.entity_code == "S1"
        assert len(tb.rows) == 3
        assert tb.total_debit == 100000.0
        assert tb.total_credit == 100000.0
        assert abs(tb.total_debit - tb.total_credit) < 0.01
        assert tb.rows[0].account_code == "1010"
        assert tb.rows[0].account_description == "Operating Revenue"
        assert tb.rows[0].debit == 100000.0

    def test_single_signed_column_parsing(self):
        """Verify handling of single signed amount column (+ for Dr, - for Cr)."""
        parser = FlexibleTBParser()

        df = pd.DataFrame({
            "GL_Account": ["100", "200"],
            "Account_Name": ["Bank Balance", "Loan"],
            "Net_Balance": [45000.0, -45000.0]
        })

        tb = parser.parse_dataframe(df, entity_code="P", currency="INR")
        assert abs(tb.total_debit - tb.total_credit) < 0.01
        assert tb.total_debit == 45000.0
        assert tb.total_credit == 45000.0

    def test_file_classifier_deterministic_entity_matching(self, sample_hierarchy):
        """Verify deterministic entity classification matching entity code, legal name, and abbreviations."""
        classifier = FileClassifier()

        # 1. Exact entity code match
        cf1 = classifier.classify_file(b"", "TB_P_2024.xlsx", entity_hierarchy=sample_hierarchy)
        assert cf1.file_type == "CURRENT_TB"
        assert cf1.entity_code == "P"
        assert cf1.confidence >= 0.90

        # 2. Subsidiary abbreviation / slug match
        cf2 = classifier.classify_file(b"", "TrialBalance_Sub_1_Final.xlsx", entity_hierarchy=sample_hierarchy)
        assert cf2.file_type == "CURRENT_TB"
        assert cf2.entity_code == "S1"
        assert cf2.confidence >= 0.85

        # 3. Legal entity name match
        cf3 = classifier.classify_file(b"", "Acme_US_LLC_December_TB.csv", entity_hierarchy=sample_hierarchy)
        assert cf3.file_type == "CURRENT_TB"
        assert cf3.entity_code == "S2"
        assert cf3.confidence >= 0.85

    def test_perimeter_completeness_gate(self, sample_hierarchy):
        """Verify that pipeline execution is blocked when perimeter is incomplete."""
        client = TestClient(app)

        # Set up an active company profile in session with 3 entities: P, S1, S2
        prof = CompanyProfile(
            company_id="test_perimeter_co",
            company_name="Test Perimeter Co",
            company_code="P",
            reporting_currency="INR",
            entity_hierarchy=sample_hierarchy
        )
        session.active_company_id = "test_perimeter_co"
        session.active_run_id = "run_test_perimeter"
        session.active_run_name = "Perimeter Test Run"
        company_manager.save_company(prof)
        if session.state:
            session.state.company_id = "test_perimeter_co"
            session.state.raw_tbs.clear()

        # Upload only P and S1 (missing S2)
        session.state.raw_tbs.append(RawTrialBalance(
            entity_code="P",
            period="31-Mar-2024",
            currency="INR",
            rows=[RawTBRow(account_code="1000", debit=100.0, credit=0.0)]
        ))
        session.state.raw_tbs.append(RawTrialBalance(
            entity_code="S1",
            period="31-Mar-2024",
            currency="INR",
            rows=[RawTBRow(account_code="1000", debit=100.0, credit=0.0)]
        ))

        # Attempt to run pipeline: MUST be blocked
        res = client.post("/api/run-pipeline")
        assert res.status_code == 400
        data = res.json()
        assert "detail" in data
        assert "S2" in data["detail"]
        assert "Perimeter Incomplete" in data["detail"]

        # Now add S2 to raw_tbs
        session.state.raw_tbs.append(RawTrialBalance(
            entity_code="S2",
            period="31-Mar-2024",
            currency="USD",
            rows=[RawTBRow(account_code="1000", debit=100.0, credit=0.0)]
        ))

        # Verify /api/status reports perimeter complete
        status_res = client.get("/api/status")
        status_data = status_res.json()
        assert status_data["is_perimeter_complete"] is True
        assert len(status_data["missing_entities"]) == 0
