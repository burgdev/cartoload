import 'core.just'

# 🐳 Build Docker image (default)
[default]
build:
    @header "Building Docker image..."
    docker build -t cartoload .
    @success "Docker image built!"

# ❓ Show help
[private]
help task="":
    @just --list docker
