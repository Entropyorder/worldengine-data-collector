# WorldEngine Data Collector — 设计文档

**日期**：2026-03-30
**状态**：已批准
**版本**：v1.0

---

## 1. 项目背景与目标

构建一套名为 **WorldEngine Data Collector** 的游戏数据采集软件，用于采集高质量、干净、以环境探索行为为主的 character+camera 轨迹数据，用于训练交互式世界模型。

**核心诉求**：
- 视频与逐帧数据**帧级强对齐**（误差为 0）
- 视频无 UI 遮挡
- 统一左手坐标系（right=X，up=Y，front=Z）
- 录制 30fps，游戏本身保持 60fps+
- 支持多引擎扩展：Unity → GTA5 → Cyberpunk 2077 → Skyrim

**第一期目标**：基于 Valheim（Unity）完成完整流水线验证。

---

## 2. 交付物格式

每次录制生成一个独立文件夹：

```
session_YYYYMMDD_HHMMSS_<gamename>/
├── video.mp4              # 1920×1080, h264_nvenc, 30fps, 无UI
├── action_camera.json     # JSONL，每行一帧，逐帧采集数据
├── systeminfo.json        # 录制开始时系统快照
├── fps.json               # 每帧游戏渲染FPS（验收要求游戏FPS≥60）
└── game_meta.xlsx         # 游戏元信息（自动生成+yaml预设）
```

### 2.1 `action_camera.json` — 每行格式

JSONL 格式，每行一个完整帧数据对象：

```json
{
  "time": "2026-03-30 14:30:22.033",
  "fps": 30,
  "frame": 0,
  "camera_position": [-28.5, 77.2, 192.7],
  "camera_rotation_quaternion": [0.0, 0.707, 0.0, 0.707],
  "camera_follow_offset": [0.505, 2.500, -5.000],
  "camera_speed": [0.0, 0.0, 0.0],
  "camera_intrinsics": {"fx": 1080.0, "fy": 1080.0, "cx": 960.0, "cy": 540.0},
  "player_position": [-29.0, 75.0, 197.7],
  "player_rotation_eule": [0.0, 90.0, 0.0],
  "player_rotation_quaternion": [0.0, 0.707, 0.0, 0.707],
  "player_speed": [-0.7, 0.0, 0.0],
  "metric_scale": 1.0,
  "mouse_x": 960.0,
  "mouse_y": 540.0,
  "mouse_dx": 0.02,
  "mouse_dy": 0.0,
  "keyCode": [87]
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `time` | string | UTC 时间，格式 `YYYY-MM-DD HH:MM:SS.fff` |
| `fps` | float | 录制帧率，固定 30 |
| `frame` | int | 帧序号，从 0 开始，由 dx_capture.dll 维护 |
| `camera_position` | Vector3 | 相机世界坐标，左手系（Y-up） |
| `camera_rotation_quaternion` | Vector4 `[x,y,z,w]` | 相机旋转四元数，左手系 |
| `camera_follow_offset` | Vector3 | 相机在角色本地坐标系下的偏移（`player.InverseTransformPoint(camera.position)`） |
| `camera_speed` | Vector3 | 离线计算：`Δposition / Δt`，单位 m/s |
| `camera_intrinsics` | Object | `fx = (w/2)/tan(fov/2)`，`fy = fx`，`cx = w/2`，`cy = h/2` |
| `player_position` | Vector3 | 玩家世界坐标，左手系 |
| `player_rotation_eule` | Vector3 | 玩家欧拉角 `[pitch, yaw, roll]`，度数，左手系 |
| `player_rotation_quaternion` | Vector4 | 玩家旋转四元数，左手系 |
| `player_speed` | Vector3 | 离线计算：`Δposition / Δt`，单位 m/s |
| `metric_scale` | float | 引擎单位到米的比例（Unity = 1.0） |
| `mouse_x/y` | float | 屏幕像素坐标（左上角为原点）。锁定光标游戏用屏幕中心 + delta 累计积分模拟 |
| `mouse_dx/dy` | float | 当帧鼠标增量，引擎原生值 |
| `keyCode` | int[] | 当帧按下的所有键的 ASCII/Virtual Key Code。无按键时为 `[]` |

**注**：`camera_speed`、`player_speed` 在引擎插件内部原始采集时置零，由 Python Post-Processor 离线计算填充，避免实时计算影响帧率。

### 2.2 `systeminfo.json`

```json
{
  "gameProcessName": "Valheim",
  "window_rect": [{"x": 0, "y": 0}, {"x": 1920, "y": 1080}],
  "width": 1920,
  "height": 1080,
  "recordDpi": 1
}
```

在录制开始时由 Python 控制中心通过 OS API 自动生成。

### 2.3 `fps.json`

```json
[
  {"time": "2026-03-30 14:30:22.033", "fps": 72.4},
  {"time": "2026-03-30 14:30:22.066", "fps": 71.8}
]
```

由 `dx_capture.dll` 基于相邻两次 Present 调用的时间差（`1/ΔPresent`）计算真实游戏渲染 FPS，每帧记录一次。验收要求此值始终 ≥ 60。

### 2.4 `game_meta.xlsx`

通过 `metadata_collector.py` 自动生成，结合运行时数据 + 各游戏 yaml 预设：

| 字段 | 获取方式 |
|------|----------|
| 游戏类型描述 | yaml 预设 |
| 视角配置 | 自动检测（camera-player 距离 < 0.5m → 第一人称） |
| 相机位置是否固定 | 自动检测（录制期间 camera-player offset 方差） |
| 相机位置描述 | 从 `camera_follow_offset.Y` 自动生成（如"眼睛高度 1.6m"） |
| 画面分辨率 | 自动（OS API） |
| 键盘映射规则 | yaml 预设（技术人员写一次） |
| 鼠标对应规则 | yaml 预设（技术人员写一次） |

---

## 3. 系统架构

### 3.1 总体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                  Python 控制中心 (Control Center)                │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  PyQt GUI   │  │ Session Mgr  │  │  Post-Processor      │   │
│  │  + OSD IPC  │  │ (start/stop) │  │  (离线清洗/转换/输出) │   │
│  └─────────────┘  └──────────────┘  └──────────────────────┘   │
└────────────────────────┬────────────────────────────────────────┘
                         │ Named Pipe (\\.\pipe\WorldEngineData)
          ┌──────────────┴──────────────┐
          │                             │
┌─────────▼──────────┐    ┌────────────▼──────────────────────────┐
│  dx_capture.dll    │◄───│      Engine Data Adapter              │
│  (通用 C++ DLL)    │    │  (每款游戏一个，负责数据提取)          │
│                    │    │                                        │
│ • Hook Present()   │    │  Unity:     BepInEx C# 插件           │
│ • NVENC 编码 MP4   │    │  GTA5:      Script Hook V .asi        │
│ • 共享内存帧同步   │    │  Cyberpunk: CET C++ 插件              │
│ • OSD 渲染         │    │  Skyrim:    SKSE C++ 插件             │
└────────────────────┘    └────────────────────────────────────────┘
```

