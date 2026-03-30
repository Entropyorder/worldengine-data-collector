# WorldEngine Data Collector — Phase 1 (Valheim) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete game data capture pipeline for Valheim that produces frame-aligned video + JSON telemetry matching the WorldEngine requirements spec.

**Architecture:** A C++ DLL (`dx_capture.dll`) hooks DirectX Present for zero-latency frame capture and shared-memory signaling; a BepInEx C# plugin reads engine data each LateUpdate and streams it via Named Pipe; a Python control center manages sessions, post-processes data, and provides GUI + OSD.

**Tech Stack:** C++17 + MinHook + DXGI + NVENC + FFmpeg (dx_capture); C# .NET 4.6.2 + BepInEx 5.x (Adapter); Python 3.11 + PyQt6 + pyyaml + openpyxl (Control Center). Target OS: Windows 10/11. GPU: NVIDIA required.

---

## Prerequisites

Before starting any task, verify the following are installed on the **Windows dev machine**:

```
□ Visual Studio 2022 (C++ + C# workloads)
□ CMake 3.25+
□ Python 3.11+  (pip install pyqt6 pyyaml openpyxl pytest)
□ FFmpeg with NVENC support  (ffmpeg.exe accessible on PATH)
□ Valheim installed + BepInEx 5.4.x installed into Valheim folder
□ NVIDIA GPU + latest drivers
□ MinHook (download: https://github.com/TsudaKageyu/minhook/releases, headers + lib)
□ Windows SDK 10.0.19041+ (ships with VS2022)
```

All file paths below assume project root: `Gaming-Camera/`

---

## File Map

```
Gaming-Camera/
├── dx_capture/
│   ├── CMakeLists.txt
│   ├── include/
│   │   ├── shared_protocol.h       # SharedFrameSync struct (used by DLL + C# via P/Invoke)
│   │   ├── dx_hook.h
│   │   ├── encoder.h
│   │   └── osd.h
│   └── src/
│       ├── dllmain.cpp             # DLL entry, MinHook init/uninit
│       ├── shared_mem.cpp          # CreateFileMapping / MapViewOfFile
│       ├── dx_hook.cpp             # IDXGISwapChain::Present hook, staging texture pool
│       ├── encoder.cpp             # FFmpeg stdin pipe + NVENC args
│       └── osd.cpp                 # D2D1 text overlay on backbuffer
│
├── adapters/unity/WorldEngineCollector/
│   ├── WorldEngineCollector.csproj
│   ├── src/
│   │   ├── Plugin.cs               # BepInEx entry point, wires everything together
│   │   ├── SharedMemReader.cs      # P/Invoke to open shared memory, read capture_active
│   │   ├── FrameCollector.cs       # LateUpdate: collect all fields, write to pipe
│   │   ├── UIHider.cs              # Disable/restore Canvas components
│   │   ├── PipeWriter.cs           # Named pipe client, buffered writes
│   │   └── Models/
│   │       ├── FrameData.cs        # JSON-serializable frame record
│   │       └── CoordUtils.cs       # InverseTransformPoint, CalcIntrinsics, EulerDeg
│   └── tests/
│       ├── CoordUtilsTests.cs      # Unit tests for pure math functions
│       └── FrameDataTests.cs       # JSON serialization round-trip
│
└── control_center/
    ├── pyproject.toml
    ├── main.py                     # Entry: starts PyQt app
    ├── session_manager.py          # Create session dir, lifecycle FSM
    ├── pipe_reader.py              # Named pipe server, buffers to raw_frames.jsonl
    ├── post_processor.py           # Speed compute, frame validation, final JSON output
    ├── metadata_collector.py       # systeminfo.json + game_meta.xlsx generation
    ├── osd_bridge.py               # Write capture_active + session path to shared mem
    ├── config/
    │   ├── games/valheim.yaml
    │   └── settings.yaml
    ├── gui/
    │   ├── main_window.py          # PyQt6 main window
    │   └── session_log.py          # Live log widget
    └── tests/
        ├── test_post_processor.py
        ├── test_metadata_collector.py
        └── test_pipe_reader.py
```

---

## Task 1: Shared Protocol Header + Project Scaffolding

**Files:**
- Create: `dx_capture/include/shared_protocol.h`
- Create: `dx_capture/CMakeLists.txt`
- Create: `adapters/unity/WorldEngineCollector/WorldEngineCollector.csproj`
- Create: `control_center/pyproject.toml`
- Create: `control_center/config/settings.yaml`
- Create: `control_center/config/games/valheim.yaml`

- [ ] **Step 1: Create shared protocol header**

This header is the contract between all three components. Create `dx_capture/include/shared_protocol.h`:

```cpp
#pragma once
#include <cstdint>

// Named objects — all three components must use these exact strings
#define WORLDENGINE_SHMEM_NAME    "WorldEngineCapture_SharedMem"
#define WORLDENGINE_FRAME_EVENT   "WorldEngineCapture_FrameEvent"
#define WORLDENGINE_PIPE_NAME     R"(\\.\pipe\WorldEngineData)"

#pragma pack(push, 1)
struct SharedFrameSync {
    volatile int64_t  frame_index;      // incremented by dx_capture each Present
    volatile double   present_time_ms;  // QueryPerformanceCounter in ms, set by dx_capture
    volatile float    game_fps;         // 1000.0 / delta_present_ms
    volatile int32_t  capture_active;   // 0=idle 1=recording  (Python writes, others read)
    volatile int32_t  reserved;
    char              session_id[64];   // "session_YYYYMMDD_HHMMSS_valheim\0"
    char              output_path[256]; // absolute path to session folder
};
#pragma pack(pop)

static_assert(sizeof(SharedFrameSync) < 4096, "SharedFrameSync must fit in one page");
```

- [ ] **Step 2: Create CMakeLists.txt for dx_capture**

Create `dx_capture/CMakeLists.txt`:

```cmake
cmake_minimum_required(VERSION 3.25)
project(dx_capture LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)

# Adjust these paths to your MinHook and FFmpeg installations
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

# DLL goes to a known output location for easy loading
set_target_properties(dx_capture PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/../adapters/bin"
)
```

- [ ] **Step 3: Create C# project file**

Create `adapters/unity/WorldEngineCollector/WorldEngineCollector.csproj`:

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net46</TargetFramework>
    <AssemblyName>WorldEngineCollector</AssemblyName>
    <RootNamespace>WorldEngine</RootNamespace>
    <Nullable>enable</Nullable>
  </PropertyGroup>
  <ItemGroup>
    <!-- Point these at your BepInEx + Valheim installation -->
    <Reference Include="BepInEx">
      <HintPath>C:\Steam\steamapps\common\Valheim\BepInEx\core\BepInEx.dll</HintPath>
      <Private>false</Private>
    </Reference>
    <Reference Include="UnityEngine">
      <HintPath>C:\Steam\steamapps\common\Valheim\valheim_Data\Managed\UnityEngine.dll</HintPath>
      <Private>false</Private>
    </Reference>
    <Reference Include="UnityEngine.CoreModule">
      <HintPath>C:\Steam\steamapps\common\Valheim\valheim_Data\Managed\UnityEngine.CoreModule.dll</HintPath>
      <Private>false</Private>
    </Reference>
    <Reference Include="Newtonsoft.Json">
      <HintPath>C:\Steam\steamapps\common\Valheim\BepInEx\core\Newtonsoft.Json.dll</HintPath>
      <Private>false</Private>
    </Reference>
  </ItemGroup>
</Project>
```

- [ ] **Step 4: Create Python project config**

Create `control_center/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "worldengine-control-center"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "PyQt6>=6.6",
    "pyyaml>=6.0",
    "openpyxl>=3.1",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-qt>=4.4"]
```

- [ ] **Step 5: Create settings.yaml**

Create `control_center/config/settings.yaml`:

```yaml
output_dir: "C:/WorldEngineCaptures"   # change to your capture output directory
ffmpeg_path: "ffmpeg"                  # assumes ffmpeg is on PATH
dx_capture_dll: "../adapters/bin/dx_capture.dll"
hotkey_start_stop: "F9"
max_session_minutes: 30
```

- [ ] **Step 6: Create valheim.yaml**

Create `control_center/config/games/valheim.yaml`:

```yaml
game_name: "Valheim"
process_name: "valheim"
engine: unity
adapter_dll: "C:/Steam/steamapps/common/Valheim/BepInEx/plugins/WorldEngineCollector.dll"
capture_fps: 30
game_target_fps: 60
coordinate_system: left_hand_y_up
metric_scale: 1.0
player_object_name: "Player(Clone)"
ui_hide_method: disable_canvas

key_mapping:
  87:  "前进(W)"
  83:  "后退(S)"
  65:  "左移(A)"
  68:  "右移(D)"
  32:  "跳跃(Space)"
  160: "冲刺(LShift)"
  69:  "交互(E)"
  81:  "技能(Q)"

mouse_config:
  cursor_locked: true
  controls_camera: true
  description: "鼠标控制视角旋转，右键开启瞄准模式"

game_meta:
  game_type_description: "3D 开放世界第三人称探索游戏"
  perspective: "第三人称"
```

- [ ] **Step 7: Commit scaffold**

```bash
git add dx_capture/ adapters/unity/ control_center/
git commit -m "chore: project scaffold, shared protocol header, config files"
```

---

## Task 2: Python Post-Processor (TDD)

**Files:**
- Create: `control_center/post_processor.py`
- Create: `control_center/tests/test_post_processor.py`

- [ ] **Step 1: Write failing tests**

Create `control_center/tests/test_post_processor.py`:

```python
import pytest
from datetime import datetime
from post_processor import compute_speeds, validate_frames, parse_frame_time

class TestParseFrameTime:
    def test_parses_milliseconds(self):
        t = parse_frame_time("2026-03-30 14:30:22.033")
        assert t == datetime(2026, 3, 30, 14, 30, 22, 33000)

    def test_parses_zero_ms(self):
        t = parse_frame_time("2026-03-30 00:00:00.000")
        assert t == datetime(2026, 3, 30, 0, 0, 0, 0)


