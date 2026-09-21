import os
import uuid
import re
from app.parsers.pdf_parser import PDFParser
from app.parsers.text_parser import TextParser
from app.schemas.script import ScriptDocument

class ScriptService:
    @staticmethod
    def normalize_text(text: str) -> str:
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        return text.strip()

    @staticmethod
    def ingest_file(file_path: str, source_type: str, filename: str) -> ScriptDocument:
        if not os.path.exists(file_path):
            raise ValueError("File does not exist.")
            
        if source_type.lower() == "pdf":
            original_text = PDFParser.parse(file_path)
        elif source_type.lower() in ["txt", "text"]:
            original_text = TextParser.parse(file_path)
        else:
            raise ValueError(f"Unsupported source type: {source_type}")
            
        return ScriptService.ingest_text(original_text, source_type, filename)
        
    @staticmethod
    def ingest_text(original_text: str, source_type: str = "text", filename: str = "raw_text") -> ScriptDocument:
        if not original_text.strip():
            raise ValueError("Input text is empty.")
            
        normalized = ScriptService.normalize_text(original_text)
        
        return ScriptDocument(
            document_id=str(uuid.uuid4()),
            source_type=source_type,
            filename=filename,
            original_text=original_text,
            normalized_text=normalized
        )
