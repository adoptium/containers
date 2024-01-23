# Containers
[![DockerPulls](https://img.shields.io/docker/pulls/_/eclipse-temurin?label=Docker%20Pulls)](https://hub.docker.com/_/eclipse-temurin)
[![Docker Stars](https://img.shields.io/docker/stars/_/eclipse-temurin?label=Docker%20Stars)](https://hub.docker.com/r/_/eclipse-temurin)

This repository contains the Dockerfiles for the official [Adoptium](https://adoptium.net) images of the Eclipse Temurin distribution (OpenJDK). These images are made available in Docker Hub.

If you are looking for the usage README then please head to the [Official Docker Hub Documentation](https://hub.docker.com/_/eclipse-temurin).

## Supported Images

In general, we support Alpine, CentOS, UBI, Ubuntu and Windows containers.

[List of Support Images By Tag](https://github.com/docker-library/docs/tree/master/eclipse-temurin#simple-tags)

## Update Policy

As these are official Docker Hub images, Docker Inc maintains the base image and so any CVEs in the base O/S layer gets updated by them in short order.
For JDK version updates, we release on a quarterly cadence whenever a Patch Set Update (PSU) is available.

## Maintenance of Dockerfiles

This section is for maintainers of the containers repository.

### Hourly automated Job

A [Updater GitHub Action](.github/workflows/updater.yml) runs every 30 mins which triggers the
[`./generate_dockerfiles.py`](./generate_dockerfiles.py) script to update the Dockerfiles by creating a Pull Request containing any changes.

#### generate_dockerfiles.py

[`./generate_dockerfiles.py`](./generate_dockerfiles.py) is a python script which uses the jinja templates defined in [docker_templates](./docker_templates/) to generate the docker updates. It uses the Adoptium API to fetch the latest artefacts for each release.

### Manual Release

During a release you can also run [`./generate_dockerfiles.py`](./generate_dockerfiles.py) manually by heading to The [GitHub Action definition](https://github.com/adoptium/containers/actions/workflows/updater.yml) and clicking the **Run Workflow** button and making sure the `main` (default) branch is selected, then click the next **Run Workflow** button.

### Review and Merge PR

Once the PR is created you can review that PR (which itself tests all of the Docker Images that we have generate configuration for).

## Update Official Docker Hub Manifest

Once you've merged the PR, you can update the official Docker Hub manifest. This is done by running the following command in the containers repo on your local machine:

```bash
# Get the latest changes
git fetch --all
# Checkout the main branch
git checkout main
./dockerhub_doc_config_update.sh
```

This script will create a file called _eclipse-temurin_ by default.

Create a new PR to replace the [Manifest on Docker Hub](https://github.com/docker-library/official-images/blob/master/library/eclipse-temurin) with the new contents of _eclipse-temurin_ 

- Go to https://github.com/docker-library/official-images/blob/master/library/eclipse-temurin web UI 
- Click **edit(pencil button)** 
- Remove its content
- Copy-paste _eclipse-temurin_'s content
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
