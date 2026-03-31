#pragma once
#include <cstdint>

#define WORLDENGINE_SHMEM_NAME    "WorldEngineCapture_SharedMem"
#define WORLDENGINE_FRAME_EVENT   "WorldEngineCapture_FrameEvent"
#define WORLDENGINE_PIPE_NAME     R"(\\.\pipe\WorldEngineData)"

#pragma pack(push, 1)
struct SharedFrameSync {
    volatile int64_t  frame_index;
    volatile double   present_time_ms;
    volatile float    game_fps;
    volatile int32_t  capture_active;
    volatile int32_t  reserved;
    char              session_id[64];
    char              output_path[256];
};
#pragma pack(pop)

static_assert(sizeof(SharedFrameSync) < 4096, "SharedFrameSync must fit in one page");
