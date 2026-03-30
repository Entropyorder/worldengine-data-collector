#pragma once
#include <d3d11.h>
#include <string>
#include <thread>
#include <queue>
#include <mutex>
#include <condition_variable>
#include <vector>
#include <cstdint>

struct EncodeJob {
    std::vector<uint8_t> pixels;  // pre-mapped CPU copy
    UINT width, height;
};

class Encoder {
public:
    bool Start(const std::string& outputMp4Path, UINT width, UINT height, int fps = 30);
    void Stop();
    // Submit pre-copied pixel data (BGRA, row-major). Caller owns the move.
    void Submit(std::vector<uint8_t> pixels, UINT w, UINT h);

private:
    void EncoderThread();

    FILE* _ffmpegPipe = nullptr;
    std::thread _thread;
    std::queue<EncodeJob> _jobs;
    std::mutex _mutex;
    std::condition_variable _cv;
    bool _running = false;
    UINT _width = 1920, _height = 1080;
};
