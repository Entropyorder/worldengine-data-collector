#pragma once
#include "shared_protocol.h"
#include <windows.h>

class SharedMemServer {
public:
    SharedMemServer();
    ~SharedMemServer();

    bool Create();   // call from DllMain
    void Destroy();  // call from DllMain

    SharedFrameSync* Get() { return _data; }

    void IncrementFrame();
    void SetGameFps(float fps);
    bool IsCaptureActive() const;

    // Win32 Event for notifying adapters of new frame
    HANDLE FrameEvent() const { return _frameEvent; }

private:
    HANDLE _mapHandle  = nullptr;
    HANDLE _frameEvent = nullptr;
    SharedFrameSync* _data = nullptr;
};
