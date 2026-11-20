#!/usr/bin/env python3
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Script that generates the `eclipse-temurin` config file for the official docker
# image github repo and the doc updates for the unofficial docker image repo.
# Process to update the official docker image repo
# 1. Run generate_dockerfiles.py to update all the dockerfiles in the current repo.
# 2. Submit PR to push the newly generated dockerfiles to the current repo.
# 3. After above PR is merged, git pull the latest changes.
# 4. Run this command

import argparse
import base64
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import urllib.request
from urllib.parse import urlencode
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from adoptium_api import get_latest_lts, get_supported_versions
from architecture_config import resolve_architectures
from eol_checker import print_eol_warnings

OFFICIAL_MANIFEST_URL = (
    "https://raw.githubusercontent.com/docker-library/official-images/"
    "master/library/eclipse-temurin"
)
OFFICIAL_IMAGES_API = "https://api.github.com/repos/docker-library/official-images"


def load_config():
    with open("config/temurin.yml", "r") as f:
        return yaml.safe_load(f)


def get_git_commit():
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def fetch_official_manifest():
    """Fetch the current official manifest for diff comparison."""
    try:
        req = urllib.request.Request(OFFICIAL_MANIFEST_URL)
        with urllib.request.urlopen(req) as response:
            return response.read().decode("utf-8")
    except (OSError, UnicodeError) as error:
        print(f"Warning: cannot compare with the official manifest: {error}", file=sys.stderr)
        return None


@dataclass
class PublicationPR:
    url: str
    releases: set[str]
    removed_directories: set[str] = field(default_factory=set)
    updated_directories: set[str] = field(default_factory=set)


@dataclass
class PublicationPRHead:
    repository: str
    branch: str
    sha: str
    manifest: str


@dataclass
class PublicationPRUpdate:
    """Binaries that became available after an open publication PR was created."""
    pr: PublicationPR
    head: PublicationPRHead
    releases: dict[int, str]
    added_architectures: dict[int, list[str]]
    directories: dict[int, set[str]]
    deferred_architectures: dict[int, list[str]] = field(default_factory=dict)
    held_back_directories: dict[int, set[str]] = field(default_factory=dict)


@dataclass
class PublicationPlan:
    upstream_manifest: str | None
    manifest: str
    ready_releases: dict[int, str]
    open_prs_available: bool = True
    cleanup_directories: set[str] = field(default_factory=set)
    added_architectures: dict[int, list[str]] = field(default_factory=dict)
    deferred_architectures: dict[int, list[str]] = field(default_factory=dict)
    follow_up_directories: dict[int, set[str]] = field(default_factory=dict)
    held_back_directories: dict[int, set[str]] = field(default_factory=dict)
    pr_updates: list[PublicationPRUpdate] = field(default_factory=list)


def get_github_token() -> str | None:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    if not shutil.which("gh"):
        return None
    result = subprocess.run(
        ["gh", "auth", "token", "--hostname", "github.com"],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    print(
        "Warning: GitHub CLI authentication unavailable; API requests are unauthenticated. "
        "Run 'gh auth login' or set GH_TOKEN to avoid rate limits.",
        file=sys.stderr,
    )
    return None


def github_request(url):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Adoptium Dockerfile Updater"}
    token = get_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def github_pages(url, items_key=None):
    page = 1
    while True:
        separator = "&" if "?" in url else "?"
        data = github_request(f"{url}{separator}per_page=100&page={page}")
        if items_key and data.get("incomplete_results"):
            raise ValueError("GitHub returned incomplete PR search results")
        items = data[items_key] if items_key else data
        yield from items
        if len(items) < 100:
            break
        page += 1


def fetch_open_publication_prs():
    """Match upstream PRs by release tags, changed commits, and removed directories."""
    query = urlencode({
        "q": "repo:docker-library/official-images is:pr is:open eclipse-temurin in:title,body",
    })
    try:
        prs = []
        for issue in github_pages(f"https://api.github.com/search/issues?{query}", "items"):
            releases = set()
            removed_directories = set()
            added_directories = set()
            updated_directories = set()
            for change in github_pages(f"{OFFICIAL_IMAGES_API}/pulls/{issue['number']}/files"):
                if change["filename"] != "library/eclipse-temurin":
                    continue
                if "patch" not in change:
                    raise ValueError(f"GitHub omitted the manifest diff for {issue['html_url']}")
                changed_commit = False
                changed_tags = False
                for line in change["patch"].splitlines():
                    if line.startswith(("@@", " Tags: ")):
                        if changed_commit and not changed_tags:
                            raise ValueError(f"GitHub omitted the directory for a changed commit in {issue['html_url']}")
                        changed_commit = False
                        changed_tags = False
                    elif line.startswith("+Tags: "):
                        changed_tags = True
                        tag = line.removeprefix("+Tags: ").split(", ", 1)[0]
                        match = re.match(r"^(.+?)-(?:jdk|jre)-", tag)
                        if match:
                            releases.add(match.group(1))
                    elif line.startswith("-Tags: "):
                        changed_tags = True
                    elif line.startswith("+GitCommit: "):
                        changed_commit = True
                    elif line.startswith("-Directory: "):
                        removed_directories.add(line.removeprefix("-Directory: "))
                    elif line.startswith((" Directory: ", "+Directory: ")):
                        directory = line.split(": ", 1)[1]
                        if line.startswith("+"):
                            added_directories.add(directory)
                        if changed_commit and not changed_tags:
                            updated_directories.add(directory)
                        changed_commit = False
                        changed_tags = False
                if changed_commit and not changed_tags:
                    raise ValueError(f"GitHub omitted the directory for a changed commit in {issue['html_url']}")
            removed_directories -= added_directories
            if releases or removed_directories or updated_directories:
                prs.append(PublicationPR(
                    issue["html_url"], releases, removed_directories, updated_directories,
                ))
        return prs
    except (OSError, ValueError) as error:
        print(f"Warning: cannot check open upstream publication PRs: {error}", file=sys.stderr)
        return None


def fetch_publication_pr_head(pr):
    """Fetch the head branch and manifest of an open upstream publication PR."""
    number = pr.url.rstrip("/").rsplit("/", 1)[-1]
    try:
        head = github_request(f"{OFFICIAL_IMAGES_API}/pulls/{number}")["head"]
        repository = head["repo"]["full_name"]
        content = github_request(
            f"https://api.github.com/repos/{repository}/contents/library/eclipse-temurin?ref={head['sha']}"
        )
        if content.get("encoding") != "base64":
            raise ValueError("GitHub did not return the PR manifest content")
        manifest = base64.b64decode(content["content"]).decode("utf-8")
        return PublicationPRHead(repository, head["ref"], head["sha"], manifest)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Warning: cannot read the head of open upstream PR {pr.url}: {error}", file=sys.stderr)
        return None


def get_java_version(dockerfile_path):
    """Extract JAVA_VERSION from a Dockerfile."""
    with open(dockerfile_path, "r") as f:
        for line in f:
            if "JAVA_VERSION=" in line:
                return line.split("=")[1].strip()
    return None


def format_ojdk_version(full_version):
    """Convert JAVA_VERSION to Docker tag-compatible version string.

    Examples:
        jdk8u482-b08 -> 8u482-b08
        jdk-25.0.1+9 -> 25.0.1_9
    """
    version = re.sub(r"^jdk-?", "", full_version)
    version = version.replace("+", "_")
    return version


def get_distro_name(os_family, directory):
    """Derive the distro tag name from the config directory."""
    name = directory.split("/")[-1]
    if os_family == "alpine-linux":
        return f"alpine-{name}"
    return name


# Map Dockerfile arch names to Docker Hub official image architecture names
DOCKERFILE_ARCH_MAP = {
    "x64": "amd64",
    "amd64": "amd64",
    "x86_64": "amd64",
    "arm64": "arm64v8",
    "aarch64": "arm64v8",
    "armhf": "arm32v7",
    "arm": "arm32v7",
    "ppc64el": "ppc64le",
    "ppc64le": "ppc64le",
    "s390x": "s390x",
    "riscv64": "riscv64",
}

DOCKERFILE_ARCH_RE = re.compile(r'\s+(\w+)\)\s*\\?\s*$')
PENDING_ARCH_MARKER = "TODO: This configured architecture is pending upstream binary availability"


def get_dockerfile_arches(dockerfile_path):
    """Parse architectures from the case statement in a Dockerfile."""
    arches = []
    with open(dockerfile_path, "r") as f:
        for line in f:
            match = DOCKERFILE_ARCH_RE.match(line)
            if match:
                arch = match.group(1)
                if arch in DOCKERFILE_ARCH_MAP:
                    arches.append(DOCKERFILE_ARCH_MAP[arch])
    return sorted(set(arches))


def parse_pending_arches(lines):
    pending = set()
    arch = None
    for line in lines:
        match = DOCKERFILE_ARCH_RE.match(line)
        if match:
            arch = DOCKERFILE_ARCH_MAP.get(match.group(1))
        elif line.strip().startswith((";;", "*)", "esac")):
            arch = None
        elif arch and PENDING_ARCH_MARKER in line:
            pending.add(arch)
    return sorted(pending)


def get_pending_arches(dockerfile_path):
    """Find architectures whose generated branches have no upstream binary yet."""
    with open(dockerfile_path) as f:
        return parse_pending_arches(f)


def read_git_file(commit, path):
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"], capture_output=True, text=True,
    )
    return result.stdout if result.returncode == 0 else None


