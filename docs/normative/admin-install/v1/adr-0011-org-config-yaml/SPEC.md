# Org `config.yaml` v1 (admin install)

This specification defines the **v1** YAML document stored as `config.yaml` in the organization’s `.fullsend` configuration repository. Repository location and purpose follow [ADR 0003: Org-level configuration lives in a conventional repo](../../../../ADRs/0003-org-config-repo-convention.md).

This document describes **data shape and validation rules** only. It does not define install workflows, enrollment, or secret handling.

## Normative references

- **JSON Schema:** [config.schema.json](config.schema.json) (Draft 7). Where this prose and the schema disagree, this SPEC is authoritative; the schema is a machine-readable projection.

## File

| Item | Value |
|------|--------|
| Repository | `<org>/.fullsend` (conventional name; see ADR 0003) |
| Path in repo | `config.yaml` |
| Format | YAML 1.x (UTF-8) |

## Document model

The root mapping MUST contain the keys below. Omitted keys are interpreted as type-appropriate zero values (empty sequences, `false`, empty mappings) when parsed by a conforming implementation.

### `version` (string, required)

Schema version of this document. For this SPEC, the value MUST be exactly `1`.

### `dispatch` (mapping, required)

#### `dispatch.platform` (string, required)

Dispatch backend for agent work. The only defined value in v1 is `github-actions`.

### `defaults` (mapping, required)

Organization-wide defaults applied to repositories unless overridden elsewhere in this file.

#### `defaults.roles` (sequence of strings, required)

Ordered list of agent **roles** enabled by default for the org. Each element MUST be one of:

`fullsend`, `triage`, `coder`, `review`

#### `defaults.max_implementation_retries` (integer, required)

Non-negative integer cap on implementation retries for agent workflows.

#### `defaults.auto_merge` (boolean, required)

Whether automatic merge is enabled by default for applicable automation (v1 uses a single boolean; semantics of merge are defined by the dispatch implementation, not by this file).

### `agents` (sequence of mappings, required)

Each element describes one GitHub App (or equivalent) identity for a **role**:

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `role` | string | yes | One of the same role literals as in `defaults.roles` |
| `name` | string | yes | Human-oriented label |
| `slug` | string | yes | Forge application slug (e.g. GitHub App slug) |

The v1 reference implementation does not require unique `role` or `slug` values; duplicates MAY be rejected by future specs or by tooling.

### `repos` (mapping, required)

Keys are **repository names** (short name within the org, not `owner/name`). Values are **repo entries**.

#### Repo entry (mapping)

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `enabled` | boolean | yes | When `true`, the repo participates in fullsend for this org |
| `roles` | sequence of strings | no | Per-repo role override; elements use the same role literals as `defaults.roles`. Omitted means “use defaults” in the reference implementation |

## Serialization (informative)

The reference `fullsend` CLI may prepend a fixed comment header before the YAML body (project URL and “managed by fullsend” notice). That header is **not** part of the data model; parsers MUST accept documents with or without it.

## Validation summary (normative)

A document is **valid v1** if and only if:

1. It parses as YAML into the structure above.
2. `version` is `1`.
3. `dispatch.platform` is `github-actions`.
4. `defaults.max_implementation_retries` ≥ 0.
5. Every entry in `defaults.roles` is one of the four defined role literals.

Per-repo `roles`, when present, are not checked by the v1 reference validator; tooling SHOULD still restrict values to the same role literals for consistency.

## Extensibility

Keys not listed in this SPEC MAY appear in a file; a strictly conforming v1 parser MAY ignore them or reject them. Forward evolution SHOULD bump `version`.
