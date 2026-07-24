"""Client / app configuration accuracy (target #4) and conflicting behavior
between near-duplicate helpers (target #6).
"""
import json

import pytest

from profile_manager import ProfileManager, ValidationError


# ---------------------------------------------------------------------------
# validate_client_id
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("client_id,expected_valid", [
    ("M", True),
    ("CLIENT1", True),
    ("A_B", True),
    ("", False),                 # empty
    ("TOOLONGID1", True),        # 10 chars is fine
    ("TOOLONGID12", False),      # 11 chars — over the limit
    ("CLIENT_M", False),         # reserved prefix
    ("CON", False),              # Windows reserved name
    ("com1", False),             # reserved name, and lowercase is rejected anyway
    ("m", False),                # lowercase not allowed by the [A-Z0-9_] regex
    ("M-1", False),              # hyphen not allowed
])
def test_validate_client_id(client_id, expected_valid):
    is_valid, _ = ProfileManager.validate_client_id(client_id)
    assert is_valid is expected_valid


# ---------------------------------------------------------------------------
# create_client_profile
# ---------------------------------------------------------------------------

def test_create_client_profile_writes_expected_files(profile_manager):
    ok = profile_manager.create_client_profile("M", "M Cosmetics")
    assert ok is True

    client_dir = profile_manager.clients_dir / "CLIENT_M"
    assert (client_dir / "packer_config.json").exists()
    assert (client_dir / "client_config.json").exists()
    assert (client_dir / "backups").is_dir()
    assert (profile_manager.sessions_dir / "CLIENT_M").is_dir()

    config = json.loads((client_dir / "packer_config.json").read_text(encoding="utf-8"))
    assert config["client_id"] == "M"
    assert config["client_name"] == "M Cosmetics"
    assert config["sku_mapping"] == {}


def test_create_client_profile_returns_false_if_already_exists(profile_manager):
    profile_manager.create_client_profile("M", "M Cosmetics")
    assert profile_manager.create_client_profile("M", "M Cosmetics Again") is False


def test_create_client_profile_rejects_invalid_id(profile_manager):
    with pytest.raises(ValidationError):
        profile_manager.create_client_profile("client_m", "whatever")


# ---------------------------------------------------------------------------
# load/save client config
# ---------------------------------------------------------------------------

def test_save_client_config_round_trips_and_stamps_metadata(profile_manager):
    profile_manager.create_client_profile("M", "M Cosmetics")
    config = profile_manager.load_client_config("M")
    config["barcode_label"]["font_size"] = 14
    assert profile_manager.save_client_config("M", config) is True

    reloaded_fresh = json.loads(
        (profile_manager.clients_dir / "CLIENT_M" / "packer_config.json").read_text(encoding="utf-8")
    )
    assert reloaded_fresh["barcode_label"]["font_size"] == 14
    assert "last_updated" in reloaded_fresh
    assert "updated_by" in reloaded_fresh


def test_save_client_config_creates_a_backup_of_the_previous_version(profile_manager):
    profile_manager.create_client_profile("M", "M Cosmetics")
    config = profile_manager.load_client_config("M")
    profile_manager.save_client_config("M", config)

    backups = list((profile_manager.clients_dir / "CLIENT_M" / "backups").glob("packer_config_*.json"))
    assert len(backups) == 1


def test_load_client_config_missing_client_returns_none(profile_manager):
    assert profile_manager.load_client_config("NOPE") is None


# ---------------------------------------------------------------------------
# BUG: load_client_config's cache-hit path returns the live cached dict by
# reference (no .copy()) — inconsistent with load_sku_mapping, which always
# .copy()s. A caller that does `cfg = load_client_config(...); cfg['x'] = y`
# for local-only processing silently corrupts the class-level cache for every
# other reader of that client's config for up to CACHE_TIMEOUT_SECONDS,
# without ever touching disk.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason=(
        "BUG: ProfileManager.load_client_config() caches and returns the same "
        "dict object (both on cache-miss and cache-hit) instead of a defensive "
        "copy, unlike load_sku_mapping() which always returns .copy(). Any "
        "caller mutating the returned config for local use corrupts the shared "
        "class-level cache."
    ),
    strict=True,
)
def test_load_client_config_does_not_leak_mutations_into_the_cache(profile_manager):
    profile_manager.create_client_profile("M", "M Cosmetics")
    config = profile_manager.load_client_config("M")
    config["client_name"] = "MUTATED BY CALLER"  # caller mutates its own local copy...

    reloaded = profile_manager.load_client_config("M")  # ...should be unaffected (still cached, same TTL)
    assert reloaded["client_name"] == "M Cosmetics"


