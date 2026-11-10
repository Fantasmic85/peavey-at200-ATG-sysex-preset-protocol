# ATG/ ATG Preset SysEx Protocol Specification

**Reverse-Engineered Hardware Specification & Developer Implementation Guide**

> **Target Hardware:** AT for Guitar (ATG-1 / ATG DSP Core)  
> Product names are used for identification purposes only. This is an independent reverse-engineering effort and is not affiliated with, endorsed by, or sponsored by Peavey or Antares.
> **Document Version:** 1.0.0  
> **Scope:** Complete Preset Payload, Parameter Encoding, Q1.23 DSP Math, and Base-128 Checksum Engine.  
> *(Global Parameters are covered in a separate document.)*

---

## Disclaimer

This document is the result of independent reverse engineering for **interoperability and preservation purposes**.  
It is **not** official documentation from Peavey or Antares.

- Use at your own risk.
- Incorrect SysEx packets may leave a preset slot in an inconsistent state (the guitar silently rejects invalid checksums).
- This work does not distribute proprietary firmware or copyrighted software.

---

## 1. Hardware Communication & SysEx Transaction Architecture

The ATGcommunicates via standard MIDI 1.0 (31,250 baud, 8-N-1).  
All System Exclusive (SysEx) data packets must strictly obey MIDI 7-bit framing: **Bit 7 of all data payload bytes must always be 0** (values `0x00` to `0x7F`).

Flashing a preset into non-volatile guitar memory requires a strict three-phase atomic handshake:

```
[Master Controller]                           [ATGGuitar]
        |                                                |
        |--- 1. Flash Preset Unlock (7 bytes) ---------->|
        |    F0 00 01 26 00 0E F7                        |
        |                                                |
        |    [Wait 100 ms pacing delay]                  |
        |                                                |
        |--- 2. Preset Data Payload (169 bytes) -------->|
        |    F0 00 01 26 00 1A [161 data bytes] F7       |
        |                                                |
        |    [Wait 100 ms pacing delay]                  |
        |                                                |
        |--- 3. Flash Preset Commit (7 bytes) ---------->|
        |    F0 00 01 26 00 16 F7                        |
        |                                                |
        |    [Wait 500 ms hardware flash write delay]    |
        |                                                |
        |--- 4. Program Change (optional audition) ----->|
        |    C0 <slot_index>                             |
```

### Handshake Command Reference

| Phase | Command | SysEx Sequence (Hex) | Description |
|-------|---------|----------------------|-------------|
| 1. Unlock | `CMD_FLASH_PRESET_UNLOCK` | `F0 00 01 26 00 0E F7` | Unlocks guitar EEPROM/Flash write buffer |
| 2. Payload | `CMD_PRESET_PAYLOAD` | `F0 00 01 26 00 1A ... F7` | 169-byte complete preset bitstream |
| 3. Commit | `CMD_FLASH_PRESET_COMMIT` | `F0 00 01 26 00 16 F7` | Validates checksum and commits to Flash |
| 4. Audition | `MIDI_PROGRAM_CHANGE` | `C0 <slot_0_to_63>` | Switches active preset to the flashed slot |

> **Note:** If the 30-bit Base-128 checksum calculated over the 169-byte payload does not match the guitar DSP's internal checksum validation, the guitar **silently rejects** the commit command (`0x16`), retaining whatever was previously in that preset slot.

---

## 2. Canonical Blank Preset Template

All generated preset packets are built by modifying a standardized 169-byte factory canonical template:

```
Byte Index   00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15
-------------------------------------------------------------
000..015:    F0 00 01 26 00 1A 00 00 00 00 00 00 00 00 00 00
016..031:    00 00 01 1C 00 00 00 00 00 00 00 00 00 05 00 00
032..047:    00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
048..063:    00 00 00 00 00 00 00 16 40 00 02 01 00 00 00 00
064..079:    00 04 12 31 02 4E 25 48 04 02 01 00 40 20 10 08
080..095:    04 02 01 00 40 20 00 00 00 00 00 00 00 00 00 08
096..111:    00 00 01 00 00 00 10 00 00 02 00 00 00 20 00 00
112..127:    04 00 00 00 40 00 00 08 00 00 01 00 00 00 10 00
128..143:    00 02 00 00 00 20 00 00 04 00 00 00 40 00 00 08
144..159:    00 00 01 00 00 00 10 00 00 02 00 00 00 00 7F 7F
160..168:    60 00 00 00 47 2B 41 00 F7
```

---

## 3. Comprehensive SysEx Byte Map (Preset Payload)