### 3.2 模块职责边界

| 模块 | 职责 | 不负责 |
|------|------|--------|
| `dx_capture.dll` | 录屏（NVENC）、帧计数、OSD 渲染 | 任何游戏逻辑或数据解析 |
| Engine Adapter | 数据提取、坐标系转换、IPC 发送 | 录屏、后处理 |
| Python 控制中心 | 会话管理、GUI、离线后处理、元数据 | 实时数据采集 |

---

## 4. `dx_capture.dll` — 通用录制与帧同步模块

### 4.1 核心流程

```
游戏主线程调用 Present()
        │
        ▼
[MinHook 拦截 IDXGISwapChain::Present]
        │
        ├─► frame_counter++  →  写入共享内存 SharedFrameSync
        │                        └─ SetEvent(FrameEvent) → 通知 Adapter 采集
        │
        ├─► 每 2 帧（30fps from 60fps）:
        │      从 stagingTexturePool[poolIdx % 3] 取空闲纹理  ← 3 纹理环形队列，避免编码线程未 Unmap 时阻塞
        │      CopyResource(stagingTexture, backBuffer)  ← GPU 异步拷贝
        │      PostMessage(stagingTexture) → 编码线程队列
        │      poolIdx++
        │
        ├─► OSD 渲染（D2D/D3D overlay）:
        │      显示：当前游戏FPS、已录制帧数、会话时长、录制状态
        │
        └─► 调用原始 Present()

编码线程（独立后台线程）:
  从队列取 stagingTexture
  → Map() 获取像素指针
  → 推入 FFmpeg stdin pipe（bgra → yuv420p）
  → Unmap()

FFmpeg 参数:
  ffmpeg -f rawvideo -pix_fmt bgra -s 1920x1080 -r 30
         -i pipe:0 -c:v h264_nvenc -preset p4
         -b:v 8M -pix_fmt yuv420p output.mp4
```

