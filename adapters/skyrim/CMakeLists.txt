cmake_minimum_required(VERSION 3.24)   # OVERRIDE_FIND_PACKAGE requires 3.24+
project(WorldEngineCollector_Skyrim VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)

# ── fmt ───────────────────────────────────────────────────────────────────────
# OVERRIDE_FIND_PACKAGE: redirects find_package(fmt) inside CommonLibSSE to
# use this FetchContent target instead of looking for an installed config file.
FetchContent_Declare(fmt
    GIT_REPOSITORY https://github.com/fmtlib/fmt.git
    GIT_TAG        10.2.1
    OVERRIDE_FIND_PACKAGE
)
FetchContent_MakeAvailable(fmt)

# ── spdlog (use the fmt we just fetched, not its bundled copy) ────────────────
set(SPDLOG_FMT_EXTERNAL ON CACHE BOOL "" FORCE)
FetchContent_Declare(spdlog
    GIT_REPOSITORY https://github.com/gabime/spdlog.git
    GIT_TAG        v1.13.0
    OVERRIDE_FIND_PACKAGE
)
FetchContent_MakeAvailable(spdlog)

# ── rapidcsv (header-only; CommonLibSSE uses find_path to locate it) ──────────
FetchContent_Declare(rapidcsv
    GIT_REPOSITORY https://github.com/d99kris/rapidcsv.git
    GIT_TAG        v8.83
)
FetchContent_MakeAvailable(rapidcsv)
# Add the src/ dir so find_path(... "rapidcsv.h") succeeds
list(APPEND CMAKE_INCLUDE_PATH "${rapidcsv_SOURCE_DIR}/src")

# ── CommonLibSSE-NG ───────────────────────────────────────────────────────────
# Disable install/export rules — CommonLibSSE tries to export spdlog which is
# a FetchContent target with no install rules, causing a generate-step error.
# We copy the DLL manually in CI so we don't need cmake --install at all.
set(CMAKE_SKIP_INSTALL_RULES TRUE CACHE BOOL "" FORCE)
set(SKSE_SUPPORT_XBYAK OFF CACHE BOOL "" FORCE)
set(BUILD_TESTS         OFF CACHE BOOL "" FORCE)
FetchContent_Declare(CommonLibSSE
    GIT_REPOSITORY https://github.com/CharmedBaryon/CommonLibSSE-NG.git
    GIT_TAG        v3.7.0
)
FetchContent_MakeAvailable(CommonLibSSE)

# ── Plugin DLL ────────────────────────────────────────────────────────────────
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

# SKSE plugins must be in Data/SKSE/Plugins/ — DLL is copied by CI script
