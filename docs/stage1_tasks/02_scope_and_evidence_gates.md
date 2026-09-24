# Task 02 — Named-entity and evidence-scope guardrails

## Goal

Prevent valid evidence from the wrong population, entity, category, period or grain from supporting a material conclusion.

## Known failure

The renamed-product case asked whether **Ocean Wash** had an inventory problem. The model used whole-inventory excess totals and attributed them to Ocean Wash even though Ocean Wash itself was low stock with zero excess units.

## Required behaviour

Before releasing a material claim, deterministically validate where practical:

- named entity attribution
- whole-business vs category vs entity scope
- current/baseline period
- measure and unit
- grain and denominator compatibility
- missing/empty/query-failure coverage

Whole-business evidence may be used as explicitly labelled context for an entity-specific answer, but must not prove a claim about the named entity.

Apply this generally to staff, products/SKUs, customers, suppliers and other named entities. Do not add an Ocean-Wash-specific rule.

## Likely files

commercial/v2_runtime.py, commercial/v2_data.py, commercial/v2_models.py and tests/test_commercial_v2.py.

## Acceptance tests

- The Ocean Wash renamed fixture cannot attribute portfolio excess stock to Ocean Wash.
- A named staff claim cannot be supported only by a whole-business packet.
- A category-specific result cannot be described as whole-business.
- Booked hours cannot support a booking-count claim.
- Customer visits cannot silently become distinct-customer counts.
- Gross profit cannot become operating profit.
- Missing values, empty filtered subsets and rejected queries cannot become zero/absence claims.
- Whole-business context remains available when explicitly labelled as context.

## Stop condition

Local tests only. Stop for review before Task 03.
