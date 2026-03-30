#pragma once
#include <d3d11.h>
#include <string>
#include <thread>
#include <queue>
#include <mutex>
#include <condition_variable>

class Encoder {
public:
    bool Start(const std::string& outputMp4Path, UINT width, UINT height,
               ID3D11DeviceContext* ctx, int fps = 30);
    void Stop();
    void Submit(ID3D11Texture2D* stagingTex);  // context stored at Start() time

private:
    void EncoderThread();

    FILE* _ffmpegPipe = nullptr;
    std::thread _thread;
    std::queue<ID3D11Texture2D*> _jobs;  // texture pointer only, context is stored
    std::mutex _mutex;
    std::condition_variable _cv;
    bool _running = false;
    UINT _width = 1920, _height = 1080;
    ID3D11DeviceContext* _ctx = nullptr;  // stored at Start()
};
