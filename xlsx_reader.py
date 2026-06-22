#!/usr/bin/env python3
"""
Created on Fri May 8th 2026

@author: Steven Li

=======================================================
Read data from an .xlsx worksheet into a list of dictionaries.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"m": MAIN_NS, "r": REL_NS, "o": OFFICE_REL_NS}
ArrayTable = list[dict[str, str]]


def _xml_root(workbook: zipfile.ZipFile, name: str) -> ET.Element:
    """Read an XML file inside the .xlsx archive and return its root element."""
    try:
        return ET.fromstring(workbook.read(name))
    except KeyError as exc:
        raise ValueError(f"Missing expected XLSX part: {name}") from exc
    except ET.ParseError as exc:
        raise ValueError(f"Could not parse XML part: {name}") from exc


def _column_number(cell_reference: str) -> int:
    """Convert an Excel cell reference such as 'A1' or 'AA4' to a column number."""
    match = re.match(r"([A-Z]+)", cell_reference.upper())
    if not match:
        return 1

    number = 0
    for char in match.group(1):
        number = number * 26 + (ord(char) - ord("A") + 1)
    return number


def _relationship_map(workbook: zipfile.ZipFile, rels_path: str) -> dict[str, str]:
    """Return a map from relationship ids to file paths inside the workbook."""
    root = _xml_root(workbook, rels_path)
    base_dir = posixpath.dirname(posixpath.dirname(rels_path))
    relationships: dict[str, str] = {}

    for rel in root.findall("r:Relationship", NS):
        rel_id = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if not rel_id or not target:
            continue

        # Relationship targets may be absolute within the archive or relative
        # to the workbook directory, so normalize both forms to archive paths.
        if target.startswith("/"):
            relationships[rel_id] = target.lstrip("/")
        else:
            relationships[rel_id] = posixpath.normpath(posixpath.join(base_dir, target))

    return relationships


def _shared_strings(workbook: zipfile.ZipFile) -> list[str]:
    """Read Excel's shared string table.

    Excel often stores repeated text values in `xl/sharedStrings.xml` and cells
    point to them by index. Workbooks that contain only numbers may not have
    this file at all.
    """
    try:
        root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    except ET.ParseError as exc:
        raise ValueError("Could not parse shared strings in the XLSX file") from exc

    strings: list[str] = []
    for item in root.findall("m:si", NS):
        parts = [node.text or "" for node in item.findall(".//m:t", NS)]
        strings.append("".join(parts))
    return strings


def _workbook_sheets(workbook: zipfile.ZipFile) -> list[tuple[str, str]]:
    """Return worksheet names with their matching XML paths inside the workbook."""
    root = _xml_root(workbook, "xl/workbook.xml")
    rels = _relationship_map(workbook, "xl/_rels/workbook.xml.rels")
    sheets: list[tuple[str, str]] = []

    for sheet in root.findall("m:sheets/m:sheet", NS):
        name = sheet.attrib.get("name")
        rel_id = sheet.attrib.get(f"{{{OFFICE_REL_NS}}}id")
        path = rels.get(rel_id or "")
        if name and path:
            sheets.append((name, path))

    return sheets


def _cell_value(cell: ET.Element, strings: list[str]) -> str:
    """Extract a cell's display value as text."""
    cell_type = cell.attrib.get("t")

    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//m:t", NS))

    value = cell.find("m:v", NS)
    if value is None or value.text is None:
        return ""

    # Shared-string cells store an integer index instead of the actual text.
    if cell_type == "s":
        try:
            return strings[int(value.text)]
        except (ValueError, IndexError):
            return ""

    if cell_type == "b":
        return "TRUE" if value.text == "1" else "FALSE"

    return value.text


def _worksheet_rows(
    workbook: zipfile.ZipFile, worksheet_path: str, strings: list[str]
) -> Iterable[list[str]]:
    """Yield worksheet rows as lists of cell values."""
    root = _xml_root(workbook, worksheet_path)

    for row in root.findall(".//m:sheetData/m:row", NS):
        values: list[str] = []
        for cell in row.findall("m:c", NS):
            column = _column_number(cell.attrib.get("r", ""))
            # Missing blank cells are omitted from the XML, so insert empty
            # values until the current cell lands in its proper column.
            while len(values) < column - 1:
                values.append("")
            values.append(_cell_value(cell, strings))
        yield values


