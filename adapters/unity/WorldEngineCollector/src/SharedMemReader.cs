using System;
using System.Runtime.InteropServices;
using System.Text;

namespace WorldEngine
{
    /// <summary>
    /// Opens the shared memory segment created by dx_capture.dll and reads/writes fields.
    /// Layout must match shared_protocol.h exactly.
    /// </summary>
    public class SharedMemReader : IDisposable
    {
        private const string SHMEM_NAME = "WorldEngineCapture_SharedMem";
        private const int FILE_MAP_ALL_ACCESS = 0x000F001F;

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr OpenFileMapping(int access, bool inherit, string name);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr MapViewOfFile(IntPtr handle, int access, uint offsetHi, uint offsetLo, UIntPtr size);

        [DllImport("kernel32.dll")]
        private static extern bool UnmapViewOfFile(IntPtr view);

        [DllImport("kernel32.dll")]
        private static extern bool CloseHandle(IntPtr handle);

        private IntPtr _handle = IntPtr.Zero;
        private IntPtr _view = IntPtr.Zero;

        // Offsets matching shared_protocol.h
        private const int OFF_FRAME_INDEX    = 0;   // int64
        private const int OFF_PRESENT_TIME   = 8;   // double
        private const int OFF_GAME_FPS       = 16;  // float
        private const int OFF_CAPTURE_ACTIVE = 20;  // int32
        private const int OFF_SESSION_ID     = 28;  // char[64]
        private const int OFF_OUTPUT_PATH    = 92;  // char[256]

        public bool IsOpen => _view != IntPtr.Zero;

        public bool Open()
        {
            _handle = OpenFileMapping(FILE_MAP_ALL_ACCESS, false, SHMEM_NAME);
            if (_handle == IntPtr.Zero) return false;
            _view = MapViewOfFile(_handle, FILE_MAP_ALL_ACCESS, 0, 0, UIntPtr.Zero);
            return _view != IntPtr.Zero;
        }

        public bool CaptureActive => _view != IntPtr.Zero &&
            Marshal.ReadInt32(_view, OFF_CAPTURE_ACTIVE) == 1;

        public long FrameIndex => _view != IntPtr.Zero ?
            Marshal.ReadInt64(_view, OFF_FRAME_INDEX) : 0;

        public float GameFps => _view != IntPtr.Zero ?
            BitConverter.ToSingle(BitConverter.GetBytes(Marshal.ReadInt32(_view, OFF_GAME_FPS)), 0) : 0f;

        public void Dispose()
        {
            if (_view != IntPtr.Zero) { UnmapViewOfFile(_view); _view = IntPtr.Zero; }
            if (_handle != IntPtr.Zero) { CloseHandle(_handle); _handle = IntPtr.Zero; }
        }
    }
}