# ---------------------------------------------------------------------------
# BUG: _config_cache / _sku_cache are class-level attributes, not per-instance
# — every ProfileManager in the process shares one cache keyed only by
# client_id, with no base_path in the key. Two ProfileManager instances
# pointed at two different file servers (e.g. dev vs prod config, or the app
# reloading config.ini after the user changes FileServerPath) but with the
# same client_id will leak each other's cached config/SKU data.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason=(
        "BUG: ProfileManager._config_cache/_sku_cache are class attributes "
        "(`Dict[...] = {}` on the class body), shared across every instance in "
        "the process regardless of base_path. A second ProfileManager pointed "
        "at a different file server root, but with the same client_id, gets "
        "the first instance's cached data instead of reading its own disk."
    ),
    strict=True,
)
def test_config_cache_does_not_leak_across_instances_with_different_base_paths(tmp_path):
    import configparser

    def make_manager(server_dir):
        server_dir.mkdir()
        config_path = tmp_path / f"{server_dir.name}.ini"
        cfg = configparser.ConfigParser()
        cfg["Network"] = {"FileServerPath": str(server_dir), "ConnectionTimeout": "5", "LocalCachePath": ""}
        with open(config_path, "w", encoding="utf-8") as f:
            cfg.write(f)
        return ProfileManager(config_path=str(config_path))

    pm1 = make_manager(tmp_path / "server1")
    pm1.create_client_profile("M", "Server One Client")

    pm2 = make_manager(tmp_path / "server2")
    pm2.create_client_profile("M", "Server Two Client")

    assert pm1.load_client_config("M")["client_name"] == "Server One Client"
    assert pm2.load_client_config("M")["client_name"] == "Server Two Client"  # currently leaks pm1's cached value


# ---------------------------------------------------------------------------
# BUG: save_sku_mapping MERGES onto whatever is already on disk
# (current_mappings.update(mappings)) instead of replacing it. The SKU
# Mapping dialog's delete button removes an entry from its local dict and
# calls save_sku_mapping() with the reduced map, expecting a full replace —
# but the merge means a deleted mapping is silently restored on next load.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason=(
        "BUG: ProfileManager.save_sku_mapping() merges the given mapping onto "
        "the existing on-disk mapping (current_mappings.update(mappings)) "
        "rather than replacing it. sku_mapping_dialog.py's delete flow saves "
        "the full reduced dict expecting a replace-semantics save, so deleted "
        "barcode->SKU mappings silently reappear on the next load — users "
        "cannot actually delete a SKU mapping."
    ),
    strict=True,
)
def test_save_sku_mapping_can_delete_an_entry(profile_manager):
    profile_manager.create_client_profile("M", "M Cosmetics")
    profile_manager.save_sku_mapping("M", {"BARCODE-A": "SKU-A", "BARCODE-B": "SKU-B"})

    # User deletes "BARCODE-B" in the dialog, then saves the reduced map.
    profile_manager.save_sku_mapping("M", {"BARCODE-A": "SKU-A"})

    reloaded = profile_manager.load_sku_mapping("M")
    assert "BARCODE-B" not in reloaded, "deleted mapping reappeared after save — delete does not persist"


def test_save_sku_mapping_updates_and_adds_entries(profile_manager):
    profile_manager.create_client_profile("M", "M Cosmetics")
    profile_manager.save_sku_mapping("M", {"BARCODE-A": "SKU-A"})
    profile_manager.save_sku_mapping("M", {"BARCODE-A": "SKU-A-RENAMED", "BARCODE-C": "SKU-C"})

    reloaded = profile_manager.load_sku_mapping("M")
    assert reloaded["BARCODE-A"] == "SKU-A-RENAMED"
    assert reloaded["BARCODE-C"] == "SKU-C"


def test_load_sku_mapping_cache_hit_returns_a_copy_not_the_cached_object(profile_manager):
    """Contrast case for the load_client_config bug above: load_sku_mapping
    does this correctly — mutating the caller's copy must not affect the
    cached entry or a subsequent load.
    """
    profile_manager.create_client_profile("M", "M Cosmetics")
    profile_manager.save_sku_mapping("M", {"BARCODE-A": "SKU-A"})

    mapping = profile_manager.load_sku_mapping("M")
    mapping["BARCODE-A"] = "TAMPERED"

    reloaded = profile_manager.load_sku_mapping("M")
    assert reloaded["BARCODE-A"] == "SKU-A"


# ---------------------------------------------------------------------------
# BUG: get_available_clients() and list_clients() are near-duplicate
# functions meant to do the same thing but diverge on a valid client_id.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason=(
        "BUG: get_available_clients() strips the 'CLIENT_' prefix with "
        "str.replace('CLIENT_', ''), which removes EVERY occurrence of that "
        "substring, not just the leading one. list_clients() correctly slices "
        "off exactly the first 7 characters (dir_name[7:]). A client_id that "
        "legitimately contains 'CLIENT_' after the first character (allowed: "
        "validate_client_id only rejects an id that *starts* with 'CLIENT_') "
        "makes the two functions disagree."
    ),
    strict=True,
)
def test_get_available_clients_and_list_clients_agree(profile_manager):
    client_id = "XCLIENT_Y"  # valid per validate_client_id: doesn't start with CLIENT_
    is_valid, msg = ProfileManager.validate_client_id(client_id)
    assert is_valid, msg
    profile_manager.create_client_profile(client_id, "Edge Case Client")

    assert profile_manager.get_available_clients() == profile_manager.list_clients()
