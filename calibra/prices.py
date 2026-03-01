"""Price table loading from prices.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path

from calibra.config import Campaign, ConfigError


def load_prices(config_path: Path) -> dict[tuple[str, str], float]:
    prices_path = config_path.parent / "prices.toml"
    if not prices_path.exists():
        return {}

    with open(prices_path, "rb") as f:
        raw = tomllib.load(f)

    prices: dict[tuple[str, str], float] = {}
    for key, value in raw.get("prices", {}).items():
        provider, _, model = key.partition("/")
        if not model:
            raise ConfigError(f"Invalid price key '{key}': expected 'provider/model' format")
        prices[(provider, model)] = float(value)

    return prices


def validate_price_coverage(campaign: Campaign, prices: dict[tuple[str, str], float]):
    missing = []
    for m in campaign.models:
        if m.model is None:
            continue
        key = (m.provider, m.model)
        if key not in prices:
            missing.append(f"{m.provider}/{m.model}")
    if missing:
        raise ConfigError(
            f"Missing price entries for: {', '.join(missing)}. "
            f"Add them to prices.toml or set require_price_coverage = false."
        )
