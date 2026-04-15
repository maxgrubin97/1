#!/usr/bin/env python3
"""Generate calibration_data.json for scorer testing."""
import json, os

records = []

# --- 25 IDEAL REFERRAL PARTNERS ---
ideal_referral = [
    {"company_name": "Summit SBA Lending Group", "category": "sba_lender", "key_signals": ["SBA preferred lender", "10-50 employees", "business acquisition loans"], "misleading_signals": ["also does consumer mortgages"]},
    {"company_name": "Cascade Business Finance", "category": "sba_lender", "key_signals": ["SBA 7(a) specialist", "boutique lender", "M&A financing"], "misleading_signals": []},
    {"company_name": "Patriot Capital SBA", "category": "sba_lender", "key_signals": ["SBA certified", "small business focus", "acquisition financing"], "misleading_signals": ["has residential division"]},
    {"company_name": "Heritage SBA Partners", "category": "sba_lender", "key_signals": ["SBA preferred", "boutique", "owner-operated deals"], "misleading_signals": []},
    {"company_name": "Pinnacle Business Credit", "category": "sba_lender", "key_signals": ["SBA 504 lender", "commercial focus", "SMB acquisitions"], "misleading_signals": []},
    {"company_name": "Apex Business Brokers", "category": "business_broker", "key_signals": ["IBBA member", "sell-side advisory", "main street M&A"], "misleading_signals": ["lists some real estate"]},
    {"company_name": "MainStreet Advisors LLC", "category": "business_broker", "key_signals": ["business sales", "buyer representation", "SMB focus"], "misleading_signals": []},
    {"company_name": "Keystone Deal Makers", "category": "business_broker", "key_signals": ["business broker", "confidential listings", "SBA deal experience"], "misleading_signals": []},
    {"company_name": "BlueSky Business Sales", "category": "business_broker", "key_signals": ["IBBA certified", "exit planning", "owner transitions"], "misleading_signals": ["also does franchise consulting"]},
    {"company_name": "Ridgeline M&A Advisors", "category": "business_broker", "key_signals": ["lower middle market", "business sales", "succession planning"], "misleading_signals": []},
    {"company_name": "Thornton & Walsh CPA", "category": "boutique_cpa", "key_signals": ["boutique CPA", "business owner clients", "tax planning"], "misleading_signals": []},
    {"company_name": "Greenfield Tax Advisory", "category": "boutique_cpa", "key_signals": ["SMB tax", "owner-operated clients", "regional firm"], "misleading_signals": []},
    {"company_name": "Blackwood Accounting Group", "category": "boutique_cpa", "key_signals": ["small firm", "business clients", "closely-held companies"], "misleading_signals": ["some individual returns"]},
    {"company_name": "Silverstone CPA Partners", "category": "boutique_cpa", "key_signals": ["boutique", "business advisory", "owner clients"], "misleading_signals": []},
    {"company_name": "Coastal Tax & Advisory", "category": "boutique_cpa", "key_signals": ["regional CPA", "SMB focus", "tax and advisory"], "misleading_signals": []},
    {"company_name": "Harmon Business Law Group", "category": "boutique_attorney", "key_signals": ["business transactions", "M&A attorney", "boutique firm"], "misleading_signals": []},
    {"company_name": "Meridian Legal Partners", "category": "boutique_attorney", "key_signals": ["corporate law", "deal counsel", "small firm"], "misleading_signals": ["some employment law"]},
    {"company_name": "Clearwater Business Attorneys", "category": "boutique_attorney", "key_signals": ["transactional law", "business sales", "boutique"], "misleading_signals": []},
    {"company_name": "Stratford Wealth Advisors", "category": "wealth_manager", "key_signals": ["independent RIA", "business owner clients", "liquidity events"], "misleading_signals": []},
    {"company_name": "Northgate Private Wealth", "category": "wealth_manager", "key_signals": ["boutique RIA", "HNW business owners", "exit planning"], "misleading_signals": []},
    {"company_name": "Lakeview Capital Advisors", "category": "wealth_manager", "key_signals": ["fee-only RIA", "SMB owners", "wealth management"], "misleading_signals": []},
    {"company_name": "First Community Business Bank", "category": "commercial_banker", "key_signals": ["community bank", "business loans", "SMB focus"], "misleading_signals": []},
    {"company_name": "Riverside Commercial Lending", "category": "commercial_banker", "key_signals": ["commercial banker", "business owner relationships", "local bank"], "misleading_signals": []},
    {"company_name": "Summit Valuation Services", "category": "valuation_advisor", "key_signals": ["business valuation", "CVA certified", "M&A advisory"], "misleading_signals": []},
    {"company_name": "Precision Business Appraisals", "category": "valuation_advisor", "key_signals": ["ASA certified", "business appraisal", "transaction support"], "misleading_signals": []},
]
for r in ideal_referral:
    records.append({
        "company_name": r["company_name"],
        "category": r["category"],
        "record_type": "ideal_referral_partner",
        "why_good_fit": "Strong referral source with business-owner client base aligned with MGR Advisory services.",
        "key_signals": r["key_signals"],
        "misleading_signals": r["misleading_signals"],
        "would_reach_out": True,
    })

