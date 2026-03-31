using System;
using System.IO;
using System.Runtime.InteropServices;
using BepInEx;
using BepInEx.Logging;
using UnityEngine;

namespace WorldEngine
{
    [BepInPlugin("com.worldengine.collector", "WorldEngine Collector", "1.0.0")]
    public class Plugin : BaseUnityPlugin
    {
        internal static ManualLogSource Log;

        [DllImport("kernel32", SetLastError = true, CharSet = CharSet.Auto)]
        private static extern IntPtr LoadLibrary(string lpFileName);

        private SharedMemReader _sharedMem;
        private PipeWriter _pipe;
        private UIHider _uiHider;
        private FrameCollector _collector;

        private void Awake()
        {
            Log = Logger;
            Log.LogInfo("WorldEngine Collector starting...");

            // Load dx_capture.dll from the same directory as this plugin
            string dxCapturePath = Path.Combine(Path.GetDirectoryName(Info.Location), "..", "..", "dx_capture.dll");
            if (File.Exists(dxCapturePath))
            {
                LoadLibrary(dxCapturePath);
                Log.LogInfo($"Loaded dx_capture.dll from {dxCapturePath}");
            }
            else
            {
                Log.LogWarning($"dx_capture.dll not found at {dxCapturePath}. Video capture disabled.");
            }

            // Wire up components as MonoBehaviours on a persistent GameObject
            var go = new GameObject("WorldEngineCollector");
            DontDestroyOnLoad(go);

            _sharedMem = new SharedMemReader();
            if (!_sharedMem.Open())
                Log.LogWarning("Could not open shared memory. Is dx_capture.dll loaded?");

            // PipeWriter is a plain C# class (not MonoBehaviour) — instantiate directly
            _pipe = new PipeWriter();
            _uiHider = go.AddComponent<UIHider>();

            _collector = go.AddComponent<FrameCollector>();
            _collector.SharedMem = _sharedMem;
            _collector.Pipe = _pipe;
            _collector.UIHider = _uiHider;
            _collector.PlayerObjectName = "Player(Clone)";

            Log.LogInfo("WorldEngine Collector ready. Press F9 in control center to start.");
        }

        private void OnDestroy()
        {
            _sharedMem?.Dispose();
            _pipe?.Dispose();
        }
    }
}
