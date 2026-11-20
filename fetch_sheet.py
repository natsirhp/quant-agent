"""Download the Investment_Tracker Google Sheet and write it as plain text for the report.

    python fetch_sheet.py work/portfolio.md            # read from Google (service account)
    python fetch_sheet.py work/portfolio.md --xlsx f   # read a local .xlsx export instead

Environment (GitHub secrets):
  GOOGLE_SERVICE_ACCOUNT_JSON  the full JSON key of a Google service account
                               that the sheet is shared with as Viewer
  GOOGLE_SHEET_ID              the ID from the sheet's URL (/spreadsheets/d/<ID>/edit)

The export contains the values Google Sheets last calculated (GOOGLEFINANCE prices
and FX included). Only the tabs the report needs are written out.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import sys
from pathlib import Path

import openpyxl
import requests

TABS = ["Dashboard", "Holdings", "Transactions", "Prices", "Monthly"]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def download_xlsx(sheet_id: str, key_json: str) -> bytes:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(
        json.loads(key_json), scopes=["https://www.googleapis.com/auth/drive.readonly"])
    creds.refresh(Request())
    r = requests.get(f"https://www.googleapis.com/drive/v3/files/{sheet_id}/export",
                     params={"mimeType": XLSX},
                     headers={"Authorization": f"Bearer {creds.token}"}, timeout=120)
    if r.status_code == 404:
        sys.exit("Sheet not found: share it with the service account's email (Viewer) "
                 "and check GOOGLE_SHEET_ID.")
    if r.status_code == 403:
        sys.exit(f"Google refused access (403). Is the Google Drive API enabled for the "
                 f"service account's project? {r.text[:300]}")
    r.raise_for_status()
    return r.content


def fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, dt.datetime):
        return v.date().isoformat() if v.time() == dt.time() else v.isoformat(sep=" ")
    if isinstance(v, float):
        return f"{v:.6g}" if abs(v) < 1000 else f"{v:,.0f}"
    return str(v).replace("|", "/").replace("\n", " ")


def to_text(xlsx: bytes) -> str:
    wb = openpyxl.load_workbook(io.BytesIO(xlsx), data_only=True)
    out = [f"# Investment_Tracker export ({dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC)",
           "Values are what Google Sheets last calculated. Currency amounts in IDR unless a "
           "column says otherwise. Percentages are fractions (0.0235 = 2.35%).", ""]
    for name in TABS:
        if name not in wb.sheetnames:
            continue
        out.append(f"## {name}")
        for row in wb[name].iter_rows(values_only=True):
            vals = list(row)
            while vals and vals[-1] in (None, ""):
                vals.pop()
            if any(v not in (None, "") for v in vals):
                out.append(" | ".join(fmt(v) for v in vals))
        out.append("")
    return "\n".join(out)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("output")
    p.add_argument("--xlsx", help="use a local .xlsx file instead of downloading")
    args = p.parse_args()

    if args.xlsx:
        data = Path(args.xlsx).read_bytes()
    else:
        missing = [k for k in ("GOOGLE_SERVICE_ACCOUNT_JSON", "GOOGLE_SHEET_ID") if not os.environ.get(k)]
        if missing:
            sys.exit(f"Missing secret(s): {', '.join(missing)}")
        data = download_xlsx(os.environ["GOOGLE_SHEET_ID"].strip(), os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])

    text = to_text(data)
    if "## Holdings" not in text:
        sys.exit("The export has no Holdings tab - is GOOGLE_SHEET_ID the Investment_Tracker sheet?")
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(text)
    print(f"Wrote {args.output} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
