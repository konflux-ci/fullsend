# 46. Build a common Task Runner image

Date: 2024-11-15

## Status

Implementable

## Context

Tekton Tasks often depend on specific CLI tools.
The tools come from a restricted set of container images
(see `allowed_step_image_registry_prefixes` in the [policy data][rule-data]).

### The current mess of Task containers

If no image containing a required CLI tool already exists, the current approach
is to build a new image specifically for that one tool. Or to add the tool to
one or more of the existing images, if Task authors find that more convenient.
Examples:

* [yq-container]
* [oras-container]
  (also includes `yq` and a copy of one script from [build-trusted-artifacts])
* [git-clone container][git-clone]
  (for the `git-init` tool, also includes `find`)
* [buildah-container]
  (also includes a wild variety of tools such as
  `dockerfile-json`, `rsync`, `kubectl`, `jq`, `subscription-manager` and others)

Then, we have some use-case-oriented containers which are somewhat intertwined
with the tool-oriented containers (or at least share software, sometimes installed
using different approaches).

* [build-trusted-artifacts]
  (a set of Trusted Artifacts scripts, also includes `oras` and `jq`)
* [source-container-build]
  (script for building source containers, also includes `skopeo` and `jq`)

And last, some Tasks use the [appstudio-utils] image, which contains a variety
of tools installed straight from GitHub releases. Many of which are also available
in the tool-oriented containers (and installed via more legitimate means).

The current situation increases confusion, maintenance burden (both for the container
maintainers and for [build-definitions] maintainers) and, in case of `appstudio-utils`,
breaks good secure supply chain practices.

### Splitting Tasks into steps

The set of CLI tools you need may already be containerized, but in two or more separate
containers. In that case, rather than adding the tools you need to one of the containers,
the better solution could be to take advantage of Tekton Tasks' `steps` feature (each
step can use a different container image).

*Could* be, but isn't. In practice, what this achieves is:

* Increased complexity of the Task code, since it typically requires splitting the
  code in unnatural ways and sharing some data between Task steps. Inexperienced
  Tekton users may not even think of this approach or know how to achieve it.
* Increased compute resource requirements for the Task. The total resource requirements
  for a Task are not the *maximum* of its steps' resource requirements, they are
  the *sum* (see [Compute Resources in Tekton][compute-resources-in-tekton]).
* Reduced size limit of the results that the task can return (unless the Tekton
  installation enables [Results from sidecar logs][results-from-sidecar-logs]).

### Konflux users and custom Tasks

The Enterprise Contract team has developed the Trusted Artifacts concept to enable
Konflux users to add custom Tasks to the pipelines without compromising the
trustworthiness of the build.

But Konflux users face the same difficulties described above (made worse by the
fact that they don't tend to have much Tekton experience). The initial hurdle of
finding/building the right container image for what they want to do may be too high.

## Decision

Build and maintain a common "Task Runner" image.

The image must:

* Include all the tools commonly needed by Konflux build tasks.
* Build and release via Konflux, hermetically if possible.
* Document the list of installed tools and their versions, similar to how GitHub
  documents the [software installed in their runner images][github-runner-software].
  * The list of tools is a public interface, both Konflux devs and Konflux users
    can depend on it.
* Use proper semver versioning. The deletion of a tool, or a change in the major
  version of a tool, is a breaking change and must result in a major version change
  for the Task Runner image.

Gradually deprecate all the current tool-oriented container images and replace
their usage with the common Task Runner image.

The Task Runner image does not replace the more specialized use-case-oriented images,
but they can use it as a base image if desirable.

To include a tool in the Task Runner image, it should meet these requirements:

* Be an actual standalone tool (e.g. not a haphazard collection of Bash/Python scripts)
* Follow a versioning scheme (ideally semver)
  * Have release notes or a changelog
* And naturally, convince the Task Runner maintainers of its suitability for inclusion

## Consequences

The maintenance of container images needed for Tasks becomes more consolidated.
The total number of rebuilds needed due to CVEs stays the same but is not scattered
across tool-container repos anymore.

Tasks get easier to write because all the tools you need are available in the same
image. For both Konflux devs and Konflux users.

Tasks have lower resource requirements because there's less of a need to split
them into steps.

The Task Runner image is larger than any of the individual images used by the Tasks
at present. But it's much smaller than all the individual images combined. And
because Tasks don't pull the image if it's already cached on the compute node,
this is a win (there's a smaller set of images to cache, less pulling to do).

By reducing the reliance on a Tekton-specific feature (steps), most Tasks become
nothing more than a bash script wrapped in some YAML. It enables a saner approach
to authoring Tasks. Write a bash script that works on your machine, wrap it in
a bunch of YAML, verify that it works, ship it. Exceptions can still exist where
necessary/justified. For example, the Trusted Artifacts variants of Tasks would
still use separate steps to create/use the artifacts.

<!-- links table -->
[rule-data]: https://github.com/release-engineering/rhtap-ec-policy/blob/main/data/rule_data.yml
[git-clone]: https://github.com/konflux-ci/git-clone/tree/main/Dockerfile
[yq-container]: https://github.com/konflux-ci/yq-container/tree/main/Containerfile
[oras-container]: https://github.com/konflux-ci/oras-container/tree/main/Containerfile
[buildah-container]: https://github.com/konflux-ci/buildah-container/tree/main/Containerfile.task
[build-trusted-artifacts]: https://github.com/konflux-ci/build-trusted-artifacts/tree/main/Containerfile
[source-container-build]: https://github.com/konflux-ci/build-tasks-dockerfiles/blob/main/source-container-build/Dockerfile
[appstudio-utils]: https://github.com/konflux-ci/build-definitions/blob/main/appstudio-utils/Dockerfile
[build-definitions]: https://github.com/konflux-ci/build-definitions
[results-from-sidecar-logs]: https://tekton.dev/docs/pipelines/tasks/#larger-results-using-sidecar-logs
[compute-resources-in-tekton]: https://tekton.dev/docs/pipelines/compute-resources/
[github-runner-software]: https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md
