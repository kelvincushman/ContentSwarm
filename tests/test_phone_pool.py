import pytest

from phone_agent.adb.connection import ConnectionType, DeviceInfo
from phone_agent.phone_pool import PhonePoolManager
import phone_agent.phone_pool as pool_module


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
