# ms-enclave Documentation

ms-enclave is a modular and robust sandbox runtime providing a secure, isolated execution environment for your applications. It leverages Docker containers for strong isolation, ships with local/HTTP managers, and an extensible tool system to execute code safely and efficiently in a controlled environment.

## Key Features

- 🔒 Security: Docker-based isolation with resource limits
- 🧩 Modularity: Pluggable sandboxes and tools (registry/factory)
- ⚡ Stability: Lightweight, fast startup, lifecycle management
- 🌐 Remote Control: Built-in FastAPI server for HTTP management
- 🔧 Tooling: Standardized tools enabled per-sandbox (OpenAI-style schema)

## Requirements

- Python >= 3.10
- OS: Linux, macOS, or Windows with Docker support
- A working local Docker daemon (Notebook sandbox needs port 8888 exposed)
