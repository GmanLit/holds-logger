#!/usr/bin/env python3
"""
MCP Server for Little Revolution Artists - Holds Logger
Handles Google Sheets integration for hold management across artist rosters
"""

import json
import os
from datetime import datetime
from typing import Any

from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from mcp.server.models import InitializationOptions
from mcp.server import Server
import mcp.types as types


# Initialize MCP Server
server = Server("lra-holds-logger")

# Google Sheets API setup
SCOPES = [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/drive"
]

# Load artist sheet configurations from environment variable
def load_artist_sheets():
      """Load artist sheet config from environment variable or use defaults"""
      config_json = os.getenv("ARTIST_SHEETS_CONFIG")
      if config_json:
                try:
                              return json.loads(config_json)
except json.JSONDecodeError:
            print("Warning: Invalid ARTIST_SHEETS_CONFIG JSON, using defaults")

    # Fallback defaults if env var not set
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

# Color codes (RGB 0-1 scale)
COLORS = {
      "asked-hold": {"red": 0.85, "green": 0.85, "blue": 0.85},
      "1-hold": {"red": 0.7, "green": 0.9, "blue": 0.7},
      "2-3-hold": {"red": 1, "green": 1, "blue": 0.7},
      "4plus-hold": {"red": 1, "green": 0.8, "blue": 0.6},
      "confirmed": {"red": 0.6, "green": 0.85, "blue": 0.6},
      "na-released": {"red": 0.95, "green": 0.7, "blue": 0.7},
      "avail": {"red": 0.8, "green": 0.95, "blue": 0.8}
}


def get_credentials():
      """Load Google credentials from environment variable"""
      creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
      if not creds_json:
                raise ValueError("GOOGLE_SHEETS_CREDENTIALS environment variable not set")

      creds_dict = json.loads(creds_json)
      credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
      return credentials


def get_sheets_service():
      """Get authenticated Google Sheets API service"""
      credentials = get_credentials()
      return build("sheets", "v4", credentials=credentials)


def get_sheet_data(sheet_id: str, tab_name: str, range_name: str) -> list:
      """Read data from a specific range in Google Sheets"""
      service = get_sheets_service()
      result = service.spreadsheets().values().get(
          spreadsheetId=sheet_id,
          range=f"'{tab_name}'!{range_name}"
      ).execute()
      return result.get("values", [])


def update_sheet_cells(sheet_id: str, tab_name: str, updates: list) -> dict:
      """Update multiple cells with values and formatting"""
      service = get_sheets_service()

    batch_update_request = {
              "requests": updates
    }

    result = service.spreadsheets().batchUpdate(
              spreadsheetId=sheet_id,
              body=batch_update_request
    ).execute()

    return result


def format_cell(sheet_id: str, tab_name: str, cell_range: str, background_color: dict) -> list:
      """Create format request for cell background color"""
      return {
          "updateCells": {
              "range": {
                  "sheetId": 0,  # Will be updated based on tab
                  "startRowIndex": int(cell_range.split(":")[0][1:]) - 1,
                  "endRowIndex": int(cell_range.split(":")[0][1:]),
                  "startColumnIndex": ord(cell_range[0]) - ord("A"),
                  "endColumnIndex": ord(cell_range[0]) - ord("A") + 1
              },
              "rows": [{
                  "values": [{
                      "userEnteredFormat": {
                          "backgroundColor": background_color
                      }
                  }]
              }],
              "fields": "userEnteredFormat.backgroundColor"
          }
      }


