"""Standard M&A due-diligence request list seeded into every new deal."""

from app.models.enums import DocumentCategory as C
from app.models.enums import Priority as P

DEFAULT_CHECKLIST: list[tuple[C, str, str, P]] = [
    # Financial
    (C.FINANCIAL, "Audited financial statements (last 3 years)", "Balance sheet, P&L, cash flow and auditor's opinion.", P.HIGH),
    (C.FINANCIAL, "Management accounts (YTD and monthly)", "Current-year monthly P&L and balance sheet.", P.HIGH),
    (C.FINANCIAL, "Quality of earnings / EBITDA bridge", "Normalisation adjustments and one-off items.", P.HIGH),
    (C.FINANCIAL, "Debt schedule and financing agreements", "Facilities, covenants, security and change-of-control triggers.", P.HIGH),
    (C.FINANCIAL, "Working capital analysis", "AR/AP ageing, inventory and seasonality.", P.MEDIUM),
    (C.FINANCIAL, "Budget and financial projections", "Forecast with key assumptions.", P.MEDIUM),
    (C.FINANCIAL, "Off-balance-sheet liabilities and guarantees", "Contingent liabilities, leases, guarantees.", P.MEDIUM),
    # Tax
    (C.TAX, "Corporate tax returns (last 3-5 years)", "Filed returns and assessments.", P.HIGH),
    (C.TAX, "Tax audits, disputes and correspondence", "Open audits, notices and settlements.", P.HIGH),
    (C.TAX, "Transfer pricing documentation", "Intercompany policies and studies.", P.MEDIUM),
    (C.TAX, "VAT / indirect tax compliance", "Returns and reconciliations.", P.MEDIUM),
    (C.TAX, "Tax losses and deferred tax position", "Availability post-transaction.", P.LOW),
    # Legal / corporate
    (C.CORPORATE, "Certificate of incorporation and constitutional documents", "Articles, by-laws, amendments.", P.MEDIUM),
    (C.CORPORATE, "Capitalisation table and shareholder register", "Classes of shares, options, warrants.", P.HIGH),
    (C.CORPORATE, "Shareholder and voting agreements", "Drag/tag rights, pre-emption, consents.", P.HIGH),
    (C.CORPORATE, "Board minutes and resolutions (last 3 years)", "Material decisions and approvals.", P.MEDIUM),
    (C.LEGAL, "Pending and threatened litigation", "Claims, disputes, provisions and counsel letters.", P.HIGH),
    (C.LEGAL, "Regulatory investigations and sanctions", "Any investigations, fines or consent orders.", P.HIGH),
    (C.LEGAL, "Insurance policies and claims history", "Coverage, limits and open claims.", P.MEDIUM),
    # Contracts / commercial
    (C.CONTRACTS, "Top customer contracts", "Terms, renewal, termination and change-of-control clauses.", P.HIGH),
    (C.CONTRACTS, "Key supplier and vendor agreements", "Exclusivity, minimum purchase and pricing.", P.HIGH),
    (C.CONTRACTS, "Contracts with change-of-control or assignment restrictions", "Consents required for the deal.", P.HIGH),
    (C.CONTRACTS, "Real estate leases", "Rent, term, break options and assignment.", P.MEDIUM),
    (C.COMMERCIAL, "Customer concentration and revenue by customer", "Top 10 customers share of revenue.", P.HIGH),
    (C.COMMERCIAL, "Market and competitor analysis", "Market size, share and positioning.", P.LOW),
    (C.COMMERCIAL, "Sales pipeline and backlog", "Contracted and probable revenue.", P.MEDIUM),
    # HR
    (C.HR, "Organisation chart and headcount", "By function, location and contract type.", P.MEDIUM),
    (C.HR, "Key employee and executive agreements", "Compensation, retention, non-compete, severance.", P.HIGH),
    (C.HR, "Pension and benefit plans", "Funding status and liabilities.", P.MEDIUM),
    (C.HR, "Employment disputes and union agreements", "Claims, collective agreements.", P.MEDIUM),
    # IP / IT
    (C.INTELLECTUAL_PROPERTY, "Patent, trademark and copyright register", "Ownership, jurisdictions and expiry.", P.HIGH),
    (C.INTELLECTUAL_PROPERTY, "IP licences (in and out)", "Royalties, exclusivity and restrictions.", P.MEDIUM),
    (C.INTELLECTUAL_PROPERTY, "IP infringement claims", "Asserted or threatened claims.", P.MEDIUM),
    (C.IT, "IT systems and software inventory", "Critical systems, licences and dependencies.", P.LOW),
    (C.IT, "Cybersecurity incidents and data breaches", "Incidents, notifications and remediation.", P.HIGH),
    # Regulatory / compliance / ESG
    (C.REGULATORY, "Business licences and permits", "Validity and transferability.", P.MEDIUM),
    (C.REGULATORY, "Data protection compliance (GDPR / privacy)", "Policies, DPIAs, processor agreements.", P.MEDIUM),
    (C.REGULATORY, "Anti-bribery, AML and sanctions compliance", "Policies, training, screening.", P.MEDIUM),
    (C.REGULATORY, "Merger control / antitrust filing analysis", "Required filings and timetable.", P.HIGH),
    (C.ENVIRONMENTAL, "Environmental permits and liabilities", "Contamination, remediation and ESG reports.", P.LOW),
    # Operational
    (C.OPERATIONAL, "Key operational assets and capacity", "Facilities, equipment and utilisation.", P.LOW),
    (C.OPERATIONAL, "Integration and synergy assumptions", "Cost and revenue synergies with owners.", P.MEDIUM),
]

# Workstreams the readiness score expects at least one document for.
CORE_CATEGORIES = [C.FINANCIAL, C.LEGAL, C.TAX, C.CONTRACTS, C.HR, C.CORPORATE]
