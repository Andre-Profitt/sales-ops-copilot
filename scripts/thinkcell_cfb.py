"""Minimal Compound File Binary stream editing for think-cell OLE blobs.

think-cell stores chart state in an OLE/CFB stream named ``think-cellXML``.
This helper only supports regular FAT streams that already have enough sector
capacity for the edited payload. It deliberately does not allocate new sectors.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
DIFSECT = 0xFFFFFFFC
CFB_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")


@dataclass(frozen=True)
class CfbStreamEdit:
    name: str
    replacements: tuple[tuple[bytes, bytes], ...]


@dataclass(frozen=True)
class CfbEditResult:
    data: bytes
    streams_touched: int
    replacements_made: int


class CompoundFileBinary:
    def __init__(self, data: bytes) -> None:
        if data[:8] != CFB_MAGIC:
            raise ValueError("not a Compound File Binary document")
        self._data = bytearray(data)
        self._sector_size = 1 << struct.unpack_from("<H", self._data, 0x1E)[0]
        self._num_fat_sectors = struct.unpack_from("<I", self._data, 0x2C)[0]
        self._first_dir_sector = struct.unpack_from("<I", self._data, 0x30)[0]
        self._mini_stream_cutoff = struct.unpack_from("<I", self._data, 0x38)[0]
        self._fat = self._read_fat()

    def replace_in_streams(self, edits: tuple[CfbStreamEdit, ...]) -> CfbEditResult:
        directory_chain = self._sector_chain(self._first_dir_sector)
        directory = bytearray(self._read_sectors(directory_chain))
        streams_touched = 0
        replacements_made = 0

        for entry_offset in range(0, len(directory), 128):
            entry = directory[entry_offset : entry_offset + 128]
            if len(entry) < 128 or entry[66] != 2:
                continue

            name_len = struct.unpack_from("<H", entry, 64)[0]
            name = entry[: max(0, name_len - 2)].decode("utf-16le", "ignore")
            matching_edits = [edit for edit in edits if edit.name == name]
            if not matching_edits:
                continue

            start_sector = struct.unpack_from("<I", entry, 116)[0]
            stream_size = struct.unpack_from("<Q", entry, 120)[0]
            if stream_size < self._mini_stream_cutoff:
                continue

            stream_chain = self._sector_chain(start_sector)
            if not stream_chain:
                continue

            capacity = len(stream_chain) * self._sector_size
            payload = self._read_sectors(stream_chain)[:stream_size]
            updated = payload
            stream_replacements = 0

            for edit in matching_edits:
                for old, new in edit.replacements:
                    count = updated.count(old)
                    if count:
                        updated = updated.replace(old, new)
                        stream_replacements += count

            if updated == payload:
                continue
            if len(updated) > capacity:
                raise ValueError(
                    f"stream {name!r} needs {len(updated)} bytes but only has "
                    f"{capacity} bytes of existing CFB sector capacity"
                )

            self._write_sectors(stream_chain, updated.ljust(capacity, b"\x00"))
            struct.pack_into("<Q", directory, entry_offset + 120, len(updated))
            streams_touched += 1
            replacements_made += stream_replacements

        if streams_touched:
            self._write_sectors(directory_chain, bytes(directory))

        return CfbEditResult(bytes(self._data), streams_touched, replacements_made)

    def _read_fat(self) -> list[int]:
        difat = list(struct.unpack_from("<109I", self._data, 0x4C))
        fat: list[int] = []
        for sector_id in difat:
            if sector_id in (FREESECT, ENDOFCHAIN, FATSECT, DIFSECT):
                continue
            offset = self._sector_offset(sector_id)
            entries_per_sector = self._sector_size // 4
            fat.extend(
                struct.unpack_from(f"<{entries_per_sector}I", self._data, offset)
            )
            if len(fat) >= self._num_fat_sectors * entries_per_sector:
                break
        return fat

    def _sector_chain(self, start_sector: int) -> list[int]:
        chain: list[int] = []
        sector = start_sector
        while sector not in (FREESECT, ENDOFCHAIN):
            if sector >= len(self._fat):
                raise ValueError(f"CFB FAT chain points outside FAT: sector {sector}")
            chain.append(sector)
            sector = self._fat[sector]
        return chain

    def _sector_offset(self, sector_id: int) -> int:
        return (sector_id + 1) * self._sector_size

    def _read_sectors(self, sectors: list[int]) -> bytes:
        chunks = []
        for sector in sectors:
            offset = self._sector_offset(sector)
            chunks.append(self._data[offset : offset + self._sector_size])
        return b"".join(chunks)

    def _write_sectors(self, sectors: list[int], data: bytes) -> None:
        expected_len = len(sectors) * self._sector_size
        if len(data) != expected_len:
            raise ValueError(f"sector write length mismatch: {len(data)} != {expected_len}")
        cursor = 0
        for sector in sectors:
            offset = self._sector_offset(sector)
            self._data[offset : offset + self._sector_size] = data[
                cursor : cursor + self._sector_size
            ]
            cursor += self._sector_size


def replace_cfb_stream_data(
    data: bytes, edits: tuple[CfbStreamEdit, ...]
) -> CfbEditResult:
    """Return ``data`` with byte replacements applied inside named CFB streams."""

    return CompoundFileBinary(data).replace_in_streams(edits)
