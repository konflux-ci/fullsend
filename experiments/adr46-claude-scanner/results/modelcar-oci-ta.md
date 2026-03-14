## ADR-46 Compliance Analysis: `modelcar-oci-ta`

### Exempt Step

**`use-trusted-artifact`** (`build-trusted-artifacts`) — The ADR explicitly carves out an exception: *"the Trusted Artifacts variants of Tasks would still use separate steps to create/use the artifacts."* This step is legitimate.

---

### Violations

**1. `download-model-files` and `push-image`** — `quay.io/konflux-ci/oras:latest`

- **What:** Both steps use the `oras-container` image, and it appears *twice* in the same task.
- **Why:** `oras-container` is explicitly named in the ADR as one of the problem images to consolidate away from. Using it twice compounds the issue the ADR identifies: resource requirements for a Task are the *sum* of all steps, not the maximum. Two separate oras steps means paying that cost twice.
- **Fix:** Migrate both steps to the Task Runner image. Since both steps are pulling/pushing, they could potentially be collapsed or at minimum share the same image. The oras tool should be included in the Task Runner image.

**2. `create-modelcar-base-image`** — `quay.io/konflux-ci/release-service-utils`

- **What:** Uses `release-service-utils` for tools like `get-image-architectures` and `oras copy`.
- **Why:** This is another ad-hoc tool image of the kind the ADR wants to consolidate. It has oras bundled into it alongside other utilities — exactly the mixed-tool-image pattern the ADR criticizes. The ADR's goal is that "all the tools you need are available in the same image" — the Task Runner image.
- **Fix:** Migrate to the Task Runner image, assuming `get-image-architectures` and `oras` are included in it (oras already warrants inclusion given steps 1 and 5 also need it).

**3. `copy-model-files`** — `registry.access.redhat.com/ubi9/python-311` with `pip install olot` at runtime

- **What:** Uses a bare UBI Python base image and installs `olot` via `pip install` at runtime during the build.
- **Why:** This is the most significant violation. Runtime `pip install` breaks hermetic builds — one of the ADR's explicit requirements (*"Build and release via Konflux, hermetically if possible"*). The tool version is pinned in an environment variable (`OLOT_VERSION: 0.1.14`) rather than baked into an image, which means the tool is fetched from PyPI at task execution time. This also sidesteps the `allowed_step_image_registry_prefixes` policy the ADR references, since the effective tooling doesn't come from the step image at all.
- **Fix:** Either add `olot` to the Task Runner image (if it meets the ADR's inclusion criteria: standalone tool, versioned, has release notes), or build a dedicated `olot` image through Konflux. The runtime `pip install` must go.

**4. `upload-sbom`** — `quay.io/konflux-ci/appstudio-utils`

- **What:** Uses `appstudio-utils` for `cosign` and `select-oci-auth`.
- **Why:** The ADR *specifically* singles out `appstudio-utils` by name: *"some Tasks use the [appstudio-utils] image, which contains a variety of tools installed straight from GitHub releases… breaks good secure supply chain practices."* This is the poster child for what the ADR is fixing.
- **Fix:** Migrate to the Task Runner image. `cosign` and `select-oci-auth` are common enough to warrant inclusion.

**5. `report-sbom-url`** — `quay.io/konflux-ci/yq:latest`

- **What:** Uses the `yq-container` image just to run a small shell script that calls `sha256sum` and `awk`. `yq` itself isn't even invoked.
- **Why:** `yq-container` is explicitly named in the ADR as a problem image to deprecate. This step also illustrates the ADR's point that tool-container proliferation leads to confusion — the step uses the `yq` image but doesn't use `yq`.
- **Fix:** Migrate to the Task Runner image. The script uses only standard shell utilities, so any reasonable base suffices.

---

### Gray Area

**`sbom-generate`** — `quay.io/konflux-ci/mobster`

Mobster is a specialized SBOM-generation tool. The ADR distinguishes between tool-oriented images (to be deprecated) and "use-case-oriented images" (which *"can use [the Task Runner] as a base image if desirable"* but aren't required to merge in). SBOM generation is use-case-specific enough that keeping it as a separate image is defensible — though using the Task Runner as its base image would be consistent with the ADR's intent.

---

### Summary Table

| Step | Image | Verdict |
|---|---|---|
| `use-trusted-artifact` | `build-trusted-artifacts` | **Exempt** (ADR explicit exception) |
| `download-model-files` | `oras-container` | **Violation** (named problem image, duplicated) |
| `create-modelcar-base-image` | `release-service-utils` | **Violation** (ad-hoc tool image) |
| `copy-model-files` | `ubi9/python-311` + runtime pip | **Violation** (breaks hermetic build requirement) |
| `push-image` | `oras-container` | **Violation** (named problem image, duplicated) |
| `sbom-generate` | `mobster` | **Gray area** (use-case-oriented, arguably exempt) |
| `upload-sbom` | `appstudio-utils` | **Violation** (explicitly called out in ADR) |
| `report-sbom-url` | `yq-container` | **Violation** (named problem image; doesn't even use yq) |
