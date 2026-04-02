#include "encoder.h"
#include <cstdio>

bool Encoder::Start(const std::string& outputPath, UINT width, UINT height, int fps)
{
    _width  = width;
    _height = height;

    char cmd[2048];
    // Use libx264 (software) — portable across all GPUs.
    // h264_nvenc requires NVIDIA NVENC and silently fails on AMD/Intel.
    // 2>NUL suppresses ffmpeg console output; errors surface via _popen returning NULL.
    snprintf(cmd, sizeof(cmd),
        "ffmpeg -y -f rawvideo -pixel_format bgra -video_size %ux%u -framerate %d "
        "-i pipe:0 -c:v libx264 -preset ultrafast -crf 23 -pix_fmt yuv420p "
        "-movflags +faststart \"%s\" 2>NUL",
        width, height, fps, outputPath.c_str());

    _ffmpegPipe = _popen(cmd, "wb");
    if (!_ffmpegPipe)
        return false;

    _running = true;
    _thread = std::thread(&Encoder::EncoderThread, this);
    return true;
}

void Encoder::Stop()
{
    {
        std::lock_guard<std::mutex> lock(_mutex);
        _running = false;
    }
    _cv.notify_all();
    if (_thread.joinable()) _thread.join();
    if (_ffmpegPipe) { _pclose(_ffmpegPipe); _ffmpegPipe = nullptr; }
}

void Encoder::Submit(std::vector<uint8_t> pixels, UINT w, UINT h)
{
    std::lock_guard<std::mutex> lock(_mutex);
    _jobs.push({std::move(pixels), w, h});
    _cv.notify_one();
}

void Encoder::EncoderThread()
{
    while (true) {
        EncodeJob job;
        {
            std::unique_lock<std::mutex> lock(_mutex);
            _cv.wait(lock, [this]{ return !_jobs.empty() || !_running; });
            if (!_running && _jobs.empty()) break;
            job = std::move(_jobs.front());
            _jobs.pop();
        }
        // Pixels are already in CPU memory — just write to ffmpeg stdin
        if (_ffmpegPipe)
            fwrite(job.pixels.data(), 1, job.pixels.size(), _ffmpegPipe);
    }
}
