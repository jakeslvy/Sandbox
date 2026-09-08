"""
Generate Filtered Team Weekly FPI Table

This script generates the team_weekly_fpi_filtered.csv file that excludes:
1. Teams that have already been picked (from picks_tracking.csv)
2. Weeks that have already been picked

This filtered table is used as the main input for the Excel analysis.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from picksim.team_weekly_analyzer import create_team_weekly_fpi_table, save_team_weekly_fpi_table
from picksim.optimizer import maximin_survivor_picks, save_optimal_picks, compare_to_naive_approach
import pandas as pd


def generate_filtered_table():
    """
    Generate the filtered team-weekly FPI table.

    Excludes:
    - Teams already picked
    - Weeks already picked
    """
    print("=" * 80)
    print("GENERATING FILTERED TEAM WEEKLY FPI TABLE")
    print("=" * 80)

    # Create the filtered table (excluding picked teams)
    print("\n1. Creating team-weekly FPI table...")
    team_weekly_table = create_team_weekly_fpi_table(
        data_folder="data/input",
        picks_file="data/input/picks_tracking.csv"
    )

    if team_weekly_table is None:
        print("ERROR: Failed to create team-weekly table")
        return False

    print(f"   [OK] Created table with {len(team_weekly_table)} teams x {len(team_weekly_table.columns)} weeks")

    # Now filter out weeks that have already been picked
    print("\n2. Filtering out already-picked weeks...")
    try:
        script_dir = Path(__file__).parent.parent
        picks_path = script_dir / "data" / "input" / "picks_tracking.csv"

        if picks_path.exists():
            picks_df = pd.read_csv(picks_path)

            # Get weeks that have been picked (where Entry_Pick is not empty)
            picked_weeks = picks_df[
                picks_df['Entry_Pick'].notna() & (picks_df['Entry_Pick'] != '')
            ]['Week'].tolist()

            # Convert to week column names
            picked_week_columns = [f"Week {week}" for week in picked_weeks]

            # Remove picked week columns
            columns_to_remove = [col for col in picked_week_columns if col in team_weekly_table.columns]
            if columns_to_remove:
                team_weekly_table = team_weekly_table.drop(columns=columns_to_remove)
                print(f"   [OK] Removed {len(columns_to_remove)} picked week columns: {columns_to_remove}")
            else:
                print(f"   [INFO] No weeks to filter out")

        else:
            print(f"   [WARN] Picks tracking file not found at {picks_path}")
            print(f"   --> Skipping week filtering")

    except Exception as e:
        print(f"   [WARN] Warning: Could not filter weeks: {e}")
        print(f"   --> Continuing with team filtering only")

    # Save the filtered table
    print("\n3. Saving filtered table...")
    output_file = "data/output/team_weekly_fpi_filtered.csv"
    success = save_team_weekly_fpi_table(team_weekly_table, output_file)

    if success:
        print(f"\n{'='*80}")
        print(f"[OK] SUCCESS: Filtered table saved to {output_file}")
        print(f"{'='*80}")
        print(f"\nTable dimensions:")
        print(f"  - Teams: {len(team_weekly_table)}")
        print(f"  - Weeks: {len(team_weekly_table.columns)}")
        print(f"\nYou can now import this CSV into your Excel file.")
        
        # Run optimization for optimal survivor picks
        print(f"\n{'='*80}")
        print(f"4. RUNNING OPTIMAL PICKS OPTIMIZATION")
        print(f"{'='*80}")
        
        optimal_picks, min_fpi = maximin_survivor_picks(team_weekly_table)
        
        if optimal_picks:
            # Save optimal picks
            optimal_output_file = "data/output/optimal_survivor_picks.csv"
            save_success = save_optimal_picks(optimal_picks, optimal_output_file)
            
            if save_success:
                # Show comparison to naive approach
                compare_to_naive_approach(team_weekly_table, optimal_picks)
                
                print(f"\n{'='*80}")
                print(f"[OK] COMPLETE: All files generated successfully!")
                print(f"{'='*80}")
                print(f"\nGenerated files:")
                print(f"  1. {output_file}")
                print(f"  2. {optimal_output_file}")
            else:
                print(f"\n[WARN] Warning: Filtered table saved but optimization output failed")
        else:
            print(f"\n[WARN] Warning: Filtered table saved but optimization failed")
        
        return True
    else:
        print(f"\n{'='*80}")
        print(f"[ERROR] ERROR: Failed to save filtered table")
        print(f"{'='*80}")
        return False


if __name__ == "__main__":
    success = generate_filtered_table()
    sys.exit(0 if success else 1)