@server.call_tool()
async def log_holds(artist: str, venue: str, dates: list) -> str:
      """
          Log hold requests to the appropriate artist's holds sheet

                  Args:
                          artist: Either 'weakened-friends' or 'ballroom-thieves'
                                  venue: Venue name
                                          dates: List of dates in format 'YYYY-MM-DD'

                                                  Returns:
                                                          Confirmation message with details
                                                              """
      if artist not in ARTIST_SHEETS:
                return f"Error: Unknown artist '{artist}'. Use 'weakened-friends' or 'ballroom-thieves'."

      sheet_info = ARTIST_SHEETS[artist]
      sheet_id = sheet_info["sheet_id"]
      tab_name = sheet_info["tab_name"]

    today = datetime.now().strftime("%m/%d")

    try:
              # Read current sheet to find venue column and date rows
              all_data = get_sheet_data(sheet_id, tab_name, "A:Z")

        # Find venue column (row 3 contains venue names)
              venue_col = None
              if len(all_data) > 2:
                            for i, cell in enumerate(all_data[2]):
                                              if venue.lower() in cell.lower():
                                                                    venue_col = chr(67 + i)  # C=67 in ASCII
                    break

        if not venue_col:
                      return f"Error: Venue '{venue}' not found in sheet. Please add it manually first."

        # Create update requests for each date
        updates = []
        for date_str in dates:
                      # Find date row (dates are in column A starting from row 5)
                      for row_idx, row in enumerate(all_data[4:], start=5):
                                        if date_str in row[0] if row else False:
                                                              cell_ref = f"{venue_col}{row_idx}"
                                                              status = f"Asked Hold ({today})"

                    # Build update request
                              updates.append({
                                                        "range": f"'{tab_name}'!{cell_ref}",
                                                        "values": [[status]]
                              })

        if not updates:
                      return f"Error: No matching dates found for {dates}"

        # Batch update values
        service = get_sheets_service()
        service.spreadsheets().values().batchUpdate(
                      spreadsheetId=sheet_id,
                      body={"data": updates, "valueInputOption": "RAW"}
        ).execute()

        return f"✅ Logged holds for {venue} ({artist}) on {len(dates)} dates - marked as Asked Hold ({today})"

except Exception as e:
        return f"Error updating sheet: {str(e)}"


@server.call_tool()
async def update_holds_status(artist: str, venue: str, hold_data: dict) -> str:
      """
          Update hold status when promoter responds

                  Args:
                          artist: 'weakened-friends' or 'ballroom-thieves'
                                  venue: Venue name
                                          hold_data: Dict mapping dates to hold numbers, e.g. {'2026-04-30': 3, '2026-05-01': 3}

                                                  Returns:
                                                          Confirmation with details of updates
                                                              """
    if artist not in ARTIST_SHEETS:
              return f"Error: Unknown artist '{artist}'."

    sheet_info = ARTIST_SHEETS[artist]
    sheet_id = sheet_info["sheet_id"]
    tab_name = sheet_info["tab_name"]
    #
