"""在专属MySQL/Redis夹具验证真实Python框架；不迁移或停止用户预览。"""

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import bcrypt
import httpx
import pymysql
import redis
from account_import_checks import CASES as ACCOUNT_IMPORT_CASES
from account_import_checks import run_account_import_checks
from authorization_store_checks import AUTHORIZATION_STORE_CASES
from browser_session_checks import BROWSER_SESSION_CASES, run_browser_session_checks
from configuration_metadata_checks import CASES as CONFIGURATION_METADATA_CASES
from configuration_metadata_checks import run_configuration_metadata_checks
from cookie_http_checks import COOKIE_HTTP_CASES
from fixture_login import LOGIN_WAIT_SECONDS, fixture_login
from identity_capacity_checks import IDENTITY_CAPACITY_CASES, run_identity_capacity_checks
from invitation_activation_checks import INVITATION_ACTIVATION_CASES
from invitation_checks import INVITATION_CASES, run_invitation_checks
from invitation_delivery_checks import DELIVERY_CASES
from invitation_worker_cli_checks import CLI_CASES
from material_checks import MATERIAL_CASES, run_material_checks
from native_bulk_lifecycle_checks import (
    NATIVE_BULK_LIFECYCLE_CASES,
    run_native_bulk_lifecycle_checks,
    write_native_browser_import_fixtures,
)
from native_directory_checks import NATIVE_DIRECTORY_CASES, run_native_directory_checks
from native_role_read_checks import NATIVE_ROLE_READ_CASES, run_native_role_read_checks
from native_role_reference_checks import (
    NATIVE_ROLE_REFERENCE_CASES,
    run_native_role_reference_checks,
)
from native_user_change_checks import NATIVE_USER_CHANGE_CASES, run_native_user_change_checks
from native_user_role_checks import NATIVE_USER_ROLE_CASES, run_native_user_role_checks
from native_write_contract_checks import (
    NATIVE_WRITE_CONTRACT_CASES,
    run_native_write_contract_checks,
)
from oidc_callback_checks import OIDC_CALLBACK_CASES
from oidc_https_fixture import LocalOidcFixture
from pymysql.constants import CLIENT
from reference_channel_checks import REFERENCE_CHANNEL_CASES, run_reference_channel_checks
from reference_channel_scope_checks import (
    REFERENCE_CHANNEL_SCOPE_CASES,
    run_reference_channel_scope_checks,
)
from role_checks import ROLE_CASES, run_role_checks
from role_guard_checks import ROLE_GUARD_CASES, run_role_guard_checks
from team_checks import TEAM_CASES, run_team_checks
from team_session_checks import TEAM_SESSION_CASES, run_team_session_checks
from user_checks import USER_CASES, run_user_checks
from user_create_checks import USER_CREATE_CASES, run_user_create_checks
from user_update_checks import USER_UPDATE_CASES, run_user_update_checks

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK = ROOT / "python/ruoyi_fastapi"
EVIDENCE = ROOT / "docs/orbit/evidence"
PORT = 18083


class CheckedCases(list):
    """只输出注册的检查名，及时暴露卡住阶段；不输出请求、SQL或任何凭据。"""

    def __init__(self, planned):
        super().__init__()
        self.allowed = frozenset(planned)
        if len(self.allowed) != len(planned):
            raise ValueError("检查计划出现重复名称，拒绝虚增检查数")
        self.started = time.monotonic()

    def append(self, name):
        if name in self:
            raise AssertionError("同一检查重复记录，拒绝虚增通过数")
        if name not in self.allowed:
            raise AssertionError("检查名称尚未登记，拒绝写入不受控内容")
        super().append(name)
        print(
            json.dumps(
                {"passed_case": name, "elapsed_seconds": round(time.monotonic() - self.started, 2)}
            ),
            flush=True,
        )

    def extend(self, names):
        for name in names:
            self.append(name)


