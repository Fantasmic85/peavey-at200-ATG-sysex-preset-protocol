#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ATGMaster Controller — UI Module (ui.py)
Desktop Graphical User Interface built with PyQt6.
Faithful 1:1 replica of the original layout, modularized to use
core, transport, and librarian components with zero linter warnings.
All comments, docstrings, and symbols are strictly in English.
"""

import os
from typing import Dict, Any

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QListWidget, QListWidgetItem, QTabWidget, QLabel,
    QSlider, QComboBox, QTextEdit, QMessageBox, QGroupBox,
    QCheckBox, QSpinBox, QDialog, QFormLayout, QLineEdit, QDialogButtonBox,
    QFileDialog, QProgressDialog
)

from core import (
    GUITAR_MODELS_13,
    TUNINGS,
    DOUBLINGS,
    DTRNSP,
    PITCH_SHIFT_MODES,
    STRING_LABELS,
    BASE_NOTES_TAB,
    CONN_STANDALONE,
    CONN_ARDUINO,
    CONN_MIDI_IFACE,
    BACKUPS_DIR,
    get_icon_path,
    midi_num_to_name,
    build_sysex_preset_packet
)
from transport import HardwareTransport
from librarian import PatchLibrarian


class SavePatchDialog(QDialog):
    """Modal dialog allowing the user to specify preset name and target slot."""

    def __init__(self, parent: QWidget, initial_name: str, current_slot: int, patches: list) -> None:
        super().__init__(parent)
        self.setWindowTitle("Save Preset")
        self.setFixedWidth(340)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.edit_name = QLineEdit(initial_name)
        self.edit_name.setMaxLength(18)
        form.addRow("Preset Name:", self.edit_name)

        self.combo_slot = QComboBox()
        for i in range(64):
            p_name = patches[i].get("name", "EMPTY")
            self.combo_slot.addItem(f"Slot {i:02d}: {p_name}")
        self.combo_slot.setCurrentIndex(current_slot)
        form.addRow("Target Slot:", self.combo_slot)

        layout.addLayout(form)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_values(self) -> tuple[str, int]:
        """Returns sanitized name and target slot index."""
        raw_name = self.edit_name.text().strip()
        sanitized_name = raw_name[:18] if raw_name else "EMPTY"
        return sanitized_name, self.combo_slot.currentIndex()

class AT200MainWindow(QWidget):
    """Main application window replicating the original AT-200 controller UI."""

    def __init__(self, transport: HardwareTransport, librarian: PatchLibrarian) -> None:
        super().__init__()
        self.transport = transport
        self.librarian = librarian

        self.setWindowTitle("ATGMaster Controller")
        self.resize(1380, 800)

        self.is_loading_ui: bool = False
        self.current_slot: int = 0

        self.init_ui()
        self.detect_hardware()

        # Só corre o retrieve se a guitarra estiver fisicamente ligada e a responder
        if self.transport.conn_type == CONN_MIDI_IFACE and getattr(self.transport, "guitar_online", False):
            self.auto_recall_guitar_presets()

        self.patch_list.setCurrentRow(0)

    # --------------------------------------------------------------------------
    # UI CONSTRUCTION
    # --------------------------------------------------------------------------
    def init_ui(self) -> None:
        main_layout = QHBoxLayout(self)

        # Left Panel
        left_panel = QVBoxLayout()

        self.lbl_status = QLabel("Checking connection...")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: #bdc3c7; font-size: 11px; padding: 2px;")
        left_panel.addWidget(self.lbl_status)

        self.lbl_working_name = QLabel("[00] EMPTY")
        self.lbl_working_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_working_name.setFixedHeight(30)
        self.lbl_working_name.setStyleSheet("""
            QLabel {
                background-color: #2c3e50;
                color: #ecf0f1;
                font-size: 12px;
                font-weight: bold;
                border: 1px solid #34495e;
                border-radius: 4px;
                padding: 2px 4px;
            }
        """)
        left_panel.addWidget(self.lbl_working_name)
        
        # self.btn_upload = QPushButton("Upload to Hardware")
        # self.btn_upload.clicked.connect(self.upload_all_to_hardware)
        # left_panel.addWidget(self.btn_upload)

        self.patch_list = QListWidget()
        self.patch_list.setFixedWidth(220)
        self.patch_list.setEditTriggers(
            QListWidget.EditTrigger.DoubleClicked | QListWidget.EditTrigger.SelectedClicked
        )
        self.patch_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)

        list_model = self.patch_list.model()
        if list_model is not None:
            list_model.rowsMoved.connect(self.on_patch_rows_moved)

        self.patch_list.itemChanged.connect(self.on_patch_item_renamed)
        self.patch_list.currentRowChanged.connect(self.on_patch_selected)
        self.populate_patch_list()
        left_panel.addWidget(self.patch_list)

        btn_box = QVBoxLayout()
        self.btn_modify = QPushButton("Modify")
        self.btn_save = QPushButton("Save")
        self.btn_clear = QPushButton("Clear")
        
        self.btn_modify.clicked.connect(self.save_current_patch)
        self.btn_save.clicked.connect(self.save_patch_as)
        self.btn_clear.clicked.connect(self.clear_current_slot)
        
        btn_box.addWidget(self.btn_modify)
        btn_box.addWidget(self.btn_save)
        btn_box.addWidget(self.btn_clear)
        left_panel.addLayout(btn_box)

        box_panic = QGroupBox("Default Patch")
        v_panic = QVBoxLayout(box_panic)
        v_panic.setContentsMargins(6, 6, 6, 6)
        self.combo_default_patch = QComboBox()
        self.update_default_patch_combo()
        self.combo_default_patch.currentIndexChanged.connect(self.on_default_patch_selected)
        v_panic.addWidget(self.combo_default_patch)
        left_panel.addWidget(box_panic)

        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText("Patch notes...")
        self.txt_notes.setFixedHeight(85)
        self.txt_notes.textChanged.connect(self.on_notes_changed)
        left_panel.addWidget(self.txt_notes)

        main_layout.addLayout(left_panel)

        # Center Tabs
        self.tabs = QTabWidget()
        self.tab_preset = QWidget()
        self.tab_global = QWidget()

        self.build_preset_tab()
        self.build_global_tab()

        self.tabs.addTab(self.tab_preset, "Preset Settings")
        self.tabs.addTab(self.tab_global, "Global Parameters")
        main_layout.addWidget(self.tabs, stretch=2)

        # Right Panel
        self.build_groups_panel(main_layout)

    # --------------------------------------------------------------------------
    # TAB 1: PRESET SETTINGS
    # --------------------------------------------------------------------------
    def build_preset_tab(self) -> None:
        layout = QVBoxLayout(self.tab_preset)

        # 13 Models Grid
        grp_models = QGroupBox("Guitar Models (13 Models)")
        grid_models = QGridLayout(grp_models)
        grid_models.setSpacing(6)
        self.model_buttons = []

        for idx, m in enumerate(GUITAR_MODELS_13):
            btn = QPushButton()
            icon_path = get_icon_path(m["icon"])
            if os.path.exists(icon_path):
                btn.setIcon(QIcon(icon_path))
                btn.setIconSize(QSize(150, 150))

            btn.setFixedSize(172, 162)
            btn.setCheckable(True)
            btn.setToolTip(f"<b>{m['name']}</b> ({m['type']})")
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.05);
                    border: 2px solid transparent;
                    border-radius: 8px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.12);
                }
                QPushButton:checked {
                    background-color: rgba(52, 152, 219, 0.25);
                    border: 2px solid #3498db;
                }
            """)
            btn.clicked.connect(lambda _, i=idx: self.select_guitar_model(i))
            grid_models.addWidget(btn, idx // 7, idx % 7)
            self.model_buttons.append(btn)

        spacer = QWidget()
        spacer.setFixedSize(172, 162)
        grid_models.addWidget(spacer, 1, 6)
        layout.addWidget(grp_models)

        # Pickup Selector
        self.grp_pickups = QGroupBox("Pickup Position")
        self.layout_pickups = QHBoxLayout(self.grp_pickups)
        self.layout_pickups.setSpacing(12)
        self.layout_pickups.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pickup_buttons = []
        layout.addWidget(self.grp_pickups)

        # Performance Controls
        grp_perf = QGroupBox("Performance Controls")
        h_perf_layout = QHBoxLayout(grp_perf)

        # Left Column: Capo & Noise Gate Sliders
        v_left_perf = QVBoxLayout()
        grid_sliders = QGridLayout()

        grid_sliders.addWidget(QLabel("Capo:"), 0, 0)
        self.slider_capo = QSlider(Qt.Orientation.Horizontal)
        self.slider_capo.setRange(-12, 12)
        self.slider_capo.setValue(0)
        self.lbl_capo = QLabel("0")
        self.lbl_capo.setFixedWidth(30)
        self.slider_capo.valueChanged.connect(self.on_capo_changed)
        grid_sliders.addWidget(self.slider_capo, 0, 1)
        grid_sliders.addWidget(self.lbl_capo, 0, 2)

        grid_sliders.addWidget(QLabel("Noise Gate:"), 1, 0)
        self.slider_gate = QSlider(Qt.Orientation.Horizontal)
        self.slider_gate.setRange(0, 22)
        self.slider_gate.setValue(0)
        self.lbl_gate = QLabel("TH 0")
        self.lbl_gate.setFixedWidth(40)
        self.slider_gate.valueChanged.connect(self.on_gate_changed)
        grid_sliders.addWidget(self.slider_gate, 1, 1)
        grid_sliders.addWidget(self.lbl_gate, 1, 2)

        v_left_perf.addLayout(grid_sliders)
        h_perf_layout.addLayout(v_left_perf, stretch=3)

        # Right Column: Solid-Tune & Pitch Shift Travel
        v_right_perf = QVBoxLayout()

        self.btn_stune = QPushButton("Solid-Tune: ON")
        self.btn_stune.setCheckable(True)
        self.btn_stune.setChecked(True)
        self.btn_stune.clicked.connect(self.on_stune_toggle)
        v_right_perf.addWidget(self.btn_stune)

        h_shift = QHBoxLayout()
        h_shift.addWidget(QLabel("Fx Pedal - Pitch Shift Travel:"))
        self.combo_pitch_shift = QComboBox()
        self.combo_pitch_shift.addItems(PITCH_SHIFT_MODES)
        h_shift.addWidget(self.combo_pitch_shift)
        v_right_perf.addLayout(h_shift)

        h_perf_layout.addLayout(v_right_perf, stretch=2)
        layout.addWidget(grp_perf)

        # Custom Tuning and Doubling (Side by Side)
        h_custom_engines = QHBoxLayout()

        # Tuning Engine
        self.grp_custom_tuning = QGroupBox("Tuning")
        v_tune = QVBoxLayout(self.grp_custom_tuning)

        h_tune_header = QHBoxLayout()
        h_tune_header.addWidget(QLabel("Preset:"))
        self.combo_tuning = QComboBox()
        self.combo_tuning.addItems(TUNINGS)
        self.combo_tuning.currentIndexChanged.connect(self.on_tuning_changed)
        h_tune_header.addWidget(self.combo_tuning, stretch=1)

        self.chk_fine_tune = QCheckBox("Fine (cents)")
        self.chk_fine_tune.toggled.connect(self.on_toggle_fine_tune)
        h_tune_header.addWidget(self.chk_fine_tune)

        btn_reset_tune = QPushButton("Reset")
        btn_reset_tune.clicked.connect(self.reset_custom_tuning)
        h_tune_header.addWidget(btn_reset_tune)
        v_tune.addLayout(h_tune_header)

        grid_tune = QGridLayout()
        grid_tune.setContentsMargins(0, 4, 0, 0)
        grid_tune.setHorizontalSpacing(10)
        grid_tune.setVerticalSpacing(3)

        self.tune_sliders = []
        self.tune_spinboxes = []
        self.tune_note_labels = []

        for i in range(6):
            lbl_str = QLabel(STRING_LABELS[i])
            lbl_str.setFixedWidth(42)

            lbl_note = QLabel(midi_num_to_name(BASE_NOTES_TAB[i]))
            lbl_note.setFixedWidth(32)
            lbl_note.setStyleSheet("font-weight: bold; color: #3498db;")

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(-12, 12)
            slider.setValue(0)

            spin = QSpinBox()
            spin.setRange(-2400, 2400)
            spin.setValue(0)
            spin.setSuffix(" c")
            spin.setFixedWidth(68)
            spin.setEnabled(False)

            slider.valueChanged.connect(lambda val, idx=i: self.on_tune_slider_changed(idx, val))
            spin.valueChanged.connect(lambda val, idx=i: self.on_tune_spin_changed(idx, val))

            grid_tune.addWidget(lbl_str, i, 0)
            grid_tune.addWidget(lbl_note, i, 1)
            grid_tune.addWidget(slider, i, 2)
            grid_tune.addWidget(spin, i, 3)

            self.tune_sliders.append(slider)
            self.tune_spinboxes.append(spin)
            self.tune_note_labels.append(lbl_note)

        v_tune.addLayout(grid_tune)
        h_custom_engines.addWidget(self.grp_custom_tuning)

        # Doubling Engine
        self.grp_custom_doubling = QGroupBox("Doubling")
        v_dbl = QVBoxLayout(self.grp_custom_doubling)

        h_dbl_header = QHBoxLayout()
        h_dbl_header.addWidget(QLabel("Preset:"))
        self.combo_double = QComboBox()
        self.combo_double.addItems(DOUBLINGS)
        self.combo_double.currentIndexChanged.connect(self.on_double_changed)
        h_dbl_header.addWidget(self.combo_double, stretch=1)

        self.chk_fine_dbl = QCheckBox("Fine (cents)")
        self.chk_fine_dbl.toggled.connect(self.on_toggle_fine_dbl)
        h_dbl_header.addWidget(self.chk_fine_dbl)

        btn_reset_dbl = QPushButton("Reset")
        btn_reset_dbl.clicked.connect(self.reset_custom_doubling)
        h_dbl_header.addWidget(btn_reset_dbl)
        v_dbl.addLayout(h_dbl_header)

        grid_dbl = QGridLayout()
        grid_dbl.setContentsMargins(0, 4, 0, 0)
        grid_dbl.setHorizontalSpacing(10)
        grid_dbl.setVerticalSpacing(3)

        self.dbl_sliders = []
        self.dbl_spinboxes = []
        self.dbl_labels = []

        for i in range(6):
            lbl_str = QLabel(STRING_LABELS[i])
            lbl_str.setFixedWidth(42)

            lbl_interval = QLabel("Off")
            lbl_interval.setFixedWidth(42)
            lbl_interval.setStyleSheet("font-weight: bold; color: #2ecc71;")

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(-12, 12)
            slider.setValue(0)

            spin = QSpinBox()
            spin.setRange(-2400, 2400)
            spin.setValue(0)
            spin.setSuffix(" c")
            spin.setFixedWidth(68)
            spin.setEnabled(False)

            slider.valueChanged.connect(lambda val, idx=i: self.on_dbl_slider_changed(idx, val))
            spin.valueChanged.connect(lambda val, idx=i: self.on_dbl_spin_changed(idx, val))

            grid_dbl.addWidget(lbl_str, i, 0)
            grid_dbl.addWidget(lbl_interval, i, 1)
            grid_dbl.addWidget(slider, i, 2)
            grid_dbl.addWidget(spin, i, 3)

            self.dbl_sliders.append(slider)
            self.dbl_spinboxes.append(spin)
            self.dbl_labels.append(lbl_interval)

        v_dbl.addLayout(grid_dbl)
        h_custom_engines.addWidget(self.grp_custom_doubling)

        layout.addLayout(h_custom_engines)

        self.btn_send_custom = QPushButton("Send Custom Parameters")
        self.btn_send_custom.setStyleSheet("""
            QPushButton {
                background-color: #2980b9;
                color: white;
                font-weight: bold;
                padding: 7px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #3498db; }
        """)
        # AQUI: em vez de self.save_current_patch, liga à função de audição/teste:
        self.btn_send_custom.clicked.connect(self.audition_custom_parameters)
        layout.addWidget(self.btn_send_custom)

    # --------------------------------------------------------------------------
    # TAB 2: GLOBAL PARAMETERS
    # --------------------------------------------------------------------------
    def build_global_tab(self) -> None:
        layout = QVBoxLayout(self.tab_global)
        layout.setSpacing(12)

        # Master Global Controls
        grp_master = QGroupBox("Master Output & Tuning")
        grid_master = QGridLayout(grp_master)
        grid_master.setVerticalSpacing(8)
        grid_master.setHorizontalSpacing(12)

        grid_master.addWidget(QLabel("Global Transpose:"), 0, 0)
        self.combo_dtrnsp = QComboBox()
        self.combo_dtrnsp.addItems(DTRNSP)
        self.combo_dtrnsp.currentIndexChanged.connect(lambda i: self.transport.send_cc(28, i))
        grid_master.addWidget(self.combo_dtrnsp, 0, 1)

        grid_master.addWidget(QLabel("Master Volume (dB):"), 1, 0)
        self.slider_boost = QSlider(Qt.Orientation.Horizontal)
        self.slider_boost.setRange(0, 127)
        self.slider_boost.setValue(64)
        self.lbl_boost = QLabel("0 dB")
        self.lbl_boost.setFixedWidth(45)
        self.slider_boost.valueChanged.connect(self.on_boost_changed)
        grid_master.addWidget(self.slider_boost, 1, 1)
        grid_master.addWidget(self.lbl_boost, 1, 2)

        grid_master.addWidget(QLabel("Tuning Ref (440Hz):"), 2, 0)
        self.slider_hz = QSlider(Qt.Orientation.Horizontal)
        self.slider_hz.setRange(0, 19)
        self.slider_hz.setValue(7)
        self.lbl_hz = QLabel("440 Hz")
        self.lbl_hz.setFixedWidth(45)
        self.slider_hz.valueChanged.connect(self.on_hz_changed)
        grid_master.addWidget(self.slider_hz, 2, 1)
        grid_master.addWidget(self.lbl_hz, 2, 2)

        grid_master.addWidget(QLabel("Detune:"), 3, 0)
        self.slider_detune = QSlider(Qt.Orientation.Horizontal)
        self.slider_detune.setRange(0, 127)
        self.slider_detune.setValue(63)
        self.lbl_detune = QLabel("0 c")
        self.lbl_detune.setFixedWidth(45)
        self.slider_detune.valueChanged.connect(self.on_detune_changed)
        grid_master.addWidget(self.slider_detune, 3, 1)
        grid_master.addWidget(self.lbl_detune, 3, 2)

        layout.addWidget(grp_master)

        # String Gain Calibration (Piezo)
        grp_piezo = QGroupBox("String Gain Calibration (Piezo)")
        grid_piezo = QGridLayout(grp_piezo)
        grid_piezo.setVerticalSpacing(6)
        grid_piezo.setHorizontalSpacing(12)

        self.piezo_sliders = []
        self.piezo_labels = []
        string_labels = [
            "String 6 (E1):", "String 5 (A1):", "String 4 (D2):",
            "String 3 (G2):", "String 2 (B2):", "String 1 (E3):"
        ]

        for i in range(6):
            lbl_str = QLabel(string_labels[i])
            lbl_str.setFixedWidth(95)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 12)
            slider.setValue(6)

            lbl_db = QLabel("0 dB")
            lbl_db.setFixedWidth(45)

            slider.valueChanged.connect(lambda _, idx=i: self.on_piezo_changed(idx))

            grid_piezo.addWidget(lbl_str, i, 0)
            grid_piezo.addWidget(slider, i, 1)
            grid_piezo.addWidget(lbl_db, i, 2)

            self.piezo_sliders.append(slider)
            self.piezo_labels.append(lbl_db)

        layout.addWidget(grp_piezo)
        layout.addStretch()

    # --------------------------------------------------------------------------
    # RIGHT PANEL: GROUPS
    # --------------------------------------------------------------------------
    def build_groups_panel(self, parent_layout: QHBoxLayout) -> None:
        panel = QVBoxLayout()
        panel.addWidget(QLabel("<b>Performance Groups:</b>"))

        self.group_list = QListWidget()
        self.group_list.setFixedWidth(230)
        self.group_list.setFixedHeight(220)
        self.group_list.setEditTriggers(
            QListWidget.EditTrigger.DoubleClicked | QListWidget.EditTrigger.SelectedClicked
        )
        self.group_list.itemChanged.connect(self.on_group_item_renamed)
        self.group_list.currentRowChanged.connect(self.on_group_selected)

        for i in range(10):
            g_name = self.librarian.groups[i].get("name", f"GROUP {i+1}")
            item = QListWidgetItem(f"G{i+1:02d}: {g_name}")
            item.setFlags(
                item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )
            self.group_list.addItem(item)
        panel.addWidget(self.group_list)

        grp_slots = QGroupBox("Group Directional Shortcuts")
        grp_slots.setFixedWidth(230)
        v_slots = QVBoxLayout(grp_slots)
        self.slot_buttons = []
        labels = ["[UP]", "[DN]", "[RG]", "[LF]"]
        for idx in range(4):
            h = QHBoxLayout()
            btn_assign = QPushButton(f"Set {labels[idx]}")
            btn_load = QPushButton("EMPTY")
            btn_assign.setFixedWidth(65)
            btn_assign.clicked.connect(lambda _, i=idx: self.assign_current_patch_to_slot(i))
            btn_load.clicked.connect(lambda _, i=idx: self.load_patch_from_slot(i))
            h.addWidget(btn_assign)
            h.addWidget(btn_load)
            v_slots.addLayout(h)
            self.slot_buttons.append(btn_load)
        panel.addWidget(grp_slots)

        panel.addStretch()

        # Backup and Hardware Panel
        grp_backups = QGroupBox("Backups & Hardware")
        grp_backups.setFixedWidth(230)
        v_backups = QVBoxLayout(grp_backups)

        self.btn_backup_lib = QPushButton("Backup Library")
        self.btn_restore_lib = QPushButton("Restore to Library")
        self.btn_backup_gtr = QPushButton("Backup Guitar")
        self.btn_flash_backup = QPushButton("Flash Backup to Guitar")  # NOVO BOTÃO

        self.btn_backup_lib.clicked.connect(self.on_backup_library)
        self.btn_restore_lib.clicked.connect(self.on_restore_backup)
        self.btn_backup_gtr.clicked.connect(self.on_backup_guitar)
        self.btn_flash_backup.clicked.connect(self.on_flash_backup_to_guitar)

        v_backups.addWidget(self.btn_backup_lib)
        v_backups.addWidget(self.btn_restore_lib)
        v_backups.addWidget(self.btn_backup_gtr)
        v_backups.addWidget(self.btn_flash_backup)

        self.btn_upload = QPushButton("Upload to Hardware")
        self.btn_upload.setFixedHeight(34)
        self.btn_upload.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #2ecc71; }
        """)
        self.btn_upload.clicked.connect(self.upload_all_to_hardware)
        v_backups.addWidget(self.btn_upload)

        panel.addWidget(grp_backups)
        panel.addStretch()

        parent_layout.addLayout(panel)
        self.group_list.setCurrentRow(0)

    # --------------------------------------------------------------------------
    # HARDWARE DETECTION & LIVE STATUS
    # --------------------------------------------------------------------------
    def detect_hardware(self) -> None:
        _, msg, color = self.transport.detect_hardware()
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold; padding: 2px;")

    # --------------------------------------------------------------------------
    # TUNING & DOUBLING CONTROLS
    # --------------------------------------------------------------------------
    def on_toggle_fine_tune(self, checked: bool) -> None:
        for i in range(6):
            self.tune_spinboxes[i].setEnabled(checked)
            self.tune_sliders[i].setEnabled(not checked)

    def on_tune_slider_changed(self, idx: int, val_semitons: int) -> None:
        cents = val_semitons * 100
        self.tune_spinboxes[idx].blockSignals(True)
        self.tune_spinboxes[idx].setValue(cents)
        self.tune_spinboxes[idx].blockSignals(False)
        self.update_tune_note_label(idx, cents)

    def on_tune_spin_changed(self, idx: int, val_cents: int) -> None:
        semitons = int(round(val_cents / 100.0))
        self.tune_sliders[idx].blockSignals(True)
        self.tune_sliders[idx].setValue(max(-12, min(12, semitons)))
        self.tune_sliders[idx].blockSignals(False)
        self.update_tune_note_label(idx, val_cents)

    def update_tune_note_label(self, idx: int, cents: int) -> None:
        semitones_offset = cents / 100.0
        resulting_midi_note = int(round(BASE_NOTES_TAB[idx] + semitones_offset))
        self.tune_note_labels[idx].setText(midi_num_to_name(resulting_midi_note))

    def on_toggle_fine_dbl(self, checked: bool) -> None:
        for i in range(6):
            self.dbl_spinboxes[i].setEnabled(checked)
            self.dbl_sliders[i].setEnabled(not checked)

    def on_dbl_slider_changed(self, idx: int, val_semitons: int) -> None:
        cents = val_semitons * 100
        self.dbl_spinboxes[idx].blockSignals(True)
        self.dbl_spinboxes[idx].setValue(cents)
        self.dbl_spinboxes[idx].blockSignals(False)
        self.update_dbl_label(idx, cents)

    def on_dbl_spin_changed(self, idx: int, val_cents: int) -> None:
        semitons = int(round(val_cents / 100.0))
        self.dbl_sliders[idx].blockSignals(True)
        self.dbl_sliders[idx].setValue(max(-12, min(12, semitons)))
        self.dbl_sliders[idx].blockSignals(False)
        self.update_dbl_label(idx, val_cents)

    def update_dbl_label(self, idx: int, cents: int) -> None:
        if cents == 0:
            self.dbl_labels[idx].setText("Off")
        elif cents == 1200:
            self.dbl_labels[idx].setText("+8va")
        elif cents == -1200:
            self.dbl_labels[idx].setText("-8va")
        elif cents == 700:
            self.dbl_labels[idx].setText("+5th")
        else:
            st = cents / 100.0
            self.dbl_labels[idx].setText(f"{st:+.1f}st")

    def reset_custom_tuning(self) -> None:
        for i in range(6):
            self.tune_spinboxes[i].setValue(0)
            self.tune_sliders[i].setValue(0)
            self.update_tune_note_label(i, 0)

    def reset_custom_doubling(self) -> None:
        for i in range(6):
            self.dbl_spinboxes[i].setValue(0)
            self.dbl_sliders[i].setValue(0)
            self.update_dbl_label(i, 0)

    # --------------------------------------------------------------------------
    # PICKUP SELECTOR
    # --------------------------------------------------------------------------
    def select_guitar_model(self, model_idx: int) -> None:
        for i, btn in enumerate(self.model_buttons):
            btn.setChecked(i == model_idx)

        m_info = GUITAR_MODELS_13[model_idx]
        m_type = m_info["type"]

        if not self.is_loading_ui:
            self.transport.send_cc(14, m_info["cc14"])
            if m_type == "AC" and m_info["cc22"] is not None:
                self.transport.send_cc(22, m_info["cc22"])

        self.render_pickup_panel(model_idx)

    def render_pickup_panel(self, model_idx: int) -> None:
        while self.layout_pickups.count():
            item = self.layout_pickups.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.pickup_buttons.clear()

        m_info = GUITAR_MODELS_13[model_idx]
        m_type = m_info["type"]

        if m_type == "AC":
            lbl = QLabel("")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout_pickups.addWidget(lbl)
            return

        if m_type == "3P":
            pickup_options = [
                ("3P5", 0, "Neck"),
                ("3P4", 1, "Neck + Middle"),
                ("3P3", 2, "Middle"),
                ("3P2", 3, "Middle + Bridge"),
                ("3P1", 4, "Bridge")
            ]
        else:
            pickup_options = [
                ("2P3", 0, "Neck"),
                ("2P2", 2, "Both (N + B)"),
                ("2P1", 4, "Bridge")
            ]

        for icon_file, cc_val, tip in pickup_options:
            btn = QPushButton()
            icon_path = get_icon_path(icon_file)
            if os.path.exists(icon_path):
                btn.setIcon(QIcon(icon_path))
                btn.setIconSize(QSize(64, 64))

            btn.setFixedSize(76, 76)
            btn.setCheckable(True)
            btn.setToolTip(f"<b>{tip}</b>")
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.05);
                    border: 2px solid transparent;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.12);
                }
                QPushButton:checked {
                    background-color: rgba(46, 204, 113, 0.25);
                    border: 2px solid #2ecc71;
                }
            """)
            btn.clicked.connect(lambda _, val=cc_val, b=btn: self.on_pickup_clicked(val, b))
            self.layout_pickups.addWidget(btn)
            self.pickup_buttons.append((btn, cc_val))

        cur_pickup = self.librarian.patches[self.current_slot].get("pickup", 0)
        self.set_pickup_button_state(cur_pickup)

    def on_pickup_clicked(self, cc_val: int, clicked_btn: QPushButton) -> None:
        for btn, _ in self.pickup_buttons:
            btn.setChecked(btn == clicked_btn)
        if not self.is_loading_ui:
            self.transport.send_cc(22, cc_val)

    def set_pickup_button_state(self, cc_val: int) -> None:
        matched = False
        for btn, val in self.pickup_buttons:
            if val == cc_val:
                btn.setChecked(True)
                matched = True
            else:
                btn.setChecked(False)
        if not matched and self.pickup_buttons:
            self.pickup_buttons[0][0].setChecked(True)

    # --------------------------------------------------------------------------
    # AUDITION & PERFORMANCE CONTROLS
    # --------------------------------------------------------------------------
    def on_capo_changed(self, val: int) -> None:
        self.lbl_capo.setText(f"{val:+d}" if val != 0 else "0")
        if not self.is_loading_ui:
            self.transport.send_cc(11, 52 + 12 + val)

    def on_tuning_changed(self, idx: int) -> None:
        is_custom = (idx == 1)
        for s in self.tune_sliders:
            s.setEnabled(is_custom and not self.chk_fine_tune.isChecked())
        for sp in self.tune_spinboxes:
            sp.setEnabled(is_custom and self.chk_fine_tune.isChecked())
        self.chk_fine_tune.setEnabled(is_custom)
        if not self.is_loading_ui:
            self.transport.send_cc(7, idx)

    def on_double_changed(self, idx: int) -> None:
        is_custom = (idx == 9)
        for s in self.dbl_sliders:
            s.setEnabled(is_custom and not self.chk_fine_dbl.isChecked())
        for sp in self.dbl_spinboxes:
            sp.setEnabled(is_custom and self.chk_fine_dbl.isChecked())
        self.chk_fine_dbl.setEnabled(is_custom)
        if not self.is_loading_ui:
            self.transport.send_cc(27, idx)

    def on_gate_changed(self, val: int) -> None:
        if val == 0:
            self.lbl_gate.setText("Off")
        else:
            db_val = -96 + (val * 3)
            self.lbl_gate.setText(f"{db_val} dB")
        if not self.is_loading_ui:
            self.transport.send_cc(25, val)

    def update_stune_style(self, is_on: bool) -> None:
        self.btn_stune.setChecked(is_on)
        self.btn_stune.setText("Solid-Tune: ON" if is_on else "Solid-Tune: OFF")
        if is_on:
            self.btn_stune.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    font-weight: bold;
                    border: 1px solid #2ecc71;
                    border-radius: 4px;
                    padding: 5px;
                }
            """)
        else:
            self.btn_stune.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.08);
                    color: #bdc3c7;
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    border-radius: 4px;
                    padding: 5px;
                }
            """)

    def on_stune_toggle(self) -> None:
        is_on = self.btn_stune.isChecked()
        self.update_stune_style(is_on)
        if not self.is_loading_ui:
            self.transport.send_cc(3, 64 if is_on else 0)

    def on_boost_changed(self, val: int) -> None:
        db = int(((val - 64) / 64.0) * 12)
        self.lbl_boost.setText(f"{db:+d} dB" if db != 0 else "0 dB")
        if not self.is_loading_ui:
            self.transport.send_cc(18, val)

    def on_hz_changed(self, val: int) -> None:
        hz = 440 + (val - 7)
        self.lbl_hz.setText(f"{hz} Hz")
        if not self.is_loading_ui:
            self.transport.send_cc(8, 57 + val)

    def on_detune_changed(self, val: int) -> None:
        cents = val - 63
        self.lbl_detune.setText(f"{cents:+d} c" if cents != 0 else "0 c")
        if not self.is_loading_ui:
            self.transport.send_cc(19, val)

    def on_piezo_changed(self, idx: int) -> None:
        val = self.piezo_sliders[idx].value()
        db = val - 6
        self.piezo_labels[idx].setText(f"{db:+d} dB" if db != 0 else "0 dB")
        if not self.is_loading_ui:
            self.transport.send_cc(34 - idx, 58 + val)

    # --------------------------------------------------------------------------
    # SERIALIZATION & PRESET ACTIONS
    # --------------------------------------------------------------------------
    def collect_ui_to_dict(self) -> Dict[str, Any]:
        model_btn_idx = 0
        for i, btn in enumerate(self.model_buttons):
            if btn.isChecked():
                model_btn_idx = i
                break

        m_info = GUITAR_MODELS_13[model_btn_idx]
        real_model_id = m_info["cc14"]

        if m_info["type"] == "AC":
            pickup_val = m_info["cc22"]
        else:
            pickup_val = 0
            for btn, val in self.pickup_buttons:
                if btn.isChecked():
                    pickup_val = val
                    break

        cur_name = self.librarian.patches[self.current_slot].get("name", "STD")

        return {
            "name": cur_name,
            "model": real_model_id,
            "pickup": pickup_val,
            "capo": self.slider_capo.value(),
            "pitch_shift": self.combo_pitch_shift.currentIndex(),
            "tuning": self.combo_tuning.currentIndex(),
            "double": self.combo_double.currentIndex(),
            "gate": self.slider_gate.value(),
            "solid_tune": self.btn_stune.isChecked(),
            "custom_tuning": [s.value() for s in self.tune_spinboxes],
            "custom_doubling": [s.value() for s in self.dbl_spinboxes],
            "notes": self.txt_notes.toPlainText()
        }

    def save_current_patch(self) -> None:
        """Modifies current slot with active UI sound settings."""
        cur_patch = self.collect_ui_to_dict()
        cur_name = cur_patch["name"]

        # Persist to local library
        self.librarian.update_patch(self.current_slot, cur_patch, sync_shadow=True)
        self.librarian.save_all()

        # Check hardware flash
        if self.transport.conn_type != CONN_STANDALONE:
            if not self.librarian.is_patch_identical(cur_patch, self.librarian.guitar_patches[self.current_slot]):
                try:
                    sysex_payload = build_sysex_preset_packet(self.current_slot, cur_patch)
                    self.transport.flash_preset_to_guitar(sysex_payload)
                    self.transport.send_pc(self.current_slot)
                    self.librarian.update_guitar_patch(self.current_slot, cur_patch)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Communication failed: {e}")
                    return

            # NOVO: Se for StrapBox Arduino, atualiza logo o nome no ecrã do pedal!
            if self.transport.conn_type == CONN_ARDUINO:
                self.transport.update_strapbox_single_name(self.current_slot, cur_name)
        else:
            self.librarian.update_guitar_patch(self.current_slot, cur_patch)

        self.populate_patch_list()
        self.patch_list.blockSignals(True)
        self.patch_list.setCurrentRow(self.current_slot)
        self.patch_list.blockSignals(False)
        self.update_default_patch_combo()
        self.update_group_slot_labels()
        self.update_working_name_display(self.current_slot, cur_name)

        # QMessageBox.information(self, "Modified", f"Slot {self.current_slot:02d} ({cur_name}) updated!")

    def save_patch_as(self) -> None:
        """Opens modal dialog to save active sound settings under a new name and slot."""
        cur_patch = self.collect_ui_to_dict()
        cur_name = cur_patch.get("name", "EMPTY")

        dialog = SavePatchDialog(self, cur_name, self.current_slot, self.librarian.patches)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name, target_slot = dialog.get_values()
            cur_patch["name"] = new_name

            # Persist to library and disk
            self.librarian.update_patch(target_slot, cur_patch, sync_shadow=True)
            self.librarian.save_all()

            # Flash to hardware if connected
            if self.transport.conn_type != CONN_STANDALONE:
                try:
                    sysex_payload = build_sysex_preset_packet(target_slot, cur_patch)
                    self.transport.flash_preset_to_guitar(sysex_payload)
                    self.transport.send_pc(target_slot)
                    self.librarian.update_guitar_patch(target_slot, cur_patch)

                    # NOVO: Atualiza o nome do target_slot no StrapBox Arduino!
                    if self.transport.conn_type == CONN_ARDUINO:
                        self.transport.update_strapbox_single_name(target_slot, new_name)

                except Exception as err:
                    QMessageBox.critical(self, "Error", f"Hardware flash failed: {err}")
                    return
            else:
                self.librarian.update_guitar_patch(target_slot, cur_patch)

            # Refresh list with updated names and sync colors (Green/Blue)
            self.populate_patch_list()

            # Switch view to destination slot without re-triggering duplicate PC
            self.patch_list.blockSignals(True)
            self.patch_list.setCurrentRow(target_slot)
            self.patch_list.blockSignals(False)

            self.current_slot = target_slot
            self.update_default_patch_combo()
            self.update_group_slot_labels()
            self.update_working_name_display(target_slot, new_name)

            QMessageBox.information(
                self, "Saved", f"Preset successfully saved to Slot {target_slot:02d} ({new_name})!"
            )
    
    def clear_current_slot(self) -> None:
        reply = QMessageBox.question(
            self, "Clear Slot", f"Clear Slot {self.current_slot:02d} to EMPTY?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.librarian.clear_patch(self.current_slot)
            self.populate_patch_list()
            self.patch_list.setCurrentRow(self.current_slot)
            self.update_default_patch_combo()
            self.update_group_slot_labels()

    def on_notes_changed(self) -> None:
        if not self.is_loading_ui:
            self.librarian.patches[self.current_slot]["notes"] = self.txt_notes.toPlainText()

    # --------------------------------------------------------------------------
    # LIST & GROUP MANAGEMENT
    # --------------------------------------------------------------------------
    def populate_patch_list(self) -> None:
        """Populates the 64 slots list with visual state flags (Green = Synced, Blue = Mismatch)."""
        self.patch_list.blockSignals(True)
        self.patch_list.clear()
        for i in range(64):
            name = self.librarian.patches[i].get("name", "EMPTY")
            is_synced = self.librarian.is_slot_synced_with_guitar(i)

            symbol = "●"
            color = QColor("#2ecc71") if is_synced else QColor("#3498db")
            state_tip = "Synced with Guitar" if is_synced else "Mismatch with Guitar"

            item = QListWidgetItem(f"{symbol}  {i:02d}: {name}")
            item.setForeground(color)
            item.setToolTip(f"Slot {i:02d}: {name} ({state_tip})")
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsEditable
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.patch_list.addItem(item)
        self.patch_list.blockSignals(False)

    def on_patch_item_renamed(self, item: QListWidgetItem) -> None:
        old_name = item.data(Qt.ItemDataRole.UserRole)
        full_text = item.text().replace("●", "").strip()

        if " - " in full_text:
            new_name = full_text.split(" - ", 1)[1].strip()
        elif ":" in full_text:
            new_name = full_text.split(":", 1)[1].strip()
        else:
            new_name = full_text

        new_name = new_name[:18] if new_name else "EMPTY"
        row = self.patch_list.row(item)
        if not (0 <= row < 64):
            return

        self.librarian.patches[row]["name"] = new_name
        self.librarian.propagate_rename(old_name, new_name)
        self.librarian.save_all()

        self.populate_patch_list()
        self.patch_list.setCurrentRow(row)

        self.update_default_patch_combo()
        self.update_group_slot_labels()
        if row == self.current_slot:
            self.update_working_name_display(row, new_name)

    def on_patch_rows_moved(self, *args: Any) -> None:
        new_data = []
        for i in range(self.patch_list.count()):
            it = self.patch_list.item(i)
            if it is None:
                continue
            name = it.data(Qt.ItemDataRole.UserRole)
            matched = next((p for p in self.librarian.patches if p["name"] == name), None)
            if matched:
                new_data.append(matched)
            else:
                new_data.append({
                    "name": name, "model": 0, "pickup": 0, "capo": 0, "pitch_shift": 0,
                    "tuning": 0, "double": 0, "gate": 0, "solid_tune": True,
                    "custom_tuning": [0] * 6, "custom_doubling": [0] * 6, "notes": ""
                })

        self.librarian.patches = new_data
        self.librarian.save_all()
        self.populate_patch_list()
        self.update_group_slot_labels()

    def on_patch_selected(self, row: int) -> None:
        """Handles slot selection with conflict resolution for divergent (Blue) patches."""
        if not (0 <= row < 64):
            return

        self.current_slot = row

        # Check if divergent from guitar shadow memory
        if not self.librarian.is_slot_synced_with_guitar(row):
            lib_name = self.librarian.patches[row].get("name", "EMPTY")
            gtr_name = self.librarian.guitar_patches[row].get("name", "EMPTY")
            
            box = QMessageBox(self)
            box.setWindowTitle("Preset Conflict")
            box.setIcon(QMessageBox.Icon.Question)
            box.setText(f"Preset conflict detected for Slot {row:02d}!\n\n• Library: {lib_name}\n• Guitar: {gtr_name}")
            box.setInformativeText("Which version do you want to load into the editor?")
            
            btn_lib = box.addButton("Load Library", QMessageBox.ButtonRole.AcceptRole)
            btn_gtr = box.addButton("Load Guitar", QMessageBox.ButtonRole.RejectRole)
            box.exec()

            if box.clickedButton() == btn_gtr:
                # Load guitar version
                self.load_slot_to_ui(row, use_guitar_source=True)
                self.transport.send_pc(row)
                return

        # Default: load local library patch
        self.load_slot_to_ui(row, use_guitar_source=False)
        self.transport.send_pc(row)

    def get_button_index_from_model(self, model_id: int, pickup_val: int) -> int:
        if model_id == 8:
            if pickup_val == 0:
                return 10
            if pickup_val == 2:
                return 11
            return 12
        if model_id == 9:
            return 9
        if model_id == 10:
            return 8
        return model_id

    def update_working_name_display(self, slot_idx: int, name: str) -> None:
        """Updates the working preset label header."""
        display_name = name.strip() if name.strip() else "EMPTY"
        self.lbl_working_name.setText(f"[{slot_idx:02d}] {display_name}")    
    
    def load_slot_to_ui(self, slot: int, use_guitar_source: bool = False) -> None:
        self.is_loading_ui = True
        if use_guitar_source:
            p = self.librarian.guitar_patches[slot]
        else:
            p = self.librarian.get_patch(slot)

        btn_idx = self.get_button_index_from_model(p.get("model", 0), p.get("pickup", 0))
        self.select_guitar_model(btn_idx)
        self.slider_capo.setValue(p.get("capo", 0))

        t_idx = p.get("tuning", 0)
        self.combo_tuning.setCurrentIndex(t_idx)
        self.on_tuning_changed(t_idx)

        d_idx = p.get("double", 0)
        self.combo_double.setCurrentIndex(d_idx)
        self.on_double_changed(d_idx)

        self.slider_gate.setValue(p.get("gate", 0))

        ps_idx = p.get("pitch_shift", 0)
        self.combo_pitch_shift.setCurrentIndex(ps_idx if 0 <= ps_idx < 4 else 0)

        st = p.get("solid_tune", True)
        self.update_stune_style(st)

        t_cents = p.get("custom_tuning", [0] * 6)
        for i in range(6):
            self.tune_spinboxes[i].setValue(t_cents[i])
            self.update_tune_note_label(i, t_cents[i])

        d_cents = p.get("custom_doubling", [0] * 6)
        for i in range(6):
            self.dbl_spinboxes[i].setValue(d_cents[i])
            self.update_dbl_label(i, d_cents[i])

        self.txt_notes.setPlainText(p.get("notes", ""))
        self.set_pickup_button_state(p.get("pickup", 0))
        self.is_loading_ui = False
        self.update_working_name_display(slot, p.get("name", "EMPTY"))

    def update_default_patch_combo(self) -> None:
        self.combo_default_patch.blockSignals(True)
        self.combo_default_patch.clear()
        for i in range(64):
            name = self.librarian.patches[i].get("name", "EMPTY")
            self.combo_default_patch.addItem(f"{i:02d}: {name}")

        def_val = self.librarian.groups[0].get("default_patch", "EMPTY")
        if isinstance(def_val, int):
            idx = def_val if 0 <= def_val < 64 else 0
        else:
            idx = next((i for i, p in enumerate(self.librarian.patches) if p["name"] == def_val), 0)

        self.combo_default_patch.setCurrentIndex(idx)
        self.combo_default_patch.blockSignals(False)

    def on_group_selected(self, row: int) -> None:
        if not (0 <= row < 10):
            return
        self.update_group_slot_labels()

    def update_group_slot_labels(self) -> None:
        g_idx = self.group_list.currentRow()
        if g_idx < 0:
            return
        slots = self.librarian.groups[g_idx].get("slots", ["EMPTY"] * 4)
        for i in range(4):
            slot_val = slots[i]
            if isinstance(slot_val, int):
                p_name = self.librarian.patches[slot_val].get("name", "EMPTY") if 0 <= slot_val < 64 else "EMPTY"
                self.slot_buttons[i].setText(str(p_name))
            else:
                self.slot_buttons[i].setText(str(slot_val))

    def assign_current_patch_to_slot(self, slot_idx: int) -> None:
        g_idx = self.group_list.currentRow()
        if g_idx < 0:
            return
        cur_name = self.librarian.patches[self.current_slot].get("name", "EMPTY")
        self.librarian.groups[g_idx]["slots"][slot_idx] = cur_name
        self.librarian.save_groups()
        self.update_group_slot_labels()

    def load_patch_from_slot(self, slot_idx: int) -> None:
        g_idx = self.group_list.currentRow()
        if g_idx < 0:
            return
        slot_val = self.librarian.groups[g_idx]["slots"][slot_idx]
        if isinstance(slot_val, int):
            idx = slot_val if 0 <= slot_val < 64 else None
        else:
            idx = next((i for i, p in enumerate(self.librarian.patches) if p["name"] == slot_val), None)

        if idx is not None:
            self.patch_list.setCurrentRow(idx)

    def on_default_patch_selected(self, idx: int) -> None:
        if idx >= 0:
            p_name = self.librarian.patches[idx].get("name", "EMPTY")
            for g in self.librarian.groups:
                g["default_patch"] = p_name
            self.librarian.save_groups()

    def on_group_item_renamed(self, item: QListWidgetItem) -> None:
        full_text = item.text().strip()
        new_name = full_text.split(":", 1)[1].strip() if ":" in full_text else full_text
        new_name = new_name[:10] if new_name else "GROUP"

        row = self.group_list.row(item)
        if not (0 <= row < 10):
            return

        self.group_list.blockSignals(True)
        item.setText(f"G{row+1:02d}: {new_name}")
        self.group_list.blockSignals(False)

        self.librarian.groups[row]["name"] = new_name
        self.librarian.save_groups()

    def audition_custom_parameters(self) -> None:
        """
        Envia os parâmetros atuais para a guitarra para teste auditivo imediato,
        atualizando apenas a shadow memory da guitarra (sem alterar o patches.json no PC).
        """
        if self.transport.conn_type == CONN_STANDALONE:
            QMessageBox.warning(
                self, "Standalone Mode",
                "Cannot audition on hardware in Standalone mode.\nConnect MIDI interface."
            )
            return

        # 1. Recolhe os parâmetros que estão nos sliders e controlos do ecrã
        cur_patch = self.collect_ui_to_dict()
        cur_name = cur_patch.get("name", "EMPTY")

        # 2. Constrói o SysEx e grava no slot da guitarra física
        try:
            sysex_payload = build_sysex_preset_packet(self.current_slot, cur_patch)
            self.transport.flash_preset_to_guitar(sysex_payload)
            self.transport.send_pc(self.current_slot)
        except Exception as e:
            QMessageBox.critical(self, "Audition Error", f"Failed to send to guitar: {e}")
            return

        # 3. Atualiza APENAS a memória shadow da guitarra (RAM)
        # O self.librarian.patches[self.current_slot] no PC permanece intocado!
        self.librarian.update_guitar_patch(self.current_slot, cur_patch)

        # 4. Atualiza a lista visual: este slot fica AZUL (mismatch entre PC e Guitarra)
        self.populate_patch_list()
        self.patch_list.blockSignals(True)
        self.patch_list.setCurrentRow(self.current_slot)
        self.patch_list.blockSignals(False)

        # 5. Feedback discreto no ecrã (sem popups intrusivos para poderes continuar a tocar)
        self.lbl_status.setText(f"Auditioning on Slot {self.current_slot:02d} (Unsaved to PC)")
        self.lbl_status.setStyleSheet("color: #3498db; font-weight: bold; padding: 2px;")

    # --------------------------------------------------------------------------
    # BACKUP & RESTORE ACTIONS
    # --------------------------------------------------------------------------
    def on_backup_library(self) -> None:
        """Creates a timestamped backup of local library and groups."""
        filepath = self.librarian.backup_library()
        if filepath:
            filename = os.path.basename(filepath)
            QMessageBox.information(
                self, "Backup Library",
                f"Library successfully exported to:\nbackups/{filename}"
            )
        else:
            QMessageBox.critical(self, "Backup Error", "Failed to export library backup.")

    def on_restore_backup(self) -> None:
        """Prompts user to select a JSON backup file and restores library."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Restore Library Backup",
            BACKUPS_DIR,
            "JSON Backup Files (*.json)"
        )
        if not filepath:
            return

        reply = QMessageBox.question(
            self, "Confirm Restore",
            "Restoring will overwrite current library and groups on disk.\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if self.librarian.restore_backup(filepath):
            self.populate_patch_list()
            self.load_slot_to_ui(self.current_slot)
            self.update_default_patch_combo()
            self.update_group_slot_labels()
            QMessageBox.information(self, "Restore Success", "Library successfully restored!")
        else:
            QMessageBox.critical(self, "Restore Error", "Failed to restore from selected file.")

    def on_backup_guitar(self) -> None:
        """Faz o dump completo dos 64 presets da guitarra física e guarda em JSON."""
        if self.transport.conn_type != CONN_MIDI_IFACE:
            QMessageBox.warning(
                self, "Backup Guitar",
                "Guitar backup is only available with native MIDI Interface connection.\n(Arduino connection is transmit-only)."
            )
            return

        reply = QMessageBox.question(
            self, "Backup Guitar",
            "Read all 64 presets directly from the physical guitar and save a backup file?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        progress = QProgressDialog("Dumping presets from guitar...", "Cancel", 0, 64, self)
        progress.setWindowTitle("Guitar Backup")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        def on_step(current: int, total: int):
            progress.setValue(current)
            progress.setLabelText(f"Reading preset {current:02d} of {total:02d} from AT-200...")
            from PyQt6.QtCore import QCoreApplication
            QCoreApplication.processEvents()

        try:
            recalled = self.transport.recall_all_presets_from_guitar(progress_callback=on_step)
            progress.close()

            if len(recalled) == 64:
                # Atualiza a memória shadow da guitarra
                for i in range(64):
                    self.librarian.update_guitar_patch(i, recalled[i])

                # Guarda ficheiro timestamped na pasta backups
                import json
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                filename = f"Guitar_Dump_{timestamp}.json"
                filepath = os.path.join(BACKUPS_DIR, filename)

                bundle = {
                    "version": 3,
                    "timestamp": timestamp,
                    "type": "guitar_dump",
                    "patches": recalled
                }
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(bundle, f, indent=2)

                self.populate_patch_list()
                QMessageBox.information(
                    self, "Backup Complete",
                    f"Guitar presets successfully dumped and saved to:\nbackups/{filename}"
                )
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Backup Error", f"Failed to dump guitar: {e}")

    def on_flash_backup_to_guitar(self) -> None:
        """Carrega diretamente um ficheiro de backup JSON para a guitarra física."""
        if self.transport.conn_type != CONN_MIDI_IFACE:
            QMessageBox.warning(
                self, "Connection Error",
                "Flashing directly to guitar requires native MIDI connection."
            )
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select Backup to Flash to Guitar",
            BACKUPS_DIR,
            "JSON Backup Files (*.json)"
        )
        if not filepath:
            return

        try:
            import json
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            patches_to_send = data.get("patches", [])
            if not isinstance(patches_to_send, list) or len(patches_to_send) != 64:
                QMessageBox.critical(self, "Invalid File", "The selected file does not contain 64 presets.")
                return

            reply = QMessageBox.question(
                self, "Confirm Flash",
                f"Flash all 64 presets from:\n{os.path.basename(filepath)}\n\nDirectly into guitar hardware?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            # Barra de progresso para a gravação
            progress = QProgressDialog("Flashing presets to guitar...", "Cancel", 0, 64, self)
            progress.setWindowTitle("Hardware Flash")
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)

            def on_step(current: int, total: int):
                progress.setValue(current)
                progress.setLabelText(f"Flashing preset {current:02d} of {total:02d} to flash...")
                from PyQt6.QtCore import QCoreApplication
                QCoreApplication.processEvents()

            success = self.transport.upload_all_presets_to_guitar(patches_to_send, progress_callback=on_step)
            progress.close()

            if success:
                # Atualiza a memória shadow da guitarra
                for i in range(64):
                    self.librarian.update_guitar_patch(i, patches_to_send[i])

                self.transport.send_pc(0)
                self.populate_patch_list()
                QMessageBox.information(
                    self, "Flash Complete",
                    f"Successfully flashed 64 presets from backup to guitar!"
                )
            else:
                QMessageBox.critical(self, "Flash Failed", "Failed to communicate with guitar flash memory.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to flash backup: {e}")

    def upload_all_to_hardware(self) -> None:
        """Grava toda a biblioteca local (64 slots) na guitarra e sincroniza o StrapBox."""
        if self.transport.conn_type == CONN_STANDALONE:
            QMessageBox.critical(self, "Connection Error", "No hardware connected!\nConnect StrapBox or MIDI interface.")
            return

        reply = QMessageBox.question(
            self, "Upload to Hardware",
            "Save all 64 presets from local library to guitar flash memory?\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            index_map = self.librarian.build_index_map()

            # 1. Modo MIDI Interface (Grava os 64 presets na guitarra física)
            if self.transport.conn_type == CONN_MIDI_IFACE:
                progress = QProgressDialog("Writing all presets to guitar...", "Cancel", 0, 64, self)
                progress.setWindowTitle("Hardware Upload")
                progress.setWindowModality(Qt.WindowModality.WindowModal)
                progress.setMinimumDuration(0)
                progress.setValue(0)

                def on_step(current: int, total: int):
                    progress.setValue(current)
                    progress.setLabelText(f"Writing preset {current:02d} of {total:02d}...")
                    from PyQt6.QtCore import QCoreApplication
                    QCoreApplication.processEvents()

                success = self.transport.upload_all_presets_to_guitar(self.librarian.patches, progress_callback=on_step)
                progress.close()

                if not success:
                    QMessageBox.critical(self, "Upload Error", "Failed to upload presets to guitar flash.")
                    return

            # 2. Modo Arduino StrapBox (Sincroniza a EEPROM)
            elif self.transport.conn_type == CONN_ARDUINO:
                self.transport.sync_strapbox_eeprom(self.librarian.patches, self.librarian.groups, index_map)

            # Envia PC para o preset inicial
            def_val = self.librarian.groups[0].get("default_patch", 0)
            initial_slot = def_val if isinstance(def_val, int) else index_map.get(str(def_val).lower(), 0)
            self.transport.send_pc(initial_slot)

            # Sincroniza a lista e as bolinhas verdes
            self.librarian.sync_all_guitar_patches()
            self.populate_patch_list()
            self.patch_list.setCurrentRow(self.current_slot)

            QMessageBox.information(
                self, "Upload Complete",
                "All 64 presets successfully written to guitar flash memory!\nEverything is synced."
            )

        except Exception as e:
            QMessageBox.critical(self, "Upload Failed", f"Upload Failed: {e}")

    def auto_recall_guitar_presets(self) -> None:
        """Executa o recall dos 64 presets da guitarra no arranque e popula a lista temporária."""
        progress = QProgressDialog("Recalling presets from AT-200...", "Cancel", 0, 64, self)
        progress.setWindowTitle("Hardware Sync")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        def on_step(current: int, total: int):
            progress.setValue(current)
            progress.setLabelText(f"Receiving preset {current:02d} of {total:02d} from AT-200...")
            from PyQt6.QtCore import QCoreApplication
            QCoreApplication.processEvents()

        try:
            # 1. Recebe e descompacta os 64 presets
            recalled = self.transport.recall_all_presets_from_guitar(progress_callback=on_step)
            
            # 2. Carrega para a lista temporária em RAM (guitar_patches)
            if len(recalled) == 64:
                for i in range(64):
                    self.librarian.update_guitar_patch(i, recalled[i])
                
                self.lbl_status.setText("MIDI Connected")
                self.lbl_status.setStyleSheet("color: #2ecc71; font-weight: bold; padding: 2px;")
        except Exception as e:
            print(f"[UI] Warning during startup recall: {e}")
        finally:
            progress.close()

        # 3. Recalcula a lista na UI: os que forem iguais ficam Verdes, os que divergirem ficam Azuis
        self.populate_patch_list()