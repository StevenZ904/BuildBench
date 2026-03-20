#!/bin/bash

# Check if version argument is provided
if [ -z "$1" ]; then
  echo "Usage: $0 <version> [--no-cache]"
  exit 1
fi

VERSION=$1
NO_CACHE=""

# Check if --no-cache flag is provided
if [ "$2" == "--no-cache" ]; then
  NO_CACHE="--no-cache"
fi

# Build the Docker image
sudo docker build $NO_CACHE -t docker_image_compilation -f src/Dockerfile_compilation .

# Tag the Docker image with the provided version
docker tag docker_image_compilation:latest buildbench/compilation_base_image:$VERSION

# Push the Docker image to the repository
docker push buildbench/compilation_base_image:$VERSION