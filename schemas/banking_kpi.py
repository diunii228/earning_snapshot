from typing import Any

from pydantic import BaseModel, Field

BANKING_KPIS = {
    "profitability": {
        "pbt": "Profit Before Tax (Lợi nhuận trước thuế)",
        "pbt_growth_yoy": "PBT Growth vs Previous Year (%)",
        "pbt_growth_qoq": "PBT Growth vs Previous Quarter (%)",
        "pat": "Profit After Tax (Lợi nhuận sau thuế)",
        "net_interest_income": "Net Interest Income",
        "non_interest_income": "Non-Interest Income",
        "eps": "Earnings Per Share (EPS - Thu nhập trên mỗi cổ phần)" 
    },
    "balance_sheet": {
        "total_assets": "Total Assets (Tổng tài sản)",
        "total_assets_growth_yoy": "Total Assets Growth vs Previous Year (%)",
        "total_assets_growth_qoq": "Total Assets Growth vs Previous Quarter (%)",
        "total_assets_growth_qtd": "Total Assets Growth QTD (%)",
        "total_assets_growth_ytd": "Total Assets Growth YTD (%)",
        "equity": "Owner's Equity (Vốn chủ sở hữu)",
        "charter_capital": "Charter Capital (Vốn điều lệ)",
        "leverage_ratio": "Leverage Ratio (Tỷ lệ đòn bẩy) %" 
    },
    "lending_deposit": {
        "total_credit": "Total Outstanding Credit (Dư nợ tín dụng)",
        "credit_growth_yoy": "Credit Growth vs Previous Year (%)",
        "credit_growth_qoq": "Credit Growth vs Previous Quarter (%)",
        "credit_growth_ytd": "Credit Growth YTD (%)",
        "total_deposits": "Total Customer Deposits (Huy động vốn)",
        "deposit_growth_yoy": "Deposit Growth vs Previous Year (%)",
        "deposit_growth_qoq": "Deposit Growth vs Previous Quarter (%)",
        "deposit_growth_ytd": "Deposit Growth YTD (%)",
        "loan_to_deposit_ratio": "Loan-to-Deposit Ratio (LDR)",
        "mlt_ratio": "Short-term Funds for MLT Loans Ratio (Tỷ lệ vốn ngắn hạn cho vay trung dài hạn) %", 
        "wholesale_funding_ratio": "Wholesale Funding Ratio (Tỷ lệ huy động vốn bán buôn) %" 
    },
    "profitability_ratios": {
        "roa": "Return on Assets (ROA) %",
        "roe": "Return on Equity (ROE) %",
        "nim": "Net Interest Margin (NIM) %",
        "cir": "Cost-to-Income Ratio (CIR) %",
        "cost_of_funds": "Cost of Funds (COF - Chi phí vốn) %",
        "lending_yields": "Lending Yields / Asset Yield (Lợi suất cho vay) %" 
    },
    "asset_quality": {
        "npl_ratio": "Non-Performing Loan Ratio (NPL/Nợ xấu) %",
        "group_2_ratio": "Group 2 Loan Ratio (Nợ nhóm 2) %",
        "llr": "Loan Loss Reserve Ratio (Dự phòng rủi ro tín dụng) %",
        "credit_cost": "Credit Cost / Cost of Risk %",
        "coverage_ratio": "NPL Coverage Ratio %"
    },
    "other_metrics": {
        "casa_ratio": "CASA Ratio (Current + Savings Account) %",
        "net_interest_income_growth": "Net Interest Income Growth %",
        "fee_income": "Fee & Commission Income",
        "operating_expenses": "Operating Expenses",
        "car": "Capital Adequacy Ratio (CAR - Tỷ lệ an toàn vốn) %",
        "p_e_ratio": "Price-to-Earnings Ratio (P/E)",
        "p_b_ratio": "Price-to-Book Ratio (P/B)" 
    }
}