def get_published_pending_arches(commit, dockerfile_path):
    """Find architectures that were still pending in the published upstream commit."""
    content = read_git_file(commit, dockerfile_path) if commit else None
    return parse_pending_arches(content.splitlines()) if content is not None else None


@dataclass
class ImageReadiness:
    directory: str
    java_version: str | None = None
    blockers: list[str] = field(default_factory=list)
    updated: bool = False
    published: bool = False
    held_back: bool = False
    deferred_arches: list[str] = field(default_factory=list)
    added_arches: list[str] = field(default_factory=list)
    arches: list[str] = field(default_factory=list)
    pending_arches: list[str] = field(default_factory=list)
    pr_added_arches: list[str] = field(default_factory=list)


def java_version_key(release):
    version, _, build = release.replace("-b", "+").replace("_", "+").partition("+")
    parts = tuple(int(n) for n in re.findall(r"\d+", version))
    return parts + (0,) * max(0, 4 - len(parts)), int(build or 0)


def matching_publication_prs(release, open_prs, directories=None):
    directories = directories or set()
    return [
        pr for pr in open_prs
        if directories & pr.updated_directories
        or any(java_version_key(tag) == java_version_key(release) for tag in pr.releases)
    ]


def get_entry_release(entry):
    tag = entry.get("Tags", "").split(", ", 1)[0]
    match = re.match(r"^(.+?)-(?:jdk|jre)-", tag)
    return match.group(1) if match else None


def covered_by_open_pr(images, entries, latest):
    """Check that an open PR publishes every image at the local release or keeps it held back."""
    for image in images:
        entry = entries.get(image.directory)
        release = get_entry_release(entry) if entry else None
        if not image.java_version or release is None:
            return False
        local_key = java_version_key(image.java_version)
        if local_key == java_version_key(latest):
            if java_version_key(release) != local_key:
                return False
        elif not (image.published and java_version_key(release) == local_key):
            return False
    return True


def apply_open_pr_baselines(readiness, open_prs):
    """Use open publication PRs as the baseline for binaries that were pending when they were opened."""
    candidates = {}
    for version, images in readiness.items():
        latest = max(
            (image.java_version for image in images if image.java_version),
            key=java_version_key, default=None,
        )
        if not latest or not any(image.updated for image in images):
            continue
        prs = [
            pr for pr in open_prs
            if any(java_version_key(tag) == java_version_key(latest) for tag in pr.releases)
        ]
        if len(prs) == 1:
            candidates[version] = (prs[0], latest)

    baselines = {}
    for url in {pr.url for pr, _ in candidates.values()}:
        versions = {version for version, (pr, _) in candidates.items() if pr.url == url}
        pr = candidates[next(iter(versions))][0]
        pr_versions = {int(re.match(r"\d+", tag).group()) for tag in pr.releases if re.match(r"\d+", tag)}
        # The PR description is regenerated, so every release in it must be accounted for.
        if pr_versions != versions:
            continue
        head = fetch_publication_pr_head(pr)
        if head is None:
            continue
        entries = get_manifest_entries(head.manifest)
        if not all(covered_by_open_pr(readiness[v], entries, candidates[v][1]) for v in versions):
            continue
        for version in versions:
            latest_key = java_version_key(candidates[version][1])
            for image in readiness[version]:
                if java_version_key(image.java_version) < latest_key:
                    image.held_back = True
                    continue
                if not image.arches:
                    continue
                pr_pending = get_published_pending_arches(
                    entries[image.directory].get("GitCommit"), f"{image.directory}/Dockerfile",
                )
                if pr_pending is None:
                    image.blockers.append("cannot read Dockerfile at open PR GitCommit")
                    continue
                still_pending = set(image.pending_arches) | set(image.deferred_arches)
                # Binaries already pending when the PR was opened are follow-ups, not blockers.
                carried = set(image.pending_arches) & set(pr_pending)
                image.deferred_arches = sorted(set(image.deferred_arches) | carried)
                image.pending_arches = sorted(set(image.pending_arches) - carried)
                image.pr_added_arches = sorted((set(pr_pending) & set(image.arches)) - still_pending)
                if not set(image.arches) - set(image.deferred_arches) and "no available binaries" not in image.blockers:
                    image.blockers.append("no available binaries")
            baselines[version] = (pr, head)
    return baselines


