#pragma once
#include <atomic>
#include <mutex>
#include <set>
#include <thread>

namespace WorldEngine {

class FrameCollector {
public:
    static FrameCollector& GetSingleton() {
        static FrameCollector instance;
        return instance;
    }

    void Start();   // called from Plugin.cpp on kDataLoaded
    void Stop();    // called on plugin unload

    // Called by InputEventSink on key events (main thread)
    void OnKeyDown(std::uint32_t vkCode);
    void OnKeyUp(std::uint32_t vkCode);

    // Called by InputEventSink on mouse move (main thread)
    void OnMouseMove(float dx, float dy);

private:
    FrameCollector() = default;
    ~FrameCollector() { Stop(); }
    FrameCollector(const FrameCollector&) = delete;
    FrameCollector& operator=(const FrameCollector&) = delete;

    void CollectLoop();   // runs in _thread at ~30 Hz

    std::thread      _thread;
    std::atomic_bool _running{ false };

    // Inputs (written by main thread, read by CollectLoop)
    std::mutex            _inputMtx;
    std::set<uint32_t>    _pressedKeys;
    float                 _mouseDx{ 0 }, _mouseDy{ 0 };
    float                 _accMouseX{ 960 }, _accMouseY{ 540 };

    long long _frameIndex{ 0 };
};

}  // namespace WorldEngine
