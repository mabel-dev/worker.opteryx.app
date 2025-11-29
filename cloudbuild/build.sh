#!/bin/bash
set -euo pipefail

# Build and push locally with gcloud (requires gcloud CLI)
PROJECT_ID=${PROJECT_ID:-$(gcloud config get-value project)}
AR_REGION=${AR_REGION:-us-east1}
AR_REPOSITORY=${AR_REPOSITORY:-cloud-run-source-deploy}
IMAGE=${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPOSITORY}/opteryx-worker:latest

echo "Building ${IMAGE}..."
docker build -t "${IMAGE}" .
echo "Pushing ${IMAGE} to Artifact Registry..."
docker push "${IMAGE}"