### 4.2 共享内存布局

```c
// 名称: "WorldEngineCapture_SharedMem"
// Event 名称: "WorldEngineCapture_FrameEvent"（新帧信号）
// Event 名称: "WorldEngineCapture_PostPresentEvent"（Present 完成信号，用于恢复UI）
struct SharedFrameSync {
    volatile int64_t  frame_index;     // 当前帧序号（由 dx_capture 维护）
    volatile double   present_time;    // Present 调用时的 QueryPerformanceCounter 时间戳
    volatile float    game_fps;        // 1 / ΔPresent，当前游戏渲染 FPS
    volatile int32_t  capture_active;  // 0=停止 1=录制（由 Python 控制端写入）
    volatile int32_t  reserved;
    char              session_id[64];  // 当前 session 目录名
    char              output_path[256]; // 输出目录绝对路径
};
```

### 4.3 性能分析

| 操作 | 线程 | 开销 | 对游戏帧率影响 |
|------|------|------|--------------|
| `CopyResource`（GPU→GPU staging） | 主线程 | ~0.1ms，GPU 端异步 | < 0.5% |
| `SetEvent`（帧信号） | 主线程 | < 0.01ms | 可忽略 |
| `Map/Unmap` + FFmpeg pipe 写入 | 编码线程 | ~2-4ms | **零影响**（独立线程） |
| NVENC 编码 | GPU 硬件 | 并行，不占渲染管线 | **零影响** |
| OSD 渲染 | 主线程 | < 0.1ms | 可忽略 |
| **总计主线程开销** | | **< 0.2ms/frame** | **< 2%** |

### 4.4 各引擎加载方式

| 引擎 | 加载 dx_capture.dll 的方式 |
|------|--------------------------|
| Unity/BepInEx | C# 插件 `Awake()` 中调用 `NativeLibrary.Load("dx_capture.dll")` |
| GTA5/Script Hook V | `.asi` 插件 `DllMain` 中 `LoadLibrary("dx_capture.dll")` |
| Cyberpunk/CET | CET 插件初始化回调中加载 |
| Skyrim/SKSE | `SKSEPlugin_Load` 回调中加载 |

**优势**：无需独立外部 DLL 注入器，全部通过各引擎已有的 mod loader 机制加载。

---

## 5. Engine Data Adapter — 各引擎数据适配器

### 5.1 采集逻辑（两类模式）

**模式 A：Unity / BepInEx**（LateUpdate 驱动，不等 Win32 Event）
```
每帧流程（LateUpdate 内）:
  1. 检查 capture_active == 1
  2. captureFrameIndex++（Adapter 本地计数，不读共享内存）
  3. 隐藏 UI（Canvas 全部 disable）
  4. 采集本帧所有字段（原始值，不做 speed 计算）
  5. 序列化为 JSON 行 → 写入 Named Pipe
  6. StartCoroutine(WaitForEndOfFrame → 恢复 UI)
```
> 注：BepInEx LateUpdate 在 Present **之前**运行，故不能从共享内存读 `frame_index`
>（那是 Present 内才递增的）。本地计数器与 dx_capture 的帧计数天然同步：
> 两者都是"每次游戏渲染一帧递增一次"。

**模式 B：C++ Adapters**（GTA5 / Cyberpunk / Skyrim，FrameEvent 驱动）
```
后台线程循环:
  1. WaitForSingleObject(FrameEvent, INFINITE)
  2. 读取 SharedFrameSync.frame_index（此时 Present 已触发，值已更新）
  3. 隐藏 UI
  4. 采集本帧所有字段
  5. 序列化为 JSON 行 → 写入 Named Pipe
  6. 恢复 UI
```

### 5.2 Adapter A：Unity (BepInEx C# 插件) — 第一期

