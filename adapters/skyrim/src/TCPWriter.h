#pragma once
#include <atomic>
#include <mutex>
#include <queue>
#include <string>
#include <thread>

namespace WorldEngine {

/// Non-blocking TCP client. Send() enqueues lines; a background thread drains the queue.
/// Reconnects automatically on error.
class TCPWriter {
public:
    static TCPWriter& GetSingleton() {
        static TCPWriter instance;
        return instance;
    }

    void Connect(const std::string& host, int port);
    void Disconnect();
    void Send(const std::string& line);  // thread-safe, non-blocking

private:
    TCPWriter() = default;
    ~TCPWriter() { Disconnect(); }
    TCPWriter(const TCPWriter&) = delete;
    TCPWriter& operator=(const TCPWriter&) = delete;

    void DrainLoop();
    bool TryConnect();

    std::string _host;
    int         _port{ 27015 };

    std::mutex             _queueMtx;
    std::queue<std::string> _queue;

    std::thread      _thread;
    std::atomic_bool _running{ false };

    // Platform socket handle — stored as uintptr_t to avoid including winsock2.h here
    std::atomic<uintptr_t> _sock{ static_cast<uintptr_t>(~0) };  // INVALID_SOCKET
};

}  // namespace WorldEngine
