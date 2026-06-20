"""Export job results to Excel (.xlsx)."""

from __future__ import annotations

import csv
from pathlib import Path

from bot.reporting import CSV_COLUMNS

EXCEL_HEADERS = [
    "Time",
    "Job type",
    "Campaign",
    "List B page",
    "List B URL",
    "Target URL",
    "Target reached",
    "Final URL",
    "Success",
    "Device",
    "Error",
]


def xlsx_path_for_csv(csv_path: str | Path) -> Path:
    path = Path(csv_path)
    return path.with_suffix(".xlsx")


def sync_xlsx(csv_path: str | Path, xlsx_path: str | Path | None = None) -> Path:
    """Rebuild the Excel file from the current CSV results."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    csv_file = Path(csv_path)
    out = Path(xlsx_path) if xlsx_path else xlsx_path_for_csv(csv_file)
    out.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Results"

    header_font = Font(bold=True)
    ws.append(EXCEL_HEADERS)
    for cell in ws[1]:
        cell.font = header_font

    if csv_file.exists() and csv_file.stat().st_size > 0:
        with csv_file.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ws.append([row.get(col, "") for col in CSV_COLUMNS])

    for column in ws.columns:
        max_len = 0
        letter = column[0].column_letter
        for cell in column:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[letter].width = min(max_len + 2, 50)

    wb.save(out)
    return out