```csharp
[BepInPlugin("com.worldengine.collector", "WorldEngine Collector", "1.0.0")]
public class CollectorPlugin : BaseUnityPlugin
{
    void LateUpdate()
    {
        if (!IsCapturing()) return;

        // 隐藏所有 Canvas
        foreach (var canvas in FindObjectsOfType<Canvas>())
            canvas.enabled = false;

        var cam = Camera.main;
        var player = FindPlayer(); // 游戏专用方法，在 valheim.yaml 里配置对象名

        var data = new FrameData {
            frame        = captureFrameIndex, // 本地计数，非共享内存（避免 LateUpdate 读到上一帧序号）
            time         = DateTime.UtcNow.ToString("yyyy-MM-dd HH:mm:ss.fff"),
            fps          = 30,
            // 坐标：Unity 原生左手系，无需转换
            camera_position             = Vec3(cam.transform.position),
            camera_rotation_quaternion  = Quat(cam.transform.rotation),
            camera_follow_offset        = Vec3(player.transform.InverseTransformPoint(cam.transform.position)),
            camera_intrinsics           = CalcIntrinsics(cam.fieldOfView, Screen.width, Screen.height),
            camera_speed                = Vector3.zero, // 离线计算
            player_position             = Vec3(player.transform.position),
            player_rotation_eule        = EulerDeg(player.transform.rotation),
            player_rotation_quaternion  = Quat(player.transform.rotation),
            player_speed                = Vector3.zero, // 离线计算
            metric_scale                = 1.0f,
            mouse_x                     = accumulatedMouseX, // 中心点 + delta 积分
            mouse_y                     = accumulatedMouseY,
            mouse_dx                    = Input.GetAxisRaw("Mouse X"),
            mouse_dy                    = Input.GetAxisRaw("Mouse Y"),
            keyCode                     = GetPressedKeyCodes(), // int[]
        };

        pipeWriter.WriteLine(JsonSerializer.Serialize(data));

        // UI 恢复：使用 WaitForEndOfFrame 协程，确保 Present 完成后再恢复
        // 注意：不能在 LateUpdate 中直接 WaitForPostPresent()——Present 也在主线程，会死锁
        StartCoroutine(RestoreUIAfterFrame(savedCanvases));
    }

    IEnumerator RestoreUIAfterFrame(Canvas[] canvases)
    {
        yield return new WaitForEndOfFrame(); // 此点之后 Present 已调用完毕
        foreach (var canvas in canvases) canvas.enabled = true;
    }

    // camera_intrinsics 公式
    CameraIntrinsics CalcIntrinsics(float fovDeg, int w, int h) {
        float fx = (w / 2f) / Mathf.Tan(fovDeg * Mathf.Deg2Rad / 2f);
        return new CameraIntrinsics { fx = fx, fy = fx, cx = w / 2f, cy = h / 2f };
    }
}
```

### 5.3 Adapter B：GTA5 (Script Hook V C++ .asi)

- 数据来源：SHVDN 原生调用 `CAM::GET_CAM_COORD`、`CAM::GET_CAM_ROT`、`CAM::GET_CAM_FOV`、`PLAYER::GET_PLAYER_PED`
- UI 隐藏：每帧调用 `HUD::HIDE_HUD_AND_RADAR_THIS_FRAME()`，`UI::DISPLAY_HUD(false)`
- 坐标系转换：RAGE 引擎为左手系 Z-up，需转换到 Y-up

```cpp
// RAGE (Z-up) → 需求文档左手系 (Y-up)
Vector3 RageToYUp(Vector3 v) { return {v.x, v.z, v.y}; }
Quaternion RageQuatToYUp(Quaternion q) {
    // 绕 X 轴旋转 -90 度的四元数变换
    return MultiplyQuat({-0.7071f, 0, 0, 0.7071f}, q);
}
```

### 5.4 Adapter C：Cyberpunk 2077 (CET Lua + C++ Native)

- 数据来源：`GetPlayer()`, `Game.GetCameraSystem():GetActiveCameraWorldTransform()`
- UI 隐藏：`GameOptions.Set("Rendering", "ShowUI", false)`，录制结束恢复为 `true`
- 坐标系：REDengine 4 为左手系 Y-up，与需求文档一致，无需转换

### 5.5 Adapter D：Skyrim (SKSE C++)

- 数据来源：`PlayerCamera::GetSingleton()`, `PlayerCharacter::GetSingleton()`
- UI 隐藏：`Console.RunCommand("tm")` 切换 UI，录制结束再次 `tm` 恢复
- 坐标系：Creation Engine 为右手系 Z-up，需完整转换

