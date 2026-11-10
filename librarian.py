#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Peavey AT-200 Master Controller — Librarian Module (librarian.py)
Manages JSON storage, timestamped backups, shadow memory diff tracking,
and preset renaming propagation.
All comments, docstrings, and symbols are strictly in English.
"""

import copy
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

from core import (
    DATA_DIR,
    BACKUPS_DIR,
    PATCHES_FILE,
    GROUPS_FILE,
    ensure_directories,
    create_empty_patch,
    create_empty_group
)


class PatchLibrarian:
    """Manages preset library, performance groups, disk persistence, and diff tracking."""

    def __init__(self) -> None:
        ensure_directories()
        self.patches: List[Dict[str, Any]] = [create_empty_patch() for _ in range(64)]
        self.groups: List[Dict[str, Any]] = [create_empty_group(i) for i in range(10)]
        self.shadow_patches: List[Dict[str, Any]] = copy.deepcopy(self.patches)
        self.guitar_patches: List[Dict[str, Any]] = copy.deepcopy(self.patches)
        self.load_all()

    # --------------------------------------------------------------------------
    # DISK PERSISTENCE
    # --------------------------------------------------------------------------
    def load_all(self) -> None:
        """Loads patches and groups from JSON disk files, or initializes defaults."""
        self.load_patches()
        self.load_groups()
        self.sync_shadow_memory()
        self.guitar_patches = copy.deepcopy(self.patches)

    def load_patches(self) -> None:
        """Loads the 64 preset slots from disk."""
        if os.path.exists(PATCHES_FILE):
            try:
                with open(PATCHES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) == 64:
                        self.patches = data
                        return
            except Exception as err:
                print(f"[Librarian] Error reading patches file: {err}")

        # Fallback to factory initialization
        self.patches = [create_empty_patch() for _ in range(64)]
        self.save_patches()

    def load_groups(self) -> None:
        """Loads the 10 performance groups from disk."""
        if os.path.exists(GROUPS_FILE):
            try:
                with open(GROUPS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) == 10:
                        self.groups = data
                        return
            except Exception as err:
                print(f"[Librarian] Error reading groups file: {err}")

        # Fallback to factory initialization
        self.groups = [create_empty_group(i) for i in range(10)]
        self.save_groups()

    def save_patches(self) -> bool:
        """Writes current patches collection to disk."""
        ensure_directories()
        try:
            with open(PATCHES_FILE, "w", encoding="utf-8") as f:
                json.dump(self.patches, f, indent=2)
            return True
        except Exception as err:
            print(f"[Librarian] Error saving patches to disk: {err}")
            return False

    def save_groups(self) -> bool:
        """Writes current performance groups collection to disk."""
        ensure_directories()
        try:
            with open(GROUPS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.groups, f, indent=2)
            return True
        except Exception as err:
            print(f"[Librarian] Error saving groups to disk: {err}")
            return False

    def save_all(self) -> bool:
        """Persists all patches and groups, updating shadow memory."""
        success_patches = self.save_patches()
        success_groups = self.save_groups()
        if success_patches and success_groups:
            self.sync_shadow_memory()
            return True
        return False

    # --------------------------------------------------------------------------
    # SHADOW MEMORY & DIFF ENGINE
    # --------------------------------------------------------------------------
    def sync_shadow_memory(self) -> None:
        """Updates shadow baseline to match current disk-persisted state."""
        self.shadow_patches = copy.deepcopy(self.patches)

    def is_patch_modified(self, slot_idx: int, live_dict: Dict[str, Any]) -> bool:
        """
        Compares an active UI preset configuration against its shadow baseline.
        Returns True if any functional parameter or note differs.
        """
        if not (0 <= slot_idx < 64):
            return False

        baseline = self.shadow_patches[slot_idx]
        comparable_keys = [
            "name", "model", "pickup", "capo", "pitch_shift",
            "tuning", "double", "gate", "solid_tune",
            "custom_tuning", "custom_doubling", "notes"
        ]

        for key in comparable_keys:
            if baseline.get(key) != live_dict.get(key):
                return True

        return False

    def has_any_unsaved_changes(self) -> bool:
        """Checks if the internal library differs from the shadow baseline."""
        return self.patches != self.shadow_patches

    def is_patch_identical(self, patch_a: Dict[str, Any], patch_b: Dict[str, Any]) -> bool:
        """
        Performs a deep field-by-field parameter comparison between two patches.
        Returns True if sound parameters and name are exactly identical.
        """
        comparable_keys = [
            "name", "model", "pickup", "capo", "pitch_shift",
            "tuning", "double", "gate", "solid_tune",
            "custom_tuning", "custom_doubling"
        ]
        for key in comparable_keys:
            if patch_a.get(key) != patch_b.get(key):
                return False
        return True

    def is_slot_synced_with_guitar(self, slot_idx: int) -> bool:
        """Returns True if local library patch matches guitar shadow memory."""
        if not (0 <= slot_idx < 64):
            return False
        return self.is_patch_identical(self.patches[slot_idx], self.guitar_patches[slot_idx])

    def update_guitar_patch(self, slot_idx: int, patch_data: Dict[str, Any]) -> None:
        """Updates guitar shadow memory slot when a successful flash occurs."""
        if 0 <= slot_idx < 64:
            self.guitar_patches[slot_idx] = copy.deepcopy(patch_data)

    def sync_all_guitar_patches(self) -> None:
        """Synchronizes all 64 guitar shadow memory slots with local library."""
        self.guitar_patches = copy.deepcopy(self.patches)

    # --------------------------------------------------------------------------
    # PRESET & GROUP OPERATIONS
    # --------------------------------------------------------------------------
    def get_patch(self, slot_idx: int) -> Dict[str, Any]:
        """Retrieves a deep copy of a specific preset slot."""
        if 0 <= slot_idx < 64:
            return copy.deepcopy(self.patches[slot_idx])
        return create_empty_patch()

    def update_patch(self, slot_idx: int, patch_data: Dict[str, Any], sync_shadow: bool = False) -> None:
        """Updates a preset slot in memory with provided dictionary."""
        if 0 <= slot_idx < 64:
            self.patches[slot_idx] = copy.deepcopy(patch_data)
            if sync_shadow:
                self.shadow_patches[slot_idx] = copy.deepcopy(patch_data)

    def clear_patch(self, slot_idx: int) -> str:
        """Resets a preset slot to factory EMPTY and returns the previous name."""
        if 0 <= slot_idx < 64:
            old_name = self.patches[slot_idx].get("name", "EMPTY")
            self.patches[slot_idx] = create_empty_patch("EMPTY")
            self.shadow_patches[slot_idx] = create_empty_patch("EMPTY")
            self.propagate_rename(old_name, "EMPTY")
            self.save_all()
            return old_name
        return "EMPTY"

    def propagate_rename(self, old_name: str, new_name: str) -> bool:
        """
        Updates references in performance group directional slots
        and the default preset when a patch is renamed or cleared.
        """
        if not old_name or old_name == new_name:
            return False

        changed = False
        for g in self.groups:
            # Update default patch reference if matched
            if g.get("default_patch") == old_name:
                g["default_patch"] = new_name
                changed = True

            # Update directional shortcut slots
            slots = g.get("slots", ["EMPTY"] * 4)
            for idx, s in enumerate(slots):
                if s == old_name:
                    slots[idx] = new_name
                    changed = True
            g["slots"] = slots

        if changed:
            self.save_groups()

        return changed

    def build_index_map(self) -> Dict[str, int]:
        """Constructs a case-insensitive name-to-index lookup dictionary."""
        index_map: Dict[str, int] = {}
        for i, patch in enumerate(self.patches):
            name_key = patch.get("name", "").strip().lower()
            if name_key and name_key not in index_map:
                index_map[name_key] = i
        return index_map

    # --------------------------------------------------------------------------
    # BACKUP & RESTORE ENGINE
    # --------------------------------------------------------------------------
    def backup_library(self) -> Optional[str]:
        """
        Exports a full timestamped JSON bundle of all 64 presets and 10 groups
        to the portable backups directory.
        """
        ensure_directories()
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        filename = f"Library_Backup_{timestamp}.json"
        filepath = os.path.join(BACKUPS_DIR, filename)

        bundle = {
            "version": 3,
            "timestamp": timestamp,
            "type": "library_backup",
            "patches": self.patches,
            "groups": self.groups
        }

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(bundle, f, indent=2)
            return filepath
        except Exception as err:
            print(f"[Librarian] Library backup export failed: {err}")
            return None

    def restore_backup(self, filepath: str) -> bool:
        """Restores library and groups from a backup JSON file."""
        if not os.path.exists(filepath):
            return False

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                bundle = json.load(f)

            loaded_patches = bundle.get("patches")
            loaded_groups = bundle.get("groups")

            if isinstance(loaded_patches, list) and len(loaded_patches) == 64:
                self.patches = loaded_patches
            if isinstance(loaded_groups, list) and len(loaded_groups) == 10:
                self.groups = loaded_groups

            self.save_all()
            return True
        except Exception as err:
            print(f"[Librarian] Backup restore failed: {err}")
            return False