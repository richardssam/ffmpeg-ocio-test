"""Format negotiation tests for FFmpeg's ocio filter.

These cover the pixel format the filter negotiates rather than the accuracy of
the colour transform, so they use an identity transform (the same colour space
in and out) and check the negotiated formats and the resulting pixel values.

Run with:
    pytest ocionegotiation.py -v
"""

import os
import re
import struct
import subprocess

import pytest

FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")
OCIO_CONFIG = "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio"
HALF_SOURCE = "sourcemedia/ocean_clean_16.exr"

testoutputdir = "./output"
if not os.path.exists(testoutputdir):
    os.makedirs(testoutputdir)

# An identity transform: same colour space in and out. Keeps these tests
# independent of the OCIO version's transform maths.
OCIO_IDENTITY = f"ocio=config={OCIO_CONFIG}:input=ACEScg:output=ACEScg"

# 4x4 frames of a single colour, written on demand so no binary fixtures are
# needed in the repository.
RGB24_PIXEL = bytes([64, 128, 192])
RGBA_PIXEL = bytes([64, 128, 192, 255])


def _raw_source(name, pixel, count=16):
    path = os.path.join(testoutputdir, name)
    with open(path, "wb") as handle:
        handle.write(pixel * count)
    return path


def run_ffmpeg(args, log_file=None, expect_success=True):
    """Run FFMPEG_BIN with args (a list) and return the CompletedProcess."""
    cmd = [FFMPEG_BIN, "-hide_banner", "-nostdin", "-y"] + args
    print("Running: " + " ".join(cmd), file=os.sys.stderr)

    result = subprocess.run(cmd, capture_output=True)

    if log_file:
        with open(log_file, "w") as handle:
            handle.write(" ".join(cmd) + "\n")
            handle.write(f"Return code: {result.returncode}\n")
            handle.write(result.stderr.decode(errors="replace"))

    if expect_success:
        assert result.returncode == 0, (
            f"ffmpeg failed ({result.returncode}): {' '.join(cmd)}\n"
            f"{result.stderr.decode(errors='replace')[-2000:]}"
        )
    return result


def negotiated_formats(stderr):
    """Return [(input_format, output_format), ...] for each ocio instance."""
    pattern = re.compile(
        r"Configuring OCIO for (\w+) \(bit depth: \d+, channels: \d+\), "
        r"output format: \((\w+)\)"
    )
    return pattern.findall(stderr)


