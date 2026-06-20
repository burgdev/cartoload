import 'core.just'

# 📋 Run tests (default)
[default]
tests cov="no":
    #! ./.shell-wrapper.sh
    header "Running tests..."
    if [[ "$(is_true "{{cov}}")" == "true" ]]; then
        uv run pytest --cov=cartoload --cov-report=term-missing --cov-report=html
    else
        uv run pytest -v
    fi

# ❓ Show help
[private]
help task="":
    @just --list tests