! / u s rt/obdiany/ e=n vd aptyetthiomne3.
n"o"w"(
)M.CsPt rSfetrivmeer( "f%omr/ %Ldi"t)t
l e   R e
v o l u ttiroyn: 
A r t i s t s   -#  HRoeladds  sLhoegegte rt
oH afnidnlde sv eGnouoeg lceo lSuhmene
t s   i n t e g raaltli_odna tfao r=  hgoeltd_ smhaeneatg_edmaetnat( sahcereots_si da,r ttiasbt_ nraomset,e r"sA
:"Z""")


 i m p o r t   j
 s o n 
  i m p o r#t  Foisn
  df rvoemn udea tceotliummen 
  i m p o r t   d avteentuiem_ec
  oflr o=m  Ntoynpei
  n g   i m p o r ti fA nlye
  n
  (farlolm_ dgaotoag)l e>. o2a:u
  t h 2 . s e r v i c e _ afcocro uin,t  ciemlplo ritn  Cerneudmeenrtaitael(sa
  lflr_odma tgao[o2g]l)e:.
  a u t h . t r a n s p o r t . r eiqfu evsetnsu ei.mlpoowretr (R)e qiune scte
  lflr.olmo wgeoro(g)l:e
  a p i c l i e n t . d i s c o v e r y   ivmepnouret_ cbouli l=d 
  cfhrro(m6 7m c+p .is)e
  r v e r . m o d e l s   i m p o r t   I nbirteiaakl
  i z a t i o n O p
  t i o n s 
   f r oimf  mncopt. sveernvueer_ ciomlp:o
   r t   S e r v e r 
    i m proerttu rmnc pf."tEyrpreosr :a sV etnyupee s'
                     {
                     v
                     e#n uIen}i't inaolti zfeo uMnCdP. "S
e r v e r 
 s e r
v e r   =   S e r#v eUrp(d"altrea -ehaoclhd sd-altoeg gweirt"h) 
h
o#l dG osotgalteu sS
h e e t s   A P Iu psdeattueps
 S=C O[P]E
S   =   [ 
      f o"rh tdtaptse:_/s/twrw,w .hgoolodg_lneuamp iisn. chooml/da_udtaht/as.pirteeamdss(h)e:e
t s " , 
         " h t tfposr: /r/owww_wi.dgxo,o grloewa piins .ecnoumm/earuatthe/(darlilv_ed"a
t]a
[
  4#: ]L,o asdt aarrtt=i5s)t: 
  s h e e t   c o n f i g u r a t iiofn sd aftreo_ms tern viinr ornomwe[n0t]  viafr iraobwl ee
ldseef  Flaolasde_:a
r t i s t _ s h e e t s ( ) : 
         "c"e"lLlo_arde fa r=t ifs"t{ vsehneueet_ ccooln}f{irgo wf_riodmx }e"n
         v i r o n m e n t   v a r i a b l e   o rs tuasteu sd e=f afu"l{thso"l"d"_
         n u m }  cHoonlfdi g(_{jtsoodna y=} )o"s
         . g e t e n v ( " A R T I S T _ S H E E TuSp_dCaOtNeFsI.Ga"p)p
         e n d ( {i
         f   c o n f i g _ j s o n : 
                          t r"yr:a
                          n g e " :   f " ' { t a br_entaumren} 'j!s{ocne.lllo_ardesf(}c"o,n
                          f i g _ j s o n ) 
                                           e x c e p t  "jvsaolnu.eJsS"O:N D[e[csotdaetEursr]o]r
                                           : 
                                                                    p r i n t ( "}W)a
                                                                    r n i n g :   I n
                                                                    v a l i d   A R TiIfS Tn_oStH EuEpTdSa_tCeOsN:F
                                                                    I G   J S O N ,   u s i nrge tduerfna ufl"tEsr"r)o
                                                                    r :   N o
                                                                      m a t c#h iFnagl ldbaatceks  dfeofuanudl.t"s
                                                                        i f   e n v   v
                                                                        a r   n o t   s e#t 
                                                                        B a t c hr eutpudrant e{

                                                                                        s"ewrevaikceen e=d -gferti_esnhdese"t:s _{s
                                                                                        e r v i c e ( ) 
                                                                                                " s h e este_rivdi"c:e ."s1pfrzefa0dxs8h9eEeltPsi(z)5.9v6a1lPuXeFsR(y)J.4b3attZcAhWUMpxdvaUtzea(-
                                                                                                Z l - f J H K I " , 
                                                                                                    s p r e a d s h e e t"Itda=bs_hneaemte_"i:d ,"
                                                                                                    W F - H O L D S " 
                                                                                                          b o d y = {}",d
                                                                                                          a t a " :   u p d"abtaelsl,r o"ovma-ltuheiIenvpeust"O:p t{i
                                                                                                          o n " :   " R A W " } 
                                                                                                            " s h e e t _ i)d."e:x e"c1u3tNe0(u)M
                                                                                                            5 u U q y P k 6 L
                                                                                                            S S z U X Y 4 G Frse5tDuXrunA yf0"V✅j gUIp6daaktdeqds 0hso"l,d
                                                                                                            s   f o r   { v e n u e }" t(a{ba_rntaimset"}:)  "-T B{Tl-e nH(oulpddsa"t
                                                                                                            e s ) }   d a t e}s
                                                                                                              u p d a}t
                                                                                                              e
                                                                                                              dA"R
                                                                                                              T I S T _
                                                                                                              S H E E TeSx c=e plto aEdx_caerpttiisotn_ sahse eet:s
                                                                                                              ( ) 
                                                                                                               
                                                                                                                #   C o lroert ucrond efs" E(rRrGoBr :0 -{1s tsrc(ael)e})"
                                                                                                                
                                                                                                                C
                                                                                                                O
                                                                                                                L@OsReSr v=e r{.
                                                                                                                c a l l _"taosokle(d)-
                                                                                                                haoslydn"c:  d{e"fr erde"a:d _0h.o8l5d,s _"sghreeeetn("a:r t0i.s8t5:,  s"tbrl)u e-">:  s0t.r8:5
                                                                                                                } , 
                                                                                                                    " " ""
                                                                                                                    1 - h o lRde"a:d  {a"nrde dr"e:t u0r.n7 ,c u"rgrreenetn "h:o l0d.s9 ,s h"ebeltu ed"a:t a0 .f7o}r, 
                                                                                                                    a n   a r"t2i-s3t-
                                                                                                                    h o l d "
                                                                                                                    :   { " rAerdg"s:: 
                                                                                                                    1 ,   " g r e e na"r:t i1s,t :" b'lwueea"k:e n0e.d7-}f,r
                                                                                                                    i e n d s"'4 polru s'-bhaollldr"o:o m{-"trheide"v:e s1',
                                                                                                                      " g r e
                                                                                                                      e n " :  R0e.t8u,r n"sb:l
                                                                                                                      u e " :   0 . 6 }S,h
                                                                                                                      e e t   d"actoan faisr mfeodr"m:a t{t"erde ds"t:r i0n.g6
                                                                                                                      ,   " g r"e"e"n
                                                                                                                      " :   0 .i8f5 ,a r"tbilsute "n:o t0 .i6n} ,A
                                                                                                                      R T I S T"_nSaH-ErEeTlSe:a
                                                                                                                      s e d " :   { " rreedt"u:r n0 .f9"5E,r r"ogrr:e eUnn"k:n o0w.n7 ,a r"tbilsute "':{ a0r.t7i}s,t
                                                                                                                      } ' . " 
                                                                                                                      " a v a i
                                                                                                                      l " :   {s"hreeedt"_:i n0f.o8 ,=  "AgRrTeIeSnT"_:S H0E.E9T5S,[ a"rbtliuset"]:
                                                                                                                        0 . 8 }s
                                                                                                                        h}e
                                                                                                                        e
                                                                                                                        t
                                                                                                                        _diedf  =g esth_ecerte_diennftoi[a"lssh(e)e:t
                                                                                                                        _ i d " ]"
                                                                                                                        " " L o atda bG_onoagmlee  =c rsehdeeentt_iianlfso [f"rtoamb _ennavmier"o]n
                                                                                                                        m e n t  
                                                                                                                        v a r i atbrlye:"
                                                                                                                        " " 
                                                                                                                                 c rdeadtsa_ j=s ogne t=_ sohse.egte_tdeantva(("sGhOeOeGtL_Ei_dS,H EtEaTbS__nCaRmEeD,E N"TAI:AZL"S)"
                                                                                                                                 ) 
                                                                                                                                          i f  
                                                                                                                                          n o t   c r e d s#_ jFsoornm:a
                                                                                                                                          t   a s   r e a draabilsee  tVeaxltu
                                                                                                                                          e E r r o r ( " GoOuOtGpLuEt_ S=H EfE"T📋S _{CaRrEtDiEsNtT.IrAeLpSl aecnev(i'r-o'n,m e'n t' )v.atriitalbel(e) }n o-t  Hsoeltd"s) 
                                                                                                                                          S h e e t
                                                                                                                                          \ n \ n "c
                                                                                                                                          r e d s _ d i c tf o=r  jrsoown .ilno addast(ac[r:e1d5s]_:j s o#n )L
                                                                                                                                          i m i t  ctroe dfeinrtsita l1s5  =r oCwrse dfeonrt iraelasd.afbriolmi_tsye
                                                                                                                                          r v i c e _ a c c o u n to_uitnpfuot( c+r=e d"s _|d i"c.tj,o isnc(ospters(=cSeClOlP)E Sf)o
                                                                                                                                          r   c e lrle tiunr nr ocwr)e d+e n"t\ina"l
                                                                                                                                          s 
                                                                                                                                           
                                                                                                                                            
                                                                                                                                             d e f   g
                                                                                                                                             e t _ s h e e t sr_esteurrvni coeu(t)p:u
                                                                                                                                             t 
                                                                                                                                                   " "
                                                                                                                                                   " G e t  eaxuctehpetn tEixccaetpetdi oGno oagsl ee :S
                                                                                                                                                   h e e t s   A P Ir esteurrvni cfe""E"r"r
                                                                                                                                                   o r   r ecardeidnegn tsihaelest :=  {gsettr_(cer)e}d"e
                                                                                                                                                   n
                                                                                                                                                   t
                                                                                                                                                   iaaslysn(c) 
                                                                                                                                                   d e f   mraeitnu(r)n: 
                                                                                                                                                   b u i l d"("""sShteaertts "t,h e" vM4C"P,  scerrevdeern"t"i"a
                                                                                                                                                   l s = c raesdyennct iwailtsh) 
                                                                                                                                                   s
                                                                                                                                                   e
                                                                                                                                                   rdveefr :g
                                                                                                                                                   e t _ s h e e t _pdraitnat((s"h🎵 eLeRtA_ iHdo:l dsst rL,o gtgaebr_ nMaCmPe :S esrtvre,r  rraunngnei_nnga.m.e.:" )s
                                                                                                                                                   t r )   - >   l ipsrti:n
                                                                                                                                                   t ( " R e"a"d"yR etaod  pdraotcae sfsr ohmo lad  srpeeqcuiefsitcs  rfaonrg ey oiunr  Gaorotgilset sS"h)e
                                                                                                                                                   e
                                                                                                                                                   t
                                                                                                                                                   si"f" "_
                                                                                                                                                   _ n a m es_e_r v=i=c e" _=_ mgaeitn__s_h"e:e
                                                                                                                                                   t s _ s eirmvpiocret( )a
                                                                                                                                                   s y n c iroe
                                                                                                                                                   s u l t  a=s ysnecrivoi.creu.ns(pmraeiand(s)h)eets().values().get(
                                                                                                                                                           spreadsheetId=sheet_id,
                                                                                                                                                                   range=f"'{tab_name}'!{range_name}"
                                                                                                                                                                       ).execute()
                                                                                                                                                                           return result.get("values", [])
                                                                                                                                                                           
                                                                                                                                                                           
                                                                                                                                                                           def update_sheet_cells(sheet_id: str, tab_name: str, updates: list) -> dict:
                                                                                                                                                                               """Update multiple cells with values and formatting"""
                                                                                                                                                                                   service = get_sheets_service()
                                                                                                                                                                                       
                                                                                                                                                                                           batch_update_request = {
                                                                                                                                                                                                   "requests": updates
                                                                                                                                                                                                       }
                                                                                                                                                                                                           
                                                                                                                                                                                                               result = service.spreadsheets().batchUpdate(
                                                                                                                                                                                                                       spreadsheetId=sheet_id,
                                                                                                                                                                                                                               body=batch_update_request
                                                                                                                                                                                                                                   ).execute()
                                                                                                                                                                                                                                       
                                                                                                                                                                                                                                           return result
                                                                                                                                                                                                                                           
                                                                                                                                                                                                                                           
                                                                                                                                                                                                                                           def format_cell(sheet_id: str, tab_name: str, cell_range: str, background_color: dict) -> list:
                                                                                                                                                                                                                                               """Create format request for cell background color"""
                                                                                                                                                                                                                                                   return {
                                                                                                                                                                                                                                                           "updateCells": {
                                                                                                                                                                                                                                                                       "range": {
                                                                                                                                                                                                                                                                                       "sheetId": 0,  # Will be updated based on tab
                                                                                                                                                                                                                                                                                                       "startRowIndex": int(cell_range.split(":")[0][1:]) - 1,
                                                                                                                                                                                                                                                                                                                       "endRowIndex": int(cell_range.split(":")[0][1:]),
                                                                                                                                                                                                                                                                                                                                       "startColumnIndex": ord(cell_range[0]) - ord("A"),
                                                                                                                                                                                                                                                                                                                                                       "endColumnIndex": ord(cell_range[0]) - ord("A") + 1
                                                                                                                                                                                                                                                                                                                                                                   },
                                                                                                                                                                                                                                                                                                                                                                               "rows": [{
                                                                                                                                                                                                                                                                                                                                                                                               "values": [{
                                                                                                                                                                                                                                                                                                                                                                                                                   "userEnteredFormat": {
                                                                                                                                                                                                                                                                                                                                                                                                                                           "backgroundColor": background_color
                                                                                                                                                                                                                                                                                                                                                                                                                                                               }
                                                                                                                                                                                                                                                                                                                                                                                                                                                                               }]
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           }],
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       "fields": "userEnteredFormat.backgroundColor"
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               }
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   }
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   @server.call_tool()
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   async def log_holds(artist: str, venue: str, dates: list) -> str:
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       """
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           Log hold requests to the appropriate artist's holds sheet
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   Args:
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           artist: Either 'weakened-friends' or 'ballroom-thieves'
        venue: Venue name
                dates: List of dates in format 'YYYY-MM-DD'

        Returns:
                Confirmation message with details
                    """
                        if artist not in ARTIST_SHEETS:
                                return f"Error: Unknown artist '{artist}'. Use 'weakened-friends' or 'ballroom-thieves'."

                                        sheet_info = ARTIST_SHEETS[artist]
                                            sheet_id = sheet_info["sheet_id"]
                                                tab_name = sheet_info["tab_name"]

                                                        today = datetime.now().strftime("%m/%d")

                                                                try:
                                                                        # Read current sheet to find venue column and date rows
                                                                                all_data = get_sheet_data(sheet_id, tab_name, "A:Z")

                                                                                                # Find venue column (row 3 contains venue names)
                                                                                                  
