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
            // fov=60° vertical, 1920x1080: fy = (540) / tan(30°) = 540 / 0.5774 ≈ 935.31
            var intr = CoordUtils.CalcIntrinsics(60f, 1920, 1080);
            Assert.AreEqual(960f, intr.Cx, 0.01f);
            Assert.AreEqual(540f, intr.Cy, 0.01f);
            Assert.AreEqual(intr.Fx, intr.Fy, 0.01f);
            Assert.AreEqual(935.31f, intr.Fx, 1f);
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
