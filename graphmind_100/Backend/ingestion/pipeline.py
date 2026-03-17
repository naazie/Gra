"""
GraphMind — Ingestion Pipeline v4.0
Improvements vs v3:
  - Passes user_id to add_custom_relation so Gemini-extracted Concept nodes
    are user-scoped (fixes the cross-user concept leak).
  - Calls compute_graph_scores() after ingestion to refresh decay_score.
  - Ghost/commented code removed.
"""

import os
import sys
import time
import uuid
from typing import Optional, List, Dict

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from embeddings.embedder import Embedder
from vector_store.faiss_mgr import FAISSManager
from ingestion.chunker import Chunker
from ingestion.multimodal_parser import MultiModalParser
from graph_engine import GraphEngine
from relation_extractor import extract_relationships


class IngestionPipeline:
    def __init__(self, dimension: int = 768):
        self.embedder     = Embedder()
        self.vector_store = FAISSManager(dimension=dimension)
        self.chunker      = Chunker()
        self.parser       = MultiModalParser()
        self.graph_engine = GraphEngine()

    def ingest(
        self,
        user_id: str,
        raw_text: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> List[Dict]:
        """
        §1.2B — Full ingestion pipeline.
        Accepts plain text OR a file path (PDF / image / txt).
        Returns list of ingested node dicts for the API response preview.
        """
        t0 = time.time()

        parsed_text = self.parser.parse(raw_text=raw_text, file_path=file_path)
        if not parsed_text.strip():
            print("[pipeline] Empty input — nothing to ingest.")
            return []

        chunks         = self.chunker.chunk_text(parsed_text)
        ingested_nodes: List[Dict] = []

        print(f"[pipeline] Processing {len(chunks)} chunks for user '{user_id}'")

        for i, chunk in enumerate(chunks):
            if i > 0:
                time.sleep(4)   # rate-limit buffer for Gemini free tier

            node_id = str(uuid.uuid4())

            vector = self.embedder.embed(text=chunk)
            self.vector_store.add_vector(
                user_id=user_id,
                node_id=node_id,
                vector=vector,
                text=chunk,
            )

            relations = extract_relationships(chunk)

            extracted_concepts = list({
                word.strip(",.!?").capitalize()
                for word in chunk.split()
                if len(word) > 3
            })[:20]

            self.graph_engine.store_memory(
                username=user_id,
                memory_id=node_id,
                content=chunk,
                concepts=extracted_concepts,
                confidence_score=1.0,
            )

            for item in relations:
                rel_type = item.get("rel", "RELATED_TO").upper().replace(" ", "_")
                self.graph_engine.add_custom_relation(
                    memory_id=node_id,
                    subj=item.get("subj", "Unknown"),
                    rel=rel_type,
                    obj=item.get("obj", "Unknown"),
                    confidence=item.get("confidence", 0.8),
                    user_id=user_id,           # ensures user-scoped Concept nodes
                )

            ingested_nodes.append({"node_id": node_id, "text": chunk})

        # Refresh centrality + decay scores after ingestion
        self.graph_engine.compute_graph_scores()

        elapsed_ms = round((time.time() - t0) * 1000, 2)
        print(f"[pipeline] Done in {elapsed_ms}ms — {len(ingested_nodes)} nodes")

        return ingested_nodes

    def delete_node(self, user_id: str, node_id: str):
        """Synchronised deletion: removes from FAISS index and Neo4j."""
        self.vector_store.remove_vector(user_id=user_id, node_id=node_id)
        self.graph_engine.delete_memory(username=user_id, memory_id=node_id)
        print(f"[pipeline] Memory {node_id} deleted.")
