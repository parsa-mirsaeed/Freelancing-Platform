## What changed?

## Affected domains

## Risk checklist

- [ ] DB migration: no
- [ ] API contract changed: no
- [ ] Payment behavior changed: no
- [ ] Security impact: no
- [ ] New config/secrets: no
- [ ] Observability added/changed: no

If any item above is `yes`, explain the impact and compatibility strategy below.

## Migration / compatibility strategy

Use expand → migrate/backfill → switch reads → contract later for production schema changes. Do not silently combine destructive contract changes with rollout code.

## Rollback strategy

State whether rollback is application-only, requires a feature flag, or requires a forward database repair. Production release must reuse an already scanned main image digest.

## Tests added or updated

List only the affected test domains selected by the PR impact map. Slow/E2E/load/full-security work belongs in nightly or pre-release workflows unless the PR specifically changes that harness.
