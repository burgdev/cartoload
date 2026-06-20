import 'core.just'

# 🌐 Serve docs locally with live reload (default)
[default]
serve port='8088':
    @header "Generating CLI docs..."
    @uv run python scripts/generate-cli-docs.py
    @header "Serving docs at localhost:{{port}}..."
    uv run --group docs zensical serve -f docs/zensical.toml --dev-addr localhost:{{port}}

# 📦 Build docs
build:
    @header "Generating CLI docs..."
    @uv run python scripts/generate-cli-docs.py
    @header "Building docs..."
    uv run --group docs zensical build -f docs/zensical.toml
    @success "Docs built in 'docs/site/'."

# ❓ Show help
[private]
help task="":
    @just --list docs
