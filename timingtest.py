import time
import subprocess
import os
import sys
import threading
import io

os.environ["OCIO"] = "ocio://studio-config-v1.0.0_aces-v1.3_ocio-v2.1"

# Specify the location of the source EXR files and output directory
# This example uses the SPARKS ACES EXR sequence there is a download script in the
# Encoding Guidelines repository - https://github.com/AcademySoftwareFoundation/EncodingGuidelines
source_exrs = "/Users/sam/git/EncodingGuidelines/enctests/sources/hdr_sources/sparks/SPARKS_ACES_#.exr"
testoutputdir = "./outputtimingtest"
logfile = "timing_test_log.txt"

#codec_params = "-c:v prores_ks -pix_fmt yuv422p10le -profile:v 3 -vendor apl0" 
#codec_params = "-c:v libx265 -pix_fmt yuv444p10le -x265-params lossless=1"
codec_params = "-c:v ffv1 -pix_fmt yuv444p10le"

ffmpeg_threads = [ 1,2,4, 6, 8]
def run_cmd(cmd, log_file=None):
    msg = f"Running command: {cmd}\n"
    print(msg, file=os.sys.stderr)

    if log_file:
        with open(log_file, "a") as f:
            f.write(msg)

    process = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
        universal_newlines=True,
    )

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    def _reader(pipe, buf, label):
        try:
            for line in iter(pipe.readline, ''):
                # Print live to stderr and append to buffers/log
                print(line, end='', file=os.sys.stderr)
                buf.write(line)
                if log_file:
                    with open(log_file, "a") as lf:
                        lf.write(f"{label}: {line}")
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    t_out = threading.Thread(target=_reader, args=(process.stdout, stdout_buf, "STDOUT"), daemon=True)
    t_err = threading.Thread(target=_reader, args=(process.stderr, stderr_buf, "STDERR"), daemon=True)
    t_out.start()
    t_err.start()

    returncode = process.wait()

    t_out.join()
    t_err.join()

    output_log = (
        f"Return Code: {returncode}\n"
        f"STDOUT:\n{stdout_buf.getvalue()}\n"
        f"STDERR:\n{stderr_buf.getvalue()}\n"
    )

    if log_file:
        with open(log_file, "a") as f:
            f.write(output_log)

    assert returncode == 0, f"Command failed: {cmd}\n{stderr_buf.getvalue()}"

    # Return a CompletedProcess-like object for compatibility
    return subprocess.CompletedProcess(args=cmd, returncode=returncode, stdout=stdout_buf.getvalue().encode(), stderr=stderr_buf.getvalue().encode())



if not os.path.exists(testoutputdir):
    os.makedirs(testoutputdir)

t = time.time()
cmd = f"oiiotool -v --framepadding 5 --parallel-frames --frames 6100-6299 {source_exrs} --iscolorspace \"ACEScg\" --ociodisplay \"Rec.2100-PQ - Display\" \"ACES 1.1 - HDR Video (1000 nits & Rec.2020 lim)\" -d uint16 -o {testoutputdir}/sparks2_pq1000.#.png"
run_cmd(cmd)
oiiotool_elapsed = time.time() - t

t1 = time.time()
ffmpegcmd = f"ffmpeg -y -framerate 24 -start_number 6100 -i {testoutputdir}/sparks2_pq1000.%05d.png {codec_params} -vf \"scale=in_range=full:in_color_matrix=bt2020:out_range=tv:out_color_matrix=bt2020\" -color_range tv -color_trc smpte2084 -color_primaries bt2020 -colorspace bt2020nc {testoutputdir}/sparks2_pq1000_prores10bit.mov"
run_cmd(ffmpegcmd)
basic_ffmpeg_elapsed = time.time() - t1

elapsed = time.time() - t


thread_timing = {}

for threads in ffmpeg_threads:
    t = time.time()

    ffmpeg_source = source_exrs.replace("#", "%05d")

    ffmpegcmd = f"ffmpeg -y -framerate 24 -start_number 6100 -i {ffmpeg_source} {codec_params} -vf \"ocio=input=ACEScg:display=Rec.2100-PQ - Display:view=ACES 1.1 - HDR Video (1000 nits & Rec.2020 lim):format=rgb48:threads={threads},scale=in_range=full:in_color_matrix=bt2020:out_range=tv:out_color_matrix=bt2020\" -color_range tv -color_trc smpte2084 -color_primaries bt2020 -colorspace bt2020nc {testoutputdir}/sparks2_pq1000_prores10bit_threads{threads}.mov"
    run_cmd(ffmpegcmd)

    ffmpeg_elapsed = time.time() - t

    thread_timing[threads] = ffmpeg_elapsed


print(f"Elapsed time for oiiotool: {oiiotool_elapsed} seconds")
print(f"Elapsed time for basic ffmpeg: {basic_ffmpeg_elapsed} seconds")
print(f"Elapsed time for oiiotool + ffmpeg: {elapsed} seconds")

for threads, thread_time in thread_timing.items():
    print(f"Elapsed time for ffmpeg with {threads} threads: {thread_time} seconds")

#print(f"Elapsed time for parallel ffmpeg only: {parallel_ffmpeg_elapsed} seconds")