| Byte Index | Field Name | Width / Format | Range / Valid Values | Description |
|------------|------------|----------------|----------------------|-------------|
| 0..4 | SysEx Header | 5 bytes | `F0 00 01 26 00` | Manufacturer ID (`00 01 26`), Sub-ID 00 |
| 5 | Command ID | 1 byte | `0x1A` | Preset Write / Flash Payload opcode |
| 6..28 | Frame Preamble | 23 bytes | Fixed | Routing preamble (`... 01 1C ...`) |
| 29 | Target Preset Slot | 1 byte | `0x05` to `0x44` | Target Slot Index: `slot_idx + 5` (Slots 0..63) |
| 30..56 | Routing Frame | 27 bytes | Fixed | Internal DSP routing flags |
| 57 | Solid-Tune Toggle | 1 byte | `0x00` or `0x10` | `0x00` = Solid-Tune ON, `0x10` = Solid-Tune OFF |
| 58 | Tuning & Capo Flag | 1 byte | `(tuning * 8) + flag` | Stock tuning ID & negative capo indicator |
| 59 | Capo Value | 1 byte | Continuous | Capo semitone offset (-12 to +12) |
| 60 | Pitch Shift Travel | 1 byte | `0x00` to `0x03` | Whammy/Fx Pedal travel mode (0 to 3) |
| 61 | Reserved | 1 byte | `0x00` | Internal control byte (always `0x00`) |
| 62..64 | Model & Pickup | 3 bytes | 21-bit register | Unified register for Model ID and Pickup position |
| 65..85 | Preset Name | 21 bytes | 144-bit stream | 18 ASCII characters (8-bit ASCII in 7-bit stream) |
| 86..87 | Doubling ID | 2 bytes | Continuous | Stock Doubling ID (0..8) or Custom flag (9) |
| 88..90 | Reserved | 3 bytes | `0x00 0x00 0x00` | Internal padding |
| 91 | Noise Gate Threshold | 1 byte | `(gate_val * 4)` | Threshold: 0 (Off) to 22 (-30 dB), mapped 0..88 |
| 92..94 | Reserved | 3 bytes | `0x00 0x00 0x00` | Internal padding |
| 95..115 | Custom Tuning Matrix | 21 bytes | 144-bit stream | 6 strings × 24-bit Q1.23 fixed-point pitch ratios |
| 116..135 | Divider Padding | 20 bytes | Fixed | DSP baseline inter-matrix divider |
| 136..157 | Custom Doubling Matrix | 22 bytes | 144-bit stream | 6 strings × 24-bit Q1.23 fixed-point pitch ratios |
| 158..162 | Postamble Frame | 5 bytes | `7F 7F 60 00 00` | Matrix closing frame markers |
| 163..167 | 30-bit Checksum | 5 bytes | Base-128 words | 5 × 7-bit words of the 30-bit accumulator |
| 168 | End of Exclusive | 1 byte | `0xF7` | Standard MIDI EOX terminator |

---

## 4. Parameter Bitstream Encoding & Register Layouts

### 4.1 Preset Slot Destination (Byte 29)

The hardware preset destination slot is offset by 5:

```python
packet[29] = (slot_idx + 5) & 0x7F
```

- Slot 0 (User Preset 1) = `0x05`
- Slot 63 (User Preset 64) = `0x44`

### 4.2 Solid-Tune State (Byte 57)

Solid-Tune is an inverted single-bit flag located at bit 4 of Byte 57:

- If Solid-Tune is **ON**: `packet[57] = 0x00`
- If Solid-Tune is **OFF**: `packet[57] = 0x10`

### 4.3 Tuning Mode & Capo Configuration (Bytes 58 and 59)

#### Tuning Flag (Byte 58)

```python
base_flag = 0x01 if capo_val < 0 else 0x02

if Custom Tuning is active (tuning == 1):
    packet[58] = 0x09 if capo_val < 0 else 0x0A
else:
    packet[58] = (stock_tuning_id * 8) + base_flag
```

#### Capo Semitone Value (Byte 59)

Capo ranges from -12 to +12 semitones:

```python
if capo_val >= 0:
    packet[59] = ((capo_val << 2) | 0x01) & 0x7F
else:
    packet[59] = (129 + capo_val * 4) & 0x7F
```

#### Stock Tuning ID Table

| ID | Tuning Name |
|----|-------------|
| 0 | Standard |
| 1 | Custom |
| 2 | Bass |
| 3 | Drop D |
| 4 | Double Drop D |
| 5 | DADGAD |
| 6 | Open G |
| 7 | Open D |
| 8 | Open E |
| 9 | Open A |
| 10 | Open E Minor |
| 11 | Open D Minor |
| 12 | Open A Minor |

### 4.4 Pitch Shift Whammy Travel (Byte 60)

The pedal travel behavior for pitch-shifting is stored in Byte 60 (values 0..3):

| Value | Travel Mode | Description |
|-------|-------------|-------------|
| 0 | 0 → +12 | Octave Up Whammy pedal |
| 1 | 0 → -12 | Octave Down Whammy pedal |
| 2 | -12 → +12 | Full Whammy travel (±1 Octave) |
| 3 | -100 → +100 | Detune / Chorus sweep (±100 cents) |

```python
packet[60] = pitch_shift_mode & 0x03
```

### 4.5 Unified Guitar Model & Pickup Register (Bytes 62, 63, and 64)

Bytes 62, 63, and 64 form a contiguous 21-bit Big-Endian register across 7-bit MIDI containers:

**21-bit Word W:**
- Bits [20..13]: ModelID (8 bits, range 0..10)
- Bits [12..5]: PickupPos (8 bits, range 0..4)
- Bits [4..0]: Always `0b00000`

```python
W = (ModelID << 13) | (PickupPos << 5)

# Serialization
packet[62] = (W >> 14) & 0x7F
packet[63] = (W >> 7)  & 0x7F
packet[64] = W         & 0x7F
```

#### Pickup Position Mapping Table

| Value | Pickup Position (3-Pickup Models) | Pickup Position (2-Pickup Models) |
|-------|-----------------------------------|-----------------------------------|
| 0 | Neck | Neck |
| 1 | Neck + Middle | Reserved / Fallback |
| 2 | Middle | Both (Neck + Bridge) |
| 3 | Middle + Bridge | Reserved / Fallback |
| 4 | Bridge | Bridge |

