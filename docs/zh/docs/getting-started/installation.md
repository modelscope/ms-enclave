# 安装指南

## 环境准备

在安装 ms-enclave 之前，请确保您的环境满足以下要求：

*   **Python**: 版本 >= 3.10
*   **Docker**: 必须安装并运行 Docker Daemon。这是 ms-enclave 创建隔离沙箱的基础。
    *   如果您打算使用 `Notebook` 沙箱，请确保 Docker 容器可以对外暴露 8888 端口。

## 安装

### 从 PyPI 安装（推荐）

使用 pip 直接安装：

```bash
pip install ms-enclave
```

如果需要 Docker 支持（通常都需要），请安装额外依赖：

```bash
pip install 'ms-enclave[docker]'
```

### 从源码安装

如果您需要最新的开发版本，可以从 GitHub 克隆源码安装：

```bash
git clone https://github.com/modelscope/ms-enclave.git
cd ms-enclave
pip install -e .
# 安装 Docker 依赖
pip install -e '.[docker]'
```

## 验证安装

安装完成后，您可以运行以下代码来验证是否安装成功：

```shell
ms-enclave -v
```
