# Installation Guide

## Prerequisites

Before installing ms-enclave, ensure your environment meets the following:

- Python: version >= 3.10
- Docker: Docker daemon must be installed and running (ms-enclave relies on it for isolated sandboxes).
  - If you plan to use the `Notebook` sandbox, ensure port 8888 can be exposed by containers.

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