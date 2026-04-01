#include "FrameCollector.h"
#include "TCPWriter.h"
#include "CoordUtils.h"

#include <RE/Skyrim.h>
#include <SKSE/SKSE.h>
#include <shared_protocol.h>

#include <chrono>
#include <ctime>
#include <sstream>
#include <iomanip>
#include <string>
#include <vector>

using namespace std::chrono_literals;

namespace WorldEngine {

// ── Input sink ────────────────────────────────────────────────────────────────
class InputSink : public RE::BSTEventSink<RE::InputEvent*> {
public:
    static InputSink* GetSingleton() {
        static InputSink s;
        return &s;
    }

    RE::BSEventNotifyControl ProcessEvent(
        RE::InputEvent* const* events,
        RE::BSTEventSource<RE::InputEvent*>*) override
    {
        for (auto* ev = *events; ev; ev = ev->next) {
            if (auto* btn = ev->AsButtonEvent()) {
                auto idCode = btn->GetIDCode();
                if (btn->IsDown()) FrameCollector::GetSingleton().OnKeyDown(idCode);
                if (btn->IsUp())   FrameCollector::GetSingleton().OnKeyUp(idCode);
            } else if (ev->GetEventType() == RE::INPUT_EVENT_TYPE::kMouseMove) {
                auto* mm = static_cast<RE::MouseMoveEvent*>(ev);
                FrameCollector::GetSingleton().OnMouseMove(
                    static_cast<float>(mm->mouseInputX),
                    static_cast<float>(mm->mouseInputY));
            }
        }
        return RE::BSEventNotifyControl::kContinue;
    }
};

// ── Public API ────────────────────────────────────────────────────────────────
void FrameCollector::Start() {
    if (_running.exchange(true)) return;

    // Register input sink on main thread
    if (auto* devMgr = RE::BSInputDeviceManager::GetSingleton()) {
        devMgr->AddEventSink(InputSink::GetSingleton());
    }

    // Open dx_capture shared memory (may not exist if DLL failed to load)
    _shmemFile = OpenFileMappingW(FILE_MAP_READ, FALSE, L"WorldEngineCapture_SharedMem");
    if (_shmemFile) {
        _shmemView = MapViewOfFile(_shmemFile, FILE_MAP_READ, 0, 0, 0);
        if (_shmemView)
            SKSE::log::info("[WorldEngineCollector] Shared memory opened — video sync enabled");
        else {
            CloseHandle(_shmemFile);
            _shmemFile = nullptr;
            SKSE::log::warn("[WorldEngineCollector] MapViewOfFile failed");
        }
    } else {
        SKSE::log::info("[WorldEngineCollector] Shared memory not available — running at 30 Hz without video sync");
    }

    _thread = std::thread(&FrameCollector::CollectLoop, this);
    SKSE::log::info("[WorldEngineCollector] CollectLoop started");
}

void FrameCollector::Stop() {
    if (!_running.exchange(false)) return;
    if (_thread.joinable()) _thread.join();

    if (_shmemView) { UnmapViewOfFile(_shmemView); _shmemView = nullptr; }
    if (_shmemFile) { CloseHandle(_shmemFile);     _shmemFile = nullptr; }
}

void FrameCollector::OnKeyDown(uint32_t vk) {
    std::lock_guard lock(_inputMtx);
    _pressedKeys.insert(vk);
}

void FrameCollector::OnKeyUp(uint32_t vk) {
    std::lock_guard lock(_inputMtx);
    _pressedKeys.erase(vk);
}

void FrameCollector::OnMouseMove(float dx, float dy) {
    std::lock_guard lock(_inputMtx);
    _mouseDx  += dx;
    _mouseDy  += dy;
    _accMouseX = std::clamp(_accMouseX + dx,   0.0f, 1920.0f);
    _accMouseY = std::clamp(_accMouseY - dy,   0.0f, 1080.0f);
}

// ── Helpers ────────────────────────────────────────────────────────────────────
static std::string NowUTC() {
    auto now   = std::chrono::system_clock::now();
    auto ms    = std::chrono::duration_cast<std::chrono::milliseconds>(
                     now.time_since_epoch()) % 1000;
    std::time_t t  = std::chrono::system_clock::to_time_t(now);
    std::tm tm_utc = {};
#ifdef _WIN32
    gmtime_s(&tm_utc, &t);
#else
    gmtime_r(&t, &tm_utc);
#endif
    std::ostringstream oss;
    oss << std::put_time(&tm_utc, "%Y-%m-%d %H:%M:%S")
        << '.' << std::setw(3) << std::setfill('0') << ms.count();
    return oss.str();
}

static std::string FloatArr3(const std::array<float,3>& a) {
    std::ostringstream o;
    o << '[' << a[0] << ',' << a[1] << ',' << a[2] << ']';
    return o.str();
}

static std::string FloatArr4(const std::array<float,4>& a) {
    std::ostringstream o;
    o << '[' << a[0] << ',' << a[1] << ',' << a[2] << ',' << a[3] << ']';
    return o.str();
}

// ── Collect loop ──────────────────────────────────────────────────────────────
void FrameCollector::CollectLoop() {
    constexpr auto kFallbackInterval = std::chrono::milliseconds(33);  // ~30 fps
    auto& writer = TCPWriter::GetSingleton();
    writer.Connect("127.0.0.1", 27015);

    auto lastFallbackEmit = std::chrono::steady_clock::now();

    while (_running.load()) {

        // ── Frame sync ────────────────────────────────────────────────────────
        // If dx_capture is active: emit once per captured video frame.
        // Otherwise: fall back to ~30 Hz so data still flows.
        auto* shm = static_cast<const SharedFrameSync*>(_shmemView);
        if (shm && shm->capture_active) {
            int64_t dxFrame = shm->frame_index;
            if (dxFrame == _lastDxFrame) {
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
                continue;
            }
            _lastDxFrame = dxFrame;
            _frameIndex  = dxFrame;
        } else {
            auto now = std::chrono::steady_clock::now();
            if (now - lastFallbackEmit < kFallbackInterval) {
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
                continue;
            }
            lastFallbackEmit = now;
        }

        // ── Snapshot game state (CommonLibSSE getters are thread-safe for reads) ──
        auto* cam    = RE::PlayerCamera::GetSingleton();
        auto* player = RE::PlayerCharacter::GetSingleton();

        if (!cam || !player) {
            std::this_thread::sleep_for(kInterval);
            continue;
        }

        // Camera position + orientation
        auto* camState = cam->currentState.get();
        RE::NiPoint3    camPos{};
        RE::NiQuaternion camRot{};
        if (camState) {
            camState->GetTranslation(camPos);
            camState->GetRotation(camRot);
        }

        // Player position + orientation
        // GetGraphRotation does not exist in CommonLibSSE-NG v3.7.0.
        // Use data.angle (stored Euler angles: x=pitch, y=roll, z=yaw, radians, Z-up)
        // and convert to quaternion manually.
        RE::NiPoint3 playerPos = player->GetPosition();
        RE::NiQuaternion playerRot{};
        {
            auto& a = player->data.angle;  // NiPoint3 {x=pitch, y=roll, z=yaw}
            float cy = std::cos(a.z * 0.5f), sy = std::sin(a.z * 0.5f);
            float cp = std::cos(a.x * 0.5f), sp = std::sin(a.x * 0.5f);
            float cr = std::cos(a.y * 0.5f), sr = std::sin(a.y * 0.5f);
            playerRot.w = cy * cp * cr + sy * sp * sr;
            playerRot.x = cy * sp * cr + sy * cp * sr;
            playerRot.y = sy * cp * cr - cy * sp * sr;
            playerRot.z = cy * cp * sr - sy * sp * cr;
        }

        // FOV (degrees)
        float fovDeg = cam->worldFOV;

        // Coordinate conversion (Z-up → Y-up)
        auto cPos  = ConvertPosition(camPos);
        auto cQuat = ConvertQuaternion(camRot);
        auto pPos  = ConvertPosition(playerPos);
        auto pQuat = ConvertQuaternion(playerRot);

        // Follow offset: camera in player local space (approximate)
        std::array<float,3> followOffset = {
            (cPos[0] - pPos[0]),
            (cPos[1] - pPos[1]),
            (cPos[2] - pPos[2])
        };

        // Camera intrinsics
        auto intr = CalcIntrinsics(fovDeg, 1920.0f, 1080.0f);

        // Euler angles from quaternion (pQuat is [qx,qz,-qy,qw] after conversion)
        float qi = pQuat[0], qj = pQuat[1], qk = pQuat[2], qw = pQuat[3];
        float sinp  = 2.0f * (qw * qj - qk * qi);
        float pitch  = std::asin(std::clamp(sinp, -1.0f, 1.0f)) * (180.0f / 3.14159265f);
        float siny   = 2.0f * (qw * qk + qi * qj);
        float cosy   = 1.0f - 2.0f * (qj * qj + qk * qk);
        float yaw    = std::atan2(siny, cosy) * (180.0f / 3.14159265f);
        float sinr   = 2.0f * (qw * qi + qj * qk);
        float cosr   = 1.0f - 2.0f * (qi * qi + qj * qj);
        float roll   = std::atan2(sinr, cosr) * (180.0f / 3.14159265f);

        // Input snapshot (swap with zeros for next interval)
        float dx, dy, ax, ay;
        std::string keysJson;
        {
            std::lock_guard lock(_inputMtx);
            dx = _mouseDx; dy = _mouseDy;
            ax = _accMouseX; ay = _accMouseY;
            _mouseDx = 0; _mouseDy = 0;

            std::ostringstream kj;
            kj << '[';
            bool first = true;
            for (auto vk : _pressedKeys) {
                if (!first) kj << ',';
                kj << vk;
                first = false;
            }
            kj << ']';
            keysJson = kj.str();
        }

        // ── Build JSON line ───────────────────────────────────────────────────
        std::ostringstream json;
        json << "{"
             << "\"frame\":"  << _frameIndex << ","
             << "\"time\":\"" << NowUTC()    << "\","
             << "\"fps\":"    << 30          << ","
             << "\"camera_position\":"             << FloatArr3(cPos)   << ","
             << "\"camera_rotation_quaternion\":"  << FloatArr4(cQuat)  << ","
             << "\"camera_follow_offset\":"        << FloatArr3(followOffset) << ","
             << "\"camera_speed\":[0,0,0],"
             << "\"camera_intrinsics\":{"
                 << "\"fx\":" << intr.fx << ","
                 << "\"fy\":" << intr.fy << ","
                 << "\"cx\":" << intr.cx << ","
                 << "\"cy\":" << intr.cy
             << "},"
             << "\"player_position\":"              << FloatArr3(pPos)  << ","
             << "\"player_rotation_eule\":["
                 << pitch << "," << yaw << "," << roll
             << "],"
             << "\"player_rotation_quaternion\":"   << FloatArr4(pQuat) << ","
             << "\"player_speed\":[0,0,0],"
             << "\"metric_scale\":0.01428,"
             << "\"mouse_x\":"  << ax << ","
             << "\"mouse_y\":"  << ay << ","
             << "\"mouse_dx\":" << dx << ","
             << "\"mouse_dy\":" << dy << ","
             << "\"keyCode\":"  << keysJson << ","
             << "\"_game_fps\":60"
             << "}";

        writer.Send(json.str());
        if (!_shmemView)  // only increment in fallback mode; sync mode uses dxFrame
            _frameIndex++;
    }

    writer.Disconnect();
}

}  // namespace WorldEngine
