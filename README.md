# Containers
[![DockerPulls](https://img.shields.io/docker/pulls/_/eclipse-temurin?label=Docker%20Pulls)](https://hub.docker.com/_/eclipse-temurin)
[![Docker Stars](https://img.shields.io/docker/stars/_/eclipse-temurin?label=Docker%20Stars)](https://hub.docker.com/r/_/eclipse-temurin)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/adoptium/containers/badge)](https://api.securityscorecards.dev/projects/github.com/adoptium/containers)

This repository contains the Dockerfiles for the official [Adoptium](https://adoptium.net) images of the Eclipse Temurin distribution (OpenJDK). These images are made available in Docker Hub.

If you are looking for the usage README then please head to the [Official Docker Hub Documentation](https://hub.docker.com/_/eclipse-temurin).

## Supported Images

In general, we support Alpine, UBI, Ubuntu and Windows containers.

[List of Supported Images By Tag](https://github.com/docker-library/docs/tree/master/eclipse-temurin#simple-tags)

We maintain images for all LTS Java releases and the latest feature release.
Older non-LTS releases are EOL and are removed from this repository and future
Docker Hub manifests.

## Update Policy

As these are official Docker Hub images, Docker Inc maintains the base image
and so any critical CVEs in the base O/S layer gets updated by them in short
order.

Note that the eclipse-temurin images include `openssl` as a prerequisite of
the `wget` and `ca-certificates` packages but they are NOT included in the
Ubuntu base image so updates to openssl will not necessarily trigger an
rebuild to pick up fixes.  In general, low severity vulnerabilities can wait
until the next rebuild.  See
[this comment](https://github.com/docker-library/official-images/issues/16225#issuecomment-1942193224)
for some details and also the
[docker-library FAQ](https://github.com/docker-library/faq/tree/master?tab=readme-ov-file#image-building).

The Debian and Ubuntu images are generally also built periodically (about
once a month) and may also be triggered by dockerhub if another high
security vulnerability is detected, such as in openssl.  Adoptium has no
mechanism - other than putting an update to the Dockerfiles - to explicitly
trigger a rebuild at dockerhub.

For JDK version updates, we update the dockerfiles and release on a
quarterly cadence Temurin releases a Patch Set Update (PSU).

## Maintenance of Dockerfiles

This section is for maintainers of the containers repository.

### Hourly automated Job

A [Updater GitHub Action](.github/workflows/updater.yml) runs every 30 mins which triggers the
[`./generate_dockerfiles.py`](./generate_dockerfiles.py) script to update the Dockerfiles by creating a Pull Request containing any changes. It uses the jinja templates defined in [docker_templates](./docker_templates/) to generate the docker updates. It uses the Adoptium API to fetch the latest artefacts for each release.

#### Manual Release

Generally this is not necessary but during a release you can also trigger the above process by running [`./generate_dockerfiles.py`](./generate_dockerfiles.py) manually by heading to The [GitHub Action definition](https://github.com/adoptium/containers/actions/workflows/updater.yml) and clicking the **Run Workflow** button and making sure the `main` (default) branch is selected, then click the next **Run Workflow** button.

### Review and Merge PR

Once the PR from the hourly automated job is created you should review it (which itself tests all of the Docker Images that we have generate configuration for).

## Update Official Docker Hub Manifest

Once you've merged the PR, you can update the official Docker Hub manifest. This is done by running the following command in the containers repo on your local machine:

```bash
# Get the latest changes
git fetch --all
# Checkout the main branch
git checkout main
python3 dockerhub_doc_config_update.py
```

This script will create a file called _eclipse-temurin_ by default.

At the end it prints a publication-readiness summary for each Java version,
checking JDK and JRE images against the configured architectures (including
version-specific overrides). Missing Dockerfiles, missing architectures, pending
upstream binary branches, and images still on an older release are reported as
blockers. Deprecated and explicitly excluded configurations are not required.
Release consistency is checked against the newest Java version found in the
local Dockerfiles for that major version, not against live release assets.

The summary is an aligned table of Java releases, readiness status, and complete
image counts, followed by a table of grouped blockers and affected images.
`READY` means that Java version has an update relative to the official upstream
manifest and all its images are complete. `UP TO DATE` means the same releases
are already published; a different Git commit alone is not a new Java release.
New distro entries also count as updates. `UNKNOWN` means the upstream manifest
could not be fetched, so publication readiness cannot be confirmed.
Open `eclipse-temurin` PRs in `docker-library/official-images` are checked for
added manifest tags matching the exact release, rather than just a Java major
version in the PR title. Matching updates show `PR OPEN`, with the PR number and
link, and are not suggested for another PR. A failed GitHub lookup is reported
explicitly and makes otherwise-ready updates `UNKNOWN`. `GH_TOKEN` or
`GITHUB_TOKEN` can be used for authenticated GitHub API requests. If neither is
set, the script automatically uses your existing GitHub CLI login (`gh auth
login`). Without either form of authentication, requests remain anonymous and
may hit GitHub's lower rate limit; a failed PR lookup still blocks publication.
Long cells wrap so the tables stay readable in terminal output.
The report is written to stderr, keeping stdout clean for tools that request the
manifest via `python3 dockerhub_doc_config_update.py /dev/stdout`.

The report also warns about deprecated, removed, or version-excluded images that
still exist in the upstream official manifest, grouped by Java version and distro.
This includes distros removed entirely from the local configuration, such as
Alpine 3.21. Required images with missing Dockerfiles or other blockers are not
mistaken for deprecated entries. These warnings do not change release readiness.
The PR creator can remove the retired entries independently, even when the Java
release is `UP TO DATE` or `BLOCKED`.

Publish each `READY` Java version independently: every required image and
architecture for that version must be available at the same release, but other
Java versions need not be ready. The report is advisory; the script still writes
the full manifest, including pending architecture entries. Select only the ready
versions for release updates, leaving other upstream entries unchanged except
for explicitly retired image cleanup.

### Optional upstream PR creation

To open one PR for **all unpublished `READY` Java versions and retired image cleanup**:

```bash
python3 dockerhub_doc_config_update.py --create-pr
```

No version selection is needed. `BLOCKED`, `UNKNOWN`, `UP TO DATE`, and `PR OPEN`
versions are excluded from release updates. If Java 17 is the only unpublished
ready version, the PR updates only Java 17's releases, but can also remove retired
entries for other Java versions. If no releases are `READY`, retired upstream
entries still result in a **cleanup-only PR**. Active entries retain their exact
upstream content, regardless of local release or architecture blockers.
Cleanup already covered by an open upstream PR is reported with its link and
excluded. If neither release updates nor uncovered cleanup remain, no PR is opened.
Without the flag, the script only generates the manifest and reports readiness
and cleanup, including when its output is `/dev/stdout`.

Preview the same PR without making changes:

```bash
python3 dockerhub_doc_config_update.py --dry-run
# Equivalent:
python3 dockerhub_doc_config_update.py --create-pr --dry-run
```

Dry runs show the proposed title, branch, and manifest diff on stderr. They do
not write the local manifest, clone a repository, create a fork, push, or open
a PR. They verify publication sources using read-only Git and GitHub API
requests and do not require the GitHub CLI when an API token is provided.

PR creation requires Git and an authenticated GitHub CLI (`gh auth login`).
You can run the script from a feature branch, including one with changes to
the script, tests, or documentation. The distribution configuration and every
selected Dockerfile and entrypoint must exactly match published
`adoptium/containers` `main`; unmerged image or configuration changes are
rejected. Cleanup-only PRs also require the configuration to match published
`main`, but do not require changes to unselected images to be merged.
Publication entries use that published commit, never the tooling
branch's unmerged commit. The script clones Official Images into a temporary directory, creates or reuses
your fork, and opens one PR containing the selected versions' JDK/JRE
entries and retired-entry removals. All other unready or already-published
upstream entries and global manifest metadata are preserved.
Your current checkout is not used for the publication branch.

Immediately before creating the branch, the script checks again for matching
open publication or cleanup PRs and refuses if the upstream manifest changed. Shared-tag
conflicts with unselected versions (such as moving `latest` from another Java
version) also stop publication rather than changing unrelated entries.
Command failures are reported and return a nonzero exit status; if pushing
succeeds but opening the PR fails, the publication branch remains in your fork.
The generated full local manifest is still advisory and must not be submitted
wholesale while other versions are unready.

### Manual upstream PR creation

Alternatively, replace the [Manifest on Docker Hub](https://github.com/docker-library/official-images/blob/master/library/eclipse-temurin) with only the selected ready versions updated. This can be done using a fork of the code or via the GitHub UI as follows:

- Go to https://github.com/docker-library/official-images/blob/master/library/eclipse-temurin web UI 
- Click **edit(pencil button)** 
- Remove its content
- Copy-paste the manifest with only the ready versions replaced from _eclipse-temurin_, preserving all other upstream entries except explicitly retired image removals
- At the bottom of that edit screen' Propose changes section
  - add **title** e.g [eclipse-temurin: XXXXX]
  - add **description** for the commit 
  - click  **Propose Change** button.

In the next screen click on the **Create Pull Request** button.

Once that PR has been created it will be automatically tested and reviewed by Docker Hub staff and eventually released.

### Diff Output at Docker Hub

It can be useful to look at the "Diff for XXX:" output created by one of the Docker Hub GitHub Actions on the Pull Request. This output
should not be read as a traditional PR (since Docker Hub bots do move things around, so you may see what looks like odd deletions)
but as a sanity check to make sure you see the platforms/architectures that you expect.

## Release time process

During a release, when linux and windows binaries are published to github, there is an ["hourly" automated containers CI](#hourly-automated-job) PR labeled "Update Dockerfiles", that will
generate any updates required to the Dockerfiles for these new linux and windows binaries. The containers Dockerfiles are located within this
repository under the folders \<version\>/\<jdk|jre\>/\<alpine|ubi|ubuntu|windows\>/\<os_container_version\>/Dockerfile.

It should be understood that no actual "pushing" of any information to dockerhub is done, the way it works is once all the necessary Dockerfiles have been updated for the new
releases, the remote dockerhub Manifest is updated with the information. Then dockerhub "pulls" the new container Dockerfiles and builds the new images for the updated Manifest, once
completed those new images are then available in dockerhub.

The "Release" process for updating dockerhub cannot start until all linux and windows binaries for all versions have been published, due to the Manifest setup.

### Release process:
1. Have all linux and windows binaries been published for all versions?
1. Verify that all the \<version\>/\<jdk|jre\>/\<alpine|ubi|ubuntu|windows\>/\<os_container_version\>/Dockerfile's have been updated by the auto-generated "Update Dockerfiles" PRs. Check there are not any left requiring "approval" to merge?
1. Create and publish the dockerhub Manifest update PR following the instructions: [Update Official Docker Hub Manifest](#update-official-docker-hub-nanifest)
