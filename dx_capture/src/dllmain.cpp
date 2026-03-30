#include <windows.h>
#include "shared_mem.h"
#include "dx_hook.h"
#include "encoder.h"
#include "osd.h"
#include <string>

// Globals accessible from dx_hook.cpp
SharedMemServer g_sharedMem;
static DxHook   g_hook;
static Encoder  g_encoder;
static Osd      g_osd;
static bool     g_initialized = false;

static void Initialize()
{
    if (g_initialized) return;
    g_initialized = true;

    if (!g_sharedMem.Create()) {
        OutputDebugStringA("[dx_capture] Failed to create shared memory\n");
        return;
    }

    g_hook.Install([](ID3D11Texture2D* tex, UINT w, UINT h) {
        // Called every captured frame (30fps)
        SharedFrameSync* s = g_sharedMem.Get();
        if (!s || !s->capture_active) return;

        // Start encoder if not running (lazy start on first captured frame)
        static bool encoderStarted = false;
        if (!encoderStarted) {
            std::string outPath = std::string(s->output_path) + "\\video.mp4";
            if (g_encoder.Start(outPath, w, h, g_hook.Context(), 30)) {
                encoderStarted = true;
                OutputDebugStringA("[dx_capture] Encoder started\n");
            }
        }

        g_encoder.Submit(tex);
    });

    OutputDebugStringA("[dx_capture] Initialized OK\n");
}

static void Shutdown()
{
    g_hook.Remove();
    g_encoder.Stop();
    g_sharedMem.Destroy();
    g_initialized = false;
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID)
{
    switch (reason) {
        case DLL_PROCESS_ATTACH:
            DisableThreadLibraryCalls(hModule);
            // Use a new thread to avoid holding the loader lock
            CreateThread(nullptr, 0,
                [](LPVOID) -> DWORD { Initialize(); return 0; },
                nullptr, 0, nullptr);
            break;
        case DLL_PROCESS_DETACH:
            Shutdown();
            break;
    }
    return TRUE;
}
