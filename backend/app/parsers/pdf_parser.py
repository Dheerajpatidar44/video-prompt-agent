import pypdf

class PDFParser:
    @staticmethod
    def parse(file_path: str) -> str:
        text = ""
        try:
            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            raise ValueError(f"Failed to parse PDF: {str(e)}")
            
        if not text.strip():
            raise ValueError("No extractable text found in PDF.")
        return text