def print_table(headers, rows, max_widths):
    widths = [
        min(limit, max(len(row[index]) for row in [headers, *rows]))
        for index, limit in enumerate(max_widths)
    ]
    separator = "+-" + "-+-".join("-" * width for width in widths) + "-+"

    def print_row(row):
        cells = [textwrap.wrap(cell, width=width) or [""] for cell, width in zip(row, widths)]
        for line in range(max(len(cell) for cell in cells)):
            values = [
                (cell[line] if line < len(cell) else "").ljust(width)
                for cell, width in zip(cells, widths)
            ]
            print("| " + " | ".join(values) + " |", file=sys.stderr)

    print(separator, file=sys.stderr)
    print_row(headers)
    print(separator, file=sys.stderr)
    for row in rows:
        print_row(row)
    print(separator, file=sys.stderr)


def format_image_targets(paths):
    packages_by_distro = {}
    for path in paths:
        _, package, distro = path.split("/", 2)
        packages_by_distro.setdefault(distro, set()).add(package)
    distros_by_packages = {}
    for distro, packages in packages_by_distro.items():
        distros_by_packages.setdefault(tuple(sorted(packages)), []).append(distro)
    return "; ".join(
        f"{'+'.join(packages).upper()} {', '.join(distros)}"
        for packages, distros in distros_by_packages.items()
    )


def print_publish_summary(readiness, output_file, upstream_available, open_prs, pr_baselines=None):
    pr_baselines = pr_baselines or {}
    print("\nUpstream publish readiness (JDK + JRE, all required architectures):", file=sys.stderr)
    ready_versions = {}
    statuses = {}
    open_versions = []
    summary_rows = {}
    blocker_rows = []
    deferred_rows = []
    linked_prs = {}
    for version, images in readiness.items():
        releases = [image.java_version for image in images if image.java_version]
        latest = max(
            releases,
            key=java_version_key,
            default=None,
        )
        blocked = {}
        deferred = {}
        for image in images:
            if image.held_back:
                continue
            if image.deferred_arches:
                deferred.setdefault(", ".join(image.deferred_arches), []).append(image.directory)
            reasons = list(image.blockers)
            if image.java_version and java_version_key(image.java_version) < java_version_key(latest):
                reasons.append(f"stale release {image.java_version}; expected {latest}")
            if reasons:
                blocked.setdefault("; ".join(reasons), []).append(image.directory)

        ready = bool(images) and not blocked
        blocked_count = sum(len(paths) for paths in blocked.values())
        updated = any(image.updated for image in images)
        affected = {image.directory for image in images if image.added_arches}
        matching_prs = (
            matching_publication_prs(latest, open_prs or [], affected)
            if updated and latest else []
        )
        pr_labels = []
        for pr in matching_prs:
            label = f"#{pr.url.rsplit('/', 1)[-1]}"
            linked_prs[label] = pr.url
            pr_labels.append(label)
        if not ready:
            status = "BLOCKED"
        elif not upstream_available:
            status = "UNKNOWN"
        elif updated and open_prs is None:
            status = "UNKNOWN"
        elif matching_prs:
            if version in pr_baselines and any(
                image.pr_added_arches for image in images if not image.held_back
            ):
                status = "PR UPDATE"
            else:
                status = "PR OPEN"
        elif updated:
            status = "READY"
            ready_versions[version] = format_ojdk_version(latest)
        else:
            status = "UP TO DATE"
        statuses[version] = status
        summary_rows[version] = [
            str(version),
            format_ojdk_version(latest) if latest else "-",
            status,
            f"{len(images) - blocked_count}/{len(images)}",
            ", ".join(pr_labels) or "-",
        ]
        if not images:
            blocker_rows.append([str(version), "No configured images", "-"])
        for reasons, paths in blocked.items():
            blocker_rows.append([str(version), reasons, format_image_targets(paths)])
        for arches, paths in deferred.items():
            deferred_rows.append([str(version), arches, format_image_targets(paths)])

    update_versions = []
    for version, status in statuses.items():
        if status == "PR UPDATE":
            url = pr_baselines[version][0].url
            group = [v for v, (pr, _) in pr_baselines.items() if pr.url == url]
            # Only update a PR when every release in it can still be published.
            if any(statuses[v] not in ("PR OPEN", "PR UPDATE") for v in group):
                status = statuses[version] = summary_rows[version][2] = "PR OPEN"
        if status == "PR UPDATE":
            update_versions.append(str(version))
        elif status == "PR OPEN":
            open_versions.append(str(version))

    if readiness:
        print_table(
            ["Java", "Release", "Status", "Complete", "Upstream PR"],
            list(summary_rows.values()), [4, 18, 10, 8, 18],
        )
    else:
        print("  No supported Java versions to assess", file=sys.stderr)
    if blocker_rows:
        print("\nPublication blockers:", file=sys.stderr)
        print_table(["Java", "Blocker", "Affected images"], blocker_rows, [4, 48, 54])
    if deferred_rows:
        print("\nDeferred binaries (non-blocking; publish in a follow-up):", file=sys.stderr)
        print_table(["Java", "Architecture", "Affected images"], deferred_rows, [4, 16, 54])
    if linked_prs:
        print("\nOpen upstream PRs:", file=sys.stderr)
        for label, url in linked_prs.items():
            print(f"  {label}: {url}", file=sys.stderr)
    print(file=sys.stderr)
    if not upstream_available:
        print("Upstream comparison unavailable; publication readiness cannot be confirmed.", file=sys.stderr)
    elif open_prs is None:
        print("Open upstream PRs could not be checked; check GitHub before opening a new PR.", file=sys.stderr)
    elif ready_versions or update_versions:
        if ready_versions:
            print(
                f"Ready for upstream publish: Java {', '.join(map(str, ready_versions))}. "
                f"Publish only these versions from {output_file}; leave other upstream entries unchanged.",
                file=sys.stderr,
            )
        if update_versions:
            print(
                f"Open upstream PRs need updates: Java {', '.join(update_versions)}. "
                "Binaries pending when those PRs were opened are now available.",
                file=sys.stderr,
            )
        print(
            "To open an upstream PR for all READY versions and pending cleanup, "
            "and push newly available binaries to open PRs:\n"
            "  python3 dockerhub_doc_config_update.py --create-pr\n"
            "Preview without making changes:\n"
            "  python3 dockerhub_doc_config_update.py --dry-run",
            file=sys.stderr,
        )
    elif open_versions:
        print(
            f"Publication already in progress: Java {', '.join(open_versions)}. "
            "See the open upstream PRs above.",
            file=sys.stderr,
        )
    else:
        print("No updated Java versions are ready for upstream publish.", file=sys.stderr)
    return ready_versions, statuses


