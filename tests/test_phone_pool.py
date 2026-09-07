import pytest
import phone_agent.phone_pool as pool_module

from phone_agent.adb.connection import ConnectionType, DeviceInfo
from phone_agent.phone_pool import PhonePoolManager


def devices():
    """Return one usable and two unusable discovery records."""
    return [
        DeviceInfo("good", "device", ConnectionType.USB),
        DeviceInfo("waiting", "unauthorized", ConnectionType.USB),
        DeviceInfo("lost", "offline", ConnectionType.REMOTE),
    ]


def test_discovery_persists_only_authorized_online_devices(tmp_path, monkeypatch):
    """Unauthorized and offline serials must never enter the registry."""
    config = tmp_path / "phones.json"
    config.write_text('{"phones": []}', encoding="utf-8")
    manager = PhonePoolManager(phones_config=str(config))
    monkeypatch.setattr(pool_module, "list_devices", devices)
    try:
        assert manager.scan_and_add_devices() == 1
        assert list(manager.phones) == ["phone_good"]
        assert '"device_id": "good"' in config.read_text(encoding="utf-8")
        assert "waiting" not in config.read_text(encoding="utf-8")
    finally:
        manager.shutdown()


def test_discovery_rolls_back_new_entries_when_persistence_fails(monkeypatch):
    """The in-memory registry must match disk after a failed save."""
    manager = PhonePoolManager()
    manager.config_path = "/unwritable/phones.json"
    monkeypatch.setattr(pool_module, "list_devices", lambda: devices()[:1])
    monkeypatch.setattr(manager, "save_phones", lambda _path: (_ for _ in ()).throw(OSError("full")))
    try:
        with pytest.raises(OSError, match="full"):
            manager.scan_and_add_devices()
        assert manager.phones == {}
    finally:
        manager.shutdown()


def test_discovery_creates_an_initially_missing_config(tmp_path, monkeypatch):
    """A first discovery survives restart when the config did not exist."""
    config = tmp_path / "phones.json"
    manager = PhonePoolManager(phones_config=str(config))
    monkeypatch.setattr(pool_module, "list_devices", lambda: devices()[:1])
    try:
        assert manager.scan_and_add_devices() == 1
        assert '"device_id": "good"' in config.read_text(encoding="utf-8")
    finally:
        manager.shutdown()


def test_direct_operation_shares_the_per_phone_task_lock():
    """A direct operation cannot interleave with another operation or task."""
    manager = PhonePoolManager()
    try:
        with manager.phone_operation("primary"):
            with pytest.raises(RuntimeError, match="busy"):
                with manager.phone_operation("primary"):
                    pass
    finally:
        manager.shutdown()


def test_save_phones_keeps_existing_config_when_replace_fails(tmp_path, monkeypatch):
    """An interrupted atomic commit cannot truncate the canonical registry."""
    config = tmp_path / "phones.json"
    original = '{"phones": [{"name": "existing"}]}\n'
    config.write_text(original, encoding="utf-8")
    manager = PhonePoolManager()
    manager.add_phone("new", "serial")
    monkeypatch.setattr(pool_module.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("full")))
    try:
        with pytest.raises(OSError, match="full"):
            manager.save_phones(str(config))
        assert config.read_text(encoding="utf-8") == original
        assert not list(tmp_path.glob(".phones.json.*"))
    finally:
        manager.shutdown()