def prepare_account_import_fixture(client, admin, headers):
    """通过真实受控导入创建可读户商，不直接伪造业务资料或平台账户。"""
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        if not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", str(cursor.fetchone()[0])):
            raise ValueError("账户夹具只允许当前独立数据库")
        cursor.execute("SELECT id,team_id FROM orbit_business_user WHERE user_id=1")
        owner, team = cursor.fetchone()
    caps = client.get("/api/v1/reference-catalog-imports/capabilities", headers=headers)
    assert caps.status_code == 200, "账户引用夹具授权失败"
    values = caps.json()
    identifier = str(uuid.uuid4())
    write = headers | {"X-CSRF-Token": values["csrf_token"]}
    preview = client.post(
        "/api/v1/reference-catalog-imports",
        headers=write | {"Idempotency-Key": "account-vendor-" + uuid.uuid4().hex},
        json={
            "kind": "VENDOR",
            "source": "账户隔离验收",
            "reason": "验证受理前引用范围",
            "base_catalog_revision": values["catalog_revision"],
            "items": [
                {
                    "kind": "VENDOR",
                    "id": identifier,
                    "name": "账户验收户商",
                    "source_key": "account-" + identifier,
                    "availability": "AVAILABLE",
                    "owner_team_id": team,
                    "data_owner_user_ids": [owner],
                }
            ],
        },
    )
    assert preview.status_code == 201 and preview.json()["state"] == "VALIDATED"
    batch = preview.json()
    committed = client.post(
        f"/api/v1/reference-catalog-imports/{batch['id']}/commit",
        headers=write
        | {
            "Idempotency-Key": "account-vendor-commit-" + uuid.uuid4().hex,
            "If-Match": f'"{batch["revision"]}"',
        },
    )
    assert committed.status_code == 200 and committed.json()["state"] == "COMMITTED"
    return owner, team, identifier


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--browser", action="store_true", help="连接独立Python后台执行三个视口的真实浏览器专项"
    )
    parser.add_argument(
        "--browser-module",
        choices=(
            "all",
            "configuration",
            "scanner-configuration",
            "tasks",
            "task-events",
            "teams",
            "roles",
            "users",
            "native-directory",
            "authentication",
            "channels",
            "materials",
            "vendor-alias",
            "accounts",
            "account-command",
            "identity-publication",
            "identity-summary",
            "channel-owners500",
            "scopes",
            "materials-and-security",
            "material-security",
            "launch",
            "metric-profiles",
            "launch-metric-profiles",
            "metrics",
        ),
        default="all",
        help="只在--browser下选择变更页面，仍验证三个视口；默认验证全部页面",
    )
    parser.add_argument(
        "--migration-through",
        type=int,
        default=8,
        help="隔离夹具显式选择已就绪迁移的最大编号；默认001—008，不执行并行开发中的迁移",
    )
    parser.add_argument(
        "--include-materials", action="store_true", help="运行素材真实文件及HTTP专项"
    )
    parser.add_argument("--include-accounts", action="store_true", help="运行账户导入受理HTTP专项")
    parser.add_argument(
        "--include-scope-visibility-verdict",
        action="store_true",
        help="附043范围当前授权证明、不可变护栏和真实RR并发专项",
    )
    parser.add_argument(
        "--include-account-worker", action="store_true", help="运行账户只读Worker真实MySQL/TLS专项"
    )
    parser.add_argument(
        "--browser-only",
        action="store_true",
        help="仅初始化独立夹具和业务浏览器专项，不冒充后台回归",
    )
    parser.add_argument("--include-channel-scope", action="store_true", help="渠道写入权限补充矩阵")
    parser.add_argument(
        "--channel-scope-only", action="store_true", help="只初始化人员夹具并运行渠道写入权限矩阵"
    )
    parser.add_argument(
        "--include-account-details", action="store_true", help="账户18列读模型真实专项"
    )
    parser.add_argument(
        "--include-material-video", action="store_true", help="真实视频及跨8MiB分片专项"
    )
    parser.add_argument(
        "--material-video-bin", type=Path, help="仅隔离子进程使用的已校验视频工具目录"
    )
    parser.add_argument(
        "--account-details-only",
        action="store_true",
        help="只初始化账户详情夹具并执行真实读模型专项",
    )
    parser.add_argument(
        "--material-only", action="store_true", help="只初始化素材夹具并执行真实文件/媒体专项"
    )
    parser.add_argument(
        "--include-material-taxonomy",
        action="store_true",
        help="标签分类迁移、查询及原始响应合同真实专项",
    )
    parser.add_argument("--include-vendor-alias", action="store_true", help="户商代称真实HTTP专项")
    parser.add_argument(
        "--vendor-alias-only", action="store_true", help="仅初始化人员与户商代称专项"
    )
    parser.add_argument(
        "--include-material-taxonomy-scope",
        action="store_true",
        help="标签引用数与游标权限真实专项",
    )
    parser.add_argument(
        "--environment-live-only", action="store_true", help="独立mTLS心跳与监测真实档"
    )
    parser.add_argument("--include-meta-connection-checks", action="store_true")
    parser.add_argument("--include-meta-pipeline-checks", action="store_true")
    parser.add_argument(
        "--include-local-adspower", action="store_true", help="显式只读访问当前机器AdsPower"
    )
    parser.add_argument("--meta-expectation-file", type=Path, help="本机Meta验收预期账户与币种的私有JSON")
    parser.add_argument(
        "--environment-registry-only",
        action="store_true",
        help="仅执行机登记与账户环境关联真实专项",
    )
    parser.add_argument(
        "--environment-internal-browser", action="store_true", help="执行机专项后等待实际页面验收"
    )
    parser.add_argument(
        "--taxonomy-internal-browser",
        action="store_true",
        help="标签元数据专项后等待人工真实UI检查",
    )
    parser.add_argument(
        "--include-launch-identity-drafts", action="store_true", help="身份发布档附投放草稿身份闭环"
    )
    parser.add_argument(
        "--material-taxonomy-metadata-only",
        action="store_true",
        help="仅人员与标签分类目录元数据，不配置对象存储/扫描，不覆盖上传验收",
    )
    parser.add_argument(
        "--include-material-taxonomy-capabilities",
        action="store_true",
        help="标签分类独立动作能力真实专项，仅附目录元数据档与显式065迁移",
    )
    parser.add_argument(
        "--material-taxonomy-scope-only", action="store_true", help="仅初始化人员与标签范围专项"
    )
    parser.add_argument(
        "--include-channel-fields", action="store_true", help="原渠道Schema及逐字段边界真实专项"
    )
    parser.add_argument(
        "--include-material-lifecycle", action="store_true", help="素材019生命周期真实专项"
    )
    parser.add_argument(
        "--material-lifecycle-only", action="store_true", help="仅素材生命周期独立夹具"
    )
    parser.add_argument(
        "--include-material-lifecycle-recovery",
        action="store_true",
        help="素材生命周期真实故障恢复矩阵",
    )
    parser.add_argument(
        "--include-channel-owners", action="store_true", help="渠道500真实拥有者与权限专项"
    )
    parser.add_argument(
        "--channel-owners-only", action="store_true", help="只初始化人员与渠道500专项"
    )
    parser.add_argument(
        "--reference-channel-only",
        action="store_true",
        help="仅B目录渠道完整专项，不执行其他模块后台回归",
    )
    parser.add_argument(
        "--include-material-lifecycle-races",
        action="store_true",
        help="真实跨进程及HTTP写入/回收竞争",
    )
    parser.add_argument(
        "--include-account-alias-snapshots",
        action="store_true",
        help="020当前代称与不可变业务快照真实专项",
    )
    parser.add_argument(
        "--migration-extra",
        action="append",
        default=[],
        help="隔离夹具额外明确选择的已就绪迁移文件名；不自动执行中间在开发迁移",
    )
    parser.add_argument(
        "--include-account-identities", action="store_true", help="023身份资源可信证据专项"
    )
    parser.add_argument(
        "--material-references-only", action="store_true", help="024内部引用与双方权限真实专项"
    )
    parser.add_argument(
        "--include-configuration-metadata", action="store_true", help="快速专项附加原配置元数据三组"
    )
    parser.add_argument(
        "--include-account-capacity",
        action="store_true",
        help="真实5万账户/百万事实/20并发，不降低原性能目标",
    )
    parser.add_argument(
        "--material-scanner-manifest", help="仅隔离验收的固定真实ClamD策略清单，不是生产配置"
    )
    parser.add_argument(
        "--include-account-scopes", action="store_true", help="025原范围冻结及成员接口真实专项"
    )
    parser.add_argument(
        "--include-launch-drafts", action="store_true", help="021投放草稿/模板真实事务专项"
    )
    parser.add_argument(
        "--include-launch-scope-consumption",
        action="store_true",
        help="025冻结账户范围在实际投放草稿中的消费专项",
    )
    parser.add_argument(
        "--include-account-command-diagnostics",
        action="store_true",
        help="031本人账户命令状态实际权限及严格响应专项",
    )
    parser.add_argument(
        "--launch-drafts-only", action="store_true", help="仅独立人员与投放草稿/模板专项"
    )
    parser.add_argument(
        "--include-material-security",
        action="store_true",
        help="旧素材安全消费者及重扫实际HTTP专项",
    )
    parser.add_argument(
        "--include-material-security-scope",
        action="store_true",
        help="素材安全本人/peer/撤权真实交集专项",
    )
    parser.add_argument(
        "--include-material-runtime-store",
        action="store_true",
        help="030真实扫描收据、运行证明及审计同事务专项",
    )
    parser.add_argument(
        "--include-material-runtime-worker",
        action="store_true",
        help="030运行证明、状态迁移及真实媒体处理Worker专项",
    )
    parser.add_argument(
        "--material-runtime-only",
        action="store_true",
        help="仅独立初始化与运行证明入库/Worker18组，不重复完整后台回归",
    )
    parser.add_argument(
        "--account-scope-visibility-plan-only",
        action="store_true",
        help="仅五万成员可见性反连接真实计划/角色及影子索引比较，不改生产查询",
    )
    parser.add_argument(
        "--launch-allocation-runtime-only",
        action="store_true",
        help="仅032真实SQL分配队列与隔离测试provider；不代表平台能力或素材引用验收",
    )
    parser.add_argument(
        "--launch-validation-only",
        action="store_true",
        help="仅038原预检HTTP与持久协议；默认正式无provider拒绝，不执行平台",
    )
    parser.add_argument(
        "--include-launch-validation-provider",
        action="store_true",
        help="仅本轮13306/UUID库显式启用ISOLATED_TEST预检协议提供器，非平台来源",
    )
    parser.add_argument(
        "--include-launch-allocation-http",
        action="store_true",
        help="仅默认无Provider档附原分配HTTP门禁/查询，不混隔离预检Provider",
    )
    parser.add_argument(
        "--include-launch-allocation-http-provider",
        action="store_true",
        help="本轮UUID库隔离分配HTTP成功协议，不代表平台能力或C引用证明",
    )
    parser.add_argument(
        "--include-template-current-scope",
        action="store_true",
        help="原模板当前可见性真实RR隔离协议专项",
    )
    parser.add_argument(
        "--include-template-metric-references",
        action="store_true",
        help="附044原模板指标依赖与版本不可变/成功重放专项",
    )
    parser.add_argument(
        "--include-metric-profile-references",
        action="store_true",
        help="原Plan真实HTTP精确指标依赖与成功重放专项",
    )
    parser.add_argument(
        "--include-metric-profile-query",
        action="store_true",
        help="附041/042指标原分页与真实来源水位专项；不代表外部Meta认证",
    )
    parser.add_argument(
        "--include-metric-profile-registry",
        action="store_true",
        help="附040指标注册表真实SQL/权限/不可变映射专项，不代表Meta来源",
    )
    parser.add_argument(
        "--include-launch-execution-provider",
        action="store_true",
        help="同轮UUID库隔离execute完整受理协议；不代表平台发送或正式权威来源",
    )
    parser.add_argument(
        "--include-launch-execution-http",
        action="store_true",
        help="原execute默认关闭HTTP门禁，验证零Task/command写入，不代表202成功受理",
    )
    parser.add_argument(
        "--include-launch-execution-guards",
        action="store_true",
        help="附039真实SQL准备/封存/并发护栏，不代表执行受理或平台发送",
    )
    parser.add_argument(
        "--task-core-only",
        action="store_true",
        help="仅033真实统一任务完整manifest/读取协议；不执行平台或预检",
    )
    parser.add_argument(
        "--include-launch-plan-source",
        action="store_true",
        help="附加真实配置源与状态CAS头分离、损坏拒绝、索引及共享锁；非预检受理",
    )
    parser.add_argument(
        "--task-event-stream-only",
        action="store_true",
        help="仅036真实事件目录/七天逻辑过期与SSE observer，不执行平台",
    )
    parser.add_argument(
        "--include-task-event-cookie",
        action="store_true",
        help="附加真实本地HTTPS IdP/Cookie退出与提供者撤销，非生产IdP验收",
    )
    parser.add_argument(
        "--include-task-event-boundaries",
        action="store_true",
        help="附加真实事务寿命、七天毫秒边界、清理竞争和checkpoint授权专项",
    )
    parser.add_argument(
        "--include-task-event-integrity",
        action="store_true",
        help="附加持久事件schema/目录一致性及在途损坏失败关闭专项",
    )
    parser.add_argument(
        "--material-scanner-configuration-only",
        action="store_true",
        help="仅034正式租户扫描配置/来源CAS与真实PNG Worker专项",
    )
    parser.add_argument(
        "--material-scanner-owner-store-only",
        action="store_true",
        help="仅037受控实例持久审计/outbox真实事务，不启动或采用任何进程",
    )
    parser.add_argument(
        "--include-material-scanner-owner-native",
        action="store_true",
        help="显式运行已审核Windows自有Job/19311两轮启停；不采用或停止原19310实例",
    )
    parser.add_argument(
        "--include-material-scanner-supervisor-native",
        action="store_true",
        help="显式单Worker监督器原生实例和PNG处理闭环，独占UUID对象根/19311",
    )
    parser.add_argument(
        "--include-material-worker-cli-native",
        action="store_true",
        help="显式CLI自有Python/Job、PNG及进程锁专项，独占UUID对象根/19311",
    )
    parser.add_argument(
        "--include-launch-execution-material-references",
        action="store_true",
        help="真实C扫描至原execute受理的素材引用接力；其余平台能力仍隔离样本",
    )
    parser.add_argument(
        "--include-launch-allocation-references",
        action="store_true",
        help="附真实扫描素材/分配引用桥专项；仅隔离SQL能力夹具，不代表Meta权威",
    )
    parser.add_argument(
        "--include-material-scanner-configuration-scope",
        action="store_true",
        help="附加扫描配置真实多身份/跨租户/撤权/注册代际专项",
    )
    parser.add_argument(
        "--include-task-core-capacity",
        action="store_true",
        help="仅附加033真实十万节点完整分页和超限拒绝，不替代模块验收",
    )
    parser.add_argument(
        "--include-template-recipients",
        action="store_true",
        help="模板分享独立最小权限候选真实专项",
    )
    parser.add_argument(
        "--template-recipients-only", action="store_true", help="仅独立人员与模板共享候选四组"
    )
    parser.add_argument(
        "--include-material-infected-memory-worker",
        action="store_true",
        help="内存测试签名真实引擎与MySQL隔离分支",
    )
    parser.add_argument(
        "--include-account-actions", action="store_true", help="账户分配/同步受理/本地解绑实际专项"
    )
    parser.add_argument(
        "--include-account-sync", action="store_true", help="账户只读同步真实MySQL/本机TLS专项"
    )
    parser.add_argument(
        "--include-launch-naming", action="store_true", help="真实命名占号/不可变来源/并发专项"
    )
    parser.add_argument(
        "--launch-naming-only",
        action="store_true",
        help="仅复用原命名真实检查与必要人员夹具，不重复无关草稿/模板全套",
    )
    parser.add_argument(
        "--browser-project",
        choices=("desktop-1440", "wide-1920", "mobile-390"),
        help="只诊断指定视口；不算三视口验收",
    )
    parser.add_argument(
        "--include-account-projection", action="store_true", help="真实到期投影读守卫与独立恢复"
    )
    parser.add_argument(
        "--include-account-assignment-options",
        action="store_true",
        help="分配动作专属候选五组真实检查",
    )
    parser.add_argument(
        "--meta-observation-registry-only",
        action="store_true",
        help="仅045原始观察真实事务/CAS/幂等专项；技术观察不授予平台执行权",
    )
    parser.add_argument(
        "--execution-lease-only",
        action="store_true",
        help="仅046尝试/租约/事实SQL护栏；隔离原execute受理，零领取或平台发送",
    )
    parser.add_argument(
        "--include-meta-identity-facts",
        action="store_true",
        help="附真实SQL来源捕获后的身份事实只读观察组合，受控Graph而非平台授权",
    )
    parser.add_argument(
        "--include-meta-receipt-bounds",
        action="store_true",
        help="附051回执原生数值CHECK边界、精确3819和无兼容性警告专项",
    )
    parser.add_argument(
        "--include-execution-lease-store",
        action="store_true",
        help="附只读恢复输入的真实流式事实和当前代际专项，不执行状态写或发送",
    )
    parser.add_argument(
        "--include-execution-fact-append",
        action="store_true",
        help="显式附050微秒事实追加、同事件并发与整笔回滚，不变更当前执行状态",
    )
    parser.add_argument(
        "--include-execution-recovery",
        action="store_true",
        help="附052恢复CAS/决策账本和原Task/SSE读取；不领取、不发送、不释放锁",
    )
    parser.add_argument(
        "--metrics-scope-only",
        action="store_true",
        help="仅监测动作消费原账户范围的真实SQL专项，不代表指标HTTP或事实来源",
    )
    parser.add_argument(
        "--include-metric-fact-schema",
        action="store_true",
        help="附048/049真实外键/不可变/完整单元选择技术SQL，不是生产发行或查询接口",
    )
    parser.add_argument(
        "--identity-publication-only",
        action="store_true",
        help="仅053身份完整发布/来源读取真实专项，不代表生产能力发行或平台验收",
    )
    parser.add_argument(
        "--metric-query-read-only",
        action="store_true",
        help="仅048/049指标事实窄读取与独立预登记来源专项，不运行旧scope夹具",
    )
    parser.add_argument(
        "--include-reference-channel-capacity",
        action="store_true",
        help="附5万渠道/5万户商及全页对账、20并发四档性能专项",
    )
    parser.add_argument(
        "--include-identity-inventory-boundaries",
        action="store_true",
        help="附完整空库存/5000原资源及5001预算拒绝真实专项，不是平台容量",
    )
    parser.add_argument(
        "--execution-recovery-scanner-only",
        action="store_true",
        help="仅054原代际恢复扫描真实混合专项，不接生产调度或发送",
    )
    parser.add_argument(
        "--include-execution-recovery-service",
        action="store_true",
        help="附显式恢复服务once/停止/原grant/实际1205专项，不注册生产调度",
    )
    parser.add_argument(
        "--identity-summary-only",
        action="store_true",
        help="仅055身份摘要/封印与独占RC真实专项，非生产Meta来源或百万容量",
    )
    parser.add_argument(
        "--include-identity-summary-capacity",
        action="store_true",
        help="显式装载200账户各5000完整身份资源并执行真实容量/P95/计划，不能附浏览器",
    )
    parser.add_argument(
        "--include-metrics-expected-manifest",
        action="store_true",
        help="附056完整预期根不可变SQL护栏，不代表结果构建/发行验收",
    )
    parser.add_argument(
        "--execution-candidate-only",
        action="store_true",
        help="仅内部候选目录原202/只读完整性及受控损坏恢复，不领取或发送",
    )
    parser.add_argument(
        "--metric-query-result-only",
        action="store_true",
        help="仅049/056内部完整结果构建真实专项，不代替生产发行或公开API验收",
    )
    parser.add_argument(
        "--include-metric-query-http",
        action="store_true",
        help="附真实Metrics公开默认未发行与当前monitor CSRF边界，非生产数据验收",
    )
    parser.add_argument(
        "--include-identity-summary-profile",
        action="store_true",
        help="显式200账户各1资源CPU诊断，不是百万容量验收",
    )
    parser.add_argument(
        "--include-metrics-browser-fixture",
        action="store_true",
        help="独立SQL来源公开200/可选三视口，非生产发行",
    )
    parser.add_argument(
        "--rules-only",
        action="store_true",
        help="原规则定义057/060真实隔离专项，不代表Simulation或调度验收",
    )
    parser.add_argument(
        "--include-rule-editor",
        action="store_true",
        help="附规则编辑真实归属与指标配置候选，不含账户选择器",
    )
    parser.add_argument(
        "--include-rule-editor-scopes",
        action="store_true",
        help="附061规则专属账户候选/冻结/成员真实专项，不等于规则模拟或调度",
    )
    parser.add_argument(
        "--include-rule-scope-consumer",
        action="store_true",
        help="附新RULE来源保存/首次绑定与并发八组，非规则执行或平台验收",
    )
    parser.add_argument(
        "--include-rule-editor-definition",
        action="store_true",
        help="附rules.edit专属完整定义及历史范围元数据七组，不借rules.read",
    )
    parser.add_argument(
        "--include-rule-schedule-preview",
        action="store_true",
        help="附未来五次运行只读技术预览七组，不授予模拟或启用资格",
    )
    parser.add_argument(
        "--rules-internal-browser",
        action="store_true",
        help="规则专项后保持隔离18083/18084最多15分钟，供内置浏览器具名验证",
    )
    parser.add_argument(
        "--include-rule-scope-options",
        action="store_true",
        help="附规则操作者/户商真实候选；不借账户读取权限或扩大可指派范围",
    )
    parser.add_argument(
        "--include-rule-simulation-schema",
        action="store_true",
        help="显式在隔离库加载063候选SQL护栏；非正式迁移或模拟业务验收",
    )
    parser.add_argument(
        "--include-rule-definition-boundaries",
        action="store_true",
        help="补原规则名称/枚举/条件/日期/数值实际HTTP边界与零部分写断言",
    )
    parser.add_argument(
        "--include-rule-simulation-access",
        action="store_true",
        help="附规则模拟有界当前授权真实SQL；不授指标发行或模拟成功资格",
    )
    parser.add_argument(
        "--include-rule-simulation-calendar",
        action="store_true",
        help="附真实账户日历与SQL共同参考时刻；非事实来源完整或模拟成功",
    )
    parser.add_argument(
        "--rules-definition-flow",
        "--rules-definition-browser",
        dest="rules_definition_browser",
        action="store_true",
        help="只建规则定义真实流程图，可选等待内置浏览器，不重复旧故障/容量档",
    )
    parser.add_argument(
        "--include-rule-display-metadata",
        action="store_true",
        help="附规则定义保存回读与真实展示元数据/权限专项",
    )
    parser.add_argument(
        "--include-rule-recovery-context",
        action="store_true",
        help="附原动作当前主体/租户与JWT、Cookie新会话CSRF真实专项",
    )
    parser.add_argument(
        "--include-account-read-cookie",
        action="store_true",
        help="在原框架Cookie六组之后附账户只读认证成功/撤权/拒绝回退两组",
    )
    parser.add_argument(
        "--include-account-scope-profile",
        action="store_true",
        help="附原五万范围创建固定SQL类别计时，不调整原超时或规模",
    )
    parser.add_argument(
        "--include-account-scope-http-profile",
        action="store_true",
        help="显式叠加范围POST同请求墙钟诊断；不替代无仪表容量验收",
    )
    parser.add_argument(
        "--include-account-query-profile",
        action="store_true",
        help="附账户首屏固定SQL类别分段诊断，仪表化档不替代容量验收",
    )
    parser.add_argument(
        "--scope-create-profile-only",
        action="store_true",
        help="仅五万范围创建与250页诊断，不替代原百万事实并发容量验收",
    )
    parser.add_argument(
        "--include-account-current-channel",
        action="store_true",
        help="附064账户当前渠道与规则筛选真实专项",
    )
    args = parser.parse_args()
    if args.include_account_current_channel and (
        not args.rules_definition_browser
        or "064_account_current_channel.sql" not in args.migration_extra
    ):
        parser.error("账户渠道专项须规则定义流程与显式064迁移")
    if args.rules_definition_browser and not (
        args.rules_only
        and args.migration_through == 62
        and not any(
            value is True
            and key
            not in {
                "rules_only",
                "rules_internal_browser",
                "rules_definition_browser",
                "include_rule_display_metadata",
                "include_rule_recovery_context",
                "include_account_current_channel",
            }
            for key, value in vars(args).items()
        )
    ):
        parser.error("规则流程图只允许through062独立规则档，可选内置浏览器")
    if args.include_rule_display_metadata and not args.rules_definition_browser:
        parser.error("展示元数据只附独立规则定义流程档，不重跑无关整轮")
    if args.include_rule_recovery_context and not args.rules_definition_browser:
        parser.error("规则恢复上下文只附独立规则定义流程档")
    if args.include_account_scope_http_profile and not (
        args.include_account_scope_profile
        and args.account_details_only
        and args.include_account_capacity
        and args.include_account_scopes
        and args.migration_through == 62
        and not args.browser
        and not args.include_account_query_profile
    ):
        parser.error("范围HTTP诊断仅叠加原through062账户容量/范围SQL诊断档")
    if (
        args.include_rule_scope_options
        or args.include_rule_simulation_schema
        or args.include_rule_definition_boundaries
        or args.include_rule_simulation_access
        or args.include_rule_simulation_calendar
    ) and not (
        args.rules_only
        and args.include_rule_editor
        and args.include_rule_editor_scopes
        and args.include_rule_scope_consumer
        and args.include_rule_editor_definition
        and args.include_rule_schedule_preview
        and args.migration_through == 62
    ):
        parser.error("规则新候选/模拟候选护栏只附完整through062规则档，不自动采用063")
    if args.include_rule_simulation_schema and args.rules_internal_browser:
        parser.error("模拟候选SQL护栏不混浏览器，避免未采用DDL影响页面证据")
    if args.include_account_read_cookie and (
        args.migration_through < 62
        or any(
            value is True and key != "include_account_read_cookie"
            for key, value in vars(args).items()
        )
    ):
        parser.error("账户Cookie两组仅附through062原框架默认HTTP档，不混独立专项或浏览器")
    if args.include_account_query_profile and (
        not args.account_details_only
        or not args.include_account_capacity
        or args.include_account_scope_profile
        or args.browser
    ):
        parser.error("账户查询诊断仅附独立账户容量档，不能混范围计时或浏览器")
    if args.include_rule_editor and (not args.rules_only or args.migration_through < 60):
        parser.error("规则编辑辅助仅附规则through060独立专项")
    if args.include_rule_editor_scopes and (
        not args.rules_only or not args.include_rule_editor or args.migration_through < 61
    ):
        parser.error("规则范围辅助仅附规则编辑through061独立专项")
    if args.include_rule_scope_consumer and not (
        args.rules_only and args.include_rule_editor and args.include_rule_editor_scopes
    ):
        parser.error("规则范围消费仅附完整through061规则编辑及范围专项")
    if args.include_rule_editor_definition and not (
        args.rules_only and args.include_rule_editor and args.migration_through >= 61
    ):
        parser.error("规则编辑定义仅附through061独立规则编辑专项")
    if args.include_rule_schedule_preview and not (
        args.rules_only and args.include_rule_editor and args.migration_through >= 62
    ):
        parser.error("时间预览仅附through062独立规则编辑专项")
    if args.rules_internal_browser and not (
        args.rules_only
        and (args.include_rule_schedule_preview or args.rules_definition_browser)
        and args.migration_through >= 62
    ):
        parser.error("内置浏览器窗口仅附through062完整规则时间预览专项")
    if args.scope_create_profile_only and (
        args.migration_through < 60
        or any(
            value is True and key != "scope_create_profile_only"
            for key, value in vars(args).items()
        )
    ):
        parser.error("范围创建专项仅允许独立through060，不混其他模式")
    if args.include_account_scope_profile and (
        not args.account_details_only
        or not args.include_account_capacity
        or not args.include_account_scopes
        or args.browser
    ):
        parser.error("范围创建诊断仅附原账户容量与范围独立档")
    if args.rules_only and (
        args.migration_through < 60
        or any(
            value is True
            and key
            not in {
                "rules_only",
                "include_rule_editor",
                "include_rule_editor_scopes",
                "include_rule_scope_consumer",
                "include_rule_editor_definition",
                "include_rule_schedule_preview",
                "rules_internal_browser",
                "include_rule_scope_options",
                "include_rule_simulation_schema",
                "include_rule_definition_boundaries",
                "include_rule_simulation_access",
                "include_rule_simulation_calendar",
                "rules_definition_browser",
                "include_rule_display_metadata",
                "include_rule_recovery_context",
                "include_account_current_channel",
            }
            for key, value in vars(args).items()
        )
    ):
        parser.error("规则定义只允许独立through060专项")
    if args.include_metrics_browser_fixture and (
        not args.metric_query_result_only
        or args.migration_through < 59
        or args.include_metric_query_http
    ):
        parser.error("指标成功链只附结果档through059，不能混默认缺来源档")
    if args.browser_module == "metrics" and not args.include_metrics_browser_fixture:
        parser.error("指标浏览器须明确独立来源夹具")
    if args.include_metrics_browser_fixture and args.browser and args.browser_module != "metrics":
        parser.error("指标成功链仅允许自己的三视口")
    if args.include_metric_query_http and not args.metric_query_result_only:
        parser.error("指标公开HTTP仅附独立结果档")
    if args.include_identity_summary_profile and (
        not args.identity_summary_only or args.browser or args.include_identity_summary_capacity
    ):
        parser.error("身份HTTP诊断仅附独立摘要档，不能混容量或浏览器")
    if args.execution_candidate_only and (
        args.migration_through < 46
        or any(
            value is True and key != "execution_candidate_only" for key, value in vars(args).items()
        )
    ):
        parser.error("执行候选只允许独立运行并明确through046以上")
    if args.metric_query_result_only and (
        args.migration_through < 56
        or any(
            value is True
            and key
            not in {
                "metric_query_result_only",
                "include_metric_query_http",
                "include_metrics_browser_fixture",
                "browser",
            }
            for key, value in vars(args).items()
        )
    ):
        parser.error("指标结果只允许独立运行并明确through056以上")
    if args.include_identity_summary_capacity and (not args.identity_summary_only or args.browser):
        parser.error("身份百万资源容量仅附独立身份摘要档，不与浏览器同轮")
    if args.identity_summary_only and (
        args.migration_through < 55
        or any(
            value is True
            and key
            not in {
                "identity_summary_only",
                "browser",
                "include_identity_summary_capacity",
                "include_identity_summary_profile",
            }
            for key, value in vars(args).items()
        )
    ):
        parser.error("身份摘要仅独立运行并明确through055以上")
    if args.identity_summary_only and args.browser and args.browser_module != "identity-summary":
        parser.error("身份摘要只允许附独立身份摘要三视口")
    if args.browser_module == "identity-summary" and not args.identity_summary_only:
        parser.error("身份摘要三视口必须使用身份摘要独立档")
    if args.include_execution_recovery_service and not args.execution_recovery_scanner_only:
        parser.error("恢复服务只能附独立恢复扫描档")
    if args.execution_recovery_scanner_only and (
        args.migration_through < 54
        or any(
            value is True
            and key not in {"execution_recovery_scanner_only", "include_execution_recovery_service"}
            for key, value in vars(args).items()
        )
    ):
        parser.error("恢复扫描仅允许独立运行及明确through054以上")
    if args.include_identity_inventory_boundaries and not args.identity_publication_only:
        parser.error("身份库存边界仅附独立完整身份发布档")
    if args.include_reference_channel_capacity and (
        not args.reference_channel_only or args.browser
    ):
        parser.error("目录渠道容量只能附独立目录渠道档，不能同轮跑浏览器")
    if args.metric_query_read_only and (
        args.migration_through < 46
        or any(
            value is True and key != "metric_query_read_only" for key, value in vars(args).items()
        )
    ):
        parser.error("指标窄读取仅允许独立运行及明确through046以上")
    if args.include_launch_identity_drafts and (
        not args.identity_publication_only or args.migration_through != 62
    ):
        parser.error("投放草稿身份专项仅附identity-publication-only through062")
    if args.identity_publication_only and (
        args.migration_through < 46
        or any(
            value is True
            and key
            not in {
                "identity_publication_only",
                "browser",
                "include_identity_inventory_boundaries",
                "include_launch_identity_drafts",
            }
            for key, value in vars(args).items()
        )
    ):
        parser.error("身份发布仅允许独立运行及明确through046以上")
    if (
        args.identity_publication_only
        and args.browser
        and args.browser_module != "identity-publication"
    ):
        parser.error("身份发布只允许附独立身份三视口")
    if args.browser_module == "identity-publication" and not args.identity_publication_only:
        parser.error("身份三视口必须使用完整发布独立档")
    if args.metrics_scope_only and (
        args.migration_through < 43
        or any(
            value is True
            and key
            not in {
                "metrics_scope_only",
                "include_metric_fact_schema",
                "include_metrics_expected_manifest",
            }
            for key, value in vars(args).items()
        )
    ):
        parser.error("监测范围专项仅允许独立运行与明确through043以上")
    if args.include_metric_fact_schema and not args.metrics_scope_only:
        parser.error("指标SQL护栏仅附独立监测范围档")
    if args.include_metrics_expected_manifest and not (
        args.metrics_scope_only and args.include_metric_fact_schema and args.migration_through >= 56
    ):
        parser.error("预期根SQL护栏必须附监测范围/原事实SQL档并明确through056")
    if args.include_meta_identity_facts and not args.meta_observation_registry_only:
        parser.error("身份事实组合仅附meta-observation-registry-only独立真实档")
    if args.include_meta_receipt_bounds and not args.meta_observation_registry_only:
        parser.error("回执数值边界只附原始观察登记独立真实档")
    if args.include_execution_lease_store and not args.execution_lease_only:
        parser.error("可信恢复读取仅附execution-lease-only独立真实档")
    if args.include_execution_fact_append and not (
        args.execution_lease_only and args.include_execution_lease_store
    ):
        parser.error("事实追加必须显式附执行租约与Store真实独立专项")
    if args.include_execution_recovery and not (
        args.execution_lease_only and args.include_execution_lease_store
    ):
        parser.error("恢复提交必须显式附执行租约与完整事实Store独立档")
    for mode, required in (("meta_observation_registry_only", 45), ("execution_lease_only", 46)):
        allowed = {mode}
        if mode == "meta_observation_registry_only":
            allowed.add("include_meta_identity_facts")
            allowed.add("include_meta_receipt_bounds")
        if mode == "execution_lease_only":
            allowed.add("include_execution_lease_store")
            allowed.add("include_execution_fact_append")
            allowed.add("include_execution_recovery")
        if getattr(args, mode) and (
            args.migration_through < required
            or any(value is True and key not in allowed for key, value in vars(args).items())
        ):
            parser.error(f"{mode}仅允许独立运行及明确through{required:03d}以上已就绪迁移")
    if args.include_account_assignment_options and not args.include_account_actions:
        parser.error("分配候选需要账户动作真实夹具")
    if args.include_account_projection and (
        not args.include_account_actions or not args.include_account_scopes
    ):
        parser.error("投影保护需要账户动作和只读范围真实夹具")
    if args.browser_project and not args.browser:
        parser.error("单视口诊断必须与browser同时使用")
    if args.include_launch_naming and (not args.include_launch_drafts or args.browser):
        parser.error("命名专项需要草稿后台真实夹具，不能混浏览器")
    if args.include_account_actions and (
        not args.include_account_alias_snapshots
        or not args.account_details_only
        or args.migration_through < 28
        or args.browser
    ):
        parser.error("账户动作需要through028与代称/详情快速夹具，不能混浏览器")
    if args.include_account_sync and (
        not args.include_account_actions or args.migration_through < 29
    ):
        parser.error("只读同步需要through029和账户动作夹具")
    if args.template_recipients_only and (
        not args.include_template_recipients
        or args.browser
        or args.include_accounts
        or args.include_materials
    ):
        parser.error("模板候选快速专项不能混入其他模块")
    if args.include_material_infected_memory_worker and not args.material_scanner_manifest:
        parser.error("真实内存感染Worker专项需要真实扫描策略")
    if args.include_template_recipients and not args.include_launch_drafts:
        parser.error("模板分享候选专项需要投放草稿/模板完整专项")
    if args.include_material_security_scope and not args.include_material_security:
        parser.error("素材安全权限专项需要完整素材安全专项及多身份夹具")
    if args.include_material_security and (
        not args.material_scanner_manifest
        or not (
            args.material_references_only
            or (
                args.browser_only
                and args.browser_module in {"material-security", "materials-and-security"}
            )
            or args.include_material_taxonomy_scope
            or not (args.material_only or args.browser_only)
        )
    ):
        parser.error("素材安全专项需要真实扫描器及完整多身份夹具")
    if args.include_scope_visibility_verdict and (
        not args.account_details_only
        or not args.include_account_scopes
        or args.migration_through < 43
        or args.browser
        or args.include_account_capacity
        or args.account_scope_visibility_plan_only
    ):
        parser.error("范围证明专项仅附through043账户详情/范围档，与容量/旧SQL计划/浏览器分开")
    if args.include_account_capacity and (not args.account_details_only or args.browser):
        parser.error("账户容量专项只附加账户详情快速模式，与浏览器单独排队")
    migration_root = ROOT / "python/orbit_api/migrations"
    for name in args.migration_extra:
        if (
            not re.fullmatch(r"[0-9]{3}_[a-z0-9_]+\.sql", name)
            or not (migration_root / name).is_file()
        ):
            parser.error("额外迁移必须是迁移目录内已存在的明确文件名")
    if len(args.migration_extra) != len(set(args.migration_extra)):
        parser.error("不能重复选择额外迁移")
    selected_migrations = sorted(
        path
        for path in migration_root.glob("*.sql")
        if int(path.name.partition("_")[0]) <= args.migration_through
        or path.name in args.migration_extra
    )
    if args.identity_summary_only and "055_identity_inventory_summary.sql" not in {
        p.name for p in selected_migrations
    }:
        parser.error("身份摘要必须包含正式055迁移")
    if args.include_metrics_expected_manifest and "056_metrics_query_expected_manifest.sql" not in {
        p.name for p in selected_migrations
    }:
        parser.error("预期根护栏必须包含正式056迁移")
    if args.execution_recovery_scanner_only and not {
        "050_execution_fact_microseconds.sql",
        "052_execution_recovery_decisions.sql",
        "054_execution_recovery_scan_indexes.sql",
    } <= {p.name for p in selected_migrations}:
        parser.error("恢复扫描必须明确已审核050/052/054正式迁移")
    if args.metric_query_read_only and not {
        "048_metric_fact_versions.sql",
        "049_metric_query_snapshots.sql",
    } <= {path.name for path in selected_migrations}:
        parser.error("指标窄读取必须明确选择已审核048/049正式迁移")
    if args.identity_publication_only and "053_identity_publication_provenance.sql" not in {
        path.name for path in selected_migrations
    }:
        parser.error("身份发布必须明确选择已审核053正式迁移")
    if args.include_metric_fact_schema and not {
        "048_metric_fact_versions.sql",
        "049_metric_query_snapshots.sql",
    } <= {path.name for path in selected_migrations}:
        parser.error("指标SQL护栏必须明确选择已审核048/049正式迁移")
    if args.include_execution_fact_append and "050_execution_fact_microseconds.sql" not in {
        path.name for path in selected_migrations
    }:
        parser.error("微秒事实追加必须明确选择已审核采用的050正式迁移")
    if args.include_execution_recovery and not {
        "050_execution_fact_microseconds.sql",
        "052_execution_recovery_decisions.sql",
    } <= {path.name for path in selected_migrations}:
        parser.error("恢复提交必须明确选择已审核050/052正式迁移")
    if args.include_meta_receipt_bounds and "051_meta_receipt_numeric_bounds.sql" not in {
        path.name for path in selected_migrations
    }:
        parser.error("回执数值边界必须明确选择已审核采用的051正式迁移")
    for mode, filename in (
        (args.meta_observation_registry_only, "045_meta_observation_registry.sql"),
        (args.execution_lease_only, "046_execution_command_leases.sql"),
    ):
        if mode and filename not in {path.name for path in selected_migrations}:
            parser.error("专项要求已审核并采用的正式迁移，候选SQL或through编号不算就绪")
    if args.include_account_scopes and (
        not args.account_details_only
        or "025_account_scope_snapshots.sql" not in {p.name for p in selected_migrations}
    ):
        parser.error("范围专项需要账户详情快速模式与明确025迁移")
    if (
        args.browser
        and args.browser_module == "scopes"
        and (
            not args.include_account_scopes
            or "027_account_scope_menu.sql" not in {p.name for p in selected_migrations}
        )
    ):
        parser.error("范围浏览器需要真实025夹具及明确027隐藏二级菜单迁移")
    if args.include_launch_drafts and args.migration_through < 22:
        parser.error("投放草稿专项需要明确001—022迁移")
    if args.include_launch_scope_consumption and (
        not args.include_launch_drafts or args.migration_through < 25 or args.browser
    ):
        parser.error("投放范围消费需要through025及原草稿专项，与浏览器独立排队")
    if args.include_account_command_diagnostics and (
        not args.include_account_actions or args.migration_through < 31 or args.browser
    ):
        parser.error("命令状态专项需要through031及原账户动作夹具，与浏览器独立排队")
    if (args.include_material_runtime_store or args.include_material_runtime_worker) and (
        "030_material_antivirus_runtime_proofs.sql" not in {p.name for p in selected_migrations}
        or args.browser
    ):
        parser.error("运行证明入库专项需要明确030迁移，与浏览器独立排队")
    if args.launch_drafts_only and (
        not args.include_launch_drafts
        or args.browser
        or args.include_accounts
        or args.include_materials
    ):
        parser.error("投放草稿快速专项不能混入其他模块或未就绪浏览器")
    if (
        args.include_materials or args.material_references_only
    ) and not args.material_scanner_manifest:
        parser.error("新版素材真实专项必须明确注入真实扫描策略，不允许默认CLEAN")
    if args.material_scanner_manifest and "026_material_antivirus_receipts.sql" not in {
        p.name for p in selected_migrations
    }:
        parser.error("真实扫描策略需要明确已就绪的026扫描证据迁移")
    if args.material_scanner_manifest and "030_material_antivirus_runtime_proofs.sql" not in {
        p.name for p in selected_migrations
    }:
        parser.error("新版素材Worker及所有CLEAN消费者必须明确030运行证明迁移")
    if args.material_references_only and (
        args.migration_through < 20
        or "024_material_reference_resource_index.sql" not in {p.name for p in selected_migrations}
        or args.browser
        or args.include_accounts
        or args.include_materials
    ):
        parser.error("素材引用快速专项需要001—020及明确024，不能混入页面或其他模块")
    if args.include_account_identities and (
        not args.account_details_only
        or not args.include_account_alias_snapshots
        or not {
            "023_account_identities.sql",
            "051_meta_receipt_numeric_bounds.sql",
            "053_identity_publication_provenance.sql",
        }
        <= {p.name for p in selected_migrations}
    ):
        parser.error("身份组合需要账户快照专项及明确023/051/053迁移")
    quick_modes = (
        args.scope_create_profile_only,
        args.rules_only,
        args.metric_query_result_only,
        args.execution_candidate_only,
        args.identity_summary_only,
        args.execution_recovery_scanner_only,
        args.metric_query_read_only,
        args.identity_publication_only,
        args.metrics_scope_only,
        args.meta_observation_registry_only,
        args.execution_lease_only,
        args.launch_naming_only,
        args.launch_validation_only,
        args.material_scanner_owner_store_only,
        args.task_event_stream_only,
        args.material_scanner_configuration_only,
        args.task_core_only,
        args.launch_allocation_runtime_only,
        args.account_scope_visibility_plan_only,
        args.material_runtime_only,
        args.template_recipients_only,
        args.launch_drafts_only,
        args.material_references_only,
        args.browser_only,
        args.channel_scope_only,
        args.account_details_only,
        args.material_only,
        args.vendor_alias_only,
        args.material_taxonomy_scope_only,
        args.material_taxonomy_metadata_only,
        args.environment_registry_only,
        args.environment_live_only,
        args.material_lifecycle_only,
        args.channel_owners_only,
        args.reference_channel_only,
    )
    if sum(quick_modes) > 1:
        parser.error("一次只能执行一种独立快速模式")
    fast_mode = any(quick_modes)
    if args.launch_naming_only:
        permitted = {"launch_naming_only", "include_configuration_metadata"}
        if args.migration_through < 31 or any(
            value is True and key not in permitted for key, value in vars(args).items()
        ):
            parser.error("命名专项需要through031，仅附元数据且不混浏览器或其他专项")
    if args.include_template_current_scope and (
        not args.launch_validation_only
        or args.migration_through < 44
        or any(
            (
                args.include_metric_profile_references,
                args.include_template_metric_references,
                args.include_metric_profile_query,
                args.include_metric_profile_registry,
                args.include_launch_validation_provider,
                args.include_launch_execution_provider,
                args.include_launch_execution_http,
                args.include_launch_execution_guards,
                args.include_launch_allocation_http,
                args.include_launch_allocation_http_provider,
            )
        )
    ):
        parser.error("模板RR专项仅附through044默认预检档，与其他业务专项分开")
    if args.include_template_metric_references and (
        not args.include_metric_profile_references or args.migration_through < 44
    ):
        parser.error("模板指标专项需要through044并附原计划指标引用档")
    if args.include_metric_profile_references and (
        not args.launch_validation_only
        or args.migration_through < 43
        or any(
            (
                args.include_metric_profile_query,
                args.include_metric_profile_registry,
                args.include_launch_validation_provider,
                args.include_launch_execution_provider,
                args.include_launch_execution_http,
                args.include_launch_execution_guards,
                args.include_launch_allocation_http,
                args.include_launch_allocation_http_provider,
            )
        )
    ):
        parser.error("指标引用专项只附through043默认预检档，不混提供器/分页/注册专项")
    if args.include_metric_profile_query and (
        not args.launch_validation_only
        or args.migration_through < 42
        or args.include_metric_profile_registry
        or args.include_launch_validation_provider
        or args.include_launch_execution_provider
        or args.include_launch_execution_http
        or args.include_launch_execution_guards
        or args.include_launch_allocation_http
        or args.include_launch_allocation_http_provider
    ):
        parser.error("指标分页专项仅附through042默认预检档，不混其他提供器")
    if args.include_metric_profile_registry and (
        not args.launch_validation_only
        or args.migration_through < 40
        or args.include_launch_validation_provider
        or args.include_launch_execution_provider
        or args.include_launch_execution_http
        or args.include_launch_execution_guards
        or args.include_launch_allocation_http
        or args.include_launch_allocation_http_provider
    ):
        parser.error("指标注册表专项仅附through040默认预检档，不混执行或分配提供器")
    if args.include_launch_execution_provider and (
        not args.launch_validation_only
        or not args.include_launch_validation_provider
        or args.migration_through < 39
        or args.include_launch_execution_http
        or args.include_launch_execution_guards
        or args.include_launch_allocation_http
        or args.include_launch_allocation_http_provider
    ):
        parser.error("执行隔离协议仅附through039隔离预检提供器，不混其他执行或分配档")
    if args.include_launch_execution_http and (
        not args.launch_validation_only
        or args.migration_through < 39
        or args.include_launch_validation_provider
        or args.include_launch_allocation_http
        or args.include_launch_allocation_http_provider
        or args.include_launch_execution_guards
    ):
        parser.error("执行默认HTTP门禁仅附through039无Provider预检档，不混其他提供器")
    if args.include_launch_execution_guards and (
        not args.launch_validation_only
        or args.migration_through < 39
        or args.include_launch_validation_provider
        or args.include_launch_allocation_http
        or args.include_launch_allocation_http_provider
    ):
        parser.error("039 SQL护栏仅附默认预检档，不能混入提供器或其他分配专项")
    if args.include_launch_validation_provider and not args.launch_validation_only:
        parser.error("隔离预检提供器仅能附同轮预检专项")
    if args.include_launch_allocation_http and (
        not args.launch_validation_only or args.include_launch_validation_provider
    ):
        parser.error("分配HTTP门禁只能附默认无Provider预检档")
    if args.include_launch_allocation_http_provider and (
        not args.launch_validation_only
        or args.include_launch_validation_provider
        or args.include_launch_allocation_http
    ):
        parser.error("分配HTTP成功协议独立附默认预检档，不能混两个提供器或默认关闭断言")
    if args.launch_validation_only:
        permitted = {
            "launch_validation_only",
            "include_launch_validation_provider",
            "include_launch_allocation_http",
            "include_launch_allocation_http_provider",
            "include_launch_execution_guards",
            "include_launch_execution_http",
            "include_launch_execution_provider",
            "include_metric_profile_registry",
            "include_metric_profile_query",
            "include_metric_profile_references",
            "include_template_metric_references",
            "include_template_current_scope",
            "include_configuration_metadata",
        }
        if args.migration_through < 38 or any(
            value is True and key not in permitted for key, value in vars(args).items()
        ):
            parser.error("原预检专项需要through038，仅附隔离提供器与元数据，不混浏览器")
    if args.include_material_scanner_owner_native and not args.material_scanner_owner_store_only:
        parser.error("Windows原生所有者专项只能附加当前037隔离审计模式")
    if args.include_material_scanner_supervisor_native and (
        not args.material_scanner_owner_store_only or args.include_material_scanner_owner_native
    ):
        parser.error("监督器原生专项仅附037审计，与旧原生实例专项分开串行执行")
    if args.include_material_worker_cli_native and (
        not args.material_scanner_owner_store_only
        or args.include_material_scanner_owner_native
        or args.include_material_scanner_supervisor_native
    ):
        parser.error("CLI原生专项仅附037审计，与其他原生专项分开串行执行")
    if args.material_scanner_owner_store_only:
        permitted = {
            "material_scanner_owner_store_only",
            "include_configuration_metadata",
            "include_material_scanner_owner_native",
            "include_material_scanner_supervisor_native",
            "include_material_worker_cli_native",
        }
        if args.migration_through < 37 or any(
            value is True and key not in permitted for key, value in vars(args).items()
        ):
            parser.error("实例审计专项需要through037，仅可附配置元数据且不启动进程")
    if args.include_task_event_cookie and not args.task_event_stream_only:
        parser.error("Cookie事件专项须附加同轮036事件快速专项")
    if args.include_task_event_boundaries and not args.task_event_stream_only:
        parser.error("事件边界专项须附加同轮036事件快速专项")
    if args.include_task_event_integrity and not args.task_event_stream_only:
        parser.error("事件完整性专项须附加同轮036事件快速专项")
    if args.task_event_stream_only:
        permitted = {
            "task_event_stream_only",
            "include_task_event_cookie",
            "include_task_event_boundaries",
            "include_task_event_integrity",
            "include_configuration_metadata",
        }
        if args.migration_through < 36 or any(
            value is True and key not in permitted for key, value in vars(args).items()
        ):
            parser.error("事件流专项需要through036，仅可附Cookie与配置元数据")
    if (
        args.include_material_scanner_configuration_scope
        and not args.material_scanner_configuration_only
    ):
        parser.error("扫描配置范围检查须附加同轮配置专项")
    if args.include_launch_execution_material_references and (
        not args.material_scanner_configuration_only
        or args.migration_through < 39
        or args.include_launch_allocation_references
        or args.include_material_scanner_configuration_scope
        or args.browser
    ):
        parser.error("执行素材引用桥只附through039以上扫描配置档，与其他桥或浏览器独立排队")
    if args.include_launch_allocation_references and (
        not args.material_scanner_configuration_only
        or args.migration_through < 38
        or args.include_material_scanner_configuration_scope
        or args.browser
    ):
        parser.error("素材分配引用桥只附through038以上扫描配置档，不混范围或浏览器专项")
    if args.material_scanner_configuration_only:
        permitted = {
            "material_scanner_configuration_only",
            "include_configuration_metadata",
            "include_material_scanner_configuration_scope",
            "include_launch_allocation_references",
            "include_launch_execution_material_references",
        }
        if args.browser and args.browser_module == "scanner-configuration":
            permitted.add("browser")
        if (
            args.migration_through < 34
            or not args.material_scanner_manifest
            or any(value is True and key not in permitted for key, value in vars(args).items())
        ):
            parser.error("扫描配置专项需要through034和明确真实扫描策略，仅可附元数据")
    if (
        args.browser
        and args.browser_module == "scanner-configuration"
        and not args.material_scanner_configuration_only
    ):
        parser.error("扫描配置浏览器须先执行同轮034真实专项，不能用空候选占位验收")
    if args.include_task_core_capacity and not args.task_core_only:
        parser.error("十万任务节点容量必须明确task-core-only")
    if args.include_launch_plan_source and (not args.task_core_only or args.browser):
        parser.error("配置源专项仅附task-core-only，真实浏览器另行排队")
    if args.include_task_core_capacity and args.browser:
        parser.error("任务容量与浏览器分开排队，不能混为页面验收")
    if args.task_core_only:
        permitted = {
            "task_core_only",
            "include_task_core_capacity",
            "include_launch_plan_source",
            "include_configuration_metadata",
        }
        if args.browser and args.browser_module in {"tasks", "task-events"}:
            permitted.add("browser")
        if args.migration_through < 36 or any(
            value is True and key not in permitted for key, value in vars(args).items()
        ):
            parser.error("统一任务专项需要through036（含快照续传凭证），仅附任务容量及配置元数据")
    if args.browser and args.browser_module in {"tasks", "task-events"} and not args.task_core_only:
        parser.error("任务页面必须使用同轮真实持久Task夹具，不能以空列表占位验收")
    if args.launch_allocation_runtime_only:
        permitted = {"launch_allocation_runtime_only", "include_configuration_metadata"}
        if args.migration_through < 32 or any(
            value is True and key not in permitted for key, value in vars(args).items()
        ):
            parser.error("分配队列专项仅允许明确through032及可选配置元数据")
    if args.account_scope_visibility_plan_only:
        permitted = {"account_scope_visibility_plan_only", "include_configuration_metadata"}
        if args.migration_through < 25 or any(
            value is True and key not in permitted for key, value in vars(args).items()
        ):
            parser.error("成员执行计划专项仅允许through025以上及可选配置元数据")
    if args.material_runtime_only:
        permitted = {
            "material_runtime_only",
            "include_material_runtime_store",
            "include_material_runtime_worker",
            "include_configuration_metadata",
        }
        if (
            not args.include_material_runtime_store
            or not args.include_material_runtime_worker
            or any(value is True and key not in permitted for key, value in vars(args).items())
        ):
            parser.error("运行证明快速模式只允许两组真实专项及可选配置元数据")
    if args.reference_channel_only and (
        args.migration_through < 11
        or args.include_materials
        or args.include_accounts
        or args.include_vendor_alias
    ):
        parser.error("B模块快速专项不能混入账户、素材或代称专项")
    if (
        args.browser
        and args.browser_module == "channel-owners500"
        and not args.include_channel_owners
    ):
        parser.error("500人浏览器需要实际500身份及引用目录夹具")
    if not 8 <= args.migration_through <= 999:
        parser.error("迁移上限必须在8至999之间")
    if (
        args.browser
        and args.browser_module in {"accounts", "account-command"}
        and not args.include_account_details
    ):
        parser.error("账户浏览器必须提供真实账户详情夹具")
    if args.browser and args.browser_module == "account-command" and args.migration_through < 31:
        parser.error("命令状态浏览器必须明确through031")
    if args.browser and args.browser_module == "vendor-alias" and args.migration_through < 17:
        parser.error("户商代称浏览器需要001—017")
    if args.browser and args.browser_module == "channels" and args.migration_through < 11:
        parser.error("渠道浏览器专项必须显式执行001—011迁移")
    if args.include_materials and args.migration_through < 11:
        parser.error("素材专项必须显式执行001—011迁移")
    if args.material_only and (
        not args.include_materials
        or (args.browser and args.browser_module not in {"materials", "materials-and-security"})
        or args.include_accounts
        or args.include_channel_scope
    ):
        parser.error("素材快速专项不能混入浏览器、账户或渠道权限专项")
    if args.include_accounts and args.migration_through < 13:
        parser.error("账户专项必须显式执行001—013迁移")
    if (
        args.browser
        and args.browser_module in {"materials", "materials-and-security"}
        and not args.include_materials
    ):
        parser.error("素材浏览器专项必须同时运行素材真实文件及HTTP检查")
    if args.include_account_worker and (not args.include_accounts or args.migration_through < 14):
        parser.error("账户Worker专项必须同时执行账户HTTP及001—014迁移")
    if args.include_account_details and (not args.include_accounts or args.migration_through < 15):
        parser.error("账户详情专项必须同时执行账户HTTP及001—015迁移")
    if args.account_details_only and (
        not args.include_account_details
        or (args.browser and args.browser_module not in {"accounts", "scopes", "account-command"})
        or args.include_materials
        or args.include_channel_scope
        or (args.include_account_worker and not args.include_account_alias_snapshots)
    ):
        parser.error("账户详情快速专项只可附加账户浏览器，不能混入其他模块")
    if args.include_channel_scope and args.migration_through < 11:
        parser.error("渠道补充权限矩阵需要001—011迁移")
    if args.channel_scope_only and (
        not args.include_channel_scope
        or args.browser
        or args.include_materials
        or args.include_accounts
        or args.include_account_details
        or args.include_account_worker
    ):
        parser.error("渠道快速矩阵仅初始化专属人员和渠道权限，不能混入其他专项")
    if args.environment_internal_browser and not (
        args.environment_registry_only or args.environment_live_only
    ):
        parser.error("执行机浏览器窗口仅附独立执行机登记档")
    if args.environment_registry_only and (
        args.migration_through != 62
        or not {"066_execution_agent_registry.sql", "067_agent_live_monitoring.sql", "068_agent_probe_requests.sql", "069_agent_action_capabilities.sql", "070_agent_execution_leases.sql"}.issubset(args.migration_extra)
        or any(
            value is True
            and key not in {"environment_registry_only", "environment_internal_browser"}
            for key, value in vars(args).items()
        )
    ):
        parser.error("执行机登记须独立through062加显式066/067/068迁移；不得混入其他专项")
    if args.meta_expectation_file and not args.include_local_adspower:
        parser.error("Meta预期文件必须伴随显式本机AdsPower验收")
    if args.include_local_adspower and not args.environment_live_only:
        parser.error("本机AdsPower访问仅允许显式独立监测档")
    if args.include_meta_connection_checks and (not args.environment_live_only or "071_meta_connections.sql" not in args.migration_extra):
        parser.error("Meta连接SQL专项需要隔离监测档及071迁移")
    if args.include_meta_pipeline_checks and (not args.include_meta_connection_checks or not {"072_meta_metric_collection.sql", "073_meta_import_source.sql", "074_meta_metric_profile_connections.sql", "075_meta_sync_policy.sql"}.issubset(args.migration_extra)):
        parser.error("Meta采集专项需要连接专项及071至075显式迁移")
    if args.environment_live_only and (
        args.migration_through != 62
        or not {"066_execution_agent_registry.sql", "067_agent_live_monitoring.sql", "068_agent_probe_requests.sql", "069_agent_action_capabilities.sql", "070_agent_execution_leases.sql"}.issubset(
            args.migration_extra
        )
        or any(
            value is True
            and key
            not in {
                "environment_live_only",
                "environment_internal_browser",
                "include_local_adspower",
                "include_meta_connection_checks",
                "include_meta_pipeline_checks",
            }
            for key, value in vars(args).items()
        )
    ):
        parser.error("监测独立档须through062加显式066/067/068迁移，不混其他专项")
    if args.taxonomy_internal_browser and not args.material_taxonomy_metadata_only:
        parser.error("标签浏览器窗口只附独立目录元数据档")
    if args.material_taxonomy_metadata_only:
        permitted = {
            "material_taxonomy_metadata_only",
            "include_material_taxonomy_capabilities",
            "taxonomy_internal_browser",
        }
        if (
            not args.include_material_taxonomy_capabilities
            or args.material_scanner_manifest
            or args.material_video_bin
            or any(value is True and key not in permitted for key, value in vars(args).items())
        ):
            parser.error("标签目录元数据档不得混入上传、对象存储、扫描或其他专项")
    if args.include_material_taxonomy_capabilities and (
        not args.material_taxonomy_metadata_only
        or args.migration_through != 62
        or "065_material_taxonomy_menu_access.sql" not in args.migration_extra
    ):
        parser.error("标签独立能力专项仅附目录元数据档、through062及显式065菜单迁移")
    if args.include_material_taxonomy_scope and (
        args.migration_through < 16 or not args.include_materials
    ):
        parser.error("标签范围专项必须执行001—016并初始化素材独立目录")
    if args.material_taxonomy_scope_only and (
        not args.include_material_taxonomy_scope
        or args.browser
        or args.include_accounts
        or args.include_channel_scope
        or args.include_vendor_alias
        or args.include_material_video
        or args.material_only
        or args.browser_only
        or args.include_material_taxonomy
    ):
        parser.error("标签范围快速模式不能混入其他专项")
    if args.include_vendor_alias and args.migration_through < 17:
        parser.error("户商代称专项必须显式执行001—017")
    if args.vendor_alias_only and (
        not args.include_vendor_alias
        or args.browser
        or args.include_materials
        or args.include_accounts
        or args.include_channel_scope
    ):
        parser.error("户商代称快速专项不能混入其他模块")
    if args.include_vendor_alias and (
        args.browser_only
        or args.material_only
        or args.account_details_only
        or args.channel_scope_only
    ):
        parser.error("户商代称专项不能混入其他模块快速模式")
    if args.include_material_taxonomy and (
        args.migration_through < 16 or not args.include_material_video or args.browser_only
    ):
        parser.error("标签分类专项需要001—016、真实素材和视频专项，不能混入浏览器快速模式")
    if args.include_material_video:
        tool_root = (ROOT.parent / ".runtime/tools").resolve()
        if (
            not args.include_materials
            or args.material_video_bin is None
            or not args.material_video_bin.resolve().is_relative_to(tool_root)
            or not args.material_video_bin.is_dir()
        ):
            parser.error("视频专项需要素材HTTP及工作区工具目录；工具SHA仍由专项再次核验")
    elif args.material_video_bin is not None:
        parser.error("视频工具路径必须与视频专项同时提供")
    if args.browser_only and (
        not args.browser
        or args.browser_module
        not in {
            "configuration",
            "channels",
            "materials",
            "vendor-alias",
            "material-security",
            "materials-and-security",
            "launch",
            "metric-profiles",
            "launch-metric-profiles",
        }
        or args.include_accounts
        or args.include_account_worker
        or args.include_account_details
        or args.include_channel_scope
        or args.include_material_video
    ):
        parser.error("浏览器快速专项仅适用于渠道/素材，不能包含账户后台专项")
    if args.browser_module == "launch" and args.migration_through < 22:
        parser.error("投放浏览器需要完整001—022迁移")
    if (
        args.browser
        and args.browser_module == "launch-metric-profiles"
        and args.migration_through < 44
    ):
        parser.error("指标编辑浏览器需要完整001—044迁移")
    if args.browser and args.browser_module == "metric-profiles" and args.migration_through < 42:
        parser.error("指标目录浏览器需要完整001—042迁移")
    if args.browser_module != "all" and not args.browser:
        parser.error("--browser-module必须与--browser一起使用")
    if args.include_channel_fields and (
        args.migration_through < 11
        or args.browser_only
        or args.channel_scope_only
        or args.account_details_only
        or args.material_only
        or args.vendor_alias_only
        or args.material_taxonomy_scope_only
        or args.material_lifecycle_only
        or args.channel_owners_only
    ):
        parser.error("渠道原字段专项需要完整目录夹具，不能混入快速模式")
    if (
        sum(
            (
                args.browser_only,
                args.channel_scope_only,
                args.account_details_only,
                args.material_only,
                args.vendor_alias_only,
                args.material_taxonomy_scope_only,
            )
        )
        > 1
    ):
        parser.error("一次只能执行一种独立快速模式")
    if args.include_material_lifecycle_races and not args.include_material_lifecycle:
        parser.error("生命周期竞争专项需要基础队列专项")
    if args.include_material_lifecycle_recovery and not args.include_material_lifecycle:
        parser.error("生命周期恢复专项必须与基础专项一起执行")
    if args.include_material_lifecycle and (
        args.migration_through < 19 or not args.include_materials
    ):
        parser.error("生命周期专项需要001—019和独立素材对象目录")
    if args.material_lifecycle_only and (
        not args.include_material_lifecycle
        or args.browser
        or args.include_accounts
        or args.include_material_taxonomy
        or args.include_material_taxonomy_scope
        or args.include_channel_fields
        or args.include_vendor_alias
        or args.include_material_video
        or args.material_only
        or args.browser_only
        or args.channel_scope_only
    ):
        parser.error("生命周期快速模式不能混入其他模块")
    if args.include_channel_owners and (
        args.migration_through < 11
        or args.browser_only
        or args.channel_scope_only
        or args.account_details_only
        or args.material_only
        or args.vendor_alias_only
        or args.material_taxonomy_scope_only
        or args.material_lifecycle_only
    ):
        parser.error("渠道500专项需要完整专属人员夹具，不能混入其他快速模式")
    if args.channel_owners_only and (
        not args.include_channel_owners
        or args.browser
        or args.include_accounts
        or args.include_materials
        or args.include_channel_scope
        or args.include_vendor_alias
        or args.include_channel_fields
    ):
        parser.error("渠道500快速专项不能混入其他模块")
    if args.include_account_alias_snapshots and (
        args.migration_through < 20
        or not args.include_accounts
        or not args.include_account_details
        or not args.include_account_worker
    ):
        parser.error("020专项需要账户受理/Worker/详情及001—020迁移")
    # 每个专项均独立声明业务包路径，不依赖其他检查先运行所产生的导入副作用。
    for package_root in (FRAMEWORK, ROOT / "python"):
        if str(package_root) not in sys.path:
            sys.path.insert(0, str(package_root))
    from config.asyncmy_compat import install_windows_asyncmy_compat

    # 独立 SQL 工具不一定导入框架 database；显式使用与应用相同的驱动兼容。
    install_windows_asyncmy_compat()
    material_scanner = raw_material_scanner = scanner_policy_json = runtime_profile_payload = None
    material_scanner_registry = None
    if args.material_scanner_manifest:
        from dataclasses import asdict

        from material_antivirus_engine_checks import (
            MATERIAL_ANTIVIRUS_ENGINE_CASES,
            fixture_scanner_policy,
            run_material_antivirus_engine_checks,
        )
        from material_antivirus_worker_checks import (
            MATERIAL_ANTIVIRUS_WORKER_CASES,
            run_material_antivirus_worker_checks,
        )
        from material_runtime_fixture import (
            material_runtime_fixture_payload,
            material_runtime_fixture_scanner,
        )

        from orbit_api.material_antivirus import ClamdMaterialScanner

        policy = fixture_scanner_policy(args.material_scanner_manifest)
        raw_material_scanner = ClamdMaterialScanner(policy)
        material_scanner, _runtime_process = material_runtime_fixture_scanner()
        assert material_scanner.profile.policy == policy
        runtime_profile_payload = material_runtime_fixture_payload(material_scanner)
        scanner_policy_json = asdict(policy)
        scanner_policy_json["daily_db_built_at"] = policy.daily_db_built_at.isoformat()
        if args.material_scanner_configuration_only:
            from orbit_api.material_scanner_registry import MaterialScannerRegistry

            material_scanner_registry = MaterialScannerRegistry()
            material_scanner_registry.publish(material_scanner, "本机隔离扫描器")
    browser_case = (
        "pythonBrowserRegisteredModulesThreeViewports"
        if args.browser_module == "all"
        else f"pythonBrowser{args.browser_module.title()}ThreeViewports"
    )
    if args.browser_project:
        browser_case = (
            f"pythonBrowser{args.browser_module.title()}SingleViewport{args.browser_project}"
        )
    started = dt.datetime.now(dt.UTC)
    result = {
        "name": "python-framework-integration",
        "phase": "testing",
        "item_ids": [],
        "executed_at": started.isoformat(),
        "command": ".venv/Scripts/python.exe tools/run_python_framework_checks.py",
        "environment": "本机独立MySQL13306、Redis16379/DB15、FastAPI真实HTTP18083；不访问平台",
        "scope": (
            "新Python框架启动、JSON登录兼容、当前用户/动态菜单、配置62字段元数据/身份注入/"
            "真实错误状态/即时撤权、配置写入/幂等/CAS/审计与outbox回滚/历史/角色及租户隔离；非完整模块验收"
        ),
    }
    if args.browser_project:
        result["browser_project"] = args.browser_project
        result["command"] += f" --browser-project {args.browser_project}"
    if args.migration_through != 8:
        result["command"] += f" --migration-through {args.migration_through}"
    if args.include_account_read_cookie:
        result["command"] += " --include-account-read-cookie"
        result["scope"] += "；附账户专属Cookie成功/撤权/拒绝Bearer回退两组，非真实IdP生产验收"
    if args.include_account_assignment_options:
        result["command"] += " --include-account-assignment-options"
    if args.include_account_projection:
        result["command"] += " --include-account-projection"
    if args.include_launch_naming:
        result["command"] += " --include-launch-naming"
    if args.launch_naming_only:
        result["command"] += " --launch-naming-only"
        result["scope"] = "仅原命名实际SQL/HTTP及必要人员夹具，不代表完整预检/执行或其他模块回归"
    if args.include_account_actions:
        result["command"] += " --include-account-actions"
    if args.include_account_sync:
        result["command"] += " --include-account-sync"
    if args.include_materials:
        result["command"] += " --include-materials"
    if args.material_only:
        result["command"] += " --material-only"
        result["scope"] = "仅独立素材夹具、真实文件/HTTP/Worker及指定媒体专项，不代表完整后台回归"
    if args.include_accounts:
        result["command"] += " --include-accounts"
    if args.include_account_worker:
        result["command"] += " --include-account-worker"
    if args.include_channel_scope:
        result["command"] += " --include-channel-scope"
    if args.channel_scope_only:
        result["command"] += " --channel-scope-only"
        result["scope"] = "仅独立夹具初始化、真实人员夹具及渠道写入权限矩阵，不代表完整后台回归"
    if args.include_account_details:
        result["command"] += " --include-account-details"
    if args.account_details_only:
        result["command"] += " --account-details-only"
        result["scope"] = "仅独立夹具初始化、真实人员、目录引用和账户详情专项，不代表完整后台回归"
        if args.include_account_query_profile:
            result["command"] += " --include-account-query-profile"
            result["scope"] += "；首屏固定SQL分段仪表化诊断，不作为容量合格证明"
    if args.include_material_video:
        result["command"] += " --include-material-video --material-video-bin <已校验本机工具目录>"
    if args.reference_channel_only:
        result["command"] += " --reference-channel-only"
        result["scope"] = "仅B目录渠道及明确附加字段/500/浏览器专项，不代表其他模块后台回归"
    if args.include_reference_channel_capacity:
        result["command"] += " --include-reference-channel-capacity"
        result["scope"] += "；附5万渠道/5万户商原HTTP完整页与20并发四档性能，不是生产冷启动"
    if args.include_account_alias_snapshots:
        result["command"] += " --include-account-alias-snapshots"
    for migration in args.migration_extra:
        result["command"] += f" --migration-extra {migration}"
    if args.include_account_identities:
        result["command"] += " --include-account-identities"
    if args.include_configuration_metadata:
        result["command"] += " --include-configuration-metadata"
    if args.include_account_capacity:
        result["command"] += " --include-account-capacity"
        if args.include_account_scope_profile:
            result["command"] += " --include-account-scope-profile"
            result["scope"] += "；原10秒/五万范围不变，附隔离SQL阶段诊断"
        if args.include_account_scope_http_profile:
            result["command"] += " --include-account-scope-http-profile"
            result["scope"] += "；附同请求认证/Store/SQL/响应墙钟，仪表档不替代容量验收"
    if args.include_account_scopes:
        result["command"] += " --include-account-scopes"
    if args.include_scope_visibility_verdict:
        result["command"] += " --include-scope-visibility-verdict"
    if args.include_launch_drafts:
        result["command"] += " --include-launch-drafts"
    if args.include_launch_scope_consumption:
        result["command"] += " --include-launch-scope-consumption"
    if args.include_account_command_diagnostics:
        result["command"] += " --include-account-command-diagnostics"
    if args.include_template_recipients:
        result["command"] += " --include-template-recipients"
    if args.launch_drafts_only:
        result["command"] += " --launch-drafts-only"
        result["scope"] = "仅投放草稿/模板及明确附加检查，不包含命名、分配、预检与真实执行"
    if args.material_scanner_manifest:
        result["command"] += " --material-scanner-manifest <固定本机真实扫描清单>"
        result["material_scanner_policy"] = scanner_policy_json
    if args.include_material_security:
        result["command"] += " --include-material-security"
    if args.include_material_security_scope:
        result["command"] += " --include-material-security-scope"
    if args.include_material_runtime_store:
        result["command"] += " --include-material-runtime-store"
    if args.include_material_runtime_worker:
        result["command"] += " --include-material-runtime-worker"
    if args.include_material_infected_memory_worker:
        result["command"] += " --include-material-infected-memory-worker"
    if args.template_recipients_only:
        result["command"] += " --template-recipients-only"
        result["scope"] = "仅模板共享候选最小权限及事务原子性，不重复执行原D1草稿检查"
    if args.material_references_only:
        result["command"] += " --material-references-only"
        result["scope"] = "仅内部引用及双方真实权限，不代表上传杀毒、投放分配HTTP或容量验收"
    if args.include_channel_owners:
        result["command"] += " --include-channel-owners"
    if args.channel_owners_only:
        result["command"] += " --channel-owners-only"
        result["scope"] = "仅初始化、专属人员与500不同有效拥有者矩阵，不代表容量或整模块验收"
    if args.include_material_lifecycle_races:
        result["command"] += " --include-material-lifecycle-races"
    if args.include_material_lifecycle_recovery:
        result["command"] += " --include-material-lifecycle-recovery"
    if args.include_material_lifecycle:
        result["command"] += " --include-material-lifecycle"
    if args.material_lifecycle_only:
        result["command"] += " --material-lifecycle-only"
        result["scope"] = (
            "仅初始化与019真实队列/文件/Worker，不代表旧HTTP写方已接入或生命周期全验收"
        )
    if args.include_channel_fields:
        result["command"] += " --include-channel-fields"
    if args.include_material_taxonomy_scope:
        result["command"] += " --include-material-taxonomy-scope"
    if args.environment_live_only:
        result["command"] += " --environment-live-only"
    if args.include_local_adspower:
        result["command"] += " --include-local-adspower"
    if args.environment_registry_only:
        result["command"] += " --environment-registry-only"
    if args.environment_internal_browser:
        result["command"] += " --environment-internal-browser"
    if args.material_taxonomy_metadata_only:
        result["command"] += " --material-taxonomy-metadata-only"
        result["scope"] = (
            "仅真实人员及标签分类目录元数据、范围计数、动作权限、CAS/幂等与引用保护；"
            "无对象存储/扫描器，不覆盖素材上传、处理、扫描或投放"
        )
    if args.taxonomy_internal_browser:
        result["command"] += " --taxonomy-internal-browser"
    if args.include_material_taxonomy_capabilities:
        result["command"] += " --include-material-taxonomy-capabilities"
    if args.material_taxonomy_scope_only:
        result["command"] += " --material-taxonomy-scope-only"
        result["scope"] = "仅初始化、真实人员与标签计数/游标范围，不代表完整后台回归"
        if args.include_material_taxonomy_capabilities:
            result["scope"] += "；含标签分类独立动作能力、CAS/幂等、引用保护"
    if args.include_vendor_alias:
        result["command"] += " --include-vendor-alias"
    if args.vendor_alias_only:
        result["command"] += " --vendor-alias-only"
        result["scope"] = "仅独立初始化、真实人员及户商代称专项，不代表完整后台回归"
    if args.include_material_taxonomy:
        result["command"] += " --include-material-taxonomy"
    if args.browser_only:
        result["command"] += " --browser-only"
        result["scope"] = (
            "仅真实独立夹具初始化、登录、当前用户、菜单与指定三视口浏览器；不执行或宣称后台全回归"
        )
    result["backend_regression_executed"] = not fast_mode
    if args.launch_validation_only:
        result["command"] += " --launch-validation-only"
        if args.include_launch_validation_provider:
            result["command"] += " --include-launch-validation-provider"
        if args.include_launch_allocation_http:
            result["command"] += " --include-launch-allocation-http"
        if args.include_launch_allocation_http_provider:
            result["command"] += " --include-launch-allocation-http-provider"
        if args.include_launch_execution_guards:
            result["command"] += " --include-launch-execution-guards"
        if args.include_launch_execution_http:
            result["command"] += " --include-launch-execution-http"
        if args.include_launch_execution_provider:
            result["command"] += " --include-launch-execution-provider"
        if args.include_metric_profile_registry:
            result["command"] += " --include-metric-profile-registry"
        if args.include_metric_profile_query:
            result["command"] += " --include-metric-profile-query"
        if args.include_metric_profile_references:
            result["command"] += " --include-metric-profile-references"
        if args.include_template_metric_references:
            result["command"] += " --include-template-metric-references"
        if args.include_template_current_scope:
            result["command"] += " --include-template-current-scope"
        result["scope"] = (
            "仅038原validate/配置源CAS/幂等/真实SQL与HTTP；"
            "ISOLATED_TEST提供器不代表Meta身份/能力来源，不开放execute或平台写入"
        )
        if args.include_launch_execution_guards:
            result["scope"] += "；附039 SQL准备/封存/锁顺序护栏夹具，不是execute受理或发送验收"
        if args.include_launch_execution_http:
            result["scope"] += "；附execute默认503零Task/command写入，不是202成功受理"
        if args.include_launch_execution_provider:
            result["scope"] = (
                "仅038/039隔离预检与execute真实SQL/HTTP完整受理、幂等、回滚和过期边界；"
                "提供器为ISOLATED_TEST，素材引用为SQL样本，不是正式Meta来源、C扫描接力或平台发送"
            )
        if args.include_metric_profile_registry:
            result["scope"] += (
                "；附040指标注册表真实SQL来源样本/原release权限/精确映射/撤权/回滚/索引，"
                "没有原GET页面或真实Meta来源验收"
            )
        if args.include_metric_profile_query:
            result["scope"] += "；附指标只读分页/来源水位/权限的真实SQL与HTTP，来源样本非Meta认证"
    if args.material_scanner_owner_store_only:
        result["command"] += " --material-scanner-owner-store-only"
        if args.include_material_scanner_owner_native:
            result["command"] += " --include-material-scanner-owner-native"
        if args.include_material_scanner_supervisor_native:
            result["command"] += " --include-material-scanner-supervisor-native"
        if args.include_material_worker_cli_native:
            result["command"] += " --include-material-worker-cli-native"
        result["scope"] = (
            "仅037运维实例head/审计/outbox原子协议与注入进程拒发布；"
            "不代表真实Windows Job启停、正式应用生命周期或多进程扫描验收"
        )
        if args.include_material_scanner_owner_native:
            result["scope"] = (
                "仅已审核Windows固定源/自有UUID目录/19311两轮Job启停和真实PNG/审计拒发布；"
                "原7492/19310受保护，不代表正式应用生命周期、多进程或全素材验收"
            )
        if args.include_material_scanner_supervisor_native:
            result["scope"] = (
                "仅显式单Worker监督器/037审计/原生19311实例/真实PNG队列及030/034证明；"
                "不改私有env或原7492/19310，不代表常驻driver、API跨进程候选或全素材验收"
            )
        if args.include_material_worker_cli_native:
            result["scope"] = (
                "仅显式CLI真实自有Python/Job、disabled零DB、PNG队列证明、进程锁争用及有限serve；"
                "不改私有env或原7492/19310，不代表外部信号优雅退出、跨主机或全素材验收"
            )
    if args.task_event_stream_only:
        result["command"] += " --task-event-stream-only"
        if args.include_task_event_cookie:
            result["command"] += " --include-task-event-cookie"
        if args.include_task_event_boundaries:
            result["command"] += " --include-task-event-boundaries"
        if args.include_task_event_integrity:
            result["command"] += " --include-task-event-integrity"
        result["scope"] = (
            "仅036真实SQL/HTTP/SSE、授权与受控七天时间注入；"
            "不代表生产IdP、自然慢TCP、跨副本限流、生产任务执行或全产品验收"
        )
    if args.material_scanner_configuration_only:
        result["command"] += " --material-scanner-configuration-only"
        if args.include_material_scanner_configuration_scope:
            result["command"] += " --include-material-scanner-configuration-scope"
        if args.include_launch_allocation_references:
            result["command"] += " --include-launch-allocation-references"
        if args.include_launch_execution_material_references:
            result["command"] += " --include-launch-execution-material-references"
        result["scope"] = (
            "仅034租户配置真实HTTP/SQL与固定本机实例PNG Worker；"
            "不代表生产受控启动器、多进程注册表、外部存储或全素材验收"
        )
        if args.include_launch_allocation_references:
            result["scope"] += "；附真实C扫描/分配引用桥，平台兼容仅SQL隔离夹具"
        if args.include_launch_execution_material_references:
            result["scope"] += "；附真实C扫描/EXECUTION引用及原202，其他能力仍隔离样本，无平台发送"
    if args.scope_create_profile_only:
        result["command"] += " --scope-create-profile-only"
        result["scope"] = "仅五万合成账户、原10秒创建及250页诊断；零日事实，不代表并发容量通过"
    if args.rules_only:
        result["command"] += " --rules-only"
        result["scope"] = (
            "仅原规则定义16组实际SQL/HTTP/六动作；技术profile来源，无生产模拟、启用或调度"
        )
        if args.include_rule_editor:
            result["command"] += " --include-rule-editor"
            result["scope"] += "；附真实编辑归属/配置候选，账户选择仍待接线"
        if args.include_rule_editor_scopes:
            result["command"] += " --include-rule-editor-scopes"
            result["scope"] += "；附061专属规则范围十组，非原五万范围容量验收"
        if args.include_rule_scope_consumer:
            result["command"] += " --include-rule-scope-consumer"
            result["scope"] += "；附新RULE实际消费与首次绑定八组"
        if args.include_rule_editor_definition:
            result["command"] += " --include-rule-editor-definition"
            result["scope"] += "；附edit-only完整定义与历史范围元数据七组"
        if args.include_rule_schedule_preview:
            result["command"] += " --include-rule-schedule-preview"
            result["scope"] += "；附未来五次运行只读技术预览七组，非正式调度"
        if args.rules_internal_browser:
            result["command"] += " --rules-internal-browser"
        if args.include_rule_scope_options:
            result["command"] += " --include-rule-scope-options"
            result["scope"] += "；附操作者/户商双范围真实候选，非指派权限或目录容量验收"
        if args.include_rule_simulation_schema:
            result["command"] += " --include-rule-simulation-schema"
            result["scope"] += "；显式加载未采用063候选SQL技术护栏，非模拟成功/启用"
        if args.include_rule_definition_boundaries:
            result["command"] += " --include-rule-definition-boundaries"
            result["scope"] += "；附原规则字段边界与原八表完整行不变，不代表所有规则功能"
        if args.include_rule_simulation_access:
            result["command"] += " --include-rule-simulation-access"
            result["scope"] += (
                "；附1001账户有界授权/根及真实事务技术专项，非指标issuer或模拟业务验收"
            )
        if args.include_rule_simulation_calendar:
            result["command"] += " --include-rule-simulation-calendar"
            result["scope"] += "；附1001账户四窗口/分批日历和单事务SQL时刻，非事实完整证明"
    if args.execution_candidate_only:
        result["command"] += " --execution-candidate-only"
        result["scope"] = (
            "仅执行候选内部只读目录/原202完整图/四档keyset及隔离SQL损坏拒绝与恢复；"
            "没有生产issuer/claim/发送，不是十万节点容量或任务全功能验收"
        )
    if args.execution_recovery_scanner_only:
        result["command"] += " --execution-recovery-scanner-only"
        result["scope"] = (
            "仅054恢复扫描原始分页/三桶/CAS/取消及SQL索引；技术维护与事实provider，"
            "没有生产issuer/CLI/调度/广告发送，不是大规模事故恢复验收"
        )
        if args.include_execution_recovery_service:
            result["command"] += " --include-execution-recovery-service"
            result["scope"] += "；附显式once/serve生命周期及真实停止/1205，未接生产调度"
    if args.identity_summary_only:
        result["command"] += " --identity-summary-only"
        result["scope"] = (
            "仅055完整身份摘要封印/独占RC/真实SQL护栏；来源为隔离技术样本，"
            "非生产Meta发行或真实平台验收"
        )
        if args.include_identity_summary_capacity:
            result["command"] += " --include-identity-summary-capacity"
            result["scope"] += "；显式200账户/百万原资源完整链路装载、真实200行/P95/执行计划"
        if args.include_identity_summary_profile:
            result["command"] += " --include-identity-summary-profile"
            result["scope"] += "；200账户各1资源CPU诊断，不是容量通过"
    if args.metric_query_result_only:
        result["command"] += " --metric-query-result-only"
        result["scope"] = (
            "仅内部指标结果构建/真实SQL/原CID取消清理；独立SQL技术来源，"
            "不是生产发行、公开Metrics API或容量验收"
        )
        if args.include_metrics_browser_fixture:
            result["command"] += " --include-metrics-browser-fixture"
            result["scope"] += "；独立SQL来源公开200/分页/币种/幂等，非生产发行"
        if args.include_metric_query_http:
            result["command"] += " --include-metric-query-http"
            result["scope"] += "；附公开默认未发行503及monitor独立CSRF/权限实测"
    if args.metric_query_read_only:
        result["command"] += " --metric-query-read-only"
        result["scope"] = (
            "仅048/049窄QueryStore真实SQL读与当前范围；独立预登记来源为SQL技术样本，"
            "没有生产发行、Metrics结果构建、HTTP查询/聚合/容量验收；未重跑旧scope13"
        )
    if args.identity_publication_only:
        result["command"] += " --identity-publication-only"
        result["scope"] = (
            "仅053完整身份发布/原GET与精确来源CAS；独立隔离能力发行技术样本，"
            "非真实Meta权威、列表摘要、浏览器或广告执行验收"
        )
    if args.include_launch_identity_drafts:
        result["command"] += " --include-launch-identity-drafts"
        result["scope"] += "；含草稿身份当前发行引用闭环，无真实Meta请求或广告写入"
    if args.include_identity_inventory_boundaries:
        result["command"] += " --include-identity-inventory-boundaries"
        result["scope"] += "；附目标真实0/5000库存与5001拒绝全表不变，非Meta或500账户容量"
    if args.metrics_scope_only:
        result["command"] += " --metrics-scope-only"
        result["scope"] = (
            "仅monitor.read当前授权消费原501/零账户范围，SQL账户技术样本；没有Metrics接口/事实/聚合/容量验收"
        )
        if args.include_metrics_expected_manifest:
            result["command"] += " --include-metrics-expected-manifest"
            result["scope"] += "；附056预期根/计数CHECK与跨代次不可变SQL护栏"
        if args.include_metric_fact_schema:
            result["command"] += " --include-metric-fact-schema"
            result["scope"] += (
                "；附048/049父树FK/不可变/最新cell技术SQL；非真实发行、QueryStore或容量"
            )
    if args.meta_observation_registry_only:
        result["command"] += " --meta-observation-registry-only"
        result["scope"] = (
            "仅045真实SQL原始观察登记/当前权限/CAS/幂等；受控Graph协议，非真实Meta来源或执行授权"
        )
        if args.include_meta_identity_facts:
            result["command"] += " --include-meta-identity-facts"
            result["scope"] += (
                "；附主体/资源白名单事实及配置/me精确绑定，无023发布、身份能力或执行权威"
            )
        if args.include_meta_receipt_bounds:
            result["command"] += " --include-meta-receipt-bounds"
            result["scope"] += "；附051真实回执边界/精确3819/无警告和回滚，非新来源或平台授权"
    if args.execution_lease_only:
        result["command"] += " --execution-lease-only"
        result["scope"] = (
            "仅046真实SQL精确尝试/租约/事实护栏；原execute隔离202，不领取、不发送、不运行Worker"
        )
        if args.include_execution_lease_store:
            result["command"] += " --include-execution-lease-store"
            result["scope"] += "；附显式技术authority只读完整事实，非生产可信provider或状态恢复提交"
        if args.include_execution_fact_append:
            result["command"] += " --include-execution-fact-append"
            result["scope"] += (
                "；附050原精度事实追加、重放/旧栅栏/并发/回滚，不提交当前状态或真实广告写入"
            )
        if args.include_execution_recovery:
            result["command"] += " --include-execution-recovery"
            result["scope"] += (
                "；附052原恢复边CAS/决策账本/Task与SSE；仅隔离authority，无发送或Worker"
            )
    if args.task_core_only:
        result["command"] += " --task-core-only"
        if args.include_task_core_capacity:
            result["command"] += " --include-task-core-capacity"
        result["scope"] = (
            "仅033原任务完整持久manifest、授权只读及可选十万节点容量；"
            "ISOLATED_TEST，不代表生产预检、平台发送、SSE或任务控制验收"
        )
        if args.include_launch_plan_source:
            result["command"] += " --include-launch-plan-source"
            result["scope"] += "；附真实配置源/CAS读取、索引/锁专项，SQL状态夹具不代表原状态接口"
    if args.launch_allocation_runtime_only:
        result["command"] += " --launch-allocation-runtime-only"
        result["scope"] = (
            "仅032真实SQL队列/claim/原子发布及容量；ISOLATED_TEST provider，"
            "不是HTTP公开接收、C活跃素材引用或真实平台授权"
        )
    if args.account_scope_visibility_plan_only:
        result["command"] += " --account-scope-visibility-plan-only"
        result["scope"] = "仅三角色五万成员反连接及同宽临时表候选计划；不改生产索引或权限复核"
    if args.material_runtime_only:
        result["command"] += " --material-runtime-only"
        result["scope"] = "仅独立初始化与真实运行证明入库/Worker18组；不代表完整后台回归"
    cases = []
    account_cookie_cases = []
    if args.include_account_read_cookie:
        from account_read_cookie_checks import ACCOUNT_READ_COOKIE_CASES

        account_cookie_cases = list(ACCOUNT_READ_COOKIE_CASES)
    planned = [
        "pythonRealMysqlRedisReadiness",
        "pythonBusinessDirectorySchemaAndUnknownHistory",
        "pythonRealJsonPasswordLogin",
        "pythonCurrentUserSanitized",
        "pythonOriginalDynamicMenus",
        *USER_CASES,
        *NATIVE_ROLE_READ_CASES,
        *NATIVE_WRITE_CONTRACT_CASES,
        *NATIVE_ROLE_REFERENCE_CASES,
        *NATIVE_BULK_LIFECYCLE_CASES,
        *BROWSER_SESSION_CASES,
        *AUTHORIZATION_STORE_CASES,
        *COOKIE_HTTP_CASES,
        *account_cookie_cases,
        *OIDC_CALLBACK_CASES,
        *NATIVE_USER_CHANGE_CASES,
        *TEAM_CASES,
        *IDENTITY_CAPACITY_CASES,
        *ROLE_CASES,
        "pythonConfigurationMetadataContract",
        "pythonConfigurationMetadataRejectsIdentityAndPreservesErrorContract",
        "pythonConfigurationMetadataRevocationIsImmediate",
        "pythonConfigurationCreateEncryptsAndIdempotentReplay",
        "pythonConfigurationUpdateCasAndClearRequiredSecret",
        "pythonConfigurationAuditFailureRollsBackWholeWrite",
        "pythonConfigurationHistoryKeysetAndNoSecretValues",
        "pythonConfigurationOutboxFailureRollsBackAuditAndConfig",
        "pythonConfigurationRoleUnionCrossTenantAndIdentityRevocation",
        "pythonNativeUserStateChangeParticipatesInDirectoryTransaction",
        "pythonNativeDisabledSessionCannotResurrectOnReenable",
        "pythonNativeUserStateRevokedActorCannotWriteAfterConcurrentTeamChange",
        *ROLE_GUARD_CASES,
        "pythonNativeAdminCannotCrossBusinessTenantViaOriginalUserMenu",
        "pythonNativeProfileOnlyEditCannotCrossBusinessTenant",
        "pythonNativeReservedLookingUsernameCannotBypassTenantGuard",
        "pythonNativeRoleAssignmentCannotStripBootstrapAdministrator",
        "pythonConfigurationConcurrentSameKeyAndRevisionCas",
        "pythonConfigurationReadOnlyProbeCasAuditAndFailureRollback",
        "pythonConfigurationProbeFourProvidersAndUnsupportedSections",
        "pythonAiStrategyProviderReferenceVisibilityAndAvailability",
        "pythonProbeInFlightRevocationRejectsResult",
        "pythonProbeInFlightUpdateRejectsStaleResult",
        "pythonProbeInFlightSessionEpochRejectsReenabledActor",
        "pythonNativeSelfProfileRemainsUsableAfterSessionRenewal",
        "pythonLogoutRevokesSameToken",
    ]
    planned[-1:-1] = USER_CREATE_CASES
    planned[-1:-1] = USER_UPDATE_CASES
    planned[-1:-1] = NATIVE_USER_ROLE_CASES
    planned[-1:-1] = TEAM_SESSION_CASES
    planned[-1:-1] = NATIVE_DIRECTORY_CASES
    planned[-1:-1] = INVITATION_CASES
    planned[-1:-1] = INVITATION_ACTIVATION_CASES
    planned[-1:-1] = DELIVERY_CASES
    planned[-1:-1] = CLI_CASES
    if args.migration_through >= 11:
        planned[-1:-1] = REFERENCE_CHANNEL_CASES
        planned[-1:-1] = REFERENCE_CHANNEL_SCOPE_CASES
    if args.include_materials:
        planned[-1:-1] = MATERIAL_CASES
    if args.include_accounts:
        planned[-1:-1] = ACCOUNT_IMPORT_CASES
    if args.include_account_worker:
        from account_worker_checks import CASES as ACCOUNT_WORKER_CASES
        from account_worker_checks import run_account_worker_checks

        planned[-1:-1] = ACCOUNT_WORKER_CASES
    if args.include_account_details:
        from account_details_checks import CASES as ACCOUNT_DETAILS_CASES
        from account_details_checks import run_account_details_checks

        planned[-1:-1] = ACCOUNT_DETAILS_CASES
    if args.include_channel_scope:
        from channel_scope_matrix_checks import (
            CHANNEL_SCOPE_MATRIX_CASES,
            run_channel_scope_matrix_checks,
        )

        planned[-1:-1] = CHANNEL_SCOPE_MATRIX_CASES
    if args.include_material_video:
        from material_video_checks import MATERIAL_VIDEO_CASES, run_material_video_checks

        planned[-1:-1] = MATERIAL_VIDEO_CASES
    if args.browser_only:
        planned = planned[:5] + ["pythonLogoutRevokesSameToken"]
    if args.channel_scope_only:
        planned = (
            planned[:5] + USER_CASES + CHANNEL_SCOPE_MATRIX_CASES + ["pythonLogoutRevokesSameToken"]
        )
    if args.browser:
        planned.insert(-1, browser_case)
        result["command"] += " --browser" + (
            f" --browser-module {args.browser_module}" if args.browser_module != "all" else ""
        )
    if args.account_details_only:
        planned = (
            planned[:5] + USER_CASES + ACCOUNT_DETAILS_CASES + ["pythonLogoutRevokesSameToken"]
        )
    if args.material_only:
        planned = (
            planned[:5]
            + (USER_CASES if args.include_material_taxonomy_scope else [])
            + MATERIAL_CASES
        )
        if args.include_material_video:
            planned += MATERIAL_VIDEO_CASES
        planned += ["pythonLogoutRevokesSameToken"]
    if args.include_material_taxonomy:
        from material_schema_checks import MATERIAL_SCHEMA_CASES, run_material_schema_checks
        from material_taxonomy_checks import (
            MATERIAL_TAXONOMY_MIGRATION_CASES,
            run_material_taxonomy_migration_checks,
        )
        from material_taxonomy_query_checks import (
            MATERIAL_TAXONOMY_QUERY_CASES,
            run_material_taxonomy_query_checks,
        )

        planned[-1:-1] = (
            MATERIAL_TAXONOMY_MIGRATION_CASES
            + MATERIAL_TAXONOMY_QUERY_CASES
            + MATERIAL_SCHEMA_CASES
        )
    if args.include_vendor_alias:
        from vendor_alias_checks import VENDOR_ALIAS_CASES, run_vendor_alias_checks

        if args.vendor_alias_only:
            planned = (
                planned[:5] + USER_CASES + VENDOR_ALIAS_CASES + ["pythonLogoutRevokesSameToken"]
            )
        else:
            planned[-1:-1] = VENDOR_ALIAS_CASES
    if args.environment_live_only:
        from environment_live_checks import ENVIRONMENT_LIVE_CASES, run_environment_live_checks

        planned = (
            planned[:5] + USER_CASES + ENVIRONMENT_LIVE_CASES + ["pythonLogoutRevokesSameToken"]
        )
    if args.include_meta_connection_checks:
        from meta_connection_checks import CASES as META_CONNECTION_CASES
        planned += META_CONNECTION_CASES
    if args.include_meta_pipeline_checks:
        from meta_pipeline_checks import PIPELINE_CASES
        planned += list(PIPELINE_CASES)
    if args.environment_registry_only:
        from environment_registry_checks import (
            ENVIRONMENT_REGISTRY_CASES,
            run_environment_registry_checks,
        )
        from profile_binding_checks import PROFILE_BINDING_CASES, run_profile_binding_checks

        planned = (
            planned[:5]
            + USER_CASES
            + ENVIRONMENT_REGISTRY_CASES
            + PROFILE_BINDING_CASES
            + ["pythonLogoutRevokesSameToken"]
        )
    if args.include_material_taxonomy_scope or args.material_taxonomy_metadata_only:
        from material_taxonomy_scope_checks import (
            MATERIAL_TAXONOMY_SCOPE_CASES,
            run_material_taxonomy_scope_checks,
        )

        if args.material_taxonomy_scope_only or args.material_taxonomy_metadata_only:
            planned = (
                planned[:5]
                + USER_CASES
                + MATERIAL_TAXONOMY_SCOPE_CASES
                + ["pythonLogoutRevokesSameToken"]
            )
        else:
            planned[-1:-1] = MATERIAL_TAXONOMY_SCOPE_CASES
    if args.include_material_taxonomy_capabilities:
        from material_taxonomy_capability_checks import (
            MATERIAL_TAXONOMY_CAPABILITY_CASES,
            run_material_taxonomy_capability_checks,
        )

        planned[-1:-1] = MATERIAL_TAXONOMY_CAPABILITY_CASES
    if args.include_channel_fields:
        from channel_field_contract_checks import (
            CHANNEL_FIELD_CONTRACT_CASES,
            run_channel_field_contract_checks,
        )

        planned[-1:-1] = CHANNEL_FIELD_CONTRACT_CASES
    if args.include_material_lifecycle:
        from material_lifecycle_checks import (
            MATERIAL_LIFECYCLE_CASES,
            run_material_lifecycle_checks,
        )

        if args.material_lifecycle_only:
            planned = planned[:5] + MATERIAL_LIFECYCLE_CASES + ["pythonLogoutRevokesSameToken"]
        else:
            planned[-1:-1] = MATERIAL_LIFECYCLE_CASES
    if args.include_material_lifecycle_recovery:
        from material_lifecycle_recovery_checks import (
            MATERIAL_LIFECYCLE_RECOVERY_CASES,
            run_material_lifecycle_recovery_checks,
        )

        planned[-1:-1] = MATERIAL_LIFECYCLE_RECOVERY_CASES
    if args.include_channel_owners:
        from channel_owners_500_checks import (
            CHANNEL_OWNERS_500_CASES,
            run_channel_owners_500_checks,
        )

        if args.channel_owners_only:
            planned = (
                planned[:5]
                + USER_CASES
                + CHANNEL_OWNERS_500_CASES
                + ["pythonLogoutRevokesSameToken"]
            )
        else:
            planned[-1:-1] = CHANNEL_OWNERS_500_CASES
    if args.reference_channel_only:
        planned = planned[:5] + USER_CASES + REFERENCE_CHANNEL_CASES + REFERENCE_CHANNEL_SCOPE_CASES
        if args.include_channel_scope:
            planned += CHANNEL_SCOPE_MATRIX_CASES
        if args.include_channel_fields:
            planned += CHANNEL_FIELD_CONTRACT_CASES
        if args.include_channel_owners:
            planned += CHANNEL_OWNERS_500_CASES
        if args.browser:
            planned += [browser_case]
        if args.include_reference_channel_capacity:
            from reference_channel_capacity_checks import (
                REFERENCE_CHANNEL_CAPACITY_CASES,
                run_reference_channel_capacity_checks,
            )

            planned += list(REFERENCE_CHANNEL_CAPACITY_CASES)
        planned += ["pythonLogoutRevokesSameToken"]
    if args.include_material_lifecycle_races:
        from material_lifecycle_http_race_checks import (
            MATERIAL_LIFECYCLE_HTTP_RACE_CASES,
            run_material_lifecycle_http_race_checks,
        )
        from material_lifecycle_race_checks import (
            MATERIAL_LIFECYCLE_RACE_CASES,
            run_material_lifecycle_race_checks,
        )

        planned[-1:-1] = MATERIAL_LIFECYCLE_RACE_CASES + MATERIAL_LIFECYCLE_HTTP_RACE_CASES
    if args.material_only and args.browser:
        planned.insert(-1, browser_case)
    if args.account_details_only and args.browser:
        planned.insert(-1, browser_case)
    if args.include_account_alias_snapshots:
        from account_alias_fixture import prepare_account_alias_fixture
        from account_alias_snapshot_checks import CASES as ACCOUNT_ALIAS_CASES
        from account_alias_snapshot_checks import run_account_alias_snapshot_checks

        if args.account_details_only:
            planned[-1:-1] = ACCOUNT_IMPORT_CASES + ACCOUNT_WORKER_CASES
        planned[-1:-1] = ACCOUNT_ALIAS_CASES
    if args.include_account_identities:
        from account_identities_checks import CASES as ACCOUNT_IDENTITIES_CASES
        from account_identities_checks import run_account_identities_checks

        planned[-1:-1] = ACCOUNT_IDENTITIES_CASES
        from identity_publication_checks import (
            IDENTITY_INVENTORY_BOUNDARY_CASES,
            IDENTITY_PUBLICATION_CASES,
            run_identity_publication_checks,
        )

        planned[-1:-1] = list(IDENTITY_PUBLICATION_CASES) + list(IDENTITY_INVENTORY_BOUNDARY_CASES)
    if args.material_references_only:
        from material_reference_checks import (
            MATERIAL_REFERENCE_CASES,
            run_material_reference_checks,
        )
        from material_reference_scope_checks import (
            MATERIAL_REFERENCE_SCOPE_CASES,
            run_material_reference_scope_checks,
        )

        planned = (
            planned[:5]
            + USER_CASES
            + MATERIAL_REFERENCE_CASES
            + MATERIAL_REFERENCE_SCOPE_CASES
            + ["pythonLogoutRevokesSameToken"]
        )
    if fast_mode and args.include_configuration_metadata:
        planned[-1:-1] = CONFIGURATION_METADATA_CASES
    if args.include_launch_naming or args.launch_naming_only:
        from launch_naming_checks import LAUNCH_NAMING_CASES, run_launch_naming_checks

        if args.launch_naming_only:
            planned = (
                planned[:5] + USER_CASES + LAUNCH_NAMING_CASES + ["pythonLogoutRevokesSameToken"]
            )
            if args.include_configuration_metadata:
                planned[-1:-1] = CONFIGURATION_METADATA_CASES
        else:
            planned[-1:-1] = LAUNCH_NAMING_CASES
    if args.include_account_assignment_options:
        from account_assignment_options_checks import CASES as ACCOUNT_ASSIGNMENT_OPTION_CASES
        from account_assignment_options_checks import run_account_assignment_options_checks

        planned[-1:-1] = ACCOUNT_ASSIGNMENT_OPTION_CASES
    if args.include_account_projection:
        from account_projection_checks import CASES as ACCOUNT_PROJECTION_CASES
        from account_projection_checks import run_account_projection_checks

        planned[-1:-1] = ACCOUNT_PROJECTION_CASES
    if args.include_account_actions:
        from account_action_fixture import prepare_account_action_fixture
        from account_actions_checks import CASES as ACCOUNT_ACTION_CASES
        from account_actions_checks import run_account_actions_checks

        planned[-1:-1] = ACCOUNT_ACTION_CASES
    if args.include_account_command_diagnostics:
        from account_command_checks import CASES as ACCOUNT_COMMAND_CASES
        from account_command_checks import run_account_command_checks

        planned[-1:-1] = ACCOUNT_COMMAND_CASES
    if args.include_account_sync:
        from account_actions_sync_checks import CASES as ACCOUNT_SYNC_CASES
        from account_actions_sync_checks import run_account_sync_checks

        planned[-1:-1] = ACCOUNT_SYNC_CASES
    if args.include_account_capacity:
        from account_capacity_checks import CASES as ACCOUNT_CAPACITY_CASES
        from account_capacity_checks import SCOPE_CAPACITY_CASES, run_account_capacity_checks

        planned[-1:-1] = ACCOUNT_CAPACITY_CASES
        if args.include_account_scopes:
            planned[-1:-1] = SCOPE_CAPACITY_CASES
    if args.material_scanner_manifest:
        planned[-1:-1] = (
            []
            if args.browser_only
            else MATERIAL_ANTIVIRUS_ENGINE_CASES + MATERIAL_ANTIVIRUS_WORKER_CASES
        )
    if args.include_account_scopes:
        from account_readonly_fixture import prepare_account_readonly_fixture
        from account_scope_checks import CASES as ACCOUNT_SCOPE_CASES
        from account_scope_checks import run_account_scope_checks

        planned[-1:-1] = ACCOUNT_SCOPE_CASES
    if args.include_scope_visibility_verdict:
        from scope_visibility_verdict_checks import (
            SCOPE_VISIBILITY_VERDICT_CASES,
            run_scope_visibility_verdict_checks,
        )

        planned[-1:-1] = SCOPE_VISIBILITY_VERDICT_CASES
    if args.include_launch_drafts:
        from launch_draft_template_checks import (
            LAUNCH_DRAFT_TEMPLATE_CASES,
            run_launch_draft_template_checks,
        )

        if args.launch_drafts_only:
            planned = (
                planned[:5]
                + USER_CASES
                + LAUNCH_DRAFT_TEMPLATE_CASES
                + ["pythonLogoutRevokesSameToken"]
            )
            if args.include_configuration_metadata:
                planned[-1:-1] = CONFIGURATION_METADATA_CASES
        else:
            planned[-1:-1] = LAUNCH_DRAFT_TEMPLATE_CASES
    if args.include_material_security:
        from material_security_checks import MATERIAL_SECURITY_CASES, run_material_security_checks

        if not args.browser_only:
            planned[-1:-1] = MATERIAL_SECURITY_CASES
    if args.include_material_runtime_store:
        from material_runtime_store_checks import (
            MATERIAL_RUNTIME_STORE_CASES,
            run_material_runtime_store_checks,
        )

        planned[-1:-1] = MATERIAL_RUNTIME_STORE_CASES
    if args.include_material_runtime_worker:
        from material_runtime_worker_checks import (
            MATERIAL_RUNTIME_WORKER_CASES,
            run_material_runtime_worker_checks,
        )

        planned[-1:-1] = MATERIAL_RUNTIME_WORKER_CASES
    if args.include_launch_scope_consumption:
        from launch_scope_consumption_checks import (
            LAUNCH_SCOPE_CONSUMPTION_CASES,
            run_launch_scope_consumption_checks,
        )

        planned[-1:-1] = LAUNCH_SCOPE_CONSUMPTION_CASES
    if args.include_material_security_scope:
        from material_security_scope_checks import (
            MATERIAL_SECURITY_SCOPE_CASES,
            run_material_security_scope_checks,
        )

        planned[-1:-1] = MATERIAL_SECURITY_SCOPE_CASES
    if args.include_template_recipients:
        from template_recipient_checks import (
            TEMPLATE_RECIPIENT_CASES,
            run_template_recipient_checks,
        )

        planned[-1:-1] = TEMPLATE_RECIPIENT_CASES
    if args.template_recipients_only:
        planned = (
            planned[:5] + USER_CASES + TEMPLATE_RECIPIENT_CASES + ["pythonLogoutRevokesSameToken"]
        )
        if args.include_configuration_metadata:
            planned[-1:-1] = CONFIGURATION_METADATA_CASES
    if args.include_material_infected_memory_worker:
        from material_antivirus_memory_worker_checks import (
            MATERIAL_ANTIVIRUS_MEMORY_WORKER_CASES,
            run_material_antivirus_memory_worker_checks,
        )

        planned[-1:-1] = MATERIAL_ANTIVIRUS_MEMORY_WORKER_CASES
    if args.material_runtime_only:
        planned = (
            planned[:5]
            + MATERIAL_RUNTIME_STORE_CASES
            + MATERIAL_RUNTIME_WORKER_CASES
            + ["pythonLogoutRevokesSameToken"]
        )
        if args.include_configuration_metadata:
            planned[-1:-1] = CONFIGURATION_METADATA_CASES
    if args.account_scope_visibility_plan_only:
        from account_scope_visibility_plan_checks import CASES as SCOPE_VISIBILITY_PLAN_CASES
        from account_scope_visibility_plan_checks import run_account_scope_visibility_plan_checks

        planned = planned[:5] + SCOPE_VISIBILITY_PLAN_CASES + ["pythonLogoutRevokesSameToken"]
        if args.include_configuration_metadata:
            planned[-1:-1] = CONFIGURATION_METADATA_CASES
    if args.launch_validation_only:
        from launch_validation_checks import (
            LAUNCH_VALIDATION_BASELINE_CASES,
            LAUNCH_VALIDATION_CASES,
            run_launch_validation_checks,
        )

        planned = (
            planned[:5]
            + (
                LAUNCH_VALIDATION_CASES
                if args.include_launch_validation_provider
                else LAUNCH_VALIDATION_BASELINE_CASES
            )
            + ["pythonLogoutRevokesSameToken"]
        )
        if args.include_launch_allocation_http:
            from launch_allocation_http_checks import (
                LAUNCH_ALLOCATION_HTTP_CASES,
                run_launch_allocation_http_checks,
            )

            planned[-1:-1] = LAUNCH_ALLOCATION_HTTP_CASES
        if args.include_launch_allocation_http_provider:
            from launch_allocation_http_provider_checks import (
                LAUNCH_ALLOCATION_HTTP_PROVIDER_CASES,
                run_launch_allocation_http_provider_checks,
            )

            planned[-1:-1] = LAUNCH_ALLOCATION_HTTP_PROVIDER_CASES
        if args.include_launch_execution_http:
            from launch_execution_http_checks import (
                EXECUTION_HTTP_CASES,
                run_launch_execution_http_checks,
            )

            planned[-1:-1] = EXECUTION_HTTP_CASES
        if args.include_launch_execution_provider:
            from launch_execution_checks import EXECUTION_CASES, run_launch_execution_checks

            planned[-1:-1] = EXECUTION_CASES
        if args.include_metric_profile_registry:
            from metric_profile_registry_checks import (
                METRIC_PROFILE_REGISTRY_CASES,
                run_metric_profile_registry_checks,
            )

            planned[-1:-1] = METRIC_PROFILE_REGISTRY_CASES
        if args.include_metric_profile_references:
            from metric_profile_reference_checks import (
                METRIC_PROFILE_REFERENCE_CASES,
                run_metric_profile_reference_checks,
            )

            planned[-1:-1] = METRIC_PROFILE_REFERENCE_CASES
        if args.include_template_current_scope:
            from template_current_scope_checks import (
                TEMPLATE_CURRENT_SCOPE_CASES,
                run_template_current_scope_checks,
            )

            planned[-1:-1] = TEMPLATE_CURRENT_SCOPE_CASES
            from launch_replay_concurrency_checks import (
                LAUNCH_REPLAY_CONCURRENCY_CASES,
                run_launch_replay_concurrency_checks,
            )

            planned[-1:-1] = LAUNCH_REPLAY_CONCURRENCY_CASES
        if args.include_template_metric_references:
            from template_metric_reference_checks import (
                TEMPLATE_METRIC_REFERENCE_CASES,
                run_template_metric_reference_checks,
            )

            planned[-1:-1] = TEMPLATE_METRIC_REFERENCE_CASES
        if args.include_metric_profile_query:
            from metric_profile_query_checks import (
                METRIC_PROFILE_QUERY_CASES,
                run_metric_profile_query_checks,
            )

            planned[-1:-1] = METRIC_PROFILE_QUERY_CASES
        if args.include_launch_execution_guards:
            from launch_execution_guard_checks import (
                LAUNCH_EXECUTION_GUARD_CASES,
                run_launch_execution_guard_checks,
            )

            planned[-1:-1] = LAUNCH_EXECUTION_GUARD_CASES
        if args.include_configuration_metadata:
            planned[-1:-1] = CONFIGURATION_METADATA_CASES
    if args.launch_allocation_runtime_only:
        from launch_allocation_runtime_checks import (
            LAUNCH_ALLOCATION_RUNTIME_CASES,
            run_launch_allocation_runtime_checks,
        )

        planned = planned[:5] + LAUNCH_ALLOCATION_RUNTIME_CASES + ["pythonLogoutRevokesSameToken"]
        if args.include_configuration_metadata:
            planned[-1:-1] = CONFIGURATION_METADATA_CASES
    if args.material_scanner_owner_store_only:
        from material_scanner_owner_store_checks import (
            MATERIAL_SCANNER_OWNER_STORE_CASES,
            run_material_scanner_owner_store_checks,
        )

        planned = (
            planned[:5] + MATERIAL_SCANNER_OWNER_STORE_CASES + ["pythonLogoutRevokesSameToken"]
        )
        if args.include_material_scanner_owner_native:
            from material_scanner_owner_native_checks import (
                MATERIAL_SCANNER_OWNER_NATIVE_CASES,
                run_material_scanner_owner_native_checks,
            )

            planned[-1:-1] = MATERIAL_SCANNER_OWNER_NATIVE_CASES
        if args.include_material_scanner_supervisor_native:
            from material_scanner_supervisor_checks import (
                MATERIAL_SCANNER_SUPERVISOR_CASES,
                run_material_scanner_supervisor_checks,
            )

            planned[-1:-1] = MATERIAL_SCANNER_SUPERVISOR_CASES
        if args.include_material_worker_cli_native:
            from material_worker_cli_checks import (
                MATERIAL_WORKER_CLI_CASES,
                run_material_worker_cli_checks,
            )

            planned[-1:-1] = MATERIAL_WORKER_CLI_CASES
        if args.include_configuration_metadata:
            planned[-1:-1] = CONFIGURATION_METADATA_CASES
    if args.task_event_stream_only:
        from task_event_stream_checks import TASK_EVENT_STREAM_CASES, run_task_event_stream_checks

        planned = planned[:5] + TASK_EVENT_STREAM_CASES + ["pythonLogoutRevokesSameToken"]
        if args.include_task_event_cookie:
            from task_event_cookie_checks import (
                TASK_EVENT_COOKIE_CASES,
                run_task_event_cookie_checks,
            )

            planned[-1:-1] = TASK_EVENT_COOKIE_CASES
        if args.include_task_event_boundaries:
            from task_event_boundary_checks import (
                TASK_EVENT_BOUNDARY_CASES,
                run_task_event_boundary_checks,
            )

            planned[-1:-1] = TASK_EVENT_BOUNDARY_CASES
        if args.include_task_event_integrity:
            from task_event_integrity_checks import (
                TASK_EVENT_INTEGRITY_CASES,
                run_task_event_integrity_checks,
            )

            planned[-1:-1] = TASK_EVENT_INTEGRITY_CASES
        if args.include_configuration_metadata:
            planned[-1:-1] = CONFIGURATION_METADATA_CASES
    if args.task_core_only:
        from task_core_checks import (
            TASK_CORE_CAPACITY_CASES,
            TASK_CORE_CASES,
            run_task_core_checks,
        )

        planned = planned[:5] + TASK_CORE_CASES + ["pythonLogoutRevokesSameToken"]
        if args.include_launch_plan_source:
            from launch_plan_source_checks import (
                LAUNCH_PLAN_SOURCE_CASES,
                run_launch_plan_source_checks,
            )

            planned[-1:-1] = LAUNCH_PLAN_SOURCE_CASES
        if args.include_task_core_capacity:
            planned[-1:-1] = TASK_CORE_CAPACITY_CASES
        if args.include_configuration_metadata:
            planned[-1:-1] = CONFIGURATION_METADATA_CASES
        if args.browser:
            planned.insert(-1, browser_case)
            if args.browser_module == "task-events":
                planned.insert(-1, "pythonTaskEventBrowserActualCommitAndPermissionRestoration")
    if args.identity_summary_only:
        from identity_publication_summary_checks import (
            IDENTITY_SUMMARY_CAPACITY_CASES,
            IDENTITY_SUMMARY_CASES,
            IDENTITY_SUMMARY_PROFILE_CASES,
            IDENTITY_SUMMARY_PUBLIC_CASES,
            run_identity_publication_summary_checks,
        )

        planned = (
            planned[:5]
            + list(IDENTITY_SUMMARY_CASES)
            + list(IDENTITY_SUMMARY_PUBLIC_CASES)
            + ["pythonLogoutRevokesSameToken"]
        )
        if args.browser:
            planned.insert(-1, browser_case)
        if args.include_identity_summary_capacity:
            planned[-1:-1] = list(IDENTITY_SUMMARY_CAPACITY_CASES)
        if args.include_identity_summary_profile:
            planned[-1:-1] = list(IDENTITY_SUMMARY_PROFILE_CASES)
    if args.execution_candidate_only:
        from launch_execution_candidate_checks import (
            EXECUTION_CANDIDATE_CASES,
            CandidateFixtureCleanupError,
            run_execution_candidate_checks,
        )

        planned = planned[:5] + list(EXECUTION_CANDIDATE_CASES) + ["pythonLogoutRevokesSameToken"]
    if args.execution_recovery_scanner_only:
        from launch_execution_recovery_scanner_checks import (
            SCANNER_CASES,
            SERVICE_CASES,
            run_execution_recovery_scanner_checks,
        )

        planned = planned[:5] + list(SCANNER_CASES) + ["pythonLogoutRevokesSameToken"]
        if args.include_execution_recovery_service:
            planned[-1:-1] = list(SERVICE_CASES)
    if args.metric_query_result_only:
        from metrics_query_result_checks import (
            METRIC_QUERY_RESULT_CASES,
            run_metrics_query_result_checks,
        )

        planned = planned[:5] + list(METRIC_QUERY_RESULT_CASES) + ["pythonLogoutRevokesSameToken"]
        if args.include_metric_query_http:
            from metrics_http_checks import METRIC_QUERY_HTTP_CASES, run_metrics_http_checks

            planned[-1:-1] = METRIC_QUERY_HTTP_CASES
        if args.include_metrics_browser_fixture:
            from metrics_public_fixture_checks import (
                METRICS_PUBLIC_FIXTURE_CASES,
                run_metrics_public_fixture_checks,
            )

            planned[-1:-1] = METRICS_PUBLIC_FIXTURE_CASES
        if args.browser:
            planned.insert(-1, browser_case)
    if args.scope_create_profile_only:
        from account_scope_profile_checks import (
            SCOPE_CREATE_PROFILE_CASES,
            run_scope_create_profile_checks,
        )

        planned = planned[:5] + list(SCOPE_CREATE_PROFILE_CASES) + ["pythonLogoutRevokesSameToken"]
    if args.rules_only:
        from rule_definition_checks import RULE_DEFINITION_CASES, run_rule_definition_checks

        planned = planned[:5] + list(RULE_DEFINITION_CASES) + ["pythonLogoutRevokesSameToken"]
        if args.include_rule_editor:
            from rule_editor_checks import RULE_EDITOR_CASES, run_rule_editor_checks

            planned[-1:-1] = RULE_EDITOR_CASES
        if args.include_rule_editor_scopes:
            from rule_editor_scope_checks import (
                RULE_EDITOR_SCOPE_CASES,
                run_rule_editor_scope_checks,
            )

            planned[-1:-1] = RULE_EDITOR_SCOPE_CASES
        if args.include_rule_scope_consumer:
            from rule_scope_consumer_checks import (
                RULE_SCOPE_CONSUMER_CASES,
                run_rule_scope_consumer_checks,
            )

            planned[-1:-1] = RULE_SCOPE_CONSUMER_CASES
        if args.include_rule_editor_definition:
            from rule_editor_definition_checks import (
                RULE_EDITOR_DEFINITION_CASES,
                run_rule_editor_definition_checks,
            )

            planned[-1:-1] = RULE_EDITOR_DEFINITION_CASES
        if args.include_rule_schedule_preview:
            from rule_schedule_preview_checks import (
                RULE_SCHEDULE_PREVIEW_CASES,
                run_rule_schedule_preview_checks,
            )

            planned[-1:-1] = RULE_SCHEDULE_PREVIEW_CASES
        if args.include_rule_scope_options:
            from rule_scope_options_checks import (
                RULE_SCOPE_OPTIONS_CASES,
                run_rule_scope_options_checks,
            )

            planned[-1:-1] = RULE_SCOPE_OPTIONS_CASES
        if args.include_rule_simulation_schema:
            from rule_simulation_schema_checks import (
                RULE_SIMULATION_SCHEMA_CASES,
                run_rule_simulation_schema_checks,
            )

            planned[-1:-1] = RULE_SIMULATION_SCHEMA_CASES
        if args.include_rule_definition_boundaries:
            from rule_definition_boundary_checks import (
                RULE_DEFINITION_BOUNDARY_CASES,
                run_rule_definition_boundary_checks,
            )

            planned[-1:-1] = RULE_DEFINITION_BOUNDARY_CASES
        if args.include_rule_simulation_access:
            from rule_simulation_access_checks import (
                RULE_SIMULATION_ACCESS_CASES,
                run_rule_simulation_access_checks,
            )

            planned[-1:-1] = RULE_SIMULATION_ACCESS_CASES
        if args.include_rule_simulation_calendar:
            from rule_simulation_calendar_checks import (
                RULE_SIMULATION_CALENDAR_CASES,
                run_rule_simulation_calendar_checks,
            )

            planned[-1:-1] = RULE_SIMULATION_CALENDAR_CASES
        if args.rules_definition_browser:
            from rules_definition_browser_fixture import (
                RULE_DEFINITION_BROWSER_CASE,
                prepare_rule_definition_browser,
            )

            planned = planned[:5] + [RULE_DEFINITION_BROWSER_CASE, "pythonLogoutRevokesSameToken"]
            result["command"] += " --rules-definition-flow"
            result["scope"] = (
                "最小真实规则定义图及原生登录/菜单，等待主线实际内置浏览器操作；"
                "不重跑既有规则故障/容量档，技术profile不是Meta来源或启用成功"
            )
            if args.include_rule_display_metadata:
                from rules_definition_flow_checks import (
                    RULES_DEFINITION_FLOW_CASES,
                    run_rules_definition_flow_checks,
                )

                planned[-1:-1] = RULES_DEFINITION_FLOW_CASES
                result["command"] += " --include-rule-display-metadata"
                result["scope"] += "；附原规则保存/编辑/归档回读及真实审计展示与当前权限"
            if args.include_rule_recovery_context:
                from rule_recovery_context_checks import (
                    RULE_RECOVERY_CONTEXT_CASES,
                    run_rule_recovery_context_checks,
                )

                planned[-1:-1] = RULE_RECOVERY_CONTEXT_CASES
                result["command"] += " --include-rule-recovery-context"
                result["scope"] += "；附原六动作真实主体和当前JWT/Cookie会话恢复上下文"
    if args.metric_query_read_only:
        from metrics_query_read_checks import (
            METRIC_QUERY_READ_CASES,
            run_metrics_query_read_checks,
        )

        planned = planned[:5] + list(METRIC_QUERY_READ_CASES) + ["pythonLogoutRevokesSameToken"]
    if args.identity_publication_only:
        from identity_publication_checks import (
            IDENTITY_PUBLICATION_CASES,
            run_identity_publication_checks,
        )

        planned = planned[:5] + list(IDENTITY_PUBLICATION_CASES) + ["pythonLogoutRevokesSameToken"]
        if args.include_launch_identity_drafts:
            from launch_identity_draft_checks import (
                LAUNCH_IDENTITY_DRAFT_CASES,
                LaunchIdentityDraftChecks,
            )

            planned[-1:-1] = LAUNCH_IDENTITY_DRAFT_CASES
        if args.include_identity_inventory_boundaries:
            from identity_publication_checks import IDENTITY_INVENTORY_BOUNDARY_CASES

            planned[-1:-1] = list(IDENTITY_INVENTORY_BOUNDARY_CASES)
        if args.browser:
            planned.insert(-1, browser_case)
    if args.metrics_scope_only:
        from metrics_scope_checks import METRIC_SCOPE_CASES, run_metric_scope_checks

        planned = planned[:5] + METRIC_SCOPE_CASES + ["pythonLogoutRevokesSameToken"]
        if args.include_metric_fact_schema:
            from metric_fact_schema_checks import (
                METRIC_FACT_SCHEMA_CASES,
                run_metric_fact_schema_checks,
            )

            planned[-1:-1] = list(METRIC_FACT_SCHEMA_CASES)
        if args.include_metrics_expected_manifest:
            from metrics_result_manifest_checks import (
                METRICS_EXPECTED_MANIFEST_CASES,
                run_metrics_expected_manifest_checks,
            )

            planned[-1:-1] = list(METRICS_EXPECTED_MANIFEST_CASES)
    if args.meta_observation_registry_only:
        from meta_observation_registry_checks import (
            META_OBSERVATION_REGISTRY_CASES,
            run_meta_observation_registry_checks,
        )

        planned = planned[:5] + META_OBSERVATION_REGISTRY_CASES + ["pythonLogoutRevokesSameToken"]
        if args.include_meta_identity_facts:
            from meta_observation_registry_checks import (
                IDENTITY_FACT_OBSERVATION_CASES,
                IDENTITY_PRINCIPAL_BINDING_CASES,
            )

            planned[-1:-1] = IDENTITY_FACT_OBSERVATION_CASES + IDENTITY_PRINCIPAL_BINDING_CASES
        if args.include_meta_receipt_bounds:
            from meta_receipt_bounds_checks import (
                META_RECEIPT_BOUNDS_CASES,
                run_meta_receipt_bounds_checks,
            )

            planned[-1:-1] = META_RECEIPT_BOUNDS_CASES
    if args.execution_lease_only:
        from launch_execution_lease_checks import EXECUTION_LEASE_CASES, run_execution_lease_checks

        planned = planned[:5] + EXECUTION_LEASE_CASES + ["pythonLogoutRevokesSameToken"]
        if args.include_execution_lease_store:
            from launch_execution_lease_store_checks import (
                EXECUTION_LEASE_STORE_CASES,
                run_execution_lease_store_checks,
            )

            planned[-1:-1] = EXECUTION_LEASE_STORE_CASES
            if args.include_execution_fact_append:
                from launch_execution_lease_store_checks import EXECUTION_FACT_APPEND_CASES

                planned[-1:-1] = EXECUTION_FACT_APPEND_CASES
            if args.include_execution_recovery:
                from launch_execution_recovery_checks import (
                    RECOVERY_COMMIT_CASES,
                    run_execution_recovery_checks,
                )

                planned[-1:-1] = RECOVERY_COMMIT_CASES
    if args.material_scanner_configuration_only:
        from material_scanner_configuration_checks import (
            MATERIAL_SCANNER_CONFIGURATION_CASES,
            run_material_scanner_configuration_checks,
        )

        planned = (
            planned[:5] + MATERIAL_SCANNER_CONFIGURATION_CASES + ["pythonLogoutRevokesSameToken"]
        )
        if args.include_launch_allocation_references:
            from launch_allocation_reference_checks import (
                LAUNCH_ALLOCATION_REFERENCE_CASES,
                run_launch_allocation_reference_checks,
            )

            planned[-1:-1] = USER_CASES + LAUNCH_ALLOCATION_REFERENCE_CASES
        if args.include_launch_execution_material_references:
            from launch_execution_material_bridge_checks import (
                EXECUTION_MATERIAL_BRIDGE_CASES,
                run_launch_execution_material_bridge_checks,
            )

            planned[-1:-1] = USER_CASES + EXECUTION_MATERIAL_BRIDGE_CASES
        if args.include_material_scanner_configuration_scope:
            from material_scanner_configuration_scope_checks import (
                MATERIAL_SCANNER_CONFIGURATION_SCOPE_CASES,
                run_material_scanner_configuration_scope_checks,
            )

            planned[-1:-1] = USER_CASES + MATERIAL_SCANNER_CONFIGURATION_SCOPE_CASES
        if args.include_configuration_metadata:
            planned[-1:-1] = CONFIGURATION_METADATA_CASES
        if args.browser:
            planned.insert(-1, browser_case)
    if args.browser and args.browser_module == "account-command":
        planned[-1:-1] = [
            "pythonAccountCommandBrowserIsolatedAdmissionFixture",
            "pythonAccountCommandBrowserAcceptedCommandsNeverClaimed",
        ]
    if args.browser_project:
        result["scope"] = result["scope"].replace(
            "指定三视口浏览器", "指定单视口浏览器诊断，非三视口验收"
        )
    if args.include_account_current_channel:
        from account_current_channel_checks import CASES as CHANNEL_CASES
        from account_current_channel_checks import run_checks as run_channel_checks

        planned[-1:-1] = CHANNEL_CASES
        result["command"] += " --include-account-current-channel"
        result["scope"] += "；附当前账户渠道真实写入与规则筛选（技术账户/profile）"
    cases = CheckedCases(planned)
    child = None
    idp = None
    browser_gateway = None
    material_browser_stop = None
    task_event_browser_control = None
    object_bundle = None
    object_bundle_path = None
    supervisor_cleanup_verified = False
    worker_cli_cleanup_verified = False
    launch_validation_control = None
    database = "orbit_py_it_" + uuid.uuid4().hex
    if (
        args.execution_candidate_only
        or args.include_material_worker_cli_native
        or args.include_material_scanner_supervisor_native
    ):
        # 仅记录本工具生成的非秘密资源ID；清理未证实时可精确定位，不能扫描后猜删除目标。
        result["isolated_fixture_database"] = database
    admin = None
    database_created = False
    log = tempfile.TemporaryFile(mode="w+b")
    try:
        with socket.socket() as guard:
            guard.bind(("127.0.0.1", PORT))
        admin = pymysql.connect(
            host="127.0.0.1",
            port=13306,
            user="root",
            password="",
            charset="utf8mb4",
            autocommit=True,
            client_flag=CLIENT.MULTI_STATEMENTS,
        )
        with admin.cursor() as cursor:
            cursor.execute("SELECT @@datadir")
            directory = str(cursor.fetchone()[0]).replace("\\", "/").rstrip("/")
            expected = str((ROOT.parent / ".runtime/mysql-it/data").resolve()).replace("\\", "/")
            assert directory.lower() == expected.lower(), "MySQL夹具目录不匹配"
            cursor.execute(
                f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs"
            )
            database_created = True
            cursor.execute(f"USE `{database}`")
            cursor.execute((FRAMEWORK / "sql/ruoyi-fastapi.sql").read_text(encoding="utf-8"))
            while cursor.nextset():
                pass
            migrations = selected_migrations
            result["fixture_migrations"] = [path.name for path in migrations]
            for migration in migrations:
                cursor.execute(migration.read_text(encoding="utf-8"))
                while cursor.nextset():
                    pass
            password = secrets.token_urlsafe(18)
            cursor.execute(
                "UPDATE sys_user SET password=%s WHERE user_id=1",
                (bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),),
            )
            cursor.execute(
                "UPDATE sys_config SET config_value='false' "
                "WHERE config_key='sys.account.captchaEnabled'"
            )
            cursor.execute("UPDATE sys_job SET status='1'")
        cache = redis.Redis(host="127.0.0.1", port=16379, db=15)
        assert cache.dbsize() == 0, "专属测试Redis空间非空，拒绝清空或覆盖"
        values = {
            "ORBIT_PYTHON_DB_SOURCES": {
                "primary": {
                    "db_type": "mysql",
                    "db_host": "127.0.0.1",
                    "db_port": 13306,
                    "db_username": "root",
                    "db_password": "",
                    "db_database": database,
                    "db_echo": False,
                }
            },
            "ORBIT_PYTHON_REDIS_HOST": "127.0.0.1",
            "ORBIT_PYTHON_REDIS_PORT": 16379,
            "ORBIT_PYTHON_REDIS_DATABASE": 15,
            "ORBIT_PYTHON_JWT_SECRET_KEY": secrets.token_hex(32),
            "ORBIT_PYTHON_LOGURU_STDOUT": False,
            "ORBIT_PYTHON_LOG_FILE_ENABLED": False,
            "ORBIT_PYTHON_APP_PORT": PORT,
            "ORBIT_PYTHON_PUBLIC_ORIGIN": "https://app.fixture.example",
            "ORBIT_PYTHON_SECRETS_ACTIVE_KEY_ID": "fixture",
            "ORBIT_PYTHON_SECRETS_KEYS": {"fixture": base64.b64encode(os.urandom(32)).decode()},
        }
        if (
            args.include_materials
            or args.include_accounts
            or args.material_scanner_manifest
            or args.include_material_runtime_worker
            or args.include_material_scanner_supervisor_native
            or args.include_material_worker_cli_native
        ):
            object_base = ROOT / ".runtime/integration-objects"
            object_base.mkdir(parents=True, exist_ok=True)
            if not object_base.resolve().is_relative_to(ROOT.resolve()):
                raise ValueError("对象夹具目录必须位于本工作区")
            if (
                args.include_material_scanner_supervisor_native
                or args.include_material_worker_cli_native
            ):
                object_bundle = object_base / ("run-" + uuid.uuid4().hex)
                object_bundle.mkdir(exist_ok=False)
            else:
                object_bundle = Path(tempfile.mkdtemp(prefix="run-", dir=object_base))
            object_bundle_path = object_bundle.resolve()
            if (
                args.include_material_worker_cli_native
                or args.include_material_scanner_supervisor_native
            ):
                result["isolated_fixture_object_bundle"] = object_bundle_path.relative_to(
                    ROOT.resolve()
                ).as_posix()
            material_root = object_bundle_path / "materials"
            material_root.mkdir()
            values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"] = str(material_root)
            if args.include_accounts:
                account_root = object_bundle_path / "account-imports"
                account_root.mkdir()
                values["ORBIT_PYTHON_ACCOUNT_IMPORT_OBJECT_ROOT"] = str(account_root)
            result["object_fixture"] = "本轮工作区内独占UUID目录；结束时仅清理本轮对象"
        if args.material_scanner_configuration_only:
            values["ORBIT_PYTHON_TEST_SCANNER_REGISTRY_PAYLOAD"] = runtime_profile_payload
        if args.environment_live_only or (args.launch_validation_only and args.include_launch_validation_provider) or (
            args.include_launch_execution_material_references
        ):
            values["ORBIT_PYTHON_TEST_LAUNCH_VALIDATION_PROVIDER"] = True
            control_base = ROOT / ".runtime/launch-validation-control"
            control_base.mkdir(parents=True, exist_ok=True)
            if not control_base.resolve().is_relative_to(ROOT.resolve()):
                raise ValueError("预检握手目录必须在本轮工作区内")
            for existing in (control_base, *control_base.parents):
                info = existing.lstat()
                if existing.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise ValueError("预检握手根拒绝链接或reparse")
            launch_validation_control = control_base / ("run-" + uuid.uuid4().hex)
            launch_validation_control.mkdir(exist_ok=False)
            values["ORBIT_PYTHON_TEST_LAUNCH_VALIDATION_CONTROL"] = str(launch_validation_control)
        if args.include_launch_allocation_http_provider:
            values["ORBIT_PYTHON_TEST_LAUNCH_ALLOCATION_PROVIDER"] = True
        if (
            args.environment_live_only
            or args.include_launch_execution_provider
            or args.execution_lease_only
            or args.execution_recovery_scanner_only
            or args.execution_candidate_only
        ):
            values["ORBIT_PYTHON_TEST_LAUNCH_EXECUTION_PROVIDER"] = True
        if args.include_launch_execution_material_references:
            values["ORBIT_PYTHON_TEST_LAUNCH_EXECUTION_MATERIAL_PROVIDER"] = True
        if (
            args.include_metric_profile_query
            or args.include_metric_profile_references
            or (
                args.browser
                and args.browser_module in {"metric-profiles", "launch-metric-profiles"}
            )
        ):
            values["ORBIT_PYTHON_TEST_METRIC_PROFILE_QUERY"] = True
        if args.include_metrics_browser_fixture:
            from metrics_browser_fixture import CONTROL_ROOT

            metrics_fixture_control = CONTROL_ROOT / str(uuid.uuid4()) / "control.json"
            values["ORBIT_PYTHON_TEST_METRICS_BROWSER"] = True
            values["ORBIT_PYTHON_TEST_METRICS_CONTROL"] = str(metrics_fixture_control.resolve())
            values["ORBIT_PYTHON_TEST_METRIC_PROFILE_QUERY"] = True
        scope_diagnostic_dir = None
        if args.include_account_query_profile:
            query_diagnostic_dir = ROOT / ".runtime/account-list-query-profile" / uuid.uuid4().hex
            values["ORBIT_PYTHON_TEST_ACCOUNT_QUERY_PROFILE"] = str(query_diagnostic_dir.resolve())
            result["account_query_diagnostic_directory"] = query_diagnostic_dir.relative_to(
                ROOT
            ).as_posix()
        if args.include_rule_editor or args.rules_definition_browser:
            values["ORBIT_PYTHON_TEST_RULE_EDITOR"] = True
        if args.include_account_scope_profile or args.scope_create_profile_only:
            scope_diagnostic_dir = (
                ROOT / ".runtime/account-scope-capacity-profile" / uuid.uuid4().hex
            )
            values["ORBIT_PYTHON_TEST_ACCOUNT_SCOPE_PROFILE"] = str(scope_diagnostic_dir.resolve())
            result["account_scope_diagnostic_directory"] = scope_diagnostic_dir.relative_to(
                ROOT
            ).as_posix()
        if args.include_account_scope_http_profile:
            scope_http_dir = ROOT / ".runtime/account-scope-http-profile" / uuid.uuid4().hex
            values["ORBIT_PYTHON_TEST_ACCOUNT_SCOPE_HTTP_PROFILE"] = str(scope_http_dir.resolve())
            result["account_scope_http_diagnostic_directory"] = scope_http_dir.relative_to(
                ROOT
            ).as_posix()
        idp = LocalOidcFixture().__enter__()
        values["ORBIT_PYTHON_TEST_OIDC_PORT"] = idp.port
        values["ORBIT_PYTHON_TEST_OIDC_CA"] = idp.ca_pem
        code = """import sys,json
from config.orbit_runtime import configure_isolated_fixture
configure_isolated_fixture(json.load(sys.stdin))
import uvicorn
from orbit_api.application import create_app
from orbit_api.configuration_routes import model_probe
from orbit_api.connection_probe import ModelConnectionProbe
import httpx,asyncio
from redis.asyncio import Redis
async def model_transport(request):
    assert request.method == 'GET'
    assert request.url.host in {'api.openai.com','api.anthropic.com','graph.facebook.com'}
    if request.url.host == 'graph.facebook.com':
        assert request.url.params.get('fields') == 'id,name'
        assert 'access_token' not in request.url.params
        return httpx.Response(200,json={'id':request.url.path.rsplit('/',1)[-1],'name':'fixture'})
    if request.url.path.endswith('/fixture-wait-model'):
        cache = Redis(host='127.0.0.1',port=16379,db=15)
        try:
            await cache.set('orbit-fixture-probe-entered','1',ex=10)
            async with asyncio.timeout(8):
                while not await cache.get('orbit-fixture-probe-release'):
                    await asyncio.sleep(0.02)
        finally:
            await cache.aclose()
    return httpx.Response(200,json={'id':'fixture-model','object':'model','type':'model'})
app = create_app()
from config.orbit_runtime import private_values
if private_values().get('ORBIT_PYTHON_TEST_METRIC_PROFILE_QUERY') is True:
    app.state.metric_profile_fixture_mode = True
if private_values().get('ORBIT_PYTHON_TEST_RULE_EDITOR') is True:
    app.state.rule_editor_fixture = True
if private_values().get('ORBIT_PYTHON_TEST_METRICS_BROWSER') is True:
    from metrics_browser_fixture import LazyMetricsReadProvider, LazyMetricsExpectedProvider
    metrics_control = private_values().get('ORBIT_PYTHON_TEST_METRICS_CONTROL')
    app.state.metrics_source_provider = LazyMetricsReadProvider(metrics_control, enabled=True)
    app.state.metrics_expected_provider = LazyMetricsExpectedProvider(metrics_control, enabled=True)
if private_values().get('ORBIT_PYTHON_TEST_LAUNCH_VALIDATION_PROVIDER') is True:
    from config.database import DataSourceRegistry
    from launch_validation_fixture import IsolatedValidationProvider
    app.state.launch_validation_provider = IsolatedValidationProvider(
        lambda: DataSourceRegistry.session(log_sql=False),
        control_dir=private_values().get('ORBIT_PYTHON_TEST_LAUNCH_VALIDATION_CONTROL'))
if private_values().get('ORBIT_PYTHON_TEST_LAUNCH_EXECUTION_PROVIDER') is True:
    from launch_execution_fixture import (
        IsolatedExecutionValidationProvider, IsolatedExecutionProvider)
    execution_sessions = lambda: DataSourceRegistry.session(log_sql=False)
    execution_control = private_values().get('ORBIT_PYTHON_TEST_LAUNCH_VALIDATION_CONTROL')
    app.state.launch_validation_provider = IsolatedExecutionValidationProvider(
        execution_sessions, control_dir=execution_control)
    app.state.launch_execution_provider = IsolatedExecutionProvider(
        execution_sessions, control_dir=execution_control)
if private_values().get('ORBIT_PYTHON_TEST_LAUNCH_EXECUTION_MATERIAL_PROVIDER') is True:
    from launch_execution_fixture import IsolatedExecutionValidationProvider
    from launch_execution_material_bridge_checks import IsolatedMaterialExecutionProvider
    material_execution_sessions = lambda: DataSourceRegistry.session(log_sql=False)
    material_execution_control = private_values().get('ORBIT_PYTHON_TEST_LAUNCH_VALIDATION_CONTROL')
    app.state.launch_validation_provider = IsolatedExecutionValidationProvider(
        material_execution_sessions, control_dir=material_execution_control)
    app.state.launch_execution_provider = IsolatedMaterialExecutionProvider(
        material_execution_sessions, control_dir=material_execution_control)
if private_values().get('ORBIT_PYTHON_TEST_LAUNCH_ALLOCATION_PROVIDER') is True:
    from launch_allocation_http_fixture import IsolatedHttpAllocationProvider
    app.state.launch_allocation_provider = IsolatedHttpAllocationProvider()
scanner_fixture = private_values().get('ORBIT_PYTHON_TEST_SCANNER_REGISTRY_PAYLOAD')
if scanner_fixture is not None:
    # 仅隔离测试引导显式发布固定实例；生产应用不会采用此fixture入口。
    from orbit_api.material_antivirus_runtime import PROFILE_KEY,ProcessBoundMaterialScanner
    fixture_values = {PROFILE_KEY:json.dumps(scanner_fixture['profiles'])}
    bound_scanner = ProcessBoundMaterialScanner(
        scanner_fixture['profile_id'],values_provider=lambda:fixture_values)
    app.state.material_scanner_registry.publish(bound_scanner,'本机隔离扫描器')
app.dependency_overrides[model_probe] = lambda: ModelConnectionProbe(
    transport=httpx.MockTransport(model_transport))
from config.database import DataSourceRegistry
from config.orbit_runtime import private_values
from orbit_api.authentication_routes import authentication_service
from orbit_api.authentication_service import AuthenticationService
from orbit_api.configuration_routes import credential_cipher
from orbit_api.oidc_http import OidcHttp
import httpcore,ssl
class IsolatedOidcNetwork(httpcore.AsyncNetworkBackend):
    async def connect_tcp(self,host,port,**kwargs):
        assert host=='orbit-idp.fixture.example' and port==443
        return await httpcore.AnyIOBackend().connect_tcp(
            '127.0.0.1',private_values()['ORBIT_PYTHON_TEST_OIDC_PORT'],**kwargs)
def isolated_authentication_service():
    context=ssl.create_default_context(cadata=private_values()['ORBIT_PYTHON_TEST_OIDC_CA'])
    return AuthenticationService(
        lambda: DataSourceRegistry.session(log_sql=False),credential_cipher(),
        http=OidcHttp(network_backend=IsolatedOidcNetwork(),ssl_context=context))
app.dependency_overrides[authentication_service]=isolated_authentication_service
uvicorn.run(app,host='127.0.0.1',port=18083,access_log=False,log_level='error')
"""
        if args.include_identity_summary_profile:
            # 仅隔离子进程、两个指定诊断GET；只存函数统计，不存请求参数或局部变量。
            profile_output = ROOT / ".runtime/identity-summary-http-profile"
            profile_output.mkdir(parents=True, exist_ok=True)
            instrumentation = """
import cProfile,io,pstats,time
from pathlib import Path
from urllib.parse import parse_qs
class DiagnosticProfile:
    def __init__(self,app): self.app,self.sequence=app,0
    async def __call__(self,scope,receive,send):
        query=parse_qs(scope.get('query_string',b'').decode('ascii'))
        selected=(self.sequence<2 and scope.get('path')=='/api/v1/accounts/extended'
            and query.get('q',[''])[0].startswith('summary-profile-'))
        if not selected: return await self.app(scope,receive,send)
        profile=cProfile.Profile()
        finished=False
        def finish():
            nonlocal finished
            if finished: return
            finished=True
            profile.disable()
            output=io.StringIO()
            pstats.Stats(profile,stream=output).sort_stats('cumulative').print_stats(120)
            self.sequence+=1
            (Path(PROFILE_DEST)/('request-'+str(self.sequence)+'.txt')).write_text(output.getvalue(),encoding='utf-8')
        async def profiled_send(message):
            if message['type']=='http.response.body' and not message.get('more_body',False):
                finish()
            await send(message)
        profile.enable()
        try: return await self.app(scope,receive,profiled_send)
        finally:
            finish()
app.add_middleware(DiagnosticProfile)
""".replace("PROFILE_DEST", repr(str(profile_output)))
            code = code.replace("uvicorn.run(app,", instrumentation + "\nuvicorn.run(app,", 1)
        if args.include_account_scope_profile or args.scope_create_profile_only:
            target = (
                "uvicorn.run(app,host='127.0.0.1',port=18083,access_log=False,log_level='error')"
            )
            if args.include_account_scope_http_profile:
                # 从安装到退出统一清理；任一层失败不覆盖原异常或跳过其余恢复。
                setup = (
                    "from account_scope_http_diagnostics import "
                    "scope_http_diagnostics_context\n"
                    "with scope_http_diagnostics_context(app, "
                    "private_values()['ORBIT_PYTHON_TEST_ACCOUNT_SCOPE_PROFILE'], "
                    "private_values()['ORBIT_PYTHON_TEST_ACCOUNT_SCOPE_HTTP_PROFILE'], "
                    "isolated_test=True) as app:\n    "
                )
                code = code.replace(target, setup + target, 1)
            else:
                setup = (
                    "from account_scope_capacity_diagnostics import "
                    "install_scope_create_diagnostics\n"
                    "scope_profile_stop = install_scope_create_diagnostics("
                    "private_values()['ORBIT_PYTHON_TEST_ACCOUNT_SCOPE_PROFILE'])\n"
                    "try:\n    "
                )
                code = code.replace(
                    target, setup + target + "\nfinally:\n    scope_profile_stop()", 1
                )
        if args.include_account_query_profile:
            target = (
                "uvicorn.run(app,host='127.0.0.1',port=18083,access_log=False,log_level='error')"
            )
            setup = (
                "from account_list_query_diagnostics import "
                "install_account_list_query_diagnostics, wrap_account_query_http, "
                "install_account_query_stage_diagnostics, install_account_query_pool_diagnostics, "
                "install_account_query_native_lease_diagnostics\n"
                "query_profile_stop = install_account_list_query_diagnostics("
                "private_values()['ORBIT_PYTHON_TEST_ACCOUNT_QUERY_PROFILE'], isolated_test=True)\n"
                "app = wrap_account_query_http(app, "
                "private_values()['ORBIT_PYTHON_TEST_ACCOUNT_QUERY_PROFILE'], isolated_test=True)\n"
                "query_stage_stop = install_account_query_stage_diagnostics("
                "private_values()['ORBIT_PYTHON_TEST_ACCOUNT_QUERY_PROFILE'], isolated_test=True)\n"
                "query_pool_stop = install_account_query_pool_diagnostics("
                "private_values()['ORBIT_PYTHON_TEST_ACCOUNT_QUERY_PROFILE'], isolated_test=True)\n"
                "query_native_stop = install_account_query_native_lease_diagnostics("
                "private_values()['ORBIT_PYTHON_TEST_ACCOUNT_QUERY_PROFILE'], isolated_test=True)\n"
                "try:\n    "
            )
            code = code.replace(
                target,
                setup + target + "\nfinally:\n    query_native_stop()\n    query_pool_stop()\n"
                "    query_stage_stop()\n    query_profile_stop()",
                1,
            )
        environment = os.environ.copy()
        python_paths = [str(ROOT / "python"), str(FRAMEWORK)]
        if (
            args.environment_live_only
            or args.execution_lease_only
            or args.execution_recovery_scanner_only
            or args.execution_candidate_only
            or args.include_metrics_browser_fixture
            or args.include_account_scope_profile
            or args.include_account_query_profile
            or args.scope_create_profile_only
            or args.include_launch_execution_material_references
            or (
                args.launch_validation_only
                and (
                    args.include_launch_validation_provider
                    or args.include_launch_allocation_http_provider
                )
            )
        ):
            python_paths.insert(0, str(ROOT / "tools"))
        environment["PYTHONPATH"] = os.pathsep.join(python_paths)
        child = subprocess.Popen(
            [sys.executable, "-c", code],
            cwd=FRAMEWORK,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=log,
        )
        child.stdin.write(json.dumps(values).encode())
        child.stdin.close()
        with httpx.Client(base_url=f"http://127.0.0.1:{PORT}", timeout=10) as client:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    raise RuntimeError("Python应用启动失败")
                try:
                    if client.get("/health/ready").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.25)
            else:
                raise RuntimeError("Python应用就绪超时")
            cases.append("pythonRealMysqlRedisReadiness")
            with admin.cursor() as cursor:
                cursor.execute("SELECT revision FROM orbit_directory_clock")
                assert cursor.fetchone()[0] == 1
                cursor.execute("SELECT created_at,updated_at FROM orbit_business_team")
                assert cursor.fetchone() == (None, None), "不能伪造迁移前未采集的团队时间"
                for table in (
                    "orbit_directory_audit",
                    "orbit_directory_idempotency",
                    "orbit_directory_outbox",
                ):
                    cursor.execute("SHOW FULL COLUMNS FROM " + table)
                    assert all(row[-1] for row in cursor.fetchall()), "新表字段必须有中文COMMENT"
                cursor.execute(
                    "SHOW INDEX FROM orbit_directory_audit "
                    "WHERE Key_name='uk_directory_audit_version'"
                )
                assert len(cursor.fetchall()) == 4
            cases.append("pythonBusinessDirectorySchemaAndUnknownHistory")
            captcha = client.get("/captchaImage")
            assert captcha.status_code == 200 and captcha.json()["captchaEnabled"] is False
            login = client.post(
                "/login", json={"username": "admin", "password": password, "code": "", "uuid": ""}
            )
            data = login.json()
            assert login.status_code == 200 and data.get("code") == 200 and data.get("token"), (
                "真实登录失败"
            )
            token = data["token"]
            cases.append("pythonRealJsonPasswordLogin")
            headers = {"Authorization": f"Bearer {token}"}
            info = client.get("/getInfo", headers=headers)
            assert info.status_code == 200 and info.json().get("user", {}).get("userId") == 1
            assert "password" not in json.dumps(info.json())
            cases.append("pythonCurrentUserSanitized")
            routers = client.get("/getRouters", headers=headers)
            assert routers.status_code == 200
            routes = routers.json()["data"]
            assert {r["path"] for r in routes} >= {"/system", "/monitor", "/tool"}
            cases.append("pythonOriginalDynamicMenus")
            if args.channel_scope_only:
                user_fixture = run_user_checks(client, admin, headers, password, cases)
                run_channel_scope_matrix_checks(
                    client, admin, headers, user_fixture, password, cache, cases
                )
            if args.reference_channel_only:
                user_fixture = run_user_checks(client, admin, headers, password, cases)
                result["reference_channel_fixture"] = run_reference_channel_checks(
                    client, admin, headers, user_fixture, cases
                )
                run_reference_channel_scope_checks(
                    client, admin, headers, user_fixture, password, cache, cases
                )
                if args.include_channel_scope:
                    run_channel_scope_matrix_checks(
                        client, admin, headers, user_fixture, password, cache, cases
                    )
                if args.include_channel_fields:
                    run_channel_field_contract_checks(
                        client,
                        admin,
                        headers,
                        result["reference_channel_fixture"],
                        cases,
                        ROOT / "docs/orbit/baseline/contracts/openapi-current.json",
                    )
                if args.include_reference_channel_capacity:
                    result["reference_channel_capacity"] = run_reference_channel_capacity_checks(
                        client, admin, headers, database, cases, child.pid
                    )
            if args.channel_owners_only:
                user_fixture = run_user_checks(client, admin, headers, password, cases)
                result["channel_owners_fixture"] = run_channel_owners_500_checks(
                    client, admin, headers, user_fixture, password, cache, cases
                )
            if args.environment_live_only:
                user_fixture = run_user_checks(client, admin, headers, password, cases)
                result["environment_live"] = run_environment_live_checks(
                    client,
                    admin,
                    headers,
                    user_fixture,
                    password,
                    cache,
                    database,
                    values,
                    cases,
                    real_adspower=args.include_local_adspower,
                    meta_expectation_file=args.meta_expectation_file,
                    browser=args.environment_internal_browser and not args.include_meta_connection_checks,
                )
            if args.include_meta_connection_checks:
                from meta_connection_checks import run_meta_connection_checks
                result["meta_connections"] = run_meta_connection_checks(admin, database, cases, client, values, browser=args.environment_internal_browser)
                if args.include_meta_pipeline_checks:
                    from meta_pipeline_checks import run_meta_pipeline_checks
                    run_meta_pipeline_checks(admin, database, cases, values)
                if args.environment_internal_browser:
                    from rules_internal_browser_checkpoint import run_rules_internal_browser_checkpoint
                    result["meta_browser"] = run_rules_internal_browser_checkpoint(admin, database, password, static_dist=ROOT.parent / "orbit-web/dist", meta_origin_fixture=True)
            if args.environment_registry_only:
                user_fixture = run_user_checks(client, admin, headers, password, cases)
                result["environment_registry"] = run_environment_registry_checks(
                    client, admin, headers, user_fixture, password, cache, database, cases
                )
                result["profile_bindings"] = run_profile_binding_checks(
                    client, admin, headers, database, password, cache, cases
                )
                if args.environment_internal_browser:
                    from rules_internal_browser_checkpoint import (
                        run_rules_internal_browser_checkpoint,
                    )

                    result["environment_internal_browser"] = run_rules_internal_browser_checkpoint(
                        admin, database, password
                    )
            if args.material_taxonomy_scope_only or args.material_taxonomy_metadata_only:
                user_fixture = run_user_checks(client, admin, headers, password, cases)
                run_material_taxonomy_scope_checks(
                    client, admin, headers, user_fixture, password, cache, cases
                )
                if args.include_material_taxonomy_capabilities:
                    run_material_taxonomy_capability_checks(
                        client, admin, headers, user_fixture, password, cache, cases
                    )
                if args.taxonomy_internal_browser:
                    from rules_internal_browser_checkpoint import (
                        run_rules_internal_browser_checkpoint,
                    )

                    result["taxonomy_internal_browser"] = run_rules_internal_browser_checkpoint(
                        admin, database, password
                    )
            if args.vendor_alias_only:
                user_fixture = run_user_checks(client, admin, headers, password, cases)
                run_vendor_alias_checks(
                    client, admin, headers, user_fixture, password, cache, cases
                )
            if fast_mode and args.include_configuration_metadata:
                run_configuration_metadata_checks(client, admin, headers, token, password, cases)
            if (
                args.material_scanner_manifest
                and not args.browser_only
                and not args.material_scanner_configuration_only
            ):
                run_material_antivirus_engine_checks(raw_material_scanner, cases)
                run_material_antivirus_worker_checks(
                    admin,
                    database,
                    values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"],
                    material_scanner,
                    cases,
                )
            if args.material_references_only:
                user_fixture = run_user_checks(client, admin, headers, password, cases)
                run_material_reference_checks(
                    admin,
                    database,
                    cases,
                    scanner=material_scanner,
                    object_root=values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"],
                )
                run_material_reference_scope_checks(
                    client, admin, database, headers, user_fixture, cases
                )
            if args.launch_drafts_only:
                user_fixture = run_user_checks(client, admin, headers, password, cases)
                run_launch_draft_template_checks(
                    client, admin, headers, user_fixture, password, cache, cases
                )
            if args.template_recipients_only:
                user_fixture = run_user_checks(client, admin, headers, password, cases)
            if args.account_details_only:
                user_fixture = run_user_checks(client, admin, headers, password, cases)
                from orbit_api.credentials import CredentialCipher

                account_cipher = CredentialCipher("fixture", values["ORBIT_PYTHON_SECRETS_KEYS"])
                if args.include_account_alias_snapshots:
                    import_identity, owner, team, vendor = prepare_account_alias_fixture(
                        client, admin, headers, password, cache
                    )
                    run_account_import_checks(client, admin, headers, owner, team, vendor, cases)
                    run_account_worker_checks(
                        client, admin, headers, account_cipher, owner, team, vendor, database, cases
                    )
                else:
                    owner, team, vendor = prepare_account_import_fixture(client, admin, headers)
                run_account_details_checks(
                    client, admin, headers, 1, owner, team, vendor, database, cases, account_cipher
                )
                if args.include_account_alias_snapshots:
                    run_account_alias_snapshot_checks(
                        client, admin, headers, import_identity, vendor, database, cases
                    )
                if args.include_account_identities:
                    run_account_identities_checks(
                        client,
                        admin,
                        headers,
                        1,
                        owner,
                        team,
                        database,
                        cases,
                        account_cipher,
                        import_identity["headers"],
                    )
                    result["identity_publication"] = run_identity_publication_checks(
                        client,
                        admin,
                        headers,
                        password,
                        cache,
                        database,
                        cases,
                        cipher=account_cipher,
                        include_inventory_boundaries=True,
                    )
                if args.include_account_actions:
                    action_identity = prepare_account_action_fixture(
                        client, admin, headers, password, cache, team
                    )
                    run_account_actions_checks(
                        client,
                        admin,
                        headers,
                        owner,
                        team,
                        vendor,
                        import_identity,
                        action_identity,
                        database,
                        cases,
                        account_cipher,
                    )
                if args.include_account_assignment_options:
                    run_account_assignment_options_checks(
                        client,
                        admin,
                        headers,
                        owner,
                        team,
                        vendor,
                        import_identity,
                        action_identity,
                        database,
                        cases,
                    )
                if args.include_account_command_diagnostics:
                    run_account_command_checks(
                        client, admin, headers, owner, team, action_identity, database, cases
                    )
                if args.include_account_sync:
                    run_account_sync_checks(
                        client,
                        admin,
                        headers,
                        account_cipher,
                        owner,
                        team,
                        action_identity,
                        database,
                        cases,
                    )
                if args.include_account_capacity:
                    result["account_capacity"] = run_account_capacity_checks(
                        client,
                        admin,
                        headers,
                        owner,
                        team,
                        database,
                        cases,
                        child.pid,
                        include_scope=args.include_account_scopes,
                        diagnostic_dir=scope_diagnostic_dir,
                    )
                if args.include_account_scopes:
                    readonly_identity = prepare_account_readonly_fixture(
                        client, admin, headers, password, cache
                    )
                    run_account_scope_checks(
                        client,
                        admin,
                        headers,
                        1,
                        owner,
                        team,
                        database,
                        cases,
                        account_cipher,
                        readonly_identity,
                    )
                if args.include_scope_visibility_verdict:
                    run_scope_visibility_verdict_checks(
                        client, admin, headers, password, cache, database, cases
                    )
                if args.include_account_projection:
                    run_account_projection_checks(
                        client,
                        admin,
                        headers,
                        owner,
                        team,
                        vendor,
                        import_identity,
                        readonly_identity,
                        database,
                        cases,
                        account_cipher,
                    )
            if args.material_only:
                if args.include_material_taxonomy_scope:
                    user_fixture = run_user_checks(client, admin, headers, password, cases)
                run_material_checks(
                    client,
                    admin,
                    database,
                    headers,
                    values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"],
                    cases,
                    scanner=material_scanner,
                )
                if args.include_material_video:
                    run_material_video_checks(
                        client,
                        admin,
                        database,
                        headers,
                        values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"],
                        cases,
                        args.material_video_bin,
                        runtime_profile=runtime_profile_payload,
                    )
            if not fast_mode:
                user_fixture = run_user_checks(client, admin, headers, password, cases)
                run_native_role_read_checks(client, admin, headers, user_fixture, cases)
                run_native_write_contract_checks(client, admin, headers, user_fixture, cases)
                run_native_role_reference_checks(client, admin, headers, user_fixture, cases)
                run_native_bulk_lifecycle_checks(client, admin, headers, user_fixture, cases)
                run_browser_session_checks(
                    admin,
                    database,
                    user_fixture,
                    cases,
                    client,
                    headers,
                    values["ORBIT_PYTHON_SECRETS_KEYS"],
                    idp,
                    include_account_read_cookie=args.include_account_read_cookie,
                )
                run_native_user_change_checks(client, admin, headers, user_fixture, cases)
                run_team_checks(client, admin, headers, password, cases)
                run_identity_capacity_checks(client, admin, headers, cases)
                run_role_checks(client, admin, headers, password, cases)
                path = "/api/v1/system-configurations/metadata"
                run_configuration_metadata_checks(client, admin, headers, token, password, cases)
                base = "/api/v1/system-configurations"
                write = {
                    "section": "AI_GPT",
                    "name": "GPT真实事务",
                    "enabled": True,
                    "settings": {"model": "fixture-model"},
                    "secrets": {"apiKey": {"operation": "REPLACE", "value": "fixture-model-key"}},
                    "reason": "真实HTTP夹具创建",
                }
                create_headers = headers | {
                    "Idempotency-Key": "fixture-create-key",
                    "X-Request-ID": "client-cannot-spoof-audit",
                }
                first = client.post(base, headers=create_headers, json=write)
                assert first.status_code == 200, "配置创建失败"
                record = first.json()
                assert record["revision"] == 1 and record["secrets"]["apiKey"]["configured"] is True
                assert "fixture-model-key" not in first.text
                replay = client.post(base, headers=create_headers, json=write)
                assert replay.status_code == 200 and replay.json() == record
                changed = client.post(
                    base, headers=create_headers, json=write | {"name": "另一个名字"}
                )
                assert changed.status_code == 409
                with admin.cursor() as cursor:
                    cursor.execute(
                        "SELECT secrets_json FROM orbit_system_configuration WHERE id=%s",
                        (record["id"],),
                    )
                    encrypted = cursor.fetchone()[0]
                    assert "fixture-model-key" not in encrypted and "v1.fixture." in encrypted
                    cursor.execute(
                        "SELECT COUNT(*) FROM orbit_configuration_audit WHERE config_id=%s",
                        (record["id"],),
                    )
                    assert cursor.fetchone()[0] == 1
                    cursor.execute(
                        "SELECT actor_subject_id,actor_team_id,request_id "
                        "FROM orbit_configuration_audit WHERE config_id=%s",
                        (record["id"],),
                    )
                    subject_id, team_id, request_id = cursor.fetchone()
                    assert str(uuid.UUID(subject_id)) == subject_id
                    assert str(uuid.UUID(team_id)) == team_id
                    assert request_id == first.headers["x-request-id"]
                    assert request_id != replay.headers["x-request-id"]
                    cursor.execute(
                        "SELECT COUNT(*) FROM orbit_configuration_outbox WHERE config_id=%s",
                        (record["id"],),
                    )
                    assert cursor.fetchone()[0] == 1
                assert client.get(base, headers=headers).json()[0]["id"] == record["id"]
                assert client.get(base + "/" + record["id"], headers=headers).json() == record
                cases.append("pythonConfigurationCreateEncryptsAndIdempotentReplay")
                change = write | {"name": "GPT修改后", "secrets": {"apiKey": {"operation": "KEEP"}}}
                updated = client.put(
                    base + "/" + record["id"],
                    headers=headers | {"Idempotency-Key": "fixture-update-key", "If-Match": '"1"'},
                    json=change,
                )
                assert updated.status_code == 200 and updated.json()["revision"] == 2
                stale = client.put(
                    base + "/" + record["id"],
                    headers=headers | {"Idempotency-Key": "fixture-stale-key", "If-Match": '"1"'},
                    json=change,
                )
                assert stale.status_code == 409
                clear = change | {"secrets": {"apiKey": {"operation": "CLEAR"}}}
                rejected = client.put(
                    base + "/" + record["id"],
                    headers=headers | {"Idempotency-Key": "fixture-clear-key", "If-Match": '"2"'},
                    json=clear,
                )
                assert rejected.status_code == 422
                assert (
                    client.get(base + "/" + record["id"], headers=headers).json()["revision"] == 2
                )
                with admin.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(*) FROM orbit_configuration_audit WHERE config_id=%s",
                        (record["id"],),
                    )
                    assert cursor.fetchone()[0] == 2
                    cursor.execute(
                        "SELECT COUNT(*) FROM orbit_configuration_idempotency "
                        "WHERE request_key IN('fixture-stale-key','fixture-clear-key')"
                    )
                    assert cursor.fetchone()[0] == 0
                cases.append("pythonConfigurationUpdateCasAndClearRequiredSecret")
                with admin.cursor() as cursor:
                    cursor.execute(
                        "CREATE TRIGGER orbit_py_audit_fail BEFORE INSERT "
                        "ON orbit_configuration_audit "
                        "FOR EACH ROW SIGNAL SQLSTATE '45000' "
                        "SET MESSAGE_TEXT='audit fixture rejection'"
                    )
                try:
                    failed = client.post(
                        base,
                        headers=headers | {"Idempotency-Key": "fixture-rollback-key"},
                        json=write | {"name": "事务必须回滚"},
                    )
                    assert failed.status_code == 503
                    assert (
                        "fixture-model-key" not in failed.text
                        and "audit fixture rejection" not in failed.text
                    )
                finally:
                    with admin.cursor() as cursor:
                        cursor.execute("DROP TRIGGER orbit_py_audit_fail")
                with admin.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(*) FROM orbit_system_configuration WHERE name='事务必须回滚'"
                    )
                    assert cursor.fetchone()[0] == 0
                    cursor.execute(
                        "SELECT COUNT(*) FROM orbit_configuration_idempotency "
                        "WHERE request_key='fixture-rollback-key'"
                    )
                    assert cursor.fetchone()[0] == 0
                    cursor.execute("SELECT COUNT(*) FROM orbit_configuration_outbox")
                    assert cursor.fetchone()[0] == 2
                cases.append("pythonConfigurationAuditFailureRollsBackWholeWrite")
                history = base + "/" + record["id"] + "/history"
                first_history = client.get(history + "?pageSize=1", headers=headers)
                assert first_history.status_code == 200
                assert [item["revision"] for item in first_history.json()["items"]] == [2]
                assert first_history.json()["nextBeforeRevision"] == 2
                second_history = client.get(
                    history + "?pageSize=1&beforeRevision=2", headers=headers
                )
                assert [item["revision"] for item in second_history.json()["items"]] == [1]
                assert second_history.json()["nextBeforeRevision"] is None
                assert "fixture-model-key" not in first_history.text + second_history.text
                assert "v1.fixture." not in first_history.text + second_history.text
                assert (
                    first_history.json()["items"][0]["beforeHash"]
                    == second_history.json()["items"][0]["afterHash"]
                )
                for query, status in [
                    ("pageSize=0", 422),
                    ("pageSize=101", 422),
                    ("pageSize=1&pageSize=2", 400),
                    ("tenant_id=forged", 400),
                ]:
                    assert client.get(history + "?" + query, headers=headers).status_code == status
                cases.append("pythonConfigurationHistoryKeysetAndNoSecretValues")
                with admin.cursor() as cursor:
                    cursor.execute(
                        "CREATE TRIGGER orbit_py_outbox_fail BEFORE INSERT "
                        "ON orbit_configuration_outbox "
                        "FOR EACH ROW SIGNAL SQLSTATE '45000' "
                        "SET MESSAGE_TEXT='outbox fixture rejection'"
                    )
                try:
                    failed = client.put(
                        base + "/" + record["id"],
                        headers=headers
                        | {"Idempotency-Key": "fixture-outbox-key", "If-Match": '"2"'},
                        json=change,
                    )
                    assert failed.status_code == 503
                finally:
                    with admin.cursor() as cursor:
                        cursor.execute("DROP TRIGGER orbit_py_outbox_fail")
                assert (
                    client.get(base + "/" + record["id"], headers=headers).json()["revision"] == 2
                )
                with admin.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM orbit_configuration_audit")
                    assert cursor.fetchone()[0] == 2
                    cursor.execute(
                        "SELECT COUNT(*) FROM orbit_configuration_idempotency "
                        "WHERE request_key='fixture-outbox-key'"
                    )
                    assert cursor.fetchone()[0] == 0
                    cursor.execute("SELECT COUNT(*) FROM orbit_configuration_outbox")
                    assert cursor.fetchone()[0] == 2
                cases.append("pythonConfigurationOutboxFailureRollsBackAuditAndConfig")
                with admin.cursor() as cursor:
                    tenant = "00000000-0000-0000-0000-000000000001"
                    other_tenant, other_id, subject = (
                        str(uuid.uuid4()),
                        str(uuid.uuid4()),
                        str(uuid.uuid4()),
                    )
                    cursor.execute(
                        "UPDATE sys_user SET password=%s,status='0',del_flag='0' WHERE user_id=2",
                        (bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),),
                    )
                    cursor.execute(
                        "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) "
                        "VALUES(2,%s,'SUPER_ADMIN')",
                        (tenant,),
                    )
                    cursor.execute(
                        "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id) "
                        "VALUES(%s,%s,2,%s)",
                        (tenant, subject, tenant),
                    )
                    cursor.execute(
                        "INSERT INTO sys_role"
                        "(role_id,role_name,role_key,role_sort,status,del_flag) "
                        "VALUES(990003,'fixture split','fixture-split',3,'0','0')"
                    )
                    cursor.execute("INSERT INTO sys_user_role(user_id,role_id) VALUES(2,990003)")
                    cursor.execute(
                        "INSERT INTO sys_role_menu(role_id,menu_id) "
                        "VALUES(2,31000),(2,31080),(990003,31081)"
                    )
                    cursor.execute(
                        "INSERT INTO orbit_tenant(id,name) VALUES(%s,'其他租户夹具')",
                        (other_tenant,),
                    )
                    cursor.execute(
                        "INSERT INTO orbit_system_configuration"
                        "(id,tenant_id,section,name,settings_json,secrets_json) "
                        "VALUES(%s,%s,'AI_GPT','不可泄露名称','{}','{}')",
                        (other_id, other_tenant),
                    )
                with admin.cursor() as cursor:
                    cursor.execute("SELECT user_name FROM sys_user WHERE user_id=2")
                    regular_name = cursor.fetchone()[0]
                regular = client.post(
                    "/login",
                    json={"username": regular_name, "password": password, "code": "", "uuid": ""},
                )
                assert regular.status_code == 200 and regular.json().get("token")
                regular_headers = {"Authorization": "Bearer " + regular.json()["token"]}
                assert client.get(path, headers=regular_headers).status_code == 200
                for downgraded_role in ("USER", "TEAM_ADMIN"):
                    with admin.cursor() as cursor:
                        cursor.execute(
                            "UPDATE orbit_user_scope SET data_role=%s WHERE user_id=2",
                            (downgraded_role,),
                        )
                    assert client.get(path, headers=regular_headers).status_code == 403
                    assert client.get(base, headers=regular_headers).status_code == 403
                    assert (
                        client.post(
                            base,
                            headers=regular_headers | {"Idempotency-Key": "fixture-downgrade-key"},
                            json=write,
                        ).status_code
                        == 403
                    )
                with admin.cursor() as cursor:
                    cursor.execute(
                        "UPDATE orbit_user_scope SET data_role='SUPER_ADMIN' WHERE user_id=2"
                    )
                assert client.get(path, headers=regular_headers).status_code == 200
                invisible = client.get(base + "/" + other_id, headers=regular_headers)
                assert invisible.status_code == 404 and "不可泄露名称" not in invisible.text
                assert (
                    client.get(
                        base + "?tenant_id=" + other_tenant, headers=regular_headers
                    ).status_code
                    == 400
                )
                with admin.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM sys_role_menu WHERE role_id=990003 AND menu_id=31081"
                    )
                assert client.get(path, headers=regular_headers).status_code == 403
                with admin.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(990003,31081)"
                    )
                    cursor.execute("UPDATE orbit_business_user SET enabled=0 WHERE user_id=2")
                # 撤销业务身份在认证层返回401；仍有会话但缺动作的前一断言保持403。
                assert client.get(path, headers=regular_headers).status_code == 401
                cases.append("pythonConfigurationRoleUnionCrossTenantAndIdentityRevocation")
                second_team = str(uuid.uuid4())
                with admin.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO orbit_business_team(tenant_id,id,name) "
                        "VALUES(%s,%s,'并发管理团队')",
                        (tenant, second_team),
                    )
                    cursor.execute(
                        "UPDATE orbit_business_user SET enabled=1,team_id=%s WHERE user_id=2",
                        (second_team,),
                    )
                    cursor.execute(
                        "UPDATE orbit_user_scope SET enabled=1,data_role='SUPER_ADMIN' "
                        "WHERE user_id=2"
                    )
                    cursor.execute(
                        "SELECT revision FROM orbit_directory_clock WHERE tenant_id=%s", (tenant,)
                    )
                    directory_before = cursor.fetchone()[0]
                    cursor.execute(
                        "SELECT revision FROM orbit_business_user WHERE user_id=2 AND tenant_id=%s",
                        (tenant,),
                    )
                    person_before = cursor.fetchone()[0]
                native_status_path = "/system/user/changeStatus"
                native_disabled = client.put(
                    native_status_path, headers=headers, json={"userId": 2, "status": "1"}
                )
                assert native_disabled.status_code == 200 and native_disabled.json()["code"] == 200
                with admin.cursor() as cursor:
                    cursor.execute("SELECT status FROM sys_user WHERE user_id=2")
                    assert cursor.fetchone()[0] == "1"
                    cursor.execute(
                        "SELECT revision FROM orbit_directory_clock WHERE tenant_id=%s", (tenant,)
                    )
                    # 身份安全事件与业务人员变更各推进一次目录时钟，同事务提交。
                    assert cursor.fetchone()[0] == directory_before + 2
                    cursor.execute(
                        "SELECT revision FROM orbit_business_user WHERE user_id=2 AND tenant_id=%s",
                        (tenant,),
                    )
                    assert cursor.fetchone()[0] == person_before + 1
                native_enabled = client.put(
                    native_status_path, headers=headers, json={"userId": 2, "status": "0"}
                )
                assert native_enabled.status_code == 200 and native_enabled.json()["code"] == 200
                with admin.cursor() as cursor:
                    cursor.execute("SELECT auth_version FROM sys_identity_subject WHERE user_id=2")
                    subject_version = cursor.fetchone()[0]
                cases.append("pythonNativeUserStateChangeParticipatesInDirectoryTransaction")
                stale_native = client.get("/getInfo", headers=regular_headers)
                assert stale_native.status_code == 401 or stale_native.json().get("code") == 401, (
                    "停用后重新启用不能恢复旧会话"
                )
                cases.append("pythonNativeDisabledSessionCannotResurrectOnReenable")
                admin.begin()
                try:
                    with admin.cursor() as cursor:
                        cursor.execute(
                            "SELECT revision FROM orbit_directory_clock "
                            "WHERE tenant_id=%s FOR UPDATE",
                            (tenant,),
                        )
                        cursor.execute(
                            "UPDATE orbit_business_team SET enabled=0 WHERE tenant_id=%s AND id=%s",
                            (tenant, tenant),
                        )
                        cursor.execute(
                            "UPDATE orbit_directory_clock SET revision=revision+1 "
                            "WHERE tenant_id=%s",
                            (tenant,),
                        )
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        pending_native = pool.submit(
                            client.put,
                            native_status_path,
                            headers=headers,
                            json={"userId": 2, "status": "1"},
                        )
                        try:
                            deadline = time.monotonic() + 5
                            while True:
                                with admin.cursor() as cursor:
                                    cursor.execute(
                                        """
                                        SELECT COUNT(*) FROM performance_schema.data_lock_waits w
                                        JOIN performance_schema.data_locks r
                                          ON r.ENGINE_LOCK_ID=w.REQUESTING_ENGINE_LOCK_ID
                                        WHERE r.OBJECT_SCHEMA=%s
                                          AND r.OBJECT_NAME='orbit_business_team'
                                    """,
                                        (database,),
                                    )
                                    waiting = cursor.fetchone()[0]
                                if waiting:
                                    break
                                assert time.monotonic() < deadline, (
                                    "原若依事务未进入当前操作者团队授权锁"
                                )
                                time.sleep(0.02)
                            admin.commit()
                        finally:
                            admin.rollback()
                        rejected_native = pending_native.result(timeout=10)
                    assert rejected_native.status_code == 200
                    assert rejected_native.json()["code"] != 200
                    assert "当前业务授权已失效" in rejected_native.json().get("msg", "")
                    with admin.cursor() as cursor:
                        cursor.execute("SELECT status FROM sys_user WHERE user_id=2")
                        assert cursor.fetchone()[0] == "0", "原若依账号停用必须整笔回滚"
                        cursor.execute(
                            "SELECT auth_version FROM sys_identity_subject WHERE user_id=2"
                        )
                        assert cursor.fetchone()[0] == subject_version
                        cursor.execute(
                            "SELECT revision FROM orbit_business_user "
                            "WHERE user_id=2 AND tenant_id=%s",
                            (tenant,),
                        )
                        assert cursor.fetchone()[0] == person_before + 2
                finally:
                    admin.rollback()
                    with admin.cursor() as cursor:
                        cursor.execute(
                            "UPDATE orbit_business_team SET enabled=1 WHERE tenant_id=%s AND id=%s",
                            (tenant, tenant),
                        )
                cases.append(
                    "pythonNativeUserStateRevokedActorCannotWriteAfterConcurrentTeamChange"
                )
                run_role_guard_checks(client, admin, headers, password, tenant, cases, cache)
                foreign_team = str(uuid.uuid4())
                with admin.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO orbit_directory_clock(tenant_id) VALUES(%s)", (other_tenant,)
                    )
                    cursor.execute(
                        "INSERT INTO orbit_business_team(tenant_id,id,name) "
                        "VALUES(%s,%s,'其他租户团队')",
                        (other_tenant, foreign_team),
                    )
                    cursor.execute(
                        "INSERT INTO sys_user(user_id,user_name,nick_name,password,status) "
                        "SELECT 999004,'fixture_foreign_admin','隔离管理员',password,'0' "
                        "FROM sys_user WHERE user_id=2"
                    )
                    cursor.execute("INSERT INTO sys_user_role(user_id,role_id) VALUES(999004,2)")
                    cursor.execute(
                        "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) "
                        "VALUES(999004,%s,'SUPER_ADMIN')",
                        (other_tenant,),
                    )
                    cursor.execute(
                        "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id) "
                        "VALUES(%s,%s,999004,%s),(%s,%s,2,%s)",
                        (
                            other_tenant,
                            str(uuid.uuid4()),
                            foreign_team,
                            other_tenant,
                            str(uuid.uuid4()),
                            foreign_team,
                        ),
                    )
                    cursor.execute(
                        "UPDATE orbit_user_scope SET tenant_id=%s WHERE user_id=2", (other_tenant,)
                    )
                try:
                    foreign_change = client.put(
                        native_status_path, headers=headers, json={"userId": 2, "status": "1"}
                    )
                    assert (
                        foreign_change.status_code == 200 and foreign_change.json()["code"] != 200
                    )
                    assert "不能跨业务租户" in foreign_change.json().get("msg", "")
                    with admin.cursor() as cursor:
                        cursor.execute("SELECT status FROM sys_user WHERE user_id=2")
                        assert cursor.fetchone()[0] == "0"
                        cursor.execute(
                            "SELECT revision FROM orbit_directory_clock WHERE tenant_id=%s",
                            (other_tenant,),
                        )
                        assert cursor.fetchone()[0] == 1
                        cases.append(
                            "pythonNativeAdminCannotCrossBusinessTenantViaOriginalUserMenu"
                        )
                        cursor.execute("SELECT role_id FROM sys_user_role WHERE user_id=2")
                        profile_roles = [row[0] for row in cursor.fetchall()]
                        cursor.execute("SELECT nick_name,dept_id FROM sys_user WHERE user_id=2")
                        prior_name, prior_dept = cursor.fetchone()
                    profile_change = client.put(
                        "/system/user",
                        headers=headers,
                        json={
                            "userId": 2,
                            "userName": regular_name,
                            "nickName": "越租户编辑不得成功",
                            "deptId": prior_dept,
                            "roleIds": profile_roles,
                            "postIds": [],
                        },
                    )
                    assert (
                        profile_change.status_code != 200
                        or profile_change.json().get("code") != 200
                    )
                    with admin.cursor() as cursor:
                        cursor.execute("SELECT nick_name FROM sys_user WHERE user_id=2")
                        assert cursor.fetchone()[0] == prior_name
                        cases.append("pythonNativeProfileOnlyEditCannotCrossBusinessTenant")
                        cursor.execute(
                            "INSERT INTO sys_user"
                            "(user_id,user_name,nick_name,password,status,dept_id) "
                            "SELECT 999005,'identity-security-event','身份隔离测试',"
                            "password,'0',dept_id "
                            "FROM sys_user WHERE user_id=2"
                        )
                        cursor.execute(
                            "INSERT INTO sys_identity_subject"
                            "(user_id,subject_id,auth_version,create_time) "
                            "VALUES(999005,%s,1,UTC_TIMESTAMP(3))",
                            (str(uuid.uuid4()),),
                        )
                        cursor.execute(
                            "INSERT INTO sys_role"
                            "(role_id,role_name,role_key,role_sort,data_scope,status,del_flag) "
                            "VALUES(991005,'原系统权限测试','fixture-native-admin',5,'1','0','0')"
                        )
                        cursor.execute(
                            "INSERT INTO sys_user_role(user_id,role_id) VALUES(999005,991005)"
                        )
                        # 补人员动作，使后续确实到达内置保护，而非只验证前置权限拒绝。
                        cursor.execute(
                            "INSERT INTO sys_user_role(user_id,role_id) VALUES(999005,%s)",
                            (user_fixture["native_role"],),
                        )
                        cursor.execute(
                            "INSERT INTO sys_role_menu(role_id,menu_id) SELECT 991005,menu_id "
                            "FROM sys_menu WHERE perms LIKE 'system:user:%' OR menu_id IN(1,100)"
                        )
                        cursor.execute(
                            "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) "
                            "VALUES(999005,%s,'SUPER_ADMIN')",
                            (tenant,),
                        )
                        cursor.execute(
                            "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id) "
                            "VALUES(%s,%s,999005,%s)",
                            (tenant, str(uuid.uuid4()), tenant),
                        )
                        cursor.execute("SELECT password FROM sys_user WHERE user_id=2")
                        original_password_hash = cursor.fetchone()[0]
                    sentinel_login = fixture_login(
                        client,
                        cache,
                        {
                            "username": "identity-security-event",
                            "password": password,
                            "code": "",
                            "uuid": "",
                        },
                    )
                    assert sentinel_login.status_code == 200 and sentinel_login.json().get("token")
                    sentinel_headers = {"Authorization": "Bearer " + sentinel_login.json()["token"]}
                    changed_password = client.put(
                        "/system/user/resetPwd",
                        headers=sentinel_headers,
                        json={"userId": 2, "password": secrets.token_urlsafe(9) + "Aa1!"},
                    )
                    assert (
                        changed_password.status_code == 200
                        and changed_password.json()["code"] != 200
                    )
                    assert "不能跨业务租户" in changed_password.json().get("msg", "")
                    with admin.cursor() as cursor:
                        cursor.execute("SELECT password FROM sys_user WHERE user_id=2")
                        assert cursor.fetchone()[0] == original_password_hash
                    cases.append("pythonNativeReservedLookingUsernameCannotBypassTenantGuard")
                    stripped = client.put(
                        "/system/user/authRole",
                        headers=sentinel_headers,
                        params={"userId": "1", "roleIds": "2"},
                    )
                    assert stripped.status_code == 200 and stripped.json()["code"] != 200
                    assert "内置管理员" in stripped.json().get("msg", "")
                    with admin.cursor() as cursor:
                        cursor.execute(
                            "SELECT role_id FROM sys_user_role WHERE user_id=1 ORDER BY role_id"
                        )
                        assert cursor.fetchall() == ((1,),)
                finally:
                    with admin.cursor() as cursor:
                        cursor.execute(
                            "UPDATE orbit_user_scope SET tenant_id=%s WHERE user_id=2", (tenant,)
                        )
                cases.append("pythonNativeRoleAssignmentCannotStripBootstrapAdministrator")
                concurrent_write = write | {"name": "并发创建只成功一次"}

                def same_create(_):
                    return client.post(
                        base,
                        headers=headers | {"Idempotency-Key": "fixture-concurrent-key"},
                        json=concurrent_write,
                    )

                with ThreadPoolExecutor(max_workers=4) as pool:
                    responses = list(pool.map(same_create, range(4)))
                assert all(response.status_code == 200 for response in responses)
                created_ids = {response.json()["id"] for response in responses}
                assert len(created_ids) == 1
                concurrent_id = next(iter(created_ids))
                with admin.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(*) FROM orbit_configuration_audit WHERE config_id=%s",
                        (concurrent_id,),
                    )
                    assert cursor.fetchone()[0] == 1
                    cursor.execute(
                        "SELECT COUNT(*) FROM orbit_configuration_outbox WHERE config_id=%s",
                        (concurrent_id,),
                    )
                    assert cursor.fetchone()[0] == 1

                def same_revision(index):
                    return client.put(
                        base + "/" + concurrent_id,
                        headers=headers
                        | {"Idempotency-Key": f"fixture-cas-{index}", "If-Match": '"1"'},
                        json=concurrent_write
                        | {
                            "name": f"并发版本{index}",
                            "secrets": {"apiKey": {"operation": "KEEP"}},
                        },
                    )

                with ThreadPoolExecutor(max_workers=2) as pool:
                    responses = list(pool.map(same_revision, range(2)))
                assert sorted(response.status_code for response in responses) == [200, 409]
                assert (
                    client.get(base + "/" + concurrent_id, headers=headers).json()["revision"] == 2
                )
                with admin.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(*) FROM orbit_configuration_audit WHERE config_id=%s",
                        (concurrent_id,),
                    )
                    assert cursor.fetchone()[0] == 2
                    cursor.execute(
                        "SELECT COUNT(*) FROM orbit_configuration_idempotency "
                        "WHERE request_key LIKE 'fixture-cas-%%'"
                    )
                    assert cursor.fetchone()[0] == 1
                cases.append("pythonConfigurationConcurrentSameKeyAndRevisionCas")
                probe_path = base + "/" + concurrent_id + "/test"
                probe_headers = headers | {"If-Match": '"2"'}
                for payload, status in [
                    ({}, 400),
                    ({"reason": 1}, 400),
                    ({"reason": "\n"}, 422),
                    ({"reason": "正常", "tenant_id": "forged"}, 400),
                ]:
                    assert (
                        client.post(probe_path, headers=probe_headers, json=payload).status_code
                        == status
                    )
                tested = client.post(
                    probe_path, headers=probe_headers, json={"reason": "人工只读核验"}
                )
                assert tested.status_code == 200
                assert tested.json()["result"]["status"] == "READ_VERIFIED"
                assert tested.json()["configuration"]["revision"] == 3
                assert "fixture-model-key" not in tested.text
                assert (
                    client.post(
                        probe_path, headers=probe_headers, json={"reason": "旧版本测试"}
                    ).status_code
                    == 409
                )
                with admin.cursor() as cursor:
                    cursor.execute(
                        "SELECT action,reason,revision FROM orbit_configuration_audit "
                        "WHERE config_id=%s ORDER BY revision DESC LIMIT 1",
                        (concurrent_id,),
                    )
                    assert cursor.fetchone() == ("READ_TEST", "人工只读核验", 3)
                    cursor.execute(
                        "CREATE TRIGGER orbit_py_probe_fail BEFORE INSERT "
                        "ON orbit_configuration_outbox FOR EACH ROW "
                        "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='probe fixture rejection'"
                    )
                try:
                    failed = client.post(
                        probe_path,
                        headers=headers | {"If-Match": '"3"'},
                        json={"reason": "验证失败原子回滚"},
                    )
                    assert failed.status_code == 503
                finally:
                    with admin.cursor() as cursor:
                        cursor.execute("DROP TRIGGER orbit_py_probe_fail")
                assert (
                    client.get(base + "/" + concurrent_id, headers=headers).json()["revision"] == 3
                )
                with admin.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(*) FROM orbit_configuration_audit WHERE config_id=%s",
                        (concurrent_id,),
                    )
                    assert cursor.fetchone()[0] == 3
                    cursor.execute(
                        "SELECT COUNT(*) FROM orbit_configuration_outbox WHERE config_id=%s",
                        (concurrent_id,),
                    )
                    assert cursor.fetchone()[0] == 3
                cases.append("pythonConfigurationReadOnlyProbeCasAuditAndFailureRollback")
                provider_settings = {
                    "AI_CLAUDE": ({"model": "fixture-claude"}, "apiKey"),
                    "META_APP": ({"appId": "000123", "graphVersion": "v25.0"}, "appSecret"),
                    "META_BM": ({"businessId": "000456", "graphVersion": "v25.0"}, "accessToken"),
                }
                sections = [
                    section["key"]
                    for section in client.get(path, headers=headers).json()["sections"]
                ]
                for section in sections:
                    if section == "AI_GPT":
                        continue
                    settings, slot = provider_settings.get(section, ({}, None))
                    payload = {
                        "section": section,
                        "name": "类型只读探测" + section,
                        "enabled": slot is not None,
                        "settings": settings,
                        "reason": "只读适配专项",
                        "secrets": {slot: {"operation": "REPLACE", "value": "fixture-provider-key"}}
                        if slot
                        else {},
                    }
                    created = client.post(
                        base,
                        headers=headers | {"Idempotency-Key": "fixture-provider-" + section},
                        json=payload,
                    )
                    assert created.status_code == 200, section
                    tested = client.post(
                        base + "/" + created.json()["id"] + "/test",
                        headers=headers | {"If-Match": '"1"'},
                        json={"reason": "逐类型只读验证"},
                    )
                    assert tested.status_code == 200, section
                    assert tested.json()["result"]["status"] == (
                        "READ_VERIFIED" if slot else "BLOCKED"
                    )
                    assert tested.json()["configuration"]["revision"] == 2
                    assert "fixture-provider-key" not in tested.text
                cases.append("pythonConfigurationProbeFourProvidersAndUnsupportedSections")
                policy = {
                    "section": "AI_SUGGESTIONS",
                    "name": "建议策略有效引用",
                    "enabled": True,
                    "settings": {"providerConfigId": record["id"]},
                    "secrets": {},
                    "reason": "提供商引用专项",
                }
                linked = client.post(
                    base, headers=headers | {"Idempotency-Key": "fixture-policy-valid"}, json=policy
                )
                assert linked.status_code == 200
                disabled = client.post(
                    base,
                    headers=headers | {"Idempotency-Key": "fixture-policy-disabled"},
                    json={
                        "section": "AI_GPT",
                        "name": "不可用于启用策略",
                        "enabled": False,
                        "settings": {},
                        "secrets": {},
                        "reason": "停用提供商夹具",
                    },
                )
                assert disabled.status_code == 200
                with admin.cursor() as cursor:
                    cursor.execute("SELECT id FROM orbit_system_configuration WHERE section='OIDC'")
                    wrong_type_id = cursor.fetchone()[0]
                for index, (provider_id, status) in enumerate(
                    [
                        (other_id, 404),
                        (str(uuid.uuid4()), 404),
                        (wrong_type_id, 422),
                        (disabled.json()["id"], 422),
                    ]
                ):
                    rejected = client.post(
                        base,
                        headers=headers | {"Idempotency-Key": f"fixture-policy-invalid-{index}"},
                        json=policy
                        | {
                            "name": "无效策略引用" + str(index),
                            "settings": {"providerConfigId": provider_id},
                        },
                    )
                    assert rejected.status_code == status
                with admin.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(*) FROM orbit_configuration_idempotency "
                        "WHERE request_key LIKE 'fixture-policy-invalid-%%'"
                    )
                    assert cursor.fetchone()[0] == 0
                cases.append("pythonAiStrategyProviderReferenceVisibilityAndAvailability")
                for scenario in ("revoke", "update", "session"):
                    fresh = client.post(
                        base,
                        headers=headers | {"Idempotency-Key": "fixture-probe-" + scenario},
                        json=write
                        | {
                            "name": "探测并发" + scenario,
                            "settings": {"model": "fixture-wait-model"},
                        },
                    )
                    assert fresh.status_code == 200
                    fresh_id = fresh.json()["id"]
                    endpoint = base + "/" + fresh_id
                    probe_headers = headers
                    if scenario == "session":
                        actor_login = fixture_login(
                            client, cache, {"username": regular_name, "password": password}
                        )
                        assert actor_login.status_code == 200 and actor_login.json().get("token")
                        probe_headers = {"Authorization": "Bearer " + actor_login.json()["token"]}
                        assert client.get(endpoint, headers=probe_headers).status_code == 200
                    cache.delete("orbit-fixture-probe-entered", "orbit-fixture-probe-release")
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        pending = pool.submit(
                            client.post,
                            endpoint + "/test",
                            headers=probe_headers | {"If-Match": '"1"'},
                            json={"reason": "探测期间改变授权或配置"},
                        )
                        deadline = time.monotonic() + 5
                        while not cache.get("orbit-fixture-probe-entered"):
                            assert time.monotonic() < deadline, "探测未进入受控传输"
                            time.sleep(0.02)
                        try:
                            if scenario == "revoke":
                                with admin.cursor() as cursor:
                                    cursor.execute("SET SESSION innodb_lock_wait_timeout=2")
                                    cursor.execute(
                                        "UPDATE orbit_user_scope SET enabled=0 WHERE user_id=1"
                                    )
                            elif scenario == "session":
                                for status in ("1", "0"):
                                    changed = client.put(
                                        native_status_path,
                                        headers=headers,
                                        json={"userId": 2, "status": status},
                                    )
                                    assert (
                                        changed.status_code == 200 and changed.json()["code"] == 200
                                    )
                            else:
                                altered = client.put(
                                    endpoint,
                                    headers=headers
                                    | {
                                        "If-Match": '"1"',
                                        "Idempotency-Key": "fixture-probe-inflight-update",
                                    },
                                    json=write
                                    | {
                                        "name": "探测期间已修改",
                                        "settings": {"model": "new-model"},
                                        "secrets": {"apiKey": {"operation": "KEEP"}},
                                    },
                                )
                                assert altered.status_code == 200, "探测期间不应持有配置行锁"
                        finally:
                            cache.set("orbit-fixture-probe-release", "1", ex=10)
                        rejected_probe = pending.result(timeout=10)
                    try:
                        assert (
                            rejected_probe.status_code
                            == {"revoke": 403, "update": 409, "session": 401}[scenario]
                        )
                        if scenario == "session":
                            assert client.get(endpoint, headers=probe_headers).status_code == 401
                            renewed = fixture_login(
                                client, cache, {"username": regular_name, "password": password}
                            )
                            assert renewed.status_code == 200 and renewed.json().get("token")
                            assert (
                                client.get(
                                    endpoint,
                                    headers={"Authorization": "Bearer " + renewed.json()["token"]},
                                ).status_code
                                == 200
                            )
                            renewed_headers = {"Authorization": "Bearer " + renewed.json()["token"]}
                            with admin.cursor() as cursor:
                                cursor.execute("SELECT nick_name FROM sys_user WHERE user_id=2")
                                old_nickname = cursor.fetchone()[0]
                            for nickname in ("本人资料仍可编辑", old_nickname):
                                own_profile = client.put(
                                    "/system/user/profile",
                                    headers=renewed_headers,
                                    json={"nickName": nickname},
                                )
                                assert (
                                    own_profile.status_code == 200
                                    and own_profile.json()["code"] == 200
                                )
                        with admin.cursor() as cursor:
                            cursor.execute(
                                "SELECT COUNT(*) FROM orbit_configuration_audit "
                                "WHERE config_id=%s AND action='READ_TEST'",
                                (fresh_id,),
                            )
                            assert cursor.fetchone()[0] == 0
                            cursor.execute(
                                "SELECT verification_status FROM orbit_system_configuration "
                                "WHERE id=%s",
                                (fresh_id,),
                            )
                            assert cursor.fetchone()[0] == "UNTESTED"
                    finally:
                        with admin.cursor() as cursor:
                            cursor.execute("UPDATE orbit_user_scope SET enabled=1 WHERE user_id=1")
                    cases.append(
                        {
                            "revoke": "pythonProbeInFlightRevocationRejectsResult",
                            "update": "pythonProbeInFlightUpdateRejectsStaleResult",
                            "session": "pythonProbeInFlightSessionEpochRejectsReenabledActor",
                        }[scenario]
                    )
                    if scenario == "session":
                        cases.append("pythonNativeSelfProfileRemainsUsableAfterSessionRenewal")
                run_user_create_checks(client, admin, headers, user_fixture, cases)
                result["user_update_login_cooldown_seconds"] = run_user_update_checks(
                    client, admin, headers, user_fixture, password, cache, cases
                )
                result["native_role_batch_boundary"] = run_native_user_role_checks(
                    client, admin, headers, user_fixture, cases
                )
                run_team_session_checks(
                    client, admin, headers, user_fixture, password, cache, cases
                )
                run_native_directory_checks(client, admin, headers, user_fixture, cases)
                run_invitation_checks(
                    client,
                    admin,
                    headers,
                    user_fixture,
                    cases,
                    values["ORBIT_PYTHON_SECRETS_KEYS"],
                    idp,
                    database,
                    password,
                    cache,
                    values,
                )
                if args.migration_through >= 11:
                    result["reference_channel_fixture"] = run_reference_channel_checks(
                        client, admin, headers, user_fixture, cases
                    )
                    if args.include_channel_fields:
                        run_channel_field_contract_checks(
                            client,
                            admin,
                            headers,
                            result["reference_channel_fixture"],
                            cases,
                            ROOT / "docs/orbit/baseline/contracts/openapi-current.json",
                        )
                    run_reference_channel_scope_checks(
                        client, admin, headers, user_fixture, password, cache, cases
                    )
                    if args.include_channel_scope:
                        run_channel_scope_matrix_checks(
                            client, admin, headers, user_fixture, password, cache, cases
                        )
                if args.include_materials:
                    run_material_checks(
                        client,
                        admin,
                        database,
                        headers,
                        values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"],
                        cases,
                        scanner=material_scanner,
                    )
                    if args.include_material_video:
                        run_material_video_checks(
                            client,
                            admin,
                            database,
                            headers,
                            values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"],
                            cases,
                            args.material_video_bin,
                            runtime_profile=runtime_profile_payload,
                        )
                if args.include_accounts:
                    if args.include_account_alias_snapshots:
                        import_identity, owner, team, vendor = prepare_account_alias_fixture(
                            client, admin, headers, password, cache
                        )
                    else:
                        owner, team, vendor = prepare_account_import_fixture(client, admin, headers)
                    run_account_import_checks(client, admin, headers, owner, team, vendor, cases)
                    if args.include_account_worker or args.include_account_details:
                        from orbit_api.credentials import CredentialCipher

                        account_cipher = CredentialCipher(
                            "fixture", values["ORBIT_PYTHON_SECRETS_KEYS"]
                        )
                    if args.include_account_worker:
                        run_account_worker_checks(
                            client,
                            admin,
                            headers,
                            account_cipher,
                            owner,
                            team,
                            vendor,
                            database,
                            cases,
                        )
                    if args.include_account_details:
                        run_account_details_checks(
                            client,
                            admin,
                            headers,
                            1,
                            owner,
                            team,
                            vendor,
                            database,
                            cases,
                            account_cipher,
                        )
                    if args.include_account_alias_snapshots:
                        run_account_alias_snapshot_checks(
                            client, admin, headers, import_identity, vendor, database, cases
                        )
            if args.include_channel_owners and not args.channel_owners_only:
                result["channel_owners_fixture"] = run_channel_owners_500_checks(
                    client, admin, headers, user_fixture, password, cache, cases
                )
            if args.include_material_lifecycle:
                run_material_lifecycle_checks(
                    admin, database, values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"], cases
                )
            if args.include_material_lifecycle_recovery:
                run_material_lifecycle_recovery_checks(
                    admin, database, values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"], cases
                )
            if args.launch_naming_only:
                user_fixture = run_user_checks(client, admin, headers, password, cases)
            if args.include_launch_naming or args.launch_naming_only:
                run_launch_naming_checks(client, admin, headers, user_fixture, cases)
            if args.include_material_runtime_store:
                run_material_runtime_store_checks(admin, database, cases)
            if args.include_material_runtime_worker:
                run_material_runtime_worker_checks(
                    admin, database, values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"], cases
                )
            if args.include_launch_scope_consumption:
                run_launch_scope_consumption_checks(client, admin, headers, user_fixture, cases)
            if args.account_scope_visibility_plan_only:
                result["account_scope_visibility_plan"] = run_account_scope_visibility_plan_checks(
                    client, admin, headers, password, cache, database, cases
                )
            if args.launch_validation_only:
                from orbit_api.credentials import CredentialCipher

                result["launch_validation"] = run_launch_validation_checks(
                    client,
                    admin,
                    headers,
                    password,
                    cache,
                    database,
                    cases,
                    include_provider=args.include_launch_validation_provider,
                    cipher=CredentialCipher("fixture", values["ORBIT_PYTHON_SECRETS_KEYS"]),
                    control_dir=launch_validation_control,
                )
                if args.include_launch_allocation_http:
                    result["launch_allocation_http"] = run_launch_allocation_http_checks(
                        client, admin, headers, database, cases
                    )
                if args.include_launch_allocation_http_provider:
                    result["launch_allocation_http_provider"] = (
                        run_launch_allocation_http_provider_checks(
                            client, admin, headers, database, cases
                        )
                    )
                if args.include_launch_execution_http:
                    result["launch_execution_http"] = run_launch_execution_http_checks(
                        client, admin, headers, database, cases
                    )
                if args.include_launch_execution_provider:
                    result["launch_execution"] = run_launch_execution_checks(
                        client,
                        admin,
                        headers,
                        password,
                        cache,
                        database,
                        cases,
                        control_dir=launch_validation_control,
                        cipher=CredentialCipher("fixture", values["ORBIT_PYTHON_SECRETS_KEYS"]),
                    )
                if args.include_metric_profile_registry:
                    result["metric_profile_registry"] = run_metric_profile_registry_checks(
                        admin, database, cases
                    )
                if args.include_metric_profile_references:
                    result["metric_profile_references"] = run_metric_profile_reference_checks(
                        client, admin, headers, password, cache, database, cases
                    )
                if args.include_template_current_scope:
                    result["template_current_scope"] = run_template_current_scope_checks(
                        client, admin, headers, password, cache, database, cases
                    )
                if args.include_template_current_scope:
                    result["launch_replay_concurrency"] = run_launch_replay_concurrency_checks(
                        client, admin, headers, database, cases
                    )
                if args.include_template_metric_references:
                    result["template_metric_references"] = run_template_metric_reference_checks(
                        client, admin, headers, password, cache, database, cases
                    )
                if args.include_metric_profile_query:
                    result["metric_profile_query"] = run_metric_profile_query_checks(
                        client, admin, headers, password, cache, database, cases
                    )
                if args.include_launch_execution_guards:
                    result["launch_execution_guards"] = run_launch_execution_guard_checks(
                        client, admin, headers, password, cache, database, cases
                    )
            if args.launch_allocation_runtime_only:
                result["launch_allocation_runtime"] = run_launch_allocation_runtime_checks(
                    admin, database, cases
                )
            if args.material_scanner_owner_store_only:
                result["material_scanner_owner_store"] = run_material_scanner_owner_store_checks(
                    admin, database, cases
                )
                if args.include_material_scanner_owner_native:
                    result["material_scanner_owner_native"] = (
                        run_material_scanner_owner_native_checks(admin, database, cases)
                    )
                if args.include_material_scanner_supervisor_native:
                    supervisor_result = run_material_scanner_supervisor_checks(
                        admin, database, values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"], cases
                    )
                    supervisor_cleanup_verified = supervisor_result.get("cleanup_complete") is True
                    if not supervisor_cleanup_verified:
                        raise ValueError("监督器未证明所有自有任务和进程已结束，保留夹具待核对")
                    result["material_scanner_supervisor"] = supervisor_result
                if args.include_material_worker_cli_native:
                    cli_result = run_material_worker_cli_checks(
                        admin, database, values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"], values, cases
                    )
                    worker_cli_cleanup_verified = cli_result.get("cleanup_complete") is True
                    if not worker_cli_cleanup_verified:
                        raise ValueError("CLI未证明所有自有任务和进程已结束，保留夹具待核对")
                    result["material_worker_cli"] = cli_result
            if args.task_event_stream_only:
                result["task_event_stream"] = run_task_event_stream_checks(
                    client, admin, headers, password, cache, database, cases
                )
                if args.include_task_event_cookie:
                    result["task_event_cookie"] = run_task_event_cookie_checks(
                        client, admin, headers, database, idp, cases
                    )
                if args.include_task_event_boundaries:
                    from orbit_api.credentials import CredentialCipher

                    result["task_event_boundaries"] = run_task_event_boundary_checks(
                        client,
                        admin,
                        headers,
                        password,
                        cache,
                        database,
                        cases,
                        cipher=CredentialCipher("fixture", values["ORBIT_PYTHON_SECRETS_KEYS"]),
                    )
                if args.include_task_event_integrity:
                    result["task_event_integrity"] = run_task_event_integrity_checks(
                        client, admin, headers, database, cases
                    )
            if args.identity_summary_only:
                from orbit_api.credentials import CredentialCipher

                result["identity_summary"] = run_identity_publication_summary_checks(
                    client,
                    admin,
                    headers,
                    password,
                    cache,
                    database,
                    cases,
                    cipher=CredentialCipher("fixture", values["ORBIT_PYTHON_SECRETS_KEYS"]),
                    prepare_browser_fixture=args.browser,
                    prepare_capacity=args.include_identity_summary_capacity,
                    prepare_http_profile=args.include_identity_summary_profile,
                    backend_pid=child.pid if args.include_identity_summary_capacity else None,
                )
            if args.execution_candidate_only:
                result["execution_candidate"] = run_execution_candidate_checks(
                    client, admin, headers, password, cache, database, cases
                )
            if args.execution_recovery_scanner_only:
                result["execution_recovery_scanner"] = run_execution_recovery_scanner_checks(
                    client,
                    admin,
                    headers,
                    password,
                    cache,
                    database,
                    cases,
                    include_service=args.include_execution_recovery_service,
                )
            if args.metric_query_result_only:
                result["metric_query_result"] = run_metrics_query_result_checks(
                    client, admin, headers, password, cache, database, cases
                )
                if args.include_metric_query_http:
                    result["metric_query_http"] = run_metrics_http_checks(
                        client, admin, headers, password, cache, database, cases
                    )
                if args.include_metrics_browser_fixture:
                    result["metrics_public_fixture"] = run_metrics_public_fixture_checks(
                        client,
                        admin,
                        headers,
                        password,
                        cache,
                        database,
                        cases,
                        destination=metrics_fixture_control,
                    )
            if args.scope_create_profile_only:
                result["scope_create_profile"] = run_scope_create_profile_checks(
                    client,
                    admin,
                    headers,
                    password,
                    cache,
                    database,
                    cases,
                    diagnostic_dir=scope_diagnostic_dir,
                )
            if args.rules_only and not args.rules_definition_browser:
                result["rule_definitions"] = run_rule_definition_checks(
                    client, admin, headers, password, cache, database, cases
                )
                if args.include_rule_editor:
                    result["rule_editor"] = run_rule_editor_checks(
                        client, admin, headers, password, cache, database, cases
                    )
                if args.include_rule_editor_scopes:
                    result["rule_editor_scopes"] = run_rule_editor_scope_checks(
                        client, admin, headers, password, cache, database, cases
                    )
                if args.include_rule_scope_consumer:
                    result["rule_scope_consumer"] = run_rule_scope_consumer_checks(
                        client, admin, headers, password, cache, database, cases
                    )
                if args.include_rule_editor_definition:
                    result["rule_editor_definition"] = run_rule_editor_definition_checks(
                        client, admin, headers, password, cache, database, cases
                    )
                if args.include_rule_schedule_preview:
                    result["rule_schedule_preview"] = run_rule_schedule_preview_checks(
                        client, admin, headers, password, cache, database, cases
                    )
                if args.include_rule_scope_options:
                    result["rule_scope_options"] = run_rule_scope_options_checks(
                        client, admin, headers, password, cache, database, cases
                    )
                if args.include_rule_simulation_schema:
                    result["rule_simulation_schema"] = run_rule_simulation_schema_checks(
                        client, admin, headers, password, cache, database, cases
                    )
                if args.include_rule_definition_boundaries:
                    result["rule_definition_boundaries"] = run_rule_definition_boundary_checks(
                        client, admin, headers, password, cache, database, cases
                    )
                if args.include_rule_simulation_access:
                    result["rule_simulation_access"] = run_rule_simulation_access_checks(
                        client, admin, headers, password, cache, database, cases
                    )
                if args.include_rule_simulation_calendar:
                    result["rule_simulation_calendar"] = run_rule_simulation_calendar_checks(
                        client, admin, headers, password, cache, database, cases
                    )
                if args.rules_internal_browser:
                    from rules_internal_browser_checkpoint import (
                        run_rules_internal_browser_checkpoint,
                    )

                    result["rules_internal_browser"] = run_rules_internal_browser_checkpoint(
                        admin, database, password
                    )
            if args.rules_definition_browser:
                from rules_internal_browser_checkpoint import run_rules_internal_browser_checkpoint

                result["rule_browser_fixture"] = prepare_rule_definition_browser(
                    client, admin, headers, database, cases
                )
                print(
                    json.dumps({"rule_browser_fixture": result["rule_browser_fixture"]}),
                    flush=True,
                )
                if args.include_rule_display_metadata:
                    result["rule_definition_flow"] = run_rules_definition_flow_checks(
                        client, admin, headers, password, cache, database, cases
                    )
                if args.include_rule_recovery_context:
                    result["rule_recovery_context"] = run_rule_recovery_context_checks(
                        client,
                        admin,
                        headers,
                        password,
                        cache,
                        database,
                        cases,
                        keys=values["ORBIT_PYTHON_SECRETS_KEYS"],
                    )
                if args.include_account_current_channel:
                    result["account_current_channel"] = run_channel_checks(
                        client,
                        admin,
                        headers,
                        database,
                        cases,
                        result["rule_browser_fixture"],
                        password,
                        cache,
                    )
                    print(
                        json.dumps({"account_current_channel": result["account_current_channel"]}),
                        flush=True,
                    )
                if args.rules_internal_browser:
                    result["rules_internal_browser"] = run_rules_internal_browser_checkpoint(
                        admin, database, password
                    )
            if args.metric_query_read_only:
                result["metric_query_read"] = run_metrics_query_read_checks(
                    client, admin, headers, password, cache, database, cases
                )
            if args.identity_publication_only:
                from orbit_api.credentials import CredentialCipher

                result["identity_publication"] = run_identity_publication_checks(
                    client,
                    admin,
                    headers,
                    password,
                    cache,
                    database,
                    cases,
                    cipher=CredentialCipher("fixture", values["ORBIT_PYTHON_SECRETS_KEYS"]),
                    prepare_browser_fixture=args.browser,
                    include_inventory_boundaries=args.include_identity_inventory_boundaries,
                    launch_draft_hook=(
                        LaunchIdentityDraftChecks() if args.include_launch_identity_drafts else None
                    ),
                )
            if args.metrics_scope_only:
                result["metric_scope"] = run_metric_scope_checks(
                    client, admin, headers, password, cache, database, cases
                )
                if args.include_metric_fact_schema:
                    result["metric_fact_schema"] = run_metric_fact_schema_checks(
                        admin, database, cases
                    )
                if args.include_metrics_expected_manifest:
                    run_metrics_expected_manifest_checks(admin, database, cases)
            if args.meta_observation_registry_only:
                from orbit_api.credentials import CredentialCipher

                result["meta_observation_registry"] = run_meta_observation_registry_checks(
                    client,
                    admin,
                    headers,
                    password,
                    cache,
                    database,
                    cases,
                    cipher=CredentialCipher("fixture", values["ORBIT_PYTHON_SECRETS_KEYS"]),
                    include_identity_facts=args.include_meta_identity_facts,
                )
                if args.include_meta_receipt_bounds:
                    result["meta_receipt_bounds"] = run_meta_receipt_bounds_checks(
                        admin, database, cases
                    )
            if args.execution_lease_only:
                result["execution_lease"] = run_execution_lease_checks(
                    client,
                    admin,
                    headers,
                    password,
                    cache,
                    database,
                    cases,
                )
                if args.include_execution_lease_store:
                    result["execution_lease_store"] = run_execution_lease_store_checks(
                        client,
                        admin,
                        headers,
                        password,
                        cache,
                        database,
                        cases,
                        include_append=args.include_execution_fact_append,
                    )
                if args.include_execution_recovery:
                    result["execution_recovery"] = run_execution_recovery_checks(
                        client, admin, headers, password, cache, database, cases
                    )
            if args.task_core_only:
                result["task_core"] = run_task_core_checks(
                    client,
                    admin,
                    headers,
                    password,
                    cache,
                    database,
                    cases,
                    include_capacity=args.include_task_core_capacity,
                )
                if args.include_launch_plan_source:
                    result["launch_plan_source"] = run_launch_plan_source_checks(
                        admin, database, cases
                    )
            if args.material_scanner_configuration_only:
                result["material_scanner_configuration"] = (
                    run_material_scanner_configuration_checks(
                        client,
                        admin,
                        headers,
                        database,
                        values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"],
                        cases,
                        registry=material_scanner_registry,
                    )
                )
                if args.include_launch_allocation_references:
                    user_fixture = run_user_checks(client, admin, headers, password, cases)
                    result["launch_allocation_references"] = run_launch_allocation_reference_checks(
                        client,
                        admin,
                        headers,
                        database,
                        cases,
                        object_root=values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"],
                        registry=material_scanner_registry,
                        user_fixture=user_fixture,
                    )
                if args.include_launch_execution_material_references:
                    user_fixture = run_user_checks(client, admin, headers, password, cases)
                    result["launch_execution_material_references"] = (
                        run_launch_execution_material_bridge_checks(
                            client,
                            admin,
                            headers,
                            database,
                            cases,
                            object_root=values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"],
                            registry=material_scanner_registry,
                            user_fixture=user_fixture,
                        )
                    )
                if args.include_material_scanner_configuration_scope:
                    user_fixture = run_user_checks(client, admin, headers, password, cases)
                    run_material_scanner_configuration_scope_checks(
                        client,
                        admin,
                        headers,
                        user_fixture,
                        password,
                        cache,
                        database,
                        values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"],
                        cases,
                        registry=material_scanner_registry,
                    )
            if args.include_material_security and not args.browser_only:
                run_material_security_checks(
                    client,
                    admin,
                    database,
                    headers,
                    values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"],
                    material_scanner,
                    cases,
                )
            if args.include_material_security_scope:
                run_material_security_scope_checks(
                    client,
                    admin,
                    database,
                    headers,
                    values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"],
                    material_scanner,
                    user_fixture,
                    password,
                    cache,
                    cases,
                )
            if args.include_material_infected_memory_worker:
                run_material_antivirus_memory_worker_checks(
                    admin, database, material_scanner, cases
                )
            if args.include_launch_drafts and not (
                args.launch_drafts_only or args.template_recipients_only
            ):
                run_launch_draft_template_checks(
                    client, admin, headers, user_fixture, password, cache, cases
                )
            if args.include_template_recipients:
                run_template_recipient_checks(
                    client, admin, headers, user_fixture, password, cache, cases
                )
            if args.include_material_lifecycle_races:
                run_material_lifecycle_race_checks(
                    values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"], cases
                )
                run_material_lifecycle_http_race_checks(
                    client,
                    admin,
                    database,
                    headers,
                    values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"],
                    cases,
                )
            if args.include_material_taxonomy_scope and not args.material_taxonomy_scope_only:
                run_material_taxonomy_scope_checks(
                    client, admin, headers, user_fixture, password, cache, cases
                )
            if args.include_vendor_alias and not args.vendor_alias_only:
                run_vendor_alias_checks(
                    client, admin, headers, user_fixture, password, cache, cases
                )
            if args.include_material_taxonomy:
                run_material_taxonomy_migration_checks(admin, database, cases)
                run_material_taxonomy_query_checks(client, headers, cases)
                run_material_schema_checks(client, headers, cases)
            result["additional_fixture_login_wait_seconds"] = list(LOGIN_WAIT_SECONDS)
            if args.browser:
                if args.browser_module == "launch-metric-profiles":
                    from launch_metric_browser_fixture import prepare_launch_metric_browser_fixture

                    launch_metric_fixture = prepare_launch_metric_browser_fixture(admin, database)
                    result["launch_metric_browser_fixture"] = {
                        "profile_count": launch_metric_fixture["profile_count"],
                        "writer_permissions": ["launch.read", "launch.create", "launch.edit"],
                        "monitor_read": False,
                    }
                if args.browser_module == "metric-profiles":
                    from metric_profile_query_checks import seed_metric_profile_browser_fixture

                    seeded_profiles = seed_metric_profile_browser_fixture(admin, database)
                    result["metric_profile_browser_fixture"] = {
                        "count": len(seeded_profiles["ids"])
                    }
                if args.browser_module == "launch":
                    from launch_account_scope_browser_fixture import (
                        prepare_launch_account_scope_browser_fixture,
                    )
                    from launch_pagination_browser_fixture import (
                        prepare_launch_pagination_browser_fixture,
                    )

                    result["launch_pagination_browser_fixture"] = (
                        prepare_launch_pagination_browser_fixture(admin, database)
                    )
                    result["launch_account_scope_browser_fixture"] = (
                        prepare_launch_account_scope_browser_fixture(admin, database)
                    )
                # HTTP专项与浏览器独立验证，不能消耗彼此的匿名登录限流额度。
                # 保留生产12次/分钟限制；只观察专属DB15的已知登录窗口，等待自然过期。
                cooldown_started = time.monotonic()
                deadline = cooldown_started + 65
                # 快速专项只登录夹具1次及三个视口各1次，未触及原12次/分钟限制。
                # 完整回归曾消耗其他登录额度，仍等待原窗口自然过期，不清空或调低限流。
                while not (
                    args.browser_only
                    or args.material_scanner_configuration_only
                    or args.task_core_only
                ) and list(cache.scan_iter(match="api_rate_limit:login:sliding_window:*")):
                    assert time.monotonic() < deadline, "独立登录限流窗口未按原60秒策略过期"
                    time.sleep(0.5)
                result["browser_login_cooldown_seconds"] = round(
                    time.monotonic() - cooldown_started, 3
                )
                output = ROOT.parent / ".runtime/python-browser-it"
                output.mkdir(parents=True, exist_ok=True)
                if not args.browser_only and args.browser_module in {"all", "native-directory"}:
                    write_native_browser_import_fixtures(output, admin, user_fixture)
                frontend_environment = os.environ.copy()
                if args.browser_module == "identity-publication":
                    frontend_environment["ORBIT_E2E_IDENTITY_PUBLICATION_FIXTURE"] = json.dumps(
                        result["identity_publication"]["browser_fixture"], ensure_ascii=False
                    )
                if args.browser_module == "identity-summary":
                    frontend_environment["ORBIT_E2E_IDENTITY_SUMMARY_FIXTURE"] = json.dumps(
                        result["identity_summary"]["browser_fixture"], ensure_ascii=False
                    )
                frontend_environment.update(
                    ORBIT_E2E_BACKEND_URL="http://127.0.0.1:18083",
                    ORBIT_E2E_FIXTURE_PASSWORD=password,
                    ORBIT_E2E_OUTPUT=str(output),
                    ORBIT_E2E_CHANNELS="1" if args.migration_through >= 11 else "0",
                    ORBIT_E2E_OWNERS500="1" if args.include_channel_owners else "0",
                    ORBIT_E2E_ACCOUNTS="1" if args.include_account_details else "0",
                    ORBIT_E2E_ACCOUNT_COMMAND="1"
                    if args.browser_module == "account-command"
                    else "0",
                    ORBIT_E2E_SCOPES="1" if args.include_account_scopes else "0",
                    ORBIT_E2E_LAUNCH="1" if args.browser_module == "launch" else "0",
                    ORBIT_E2E_LAUNCH_METRIC_PROFILES="1"
                    if args.browser_module == "launch-metric-profiles"
                    else "0",
                    ORBIT_E2E_METRIC_PROFILES="1"
                    if args.browser_module == "metric-profiles"
                    else "0",
                    ORBIT_E2E_TASK_CORE="1"
                    if args.browser_module in {"tasks", "task-events"}
                    else "0",
                    ORBIT_E2E_TASK_EVENTS="1" if args.browser_module == "task-events" else "0",
                    ORBIT_E2E_MATERIAL_SCANNER_CONFIGURATION="1"
                    if args.browser_module == "scanner-configuration"
                    else "0",
                    ORBIT_E2E_VENDOR_ALIAS="1" if args.migration_through >= 17 else "0",
                    ORBIT_E2E_MATERIALS="1" if args.include_materials else "0",
                    ORBIT_E2E_MATERIAL_SECURITY="1" if args.include_material_security else "0",
                )
                if args.browser_module == "launch-metric-profiles":
                    frontend_environment["ORBIT_E2E_LAUNCH_METRIC_WRITER_USERNAME"] = (
                        launch_metric_fixture["writer_username"]
                    )
                    frontend_environment["ORBIT_E2E_LAUNCH_METRIC_PROFILE_ID"] = (
                        launch_metric_fixture["profile_id"]
                    )
                if args.browser_module in {"tasks", "task-events"}:
                    with admin.cursor() as cursor:
                        cursor.execute(
                            "SELECT u.user_name FROM sys_user u JOIN orbit_user_scope s "
                            "ON s.user_id=u.user_id WHERE u.user_id=990371 AND s.enabled=1"
                        )
                        task_reader = cursor.fetchone()
                    assert task_reader and re.fullmatch(r"task_reader_[a-f0-9]{12}", task_reader[0])
                    # 只传本轮公开夹具用户名；密码沿既有私有fixture内存，不记录Token。
                    frontend_environment["ORBIT_E2E_TASK_READER_USERNAME"] = task_reader[0]
                if args.browser_module == "task-events":
                    from task_event_browser_fixture import TaskEventBrowserControl

                    task_event_browser_control = TaskEventBrowserControl(admin, database, output)
                    task_event_browser_control.start()
                    frontend_environment["ORBIT_E2E_TASK_EVENT_CONTROL"] = json.dumps(
                        task_event_browser_control.manifest
                    )
                if args.browser_module in {"all", "authentication"}:
                    from authentication_browser_fixture import prepare_authentication_browser

                    from orbit_api.credentials import CredentialCipher

                    auth_fixture = prepare_authentication_browser(
                        client,
                        admin,
                        headers,
                        user_fixture,
                        CredentialCipher("fixture", values["ORBIT_PYTHON_SECRETS_KEYS"]),
                        idp,
                        database,
                    )
                    frontend_environment.update(
                        ORBIT_E2E_AUTH_FIXTURES=json.dumps(auth_fixture),
                        ORBIT_E2E_IDP_PORT=str(idp.port),
                    )
                if args.browser_module in {
                    "all",
                    "authentication",
                    "materials",
                    "materials-and-security",
                    "material-security",
                }:
                    from authentication_browser_gateway import LocalBrowserGateway

                    browser_gateway = LocalBrowserGateway(idp).__enter__()
                if args.include_material_security and args.browser_module in {
                    "all",
                    "materials-and-security",
                    "material-security",
                }:
                    from material_security_browser_fixture import (
                        prepare_material_security_browser_fixture,
                    )

                    manifest = prepare_material_security_browser_fixture(
                        admin, database, values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"]
                    )
                    frontend_environment["ORBIT_E2E_MATERIAL_SECURITY_FIXTURE"] = json.dumps(
                        manifest
                    )
                if args.include_materials and args.browser_module in {
                    "all",
                    "materials",
                    "materials-and-security",
                    "material-security",
                }:
                    from material_browser_fixture import start_material_browser_worker

                    material_browser_stop = start_material_browser_worker(
                        admin,
                        database,
                        values["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"],
                        scanner=material_scanner,
                    )
                if args.include_channel_owners:
                    owner_manifest = output / "channel-owners500-fixture.json"
                    owner_manifest.write_text(
                        json.dumps(result["channel_owners_fixture"], ensure_ascii=False),
                        encoding="utf-8",
                    )
                    frontend_environment["ORBIT_E2E_OWNERS500_FIXTURE"] = str(owner_manifest)
                if args.browser_module == "account-command":
                    from account_command_browser_fixture import prepare_account_command_browser

                    command_browser_fixture = prepare_account_command_browser(
                        admin, database, account_cipher
                    )
                    result["account_command_browser_scope"] = (
                        "受控来源只是本地入队前置，不代表真实Meta验证；"
                        "不启动SYNC执行器，SQL复核三条命令始终未认领/零尝试"
                    )
                    cases.append("pythonAccountCommandBrowserIsolatedAdmissionFixture")
                if args.browser_module == "metrics":
                    frontend_environment["ORBIT_E2E_METRICS_FIXTURE"] = json.dumps(
                        result["metrics_public_fixture"]
                    )
                before_browser = time.time()
                browser_argv = [
                    shutil.which("pnpm.cmd") or "pnpm",
                    "exec",
                    "playwright",
                    "test",
                    "-c",
                    "playwright.python.config.ts",
                ]
                if args.browser_module == "materials-and-security":
                    browser_argv += [
                        "orbit-python-materials.spec.ts",
                        "orbit-python-material-security.spec.ts",
                    ]
                elif args.browser_module != "all":
                    browser_argv.append(
                        "orbit-metrics.spec.ts"
                        if args.browser_module == "metrics"
                        else f"orbit-python-{args.browser_module}.spec.ts"
                    )
                if args.browser_project:
                    browser_argv += ["--project", args.browser_project]
                expected_browser_tests = (
                    (
                        (24 if args.migration_through >= 11 else 21)
                        + (3 if args.include_materials else 0)
                        + (3 if args.migration_through >= 17 else 0)
                        + (3 if args.include_account_details else 0)
                        + (3 if args.include_account_scopes else 0)
                        + (3 if args.include_material_security else 0)
                        + (3 if args.include_channel_owners else 0)
                    )
                    if args.browser_module == "all"
                    else 9
                    if args.browser_module
                    in {"launch", "metric-profiles", "launch-metric-profiles", "metrics"}
                    else 6
                    if args.browser_module
                    in {
                        "native-directory",
                        "materials-and-security",
                        "tasks",
                        "task-events",
                    }
                    else 3
                )
                if args.browser_project:
                    assert expected_browser_tests % 3 == 0
                    expected_browser_tests //= 3
                    result["browser_scope"] = "仅指定单视口诊断；非三视口验收"
                # 原12项串行进程预算240秒；增加到18项时同比扩大整轮预算。
                # 不修改Playwright单项60秒、零重试与完整断言，不能把未结束的整轮算通过。
                browser_process_budget = max(240, expected_browser_tests * 20)
                result["browser_expected_tests"] = expected_browser_tests
                result["browser_process_timeout_seconds"] = browser_process_budget
                print(
                    json.dumps(
                        {
                            "phase": "browser",
                            "module": args.browser_module,
                            "expected": expected_browser_tests,
                        }
                    ),
                    flush=True,
                )
                browser_process = subprocess.Popen(
                    browser_argv,
                    cwd=ROOT.parent / "orbit-web",
                    env=frontend_environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                try:
                    browser_stdout, browser_stderr = browser_process.communicate(
                        timeout=browser_process_budget
                    )
                except subprocess.TimeoutExpired as timeout_error:
                    diagnostic = Path(tempfile.gettempdir()) / (
                        "orbit-python-browser-timeout-" + uuid.uuid4().hex + ".log"
                    )
                    diagnostic.write_bytes(
                        (timeout_error.output or b"") + (timeout_error.stderr or b"")
                    )
                    print(json.dumps({"browser_timeout_diagnostic": str(diagnostic)}))
                    # Windows的cmd父进程退出不会关闭后代管道；只结束本工具刚创建的测试进程树。
                    if os.name == "nt":
                        subprocess.run(
                            ["taskkill", "/PID", str(browser_process.pid), "/T", "/F"],
                            capture_output=True,
                            timeout=10,
                        )
                    else:
                        browser_process.kill()
                    browser_process.communicate(timeout=10)
                    raise
                browser_run = subprocess.CompletedProcess(
                    browser_argv, browser_process.returncode, browser_stdout, browser_stderr
                )
                if material_browser_stop is not None:
                    stop = material_browser_stop
                    stop()
                    material_browser_stop = None
                if browser_run.returncode:
                    diagnostic = Path(tempfile.gettempdir()) / (
                        "orbit-python-browser-" + uuid.uuid4().hex + ".log"
                    )
                    diagnostic.write_bytes(browser_run.stdout + browser_run.stderr)
                    print(json.dumps({"browser_diagnostic": str(diagnostic)}))
                report = output / "playwright-result.json"
                assert report.is_file() and report.stat().st_mtime >= before_browser
                stats = json.loads(report.read_text(encoding="utf-8"))["stats"]
                result["browser_summary"] = stats
                assert (
                    browser_run.returncode == 0
                    and stats["expected"] == expected_browser_tests
                    and stats["unexpected"] == stats["skipped"] == stats["flaky"] == 0
                )
                cases.append(browser_case)
                if args.browser_module == "task-events":
                    result["task_event_browser_control"] = task_event_browser_control.verify(
                        admin, 1 if args.browser_project else 3
                    )
                    cases.append("pythonTaskEventBrowserActualCommitAndPermissionRestoration")
                if args.browser_module == "account-command":
                    from account_command_browser_fixture import verify_account_command_browser

                    verify_account_command_browser(
                        admin, command_browser_fixture, args.browser_project
                    )
                    cases.append("pythonAccountCommandBrowserAcceptedCommandsNeverClaimed")
            logout = client.post("/logout", headers=headers)
            assert logout.status_code == 200
            denied = client.get("/getInfo", headers=headers)
            assert denied.status_code == 401 or denied.json().get("code") == 401
            cases.append("pythonLogoutRevokesSameToken")
        assert len(cases) == len(planned) and set(cases) == set(planned), (
            "检查计划未全部实际执行，不能通过"
        )
        result.update(result="PASS", exit_code=0)
    except Exception as error:
        if args.execution_candidate_only and isinstance(error, CandidateFixtureCleanupError):
            # 只认本工具内部异常类型，不信HTTP参数或任意同名属性。
            result["candidate_fixture_database_retained"] = True
            result["candidate_fixture_cleanup_verified"] = False
        source_frames = []
        for frame in traceback.extract_tb(error.__traceback__):
            filename = Path(frame.filename).resolve()
            if (
                filename.is_file()
                and filename.is_relative_to(ROOT)
                and filename.relative_to(ROOT).parts[0] in {"tools", "python"}
            ):
                source_frames.append(
                    {
                        "file": str(filename.relative_to(ROOT)).replace("\\", "/"),
                        "line": frame.lineno,
                        "function": frame.name,
                    }
                )
        result.update(
            result="FAIL",
            exit_code=1,
            failure_type=type(error).__name__,
            failure_line=traceback.extract_tb(error.__traceback__)[-1].lineno,
            failure_message="独立Python框架集成验证失败，保留脱敏失败回执，不计功能通过",
            last_passed_case=cases[-1] if cases else None,
            failure_source_frames=source_frames[-6:],
        )
        database_error = (
            error if isinstance(error, pymysql.err.MySQLError) else getattr(error, "orig", None)
        )
        arguments = getattr(database_error, "args", ())
        if arguments and type(arguments[0]) is int and 0 <= arguments[0] <= 65535:
            result["database_error_code"] = arguments[0]
        # 原始诊断仅留本机临时文件，不把响应、Token、连接串或SQL参数写进证据。
        log.seek(0)
        diagnostic = Path(tempfile.gettempdir()) / ("orbit-python-it-" + uuid.uuid4().hex + ".log")
        diagnostic.write_bytes(log.read())
        print(
            json.dumps(
                {
                    "failure_type": type(error).__name__,
                    "failure_line": result["failure_line"],
                    "failure_source_frames": result["failure_source_frames"],
                    "database_error_code": result.get("database_error_code"),
                    "diagnostic_file": str(diagnostic),
                }
            )
        )
    finally:
        if task_event_browser_control is not None:
            task_event_browser_control.stop()
        if material_browser_stop is not None:
            # 真实Worker未退出时拒绝清除其对象或数据库，不能产生后台悬挂写入。
            material_browser_stop()
        if browser_gateway is not None:
            browser_gateway.__exit__(None, None, None)
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        if idp is not None:
            idp.__exit__(None, None, None)
        if object_bundle is not None:
            # Windows递归清理前核对最终解析路径；不能跟随被替换的目录或影响其他运行。
            current_path = object_bundle.resolve()
            if current_path != object_bundle_path or not current_path.is_relative_to(
                ROOT.resolve()
            ):
                raise ValueError("对象夹具清理路径异常，拒绝递归删除")
            if (
                args.include_material_scanner_supervisor_native and not supervisor_cleanup_verified
            ) or (args.include_material_worker_cli_native and not worker_cli_cleanup_verified):
                # 不确定的后台扫描/处理仍可能访问对象；保留本轮UUID根，不能先删后声称清理成功。
                result["supervisor_fixture_objects_retained"] = True
            else:
                shutil.rmtree(current_path)
        if admin is not None:
            if (
                database_created
                and not result.get("candidate_fixture_database_retained", False)
                and not (
                    (
                        args.include_material_scanner_supervisor_native
                        and not supervisor_cleanup_verified
                    )
                    or (args.include_material_worker_cli_native and not worker_cli_cleanup_verified)
                )
            ):
                with admin.cursor() as cursor:
                    cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
            elif database_created and not result.get("candidate_fixture_database_retained", False):
                result["supervisor_fixture_database_retained"] = True
            admin.close()
        # 仅本工具验证为空后使用的专属DB15；不操作预览或其他Redis DB。
        if "cache" in locals() and "child" in locals() and child is not None:
            cache.flushdb()
            cache.close()
        log.close()
    if result["result"] != "PASS":
        # 业务检查实际顺序可能与计划注册顺序不同，不能猜测具体失败用例名称。
        failed = (
            "pythonIntegrationCheckFailed" if len(cases) < len(planned) else "pythonFixtureCleanup"
        )
        executed = cases + [failed]
    else:
        executed = cases
    result["summary"] = {
        "tests": len(executed),
        "expected": len(planned),
        "passed": len(cases),
        "failures": int(result["result"] != "PASS"),
        "not_run": max(0, len(planned) - len(executed)),
        "cases": executed,
    }
    files = [
        ROOT / "pyproject.toml",
        Path(__file__),
        ROOT / "tools/team_checks.py",
        ROOT / "tools/identity_capacity_checks.py",
        ROOT / "tools/role_guard_checks.py",
        ROOT / "tools/role_checks.py",
        ROOT / "tools/user_checks.py",
        ROOT / "tools/user_create_checks.py",
        ROOT / "tools/user_update_checks.py",
        ROOT / "tools/native_user_role_checks.py",
        ROOT / "tools/team_session_checks.py",
        ROOT / "tools/native_directory_checks.py",
        ROOT / "tools/native_role_read_checks.py",
        ROOT / "tools/native_write_contract_checks.py",
        ROOT / "tools/native_role_reference_checks.py",
        ROOT / "tools/native_bulk_lifecycle_checks.py",
        ROOT / "tools/browser_session_checks.py",
        ROOT / "tools/authorization_store_checks.py",
        ROOT / "tools/cookie_http_checks.py",
        ROOT / "tools/oidc_https_fixture.py",
        ROOT / "tools/authentication_browser_fixture.py",
        ROOT / "tools/authentication_browser_gateway.py",
        ROOT / "tools/tls_fixture_server.py",
        ROOT / "tools/oidc_callback_checks.py",
        ROOT / "tools/invitation_checks.py",
        ROOT / "tools/invitation_activation_checks.py",
        ROOT / "tools/invitation_delivery_checks.py",
        ROOT / "tools/invitation_worker_cli_checks.py",
        ROOT / "tools/run_invitation_worker.py",
        ROOT / "tools/invitation_worker_lock.py",
        ROOT / "tools/reference_channel_checks.py",
        ROOT / "tools/reference_channel_scope_checks.py",
        ROOT / "tools/material_checks.py",
        ROOT / "tools/material_browser_fixture.py",
        ROOT / "tools/account_import_checks.py",
        ROOT / "tools/fixture_login.py",
        ROOT / "tools/native_user_change_checks.py",
    ] + list((ROOT / "python/orbit_api").glob("*.py"))
    if args.include_account_worker:
        files += [
            ROOT / "tools/account_worker_checks.py",
            ROOT / "tools/account_platform_checks.py",
        ]
    if args.include_account_details:
        files += [ROOT / "tools/account_details_checks.py"]
    if args.include_channel_scope:
        files += [ROOT / "tools/channel_scope_matrix_checks.py"]
    if args.include_material_video:
        files += [ROOT / "tools/material_video_checks.py"]
    files += selected_migrations
    if args.include_account_read_cookie:
        files += [ROOT / "tools/account_read_cookie_checks.py"]
    if args.include_reference_channel_capacity:
        files += [
            ROOT / "tools/reference_channel_capacity_checks.py",
            ROOT / "tools/account_capacity_checks.py",
        ]
    if args.execution_candidate_only:
        files += [
            ROOT / "tools/launch_execution_candidate_checks.py",
            ROOT / "tools/launch_execution_fixture.py",
        ]
    if args.execution_recovery_scanner_only:
        files += [
            ROOT / "tools/launch_execution_recovery_scanner_checks.py",
            ROOT / "tools/launch_execution_fixture.py",
            ROOT / "tools/launch_execution_lease_checks.py",
            ROOT / "tools/launch_execution_lease_store_checks.py",
        ]
    if args.metric_query_result_only:
        files += [
            ROOT / "tools/metrics_query_result_checks.py",
            ROOT / "tools/metrics_query_read_checks.py",
            ROOT / "tools/metric_fact_schema_checks.py",
            ROOT / "tools/metric_profile_query_checks.py",
        ]
        if args.include_metric_query_http:
            files += [ROOT / "tools/metrics_http_checks.py"]
        if args.include_metrics_browser_fixture:
            files += [
                ROOT / "tools/metrics_browser_fixture.py",
                ROOT / "tools/metrics_public_fixture_checks.py",
            ]
    if args.scope_create_profile_only:
        files += [
            ROOT / "tools/account_scope_profile_checks.py",
            ROOT / "tools/account_scope_capacity_diagnostics.py",
        ]
    if args.rules_only:
        files += [
            ROOT / "tools/rule_definition_checks.py",
            ROOT / "tools/metric_profile_query_checks.py",
        ]
        if args.include_rule_editor:
            files += [ROOT / "tools/rule_editor_checks.py"]
        if args.include_rule_editor_scopes:
            files += [ROOT / "tools/rule_editor_scope_checks.py"]
        if args.include_rule_scope_consumer:
            files += [ROOT / "tools/rule_scope_consumer_checks.py"]
        if args.include_rule_editor_definition:
            files += [ROOT / "tools/rule_editor_definition_checks.py"]
        if args.include_rule_schedule_preview:
            files += [ROOT / "tools/rule_schedule_preview_checks.py"]
        if args.include_rule_scope_options:
            files += [ROOT / "tools/rule_scope_options_checks.py"]
        if args.include_rule_simulation_schema:
            files += [
                ROOT / "tools/rule_simulation_schema_checks.py",
                ROOT / "docs/orbit/sql-drafts/063_rule_simulation_candidate.sql",
                ROOT / "tools/metric_fact_schema_checks.py",
                ROOT / "tools/metric_profile_reference_checks.py",
            ]
        if args.include_rule_definition_boundaries:
            files += [
                ROOT / "tools/rule_definition_boundary_checks.py",
                ROOT / "tools/metric_fact_schema_checks.py",
                ROOT / "tools/metric_profile_reference_checks.py",
            ]
        if args.include_rule_simulation_access:
            files += [
                ROOT / "tools/rule_simulation_access_checks.py",
                ROOT / "tools/metric_fact_schema_checks.py",
                ROOT / "tools/metric_profile_reference_checks.py",
            ]
        if args.include_rule_simulation_calendar:
            files += [
                ROOT / "tools/rule_simulation_calendar_checks.py",
                ROOT / "tools/rule_simulation_access_checks.py",
                ROOT / "tools/metric_profile_reference_checks.py",
            ]
        if args.rules_internal_browser:
            files += [ROOT / "tools/rules_internal_browser_checkpoint.py"]
        if args.rules_definition_browser:
            files += [
                ROOT / "tools/rules_definition_browser_fixture.py",
                ROOT / "tools/metric_fact_schema_checks.py",
                ROOT / "tools/metric_profile_reference_checks.py",
            ]
            if args.include_rule_display_metadata:
                files += [ROOT / "tools/rules_definition_flow_checks.py"]
            if args.include_rule_recovery_context:
                files += [ROOT / "tools/rule_recovery_context_checks.py"]
    if args.metric_query_read_only:
        files += [
            ROOT / "tools/metrics_query_read_checks.py",
            ROOT / "tools/metric_fact_schema_checks.py",
            ROOT / "tools/account_scope_visibility_plan_checks.py",
        ]
    if args.identity_publication_only:
        files += [ROOT / "tools/identity_publication_checks.py"]
    if args.include_launch_identity_drafts:
        files += [ROOT / "tools/launch_identity_draft_checks.py"]
    if args.identity_summary_only:
        files += [
            ROOT / "tools/identity_publication_summary_checks.py",
            ROOT / "tools/identity_publication_checks.py",
            ROOT / "tools/account_scope_visibility_plan_checks.py",
        ]
    if args.metrics_scope_only:
        files += [
            ROOT / "tools/metrics_scope_checks.py",
            ROOT / "tools/account_scope_visibility_plan_checks.py",
        ]
        if args.include_metric_fact_schema:
            files += [ROOT / "tools/metric_fact_schema_checks.py"]
        if args.include_metrics_expected_manifest:
            files += [ROOT / "tools/metrics_result_manifest_checks.py"]
    if args.meta_observation_registry_only:
        files += [ROOT / "tools/meta_observation_registry_checks.py"]
        if args.include_meta_receipt_bounds:
            files += [ROOT / "tools/meta_receipt_bounds_checks.py"]
    if args.execution_lease_only:
        files += [
            ROOT / "tools/launch_execution_lease_checks.py",
            ROOT / "tools/launch_execution_fixture.py",
        ]
        if args.include_execution_lease_store:
            files += [ROOT / "tools/launch_execution_lease_store_checks.py"]
        if args.include_execution_recovery:
            files += [ROOT / "tools/launch_execution_recovery_checks.py"]
    files += list((ROOT / "python/orbit_api/contracts").glob("*.json"))
    files += [
        FRAMEWORK / "config/env.py",
        FRAMEWORK / "config/database.py",
        FRAMEWORK / "config/asyncmy_compat.py",
        FRAMEWORK / "config/orbit_runtime.py",
        FRAMEWORK / "config/lifecycle.py",
        FRAMEWORK / "module_admin/entity/vo/user_vo.py",
        FRAMEWORK / "module_admin/entity/vo/role_vo.py",
        FRAMEWORK / "module_admin/entity/do/user_do.py",
        FRAMEWORK / "module_admin/entity/do/role_do.py",
        FRAMEWORK / "module_admin/service/role_service.py",
        FRAMEWORK / "module_admin/service/login_service.py",
        FRAMEWORK / "module_admin/service/user_service.py",
        FRAMEWORK / "common/directory_policy.py",
        FRAMEWORK / "common/directory_mutation_policy.py",
        FRAMEWORK / "common/annotation/cache_annotation.py",
        FRAMEWORK / "module_admin/dao/role_dao.py",
        FRAMEWORK / "module_admin/dao/user_dao.py",
        FRAMEWORK / "module_admin/controller/role_controller.py",
        FRAMEWORK / "module_admin/service/menu_service.py",
        FRAMEWORK / "module_admin/controller/user_controller.py",
        FRAMEWORK / "module_identity/service/identity_service.py",
    ]
    if args.include_material_taxonomy:
        files += [
            ROOT / "tools" / name
            for name in (
                "material_taxonomy_checks.py",
                "material_taxonomy_query_checks.py",
                "material_schema_checks.py",
            )
        ]
    if args.include_vendor_alias:
        files += [ROOT / "tools/vendor_alias_checks.py"]
    if args.include_material_taxonomy_scope or args.material_taxonomy_metadata_only:
        files += [ROOT / "tools/material_taxonomy_scope_checks.py"]
    if args.include_material_taxonomy_capabilities:
        files += [ROOT / "tools/material_taxonomy_capability_checks.py"]
    if args.environment_live_only:
        files += [
            ROOT / "tools/environment_live_checks.py",
            ROOT / "tools/environment_probe_checks.py",
            ROOT / "tools/environment_capability_checks.py",
            ROOT / "tools/agent_execution_checks.py",
            ROOT / "tools/environment_execution_checks.py",
            ROOT / "tools/environment_tls_fixture.py",
            ROOT / "tools/frontend_static_fixture.py",
            ROOT / "python/orbit_agent/requirements.txt",
        ] + list((ROOT / "python/orbit_agent").glob("*.py"))
    if args.environment_registry_only:
        files += [
            ROOT / "tools/environment_registry_checks.py",
            ROOT / "tools/profile_binding_checks.py",
        ]
    if args.environment_internal_browser:
        files += [ROOT / "tools/rules_internal_browser_checkpoint.py"]
    if args.taxonomy_internal_browser:
        files += [ROOT / "tools/rules_internal_browser_checkpoint.py"]
    if args.include_channel_fields:
        files += [
            ROOT / "tools/channel_field_contract_checks.py",
            ROOT / "docs/orbit/baseline/contracts/openapi-current.json",
        ]
    if args.include_material_lifecycle:
        files += [ROOT / "tools/material_lifecycle_checks.py"]
    if args.include_material_lifecycle_recovery:
        files += [ROOT / "tools/material_lifecycle_recovery_checks.py"]
    if args.include_channel_owners:
        files += [ROOT / "tools/channel_owners_500_checks.py"]
    if args.include_material_lifecycle_races:
        files += [
            ROOT / "tools/material_lifecycle_race_checks.py",
            ROOT / "tools/material_lifecycle_http_race_checks.py",
        ]
    if args.include_account_alias_snapshots:
        files += [
            ROOT / "tools/account_alias_fixture.py",
            ROOT / "tools/account_alias_snapshot_checks.py",
        ]
    if args.include_account_identities:
        files += [
            ROOT / "tools/account_identities_checks.py",
            ROOT / "tools/identity_publication_checks.py",
            ROOT / "tools/account_scope_visibility_plan_checks.py",
        ]
    if args.material_references_only:
        files += [
            ROOT / "tools/material_reference_checks.py",
            ROOT / "tools/material_reference_scope_checks.py",
        ]
    files += [ROOT / "tools/configuration_metadata_checks.py"]
    if args.include_account_assignment_options:
        files += [ROOT / "tools/account_assignment_options_checks.py"]
    if args.include_account_projection:
        files += [ROOT / "tools/account_projection_checks.py"]
    if args.include_launch_naming or args.launch_naming_only:
        files += [ROOT / "tools/launch_naming_checks.py"]
    if args.include_account_actions:
        files += [
            ROOT / "tools/account_action_fixture.py",
            ROOT / "tools/account_actions_checks.py",
        ]
    if args.include_account_sync:
        files += [ROOT / "tools/account_actions_sync_checks.py"]
    if args.include_account_capacity:
        files += [ROOT / "tools/account_capacity_checks.py"]
        if args.include_account_query_profile:
            files += [ROOT / "tools/account_list_query_diagnostics.py"]
        if args.include_account_scope_profile:
            files += [ROOT / "tools/account_scope_capacity_diagnostics.py"]
        if args.include_account_scope_http_profile:
            files += [ROOT / "tools/account_scope_http_diagnostics.py"]
    if args.include_scope_visibility_verdict:
        files += [ROOT / "tools/scope_visibility_verdict_checks.py"]
    if args.include_account_scopes:
        files += [
            ROOT / "tools/account_readonly_fixture.py",
            ROOT / "tools/account_scope_checks.py",
        ]
    if args.include_launch_drafts:
        files += [ROOT / "tools/launch_draft_template_checks.py"]
    if args.include_launch_scope_consumption:
        files += [ROOT / "tools/launch_scope_consumption_checks.py"]
    if args.include_account_command_diagnostics:
        files += [ROOT / "tools/account_command_checks.py"]
    if args.account_scope_visibility_plan_only:
        files += [ROOT / "tools/account_scope_visibility_plan_checks.py"]
    if args.launch_validation_only:
        files += [ROOT / "tools/launch_validation_checks.py"]
        if args.include_launch_execution_http:
            files += [ROOT / "tools/launch_execution_http_checks.py"]
        if args.include_launch_execution_provider:
            files += [
                ROOT / "tools/launch_execution_checks.py",
                ROOT / "tools/launch_execution_fixture.py",
            ]
        if args.include_metric_profile_registry:
            files += [ROOT / "tools/metric_profile_registry_checks.py"]
        if args.include_metric_profile_query:
            files += [ROOT / "tools/metric_profile_query_checks.py"]
        if args.include_template_metric_references:
            files += [ROOT / "tools/template_metric_reference_checks.py"]
        if args.include_template_current_scope:
            files += [ROOT / "tools/launch_replay_concurrency_checks.py"]
        if args.include_template_current_scope:
            files += [
                ROOT / "tools/template_current_scope_checks.py",
                ROOT / "tools/account_scope_visibility_plan_checks.py",
            ]
        if args.include_metric_profile_references:
            files += [
                ROOT / "tools/metric_profile_reference_checks.py",
                ROOT / "tools/metric_profile_query_checks.py",
            ]
        if args.include_launch_execution_guards:
            files += [ROOT / "tools/launch_execution_guard_checks.py"]
        if args.include_launch_allocation_http:
            files += [ROOT / "tools/launch_allocation_http_checks.py"]
        if args.include_launch_allocation_http_provider:
            files += [
                ROOT / "tools/launch_allocation_http_provider_checks.py",
                ROOT / "tools/launch_allocation_http_fixture.py",
                ROOT / "tools/material_schema_checks.py",
            ]
        if args.include_launch_validation_provider:
            files += [ROOT / "tools/launch_validation_fixture.py"]
    if args.launch_allocation_runtime_only:
        files += [ROOT / "tools/launch_allocation_runtime_checks.py"]
    if args.task_core_only:
        files += [ROOT / "tools/task_core_checks.py"]
        if args.include_launch_plan_source:
            files += [
                ROOT / "tools/launch_plan_source_checks.py",
                ROOT / "tools/task_core_fixture.py",
            ]
        if args.browser and args.browser_module == "task-events":
            files += [ROOT / "tools/task_event_browser_fixture.py"]
    if args.material_scanner_owner_store_only:
        files += [ROOT / "tools/material_scanner_owner_store_checks.py"]
        if args.include_material_worker_cli_native:
            files += [
                ROOT / "tools/material_worker_cli_checks.py",
                ROOT / "tools/run_material_worker.py",
                ROOT / "tools/material_scanner_supervisor_checks.py",
                ROOT / "tools/material_scanner_owner_native_checks.py",
                ROOT / "tools/clamd_fixture_attestation.py",
            ]
        if args.include_material_scanner_supervisor_native:
            files += [
                ROOT / "tools/material_scanner_supervisor_checks.py",
                ROOT / "tools/material_scanner_owner_native_checks.py",
                ROOT / "tools/clamd_fixture_attestation.py",
            ]
        if args.include_material_scanner_owner_native:
            files += [
                ROOT / "tools/material_scanner_owner_native_checks.py",
                ROOT / "tools/clamd_fixture_attestation.py",
            ]
    if args.task_event_stream_only:
        files += [
            ROOT / "tools/task_event_stream_checks.py",
            ROOT / "tools/task_event_fixture.py",
            ROOT / "tools/task_core_fixture.py",
            FRAMEWORK / "middlewares/cors_middleware.py",
        ]
        if args.include_task_event_cookie:
            files += [ROOT / "tools/task_event_cookie_checks.py"]
        if args.include_task_event_boundaries:
            files += [ROOT / "tools/task_event_boundary_checks.py"]
        if args.include_task_event_integrity:
            files += [ROOT / "tools/task_event_integrity_checks.py"]
    if args.material_scanner_configuration_only:
        if args.include_launch_execution_material_references:
            files += [
                ROOT / "tools/launch_execution_material_bridge_checks.py",
                ROOT / "tools/launch_execution_fixture.py",
                ROOT / "tools/launch_validation_fixture.py",
            ]
        if args.include_launch_allocation_references:
            files += [ROOT / "tools/launch_allocation_reference_checks.py"]
        files += [ROOT / "tools/material_scanner_configuration_checks.py"]
        if args.include_material_scanner_configuration_scope:
            files += [ROOT / "tools/material_scanner_configuration_scope_checks.py"]
    if args.browser and args.browser_module == "account-command":
        files += [ROOT / "tools/account_command_browser_fixture.py"]
    if args.include_template_recipients:
        files += [ROOT / "tools/template_recipient_checks.py"]
    if args.include_material_infected_memory_worker:
        files += [ROOT / "tools/material_antivirus_memory_worker_checks.py"]
    if args.browser and args.include_material_security:
        files += [ROOT / "tools/material_security_browser_fixture.py"]
    if args.include_material_security:
        files += [ROOT / "tools/material_security_checks.py"]
    if args.include_material_runtime_store:
        files += [
            ROOT / "tools/material_runtime_store_checks.py",
            ROOT / "tools/material_runtime_fixture.py",
            ROOT / "tools/clamd_fixture_attestation.py",
        ]
    if args.include_material_runtime_worker:
        files += [
            ROOT / "tools/material_runtime_worker_checks.py",
            ROOT / "tools/material_runtime_fixture.py",
            ROOT / "tools/clamd_fixture_attestation.py",
        ]
    if args.include_material_security_scope:
        files += [ROOT / "tools/material_security_scope_checks.py"]
    if args.material_scanner_manifest:
        files += [
            ROOT / "tools/material_runtime_fixture.py",
            ROOT / "tools/clamd_fixture_attestation.py",
            ROOT / "tools/material_antivirus_engine_checks.py",
            ROOT / "tools/material_antivirus_worker_checks.py",
        ]
    result["source_sha256"] = {
        str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(
            p.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for p in files
    }
    frontend = ROOT.parent / "orbit-web"
    frontend_files = [
        "playwright.python.config.ts",
        "tests/e2e/orbit-python-configuration.spec.ts",
        "tests/e2e/python-browser-diagnostics.ts",
        "tests/e2e/orbit-python-teams.spec.ts",
        "tests/e2e/orbit-python-roles.spec.ts",
        "src/api/orbit/roles.ts",
        "src/api/orbit/users.ts",
        "src/api/orbit/authentication.ts",
        "src/api/orbit/auth-entry.ts",
        "src/views/orbit/auth/Login.vue",
        "tests/e2e/orbit-python-authentication.spec.ts",
        "tests/e2e/orbit-python-channels.spec.ts",
        "tests/e2e/orbit-python-materials.spec.ts",
        "tests/e2e/material-browser-diagnostics.ts",
        "src/api/orbit/materials.ts",
        "src/api/orbit/material-hash.ts",
        "src/views/orbit/materials/index.vue",
        "src/views/orbit/materials/MaterialTaxonomy.vue",
        "src/views/orbit/materials/MaterialUpload.vue",
        "src/api/orbit/channels.ts",
        "src/api/orbit/references.ts",
        "src/views/orbit/channels/index.vue",
        "src/views/orbit/channels/ReferenceCatalog.vue",
        "index.html",
        "src/main.js",
        "src/permission.js",
        "src/router/index.js",
        "src/store/modules/user.js",
        "src/utils/request.js",
        "src/views/login.vue",
        "src/views/orbit/system/users/index.vue",
        "src/views/orbit/system/users/CreateUser.vue",
        "src/views/orbit/system/users/ReferenceSelect.vue",
        "src/views/system/user/profile/index.vue",
        "src/views/system/user/profile/userInfo.vue",
        "tests/e2e/orbit-python-users.spec.ts",
        "tests/e2e/orbit-python-native-directory.spec.ts",
        "src/views/system/user/index.vue",
        "src/components/ExcelImportDialog/index.vue",
        "src/views/system/user/view.vue",
        "src/views/system/user/authRole.vue",
        "src/views/system/role/index.vue",
        "src/views/system/role/authUser.vue",
        "src/views/system/role/selectUser.vue",
        "src/assets/styles/index.scss",
        "src/assets/styles/orbit-native-directory.scss",
        "src/views/orbit/system/roles/index.vue",
        "src/views/orbit/system/roles/labels.ts",
        "src/views/orbit/system/directory-date.scss",
        "src/api/orbit/teams.ts",
        "src/views/orbit/system/teams/index.vue",
        "vite.config.js",
        "vite.python.config.js",
        "src/api/orbit/configuration.ts",
    ]
    frontend_files += [
        str(p.relative_to(frontend)).replace("\\", "/")
        for p in (frontend / "src/views/orbit/system/configuration").glob("*.vue")
    ]
    frontend_files += ["src/views/orbit/system/configuration/validation.ts"]
    frontend_files += ["src/api/orbit/configuration-intent.ts"]
    if args.browser and args.browser_module in {"all", "vendor-alias"}:
        frontend_files += [
            name
            for name in (
                "src/api/orbit/vendor-aliases.ts",
                "src/views/orbit/channels/VendorAliases.vue",
                "tests/e2e/orbit-python-vendor-alias.spec.ts",
            )
        ]
    if args.browser and args.browser_module in {"all", "accounts", "scopes", "account-command"}:
        frontend_files += [
            "src/api/orbit/account-details.ts",
            "src/api/orbit/account-actions.ts",
            "src/api/orbit/account-assignment.ts",
            "src/api/orbit/account-command.ts",
            "src/api/orbit/accounts.ts",
            "src/views/orbit/accounts/index.vue",
            "src/views/orbit/accounts/AccountDetailsDrawer.vue",
            "src/views/orbit/accounts/AccountActionDialog.vue",
            "src/views/orbit/accounts/AccountAssignmentDialog.vue",
            "src/views/orbit/accounts/AccountCommandStatus.vue",
            "src/views/orbit/accounts/ImportAccounts.vue",
            "tests/e2e/orbit-python-accounts.spec.ts",
        ]
    if args.browser and args.browser_module == "account-command":
        frontend_files += ["tests/e2e/orbit-python-account-command.spec.ts"]
    if args.browser and args.browser_module in {"all", "channel-owners500"}:
        frontend_files += ["tests/e2e/orbit-python-channel-owners500.spec.ts"]
    if args.browser and args.include_account_scopes:
        frontend_files += [
            "src/api/orbit/scopes.ts",
            "src/views/orbit/accounts/scopes/index.vue",
            "src/views/orbit/accounts/scopes/ScopeMembers.vue",
            "tests/e2e/orbit-python-scopes.spec.ts",
        ]
    if args.browser and args.include_material_security:
        frontend_files += [
            "tests/e2e/orbit-python-material-security.spec.ts",
            "tests/e2e/material-security-response.ts",
        ]
    if args.browser and args.browser_module == "metric-profiles":
        files += [ROOT / "tools/metric_profile_query_checks.py"]
        frontend_files += ["tests/e2e/orbit-python-metric-profiles.spec.ts"]
    if args.browser and args.browser_module == "launch":
        files += [
            ROOT / "tools/launch_pagination_browser_fixture.py",
            ROOT / "tools/launch_account_scope_browser_fixture.py",
        ]
        frontend_files += ["tests/e2e/orbit-python-launch.spec.ts"]
    if args.browser and args.browser_module == "launch-metric-profiles":
        files += [
            ROOT / "tools/launch_metric_browser_fixture.py",
            ROOT / "tools/metric_profile_query_checks.py",
        ]
        frontend_files += [
            "tests/e2e/orbit-python-launch-metric-profiles.spec.ts",
            "src/api/orbit/metric-profiles.ts",
        ]
    if args.browser and args.browser_module in {"launch", "launch-metric-profiles"}:
        frontend_files += [
            str(p.relative_to(frontend)).replace("\\", "/")
            for p in (frontend / "src/views/orbit/launch").rglob("*.vue")
        ]
        frontend_files += [
            str(p.relative_to(frontend)).replace("\\", "/")
            for p in (frontend / "src/api/orbit").glob("launch*.ts")
        ]
        frontend_files += ["src/api/orbit/templates.ts"]
    if args.browser and args.browser_module == "scanner-configuration":
        frontend_files += [
            "tests/e2e/orbit-python-scanner-configuration.spec.ts",
            "src/views/orbit/system/configuration/MaterialScannerProfileSelect.vue",
        ]
    if args.browser and args.browser_module in {"tasks", "task-events"}:
        frontend_files += [
            "tests/e2e/orbit-python-tasks.spec.ts",
            "src/api/orbit/tasks.ts",
            "src/views/orbit/launch/index.vue",
        ] + [
            str(p.relative_to(frontend)).replace("\\", "/")
            for p in (frontend / "src/views/orbit/launch").glob("Task*.vue")
        ]
        if args.browser_module == "task-events":
            frontend_files += [
                "tests/e2e/orbit-python-task-events.spec.ts",
                "src/api/orbit/task-events.ts",
            ]
    if args.browser and args.browser_module == "metrics":
        frontend_files += ["tests/e2e/orbit-metrics.spec.ts", "src/api/orbit/metrics.ts"] + [
            p.relative_to(frontend).as_posix()
            for p in (frontend / "src/views/orbit/monitor").glob("*.vue")
        ]
    if args.browser and args.browser_module == "identity-summary":
        frontend_files += [
            "tests/e2e/orbit-python-identity-summary.spec.ts",
            "src/views/orbit/accounts/AccountDetailsDrawer.vue",
        ]
    if args.environment_internal_browser:
        frontend_files += [
            "src/api/orbit/environments.ts",
            "src/api/orbit/environments-monitor.ts",
            "src/api/orbit/environments-probe.ts",
            "src/views/orbit/environments/index.vue",
            "src/views/orbit/environments/AgentMonitorPanel.vue",
            "src/views/orbit/environments/AgentProbePanel.vue",
            "src/views/orbit/environments/ProfileBindingsPanel.vue",
        ]
    result["frontend_source_sha256"] = (
        {
            f: hashlib.sha256((frontend / f).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for f in frontend_files
        }
        if args.browser or args.environment_internal_browser
        else {}
    )
    destination = EVIDENCE / "python-framework-integration.json"
    if destination.exists():
        previous = json.loads(destination.read_text(encoding="utf-8"))
        archive = EVIDENCE / (
            "python-framework-attempt-"
            + previous["executed_at"].replace(":", "").replace("+", "_")
            + ".json"
        )
        if not archive.exists():
            archive.write_bytes(destination.read_bytes())
    destination.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps({"result": result["result"], "summary": result["summary"]}, ensure_ascii=False)
    )
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
