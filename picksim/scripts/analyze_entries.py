"""
Analyze Entry Remaining Teams

This script analyzes all survivor pool entries and ranks them by the quality
of their remaining team pool. It generates:
1. CSV with entry rankings and statistics
2. Optional PDF reports for specific entries

The analysis considers only the top N teams (where N = weeks remaining) for each entry.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from picksim.fpi_loader import load_fpi_data


def analyze_entries(current_week: int, total_weeks: int = 18):
    """
    Analyze all entries and rank by remaining team pool quality.

    Args:
        current_week: The week just completed (e.g., 5 means Week 5 just finished)
        total_weeks: Total weeks in season (default: 18)
    """
    print("=" * 80)
    print("SURVIVOR POOL - REMAINING TEAMS ANALYSIS")
    print("=" * 80)

    weeks_remaining = total_weeks - current_week
    print(f"\nCurrent Status: Week {current_week} completed")
    print(f"Weeks Remaining: {weeks_remaining} (Week {current_week + 1} through Week {total_weeks})")
    print(f"Analyzing TOP {weeks_remaining} teams for each entry\n")

    # Get paths
    script_dir = Path(__file__).parent.parent
    abbrev_file = script_dir / "data" / "input" / "abbreviation_mapping.csv"
    picks_file = script_dir / "data" / "input" / "all_picks.csv"
    output_file = script_dir / "data" / "output" / "entry_remaining_teams_analysis.csv"

    # 1. Load FPI data
    print("1. Loading FPI data...")
    fpi_data = load_fpi_data()
    if fpi_data is None:
        print("ERROR: Failed to load FPI data!")
        return False

    print(f"   [OK] Loaded FPI data for {len(fpi_data)} teams")

    # Create FPI lookup dictionary
    fpi_dict = dict(zip(fpi_data['Team'], fpi_data['FPI']))
    print(f"   [OK] Created FPI lookup dictionary")

    # 2. Load abbreviation mapping
    print("\n2. Loading team abbreviation mapping...")
    try:
        abbrev_df = pd.read_csv(abbrev_file)
        abbrev_to_name = dict(zip(abbrev_df['team_abbreviation'], abbrev_df['team_name']))
        print(f"   [OK] Loaded {len(abbrev_to_name)} team mappings")
    except Exception as e:
        print(f"ERROR: Failed to load abbreviation mapping: {e}")
        return False

    # 3. Load all picks
    print("\n3. Loading all picks data...")
    try:
        picks_df = pd.read_csv(picks_file, encoding='latin-1')
        print(f"   [OK] Loaded picks for {len(picks_df)} entries")
    except Exception as e:
        print(f"ERROR: Failed to load picks data: {e}")
        return False

    # 4. Get all NFL teams
    all_nfl_teams = set(abbrev_df['team_name'].tolist())
    print(f"\n4. NFL teams: {len(all_nfl_teams)} total teams")

    # 5. Process each entry
    print("\n5. Processing each entry's picks...")
    print("-" * 80)

    week_columns = [col for col in picks_df.columns if col.startswith('Week ')]
    results = []

    for idx, row in picks_df.iterrows():
        entry_name = row['Name']

        # Get all picks for this entry (ignore empty and 'X')
        picked_abbrevs = []
        for week_col in week_columns:
            pick = row[week_col]
            if pd.notna(pick) and pick != '' and pick != 'X':
                picked_abbrevs.append(pick.lower())

        # Convert abbreviations to full team names
        picked_teams = []
        for abbrev in picked_abbrevs:
            if abbrev in abbrev_to_name:
                picked_teams.append(abbrev_to_name[abbrev])
            else:
                print(f"   WARNING: Unknown abbreviation '{abbrev}' for {entry_name}")

        # Calculate remaining teams
        remaining_teams = all_nfl_teams - set(picked_teams)

        # Get FPI values for remaining teams (use dictionary lookup)
        remaining_fpis = []
        for team in remaining_teams:
            fpi = fpi_dict.get(team)
            if fpi is not None:
                remaining_fpis.append(fpi)

        # Sort FPIs descending and take only top N teams (where N = weeks remaining)
        remaining_fpis_sorted = sorted(remaining_fpis, reverse=True)
        top_n_fpis = remaining_fpis_sorted[:weeks_remaining]

        # Calculate metrics on TOP N teams only
        if top_n_fpis:
            avg_fpi = np.mean(top_n_fpis)
            max_fpi = np.max(top_n_fpis)
            min_fpi = np.min(top_n_fpis)
            median_fpi = np.median(top_n_fpis)
            std_fpi = np.std(top_n_fpis)
        else:
            avg_fpi = max_fpi = min_fpi = median_fpi = std_fpi = 0

        results.append({
            'Entry_Name': entry_name,
            'Teams_Picked': len(picked_teams),
            'Teams_Remaining': len(remaining_teams),
            'Avg_FPI_Remaining': avg_fpi,
            'Max_FPI_Remaining': max_fpi,
            'Min_FPI_Remaining': min_fpi,
            'Median_FPI_Remaining': median_fpi,
            'Std_FPI_Remaining': std_fpi,
            'Picked_Teams': ', '.join(sorted(picked_teams))
        })

    # Create results DataFrame
    results_df = pd.DataFrame(results)

    # Sort by average FPI (descending - best first)
    results_df = results_df.sort_values('Avg_FPI_Remaining', ascending=False)
    results_df['Rank'] = range(1, len(results_df) + 1)

    # Calculate percentile (1% = best, 100% = worst)
    results_df['Percentile'] = (results_df['Rank'] / len(results_df) * 100).round(1)

    # Reorder columns
    results_df = results_df[[
        'Rank', 'Percentile', 'Entry_Name', 'Teams_Picked', 'Teams_Remaining',
        'Avg_FPI_Remaining', 'Max_FPI_Remaining', 'Min_FPI_Remaining',
        'Median_FPI_Remaining', 'Std_FPI_Remaining', 'Picked_Teams'
    ]]

    print(f"   [OK] Processed {len(results_df)} entries")

    # 6. Display summary statistics
    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)
    print(f"Weeks remaining: {weeks_remaining}")
    print(f"Average teams picked per entry: {results_df['Teams_Picked'].mean():.1f}")
    print(f"Average teams remaining per entry: {results_df['Teams_Remaining'].mean():.1f}")
    print(f"\nAnalyzing TOP {weeks_remaining} teams for each entry:")
    print(f"  Average FPI of top {weeks_remaining} teams: {results_df['Avg_FPI_Remaining'].mean():.2f}")
    print(f"  Best average FPI (top {weeks_remaining}): {results_df['Avg_FPI_Remaining'].max():.2f}")
    print(f"  Worst average FPI (top {weeks_remaining}): {results_df['Avg_FPI_Remaining'].min():.2f}")

    # 7. Display top 20 entries
    print("\n" + "=" * 80)
    print(f"TOP 20 ENTRIES - BEST REMAINING TEAM POOLS (Top {weeks_remaining} teams by Avg FPI)")
    print("=" * 80)
    print(f"{'Rank':<6} {'Pct':<7} {'Entry Name':<35} {'Picked':<8} {'Remain':<8} {'Avg FPI':<10} {'Max FPI':<10} {'Min FPI':<10}")
    print("-" * 80)

    for _, row in results_df.head(20).iterrows():
        print(f"{row['Rank']:<6} {row['Percentile']:<6.1f}% {row['Entry_Name']:<35} {row['Teams_Picked']:<8} "
              f"{row['Teams_Remaining']:<8} {row['Avg_FPI_Remaining']:<10.2f} "
              f"{row['Max_FPI_Remaining']:<10.2f} {row['Min_FPI_Remaining']:<10.2f}")

    # 8. Display bottom 20 entries
    print("\n" + "=" * 80)
    print(f"BOTTOM 20 ENTRIES - WORST REMAINING TEAM POOLS (Top {weeks_remaining} teams by Avg FPI)")
    print("=" * 80)
    print(f"{'Rank':<6} {'Pct':<7} {'Entry Name':<35} {'Picked':<8} {'Remain':<8} {'Avg FPI':<10} {'Max FPI':<10} {'Min FPI':<10}")
    print("-" * 80)

    for _, row in results_df.tail(20).iterrows():
        print(f"{row['Rank']:<6} {row['Percentile']:<6.1f}% {row['Entry_Name']:<35} {row['Teams_Picked']:<8} "
              f"{row['Teams_Remaining']:<8} {row['Avg_FPI_Remaining']:<10.2f} "
              f"{row['Max_FPI_Remaining']:<10.2f} {row['Min_FPI_Remaining']:<10.2f}")

    # 9. Save to CSV
    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        results_df.to_csv(output_file, index=False)
        print(f"\n{'=' * 80}")
        print(f"[OK] SUCCESS: Full results saved to {output_file}")
        print(f"{'=' * 80}")
        return True
    except Exception as e:
        print(f"\n{'=' * 80}")
        print(f"[ERROR] ERROR: Failed to save results: {e}")
        print(f"{'=' * 80}")
        return False


if __name__ == "__main__":
    # You can change this to match your current week
    # For example, if you just finished Week 5, set current_week = 5
    CURRENT_WEEK = 6  # <-- UPDATE THIS EACH WEEK

    success = analyze_entries(current_week=CURRENT_WEEK)
    sys.exit(0 if success else 1)
