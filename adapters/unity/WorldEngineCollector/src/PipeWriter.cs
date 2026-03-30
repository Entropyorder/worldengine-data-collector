using System;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Collections.Generic;

namespace WorldEngine
{
    /// <summary>
    /// Named pipe client that streams JSON lines to the Python control center.
    /// Connects on first use; reconnects automatically if pipe closes.
    /// </summary>
    public class PipeWriter : IDisposable
    {
        private const string PIPE_NAME = "WorldEngineData";
        private NamedPipeClientStream _pipe;
        private StreamWriter _writer;
        private readonly Queue<string> _backlog = new Queue<string>();

        public bool IsConnected => _pipe?.IsConnected == true;

        public void EnsureConnected()
        {
            if (IsConnected) return;
            try
            {
                _pipe?.Dispose();
                _pipe = new NamedPipeClientStream(".", PIPE_NAME, PipeDirection.Out, PipeOptions.Asynchronous);
                _pipe.Connect(timeoutMilliseconds: 100);
                _writer = new StreamWriter(_pipe, Encoding.UTF8) { AutoFlush = true };
                // Drain backlog
                while (_backlog.Count > 0)
                    _writer.WriteLine(_backlog.Dequeue());
            }
            catch (TimeoutException)
            {
                // Python server not yet ready — queue locally
            }
        }

        public void WriteLine(string jsonLine)
        {
            EnsureConnected();
            try
            {
                if (IsConnected)
                    _writer.WriteLine(jsonLine);
                else
                    _backlog.Enqueue(jsonLine);
            }
            catch (IOException)
            {
                _pipe = null; // Force reconnect next call
                _backlog.Enqueue(jsonLine);
            }
        }

        public void Dispose()
        {
            _writer?.Dispose();
            _pipe?.Dispose();
        }
    }
}
