import subprocess
import os
import pytest
import re

testoutputdir = "./output"
if not os.path.exists(testoutputdir):
    os.makedirs(testoutputdir)

PSNR_RESULTS = []

@pytest.fixture(scope="session", autouse=True)
def print_psnr_summary():
    yield
    print("\n\n" + "=" * 80)
    print(f"{'Test':<20} | {'FFmpeg Output File':<50} | {'PSNR':<8} | {'Min PSNR':<8} | {'Status'}")
    print("-" * 100)
    for res in PSNR_RESULTS:
        status = "PASS" if res['passed'] else "FAIL"
        print(f"{res['test']:<20} | {res['file']:<50} | {res['psnr']:>8.2f} | {res['min_psnr']:>8.2f} | {status}")
    print("=" * 80 + "\n")

def run_cmd(cmd, log_file=None):
    msg = f"Running command: {cmd}\n"
    print(msg, file=os.sys.stderr)
    
    if log_file:
        with open(log_file, "a") as f:
            f.write(msg)

    result = subprocess.run(cmd, shell=True, capture_output=True)
    
    output_log = f"Return Code: {result.returncode}\nSTDOUT:\n{result.stdout.decode()}\nSTDERR:\n{result.stderr.decode()}\n"
    
    if log_file:
        with open(log_file, "a") as f:
            f.write(output_log)

    assert result.returncode == 0, f"Command failed: {cmd}\n{result.stderr.decode()}"
    return result

def psnr_comparison(file1, file2, max_psnr_allowed, testname, log_file=None):
    """
    Compares two Y4M video files using FFmpeg's psnr filter and checks if
    the average Mean Squared Error (MSE) is below a specified threshold.
    """
    assert os.path.isfile(file1), f"psnr_comparison:File not found: {file1}"
    assert os.path.isfile(file2), f"psnr_comparison:File not found: {file2}"
    
    msg = f"Comparing '{file1}' with '{file2}' for MSE > {max_psnr_allowed}\n"
    print(msg, file=os.sys.stderr)
    if log_file:
        with open(log_file, "a") as f:
            f.write(msg)

    ffmpeg_path = "ffmpeg" # Use the hardcoded FFmpeg path from other tests
    ffmpeg_cmd_str = (            
        f"{ffmpeg_path} -i {file1} -i {file2} "
        f"-filter_complex \"[0:v][1:v]psnr\" -f null -"
    )

    msg = f"Running command: {ffmpeg_cmd_str}\n"
    print(msg, file=os.sys.stderr)
    if log_file:
        with open(log_file, "a") as f:
            f.write(msg)
            
    # Execute FFmpeg. We capture stderr to parse the PSNR/MSE output.
    # We use shell=True for consistency with other run_cmd calls in this file.
    # text=True ensures stdout/stderr are strings.
    result = subprocess.run(ffmpeg_cmd_str, shell=True, capture_output=True, text=True)

    output_log = f"Return Code: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}\n"
    if log_file:
        with open(log_file, "a") as f:
            f.write(output_log)

    # Check if FFmpeg command itself failed (e.g., file not found, invalid arguments)
    if result.returncode != 0:
        pytest.fail(f"FFmpeg command failed with exit code {result.returncode}:\n"
                     f"Command: {ffmpeg_cmd_str}\n"
                     f"STDOUT:\n{result.stdout}\n"
                     f"STDERR:\n{result.stderr}")

    ffmpeg_output = result.stderr

    mse_avg = None
    # The psnr filter output line containing MSE looks like:
    # [Parsed_psnr_0 @ 0x...] PSNR y:XX.XX u:YY.YY v:ZZ.ZZ average:AA.AA min:BB.BB max:CC.CC mse_y:D.D mse_u:E.E mse_v:F.F mse_avg:G.G
    match = re.search(r"average:(\S+)", ffmpeg_output)

    if match:
        mse_avg = float(match.group(1))

    assert mse_avg is not None, (
        f"Could not extract average PSNR from FFmpeg output. "
        f"Ensure input files are valid Y4M and FFmpeg's psnr filter produced output.\n"
        f"FFmpeg STDERR:\n{ffmpeg_output}"
    )

    msg = f"Calculated average PSNR: {mse_avg}\n"
    print(msg, file=os.sys.stderr)
    if log_file:
        with open(log_file, "a") as f:
            f.write(msg)

    passed = mse_avg > max_psnr_allowed
    PSNR_RESULTS.append({
        'file': os.path.basename(file2),
        'psnr': mse_avg,
        'test': testname,
        'min_psnr': max_psnr_allowed,
        'passed': passed
    })

    if passed:
        msg = f"Comparison passed: Average PSNR ({mse_avg}) is greater than {max_psnr_allowed}.\n"
        print(msg, file=os.sys.stderr)
        if log_file:
            with open(log_file, "a") as f:
                f.write(msg)
    
    assert passed, (
        f"Comparison failed: Average PSNR ({mse_avg}) is not greater than "
        f"the allowed threshold ({max_psnr_allowed})."
    )



