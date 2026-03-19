import os
from typing import Optional

import fitz  # PyMuPDF
from PIL import Image
import pytesseract


class MultiModalParser:
    """
    Handles:
    - plain text
    - PDFs
    - images
    """

    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}

    def parse(self, raw_text: Optional[str] = None, file_path: Optional[str] = None) -> str:
        """
        Returns extracted text from either:
        - raw_text directly
        - file_path (PDF/image/text)
        """
        if file_path:
            ext = os.path.splitext(file_path)[1].lower()

            if ext == ".pdf":
                return self._parse_pdf(file_path)

            if ext in self.IMAGE_EXTENSIONS:
                return self._parse_image(file_path)

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()

        return raw_text or ""

    def _parse_pdf(self, file_path: str) -> str:
        try:
            doc = fitz.open(file_path)
            text = [page.get_text("text") for page in doc]
            return "\n".join(text).strip()
        except Exception as e:
            return f"[PDF Error: {str(e)}]"

    def _parse_image(self, file_path: str) -> str:
        try:
            image = Image.open(file_path).convert("L")
            return pytesseract.image_to_string(image).strip()
        except Exception as e:
            return f"[OCR Error: {str(e)}]"