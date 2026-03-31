-- WorldEngine Collector for Cyberpunk 2077
-- Streams per-frame telemetry (camera + player) to Python control center via TCP.
-- Requires: Cyber Engine Tweaks (CET)

local socket = require("socket")

-- ── Config ────────────────────────────────────────────────────────────────────
local HOST        = "127.0.0.1"
local PORT        = 27015
local TARGET_FPS  = 30
local FRAME_DT    = 1.0 / TARGET_FPS   -- seconds between emissions

-- ── State ─────────────────────────────────────────────────────────────────────
local tcp           = nil     -- socket client (nil = disconnected)
local frameIndex    = 0       -- emitted frame counter
local timeSinceLast = 0.0     -- accumulated dt since last emission
local mouseDx       = 0.0
local mouseDy       = 0.0
local accMouseX     = 960.0   -- accumulated absolute position (assume 1920×1080)
local accMouseY     = 540.0
local pressedKeys   = {}      -- set of VK codes currently held

-- ── VK code table: CET key name → Windows VK code ─────────────────────────────
local VK = {
    IK_W = 87, IK_S = 83, IK_A = 65, IK_D = 68,
    IK_Space = 32, IK_LShift = 160, IK_F = 70, IK_E = 69,
    IK_R = 82, IK_C = 67, IK_LAlt = 18, IK_Z = 90,
    IK_Tab = 9, IK_LMouse = 1, IK_RMouse = 2,
}