@pytest.mark.parametrize("testname, input_file, outputext, ocio_config, input_space, output_space, format, min_psnr", [
    ("exr16ACEScct24", "sourcemedia/ocean_clean_16.exr", "tif", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScg", "ACEScct", "rgb24", 52.0),
    ("exr16ACEScct48", "sourcemedia/ocean_clean_16.exr", "tif", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScg", "ACEScct", "rgb48", 100.0),
    ("exr32ACEScct", "sourcemedia/ocean_clean_32.exr", "tif", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScg", "ACEScct", "rgb48", 100.0),
    ("dpx16ACEScct", "sourcemedia/ocean_clean_16_ACEScct.dpx", "tif", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScc", "ACEScct", "rgba24", 52.0),
    ("png8simpleocean", "sourcemedia/ocean_oiio_raw8.png", "tif", "sourcemedia/simpleconfig.ocio", "Linear", "Gamma2.2", "rgb24", 100.0),
    ("dpx16simpleocean", "sourcemedia/ocean_clean_16_ACEScct.dpx", "tif", "sourcemedia/simpleconfig.ocio", "Linear", "Gamma2.2", "rgb48", 100.0),
    ("dpx16simpleocean2", "sourcemedia/ocean_clean_16_ACEScct.dpx", "tif", "sourcemedia/simpleconfig.ocio", "Linear", "TestCDL", "rgb48", 100.0),
    ("dpx16simpleocean3", "sourcemedia/ocean_clean_16_ACEScct.dpx", "tif", "sourcemedia/simpleconfig.ocio", "Linear", "TestCDL2", "rgb48", 100.0),
    #("png16simple", "/Users/sam/git/EncodingGuidelines/sourceimages/chip-chart-1080-16bit-noicc.png", "tif", "sourcemedia/simpleconfig.ocio", "Linear", "TestCDL", "rgba64", 100.0),
    ("dpx16simple", "sourcemedia/chip-chart-1080-16bit-noicc.dpx", "tif", "sourcemedia/simpleconfig.ocio", "Linear", "TestCDL", "rgb48", 100.0),
    ("dpx16simple2", "sourcemedia/chip-chart-1080-16bit-noicc.dpx", "tif", "sourcemedia/simpleconfig.ocio", "Linear", "TestCDL2", "rgb48", 100.0),
    ## Add more parameter sets as needed
])
def test_ocio_colorspace_vs_oiiotool(testname, input_file, outputext, ocio_config, input_space, output_space, format, min_psnr):
    """Compare OpenColorIO color transformations between FFmpeg and oiiotool."""
    oiiotool_out = os.path.join(testoutputdir, f"{testname}_oiiotool_{format}_{output_space}.{outputext}")
    ffmpeg_out = os.path.join(testoutputdir, f"{testname}_ffmpeg_{format}_{output_space}.{outputext}")
    log_file = os.path.join(testoutputdir, f"{testname}_{format}_{output_space.replace(' ', '_')}.log")
    
    # Clear log file
    with open(log_file, "w") as f:
        f.write(f"Test: {testname}\nFormat: {format}\n\n")

    if format in ("rgb48", "rgba64"):
        oiioformat = "uint16"
    elif format in ("gbrpf16", "gbrapf16"):
        oiioformat = "half"
    elif format in ("gbrpf32", "gbrapf32"):
        oiioformat = "float"
    else:
        oiioformat = "uint8"

    # oiiotool command
    oiiotool_cmd = (
        f"oiiotool {input_file} "
        f"--colorconfig {ocio_config} "
        f"--colorconvert '{input_space}' '{output_space}' "
        f"-d {oiioformat} "
        f"-o {oiiotool_out}"
    )
    run_cmd(oiiotool_cmd, log_file)

    # ffmpeg command
    ffmpeg_cmd = (
        f"ffmpeg -y -i {input_file} -sws_dither none "
        f"-vf \"ocio=config={ocio_config}:input={input_space}:output={output_space}:format={format}\" "
        f"{ffmpeg_out}"
    )
    run_cmd(ffmpeg_cmd, log_file)

    psnr_comparison(oiiotool_out, ffmpeg_out, max_psnr_allowed=min_psnr, testname=testname, log_file=log_file)



@pytest.mark.parametrize("testname, input_file, outputext, ocio_config, input_space, display, view, format, min_psnr", [
    ("exr16rgb24", "sourcemedia/ocean_clean_16.exr", "tif", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScg", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb24", 52.0),
    ("exr16rgb48", "sourcemedia/ocean_clean_16.exr", "tif", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScg", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48", 100.0),
    #("exr16", "sourcemedia/ocean_clean_16.exr", "exr", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScg", "sRGB - Display", "ACES 1.0 - SDR Video", "gbrapf32le", 100.0),
    ("exr32rgb48", "sourcemedia/ocean_clean_32.exr", "tif", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScg", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48", 100.0),
    ("exr32exr32", "sourcemedia/ocean_clean_32.exr", "exr", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScg", "sRGB - Display", "ACES 1.0 - SDR Video", "gbrpf32le", 100.0),
    #("exr32rgb48le", "sourcemedia/ocean_clean_32.exr", "exr", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScg", "sRGB - Display", "ACES 1.0 - SDR Video", "gbrapf32le", 100.0),
    ("dpx10rgb48le", "sourcemedia/ocean_clean_10_ACEScct.dpx", "tif","sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScct", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48", 95.0),
    ("dpx12rgb48le", "sourcemedia/ocean_clean_12_ACEScct.dpx", "tif", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScct", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48", 95.0),
    ("dpx16rgb48le", "sourcemedia/ocean_clean_16_ACEScct.dpx", "tif", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScct", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48", 100.0),
    # Add more parameter sets as needed
])
def test_ocio_vs_oiiotool(testname, input_file, outputext, ocio_config, input_space, display, view, format, min_psnr):
    """Compare OpenColorIO color transformations between FFmpeg and oiiotool."""
    oiiotool_out = os.path.join(testoutputdir, f"{testname}_oiiotool_{format}.{outputext}")
    ffmpeg_out = os.path.join(testoutputdir, f"{testname}_ffmpeg_{format}.{outputext}")
    log_file = os.path.join(testoutputdir, f"{testname}_{format}_display.log")

    # Clear log file
    with open(log_file, "w") as f:
        f.write(f"Test: {testname}\nFormat: {format}\n\n")

    if format in ("rgb48", "rgba64"):
        oiioformat = "uint16"
    elif format in ("gbrpf16le", "gbrapf16le"):
        oiioformat = "half"
    elif format in ("gbrpf32le", "gbrapf32le"):
        oiioformat = "float"
    else:
        oiioformat = "uint8"

    # oiiotool command
    oiiotool_cmd = (
        f"oiiotool {input_file} "
        f"--colorconfig {ocio_config} "
        f"--iscolorspace '{input_space}' "
        f"--ociodisplay '{display}' '{view}' "
        f"-d {oiioformat} "
        f"-o {oiiotool_out}"
    )
    run_cmd(oiiotool_cmd, log_file)

    # ffmpeg command
    ffmpeg_cmd = (
        f"ffmpeg -y -i {input_file}  -sws_dither none "
        f"-vf \"ocio=config={ocio_config}:input={input_space}:display={display}:view={view}:format={format}\" "
        f"{ffmpeg_out}"
    )
    run_cmd(ffmpeg_cmd, log_file)

    psnr_comparison(oiiotool_out, ffmpeg_out, max_psnr_allowed=min_psnr, testname=testname, log_file=log_file)

@pytest.mark.parametrize("testname, input_file, outputext, ocio_config, input_space, display, view, format, min_psnr", [
    #("exr32rgb48le", "sourcemedia/ocean_clean_32.exr", "exr", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScg", "sRGB - Display", "ACES 1.0 - SDR Video", "gbrapf32le", 100.0),
    ("dpx10rgb48leinvert", "sourcemedia/ocean_clean_10_ACEScct.dpx", "tif","sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScct", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48", 95.0),
    ("dpx12rgb48leinvert", "sourcemedia/ocean_clean_12_ACEScct.dpx", "tif", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScct", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48", 95.0),
    ("dpx16rgb48leinvert", "sourcemedia/ocean_clean_16_ACEScct.dpx", "tif", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScct", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48", 100.0),
    # Add more parameter sets as needed
])
def test_ocio_invert_vs_oiiotool(testname, input_file, outputext, ocio_config, input_space, display, view, format, min_psnr):
    """Compare OpenColorIO color transformations between FFmpeg and oiiotool."""
    oiiotool_out = os.path.join(testoutputdir, f"{testname}_oiiotool_{format}.{outputext}")
    ffmpeg_out = os.path.join(testoutputdir, f"{testname}_ffmpeg_{format}.{outputext}")
    log_file = os.path.join(testoutputdir, f"{testname}_{format}_display.log")

    # Clear log file
    with open(log_file, "w") as f:
        f.write(f"Test: {testname}\nFormat: {format}\n\n")

    if format in ("rgb48", "rgba64"):
        oiioformat = "uint16"
    elif format in ("gbrpf16le", "gbrapf16le"):
        oiioformat = "half"
    elif format in ("gbrpf32le", "gbrapf32le"):
        oiioformat = "float"
    else:
        oiioformat = "uint8"

    # oiiotool command
    oiiotool_cmd = (
        f"oiiotool {input_file} "
        f"--colorconfig {ocio_config} "
        f"--iscolorspace '{input_space}' "
        f"--ociodisplay:inverse=1 '{display}' '{view}' "
        f"-d {oiioformat} "
        f"-o {oiiotool_out}"
    )
    run_cmd(oiiotool_cmd, log_file)

    # ffmpeg command
    ffmpeg_cmd = (
        f"ffmpeg -y -i {input_file}  -sws_dither none "
        f"-vf \"ocio=config={ocio_config}:input={input_space}:display={display}:view={view}:inverse=1:format={format}\" "
        f"{ffmpeg_out}"
    )
    run_cmd(ffmpeg_cmd, log_file)

    psnr_comparison(oiiotool_out, ffmpeg_out, max_psnr_allowed=min_psnr, testname=testname, log_file=log_file)



@pytest.mark.parametrize("testname, input_file, outputext, ocio_config, input_space, display, view, format, out_format, min_psnr, compression, yuvoutputext", [
    ("exr162y4m10", "sourcemedia/ocean_clean_16.exr", "tif", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScg", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48", "yuv444p10", 100.0, "", "y4m"),
    ("exr162y4m12", "sourcemedia/ocean_clean_16.exr", "tif", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScg", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48", "yuv444p12", 100.0, "", "y4m"),
    #("exr162mp410", "sourcemedia/ocean_clean_16.exr", "tif", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScg", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48", "yuv444p10", 100.0, "-c:v libx265 -x265-params -color_range tv -colorspace bt709 -color_primaries bt709 -color_trc iec61966-2-1 ", "mp4"),
    ("exr162mp410h265yuv444p10", "sourcemedia/ocean_clean_16.exr", "tif", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScg", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48", "yuv444p10", 100.0, "-c:v libx265 -x265-params lossless=1 -color_range tv -colorspace bt709 -color_primaries bt709 -color_trc iec61966-2-1 ", "mp4"),
    ("exr162mp412h265yuv444p12", "sourcemedia/ocean_clean_16.exr", "tif", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScg", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48", "yuv444p12", 100.0, "-c:v libx265 -x265-params lossless=1 -color_range tv -colorspace bt709 -color_primaries bt709 -color_trc iec61966-2-1 ", "mp4"),
    ("dpx102y4m10", "sourcemedia/ocean_clean_10_ACEScct.dpx", "tif", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScct", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48" ,  "yuv444p10" , 82.0, "", "y4m"),
    ("dpx102y4m10", "sourcemedia/ocean_clean_10_ACEScct.dpx", "tif", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScct", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48" ,  "yuv444p10" , 82.0, "", "y4m"),
    ("dpx122y4m10" , "sourcemedia/ocean_clean_12_ACEScct.dpx" , "tif" , "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScct", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48" ,  "yuv444p10" , 82.0, "", "y4m"),
    ("dpx102mp410", "sourcemedia/ocean_clean_10_ACEScct.dpx", "dpx", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScct", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48" ,  "rgb48" , 82.0, "-c:v libx265 -x265-params lossless=1 ", "mp4"),
    ("dpx102mp4yuv10", "sourcemedia/ocean_clean_10_ACEScct.dpx", "dpx", "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScct", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48" ,  "yuv444p10le" , 82.0, "-c:v libx265 -x265-params lossless=1 -color_range tv -colorspace bt709 -color_primaries bt709 -color_trc iec61966-2-1 ", "mp4"),
    #("dpx122mp410" , "sourcemedia/ocean_clean_12_ACEScct.dpx" , "dpx" , "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScct", "sRGB - Display", "ACES 1.0 - SDR Video", "gbrp10le" ,  "gbrp10le" , 82.0, "-c:v ffv1", "mp4"),
    #("tif122mp412" , "sourcemedia/ocean_clean_12_ACEScct.tif" , "tif" , "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScct", "sRGB - Display", "ACES 1.0 - SDR Video", "gbrp10le" ,  "gbrp12le" , 82.0, "-c:v ffv1", "mp4"),
    #("dpx162mp416" , "sourcemedia/ocean_clean_16_ACEScct.dpx" , "dpx" , "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScct", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48" ,  "gbrp16le" , 82.0, "-c:v libx265 -x265-params -color_range tv -colorspace bt709 -color_primaries bt709 -color_trc iec61966-2-1 ", "mp4"),
    #("png162mp4yuv16" , "sourcemedia/ocean_clean_16_ACEScct.png" , "png" , "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScct", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48" ,  "yuv444p16le" , 82.0, "-c:v libx265 -x265-params -color_range tv -colorspace bt709 -color_primaries bt709 -color_trc iec61966-2-1 ", "mp4"),
    #("y4m2tif" , "sourcemedia/ocean_clean_16_ACEScct.y4m" , "tif" , "sourcemedia/studio-config-v1.0.0_aces-v1.3_ocio-v2.1_ns.ocio", "ACEScct", "sRGB - Display", "ACES 1.0 - SDR Video", "rgb48" ,  "yuv444p12" , 82.0, "", "y4m"),
    # Add more parameter sets as needed
])
def test_ocio_vs_oiiotool_2_yuv444(testname, input_file, outputext, ocio_config, input_space, display, view, format, out_format, min_psnr, compression, yuvoutputext):
    """Compare OpenColorIO color transformations between FFmpeg and oiiotool."""
    oiiotool_out = os.path.join(testoutputdir, f"{testname}_oiiotool_{format}.{outputext}")
    yuv_oiiotool_out = os.path.join(testoutputdir, f"{testname}_oiiotool_{format}.{yuvoutputext}")
    ffmpeg_out = os.path.join(testoutputdir, f"{testname}_ffmpeg_{format}.{yuvoutputext}")
    log_file = os.path.join(testoutputdir, f"{testname}_{format}_yuv.log")

    # Clear log file
    with open(log_file, "w") as f:
        f.write(f"Test: {testname}\nFormat: {format}\n\n")

    if format in ("rgb48", "rgba64", "gbrp16le"):
        oiioformat = "uint16"
    elif format in ("gbrp10le"):
        oiioformat = "uint10"
    elif format in ("gbrp12le"):
        oiioformat = "uint12"
    elif format in ("gbrpf16le", "gbrapf16le"):
        oiioformat = "half"
    elif format in ("gbrpf32le", "gbrapf32le"):
        oiioformat = "float"
    else:
        oiioformat = "uint8"

    yuvconvert = "scale=in_color_matrix=bt709:sws_dither=none:out_color_matrix=bt709,"
    if "yuv" not in out_format:
        yuvconvert = ""

    # ffmpeg command
    ffmpeg_cmd = (
        f"ffmpeg -y -i {input_file} "
        f"-vf \"ocio=config={ocio_config}:input={input_space}:display={display}:view={view}:format={format},{yuvconvert}format={out_format}\" "
        f" -strict -1 {compression} "
        f"{ffmpeg_out}"
    )
    run_cmd(ffmpeg_cmd, log_file)


    # oiiotool command
    oiiotool_cmd = (
        f"oiiotool {input_file} "
        f"--colorconfig {ocio_config} "
        f"--iscolorspace '{input_space}' "
        f"--ociodisplay '{display}' '{view}' "
        f"-d {oiioformat} "
        f"-o {oiiotool_out}"
    )
    run_cmd(oiiotool_cmd, log_file)

    if yuvconvert != "":
        yuvconvert = f" -vf {yuvconvert[0:-1]} "

    ffmpeg_oiio_cmd = (
        f"ffmpeg -y -i {oiiotool_out} "
        f"-pix_fmt {out_format} {yuvconvert} {compression} -strict -1 "
        f"{yuv_oiiotool_out}"
    )
    run_cmd(ffmpeg_oiio_cmd, log_file)

    psnr_comparison(yuv_oiiotool_out, ffmpeg_out, max_psnr_allowed=min_psnr, testname=testname, log_file=log_file)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__]))

