#!/bin/bash

# Build Python sandbox Docker image
# This creates a basic Python environment for sandbox execution

set -e

IMAGE_NAME="python-sandbox"
IMAGE_TAG="latest"

echo "Building Python sandbox Docker image..."

# Create a temporary Dockerfile
cat > Dockerfile.sandbox << 'EOF'
FROM python:3.11-slim

# Install basic system utilities
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    vim \
    nano \
    htop \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install common Python packages
RUN pip install --no-cache-dir \
    numpy \
    pandas \
    matplotlib \
    seaborn \
    scikit-learn \
    requests \
    beautifulsoup4 \
    lxml \
    pillow \
    tqdm \
    jupyter

# Create sandbox user (non-root for security)
RUN useradd -m -s /bin/bash sandbox

# Create working directory
RUN mkdir -p /sandbox && chown sandbox:sandbox /sandbox

# Set working directory
WORKDIR /sandbox

# Switch to sandbox user
USER sandbox

# Set default command
CMD ["/bin/bash"]
EOF

# Build the image
echo "Building Docker image: ${IMAGE_NAME}:${IMAGE_TAG}"
docker build -f Dockerfile.sandbox -t "${IMAGE_NAME}:${IMAGE_TAG}" .

# Clean up
rm Dockerfile.sandbox

echo "✓ Docker image built successfully: ${IMAGE_NAME}:${IMAGE_TAG}"
echo ""
echo "To test the image, run:"
echo "  docker run -it --rm ${IMAGE_NAME}:${IMAGE_TAG}"
echo ""
echo "To use with the sandbox system, use image: '${IMAGE_NAME}:${IMAGE_TAG}'"
