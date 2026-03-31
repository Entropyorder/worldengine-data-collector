using System.Collections;
using UnityEngine;

namespace WorldEngine
{
    /// <summary>
    /// Disables all Canvas components before Present and restores them after.
    /// Uses WaitForEndOfFrame coroutine to ensure restore happens after GPU readback.
    /// </summary>
    public class UIHider : MonoBehaviour
    {
        private Canvas[] _hidden = System.Array.Empty<Canvas>();

        public void HideAllUI()
        {
            _hidden = Object.FindObjectsOfType<Canvas>();
            foreach (var c in _hidden)
                c.enabled = false;
        }

        public void ScheduleRestore()
        {
            StartCoroutine(RestoreAfterFrame());
        }

        private IEnumerator RestoreAfterFrame()
        {
            yield return new WaitForEndOfFrame();
            foreach (var c in _hidden)
                if (c != null) c.enabled = true;
            _hidden = System.Array.Empty<Canvas>();
        }
    }
}
