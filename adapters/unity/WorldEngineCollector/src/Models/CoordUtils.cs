using UnityEngine;
using WorldEngine.Models;

namespace WorldEngine.Models
{
    public static class CoordUtils
    {
        // Unity is natively left-hand Y-up — no coordinate conversion needed.
        // These are pass-through helpers for clarity and future non-Unity adapters.

        public static float[] Vec3(Vector3 v) => new[] { v.x, v.y, v.z };

        public static float[] Quat(Quaternion q) => new[] { q.x, q.y, q.z, q.w };

        /// <summary>Returns Euler angles in degrees [pitch(x), yaw(y), roll(z)].</summary>
        public static float[] EulerDeg(Quaternion q)
        {
            var e = q.eulerAngles;
            return new[] { e.x, e.y, e.z };
        }

        /// <summary>
        /// Camera position in player's local coordinate space.
        /// Result is the "follow offset" vector.
        /// </summary>
        public static float[] FollowOffset(Transform player, Transform camera) =>
            Vec3(player.InverseTransformPoint(camera.position));

        /// <summary>
        /// Compute camera intrinsic matrix parameters from Unity camera.
        /// Unity camera.fieldOfView is vertical FOV, so fy = (height/2) / tan(fovRad/2).
        /// fx = fy (isotropic: square pixels), cx = width/2, cy = height/2
        /// </summary>
        public static CameraIntrinsics CalcIntrinsics(float fovDeg, int width, int height)
        {
            float fovRad = fovDeg * Mathf.Deg2Rad;
            // Unity camera.fieldOfView is vertical FOV; use height for physically correct fy
            float fy = (height / 2f) / Mathf.Tan(fovRad / 2f);
            return new CameraIntrinsics
            {
                Fx = fy,   // isotropic: square pixels, fx = fy
                Fy = fy,
                Cx = width / 2f,
                Cy = height / 2f,
            };
        }
    }
}
