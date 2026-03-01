"""Budget tracking for campaign execution."""

from __future__ import annotations

from dataclasses import dataclass

from calibra.config import BudgetConfig
from calibra.utils import sum_prompt_tokens


@dataclass
class BudgetTracker:
    budget: BudgetConfig
    prices: dict[tuple[str, str], float]
    cumulative_tokens: int = 0
    cumulative_cost_usd: float = 0.0
    exceeded: bool = False
    reason: str = ""

    def update(self, result) -> bool:
        if result.report:
            tokens = sum_prompt_tokens(result.report)
            self.cumulative_tokens += tokens

            model = result.spec.variant.model
            key = (model.provider, model.model)
            if key in self.prices:
                self.cumulative_cost_usd += tokens / 1000 * self.prices[key]

        if (
            self.budget.max_total_tokens > 0
            and self.cumulative_tokens > self.budget.max_total_tokens
        ):
            self.exceeded = True
            self.reason = (
                f"Token budget exceeded: {self.cumulative_tokens} > {self.budget.max_total_tokens}"
            )
        if self.budget.max_cost_usd > 0 and self.cumulative_cost_usd > self.budget.max_cost_usd:
            self.exceeded = True
            self.reason = f"Cost budget exceeded: ${self.cumulative_cost_usd:.2f} > ${self.budget.max_cost_usd:.2f}"

        return self.exceeded
