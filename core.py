#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ATGMaster Controller — Core Module (core.py)
Hardware bitstream engine, Q1.23 mathematics, checksum serialization,
lookup tables, and portable filesystem definitions.
All comments, docstrings, and symbols are strictly in English.
"""

import os
import sys
import math
from typing import List, Dict, Any, Tuple

# ==============================================================================
# PORTABLE PATHS ENGINE
# ==============================================================================
def get_base_dir() -> str:
    """
    Returns the portable working directory where user data and backups live.
    When frozen with PyInstaller, returns the folder containing the executable.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_dir() -> str:
    """
    Returns the path to bundled read-only assets (e.g. PyInstaller temporary _MEIPASS folder).
    Falls back to base directory in standard execution.
    """
    if hasattr(sys, "_MEIPASS"):
        return getattr(sys, "_MEIPASS")
    return get_base_dir()


BASE_DIR = get_base_dir()
RESOURCE_DIR = get_resource_dir()

# Portable data and backups directories (created next to the executable/script)
DATA_DIR = os.path.join(BASE_DIR, "data")
BACKUPS_DIR = os.path.join(BASE_DIR, "backups")
ICONS_DIR = os.path.join(RESOURCE_DIR, "icons")

PATCHES_FILE = os.path.join(DATA_DIR, "patches.json")
GROUPS_FILE = os.path.join(DATA_DIR, "groups.json")