def check_forced_versions(readiness, force_versions, statuses):
    """Print the binaries still missing for forced versions and reject unpublishable ones."""
    rows = []
    for version in sorted(force_versions):
        images = readiness[version]
        release = max(
            (image.java_version for image in images if image.java_version),
            key=java_version_key, default=None,
        )
        missing = {}
        held = {}
        for image in images:
            if image.held_back:
                key = f"held at {format_ojdk_version(image.java_version)}"
                held.setdefault(key, []).append(image.directory)
                continue
            for arch in image.deferred_arches:
                missing.setdefault(arch, []).append(image.directory)
        cells = [str(version), format_ojdk_version(release) if release else "-", statuses[version]]
        if not missing and not held:
            rows.append([*cells, "none", "-"])
        for arch, paths in sorted(missing.items()) + sorted(held.items()):
            rows.append([*cells, arch, format_image_targets(paths)])
    print(
        "\nForced partial publication plan (missing binaries have pending Dockerfile case branches; "
        "their manifest architectures are retained for a follow-up. Images held at an older, "
        "already-published release keep their current upstream entries):",
        file=sys.stderr,
    )
    print_table(
        ["Java", "Release", "Status", "Missing binary", "Affected images"],
        rows, [4, 18, 10, 18, 54],
    )
    for version in sorted(force_versions):
        if statuses[version] in ("UP TO DATE", "PR OPEN"):
            print(f"Java {version} is {statuses[version]}; nothing to force-publish.", file=sys.stderr)
    unpublishable = [
        f"Java {version} is {statuses[version]}" for version in sorted(force_versions)
        if statuses[version] in ("BLOCKED", "UNKNOWN")
    ]
    if unpublishable:
        raise ValueError(
            "Cannot force-publish: " + "; ".join(unpublishable) + ". "
            "--force only defers architectures whose Dockerfile case branch is marked pending; "
            "resolve the other publication blockers reported above."
        )


def confirm_publication(prompt: str) -> bool:
    # The prompt goes to stderr so stdout stays clean for manifest output.
    print(prompt, end="", file=sys.stderr, flush=True)
    answer = sys.stdin.readline()
    if not answer:
        print(file=sys.stderr)
    return answer.strip().lower() in ("y", "yes")


def print_deprecated_upstream_images(directories):
    retired = {}
    for directory in sorted(directories, key=lambda path: (int(path.split("/", 1)[0]), path)):
        version, package, distro = directory.split("/", 2)
        retired.setdefault((version, distro), set()).add(package)
    if not retired:
        return
    print(
        "\nWarning: Deprecated or removed images still in the upstream official manifest:",
        file=sys.stderr,
    )
    rows = [
        [version, f"{'+'.join(sorted(packages)).upper()} {distro}"]
        for (version, distro), packages in retired.items()
    ]
    print_table(["Java", "Affected upstream images"], rows, [4, 80])
    print(
        "These entries can be cleaned up independently of release readiness.",
        file=sys.stderr,
    )


def get_manifest_entries(manifest):
    entries = {}
    for block in (manifest or "").split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "Directory" in fields:
            entries[fields["Directory"]] = fields
    return entries


def merge_publication_manifest(
    upstream: str, generated: str, versions: list[int],
    cleanup_directories: set[str] | None = None,
    follow_up_directories: dict[int, set[str]] | None = None,
    held_back_directories: set[str] | None = None,
) -> str:
    cleanup_directories = cleanup_directories or set()
    follow_up_directories = follow_up_directories or {}
    held_back_directories = held_back_directories or set()
    upstream_entries = get_manifest_entries(upstream)
    generated_entries = get_manifest_entries(generated)
    missing = held_back_directories - upstream_entries.keys()
    if missing:
        raise ValueError("Held-back images are absent from upstream manifest: " + ", ".join(sorted(missing)))
    upstream_blocks = {
        directory: block.strip("\n")
        for block in upstream.split("\n\n")
        for directory in get_manifest_entries(block)
    }
    missing = cleanup_directories - upstream_entries.keys()
    if missing:
        raise ValueError("Cleanup targets are absent from upstream manifest: " + ", ".join(sorted(missing)))
    active = cleanup_directories & generated_entries.keys()
    if active:
        raise ValueError("Cleanup targets still have generated manifest entries: " + ", ".join(sorted(active)))
    for version, directories in follow_up_directories.items():
        if (
            version not in versions or not directories
            or any(not directory.startswith(f"{version}/") for directory in directories)
        ):
            raise ValueError(f"Invalid follow-up directories for Java {version}")
    follow_up_targets = {directory for directories in follow_up_directories.values() for directory in directories}
    missing = follow_up_targets - upstream_entries.keys()
    if missing:
        raise ValueError("Follow-up targets are absent from upstream manifest: " + ", ".join(sorted(missing)))
    missing = follow_up_targets - generated_entries.keys()
    if missing:
        raise ValueError("Follow-up targets are absent from generated manifest: " + ", ".join(sorted(missing)))
    replacements: dict[int, list[str]] = {
        version: [] for version in versions if version not in follow_up_directories
    }
    for block in generated.split("\n\n"):
        for directory in get_manifest_entries(block):
            version = int(directory.split("/", 1)[0])
            if version in replacements:
                if directory in held_back_directories:
                    block = upstream_blocks[directory]
                replacements[version].append(block.rstrip("\n"))
    if any(not blocks for blocks in replacements.values()):
        raise ValueError("A selected Java version has no generated manifest entries")

    blocks = []
    replaced = set()
    preserved_entries = {}
    for block in upstream.split("\n\n"):
        entries = get_manifest_entries(block)
        version = int(next(iter(entries)).split("/", 1)[0]) if entries else None
        if version in replacements:
            if version not in replaced:
                blocks.extend(replacements[version])
                replaced.add(version)
        elif follow_up_targets.intersection(entries):
            directory = next(iter(entries))
            commit = generated_entries[directory].get("GitCommit")
            if not commit or not entries[directory].get("GitCommit"):
                raise ValueError(f"Follow-up target has no GitCommit: {directory}")
            block, count = re.subn(r"(?m)^GitCommit: .+$", f"GitCommit: {commit}", block)
            if count != 1:
                raise ValueError(f"Follow-up target must have exactly one GitCommit: {directory}")
            blocks.append(block)
            preserved_entries.update(entries)
        elif not cleanup_directories.intersection(entries):
            blocks.append(block)
            preserved_entries.update(entries)
    for version in replacements:
        if version not in replaced:
            blocks.extend(replacements[version])

    def tags(entries):
        return {
            tag
            for entry in entries.values()
            for field in ("Tags", "SharedTags")
            for tag in entry.get(field, "").split(", ")
            if tag
        }

    selected_entries = get_manifest_entries(
        "\n\n".join(block for version_blocks in replacements.values() for block in version_blocks)
    )
    conflicts = tags(selected_entries) & tags(preserved_entries)
    if conflicts:
        raise ValueError(
            "Selected versions would conflict with preserved upstream tags: "
            + ", ".join(sorted(conflicts))
        )
    merged = "\n\n".join(blocks)
    if follow_up_targets and not replacements and not cleanup_directories:
        return merged
    return merged.rstrip("\n") + "\n"


def run_publication_command(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, check=True,
    ).stdout.strip()


