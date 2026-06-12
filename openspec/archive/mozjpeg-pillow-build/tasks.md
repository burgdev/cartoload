## 1. Research and preparation

- [ ] 1.1 Verify mozjpeg builds successfully in the current Docker base image
- [ ] 1.2 Verify Pillow detects and uses mozjpeg when compiled against it (test with a simple Docker build)
- [ ] 1.3 Benchmark: encode 100 tiles with standard Pillow vs mozjpeg Pillow, measure size difference and encoding time

## 2. Docker build integration

- [ ] 2.1 Add mozjpeg build stage to Dockerfile: clone, cmake, make, install
- [ ] 2.2 Modify Pillow installation to build from source against mozjpeg (instead of using pre-built wheel)
- [ ] 2.3 Add a runtime check that logs which JPEG library is active (libjpeg-turbo vs mozjpeg)

## 3. Verify

- [ ] 3.1 Build Docker image and verify mozjpeg is active
- [ ] 3.2 Build a full map in Docker and compare output size vs non-mozjpeg build
- [ ] 3.3 Verify output works on GPS device (trellis quantization changes DCT coefficients — confirm device compatibility)