def ensure_directories() -> None:
    """Guarantees that portable runtime directories exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(BACKUPS_DIR, exist_ok=True)


def get_icon_path(name: str) -> str:
    """Returns absolute path to an icon file."""
    return os.path.join(ICONS_DIR, f"{name}.png")


# ==============================================================================
# CONNECTION STATES
# ==============================================================================
CONN_STANDALONE = "STANDALONE"
CONN_ARDUINO = "ARDUINO"
CONN_MIDI_IFACE = "MIDI_IFACE"

# ==============================================================================
# DATA TABLES & CONSTANTS
# ==============================================================================
GUITAR_MODELS_13: List[Dict[str, Any]] = [
    {"name": "ModHB",   "icon": "ModHB",  "type": "2P", "cc14": 0,  "cc22": None},
    {"name": "VinHB",   "icon": "VinHB",  "type": "2P", "cc14": 1,  "cc22": None},
    {"name": "MiniHB",  "icon": "MiniHB", "type": "2P", "cc14": 2,  "cc22": None},
    {"name": "SBar",    "icon": "SBar",   "type": "2P", "cc14": 3,  "cc22": None},
    {"name": "CstHSH",  "icon": "CstHSH", "type": "3P", "cc14": 4,  "cc22": None},
    {"name": "NasSC",   "icon": "NasSC",  "type": "2P", "cc14": 5,  "cc22": None},
    {"name": "CalSC",   "icon": "CalSC",  "type": "3P", "cc14": 6,  "cc22": None},
    {"name": "LStick",  "icon": "LStick", "type": "2P", "cc14": 7,  "cc22": None},
    {"name": "JPHSH",   "icon": "JPHSH",  "type": "3P", "cc14": 10, "cc22": None},
    {"name": "Bass",    "icon": "Bass",   "type": "2P", "cc14": 9,  "cc22": None},
    {"name": "FSt",     "icon": "FSt",    "type": "AC", "cc14": 8,  "cc22": 0},
    {"name": "OM",      "icon": "OM",     "type": "AC", "cc14": 8,  "cc22": 2},
    {"name": "Drn",     "icon": "Drn",    "type": "AC", "cc14": 8,  "cc22": 4},
]

TUNINGS: List[str] = [
    "Standard", "Custom", "Bass", "Drop D", "Double Drop D",
    "DADGAD", "Open G", "Open D", "Open E", "Open A",
    "Open e (min)", "Open d (min)", "Open a (min)"
]

DOUBLINGS: List[str] = [
    "None", "Octave Down", "Octave Up", "4th Up", "5th Up",
    "7-String", "7-String 2", "12-String", "12-String 2", "Custom"
]

DTRNSP: List[str] = [
    "Standard", "-1 Eb", "-2 D", "-3 C#", "-4 C", "-5 B", "-12 Bass", "+12 Oct"
]

NOTE_NAMES: List[str] = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

PITCH_SHIFT_MODES: List[str] = [
    "0 -> +12 (Octave Up)",
    "0 -> -12 (Octave Down)",
    "-12 -> +12 (Full Whammy)",
    "-100 -> +100 (Detune/Chorus)"
]

# Tablature String Ordering: String 6 at top down to String 1 at bottom
STRING_LABELS: List[str] = ["6 (E1)", "5 (A1)", "4 (D2)", "3 (G2)", "2 (B2)", "1 (E3)"]
BASE_NOTES_TAB: List[int] = [40, 45, 50, 55, 59, 64]

ATG_NAME_WEIGHTS: List[int] = [16384, 64, 4194304] * 6  # 18 characters (144 bits total, 3-phase cycle)

# Canonical BLANK Sysex Template (169 bytes)
BLANK_SYSEX_TEMPLATE = bytes.fromhex(
    "F0000126001A00000000000000000000"
    "0000011C000000000000000000050000"
    "00000000000000000000000000000000"
    "00000000000000164000020100000000"
    "00041231024E25480402010040201008"
    "04020100402000000000000000000008"
    "00000100000010000002000000200000"
    "04000000400000080000010000001000"
    "00020000002000000400000040000008"
    "00000100000010000002000000007F7F"
    "60000000472B4100F7"
)


# ==============================================================================
# FACTORY STRUCTURES
# ==============================================================================
def create_empty_patch(name: str = "EMPTY") -> Dict[str, Any]:
    """Factory creating a standardized patch dictionary."""
    return {
        "name": name[:18],
        "model": 0,
        "pickup": 0,
        "capo": 0,
        "pitch_shift": 0,
        "tuning": 0,
        "double": 0,
        "gate": 0,
        "solid_tune": True,
        "custom_tuning": [0] * 6,
        "custom_doubling": [0] * 6,
        "notes": ""
    }


def create_empty_group(index: int) -> Dict[str, Any]:
    """Factory creating a standardized group dictionary."""
    return {
        "name": f"GROUP {index + 1}",
        "slots": ["EMPTY"] * 4,
        "default_patch": "EMPTY"
    }


# ==============================================================================
# CANONICAL BITSTREAM & MATHEMATICS ENGINE
# ==============================================================================
def midi_num_to_name(n: int) -> str:
    """Converts a standard MIDI note number into note name and octave (e.g. 40 -> E1)."""
    return f"{NOTE_NAMES[n % 12]}{(n // 12) - 1}"


def cents_to_q123(cents: int) -> int:
    """
    Converts musical cents to DSP Q1.23 fixed-point format.
    Strictly uses math.ceil() followed by clearing bits 0 and 1 (& ~0b11),
    matching the ATG firmware implementation.
    Clamps positive cents to 1199 to prevent 24-bit container overflow (ratio 2.0 = 2^24).
    """
    if cents == 0:
        return 8388608
    safe_cents = min(1199, cents)
    raw = (2.0 ** (safe_cents / 1200.0)) * 8388608.0
    ceiled = math.ceil(raw)
    return ceiled & ~0b11


def write_bits_to_midi_stream(
    buffer: bytearray,
    start_byte: int,
    start_bit: int,
    value: int,
    num_bits: int
) -> Tuple[int, int]:
    """
    Injects num_bits MSB-first into a continuous 7-bit MIDI data stream (bits 6..0).
    Guarantees MIDI 1.0 compliance by keeping MSB (bit 7) cleared at 0.
    """
    cur_byte = start_byte
    cur_bit = start_bit
    for b in range(num_bits - 1, -1, -1):
        bit_val = (value >> b) & 1
        if bit_val:
            buffer[cur_byte] |= (1 << cur_bit)
        else:
            buffer[cur_byte] &= ~(1 << cur_bit)

        cur_bit -= 1
        if cur_bit < 0:
            cur_bit = 6
            cur_byte += 1

    return cur_byte, cur_bit


def compute_name_weight_sum(name_str: str) -> int:
    """Calculates the 35-bit accumulator sum contribution for an 18-character ASCII name."""
    padded = name_str[:18].ljust(18, " ")
    total = 0
    for i, ch in enumerate(padded):
        total += (ord(ch) & 0x7F) * ATG_NAME_WEIGHTS[i]
    return total


def encode_atg_name_canonical(buffer: bytearray, name_str: str) -> int:
    """
    Encodes an ASCII preset name up to 18 characters directly into buffer bytes 65..85.
    Preserves hardware bits 6..3 of byte 65, writes 144 bits across 7-bit containers,
    and returns the weighted sum for checksum adjustment.
    """
    padded = name_str[:18].ljust(18, " ")
    raw_ascii = [ord(c) & 0x7F for c in padded]

    # Clean destination name bitstream region (bytes 65..85)
    buffer[65] &= 0xF8  # Preserve bits 6..3 (clears bits 2..0)
    for i in range(66, 86):
        buffer[i] = 0x00

    cur_byte = 65
    cur_bit = 3
    for char_val in raw_ascii:
        cur_byte, cur_bit = write_bits_to_midi_stream(buffer, cur_byte, cur_bit, char_val, 8)

    char_sum = 0
    for i in range(18):
        char_sum += raw_ascii[i] * ATG_NAME_WEIGHTS[i]

    return char_sum


def encode_matrix_q123(
    buffer: bytearray,
    start_byte: int,
    start_bit: int,
    cents_list: List[int]
) -> int:
    """
    Encodes 6 strings in 24-bit Q1.23 format from String 1 (High E) to String 6 (Low E).
    cents_list is passed in Tablature order [Str 6, Str 5, Str 4, Str 3, Str 2, Str 1].
    """
    cur_byte = start_byte
    cur_bit = start_bit
    delta_accum = 0

    antares_order_cents = list(reversed(cents_list))
    for c in antares_order_cents:
        q_val = cents_to_q123(c)
        cur_byte, cur_bit = write_bits_to_midi_stream(buffer, cur_byte, cur_bit, q_val, 24)
        delta_accum += (q_val - 8388608)

    return delta_accum


# ==============================================================================
# SYSEX PRESET PACKET BUILDER
# ==============================================================================
def build_sysex_preset_packet(slot_idx: int, patch_dict: Dict[str, Any]) -> bytes:
    """
    Builds the 169-byte SysEx preset packet for ATG/ ATG hardware.
    Computes exact Base-128 checksum and packs parameters into the continuous 7-bit stream.
    """
    packet = bytearray(BLANK_SYSEX_TEMPLATE)

    # 1. Preset Slot Destination (Byte 29: slot + 5)
    packet[29] = (slot_idx + 5) & 0x7F

    # 2. Solid-Tune Toggle (Byte 57)
    solid_on = patch_dict.get("solid_tune", True)
    packet[57] = 0x00 if solid_on else 0x10

    # 3. Tuning & Capo
    custom_cents = patch_dict.get("custom_tuning", [0] * 6)
    has_custom_tune = (patch_dict.get("tuning", 0) == 1)
    capo_val = patch_dict.get("capo", 0)
    stock_tuning = patch_dict.get("tuning", 0)

    base_flag = 0x01 if capo_val < 0 else 0x02
    if has_custom_tune:
        packet[58] = 0x0A if capo_val >= 0 else 0x09
    else:
        packet[58] = (stock_tuning * 8) + base_flag

    if has_custom_tune:
        encode_matrix_q123(packet, 95, 3, custom_cents)

    if capo_val >= 0:
        packet[59] = ((capo_val << 2) | 0x01) & 0x7F
    else:
        packet[59] = (129 + capo_val * 4) & 0x7F

    # 4. Pitch Shift Travel (Byte 60)
    pitch_shift_val = patch_dict.get("pitch_shift", 0) & 0x03
    packet[60] = pitch_shift_val

    # 5. Guitar Model & Pickup Position (Unified 21-bit register across Bytes 62..64)
    model_id = patch_dict.get("model", 0)
    pickup_pos = patch_dict.get("pickup", 0)  # 0: Neck, 1: Neck+Mid, 2: Mid/Both, 3: Mid+Bridge, 4: Bridge

    # Empacotamento direto: ModelID no bit 13, PickupPos no bit 5
    word_21 = (model_id << 13) | (pickup_pos << 5)

    packet[62] = (word_21 >> 14) & 0x7F
    packet[63] = (word_21 >> 7)  & 0x7F
    packet[64] = word_21 & 0x7F

    # 6. Preset Name Packing (Bytes 65..85)
    name_str = patch_dict.get("name", "BLANK")
    new_name_sum = encode_atg_name_canonical(packet, name_str)
    blank_name_sum = compute_name_weight_sum("BLANK")

    # 7. Doubling Packing (Bytes 86..87 and Q1.23 Matrix at Bytes 136..157)
    custom_double_cents = patch_dict.get("custom_doubling", [0] * 6)
    doubling_id = patch_dict.get("double", 0)
    has_custom_double = (doubling_id == 9)

    if has_custom_double:
        packet[86] = 0x04
        packet[87] = 0x40
        encode_matrix_q123(packet, 136, 2, custom_double_cents)
    else:
        packet[86] = (doubling_id >> 1) & 0x7F
        packet[87] = ((doubling_id & 1) << 6) & 0x7F

    # 8. Noise Gate Threshold (Byte 91, 0..22 mapped to 0..88)
    gate_val = max(0, min(22, patch_dict.get("gate", 0)))
    packet[91] = (gate_val * 4) & 0x7F

    # 9. Checksum Calculation (Base-128 accumulator)
    # Calibrated hardware baseline accumulator: 225612864 (0x00, 0x6B, 0x4A, 0x28, 0x40)
    # total_accum = (0x00 << 28) | (0x6B << 21) | (0x4A << 14) | (0x28 << 7) | 0x40
    total_accum = (0x00 << 28) | (0x47 << 21) | (0x2B << 14) | (0x41 << 7) | 0x00

    # Name delta (18 characters)
    total_accum += (new_name_sum - blank_name_sum)

    # Performance and sound engine deltas
    # Performance and sound engine deltas
    total_accum += slot_idx * 64
    total_accum += capo_val * 16384
    total_accum += pitch_shift_val * 4194304
    total_accum += model_id * 16384
    total_accum += pickup_pos * 64
    total_accum += doubling_id * 16384
    total_accum += 16 * packet[91] # Noise Gate

    # Custom vs Stock Tuning delta
    if has_custom_tune:
        total_accum += 4194304
        for c in custom_cents:
            q = cents_to_q123(c)
            total_accum += 16 * (q - 8388608)
    else:
        total_accum += stock_tuning * 4194304

    # Custom Doubling matrix delta
    if has_custom_double:
        for c in custom_double_cents:
            q = cents_to_q123(c)
            total_accum += 16 * (q - 8388608)

    # Pack 30-bit checksum into Bytes 163..167 (Byte 163 holds only the 2 MSB bits: 28 and 29)
    total_accum &= 0x3FFFFFFF  # 30-bit hardware accumulator wrap
    packet[163] = (total_accum >> 28) & 0x03
    packet[164] = (total_accum >> 21) & 0x7F
    packet[165] = (total_accum >> 14) & 0x7F
    packet[166] = (total_accum >> 7) & 0x7F
    packet[167] = total_accum & 0x7F

    return bytes(packet)

# ==============================================================================
# RETRIEVE AND UNPACK
# ==============================================================================
def q123_to_cents(q_val: int) -> int:
    """Converte formato fixed-point DSP Q1.23 para cents (-2400..+2400)."""
    if q_val <= 0 or q_val == 8388608:
        return 0
    ratio = q_val / 8388608.0
    return int(round(1200.0 * math.log2(ratio)))


def unpack_atg_bits(buffer: bytes, start_byte: int, start_bit: int, num_bits: int) -> Tuple[int, int, int]:
    """Lê num_bits MSB-first de um fluxo contínuo de 7-bit MIDI."""
    val = 0
    cur_byte = start_byte
    cur_bit = start_bit
    for _ in range(num_bits):
        if cur_byte >= len(buffer):
            break
        bit = (buffer[cur_byte] >> (6 - cur_bit)) & 1
        val = (val << 1) | bit
        cur_bit += 1
        if cur_bit >= 7:
            cur_bit = 0
            cur_byte += 1
    return val, cur_byte, cur_bit


def read_bits_from_stream(buffer: bytes, start_byte: int, start_bit: int, num_bits: int) -> Tuple[int, int, int]:
    """Lê num_bits MSB-first de um fluxo de 7-bit MIDI."""
    val = 0
    cur_byte = start_byte
    cur_bit = start_bit
    for _ in range(num_bits):
        if cur_byte >= len(buffer):
            break
        bit = (buffer[cur_byte] >> cur_bit) & 1
        val = (val << 1) | bit
        cur_bit -= 1
        if cur_bit < 0:
            cur_bit = 6
            cur_byte += 1
    return val, cur_byte, cur_bit

def unpack_sysex_preset_packet(raw_sysex: bytes) -> Dict[str, Any]:
    """
    Desempacota a resposta SysEx de 114 bytes validada a 100% no hardware Peavey AT-200.
    """
    # Isola os 107 bytes de payload após F0 00 01 26 xx 1F
    if raw_sysex.startswith(b"\xF0\x00\x01\x26"):
        payload = raw_sysex[6:-1]
    else:
        payload = raw_sysex

    patch = create_empty_patch()
    if len(payload) < 40:
        return patch

    # 1. Solid-Tune (Byte 3: 0x00 = ON, 0x10 = OFF)
    patch["solid_tune"] = (payload[3] & 0x10) == 0

    # 2. Tuning & Capo (Bytes 4 e 5)
    tuning_byte = payload[4]
    is_custom_tune = (tuning_byte in (0x09, 0x0A))
    patch["tuning"] = 1 if is_custom_tune else ((tuning_byte >> 3) & 0x0F)

    b59 = payload[5]
    if tuning_byte & 0x02:
        patch["capo"] = (b59 >> 2)
    else:
        patch["capo"] = (b59 - 129) // 4

    # 3. Pitch Shift Travel (Byte 6)
    patch["pitch_shift"] = payload[6] & 0x03

    # 4. Model & Pickup Position (Bytes 8, 9, 10 - Registo de 21 bits)
    word_21 = (payload[8] << 14) | (payload[9] << 7) | payload[10]
    patch["model"] = (word_21 >> 13) & 0x7F
    patch["pickup"] = (word_21 >> 5) & 0x07

    # 5. Preset Name (18 caracteres ASCII no Byte 11, bit 3)
    cur_byte, cur_bit = 11, 3
    chars = []
    for _ in range(18):
        char_val, cur_byte, cur_bit = read_bits_from_stream(payload, cur_byte, cur_bit, 8)
        chars.append(chr(char_val & 0x7F))
    raw_name = "".join(chars).rstrip()
    patch["name"] = raw_name if raw_name else "EMPTY"

    # 6. Doubling (Bytes 32 e 33)
    b86 = payload[32]
    b87 = payload[33]
    if b86 == 0x04 and b87 == 0x40:
        patch["double"] = 9  # Custom Doubling
        # Desempacota matriz custom doubling (Byte 82, bit 2)
        cur_b, cur_bt = 82, 2
        dbl_q = []
        for _ in range(6):
            q_val, cur_b, cur_bt = read_bits_from_stream(payload, cur_b, cur_bt, 24)
            dbl_q.append(q123_to_cents(q_val))
        patch["custom_doubling"] = list(reversed(dbl_q))
    else:
        patch["double"] = ((b86 & 0x7F) << 1) | ((b87 >> 6) & 1)
        patch["custom_doubling"] = [0] * 6

    # 7. Noise Gate Threshold (Byte 37)
    if len(payload) > 37:
        patch["gate"] = (payload[37] >> 2) & 0x1F

    # 8. Custom Tuning Matrix Q1.23 (Byte 41, bit 3)
    if is_custom_tune and len(payload) > 65:
        cur_b, cur_bt = 41, 3
        tune_q = []
        for _ in range(6):
            q_val, cur_b, cur_bt = read_bits_from_stream(payload, cur_b, cur_bt, 24)
            tune_q.append(q123_to_cents(q_val))
        patch["custom_tuning"] = list(reversed(tune_q))
    else:
        patch["custom_tuning"] = [0] * 6

    return patch