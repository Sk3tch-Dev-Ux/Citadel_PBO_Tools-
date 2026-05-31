"""Sanity checks for the BI LZSS decoder."""

from __future__ import annotations

from citadel.core import lzss


def _encode_literal(data: bytes) -> bytes:
    """Tiny helper: encode ``data`` as all-literal flag bytes for round-trip tests."""
    out = bytearray()
    pos = 0
    while pos < len(data):
        chunk = data[pos:pos + 8]
        flag = 0
        for i in range(len(chunk)):
            flag |= 1 << i
        out.append(flag)
        out.extend(chunk)
        pos += len(chunk)
    return bytes(out)


def test_all_literals_round_trip() -> None:
    payload = b"Hello, world!" * 10
    encoded = _encode_literal(payload)
    decoded = lzss.decompress(encoded, len(payload))
    assert decoded == payload


def test_truncates_to_expected_size() -> None:
    payload = b"abcdefgh" * 4
    encoded = _encode_literal(payload)
    decoded = lzss.decompress(encoded, 10)
    assert len(decoded) == 10
    assert decoded == payload[:10]


def test_zero_size_returns_empty() -> None:
    assert lzss.decompress(b"\xff" + b"A" * 8, 0) == b""
