"""Offline cache regressions: no SentenceTransformer is instantiated."""
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from pipeline import encoder
import server


class FakeEncoder:
    def __init__(self, name="fake", revision="commit-1", dimension=4):
        self._embedding_cache_identity = {"name": name, "revision": revision}
        self.dimension = dimension
        self.calls = []

    def get_sentence_embedding_dimension(self):
        return self.dimension

    def encode(self, texts, **kwargs):
        self.calls.append(list(texts))
        vectors = np.array([list(hashlib.sha256(t.encode()).digest()[:self.dimension])
                            for t in texts], dtype=np.float32)
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name) / "cache"
        self.patch = patch.object(encoder, "CACHE_DIR", self.cache)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.model = FakeEncoder()
        sample = Path(__file__).resolve().parents[1] / "sample_candidates.json"
        self.candidates = json.loads(sample.read_text())[:2]

    def test_genuine_hits_and_new_model_instance(self):
        expected = encoder.encode_candidates(self.candidates, self.model)
        jd = encoder.encode_jd("exact JD", self.model)
        other = FakeEncoder()
        np.testing.assert_array_equal(expected, encoder.encode_candidates(self.candidates, other))
        np.testing.assert_array_equal(jd, encoder.encode_jd("exact JD", other))
        self.assertEqual(other.calls, [])

    def test_candidate_identity_changes(self):
        encoder.encode_candidates(self.candidates, self.model)
        different_ids = copy.deepcopy(self.candidates)
        different_ids[0]["candidate_id"] = "CAND_9999999"
        changed_text = copy.deepcopy(self.candidates)
        changed_text[0]["profile"]["summary"] += " changed exact text\n"
        for changed in (different_ids, list(reversed(self.candidates)), changed_text):
            with self.subTest(ids=[c["candidate_id"] for c in changed]):
                before = len(self.model.calls)
                encoder.encode_candidates(changed, self.model)
                self.assertEqual(len(self.model.calls), before + 1)
        self.assertEqual(len(list(self.cache.glob('candidates_*.npy'))), 4)

    def test_exact_jd_text(self):
        for text in ("JD", "JD ", "JD\n"):
            encoder.encode_jd(text, self.model)
        self.assertEqual(len(self.model.calls), 3)

    def test_model_name_revision_dimension_and_format_version(self):
        encoder.encode_candidates(self.candidates, self.model)
        encoder.encode_jd("JD", self.model)
        for model in (FakeEncoder(name="other"), FakeEncoder(revision="commit-2"),
                      FakeEncoder(dimension=3)):
            encoder.encode_candidates(self.candidates, model)
            encoder.encode_jd("JD", model)
            self.assertEqual(len(model.calls), 2)
        with patch.object(encoder, "CACHE_FORMAT_VERSION", 2):
            encoder.encode_candidates(self.candidates, self.model)
            encoder.encode_jd("JD", self.model)
        self.assertEqual(len(self.model.calls), 4)

    def test_invalid_arrays_and_corrupt_files_recomputed(self):
        for kind in ("candidates", "jd"):
            encode = (lambda: encoder.encode_candidates(self.candidates, self.model)) if kind == "candidates" else (lambda: encoder.encode_jd("JD", self.model))
            expected = encode()
            path = next(self.cache.glob(f"{kind}_*.npy"))
            invalid = [np.zeros((1,)), np.zeros(expected.shape, dtype=np.int64),
                       np.zeros(expected.shape, dtype=object),
                       np.full(expected.shape, np.nan), np.full(expected.shape, np.inf),
                       np.zeros((*expected.shape[:-1], expected.shape[-1] + 1))]
            for array in invalid:
                with self.subTest(kind=kind, shape=array.shape, dtype=str(array.dtype)):
                    np.save(path, array)
                    before = len(self.model.calls)
                    np.testing.assert_array_equal(encode(), expected)
                    self.assertEqual(len(self.model.calls), before + 1)
            for corrupt in (b"not an npy file", b"PK\x03\x04broken zip", path.read_bytes()[:-7]):
                path.write_bytes(corrupt)
                before = len(self.model.calls)
                np.testing.assert_array_equal(encode(), expected)
                self.assertEqual(len(self.model.calls), before + 1)

    def test_legacy_files_untouched(self):
        self.cache.mkdir()
        legacy = {self.cache / 'candidate_embeddings_2.npy': b'legacy candidates',
                  self.cache / 'jd_embedding.npy': b'legacy JD'}
        for path, data in legacy.items():
            path.write_bytes(data)
        encoder.encode_candidates(self.candidates, self.model)
        encoder.encode_jd("JD", self.model)
        self.assertEqual(len(self.model.calls), 2)
        for path, data in legacy.items():
            self.assertEqual(path.read_bytes(), data)

    def test_no_cache_bypasses_reads_and_writes(self):
        encoder.encode_candidates(self.candidates, self.model, cache=False)
        encoder.encode_jd("JD", self.model, cache=False)
        self.assertFalse(self.cache.exists())
        encoder.encode_candidates(self.candidates, self.model)
        encoder.encode_jd("JD", self.model)
        before = {p.name: p.read_bytes() for p in self.cache.iterdir()}
        calls = len(self.model.calls)
        encoder.encode_candidates(self.candidates, self.model, cache=False)
        encoder.encode_jd("JD", self.model, cache=False)
        self.assertEqual(len(self.model.calls), calls + 2)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.cache.iterdir()})

    def test_atomic_publication_and_cleanup(self):
        self.cache.mkdir()
        path = self.cache / 'entry.npy'
        old, new = np.ones((2, 4)), np.zeros((2, 4))
        np.save(path, old)
        replace = os.replace
        def inspect_replace(source, destination):
            self.assertEqual(Path(source).parent, path.parent)
            np.testing.assert_array_equal(np.load(destination), old)
            np.testing.assert_array_equal(np.load(source), new)
            replace(source, destination)
        with patch.object(encoder.os, 'replace', side_effect=inspect_replace):
            encoder._write_cache(path, new)
        np.testing.assert_array_equal(np.load(path), new)
        with patch.object(encoder.os, 'replace', side_effect=OSError('test failure')):
            with self.assertRaises(OSError):
                encoder._write_cache(path, old)
        self.assertEqual(list(self.cache.iterdir()), [path])

    def test_concurrent_writers_publish_complete_arrays(self):
        self.cache.mkdir()
        path = self.cache / 'shared.npy'
        initial = np.zeros((20, 4), dtype=np.float32)
        np.save(path, initial)
        def write(value):
            encoder._write_cache(path, np.full(initial.shape, value, dtype=np.float32))
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(write, value) for value in range(1, 9)]
            while not all(f.done() for f in futures):
                current = np.load(path, allow_pickle=False)
                self.assertEqual(current.shape, initial.shape)
                self.assertTrue(np.all(current == current[0, 0]))
            for future in futures:
                future.result()
        self.assertEqual(list(self.cache.iterdir()), [path])

    def test_request_reloads_file_even_with_same_size_and_mtime(self):
        path = Path(self.temp.name) / 'sample.json'
        path.write_text(json.dumps(self.candidates))
        original_stat = path.stat()
        request = server.RankRequest(data_path=str(path), is_sample=True, top_n=2, use_llm=False)
        with patch.object(server, 'get_model', return_value=self.model):
            first = server.api_rank(request)
            changed = copy.deepcopy(self.candidates)
            old = changed[0]['profile']['headline']
            changed[0]['profile']['headline'] = 'X' * len(old)
            path.write_text(json.dumps(changed))
            self.assertEqual(path.stat().st_size, original_stat.st_size)
            os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
            second = server.api_rank(request)
        by_id = {r['candidate_id']: r for r in second['results']}
        self.assertEqual(by_id[changed[0]['candidate_id']]['headline'], 'X' * len(old))
        self.assertNotEqual(first['results'], second['results'])
        # First JD + candidates, then only changed candidates (JD cache hit).
        self.assertEqual(len(self.model.calls), 3)


if __name__ == '__main__':
    unittest.main()
