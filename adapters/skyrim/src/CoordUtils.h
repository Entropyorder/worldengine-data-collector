#pragma once
#include <array>
#include <RE/Skyrim.h>  // CommonLibSSE: NiPoint3, NiQuaternion

namespace WorldEngine {

/// Skyrim uses right-hand Z-up. Output is right-hand Y-up (matches all other adapters).
///
/// Position:   (x, y, z) → (x, z, -y)
/// Quaternion: (qx, qy, qz, qw) → (qx, qz, -qy, qw)
///
/// Rationale:
///   - Skyrim Z (up)   becomes output Y (up)    → swap
///   - Skyrim Y (north) becomes output -Z        → negate
///   - Skyrim X (east)  stays X                  → unchanged

inline std::array<float, 3> ConvertPosition(const RE::NiPoint3& p) {
    return { p.x, p.z, -p.y };
}

inline std::array<float, 4> ConvertQuaternion(const RE::NiQuaternion& q) {
    // q = (x, y, z, w) in Skyrim Z-up space
    return { q.x, q.z, -q.y, q.w };
}

/// Camera intrinsics from vertical FOV (degrees) and screen dimensions.
struct Intrinsics { float fx, fy, cx, cy; };

inline Intrinsics CalcIntrinsics(float fovDeg, float width, float height) {
    constexpr float kDeg2Rad = 0.017453292f;
    float fovRad = fovDeg * kDeg2Rad;
    float fy     = (height * 0.5f) / std::tan(fovRad * 0.5f);
    return { fy, fy, width * 0.5f, height * 0.5f };
}

}  // namespace WorldEngine
