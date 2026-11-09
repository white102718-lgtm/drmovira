"""真实HTTP身份草稿验收hook；仅053独立发行专项串行调用，不执行任何广告写入。"""

import json
from copy import deepcopy
from uuid import uuid4

from launch_draft_template_checks import assert_status, draft, snapshot, tree

LAUNCH_IDENTITY_DRAFT_CASES = [
    "pythonLaunchIdentityDraftCreateReadUpdateAndCas",
    "pythonLaunchIdentityDraftScopeResolvedMembers",
    "pythonLaunchIdentityDraftUnavailableResourcesAndProfileFailAtomic",
    "pythonLaunchIdentityDraftNewProofCreatesVersionAndOldKeyReplays",
    "pythonLaunchIdentityDraftRevokedSourceFailsAtomic",
    "pythonLaunchIdentityDraftCurrentAccountOwnershipFailsAtomic",
]


class LaunchIdentityDraftChecks:
    """传入 run_identity_publication_checks(..., launch_draft_hook=本实例)。"""

    def __init__(self):
        self.created = None
        self.body = None
        self.create_headers = None
        self.original_body = None
        self.proof = None

    def __call__(
        self, phase, *, client, admin, headers, tenant, owner, team, account_id, inventory, cases
    ):
        # 原snapshot首先严格核UUID隔离数据库，并覆盖所有计划事务表。
        snapshot(admin)

        def write_headers(revision=None):
            caps = assert_status(
                client.get("/api/v1/launch-plans/capabilities", headers=headers), 200
            )
            return (
                headers
                | {
                    "X-CSRF-Token": caps["csrf_token"],
                    "Idempotency-Key": str(uuid4()),
                }
                | ({"If-Match": f'"{revision}"'} if revision is not None else {})
            )

        def create(value, selected_headers=None):
            return client.post(
                "/api/v1/launch-plans", headers=selected_headers or write_headers(), json=value
            )

        def denied(value, status, pointer=None):
            before = snapshot(admin)
            error = assert_status(create(value), status)
            if pointer is not None:
                assert any(item["path"] == pointer for item in error["field_errors"])
            assert snapshot(admin) == before

        def proof(plan):
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT dependency_json FROM orbit_launch_plan_version "
                    "WHERE tenant_id=%s AND plan_id=%s AND revision=%s",
                    (tenant, plan["id"], plan["revision"]),
                )
                value = cursor.fetchone()[0]
            value = json.loads(value) if isinstance(value, str) else value
            return value["identities"][account_id]

        if phase == "initial":
            pages = [
                r["external_id"]
                for r in inventory["resources"]
                if r["kind"] == "PAGE" and r["usable"]
            ]
            assert pages, "必须来自原053可信发行，不能手写usable库存"
            body = draft({"id": owner, "team": team})
            body.update(account_ids=[account_id], campaigns=tree())
            group = body["campaigns"][0]["adsets"][0]
            body["identity_bindings"] = [
                {
                    "account_id": account_id,
                    "page_id": pages[0],
                    "groups": [],
                    "ad_overrides": [
                        {"ad_local_id": group["ads"][0]["local_id"], "page_id": pages[0]}
                    ],
                }
            ]
            self.original_body = deepcopy(body)
            self.create_headers = write_headers()
            first = assert_status(create(body, self.create_headers), 201)
            assert (
                first["state"] == "DRAFT"
                and first["identity_bindings"] == body["identity_bindings"]
            )
            loaded = assert_status(
                client.get(f"/api/v1/launch-plans/{first['id']}", headers=headers), 200
            )
            assert loaded == first
            original_proof = proof(first)
            assert original_proof["observed_at"] == inventory["observed_at"]
            assert len(original_proof["inventory_hash"]) == 64
            body["name"] += "-编辑"
            self.created = assert_status(
                client.put(
                    f"/api/v1/launch-plans/{first['id']}",
                    headers=write_headers(first["revision"]),
                    json=body,
                ),
                200,
            )
            assert self.created["revision"] == first["revision"] + 1
            before = snapshot(admin)
            assert_status(
                client.put(
                    f"/api/v1/launch-plans/{first['id']}",
                    headers=write_headers(first["revision"]),
                    json=body,
                ),
                409,
            )
            assert snapshot(admin) == before
            self.body, self.proof = body, proof(self.created)
            cases.append(LAUNCH_IDENTITY_DRAFT_CASES[0])

            caps = assert_status(
                client.get("/api/v1/scope-snapshots/capabilities", headers=headers), 200
            )
            frozen = assert_status(
                client.post(
                    "/api/v1/scope-snapshots",
                    headers=headers
                    | {
                        "X-CSRF-Token": caps["csrf_token"],
                        "Idempotency-Key": str(uuid4()),
                    },
                    json={"mode": "IDS", "account_ids": [account_id], "filter": None},
                ),
                201,
            )
            scoped = assert_status(
                create(body | {"account_ids": [], "account_scope_snapshot_id": frozen["id"]}), 201
            )
            assert scoped["account_ids"] == [account_id]
            assert scoped["identity_bindings"] == body["identity_bindings"]
            assert scoped["account_scope_snapshot_id"] is None
            cases.append(LAUNCH_IDENTITY_DRAFT_CASES[1])

            for kind in ("PAGE", "PIXEL", "APPLICATION"):
                invalid = deepcopy(body)
                binding = invalid["identity_bindings"][0]
                if kind == "PAGE":
                    binding["page_id"] = "9999999999999999999999999999999999999999"
                    pointer = "/identity_bindings/0/page_id"
                else:
                    binding["groups"] = [
                        {
                            "adset_local_id": group["local_id"],
                            "pixel_id": None,
                            "conversion_event": None,
                            "application_id": None,
                            "object_store_url": None,
                        }
                    ]
                    field = "pixel_id" if kind == "PIXEL" else "application_id"
                    binding["groups"][0][field] = next(
                        r["external_id"] for r in inventory["resources"] if r["kind"] == kind
                    )
                    if kind == "APPLICATION":
                        invalid["campaigns"][0]["objective"] = "OUTCOME_APP_PROMOTION"
                    pointer = "/identity_bindings/0/groups/0/" + field
                denied(invalid, 422, pointer)
            denied(body | {"profile_binding_ids": [str(uuid4())]}, 503, "/profile_binding_ids")
            cases.append(LAUNCH_IDENTITY_DRAFT_CASES[2])
        elif phase == "refreshed":
            previous = self.created
            self.created = assert_status(
                client.put(
                    f"/api/v1/launch-plans/{previous['id']}",
                    headers=write_headers(previous["revision"]),
                    json=self.body,
                ),
                200,
            )
            assert self.created["revision"] == previous["revision"] + 1
            current_proof = proof(self.created)
            assert current_proof["evidence_id"] != self.proof["evidence_id"]
            assert current_proof["observed_at"] == inventory["observed_at"]
            before = snapshot(admin)
            replay = assert_status(create(self.original_body, self.create_headers), 201)
            assert replay["id"] == self.created["id"] and replay["revision"] == 1
            assert snapshot(admin) == before
            cases.append(LAUNCH_IDENTITY_DRAFT_CASES[3])
        elif phase == "revoked":
            denied(self.body, 503)
            cases.append(LAUNCH_IDENTITY_DRAFT_CASES[4])
        elif phase == "owner_changed":
            denied(self.body, 404)
            cases.append(LAUNCH_IDENTITY_DRAFT_CASES[5])
        else:
            raise ValueError("未声明身份草稿验收阶段")
