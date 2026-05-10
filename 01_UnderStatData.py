"""
Pulls Premier League match data from Understat for 8 seasons (2017-18 through
2024-25) using the soccerdata package.

Output: data/understat_match_panel.parquet + .csv
    One row per team-match with columns:
        match_id, season, season_label, date, gameweek,
        team, opponent, is_home,
        goals_for, goals_against, points, result,
        xg_for, xg_against, xgd

"""

import logging
from pathlib import Path

import pandas as pd
import soccerdata as sd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Understat uses the START year of the season as a 4-digit string
# "2017" = 2017-18, ..., "2024" = 2024-25
SEASONS = ["1718", "1819", "1920", "2021", "2122", "2223", "2324", "2425"]
LEAGUE = "ENG-Premier League"

OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(exist_ok=True)

# Canonical team name mapping — align with script 02 (manager data)
# Keys are Understat names, values are canonical names
TEAM_NAME_CANONICAL = {
    "Manchester United":    "Manchester United",
    "Manchester City":      "Manchester City",
    "Arsenal":              "Arsenal",
    "Chelsea":              "Chelsea",
    "Liverpool":            "Liverpool",
    "Tottenham":            "Tottenham Hotspur",
    "Newcastle United":     "Newcastle United",
    "West Ham":             "West Ham United",
    "Aston Villa":          "Aston Villa",
    "Everton":              "Everton",
    "Brighton":             "Brighton & Hove Albion",
    "Wolverhampton Wanderers": "Wolverhampton Wanderers",
    "Leicester":            "Leicester City",
    "Crystal Palace":       "Crystal Palace",
    "Brentford":            "Brentford",
    "Fulham":               "Fulham",
    "Nottingham Forest":    "Nottingham Forest",
    "Bournemouth":          "AFC Bournemouth",
    "Burnley":              "Burnley",
    "Southampton":          "Southampton",
    "Leeds":                "Leeds United",
    "Watford":              "Watford",
    "Norwich":              "Norwich City",
    "Sheffield United":     "Sheffield United",
    "West Brom":            "West Bromwich Albion",
    "Huddersfield":         "Huddersfield Town",
    "Cardiff":              "Cardiff City",
    "Swansea":              "Swansea City",
    "Stoke":                "Stoke City",
    "Luton":                "Luton Town",
    "Ipswich":              "Ipswich Town",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def standardize_team(name: str) -> str:
    if pd.isna(name):
        return name
    name = str(name).strip()
    return TEAM_NAME_CANONICAL.get(name, name)


def points_from_goals(gf: int, ga: int) -> int:
    if gf > ga:
        return 3
    if gf == ga:
        return 1
    return 0


def result_letter(gf: int, ga: int) -> str:
    if gf > ga:
        return "W"
    if gf == ga:
        return "D"
    return "L"


SEASON_LABEL_MAP = {
    "1718": "2017-18", "1819": "2018-19", "1920": "2019-20",
    "2021": "2020-21", "2122": "2021-22", "2223": "2022-23",
    "2324": "2023-24", "2425": "2024-25",
}

def season_label(season_str: str) -> str:
    return SEASON_LABEL_MAP.get(str(season_str), str(season_str))


# ---------------------------------------------------------------------------
# Pull and reshape
# ---------------------------------------------------------------------------

def pull_understat_schedule() -> pd.DataFrame:
    """
    Pull match schedule from Understat for all configured seasons.
    Returns the raw schedule DataFrame (one row per match).

    Understat's read_schedule() includes xG directly:
        home_team, away_team, home_goals, away_goals, home_xg, away_xg, date, ...
    """
    logger.info("Initializing Understat scraper for seasons: %s", SEASONS)
    understat = sd.Understat(leagues=LEAGUE, seasons=SEASONS)

    logger.info("Pulling schedule (includes xG) — this should take 2-5 minutes...")
    schedule = understat.read_schedule()
    schedule = schedule.reset_index()

    logger.info("Raw schedule shape: %s", schedule.shape)
    logger.info("Raw schedule columns: %s", list(schedule.columns))
    return schedule


def reshape_to_panel(schedule: pd.DataFrame) -> pd.DataFrame:
    """
    Convert match-level schedule (one row per match) into a team-match panel
    (two rows per match — one per team perspective).

    Handles Understat's column naming conventions robustly.
    """
    s = schedule.copy()

    # --- Detect column names robustly (Understat naming can vary slightly) ---

    # xG columns
    home_xg_col = next((c for c in s.columns if "home" in c.lower() and "xg" in c.lower()), None)
    away_xg_col = next((c for c in s.columns if "away" in c.lower() and "xg" in c.lower()), None)

    # Goals columns
    home_goals_col = next(
        (c for c in s.columns if "home" in c.lower() and "goal" in c.lower()), None
    )
    away_goals_col = next(
        (c for c in s.columns if "away" in c.lower() and "goal" in c.lower()), None
    )

    # Team columns
    home_team_col = next(
        (c for c in s.columns if "home" in c.lower() and "team" in c.lower()), None
    )
    away_team_col = next(
        (c for c in s.columns if "away" in c.lower() and "team" in c.lower()), None
    )

    # Date column
    date_col = next((c for c in s.columns if "date" in c.lower()), None)

    # Season column
    season_col = next((c for c in s.columns if "season" in c.lower()), None)

    # Gameweek / round column
    gw_col = next(
        (c for c in s.columns if c.lower() in ["week", "round", "gameweek", "gw"]), None
    )

    # Match ID
    id_col = next((c for c in s.columns if "game_id" in c.lower() or c.lower() == "id"), None)

    logger.info("Detected columns — home_team: %s | away_team: %s | home_xg: %s | "
                "away_xg: %s | home_goals: %s | away_goals: %s | date: %s | season: %s",
                home_team_col, away_team_col, home_xg_col, away_xg_col,
                home_goals_col, away_goals_col, date_col, season_col)

    if None in [home_team_col, away_team_col, home_goals_col, away_goals_col, date_col]:
        logger.error(
            "Could not detect essential columns. Available columns: %s", list(s.columns)
        )
        raise ValueError("Missing essential columns — check column detection logic above.")

    if home_xg_col is None or away_xg_col is None:
        logger.warning(
            "xG columns not found! Available columns: %s. "
            "Panel will be built without xG.", list(s.columns)
        )

    # Parse date
    s["_date"] = pd.to_datetime(s[date_col], errors="coerce")

    # Build match ID if not present
    if id_col is None:
        s["_match_id"] = (
            s[season_col].astype(str) + "_"
            + s[home_team_col].astype(str) + "_vs_"
            + s[away_team_col].astype(str)
        )
        id_col = "_match_id"

    # Season label (e.g. "2017-18")
    s["_season_label"] = s[season_col].astype(str).apply(season_label)

    # --- Build home-perspective rows ---
    home = pd.DataFrame({
        "match_id":      s[id_col],
        "season":        s[season_col],
        "season_label":  s["_season_label"],
        "date":          s["_date"],
        "gameweek":      s[gw_col] if gw_col else pd.NA,
        "team":          s[home_team_col].apply(standardize_team),
        "opponent":      s[away_team_col].apply(standardize_team),
        "is_home":       1,
        "goals_for":     pd.to_numeric(s[home_goals_col], errors="coerce"),
        "goals_against": pd.to_numeric(s[away_goals_col], errors="coerce"),
        "xg_for":        pd.to_numeric(s[home_xg_col], errors="coerce") if home_xg_col else pd.NA,
        "xg_against":    pd.to_numeric(s[away_xg_col], errors="coerce") if away_xg_col else pd.NA,
    })

    # --- Build away-perspective rows (mirror) ---
    away = pd.DataFrame({
        "match_id":      s[id_col],
        "season":        s[season_col],
        "season_label":  s["_season_label"],
        "date":          s["_date"],
        "gameweek":      s[gw_col] if gw_col else pd.NA,
        "team":          s[away_team_col].apply(standardize_team),
        "opponent":      s[home_team_col].apply(standardize_team),
        "is_home":       0,
        "goals_for":     pd.to_numeric(s[away_goals_col], errors="coerce"),
        "goals_against": pd.to_numeric(s[home_goals_col], errors="coerce"),
        "xg_for":        pd.to_numeric(s[away_xg_col], errors="coerce") if away_xg_col else pd.NA,
        "xg_against":    pd.to_numeric(s[home_xg_col], errors="coerce") if home_xg_col else pd.NA,
    })

    panel = pd.concat([home, away], ignore_index=True)

    # Drop unplayed matches (no goals yet — current season future fixtures)
    panel = panel.dropna(subset=["goals_for", "goals_against"]).copy()

    # Cast goals to int
    panel["goals_for"]     = panel["goals_for"].astype(int)
    panel["goals_against"] = panel["goals_against"].astype(int)

    # Derived columns
    panel["points"] = panel.apply(
        lambda r: points_from_goals(r["goals_for"], r["goals_against"]), axis=1
    )
    panel["result"] = panel.apply(
        lambda r: result_letter(r["goals_for"], r["goals_against"]), axis=1
    )
    panel["xgd"] = panel["xg_for"] - panel["xg_against"]

    # Also compute goal difference for convenience
    panel["gd"] = panel["goals_for"] - panel["goals_against"]

    # Sort by team then date — essential for rolling window calculations later
    panel = panel.sort_values(["team", "date"]).reset_index(drop=True)

    return panel


# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------

def sanity_check(panel: pd.DataFrame) -> None:
    print("\n" + "=" * 70)
    print("SANITY CHECKS — UNDERSTAT MATCH PANEL")
    print("=" * 70)
    print(f"Total rows (team-matches): {len(panel):,}")
    print(f"  Expected: ~6,080 for 8 complete seasons (380 matches x 2 x 8)")
    print(f"\nRows per season (should be ~760 each, less for current season):")
    print(panel.groupby("season_label").size().to_string())
    print(f"\nUnique teams total: {panel['team'].nunique()}")
    print(f"  Expected: 28-32 (20 per season with promotion/relegation)")
    print(f"\nxG coverage by season (should be ~100% for all completed seasons):")
    xg_cov = panel.groupby("season_label")["xg_for"].apply(
        lambda x: f"{x.notna().mean():.1%}"
    )
    print(xg_cov.to_string())
    print(f"\nDate range: {panel['date'].min().date()} -> {panel['date'].max().date()}")
    print(f"\nxGD distribution (should be roughly centered at 0):")
    print(panel["xgd"].describe().round(3).to_string())
    print(f"\nSample rows:")
    print(panel[["season_label", "date", "team", "opponent", "is_home",
                 "goals_for", "goals_against", "points", "xg_for",
                 "xg_against", "xgd"]].head(10).to_string(index=False))
    print("=" * 70 + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logger.info("Starting Understat data pull.")

    # Step 1: Pull raw schedule from Understat
    schedule = pull_understat_schedule()

    # Save raw schedule for reference
    schedule.to_csv(OUTPUT_DIR / "understat_schedule_raw.csv", index=False)
    logger.info("Saved raw schedule to data/understat_schedule_raw.csv")

    # Step 2: Reshape into team-match panel
    logger.info("Reshaping into team-match panel...")
    panel = reshape_to_panel(schedule)
    logger.info("Panel shape: %s", panel.shape)

    # Step 3: Save outputs
    panel.to_parquet(OUTPUT_DIR / "understat_match_panel.parquet", index=False)
    panel.to_csv(OUTPUT_DIR / "understat_match_panel.csv", index=False)
    logger.info("Saved panel to data/understat_match_panel.parquet and .csv")

    # Step 4: Sanity checks
    sanity_check(panel)

    logger.info("Done. Your match panel is ready at data/understat_match_panel.parquet")
    logger.info("Next step: run 02_pull_manager_data.py")


if __name__ == "__main__":
    main()
