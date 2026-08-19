# AI rule baselines

This phase intentionally ships deterministic baselines rather than trained models.

| Model | Version | Feature version | Purpose |
| --- | --- | --- | --- |
| freelancer matching | `rule-v1` | `matching-features-v1` | Candidate reranking after Elasticsearch generation |
| skill extraction | `skill-rules-v1` | `skill-text-features-v1` | Non-mutating canonical skill suggestions |
| price estimation | `pricing-baseline-v1` | `pricing-history-v1` | Competitive interval from comparable proposal history |
| fraud risk | `fraud-rules-v1` | `fraud-signals-v1` | Explainable review prioritization only |

## Promotion rules

A future supervised model must be registered with a new immutable version and feature schema.
Before activation it must pass deterministic serialization/inference checks, schema
compatibility, and a fixed offline ranking/risk regression suite. Large training jobs and
large datasets do not run in pull requests.

Recommendation evaluation tracks Precision@K, Recall@K, NDCG@K, and conversion@K. Online
conversion labels are joined from authoritative invite/proposal/hire/completion/review data;
clients provide only impression/profile-view attribution.

Fraud model promotion must preserve reason codes, human review, and the rule that model output
alone cannot permanently ban a user, move funds, cancel a contract, or decide a dispute.
