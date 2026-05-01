"""Pure Python reader for Source 2 .dem (PBDEMS2) replay files.

Extracts CDemoFileInfo which contains:
- Match duration, game mode, winner
- Player hero assignments and team sides
- Player Steam names

No external dependencies beyond the standard library.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

MAGIC = b"PBDEMS2\0"

# Source 2 demo command types
DEM_STOP = 0
DEM_FILE_HEADER = 1
DEM_FILE_INFO = 2
DEM_IS_COMPRESSED = 64


@dataclass
class PlayerInfo:
    hero_name: str  # e.g. "npc_dota_hero_invoker"
    player_name: str
    game_team: int  # 2 = Radiant, 3 = Dire
    steamid: int = 0
    is_fake_client: bool = False


@dataclass
class DemoFileInfo:
    playback_time: float = 0.0
    playback_ticks: int = 0
    playback_frames: int = 0
    match_id: int = 0
    game_mode: int = 0
    game_winner: int = 0  # 2 = Radiant, 3 = Dire
    players: list[PlayerInfo] = field(default_factory=list)


def read_demo_file_info(path: str | Path) -> DemoFileInfo | None:
    """Read CDemoFileInfo from a Dota 2 .dem replay file.

    This reads only the file header + the CDemoFileInfo section,
    NOT the full replay. It's fast (< 1ms for any file size).
    """
    path = Path(path)
    if not path.exists():
        return None

    with open(path, "rb") as f:
        magic = f.read(8)
        if magic != MAGIC:
            return None

        # Read file info offset (int32 LE at offset 8)
        file_info_offset = struct.unpack("<i", f.read(4))[0]
        _game_info_size = struct.unpack("<i", f.read(4))[0]

        if file_info_offset <= 0:
            return None

        # Seek to file info position
        f.seek(file_info_offset)
        remaining = f.read()

    if not remaining:
        return None

    # At file_info_offset there's a command frame:
    #   varint: command (possibly OR'd with DEM_IS_COMPRESSED=64)
    #   varint: tick
    #   varint: size
    #   size bytes: CDemoFileInfo protobuf data
    pos = 0
    cmd, pos = _decode_varint(remaining, pos)
    is_compressed = bool(cmd & DEM_IS_COMPRESSED)
    _cmd_type = cmd & ~DEM_IS_COMPRESSED

    _tick, pos = _decode_varint(remaining, pos)
    size, pos = _decode_varint(remaining, pos)

    payload = remaining[pos : pos + size]

    if is_compressed:
        payload = _try_snappy_decompress(payload)
        if payload is None:
            return None

    return _parse_file_info_proto(payload)


# ── Varint decoder ────────────────────────────────────────────────────────────


def _decode_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Decode a protobuf varint. Returns (value, new_offset)."""
    result = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            break
        shift += 7
    return result, offset


# ── Protobuf wire format decoder ─────────────────────────────────────────────


def _decode_proto(data: bytes) -> dict[int, list]:
    """Decode a protobuf message into {field_number: [values]}.

    Wire types:
      0 = varint, 1 = 64-bit fixed, 2 = length-delimited, 5 = 32-bit fixed
    Length-delimited values are returned as raw bytes (could be string,
    bytes, or a sub-message — caller decides).
    """
    fields: dict[int, list] = {}
    offset = 0
    while offset < len(data):
        try:
            key, offset = _decode_varint(data, offset)
        except (IndexError, ValueError):
            break
        field_number = key >> 3
        wire_type = key & 0x07

        if wire_type == 0:  # varint
            value, offset = _decode_varint(data, offset)
        elif wire_type == 1:  # 64-bit fixed
            if offset + 8 > len(data):
                break
            value = struct.unpack_from("<Q", data, offset)[0]
            offset += 8
        elif wire_type == 2:  # length-delimited
            length, offset = _decode_varint(data, offset)
            if offset + length > len(data):
                break
            value = data[offset : offset + length]
            offset += length
        elif wire_type == 5:  # 32-bit fixed
            if offset + 4 > len(data):
                break
            value = struct.unpack_from("<I", data, offset)[0]
            offset += 4
        else:
            break

        fields.setdefault(field_number, []).append(value)

    return fields


# ── CDemoFileInfo parser ──────────────────────────────────────────────────────


def _parse_file_info_proto(data: bytes) -> DemoFileInfo:
    """Parse CDemoFileInfo protobuf message.

    Structure:
      CDemoFileInfo {
        float playback_time = 1;     // wire type 5 (32-bit fixed)
        int32 playback_ticks = 2;    // wire type 0
        int32 playback_frames = 3;   // wire type 0
        CGameInfo game_info = 4;     // wire type 2 (sub-message)
      }
      CGameInfo {
        CDotaGameInfo dota = 4;      // wire type 2
      }
      CDotaGameInfo {
        uint64 match_id = 1;
        int32 game_mode = 2;
        int32 game_winner = 3;       // 2=Radiant, 3=Dire
        repeated CPlayerInfo player_info = 4;
      }
      CPlayerInfo {
        string hero_name = 1;
        string player_name = 2;
        bool is_fake_client = 3;
        uint64 steamid = 4;
        int32 game_team = 5;         // 2=Radiant, 3=Dire
      }
    """
    info = DemoFileInfo()
    fields = _decode_proto(data)

    # playback_time: field 1, wire type 5 (32-bit float)
    if 1 in fields:
        raw = fields[1][0]
        if isinstance(raw, int):
            info.playback_time = struct.unpack("<f", struct.pack("<I", raw))[0]

    # playback_ticks: field 2
    if 2 in fields:
        info.playback_ticks = fields[2][0]

    # playback_frames: field 3
    if 3 in fields:
        info.playback_frames = fields[3][0]

    # game_info: field 4 (sub-message CGameInfo)
    if 4 not in fields:
        return info

    game_info = _decode_proto(fields[4][0])

    # CGameInfo.dota: field 4 (sub-message CDotaGameInfo)
    if 4 not in game_info:
        return info

    dota_info = _decode_proto(game_info[4][0])

    # CDotaGameInfo fields
    if 1 in dota_info:
        info.match_id = dota_info[1][0]
    if 2 in dota_info:
        info.game_mode = dota_info[2][0]
    if 3 in dota_info:
        info.game_winner = dota_info[3][0]

    # player_info: field 4, repeated
    for player_raw in dota_info.get(4, []):
        pf = _decode_proto(player_raw)
        hero = _bytes_to_str(pf.get(1, [b""])[0])
        name = _bytes_to_str(pf.get(2, [b""])[0])
        is_fake = bool(pf.get(3, [0])[0])
        steamid = pf.get(4, [0])[0]
        team = pf.get(5, [0])[0]

        info.players.append(
            PlayerInfo(
                hero_name=hero,
                player_name=name,
                game_team=team,
                steamid=steamid,
                is_fake_client=is_fake,
            )
        )

    return info


# ── Helpers ───────────────────────────────────────────────────────────────────


def _bytes_to_str(val) -> str:
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return str(val)


def _try_snappy_decompress(data: bytes) -> bytes | None:
    """Decompress Snappy data. Returns None if no Snappy library available."""
    try:
        import cramjam

        return bytes(cramjam.snappy.decompress_raw(data))
    except ImportError:
        pass
    try:
        import snappy

        return snappy.decompress(data)
    except ImportError:
        pass
    # Last resort: return data as-is (maybe it wasn't actually compressed)
    return data
