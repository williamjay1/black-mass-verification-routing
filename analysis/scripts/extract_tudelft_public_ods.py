"""Extract the openly deposited TU Delft black-mass workbook tables.

Reads only the D-drive working copy of the public deposit and writes derived
CSV, README text, and source checksums under D:\\MLWork. The F-drive archive
is never modified.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "datasets" / "work_tudelft_58947_20260930" / "publication_files" / "Data for publication"
OUT = ROOT / "results" / "tudelft_58947_ods_extract_2026-09-30"

NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def cell_value(cell: ET.Element) -> str:
    office = NS["office"]
    for attr in ("value", "string-value", "date-value", "time-value", "boolean-value"):
        value = cell.get(f"{{{office}}}{attr}")
        if value is not None:
            return value
    paras = []
    for paragraph in cell.findall(".//text:p", NS):
        paras.append("".join(paragraph.itertext()).strip())
    return "\n".join(p for p in paras if p)


def parse_ods(path: Path) -> dict[str, list[list[str]]]:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("content.xml")
    root = ET.fromstring(xml)
    sheets: dict[str, list[list[str]]] = {}
    for sheet in root.findall(".//table:table", NS):
        name = sheet.get(f"{{{NS['table']}}}name", "sheet")
        rows: list[list[str]] = []
        for row in sheet.findall("table:table-row", NS):
            repeat_rows = int(row.get(f"{{{NS['table']}}}number-rows-repeated", "1"))
            values: list[str] = []
            for cell in list(row):
                if cell.tag not in {
                    f"{{{NS['table']}}}table-cell",
                    f"{{{NS['table']}}}covered-table-cell",
                }:
                    continue
                repeat_cols = int(cell.get(f"{{{NS['table']}}}number-columns-repeated", "1"))
                value = cell_value(cell)
                values.extend([value] * min(repeat_cols, 5000))
            while values and values[-1] == "":
                values.pop()
            if values:
                rows.extend([values.copy() for _ in range(min(repeat_rows, 1000))])
        sheets[name] = rows
    return sheets


def extract_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    paragraphs = []
    for para in root.findall(f".//{{{w_ns}}}p"):
        text = "".join(node.text or "" for node in para.iter(f"{{{w_ns}}}t"))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n".join(paragraphs)


def safe_name(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
    return value[:100] or "sheet"


def main() -> None:
    if not SOURCE.is_dir():
        raise FileNotFoundError(SOURCE)
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    for path in sorted(SOURCE.glob("*.ods")):
        sheets = parse_ods(path)
        for sheet_name, rows in sheets.items():
            width = max((len(row) for row in rows), default=0)
            out_path = OUT / f"{safe_name(path.stem)}__{safe_name(sheet_name)}.csv"
            with out_path.open("w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.writer(stream)
                for row in rows:
                    writer.writerow(row + [""] * (width - len(row)))
            records.append({
                "source_file": path.name,
                "source_sha256": sha256(path),
                "sheet_name": sheet_name,
                "output_csv": out_path.name,
                "nonempty_rows": len(rows),
                "maximum_columns": width,
                "first_rows": [row[:16] for row in rows[:10]],
            })
    readmes = []
    for path in sorted(SOURCE.glob("*.docx")):
        content = extract_docx(path)
        out_path = OUT / f"{safe_name(path.stem)}.txt"
        out_path.write_text(content, encoding="utf-8")
        readmes.append({"source_file": path.name, "source_sha256": sha256(path), "output_text": out_path.name,
                        "text": content})
    metadata = {
        "extraction_date": "2026-09-30",
        "deposit_dataset_doi": "10.4121/58947ce2-c651-43cc-8e4d-760b2e60adfb",
        "related_article_doi": "10.1039/d6ra04652e",
        "source_directory": str(SOURCE),
        "output_directory": str(OUT),
        "parser": "Python standard library ZIP/XML; repeated rows and columns expanded; no inferential processing",
        "sheets": records,
        "readmes": readmes,
    }
    (OUT / "extraction_inventory.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(OUT), "sheets": len(records), "readmes": len(readmes),
                      "rows": sum(item["nonempty_rows"] for item in records)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
