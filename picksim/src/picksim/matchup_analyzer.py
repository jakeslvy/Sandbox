"""
Matchup Analyzer Utility

This module provides functions to analyze weekly NFL matchups using FPI data.
It creates a flat file with FPI differences, picks, and weekly rankings for
survivor pick'em strategy.
"""

import os
import pandas as pd
from pathlib import Path
from typing import Optional, List, Dict, Any
try:
    from .fpi_loader import load_fpi_data
except ImportError:
    # For direct execution
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent))
    from fpi_loader import load_fpi_data


def load_weekly_matchups(data_folder: str = "data/input") -> Optional[pd.DataFrame]:
    """
    Load the weekly matchups data from CSV file.

    Args:
        data_folder: Path to the data folder (relative to picksim root directory)

    Returns:
        DataFrame with weekly matchups, or None if loading fails
    """
    script_dir = Path(__file__).parent.parent.parent
    matchups_file = script_dir / data_folder / "weekly_matchups.csv"
    
    if not matchups_file.exists():
        print(f"Weekly matchups file not found: {matchups_file}")
        return None
    
    try:
        df = pd.read_csv(matchups_file)
        
        # Validate required columns
        required_columns = ['Week', 'TeamA', 'TeamB']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            print(f"Error: Missing required columns: {missing_columns}")
            return None
        
        print(f"Loaded weekly matchups: {len(df)} games")
        return df
        
    except Exception as e:
        print(f"Error loading weekly matchups from {matchups_file}: {e}")
        return None


def get_team_fpi_from_dataframe(team_name: str, fpi_data: pd.DataFrame) -> Optional[float]:
    """
    Get FPI rating for a team from the FPI DataFrame.
    
    Args:
        team_name: Name of the team to look up
        fpi_data: DataFrame containing FPI data
        
    Returns:
        FPI rating as float, or None if team not found
    """
    team_row = fpi_data[fpi_data['Team'].str.strip().str.lower() == team_name.strip().lower()]
    
    if team_row.empty:
        print(f"Warning: Team '{team_name}' not found in FPI data")
        return None
    
    return float(team_row['FPI'].iloc[0])


def analyze_weekly_matchups(data_folder: str = "data/input") -> Optional[pd.DataFrame]:
    """
    Analyze all weekly matchups with FPI data.
    
    Args:
        data_folder: Path to the data folder (relative to picksim root directory)
        
    Returns:
        DataFrame with FPI analysis for all matchups, or None if analysis fails
    """
    # Load FPI data (append /fpi to data_folder path)
    fpi_data = load_fpi_data(data_folder + "/fpi")
    if fpi_data is None:
        print("Failed to load FPI data")
        return None
    
    # Load weekly matchups
    matchups = load_weekly_matchups(data_folder)
    if matchups is None:
        print("Failed to load weekly matchups")
        return None
    
    # Create analysis DataFrame
    analysis_data = []
    
    for _, row in matchups.iterrows():
        week = row['Week']
        team_a = row['TeamA']
        team_b = row['TeamB']
        
        # Get FPI ratings
        team_a_fpi = get_team_fpi_from_dataframe(team_a, fpi_data)
        team_b_fpi = get_team_fpi_from_dataframe(team_b, fpi_data)
        
        if team_a_fpi is None or team_b_fpi is None:
            print(f"Skipping {week}: {team_a} vs {team_b} - missing FPI data")
            continue
        
        # Calculate FPI difference (absolute)
        fpi_diff = abs(team_a_fpi - team_b_fpi)
        
        # Determine FPI pick (team with higher FPI)
        if team_a_fpi > team_b_fpi:
            fpi_pick = team_a
        else:
            fpi_pick = team_b
        
        analysis_data.append({
            'Week': week,
            'TeamA': team_a,
            'TeamA_FPI': team_a_fpi,
            'TeamB': team_b,
            'TeamB_FPI': team_b_fpi,
            'FPI_abs_Diff': fpi_diff,
            'FPI_Pick': fpi_pick
        })
    
    if not analysis_data:
        print("No valid matchups found for analysis")
        return None
    
    # Create DataFrame
    analysis_df = pd.DataFrame(analysis_data)
    
    # Add weekly rankings based on FPI difference (highest difference = rank 1)
    analysis_df['FPI_week_rank'] = analysis_df.groupby('Week')['FPI_abs_Diff'].rank(
        method='dense', ascending=False
    ).astype(int)
    
    # Sort by week and then by rank
    analysis_df = analysis_df.sort_values(['Week', 'FPI_week_rank']).reset_index(drop=True)
    
    print(f"Analyzed {len(analysis_df)} matchups across {analysis_df['Week'].nunique()} weeks")
    return analysis_df


def save_matchup_analysis(analysis_df: pd.DataFrame, output_file: str = "data/output/fpi_matchup_analysis.csv") -> bool:
    """
    Save the matchup analysis to a CSV file.

    Args:
        analysis_df: DataFrame with matchup analysis
        output_file: Path to output file (relative to picksim root directory)

    Returns:
        True if successful, False otherwise
    """
    try:
        script_dir = Path(__file__).parent.parent.parent
        output_path = script_dir / output_file
        
        # Create directory if it doesn't exist
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        analysis_df.to_csv(output_path, index=False)
        print(f"Matchup analysis saved to: {output_path}")
        return True
        
    except Exception as e:
        print(f"Error saving matchup analysis: {e}")
        return False


def get_weekly_picks(week: str, data_folder: str = "data/input") -> Optional[pd.DataFrame]:
    """
    Get FPI picks for a specific week, ranked by confidence.
    
    Args:
        week: Week to analyze (e.g., "Week 1")
        data_folder: Path to the data folder (relative to picksim root directory)
        
    Returns:
        DataFrame with picks for the specified week, or None if not found
    """
    analysis_df = analyze_weekly_matchups(data_folder)
    
    if analysis_df is None:
        return None
    
    week_data = analysis_df[analysis_df['Week'] == week].copy()
    
    if week_data.empty:
        print(f"No data found for {week}")
        return None
    
    return week_data


def get_top_picks_by_week(data_folder: str = "data/input", top_n: int = 5) -> Optional[pd.DataFrame]:
    """
    Get the top N picks for each week based on FPI difference.
    
    Args:
        data_folder: Path to the data folder (relative to picksim root directory)
        top_n: Number of top picks to return per week
        
    Returns:
        DataFrame with top picks for each week, or None if analysis fails
    """
    analysis_df = analyze_weekly_matchups(data_folder)
    
    if analysis_df is None:
        return None
    
    # Get top N picks for each week
    top_picks = analysis_df.groupby('Week').head(top_n).reset_index(drop=True)
    
    return top_picks


if __name__ == "__main__":
    # Test the matchup analyzer
    print("Testing Matchup Analyzer")
    print("=" * 40)
    
    # Analyze all matchups
    analysis = analyze_weekly_matchups()
    
    if analysis is not None:
        print(f"\nAnalysis Preview (first 10 rows):")
        print(analysis.head(10))
        
        # Save to file
        save_matchup_analysis(analysis)
        
        # Test weekly picks
        week1_picks = get_weekly_picks("Week 1")
        if week1_picks is not None:
            print(f"\nWeek 1 Picks:")
            print(week1_picks)
        
        # Test top picks
        top_picks = get_top_picks_by_week(top_n=3)
        if top_picks is not None:
            print(f"\nTop 3 Picks by Week:")
            print(top_picks)
