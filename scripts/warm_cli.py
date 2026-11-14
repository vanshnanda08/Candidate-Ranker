"""Run the unchanged CLI with real model loading, forbidding any cache-miss encode."""
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rank

if __name__ == "__main__":
    with patch("pipeline.encoder.SentenceTransformer.encode", side_effect=RuntimeError(
            "Warm-only verification stopped: an embedding cache missed. Diagnose its identity before encoding.")):
        rank.main()
