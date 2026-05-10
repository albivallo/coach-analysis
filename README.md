# coach-analysis

Data collection pipeline for analyzing the performance impact of mid-season managerial changes in the Premier League (2017-18 through 2024-25).

## Scripts

### `01_UnderStatData.py`

Pulls Premier League match data from [Understat](https://understat.com) for 8 seasons using the `soccerdata` Python package. Produces a clean panel dataset with one row per team per match.

**Output columns:**

| Column | Description |
|--------|-------------|
| `match_id` | Unique match identifier |
| `season` | Season code (e.g. `1718`) |
| `season_label` | Human-readable season (e.g. `2017-18`) |
| `date` | Match date |
| `team` / `opponent` | Standardized club names |
| `is_home` | 1 if home, 0 if away |
| `goals_for` / `goals_against` | Match goals |
| `points` | Points earned (3/1/0) |
| `result` | W / D / L |
| `xg_for` / `xg_against` | Expected goals for/against |
| `xgd` | Expected goal difference (`xg_for − xg_against`) |
| `gd` | Goal difference |

### `02_pull_manager_changes.py`

Scrapes the Transfermarkt "Changes in Coach" pages for the Premier League across 8 seasons, producing a structured dataset of every managerial change event.

**Output columns:**

| Column | Description |
|--------|-------------|
| `season_label` | Season the change occurred in |
| `change_type` | `end_of_season` or `during_season` |
| `club` | Club name |
| `out_manager` / `out_role` | Departing manager and role |
| `out_matchday` / `out_rank` / `out_ppg` | Performance context at departure |
| `leaving_date` | Date of departure |
| `days_in_charge` | Total days as manager |
| `in_manager` / `in_role` | Incoming manager and role |
| `in_rank` / `in_ppg` | Successor's subsequent performance |
| `reason` | *(manual)* `sacked` / `mutual_consent` / `voluntary` |
| `include` | *(manual)* `1` to include in analysis, `0` to exclude |
| `ambiguity_flag` | *(manual)* `1` if departure circumstances are ambiguous |
| `notes` | *(manual)* Free text |

## Data Sources

| Source | URL | Used for |
|--------|-----|----------|
| Understat | [understat.com](https://understat.com) | Match-level xG and results data |
| Transfermarkt | [transfermarkt.com](https://transfermarkt.com) | Managerial change dates and context |
