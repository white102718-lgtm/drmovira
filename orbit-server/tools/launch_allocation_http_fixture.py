"""仅主线私有引导显式注入的HTTP协议fixture；无平台/病毒证明，不提供HTTP控制入口。"""

from orbit_api.launch_access import digest
from orbit_api.launch_allocation import build_compatibility_evidence
from orbit_api.launch_allocation_runtime import AllocationProvider, CapturedAllocation
from orbit_api.launch_expansion import ad_slots


class IsolatedHttpAllocationProvider(AllocationProvider):
    """运行时强制127.0.0.1:13306及UUID库；所有能力仅属协议夹具。"""

    kind = "ISOLATED_TEST"

    async def capture(self, session, current, plan, request):
        material = {
            asset: {
                "revision": 1,
                "sha256": "b" * 64,
                "kind": "IMAGE",
                "mime": "image/png",
                "byte_size": 100,
                "width_px": 24,
                "height_px": 24,
                "duration_seconds": None,
            }
            for asset in plan["asset_ids"]
        }
        evidence = build_compatibility_evidence(
            ad_slots(plan),
            plan["asset_ids"],
            capability_version="ISOLATED-HTTP-PROTOCOL-NOT-PLATFORM",
            source_hash="a" * 64,
            verified=True,
            complete=True,
            evaluate=lambda _slot, _asset: True,
            material_revisions={asset: 1 for asset in material},
        )
        return CapturedAllocation(evidence, material, "c" * 64, digest(plan))

    async def prepare_publication(self, session, current, packet, previous_id):
        captured = await self.capture(session, current, packet["plan"], packet["request"])
        return captured, None

    async def publish_references(self, *args):
        # 明示no-op：仅验HTTP→真实队列→完整结果协议，不证明C活跃引用/ClamAV或Meta。
        return None