def _unique_headers(headers: list[str]) -> list[str]:
    """Make header names safe for dictionary keys by filling blanks and duplicates."""
    seen: dict[str, int] = {}
    unique: list[str] = []

    for index, header in enumerate(headers, start=1):
        key = header.strip() or f"column_{index}"
        count = seen.get(key, 0)
        seen[key] = count + 1
        unique.append(key if count == 0 else f"{key}_{count + 1}")

    return unique


def rows_to_dicts(rows: list[list[str]], header_row: int = 1) -> ArrayTable:
    """Convert worksheet rows to dictionaries using the selected header row.

    Args:
        rows: Worksheet data where each inner list is one row of cell values.
        header_row: 1-based row number containing the column names.

    Returns:
        A list of dictionaries. Each dictionary represents one non-empty data
        row and uses the selected header row as keys.
    """
    if header_row < 1:
        raise ValueError("header_row must be 1 or greater")
    if len(rows) < header_row:
        return []

    headers = _unique_headers(rows[header_row - 1])
    records: ArrayTable = []

    for row in rows[header_row:]:
        record = {
            header: row[index] if index < len(row) else ""
            for index, header in enumerate(headers)
        }
        # Skip completely empty rows so callers only receive useful records.
        if any(value != "" for value in record.values()):
            records.append(record)

    return records


def read_xlsx_as_dicts(
    file_path: str | Path,
    sheet_name: str | None = None,
    header_row: int = 1,
) -> ArrayTable:
    """Read an .xlsx worksheet and return its data as a list of dictionaries.

    Args:
        file_path: Path to the `.xlsx` file.
        sheet_name: Optional worksheet name. If omitted, the first worksheet is
            used.
        header_row: 1-based row number containing the column names.

    Returns:
        A list of dictionaries where each dictionary is one row of worksheet
        data.

    Raises:
        ValueError: If the file is not `.xlsx`, the sheet cannot be found, or
        the workbook XML cannot be read.
    """
    xlsx_path = Path(file_path)
    if xlsx_path.suffix.lower() != ".xlsx":
        raise ValueError("Input file must be an .xlsx file")

    with zipfile.ZipFile(xlsx_path) as workbook:
        sheets = _workbook_sheets(workbook)
        if not sheets:
            return []

        # Choose the requested worksheet, or default to the first worksheet in
        # the workbook when the caller does not provide a sheet name.
        if sheet_name is None:
            worksheet_path = sheets[0][1]
        else:
            matches = [path for name, path in sheets if name == sheet_name]
            if not matches:
                available = ", ".join(name for name, _ in sheets)
                raise ValueError(f"Sheet '{sheet_name}' was not found. Available sheets: {available}")
            worksheet_path = matches[0]

        strings = _shared_strings(workbook)
        rows = list(_worksheet_rows(workbook, worksheet_path, strings))
        print(rows)
        return rows_to_dicts(rows, header_row)


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments for quick manual inspection."""
    parser = argparse.ArgumentParser(
        description="Read an .xlsx worksheet as a list of dictionaries."
    )
    parser.add_argument("input", type=Path, help="Path to the .xlsx file")
    parser.add_argument("-s", "--sheet", help="Worksheet name. Defaults to the first worksheet.")
    parser.add_argument(
        "--header-row",
        type=int,
        default=1,
        help="1-based row number containing column names. Defaults to 1.",
    )
    return parser.parse_args()


def run_cli() -> int:
    """Run the command-line interface and print the result as formatted JSON."""
    args = _parse_args()
    try:
        data = read_xlsx_as_dicts(args.input, sheet_name=args.sheet, header_row=args.header_row)
    except (ValueError, zipfile.BadZipFile) as exc:
        print(exc, file=sys.stderr)
        return 1

    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    print(read_xlsx_as_dicts("array_position_table.xlsx"))
