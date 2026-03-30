#pragma once
#include <d3d11.h>
#include <dxgi.h>
#include <string>

// Simple D2D1 text overlay on top of the swapchain
class Osd {
public:
    bool Init(IDXGISwapChain* swapChain);
    void Render(const std::wstring& line1, const std::wstring& line2);
    void Destroy();
private:
    // D2D1 objects initialized lazily
    void* _renderTarget = nullptr;  // ID2D1RenderTarget*
    void* _textFormat   = nullptr;  // IDWriteTextFormat*
    void* _brush        = nullptr;  // ID2D1SolidColorBrush*
    bool  _initialized  = false;
};
