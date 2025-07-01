import pandas as pd
import numpy as np
from duckdb import query as qr
from .data_fetchers import fetch_loop_habits_data, get_sheet_data, fetch_daily_steps
from .common import time_from_midnight

def prepare_habit_data(raw_scores):
    """
    Clean and transform raw habit tracking data from Loop Habits.
    
    Parameters:
    raw_scores (pd.DataFrame): Raw data from Loop Habits export
    
    Returns:
    pd.DataFrame: Cleaned and transformed habit data with derived metrics
    """
    # Make copy to avoid modifying original
    df = raw_scores.copy()
    
    # Make all column names lowercase
    df.columns = df.columns.str.lower()
    
    # Rename columns as needed
    df = df.rename(columns = {
        'date': 'habit_date',
        'video games': 'video_games'
    })
    
    # Keep only specified columns
    df = df[['habit_date', 'meditate', 'exercise', 'morning', 'day', 
             'evening', 'drinks', 'candy', 'pen', 'video_games']]
    
    # Convert 2 to 1 for binary columns
    df['meditate'] = df['meditate'].replace(2, 1)
    df['exercise'] = df['exercise'].replace(2, 1)
    
    # Convert -1 to 0 for all columns
    columns_to_fix = ['drinks', 'candy', 'pen', 'morning', 'day', 'evening', 
                      'meditate', 'exercise', 'video_games']
    for col in columns_to_fix:
        df[col] = df[col].replace(-1, 0)
    
    # Divide numerical columns by 1000 and round
    numerical_cols = ['morning', 'day', 'evening', 'drinks', 'candy', 'pen']
    for col in numerical_cols:
        df[col] = round(df[col]/1000, 1)
    df['video_games'] = round(df['video_games']/1000, 2)
    
    # Add date-based columns
    df['habit_date'] = pd.to_datetime(df['habit_date'])
    df['day_of_week'] = df['habit_date'].dt.dayofweek
    df['day_label'] = df['habit_date'].dt.day_name()
    df['week_number'] = df['habit_date'].dt.isocalendar().week
    df['month'] = df['habit_date'].dt.month
    
    # Create weekend flag
    df['weekend'] = df['day_label'].isin(['Saturday', 'Sunday']).astype(int)
    
    # Create activity flags
    for col in ['drinks', 'candy', 'pen', 'video_games']:
        df[f'{col}_flag'] = (df[col] > 0).astype(int)
    
    # Calculate total score
    df['total_score'] = df[['morning', 'day', 'evening']].sum(axis=1)
    
    # Set total score to null if any component is 0
    zero_mask = (df[['morning', 'day', 'evening']] == 0).any(axis=1)
    df.loc[zero_mask, 'total_score'] = None
    
    # Set 0 values to null for component scores
    for col in ['morning', 'day', 'evening']:
        df.loc[df[col] == 0, col] = None
    
    # Create interpolated versions for charting
    df['morning_chart'] = df['morning'].interpolate()
    df['day_chart'] = df['day'].interpolate()
    df['evening_chart'] = df['evening'].interpolate()
    
    # Create lag columns
    lag_columns = ['total_score', 'morning', 'day', 'evening', 'meditate', 
                   'exercise', 'drinks', 'candy', 'pen', 'drinks_flag', 
                   'candy_flag', 'pen_flag', 'video_games']
    for col in lag_columns:
        df[f'{col}_lag1'] = df[col].shift(1)
    
    # Calculate chart scores
    df['total_score_chart'] = df[['morning_chart', 'day_chart', 'evening_chart']].sum(axis=1)
    df['total_score_chart_r3'] = df['total_score_chart'].rolling(window=3, min_periods=1).mean()
    
    return df

def get_sleep_data(sheet_url="https://docs.google.com/spreadsheets/d/169r9jn66M-ij0Pj6eS7wV6q5jhE2vWUz5vhYCrcBLBA/edit?usp=sharing"):
    """
    Fetch and prepare sleep data from Google Sheets.
    
    Parameters:
    sheet_url (str): URL of the Google Sheet containing sleep data (default: Jake's sleep tracking sheet)
    
    Returns:
    pandas.DataFrame: Cleaned and transformed sleep data
    """
    raw_sleep = get_sheet_data(sheet_url)
    return prepare_sleep_data(raw_sleep)

