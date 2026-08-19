# ADR 0015: AI Baseline and Model Governance

## Status

Accepted.

## Context

The marketplace now has stable Marketplace, Contract, Money, Communication, Dispute, and
one-to-one Calls boundaries. The next phase needs intelligent matching, event attribution,
skill suggestions, price estimates, and spam/fraud signals. Product interaction data is not
yet mature enough to justify a neural recommender or online-trained fraud model.

The source blueprint explicitly requires candidate generation followed by hard filters and a
rule-based ranking baseline before ML ranking, versioned predictions, offline ranking metrics,
non-mutating low-confidence skill suggestions, interval-based price estimates, and fraud
scoring that never delegates heavy enforcement solely to a model.

## Decision

### Recommendation baseline

Project matching uses the existing Elasticsearch freelancer projection for candidate
generation. PostgreSQL remains authoritative for project ownership, historical proposal
amounts, prediction attribution, and interaction events.

The first deterministic score is:

- skill overlap: 40%
- historical experience: 20%
- price fit from prior proposal amounts: 15%
- accepting-work availability: 10%
- review reputation: 15%

Scores are stored as integer basis points. Ties are broken by freelancer user id for stable
ranking. Project language/timezone requirements are not currently modeled, so this version
does not invent those features; they may be added in a future feature schema.

Each run persists `model_version`, `feature_version`, `candidate_set_version`, rank, score,
feature vector, and human-readable reasons. The candidate set version is a SHA-256 digest of
the project revision plus sorted candidate ids.

### Interaction attribution

Clients may submit only low-stakes `IMPRESSION` and `PROFILE_VIEW` events with an idempotent
client event id. Invite, proposal, hire, completion, and rating labels are derived from the
existing authoritative marketplace tables during offline evaluation/training instead of
trusting client-supplied conversion events.

### Skill extraction

The first skill extractor matches active canonical skills against profile title, bio, and
portfolio title/description text. Confidence reflects the evidence source. Suggestions never
mutate the freelancer profile; the user must explicitly choose skills through the normal
profile workflow. File/OCR text extraction is deferred until a dedicated extraction pipeline
exists.

### Smart pricing

Price estimation returns an interval, not a false-precision point estimate. With at least
three historical comparable proposals it returns the 25th-75th percentile range. Otherwise it
falls back to the project's explicit budget range when available, and reports insufficient
data when neither source is adequate.

### Fraud/spam baseline

The first fraud scorer combines explainable rules over URL spam, off-platform contact terms,
message velocity, account age, failed payments, proposal bursts, repeated disputes, and
repeated assessed text. No protected-class feature is used. IP/device reuse is intentionally
absent until trustworthy telemetry exists.

A score at or above the configured review threshold creates a `PENDING` human-review item.
Reviewers may only mark it `CLEARED` or `ESCALATED`; this domain does not ban accounts, move
money, cancel contracts, or apply another heavy action automatically.

### Model registry and evaluation

All deployed baselines are registered in PostgreSQL with model name/version, feature version,
configuration, metrics, status, and optional artifact URI. Only one version per model name may
be `ACTIVE`.

PR validation never performs full training. It covers feature transformations, deterministic
inference, configuration serialization, schema compatibility, and a tiny fixed ranking
regression dataset using Precision@K, Recall@K, NDCG@K, and conversion@K. Real training and
large evaluation datasets belong to offline/nightly workflows before a future ML model is
promoted.

## Consequences

The system gains explainable intelligent behavior now while preserving a clean upgrade path
to supervised ranking and fraud models later. Search/index loss cannot remove prediction or
business history because Elasticsearch is used only for candidate generation. Training data
can be built by joining immutable/versioned recommendation attribution with authoritative
business outcomes.

## Rollback

The recommendation and fraud blueprints may be disabled independently. Migration
`0008_ai_baseline` is additive; it may be rolled back only after AI endpoints are disabled and
stored prediction/risk history is no longer needed.
