#include "TCPWriter.h"
#include <SKSE/SKSE.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")

using namespace std::chrono_literals;

namespace WorldEngine {

static const SOCKET kInvalid = INVALID_SOCKET;

void TCPWriter::Connect(const std::string& host, int port) {
    _host = host;
    _port = port;

    // Init Winsock once
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2, 2), &wsaData);

    if (_running.exchange(true)) return;
    _thread = std::thread(&TCPWriter::DrainLoop, this);
}

void TCPWriter::Disconnect() {
    if (!_running.exchange(false)) return;
    if (_thread.joinable()) _thread.join();

    SOCKET s = static_cast<SOCKET>(_sock.load());
    if (s != kInvalid) {
        closesocket(s);
        _sock.store(static_cast<uintptr_t>(kInvalid));
    }
    WSACleanup();
}

void TCPWriter::Send(const std::string& line) {
    std::lock_guard lock(_queueMtx);
    // Bound queue to avoid unbounded memory growth if server is down
    if (_queue.size() < 300) {
        _queue.push(line + "\n");
    }
}

bool TCPWriter::TryConnect() {
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == kInvalid) return false;

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port   = htons(static_cast<u_short>(_port));
    inet_pton(AF_INET, _host.c_str(), &addr.sin_addr);

    // 200ms connect timeout
    u_long nonblocking = 1;
    ioctlsocket(s, FIONBIO, &nonblocking);

    connect(s, reinterpret_cast<sockaddr*>(&addr), sizeof(addr));

    fd_set wset;
    FD_ZERO(&wset);
    FD_SET(s, &wset);
    timeval tv{ 0, 200000 };
    int result = select(0, nullptr, &wset, nullptr, &tv);

    if (result <= 0) {
        closesocket(s);
        return false;
    }

    // Back to blocking for sends
    nonblocking = 0;
    ioctlsocket(s, FIONBIO, &nonblocking);

    SOCKET old = static_cast<SOCKET>(_sock.exchange(static_cast<uintptr_t>(s)));
    if (old != kInvalid) closesocket(old);

    SKSE::log::info("[WorldEngineCollector] TCP connected to {}:{}", _host, _port);
    return true;
}

void TCPWriter::DrainLoop() {
    while (_running.load()) {
        SOCKET s = static_cast<SOCKET>(_sock.load());
        if (s == kInvalid) {
            if (!TryConnect()) {
                std::this_thread::sleep_for(500ms);
                continue;
            }
            s = static_cast<SOCKET>(_sock.load());
        }

        std::string line;
        {
            std::lock_guard lock(_queueMtx);
            if (_queue.empty()) {
                std::this_thread::sleep_for(5ms);
                continue;
            }
            line = std::move(_queue.front());
            _queue.pop();
        }

        int sent = send(s, line.c_str(), static_cast<int>(line.size()), 0);
        if (sent == SOCKET_ERROR) {
            SKSE::log::warn("[WorldEngineCollector] TCP send error, reconnecting");
            closesocket(s);
            _sock.store(static_cast<uintptr_t>(kInvalid));
        }
    }
}

}  // namespace WorldEngine
