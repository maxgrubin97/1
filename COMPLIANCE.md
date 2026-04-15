# Compliance & Data Source Notes

## What This System Does

This is a business research tool that discovers publicly available information
about companies and professionals for the purpose of business development
outreach. It uses the same data sources a human researcher would use:
Google Maps, company websites, and public LinkedIn profiles.

## What Was Intentionally NOT Built

### LinkedIn

- **No login bypass.** The system never logs into LinkedIn or attempts to
  access authenticated pages.
- **No private data scraping.** Only data visible in public Google search
  result snippets is captured (name, title, company from search result titles).
- **No CAPTCHA circumvention.** No anti-bot evasion of any kind.
- **No browser fingerprint spoofing.** No residential proxies or stealth mode.
- **No rate limit circumvention.** Configurable delays between all requests.
- **CSV import is first-class.** The recommended path for LinkedIn data is
  exporting from LinkedIn Sales Navigator or Apollo, then importing the CSV.
  This is compliant with those platforms' export features.

### Google Maps

- **Uses the official Places API.** All Maps data is obtained through Google's
  paid API, which is the sanctioned method for programmatic access.
- **No scraping of Google Maps HTML.** Only API responses are used.
- **API key required.** Users must provide their own API key and agree to
  Google's Terms of Service.

### Company Websites

- **Respects robots.txt.** The system checks robots.txt before fetching pages
  and skips blocked paths.
- **Honest user agent.** The system identifies itself as a research tool,
  not a browser.
- **Rate limited.** Configurable delays between requests (default 2-5 seconds).
- **Limited page fetches.** Only key pages are fetched (home, about, team,
  services) — typically 3-4 pages per site.

### General

- **No credential theft.** No passwords, tokens, or session cookies are
  captured or stored.
- **No stealth scraping.** No headless browser spoofing, no residential
  proxy rotation, no fingerprint evasion.
- **No Terms of Service violation.** The system is designed to use each
  data source within its intended access model.

## Data Handling

- All data is stored locally in SQLite (`data/leads.db`).
- No data is transmitted to third parties (except API calls to Google/SerpAPI).
- Whitelist and blacklist files allow manual control over what is included.
- Exported files are saved locally to the `output/` directory.

## Recommendations

1. **Use SerpAPI** for Google search queries. It's a paid, compliant API
   that avoids direct Google scraping.
2. **Import LinkedIn data via CSV** rather than relying on public discovery.
   Sales Navigator exports provide richer, more reliable data.
3. **Review the `data/competitor_domains.csv`** file and add known competitors
   to avoid including them in results.
4. **Set appropriate rate limits** in your `.env` file to avoid overwhelming
   any data source.
