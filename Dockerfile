FROM python:3.12-slim-bookworm

# System deps: GDAL, Java (mkgmap Phase 2), osmium (Phase 2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    python3-gdal \
    libgdal-dev \
    default-jre-headless \
    osmium-tool \
    wget \
    unzip \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# gmt (GMapTool) — for .img merging/splitting
# Pin version 0.8.220; check https://www.gmaptool.eu for updates
RUN wget -q https://www.gmaptool.eu/sites/default/files/lgmt08220.zip \
  && unzip lgmt08220.zip \
  && mv gmt /usr/local/bin/gmt \
  && chmod +x /usr/local/bin/gmt \
  && rm lgmt08220.zip

# mkgmap — for Phase 2 vector .img generation
RUN wget -q https://www.mkgmap.org.uk/download/mkgmap-latest.tar.gz \
  && tar -xzf mkgmap-latest.tar.gz \
  && mv mkgmap-*/mkgmap.jar /opt/mkgmap.jar \
  && rm -rf mkgmap-* mkgmap-latest.tar.gz

# uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN uv sync --no-dev

ENTRYPOINT ["uv", "run", "cartoload"]
