#include "dx_hook.h"
#include "shared_mem.h"
#include <MinHook.h>
#include <d3d11.h>
#include <dxgi.h>
#include <cassert>

DxHook* DxHook::s_instance = nullptr;

// Extern reference to global shared mem (defined in dllmain.cpp)
extern SharedMemServer g_sharedMem;

bool DxHook::Install(FrameCapturedCallback onFrame)
{
    s_instance = this;
    _onFrame = onFrame;
    QueryPerformanceFrequency(&_perfFreq);

    // Create a temporary D3D11 device + swap chain just to get the vtable pointer
    DXGI_SWAP_CHAIN_DESC scd = {};
    scd.BufferCount       = 1;
    scd.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    scd.BufferUsage       = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    scd.OutputWindow      = GetDesktopWindow();
    scd.SampleDesc.Count  = 1;
    scd.Windowed          = TRUE;
    scd.SwapEffect        = DXGI_SWAP_EFFECT_DISCARD;

    IDXGISwapChain* tempChain = nullptr;
    ID3D11Device* tempDevice  = nullptr;
    ID3D11DeviceContext* tempCtx = nullptr;

    if (FAILED(D3D11CreateDeviceAndSwapChain(
            nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, 0,
            nullptr, 0, D3D11_SDK_VERSION,
            &scd, &tempChain, &tempDevice, nullptr, &tempCtx)))
        return false;

    // vtable[8] = IDXGISwapChain::Present
    void** vtable = *reinterpret_cast<void***>(tempChain);
    void* presentAddr = vtable[8];

    tempChain->Release();
    tempDevice->Release();
    tempCtx->Release();

    MH_Initialize();
    MH_CreateHook(presentAddr, &PresentHook, &_originalPresent);
    MH_EnableHook(presentAddr);
    return true;
}

void DxHook::Remove()
{
    MH_DisableHook(MH_ALL_HOOKS);
    MH_Uninitialize();
    for (int i = 0; i < POOL_SIZE; i++)
        if (_stagingPool[i]) { _stagingPool[i]->Release(); _stagingPool[i] = nullptr; }
}

bool DxHook::InitStagingPool(ID3D11Device* device, UINT width, UINT height)
{
    D3D11_TEXTURE2D_DESC desc = {};
    desc.Width  = width;
    desc.Height = height;
    desc.MipLevels = 1;
    desc.ArraySize = 1;
    desc.Format    = DXGI_FORMAT_B8G8R8A8_UNORM;
    desc.SampleDesc.Count = 1;
    desc.Usage     = D3D11_USAGE_STAGING;
    desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;

    for (int i = 0; i < POOL_SIZE; i++) {
        if (FAILED(device->CreateTexture2D(&desc, nullptr, &_stagingPool[i])))
            return false;
    }
    _width  = width;
    _height = height;
    return true;
}

HRESULT STDMETHODCALLTYPE DxHook::PresentHook(
    IDXGISwapChain* swapChain, UINT syncInterval, UINT flags)
{
    auto* self = s_instance;

    // Lazy-init device and staging pool on first call
    if (!self->_device) {
        swapChain->GetDevice(__uuidof(ID3D11Device), reinterpret_cast<void**>(&self->_device));
        self->_device->GetImmediateContext(&self->_context);

        ID3D11Texture2D* backBuf = nullptr;
        swapChain->GetBuffer(0, __uuidof(ID3D11Texture2D), reinterpret_cast<void**>(&backBuf));
        D3D11_TEXTURE2D_DESC bDesc;
        backBuf->GetDesc(&bDesc);
        backBuf->Release();

        self->InitStagingPool(self->_device, bDesc.Width, bDesc.Height);
    }

    // Compute game FPS
    LARGE_INTEGER now;
    QueryPerformanceCounter(&now);
    if (self->_lastPresentTime.QuadPart > 0) {
        double dt_ms = 1000.0 * (now.QuadPart - self->_lastPresentTime.QuadPart)
                       / self->_perfFreq.QuadPart;
        g_sharedMem.SetGameFps(dt_ms > 0 ? static_cast<float>(1000.0 / dt_ms) : 0.f);
        g_sharedMem.Get()->present_time_ms = static_cast<double>(now.QuadPart) * 1000.0
                                              / self->_perfFreq.QuadPart;
    }
    self->_lastPresentTime = now;

    // Update frame counter in shared memory + notify adapters
    g_sharedMem.IncrementFrame();
    self->_frameCounter++;

    // Capture every 2nd frame (30fps from 60fps) when recording
    if (g_sharedMem.IsCaptureActive() && (self->_frameCounter % 2 == 0))
    {
        int idx = self->_poolIdx % POOL_SIZE;
        ID3D11Texture2D* backBuf = nullptr;
        if (SUCCEEDED(swapChain->GetBuffer(0, __uuidof(ID3D11Texture2D),
                                            reinterpret_cast<void**>(&backBuf))))
        {
            self->_context->CopyResource(self->_stagingPool[idx], backBuf);
            backBuf->Release();
            if (self->_onFrame)
                self->_onFrame(self->_stagingPool[idx], self->_width, self->_height);
            self->_poolIdx++;
        }
    }

    // Call original Present
    using PresentFn = HRESULT(STDMETHODCALLTYPE*)(IDXGISwapChain*, UINT, UINT);
    return reinterpret_cast<PresentFn>(self->_originalPresent)(swapChain, syncInterval, flags);
}