def planar_alpha(path, width=4, height=4):
    """Return the alpha plane of a planar float (gbrapf32le) raw frame."""
    data = open(path, "rb").read()
    count = width * height
    values = struct.unpack("<%df" % (len(data) // 4), data)
    return list(values[3 * count:4 * count])


# --------------------------------------------------------------------------
# Crash regressions
# --------------------------------------------------------------------------

def test_alpha_mode_conversion_does_not_crash():
    """An alpha-mode converter on the input must not crash the graph.

    The filter delays publishing its output formats, so it has to publish the
    input colour space, range and alpha mode lists in the meantime; otherwise
    inserting a converter dereferences a null format list.
    """
    source = _raw_source("negotiation_rgba.raw", RGBA_PIXEL)
    log_file = os.path.join(testoutputdir, "negotiation_alpha_mode.log")

    result = run_ffmpeg([
        "-f", "rawvideo", "-pixel_format", "rgba", "-video_size", "4x4",
        "-alpha_mode", "straight", "-i", source,
        "-vf", f"{OCIO_IDENTITY},format=alpha_modes=premultiplied",
        "-frames:v", "1", "-f", "null", "-",
    ], log_file=log_file, expect_success=False)

    assert result.returncode >= 0, "ffmpeg terminated by a signal (crash)"
    assert result.returncode == 0, (
        f"alpha-mode conversion failed: "
        f"{result.stderr.decode(errors='replace')[-2000:]}"
    )


def test_chained_filters_without_auto_conversion():
    """Consecutive ocio filters must agree on a format without a converter.

    The filter must wait for its input list to be merged before choosing the
    default output, otherwise the second instance selects float output while
    still looking at its own unmerged list.
    """
    source = _raw_source("negotiation_rgb24.raw", RGB24_PIXEL)
    log_file = os.path.join(testoutputdir, "negotiation_chained.log")

    result = run_ffmpeg([
        "-noauto_conversion_filters",
        "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", "4x4",
        "-i", source, "-v", "verbose",
        "-vf", f"{OCIO_IDENTITY},{OCIO_IDENTITY},format=rgb24",
        "-frames:v", "1", "-f", "null", "-",
    ], log_file=log_file)

    formats = negotiated_formats(result.stderr.decode(errors="replace"))
    assert formats == [("rgb24", "rgb24"), ("rgb24", "rgb24")], formats


# --------------------------------------------------------------------------
# Alpha handling
# --------------------------------------------------------------------------

@pytest.mark.parametrize("out_format,expected", [
    ("rgba", 255),
    ("rgba64", 65535),
    ("gbrap10", 1023),
    ("gbrap12", 4095),
])
def test_opaque_alpha_added_for_integer_formats(out_format, expected):
    """Input without alpha must produce opaque alpha, not a transparent frame."""
    source = _raw_source("negotiation_rgb24.raw", RGB24_PIXEL)
    out_file = os.path.join(testoutputdir, f"negotiation_alpha_{out_format}.raw")
    log_file = os.path.join(testoutputdir, f"negotiation_alpha_{out_format}.log")

    run_ffmpeg([
        "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", "4x4",
        "-i", source,
        "-vf", f"{OCIO_IDENTITY}:format={out_format}",
        "-frames:v", "1", "-c:v", "rawvideo", "-f", "rawvideo", out_file,
    ], log_file=log_file)

    data = open(out_file, "rb").read()
    if out_format == "rgba":
        alpha = [data[i] for i in range(3, 16 * 4, 4)]
    elif out_format == "rgba64":
        alpha = [struct.unpack_from("<H", data, i)[0] for i in range(6, 16 * 8, 8)]
    else:
        # planar: G, B, R, A -- the alpha plane is last
        alpha = [struct.unpack_from("<H", data, i)[0]
                 for i in range(3 * 16 * 2, 4 * 16 * 2, 2)]

    assert alpha == [expected] * 16, f"{out_format}: {alpha[:4]}"


def test_opaque_alpha_added_for_float_format():
    source = _raw_source("negotiation_rgb24.raw", RGB24_PIXEL)
    out_file = os.path.join(testoutputdir, "negotiation_alpha_gbrapf32.raw")
    log_file = os.path.join(testoutputdir, "negotiation_alpha_gbrapf32.log")

    run_ffmpeg([
        "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", "4x4",
        "-i", source,
        "-vf", f"{OCIO_IDENTITY}:format=gbrapf32",
        "-frames:v", "1", "-c:v", "rawvideo", "-f", "rawvideo", out_file,
    ], log_file=log_file)

    assert planar_alpha(out_file) == [1.0] * 16


def test_opaque_alpha_through_negotiated_output():
    """The same, but with the alpha format chosen by negotiation.

    A downstream constraint can give the filter a four-component output for a
    three-component input without format= being set.
    """
    source = _raw_source("negotiation_rgb24.raw", RGB24_PIXEL)
    out_file = os.path.join(testoutputdir, "negotiation_alpha_negotiated.raw")
    log_file = os.path.join(testoutputdir, "negotiation_alpha_negotiated.log")

    run_ffmpeg([
        "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", "4x4",
        "-i", source,
        "-vf", f"zscale,{OCIO_IDENTITY},format=gbrapf32le",
        "-frames:v", "1", "-c:v", "rawvideo", "-f", "rawvideo", out_file,
    ], log_file=log_file)

    assert planar_alpha(out_file) == [1.0] * 16


def test_existing_alpha_is_preserved():
    source = _raw_source("negotiation_rgba.raw", RGBA_PIXEL)
    out_file = os.path.join(testoutputdir, "negotiation_alpha_preserved.raw")
    log_file = os.path.join(testoutputdir, "negotiation_alpha_preserved.log")

    run_ffmpeg([
        "-f", "rawvideo", "-pixel_format", "rgba", "-video_size", "4x4",
        "-i", source,
        "-vf", f"{OCIO_IDENTITY}:format=gbrapf32",
        "-frames:v", "1", "-c:v", "rawvideo", "-f", "rawvideo", out_file,
    ], log_file=log_file)

    assert planar_alpha(out_file) == [1.0] * 16


# --------------------------------------------------------------------------
# Negotiated formats
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name,graph,expected", [
    # Without format=, an integer input passes through unchanged.
    ("passthrough_rgb24", "format=rgb24,{ocio}", [("rgb24", "rgb24")]),
    ("passthrough_gbrap12", "format=gbrap12,{ocio}", [("gbrap12le", "gbrap12le")]),
    # A downstream constraint reaches the input, so no conversion is needed.
    ("downstream_rgb48", "scale,{ocio},format=rgb48", [("rgb48le", "rgb48le")]),
    # format= wins over the default.
    ("explicit_rgba64", "format=rgb24,{ocio}:format=rgba64", [("rgb24", "rgba64le")]),
])
def test_negotiated_format_from_integer_input(name, graph, expected):
    log_file = os.path.join(testoutputdir, f"negotiation_{name}.log")

    result = run_ffmpeg([
        "-f", "lavfi", "-i", "testsrc2=s=64x64:d=0.04", "-v", "verbose",
        "-vf", graph.format(ocio=OCIO_IDENTITY),
        "-frames:v", "1", "-f", "null", "-",
    ], log_file=log_file)

    assert negotiated_formats(result.stderr.decode(errors="replace")) == expected