# --- 25 POOR REFERRAL PARTNERS ---
poor_referral = [
    {"company_name": "Chase Business Banking", "category": "sba_lender", "key_signals": ["national bank", "consumer focus", "too large"], "misleading_signals": ["has SBA division"]},
    {"company_name": "Wells Fargo SBA Division", "category": "sba_lender", "key_signals": ["national bank", "mass market", "no personal relationship"], "misleading_signals": ["SBA preferred lender"]},
    {"company_name": "Bank of America Small Business", "category": "sba_lender", "key_signals": ["mega bank", "product-push culture", "no referral reciprocity"], "misleading_signals": ["SBA loans offered"]},
    {"company_name": "PNC Business Credit", "category": "commercial_banker", "key_signals": ["large regional bank", "impersonal", "relationship manager turnover"], "misleading_signals": ["SMB focus advertised"]},
    {"company_name": "Deloitte Tax LLP", "category": "boutique_cpa", "key_signals": ["Big 4", "enterprise clients", "no SMB referrals"], "misleading_signals": ["offers tax services"]},
    {"company_name": "PwC Advisory", "category": "boutique_cpa", "key_signals": ["Big 4", "Fortune 500 focus", "wrong client segment"], "misleading_signals": ["has advisory services"]},
    {"company_name": "Ernst & Young Assurance", "category": "boutique_cpa", "key_signals": ["Big 4", "public company audit", "no SMB relationships"], "misleading_signals": ["CPA firm"]},
    {"company_name": "KPMG Deal Advisory", "category": "boutique_cpa", "key_signals": ["Big 4", "large deal focus", "minimum engagement size too high"], "misleading_signals": ["M&A advisory"]},
    {"company_name": "Morgan Stanley Wealth", "category": "wealth_manager", "key_signals": ["wirehouse", "product sales culture", "no referral incentive"], "misleading_signals": ["serves HNW clients"]},
    {"company_name": "Merrill Lynch Wealth Management", "category": "wealth_manager", "key_signals": ["wirehouse", "AUM focus", "no business advisory referrals"], "misleading_signals": ["business owner clients"]},
    {"company_name": "UBS Financial Services", "category": "wealth_manager", "key_signals": ["wirehouse", "compliance-heavy", "referral restrictions"], "misleading_signals": ["wealth management"]},
    {"company_name": "Edward Jones", "category": "wealth_manager", "key_signals": ["retail brokerage", "individual investor focus", "wrong segment"], "misleading_signals": ["community presence"]},
    {"company_name": "Smith & Associates Injury Law", "category": "boutique_attorney", "key_signals": ["personal injury", "litigation focus", "no business clients"], "misleading_signals": ["boutique law firm"]},
    {"company_name": "Peterson Divorce Attorneys", "category": "boutique_attorney", "key_signals": ["family law", "no business owners", "wrong practice area"], "misleading_signals": ["local firm"]},
    {"company_name": "National PI Law Group", "category": "boutique_attorney", "key_signals": ["contingency fee", "plaintiff litigation", "no transactional work"], "misleading_signals": ["law firm"]},
    {"company_name": "BigBox Business Brokers", "category": "business_broker", "key_signals": ["franchise broker", "low-value transactions", "no M&A sophistication"], "misleading_signals": ["business sales"]},
    {"company_name": "Global M&A Corp", "category": "business_broker", "key_signals": ["large deal focus", "minimum $50M revenue", "wrong deal size"], "misleading_signals": ["M&A advisory"]},
    {"company_name": "RE/MAX Commercial", "category": "business_broker", "key_signals": ["real estate focus", "not business sales", "wrong specialty"], "misleading_signals": ["commercial listings"]},
    {"company_name": "Truist Bank Commercial", "category": "commercial_banker", "key_signals": ["large regional", "high turnover", "impersonal service"], "misleading_signals": ["business banking"]},
    {"company_name": "Fifth Third Business", "category": "commercial_banker", "key_signals": ["large bank", "product-centric", "no referral culture"], "misleading_signals": ["SMB services"]},
    {"company_name": "H&R Block Business", "category": "boutique_cpa", "key_signals": ["franchise tax prep", "transactional model", "no advisory relationships"], "misleading_signals": ["business tax returns"]},
    {"company_name": "Mass Mutual Financial", "category": "wealth_manager", "key_signals": ["insurance sales", "commission culture", "product push"], "misleading_signals": ["financial planning"]},
    {"company_name": "Nationwide Financial Advisors", "category": "wealth_manager", "key_signals": ["insurance-based", "captive agents", "wrong alignment"], "misleading_signals": ["financial advice"]},
    {"company_name": "Century 21 Commercial", "category": "valuation_advisor", "key_signals": ["real estate brokerage", "not business appraisal", "wrong specialty"], "misleading_signals": ["commercial property"]},
    {"company_name": "Zillow Business Listings", "category": "business_broker", "key_signals": ["online marketplace", "no relationship", "wrong model"], "misleading_signals": ["business listings"]},
]
for r in poor_referral:
    records.append({
        "company_name": r["company_name"],
        "category": r["category"],
        "record_type": "poor_referral_partner",
        "why_poor_fit": "Not aligned with MGR Advisory referral model — wrong segment, size, or relationship type.",
        "key_signals": r["key_signals"],
        "misleading_signals": r["misleading_signals"],
        "would_reach_out": False,
    })

