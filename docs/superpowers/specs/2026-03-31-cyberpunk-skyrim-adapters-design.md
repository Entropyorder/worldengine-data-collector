# Design: Cyberpunk 2077 + Skyrim SE Adapters

**Date:** 2026-03-31  
**Status:** Approved  
**Scope:** Add two new game adapters (CP2077 via CET Lua, Skyrim SE via SKSE C++) plus Python TCP transport layer.

---

## 1. Goals

Extend WorldEngine Data Collector to support two additional games with the exact same FrameData schema as Valheim:

- `time`, `fps`, `frame`
- `camera_position`, `camera_rotation_quaternion`, `camera_follow_offset`, `camera_speed`, `camera_intrinsics`
- `player_position`, `player_rotation_eule`, `player_rotation_quaternion`, `player_speed`
- `metric_scale`, `mouse_x`, `mouse_y`, `mouse_dx`, `mouse_dy`, `keyCode`, `_game_fps`

**Constraints:**
- Each game is independently deployable; installing one does not require the others
- Only one game runs at a time — single shared TCP port (27015)
- Adapter data emission is gated on dx_capture's FrameIndex (frame-aligned, not every game tick)
- Sending must not block the game's main thread

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Python Control Center                   │
│  SessionManager → FrameBuffer → post_processor          │
│                       ↑                                 │
│              TransportReader (abstract)                  │
│           ┌──────────┴──────────┐                       │
│     NamedPipeReader          TCPReader (new)             │
└─────────────────────────────────────────────────────────┘
         ↑ Named Pipe              ↑ TCP localhost:27015
         │                        │
   Valheim                  CP2077        Skyrim SE
   (BepInEx C#)          (CET Lua)      (SKSE C++)
```

Transport is selected per-game via `transport` field in `game.yaml`. Never two games simultaneously.

---

## 3. Python Transport Layer

### Files changed
- `control_center/pipe_reader.py` — add `TransportReader` ABC, `TCPReader`; wrap existing logic in `NamedPipeReader`

### Interface
```python
class TransportReader(ABC):
    @abstractmethod
    def read_lines(self) -> Iterator[str]: ...
    @abstractmethod
    def close(self) -> None: ...

class NamedPipeReader(TransportReader):
    # existing logic, unchanged behaviour

class TCPReader(TransportReader):
    def __init__(self, port: int = 27015): ...
    # listen on localhost:port
    # accept one connection, read lines
    # socket.setblocking(False) + select — never blocks UI thread
```

### SessionManager change
```python
transport = game_config.get("transport", "namedpipe")
if transport == "tcp":
    self._reader = TCPReader(port=game_config.get("tcp_port", 27015))
else:
    self._reader = NamedPipeReader(pipe_name="WorldEngineData")
```

### Valheim yaml addition
```yaml
transport: namedpipe   # backward-compatible, behaviour unchanged
```

---

## 4. Game Configs

### `config/games/cyberpunk2077.yaml`
```yaml
game_name: "Cyberpunk 2077"
process_name: "Cyberpunk2077"
engine: redengine
adapter_type: cet_lua
transport: tcp
tcp_port: 27015
capture_fps: 30
game_target_fps: 60
coordinate_system: right_hand_y_up
metric_scale: 1.0
player_object_name: "V"
ui_hide_method: none   # CET handles UI hiding via Game.GetUISystem()

key_mapping:
  87:  "前进(W)"
  83:  "后退(S)"
  65:  "左移(A)"
  68:  "右移(D)"
  32:  "跳跃(Space)"
  160: "冲刺(LShift)"
  70:  "翻滚(F)"
  69:  "交互(E)"
  82:  "上车/下车(R)"
  67:  "蹲下(C)"
  18:  "瞄准(LAlt)"
  1:   "攻击(LMB)"
  2:   "格挡/闪避(RMB)"

mouse_config:
  cursor_locked: true
  controls_camera: true
  description: "鼠标控制视角，右键瞄准"

game_meta:
  game_type_description: "3D 开放世界第一人称RPG"
  perspective: "第一人称"
```

### `config/games/skyrim_se.yaml`
```yaml
game_name: "Skyrim Special Edition"
process_name: "SkyrimSE"
engine: creation
adapter_type: skse_cpp
transport: tcp
tcp_port: 27015
capture_fps: 30
game_target_fps: 60
coordinate_system: right_hand_z_up
metric_scale: 0.01428   # 70 units = 1 metre
player_object_name: "Player"
ui_hide_method: none   # SKSE handles via UIManager

key_mapping:
  87:  "前进(W)"
  83:  "后退(S)"
  65:  "左移(A)"
  68:  "右移(D)"
  32:  "跳跃(Space)"
  160: "冲刺(LShift)"
  69:  "交互(E)"
  82:  "翻滚/翻滚(R)"
  67:  "蹲下(C)"
  90:  "潜行(Z)"
  9:   "战斗准备(Tab)"
  1:   "攻击(LMB)"
  2:   "格挡(RMB)"

mouse_config:
  cursor_locked: true
  controls_camera: true
  description: "鼠标控制视角旋转，右键格挡"

game_meta:
  game_type_description: "3D 开放世界第三人称/第一人称RPG"
  perspective: "第三/第一人称可切换"
```

---

## 5. Cyberpunk 2077 Adapter (CET Lua)

### Directory structure
```
adapters/cyberpunk/
└── WorldEngineCollector/
    ├── metadata.json       ← CET mod registration
    └── init.lua            ← main script (~200 lines)
```

### Key implementation details

**Frame gating:** Reads dx_capture shared memory (`WorldEngineFrameIndex` named mapping). Emits only when FrameIndex advances — same logic as Valheim C#.

**Camera data:**
```lua
local transform = GetCamera():GetLocalToWorld()
-- Extract position: transform:GetTranslation()
-- Extract quaternion: transform:ToQuat()
-- FOV: Game.GetSettingsSystem():GetVar("/graphics/basic", "FieldOfView"):GetValue()
```

**Player data:**
```lua
local player = GetPlayer()
local pos = player:GetWorldPosition()    -- Vector4
local rot = player:GetWorldOrientation() -- Quaternion
```

**Coordinate system:** CET API returns right-hand Y-up natively. No conversion needed. `metric_scale = 1.0`.

**Mouse input:** CET `registerForEvent("onMouseRelative", fn)` — accumulate dx/dy each frame.

**Key input:** `registerForEvent("onKeyDown/onKeyUp", fn)` — maintain pressed-keys set, emit as array of Windows VK codes.

**TCP send:** LuaSocket coroutine — non-blocking, queues on disconnect, retries on next frame.

**UI hide:** `Game.GetUISystem():QueueEvent(...)` to toggle HUD before Present, restore after.

---

## 6. Skyrim SE Adapter (SKSE C++)

### Directory structure
```
adapters/skyrim/
├── CMakeLists.txt
└── src/
    ├── Plugin.cpp          ← SKSE entry point, Init
    ├── FrameCollector.cpp  ← main loop hook, data collection
    ├── FrameCollector.h
    ├── TCPWriter.cpp       ← Winsock TCP client, background thread
    ├── TCPWriter.h
    └── CoordUtils.h        ← Z-up → Y-up conversion
```

### Key implementation details

**SKSE registration:**
```cpp
SKSEPlugin_Load: register MainLoop hook via GetTaskInterface()->AddTask()
```

**Frame gating:** Same shared memory pattern as Valheim — only emit when dx_capture FrameIndex advances.

**Camera data:**
```cpp
auto* cam = PlayerCamera::GetSingleton();
auto* camState = cam->currentState.get();
NiPoint3 pos; NiQuaternion rot;
camState->GetTranslation(pos);
camState->GetRotation(rot);
float fov = cam->worldFOV;
```

**Player data:**
```cpp
auto* player = PlayerCharacter::GetSingleton();
NiPoint3 ppos = player->GetPosition();
NiQuaternion prot; player->GetGraphRotation(0, prot);
```

**Coordinate conversion** (right-hand Z-up → right-hand Y-up):
```cpp
// Swap Y and Z, negate new Z
float outX =  in.x;
float outY =  in.z;   // world Z becomes Y
float outZ = -in.y;   // world Y becomes -Z
```
Quaternion conversion follows same axis swap.

**TCP send:** Winsock on background thread. `send()` with non-blocking socket. Queue JSONL strings in a `std::queue<std::string>` protected by `std::mutex`. Main thread enqueues, background thread drains.

**Camera intrinsics:** Same formula as Valheim — derive fx/fy from vertical FOV + screen resolution.

**Mouse input:** SKSE `InputEventSink` — accumulate relative mouse deltas per frame.

**Key input:** `InputEventSink` ButtonEvents → maintain VK code set → emit as JSON array.

---

## 7. CI/CD

### Cyberpunk adapter
No build needed — pure Lua. Packaged as a zip in CI artifacts:
```
WorldEngineCollector_CP2077.zip
└── bin/x64/plugins/cyber_engine_tweaks/mods/WorldEngineCollector/
    ├── metadata.json
    └── init.lua
```

### Skyrim adapter
New CMake project in `adapters/skyrim/`. Add to `build-release.yml`:
- Download CommonLibSSE-NG (SKSE headers) via CMake FetchContent
- Build `WorldEngineCollector_Skyrim.dll`
- Package as `WorldEngineCollector_Skyrim.zip` artifact

### Existing Valheim build
Unchanged.

---

## 8. File Changelist

| File | Action |
|------|--------|
| `control_center/pipe_reader.py` | Refactor: add `TransportReader`, `TCPReader` |
| `control_center/session_manager.py` | Add transport selection logic |
| `control_center/config/games/valheim.yaml` | Add `transport: namedpipe` |
| `control_center/config/games/cyberpunk2077.yaml` | New |
| `control_center/config/games/skyrim_se.yaml` | New |
| `adapters/cyberpunk/WorldEngineCollector/metadata.json` | New |
| `adapters/cyberpunk/WorldEngineCollector/init.lua` | New |
| `adapters/skyrim/CMakeLists.txt` | New |
| `adapters/skyrim/src/Plugin.cpp` | New |
| `adapters/skyrim/src/FrameCollector.cpp` | New |
| `adapters/skyrim/src/FrameCollector.h` | New |
| `adapters/skyrim/src/TCPWriter.cpp` | New |
| `adapters/skyrim/src/TCPWriter.h` | New |
| `adapters/skyrim/src/CoordUtils.h` | New |
| `.github/workflows/build-release.yml` | Add Skyrim build step + CP2077 zip step |
| `control_center/tests/test_pipe_reader.py` | Add TCPReader tests |
