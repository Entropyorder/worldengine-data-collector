cmake_minimum_required(VERSION 3.25)
project(dx_capture LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)

set(MINHOOK_INCLUDE_DIR "C:/libs/minhook/include")
set(MINHOOK_LIB         "C:/libs/minhook/lib/MinHook.x64.lib")
set(FFMPEG_INCLUDE_DIR  "C:/libs/ffmpeg/include")
set(FFMPEG_LIB_DIR      "C:/libs/ffmpeg/lib")

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
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/../adapters/bin"
)
