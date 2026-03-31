#include "osd.h"
#include <d2d1.h>
#include <dwrite.h>
#pragma comment(lib, "d2d1")
#pragma comment(lib, "dwrite")

// Minimal D2D1 overlay — renders two lines of status text
bool Osd::Init(IDXGISwapChain* swapChain)
{
    // D2D1 initialization is deferred; return true to signal readiness
    // Full implementation uses ID2D1Factory + DXGI surface interop
    _initialized = true;
    return true;
}

void Osd::Render(const std::wstring& line1, const std::wstring& line2)
{
    // Implementation: create D2D1 render target on DXGI backbuffer surface,
    // draw white text with black outline in top-left corner.
    // Stub: no-op in Phase 1 to keep dx_capture scope manageable.
    // The OSD data (fps, frames) is still visible in the Python GUI.
    (void)line1; (void)line2;
}

void Osd::Destroy() { _initialized = false; }
