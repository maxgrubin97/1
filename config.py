"""
Default configuration for the MGR Advisory client scraper.

Target: Small-to-mid businesses ($1M-$15M revenue) in the tri-state area
that are strong candidates for Fractional CFO services.

Industries are ranked by likelihood of needing fractional CFO support,
based on common characteristics: irregular cash flow, complex revenue
recognition, high growth, regulatory overhead, or lack of in-house
finance leadership.
"""

# ---------------------------------------------------------------------------
# Target Industries
# Ranked by fit for fractional CFO services at $1-15M revenue.
# Each entry: (search_term_for_google_maps, industry_label)
# ---------------------------------------------------------------------------
TARGET_INDUSTRIES = [
    # Tier 1 — Highest-fit industries
    ("law firm", "Legal / Law Firm"),
    ("accounting firm", "Accounting / Finance"),
    ("medical practice", "Healthcare"),
    ("dental practice", "Healthcare / Dental"),
    ("dermatology clinic", "Healthcare / Dermatology"),
    ("physical therapy clinic", "Healthcare / PT"),
    ("veterinary clinic", "Veterinary"),
    ("marketing agency", "Marketing / Advertising"),
    ("digital marketing agency", "Marketing / Digital"),
    ("PR agency", "Public Relations"),
    ("architecture firm", "Architecture / Design"),
    ("engineering firm", "Engineering"),
    ("IT services company", "Technology / IT Services"),
    ("software company", "Technology / SaaS"),
    ("consulting firm", "Consulting"),
    ("management consulting", "Consulting"),

    # Tier 2 — Strong fit
    ("construction company", "Construction"),
    ("general contractor", "Construction"),
    ("real estate agency", "Real Estate"),
    ("property management company", "Real Estate / Property Mgmt"),
    ("insurance agency", "Insurance"),
    ("wealth management firm", "Financial Services"),
    ("staffing agency", "Staffing / Recruiting"),
    ("recruiting firm", "Staffing / Recruiting"),
    ("manufacturing company", "Manufacturing"),
    ("logistics company", "Logistics / Distribution"),
    ("wholesale distributor", "Wholesale / Distribution"),

    # Tier 3 — Good fit
    ("e-commerce company", "E-Commerce"),
    ("restaurant group", "Hospitality / Restaurant"),
    ("catering company", "Hospitality / Catering"),
    ("event planning company", "Events / Planning"),
    ("fitness studio", "Fitness / Wellness"),
    ("med spa", "Healthcare / Med Spa"),
    ("auto dealership", "Automotive"),
    ("auto body shop", "Automotive"),
    ("landscaping company", "Landscaping / Outdoor"),
    ("cleaning company", "Facility Services"),
    ("security company", "Security Services"),
    ("printing company", "Printing / Media"),
]

# ---------------------------------------------------------------------------
# LinkedIn search queries
# These target decision makers at companies likely to need a fractional CFO.
# The scraper prepends site:linkedin.com/in/ and appends location.
# ---------------------------------------------------------------------------
LINKEDIN_QUERIES = [
    # Direct decision-maker searches
    '"CEO" "small business"',
    '"founder" "startup"',
    '"owner" "business"',
    '"president" "company"',
    '"managing partner"',
    '"managing director"',

    # Industry-specific decision makers
    '"CEO" OR "founder" "agency"',
    '"CEO" OR "owner" "law firm"',
    '"CEO" OR "owner" "medical" OR "dental" OR "healthcare"',
    '"CEO" OR "owner" "construction" OR "contractor"',
    '"CEO" OR "owner" "real estate"',
    '"CEO" OR "owner" "manufacturing"',
    '"CEO" OR "owner" "consulting"',
    '"CEO" OR "owner" "technology" OR "software" OR "IT"',
    '"CEO" OR "owner" "staffing" OR "recruiting"',
    '"CEO" OR "owner" "insurance"',

    # People likely seeking CFO help
    '"looking for CFO"',
    '"need a CFO"',
    '"fractional CFO"',
    '"outsourced CFO"',
    '"part-time CFO"',
]

# ---------------------------------------------------------------------------
# Default locations — Tri-State Area (NY, NJ, CT)
# ---------------------------------------------------------------------------
DEFAULT_LOCATIONS = [
    # New York City
    "New York, NY",
    "Manhattan, NY",
    "Brooklyn, NY",
    "Queens, NY",

    # NYC Suburbs — New York
    "Westchester County, NY",
    "White Plains, NY",
    "Long Island, NY",
    "Garden City, NY",

    # New Jersey
    "Jersey City, NJ",
    "Newark, NJ",
    "Hoboken, NJ",
    "Morristown, NJ",
    "Princeton, NJ",
    "Paramus, NJ",
    "Edison, NJ",
    "Cherry Hill, NJ",

    # Connecticut
    "Stamford, CT",
    "Greenwich, CT",
    "Hartford, CT",
    "New Haven, CT",
    "Norwalk, CT",
    "Bridgeport, CT",
]

# ---------------------------------------------------------------------------
# Scraping parameters
# ---------------------------------------------------------------------------
REQUEST_DELAY_MIN = 3.0      # Seconds between requests (minimum)
REQUEST_DELAY_MAX = 6.0      # Seconds between requests (maximum)
MAX_RESULTS_PER_QUERY = 20   # Google results per search
MAX_GMAPS_PER_QUERY = 20     # Places results per Maps search
