# Picksim - NFL Survivor Pool Optimizer

An NFL survivor pool strategy optimizer using ESPN's Football Power Index (FPI) data.

## Overview

Picksim helps optimize NFL survivor pick'em selections by analyzing team strength (FPI ratings), weekly matchups, and remaining team pools across multiple entries. Designed to handle large survivor pools (2000+ entries).

## Features

- **FPI Data Management**: Automatically loads the latest weekly FPI data
- **Matchup Analysis**: Analyzes weekly matchups and ranks picks by FPI confidence
- **Entry Rankings**: Ranks all pool entries by quality of remaining team pool
- **Filtered Tables**: Generates tables excluding already-picked teams and weeks
- **Excel Integration**: Exports filtered data for use in Excel analysis

## Project Structure

```
picksim/
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
├── setup.py                           # Package setup
├── team_weekly_fpi.xlsx              # Personal Excel working file
├── src/
│   └── picksim/                      # Main package
│       ├── fpi_loader.py             # Load FPI data
│       ├── matchup_analyzer.py       # Analyze matchups
│       ├── team_weekly_analyzer.py   # Team-week analysis
│       └── optimizer.py              # Maximin pick optimization
├── scripts/                           # Weekly workflow scripts
│   ├── generate_filtered_table.py    # Create filtered FPI table
│   └── analyze_entries.py            # Rank entries by pool quality
├── notebooks/                         # Jupyter notebooks
│   └── fpi_analysis.ipynb            # Interactive analysis
└── data/
    ├── input/                         # Source data (manually updated)
    │   ├── fpi/                       # Weekly FPI snapshots
    │   │   ├── week0_fpi.csv
    │   │   └── ...
    │   ├── weekly_matchups.csv        # NFL schedule
    │   ├── abbreviation_mapping.csv   # Team name mappings
    │   ├── all_picks.csv              # All entry picks
    │   └── picks_tracking.csv         # Track your picks
    └── output/                        # Generated outputs
        ├── team_weekly_fpi_filtered.csv
        ├── optimal_survivor_picks.csv
        ├── entry_remaining_teams_analysis.csv
        └── reports/                   # PDF reports
```

## Installation

### Option 1: Basic Setup (recommended)
```bash
cd picksim
pip install -r requirements.txt
```

### Option 2: Development Install
```bash
cd picksim
pip install -e .
```

## Weekly Workflow

### 1. Update FPI Data
Manually download the latest FPI data from ESPN and save as `data/input/fpi/weekX_fpi.csv`

Expected CSV format:
```
Team,FPI
Kansas City Chiefs,6.1
Detroit Lions,5.7
...
```

### 2. Generate Filtered Table & Optimal Picks
This creates the filtered table for your Excel analysis AND generates optimal survivor picks:

```bash
python scripts/generate_filtered_table.py
```

Outputs:
1. `data/output/team_weekly_fpi_filtered.csv`
   - Excludes teams you've already picked
   - Excludes weeks you've already picked
   - Use this as input to `team_weekly_fpi.xlsx`

2. `data/output/optimal_survivor_picks.csv`
   - Optimal picks using maximin optimization
   - Maximizes the minimum weekly FPI value
   - Ensures your "worst" pick is as good as possible

### 3. Analyze Entries
Rank all pool entries by remaining team quality:

```bash
python scripts/analyze_entries.py
```

**Before running:** Update the `CURRENT_WEEK` variable in the script!

Output: `data/output/entry_remaining_teams_analysis.csv`
- Shows your rank/percentile
- Displays top/bottom 20 entries
- Analyzes top N teams (where N = weeks remaining)

## Input Data Files

### Required Files

**`data/input/fpi/weekX_fpi.csv`** - Weekly FPI data
```csv
Team,FPI
Kansas City Chiefs,6.1
Detroit Lions,5.7
```

**`data/input/weekly_matchups.csv`** - NFL schedule
```csv
Week,TeamA,TeamB
Week 1,Kansas City Chiefs,Baltimore Ravens
Week 1,Philadelphia Eagles,Green Bay Packers
```

**`data/input/picks_tracking.csv`** - Your picks tracker
```csv
Week,Entry_Pick
1,Kansas City Chiefs
2,Detroit Lions
```

**`data/input/abbreviation_mapping.csv`** - Team abbreviations
```csv
team_abbreviation,team_name
KC,Kansas City Chiefs
DET,Detroit Lions
```

**`data/input/all_picks.csv`** - All pool entry picks
```csv
Name,Week 1,Week 2,Week 3,...
John Doe #1,KC,DET,PHI,...
Jane Smith #2,BUF,GB,SF,...
```

## Output Files

**`data/output/team_weekly_fpi_filtered.csv`**
- Filtered team-by-week FPI differences
- Excludes picked teams and weeks
- Import into Excel for analysis

**`data/output/optimal_survivor_picks.csv`**
- Optimal survivor picks using maximin optimization
- Shows best team to pick each remaining week
- Maximizes minimum weekly FPI value

**`data/output/entry_remaining_teams_analysis.csv`**
- Rankings of all pool entries
- Statistics on remaining team pools
- Percentile rankings

**`data/output/fpi_matchup_analysis.csv`**
- Weekly matchup analysis
- FPI picks ranked by confidence

## Usage Examples

### Using the Package in Python
```python
from picksim.fpi_loader import load_fpi_data, get_fpi_rankings
from picksim.team_weekly_analyzer import create_team_weekly_fpi_table

# Load latest FPI data
fpi_data = load_fpi_data()

# Get team rankings
rankings = get_fpi_rankings()
print(rankings.head(10))

# Create filtered table
filtered_table = create_team_weekly_fpi_table(
    data_folder="data/input",
    picks_file="data/input/picks_tracking.csv"
)
```

### Using Jupyter Notebook
```bash
cd picksim
jupyter notebook notebooks/fpi_analysis.ipynb
```

The notebook includes:
- Interactive visualizations
- Maximin optimization algorithm
- Entry comparison tools
- PDF report generation

## Future Enhancements

- [ ] Automate FPI data fetching from ESPN
- [ ] Web dashboard for real-time analysis
- [ ] Historical performance tracking
- [ ] Machine learning predictions
- [ ] Email alerts for weekly picks

## License

Personal project - not licensed for public distribution

## Author

Jake Selvey
