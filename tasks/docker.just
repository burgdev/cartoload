import 'core.just'

IMAGE := "cartoload"

# 🐳 Build Docker image (default: base)
[default]
build mkgmap="":
    @#!/usr/bin/env bash
    set -euo pipefail
    tag="{{IMAGE}}:base"
    args=()
    if [ -n "{{ mkgmap }}" ]; then
      tag="{{IMAGE}}:mkgmap"
      args+=(--build-arg INSTALL_MKGMAP=1)
    fi
    docker build -t "$tag" "${args[@]}" .

# ❓ Show help
[private]
help task="":
    @just --list docker