# --- 25 IDEAL DIRECT PROSPECTS ---
ideal_direct = [
    {"company_name": "Ironclad General Contractors", "category": "construction", "key_signals": ["$5M-$50M revenue", "owner-operated", "established 10+ years"]},
    {"company_name": "Summit Excavation & Grading", "category": "construction", "key_signals": ["specialty contractor", "owner-run", "profitable niche"]},
    {"company_name": "Pacific Mechanical Services", "category": "construction", "key_signals": ["HVAC contractor", "commercial focus", "recurring revenue"]},
    {"company_name": "Keystone Electrical Group", "category": "construction", "key_signals": ["electrical contractor", "owner nearing retirement", "established"]},
    {"company_name": "Riverstone Plumbing Inc", "category": "construction", "key_signals": ["plumbing contractor", "commercial clients", "10-50 employees"]},
    {"company_name": "Westside Orthopedic Associates", "category": "healthcare", "key_signals": ["specialty practice", "owner physician", "profitable"]},
    {"company_name": "Lakeview Dental Group", "category": "healthcare", "key_signals": ["multi-location dental", "owner-operated", "strong cash flow"]},
    {"company_name": "Summit Veterinary Clinic", "category": "healthcare", "key_signals": ["veterinary practice", "owner-operated", "exit planning age"]},
    {"company_name": "Clearwater Physical Therapy", "category": "healthcare", "key_signals": ["PT practice", "owner nearing exit", "recurring patients"]},
    {"company_name": "Heritage Chiropractic Center", "category": "healthcare", "key_signals": ["established practice", "owner-operated", "stable revenue"]},
    {"company_name": "Pinnacle Engineering Consultants", "category": "professional_services", "key_signals": ["engineering firm", "owner-operated", "$5M+ revenue"]},
    {"company_name": "Meridian IT Solutions", "category": "professional_services", "key_signals": ["managed services", "recurring revenue", "owner-operated"]},
    {"company_name": "Stratford HR Consulting", "category": "professional_services", "key_signals": ["HR outsourcing", "SMB clients", "owner-operated"]},
    {"company_name": "Apex Environmental Services", "category": "professional_services", "key_signals": ["environmental consulting", "specialized niche", "owner-run"]},
    {"company_name": "Northgate Staffing Group", "category": "professional_services", "key_signals": ["staffing firm", "owner-operated", "established"]},
    {"company_name": "Cascade Commercial Properties", "category": "real_estate", "key_signals": ["commercial real estate", "portfolio owner", "multiple entities"]},
    {"company_name": "Summit Self-Storage LLC", "category": "real_estate", "key_signals": ["self-storage operator", "passive income", "tax optimization need"]},
    {"company_name": "Riverside Apartment Group", "category": "real_estate", "key_signals": ["multifamily owner", "1031 exchange", "depreciation planning"]},
    {"company_name": "Coastal Industrial Partners", "category": "real_estate", "key_signals": ["industrial real estate", "owner", "complex tax needs"]},
    {"company_name": "Heartland Car Wash Group", "category": "real_estate", "key_signals": ["car wash chain", "real estate heavy", "owner-operated"]},
    {"company_name": "Bluewave Digital Marketing", "category": "agency", "key_signals": ["digital agency", "owner-operated", "$3M+ revenue"]},
    {"company_name": "Ironwood Creative Agency", "category": "agency", "key_signals": ["marketing agency", "growing", "owner considering exit"]},
    {"company_name": "Summit Media Group", "category": "agency", "key_signals": ["media agency", "owner-operated", "recurring client retainers"]},
    {"company_name": "Clearwater PR & Communications", "category": "agency", "key_signals": ["PR firm", "boutique", "owner-operated"]},
    {"company_name": "Pacific Growth Marketing", "category": "agency", "key_signals": ["performance marketing", "SaaS clients", "owner-operated"]},
]
for r in ideal_direct:
    records.append({
        "company_name": r["company_name"],
        "category": r["category"],
        "record_type": "ideal_direct_prospect",
        "why_good_fit": "Owner-operated SMB with revenue scale and complexity suited for MGR Advisory tax and M&A services.",
        "key_signals": r["key_signals"],
        "misleading_signals": [],
        "would_reach_out": True,
    })

