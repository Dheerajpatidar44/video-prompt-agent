import os
import re
import pdfplumber
import pypdfium2 as pdfium
import numpy as np
from typing import List, Optional


_ocr_engine = None      

 
def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine = RapidOCR()
        except ImportError:
            raise ImportError(
                "rapidocr-onnxruntime is not installed. Please run: pip install rapidocr-onnxruntime"
            )
    return _ocr_engine


class PDFParser:
    @staticmethod
    async def parse(file_path: str) -> str:
        # 1. File Size Validation (Max 50MB) to prevent memory crash
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > 50:
            raise ValueError(f"File size ({file_size_mb:.1f}MB) exceeds the maximum allowed size of 50MB.")

        # 2. Digital Text & Table Extraction (Primary local method - fast, exact, 0 API calls)
        text = PDFParser._extract_with_pdfplumber(file_path)

        # 3. Smart Length Checking: If text is extremely short (< 15 chars),
        # it is likely a scanned / flattened image PDF -> fallback to local Python OCR
        if not text or len(text.strip()) < 15:
            text = PDFParser._extract_with_local_ocr(file_path)

        if not text or not text.strip():
            raise ValueError(
                "No extractable text found in PDF, even after Local Python OCR. "
                "The file may be corrupted, blank, or unreadable."
            )
        return text

    @staticmethod
    def _clean_cell(cell: Optional[str]) -> str:
        """Cleans internal line-breaks and whitespace in table cells."""
        if cell is None:
            return ""
        # Convert internal newlines to spaces and normalize spaces
        cleaned = str(cell).replace("\r", " ").replace("\n", " ")
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        # Escape pipe characters to keep markdown table layout intact
        return cleaned.replace("|", "\\|")

    @staticmethod
    def _format_table_as_markdown(table: List[List[Optional[str]]]) -> str:
        """Converts extracted 2D table grid into a clean, structured Markdown table."""
        if not table or not any(table):
            return ""

        clean_rows = []
        for row in table:
            clean_row = [PDFParser._clean_cell(cell) for cell in row]
            # Ignore completely blank rows
            if any(clean_row):
                clean_rows.append(clean_row)

        if not clean_rows:
            return ""

        # Normalize column count across all rows
        max_cols = max(len(row) for row in clean_rows)
        if max_cols == 0:
            return ""

        normalized_rows = [row + [""] * (max_cols - len(row)) for row in clean_rows]

        md_lines = []
        # Header row
        header = normalized_rows[0]
        md_lines.append("| " + " | ".join(header) + " |")
        md_lines.append("| " + " | ".join(["---"] * max_cols) + " |")

        # Body rows
        for row in normalized_rows[1:]:
            md_lines.append("| " + " | ".join(row) + " |")

        return "\n".join(md_lines)

    @staticmethod
    def _extract_page_content(page, page_idx: int) -> str:
        """Extracts text and tables from a single page preserving visual layout."""
        try:
            tables = page.find_tables()
        except Exception:
            tables = []

        if not tables:
            # Simple text page without grid tables
            page_text = page.extract_text(layout=True)
            if not page_text or not page_text.strip():
                page_text = page.extract_text()
            return page_text.strip() if page_text else ""

        # Page has structured tables (like AV script with Timestamp, Visual, Audio)
        # Sort tables from top to bottom
        tables = sorted(tables, key=lambda t: t.bbox[1])
        parts = []
        current_top = 0.0

        for t in tables:
            x0, top, x1, bottom = t.bbox

            # Extract any narrative/header text above this table
            if top > current_top + 4:
                try:
                    top_crop = page.crop((0, current_top, page.width, top))
                    text_above = top_crop.extract_text(layout=True)
                    if text_above and text_above.strip():
                        parts.append(text_above.strip())
                except Exception:
                    pass

            # Extract table grid and format as Markdown
            raw_table = t.extract()
            if raw_table:
                md_table = PDFParser._format_table_as_markdown(raw_table)
                if md_table:
                    parts.append(md_table)

            current_top = max(current_top, bottom)

        # Extract any footer / disclaimer / compliance text below the last table
        if current_top < page.height - 4:
            try:
                bottom_crop = page.crop((0, current_top, page.width, page.height))
                text_below = bottom_crop.extract_text(layout=True)
                if text_below and text_below.strip():
                    parts.append(text_below.strip())
            except Exception:   
                pass

        return "\n\n".join(parts)

    @staticmethod
    def _extract_with_pdfplumber(file_path: str) -> str:
        """Extracts text and formatted tables across all pages of a digital PDF."""
        extracted_pages = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for idx, page in enumerate(pdf.pages):
                    page_content = PDFParser._extract_page_content(page, idx)
                    if page_content:
                        extracted_pages.append(page_content)
        except Exception as e:
            print(f"pdfplumber extraction warning: {e}")

        return "\n\n---\n\n".join(extracted_pages)

    @staticmethod
    def _extract_with_local_ocr(file_path: str) -> str:
        """Fallback for scanned / image-based PDFs using pypdfium2 + RapidOCR locally (No Claude)."""
        ocr = _get_ocr_engine()
        extracted_pages = []
        pdf = None

        try:
            pdf = pdfium.PdfDocument(file_path)
            max_pages = min(len(pdf), 15)

            for i in range(max_pages):
                page = pdf[i]
                try:
                    bitmap = page.render(scale=2.0)
                    try:
                        pil_image = bitmap.to_pil()
                        img_np = np.array(pil_image)
                        
                        result, _ = ocr(img_np)

                        if result:
                            lines = [line[1] for line in result if line[1].strip()]
                            if lines:
                                extracted_pages.append(f"--- Page {i + 1} (Scanned OCR) ---\n" + "\n".join(lines))
                    finally:
                        bitmap.close()
                finally:
                    page.close()

            return "\n\n".join(extracted_pages)
        except Exception as e:
            raise ValueError(f"Local Python OCR extraction failed: {str(e)}")
        finally:
            if pdf is not None:
                pdf.close()