import 'core.just'

# 🗺️ Build a specific layer (usage: just layer build ch_basemap_25k) (default)
[default]
build layer:
    @header "Building layer '{{layer}}'..."
    uv run cartoload build \
        --sources examples/configs/sources/swisstopo.yaml \
        --layers examples/configs/layers/switzerland.yaml \
        --layer {{layer}}

# 🇨🇭 Build full Switzerland 25k basemap
build-ch-25k:
    @header "Building Switzerland 1:25k basemap..."
    uv run cartoload build \
        --sources examples/configs/sources/swisstopo.yaml \
        --layers examples/configs/layers/switzerland.yaml \
        --layer ch_basemap_25k

# ❓ Show help
[private]
help task="":
    @just --list layer
