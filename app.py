#!/usr/bin/env python3
import json
import os
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from mcp.server import Server
from mcp.types import Tool, TextContent
import asyncio
import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager

app = FastAPI()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def load_artist_sheets():
    config_json = os.getenv("ARTIST_SHEETS_CONFIG")
    if config_json:
        try:
            return json.loads(config_json)
        except:
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
    return Credentials.from_service_account_info(json.loads(creds_json), scopes=SCOPES)

def get_sheets_service():
    return build("sheets", "v4", credentials=get_credentials())

def get_sheet_data(sheet_id: str, tab_name: str, range_name: str):
    result = get_sheets_service().spreadsheets().values().get(spreadsheetId=sheet_id, range=f"'{tab_name}'!{range_name}").execute()
    return result.get("values", [])

def update_sheet_values(sheet_id: str, tab_name: str, updates):
    body = {"data": updates, "valueInputOption": "RAW"}
    return get_sheets_service().spreadsheets().values().batchUpdate(spreadsheetId=sheet_id, body=body).execute()

server = Server("lra-holds-logger")

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list:
    if name == "log_holds":
        artist = arguments.get("artist")
        venue = arguments.get("venue")
        dates = arguments.get("dates", [])
        
        try:
            if not artist or not venue or not dates or artist not in ARTIST_SHEETS:
                return [TextContent(type="text", text="Error: Invalid parameters")]
            
            sheet = ARTIST_SHEETS[artist]
            today = datetime.now().strftime("%m/%d")
            data = get_sheet_data(sheet["sheet_id"], sheet["tab_name"], "A:Z")
            
            venue_col = None
            if len(data) > 2:
                for i, cell in enumerate(data[2]):
                    if venue.lower() in cell.lower():
                        venue_col = chr(67 + i)
                        break
            
            if not venue_col:
                return [TextContent(type="text", text=f"Error: Venue '{venue}' not found")]
            
            updates = []
            for date_str in dates:
                for row_idx, row in enumerate(data[4:], start=5):
                    if row and date_str in row[0]:
                        updates.append({"range": f"'{sheet['tab_name']}'!{venue_col}{row_idx}", "values": [[f"Asked Hold ({today})"]]})
            
            if updates:
                update_sheet_values(sheet["sheet_id"], sheet["tab_name"], updates)
            
            return [TextContent(type="text", text=f"Success: Logged {len(updates)} holds for {venue}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    elif name == "read_holds":
        artist = arguments.get("artist")
        
        try:
            if artist not in ARTIST_SHEETS:
                return [TextContent(type="text", text="Error: Unknown artist")]
            
            sheet = ARTIST_SHEETS[artist]
            data = get_sheet_data(sheet["sheet_id"], sheet["tab_name"], "A:Z")
            
            result = f"Holds for {artist}:\n"
            for i, row in enumerate(data[:20]):
                result += f"Row {i+1}: {' | '.join(str(c) for c in row)}\n"
            
            return [TextContent(type="text", text=result)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    else:
        return [TextContent(type="text", text="Unknown tool")]

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="log_holds",
            description="Log hold requests to Google Sheets for an artist venue",
            inputSchema={
                "type": "object",
                "properties": {
                    "artist": {"type": "string", "description": "Artist name (weakened-friends or ballroom-thieves)"},
                    "venue": {"type": "string", "description": "Venue name"},
                    "dates": {"type": "array", "items": {"type": "string"}, "description": "List of dates to log holds for"}
                },
                "required": ["artist", "venue", "dates"]
            }
        ),
        Tool(
            name="read_holds",
            description="Read current holds data for an artist",
            inputSchema={
                "type": "object",
                "properties": {
                    "artist": {"type": "string", "description": "Artist name"}
                },
                "required": ["artist"]
            }
        )
    ]

@app.get("/health")
async def health():
    return {"status": "ok", "service": "lra-holds-logger"}

@app.post("/sse")
async def sse():
    async with server.session() as session:
        async with session.transport.stream(None) as stream:
            async for message in stream:
                yield message

if __name__ == "__main__":
    import sys
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
