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
