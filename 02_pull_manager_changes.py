"""

Scrapes the Transfermarkt "Changes in coach" pages for the Premier League
across 8 seasons (2017-18 through 2024-25) and produces a clean CSV of
all managerial changes.

Output: data/manager_changes_raw.csv
    One row per managerial change with columns:
        season_label, change_type, club,
        out_manager, out_role, out_matchday, out_rank, out_ppg, leaving_date,
        in_manager, in_role, in_rank, in_ppg, in_first_match,
        days_in_charge,
        [empty for manual coding]: reason, include, ambiguity_flag, notes

Dependencies:
    pip install requests beautifulsoup4 pandas
"""

import time
import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(exist_ok=True)

# Start years for each season (2017 = 2017-18, ..., 2024 = 2024-25)
SEASON_YEARS = [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]

SEASON_LABEL_MAP = {
    2017: "2017-18", 2018: "2018-19", 2019: "2019-20", 2020: "2020-21",
    2021: "2021-22", 2022: "2022-23", 2023: "2023-24", 2024: "2024-25",
}

BASE_URL = (
    "https://www.transfermarkt.com/premier-league/trainerwechsel/"
    "wettbewerb/GB1/saison_id/{year}/plus/1"
)

# Transfermarkt blocks default Python user agents — this mimics a browser
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.transfermarkt.com/",
}

# Polite delay between requests (seconds) — don't hammer the server
REQUEST_DELAY = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scraping helpers
# ---------------------------------------------------------------------------

def fetch_page(year: int) -> BeautifulSoup | None:
    url = BASE_URL.format(year=year)
    logger.info("Fetching %s ...", url)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        logger.error("Failed to fetch year %d: %s", year, e)
        return None


def clean_text(text: str) -> str:
    """Strip whitespace and normalise."""
    if not text:
        return ""
    return " ".join(text.split()).strip()


