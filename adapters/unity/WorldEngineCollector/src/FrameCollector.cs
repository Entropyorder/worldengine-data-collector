using System;
using System.Collections.Generic;
using UnityEngine;
using Newtonsoft.Json;
using WorldEngine.Models;

namespace WorldEngine
{
    /// <summary>
    /// Runs every LateUpdate during active capture. Collects all frame fields and
    /// sends them as a JSON line over the Named Pipe.
    /// </summary>
    public class FrameCollector : MonoBehaviour
    {
        public SharedMemReader SharedMem;
        public PipeWriter Pipe;
        public UIHider UIHider;
        public string PlayerObjectName = "Player(Clone)";

        private long _captureFrameIndex = 0;  // local counter — NOT from shared mem (timing issue)
        private float _accMouseX;
        private float _accMouseY;

        private void Start()
        {
            // Initialize accumulated mouse position to screen center
            _accMouseX = Screen.width / 2f;
            _accMouseY = Screen.height / 2f;
        }

        private void LateUpdate()
        {
            if (SharedMem == null || !SharedMem.CaptureActive) return;

            var cam = Camera.main;
            if (cam == null) return;

            var playerObj = GameObject.Find(PlayerObjectName);
            if (playerObj == null) return;

            // Hide UI before GPU readback in this frame's Present
            UIHider.HideAllUI();

            // Accumulate mouse position (cursor is locked, so simulate from delta)
            float dx = Input.GetAxisRaw("Mouse X");
            float dy = Input.GetAxisRaw("Mouse Y");
            _accMouseX = Mathf.Clamp(_accMouseX + dx, 0, Screen.width);
            _accMouseY = Mathf.Clamp(_accMouseY - dy, 0, Screen.height); // flip Y (screen top=0)

            var data = new FrameData
            {
                Frame                = _captureFrameIndex,
                Time                 = DateTime.UtcNow.ToString("yyyy-MM-dd HH:mm:ss.fff"),
                Fps                  = 30f,
                CameraPosition       = CoordUtils.Vec3(cam.transform.position),
                CameraRotationQuat   = CoordUtils.Quat(cam.transform.rotation),
                CameraFollowOffset   = CoordUtils.FollowOffset(playerObj.transform, cam.transform),
                CameraSpeed          = new[] { 0f, 0f, 0f },  // computed offline
                CameraIntrinsics     = CoordUtils.CalcIntrinsics(cam.fieldOfView, Screen.width, Screen.height),
                PlayerPosition       = CoordUtils.Vec3(playerObj.transform.position),
                PlayerRotationEule   = CoordUtils.EulerDeg(playerObj.transform.rotation),
                PlayerRotationQuat   = CoordUtils.Quat(playerObj.transform.rotation),
                PlayerSpeed          = new[] { 0f, 0f, 0f },  // computed offline
                MetricScale          = 1.0f,
                MouseX               = _accMouseX,
                MouseY               = _accMouseY,
                MouseDx              = dx,
                MouseDy              = dy,
                KeyCode              = GetPressedKeyCodes(),
                GameFps              = SharedMem.GameFps,      // written to _game_fps in JSON
            };

            Pipe.WriteLine(JsonConvert.SerializeObject(data));

            // Restore UI after Present completes (WaitForEndOfFrame coroutine)
            UIHider.ScheduleRestore();

            _captureFrameIndex++;
        }

        private static List<int> GetPressedKeyCodes()
        {
            var codes = new List<int>();
            foreach (KeyCode kc in Enum.GetValues(typeof(KeyCode)))
            {
                // Skip mouse buttons and joystick axes (only keyboard scan codes)
                if (kc >= KeyCode.Mouse0 && kc <= KeyCode.Mouse6) continue;
                if (kc >= KeyCode.JoystickButton0) continue;
                if (Input.GetKey(kc))
                    codes.Add((int)kc);
            }
            return codes;
        }
    }
}
