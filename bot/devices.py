"""Device and user-agent rotation for realistic browser emulation."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceProfile:
    name: str
    user_agent: str
    viewport_width: int
    viewport_height: int
    is_mobile: bool
    platform: str


DESKTOP_PROFILES: list[DeviceProfile] = [
    DeviceProfile(
        name="Windows Chrome",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        viewport_width=1920,
        viewport_height=1080,
        is_mobile=False,
        platform="Win32",
    ),
    DeviceProfile(
        name="Windows Edge",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
        ),
        viewport_width=1536,
        viewport_height=864,
        is_mobile=False,
        platform="Win32",
    ),
    DeviceProfile(
        name="macOS Safari",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.2 Safari/605.1.15"
        ),
        viewport_width=1440,
        viewport_height=900,
        is_mobile=False,
        platform="MacIntel",
    ),
    DeviceProfile(
        name="macOS Chrome",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        viewport_width=1680,
        viewport_height=1050,
        is_mobile=False,
        platform="MacIntel",
    ),
    DeviceProfile(
        name="Linux Firefox",
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0"
        ),
        viewport_width=1366,
        viewport_height=768,
        is_mobile=False,
        platform="Linux x86_64",
    ),
]

MOBILE_PROFILES: list[DeviceProfile] = [
    DeviceProfile(
        name="iPhone 14",
        user_agent=(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 "
            "Mobile/15E148 Safari/604.1"
        ),
        viewport_width=390,
        viewport_height=844,
        is_mobile=True,
        platform="iPhone",
    ),
    DeviceProfile(
        name="Samsung Galaxy S23",
        user_agent=(
            "Mozilla/5.0 (Linux; Android 14; SM-S911B) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
        ),
        viewport_width=360,
        viewport_height=780,
        is_mobile=True,
        platform="Linux armv81",
    ),
    DeviceProfile(
        name="iPad Air",
        user_agent=(
            "Mozilla/5.0 (iPad; CPU OS 17_3 like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1"
        ),
        viewport_width=820,
        viewport_height=1180,
        is_mobile=True,
        platform="iPad",
    ),
    DeviceProfile(
        name="Pixel 7",
        user_agent=(
            "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
        ),
        viewport_width=412,
        viewport_height=915,
        is_mobile=True,
        platform="Linux armv81",
    ),
]

ALL_PROFILES = DESKTOP_PROFILES + MOBILE_PROFILES


def random_device() -> DeviceProfile:
    """Pick a random device profile (70% desktop, 30% mobile)."""
    pool = MOBILE_PROFILES if random.random() < 0.3 else DESKTOP_PROFILES
    return random.choice(pool)
