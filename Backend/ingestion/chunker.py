import re


class Chunker:
    def __init__(self, max_chunk_size=300):
        self.max_chunk_size = max_chunk_size

    def chunk_text(self, text: str):
        # Step 1: Split by paragraphs
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

        chunks = []

        for para in paragraphs:
            if len(para) <= self.max_chunk_size:
                chunks.append(para)
            else:
                # If paragraph too long, split by sentences
                sentences = re.split(r'(?<=[.!?]) +', para)
                temp_chunk = ""

                for sentence in sentences:
                    if len(temp_chunk) + len(sentence) < self.max_chunk_size:
                        temp_chunk += " " + sentence
                    else:
                        chunks.append(temp_chunk.strip())
                        temp_chunk = sentence

                if temp_chunk:
                    chunks.append(temp_chunk.strip())

        return chunks