```cpp
// Creation Engine (右手 Z-up) → 左手系 (Y-up)
NiPoint3 CEToLeftHand(NiPoint3 v) { return {v.x, v.z, -v.y}; }
```

---

## 6. Python 控制中心

### 6.1 模块结构

```
control_center/
├── main.py                    # 入口，启动 PyQt GUI
├── session_manager.py         # 录制生命周期管理
├── pipe_reader.py             # Named Pipe 读取，缓冲帧数据到 raw_frames.jsonl
├── post_processor.py          # 离线清洗：速度计算、帧连续性校验、最终输出
├── metadata_collector.py      # 自动生成 systeminfo.json 和 game_meta.xlsx
├── osd_bridge.py              # 通过共享内存向 dx_capture.dll 发送控制指令
├── config/
│   ├── games/
│   │   ├── valheim.yaml
│   │   ├── gta5.yaml
│   │   ├── cyberpunk.yaml
│   │   └── skyrim.yaml
│   └── settings.yaml          # 全局设置（输出目录、编码参数等）
└── gui/
    ├── main_window.py         # 主界面：游戏选择、开始/停止录制、会话列表
    └── session_log.py         # 实时日志面板
```

### 6.2 录制生命周期

```
[GUI: 下拉选择游戏] → 读取 games/valheim.yaml
[点击"开始录制" 或 热键 F9]
  ├─ 创建 session_YYYYMMDD_HHMMSS_valheim/
  ├─ 写入 systeminfo.json（即时）
  ├─ 写入 SharedMem: capture_active=1, session_id, output_path
  ├─ pipe_reader 开始接收 → raw_frames.jsonl（临时文件）
  └─ OSD: 显示录制状态

[录制中]
  ├─ GUI 实时显示: 帧数、当前游戏FPS、已录制时长
  └─ OSD 层: 同步显示以上信息

[按 F9 停止 / 超过30分钟自动停止]
  ├─ capture_active=0
  ├─ FFmpeg pipe 关闭 → video.mp4 写入完成
  └─ 触发 Post-Processor:
       ├─ 读取 raw_frames.jsonl
       ├─ 逐帧计算 camera_speed = (pos[n] - pos[n-1]) / (time[n] - time[n-1])
       ├─ 逐帧计算 player_speed（同上）
       ├─ 校验帧连续性（检测跳帧，记录警告）
       ├─ 输出 action_camera.json（最终 JSONL）
       ├─ 输出 fps.json
       └─ 触发 metadata_collector.py → game_meta.xlsx
```

### 6.3 游戏预设配置（valheim.yaml）

```yaml
game_name: "Valheim"
process_name: "valheim"
engine: unity
adapter_path: "adapters/unity/valheim/BepInEx/plugins/WorldEngineCollector.dll"
dx_capture_path: "adapters/dx_capture.dll"
capture_fps: 30
game_target_fps: 60
coordinate_system: left_hand_y_up   # Unity 原生，无需转换
metric_scale: 1.0
player_find_method: "FindGameObjectByName"
player_object_name: "Player(Clone)"
ui_hide_method: disable_canvas

# 键盘语义描述（用于 game_meta.xlsx）
key_mapping:
  87: "前进(W)"
  83: "后退(S)"
  65: "左移(A)"
  68: "右移(D)"
  32: "跳跃(Space)"
  160: "冲刺(Shift)"

# 鼠标行为描述
mouse_config:
  cursor_locked: true
  controls_camera: true
  description: "鼠标控制视角，按住鼠标右键瞄准"
```

### 6.4 Post-Processor 速度计算

```python
def compute_speeds(frames: list[dict]) -> list[dict]:
    for i in range(len(frames)):
        if i == 0:
            frames[i]["camera_speed"] = [0.0, 0.0, 0.0]
            frames[i]["player_speed"] = [0.0, 0.0, 0.0]
            continue
        dt = parse_time(frames[i]["time"]) - parse_time(frames[i-1]["time"])
        dt_sec = dt.total_seconds()
        if dt_sec <= 0:
            frames[i]["camera_speed"] = [0.0, 0.0, 0.0]
            frames[i]["player_speed"] = [0.0, 0.0, 0.0]
            continue
        cp = frames[i]["camera_position"]
        pp_prev = frames[i-1]["camera_position"]
        frames[i]["camera_speed"] = [(cp[j] - pp_prev[j]) / dt_sec for j in range(3)]
        # player_speed 同理
    return frames
```

