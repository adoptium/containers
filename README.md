# Containers

This repository contains the Dockerfiles for the official Adoptium images of the Eclipse Temurin distribution (OpenJDK). These images are made available in Docker Hub.

If you are looking for the usage README then please head to the [Official Docker Hub Documentation](https://hub.docker.com/_/eclipse-temurin).

## Supported Images

In general, we support Ubuntu, CentOS and Windows containers.

[List of Support Images By Tag](https://github.com/docker-library/docs/tree/master/eclipse-temurin#simple-tags)

Alpine (Musl) will be supported in the near future.

## Maintenance of Dockerfiles

This section is for maintainers of the containers repository.

### Nightly automated Job

A [Updater GitHub Action](.github/workflows/updater.yml) runs every night which triggers the
[`./update_all.sh`](./update_all.sh) script to update the Dockerfiles by creating a Pull Request containing any changes.

#### update_all.sh

[`./update_all.sh`](./update_all.sh) is a wrapper script to control what is passed into [`./update_multiarch.sh`](./update_multiarch.sh).

#### update_multiarch.sh

[`./update_multiarch.sh`](./update_multiarch.sh) loops around the configuration for which versions and architectures are supported in [`./common_functions.sh`](./common_functions.sh) and uses a bunch of small functions in [`./dockerfile_functions.sh`](./dockerfile_functions.sh) to write the Dockerfiles.

### Manual Release

During a release you can also run [`./update_all.sh`](./update_all.sh) manually by heading to The [GitHub Action definition](https://github.com/adoptium/containers/actions/workflows/updater.yml) and clicking the _Run Workflow_ button and making sure the `main` (default) branch is selected, then click the next _Run Workflow_ button.

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

This script will create a file called _eclipse-temurin_.

Then edit the [Manifest on Docker Hub](https://github.com/docker-library/official-images/blob/master/library/eclipse-temurin), replacing all of the contents.

At the bottom of that edit screen add a title and description for the commit and click on the _Propose Change_ button.

In the next screen click on the _Create Pull Request Button_.

Once that PR has been created it will be automatically tested and reviewed by Docker Hub staff and eventually released.

### Diff Output at Docker Hub

It can be useful to look at the diff output created by one of the Docker Hub GitHub Actions on the Pull Request. This output
should not be read as a traditional PR (since Docker Hub bots do move things around, so you may see what looks like odd deletions)
but as a sanity check to make sure you see the platoforms/architectures that you expect.
