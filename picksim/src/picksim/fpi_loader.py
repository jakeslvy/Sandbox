"""
FPI Data Loader Utility

This module provides functions to load the latest FPI (Football Power Index) data
from the data folder. It automatically finds the most recent FPI file based on
naming convention (e.g., week0_fpi.csv, week1_fpi.csv, etc.).
"""

import os
import pandas as pd
import glob
from pathlib import Path
from typing import Optional, Dict, Any


def find_latest_fpi_file(data_folder: str = "data/input/fpi") -> Optional[str]:
    """
    Find the latest FPI data file in the specified folder.

    Looks for files matching pattern: week*_fpi.csv
    Returns the file with the highest week number.

    Args:
        data_folder: Path to the data folder (relative to picksim root directory)

    Returns:
        Path to the latest FPI file, or None if no files found
    """
    # Get the directory containing this script (src/picksim/)
    # Go up two levels to reach picksim root
    script_dir = Path(__file__).parent.parent.parent
    data_path = script_dir / data_folder
    
    if not data_path.exists():
        print(f"Data folder not found: {data_path}")
        return None
    
    # Find all FPI files matching the pattern
    fpi_pattern = str(data_path / "week*_fpi.csv")
    fpi_files = glob.glob(fpi_pattern)
    
    if not fpi_files:
        print(f"No FPI files found matching pattern: {fpi_pattern}")
        return None
    
    # Extract week numbers and find the latest
    latest_file = None
    latest_week = -1
    
    for file_path in fpi_files:
        filename = os.path.basename(file_path)
        # Extract week number from filename (e.g., "week0" -> 0)
        try:
            week_str = filename.split('_')[0].replace('week', '')
            week_num = int(week_str)
            
            if week_num > latest_week:
                latest_week = week_num
                latest_file = file_path
        except (ValueError, IndexError):
            print(f"Warning: Could not parse week number from {filename}")
            continue
    
    if latest_file:
        print(f"Found latest FPI file: {os.path.basename(latest_file)} (Week {latest_week})")
    
    return latest_file


def load_fpi_data(data_folder: str = "data/input/fpi") -> Optional[pd.DataFrame]:
    """
    Load the latest FPI data into a pandas DataFrame.
    
    Args:
        data_folder: Path to the data folder (relative to picksim directory)
        
    Returns:
        DataFrame with FPI data (Team, FPI columns), or None if loading fails
    """
    fpi_file = find_latest_fpi_file(data_folder)
    
    if not fpi_file:
        return None
    
    try:
        df = pd.read_csv(fpi_file)
        
        # Validate required columns
        required_columns = ['Team', 'FPI']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            print(f"Error: Missing required columns: {missing_columns}")
            return None
        
        # Clean up the data
        df = df.dropna(subset=['Team', 'FPI'])  # Remove rows with missing data
        df['FPI'] = pd.to_numeric(df['FPI'], errors='coerce')  # Ensure FPI is numeric
        df = df.dropna(subset=['FPI'])  # Remove rows where FPI conversion failed
        
        print(f"Loaded FPI data: {len(df)} teams")
        return df
        
    except Exception as e:
        print(f"Error loading FPI data from {fpi_file}: {e}")
        return None


def get_team_fpi(team_name: str, data_folder: str = "data/input/fpi") -> Optional[float]:
    """
    Get the FPI rating for a specific team.
    
    Args:
        team_name: Name of the team to look up
        data_folder: Path to the data folder (relative to picksim directory)
        
    Returns:
        FPI rating as float, or None if team not found
    """
    df = load_fpi_data(data_folder)
    
    if df is None:
        return None
    
    team_row = df[df['Team'].str.strip().str.lower() == team_name.strip().lower()]
    
    if team_row.empty:
        print(f"Team '{team_name}' not found in FPI data")
        return None
    
    return float(team_row['FPI'].iloc[0])


def get_fpi_rankings(data_folder: str = "data/input/fpi") -> Optional[pd.DataFrame]:
    """
    Get FPI data sorted by rating (highest to lowest).
    
    Args:
        data_folder: Path to the data folder (relative to picksim directory)
        
    Returns:
        DataFrame with teams sorted by FPI rating, or None if loading fails
    """
    df = load_fpi_data(data_folder)
    
    if df is None:
        return None
    
    # Sort by FPI (descending) and add rank
    df_sorted = df.sort_values('FPI', ascending=False).reset_index(drop=True)
    df_sorted['Rank'] = range(1, len(df_sorted) + 1)
    
    return df_sorted


if __name__ == "__main__":
    # Test the utility functions
    print("Testing FPI Loader Utility")
    print("=" * 40)
    
    # Test finding latest file
    latest_file = find_latest_fpi_file()
    print(f"Latest FPI file: {latest_file}")
    
    # Test loading data
    fpi_data = load_fpi_data()
    if fpi_data is not None:
        print(f"\nFPI Data Preview:")
        print(fpi_data.head(10))
        
        # Test getting specific team FPI
        test_team = "Philadelphia Eagles"
        team_fpi = get_team_fpi(test_team)
        print(f"\n{test_team} FPI: {team_fpi}")
        
        # Test rankings
        rankings = get_fpi_rankings()
        if rankings is not None:
            print(f"\nTop 5 Teams by FPI:")
            print(rankings.head())
