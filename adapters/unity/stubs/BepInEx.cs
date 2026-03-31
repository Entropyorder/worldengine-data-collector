// Minimal BepInEx API stubs — for CI compilation ONLY.
// At runtime the actual BepInEx.dll from the BepInEx installation is used.
using System;

namespace BepInEx
{
    [AttributeUsage(AttributeTargets.Class)]
    public sealed class BepInPlugin : Attribute
    {
        public BepInPlugin(string guid, string name, string version) { }
    }

    public class PluginInfo
    {
        public string Location { get; } = "";
    }

    public abstract class BaseUnityPlugin : UnityEngine.MonoBehaviour
    {
        protected Logging.ManualLogSource Logger { get; } = null!;
        public PluginInfo Info { get; } = null!;
    }
}

namespace BepInEx.Logging
{
    public class ManualLogSource
    {
        public void LogInfo(object data)    { }
        public void LogWarning(object data) { }
        public void LogError(object data)   { }
        public void LogDebug(object data)   { }
    }
}