---

## 7. 坐标系转换规范

所有最终输出统一为**左手坐标系（right=X, up=Y, front=Z）**：

| 引擎 | 原生坐标系 | 转换方法 |
|------|-----------|---------|
| Unity | 左手 Y-up | 无需转换（直接输出） |
| RAGE (GTA5) | 左手 Z-up | `(x, z, y)` + 四元数 X轴旋转-90° |
| REDengine 4 (Cyberpunk) | 左手 Y-up | 无需转换 |
| Creation Engine (Skyrim) | 右手 Z-up | `(x, z, -y)` + 四元数变换 |

转换逻辑封装在各 Adapter 内部，Python 控制中心接收到的数据已经是统一坐标系。

---

## 8. 扩展新游戏的步骤

接入一款新游戏只需三步：

1. **创建 yaml 配置文件**（`config/games/<gamename>.yaml`）：填写引擎类型、玩家对象名、键盘语义、坐标系类型
2. **编写 Engine Data Adapter**：根据引擎类型，基于模板实现数据提取逻辑（Unity C#：约 200 行；其他引擎 C++：约 300 行）
3. **运行元数据采集脚本**（技术人员执行一次）：自动生成该游戏的 `game_meta.xlsx` 模板

`dx_capture.dll` 和 Python 控制中心无需修改。

---

## 9. 验收对齐检查

| 验收要求 | 实现方式 | 满足 |
|---------|---------|------|
| 视频 1920×1080 | FFmpeg NVENC 输出参数固定 | ✅ |
| 视频 30fps | dx_capture 每 2 帧采一帧（游戏 60fps） | ✅ |
| 延迟 < 20ms | CopyResource GPU异步，编码线程独立 | ✅ |
| 游戏 FPS ≥ 60 | fps.json 记录，验收脚本检查 | ✅ |
| 无 UI 遮挡 | Present 前隐藏，Present 后恢复 | ✅ |
| 帧级数据对齐 | 同一 Present 调用触发录屏+数据采集 | ✅ |
| 左手坐标系 | 各 Adapter 内部转换，输出已统一 | ✅ |
| 速度单位 m/s | 离线差分计算，Unity metric_scale=1.0 | ✅ |
| keyCode 多键 | int[] 格式，无按键时为 [] | ✅ |
| game_meta.xlsx | 自动生成 + yaml 预设补充 | ✅ |

---

## 10. 开发阶段规划

### 第一期：Valheim 验证（Unity）
- `dx_capture.dll`：DX11 Present Hook + NVENC + 共享内存
- BepInEx Adapter：Valheim 专用，完整字段采集
- Python 控制中心：基础 GUI + Session Manager + Post-Processor
- 验证：生成完整 session 文件夹，对照需求文档验收

### 第二期：其他 Unity 游戏扩展
- 验证 BepInEx Adapter 的通用性
- 补充多款游戏的 yaml 配置

### 第三期：RAGE + REDengine + Creation Engine
- GTA5 Script Hook V Adapter（含 Z-up 坐标转换）
- Cyberpunk 2077 CET Adapter
- Skyrim SKSE Adapter（含右手系转换）

---

## 附：技术选型汇总

| 组件 | 技术选型 | 理由 |
|------|---------|------|
| DX Hook | MinHook (C++) | 轻量、稳定、MIT 开源 |
| 视频编码 | FFmpeg + NVENC | 硬件编码，低 CPU 占用，成熟管线 |
| Unity 注入 | BepInEx 5.x | Unity 游戏标准 mod 框架 |
| GTA5 | Script Hook V | 业界标准，无需绕过游戏保护 |
| Cyberpunk | Cyber Engine Tweaks | 官方认可的社区工具 |
| Skyrim | SKSE64 | 标准 Skyrim 扩展框架 |
| 控制端语言 | Python 3.11+ | 便于对接后续 AI 训练脚本 |
| GUI | PyQt6 | 跨平台，功能完善 |
| IPC | Windows Named Pipe | 低延迟，同机进程通信首选 |
| 序列化 | JSON（JSONL） | 与现有样例格式一致 |
