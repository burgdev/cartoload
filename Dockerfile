# ---- mozjpeg stage: build cjpeg with trellis quantization ----
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.13.0 AS mozjpeg

RUN apt-get update && apt-get install -y --no-install-recommends \
  cmake git build-essential libpng-dev nasm \
  && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch v4.1.5 https://github.com/mozilla/mozjpeg.git /tmp/mozjpeg \
  && cd /tmp/mozjpeg \
  && mkdir build && cd build \
  && cmake -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/opt/mozjpeg \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    .. \
  && cmake --build . -j$(nproc) \
  && cmake --install . \
  && rm -rf /tmp/mozjpeg

# ---- Builder stage: download tools + install Python deps ----
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.13.0 AS builder

# Install uv in builder only
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# gmt (GMapTool) 0.8.220 — for .img merging/splitting
# https://www.gmaptool.eu
RUN python3 -c "import urllib.request; urllib.request.urlretrieve('https://www.gmaptool.eu/sites/default/files/lgmt08220.zip', 'lgmt08220.zip')" \
  && unzip lgmt08220.zip \
  && mv gmt /usr/local/bin/gmt \
  && chmod +x /usr/local/bin/gmt \
  && rm lgmt08220.zip

# mkgmap r4924 — optional, for vector .img generation
# https://www.mkgmap.org.uk
# Build with --build-arg INSTALL_MKGMAP=1 to include
ARG INSTALL_MKGMAP=0
RUN if [ "$INSTALL_MKGMAP" = "1" ]; then \
  python3 -c "import urllib.request; urllib.request.urlretrieve('https://www.mkgmap.org.uk/download/mkgmap-r4924.zip', 'mkgmap-r4924.zip')" \
  && unzip mkgmap-r4924.zip \
  && mv mkgmap-r4924/mkgmap.jar /opt/mkgmap.jar \
  && rm -rf mkgmap-r4924 mkgmap-r4924.zip; \
  else \
  touch /opt/mkgmap.jar; \
  fi

# Install Python deps into a venv
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
RUN uv venv /app/.venv --system-site-packages && uv sync --no-dev \
  && uv cache clean

# ---- Runtime stage ----
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.13.0

# System deps: osmium (OSM processing), optionally Java (mkgmap)
ARG INSTALL_MKGMAP=0
RUN apt-get update && apt-get install -y --no-install-recommends \
  osmium-tool \
  $([ "$INSTALL_MKGMAP" = "1" ] && echo "default-jre-headless") \
  && rm -rf /var/lib/apt/lists/*

# Strip docs (after apt so Java postinst can create man symlinks)
RUN rm -rf /usr/share/doc /usr/share/man

# Copy tools from builder
COPY --from=builder /usr/local/bin/gmt /usr/local/bin/gmt
COPY --from=builder /opt/mkgmap.jar /opt/mkgmap.jar

# Copy mozjpeg cjpeg binary (trellis quantization for smaller JPEG tiles)
COPY --from=mozjpeg /opt/mozjpeg/bin/cjpeg /usr/local/bin/cjpeg

# Remove mkgmap placeholder if it wasn't built with INSTALL_MKGMAP=1
RUN if [ "$INSTALL_MKGMAP" != "1" ]; then rm -f /opt/mkgmap.jar; fi

# Copy app with pre-built venv (no uv needed at runtime)
COPY --from=builder /app /app

# Use venv python directly — no uv at runtime
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app
ENTRYPOINT ["cartoload"]
