#!/usr/bin/env python3
import json
import os
from datetime import datetime

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from mcp.server.fastapi import FastAPIServer
import uvicorn

mcp = FastAPIServer("lra-holds-logger")

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
            pass
    return {
        "weakened-friends": {"sheet_id": "1fzf0x89ElPiz5961PXFRyJ43tZAWMxvUza-Zl-fJHKI", "tab_name": "WF-HOLDS"},
        "ballroom-thieves": {"sheet_id": "13N0uM5uUqyPk6LSSzUXY4GFs5DXuAy0VjgI6akdqs0s", "tab_name": "TBT- Holds"}
    }

ARTIST_SHEETS = load_artist_sheets()

def get_credentials():
    creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_json:
        raise ValueError("GOOGLE_SHEETS_CREDENTIALS not set")
    creds_dict = json.loads(creds_json)
    return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)

def get_sheets_service():
    credentials = get_credentials()
    return build("sheets", "v4", credentials=credentials)

def get_sheet_data(sheet_id: str, tab_name: str, range_name: str):
    service = get_sheets_service()
    result = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=f"'{tab_name}'!{range_name}").execute()
    return result.get("values", [])

def update_sheet_values(sheet_id: str, tab_name: str, updates):
    service = get_sheets_service()
    body = {"data": updates, "valueInputOption": "RAW"}
    return service.spreadsheets().values().batchUpdate(spreadsheetId=sheet_id, body=body).execute()

@mcp.tool()
def log_holds(artist: str, venue: str, dates: list) -> str:
    try:
        if not artist or not venue or not dates:
            return "Error: Missing required fields"
        if artist not in ARTIST_SHEETS:
            return f"Error: Unknown artist. Available: {', '.join(ARTIST_SHEETS.keys())}"
        
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
            return f"Error: Venue '{venue}' not found"
        
        updates = []
        for date_str in dates:
            for row_idx, row in enumerate(all_data[4:], start=5):
                if row and date_str in row[0]:
                    cell_ref = f"{venue_col}{row_idx}"
                    status = f"Asked Hold ({today})"
                    updates.append({"range": f"'{tab_name}'!{cell_ref}", "values": [[status]]})
        
        if not updates:
            return "Error: No matching dates found"
        
        update_sheet_values(sheet_id, tab_name, updates)
        return f"Success: Logged {len(updates)} holds for {venue}"
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def update_holds_status(artist: str, venue: str, hold_data: dict) -> str:
    try:
        if not artist or not venue or not hold_data:
            return "Error: Missing required fields"
        if artist not in ARTIST_SHEETS:
            return f"Error: Unknown artist"
        
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
            return f"Error: Venue not found"
        
        updates = []
        for date_str, hold_num in hold_data.items():
            for row_idx, row in enumerate(all_data[4:], start=5):
                if row and date_str in row[0]:
                    cell_ref = f"{venue_col}{row_idx}"
                    status = f"{hold_num} Hold ({today})"
                    updates.append({"range": f"'{tab_name}'!{cell_ref}", "values": [[status]]})
        
        if not updates:
            return "Error: No matching dates found"
        
        update_sheet_values(sheet_id, tab_name, updates)
        return f"Success: Updated {len(updates)} holds"
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def read_holds_sheet(artist: str) -> str:
    try:
        if artist not in ARTIST_SHEETS:
            return f"Error: Unknown artist"
        
        sheet_info = ARTIST_SHEETS[artist]
        sheet_id = sheet_info["sheet_id"]
        tab_name = sheet_info["tab_name"]
        data = get_sheet_data(sheet_id, tab_name, "A:Z")
        
        if not data:
            return f"No data found"
        
        result = f"Holds for {artist}:\n"
        for i, row in enumerate(data[:15]):
            result += f"Row {i+1}: {' | '.join(str(c) for c in row)}\n"
        return result
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(mcp.app, host="0.0.0.0", port=port, log_level="info")