def prepare_sleep_data(raw_sleep):
    """
    Clean and transform raw sleep tracking data from Google Sheets.
    
    Parameters:
    raw_sleep (pd.DataFrame): Raw data from sleep tracking sheet
    
    Returns:
    pd.DataFrame: Cleaned and transformed sleep data
    """
    # Make copy to avoid modifying original
    df = raw_sleep.copy()
    
    # Remove unnamed columns
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    
    # Convert date columns
    df['day_of_date'] = pd.to_datetime(df['day_of_date'])
    df['next_day_date'] = pd.to_datetime(df['next_day_date'])
    df['sleep_start_time'] = pd.to_datetime(df['sleep_start_time'])
    df['laydown_time'] = pd.to_datetime(df['laydown_time'])
    df['out_of_bed_time'] = pd.to_datetime(df['out_of_bed_time'])

    # Convert date columns to minutes since
    df['out_of_bed_time_mins'] = df['out_of_bed_time'].apply(time_from_midnight)
    

    # Convert numeric columns
    time_columns = ['time_to_fall_asleep_hrs', 'time_to_fall_asleep_min',
                   'restful_hrs', 'restful_min', 'restless_hrs', 'restless_min',
                   'bed_exit_hrs', 'bed_exit_min']
    
    for col in time_columns:
        df[col] = df[col].fillna(0).astype(int)
    
    #Convert time columns to minutes
    df['time_to_fall_asleep'] = df['time_to_fall_asleep_hrs'] * 60 + df['time_to_fall_asleep_min']
    df['restful_time'] = df['restful_hrs'] * 60 + df['restful_min']
    df['restless_time'] = df['restless_hrs'] * 60 + df['restless_min']
    df['bed_exit_time'] = df['bed_exit_hrs'] * 60 + df['bed_exit_min']

    # Drop original hours/minutes columns
    columns_to_drop = ['time_to_fall_asleep_hrs', 'time_to_fall_asleep_min',
                      'restful_hrs', 'restful_min', 'restless_hrs', 'restless_min',
                      'bed_exit_hrs', 'bed_exit_min']
    df.drop(columns=columns_to_drop, inplace=True)
    
    #combine restful and restless time
    df['total_sleep_time'] = df['restful_time'] + df['restless_time']

    return df

def get_combined_data(email="jake.selvey@gmail.com", 
                     sheet_url="https://docs.google.com/spreadsheets/d/169r9jn66M-ij0Pj6eS7wV6q5jhE2vWUz5vhYCrcBLBA/edit?usp=sharing"):
    """
    Get and prepare combined data from all sources: Loop Habits, Sleep tracking, and steps.
    
    Parameters:
    email (str): Email address for fetching Loop Habits data
    sheet_url (str): URL of the Google Sheet containing sleep data
    
    Returns:
    pandas.DataFrame: Combined and cleaned dataset with all metrics
    """
    # Get raw data from all sources
    from .data_fetchers import fetch_loop_habits_data, get_sheet_data, fetch_daily_steps
    
    habits_data = fetch_loop_habits_data(email)
    sleep_data = get_sheet_data(sheet_url)
    steps_data = fetch_daily_steps()
    
    if habits_data is not None and sleep_data is not None:
        # Clean and prepare individual datasets
        habits_df = prepare_habit_data(habits_data)
        sleep_df = prepare_sleep_data(sleep_data)
        
        # Merge habit and sleep data
        combined_data = habits_df.merge(
            sleep_df,
            left_on='habit_date',
            right_on='next_day_date',
            how='left'
        )
        
        # Add steps data if available
        if steps_data is not None:
            # Ensure date types match for merging
            combined_data['habit_date'] = pd.to_datetime(combined_data['habit_date']).dt.date
            
            # Merge steps data
            combined_data = combined_data.merge(
                steps_data,
                left_on='habit_date',
                right_on='fit_date',
                how='left'
            )
            
            # Drop redundant/unnecessary columns with habit_date
            combined_data = combined_data.drop(columns=['fit_date'])
            combined_data = combined_data.drop(columns=['day_of_date'])
            combined_data = combined_data.drop(columns=['next_day_date'])

            # Add derived step metrics if needed
            combined_data['steps_10k'] = (combined_data['steps'] >= 10000).astype(int)
            combined_data['steps'] = combined_data['steps'].fillna(method='ffill')

            #create lag columns for steps
            combined_data['steps_lag1'] = combined_data['steps'].shift(1)

            # Calculate rolling averages
            combined_data['steps_r3'] = combined_data['steps'].rolling(window=3, min_periods=1).mean()
        
        return combined_data
    
    return None