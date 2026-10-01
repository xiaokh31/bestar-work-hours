"""Read-only BIFF assertions adapted from stripSystem tests; see NOTICE."""
import struct
from pathlib import Path

from xlrd.compdoc import CompDoc


def _biff_record_payloads(path: Path, record_id: int) -> tuple[bytes, ...]:
    stream = _workbook_stream(path)
    payloads: list[bytes] = []
    position = 0
    while position + 4 <= len(stream):
        current_id, payload_size = struct.unpack_from("<HH", stream, position)
        end = position + 4 + payload_size
        if current_id == record_id:
            payloads.append(stream[position + 4 : end])
        position = end
    return tuple(payloads)



def _sheet_record_payloads(
    path: Path,
    sheet_name: str,
    target_record_id: int,
) -> tuple[bytes, ...]:
    stream = _workbook_stream(path)
    boundsheets: list[tuple[int, str]] = []
    position = 0
    while position + 4 <= len(stream):
        record_id, payload_size = struct.unpack_from("<HH", stream, position)
        payload = stream[position + 4 : position + 4 + payload_size]
        if record_id == 0x0085:
            offset = struct.unpack_from("<I", payload, 0)[0]
            character_count = payload[6]
            unicode_name = bool(payload[7] & 0x01)
            name_bytes = payload[8 : 8 + character_count * (2 if unicode_name else 1)]
            name = name_bytes.decode("utf-16le" if unicode_name else "latin1")
            boundsheets.append((offset, name))
        position += 4 + payload_size
        if boundsheets and position >= min(offset for offset, _ in boundsheets):
            break

    sheet_index = next(
        index for index, (_, name) in enumerate(boundsheets) if name == sheet_name
    )
    position = boundsheets[sheet_index][0]
    payloads: list[bytes] = []
    while position + 4 <= len(stream):
        record_id, payload_size = struct.unpack_from("<HH", stream, position)
        if record_id == target_record_id:
            payloads.append(stream[position + 4 : position + 4 + payload_size])
        position += 4 + payload_size
        if record_id == 0x000A:
            break
    return tuple(payloads)



def _workbook_stream(path: Path) -> bytes:
    compound = CompDoc(path.read_bytes())
    return compound.get_named_stream("Workbook") or compound.get_named_stream("Book")