class TestComputeSpeeds:
    def _make_frame(self, time_str, cam_pos, player_pos, frame_idx=0):
        return {
            "frame": frame_idx,
            "time": time_str,
            "camera_position": cam_pos,
            "player_position": player_pos,
            "camera_speed": [0.0, 0.0, 0.0],
            "player_speed": [0.0, 0.0, 0.0],
        }

    def test_first_frame_speed_is_zero(self):
        frames = [self._make_frame("2026-03-30 00:00:00.000", [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])]
        result = compute_speeds(frames)
        assert result[0]["camera_speed"] == [0.0, 0.0, 0.0]
        assert result[0]["player_speed"] == [0.0, 0.0, 0.0]

    def test_camera_speed_computed_correctly(self):
        frames = [
            self._make_frame("2026-03-30 00:00:00.000", [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], 0),
            self._make_frame("2026-03-30 00:00:00.033", [1.0, 0.0, 0.0], [1.0, 0.0, 0.0], 1),
        ]
        result = compute_speeds(frames)
        # dt = 0.033s, Δx = 1.0 → speed_x ≈ 30.3 m/s
        assert abs(result[1]["camera_speed"][0] - 1.0 / 0.033) < 0.01
        assert result[1]["camera_speed"][1] == 0.0
        assert result[1]["camera_speed"][2] == 0.0

    def test_player_speed_computed_correctly(self):
        frames = [
            self._make_frame("2026-03-30 00:00:00.000", [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], 0),
            self._make_frame("2026-03-30 00:00:00.033", [0.0, 0.0, 0.0], [0.0, 0.0, 3.0], 1),
        ]
        result = compute_speeds(frames)
        assert abs(result[1]["player_speed"][2] - 3.0 / 0.033) < 0.01

    def test_zero_dt_returns_zero_speed(self):
        frames = [
            self._make_frame("2026-03-30 00:00:00.000", [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], 0),
            self._make_frame("2026-03-30 00:00:00.000", [1.0, 0.0, 0.0], [0.0, 0.0, 0.0], 1),
        ]
        result = compute_speeds(frames)
        assert result[1]["camera_speed"] == [0.0, 0.0, 0.0]


class TestValidateFrames:
    def test_empty_returns_no_warnings(self):
        warnings = validate_frames([])
        assert warnings == []

    def test_detects_gap_in_frame_index(self):
        frames = [
            {"frame": 0, "time": "2026-03-30 00:00:00.000"},
            {"frame": 2, "time": "2026-03-30 00:00:00.033"},  # gap: frame 1 missing
        ]
        warnings = validate_frames(frames)
        assert any("gap" in w.lower() or "frame 1" in w for w in warnings)

    def test_contiguous_frames_no_warning(self):
        frames = [
            {"frame": 0, "time": "2026-03-30 00:00:00.000"},
            {"frame": 1, "time": "2026-03-30 00:00:00.033"},
            {"frame": 2, "time": "2026-03-30 00:00:00.066"},
        ]
        warnings = validate_frames(frames)
        assert warnings == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd control_center
python -m pytest tests/test_post_processor.py -v
```

Expected: `ModuleNotFoundError: No module named 'post_processor'`

- [ ] **Step 3: Implement post_processor.py**

Create `control_center/post_processor.py`:

```python
from __future__ import annotations
import json
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def parse_frame_time(time_str: str) -> datetime:
    """Parse 'YYYY-MM-DD HH:MM:SS.fff' → datetime (microseconds precision)."""
    return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")


def compute_speeds(frames: list[dict]) -> list[dict]:
    """
    Fill camera_speed and player_speed for each frame via finite difference.
    Mutates and returns the list.
    """
    for i, frame in enumerate(frames):
        if i == 0:
            frame["camera_speed"] = [0.0, 0.0, 0.0]
            frame["player_speed"] = [0.0, 0.0, 0.0]
            continue

        dt = (parse_frame_time(frames[i]["time"]) - parse_frame_time(frames[i - 1]["time"])).total_seconds()
        if dt <= 0.0:
            frame["camera_speed"] = [0.0, 0.0, 0.0]
            frame["player_speed"] = [0.0, 0.0, 0.0]
            continue

        cp = frame["camera_position"]
        cp_prev = frames[i - 1]["camera_position"]
        frame["camera_speed"] = [(cp[j] - cp_prev[j]) / dt for j in range(3)]

        pp = frame["player_position"]
        pp_prev = frames[i - 1]["player_position"]
        frame["player_speed"] = [(pp[j] - pp_prev[j]) / dt for j in range(3)]

    return frames


def validate_frames(frames: list[dict]) -> list[str]:
    """Return list of human-readable warning strings for anomalies."""
    warnings: list[str] = []
    for i in range(1, len(frames)):
        expected = frames[i - 1]["frame"] + 1
        actual = frames[i]["frame"]
        if actual != expected:
            warnings.append(f"Frame gap between frame {frames[i-1]['frame']} and frame {actual} (expected frame {expected})")
    return warnings