def prepare_publication_source(plan: PublicationPlan, versions=None) -> tuple[str, str]:
    versions = plan.ready_releases if versions is None else versions
    commit = github_request("https://api.github.com/repos/adoptium/containers/commits/main")
    if not isinstance(commit, dict) or not isinstance(commit.get("sha"), str) or not commit["sha"]:
        raise ValueError("GitHub did not return the published containers main commit")
    published_commit = commit["sha"]
    tree = github_request(
        f"https://api.github.com/repos/adoptium/containers/git/trees/{published_commit}?recursive=1"
    )
    if not isinstance(tree, dict) or tree.get("truncated") or not isinstance(tree.get("tree"), list):
        raise ValueError("GitHub did not return a complete published containers source tree")
    published_files = {
        entry["path"]: entry["sha"] for entry in tree["tree"] if entry.get("type") == "blob"
    }
    source_paths = {"config/temurin.yml"}
    blocks = []
    for block in plan.manifest.split("\n\n"):
        entries = get_manifest_entries(block)
        selected = [
            directory for directory in entries
            if int(directory.split("/", 1)[0]) in versions
        ]
        for directory in selected:
            source_paths.add(f"{directory}/Dockerfile")
            entrypoint = f"{directory}/entrypoint.sh"
            if entrypoint in published_files or Path(entrypoint).exists():
                source_paths.add(entrypoint)
        if selected:
            block = re.sub(r"(?m)^GitCommit: .+$", f"GitCommit: {published_commit}", block)
        blocks.append(block)

    paths = sorted(source_paths)
    for path in paths:
        if path not in published_files or not Path(path).is_file():
            raise ValueError(f"Publication source is missing or not merged upstream: {path}")
    hashes = run_publication_command("git", "hash-object", "--", *paths).splitlines()
    if len(hashes) != len(paths):
        raise ValueError("Git did not return a hash for every publication source file")
    for path, blob in zip(paths, hashes):
        if blob != published_files[path]:
            raise ValueError(
                f"Publication source differs from published upstream main: {path}. "
                "Merge image and configuration changes before publishing."
            )
    return published_commit, "\n\n".join(blocks)


def describe_publication(
    published_commit, releases, added, deferred_architectures, held_back_directories, cleanup,
    added_since_opened=None,
):
    """Build the upstream PR title and description."""
    added_since_opened = added_since_opened or {}
    title = ", ".join(
        f"{version} {release} add {', '.join(added[version])}" if version in added
        else f"{version} to {release}"
        for version, release in releases.items()
    )
    if cleanup:
        title = f"{title}; remove deprecated images" if title else "remove deprecated images"
    title = "eclipse-temurin: " + title
    body = f"Update Eclipse Temurin from adoptium/containers commit {published_commit}.\n\n"
    new_releases = {v: r for v, r in releases.items() if v not in added}
    if new_releases:
        body += "Publish READY releases:\n"
        for version, release in new_releases.items():
            deferred = deferred_architectures.get(version)
            if deferred:
                body += (
                    f"- Temurin {version}: `{release}` (JDK and JRE). {', '.join(deferred)} "
                    "binaries are not released yet, so those builds cannot install Temurin; "
                    "a follow-up PR will publish them once the binaries are available.\n"
                )
            else:
                body += f"- Temurin {version}: `{release}` (JDK and JRE, all required architectures)\n"
            held = held_back_directories.get(version)
            if held:
                body += (
                    f"  - Not yet updated to `{release}`, so these images keep their current "
                    f"upstream entries: {format_image_targets(held)}\n"
                )
            arches = added_since_opened.get(version)
            if arches:
                body += (
                    f"  - {', '.join(arches)} binaries became available after this PR was opened; "
                    "the affected entries now point at the commit that adds them.\n"
                )
        body += "\n"
    follow_ups = {v: r for v, r in releases.items() if v in added}
    if follow_ups:
        body += "Follow-up for releases already published upstream:\n" + "\n".join(
            f"- Temurin {version}: `{release}` now includes {', '.join(added[version])} binaries. "
            "They were not available when this release was first published, so the corresponding "
            "builds could not install Temurin. This PR "
            "points the affected entries at the commit that adds the binaries."
            for version, release in follow_ups.items()
        ) + "\n\n"
    if cleanup:
        body += "Remove deprecated, removed, or version-excluded image entries:\n"
        body += "\n".join(f"- `{directory}`" for directory in sorted(cleanup)) + "\n\n"
    body += "All other upstream manifest entries are preserved."
    return title, body


def update_publication_prs(plan: PublicationPlan, dry_run: bool = False, confirm=None) -> list[str]:
    """Push newly available binaries to open publication PRs and refresh their descriptions."""
    urls = []
    for update in plan.pr_updates:
        published_commit, generated = prepare_publication_source(plan, set(update.directories))
        manifest = merge_publication_manifest(
            update.head.manifest, generated, list(update.directories),
            follow_up_directories=update.directories,
        )
        if manifest == update.head.manifest:
            print(f"Upstream PR {update.pr.url} already includes the available binaries.", file=sys.stderr)
            continue
        title, body = describe_publication(
            published_commit, update.releases, {}, update.deferred_architectures,
            update.held_back_directories, update.pr.removed_directories, update.added_architectures,
        )
        message = "eclipse-temurin: " + ", ".join(
            f"{version} {update.releases[version]} add {', '.join(arches)}"
            for version, arches in update.added_architectures.items()
        )
        if dry_run or confirm:
            heading = "Dry run: would update" if dry_run else "Proposed update to"
            print(
                f"{heading} upstream PR {update.pr.url} on branch "
                f"{update.head.repository}:{update.head.branch} with commit '{message}'",
                file=sys.stderr,
            )
            print(f"PR title: {title}", file=sys.stderr)
            print(f"PR description:\n{body}\n", file=sys.stderr)
            print(
                "".join(difflib.unified_diff(
                    update.head.manifest.splitlines(keepends=True), manifest.splitlines(keepends=True),
                    fromfile="a/library/eclipse-temurin", tofile="b/library/eclipse-temurin",
                )),
                end="", file=sys.stderr,
            )
        if dry_run:
            print("Dry run only; no branches or PRs were changed.", file=sys.stderr)
            continue
        if confirm and not confirm("Push this update to the upstream PR? [y/N] "):
            print("Aborted; the upstream PR was not changed.", file=sys.stderr)
            continue
        push_publication_pr_update(update, manifest, message, title, body)
        urls.append(update.pr.url)
    return urls