#### Guitar Model ID Table

| ModelID | Guitar Model Emulation | CC 14 | Model Type | Available Pickups | Bytes [62, 63, 64] (Pos 0) |
|---------|------------------------|-------|------------|-------------------|----------------------------|
| 0 | Modern Passive Humbucker | 0 | 2P | Neck(0), Both(2), Bridge(4) | `00 00 00` |
| 1 | Vintage Humbucker | 1 | 2P | Neck(0), Both(2), Bridge(4) | `00 40 00` |
| 2 | Mini Humbucker | 2 | 2P | Neck(0), Both(2), Bridge(4) | `01 00 00` |
| 3 | P90 Single Coil | 3 | 2P | Neck(0), Both(2), Bridge(4) | `01 40 00` |
| 4 | Custom HSH | 4 | 3P | 5 positions (0, 1, 2, 3, 4) | `02 00 00` |
| 5 | Nashville Single Coil | 5 | 2P | Neck(0), Both(2), Bridge(4) | `02 40 00` |
| 6 | California Single Coil | 6 | 3P | 5 positions (0, 1, 2, 3, 4) | `03 00 00` |
| 7 | Vintage Lipstick | 7 | 2P | Neck(0), Both(2), Bridge(4) | `03 40 00` |
| 8 | Acoustic (FS / OM / Dreadnought) | 8 | 2P | Sub-models via CC22 (0, 2, 4) | `04 00 00` |
| 9 | Bass (J B / J N+B / P) | 9 | 2P | Neck(0), Both(2), Bridge(4) | `04 40 00` |
| 10 | Japanese HSH | 10 | 3P | 5 positions (0, 1, 2, 3, 4) | `05 00 00` |

> **Note for Acoustic Models:** When ModelID = 8, the pickup selector selects the acoustic body type:  
> 0 = Fingerstyle, 2 = Orchestra Model (OM), 4 = Dreadnought.

### 4.6 Preset Name Bitstream Encoding (Bytes 65..85)

The preset name consists of strictly 18 ASCII characters (padded with ASCII spaces `0x20`). It is packed as a continuous 144-bit stream (18 characters × 8 bits) spanning from Byte 65, Bit 3 down to Byte 85, Bit 0:

**Bit Stream Budget:**
- Byte 65: Bits [3..0] = 4 bits
- Bytes 66..84: 19 × 7 = 133 bits
- Byte 85: Bits [6..0] = 7 bits  
- **Total Bits = 144 bits** (18 bytes × 8 bits)

```python
padded_name = raw_name[:18].ljust(18, " ")
raw_ascii = [ord(c) & 0x7F for c in padded_name]

packet[65] &= 0xF8
for i in range(66, 86):
    packet[i] = 0x00

cur_byte = 65
cur_bit = 3
for char_val in raw_ascii:
    cur_byte, cur_bit = write_bits_to_midi_stream(packet, cur_byte, cur_bit, char_val, 8)
```

### 4.7 Doubling Mode (Bytes 86 and 87)

The doubling mode ID occupies a 14-bit register across Bytes 86 and 87:

```python
if Custom Doubling is active (doubling_id == 9):
    packet[86] = 0x04
    packet[87] = 0x40
else:  # Stock Doublings 0..8
    packet[86] = (doubling_id >> 1) & 0x7F
    packet[87] = ((doubling_id & 1) << 6) & 0x7F
```

#### Doubling ID Reference Table

| Doubling ID | Doubling Name | Hardware Pitch Shift Effect |
|-------------|---------------|-----------------------------|
| 0 | None | Doubling engine disabled |
| 1 | Octave Down | Second voice shifted -12 semitones |
| 2 | Octave Up | Second voice shifted +12 semitones |
| 3 | 4th Up | Second voice shifted +5 semitones |
| 4 | 5th Up | Second voice shifted +7 semitones |
| 5 | 7-String | Low B simulated on String 6 |
| 6 | 7-String 2 | Alternate low voicing |
| 7 | 12-String | Octave up on Strings 6, 5, 4, 3; Unison on Strings 2, 1 |
| 8 | 12-String 2 | Alternate 12-string octave voicing |
| 9 | Custom | Custom Q1.23 Pitch Matrix in Bytes 136..157 |

> **Note:** For Stock Doublings (0..8), the DSP internally synthesizes the factory intervals directly from Bytes 86/87. The Custom Doubling matrix in Bytes 136..157 remains neutral.

### 4.8 Noise Gate Threshold (Byte 91)

The Noise Gate threshold is stored directly in Byte 91. The physical parameter scale ranges from 0 (Off) to 22 (-30 dB) in linear 3 dB steps:

```python
gate_val = max(0, min(22, gate_slider_value))
packet[91] = (gate_val * 4) & 0x7F
```

#### Calibration Table

| Gate Parameter | Threshold (dB) | Byte 91 Hex | Byte 91 Dec | Formula |
|----------------|----------------|-------------|-------------|---------|
| 0 | Off | `0x00` | 0 | 0 × 4 = 0 |
| 1 | -93 dB | `0x04` | 4 | 1 × 4 = 4 |
| 5 | -81 dB | `0x14` | 20 | 5 × 4 = 20 |
| 12 | -60 dB (Mid) | `0x30` | 48 | 12 × 4 = 48 |
| 18 | -42 dB | `0x48` | 72 | 18 × 4 = 72 |
| 22 | -30 dB (Max) | `0x58` | 88 | 22 × 4 = 88 |