def process_session(session_dir: str) -> None:
    """
    Read raw_frames.jsonl, compute speeds, validate, write action_camera.json.
    Also writes fps.json from the game_fps field embedded in each raw frame.
    """
    session_path = Path(session_dir)
    raw_path = session_path / "raw_frames.jsonl"

    frames: list[dict] = []
    fps_records: list[dict] = []

    with open(raw_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            # fps.json records come from _game_fps field injected by pipe_reader
            fps_records.append({"time": record["time"], "fps": record.pop("_game_fps", 0.0)})
            frames.append(record)

    warnings = validate_frames(frames)
    for w in warnings:
        print(f"[WARN] {w}")

    frames = compute_speeds(frames)

    out_action = session_path / "action_camera.json"
    with open(out_action, "w", encoding="utf-8") as f:
        for frame in frames:
            f.write(json.dumps(frame, ensure_ascii=False) + "\n")

    out_fps = session_path / "fps.json"
    with open(out_fps, "w", encoding="utf-8") as f:
        json.dump(fps_records, f, ensure_ascii=False, indent=2)

    print(f"[OK] Processed {len(frames)} frames → {out_action}")
    print(f"[OK] FPS log → {out_fps}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd control_center
python -m pytest tests/test_post_processor.py -v
```

Expected: all 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add control_center/post_processor.py control_center/tests/test_post_processor.py
git commit -m "feat: post_processor with speed computation and frame validation"
```

---

## Task 3: Python Pipe Reader + Session Manager (TDD)

**Files:**
- Create: `control_center/pipe_reader.py`
- Create: `control_center/session_manager.py`
- Create: `control_center/tests/test_pipe_reader.py`

- [ ] **Step 1: Write failing tests for pipe_reader**

Create `control_center/tests/test_pipe_reader.py`:

```python
import json
import threading
import time
import pytest
from unittest.mock import MagicMock, patch, mock_open
from pipe_reader import FrameBuffer


class TestFrameBuffer:
    def test_empty_on_init(self):
        buf = FrameBuffer(output_path="dummy.jsonl")
        assert buf.frame_count == 0

    def test_ingest_increments_count(self):
        buf = FrameBuffer(output_path="dummy.jsonl")
        with patch("builtins.open", mock_open()):
            buf.ingest('{"frame":0,"time":"2026-03-30 00:00:00.000"}\n')
            assert buf.frame_count == 1

    def test_ingest_ignores_blank_lines(self):
        buf = FrameBuffer(output_path="dummy.jsonl")
        with patch("builtins.open", mock_open()):
            buf.ingest("")
            buf.ingest("   \n")
            assert buf.frame_count == 0

    def test_ingest_invalid_json_raises(self):
        buf = FrameBuffer(output_path="dummy.jsonl")
        with pytest.raises(json.JSONDecodeError):
            buf.ingest("not json\n")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd control_center
python -m pytest tests/test_pipe_reader.py -v
```

Expected: `ModuleNotFoundError: No module named 'pipe_reader'`

- [ ] **Step 3: Implement pipe_reader.py**

Create `control_center/pipe_reader.py`:

```python
from __future__ import annotations
import json
import threading
from pathlib import Path


class FrameBuffer:
    """
    Accepts raw JSON lines from the Named Pipe and appends them to a JSONL file.
    Thread-safe: ingest() may be called from a reader thread.
    """

    def __init__(self, output_path: str) -> None:
        self._output_path = Path(output_path)
        self._lock = threading.Lock()
        self._count = 0
        self._file = None

    @property
    def frame_count(self) -> int:
        return self._count

    def open(self) -> None:
        self._file = open(self._output_path, "w", encoding="utf-8", buffering=1)

    def close(self) -> None:
        if self._file:
            self._file.flush()
            self._file.close()
            self._file = None

    def ingest(self, line: str) -> None:
        """Parse one JSON line and write to disk. Raises json.JSONDecodeError on bad input."""
        line = line.strip()
        if not line:
            return
        record = json.loads(line)  # validates JSON; raises on error
        with self._lock:
            if self._file:
                self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._count += 1


class PipeServer:
    """
    Opens a Windows Named Pipe server and reads lines into a FrameBuffer.
    Runs on a background daemon thread.
    """

    PIPE_NAME = r"\\.\pipe\WorldEngineData"
    BUFFER_SIZE = 65536

    def __init__(self, frame_buffer: FrameBuffer) -> None:
        self._buffer = frame_buffer
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def _run(self) -> None:
        import ctypes
        import ctypes.wintypes as wt

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        PIPE_ACCESS_INBOUND = 0x00000001
        PIPE_TYPE_MESSAGE   = 0x00000004
        PIPE_READMODE_MESSAGE = 0x00000002
        PIPE_WAIT           = 0x00000000
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

        handle = kernel32.CreateNamedPipeW(
            self.PIPE_NAME,
            PIPE_ACCESS_INBOUND,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
            1,
            self.BUFFER_SIZE,
            self.BUFFER_SIZE,
            0,
            None,
        )
        if handle == INVALID_HANDLE_VALUE:
            raise OSError(f"CreateNamedPipe failed: {ctypes.get_last_error()}")

        try:
            kernel32.ConnectNamedPipe(handle, None)
            buf = ctypes.create_string_buffer(self.BUFFER_SIZE)
            leftovers = b""
            while not self._stop_event.is_set():
                read = wt.DWORD(0)
                ok = kernel32.ReadFile(handle, buf, self.BUFFER_SIZE, ctypes.byref(read), None)
                if not ok or read.value == 0:
                    break
                data = leftovers + buf.raw[: read.value]
                *lines, leftovers = data.split(b"\n")
                for raw in lines:
                    try:
                        self._buffer.ingest(raw.decode("utf-8") + "\n")
                    except Exception as e:
                        print(f"[PipeServer] ingest error: {e}")
        finally:
            kernel32.CloseHandle(handle)
```

- [ ] **Step 4: Implement session_manager.py**

Create `control_center/session_manager.py`:

```python
from __future__ import annotations
import os
import yaml
from datetime import datetime
from pathlib import Path
from enum import Enum, auto


class SessionState(Enum):
    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()


class SessionManager:
    """
    Manages the lifecycle of a single recording session.
    Coordinates PipeServer, FrameBuffer, OsdBridge, and PostProcessor.
    """

    def __init__(self, settings_path: str = "config/settings.yaml") -> None:
        with open(settings_path, encoding="utf-8") as f:
            self._settings = yaml.safe_load(f)
        self._state = SessionState.IDLE
        self._session_dir: Path | None = None
        self._game_config: dict = {}

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def session_dir(self) -> Path | None:
        return self._session_dir

    def load_game(self, game_yaml_path: str) -> None:
        with open(game_yaml_path, encoding="utf-8") as f:
            self._game_config = yaml.safe_load(f)

    def start_session(self) -> Path:
        assert self._state == SessionState.IDLE, "Already in a session"
        assert self._game_config, "Call load_game() first"

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = self._game_config["process_name"]
        dir_name = f"session_{ts}_{name}"
        output_root = Path(self._settings["output_dir"])
        self._session_dir = output_root / dir_name
        self._session_dir.mkdir(parents=True, exist_ok=True)

        self._state = SessionState.RECORDING
        return self._session_dir

    def stop_session(self) -> None:
        assert self._state == SessionState.RECORDING
        self._state = SessionState.PROCESSING

    def finish_processing(self) -> None:
        assert self._state == SessionState.PROCESSING
        self._state = SessionState.IDLE
```

- [ ] **Step 5: Run pipe_reader tests**

```bash
cd control_center
python -m pytest tests/test_pipe_reader.py -v
```

Expected: all 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add control_center/pipe_reader.py control_center/session_manager.py \
        control_center/tests/test_pipe_reader.py
git commit -m "feat: pipe_reader FrameBuffer + PipeServer, session_manager lifecycle FSM"
```

---

## Task 4: Metadata Collector (TDD)

**Files:**
- Create: `control_center/metadata_collector.py`
- Create: `control_center/tests/test_metadata_collector.py`

- [ ] **Step 1: Write failing tests**

Create `control_center/tests/test_metadata_collector.py`:

```python
import json
import pytest
from unittest.mock import patch, MagicMock
from metadata_collector import build_systeminfo, detect_perspective, build_game_meta_dict


class TestBuildSystemInfo:
    def test_returns_required_keys(self):
        mock_rect = (0, 0, 1920, 1080)
        with patch("metadata_collector.get_game_window_rect", return_value=mock_rect), \
             patch("metadata_collector.get_system_dpi", return_value=1.0), \
             patch("metadata_collector.get_process_title", return_value="Valheim"):
            info = build_systeminfo("valheim", 1920, 1080)
        assert info["gameProcessName"] == "Valheim"
        assert info["width"] == 1920
        assert info["height"] == 1080
        assert info["recordDpi"] == 1.0
        assert info["window_rect"] == [{"x": 0, "y": 0}, {"x": 1920, "y": 1080}]

    def test_dpi_rounds_to_one_decimal(self):
        with patch("metadata_collector.get_game_window_rect", return_value=(0, 0, 1920, 1080)), \
             patch("metadata_collector.get_system_dpi", return_value=1.4999), \
             patch("metadata_collector.get_process_title", return_value="Valheim"):
            info = build_systeminfo("valheim", 1920, 1080)
        assert info["recordDpi"] == round(1.4999, 1)


class TestDetectPerspective:
    def test_small_offset_is_first_person(self):
        # camera within 0.5m of player → first person
        offsets = [[0.0, 0.1, 0.0]] * 100
        assert detect_perspective(offsets) == "第一人称"

    def test_large_offset_is_third_person(self):
        offsets = [[0.5, 2.5, -5.0]] * 100
        assert detect_perspective(offsets) == "第三人称"


class TestBuildGameMetaDict:
    def test_returns_required_keys(self):
        game_cfg = {
            "game_name": "Valheim",
            "game_meta": {"game_type_description": "探索游戏", "perspective": "第三人称"},
            "key_mapping": {87: "前进(W)"},
            "mouse_config": {"description": "鼠标控制视角"},
        }
        sample_offsets = [[0.5, 2.5, -5.0]] * 10
        result = build_game_meta_dict(game_cfg, sample_offsets, width=1920, height=1080)
        assert result["游戏类型描述"] == "探索游戏"
        assert result["视角配置"] == "第三人称"
        assert result["画面分辨率"] == "1920x1080"
        assert "键盘映射规则" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd control_center
python -m pytest tests/test_metadata_collector.py -v
```

Expected: `ModuleNotFoundError: No module named 'metadata_collector'`

- [ ] **Step 3: Implement metadata_collector.py**

Create `control_center/metadata_collector.py`:

```python
from __future__ import annotations
import ctypes
import ctypes.wintypes as wt
import json
import math
import os
from pathlib import Path
from typing import Any

import openpyxl
import yaml


# ---------- OS helpers ----------

def get_game_window_rect(process_name: str) -> tuple[int, int, int, int]:
    """Return (left, top, right, bottom) of the game window. Returns (0,0,1920,1080) on failure."""
    import ctypes
    user32 = ctypes.WinDLL("user32")

    result = [0, 0, 1920, 1080]

    def _enum_callback(hwnd, _):
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            rect = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            result[0] = rect.left
            result[1] = rect.top
            result[2] = rect.right
            result[3] = rect.bottom
            return False
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(WNDENUMPROC(_enum_callback), 0)
    return tuple(result)


def get_system_dpi() -> float:
    """Return system DPI scale factor (1.0 = 100%, 1.5 = 150%)."""
    try:
        shcore = ctypes.WinDLL("shcore")
        dpi = wt.UINT()
        shcore.GetDpiForMonitor(0, 0, ctypes.byref(dpi), ctypes.byref(wt.UINT()))
        return round(dpi.value / 96.0, 1)
    except Exception:
        return 1.0


def get_process_title(process_name: str) -> str:
    """Return window title of the first window belonging to process_name."""
    import subprocess
    try:
        out = subprocess.check_output(
            ["powershell", "-Command",
             f"(Get-Process '{process_name}' | Select-Object -First 1).MainWindowTitle"],
            text=True, timeout=5
        ).strip()
        return out if out else process_name
    except Exception:
        return process_name


# ---------- Core builders ----------

def build_systeminfo(process_name: str, width: int, height: int) -> dict:
    rect = get_game_window_rect(process_name)
    title = get_process_title(process_name)
    dpi = get_system_dpi()
    return {
        "gameProcessName": title,
        "window_rect": [{"x": rect[0], "y": rect[1]}, {"x": rect[2], "y": rect[3]}],
        "width": width,
        "height": height,
        "recordDpi": round(dpi, 1),
    }


def detect_perspective(camera_follow_offsets: list[list[float]]) -> str:
    """
    Determine first vs third person from sampled follow offsets.
    If average distance < 0.5m → first person.
    """
    if not camera_follow_offsets:
        return "未知"
    avg_dist = sum(
        math.sqrt(sum(x ** 2 for x in v)) for v in camera_follow_offsets
    ) / len(camera_follow_offsets)
    return "第一人称" if avg_dist < 0.5 else "第三人称"


def build_game_meta_dict(
    game_cfg: dict,
    sample_offsets: list[list[float]],
    width: int,
    height: int,
) -> dict:
    meta_cfg = game_cfg.get("game_meta", {})
    key_map = game_cfg.get("key_mapping", {})
    mouse_cfg = game_cfg.get("mouse_config", {})
    perspective = detect_perspective(sample_offsets)

    key_rules = "; ".join(f"{v}" for v in key_map.values()) if key_map else "未配置"

    return {
        "游戏类型描述": meta_cfg.get("game_type_description", ""),
        "视角配置": meta_cfg.get("perspective", perspective),
        "相机位置是否固定": "否",
        "相机位置描述": f"第三人称跟随，典型偏移距离约 {_avg_offset_distance(sample_offsets):.1f}m",
        "画面分辨率": f"{width}x{height}",
        "键盘映射规则": key_rules,
        "鼠标对应规则": mouse_cfg.get("description", ""),
    }


def _avg_offset_distance(offsets: list[list[float]]) -> float:
    if not offsets:
        return 0.0
    return sum(math.sqrt(sum(x ** 2 for x in v)) for v in offsets) / len(offsets)


def write_game_meta_xlsx(meta_dict: dict, output_path: str) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "游戏元信息"
    ws.append(["字段", "内容"])
    for k, v in meta_dict.items():
        ws.append([k, v])
    wb.save(output_path)


def collect_and_write(
    session_dir: str,
    game_yaml_path: str,
    raw_frames_path: str,
    width: int = 1920,
    height: int = 1080,
) -> None:
    """Top-level: generate systeminfo.json + game_meta.xlsx for a completed session."""
    import json as _json
    session_path = Path(session_dir)

    with open(game_yaml_path, encoding="utf-8") as f:
        game_cfg = yaml.safe_load(f)

    # systeminfo.json
    sysinfo = build_systeminfo(game_cfg["process_name"], width, height)
    with open(session_path / "systeminfo.json", "w", encoding="utf-8") as f:
        _json.dump(sysinfo, f, ensure_ascii=False, indent=2)

    # Sample follow offsets from raw frames for perspective detection
    sample_offsets: list[list[float]] = []
    with open(raw_frames_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= 300:  # sample first 300 frames
                break
            line = line.strip()
            if line:
                rec = _json.loads(line)
                offset = rec.get("camera_follow_offset")
                if offset:
                    sample_offsets.append(offset)

    meta_dict = build_game_meta_dict(game_cfg, sample_offsets, width, height)
    write_game_meta_xlsx(meta_dict, str(session_path / "game_meta.xlsx"))
    print(f"[OK] Metadata written to {session_path}")
```

- [ ] **Step 4: Run tests**

```bash
cd control_center
python -m pytest tests/test_metadata_collector.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add control_center/metadata_collector.py control_center/tests/test_metadata_collector.py
git commit -m "feat: metadata_collector for systeminfo.json and game_meta.xlsx generation"
```

---

## Task 5: OSD Bridge + Python Entry Point

**Files:**
- Create: `control_center/osd_bridge.py`
- Create: `control_center/main.py`

- [ ] **Step 1: Implement osd_bridge.py**

This module writes to shared memory to control dx_capture's capture state and OSD content.

Create `control_center/osd_bridge.py`:

```python
from __future__ import annotations
import ctypes
import ctypes.wintypes as wt
import struct
from pathlib import Path

SHMEM_NAME = "WorldEngineCapture_SharedMem"
SHMEM_SIZE = 4096

# SharedFrameSync layout offsets (must match shared_protocol.h exactly)
# int64  frame_index        offset 0
# double present_time_ms    offset 8
# float  game_fps           offset 16
# int32  capture_active     offset 20
# int32  reserved           offset 24
# char[64] session_id       offset 28
# char[256] output_path     offset 92

OFFSET_FRAME_INDEX    = 0
OFFSET_PRESENT_TIME   = 8
OFFSET_GAME_FPS       = 16
OFFSET_CAPTURE_ACTIVE = 20
OFFSET_SESSION_ID     = 28
OFFSET_OUTPUT_PATH    = 92


class OsdBridge:
    def __init__(self) -> None:
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._handle = None
        self._view = None

    def open(self) -> bool:
        """Open existing shared memory created by dx_capture.dll. Returns True on success."""
        FILE_MAP_ALL_ACCESS = 0x000F001F
        self._handle = self._kernel32.OpenFileMappingW(FILE_MAP_ALL_ACCESS, False, SHMEM_NAME)
        if not self._handle:
            return False
        self._view = self._kernel32.MapViewOfFile(self._handle, FILE_MAP_ALL_ACCESS, 0, 0, SHMEM_SIZE)
        return bool(self._view)

    def close(self) -> None:
        if self._view:
            self._kernel32.UnmapViewOfFile(self._view)
        if self._handle:
            self._kernel32.CloseHandle(self._handle)

    def set_capture_active(self, active: bool) -> None:
        val = ctypes.c_int32(1 if active else 0)
        ctypes.memmove(self._view + OFFSET_CAPTURE_ACTIVE, ctypes.addressof(val), 4)

    def set_session(self, session_id: str, output_path: str) -> None:
        sid = session_id.encode("utf-8")[:63] + b"\x00"
        ctypes.memmove(self._view + OFFSET_SESSION_ID, sid, len(sid))
        pth = output_path.encode("utf-8")[:255] + b"\x00"
        ctypes.memmove(self._view + OFFSET_OUTPUT_PATH, pth, len(pth))

    def read_game_fps(self) -> float:
        val = ctypes.c_float()
        ctypes.memmove(ctypes.addressof(val), self._view + OFFSET_GAME_FPS, 4)
        return val.value

    def read_frame_index(self) -> int:
        val = ctypes.c_int64()
        ctypes.memmove(ctypes.addressof(val), self._view + OFFSET_FRAME_INDEX, 8)
        return val.value
```

- [ ] **Step 2: Implement main.py entry point**

Create `control_center/main.py`:

```python
import sys
import os

# Ensure control_center package root is on path when run directly
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication
from gui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("WorldEngine Data Collector")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
git add control_center/osd_bridge.py control_center/main.py
git commit -m "feat: osd_bridge shared memory writer, main.py entry point"
```

---

## Task 6: PyQt6 GUI

**Files:**
- Create: `control_center/gui/__init__.py`
- Create: `control_center/gui/main_window.py`
- Create: `control_center/gui/session_log.py`

- [ ] **Step 1: Create session_log.py**

Create `control_center/gui/__init__.py` (empty).

Create `control_center/gui/session_log.py`:

```python
from PyQt6.QtWidgets import QTextEdit
from PyQt6.QtCore import Qt


class SessionLog(QTextEdit):
    """Read-only scrolling log widget."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumHeight(200)

    def append_line(self, msg: str) -> None:
        self.append(msg)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
```

- [ ] **Step 2: Create main_window.py**

Create `control_center/gui/main_window.py`:

```python
from __future__ import annotations
import os
import threading
import yaml
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox, QLabel, QGroupBox, QStatusBar,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QKeySequence, QShortcut

from gui.session_log import SessionLog
from session_manager import SessionManager, SessionState
from pipe_reader import FrameBuffer, PipeServer
from osd_bridge import OsdBridge
from post_processor import process_session
from metadata_collector import collect_and_write


class _Signals(QObject):
    log = pyqtSignal(str)
    stats_updated = pyqtSignal(int, float, str)  # frames, fps, elapsed


class MainWindow(QMainWindow):
    GAMES_CONFIG_DIR = Path(__file__).parent.parent / "config" / "games"
    SETTINGS_PATH    = Path(__file__).parent.parent / "config" / "settings.yaml"

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("WorldEngine Data Collector")
        self.setMinimumSize(640, 480)

        self._sm = SessionManager(str(self.SETTINGS_PATH))
        self._osd = OsdBridge()
        self._frame_buffer: FrameBuffer | None = None
        self._pipe_server: PipeServer | None = None
        self._signals = _Signals()
        self._signals.log.connect(self._on_log)
        self._signals.stats_updated.connect(self._on_stats)
        self._start_time: datetime | None = None

        self._build_ui()
        self._load_game_list()
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._poll_stats)

        # F9 hotkey
        shortcut = QShortcut(QKeySequence("F9"), self)
        shortcut.activated.connect(self._toggle_recording)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Game selector
        game_row = QHBoxLayout()
        game_row.addWidget(QLabel("游戏:"))
        self._game_combo = QComboBox()
        self._game_combo.setMinimumWidth(200)
        game_row.addWidget(self._game_combo)
        game_row.addStretch()
        layout.addLayout(game_row)

        # Stats
        stats_group = QGroupBox("当前状态")
        stats_layout = QHBoxLayout(stats_group)
        self._lbl_frames = QLabel("帧数: 0")
        self._lbl_fps    = QLabel("游戏FPS: --")
        self._lbl_time   = QLabel("时长: 00:00")
        self._lbl_status = QLabel("待机")
        self._lbl_status.setStyleSheet("color: gray; font-weight: bold;")
        for w in [self._lbl_frames, self._lbl_fps, self._lbl_time, self._lbl_status]:
            stats_layout.addWidget(w)
        layout.addWidget(stats_group)

        # Log
        self._log = SessionLog()
        layout.addWidget(self._log)

        # Buttons
        btn_row = QHBoxLayout()
        self._btn_start = QPushButton("开始录制 (F9)")
        self._btn_start.setMinimumHeight(40)
        self._btn_start.clicked.connect(self._toggle_recording)
        btn_row.addWidget(self._btn_start)
        layout.addLayout(btn_row)

        self.setStatusBar(QStatusBar())

    def _load_game_list(self) -> None:
        self._game_combo.clear()
        for yaml_file in sorted(self.GAMES_CONFIG_DIR.glob("*.yaml")):
            with open(yaml_file, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            self._game_combo.addItem(cfg.get("game_name", yaml_file.stem), str(yaml_file))

    def _toggle_recording(self) -> None:
        if self._sm.state == SessionState.IDLE:
            self._start_recording()
        elif self._sm.state == SessionState.RECORDING:
            self._stop_recording()

    def _start_recording(self) -> None:
        yaml_path = self._game_combo.currentData()
        if not yaml_path:
            return
        self._sm.load_game(yaml_path)
        session_dir = self._sm.start_session()

        raw_path = session_dir / "raw_frames.jsonl"
        self._frame_buffer = FrameBuffer(str(raw_path))
        self._frame_buffer.open()

        self._pipe_server = PipeServer(self._frame_buffer)
        self._pipe_server.start()

        if self._osd.open():
            self._osd.set_session(session_dir.name, str(session_dir))
            self._osd.set_capture_active(True)
        else:
            self._signals.log.emit("[WARN] 无法连接 dx_capture.dll 共享内存，DLL 是否已加载？")

        self._start_time = datetime.now()
        self._timer.start()
        self._btn_start.setText("停止录制 (F9)")
        self._lbl_status.setText("录制中")
        self._lbl_status.setStyleSheet("color: red; font-weight: bold;")
        self._signals.log.emit(f"[录制开始] {session_dir.name}")

    def _stop_recording(self) -> None:
        self._osd.set_capture_active(False)
        self._osd.close()
        self._pipe_server.stop()
        self._frame_buffer.close()
        self._timer.stop()
        self._sm.stop_session()
        self._btn_start.setText("处理中…")
        self._btn_start.setEnabled(False)
        self._lbl_status.setText("处理中")
        self._lbl_status.setStyleSheet("color: orange; font-weight: bold;")
        self._signals.log.emit("[录制停止] 开始后处理…")

        session_dir = str(self._sm.session_dir)
        yaml_path = self._game_combo.currentData()

        def _process():
            try:
                process_session(session_dir)
                collect_and_write(
                    session_dir, yaml_path,
                    str(Path(session_dir) / "raw_frames.jsonl"),
                )
                self._signals.log.emit("[完成] 所有文件已生成")
            except Exception as e:
                self._signals.log.emit(f"[ERROR] 后处理失败: {e}")
            finally:
                self._sm.finish_processing()
                self._signals.stats_updated.emit(0, 0.0, "00:00")

        threading.Thread(target=_process, daemon=True).start()

    def _poll_stats(self) -> None:
        if not self._frame_buffer or not self._start_time:
            return
        frames = self._frame_buffer.frame_count
        fps = self._osd.read_game_fps() if self._osd._view else 0.0
        elapsed = datetime.now() - self._start_time
        mins, secs = divmod(int(elapsed.total_seconds()), 60)
        self._signals.stats_updated.emit(frames, fps, f"{mins:02d}:{secs:02d}")

    def _on_log(self, msg: str) -> None:
        self._log.append_line(msg)

    def _on_stats(self, frames: int, fps: float, elapsed: str) -> None:
        if self._sm.state == SessionState.IDLE:
            self._btn_start.setText("开始录制 (F9)")
            self._btn_start.setEnabled(True)
            self._lbl_status.setText("待机")
            self._lbl_status.setStyleSheet("color: gray; font-weight: bold;")
            return
        self._lbl_frames.setText(f"帧数: {frames}")
        self._lbl_fps.setText(f"游戏FPS: {fps:.1f}")
        self._lbl_time.setText(f"时长: {elapsed}")
```

- [ ] **Step 3: Smoke test the GUI**

```bash
cd control_center
python main.py
```

Expected: Window opens, shows game dropdown with "Valheim", Start button, log area. No crash.

- [ ] **Step 4: Commit**

```bash
git add control_center/gui/ control_center/main.py
git commit -m "feat: PyQt6 GUI - main_window with session lifecycle, F9 hotkey, live stats"
```

---

## Task 7: C# BepInEx Adapter — Models + CoordUtils (TDD)

**Files:**
- Create: `adapters/unity/WorldEngineCollector/src/Models/FrameData.cs`
- Create: `adapters/unity/WorldEngineCollector/src/Models/CoordUtils.cs`
- Create: `adapters/unity/WorldEngineCollector/tests/CoordUtilsTests.cs`

- [ ] **Step 1: Create FrameData.cs**

Create `adapters/unity/WorldEngineCollector/src/Models/FrameData.cs`:

```csharp
using System.Collections.Generic;
using Newtonsoft.Json;

namespace WorldEngine.Models
{
    public class CameraIntrinsics
    {
        [JsonProperty("fx")] public float Fx;
        [JsonProperty("fy")] public float Fy;
        [JsonProperty("cx")] public float Cx;
        [JsonProperty("cy")] public float Cy;
    }

    public class FrameData
    {
        [JsonProperty("time")]                        public string Time;
        [JsonProperty("fps")]                         public float Fps;
        [JsonProperty("frame")]                       public long Frame;
        [JsonProperty("camera_position")]             public float[] CameraPosition;        // [x,y,z]
        [JsonProperty("camera_rotation_quaternion")]  public float[] CameraRotationQuat;    // [x,y,z,w]
        [JsonProperty("camera_follow_offset")]        public float[] CameraFollowOffset;    // [x,y,z]
        [JsonProperty("camera_speed")]                public float[] CameraSpeed;           // [x,y,z] zero here
        [JsonProperty("camera_intrinsics")]           public CameraIntrinsics CameraIntrinsics;
        [JsonProperty("player_position")]             public float[] PlayerPosition;        // [x,y,z]
        [JsonProperty("player_rotation_eule")]        public float[] PlayerRotationEule;    // [x,y,z] degrees
        [JsonProperty("player_rotation_quaternion")]  public float[] PlayerRotationQuat;    // [x,y,z,w]
        [JsonProperty("player_speed")]                public float[] PlayerSpeed;           // [x,y,z] zero here
        [JsonProperty("metric_scale")]                public float MetricScale;
        [JsonProperty("mouse_x")]                     public float MouseX;
        [JsonProperty("mouse_y")]                     public float MouseY;
        [JsonProperty("mouse_dx")]                    public float MouseDx;
        [JsonProperty("mouse_dy")]                    public float MouseDy;
        [JsonProperty("keyCode")]                     public List<int> KeyCode;
        // Internal field passed to Python for fps.json (stripped by post_processor)
        [JsonProperty("_game_fps")]                   public float GameFps;
    }
}
```

- [ ] **Step 2: Create CoordUtils.cs**

Create `adapters/unity/WorldEngineCollector/src/Models/CoordUtils.cs`:

```csharp
using UnityEngine;
using WorldEngine.Models;

namespace WorldEngine.Models
{
    public static class CoordUtils
    {
        // Unity is natively left-hand Y-up — no coordinate conversion needed.
        // These are pass-through helpers for clarity and future non-Unity adapters.

        public static float[] Vec3(Vector3 v) => new[] { v.x, v.y, v.z };

        public static float[] Quat(Quaternion q) => new[] { q.x, q.y, q.z, q.w };

        /// <summary>Returns Euler angles in degrees [pitch(x), yaw(y), roll(z)].</summary>
        public static float[] EulerDeg(Quaternion q)
        {
            var e = q.eulerAngles;
            return new[] { e.x, e.y, e.z };
        }

        /// <summary>
        /// Camera position in player's local coordinate space.
        /// Result is the "follow offset" vector.
        /// </summary>
        public static float[] FollowOffset(Transform player, Transform camera) =>
            Vec3(player.InverseTransformPoint(camera.position));

        /// <summary>
        /// Compute camera intrinsic matrix parameters from Unity camera.
        /// fx = fy = (width/2) / tan(fovRad/2), cx = width/2, cy = height/2
        /// </summary>
        public static CameraIntrinsics CalcIntrinsics(float fovDeg, int width, int height)
        {
            float fovRad = fovDeg * Mathf.Deg2Rad;
            float fx = (width / 2f) / Mathf.Tan(fovRad / 2f);
            return new CameraIntrinsics
            {
                Fx = fx,
                Fy = fx,
                Cx = width / 2f,
                Cy = height / 2f,
            };
        }
    }
}
```

- [ ] **Step 3: Write unit tests (no Unity runtime needed)**

Create `adapters/unity/WorldEngineCollector/tests/CoordUtilsTests.cs`:

```csharp
// These tests use NUnit and reference UnityEngine stubs or run in a test harness.
// For CI without Unity: mock Vector3/Quaternion as simple structs.
// For manual verification: build and run in Valheim with BepInEx test runner.
using NUnit.Framework;
using WorldEngine.Models;
using UnityEngine;

namespace WorldEngine.Tests
{
    [TestFixture]
    public class CoordUtilsTests
    {
        [Test]
        public void Vec3_ReturnsCorrectComponents()
        {
            var result = CoordUtils.Vec3(new Vector3(1f, 2f, 3f));
            Assert.AreEqual(new[] { 1f, 2f, 3f }, result);
        }

        [Test]
        public void Quat_ReturnsXYZW()
        {
            var q = new Quaternion(0.1f, 0.2f, 0.3f, 0.9f);
            var result = CoordUtils.Quat(q);
            Assert.AreEqual(q.x, result[0], 1e-5f);
            Assert.AreEqual(q.w, result[3], 1e-5f);
        }

        [Test]
        public void CalcIntrinsics_1080p_60fov()
        {
            // fov=60°, 1920x1080: fx = (960) / tan(30°) = 960 / 0.5774 ≈ 1662.77
            var intr = CoordUtils.CalcIntrinsics(60f, 1920, 1080);
            Assert.AreEqual(960f, intr.Cx, 0.01f);
            Assert.AreEqual(540f, intr.Cy, 0.01f);
            Assert.AreEqual(intr.Fx, intr.Fy, 0.01f);
            Assert.AreEqual(1662.77f, intr.Fx, 1f);
        }

        [Test]
        public void EulerDeg_IdentityIsZero()
        {
            var result = CoordUtils.EulerDeg(Quaternion.identity);
            Assert.AreEqual(0f, result[0], 1e-4f);
            Assert.AreEqual(0f, result[1], 1e-4f);
            Assert.AreEqual(0f, result[2], 1e-4f);
        }
    }
}
```

- [ ] **Step 4: Build and run tests**

Open the project in Visual Studio, set references to your Valheim/BepInEx DLLs, then:

```
Build → Build Solution
Test → Run All Tests
```

Expected: 4 tests pass. If NUnit runner not available, verify logic manually in-game.

- [ ] **Step 5: Commit**

```bash
git add adapters/unity/WorldEngineCollector/src/Models/ \
        adapters/unity/WorldEngineCollector/tests/CoordUtilsTests.cs
git commit -m "feat: FrameData model + CoordUtils for Unity left-hand coordinate helpers"
```

---

## Task 8: C# BepInEx Adapter — SharedMem + PipeWriter + UIHider

**Files:**
- Create: `adapters/unity/WorldEngineCollector/src/SharedMemReader.cs`
- Create: `adapters/unity/WorldEngineCollector/src/PipeWriter.cs`
- Create: `adapters/unity/WorldEngineCollector/src/UIHider.cs`

- [ ] **Step 1: Implement SharedMemReader.cs**

Create `adapters/unity/WorldEngineCollector/src/SharedMemReader.cs`:

```csharp
using System;
using System.Runtime.InteropServices;
using System.Text;

namespace WorldEngine
{
    /// <summary>
    /// Opens the shared memory segment created by dx_capture.dll and reads/writes fields.
    /// Layout must match shared_protocol.h exactly.
    /// </summary>
    public class SharedMemReader : IDisposable
    {
        private const string SHMEM_NAME = "WorldEngineCapture_SharedMem";
        private const int FILE_MAP_ALL_ACCESS = 0x000F001F;

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr OpenFileMapping(int access, bool inherit, string name);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr MapViewOfFile(IntPtr handle, int access, uint offsetHi, uint offsetLo, UIntPtr size);

        [DllImport("kernel32.dll")]
        private static extern bool UnmapViewOfFile(IntPtr view);

        [DllImport("kernel32.dll")]
        private static extern bool CloseHandle(IntPtr handle);

        private IntPtr _handle = IntPtr.Zero;
        private IntPtr _view = IntPtr.Zero;

        // Offsets matching shared_protocol.h
        private const int OFF_FRAME_INDEX    = 0;   // int64
        private const int OFF_PRESENT_TIME   = 8;   // double
        private const int OFF_GAME_FPS       = 16;  // float
        private const int OFF_CAPTURE_ACTIVE = 20;  // int32
        private const int OFF_SESSION_ID     = 28;  // char[64]
        private const int OFF_OUTPUT_PATH    = 92;  // char[256]

        public bool IsOpen => _view != IntPtr.Zero;

        public bool Open()
        {
            _handle = OpenFileMapping(FILE_MAP_ALL_ACCESS, false, SHMEM_NAME);
            if (_handle == IntPtr.Zero) return false;
            _view = MapViewOfFile(_handle, FILE_MAP_ALL_ACCESS, 0, 0, UIntPtr.Zero);
            return _view != IntPtr.Zero;
        }

        public bool CaptureActive => _view != IntPtr.Zero &&
            Marshal.ReadInt32(_view, OFF_CAPTURE_ACTIVE) == 1;

        public long FrameIndex => _view != IntPtr.Zero ?
            Marshal.ReadInt64(_view, OFF_FRAME_INDEX) : 0;

        public float GameFps => _view != IntPtr.Zero ?
            BitConverter.ToSingle(BitConverter.GetBytes(Marshal.ReadInt32(_view, OFF_GAME_FPS)), 0) : 0f;

        public void Dispose()
        {
            if (_view != IntPtr.Zero) { UnmapViewOfFile(_view); _view = IntPtr.Zero; }
            if (_handle != IntPtr.Zero) { CloseHandle(_handle); _handle = IntPtr.Zero; }
        }
    }
}
```

- [ ] **Step 2: Implement PipeWriter.cs**

Create `adapters/unity/WorldEngineCollector/src/PipeWriter.cs`:

```csharp
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
```

- [ ] **Step 3: Implement UIHider.cs**

Create `adapters/unity/WorldEngineCollector/src/UIHider.cs`:

```csharp
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
```

- [ ] **Step 4: Commit**

```bash
git add adapters/unity/WorldEngineCollector/src/SharedMemReader.cs \
        adapters/unity/WorldEngineCollector/src/PipeWriter.cs \
        adapters/unity/WorldEngineCollector/src/UIHider.cs
git commit -m "feat: SharedMemReader, PipeWriter, UIHider for BepInEx adapter"
```

---

## Task 9: C# BepInEx Adapter — FrameCollector + Plugin Entry

**Files:**
- Create: `adapters/unity/WorldEngineCollector/src/FrameCollector.cs`
- Create: `adapters/unity/WorldEngineCollector/src/Plugin.cs`

- [ ] **Step 1: Implement FrameCollector.cs**

Create `adapters/unity/WorldEngineCollector/src/FrameCollector.cs`:

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;
using Newtonsoft.Json;
using WorldEngine.Models;

namespace WorldEngine
{
    /// <summary>
    /// Runs every LateUpdate during active capture. Collects all frame fields and
    /// sends them as a JSON line over the Named Pipe.
    /// </summary>
    public class FrameCollector : MonoBehaviour
    {
        public SharedMemReader SharedMem;
        public PipeWriter Pipe;
        public UIHider UIHider;
        public string PlayerObjectName = "Player(Clone)";

        private long _captureFrameIndex = 0;  // local counter — NOT from shared mem (timing issue)
        private float _accMouseX;
        private float _accMouseY;

        private void Start()
        {
            // Initialize accumulated mouse position to screen center
            _accMouseX = Screen.width / 2f;
            _accMouseY = Screen.height / 2f;
        }

        private void LateUpdate()
        {
            if (SharedMem == null || !SharedMem.CaptureActive) return;

            var cam = Camera.main;
            if (cam == null) return;

            var playerObj = GameObject.Find(PlayerObjectName);
            if (playerObj == null) return;

            // Hide UI before GPU readback in this frame's Present
            UIHider.HideAllUI();

            // Accumulate mouse position (cursor is locked, so simulate from delta)
            float dx = Input.GetAxisRaw("Mouse X");
            float dy = Input.GetAxisRaw("Mouse Y");
            _accMouseX = Mathf.Clamp(_accMouseX + dx, 0, Screen.width);
            _accMouseY = Mathf.Clamp(_accMouseY - dy, 0, Screen.height); // flip Y (screen top=0)

            var data = new FrameData
            {
                Frame                = _captureFrameIndex,
                Time                 = DateTime.UtcNow.ToString("yyyy-MM-dd HH:mm:ss.fff"),
                Fps                  = 30f,
                CameraPosition       = CoordUtils.Vec3(cam.transform.position),
                CameraRotationQuat   = CoordUtils.Quat(cam.transform.rotation),
                CameraFollowOffset   = CoordUtils.FollowOffset(playerObj.transform, cam.transform),
                CameraSpeed          = new[] { 0f, 0f, 0f },  // computed offline
                CameraIntrinsics     = CoordUtils.CalcIntrinsics(cam.fieldOfView, Screen.width, Screen.height),
                PlayerPosition       = CoordUtils.Vec3(playerObj.transform.position),
                PlayerRotationEule   = CoordUtils.EulerDeg(playerObj.transform.rotation),
                PlayerRotationQuat   = CoordUtils.Quat(playerObj.transform.rotation),
                PlayerSpeed          = new[] { 0f, 0f, 0f },  // computed offline
                MetricScale          = 1.0f,
                MouseX               = _accMouseX,
                MouseY               = _accMouseY,
                MouseDx              = dx,
                MouseDy              = dy,
                KeyCode              = GetPressedKeyCodes(),
                GameFps              = SharedMem.GameFps,      // written to _game_fps in JSON
            };

            Pipe.WriteLine(JsonConvert.SerializeObject(data));

            // Restore UI after Present completes (WaitForEndOfFrame coroutine)
            UIHider.ScheduleRestore();

            _captureFrameIndex++;
        }

        private static List<int> GetPressedKeyCodes()
        {
            var codes = new List<int>();
            foreach (KeyCode kc in Enum.GetValues(typeof(KeyCode)))
            {
                // Skip mouse buttons and joystick axes (only keyboard scan codes)
                if (kc >= KeyCode.Mouse0 && kc <= KeyCode.Mouse6) continue;
                if (kc >= KeyCode.JoystickButton0) continue;
                if (Input.GetKey(kc))
                    codes.Add((int)kc);
            }
            return codes;
        }
    }
}
```

- [ ] **Step 2: Implement Plugin.cs**

Create `adapters/unity/WorldEngineCollector/src/Plugin.cs`:

```csharp
using BepInEx;
using BepInEx.Logging;
using System.IO;
using UnityEngine;

namespace WorldEngine
{
    [BepInPlugin("com.worldengine.collector", "WorldEngine Collector", "1.0.0")]
    public class Plugin : BaseUnityPlugin
    {
        internal static ManualLogSource Log;

        private SharedMemReader _sharedMem;
        private PipeWriter _pipe;
        private UIHider _uiHider;
        private FrameCollector _collector;

        private void Awake()
        {
            Log = Logger;
            Log.LogInfo("WorldEngine Collector starting...");

            // Load dx_capture.dll from the same directory as this plugin
            string dxCapturePath = Path.Combine(Path.GetDirectoryName(Info.Location), "..", "..", "dx_capture.dll");
            if (File.Exists(dxCapturePath))
            {
                System.Runtime.InteropServices.NativeLibrary.Load(dxCapturePath);
                Log.LogInfo($"Loaded dx_capture.dll from {dxCapturePath}");
            }
            else
            {
                Log.LogWarning($"dx_capture.dll not found at {dxCapturePath}. Video capture disabled.");
            }

            // Wire up components as MonoBehaviours on a persistent GameObject
            var go = new GameObject("WorldEngineCollector");
            DontDestroyOnLoad(go);

            _sharedMem = new SharedMemReader();
            if (!_sharedMem.Open())
                Log.LogWarning("Could not open shared memory. Is dx_capture.dll loaded?");

            // PipeWriter is a plain C# class (not MonoBehaviour) — instantiate directly
            _pipe = new PipeWriter();
            _uiHider = go.AddComponent<UIHider>();

            _collector = go.AddComponent<FrameCollector>();
            _collector.SharedMem = _sharedMem;
            _collector.Pipe = _pipe;
            _collector.UIHider = _uiHider;
            _collector.PlayerObjectName = "Player(Clone)";

            Log.LogInfo("WorldEngine Collector ready. Press F9 in control center to start.");
        }

        private void OnDestroy()
        {
            _sharedMem?.Dispose();
            _pipe?.Dispose();
        }
    }
}
```

> **Note on PipeWriter MonoBehaviour**: `PipeWriter` above is added as a MonoBehaviour but it doesn't use Unity lifecycle methods — it only needs to exist on a GameObject for Unity memory management. The `AddComponent` pattern is the correct way to attach it.

- [ ] **Step 3: Build plugin DLL**

In Visual Studio:
```
Build → Build Solution
```

Copy output `WorldEngineCollector.dll` to:
```
C:\Steam\steamapps\common\Valheim\BepInEx\plugins\WorldEngineCollector.dll
```

- [ ] **Step 4: Smoke test in Valheim (without dx_capture.dll yet)**

1. Start Valheim
2. Check BepInEx console for: `WorldEngine Collector ready`
3. Check for warning: `Could not open shared memory` (expected — dx_capture not built yet)
4. Start Python control center: `python main.py`
5. Select Valheim, click "Start Recording"
6. GUI should show warning in log: `无法连接 dx_capture.dll 共享内存`
7. Data pipe should be waiting for connection — no crash

- [ ] **Step 5: Commit**

```bash
git add adapters/unity/WorldEngineCollector/src/FrameCollector.cs \
        adapters/unity/WorldEngineCollector/src/Plugin.cs
git commit -m "feat: FrameCollector LateUpdate data collection, Plugin BepInEx entry point"
```

---

## Task 10: C++ dx_capture.dll — Shared Memory Module

**Files:**
- Create: `dx_capture/src/shared_mem.cpp`
- Create: `dx_capture/include/shared_mem.h`

- [ ] **Step 1: Implement shared_mem.h**

Create `dx_capture/include/shared_mem.h`:

```cpp
#pragma once
#include "shared_protocol.h"
#include <windows.h>

class SharedMemServer {
public:
    SharedMemServer();
    ~SharedMemServer();

    bool Create();   // call from DllMain
    void Destroy();  // call from DllMain

    SharedFrameSync* Get() { return _data; }

    void IncrementFrame();
    void SetGameFps(float fps);
    bool IsCaptureActive() const;

    // Win32 Event for notifying adapters of new frame
    HANDLE FrameEvent() const { return _frameEvent; }

private:
    HANDLE _mapHandle  = nullptr;
    HANDLE _frameEvent = nullptr;
    SharedFrameSync* _data = nullptr;
};
```

- [ ] **Step 2: Implement shared_mem.cpp**

Create `dx_capture/src/shared_mem.cpp`:

```cpp
#include "shared_mem.h"
#include <stdexcept>
#include <cstring>

SharedMemServer::SharedMemServer() = default;

SharedMemServer::~SharedMemServer() { Destroy(); }

bool SharedMemServer::Create()
{
    _mapHandle = CreateFileMappingA(
        INVALID_HANDLE_VALUE, nullptr,
        PAGE_READWRITE, 0, sizeof(SharedFrameSync),
        WORLDENGINE_SHMEM_NAME
    );
    if (!_mapHandle) return false;

    _data = static_cast<SharedFrameSync*>(
        MapViewOfFile(_mapHandle, FILE_MAP_ALL_ACCESS, 0, 0, 0)
    );
    if (!_data) return false;

    ZeroMemory(_data, sizeof(SharedFrameSync));

    _frameEvent = CreateEventA(nullptr, FALSE, FALSE, WORLDENGINE_FRAME_EVENT);
    return _frameEvent != nullptr;
}

void SharedMemServer::Destroy()
{
    if (_data)       { UnmapViewOfFile(_data);    _data = nullptr; }
    if (_mapHandle)  { CloseHandle(_mapHandle);   _mapHandle = nullptr; }
    if (_frameEvent) { CloseHandle(_frameEvent);  _frameEvent = nullptr; }
}

void SharedMemServer::IncrementFrame()
{
    if (!_data) return;
    InterlockedIncrement64(&_data->frame_index);
    SetEvent(_frameEvent);
}

void SharedMemServer::SetGameFps(float fps)
{
    if (_data) _data->game_fps = fps;
}

bool SharedMemServer::IsCaptureActive() const
{
    return _data && _data->capture_active == 1;
}
```

- [ ] **Step 3: Commit**

```bash
git add dx_capture/include/shared_mem.h dx_capture/src/shared_mem.cpp
git commit -m "feat: dx_capture shared memory server (create/destroy/increment/fps)"
```

---

## Task 11: C++ dx_capture.dll — DXGI Present Hook + Staging Pool

**Files:**
- Create: `dx_capture/include/dx_hook.h`
- Create: `dx_capture/src/dx_hook.cpp`

- [ ] **Step 1: Implement dx_hook.h**

Create `dx_capture/include/dx_hook.h`:

```cpp
#pragma once
#include <d3d11.h>
#include <dxgi.h>
#include <functional>

// Callback type: called every captured frame (every 2nd Present when recording)
using FrameCapturedCallback = std::function<void(ID3D11Texture2D* stagingTex, UINT width, UINT height)>;

class DxHook {
public:
    bool Install(FrameCapturedCallback onFrame);
    void Remove();

    UINT Width()  const { return _width; }
    UINT Height() const { return _height; }

private:
    static HRESULT STDMETHODCALLTYPE PresentHook(
        IDXGISwapChain* swapChain, UINT syncInterval, UINT flags);

    bool InitStagingPool(ID3D11Device* device, UINT width, UINT height);

    static DxHook* s_instance;

    ID3D11Device*        _device        = nullptr;
    ID3D11DeviceContext* _context       = nullptr;
    // Ring buffer of 3 staging textures to avoid blocking encoder thread
    static constexpr int POOL_SIZE = 3;
    ID3D11Texture2D*     _stagingPool[POOL_SIZE] = {};
    int                  _poolIdx       = 0;

    UINT _width  = 1920;
    UINT _height = 1080;
    UINT64 _frameCounter = 0;
    LARGE_INTEGER _lastPresentTime = {};
    LARGE_INTEGER _perfFreq        = {};

    FrameCapturedCallback _onFrame;
    void* _originalPresent = nullptr;
};
```

- [ ] **Step 2: Implement dx_hook.cpp**

Create `dx_capture/src/dx_hook.cpp`:

```cpp
#include "dx_hook.h"
#include "shared_mem.h"
#include <MinHook.h>
#include <d3d11.h>
#include <dxgi.h>
#include <cassert>

DxHook* DxHook::s_instance = nullptr;

// Extern reference to global shared mem (defined in dllmain.cpp)
extern SharedMemServer g_sharedMem;

bool DxHook::Install(FrameCapturedCallback onFrame)
{
    s_instance = this;
    _onFrame = onFrame;
    QueryPerformanceFrequency(&_perfFreq);

    // Create a temporary D3D11 device + swap chain just to get the vtable pointer
    DXGI_SWAP_CHAIN_DESC scd = {};
    scd.BufferCount       = 1;
    scd.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    scd.BufferUsage       = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    scd.OutputWindow      = GetDesktopWindow();
    scd.SampleDesc.Count  = 1;
    scd.Windowed          = TRUE;
    scd.SwapEffect        = DXGI_SWAP_EFFECT_DISCARD;

    IDXGISwapChain* tempChain = nullptr;
    ID3D11Device* tempDevice  = nullptr;
    ID3D11DeviceContext* tempCtx = nullptr;

    if (FAILED(D3D11CreateDeviceAndSwapChain(
            nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, 0,
            nullptr, 0, D3D11_SDK_VERSION,
            &scd, &tempChain, &tempDevice, nullptr, &tempCtx)))
        return false;

    // vtable[8] = IDXGISwapChain::Present
    void** vtable = *reinterpret_cast<void***>(tempChain);
    void* presentAddr = vtable[8];

    tempChain->Release();
    tempDevice->Release();
    tempCtx->Release();

    MH_Initialize();
    MH_CreateHook(presentAddr, &PresentHook, &_originalPresent);
    MH_EnableHook(presentAddr);
    return true;
}

void DxHook::Remove()
{
    MH_DisableHook(MH_ALL_HOOKS);
    MH_Uninitialize();
    for (int i = 0; i < POOL_SIZE; i++)
        if (_stagingPool[i]) { _stagingPool[i]->Release(); _stagingPool[i] = nullptr; }
}

bool DxHook::InitStagingPool(ID3D11Device* device, UINT width, UINT height)
{
    D3D11_TEXTURE2D_DESC desc = {};
    desc.Width  = width;
    desc.Height = height;
    desc.MipLevels = 1;
    desc.ArraySize = 1;
    desc.Format    = DXGI_FORMAT_B8G8R8A8_UNORM;
    desc.SampleDesc.Count = 1;
    desc.Usage     = D3D11_USAGE_STAGING;
    desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;

    for (int i = 0; i < POOL_SIZE; i++) {
        if (FAILED(device->CreateTexture2D(&desc, nullptr, &_stagingPool[i])))
            return false;
    }
    _width  = width;
    _height = height;
    return true;
}

HRESULT STDMETHODCALLTYPE DxHook::PresentHook(
    IDXGISwapChain* swapChain, UINT syncInterval, UINT flags)
{
    auto* self = s_instance;

    // Lazy-init device and staging pool on first call
    if (!self->_device) {
        swapChain->GetDevice(__uuidof(ID3D11Device), reinterpret_cast<void**>(&self->_device));
        self->_device->GetImmediateContext(&self->_context);

        ID3D11Texture2D* backBuf = nullptr;
        swapChain->GetBuffer(0, __uuidof(ID3D11Texture2D), reinterpret_cast<void**>(&backBuf));
        D3D11_TEXTURE2D_DESC bDesc;
        backBuf->GetDesc(&bDesc);
        backBuf->Release();

        self->InitStagingPool(self->_device, bDesc.Width, bDesc.Height);
    }

    // Compute game FPS
    LARGE_INTEGER now;
    QueryPerformanceCounter(&now);
    if (self->_lastPresentTime.QuadPart > 0) {
        double dt_ms = 1000.0 * (now.QuadPart - self->_lastPresentTime.QuadPart)
                       / self->_perfFreq.QuadPart;
        g_sharedMem.SetGameFps(dt_ms > 0 ? static_cast<float>(1000.0 / dt_ms) : 0.f);
        g_sharedMem.Get()->present_time_ms = static_cast<double>(now.QuadPart) * 1000.0
                                              / self->_perfFreq.QuadPart;
    }
    self->_lastPresentTime = now;

    // Update frame counter in shared memory + notify adapters
    g_sharedMem.IncrementFrame();
    self->_frameCounter++;

    // Capture every 2nd frame (30fps from 60fps) when recording
    if (g_sharedMem.IsCaptureActive() && (self->_frameCounter % 2 == 0))
    {
        int idx = self->_poolIdx % POOL_SIZE;
        ID3D11Texture2D* backBuf = nullptr;
        if (SUCCEEDED(swapChain->GetBuffer(0, __uuidof(ID3D11Texture2D),
                                            reinterpret_cast<void**>(&backBuf))))
        {
            self->_context->CopyResource(self->_stagingPool[idx], backBuf);
            backBuf->Release();
            if (self->_onFrame)
                self->_onFrame(self->_stagingPool[idx], self->_width, self->_height);
            self->_poolIdx++;
        }
    }

    // Call original Present
    using PresentFn = HRESULT(STDMETHODCALLTYPE*)(IDXGISwapChain*, UINT, UINT);
    return reinterpret_cast<PresentFn>(self->_originalPresent)(swapChain, syncInterval, flags);
}
```

- [ ] **Step 3: Commit**

```bash
git add dx_capture/include/dx_hook.h dx_capture/src/dx_hook.cpp
git commit -m "feat: DXGI Present hook with 3-texture staging pool, FPS measurement"
```

---

## Task 12: C++ dx_capture.dll — FFmpeg Encoder + OSD + DllMain

**Files:**
- Create: `dx_capture/include/encoder.h`
- Create: `dx_capture/src/encoder.cpp`
- Create: `dx_capture/include/osd.h`
- Create: `dx_capture/src/osd.cpp`
- Create: `dx_capture/src/dllmain.cpp`

- [ ] **Step 1: Implement encoder.h / encoder.cpp**

Create `dx_capture/include/encoder.h`:

```cpp
#pragma once
#include <d3d11.h>
#include <string>
#include <thread>
#include <queue>
#include <mutex>
#include <condition_variable>

struct EncodeJob {
    ID3D11Texture2D*     texture;
    ID3D11DeviceContext* context;
    UINT width, height;
};

class Encoder {
public:
    bool Start(const std::string& outputMp4Path, UINT width, UINT height, int fps = 30);
    void Stop();
    void Submit(ID3D11Texture2D* stagingTex, ID3D11DeviceContext* ctx, UINT w, UINT h);

private:
    void EncoderThread();

    FILE* _ffmpegPipe = nullptr;
    std::thread _thread;
    std::queue<EncodeJob> _jobs;
    std::mutex _mutex;
    std::condition_variable _cv;
    bool _running = false;
    UINT _width = 1920, _height = 1080;
};
```

Create `dx_capture/src/encoder.cpp`:

```cpp
#include "encoder.h"
#include <cstdio>
#include <stdexcept>
#include <vector>
#include <d3d11.h>

bool Encoder::Start(const std::string& outputPath, UINT width, UINT height, int fps)
{
    _width  = width;
    _height = height;

    // Build FFmpeg command with NVENC
    char cmd[2048];
    snprintf(cmd, sizeof(cmd),
        "ffmpeg -y -f rawvideo -pixel_format bgra -video_size %ux%u -framerate %d "
        "-i pipe:0 -c:v h264_nvenc -preset p4 -b:v 8M -pix_fmt yuv420p "
        "-movflags +faststart \"%s\" 2>NUL",
        width, height, fps, outputPath.c_str());

    _ffmpegPipe = _popen(cmd, "wb");
    if (!_ffmpegPipe)
        return false;

    _running = true;
    _thread = std::thread(&Encoder::EncoderThread, this);
    return true;
}

void Encoder::Stop()
{
    {
        std::lock_guard<std::mutex> lock(_mutex);
        _running = false;
    }
    _cv.notify_all();
    if (_thread.joinable()) _thread.join();
    if (_ffmpegPipe) { _pclose(_ffmpegPipe); _ffmpegPipe = nullptr; }
}

void Encoder::Submit(ID3D11Texture2D* stagingTex, ID3D11DeviceContext* ctx, UINT w, UINT h)
{
    std::lock_guard<std::mutex> lock(_mutex);
    _jobs.push({stagingTex, ctx, w, h});
    _cv.notify_one();
}

void Encoder::EncoderThread()
{
    while (true) {
        EncodeJob job;
        {
            std::unique_lock<std::mutex> lock(_mutex);
            _cv.wait(lock, [this]{ return !_jobs.empty() || !_running; });
            if (!_running && _jobs.empty()) break;
            job = _jobs.front();
            _jobs.pop();
        }

        D3D11_MAPPED_SUBRESOURCE mapped = {};
        HRESULT hr = job.context->Map(job.texture, 0, D3D11_MAP_READ, 0, &mapped);
        if (SUCCEEDED(hr)) {
            // Write row by row (handle row pitch != width*4)
            UINT rowBytes = job.width * 4;
            const BYTE* src = static_cast<const BYTE*>(mapped.pData);
            for (UINT row = 0; row < job.height; row++) {
                fwrite(src + row * mapped.RowPitch, 1, rowBytes, _ffmpegPipe);
            }
            job.context->Unmap(job.texture, 0);
        }
    }
}
```

- [ ] **Step 2: Implement simple OSD**

Create `dx_capture/include/osd.h`:

```cpp
#pragma once
#include <d3d11.h>
#include <dxgi.h>
#include <string>

// Simple D2D1 text overlay on top of the swapchain
class Osd {
public:
    bool Init(IDXGISwapChain* swapChain);
    void Render(const std::wstring& line1, const std::wstring& line2);
    void Destroy();
private:
    // D2D1 objects initialized lazily
    void* _renderTarget = nullptr;  // ID2D1RenderTarget*
    void* _textFormat   = nullptr;  // IDWriteTextFormat*
    void* _brush        = nullptr;  // ID2D1SolidColorBrush*
    bool  _initialized  = false;
};
```

Create `dx_capture/src/osd.cpp`:

```cpp
#include "osd.h"
#include <d2d1.h>
#include <dwrite.h>
#pragma comment(lib, "d2d1")
#pragma comment(lib, "dwrite")

// Minimal D2D1 overlay — renders two lines of status text
bool Osd::Init(IDXGISwapChain* swapChain)
{
    // D2D1 initialization is deferred; return true to signal readiness
    // Full implementation uses ID2D1Factory + DXGI surface interop
    _initialized = true;
    return true;
}

void Osd::Render(const std::wstring& line1, const std::wstring& line2)
{
    // Implementation: create D2D1 render target on DXGI backbuffer surface,
    // draw white text with black outline in top-left corner.
    // Stub: no-op in Phase 1 to keep dx_capture scope manageable.
    // The OSD data (fps, frames) is still visible in the Python GUI.
    (void)line1; (void)line2;
}

void Osd::Destroy() { _initialized = false; }
```

> **Note:** Full D2D1 OSD is a stub in Phase 1. The Python GUI shows the same stats. Implement fully in Phase 2 if needed.

- [ ] **Step 3: Implement dllmain.cpp**

Create `dx_capture/src/dllmain.cpp`:

```cpp
#include <windows.h>
#include "shared_mem.h"
#include "dx_hook.h"
#include "encoder.h"
#include "osd.h"
#include <string>

// Globals accessible from dx_hook.cpp
SharedMemServer g_sharedMem;
static DxHook   g_hook;
static Encoder  g_encoder;
static Osd      g_osd;
static bool     g_initialized = false;

static void Initialize()
{
    if (g_initialized) return;
    g_initialized = true;

    if (!g_sharedMem.Create()) {
        OutputDebugStringA("[dx_capture] Failed to create shared memory\n");
        return;
    }

    g_hook.Install([](ID3D11Texture2D* tex, UINT w, UINT h) {
        // Called every captured frame (30fps)
        SharedFrameSync* s = g_sharedMem.Get();
        if (!s || !s->capture_active) return;

        // Start encoder if not running (lazy start on first captured frame)
        static bool encoderStarted = false;
        if (!encoderStarted) {
            std::string outPath = std::string(s->output_path) + "\\video.mp4";
            if (g_encoder.Start(outPath, w, h, 30)) {
                encoderStarted = true;
                OutputDebugStringA("[dx_capture] Encoder started\n");
            }
        }

        // Encoder stores device context internally (passed at Start() time via g_hook.Context())
        g_encoder.Submit(tex);
    });

    OutputDebugStringA("[dx_capture] Initialized OK\n");
}

static void Shutdown()
{
    g_hook.Remove();
    g_encoder.Stop();
    g_sharedMem.Destroy();
    g_initialized = false;
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID)
{
    switch (reason) {
        case DLL_PROCESS_ATTACH:
            DisableThreadLibraryCalls(hModule);
            // Use a new thread to avoid holding the loader lock
            CreateThread(nullptr, 0,
                [](LPVOID) -> DWORD { Initialize(); return 0; },
                nullptr, 0, nullptr);
            break;
        case DLL_PROCESS_DETACH:
            Shutdown();
            break;
    }
    return TRUE;
}
```

```cpp
// In encoder.h — store context at Start() time:
class Encoder {
public:
    bool Start(const std::string& outputMp4Path, UINT width, UINT height,
               ID3D11DeviceContext* ctx, int fps = 30);
    void Stop();
    void Submit(ID3D11Texture2D* stagingTex);  // context stored internally
private:
    void EncoderThread();
    FILE* _ffmpegPipe = nullptr;
    std::thread _thread;
    std::queue<ID3D11Texture2D*> _jobs;  // just texture pointer, context is shared
    std::mutex _mutex;
    std::condition_variable _cv;
    bool _running = false;
    UINT _width = 1920, _height = 1080;
    ID3D11DeviceContext* _ctx = nullptr;  // stored at Start()
};
```

In `encoder.cpp`:
```cpp
bool Encoder::Start(const std::string& path, UINT w, UINT h, ID3D11DeviceContext* ctx, int fps) {
    _ctx = ctx;   // store context once
    // ... rest unchanged ...
}
void Encoder::Submit(ID3D11Texture2D* stagingTex) {
    std::lock_guard<std::mutex> lock(_mutex);
    _jobs.push(stagingTex);
    _cv.notify_one();
}
// EncoderThread uses _ctx->Map() directly (no job.context)
```

In `dllmain.cpp`, pass context when starting encoder:
```cpp
g_encoder.Start(outPath, w, h, /* get context */ hookContext, 30);
```
Expose `DxHook::Context()` getter returning `_context` to pass to encoder.

- [ ] **Step 4: Build dx_capture.dll**

```
cmake -S dx_capture -B dx_capture/build -G "Visual Studio 17 2022" -A x64
cmake --build dx_capture/build --config Release
```

Expected: `adapters/bin/dx_capture.dll` created.

- [ ] **Step 5: Copy to Valheim BepInEx folder**

```
copy adapters\bin\dx_capture.dll C:\Steam\steamapps\common\Valheim\BepInEx\plugins\dx_capture.dll
```

- [ ] **Step 6: Commit**

```bash
git add dx_capture/src/ dx_capture/include/
git commit -m "feat: dx_capture.dll - FFmpeg NVENC encoder, DXGI hook, shared mem, dllmain"
```

---

## Task 13: Full Integration Test with Valheim

This task validates the entire pipeline end-to-end.

- [ ] **Step 1: Verify BepInEx loads both DLLs**

1. Copy `dx_capture.dll` and `WorldEngineCollector.dll` to `BepInEx/plugins/`
2. Launch Valheim
3. Open BepInEx console (enabled in `BepInEx/config/BepInEx.cfg`, set `Enabled = true` under `[Logging.Console]`)
4. Verify console shows:
   ```
   [Info   : WorldEngine] Loaded dx_capture.dll from ...
   [Info   : WorldEngine] WorldEngine Collector ready. Press F9 in control center to start.
   ```

- [ ] **Step 2: Start a recording session**

1. Start Python control center: `python control_center/main.py`
2. Select "Valheim" in dropdown
3. Switch to Valheim, load a world, walk around outdoors
4. Press **F9** (or click "开始录制" in GUI)
5. Confirm GUI shows:
   - Status: 录制中 (red)
   - Frame count incrementing
   - Game FPS > 60
6. Walk around for at least 1 minute

- [ ] **Step 3: Stop and verify output**

1. Press **F9** again to stop
2. GUI shows "处理中…" then "完成"
3. Open the session folder (configured in `settings.yaml → output_dir`):
   ```
   session_YYYYMMDD_HHMMSS_valheim/
   ├── video.mp4           ← exists, plays in VLC
   ├── action_camera.json  ← exists, valid JSONL
   ├── systeminfo.json     ← exists
   ├── fps.json            ← exists
   └── game_meta.xlsx      ← exists
   ```

- [ ] **Step 4: Validate video**

```bash
ffprobe -v quiet -print_format json -show_streams session_.../video.mp4
```

Expected JSON contains:
```json
"width": 1920,
"height": 1080,
"r_frame_rate": "30/1",
"codec_name": "h264"
```

- [ ] **Step 5: Validate action_camera.json**

```bash
cd control_center
python - << 'EOF'
import json
from pathlib import Path

path = Path(input("Session path: ")) / "action_camera.json"
frames = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
print(f"Total frames: {len(frames)}")
print(f"First frame keys: {list(frames[0].keys())}")

# Check required fields
required = ["time","fps","frame","camera_position","camera_rotation_quaternion",
            "camera_follow_offset","camera_speed","camera_intrinsics",
            "player_position","player_rotation_eule","player_rotation_quaternion",
            "player_speed","metric_scale","mouse_x","mouse_y","mouse_dx","mouse_dy","keyCode"]
missing = [k for k in required if k not in frames[0]]
print(f"Missing fields: {missing}")  # should be []

# Check frame alignment (no gaps)
for i in range(1, len(frames)):
    assert frames[i]["frame"] == frames[i-1]["frame"] + 1, f"Gap at frame {i}"
print("Frame continuity: OK")

# Check camera_speed is non-zero (offline computed)
has_speed = any(any(v != 0.0 for v in f["camera_speed"]) for f in frames[1:])
print(f"Camera speed computed: {has_speed}")  # should be True
EOF
```

Expected output:
```
Total frames: ~1800  (1 min @ 30fps)
Missing fields: []
Frame continuity: OK
Camera speed computed: True
```

- [ ] **Step 6: Validate fps.json**

```bash
python - << 'EOF'
import json
from pathlib import Path
path = Path(input("Session path: ")) / "fps.json"
records = json.loads(path.read_text())
min_fps = min(r["fps"] for r in records)
avg_fps = sum(r["fps"] for r in records) / len(records)
print(f"Min game FPS: {min_fps:.1f}  (must be >= 60)")
print(f"Avg game FPS: {avg_fps:.1f}")
assert min_fps >= 60, "FAIL: game FPS dropped below 60"
print("FPS validation: PASS")
EOF
```

- [ ] **Step 7: Final commit**

```bash
git add .
git commit -m "feat: Phase 1 complete — Valheim full pipeline validated"
```

---

## Acceptance Checklist

Run this after Step 13 passes:

| 验收项 | 验证方式 | 状态 |
|--------|---------|------|
| 视频 1920×1080 | ffprobe width/height | ☐ |
| 视频 30fps | ffprobe r_frame_rate | ☐ |
| 视频无UI | 目视检查 VLC | ☐ |
| 游戏FPS≥60 | fps.json min_fps | ☐ |
| 所有字段存在 | Python missing fields check | ☐ |
| 帧连续无跳帧 | Frame continuity check | ☐ |
| camera_speed 非零 | Python speed check | ☐ |
| metric_scale=1.0 | 目视 action_camera.json | ☐ |
| keyCode 为 int[] | 目视 action_camera.json | ☐ |
| systeminfo.json 存在 | ls session dir | ☐ |
| game_meta.xlsx 存在 | ls session dir | ☐ |
