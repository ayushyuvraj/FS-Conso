"""Chart of Accounts (COA) domain models."""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class AccountClassification(str, Enum):
    ASSET = "Asset"
    LIABILITY = "Liability"
    EQUITY = "Equity"
    INCOME = "Income"
    EXPENSE = "Expense"

class RollUpOperator(str, Enum):
    ADDITION = "Addition"
    SUBTRACTION = "Subtraction"

class COAItem(BaseModel):
    """An individual line item within the Group Chart of Accounts."""
    account_code: str = Field(..., description="Unique standardized GL code (e.g. 100000, A110101)")
    account_name: str = Field(..., description="Standardized account description")
    level_3: Optional[str] = None  # Assets, Liabilities, Equity, etc.
    level_2: Optional[str] = None  # Non-Current Assets, Current Assets
    level_1: Optional[str] = None  # Property, Plant & Equipment
    level_0_account: Optional[str] = None  # Land, Buildings, Cash
    account_type: AccountClassification = AccountClassification.ASSET
    rollup_operator: RollUpOperator = RollUpOperator.ADDITION
    fs_statement: str = "BS"  # "BS" for Balance Sheet, "PL" for Profit & Loss
    fs_line: Optional[str] = None

    @property
    def is_debit_natural(self) -> bool:
        """Assets and Expenses are debit-natural (positive in standardized import)."""
        return self.account_type in (AccountClassification.ASSET, AccountClassification.EXPENSE)

    @property
    def is_credit_natural(self) -> bool:
        """Liabilities, Equity, and Income are credit-natural (negative in standardized import)."""
        return self.account_type in (AccountClassification.LIABILITY, AccountClassification.EQUITY, AccountClassification.INCOME)

class ChartOfAccounts(BaseModel):
    """Complete Group Chart of Accounts structure."""
    items: Dict[str, COAItem] = Field(default_factory=dict)

    def add_item(self, item: COAItem) -> None:
        self.items[item.account_code] = item

    def get_item(self, code: str) -> Optional[COAItem]:
        return self.items.get(code)

    def find_by_name(self, name: str) -> Optional[COAItem]:
        normalized = name.strip().lower()
        for item in self.items.values():
            if item.account_name.strip().lower() == normalized:
                return item
        return None
