"""
Team Weekly FPI Analyzer Utility

This module provides functions to create a team-by-week FPI difference table
showing each team's FPI advantage/disadvantage for each week they play.
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, List, Dict, Any
try:
    from .matchup_analyzer import analyze_weekly_matchups
except ImportError:
    # For direct execution
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent))
    from matchup_analyzer import analyze_weekly_matchups


def create_team_weekly_fpi_table(data_folder: str = "data/input", picks_file: str = None) -> Optional[pd.DataFrame]:
    """
    Create a team-by-week table showing FPI differences for each team.

    Each row represents a team, each column represents a week.
    Values show the FPI difference (positive = favored, negative = underdog).
    NULL values indicate the team doesn't play that week (bye week).

    Args:
        data_folder: Path to the data folder (relative to picksim root directory)
        picks_file: Path to picks tracking CSV file (relative to picksim root directory).
                   If provided, teams that have already been picked will be excluded.

    Returns:
        DataFrame with teams as rows and weeks as columns, or None if analysis fails
    """
    # Get the matchup analysis
    analysis = analyze_weekly_matchups(data_folder)
    if analysis is None:
        print("Failed to load matchup analysis")
        return None

    # Get all unique teams from FPI data
    try:
        from .fpi_loader import load_fpi_data
    except ImportError:
        from fpi_loader import load_fpi_data
    fpi_data = load_fpi_data(data_folder + "/fpi")
    if fpi_data is None:
        print("Failed to load FPI data")
        return None

    all_teams = fpi_data['Team'].tolist()

    # Filter out already picked teams if picks_file is provided
    if picks_file:
        try:
            script_dir = Path(__file__).parent.parent.parent
            picks_path = script_dir / picks_file
            
            if picks_path.exists():
                picks_df = pd.read_csv(picks_path)
                # Get teams that have already been picked (non-empty Entry_Pick values)
                picked_teams = picks_df[picks_df['Entry_Pick'].notna() & (picks_df['Entry_Pick'] != '')]['Entry_Pick'].tolist()
                
                # Filter out picked teams from all_teams
                all_teams = [team for team in all_teams if team not in picked_teams]
                print(f"Excluded {len(picked_teams)} already picked teams: {picked_teams}")
                print(f"Remaining teams: {len(all_teams)}")
            else:
                print(f"Warning: Picks file not found at {picks_path}")
        except Exception as e:
            print(f"Warning: Could not read picks file: {e}")
    
    # Create all possible week columns (Week 1 through Week 18)
    all_weeks = [f"Week {i}" for i in range(1, 19)]
    
    # Initialize the pivot table with all teams and all weeks (filled with NaN)
    pivot_data = {}
    for team in all_teams:
        pivot_data[team] = {week: np.nan for week in all_weeks}
    
    # Fill in the actual matchup data
    for _, row in analysis.iterrows():
        week = row['Week']
        team_a = row['TeamA']
        team_b = row['TeamB']
        team_a_fpi = row['TeamA_FPI']
        team_b_fpi = row['TeamB_FPI']
        
        # Calculate FPI difference for each team
        # Team A's FPI difference (positive if favored, negative if underdog)
        team_a_diff = team_a_fpi - team_b_fpi
        
        # Team B's FPI difference (positive if favored, negative if underdog)
        team_b_diff = team_b_fpi - team_a_fpi
        
        # Add data for both teams (only if they're in our filtered list)
        if team_a in pivot_data:
            pivot_data[team_a][week] = team_a_diff
        if team_b in pivot_data:
            pivot_data[team_b][week] = team_b_diff
    
    # Convert to DataFrame
    pivot_table = pd.DataFrame(pivot_data).T
    
    # Ensure all week columns are present and in correct order
    for week in all_weeks:
        if week not in pivot_table.columns:
            pivot_table[week] = np.nan
    
    # Sort columns by week number
    pivot_table = pivot_table[all_weeks]
    
    # Sort teams alphabetically
    pivot_table = pivot_table.sort_index()
    
    print(f"Created team-weekly FPI table: {len(pivot_table)} teams x {len(pivot_table.columns)} weeks")
    return pivot_table


def save_team_weekly_fpi_table(pivot_table: pd.DataFrame, output_file: str = "data/output/team_weekly_fpi.csv") -> bool:
    """
    Save the team-weekly FPI table to a CSV file.

    Args:
        pivot_table: DataFrame with team-weekly FPI data
        output_file: Path to output file (relative to picksim root directory)

    Returns:
        True if successful, False otherwise
    """
    try:
        script_dir = Path(__file__).parent.parent.parent
        output_path = script_dir / output_file
        
        # Create directory if it doesn't exist
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        pivot_table.to_csv(output_path)
        print(f"Team-weekly FPI table saved to: {output_path}")
        return True
        
    except Exception as e:
        print(f"Error saving team-weekly FPI table: {e}")
        return False


def get_team_weekly_fpi(team_name: str, data_folder: str = "data/input", picks_file: str = None) -> Optional[pd.Series]:
    """
    Get the weekly FPI differences for a specific team.
    
    Args:
        team_name: Name of the team to look up
        data_folder: Path to the data folder (relative to picksim root directory)
        picks_file: Path to picks tracking CSV file (relative to picksim directory)
        
    Returns:
        Series with weekly FPI differences for the team, or None if not found
    """
    pivot_table = create_team_weekly_fpi_table(data_folder, picks_file)
    
    if pivot_table is None:
        return None
    
    # Find the team (case-insensitive)
    team_row = pivot_table[pivot_table.index.str.lower() == team_name.lower()]
    
    if team_row.empty:
        print(f"Team '{team_name}' not found")
        return None
    
    return team_row.iloc[0]


if __name__ == "__main__":
    # Test the team weekly analyzer
    print("Testing Team Weekly FPI Analyzer")
    print("=" * 40)
    
    # Create team-weekly table
    team_weekly_table = create_team_weekly_fpi_table()
    
    if team_weekly_table is not None:
        print(f"\nTable Preview (first 5 teams, first 5 weeks):")
        print(team_weekly_table.iloc[:5, :5])
        
        # Save to file
        save_team_weekly_fpi_table(team_weekly_table)
        
        # Test specific team lookup
        eagles_weekly = get_team_weekly_fpi("Philadelphia Eagles")
        if eagles_weekly is not None:
            print(f"\nPhiladelphia Eagles Weekly FPI Differences:")
            print(eagles_weekly.dropna())