# --- 25 POOR DIRECT PROSPECTS ---
poor_direct = [
    {"company_name": "Microsoft Corporation", "category": "professional_services", "key_signals": ["Fortune 500", "public company", "internal tax team"], "reason": "Too large, public company with Big 4 auditors."},
    {"company_name": "Amazon Web Services", "category": "professional_services", "key_signals": ["Fortune 500", "public", "no SMB fit"], "reason": "Public mega-corp, wrong segment."},
    {"company_name": "Google LLC", "category": "agency", "key_signals": ["Fortune 500", "public", "internal finance team"], "reason": "Too large."},
    {"company_name": "Apple Inc", "category": "professional_services", "key_signals": ["Fortune 500", "public", "wrong segment"], "reason": "Public company."},
    {"company_name": "Walmart Inc", "category": "professional_services", "key_signals": ["Fortune 500", "retail giant", "public"], "reason": "Wrong segment entirely."},
    {"company_name": "TechStart AI Inc", "category": "professional_services", "key_signals": ["seed stage", "pre-revenue", "VC-backed"], "reason": "Pre-revenue startup, no tax complexity yet."},
    {"company_name": "GreenLeaf Nonprofit", "category": "professional_services", "key_signals": ["501(c)(3)", "no profit motive", "grant funded"], "reason": "Non-profit, no M&A or tax advisory need."},
    {"company_name": "Community Food Bank", "category": "professional_services", "key_signals": ["nonprofit", "no revenue", "donation funded"], "reason": "Non-profit."},
    {"company_name": "United Way Chapter", "category": "professional_services", "key_signals": ["nonprofit", "charity", "no SMB profile"], "reason": "Non-profit."},
    {"company_name": "Local Arts Council", "category": "agency", "key_signals": ["nonprofit", "grant funded", "no commercial activity"], "reason": "Non-profit."},
    {"company_name": "John Smith Consulting", "category": "professional_services", "key_signals": ["solopreneur", "1 employee", "minimal revenue"], "reason": "Too small, solopreneur."},
    {"company_name": "Jane Doe Freelance Design", "category": "agency", "key_signals": ["freelancer", "sole proprietor", "no employees"], "reason": "Too small."},
    {"company_name": "Bob's Lawn Care", "category": "construction", "key_signals": ["micro business", "1 person", "cash basis"], "reason": "Too small, no complexity."},
    {"company_name": "Mary's Etsy Shop", "category": "agency", "key_signals": ["hobby business", "no employees", "minimal revenue"], "reason": "Not a real business."},
    {"company_name": "Tom's Mobile Car Wash", "category": "construction", "key_signals": ["micro business", "cash only", "1 employee"], "reason": "Too small."},
    {"company_name": "Unicorn Health App", "category": "healthcare", "key_signals": ["VC-backed startup", "pre-revenue", "consumer app"], "reason": "Startup, no revenue."},
    {"company_name": "Series A SaaS Co", "category": "professional_services", "key_signals": ["startup", "burn rate", "no profit"], "reason": "Startup."},
    {"company_name": "Pre-seed Fintech", "category": "professional_services", "key_signals": ["no revenue", "angel funded", "startup"], "reason": "Pre-revenue startup."},
    {"company_name": "Beta Stage Marketplace", "category": "agency", "key_signals": ["pre-launch", "no customers", "startup"], "reason": "Not operational."},
    {"company_name": "MVP Health Tech", "category": "healthcare", "key_signals": ["startup", "no revenue", "seed stage"], "reason": "Startup."},
    {"company_name": "National Healthcare Corp", "category": "healthcare", "key_signals": ["Fortune 500", "public", "hospital system"], "reason": "Too large, public."},
    {"company_name": "Global Construction Partners", "category": "construction", "key_signals": ["ENR 500", "public company", "wrong segment"], "reason": "Too large."},
    {"company_name": "REIT Holdings Inc", "category": "real_estate", "key_signals": ["public REIT", "institutional", "no owner-operator"], "reason": "Public REIT, wrong profile."},
    {"company_name": "National Staffing Corp", "category": "professional_services", "key_signals": ["public company", "too large", "national"], "reason": "Too large, public."},
    {"company_name": "BigAgency Holdings", "category": "agency", "key_signals": ["holding company", "private equity owned", "no owner relationship"], "reason": "PE-owned, no owner to advise."},
]
for r in poor_direct:
    records.append({
        "company_name": r["company_name"],
        "category": r["category"],
        "record_type": "poor_direct_prospect",
        "why_poor_fit": r["reason"],
        "key_signals": r["key_signals"],
        "misleading_signals": [],
        "would_reach_out": False,
    })

output_path = os.path.join(os.path.dirname(__file__), "calibration_data.json")
with open(output_path, "w") as f:
    json.dump(records, f, indent=2)

print(f"Written {len(records)} records to {output_path}")
