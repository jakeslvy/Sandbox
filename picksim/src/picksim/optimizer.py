"""
Survivor Pool Pick Optimizer

This module provides optimization algorithms for selecting optimal survivor pool picks
using the maximin approach to maximize the minimum weekly FPI value.
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional


def maximin_survivor_picks(fpi_table: pd.DataFrame) -> Tuple[Optional[Dict[str, Tuple[str, float]]], float]:
    """
    Find optimal survivor picks using maximin optimization.
    
    The maximin approach maximizes the minimum weekly FPI value across all picks,
    ensuring the "worst" pick is as good as possible. This is a greedy algorithm
    that processes weeks in order of constraint (fewest options first).
    
    Args:
        fpi_table: DataFrame with teams as rows and weeks as columns.
                  Values are FPI differences (positive = favored).
                  NaN values indicate bye weeks.
    
    Returns:
        Tuple of (picks_dict, min_fpi_value) where:
        - picks_dict: {week: (team, fpi_value), ...}
        - min_fpi_value: The minimum FPI value across all picks
        Returns (None, -inf) if optimization fails
    """
    if fpi_table is None or fpi_table.empty:
        print("ERROR: Empty FPI table provided")
        return None, float('-inf')
    
    teams = fpi_table.index.tolist()
    weeks = fpi_table.columns.tolist()
    
    print(f"\nOptimizing picks for {len(teams)} teams across {len(weeks)} weeks...")
    print("Using maximin approach (maximize the minimum weekly FPI)")
    
    # Track used teams and picks
    used_teams = set()
    picks = {}
    weekly_values = []
    
    # Calculate constraints for each week (how many valid options)
    week_constraints = {}
    for week in weeks:
        valid_values = fpi_table[week].dropna()
        week_constraints[week] = len(valid_values)
    
    # Process most constrained weeks first (fewest options)
    sorted_weeks = sorted(weeks, key=lambda w: week_constraints[w])
    
    print("\nWeek processing order (most constrained first):")
    for week in sorted_weeks:
        print(f"  {week}: {week_constraints[week]} available teams")
    
    print("\nOptimization progress:")
    # Greedy optimization: for each week, pick the team that maximizes the current minimum
    for week in sorted_weeks:
        # Get available teams for this week (not used and not on bye)
        available_data = fpi_table[week].dropna()
        available_teams = [team for team in available_data.index if team not in used_teams]
        
        if not available_teams:
            print(f"\nERROR: No available teams for {week}!")
            return None, float('-inf')
        
        # Among available teams, pick the one that maximizes the current minimum
        best_team = None
        best_value = float('-inf')
        
        for team in available_teams:
            fpi_value = fpi_table.loc[team, week]
            
            # Calculate what the minimum would be if we pick this team
            temp_values = weekly_values + [fpi_value]
            temp_min = min(temp_values)
            
            # Pick the team that gives us the best minimum
            if temp_min > best_value:
                best_value = temp_min
                best_team = team
        
        # Make the pick
        fpi_value = fpi_table.loc[best_team, week]
        picks[week] = (best_team, fpi_value)
        used_teams.add(best_team)
        weekly_values.append(fpi_value)
        
        print(f"  {week}: {best_team:30} (FPI: {fpi_value:6.1f})")
    
    final_min = min(weekly_values)
    print(f"\n[OK] Optimization complete!")
    print(f"  Minimum weekly FPI: {final_min:.1f}")
    print(f"  Maximum weekly FPI: {max(weekly_values):.1f}")
    print(f"  Average weekly FPI: {np.mean(weekly_values):.1f}")
    
    return picks, final_min


def compare_to_naive_approach(fpi_table: pd.DataFrame, optimal_picks: Dict[str, Tuple[str, float]]) -> None:
    """
    Compare optimal picks to a naive greedy approach (always pick highest available FPI).
    
    Args:
        fpi_table: The filtered team-weekly FPI table
        optimal_picks: The optimal picks from maximin optimization
    """
    print("\n" + "="*80)
    print("COMPARISON: OPTIMAL vs NAIVE GREEDY APPROACH")
    print("="*80)
    
    # Naive approach: just pick the best available team each week in order
    naive_picks = {}
    naive_used = set()
    naive_values = []
    
    for week in fpi_table.columns:
        available_data = fpi_table[week].dropna()
        available_teams = [team for team in available_data.index if team not in naive_used]
        
        if available_teams:
            # Pick team with highest FPI this week
            best_naive_team = available_data[available_teams].idxmax()
            best_naive_fpi = available_data[best_naive_team]
            
            naive_picks[week] = (best_naive_team, best_naive_fpi)
            naive_used.add(best_naive_team)
            naive_values.append(best_naive_fpi)
    
    optimal_values = [fpi for _, fpi in optimal_picks.values()]
    
    print(f"\nNaive Greedy Approach:")
    print(f"  Min FPI:  {min(naive_values):6.1f}")
    print(f"  Max FPI:  {max(naive_values):6.1f}")
    print(f"  Avg FPI:  {np.mean(naive_values):6.1f}")
    
    print(f"\nOptimal Maximin Approach:")
    print(f"  Min FPI:  {min(optimal_values):6.1f}")
    print(f"  Max FPI:  {max(optimal_values):6.1f}")
    print(f"  Avg FPI:  {np.mean(optimal_values):6.1f}")
    
    print(f"\nImprovement in minimum FPI: +{min(optimal_values) - min(naive_values):.1f}")
    print("="*80)


def save_optimal_picks(picks: Dict[str, Tuple[str, float]], output_file: str) -> bool:
    """
    Save optimal picks to a CSV file.
    
    Args:
        picks: Dictionary of {week: (team, fpi_value)}
        output_file: Path to output file (relative to picksim root)
    
    Returns:
        True if successful, False otherwise
    """
    if not picks:
        print("ERROR: No picks to save")
        return False
    
    try:
        from pathlib import Path
        
        # Create summary data
        summary_data = []
        for week, (team, fpi) in picks.items():
            summary_data.append({
                'Week': week,
                'Team': team,
                'FPI': fpi
            })
        
        # Convert to DataFrame
        df = pd.DataFrame(summary_data)
        
        # Sort by week number
        df['week_num'] = df['Week'].str.extract(r'(\d+)').astype(int)
        df = df.sort_values('week_num').drop(columns=['week_num'])
        
        # Save to CSV
        script_dir = Path(__file__).parent.parent.parent
        output_path = script_dir / output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        df.to_csv(output_path, index=False)
        print(f"\n[OK] Optimal picks saved to: {output_file}")
        return True
        
    except Exception as e:
        print(f"\nERROR: Failed to save optimal picks: {e}")
        return False


if __name__ == "__main__":
    # Test the optimizer
    print("Testing Survivor Pool Optimizer")
    print("=" * 40)
    
    # This would normally be called from generate_filtered_table.py
    # with actual FPI data
    print("\nThis module should be imported and used by generate_filtered_table.py")

