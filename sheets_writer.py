"""
Tiny helper around the Google Sheets API v4.
Only two public functions:  write_dataframe_to_sheet  and  clear_worksheet.
"""
from __future__ import annotations

from typing import List

import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build


SCOPES: List[str] = ["https://www.googleapis.com/auth/spreadsheets"]


def _service(creds_json: dict):
    credentials = service_account.Credentials.from_service_account_info(
        creds_json, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def clear_worksheet(spreadsheet_id: str, worksheet_name: str, creds_json: dict) -> None:
    svc = _service(creds_json)
    range_ = f"{worksheet_name}!A:Z"
    svc.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=range_,
        body={},
    ).execute()


def write_dataframe_to_sheet(
    df: pd.DataFrame,
    creds_json: dict,
    spreadsheet_id: str,
    worksheet_name: str,
) -> None:
    svc = _service(creds_json)
    # 1) wipe old data
    clear_worksheet(spreadsheet_id, worksheet_name, creds_json)
    # 2) write header + rows
    body = {
        "values": [df.columns.to_list()] + df.astype(str).values.tolist()
    }
    svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{worksheet_name}!A1",
        valueInputOption="RAW",
        body=body,
    ).execute()
