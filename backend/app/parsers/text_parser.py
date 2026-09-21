class TextParser:
    @staticmethod
    def parse(file_path: str) -> str:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            raise ValueError(f"Failed to read TXT file: {str(e)}")
            
        if not text.strip():
            raise ValueError("The text file is empty.")
        return text