@pytest.mark.parametrize("name,graph,expected", [
    # Half-float input is promoted to float, as F16 is not a valid output.
    ("half_default", "{ocio}", [("gbrpf16le", "gbrpf32le")]),
    # Still promoted when something downstream wants an integer format: the
    # conversion happens after the filter rather than before it.
    ("half_downstream_rgb48", "{ocio},format=rgb48", [("gbrpf16le", "gbrpf32le")]),
    # Behind zscale, which offers half-float and integer formats alike.
    ("half_zscale", "zscale,{ocio}", [("gbrpf16le", "gbrpf32le")]),
    ("half_zscale_rgb48", "zscale,{ocio},format=rgb48", [("gbrpf16le", "gbrpf32le")]),
    # An explicit format is still honoured for half-float input.
    ("half_explicit_rgba64", "{ocio}:format=rgba64", [("gbrpf16le", "rgba64le")]),
])
def test_half_float_promoted_to_float(name, graph, expected):
    if not os.path.exists(HALF_SOURCE):
        pytest.skip(f"{HALF_SOURCE} not present")

    log_file = os.path.join(testoutputdir, f"negotiation_{name}.log")

    result = run_ffmpeg([
        "-i", HALF_SOURCE, "-v", "verbose",
        "-vf", graph.format(ocio=OCIO_IDENTITY),
        "-frames:v", "1", "-f", "null", "-",
    ], log_file=log_file)

    assert negotiated_formats(result.stderr.decode(errors="replace")) == expected


def test_half_float_values_survive_the_filter():
    """Half-float values outside [0,1] must not be clamped.

    swscale's legacy half-float read path clamps to [0,1], which is why the
    filter promotes half-float input to float rather than letting a converter
    handle it.
    """
    if not os.path.exists(HALF_SOURCE):
        pytest.skip(f"{HALF_SOURCE} not present")

    out_file = os.path.join(testoutputdir, "negotiation_half_roundtrip.exr")
    log_file = os.path.join(testoutputdir, "negotiation_half_roundtrip.log")

    run_ffmpeg([
        "-i", HALF_SOURCE, "-vf", OCIO_IDENTITY,
        "-frames:v", "1", "-format", "half", out_file,
    ], log_file=log_file)

    diff = subprocess.run(
        ["oiiotool", HALF_SOURCE, out_file, "--diff"],
        capture_output=True,
    )
    report = diff.stdout.decode(errors="replace")
    assert "PASS" in report, report
