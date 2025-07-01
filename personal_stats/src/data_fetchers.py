import pandas as pd
import imaplib
import email
import os
from datetime import datetime
import zipfile
import io
from email.utils import parseaddr
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
from datetime import datetime, timedelta

load_dotenv()

def fetch_loop_habits_data(email_address="jake.selvey@gmail.com", date=None):
    """
    Fetch Loop Habits data from Gmail attachments.
    
    Parameters:
    email_address (str): Gmail address to fetch data from (default: jake.selvey@gmail.com)
    date (str): Date to fetch data for in YYYY-MM-DD format (default: current date)
    
    Returns:
    pandas.DataFrame: The Loop Habits data for the specified date
    """
    app_password = os.getenv('GMAIL_PASSWORD')
    if not app_password:
        raise ValueError("Gmail password not found in environment variables")
    
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    search_date = datetime.strptime(date, '%Y-%m-%d').strftime('%d-%b-%Y')
    expected_filename = f"Loop Habits CSV {date}.zip"
    
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_address, app_password)
        mail.select('inbox')
        
        # Search for messages from that date
        _, message_numbers = mail.search(None, f'(SENTON {search_date})')
        
        if not message_numbers[0]:
            print(f"No emails found for {date}")
            return None
        
        # Store matching messages with their received timestamps
        messages = []
        for num in message_numbers[0].split():
            try:
                _, msg_data = mail.fetch(num, '(RFC822)')
                email_body = msg_data[0][1]
                message = email.message_from_bytes(email_body)
                
                _, sender_email = parseaddr(message['from'])
                
                if sender_email == email_address and message['subject'] in (None, ''):
                    # Get received timestamp
                    received_time = email.utils.parsedate_to_datetime(message['Date'])
                    messages.append((received_time, num, message))
                    
            except Exception as e:
                print(f"Error processing message {num}: {str(e)}")
                continue
        
        if not messages:
            print(f"No matching emails found for date {date}")
            return None
            
        # Sort messages by received timestamp (newest first)
        messages.sort(key=lambda x: x[0], reverse=True)
        latest_message = messages[0][2]  # Take the message from the latest tuple
        
        # Process the latest message
        for part in latest_message.walk():
            if part.get_content_maintype() == 'application':
                attachment_filename = part.get_filename()
                print(f"Found attachment: {attachment_filename}")
                
                if attachment_filename == expected_filename:
                    zip_data = part.get_payload(decode=True)
                    zip_file = zipfile.ZipFile(io.BytesIO(zip_data))
                    
                    with zip_file.open('Checkmarks.csv') as csv_file:
                        df = pd.read_csv(csv_file)
                        print(f"Successfully loaded data from {expected_filename}")
                        return df
        
        print(f"No matching attachment found for date {date}")
        return None
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return None
        
    finally:
        try:
            mail.logout()
        except:
            pass

def get_sheet_data(url="https://docs.google.com/spreadsheets/d/169r9jn66M-ij0Pj6eS7wV6q5jhE2vWUz5vhYCrcBLBA/edit?usp=sharing", sheet_name='Sheet1'):
    """
    Import data from a public Google Sheet into a pandas DataFrame
    
    Parameters:
    url (str): The sharing URL of the Google Sheet (default: Jake's sleep tracking sheet)
    sheet_name (str): Name of the specific sheet to import (default 'Sheet1')
    
    Returns:
    pandas.DataFrame: The imported sheet data
    """
    # Extract the sheet ID from the URL
    # URL format: https://docs.google.com/spreadsheets/d/{sheet_id}/edit?usp=sharing
    try:
        sheet_id = url.split('/d/')[1].split('/')[0]
    except IndexError:
        raise ValueError("Invalid Google Sheets URL format")
    
    # Create the export URL
    export_url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}'
    
    try:
        # Read the sheet into a pandas DataFrame
        df = pd.read_csv(export_url)
        return df
    except Exception as e:
        raise Exception(f"Error reading sheet: {str(e)}")
    
def get_google_fit_credentials():
    """Get or refresh Google Fit credentials"""
    
    SCOPES = ['https://www.googleapis.com/auth/fitness.activity.read']
    
    # Get project root directory (two levels up from notebooks)
    project_root = os.path.abspath(os.path.join(os.getcwd(), '..'))
    
    creds = None
    token_file = os.path.join(project_root, 'credentials', 'token.pickle')
    client_secret_file = os.path.join(project_root, 'credentials', 'client_secret.json')
    
    # Load existing credentials if they exist
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)
    
    # If credentials don't exist or are invalid, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save credentials for future use
        os.makedirs(os.path.dirname(token_file), exist_ok=True)
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)
    
    return creds

def fetch_daily_steps():
    """
    Fetch daily step count from Google Fit API starting from August 15, 2024.
    Handles API limitations by fetching in 30-day chunks.
    
    Returns:
    pandas.DataFrame: Daily step counts with columns ['fit_date', 'steps']
    """
    try:
        # Set fixed start date and current date as end
        end_time = datetime.now()
        start_time = datetime(2024, 8, 15)
        
        # Get credentials and build service
        creds = get_google_fit_credentials()
        service = build('fitness', 'v1', credentials=creds)
        
        # Initialize list to store all step data
        all_steps = []
        
        # Fetch data in 30-day chunks
        current_start = start_time
        while current_start < end_time:
            # Calculate end of current chunk
            chunk_end = min(current_start + timedelta(days=30), end_time)
            
            # Request body for daily step count
            request_body = {
                "aggregateBy": [
                    {"dataTypeName": "com.google.step_count.delta"}
                ],
                "bucketByTime": {"durationMillis": 86400000},  # Daily buckets
                "startTimeMillis": int(current_start.timestamp() * 1000),
                "endTimeMillis": int(chunk_end.timestamp() * 1000)
            }
            
            response = service.users().dataset().aggregate(userId="me", 
                                                         body=request_body).execute()
            
            # Process response for this chunk
            for bucket in response['bucket']:
                date = datetime.fromtimestamp(int(bucket['startTimeMillis'])/1000)
                steps = 0
                
                # Get step count if available
                if bucket['dataset'][0]['point']:
                    steps = bucket['dataset'][0]['point'][0]['value'][0]['intVal']
                
                all_steps.append({
                    'fit_date': date.date(),
                    'steps': steps
                })
            
            # Move to next chunk
            current_start = chunk_end
        
        return pd.DataFrame(all_steps)
        
    except Exception as e:
        print(f"Error fetching step data: {str(e)}")
        return None