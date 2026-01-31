# FFmpeg OpenColorIO Test Suite

A comprehensive test suite for validating FFmpeg's OpenColorIO (OCIO) filter implementation against the reference `oiiotool` implementation.

## Overview

This test suite compares FFmpeg's `ocio` video filter output against `oiiotool` (from OpenImageIO) to ensure color transformations are accurate. It uses PSNR (Peak Signal-to-Noise Ratio) analysis to validate that FFmpeg produces results matching the reference implementation.

## Features

- **Colorspace Transformations**: Tests color space conversions (e.g., ACEScg → ACEScct)
- **Display/View Transforms**: Validates display and view transformations with ACES configs
- **Inverse Transforms**: Tests inverse display transformations
- **Context Parameters**: Verifies OCIO context parameter handling
- **File Transforms**: Tests LUT-based file transformations
- **Format Support**: Validates multiple pixel formats (8-bit, 10-bit, 12-bit, 16-bit, float)
- **YUV Conversion**: Tests RGB to YUV444 conversions with OCIO transforms
- **Comprehensive Logging**: Generates detailed logs for each test case

## Requirements

- Python 3.x
- pytest
- FFmpeg with OpenColorIO support (custom build)
- oiiotool (from OpenImageIO)
- Test media files in `sourcemedia/` directory

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd ffmpeg-ocio-test
```

2. Create and activate a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate  # On macOS/Linux
```

3. Install dependencies:
```bash
pip install pytest
```

4. Update the FFmpeg binary path in `ociotest.py`:
```python
FFMPEG_BIN = "/path/to/your/ffmpeg-with-ocio"
```

## Usage

### Run All Tests

```bash
pytest ociotest.py -v
```

### Run Specific Test Categories

```bash
# Colorspace conversion tests
pytest ociotest.py::test_ocio_colorspace_vs_oiiotool -v

# Display/view transform tests
pytest ociotest.py::test_ocio_vs_oiiotool -v

# Inverse transform tests
pytest ociotest.py::test_ocio_invert_vs_oiiotool -v

# Generic argument tests (including context params and file transforms)
pytest ociotest.py::test_ocio_args_vs_oiiotool -v

# YUV conversion tests
pytest ociotest.py::test_ocio_vs_oiiotool_2_yuv444 -v
```

### Run Specific Test Case

```bash
pytest ociotest.py::test_ocio_vs_oiiotool[exr16rgb24] -v
```

### View PSNR Summary

The test suite automatically generates a PSNR summary table at the end of the test run, showing:
- Test name
- Output file
- Calculated PSNR
- Minimum required PSNR
- Pass/fail status

## Test Structure

### Test Categories

1. **`test_ocio_colorspace_vs_oiiotool`**: Colorspace-to-colorspace conversions
   - Tests various input formats (EXR, DPX, PNG)
   - Validates different bit depths (8, 10, 12, 16, 32-bit)
   - Compares FFmpeg's `input`/`output` parameters against oiiotool's `--colorconvert`

2. **`test_ocio_vs_oiiotool`**: Display and view transformations
   - Tests ACES display transforms
   - Validates sRGB display output
   - Compares FFmpeg's `display`/`view` parameters against oiiotool's `--ociodisplay`

3. **`test_ocio_invert_vs_oiiotool`**: Inverse display transformations
   - Tests inverse display transforms
   - Validates the `inverse=1` parameter

4. **`test_ocio_args_vs_oiiotool`**: Generic OCIO operations
   - Tests OCIO context parameters
   - Tests file-based transforms (LUTs)
   - Flexible parameter testing

5. **`test_ocio_vs_oiiotool_2_yuv444`**: YUV conversion pipeline
   - Tests OCIO transform + RGB to YUV conversion
   - Validates various YUV formats (yuv444p10, yuv444p12)
   - Tests video encoding with color metadata

### Output

- **Test outputs**: `./output/` directory
  - Generated images from both FFmpeg and oiiotool
  - Detailed log files for each test case
  - PSNR comparison results

## Test Media

The `sourcemedia/` directory contains:
- **Test images**: EXR, DPX, PNG files at various bit depths
- **OCIO configs**: ACES studio config and simple test configs
- **LUT files**: Sample .spi1d files for file transform tests

## PSNR Thresholds

Tests use different PSNR thresholds based on bit depth and conversion complexity:
- **100.0 dB**: Lossless conversions (16-bit, 32-bit float)
- **95.0 dB**: High-quality conversions (10-bit, 12-bit)
- **82.0 dB**: YUV conversions (accounts for chroma subsampling)
- **52.0 dB**: 8-bit conversions (lower precision)

## Configuration

### FFmpeg Binary Path

Update `FFMPEG_BIN` in `ociotest.py`:
```python
FFMPEG_BIN = "/Users/sam/roots/ffmpeg-ocio-8.0/bin/ffmpeg"
```

### Custom Test Cases

Add new test cases by extending the `@pytest.mark.parametrize` decorators with additional parameter sets.

## Troubleshooting

### Tests Failing

1. Check that FFmpeg has OCIO support:
   ```bash
   ffmpeg -filters | grep ocio
   ```

2. Verify oiiotool is installed:
   ```bash
   which oiiotool
   ```

3. Check log files in `./output/` for detailed error messages

### Missing Source Media

Ensure all required test media files are present in `sourcemedia/`. The test will fail with "File not found" errors if media is missing.

## License

See [LICENSE](LICENSE) file for details.

## Notes

This test suite was created as a separate project because it requires external dependencies (oiiotool) and large media files that are not suitable for FFmpeg's FATE (FFmpeg Automated Testing Environment) test suite. A minimal subset of these tests may be adapted for FATE in the future.
