// Minimal Unity Engine API stubs — for CI compilation ONLY.
// At runtime the actual UnityEngine.dll from the game is used; these stubs are never shipped.
using System.Collections;

namespace UnityEngine
{
    public class Object
    {
        public string name { get; set; } = "";
        public static T[] FindObjectsOfType<T>() where T : Object => System.Array.Empty<T>();
        public static void Destroy(Object obj) { }
        public static void DontDestroyOnLoad(Object target) { }
    }

    public class Component : Object
    {
        public Transform transform { get; } = null!;
        public GameObject gameObject { get; } = null!;
    }

    public class Behaviour : Component
    {
        public bool enabled { get; set; }
    }

    public class MonoBehaviour : Behaviour
    {
        protected Coroutine StartCoroutine(IEnumerator routine) => null!;
    }

    public class Transform : Component
    {
        public Vector3 position { get; set; }
        public Quaternion rotation { get; set; }
        public Vector3 InverseTransformPoint(Vector3 position) => default;
    }

    public class GameObject : Object
    {
        public Transform transform { get; } = null!;
        public GameObject() { }
        public GameObject(string name) { }
        public static GameObject Find(string name) => null!;
        public T AddComponent<T>() where T : Component => null!;
    }

    public class Camera : Behaviour
    {
        public static Camera main { get; } = null!;
        public float fieldOfView { get; set; }
    }

    public class Canvas : Behaviour { }

    public struct Vector3 { public float x, y, z; }
    public struct Quaternion
    {
        public float x, y, z, w;
        public Vector3 eulerAngles { get; set; }
    }

    public static class Screen
    {
        public static int width  { get; }
        public static int height { get; }
    }

    public static class Input
    {
        public static float GetAxisRaw(string axisName) => 0f;
        public static bool  GetKey(KeyCode key) => false;
    }

    // Matches Unity KeyCode enum values exactly so Enum.GetValues works at runtime
    public enum KeyCode
    {
        None = 0, Backspace = 8, Delete = 127, Tab = 9, Clear = 12,
        Return = 13, Pause = 19, Escape = 27, Space = 32,
        Exclaim = 33, DoubleQuote = 34, Hash = 35, Dollar = 36,
        Ampersand = 38, Quote = 39, LeftParen = 40, RightParen = 41,
        Asterisk = 42, Plus = 43, Comma = 44, Minus = 45, Period = 46, Slash = 47,
        Alpha0 = 48, Alpha1 = 49, Alpha2 = 50, Alpha3 = 51, Alpha4 = 52,
        Alpha5 = 53, Alpha6 = 54, Alpha7 = 55, Alpha8 = 56, Alpha9 = 57,
        Colon = 58, Semicolon = 59, Less = 60, Equals = 61, Greater = 62,
        Question = 63, At = 64,
        LeftBracket = 91, Backslash = 92, RightBracket = 93, Caret = 94,
        Underscore = 95, BackQuote = 96,
        A = 97, B = 98, C = 99, D = 100, E = 101, F = 102, G = 103,
        H = 104, I = 105, J = 106, K = 107, L = 108, M = 109, N = 110,
        O = 111, P = 112, Q = 113, R = 114, S = 115, T = 116, U = 117,
        V = 118, W = 119, X = 120, Y = 121, Z = 122,
        Keypad0 = 256, Keypad1 = 257, Keypad2 = 258, Keypad3 = 259, Keypad4 = 260,
        Keypad5 = 261, Keypad6 = 262, Keypad7 = 263, Keypad8 = 264, Keypad9 = 265,
        KeypadPeriod = 266, KeypadDivide = 267, KeypadMultiply = 268,
        KeypadMinus = 269, KeypadPlus = 270, KeypadEnter = 271, KeypadEquals = 272,
        UpArrow = 273, DownArrow = 274, RightArrow = 275, LeftArrow = 276,
        Insert = 277, Home = 278, End = 279, PageUp = 280, PageDown = 281,
        F1 = 282, F2 = 283, F3 = 284, F4 = 285, F5 = 286, F6 = 287,
        F7 = 288, F8 = 289, F9 = 290, F10 = 291, F11 = 292, F12 = 293,
        Numlock = 300, CapsLock = 301, ScrollLock = 302,
        RightShift = 303, LeftShift = 304, RightControl = 305, LeftControl = 306,
        RightAlt = 307, LeftAlt = 308, LeftWindows = 311, RightWindows = 312,
        Help = 315, Print = 316, SysReq = 317, Break = 318, Menu = 319,
        Mouse0 = 323, Mouse1 = 324, Mouse2 = 325, Mouse3 = 326,
        Mouse4 = 327, Mouse5 = 328, Mouse6 = 329,
        JoystickButton0 = 330, JoystickButton1 = 331, JoystickButton2 = 332,
        JoystickButton3 = 333, JoystickButton4 = 334, JoystickButton5 = 335,
        JoystickButton6 = 336, JoystickButton7 = 337, JoystickButton8 = 338,
        JoystickButton9 = 339, JoystickButton10 = 340, JoystickButton11 = 341,
        JoystickButton12 = 342, JoystickButton13 = 343, JoystickButton14 = 344,
        JoystickButton15 = 345, JoystickButton16 = 346, JoystickButton17 = 347,
        JoystickButton18 = 348, JoystickButton19 = 349
    }

    public static class Mathf
    {
        public const float Deg2Rad = 0.017453292f;
        public static float Clamp(float value, float min, float max) =>
            value < min ? min : value > max ? max : value;
        public static float Tan(float f) => (float)System.Math.Tan(f);
    }

    public class Coroutine { }
    public abstract class CustomYieldInstruction { public abstract bool keepWaiting { get; } }
    public class WaitForEndOfFrame : CustomYieldInstruction
    {
        public override bool keepWaiting => false;
    }
}