**Formula for UI display:**
```python
if gate_val == 0:
    Display "Off"
else:
    Display f"({-96 + gate_val * 3}) dB"
```

---

## 5. DSP Fixed-Point Q1.23 Mathematical Engine

The ATG processor operates on 24-bit fixed-point pitch multipliers in **Q1.23** format (1 integer bit, 23 fractional bits).

### 5.1 Cents to Q1.23 Conversion Formula

For a given detune offset in musical cents (where 100 cents = 1 semitone):

```
Pitch Ratio = 2.0 ** (cents / 1200.0)
Raw Value   = Pitch Ratio * 8388608.0
Q1.23 Value = ceil(Raw Value) & ~0b11
```

**Crucial Firmware Requirements:**
- **Ceiling Rounding (`ceil`)**: ATG firmware uses strict mathematical ceiling rounding (`math.ceil`) before integer truncation.
- **Phase Mask (`& ~0b11`)**: The two least-significant bits (bits 0 and 1) are reserved by the hardware interpolation engine and must always be zero (`& 0xFFFFFC`).
- **Neutral Unity Point**: 0 cents produces exactly `8388608` (`0x800000`, ratio 1.0).
- **The +1200 Cents Overflow Clamping**: A full octave up (+1200 cents) produces ratio 2.0 → `16777216` = 2²⁴, which does not fit in a 24-bit container. When passed 1200, it wraps around to `0x000000` (silencing the voice).  
  **Protection:** All positive cents must be clamped to 1199 cents before conversion:

```python
safe_cents = min(1199, cents)
```

This produces `16767528` (`0xFFD928`), a pitch deviation of under 0.0008 Hz that fits in 24 bits.

### 5.2 Universal Continuous 7-Bit Bitstream Serializer

MIDI SysEx packets require that data bytes never exceed `0x7F`. The function `write_bits_to_midi_stream` streams arbitrary N-bit words MSB-first into continuous 7-bit containers:

```python
def write_bits_to_midi_stream(buffer, start_byte, start_bit, value, num_bits):
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
```

### 5.3 Pitch Matrix Architecture (Tuning vs Doubling)

Each matrix consists of **6 strings × 24-bit Q1.23 pitch ratios = 144 bits total**.

**String Encoding Order:**  
The hardware always stores strings in descending pitch order: String 1 (High E) to String 6 (Low E).  
When taking a standard guitar tablature list `[Str 6, Str 5, Str 4, Str 3, Str 2, Str 1]`, the list must be reversed before serializing:

```python
antares_order_cents = list(reversed(tab_order_cents))
```

**Matrix Anchors:**
- Custom Tuning Matrix: Starts at Byte 95, Bit 3 (ends at Byte 115, Bit 4).
- Custom Doubling Matrix: Starts at Byte 136, Bit 2 (ends at Byte 157, Bit 6).

---

## 6. The 30-Bit Base-128 Checksum Engine

The preset checksum is validated by an internal hardware accumulator mapped to a 30-bit unsigned register (`total_accum & 0x3FFFFFFF`).

### 6.1 Baseline Origin

All checksum calculations originate from the canonical blank template accumulator baseline:

```
BASE_CHECKSUM_ACCUM = 0x472B4100  (Decimal: 149,610,624)
total_accum = (0x00 << 28) | (0x47 << 21) | (0x2B << 14) | (0x41 << 7) | 0x00
```

### 6.2 The 3-Phase Preset Name Weight Cycle

The 18-character preset name modifies the checksum according to a 3-phase repeating weight cycle modulo 24 bits:

```
ATG_NAME_WEIGHTS = [16384, 64, 4194304] * 6   # 18 entries total
```

- Characters 0,3,6,9,12,15 : Weight = 16384 (2¹⁴)
- Characters 1,4,7,10,13,16 : Weight = 64 (2⁶)
- Characters 2,5,8,11,14,17 : Weight = 4194304 (2²²)

```python
new_name_sum   = sum((ord(name[i]) & 0x7F) * ATG_NAME_WEIGHTS[i] for i in range(18))
blank_name_sum = sum((ord(blank[i]) & 0x7F) * ATG_NAME_WEIGHTS[i] for i in range(18))
total_accum += (new_name_sum - blank_name_sum)
```

*(For blank = `"BLANK "`, `blank_name_sum` is exactly 948,192,704).*

### 6.3 Comprehensive Parameter Delta Contributions

Every active preset parameter adds a deterministic delta to `total_accum`:

| Parameter | Multiplier / Delta Formula | Description |
|-----------|----------------------------|-------------|
| Preset Slot | `slot_idx * 64` | Target slot index (0..63) |
| Capo | `capo_val * 16384` | Capo semitone offset (-12..+12) |
| Pitch Shift Travel | `pitch_shift_val * 4194304` | Travel mode index (0..3) |
| Guitar Model | `model_id * 16384` | Model ID (0..10) |
| Pickup Position | `pickup_pos * 64` | Pickup position (0..4) |
| Doubling ID | `doubling_id * 16384` | Doubling mode ID (0..9) |
| Noise Gate | `16 * packet[91]` (or `gate_val * 64`) | Threshold (0..22) |
| Stock Tuning | `stock_tuning_id * 4194304` | Active when stock tuning is selected |
| Custom Tuning | `4194304 + sum(16 * (Q - 8388608))` | Base flag + Q1.23 delta per string |
| Custom Doubling | `sum(16 * (Q - 8388608))` | Active when Custom Doubling (id==9) is set |

