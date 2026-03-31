cmake_minimum_required(VERSION 3.21)
project(WorldEngineCollector_Skyrim VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ── fmt (required by CommonLibSSE-NG) ─────────────────────────────────────────
include(FetchContent)
FetchContent_Declare(
    fmt
    GIT_REPOSITORY https://github.com/fmtlib/fmt.git
    GIT_TAG        10.2.1
)
FetchContent_MakeAvailable(fmt)
# Tell find_package(fmt) where the generated fmtConfig.cmake lives
set(fmt_DIR "${fmt_BINARY_DIR}" CACHE PATH "" FORCE)

# ── CommonLibSSE-NG (SKSE API headers + implementation) ───────────────────────
FetchContent_Declare(
    CommonLibSSE
    GIT_REPOSITORY https://github.com/CharmedBaryon/CommonLibSSE-NG.git
    GIT_TAG        v3.7.0
)
set(SKSE_SUPPORT_XBYAK OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(CommonLibSSE)

# ── Plugin DLL ─────────────────────────────────────────────────────────────────
add_library(WorldEngineCollector_Skyrim SHARED
    src/Plugin.cpp
    src/FrameCollector.cpp
    src/TCPWriter.cpp
)

target_include_directories(WorldEngineCollector_Skyrim PRIVATE src)

target_link_libraries(WorldEngineCollector_Skyrim
    PRIVATE
        CommonLibSSE::CommonLibSSE
        ws2_32          # Winsock
)

# Output name matches what the CI packages
set_target_properties(WorldEngineCollector_Skyrim PROPERTIES
    OUTPUT_NAME "WorldEngineCollector"
)

# SKSE plugins must be in Data/SKSE/Plugins/ — runtime hint only
install(TARGETS WorldEngineCollector_Skyrim
    RUNTIME DESTINATION "Data/SKSE/Plugins"
)
