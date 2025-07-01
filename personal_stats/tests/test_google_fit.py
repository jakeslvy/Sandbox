from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

def test_google_fit_connection():
    """Simple test to verify Google Fit API connection"""
    
    # OAuth 2.0 scopes for Google Fit
    SCOPES = [
        'https://www.googleapis.com/auth/fitness.activity.read',
        'https://www.googleapis.com/auth/fitness.heart_rate.read',
        'https://www.googleapis.com/auth/fitness.body.read'
    ]
    
    # Get path to credentials file
    client_secret_file = os.getenv('GOOGLE_FIT_CLIENT_SECRET')
    if not client_secret_file:
        raise ValueError("GOOGLE_FIT_CLIENT_SECRET not found in .env file")
    
    print(f"Using credentials from: {client_secret_file}")
    
    try:
        # Initialize the flow
        flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
        
        # This will open your browser for authentication
        print("\nOpening browser for authentication...")
        creds = flow.run_local_server(port=0)
        
        # Build the Fitness API service
        service = build('fitness', 'v1', credentials=creds)
        
        # Try to fetch last 24 hours of step data as a test
        end_time = datetime.now()
        start_time = end_time - timedelta(days=1)
        
        print("\nTrying to fetch step data...")
        
        request_body = {
            "aggregateBy": [
                {"dataTypeName": "com.google.step_count.delta"}
            ],
            "bucketByTime": {"durationMillis": 86400000},  # 24 hours
            "startTimeMillis": int(start_time.timestamp() * 1000),
            "endTimeMillis": int(end_time.timestamp() * 1000)
        }
        
        response = service.users().dataset().aggregate(userId="me", 
                                                     body=request_body).execute()
        
        print("\nSuccessfully connected to Google Fit!")
        print("Response received:", response)
        
        return True
        
    except Exception as e:
        print(f"\nError connecting to Google Fit: {str(e)}")
        return False

if __name__ == "__main__":
    print("Testing Google Fit API connection...")
    test_google_fit_connection()