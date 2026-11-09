"""素材统一SQL安全资格；核扫描当时证明，不隐式引入全库读取时TTL。"""

import re

from sqlalchemy import text


def scan_evidence_predicate(alias="a", *, job_state="DONE"):
    if not re.fullmatch(r"[a-z_]+", alias) or job_state not in {"DONE", "RUNNING"}:
        raise ValueError("扫描谓词只接受服务内部固定SQL参数")
    return f"""EXISTS(SELECT 1 FROM orbit_material_scan_receipt sr
        JOIN orbit_material_job sj ON sj.tenant_id=sr.tenant_id AND sj.asset_id=sr.asset_id
          AND sj.claim_id=sr.claim_id AND sj.state='{job_state}'
        JOIN orbit_material_scan_runtime_proof rp ON rp.tenant_id=sr.tenant_id
          AND rp.asset_id=sr.asset_id AND rp.receipt_id=sr.id AND rp.claim_id=sr.claim_id
        WHERE sr.tenant_id={alias}.tenant_id AND sr.asset_id={alias}.id
          AND sr.sha256={alias}.sha256 AND sr.byte_size={alias}.byte_size
          AND sr.result='CLEAN' AND sr.error_code IS NULL
          AND sr.engine_version IS NOT NULL AND sr.database_version IS NOT NULL
          AND sr.database_built_at IS NOT NULL AND sr.policy_sha256 IS NOT NULL
          AND rp.config_sha256=sr.policy_sha256 AND rp.profile_revision>0
          AND rp.issued_at<=rp.verified_before AND rp.verified_before<=sr.started_at
          AND sr.started_at<=sr.completed_at AND sr.completed_at<=rp.verified_after
          AND rp.verified_after<rp.expires_at)"""


async def processing_scan_verified(session, claim):
    query = text(
        """SELECT a.id FROM orbit_material_asset a
        WHERE a.tenant_id=:tenant_id AND a.id=:asset_id AND a.state='PROCESSING'
          AND a.revision=:revision AND a.sha256=:sha256 AND a.byte_size=:byte_size
          AND a.physical_cleanup_state='LIVE' AND """
        + scan_evidence_predicate(job_state="RUNNING")
    )
    return (await session.execute(query, claim)).scalar_one_or_none() is not None
