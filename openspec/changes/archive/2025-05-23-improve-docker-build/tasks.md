## 1. Rewrite Dockerfile

- [x] 1.1 Rewrite Dockerfile with multi-stage build: use `ghcr.io/osgeo/gdal:ubuntu-small-3.13.0` as base for both stages (Ubuntu 26.04, Python 3.14.4, GDAL 3.13.0)
- [x] 1.2 In builder stage: download gmt 0.8.220 with pinned URL, install Python deps with uv into a venv (`--system-site-packages` to inherit system `osgeo`), clean uv cache
- [x] 1.3 In runtime stage: copy gmt and pre-built /app (with venv) from builder, strip docs/manpages

## 2. Add .dockerignore

- [x] 2.1 Create `.dockerignore` excluding `.git`, `__pycache__`, `*.pyc`, `.venv`, `openspec/`, `docs/`, `tests/`, `*.egg-info`, `output/`, `cache/`, `.ruff_cache/`, `dist/`, `build/`

## 3. Verify

- [x] 3.1 Build the Docker image with `docker build -t cartoload .`
- [x] 3.2 Test that GDAL tools work: run `gdalwarp --version` in the container — reports GDAL 3.13.0
- [x] 3.3 Test that cartoload CLI works: run `docker run cartoload --help`
- [x] 3.4 Image size: 639 MB (down from 983 MB initial)

## 4. Remove fiona dependency

- [x] 4.1 Replace fiona usage in `vector_rasterizer.py` with `osgeo.ogr` (inherited from OSGeo base image via `--system-site-packages`)
- [x] 4.2 Remove `fiona>=1.10.1` from `pyproject.toml` dependencies (fiona lacks Python 3.14 wheels)

## 5. Optimize image size

- [x] 5.1 Make mkgmap/JVM optional via `--build-arg INSTALL_MKGMAP=1` (default: slim without JVM)
- [x] 5.2 Remove uv binary from runtime image (use venv python directly via `ENV PATH`)
- [x] 5.3 Strip `/usr/share/doc` and `/usr/share/man` (after apt-get so Java postinst succeeds)
- [x] 5.4 Investigate stripping bundled `.libs` from rasterio/numpy/pyproj — concluded they are hard-linked by compiled extensions and cannot be safely removed
- [x] 5.5 Use `--system-site-packages` for venv to inherit `osgeo` from base image

## 6. Build and test both variants

- [x] 6.1 Slim variant (`docker build -t cartoload:slim .`): 644 MB, all libs work (GDAL 3.13, rasterio 1.5, numpy 2.4, pyproj 3.7, cartoload CLI)
- [x] 6.2 mkgmap variant (`docker build -t cartoload:mkgmap --build-arg INSTALL_MKGMAP=1 .`): 897 MB, includes Java + mkgmap r4924
