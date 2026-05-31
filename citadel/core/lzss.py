"""Decoder for BI LZSS-compressed PBO entries (the ``Cprs`` packing mode).

PboProject and similar tools may compress entries such as ``.rvmat`` files
using a BI variant of LZSS. This module decodes those bytes back to their
original form.

The algorithm is the standard BI LZSS:
  - Read a flag byte (8 bits, LSB first).
  - For each bit:
      bit = 1 -> emit a literal byte from the input.
      bit = 0 -> read two bytes; high 4 bits of byte 2 + byte 1 = offset,
                 low 4 bits of byte 2 + 3 = run length; copy from a ring
                 buffer at the given offset.
  - The ring buffer starts pre-filled with 0x20 (space) for the first
    (BUF_SIZE - 18) bytes.
  - Output is truncated to ``expected_size`` bytes.

The original archives also carry a 4-byte CRC sum trailing the compressed
data, but that is part of the PBO entry framing and not the LZSS stream
itself.
"""

from __future__ import annotations

BUFFER_SIZE = 4096
RUN_LENGTH_MIN = 3
FILL_BYTE = 0x20


def decompress(data: bytes, expected_size: int) -> bytes:
    """Decode BI LZSS ``data`` to ``expected_size`` bytes."""
    if expected_size <= 0:
        return b""

    output = bytearray()
    buffer = bytearray([FILL_BYTE] * BUFFER_SIZE)
    buffer_pos = BUFFER_SIZE - 18  # standard BI initial write head
    data_pos = 0
    data_len = len(data)

    while len(output) < expected_size and data_pos < data_len:
        flag_byte = data[data_pos]
        data_pos += 1

        for bit_index in range(8):
            if len(output) >= expected_size:
                break

            bit = (flag_byte >> bit_index) & 1
            if bit:
                # Literal
                if data_pos >= data_len:
                    return bytes(output)
                byte = data[data_pos]
                data_pos += 1
                output.append(byte)
                buffer[buffer_pos] = byte
                buffer_pos = (buffer_pos + 1) % BUFFER_SIZE
            else:
                # Back-reference
                if data_pos + 1 >= data_len:
                    return bytes(output)
                b1 = data[data_pos]
                b2 = data[data_pos + 1]
                data_pos += 2
                offset = ((b2 & 0xF0) << 4) | b1
                run = (b2 & 0x0F) + RUN_LENGTH_MIN
                for run_index in range(run):
                    if len(output) >= expected_size:
                        break
                    src = (offset + run_index) % BUFFER_SIZE
                    byte = buffer[src]
                    output.append(byte)
                    buffer[buffer_pos] = byte
                    buffer_pos = (buffer_pos + 1) % BUFFER_SIZE

    return bytes(output[:expected_size])
