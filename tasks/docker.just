import 'core.just'

IMAGE := "cartoload"

# 🐳 Build Docker image (default: base)
build mkgmap="":
	@#!/usr/bin/env bash
	if [ -n "{{ mkgmap }}" ]; then tag="{{IMAGE}}:mkgmap"; args=(--build-arg INSTALL_MKGMAP=1); else tag="{{IMAGE}}:base"; args=(); fi && docker build -t "$tag" "${args[@]}" .

# ❓ Show help
[private]
[default]
help task="":
	@just --list docker