class ProfitabilitySchema(BaseModel):
    """Schema for profitability information."""

    pbt: float = Field(description="Profit Before Tax (Lợi nhuận trước thuế)")
    pbt_growth_yoy: float = Field(
        description="PBT Growth vs Previous Year (%)",
    )
    pbt_growth_qoq: float = Field(
        description="PBT Growth vs Previous Quarter (%)",
    )
    pat: float = Field(description="Profit After Tax (Lợi nhuận sau thuế)")
    net_interest_income: float = Field(description="Net Interest Income")
    non_interest_income: float = Field(description="Non-Interest Income")


class BalanceSheetSchema(BaseModel):
    """Schema for balance sheet information."""

    total_assets: float = Field(
        description="Total Assets (Tổng tài sản)",
    )
    total_assets_growth_yoy: float = Field(
        description="Total Assets Growth vs Previous Year (%)",
    )
    total_assets_growth_qoq: float = Field(
        description="Total Assets Growth vs Previous Quarter (%)",
    )
    total_assets_growth_qtd: float = Field(
        description="Total Assets Growth QTD (%)",
    )
    total_assets_growth_ytd: float = Field(
        description="Total Assets Growth YTD (%)",
    )


class LendingDepositSchema(BaseModel):
    """Schema for lending and deposit information."""

    total_credit: float = Field(
        description="Total Outstanding Credit (Dư nợ tín dụng)",
    )
    credit_growth_yoy: float = Field(
        description="Credit Growth vs Previous Year (%)",
    )
    credit_growth_qoq: float = Field(
        description="Credit Growth vs Previous Quarter (%)",
    )
    credit_growth_ytd: float = Field(
        description="Credit Growth YTD (%)",
    )
    total_deposits: float = Field(
        description="Total Customer Deposits (Huy động vốn)",
    )
    deposit_growth_yoy: float = Field(
        description="Deposit Growth vs Previous Year (%)",
    )
    deposit_growth_qoq: float = Field(
        description="Deposit Growth vs Previous Quarter (%)",
    )
    deposit_growth_ytd: float = Field(
        description="Deposit Growth YTD (%)",
    )
    loan_to_deposit_ratio: float = Field(
        description="Loan-to-Deposit Ratio (LDR)",
    )


class ProfitabilityRatiosSchema(BaseModel):
    """Schema for profitability ratios information."""

    roa: float = Field(description="Return on Assets (ROA) %")
    roe: float = Field(description="Return on Equity (ROE) %")
    nim: float = Field(description="Net Interest Margin (NIM) %")
    cir: float = Field(description="Cost-to-Income Ratio (CIR) %")


class AssetQualitySchema(BaseModel):
    """Schema for asset quality information."""

    npl_ratio: float = Field(
        description="Non-Performing Loan Ratio (NPL/Nợ xấu) %",
    )
    group_2_ratio: float = Field(
        description="Group 2 Loan Ratio (Nợ nhóm 2) %",
    )
    llr: float = Field(
        description=(
            "Loan Loss Reserve Ratio (Dự phòng rủi ro tín dụng) %"
        ),
    )
    credit_cost: float = Field(
        description="Credit Cost / Cost of Risk %",
    )
    coverage_ratio: float = Field(
        description="NPL Coverage Ratio %",
    )


class OtherMetricsSchema(BaseModel):
    """Schema for other metrics information."""

    casa_ratio: float = Field(
        description="CASA Ratio (Current + Savings Account) %",
    )
    net_interest_income_growth: float = Field(
        description="Net Interest Income Growth %",
    )
    fee_income: float = Field(description="Fee & Commission Income")
    operating_expenses: float = Field(description="Operating Expenses")


class BankingKpiInfoSchema(BaseModel):
    """Schema for banking KPI info."""

    profitability: ProfitabilitySchema
    balance_sheet: BalanceSheetSchema
    lending_deposit: LendingDepositSchema
    profitability_ratios: ProfitabilityRatiosSchema
    asset_quality: AssetQualitySchema
    other_metrics: OtherMetricsSchema


__all__ = [
    "BANKING_KPIS",
    "ProfitabilitySchema",
    "BalanceSheetSchema",
    "LendingDepositSchema",
    "ProfitabilityRatiosSchema",
    "AssetQualitySchema",
    "OtherMetricsSchema",
    "BankingKpiInfoSchema",
]

