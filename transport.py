#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Peavey AT-200 Master Controller — Transport Module (transport.py)
Handles native MIDI (Mido) and raw Serial (PySerial) communication
with the guitar and the Arduino StrapBox hardware.
All comments, docstrings, and symbols are strictly in English.
"""

import time
from typing import List, Dict, Any, Tuple, Optional

import serial
from serial.tools import list_ports

try:
    import mido
    MIDO_AVAILABLE = True
except ImportError:
    MIDO_AVAILABLE = False

from core import (
    CONN_STANDALONE,
    CONN_ARDUINO,
    CONN_MIDI_IFACE
)

# Hardware SysEx control commands
CMD_FLASH_PRESET_UNLOCK = bytes([0xF0, 0x00, 0x01, 0x26, 0x00, 0x0E, 0xF7])
CMD_FLASH_PRESET_COMMIT = bytes([0xF0, 0x00, 0x01, 0x26, 0x00, 0x16, 0xF7])


class HardwareTransport:
    """Manages active hardware communication channels (MIDI or Serial)."""

    def __init__(self) -> None:
        self.conn_type: str = CONN_STANDALONE
        self.status_message: str = "Standalone"
        self.status_color: str = "#bdc3c7"
        self.serial_conn: Optional[serial.Serial] = None
        self.midi_out = None
        self.midi_in = None
        self.guitar_online: bool = False

    def close(self) -> None:
        """Closes all active serial and MIDI connections."""
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
            except Exception as err:
                print(f"[Transport] Error closing serial port: {err}")
        self.serial_conn = None

        if self.midi_out:
            try:
                self.midi_out.close()
            except Exception as err:
                print(f"[Transport] Error closing MIDI output: {err}")
        self.midi_out = None

        if self.midi_in:
            try:
                self.midi_in.close()
            except Exception as err:
                print(f"[Transport] Error closing MIDI input: {err}")
        self.midi_in = None

        self.conn_type = CONN_STANDALONE
        self.status_message = "Mode: Standalone (Offline)"
        self.status_color = "#bdc3c7"

    def detect_hardware(self) -> Tuple[str, str, str]:
        self.close()

        # 1. Tentativa de ligação MIDI Nativa
        if MIDO_AVAILABLE:
            try:
                out_ports = mido.get_output_names()
                in_ports = mido.get_input_names()
                ignored_keywords = ("through", "timidity", "loop", "rtp")

                for p_out in out_ports:
                    if not any(k in p_out.lower() for k in ignored_keywords):
                        try:
                            self.midi_out = mido.open_output(p_out)
                            for p_in in in_ports:
                                if not any(k in p_in.lower() for k in ignored_keywords):
                                    self.midi_in = mido.open_input(p_in)
                                    break

                            self.conn_type = CONN_MIDI_IFACE
                            
                            # VERIFICAÇÃO ATIVA DA GUITARRA (PING)
                            if self.ping_guitar(timeout=0.25):
                                self.status_message = "AT-200 Connected"
                                self.status_color = "#2ecc71"  # Verde
                                self.guitar_online = True
                            else:
                                self.status_message = "MIDI Ready (Guitar Offline)"
                                self.status_color = "#f39c12"  # Laranja
                                self.guitar_online = False

                            return self.conn_type, self.status_message, self.status_color
                        except Exception as midi_err:
                            print(f"[Transport] Failed to open MIDI port {p_out}: {midi_err}")
            except Exception as scan_err:
                print(f"[Transport] MIDI enumeration warning: {scan_err}")

        # 2. Attempt Arduino / StrapBox Serial connection
        for port in list_ports.comports():
            dev = port.device.lower()
            desc = port.description.lower()

            is_nix_port = any(k in dev for k in ("ttyusb", "ttyacm", "usbserial", "usbmodem", "cu."))
            is_known_hw = any(k in desc for k in ("arduino", "ch34", "usb-serial", "usb serial", "ftdi", "cp210"))
            is_win_com = dev.startswith("com")

            if is_nix_port or is_known_hw or (is_win_com and is_known_hw):
                try:
                    dev_path = port.device.replace("/dev/tty.", "/dev/cu.")
                    self.serial_conn = serial.Serial(dev_path, baudrate=31250, timeout=0.5)
                    time.sleep(1.8)  # Allow Arduino bootloader to initialize
                    self.serial_conn.write(b"\x55")  # Handshake ping

                    self.conn_type = CONN_ARDUINO
                    self.status_message = f"Serial Connected"
                    self.status_color = "#3498db"
                    return self.conn_type, self.status_message, self.status_color
                except Exception as serial_err:
                    print(f"[Transport] Serial port warning on {port.device}: {serial_err}")

        # 3. Fallback to Standalone
        self.conn_type = CONN_STANDALONE
        self.status_message = "Standalone Mode"
        self.status_color = "#bdc3c7"
        return self.conn_type, self.status_message, self.status_color

    def send_cc(self, control: int, value: int) -> bool:
        """Sends a standard MIDI Control Change message."""
        if self.conn_type == CONN_STANDALONE:
            return False

        ctrl = control & 0x7F
        val = value & 0x7F

        if self.conn_type == CONN_MIDI_IFACE and self.midi_out:
            try:
                msg = mido.Message("control_change", channel=0, control=ctrl, value=val)
                self.midi_out.send(msg)
                return True
            except Exception as err:
                print(f"[Transport] MIDI CC error: {err}")
                return False

        if self.conn_type == CONN_ARDUINO and self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.write(bytes([0xB0, ctrl, val]))
                return True
            except Exception as err:
                print(f"[Transport] Serial CC error: {err}")
                return False

        return False

    def send_pc(self, program: int) -> bool:
        """Sends a standard MIDI Program Change message."""
        if self.conn_type == CONN_STANDALONE:
            return False

        prog = program & 0x7F

        if self.conn_type == CONN_MIDI_IFACE and self.midi_out:
            try:
                msg = mido.Message("program_change", channel=0, program=prog)
                self.midi_out.send(msg)
                return True
            except Exception as err:
                print(f"[Transport] MIDI PC error: {err}")
                return False

        if self.conn_type == CONN_ARDUINO and self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.write(bytes([0xC0, prog]))
                return True
            except Exception as err:
                print(f"[Transport] Serial PC error: {err}")
                return False

        return False

    def send_sysex(self, data_bytes: bytes) -> bool:
        """Transmits a SysEx stream to the target hardware."""
        if self.conn_type == CONN_STANDALONE or not data_bytes:
            return False

        if self.conn_type == CONN_MIDI_IFACE and self.midi_out:
            try:
                # Mido SysEx expects data payload without bounding F0 and F7
                payload = list(data_bytes[1:-1])
                msg = mido.Message("sysex", data=payload)
                self.midi_out.send(msg)
                return True
            except Exception as err:
                print(f"[Transport] MIDI SysEx error: {err}")
                return False

        if self.conn_type == CONN_ARDUINO and self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.write(data_bytes)
                self.serial_conn.flush()
                return True
            except Exception as err:
                print(f"[Transport] Serial SysEx error: {err}")
                return False

        return False

    def flash_preset_to_guitar(self, sysex_payload: bytes) -> bool:
        """
        Executes the three-phase hardware preset flash sequence:
        1. Flash Unlock Command (0x0E)
        2. Preset SysEx Payload (169 bytes)
        3. Flash Commit Command (0x16)
        """
        if self.conn_type == CONN_STANDALONE:
            return False

        try:
            self.send_sysex(CMD_FLASH_PRESET_UNLOCK)
            time.sleep(0.1)

            self.send_sysex(sysex_payload)
            time.sleep(0.1)

            self.send_sysex(CMD_FLASH_PRESET_COMMIT)
            time.sleep(0.5)
            return True
        except Exception as err:
            print(f"[Transport] Preset flash failed: {err}")
            return False

    def sync_strapbox_eeprom(
        self,
        patches_data: List[Dict[str, Any]],
        groups_data: List[Dict[str, Any]],
        index_map: Dict[str, int]
    ) -> bool:
        """
        Synchronizes preset names and performance group configurations
        into the Arduino StrapBox internal EEPROM storage.
        """
        if self.conn_type != CONN_ARDUINO or not self.serial_conn or not self.serial_conn.is_open:
            return False

        try:
            # EEPROM Sync trigger byte
            self.serial_conn.write(b"\xEE")
            time.sleep(0.05)

            # 1. 64 Preset Names (10 ASCII chars each = 640 bytes)
            payload_names = bytearray()
            for i in range(64):
                raw_name = patches_data[i].get("name", "EMPTY")[:10]
                payload_names.extend(raw_name.encode("ascii", errors="ignore").ljust(10, b" "))

            # 2. 10 Performance Groups (10 bytes name + 4 bytes slot indices = 140 bytes)
            payload_groups = bytearray()
            for g in groups_data:
                g_name = g.get("name", "GROUP")[:10].encode("ascii", errors="ignore").ljust(10, b" ")
                slots_idx = []
                for s in g.get("slots", ["EMPTY"] * 4):
                    if isinstance(s, int):
                        slots_idx.append(s if 0 <= s < 64 else 0)
                    else:
                        slots_idx.append(index_map.get(str(s).lower(), 0))
                payload_groups.extend(g_name + bytes(slots_idx[:4]))

            # 3. Default Preset Index (1 byte)
            def_val = groups_data[0].get("default_patch", "EMPTY")
            if isinstance(def_val, int) and 0 <= def_val < 64:
                def_byte = def_val
            else:
                def_byte = index_map.get(str(def_val).lower(), 0)

            full_payload = payload_names + payload_groups + bytes([def_byte])

            # Transmit byte-by-byte with small pacing interval to avoid Arduino buffer overrun
            for byte_val in full_payload:
                self.serial_conn.write(bytes([byte_val]))
                time.sleep(0.004)

            self.serial_conn.flush()
            return True

        except Exception as err:
            print(f"[Transport] StrapBox EEPROM sync failed: {err}")
            return False

    # --- Adicionar dentro da classe HardwareTransport em transport.py ---

    def recall_all_presets_from_guitar(self, progress_callback=None) -> List[Dict[str, Any]]:
        """
        Executa a sequência de handshake e descarrega os 64 presets da Peavey AT-200.
        Garante sincronização estrita sem desfasamento de slots.
        """
        from core import unpack_sysex_preset_packet, create_empty_patch

        if self.conn_type != CONN_MIDI_IFACE or not self.midi_out or not self.midi_in:
            return []

        # 1. Unlock
        self.send_sysex(bytes.fromhex("F0 00 01 26 00 0E F7"))
        time.sleep(0.08)

        # 2. Handshake obrigatório (3 pacotes proprietários)
        handshake = [
            "F0 00 01 26 00 12 00 00 00 00 00 00 1C 00 00 03 40 F7",
            "F0 00 01 26 00 12 00 10 00 00 00 00 0C 00 20 01 40 F7",
            "F0 00 01 26 00 12 00 10 00 00 00 01 40 00 20 18 00 F7"
        ]
        for pkt in handshake:
            self.send_sysex(bytes.fromhex(pkt.replace(" ", "")))
            time.sleep(0.05)

        # O Handshake 3 devolve 340 bytes (~110ms a 31250 baud).
        # Aguardamos 250ms para garantir que a guitarra terminou a transmissão.
        time.sleep(0.25)
        for _ in self.midi_in.iter_pending():
            pass

        recalled_patches = []

        # 3. Pedidos individuais dos 64 slots: (slot + 5) << 4
        for slot in range(64):
            # Limpa qualquer resíduo antes de emitir o pedido
            for _ in self.midi_in.iter_pending():
                pass

            addr = (slot + 5) << 4
            msb = (addr >> 7) & 0x7F
            lsb = addr & 0x7F

            req = bytes([0xF0, 0x00, 0x01, 0x26, 0x00, 0x1D, 0x00, 0x00, msb, lsb, 0xF7])
            self.send_sysex(req)

            resp_packet = None
            t0 = time.time()
            while time.time() - t0 < 0.35:
                msg = self.midi_in.poll()
                if msg and msg.type == "sysex":
                    full = bytes([0xF0] + list(msg.data) + [0xF7])
                    # FILTRO ESTRITO: tem de ser uma resposta de preset válida (114 bytes e comando 0x1F)
                    if len(full) == 114 and len(full) > 5 and full[5] == 0x1F:
                        resp_packet = full
                        break
                time.sleep(0.003)

            if resp_packet:
                patch = unpack_sysex_preset_packet(resp_packet)
            else:
                patch = create_empty_patch(f"EMPTY {slot:02d}")

            recalled_patches.append(patch)

            if progress_callback:
                progress_callback(slot + 1, 64)

        # 4. Fecho da Sessão
        self.send_sysex(bytes.fromhex("F0 00 01 26 00 16 F7"))
        time.sleep(0.05)

        return recalled_patches

    def upload_all_presets_to_guitar(self, patches: List[Dict[str, Any]], progress_callback=None) -> bool:
        """
        Grava os 64 presets na memória flash da Peavey AT-200.
        Funciona via Interface MIDI Nativa E via Arduino StrapBox (Serial Forward).
        """
        from core import build_sysex_preset_packet

        # Só bloqueia se estiver em modo Standalone (sem nenhum hardware ligado)
        if self.conn_type == CONN_STANDALONE:
            return False

        try:
            # 1. Unlock da Memória Flash (0x0E)
            self.send_sysex(CMD_FLASH_PRESET_UNLOCK)
            time.sleep(0.12)

            # 2. Envio sequencial dos 64 pacotes SysEx de 169 bytes
            for slot in range(64):
                patch_data = patches[slot] if slot < len(patches) else {}
                sysex_payload = build_sysex_preset_packet(slot, patch_data)
                
                self.send_sysex(sysex_payload)
                # Pausa para a flash da guitarra processar o pacote
                time.sleep(0.08)

                if progress_callback:
                    progress_callback(slot + 1, 64)

            # 3. Commit e Fecho da Gravação Flash (0x16)
            time.sleep(0.1)
            self.send_sysex(CMD_FLASH_PRESET_COMMIT)
            time.sleep(0.3)
            return True

        except Exception as err:
            print(f"[Transport] Falha no upload em bloco: {err}")
            return False

    def update_strapbox_single_name(self, slot_idx: int, name: str) -> bool:
        """
        Atualiza o nome de um único preset na EEPROM do StrapBox (comando 0xED).
        Transmite apenas 12 bytes: [0xED, slot_id, 10 chars ASCII].
        Execução praticamente instantânea (< 40ms).
        """
        if self.conn_type != CONN_ARDUINO or not self.serial_conn or not self.serial_conn.is_open:
            return False

        try:
            # Formata o nome para exatamente 10 caracteres ASCII
            clean_name = name[:10].encode("ascii", errors="ignore").ljust(10, b" ")
            slot_byte = slot_idx & 0x3F  # 0 a 63

            # Pacote: 0xED + Slot + 10 bytes de texto
            packet = bytes([0xED, slot_byte]) + clean_name
            
            self.serial_conn.write(packet)
            self.serial_conn.flush()
            return True
        except Exception as err:
            print(f"[Transport] Erro ao atualizar nome no StrapBox: {err}")
            return False

    def ping_guitar(self, timeout: float = 0.25) -> bool:
        """
        Envia uma sonda de Unlock (0x0E) para verificar se a guitarra está ligada e alimentada.
        Devolve True se a guitarra responder com o ACK 0x0F, False caso contrário.
        """
        if self.conn_type != CONN_MIDI_IFACE or not self.midi_out or not self.midi_in:
            return False

        # Limpa qualquer resíduo anterior no buffer
        for _ in self.midi_in.iter_pending():
            pass

        # Envia pedido de Unlock (0x0E)
        self.send_sysex(bytes.fromhex("F0 00 01 26 00 0E F7"))

        t0 = time.time()
        while time.time() - t0 < timeout:
            msg = self.midi_in.poll()
            if msg and msg.type == "sysex":
                full = bytes([0xF0] + list(msg.data) + [0xF7])
                # Confirma se é o ACK do Unlock (F0 00 01 26 01 0F F7)
                if len(full) == 7 and full[5] == 0x0F:
                    return True
            time.sleep(0.005)

        return False