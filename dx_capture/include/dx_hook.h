#pragma once
#include <d3d11.h>
#include <dxgi.h>
#include <functional>

// Callback type: called every captured frame (every 2nd Present when recording)
using FrameCapturedCallback = std::function<void(ID3D11Texture2D* stagingTex, UINT width, UINT height)>;

class DxHook {
public:
    bool Install(FrameCapturedCallback onFrame);
    void Remove();

    UINT Width()  const { return _width; }
    UINT Height() const { return _height; }
    ID3D11DeviceContext* Context() const { return _context; }

private:
    static HRESULT STDMETHODCALLTYPE PresentHook(
        IDXGISwapChain* swapChain, UINT syncInterval, UINT flags);

    bool InitStagingPool(ID3D11Device* device, UINT width, UINT height);

    static DxHook* s_instance;

    ID3D11Device*        _device        = nullptr;
    ID3D11DeviceContext* _context       = nullptr;
    // Ring buffer of 3 staging textures to avoid blocking encoder thread
    static constexpr int POOL_SIZE = 3;
    ID3D11Texture2D*     _stagingPool[POOL_SIZE] = {};
    int                  _poolIdx       = 0;

    UINT _width  = 1920;
    UINT _height = 1080;
    UINT64 _frameCounter = 0;
    LARGE_INTEGER _lastPresentTime = {};
    LARGE_INTEGER _perfFreq        = {};

    FrameCapturedCallback _onFrame;
    void* _originalPresent = nullptr;
};
