import 'core.just'

# ▶️  Run all checks: lock + lint (default)
[default]
all: lock lint
    @info "Tests are not run separately — use 'just tests'."

# 🔒 Check uv lock file is up to date
lock:
    @header "Checking lock file..."
    uv lock --locked
    @success "Lock file OK!"

# 🧹 Lint with ruff
lint:
    @header "Linting..."
    uv run ruff check .
    uv run ruff format --check .
    @success "Linting passed!"

# 🪄 Auto-fix with ruff
fix:
    @header "Fixing..."
    uv run ruff check --fix .
    uv run ruff format .
    @success "Fixes applied!"

# 🔍 Static type checking with ty
types:
    @header "Type checking..."
    uv run ty check src/
    @success "Type checking passed!"

# ❓ Show help
[private]
help task="":
    @just --list check
