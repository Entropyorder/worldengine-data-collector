#include "shared_mem.h"
#include <stdexcept>
#include <cstring>

SharedMemServer::SharedMemServer() = default;

SharedMemServer::~SharedMemServer() { Destroy(); }

bool SharedMemServer::Create()
{
    _mapHandle = CreateFileMappingA(
        INVALID_HANDLE_VALUE, nullptr,
        PAGE_READWRITE, 0, sizeof(SharedFrameSync),
        WORLDENGINE_SHMEM_NAME
    );
    if (!_mapHandle) return false;

    _data = static_cast<SharedFrameSync*>(
        MapViewOfFile(_mapHandle, FILE_MAP_ALL_ACCESS, 0, 0, 0)
    );
    if (!_data) return false;

    ZeroMemory(_data, sizeof(SharedFrameSync));

    _frameEvent = CreateEventA(nullptr, FALSE, FALSE, WORLDENGINE_FRAME_EVENT);
    return _frameEvent != nullptr;
}

void SharedMemServer::Destroy()
{
    if (_data)       { UnmapViewOfFile(_data);    _data = nullptr; }
    if (_mapHandle)  { CloseHandle(_mapHandle);   _mapHandle = nullptr; }
    if (_frameEvent) { CloseHandle(_frameEvent);  _frameEvent = nullptr; }
}

void SharedMemServer::IncrementFrame()
{
    if (!_data) return;
    InterlockedIncrement64(&_data->frame_index);
    SetEvent(_frameEvent);
}

void SharedMemServer::SetGameFps(float fps)
{
    if (_data) _data->game_fps = fps;
}

bool SharedMemServer::IsCaptureActive() const
{
    return _data && _data->capture_active == 1;
}
