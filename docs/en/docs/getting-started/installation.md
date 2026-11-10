# Installation Guide

## Prerequisites

Before installing ms-enclave, ensure your environment meets the following:

- Python: version >= 3.11
- Docker backends: a Docker daemon must be installed and running.
  - If you plan to use the `Notebook` sandbox, ensure port 8888 can be exposed by containers.
- E2B backend: an E2B-compatible service and API key; no local Docker daemon is required.

## Install

### From PyPI (recommended)

Use pip:

```bash
pip install ms-enclave
```

If you need Docker support (usually yes), install extra dependencies:

```bash
pip install 'ms-enclave[docker]'
```

For [E2B-compatible remote sandboxes](../deployment/e2b.md), install:

```bash
pip install 'ms-enclave[e2b]'
```

### From source

For the latest development version:

```bash
git clone https://github.com/modelscope/ms-enclave.git
cd ms-enclave
pip install -e .
# Install Docker extras
pip install -e '.[docker]'
```

## Verify

After installation, verify with:

```shell
ms-enclave -v
```
