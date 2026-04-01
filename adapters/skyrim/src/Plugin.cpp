#include <RE/Skyrim.h>
#include <SKSE/SKSE.h>
#include <spdlog/sinks/basic_file_sink.h>
#include "FrameCollector.h"

SKSEPluginInfo(
    .Version = REL::Version{ 1, 0, 0, 0 },
    .Name    = "WorldEngineCollector",
    .Author  = "WorldEngine",
)

namespace {

void LoadDxCapture() {
    // dx_capture.dll must be placed in the Skyrim root (same dir as SkyrimSE.exe).
    // Windows searches the application directory first, so a bare name suffices.
    HMODULE h = LoadLibraryW(L"dx_capture.dll");
    if (h)
        SKSE::log::info("[WorldEngineCollector] dx_capture.dll loaded — video capture enabled");
    else
        SKSE::log::warn("[WorldEngineCollector] dx_capture.dll not found in Skyrim directory — video capture disabled");
}

void OnMessage(SKSE::MessagingInterface::Message* msg) {
    // kDataLoaded fires after all game data is loaded — safe to start capture
    if (msg->type == SKSE::MessagingInterface::kDataLoaded) {
        LoadDxCapture();
        WorldEngine::FrameCollector::GetSingleton().Start();
        SKSE::log::info("[WorldEngineCollector] Started frame collection");
    }
}

}  // namespace

SKSEPluginLoad(const SKSE::LoadInterface* skse) {
    SKSE::Init(skse);

    // Set up logging to Data/SKSE/Plugins/WorldEngineCollector.log
    auto path = SKSE::log::log_directory();
    if (path) {
        auto sink = std::make_shared<spdlog::sinks::basic_file_sink_mt>(
            (*path / "WorldEngineCollector.log").string(), true);
        auto logger = std::make_shared<spdlog::logger>("WorldEngineCollector", sink);
        logger->set_level(spdlog::level::info);
        spdlog::set_default_logger(logger);
    }

    SKSE::log::info("[WorldEngineCollector] Plugin loaded");

    auto* msg = SKSE::GetMessagingInterface();
    if (!msg) {
        SKSE::log::error("Could not get MessagingInterface");
        return false;
    }
    msg->RegisterListener(OnMessage);

    return true;
}
