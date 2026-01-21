import time
import subprocess
import os
import sys
import threading
import io

os.environ["OCIO"] = "ocio://studio-config-v1.0.0_aces-v1.3_ocio-v2.1"

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


source_exrs = "/Users/sam/git/EncodingGuidelines/enctests/sources/hdr_sources/sparks/SPARKS_ACES_#.exr"
#source_exrs = "test_frames/frame.#.exr"
testoutputdir = "./outputtimingtest"
logfile = "timing_test_log.txt"

if not os.path.exists(testoutputdir):
    os.makedirs(testoutputdir)

t = time.time()
cmd = f"oiiotool -v --framepadding 5 --parallel-frames --frames 6100-6299 {source_exrs} --iscolorspace \"ACEScg\" --ociodisplay \"Rec.2100-PQ - Display\" \"ACES 1.1 - HDR Video (1000 nits & Rec.2020 lim)\" -d uint16 -o {testoutputdir}/sparks2_pq1000.#.png"
run_cmd(cmd)
oiiotool_elapsed = time.time() - t

t1 = time.time()
ffmpegcmd = "ffmpeg -y -framerate 24 -start_number 6100 -i {}/sparks2_pq1000.%05d.png -c:v prores_ks -pix_fmt yuv422p10le -profile:v 3 -vendor apl0 -vf \"scale=in_range=full:in_color_matrix=bt2020:out_range=tv:out_color_matrix=bt2020\" -color_range tv -color_trc smpte2084 -color_primaries bt2020 -colorspace bt2020nc {}/sparks2_pq1000_prores10bit.mov".format(testoutputdir, testoutputdir)
run_cmd(ffmpegcmd)
basic_ffmpeg_elapsed = time.time() - t1

elapsed = time.time() - t

t = time.time()

ffmpeg_source = source_exrs.replace("#", "%05d")

ffmpegcmd = f"ffmpeg -y -framerate 24 -start_number 6100 -i {ffmpeg_source} -c:v prores_ks -pix_fmt yuv422p10le -profile:v 3 -vendor apl0 -threads 0 -filter_threads 0 \-vf \"ocio=input=ACEScg:display=Rec.2100-PQ - Display:view=ACES 1.1 - HDR Video (1000 nits & Rec.2020 lim):format=rgb48,scale=in_range=full:in_color_matrix=bt2020:out_range=tv:out_color_matrix=bt2020\" -color_range tv -color_trc smpte2084 -color_primaries bt2020 -colorspace bt2020nc {testoutputdir}/sparks2_pq1000_prores10bit_ffmpeg.mov"
run_cmd(ffmpegcmd)

ffmpeg_elapsed = time.time() - t



start_frame = 6100
end_frame = 6299

def make_path(pattern, frame):
    # find contiguous run of '#'
    import re
    m = re.search(r"(#+)", pattern)
    if m:
        pad = 5
        num = str(frame).zfill(pad)
        return pattern[:m.start()] + num + pattern[m.end():]
    # fallback: simple replace single '#'
    return pattern.replace("#", str(frame))


with open("odd.txt", "w") as oddf, open("even.txt", "w") as evenf:
    for f in range(start_frame, end_frame + 1):
        path = make_path(source_exrs, f)
        line = f"file '{path}'\n"
        if f % 2 == 0:
            evenf.write(line)
        else:
            oddf.write(line)


ffmpegcmd_parallel = """ffmpeg -y \
-f concat -safe 0 -r 12 -i odd.txt \
-f concat -safe 0 -r 12 -i even.txt \
-filter_complex_threads 2 \
-threads 2 \
-filter_complex \"\
    [0:v] ocio=input=ACEScg:display=Rec.2100-PQ - Display:view=ACES 1.1 - HDR Video (1000 nits & Rec.2020 lim):format=rgb48, 
          scale=in_range=full:in_color_matrix=bt2020:out_range=tv:out_color_matrix=bt2020, drawtext=fontfile='/System/Library/Fonts/Monaco.ttf':text=\'ODD %{{eif\\:6100+n*2\\:d}}\':fontsize=100:fontcolor=white:x=50:y=50,
          format=yuv422p10le [odd_processed];
    [1:v] ocio=input=ACEScg:display=Rec.2100-PQ - Display:view=ACES 1.1 - HDR Video (1000 nits & Rec.2020 lim):format=rgb48, 
          scale=in_range=full:in_color_matrix=bt2020:out_range=tv:out_color_matrix=bt2020, 
          setpts=PTS+0.5, drawtext=fontfile='/System/Library/Fonts/Monaco.ttf':text=\'EVEN %{{eif\\:6100+n*2+1\\:d}}\':fontsize=100:fontcolor=white:x=50:y=50,
          format=yuv422p10le [even_processed];
    [even_processed][odd_processed] interleave
\" \
-r 24 \
-c:v prores_ks -profile:v 3 -vendor apl0 \
-color_range tv -color_trc smpte2084 -color_primaries bt2020 -colorspace bt2020nc \
{testoutputdir}/sparks2_pq1000_prores10bit_ffmpegparallel.mov""".format(testoutputdir=testoutputdir)

t = time.time()
print(ffmpegcmd_parallel)
#ffmpegcmd = f"ffmpeg -y -framerate 24 -start_number 6100 -i {ffmpeg_source} -c:v prores_ks -pix_fmt yuv422p10le -profile:v 3 -vendor apl0 -threads 0 -filter_threads 0 \-vf \"ocio=input=ACEScg:display=Rec.2100-PQ - Display:view=ACES 1.1 - HDR Video (1000 nits & Rec.2020 lim):format=rgb48,scale=in_range=full:in_color_matrix=bt2020:out_range=tv:out_color_matrix=bt2020\" -color_range tv -color_trc smpte2084 -color_primaries bt2020 -colorspace bt2020nc {testoutputdir}/sparks2_pq1000_prores10bit_ffmpeg.mov"
#run_cmd(ffmpegcmd_parallel)
#parallel_ffmpeg_elapsed = time.time() - t

print(f"Elapsed time for oiiotool: {oiiotool_elapsed} seconds")
print(f"Elapsed time for basic ffmpeg: {basic_ffmpeg_elapsed} seconds")
print(f"Elapsed time for oiiotool + ffmpeg: {elapsed} seconds")
print(f"Elapsed time for ffmpeg only: {ffmpeg_elapsed} seconds")
#print(f"Elapsed time for parallel ffmpeg only: {parallel_ffmpeg_elapsed} seconds")