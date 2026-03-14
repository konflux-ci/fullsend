# Expected Analysis: modelcar-oci-ta vs ADR-0046

## ADR-0046 requirement

All Tekton task steps should use the common task runner image
(`quay.io/konflux-ci/task-runner`) unless they have a legitimate exemption.
The ADR explicitly carves out an exception for use-case-oriented images
like build-trusted-artifacts.

## Step-by-step analysis

### use-trusted-artifact — EXEMPT

Image: `quay.io/konflux-ci/build-trusted-artifacts`

ADR-0046 states: "The Task Runner image does not replace the more specialized
use-case-oriented images." The build-trusted-artifacts image is a use-case-oriented
image (Trusted Artifacts), not a tool-oriented one. Additionally, the ADR notes
that "Trusted Artifacts variants of Tasks would still use separate steps to
create/use the artifacts." This step is legitimately exempt.

### download-model-files — VIOLATION

Image: `quay.io/konflux-ci/oras`

This step uses the oras tool-oriented container image. ADR-0046 calls for
gradually deprecating "all the current tool-oriented container images" in
favor of the task runner. The step uses `oras` and `retry`, both of which
are available in the task runner image.

**Fix:** Replace the image reference with the task runner image. No other
changes needed — `oras` and `retry` are already installed.

### create-modelcar-base-image — VIOLATION

Image: `quay.io/konflux-ci/release-service-utils`

This step uses `get-image-architectures`, `oras`, and `jq`. While `oras`
and `jq` are in the task runner, `get-image-architectures` is not.

**Fix:** The `get-image-architectures` tool needs to be added to the task
runner image first. Once added, replace the image reference with the task
runner image.

### copy-model-files — VIOLATION

Image: `registry.access.redhat.com/ubi9/python-311`

This step uses `python3` and `pip install olot`. The task runner has `python3`
but `olot` is a Python package installed at runtime via pip, not a standalone
tool baked into any image.

**Fix:** This is a gray area. `olot` is installed via `pip` at runtime, so
swapping to the task runner image would work if `pip` is available. However,
`olot` may not meet the ADR's inclusion criteria for the task runner ("be an
actual standalone tool", "follow a versioning scheme") since it's a Python
library. The image swap may be possible without adding `olot` to the task
runner — just use the task runner's `python3` and keep the `pip install`
in the script. Alternatively, if `olot` qualifies as a tool, propose adding
it to the task runner.

### push-image — VIOLATION

Image: `quay.io/konflux-ci/oras`

Same as download-model-files. Uses `oras`, `select-oci-auth`, and `retry`,
all available in the task runner.

**Fix:** Replace the image reference with the task runner image. No other
changes needed.

### sbom-generate — VIOLATION

Image: `quay.io/konflux-ci/mobster`

This step uses `mobster`, which is not in the task runner image.

**Fix:** `mobster` needs to be added to the task runner image first. It
appears to meet the ADR's inclusion criteria (standalone tool with versioned
releases). Once added, replace the image reference.

### upload-sbom — VIOLATION

Image: `quay.io/konflux-ci/appstudio-utils`

This step uses `cosign`, `select-oci-auth`, and `retry`, all available in
the task runner. ADR-0046 specifically calls out `appstudio-utils` as
problematic ("breaks good secure supply chain practices").

**Fix:** Replace the image reference with the task runner image. No other
changes needed.

### report-sbom-url — VIOLATION

Image: `quay.io/konflux-ci/yq`

This step uses the yq tool-oriented container image, but the script itself
only uses basic shell utilities (`sha256sum`, `awk`, bash string manipulation)
— it does not actually invoke the `yq` binary. All tools used are available
in the task runner.

**Fix:** Replace the image reference with the task runner image. No other
changes needed — the step doesn't even use `yq`.

## Summary

- 1 step exempt (use-trusted-artifact)
- 7 steps in violation
- 4 violations fixable today by swapping the image (download-model-files, push-image, upload-sbom, report-sbom-url)
- 2 violations require adding tools to the task runner first (create-modelcar-base-image needs `get-image-architectures`, sbom-generate needs `mobster`)
- 1 violation is a gray area (copy-model-files — may work with a simple image swap if pip is available, or may need `olot` added)
