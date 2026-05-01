"""Unit tests for the replay parser modules."""

import struct

from dotaengineer.replay.dem_reader import (
    _decode_proto,
    _decode_varint,
)
from dotaengineer.replay.parser import _game_mode_name, _resolve_hero_id

# ── Varint tests ──────────────────────────────────────────────────────────────


def test_decode_varint_single_byte():
    data = bytes([42])
    val, pos = _decode_varint(data, 0)
    assert val == 42
    assert pos == 1


def test_decode_varint_multi_byte():
    # 300 = 0b100101100 → varint: [0xAC, 0x02]
    data = bytes([0xAC, 0x02])
    val, pos = _decode_varint(data, 0)
    assert val == 300
    assert pos == 2


def test_decode_varint_with_offset():
    data = bytes([0x00, 0x00, 42])
    val, pos = _decode_varint(data, 2)
    assert val == 42
    assert pos == 3


# ── Protobuf decoder tests ──────────────────────────────────────────────────


def test_decode_proto_varint_field():
    # field 1, wire type 0 (varint), value 150
    # key = (1 << 3) | 0 = 8
    # 150 = [0x96, 0x01]
    data = bytes([0x08, 0x96, 0x01])
    fields = _decode_proto(data)
    assert 1 in fields
    assert fields[1][0] == 150


def test_decode_proto_length_delimited():
    # field 2, wire type 2 (length-delimited), value "test"
    # key = (2 << 3) | 2 = 18
    payload = b"test"
    data = bytes([18, len(payload)]) + payload
    fields = _decode_proto(data)
    assert 2 in fields
    assert fields[2][0] == b"test"


def test_decode_proto_32bit_fixed():
    # field 1, wire type 5 (32-bit), value for float 42.5
    # key = (1 << 3) | 5 = 13
    float_bytes = struct.pack("<f", 42.5)
    data = bytes([13]) + float_bytes
    fields = _decode_proto(data)
    assert 1 in fields
    # Stored as uint32, needs reinterpretation for float
    raw = fields[1][0]
    result = struct.unpack("<f", struct.pack("<I", raw))[0]
    assert abs(result - 42.5) < 0.001


# ── Hero resolution tests ────────────────────────────────────────────────────


def test_resolve_hero_id_full_name():
    # Anti-Mage has ID 1
    hero_id = _resolve_hero_id("npc_dota_hero_antimage")
    assert hero_id == 1


def test_resolve_hero_id_unknown():
    hero_id = _resolve_hero_id("npc_dota_hero_doesnotexist")
    assert hero_id == 0


def test_resolve_hero_id_empty():
    assert _resolve_hero_id("") == 0


# ── Game mode name tests ─────────────────────────────────────────────────────


def test_game_mode_captains():
    assert _game_mode_name(2) == "captains_mode"


def test_game_mode_all_pick():
    assert _game_mode_name(1) == "all_pick"


def test_game_mode_unknown():
    assert _game_mode_name(999) == "mode_999"
