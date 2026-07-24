from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import wanbang_douyin_batch_download as wanbang  # noqa: E402


class FakeResponse:
    def __init__(self, chunks: list[bytes | BaseException]) -> None:
        self.chunks = iter(chunks)

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self, _size: int) -> bytes:
        value = next(self.chunks, b"")
        if isinstance(value, BaseException):
            raise value
        return value


class AtomicDownloadTests(unittest.TestCase):
    def test_nonempty_invalid_file_is_not_reusable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "partial.mp4"
            path.write_bytes(b"not-an-mp4" * 200)

            self.assertFalse(wanbang.validate_mp4_file(path))

    def test_interrupted_download_removes_partial_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "gid.mp4"
            response = FakeResponse([b"x" * 2048, OSError("connection reset")])

            with mock.patch.object(wanbang.urllib.request, "urlopen", return_value=response):
                with self.assertRaisesRegex(OSError, "connection reset"):
                    wanbang.download_file("https://example.test/video", target)

            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix(".mp4.part").exists())

    def test_success_replaces_part_file_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "gid.mp4"
            response = FakeResponse([b"x" * 2048, b""])

            with (
                mock.patch.object(wanbang.urllib.request, "urlopen", return_value=response),
                mock.patch.object(wanbang, "validate_mp4_file", return_value=True),
            ):
                size = wanbang.download_file("https://example.test/video", target)

            self.assertEqual(size, 2048)
            self.assertTrue(target.exists())
            self.assertFalse(target.with_suffix(".mp4.part").exists())


if __name__ == "__main__":
    unittest.main()
