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
