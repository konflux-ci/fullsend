---
title: "11. Canonical schema for admin-managed org config.yaml (v1)"
status: Accepted
relates_to:
  - governance
  - codebase-context
  - agent-infrastructure
topics:
  - configuration
  - admin-install
  - yaml
---

# 11. Canonical schema for admin-managed org config.yaml (v1)

Date: 2026-04-05

## Status

Accepted

## Context

[ADR 0003](0003-org-config-repo-convention.md) places org-level fullsend configuration in `<org>/.fullsend`, including a top-level `config.yaml`. That ADR intentionally deferred exact schema details. The admin CLI and config-repo layer now read and write a concrete v1 document; adopters and tooling need a single normative definition that stays aligned with the implementation.

## Decision

The **canonical** definition of admin-managed `config.yaml` **v1** is:

- [SPEC.md](../normative/admin-install/v1/adr-0011-org-config-yaml/SPEC.md) (normative prose), and
- [config.schema.json](../normative/admin-install/v1/adr-0011-org-config-yaml/config.schema.json) (Draft 7 JSON Schema for structure; semantic constraints in the SPEC prevail if they differ).

Implementations that claim `config.yaml` v1 compatibility MUST conform to that SPEC for fields and validation rules it defines. Future versions SHOULD introduce a new `version` value and companion normative artifacts.

## Consequences

- Org configuration in `.fullsend` can be validated, reviewed, and generated against a stable, published contract.
- The admin CLI and other tools can share one reference for field names, types, and allowed enumeration values.
- Broader `.fullsend` layout (other files, inheritance, guardrails) remains governed by ADR 0003 and is not specified here.
- Changes to v1 require updating the normative SPEC/schema and, when behavior changes, follow-up design or ADR work.