def push_publication_pr_update(update: PublicationPRUpdate, manifest, message, title, body):
    url = update.pr.url
    number = url.rstrip("/").rsplit("/", 1)[-1]
    head = update.head
    login = run_publication_command("gh", "api", "user", "--jq", ".login")
    if not login:
        raise ValueError("GitHub did not return an authenticated user")
    if head.repository.split("/", 1)[0] != login:
        raise ValueError(f"Cannot push to {url}: its branch is in {head.repository}, not {login}'s fork")
    state = run_publication_command(
        "gh", "api", f"repos/docker-library/official-images/pulls/{number}",
        "--jq", '.state + " " + .head.sha',
    )
    if state != f"open {head.sha}":
        raise ValueError(f"Upstream PR {url} changed since the readiness check; rerun")
    remote = f"https://github.com/{head.repository}.git"
    with tempfile.TemporaryDirectory(prefix="temurin-publication-") as temporary:
        checkout = Path(temporary) / "official-images"
        run_publication_command(
            "git", "clone", "--depth=1", "--single-branch", "--branch", head.branch, remote, str(checkout),
        )
        manifest_file = checkout / "library" / "eclipse-temurin"
        if (
            run_publication_command("git", "rev-parse", "HEAD", cwd=checkout) != head.sha
            or manifest_file.read_text() != head.manifest
        ):
            raise ValueError(f"Upstream PR {url} changed since the readiness check; rerun")
        manifest_file.write_text(manifest)
        run_publication_command("git", "add", "--", "library/eclipse-temurin", cwd=checkout)
        run_publication_command("git", "commit", "-m", message, cwd=checkout)
        # A plain push only fast-forwards, so concurrent branch changes are never overwritten.
        run_publication_command(
            "git", "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential",
            "push", remote, f"HEAD:refs/heads/{head.branch}", cwd=checkout,
        )
    run_publication_command(
        "gh", "pr", "edit", number, "--repo", "docker-library/official-images",
        "--title", title, "--body", body,
    )
    print(f"Updated upstream publication PR: {url}", file=sys.stderr)


def create_publication_pr(plan: PublicationPlan, dry_run: bool = False, confirm=None) -> str | None:
    if not plan.upstream_manifest:
        raise ValueError("Upstream comparison unavailable; cannot create a publication PR")
    if not plan.open_prs_available:
        raise ValueError("Open upstream PRs could not be checked; refusing to create a PR")
    versions = list(plan.ready_releases)
    cleanup = plan.cleanup_directories
    if not versions and not cleanup:
        print("No unpublished READY versions or upstream cleanup; no publication PR to create.", file=sys.stderr)
        return None
    published_commit, generated = prepare_publication_source(plan)
    follow_ups = {
        version: plan.follow_up_directories.get(version, set())
        for version in plan.added_architectures
    }
    held_back = {
        directory
        for version in versions
        for directory in plan.held_back_directories.get(version, set())
    }
    manifest = merge_publication_manifest(
        plan.upstream_manifest, generated, versions, cleanup, follow_ups, held_back,
    )
    if manifest == plan.upstream_manifest:
        raise ValueError("Selected updates do not change the upstream manifest")
    releases = plan.ready_releases
    added = plan.added_architectures
    branch_parts = [
        "-".join([release, *added.get(version, [])]) for version, release in releases.items()
    ]
    if cleanup:
        digest = hashlib.sha256("\n".join(sorted(cleanup)).encode("utf-8")).hexdigest()[:12]
        branch_parts.append(f"cleanup-{digest}")
    branch = "eclipse-temurin-" + "-".join(branch_parts)
    title, body = describe_publication(
        published_commit, releases, added, plan.deferred_architectures,
        plan.held_back_directories, cleanup,
    )
    if dry_run or confirm:
        heading = "Dry run: would open" if dry_run else "Proposed"
        print(f"{heading} upstream PR '{title}' on branch {branch}", file=sys.stderr)
        print(f"PR description:\n{body}\n", file=sys.stderr)
        print(
            "".join(difflib.unified_diff(
                plan.upstream_manifest.splitlines(keepends=True), manifest.splitlines(keepends=True),
                fromfile="a/library/eclipse-temurin", tofile="b/library/eclipse-temurin",
            )),
            end="", file=sys.stderr,
        )
    if dry_run:
        print("Dry run only; no files, branches, forks, or PRs were changed.", file=sys.stderr)
        return None
    if confirm and not confirm("Open this upstream PR? [y/N] "):
        print("Aborted; no branches, forks, or PRs were changed.", file=sys.stderr)
        return None
    with tempfile.TemporaryDirectory(prefix="temurin-publication-") as temporary:
        checkout = Path(temporary) / "official-images"
        run_publication_command(
            "gh", "repo", "clone", "docker-library/official-images", str(checkout),
            "--", "--depth=1", "--single-branch",
        )
        upstream_file = checkout / "library" / "eclipse-temurin"
        if upstream_file.read_text() != plan.upstream_manifest:
            raise ValueError("The upstream manifest changed; rerun the readiness check")
        open_prs = fetch_open_publication_prs()
        if open_prs is None:
            raise ValueError("Open upstream PRs could not be checked; refusing to create a PR")
        for version, release in releases.items():
            matches = matching_publication_prs(
                release, open_prs, plan.follow_up_directories.get(version),
            )
            if matches:
                raise ValueError(f"Release {release} is already in an upstream PR: {matches[0].url}")
        removed = get_manifest_entries(plan.upstream_manifest).keys() - get_manifest_entries(manifest).keys()
        for pr in open_prs:
            if removed & pr.removed_directories:
                raise ValueError(f"Cleanup is already in an upstream PR: {pr.url}")

        login = run_publication_command("gh", "api", "user", "--jq", ".login")
        if not login:
            raise ValueError("GitHub did not return an authenticated user")
        run_publication_command(
            "gh", "repo", "fork", "docker-library/official-images", "--clone=false",
        )
        run_publication_command("git", "checkout", "-b", branch, cwd=checkout)
        upstream_file.write_text(manifest)
        run_publication_command("git", "add", "--", "library/eclipse-temurin", cwd=checkout)
        run_publication_command(
            "git", "commit", "-m", title, cwd=checkout,
        )
        run_publication_command(
            "git", "remote", "add", "publication", f"https://github.com/{login}/official-images.git",
            cwd=checkout,
        )
        run_publication_command(
            "git", "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential",
            "push", "publication", branch, cwd=checkout,
        )
        url = run_publication_command(
            "gh", "pr", "create", "--repo", "docker-library/official-images",
            "--base", "master", "--head", f"{login}:{branch}", "--title", title,
            "--body", body,
            cwd=checkout,
        )
        if not url.startswith("https://github.com/docker-library/official-images/pull/"):
            raise ValueError("GitHub did not return a publication PR URL")
        print(f"Created upstream publication PR: {url}", file=sys.stderr)
        return url


def find_manifest_block(official_manifest, tags_str):
    """Find the manifest block matching the given tags in the official manifest."""
    if not official_manifest:
        return None
    for block in official_manifest.split("\n\n"):
        if tags_str in block:
            return block
    return None


def get_block_gitcommit(block):
    """Extract GitCommit from a manifest block."""
    if not block:
        return None
    for line in block.split("\n"):
        if line.startswith("GitCommit:"):
            return line.split(":")[1].strip()
    return None


