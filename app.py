#!/usr/bin/env python3
"""
LRA Holds Logger - Google Sheets MCP Server
"""

import json
import os
from datetime import datetime
from typing import List, Dict

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(
    title="LRA Holds Logger",
    description="Google Sheets integration for Little Revolution Artists",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def load_artist_sheets():
    config_json = os.getenv("ARTIST_SHEETS_CONFIG")
    if config_json:
        try:
            return json.loads(config_json)
        except json.JSONDecodeError:
            print("Warning: Invalid ARTIST_SHEETS_CONFIG JSON, using defaults")
    
    return {
        "weakened-friends": {
            "sheet_id": "1fzf0x89ElPiz5961PXFRyJ43tZAWMxvUza-Zl-fJHKI",
            "tab_name": "WF-HOLDS"
        },
        "ballroom-thieves": {
            "sheet_id": "13N0uM5uUqyPk6LSSzUXY4GFs5DXuAy0VjgI6akdqs0s",
            "tab_name": "TBT- Holds"
        }
    }

ARTIST_SHEETS = load_artist_sheets()

def get_credentials():
    creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_json:
        raise ValueError("GOOGLE_SHEETS_CREDENTIALS environment variable not set")
    
    creds_dict = json.loads(creds_json)
    credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return credentials

def get_sheets_service():
    credentials = get_credentials()
    return build("sheets", "v4", credentials=credentials)

def get_sheet_data(sheet_id: str, tab_name: str, range_name: str) -> List[List[str]]:
    service = get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!{range_name}"
    ).execute()
    return result.get("values", [])

def update_sheet_values(sheet_id: str, tab_name: str, updates: List[Dict]) -> Dict:
    service = get_sheets_service()
    body = {
        "data": updates,
        "valueInputOption": "RAW"
    }
    result = service.spreadsheets().values().batchUpdate(
        spreadsheetId=sheet_id,
        body=body
    ).execute()
    return result

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "lra-holds-logger",
        "artists": list(ARTIST_SHEETS.keys())
    }

@app.post("/api/log-holds")
async def log_holds(artist: str, venue: str, dates: List[str]):
    try:
        if not artist or not venue or not dates:
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        if artist not in ARTIST_SHEETS:
            raise HTTPException(status_code=400, detail=f"Unknown artist: {artist}")
        
        sheet_info = ARTIST_SHEETS[artist]
        sheet_id = sheet_info["sheet_id"]
        tab_name = sheet_info["tab_name"]
        
        today = datetime.now().strftime("%m/%d")
        all_data = get_sheet_data(sheet_id, tab_name, "A:Z")
        
        venue_col = None
        if len(all_data) > 2:
            for i, cell in enumerate(all_data[2]):
                if venue.lower() in cell.lower():
                    venue_col = chr(67 + i)
                    break
        
        if not venue_col:
            raise HTTPException(status_code=400, detail=f"Venue not found: {venue}")
        
        updates = []
        for date_str in dates:
            for row_idx, row in enumerate(all_data[4:], start=5):
                if row and date_str in row[0]:
                    cell_ref = f"{venue_col}{row_idx}"
                    status = f"Asked Hold ({today})"
                    updates.append({
                        "range": f"'{tab_name}'!{cell_ref}",
                        "values": [[status]]
                    })
        
        if not updates:
            raise HTTPException(status_code=400, detail="No matching dates found")
        
        update_sheet_values(sheet_id, tab_name, updates)
        
        return {
            "status": "success",
            "message": f"Logged {len(updates)} holds for {venue}",
            "dates_updated": len(updates)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/artists")
async def list_artists():
    return {
        "artists": list(ARTIST_SHEETS.keys()),
        "count": len(ARTIST_SHEETS)
    }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="info")
```

Then click **"Commit changes"**.

---

Heroku will redeploy in 30 seconds. Then test:
```
https://holds-logger-fbfb0a6ead7c.herokuapp.com/health
