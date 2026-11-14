"""
Converts candidate profiles and the JD into dense vector embeddings
using a local sentence-transformer model (no API calls, no GPU needed).
"""

import hashlib
import json
import os
import tempfile
from zipfile import BadZipFile

import numpy as np
from pathlib import Path
from tqdm import tqdm
from sentence_transformers import SentenceTransformer

CACHE_DIR = Path(__file__).parent.parent / "cache"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
# Pin the immutable model revision so cache identity matches the loaded weights.
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
CACHE_FORMAT_VERSION = 1


def load_model() -> SentenceTransformer:
    print(f"Loading embedding model: {MODEL_NAME}@{MODEL_REVISION}")
    model = SentenceTransformer(MODEL_NAME, revision=MODEL_REVISION)
    model._embedding_cache_identity = {"name": MODEL_NAME, "revision": MODEL_REVISION}
    return model


def _cache_path(kind, model, records):
    """Hash framed JSON records in order, without building a second full text copy."""
    identity = getattr(model, "_embedding_cache_identity", None)
    if not identity or not identity.get("name") or not identity.get("revision"):
        # An arbitrary unversioned encoder cannot safely share persistent entries.
        raise ValueError("Caching requires a model name and immutable revision")
    digest = hashlib.sha256()
    header = {"version": CACHE_FORMAT_VERSION, "kind": kind, "model": identity,
              "dimension": model.get_sentence_embedding_dimension(), "normalize": True}
    digest.update(json.dumps(header, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8"))
    digest.update(b"\n")
    for record in records:
        digest.update(json.dumps(record, ensure_ascii=False,
                                 separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return CACHE_DIR / f"{kind}_v{CACHE_FORMAT_VERSION}_{digest.hexdigest()}.npy"


def _valid_array(array, shape):
    return (array.shape == shape and np.issubdtype(array.dtype, np.floating)
            and np.isfinite(array).all())


def _read_cache(path, shape):
    try:
        array = np.load(path, allow_pickle=False)
        if isinstance(array, np.ndarray) and _valid_array(array, shape):
            print(f"Embedding cache hit: {path}")
            return array
        if hasattr(array, "close"):
            array.close()
        print(f"Invalid embedding cache; recomputing: {path}")
    except FileNotFoundError:
        print(f"Embedding cache miss: {path}")
    except (OSError, ValueError, EOFError, BadZipFile) as exc:
        print(f"Unreadable embedding cache; recomputing: {path} ({exc})")
    return None


def _write_cache(path, array):
    """Publish a complete array with same-filesystem atomic replacement.

    Concurrent misses may duplicate encoding, but readers see only whole files.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".embedding-",
                                         suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            np.save(handle, array, allow_pickle=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        print(f"Embedding cache written: {path}")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def build_candidate_text(candidate: dict) -> str:
    """
    Converts a candidate record into a single string for embedding.
    Weights important fields by repeating them.
    """
    p = candidate["profile"]
    skills = candidate.get("skills", [])
    career = candidate.get("career_history", [])
    edu = candidate.get("education", [])
    certs = candidate.get("certifications", [])

    # Skills string — repeat expert/advanced skills for emphasis
    skill_parts = []
    for s in skills:
        name = s["name"]
        if s["proficiency"] in ("expert", "advanced"):
            skill_parts.extend([name, name])  # repeat for weight
        else:
            skill_parts.append(name)
    skills_text = " ".join(skill_parts)

    # Career descriptions — most important signal
    career_parts = []
    for job in career:
        career_parts.append(
            f"{job['title']} at {job['company']}: {job['description']}"
        )
    career_text = " | ".join(career_parts)

    # Education
    edu_text = " ".join(
        f"{e['degree']} in {e['field_of_study']} from {e['institution']}"
        for e in edu
    )

    # Certifications
    cert_text = " ".join(c["name"] for c in certs)

    return (
        f"{p['headline']} {p['summary']} "
        f"Current role: {p['current_title']} at {p['current_company']} "
        f"Industry: {p['current_industry']} "
        f"Skills: {skills_text} "
        f"Career: {career_text} "
        f"Education: {edu_text} "
        f"Certifications: {cert_text}"
    )


def encode_candidates(
    candidates: list[dict],
    model: SentenceTransformer,
    batch_size: int = 256,
    cache: bool = True,
) -> np.ndarray:

    print("Building candidate texts...")
    texts = [build_candidate_text(c) for c in tqdm(candidates, desc="Building texts")]
    shape = (len(candidates), model.get_sentence_embedding_dimension())
    cache_path = None
    if cache:
        cache_path = _cache_path("candidates", model,
                                 ([c["candidate_id"], text]
                                  for c, text in zip(candidates, texts)))
        cached = _read_cache(cache_path, shape)
        if cached is not None:
            return cached
    else:
        print("Embedding cache bypass: candidates (reads and writes disabled)")

    print(f"Encoding {len(texts):,} candidates (batch_size={batch_size})...")
    embeddings = model.encode(texts, batch_size=batch_size,
                              show_progress_bar=True, normalize_embeddings=True)
    if not _valid_array(embeddings, shape):
        raise ValueError(f"Encoder returned invalid candidate embeddings; expected {shape}")
    if cache_path is not None:
        _write_cache(cache_path, embeddings)
    return embeddings


def encode_jd(
    jd_text: str,
    model: SentenceTransformer,
    cache: bool = True,
) -> np.ndarray:
    shape = (model.get_sentence_embedding_dimension(),)
    cache_path = _cache_path("jd", model, [jd_text]) if cache else None
    if cache_path is not None:
        cached = _read_cache(cache_path, shape)
        if cached is not None:
            return cached
    else:
        print("Embedding cache bypass: JD (reads and writes disabled)")
    print("Encoding JD...")
    embedding = model.encode([jd_text], normalize_embeddings=True)[0]
    if not _valid_array(embedding, shape):
        raise ValueError(f"Encoder returned invalid JD embedding; expected {shape}")
    if cache_path is not None:
        _write_cache(cache_path, embedding)
    return embedding


def cosine_similarities(
    jd_vec: np.ndarray,
    candidate_vecs: np.ndarray,
) -> np.ndarray:
    """Fast dot product similarity (vectors are already normalized)."""
    return candidate_vecs @ jd_vec
