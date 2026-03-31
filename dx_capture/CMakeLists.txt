cmake_minimum_required(VERSION 3.25)
project(dx_capture LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)

# Dependency root paths.
# Priority: CMake cache variable (-DMINHOOK_ROOT=...) > env var > hard-coded default.
if(NOT DEFINED MINHOOK_ROOT)
    if(DEFINED ENV{MINHOOK_ROOT})
        set(MINHOOK_ROOT "$ENV{MINHOOK_ROOT}")
    else()
        set(MINHOOK_ROOT "C:/libs/minhook")
    endif()
endif()

if(NOT DEFINED FFMPEG_ROOT)
    if(DEFINED ENV{FFMPEG_ROOT})
        set(FFMPEG_ROOT "$ENV{FFMPEG_ROOT}")
    else()
        set(FFMPEG_ROOT "C:/libs/ffmpeg")
    endif()
endif()

set(MINHOOK_INCLUDE_DIR "${MINHOOK_ROOT}/include")
set(MINHOOK_LIB         "${MINHOOK_ROOT}/lib/MinHook.x64.lib")
set(FFMPEG_INCLUDE_DIR  "${FFMPEG_ROOT}/include")
set(FFMPEG_LIB_DIR      "${FFMPEG_ROOT}/lib")

add_library(dx_capture SHARED
    src/dllmain.cpp
    src/shared_mem.cpp
    src/dx_hook.cpp
    src/encoder.cpp
    src/osd.cpp
)

target_include_directories(dx_capture PRIVATE
    include
    ${MINHOOK_INCLUDE_DIR}
    ${FFMPEG_INCLUDE_DIR}
)

target_link_libraries(dx_capture PRIVATE
    ${MINHOOK_LIB}
    d3d11 dxgi d2d1 dwrite
    "${FFMPEG_LIB_DIR}/avcodec.lib"
    "${FFMPEG_LIB_DIR}/avformat.lib"
    "${FFMPEG_LIB_DIR}/avutil.lib"
    "${FFMPEG_LIB_DIR}/swscale.lib"
)

set_target_properties(dx_capture PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY         "${CMAKE_SOURCE_DIR}/../adapters/bin"
    RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_SOURCE_DIR}/../adapters/bin"
    RUNTIME_OUTPUT_DIRECTORY_DEBUG   "${CMAKE_SOURCE_DIR}/../adapters/bin"
)