### 6.4 Accumulator 30-Bit Clamping & Output Packing

Before writing to the final 5 bytes of the SysEx packet, the accumulator must be wrapped to 30 bits:

```python
total_accum &= 0x3FFFFFFF  # Mandatory 30-bit register wrap
```

The 30-bit integer is serialized into 5 continuous 7-bit words in Bytes 163..167:

- Byte 163: Bits [29..28] (only 2 bits wide! `(total_accum >> 28) & 0x03`)
- Byte 164: Bits [27..21] `((total_accum >> 21) & 0x7F)`
- Byte 165: Bits [20..14] `((total_accum >> 14) & 0x7F)`
- Byte 166: Bits [13..7] `((total_accum >> 7) & 0x7F)`
- Byte 167: Bits [6..0] `(total_accum & 0x7F)`

---

## 7. Reference Implementation

```python
import math
from typing import Dict, Any, List

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

ATG_NAME_WEIGHTS: List[int] = [16384, 64, 4194304] * 6

def cents_to_q123(cents: int) -> int:
    """Converts musical cents to DSP Q1.23 fixed-point format with overflow clamp."""
    if cents == 0:
        return 8388608
    safe_cents = min(1199, cents)
    raw = (2.0 ** (safe_cents / 1200.0)) * 8388608.0
    ceiled = math.ceil(raw)
    return ceiled & ~0b11

def write_bits_to_midi_stream(buffer: bytearray, start_byte: int, start_bit: int, value: int, num_bits: int):
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
    padded = name_str[:18].ljust(18, " ")
    return sum((ord(ch) & 0x7F) * ATG_NAME_WEIGHTS[i] for i, ch in enumerate(padded))

def encode_atg_name_canonical(buffer: bytearray, name_str: str) -> int:
    padded = name_str[:18].ljust(18, " ")
    raw_ascii = [ord(c) & 0x7F for c in padded]
    buffer[65] &= 0xF8
    for i in range(66, 86):
        buffer[i] = 0x00
    cur_byte, cur_bit = 65, 3
    for char_val in raw_ascii:
        cur_byte, cur_bit = write_bits_to_midi_stream(buffer, cur_byte, cur_bit, char_val, 8)
    return sum(raw_ascii[i] * ATG_NAME_WEIGHTS[i] for i in range(18))

def encode_matrix_q123(buffer: bytearray, start_byte: int, start_bit: int, cents_list: List[int]) -> int:
    cur_byte, cur_bit = start_byte, start_bit
    delta_accum = 0
    antares_order_cents = list(reversed(cents_list))
    for c in antares_order_cents:
        q_val = cents_to_q123(c)
        cur_byte, cur_bit = write_bits_to_midi_stream(buffer, cur_byte, cur_bit, q_val, 24)
        delta_accum += (q_val - 8388608)
    return delta_accum

def build_sysex_preset_packet(slot_idx: int, patch_dict: Dict[str, Any]) -> bytes:
    """Builds an authentic 169-byte SysEx preset packet for ATG/ ATG hardware."""
    packet = bytearray(BLANK_SYSEX_TEMPLATE)

    # 1. Preset Slot Destination (Byte 29: slot + 5)
    packet[29] = (slot_idx + 5) & 0x7F

    # 2. Solid-Tune Toggle (Byte 57)
    solid_on = patch_dict.get("solid_tune", True)
    packet[57] = 0x00 if solid_on else 0x10

    # 3. Tuning & Capo Configuration (Bytes 58, 59 and Matrix at Bytes 95..115)
    custom_cents = patch_dict.get("custom_tuning", [0] * 6)
    has_custom_tune = (patch_dict.get("tuning", 0) == 1)
    capo_val = patch_dict.get("capo", 0)
    stock_tuning = patch_dict.get("tuning", 0)
    base_flag = 0x01 if capo_val < 0 else 0x02

    if has_custom_tune:
        packet[58] = 0x0A if capo_val >= 0 else 0x09
        encode_matrix_q123(packet, 95, 3, custom_cents)
    else:
        packet[58] = (stock_tuning * 8) + base_flag

    if capo_val >= 0:
        packet[59] = ((capo_val << 2) | 0x01) & 0x7F
    else:
        packet[59] = (129 + capo_val * 4) & 0x7F

    # 4. Pitch Shift Travel (Byte 60)
    pitch_shift_val = patch_dict.get("pitch_shift", 0) & 0x03
    packet[60] = pitch_shift_val

    # 5. Guitar Model & Pickup Position (Unified 21-bit register across Bytes 62..64)
    model_id = patch_dict.get("model", 0)
    pickup_pos = patch_dict.get("pickup", 0)
    word_21 = (model_id << 13) | (pickup_pos << 5)
    packet[62] = (word_21 >> 14) & 0x7F
    packet[63] = (word_21 >> 7) & 0x7F
    packet[64] = word_21 & 0x7F

    # 6. Preset Name (18 ASCII characters across Bytes 65..85)
    name_str = patch_dict.get("name", "BLANK")
    new_name_sum = encode_atg_name_canonical(packet, name_str)
    blank_name_sum = compute_name_weight_sum("BLANK")

    # 7. Doubling Configuration (Bytes 86..87 and Matrix at Bytes 136..157)
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

    # 8. Noise Gate Threshold (Byte 91)
    gate_val = max(0, min(22, patch_dict.get("gate", 0)))
    packet[91] = (gate_val * 4) & 0x7F

    # 9. 30-Bit Base-128 Checksum Calculation
    total_accum = (0x00 << 28) | (0x47 << 21) | (0x2B << 14) | (0x41 << 7) | 0x00
    total_accum += (new_name_sum - blank_name_sum)
    total_accum += slot_idx * 64
    total_accum += capo_val * 16384
    total_accum += pitch_shift_val * 4194304
    total_accum += model_id * 16384
    total_accum += pickup_pos * 64
    total_accum += doubling_id * 16384
    total_accum += 16 * packet[91]

    if has_custom_tune:
        total_accum += 4194304
        for c in custom_cents:
            q = cents_to_q123(c)
            total_accum += 16 * (q - 8388608)
    else:
        total_accum += stock_tuning * 4194304

    if has_custom_double:
        for c in custom_double_cents:
            q = cents_to_q123(c)
            total_accum += 16 * (q - 8388608)

    # 30-bit hardware accumulator wrap
    total_accum &= 0x3FFFFFFF

    # Pack into Bytes 163..167
    packet[163] = (total_accum >> 28) & 0x03
    packet[164] = (total_accum >> 21) & 0x7F
    packet[165] = (total_accum >> 14) & 0x7F
    packet[166] = (total_accum >> 7) & 0x7F
    packet[167] = total_accum & 0x7F

    return bytes(packet)
```

