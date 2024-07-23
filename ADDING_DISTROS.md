# Adding New Distributions to Adoptium

## 1. Introduction

This document aims to formalize the process and criteria for adding new operating system distributions to the Adoptium project. Adoptium currently supports a range of Long-Term Support (LTS) distributions and is committed to ensuring that new additions meet the community's needs and project's standards.

## 2. Current Supported Distributions

The current list of supported distributions can be seen at [Supported Platforms](https://adoptium.net/supported-platforms/). The Docker icon indicates which distributions are supported as part of the official image manifest.

## 3. Criteria for Adding New Distributions

All proposals for new distributions must be reviewed and approved by the Project Management Committee (PMC). The PMC evaluates each proposal based on the established criteria to ensure that the addition aligns with the project's strategic goals and resource capabilities.

### 3.1 Long-Term Support (LTS) Requirement

Only distributions with a commitment to long-term support are considered to ensure stability and ongoing support.

### 3.2 Community Demand

The distribution must demonstrate significant demand from the Adoptium community or enterprise users.

### 3.3 Technical Feasibility

The distribution should be capable of supporting the Eclipse Temurin versions without requiring excessive adaptations.

### 3.4 Compatibility Testing

New distributions must pass a predefined set of compatibility tests to confirm that existing functionalities are not adversely affected.

### 3.5 Official Base Images

Because Eclipse Temurin images are published as [official images](https://docs.docker.com/trusted-content/official-images/), there are restrictions as to which base images we can depend on.

### 3.5 Encouraging Flexible Deployment via Docker

While we strive to support a range of widely-used distributions, our main goal is not to support every possible distribution. Instead, we encourage users to leverage Docker's `COPY` command to deploy Java and other dependencies on top of any base image they prefer. This approach allows users greater flexibility and control over their deployment environments, aligning with modern best practices for software distribution and deployment.

#### Example of Using Docker `COPY`:

```dockerfile
# Use an arbitrary base image
FROM your-choice-of-base-image

# Copy the JDK from an Eclipse Temurin image
COPY --from=eclipse-temurin:21-jdk /opt/java/openjdk /opt/java/openjdk

# Set environment variables for Java
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# Continue with your application setup
```

## 4. Process for Adding New Distributions

### 4.1 Proposal Submission

Contributors may submit proposals for new distributions by filling out a specified template that includes:
- Distribution name and version
- Justification for inclusion
- LTS evidence
- Expected community interest
- Preliminary compatibility assessment

### 4.2 Review Process

Proposals are reviewed quarterly by a designated committee, including:
- Initial feasibility assessment
- Community consultation (via surveys and forums)
- Final decision-making

### 4.3 Implementation

Upon approval, the following steps are taken:
- Setup of build and test environments
- Integration into existing CI/CD pipelines
- Monitoring initial deployment

### 4.4 Documentation

All support for new distributions is documented in the official project documentation and announced via official channels.

### 4.5 Announcement

New distribution support is announced in the project newsletter and on major community channels.

## 5. Deprecation and End-of-Life Policy

Adoptium is committed to providing robust and secure software environments. To maintain the integrity and security of our distributions, it is necessary to phase out support for distributions that reach their End-of-Life (EOL). This policy outlines the steps and considerations involved in the deprecation process.

### 5.1 Definition of End-of-Life

A distribution reaches End-of-Life when it no longer receives updates and patches from its original maintainers. This includes security patches, performance improvements, and compatibility updates.

### 5.2 Deprecation Process

Upon a distribution reaching its EOL, Adoptium will take the following steps:

1. **Announcement**: We will announce the impending deprecation through our official channels at least six months prior to the final update. This announcement will include the final date of support and recommended migration paths for users.

2. **Final Update**: The last update provided will ensure that the distribution remains secure and stable until the EOL date.

3. **Removal from Active Support**: After the final update, no further builds or updates will be published for the EOL distribution. Documentation will be updated to reflect the distribution's deprecated status.

4. **Documentation and Guidance**: Provide detailed guidance on migrating to supported distributions, including potential substitutes that offer similar or improved functionality.

### 5.3 Encouraging Migration

Users are encouraged to plan their migration strategies well before the EOL date to ensure seamless transitions to supported distributions. Adoptium is committed to assisting in these migration efforts through documentation, community support, and direct assistance where possible.

### 5.4 Archive and Access

While updates will cease for EOL distributions, previous tagged versions will remain available for historical access and audit purposes. These archived versions are not recommended for use in production environments as they will not receive updates or security patches.

This policy ensures that Adoptium can focus resources on supporting and developing distributions that provide the most value and security to our users, while also adhering to best practices in software maintenance and support.

## 6. Amendment Procedure

The process for updating this document includes community consultation and must be approved by a majority of the Project Management Committee (PMC).

## Feedback and Improvements

Feedback on this document is welcome and can be submitted via [GitHub issues](https://github.com/adoptium/containers/issues/new/choose).
