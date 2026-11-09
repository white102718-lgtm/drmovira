from fastapi import APIRouter, Depends
import aiohttp

from app.core.security import auth_current_user
from app.model_type_defs.common_models import ApiResponse
from app.model_type_defs.user_models import UserModel

router = APIRouter(prefix="/superset")

base_url = "http://13.229.203.162:8088"


@router.get("/fetchGuestToken/{sdk_id}")
async def fetch_token(
    sdk_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    # 需要在superset的这个配置中加上WTF_CSRF_EXEMPT_LIST = [
    #     "superset.security.api.guest_token",
    url = f"{base_url}/api/v1/security/guest_token/"
    access_token, refresh_token = await get_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}
    body = {
        "resources": [
            {
                "type": "dashboard",
                "id": sdk_id,
            }
        ],
        "rls": [],
        "user": {
            "username": current_user.username,
            "first_name": current_user.real_name,
            "last_name": current_user.real_name,
        },
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url=url, json=body, headers=headers) as response:
            token = await response.json()
            return ApiResponse(data=token)


async def get_access_token():
    url = f"{base_url}/api/v1/security/login"
    body = {
        "username": "admin",
        "password": "REDACTED_REFERENCE_SECRET",
        "provider": "db",
        "refresh": True,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url=url, json=body) as response:
            tokens = await response.json()
            return tokens["access_token"], tokens["refresh_token"]


@router.get("/{name}")
async def fetch_sdk_id(name: str):
    return ApiResponse(
        data={
            "test": "8d9c7ea9-529f-418e-86a6-685e6c8c1aea",
            "af_data": "8d9c7ea9-529f-418e-86a6-685e6c8c1aea",
            "ad_data": "6fe36b68-46ba-4c25-b20d-9fc6c25d16bf",
        }.get(name)
    )