---




# AT for Guitar (ATG) Preset Retrieve Protocol

Reverse-engineered specification and Python reference implementation for retrieving (reading) and unpacking the 64 preset slots directly from the **Peavey AT-200** / **ATG-1** hardware over standard MIDI System Exclusive (SysEx).

---

## Overview

The ATG uses proprietary SysEx messages (`Manufacturer ID: 00 01 26`). While write/flashing operations have historically been documented, preset extraction (reading from hardware) requires a specific session handshake, a Base-128 memory addressing formula, and a bit-level unpacking engine across 7-bit MIDI containers.

### Hardware Visual Feedback (LED Status)
* **Session Start (Unlock):** The guitar's active LED indicator **turns OFF** when the unlock sequence is initiated.
* **During Transfer:** The LED remains unlit while presets are being transferred.
* **Session End (Close):** The LED **turns back ON** immediately after receiving the session close command (`0x16`), confirming that the guitar has returned to normal performance mode.

---

## Communication Protocol & Session Lifecycle

Reading presets requires a strictly timed 4-phase sequence. Standard MIDI baud rate (31,250 bps) constraints apply.

Host (PC) Guitar (AT-200)
| |

|--- 1. Unlock Session (0x0E) -------------------------->| (Guitar LED turns OFF)

|<-- ACK (0x0F) -----------------------------------------|

| |

|--- 2. Handshake Phase (3 packets, 0x12) -------------->|

|<-- Handshake ACKs (0x13, includes 340B descriptor) ----|

| [Drain / Buffer Settle: 200-250 ms] |

| |

|--- 3. Preset Requests (0x1D, Slots 0..63) ------------>|

|<-- Preset Responses (0x1F, 114 bytes each) ------------|

| |

|--- 4. Close Session (0x16) --------------------------->| (Guitar LED turns back ON)

|<-- ACK (0x17) -----------------------------------------|


### Phase 1: Unlock Session
Initiates communication. The guitar's LED turns off.
* **TX:** `F0 00 01 26 00 0E F7` (7 bytes)
* **RX:** `F0 00 01 26 01 0F F7` (7 bytes)

### Phase 2: Memory Handshake
Three mandatory proprietary packets must be transmitted:
1. `F0 00 01 26 00 12 00 00 00 00 00 00 1C 00 00 03 40 F7` (18 bytes)  
   *RX response: 59 bytes (`0x13`)*
2. `F0 00 01 26 00 12 00 10 00 00 00 00 0C 00 20 01 40 F7` (18 bytes)  
   *RX response: 31 bytes (`0x13`)*
3. `F0 00 01 26 00 12 00 10 00 00 00 01 40 00 20 18 00 F7` (18 bytes)  
   *RX response: 340 bytes (`0x13`)*

> **CRITICAL TIMING NOTE:** Handshake ACK #3 transmits **340 bytes**. At 31,250 baud, this takes ~110 ms to transmit over the physical wire. The host **must wait at least 200–250 ms** and fully flush/drain the incoming MIDI buffer before requesting presets. Failing to do so will cause the first preset request to swallow this 340-byte residual packet, causing an **Off-by-One pipeline shift** where every preset is assigned to the wrong slot.

### Phase 3: Preset Data Requests (`0x1D`)
The guitar's 64 preset slots (0 to 63) are addressed using a continuous Base-128 MIDI container formula:

Address = (slot + 5) * 16 = (slot + 5) << 4
MSB = (Address >> 7) & 0x7F
LSB = Address & 0x7F

* **Request Packet (11 bytes):**  
  `F0 00 01 26 00 1D 00 00 [MSB] [LSB] F7`

