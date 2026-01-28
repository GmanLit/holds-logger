# LRA Holds Logger - MCP Server

MCP (Model Context Protocol) server for Little Revolution Artists' holds management system. Handles Google Sheets integration for tracking hold requests and responses across artist rosters.

## Features

- **Log Holds**: Record new hold requests to Google Sheets with "Asked Hold" status
- **Update Status**: Change hold status when promoters respond with hold numbers
- **Read Sheets**: Query current holds data for any artist
- **Auto-formatting**: Color-code holds by priority (1st, 2nd, 3rd, 4th+)

## Setup

### Prerequisites

1. Google Service Account credentials (JSON key)
2. Heroku account
3. GitHub account

### Deployment to Heroku

1. **Set Environment Variable**:
   - Go to Heroku Dashboard → Your App → Settings → Config Vars
   - Add `GOOGLE_SHEETS_CREDENTIALS` = paste your entire service account JSON (as one line)

2. **Deploy**:
```bash
   git push heroku main
```

## MCP Tools Available

### `log_holds`
Log new hold requests to a sheet.
- `artist`: "weakened-friends" or "ballroom-thieves"
- `venue`: Venue name
- `dates`: List of dates (YYYY-MM-DD format)

### `update_holds_status`
Update hold status when promoter responds.
- `artist`: "weakened-friends" or "ballroom-thieves"
- `venue`: Venue name
- `hold_data`: Dict mapping dates to hold numbers, e.g., {"2026-04-30": 3}

### `read_holds_sheet`
Read current holds data.
- `artist`: "weakened-friends" or "ballroom-thieves"

## Environment Variables

### Required:
- `GOOGLE_SHEETS_CREDENTIALS`: Your Google service account JSON as a string

### Optional (for adding artists):
- `ARTIST_SHEETS_CONFIG`: JSON configuration of all artist sheets (see "Adding New Artists" below)

## Adding New Artists (Without Redeploying)

The server uses an environment variable to load artist configurations. You can add new artists anytime without touching the code.

### Step 1: Get Your New Sheet Details
For each artist, you need:
- **Sheet ID**: From the URL `https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/edit`
- **Tab Name**: The exact name of your holds tab (e.g., "WF-HOLDS", "TBT- Holds")

### Step 2: Update Heroku Config Variable
1. Go to Heroku Dashboard → Your App → Settings
2. Click "Reveal Config Vars"
3. Find or create `ARTIST_SHEETS_CONFIG`
4. Paste this JSON (all artists together):
```json
{
  "weakened-friends": {
    "sheet_id": "1fzf0x89ElPiz5961PXFRyJ43tZAWMxvUza-Zl-fJHKI",
    "tab_name": "WF-HOLDS"
  },
  "ballroom-thieves": {
    "sheet_id": "13N0uM5uUqyPk6LSSzUXY4GFs5DXuAy0VjgI6akdqs0s",
    "tab_name": "TBT- Holds"
  },
  "highly-suspect": {
    "sheet_id": "YOUR_SHEET_ID_HERE",
    "tab_name": "YOUR_TAB_NAME_HERE"
  },
  "slothrust": {
    "sheet_id": "YOUR_SHEET_ID_HERE",
    "tab_name": "YOUR_TAB_NAME_HERE"
  }
}
```

5. Click "Save" — **changes take effect immediately, no redeployment needed**

### Step 3: Use in Claude
Now your team can use the new artist name in any Claude tool:
```
artist: "highly-suspect"
```

**That's it! No code changes, no GitHub pushes, no waiting for deployment.**