-- ── Minimal JSON encoder (no external library needed) ─────────────────────────
local function encodeValue(v)
    local t = type(v)
    if t == "nil"     then return "null"
    elseif t == "boolean" then return tostring(v)
    elseif t == "number"  then
        if v ~= v then return "null" end  -- NaN guard
        return string.format("%.6g", v)
    elseif t == "string"  then
        return '"' .. v:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n') .. '"'
    elseif t == "table"   then
        -- Array check: all keys are consecutive integers from 1
        local isArray = true
        local n = 0
        for k, _ in pairs(v) do
            n = n + 1
            if type(k) ~= "number" or k ~= math.floor(k) then isArray = false; break end
        end
        if isArray and n == #v then
            local parts = {}
            for _, val in ipairs(v) do parts[#parts + 1] = encodeValue(val) end
            return "[" .. table.concat(parts, ",") .. "]"
        else
            local parts = {}
            for key, val in pairs(v) do
                parts[#parts + 1] = '"' .. tostring(key) .. '":' .. encodeValue(val)
            end
            return "{" .. table.concat(parts, ",") .. "}"
        end
    end
    return "null"
end

local function encodeJSON(t) return encodeValue(t) end

-- ── Helpers ───────────────────────────────────────────────────────────────────
local function tryConnect()
    local t = socket.tcp()
    t:settimeout(0.1)
    local ok, err = t:connect(HOST, PORT)
    if ok then
        t:settimeout(0)   -- non-blocking after connect
        return t
    end
    t:close()
    return nil
end

local function sendLine(line)
    if not tcp then
        tcp = tryConnect()
        if not tcp then return end
    end
    local ok, err = tcp:send(line .. "\n")
    if not ok then
        tcp:close()
        tcp = nil
    end
end

-- Forward declarations
local collectFrame

-- ── CET event registrations ───────────────────────────────────────────────────
registerForEvent("onInit", function()
    print("[WorldEngineCollector] Loaded. Connecting to " .. HOST .. ":" .. PORT)
end)

registerForEvent("onUpdate", function(dt)
    timeSinceLast = timeSinceLast + dt
    if timeSinceLast < FRAME_DT then return end
    timeSinceLast = timeSinceLast - FRAME_DT

    collectFrame()

    -- Reset per-frame mouse delta after emission
    mouseDx = 0.0
    mouseDy = 0.0
end)

registerForEvent("onMouseRelative", function(x, y)
    mouseDx = mouseDx + x
    mouseDy = mouseDy + y
    accMouseX = math.max(0, math.min(1920, accMouseX + x))
    accMouseY = math.max(0, math.min(1080, accMouseY - y))  -- flip Y
end)

registerForEvent("onKeyDown", function(keyName)
    local vk = VK[keyName]
    if vk then pressedKeys[vk] = true end
end)

registerForEvent("onKeyUp", function(keyName)
    local vk = VK[keyName]
    if vk then pressedKeys[vk] = nil end
end)

-- ── Frame collection ──────────────────────────────────────────────────────────
collectFrame = function()
    local player = GetPlayer()
    if not player then return end

    local cam = GetCamera()
    if not cam then return end

    -- Camera world transform
    local camTransform = cam:GetLocalToWorld()
    local camPos       = camTransform:GetTranslation()        -- Vector4
    local camQuat      = camTransform:GetRotation()           -- Quaternion

    -- Player world transform
    local playerPos    = player:GetWorldPosition()            -- Vector4
    local playerQuat   = player:GetWorldOrientation()         -- Quaternion

    -- Follow offset: camera in player's local space
    local playerTransform = player:GetLocalToWorld()
    local invPlayer       = playerTransform:GetInverted()
    local camInPlayer     = invPlayer:Transform(camPos)

    -- FOV (vertical, degrees)
    local fovDeg = 80.0   -- sensible default; CET GetFOV not always available
    pcall(function()
        fovDeg = cam:GetFOV()
    end)

    -- Camera intrinsics (assume 1920×1080; runtime resolution not easily accessible in Lua)
    local W, H    = 1920, 1080
    local fovRad  = fovDeg * math.pi / 180.0
    local fy      = (H / 2.0) / math.tan(fovRad / 2.0)
    local fx      = fy

    -- Pressed keys as array
    local keyCodes = {}
    for vk, _ in pairs(pressedKeys) do
        keyCodes[#keyCodes + 1] = vk
    end

    -- Timestamp
    local now = os.date("!%Y-%m-%d %H:%M:%S") .. ".000"

    -- Euler angles from quaternion (yaw/pitch/roll in degrees)
    local qi, qj, qk, qr = playerQuat.i, playerQuat.j, playerQuat.k, playerQuat.r
    local sinp = 2 * (qr * qj - qk * qi)
    local pitch = math.deg(math.asin(math.max(-1, math.min(1, sinp))))
    local siny  = 2 * (qr * qk + qi * qj)
    local cosy  = 1 - 2 * (qj * qj + qk * qk)
    local yaw   = math.deg(math.atan2(siny, cosy))
    local sinr  = 2 * (qr * qi + qj * qk)
    local cosr  = 1 - 2 * (qi * qi + qj * qj)
    local roll  = math.deg(math.atan2(sinr, cosr))

    local record = {
        frame                   = frameIndex,
        time                    = now,
        fps                     = TARGET_FPS,
        camera_position         = { camPos.x,    camPos.y,    camPos.z    },
        camera_rotation_quaternion = { camQuat.i, camQuat.j, camQuat.k, camQuat.r },
        camera_follow_offset    = { camInPlayer.x, camInPlayer.y, camInPlayer.z },
        camera_speed            = { 0, 0, 0 },
        camera_intrinsics       = { fx = fx, fy = fy, cx = W / 2.0, cy = H / 2.0 },
        player_position         = { playerPos.x,  playerPos.y,  playerPos.z  },
        player_rotation_eule    = { pitch, yaw, roll },
        player_rotation_quaternion = { playerQuat.i, playerQuat.j, playerQuat.k, playerQuat.r },
        player_speed            = { 0, 0, 0 },
        metric_scale            = 1.0,
        mouse_x                 = accMouseX,
        mouse_y                 = accMouseY,
        mouse_dx                = mouseDx,
        mouse_dy                = mouseDy,
        keyCode                 = keyCodes,
        _game_fps               = TARGET_FPS,
    }

    -- Serialize to JSON and send
    local line = encodeJSON(record)
    sendLine(line)
    frameIndex = frameIndex + 1
end