| Slot Index | Formula `(slot + 5) << 4` | MSB | LSB | Request Bytes |
|:---|:---|:---:|:---:|:---|
| **Slot 00** | (0 + 5) * 16 = 80 | `0x00` | `0x50` | `F0 00 01 26 00 1D 00 00 00 50 F7` |
| **Slot 01** | (1 + 5) * 16 = 96 | `0x00` | `0x60` | `F0 00 01 26 00 1D 00 00 00 60 F7` |
| **Slot 02** | (2 + 5) * 16 = 112 | `0x00` | `0x70` | `F0 00 01 26 00 1D 00 00 00 70 F7` |
| **Slot 03** | (3 + 5) * 16 = 128 | `0x01` | `0x00` | `F0 00 01 26 00 1D 00 00 01 00 F7` |
| ... | ... | ... | ... | ... |
| **Slot 63** | (63 + 5) * 16 = 1088 | `0x08` | `0x40` | `F0 00 01 26 00 1D 00 00 08 40 F7` |

* **Response Packet (114 bytes):**  
  `F0 00 01 26 [dev] 1F [107 bytes Payload] F7`  
  *Valid preset packets must strictly be 114 bytes in length with command byte `0x1F` at index 5.*

### Phase 4: Close Session
Closes the communication channel and restores physical control. The guitar's LED turns back on.
* **TX:** `F0 00 01 26 00 16 F7` (7 bytes)
* **RX:** `F0 00 01 26 05 17 F7` (7 bytes)

---

## Preset Payload Bitstream Specification (107 Bytes)

All offsets refer to the payload buffer **after** stripping the 6-byte header (`F0 00 01 26 xx 1F`) and the terminating `F7`:

payload = raw_sysex[6:-1]   # 107 bytes total

### 1. Solid-Tune Toggle
* **Location:** `payload[3]`
* **Encoding:** `0x00` = ON, `0x10` = OFF
solid_tune = (payload[3] & 0x10) == 0

### 2. Tuning Engine & Capo
* **Locations:** `payload[4]` (Tuning ID & Capo Sign) and `payload[5]` (Capo Value)
* **Stock Tunings:** `0x02` = Standard, `0x1A` = Drop D, `0x2A` = DADGAD.
* **Custom Tuning Flag:** `0x09` or `0x0A`.

tuning_byte = payload[4]
is_custom_tune = tuning_byte in (0x09, 0x0A)
stock_tuning_id = (tuning_byte >> 3) & 0x0F

# Capo Decoding
b59 = payload[5]
if tuning_byte & 0x02:
    capo = b59 >> 2           # Non-negative (0 to +12)
else:
    capo = (b59 - 129) // 4   # Negative (-1 to -12)

### 3. Pitch Shift Travel
* **Location:** `payload[6]`
* **Modes:** `0` = Octave Up (+12), `1` = Octave Down (-12), `2` = Full Whammy (-12..+12), `3` = Detune/Chorus (-100c..+100c).
pitch_shift = payload[6] & 0x03

### 4. Guitar Model & Pickup Position (21-bit Register)
Packed across 3 MIDI 7-bit bytes (`payload[8]`, `payload[9]`, `payload[10]`):

word_21 = (payload[8] << 14) | (payload[9] << 7) | payload[10]
model_id   = (word_21 >> 13) & 0x7F
pickup_pos = (word_21 >> 5)  & 0x07

* **Pickup Positions:** `0` = Neck, `1` = Neck + Mid, `2` = Mid / Both, `3` = Mid + Bridge, `4` = Bridge.
* **Guitar Models:**
  * `0` = ModHB, `1` = VinHB HB, `2` = MiniHB, `3` = SBar, `4` = MMHSH, `5` = NasSC, `6` = CalSC, `7` = LStick, `8` = Acoustic, `9` = Bass, `10` = JPHSH.

### 5. Preset Name (18 ASCII Characters)
Starts at **Byte 11, bit 3** (MSB-first). Spans 144 bits across continuous 7-bit containers (bytes 11 through 31).

### 6. Doubling Engine
* **Locations:** `payload[32]` and `payload[33]`

b86 = payload[32]
b87 = payload[33]
if b86 == 0x04 and b87 == 0x40:
    doubling_id = 9   # Custom Doubling
else:
    doubling_id = ((b86 & 0x7F) << 1) | ((b87 >> 6) & 1)

### 7. Noise Gate Threshold
* **Location:** `payload[37]`
gate_threshold = (payload[37] >> 2) & 0x1F  # Range: 0 to 22

### 8. Custom Tuning & Doubling (Q1.23 Fixed-Point Math)
When Custom Tuning (`tuning == 1`) or Custom Doubling (`doubling == 9`) is enabled, a matrix of **6 strings x 24-bit fixed-point** values is packed into the stream:
* **Custom Tuning Offset:** Starts at **Byte 41, bit 3**.
* **Custom Doubling Offset:** Starts at **Byte 82, bit 2**.
* **Hardware String Order:** High E (String 1) to Low E (String 6). Reverse order for tablature representation (String 6 to 1).

The DSP representation maps 0 cents to 2^23 = 8,388,608.
Formula: cents = 1200 * log2(Q / 8388608)

---

## Standalone Python Reference Implementation

Requires `mido` and `python-rtmidi` (`pip install mido python-rtmidi`).