def parse_season_page(soup: BeautifulSoup, year: int) -> list[dict]:
    """
    Parse one season's Transfermarkt coach-changes page.
    
    The page has two sections separated by a header row:
        - "Change(s) in coach at the end of the season"  -> change_type = "end_of_season"
        - "Change(s) in coach during the season"         -> change_type = "during_season"
    
    Returns a list of dicts, one per row.
    """
    season = SEASON_LABEL_MAP[year]
    rows = []
    current_type = "unknown"

    # The main table has class "items"
    table = soup.find("table", {"class": "items"})
    if table is None:
        logger.warning("No table found for season %s — page structure may have changed.", season)
        return rows

    tbody = table.find("tbody")
    if tbody is None:
        logger.warning("No tbody found for season %s.", season)
        return rows

    for tr in tbody.find_all("tr"):
        # Check if this row is a section header
        header_cell = tr.find("td", {"class": "extrarow"})
        if header_cell:
            text = clean_text(header_cell.get_text())
            if "end of the season" in text.lower():
                current_type = "end_of_season"
            elif "during the season" in text.lower():
                current_type = "during_season"
            continue

        # Skip image-only rows or empty rows
        cells = tr.find_all("td")
        if len(cells) < 8:
            continue

        try:
            # --- Club (cell 0) ---
            club_cell = cells[0]
            club_img = club_cell.find("img")
            club = clean_text(club_img["title"]) if club_img and club_img.get("title") else ""

            # --- Outgoing manager (cell 1) ---
            out_cell = cells[1]
            out_links = out_cell.find_all("a")
            out_manager = clean_text(out_links[0].get_text()) if out_links else clean_text(out_cell.get_text())
            # Role (Manager / Caretaker Manager) is in a span or second line
            out_role_tag = out_cell.find("span") or out_cell.find("small")
            out_role = clean_text(out_role_tag.get_text()) if out_role_tag else "manager"

            # --- Matchday (cell 2) ---
            out_matchday = clean_text(cells[2].get_text())

            # --- Rank at departure (cell 3) ---
            out_rank = clean_text(cells[3].get_text())

            # --- PPG outgoing (cell 4) ---
            out_ppg = clean_text(cells[4].get_text())

            # --- Last match (cell 5) — skip, visual only ---

            # --- Leaving date (cell 6) ---
            leaving_date = clean_text(cells[6].get_text())

            # --- Days in charge (cell 7) ---
            days_in_charge = clean_text(cells[7].get_text())

            # --- Incoming manager (cell 8) ---
            in_cell = cells[8]
            in_links = in_cell.find_all("a")
            in_manager = clean_text(in_links[0].get_text()) if in_links else clean_text(in_cell.get_text())
            in_role_tag = in_cell.find("span") or in_cell.find("small")
            in_role = clean_text(in_role_tag.get_text()) if in_role_tag else "manager"

            # --- Rank at arrival (cell 9) ---
            in_rank = clean_text(cells[9].get_text()) if len(cells) > 9 else ""

            # --- PPG incoming (cell 10) ---
            in_ppg = clean_text(cells[10].get_text()) if len(cells) > 10 else ""

            # --- First match (cell 11) — visual only, skip ---

            # Skip rows that have no club (malformed)
            if not club and not out_manager:
                continue

            rows.append({
                "season_label":    season,
                "change_type":     current_type,
                "club":            club,
                "out_manager":     out_manager,
                "out_role":        out_role,
                "out_matchday":    out_matchday,
                "out_rank":        out_rank,
                "out_ppg":         out_ppg,
                "leaving_date":    leaving_date,
                "days_in_charge":  days_in_charge,
                "in_manager":      in_manager,
                "in_role":         in_role,
                "in_rank":         in_rank,
                "in_ppg":          in_ppg,
                # Manual coding columns — fill these in yourself
                "reason":          "",  # sacked | mutual_consent | voluntary
                "include":         "",  # 1 | 0
                "ambiguity_flag":  "",  # 0 | 1
                "notes":           "",  # free text
            })

        except Exception as e:
            logger.debug("Skipping malformed row: %s", e)
            continue

    logger.info("  -> %d changes found for %s (%d during season)",
                len(rows), season,
                sum(1 for r in rows if r["change_type"] == "during_season"))
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    all_rows = []

    for year in SEASON_YEARS:
        soup = fetch_page(year)
        if soup:
            rows = parse_season_page(soup, year)
            all_rows.extend(rows)
        time.sleep(REQUEST_DELAY)  # be polite to Transfermarkt

    if not all_rows:
        logger.error("No data collected. Check if Transfermarkt blocked the requests.")
        return

    df = pd.DataFrame(all_rows)

    # Summary
    logger.info("Total changes scraped: %d", len(df))
    logger.info("During-season changes (your treatment events): %d",
                len(df[df["change_type"] == "during_season"]))
    logger.info("End-of-season changes (exclude from analysis): %d",
                len(df[df["change_type"] == "end_of_season"]))

    # Save full dataset
    df.to_csv(OUTPUT_DIR / "manager_changes_raw.csv", index=False)
    logger.info("Saved to data/manager_changes_raw.csv")

    # Also save a filtered view of just the during-season changes
    # (the ones you actually need to code)
    during = df[df["change_type"] == "during_season"].copy()
    during.to_csv(OUTPUT_DIR / "manager_changes_during_season.csv", index=False)
    logger.info("Saved during-season only to data/manager_changes_during_season.csv")

    # Print a preview
    print("\n" + "=" * 70)
    print("DURING-SEASON CHANGES — PREVIEW (your treatment events)")
    print("=" * 70)
    print(during[["season_label", "club", "out_manager", "in_manager",
                   "leaving_date", "out_rank", "out_ppg", "in_role"]
                 ].to_string(index=False))
    print("=" * 70)
    print(f"\nTotal during-season changes: {len(during)}")
    print("\nBreakdown by season:")
    print(during.groupby("season_label").size().to_string())
    print("\nNEXT STEP:")
    print("  Open data/manager_changes_during_season.csv")
    print("  Fill in: reason, include, ambiguity_flag columns")
    print("  Save as: data/manager_changes_coded.csv")


if __name__ == "__main__":
    main()
