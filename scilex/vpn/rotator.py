"""NordVPN IP rotation for bypassing per-IP API rate limits.

Works on native Windows, native Linux (nordvpn CLI), and WSL2 (calls NordVPN.exe
directly via the WSL2 interop path /mnt/c/Program Files/NordVPN/NordVPN.exe).
"""

import logging
import os
import platform
import random
import subprocess
import threading
import time
import urllib.request
from typing import Optional

import yaml


class VPNRotator:
    """Controls NordVPN IP rotation to bypass per-IP rate limits.

    Configured via the ``vpn:`` section of ``api.config.yml``.  Use the
    module-level :func:`get_vpn_rotator` to obtain the shared singleton.
    """

    _WSL_EXE_PATHS = [
        "/mnt/c/Program Files/NordVPN/NordVPN.exe",
        "/mnt/c/Program Files (x86)/NordVPN/NordVPN.exe",
    ]
    _WIN_EXE_PATHS = [
        "C:/Program Files/NordVPN/NordVPN.exe",
        "C:/Program Files (x86)/NordVPN/NordVPN.exe",
    ]

    # All countries available on NordVPN (as of 2025)
    ALL_COUNTRIES = [
        "Albania", "Argentina", "Australia", "Austria", "Belgium",
        "Bosnia and Herzegovina", "Brazil", "Bulgaria", "Canada", "Chile",
        "Colombia", "Costa Rica", "Croatia", "Cyprus", "Czech Republic",
        "Denmark", "Estonia", "Finland", "France", "Georgia", "Germany",
        "Greece", "Hong Kong", "Hungary", "Iceland", "India", "Indonesia",
        "Ireland", "Israel", "Italy", "Japan", "Latvia", "Luxembourg",
        "Malaysia", "Mexico", "Moldova", "Netherlands", "New Zealand",
        "North Macedonia", "Norway", "Poland", "Portugal", "Romania",
        "Serbia", "Singapore", "Slovakia", "Slovenia", "South Africa",
        "South Korea", "Spain", "Sweden", "Switzerland", "Taiwan", "Thailand",
        "Turkey", "Ukraine", "United Arab Emirates", "United Kingdom",
        "United States", "Vietnam",
    ]

    def __init__(self, config: dict):
        self.enabled: bool = config.get("enabled", False)
        self.rotate_on: set = set(config.get("rotate_on_rate_limit", []))
        self.rotation_delay: int = int(config.get("rotation_delay", 15))
        self.max_rotations: int = int(config.get("max_rotations_per_session", 10))
        # countries: explicit list from config, or full list, or [] for quick-connect
        cfg_countries = config.get("countries", self.ALL_COUNTRIES)
        self.countries: list = cfg_countries if cfg_countries else []

        self._rotation_count = 0
        self._lock = threading.Lock()
        self._exe_path: Optional[str] = None

        if self.enabled:
            self._exe_path = self._find_nordvpn_exe()
            if self._exe_path:
                apis_str = ", ".join(sorted(self.rotate_on)) if self.rotate_on else "all APIs"
                logging.warning(
                    f"[VPN] Rotation enabled — exe: {self._exe_path} | "
                    f"APIs: {apis_str} | limit: {self.max_rotations} rotations/session"
                )
            else:
                logging.warning(
                    "[VPN] Rotation enabled in config but NordVPN.exe not found — disabling."
                )
                self.enabled = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_rotate(self, api_name: str) -> bool:
        """Return True if rotation is enabled for *api_name* and within limits."""
        if not self.enabled:
            return False
        if self.rotate_on and api_name not in self.rotate_on:
            return False
        if self._rotation_count >= self.max_rotations:
            logging.warning(
                f"[VPN] Session limit of {self.max_rotations} rotations reached — "
                f"no further rotation will be attempted."
            )
            return False
        return True

    def rotate(self) -> bool:
        """Disconnect then reconnect NordVPN and verify the IP changed.

        Thread-safe: only one rotation runs at a time even when multiple API
        threads hit a rate limit simultaneously.

        Returns:
            True if the public IP changed after rotation, False otherwise.
        """
        with self._lock:
            if not self._exe_path:
                return False

            rotation_n = self._rotation_count + 1
            old_ip = self._get_public_ip()
            logging.warning(
                f"[VPN] --- Starting rotation {rotation_n}/{self.max_rotations} "
                f"(current IP: {old_ip or 'unknown'}) ---"
            )

            try:
                logging.warning("[VPN] Disconnecting from current server...")
                subprocess.run(
                    [self._exe_path, "-d"],
                    timeout=30,
                    check=False,
                    capture_output=True,
                )
                time.sleep(2)

                if self.countries:
                    country = random.choice(self.countries)
                    logging.warning(f"[VPN] Connecting to: {country}")
                    cmd = [self._exe_path, "-c", "-g", country]
                else:
                    logging.warning("[VPN] Connecting to new server (quick connect)...")
                    cmd = [self._exe_path, "-c"]
                subprocess.run(cmd, timeout=60, check=False, capture_output=True)

                logging.warning(
                    f"[VPN] Connected — waiting {self.rotation_delay}s for IP to propagate"
                )
                time.sleep(self.rotation_delay)

                new_ip = self._get_public_ip()
                if new_ip and new_ip != old_ip:
                    self._rotation_count += 1
                    logging.warning(
                        f"[VPN] Rotation {self._rotation_count}/{self.max_rotations} complete: "
                        f"{old_ip} -> {new_ip}"
                    )
                    return True

                logging.warning(
                    f"[VPN] Rotation failed: IP unchanged after reconnect (still {new_ip})"
                )
                return False

            except Exception as e:
                logging.error(f"[VPN] Rotation error: {e}")
                return False

    @property
    def rotation_count(self) -> int:
        return self._rotation_count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_wsl2() -> bool:
        if platform.system() != "Linux":
            return False
        try:
            with open("/proc/version") as fh:
                return "microsoft" in fh.read().lower()
        except OSError:
            return False

    def _find_nordvpn_exe(self) -> Optional[str]:
        candidates = self._WSL_EXE_PATHS if self._is_wsl2() else self._WIN_EXE_PATHS
        # Also allow native Linux nordvpn CLI
        if platform.system() == "Linux" and not self._is_wsl2():
            import shutil
            if shutil.which("nordvpn"):
                return "nordvpn"
        for p in candidates:
            if os.path.isfile(p):
                return p
        return None

    @staticmethod
    def _get_public_ip() -> Optional[str]:
        for url in ("https://api64.ipify.org", "https://api4.ipify.org"):
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    return resp.read().decode().strip()
            except Exception:
                continue
        return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: Optional[VPNRotator] = None
_instance_lock = threading.Lock()


def get_vpn_rotator() -> VPNRotator:
    """Return the process-wide VPNRotator singleton (thread-safe, lazy init)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = VPNRotator(_load_vpn_config())
    return _instance


def _load_vpn_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "api.config.yml")
    try:
        with open(config_path) as fh:
            cfg = yaml.safe_load(fh) or {}
        return cfg.get("vpn", {})
    except Exception as e:
        logging.debug(f"VPN: could not load config ({e}) — VPN rotation disabled.")
        return {}