def has_changed(gitcommit, official_gitcommit, dfdir):
    """Check if Dockerfile or entrypoint.sh changed between two git commits."""
    if not official_gitcommit:
        return True
    try:
        result = subprocess.run(
            [
                "git", "diff",
                f"{gitcommit}:{dfdir}/Dockerfile",
                f"{official_gitcommit}:{dfdir}/Dockerfile",
            ],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return True
        diff_lines = len(result.stdout.splitlines())

        entrypoint = os.path.join(dfdir, "entrypoint.sh")
        if os.path.exists(entrypoint):
            result = subprocess.run(
                [
                    "git", "diff",
                    f"{gitcommit}:{dfdir}/entrypoint.sh",
                    f"{official_gitcommit}:{dfdir}/entrypoint.sh",
                ],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                return True
            diff_lines += len(result.stdout.splitlines())

        return diff_lines > 0
    except Exception:
        return True


def generate_manifest(config, output_file, dry_run=False, force_versions=frozenset()):
    maintainers = config.get("maintainers")
    if (
        not isinstance(maintainers, list) or not maintainers
        or any(
            not isinstance(maintainer, str) or not maintainer.strip()
            or "\n" in maintainer or "\r" in maintainer
            for maintainer in maintainers
        )
    ):
        raise ValueError("config/temurin.yml must define maintainers as a non-empty list of single-line strings")

    gitcommit = get_git_commit()
    official_manifest = fetch_official_manifest()
    official_entries = get_manifest_entries(official_manifest)

    versions = get_supported_versions()
    unsupported = sorted(set(force_versions) - set(versions))
    if unsupported:
        raise ValueError(
            f"Cannot force unsupported Java versions: {', '.join(map(str, unsupported))}. "
            f"Supported versions: {', '.join(map(str, versions))}"
        )
    readiness = {version: [] for version in versions}
    latest_version = get_latest_lts()
    # Default images are the first entry in each OS family
    default_linux_image = get_distro_name("linux", config["configurations"]["linux"][0]["directory"])
    default_alpine_image = get_distro_name("alpine-linux", config["configurations"]["alpine-linux"][0]["directory"])

    lines = []

    # Header
    lines.append("# Eclipse Temurin OpenJDK images provided by the Eclipse Foundation.")
    lines.append("")
    maintainer_prefix = "Maintainers: "
    lines.append(maintainer_prefix + (",\n" + " " * len(maintainer_prefix)).join(maintainers))
    lines.append("GitRepo: https://github.com/adoptium/containers.git")
    lines.append("GitFetch: refs/heads/main")
    lines.append("Builder: buildkit")

    # OS family iteration order matches the original script
    os_family_order = ["alpine-linux", "linux", "windows"]

    for ver in versions:
        lines.append("")
        lines.append(
            f"#------------------------------v{ver} images---------------------------------"
        )

        for pkg in ["jdk", "jre"]:
            for os_family in os_family_order:
                if os_family not in config["configurations"]:
                    continue

                for cfg in config["configurations"][os_family]:
                    directory = cfg["directory"]
                    deprecated = cfg.get("deprecated", None)
                    cfg_versions = cfg.get("versions", versions)

                    if ver not in cfg_versions:
                        continue
                    if deprecated and ver >= deprecated:
                        continue

                    dfdir = os.path.join(str(ver), pkg, directory)
                    dockerfile = os.path.join(dfdir, "Dockerfile")
                    image = ImageReadiness(dfdir)
                    readiness[ver].append(image)

                    if not os.path.exists(dockerfile):
                        image.blockers.append("missing Dockerfile")
                        continue

                    full_version = get_java_version(dockerfile)
                    if not full_version:
                        image.blockers.append("missing JAVA_VERSION")
                        continue
                    image.java_version = full_version

                    overrides = config.get("architecture_overrides", []) + cfg.get("architecture_overrides", [])
                    architectures = resolve_architectures(cfg["architectures"], overrides, ver)
                    expected_arches = {
                        ("windows-" if os_family == "windows" else "") + DOCKERFILE_ARCH_MAP[arch]
                        for arch in architectures
                    }
                    arches = ["windows-amd64"] if os_family == "windows" else get_dockerfile_arches(dockerfile)
                    missing = sorted(expected_arches - set(arches))
                    if not expected_arches:
                        image.blockers.append("no configured architectures")
                    if missing:
                        image.blockers.append(f"missing architectures: {', '.join(missing)}")
                    pending = []
                    if os_family != "windows":
                        pending = get_pending_arches(dockerfile)
                        if ver == 8 and "arm32v7" in pending:
                            image.deferred_arches.append("arm32v7")
                            pending.remove("arm32v7")
                        if ver in force_versions:
                            image.deferred_arches = sorted(set(image.deferred_arches) | set(pending))
                            pending = []
                        if arches and not set(arches) - set(image.deferred_arches):
                            image.blockers.append("no available binaries")
                    if not arches:
                        image.blockers.append("no Dockerfile architectures")
                        continue

                    ojdk_version = format_ojdk_version(full_version)
                    distro = get_distro_name(os_family, directory)
                    is_windows = os_family == "windows"

                    # Build tags
                    full_ver_tag = f"{ojdk_version}-{pkg}-{distro}"
                    upstream_entry = official_entries.get(dfdir)
                    if upstream_entry is None:
                        image.updated = True
                    else:
                        suffix = f"-{pkg}-{distro}"
                        published_version = next(
                            (
                                tag[:-len(suffix)]
                                for tag in upstream_entry.get("Tags", "").split(", ")
                                if tag.endswith(suffix)
                            ),
                            None,
                        )
                        if published_version is None:
                            image.blockers.append("upstream entry has no release tag")
                        else:
                            local_key = java_version_key(ojdk_version)
                            published_key = java_version_key(published_version)
                            image.updated = local_key > published_key
                            image.published = local_key == published_key
                            if local_key < published_key:
                                image.blockers.append(f"older than upstream release {published_version}")
                            elif not image.updated and os_family != "windows":
                                # Same release, but binaries pending in the published commit may now exist.
                                still_pending = set(pending) | set(image.deferred_arches)
                                published_pending = get_published_pending_arches(
                                    upstream_entry.get("GitCommit"), dockerfile,
                                )
                                if published_pending is None:
                                    image.blockers.append("cannot read published Dockerfile at upstream GitCommit")
                                else:
                                    # Binaries already pending when this release was published are follow-ups, not blockers.
                                    carried = set(pending) & set(published_pending)
                                    image.deferred_arches = sorted(set(image.deferred_arches) | carried)
                                    pending = sorted(set(pending) - carried)
                                    image.added_arches = sorted(
                                        (set(published_pending) & set(arches)) - still_pending
                                    )
                                    image.updated = bool(image.added_arches)
                    image.pending_arches = pending
                    if os_family != "windows":
                        image.arches = arches
                    ver_tag = f"{ver}-{pkg}-{distro}"
                    all_tags = f"{full_ver_tag}, {ver_tag}"

                    extra_shared_tags = ""
                    if pkg == "jdk":
                        jdk_tag = f"{ver}-{distro}"
                        all_tags = f"{all_tags}, {jdk_tag}"
                        if ver == latest_version and os_family != "alpine-linux":
                            extra_shared_tags = ", latest"

                    # Shared tags = tags without distro suffix
                    shared_tags = all_tags.replace(f"-{distro}", "")

                    if is_windows:
                        parts = distro.split("-", 1)
                        windows_version = parts[0]
                        windows_version_number = parts[1] if len(parts) > 1 else ""
                        windows_shared_tags = all_tags.replace(distro, windows_version)

                        if distro.startswith("nanoserver"):
                            constraints = (
                                f"{distro}, windowsservercore-{windows_version_number}"
                            )
                            all_shared_tags = windows_shared_tags
                        else:
                            constraints = distro
                            all_shared_tags = (
                                f"{windows_shared_tags}, "
                                f"{shared_tags}{extra_shared_tags}"
                            )
                    else:
                        all_shared_tags = f"{shared_tags}{extra_shared_tags}"

                    # Compare with official manifest (before appending alpine aliases)
                    manifest_block = find_manifest_block(official_manifest, all_tags)
                    official_gitcommit = get_block_gitcommit(manifest_block)

                    if official_gitcommit and not has_changed(
                        gitcommit, official_gitcommit, dfdir
                    ):
                        commit = official_gitcommit
                    else:
                        commit = gitcommit

                    # Append alpine alias tags for the default alpine image
                    if distro == default_alpine_image:
                        alpine_aliases = (
                            all_shared_tags.replace(", ", "-alpine, ") + "-alpine"
                        )
                        all_tags = f"{all_tags}, {alpine_aliases}"

                    # Write entry
                    lines.append(f"Tags: {all_tags}")
                    if is_windows or distro == default_linux_image:
                        lines.append(f"SharedTags: {all_shared_tags}")
                    lines.append(f"Architectures: {', '.join(arches)}")
                    lines.append(f"GitCommit: {commit}")
                    lines.append(f"Directory: {dfdir}")
                    if is_windows:
                        lines.append("Builder: classic")
                        lines.append(f"Constraints: {constraints}")
                    lines.append("")

    while lines and lines[-1] == "":
        lines.pop()
    manifest = "\n".join(lines) + "\n"
    if not dry_run:
        with open(output_file, "w") as f:
            f.write(manifest)

    configured_directories = {
        image.directory for images in readiness.values() for image in images
    }
    retired = official_entries.keys() - configured_directories
    updated = any(image.updated for images in readiness.values() for image in images)
    open_prs = fetch_open_publication_prs() if official_manifest and (updated or retired) else []
    cleanup = set(retired)
    for pr in open_prs or []:
        cleanup -= pr.removed_directories
    if open_prs is None:
        cleanup.clear()
    print_deprecated_upstream_images(retired)
    for version in force_versions:
        releases = [image.java_version for image in readiness[version] if image.java_version]
        latest = max(releases, key=java_version_key, default=None)
        for image in readiness[version]:
            # Images already published at an older release can keep their upstream entry.
            image.held_back = bool(
                image.published and java_version_key(image.java_version) < java_version_key(latest)
            )
    pr_baselines = apply_open_pr_baselines(readiness, open_prs or [])
    for images in readiness.values():
        for image in images:
            if image.pending_arches:
                image.blockers.append(f"pending binaries: {', '.join(image.pending_arches)}")
    ready_releases, statuses = print_publish_summary(
        readiness, output_file, official_manifest is not None, open_prs, pr_baselines,
    )
    for pr in open_prs or []:
        if retired & pr.removed_directories:
            print(f"Upstream cleanup PR open: {pr.url}", file=sys.stderr)
    if cleanup:
        print(
            f"\nUpstream cleanup ready: {len(cleanup)} retired image entries. "
            "Use --create-pr to remove them, or --dry-run to preview, "
            "even if no Java versions are READY.",
            file=sys.stderr,
        )
    elif retired and open_prs is None:
        print("Upstream cleanup UNKNOWN: open upstream PRs could not be checked.", file=sys.stderr)
    if force_versions:
        check_forced_versions(readiness, force_versions, statuses)
    added_architectures = {}
    deferred_architectures = {}
    follow_up_directories = {}
    held_back_directories = {}
    for version in ready_releases:
        held = {image.directory for image in readiness[version] if image.held_back}
        if held:
            held_back_directories[version] = held
        images = [image for image in readiness[version] if not image.held_back]
        affected = {image.directory for image in images if image.added_arches}
        if affected:
            follow_up_directories[version] = affected
        # A follow-up only adds binaries to a release that is already published upstream.
        if all(image.added_arches for image in images if image.updated):
            added_architectures[version] = sorted({a for image in images for a in image.added_arches})
        deferred = sorted({a for image in images for a in image.deferred_arches})
        if deferred:
            deferred_architectures[version] = deferred
    pr_updates = {}
    for version, status in statuses.items():
        if status != "PR UPDATE":
            continue
        pr, head = pr_baselines[version]
        update = pr_updates.setdefault(pr.url, PublicationPRUpdate(pr, head, {}, {}, {}))
        for pr_version, (other, _) in pr_baselines.items():
            if other.url != pr.url:
                continue
            images = [image for image in readiness[pr_version] if not image.held_back]
            update.releases[pr_version] = format_ojdk_version(
                max((image.java_version for image in images), key=java_version_key)
            )
            deferred = sorted({a for image in images for a in image.deferred_arches})
            if deferred:
                update.deferred_architectures[pr_version] = deferred
            held = {image.directory for image in readiness[pr_version] if image.held_back}
            if held:
                update.held_back_directories[pr_version] = held
        images = [image for image in readiness[version] if not image.held_back]
        update.added_architectures[version] = sorted({a for image in images for a in image.pr_added_arches})
        update.directories[version] = {image.directory for image in images if image.pr_added_arches}
    return PublicationPlan(
        official_manifest, manifest, ready_releases, open_prs is not None, cleanup,
        added_architectures, deferred_architectures, follow_up_directories, held_back_directories,
        list(pr_updates.values()),
    )


def parse_java_versions(value):
    try:
        return {int(version) for version in value.split(",")}
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected comma-separated Java versions such as 17,21,25; got {value!r}"
        ) from None


def main():
    parser = argparse.ArgumentParser(description="Generate the Temurin manifest and report publication readiness and retired-image cleanup.")
    parser.add_argument("output_file", nargs="?", default="eclipse-temurin")
    parser.add_argument(
        "--create-pr", action="store_true",
        help="open an upstream PR for all unpublished READY Java versions and retired image cleanup (requires git and authenticated gh)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="preview READY release updates and retired image cleanup without writing files or creating a PR",
    )
    parser.add_argument(
        "--force", type=parse_java_versions, default=set(), metavar="VERSIONS",
        help="comma-separated Java versions (e.g. 17,21,25) to publish while binaries are still pending "
             "for some architectures; prints the missing binaries and PR preview, then asks y/n before opening the PR",
    )
    args = parser.parse_args()
    try:
        config = load_config()
        print_eol_warnings(config)
        plan = generate_manifest(
            config, args.output_file, dry_run=args.dry_run, force_versions=args.force,
        )
        if args.create_pr or args.dry_run or args.force:
            confirm = confirm_publication if args.force else None
            update_publication_prs(plan, dry_run=args.dry_run, confirm=confirm)
            create_publication_pr(plan, dry_run=args.dry_run, confirm=confirm)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        details = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
        parser.exit(1, f"Error: {details or str(error)}\n")


if __name__ == "__main__":
    main()
