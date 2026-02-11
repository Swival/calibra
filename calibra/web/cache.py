"""In-memory result index for fast page loads."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from calibra.utils import weighted_pass_rate


@dataclass
class CampaignIndex:
    name: str
    summary: dict | None
    trial_files: list[Path]
    latest_mtime: float

    @property
    def n_variants(self) -> int:
        if self.summary and "variants" in self.summary:
            return len(self.summary["variants"])
        return 0

    @property
    def n_tasks(self) -> int:
        if self.summary and "trials" in self.summary:
            return len({t["task"] for t in self.summary["trials"]})
        return 0

    @property
    def n_trials(self) -> int:
        if self.summary and "trials" in self.summary:
            return len(self.summary["trials"])
        return len(self.trial_files)

    @property
    def pass_rate(self) -> float | None:
        if self.summary and "variants" in self.summary:
            variants = self.summary["variants"]
            if variants:
                return weighted_pass_rate(variants)
        return None


@dataclass
class ResultCache:
    results_dir: Path
    campaigns: dict[str, CampaignIndex] = field(default_factory=dict)

    def scan(self) -> None:
        self.campaigns.clear()
        if not self.results_dir.is_dir():
            return

        for entry in sorted(self.results_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            self._index_campaign(entry)

    def _index_campaign(self, campaign_dir: Path) -> None:
        summary = None
        summary_path = campaign_dir / "summary.json"
        if summary_path.is_file():
            try:
                summary = json.loads(summary_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        trial_files = sorted(p for p in campaign_dir.rglob("*.json") if p.name != "summary.json")

        latest_mtime = 0.0
        for tf in trial_files:
            try:
                mt = tf.stat().st_mtime
                if mt > latest_mtime:
                    latest_mtime = mt
            except OSError:
                pass

        self.campaigns[campaign_dir.name] = CampaignIndex(
            name=campaign_dir.name,
            summary=summary,
            trial_files=trial_files,
            latest_mtime=latest_mtime,
        )

    def reload(self) -> None:
        self.scan()

    def get(self, name: str) -> CampaignIndex | None:
        return self.campaigns.get(name)
