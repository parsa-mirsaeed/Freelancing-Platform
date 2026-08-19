from __future__ import annotations

import json
from dataclasses import dataclass

FEATURE_VERSION = "matching-features-v1"
MODEL_NAME = "freelancer_matching"
MODEL_VERSION = "rule-v1"


@dataclass(frozen=True, slots=True)
class RankingConfig:
    skill_match_weight: int = 4000
    experience_weight: int = 2000
    price_fit_weight: int = 1500
    availability_weight: int = 1000
    reputation_weight: int = 1500

    def __post_init__(self) -> None:
        weights = self.weights()
        if any(weight < 0 for weight in weights.values()) or sum(weights.values()) != 10000:
            raise ValueError("Recommendation weights must be nonnegative and sum to 10000")

    def weights(self) -> dict[str, int]:
        return {
            "skill_match": self.skill_match_weight,
            "experience": self.experience_weight,
            "price_fit": self.price_fit_weight,
            "availability": self.availability_weight,
            "reputation": self.reputation_weight,
        }

    def score_basis_points(self, features: dict[str, float]) -> int:
        total = 0.0
        for name, weight in self.weights().items():
            value = min(1.0, max(0.0, float(features.get(name, 0.0))))
            total += value * weight
        return min(10000, max(0, int(round(total))))

    def to_json(self) -> str:
        return json.dumps(self.weights(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, payload: str) -> RankingConfig:
        values = json.loads(payload)
        if not isinstance(values, dict):
            raise ValueError("Ranking config payload must be an object")
        return cls(
            skill_match_weight=int(values["skill_match"]),
            experience_weight=int(values["experience"]),
            price_fit_weight=int(values["price_fit"]),
            availability_weight=int(values["availability"]),
            reputation_weight=int(values["reputation"]),
        )


DEFAULT_RANKING_CONFIG = RankingConfig()
EXPECTED_FEATURE_KEYS = frozenset(DEFAULT_RANKING_CONFIG.weights())
