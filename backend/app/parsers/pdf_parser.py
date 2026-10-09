import pdfplumber
import pypdfium2 as pdfium
import base64
import os
from io import BytesIO
from app.llm.claude_client import llm_service

class PDFParser:
    @staticmethod
    async def parse(file_path: str) -> str:
        # 1. File Size Validation (Max 50MB) to prevent memory crash
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > 50:
            raise ValueError(f"File size ({file_size_mb:.1f}MB) exceeds the maximum allowed size of 50MB.")

        text = PDFParser._extract_with_pdfplumber(file_path)

        # 2. Smart Length Checking: If text is extremely short (less than 15 chars), 
        # it might be an image-only PDF, so fallback to vision.
        if not text or len(text.strip()) < 15:
            text = await PDFParser._extract_with_vision(file_path)

        if not text or not text.strip():
            raise ValueError(
                "No extractable text found in PDF, even after AI Vision extraction. "
                "The file may be corrupted or empty."
            )
        return text

    @staticmethod
    def _extract_with_pdfplumber(file_path: str) -> str:
        text = ""
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    # 3. Use layout=True to preserve table structures and prevent columns from mixing
                    page_text = page.extract_text(layout=True)
                    
                    # If layout extraction fails or returns nothing, fallback to standard extraction
                    if not page_text or not page_text.strip():
                        page_text = page.extract_text()
                        
                    if page_text:
                        text += page_text + "\n\n"
        except Exception as e:
            # We don't raise here, we just return empty so it falls back to vision
            print(f"pdfplumber failed: {e}")
        return text

    @staticmethod
    async def _extract_with_vision(file_path: str) -> str:
        """Fallback for scanned/flattened PDFs using pypdfium2 + Claude Vision"""
        try:
            base64_images = []
            pdf = pdfium.PdfDocument(file_path)
            
            # Limit to first 10 pages to avoid massive token consumption if someone uploads a huge PDF
            max_pages = min(len(pdf), 10)
            
            if len(pdf) > 10:
                print(f"Warning: PDF has {len(pdf)} pages. AI Vision OCR is limited to the first 10 pages to prevent excessive costs.")
            
            for i in range(max_pages):
                page = pdf[i]
                # scale=2 gives good clarity for OCR
                bitmap = page.render(scale=2)
                pil_image = bitmap.to_pil()
                
                # Convert to base64
                buffered = BytesIO()
                pil_image.save(buffered, format="PNG")
                img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
                base64_images.append(img_str)
                
            pdf.close()
            
            if not base64_images:
                return ""
                
            # Call Claude Vision
            text = await llm_service.extract_text_from_images(base64_images)
            return text
        except Exception as e:
            raise ValueError(f"Failed to perform AI Vision extraction on PDF: {str(e)}")