```python
import time
import math
from typing import Dict, Any, List, Tuple
import mido

def q123_to_cents(q_val: int) -> int:
    if q_val <= 0 or q_val == 8388608:
        return 0
    return int(round(1200.0 * math.log2(q_val / 8388608.0)))

def read_bits(buffer: bytes, start_byte: int, start_bit: int, num_bits: int) -> Tuple[int, int, int]:
    val = 0
    cur_byte, cur_bit = start_byte, start_bit
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

def unpack_preset(raw_sysex: bytes) -> Dict[str, Any]:
    payload = raw_sysex[6:-1]
    
    solid_tune = (payload[3] & 0x10) == 0
    tuning_byte = payload[4]
    is_custom_tune = tuning_byte in (0x09, 0x0A)
    tuning_id = 1 if is_custom_tune else ((tuning_byte >> 3) & 0x0F)
    
    b59 = payload[5]
    capo = (b59 >> 2) if (tuning_byte & 0x02) else ((b59 - 129) // 4)
    
    w21 = (payload[8] << 14) | (payload[9] << 7) | payload[10]
    model_id = (w21 >> 13) & 0x7F
    pickup_pos = (w21 >> 5) & 0x07
    
    cur_b, cur_bt = 11, 3
    chars = []
    for _ in range(18):
        c, cur_b, cur_bt = read_bits(payload, cur_b, cur_bt, 8)
        chars.append(chr(c & 0x7F))
    name = "".join(chars).rstrip()
    
    b86, b87 = payload[32], payload[33]
    double_id = 9 if (b86 == 0x04 and b87 == 0x40) else (((b86 & 0x7F) << 1) | ((b87 >> 6) & 1))
        
    custom_tuning = [0] * 6
    if is_custom_tune:
        cur_b, cur_bt = 41, 3
        q_cents = []
        for _ in range(6):
            q, cur_b, cur_bt = read_bits(payload, cur_b, cur_bt, 24)
            q_cents.append(q123_to_cents(q))
        custom_tuning = list(reversed(q_cents))
        
    return {
        "name": name,
        "model": model_id,
        "pickup": pickup_pos,
        "tuning": tuning_id,
        "capo": capo,
        "solid_tune": solid_tune,
        "double": double_id,
        "custom_tuning": custom_tuning
    }

def dump_guitar_presets(port_name: str) -> List[Dict[str, Any]]:
    out_port = mido.open_output(port_name)
    in_port = mido.open_input(port_name)
    
    def send(hex_cmd: str):
        data = bytes.fromhex(hex_cmd.replace(" ", ""))
        out_port.send(mido.Message("sysex", data=list(data[1:-1])))

    # 1. Unlock Session (Guitar LED turns OFF)
    send("F0 00 01 26 00 0E F7")
    time.sleep(0.08)

    # 2. Handshake Phase
    handshake = [
        "F0 00 01 26 00 12 00 00 00 00 00 00 1C 00 00 03 40 F7",
        "F0 00 01 26 00 12 00 10 00 00 00 00 0C 00 20 01 40 F7",
        "F0 00 01 26 00 12 00 10 00 00 00 01 40 00 20 18 00 F7"
    ]
    for pkt in handshake:
        send(pkt)
        time.sleep(0.05)

    # Wait for the 340-byte descriptor and drain incoming queue
    time.sleep(0.25)
    for _ in in_port.iter_pending():
        pass

    presets = []

    # 3. Retrieve 64 Preset Slots
    for slot in range(64):
        for _ in in_port.iter_pending():
            pass

        addr = (slot + 5) << 4
        msb = (addr >> 7) & 0x7F
        lsb = addr & 0x7F
        req = bytes([0xF0, 0x00, 0x01, 0x26, 0x00, 0x1D, 0x00, 0x00, msb, lsb, 0xF7])
        out_port.send(mido.Message("sysex", data=list(req[1:-1])))

        raw_preset = None
        t0 = time.time()
        while time.time() - t0 < 0.35:
            msg = in_port.poll()
            if msg and msg.type == "sysex":
                full = bytes([0xF0] + list(msg.data) + [0xF7])
                if len(full) == 114 and len(full) > 5 and full[5] == 0x1F:
                    raw_preset = full
                    break
            time.sleep(0.003)

        if raw_preset:
            p = unpack_preset(raw_preset)
            print(f"Slot {slot:02d}: '{p['name']}' | Model: {p['model']} | Tuning: {p['tuning']}")
            presets.append(p)
        else:
            print(f"Slot {slot:02d}: TIMEOUT")
            presets.append({"name": f"EMPTY {slot:02d}"})

    # 4. Close Session (Guitar LED turns back ON)
    send("F0 00 01 26 00 16 F7")
    time.sleep(0.05)

    out_port.close()
    in_port.close()
    return presets

if __name__ == "__main__":
    ports = mido.get_output_names()
    target_ports = [p for p in ports if not any(k in p.lower() for k in ("through", "rtp"))]
    if target_ports:
        print(f"Connecting to MIDI device: {target_ports[0]}")
        dump_guitar_presets(target_ports[0])
    else:
        print("No MIDI interface detected.")
```

---


License

MIT License. Open for reverse engineers, musicians, and developers preserving and extending the AT for Guitar ecosystem.


**Document Version 1.0.0** — Reverse-engineered for interoperability and community preservation.  
Contributions and validations welcome.



