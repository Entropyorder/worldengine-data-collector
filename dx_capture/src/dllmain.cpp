#include <windows.h>
#include <atomic>
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
static HANDLE   g_initThread  = nullptr;  // stored for Shutdown sync

static void Initialize()
{
    if (g_initialized) return;
    g_initialized = true;

    if (!g_sharedMem.Create()) {
        OutputDebugStringA("[dx_capture] Failed to create shared memory\n");
        return;
    }

    static std::atomic<bool> encoderStarted{false};

    g_hook.Install([](std::vector<uint8_t> pixels, UINT w, UINT h) {
        SharedFrameSync* s = g_sharedMem.Get();
        if (!s || !s->capture_active) return;

        // Lazy-start encoder on first captured frame
        bool expected = false;
        if (!encoderStarted.load(std::memory_order_acquire)) {
            if (encoderStarted.compare_exchange_strong(expected, true, std::memory_order_acq_rel)) {
                // We won the race — start the encoder
                // Null-terminate defensively before string conversion
                char safePath[256];
                strncpy_s(safePath, sizeof(safePath), s->output_path, _TRUNCATE);
                std::string outPath = std::string(safePath) + "\\video.mp4";
                if (!g_encoder.Start(outPath, w, h, 30)) {
                    encoderStarted.store(false, std::memory_order_release);  // reset on failure
                    OutputDebugStringA("[dx_capture] Encoder failed to start\n");
                    return;
                }
                OutputDebugStringA("[dx_capture] Encoder started\n");
            } else {
                return;  // Another thread is starting encoder; drop this frame
            }
        }

        g_encoder.Submit(std::move(pixels), w, h);
    });

    OutputDebugStringA("[dx_capture] Initialized OK\n");
}

static void Shutdown()
{
    // Wait for init thread to complete before tearing down hook
    if (g_initThread) {
        WaitForSingleObject(g_initThread, 5000);
        CloseHandle(g_initThread);
        g_initThread = nullptr;
    }
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
            g_initThread = CreateThread(nullptr, 0,
                [](LPVOID) -> DWORD { Initialize(); return 0; },
                nullptr, 0, nullptr);
            break;
        case DLL_PROCESS_DETACH:
            Shutdown();
            break;
    }
    return TRUE;
}
