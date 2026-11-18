from decimal import Decimal
from enum import StrEnum


class OTPChannel(StrEnum):
    EMAIL = "email"
    PHONE = "phone"


class ApplicationType(StrEnum):
    SELF = "self"
    REFERRAL = "referral"


class LoanType(StrEnum):
    PERSONAL_LOAN = "personal_loan"
    BUSINESS_LOAN = "business_loan"
    HOUSING_LOAN = "housing_loan"
    LOAN_AGAINST_PROPERTY = "loan_against_property"


class LeadStatus(StrEnum):
    LEAD_SUBMITTED = "lead_submitted"
    CUSTOMER_EVALUATION = "customer_evaluation"
    DOCUMENTS = "documents"
    BANK_PROCESS = "bank_process"
    DISBURSED = "disbursed"
    REJECTED = "rejected"


# Bonus commission rates per loan category
# Personal Loan: 1% per Lakh (0.010)
# Business Loan: 1% per Lakh (0.010)
# Loan Against Property: 0.5% per Lakh (0.005)
# Home Loan (Housing Loan): 0.2% per Lakh (0.002)
BONUS_RATES_BY_LOAN_TYPE: dict[str, Decimal] = {
    LoanType.PERSONAL_LOAN.value: Decimal("0.010"),
    LoanType.BUSINESS_LOAN.value: Decimal("0.010"),
    LoanType.LOAN_AGAINST_PROPERTY.value: Decimal("0.005"),
    LoanType.HOUSING_LOAN.value: Decimal("0.002"),
}

# Standard 5% Tax Deducted at Source (TDS)
TDS_RATE: Decimal = Decimal("0.050")

# Cooling period: 7 working days from date of disbursal
BONUS_COOLING_PERIOD_WORKING_DAYS: int = 7


class WithdrawalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    PROCESSED = "processed"
    REJECTED = "rejected"
