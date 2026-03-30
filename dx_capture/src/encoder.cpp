#include "encoder.h"
#include <cstdio>
#include <stdexcept>
#include <vector>
#include <d3d11.h>

bool Encoder::Start(const std::string& outputPath, UINT width, UINT height,
                    ID3D11DeviceContext* ctx, int fps)
{
    _width  = width;
    _height = height;
    _ctx    = ctx;

    // Build FFmpeg command with NVENC
    char cmd[2048];
    snprintf(cmd, sizeof(cmd),
        "ffmpeg -y -f rawvideo -pixel_format bgra -video_size %ux%u -framerate %d "
        "-i pipe:0 -c:v h264_nvenc -preset p4 -b:v 8M -pix_fmt yuv420p "
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

void Encoder::Submit(ID3D11Texture2D* stagingTex)
{
    std::lock_guard<std::mutex> lock(_mutex);
    _jobs.push(stagingTex);
    _cv.notify_one();
}

void Encoder::EncoderThread()
{
    while (true) {
        ID3D11Texture2D* tex = nullptr;
        {
            std::unique_lock<std::mutex> lock(_mutex);
            _cv.wait(lock, [this]{ return !_jobs.empty() || !_running; });
            if (!_running && _jobs.empty()) break;
            tex = _jobs.front();
            _jobs.pop();
        }

        D3D11_MAPPED_SUBRESOURCE mapped = {};
        HRESULT hr = _ctx->Map(tex, 0, D3D11_MAP_READ, 0, &mapped);
        if (SUCCEEDED(hr)) {
            // Write row by row (handle row pitch != width*4)
            UINT rowBytes = _width * 4;
            const BYTE* src = static_cast<const BYTE*>(mapped.pData);
            for (UINT row = 0; row < _height; row++) {
                fwrite(src + row * mapped.RowPitch, 1, rowBytes, _ffmpegPipe);
            }
            _ctx->Unmap(tex, 0);
        }
    }
}
