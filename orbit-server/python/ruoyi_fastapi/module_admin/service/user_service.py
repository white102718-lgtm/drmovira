import io
import re
from collections.abc import Awaitable, Callable
from typing import Any

import pandas as pd
from fastapi import Request, UploadFile
from redis import asyncio as aioredis
from sqlalchemy import ColumnElement, and_
from sqlalchemy.ext.asyncio import AsyncSession

from common.constant import CommonConstant
from common.directory_mutation_policy import DirectoryMutationPolicy
from common.directory_policy import DirectoryReadPolicy
from common.enums import PasswordCharacterType
from common.vo import CrudResponseModel, PageModel
from exceptions.exception import ServiceException
from module_admin.dao.user_dao import UserDao
from module_admin.entity.do.user_do import SysUserRole
from module_admin.entity.vo.post_vo import PostPageQueryModel
from module_admin.entity.vo.user_vo import (
    AddUserModel,
    CrudUserRoleModel,
    CurrentUserModel,
    DeleteUserModel,
    EditUserModel,
    ResetUserModel,
    SelectedRoleModel,
    UserDetailModel,
    UserInfoModel,
    UserModel,
    UserPageQueryModel,
    UserPostModel,
    UserProfileModel,
    UserRoleModel,
    UserRoleQueryModel,
    UserRoleResponseModel,
    UserRowModel,
)
from module_admin.service.config_service import ConfigService
from module_admin.service.dept_service import DeptService
from module_admin.service.post_service import PostService
from module_admin.service.role_service import RoleService
from module_identity.service.identity_service import IdentitySecurityEventService, IdentitySubjectService
from utils.common_util import CamelCaseUtil
from utils.excel_util import ExcelUtil
from utils.pwd_util import PwdUtil
from utils.time_util import TimezoneUtil


class UserService:
    """
    用户管理模块服务层
    """

    PASSWORD_MIN_LENGTH = 6
    PASSWORD_MAX_LENGTH = 20
    _BUSINESS_ROLE_BATCH_LIMIT = 200

    _business_edit_guards: tuple[Callable[[AsyncSession, EditUserModel], Awaitable[None]], ...] = ()
    _business_role_guards: tuple[Callable[[AsyncSession, list[int]], Awaitable[None]], ...] = ()
    _business_contact_policies: tuple[Callable[[AsyncSession, int], Awaitable[bool]], ...] = ()
    _business_change_bridges: tuple[
        tuple[Callable[[AsyncSession, int], Awaitable[Any]], Callable[[AsyncSession, Any], Awaitable[None]]], ...
    ] = ()

    @staticmethod
    def _check_unique_role_references(role_ids: list[str], unique_ids: set[int]) -> None:
        """原入口也在DAO写入前拒绝重复引用，不能依赖数据库冲突变成500。"""
        if len(role_ids) != len(unique_ids):
            raise ServiceException(message='功能角色引用不能重复')

    @classmethod
    def register_business_change_bridge(
        cls,
        capture: Callable[[AsyncSession, int], Awaitable[Any]],
        finish: Callable[[AsyncSession, Any], Awaitable[None]],
    ) -> None:
        """宿主在同一事务捕获修改前状态并在提交前写入业务版本及审计，不执行额外commit。"""
        bridge = (capture, finish)
        if bridge not in cls._business_change_bridges:
            cls._business_change_bridges += (bridge,)

    @classmethod
    async def _capture_business_changes(cls, query_db: AsyncSession, user_id: int) -> list[tuple[Any, Any]]:
        return [(finish, await capture(query_db, user_id)) for capture, finish in cls._business_change_bridges]

    @classmethod
    async def _capture_business_role_changes(
        cls, query_db: AsyncSession, user_ids: list[int | str]
    ) -> list[tuple[Any, Any]]:
        """宿主业务启用时先冻结整批目标，避免写入到一半才发现越租户或超量。"""
        if not cls._business_change_bridges and not cls._business_role_guards:
            return []
        if len(user_ids) > cls._BUSINESS_ROLE_BATCH_LIMIT:
            raise ServiceException(message='组织目录角色批量操作每次最多200人，请分批提交')
        try:
            identifiers = sorted({int(identifier) for identifier in user_ids})
            if any(identifier <= 0 or identifier >= 2**63 for identifier in identifiers):
                raise ValueError
        except (TypeError, ValueError):
            raise ServiceException(message='用户ID列表无效') from None
        for guard in cls._business_role_guards:
            await guard(query_db, identifiers)
        captured = []
        for user_id in identifiers:
            captured.extend(await cls._capture_business_changes(query_db, user_id))
        return captured

    @classmethod
    def register_business_role_guard(cls, guard: Callable[[AsyncSession, list[int]], Awaitable[None]]) -> None:
        """角色分配包含空操作时也先检查宿主权限；不能把资料自服务例外当成角色管理授权。"""
        if guard not in cls._business_role_guards:
            cls._business_role_guards += (guard,)

    @classmethod
    def register_business_contact_policy(cls, policy: Callable[[AsyncSession, int], Awaitable[bool]]) -> None:
        """宿主可明确业务人员联系方式不唯一；独立框架和原技术账号仍使用原检查。"""
        if policy not in cls._business_contact_policies:
            cls._business_contact_policies += (policy,)

    @staticmethod
    async def _finish_business_changes(query_db: AsyncSession, captured: list[tuple[Any, Any]]) -> None:
        for finish, snapshot in captured:
            await finish(query_db, snapshot)

    @classmethod
    def register_business_edit_guard(cls, guard: Callable[[AsyncSession, EditUserModel], Awaitable[None]]) -> None:
        """普通资料编辑同样允许宿主校验业务边界，不依赖是否触发角色或状态事件。"""
        if guard not in cls._business_edit_guards:
            cls._business_edit_guards += (guard,)

    @classmethod
    async def _check_business_edit_guards(cls, query_db: AsyncSession, value: EditUserModel) -> None:
        """提交前校验普通资料编辑，不向原独立框架强加业务租户实现。"""
        for guard in cls._business_edit_guards:
            await guard(query_db, value)

    @staticmethod
    async def _current_role_ids(query_db: AsyncSession, user_id: int) -> set[int]:
        """
        读取用户当前角色ID，用于避免无变化时递增身份版本

        :param query_db: orm对象
        :param user_id: 用户id
        :return: 用户当前角色ID集合
        """
        return await UserDao.get_role_ids(query_db, user_id)

    @staticmethod
    async def _handle_role_assignment_changes(
        query_db: AsyncSession, user_ids: list[int], actor: str | None = None
    ) -> None:
        """
        仅在角色关联实际变化时批量触发身份安全事件

        :param query_db: orm对象
        :param user_ids: 角色关联发生变化的用户ID列表
        :param actor: 实际执行角色分配的操作者
        :return: None
        """
        if user_ids:
            await IdentitySecurityEventService.handle_users_event(
                query_db,
                user_ids,
                'role_assignment_changed',
                actor=actor,
            )

    @classmethod
    async def validate_password_services(
        cls,
        redis: aioredis.Redis,
        password: str | None,
        pwd_chrtype: PasswordCharacterType | str | None = None,
    ) -> None:
        """
        校验密码是否符合系统密码策略。

        :param redis: redis对象
        :param password: 明文密码
        :param pwd_chrtype: 指定密码字符范围，未指定时读取系统配置
        :return: None
        """
        if pwd_chrtype is None:
            pwd_chrtype = await ConfigService.query_config_list_from_cache_services(redis, 'sys.account.chrtype')
        password_character_type = (
            pwd_chrtype
            if isinstance(pwd_chrtype, PasswordCharacterType)
            else PasswordCharacterType.from_code(pwd_chrtype)
        )

        if not password:
            raise ServiceException(message='密码不能为空')
        if len(password) < cls.PASSWORD_MIN_LENGTH or len(password) > cls.PASSWORD_MAX_LENGTH:
            raise ServiceException(message='密码长度必须介于 6 和 20 之间')

        if not re.fullmatch(password_character_type.pattern, password):
            raise ServiceException(message=password_character_type.message)

    @classmethod
    async def get_user_list_services(
        cls,
        query_db: AsyncSession,
        query_object: UserPageQueryModel,
        data_scope_sql: ColumnElement,
        is_page: bool = False,
    ) -> PageModel[UserRowModel] | list[dict[str, Any]]:
        """
        获取用户列表信息service

        :param query_db: orm对象
        :param query_object: 查询参数对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :param is_page: 是否开启分页
        :return: 用户列表信息对象
        """
        business_scope = await DirectoryReadPolicy.scope(query_db, 'USER')
        query_result = await UserDao.get_user_list(
            query_db, query_object, and_(data_scope_sql, business_scope), is_page
        )
        if is_page:
            user_list_result = PageModel[UserRowModel](
                **{
                    **query_result.model_dump(by_alias=True),
                    'rows': [{**row[0], 'dept': row[1]} for row in query_result.rows],
                }
            )
        else:
            user_list_result = []
            if query_result:
                user_list_result = [{**row[0], 'dept': row[1]} for row in query_result]

        return user_list_result

    @classmethod
    async def check_user_allowed_services(cls, check_user: UserModel) -> CrudResponseModel:
        """
        校验用户是否允许操作service

        :param check_user: 用户信息
        :return: 校验结果
        """
        if check_user.admin:
            raise ServiceException(message='不允许操作超级管理员用户')
        return CrudResponseModel(is_success=True, message='校验通过')

    @classmethod
    async def check_user_data_scope_services(
        cls, query_db: AsyncSession, user_id: int, data_scope_sql: ColumnElement
    ) -> CrudResponseModel:
        """
        校验用户数据权限service

        :param query_db: orm对象
        :param user_id: 用户id
        :param data_scope_sql: 数据权限对应的查询sql语句
        :return: 校验结果
        """
        users = await UserDao.get_user_list(query_db, UserPageQueryModel(userId=user_id), data_scope_sql, is_page=False)
        if users:
            return CrudResponseModel(is_success=True, message='校验通过')
        raise ServiceException(message='没有权限访问用户数据')

    @classmethod
    async def check_user_name_unique_services(cls, query_db: AsyncSession, page_object: UserModel) -> bool:
        """
        校验用户名是否唯一service

        :param query_db: orm对象
        :param page_object: 用户对象
        :return: 校验结果
        """
        user_id = -1 if page_object.user_id is None else page_object.user_id
        user = await UserDao.get_user_by_info(query_db, UserModel(userName=page_object.user_name))
        if user and user.user_id != user_id:
            return CommonConstant.NOT_UNIQUE
        return CommonConstant.UNIQUE

    @classmethod
    async def check_phonenumber_unique_services(cls, query_db: AsyncSession, page_object: UserModel) -> bool:
        """
        校验用户手机号是否唯一service

        :param query_db: orm对象
        :param page_object: 用户对象
        :return: 校验结果
        """
        user_id = -1 if page_object.user_id is None else page_object.user_id
        user = await UserDao.get_user_by_info(query_db, UserModel(phonenumber=page_object.phonenumber))
        if user and user.user_id != user_id:
            return CommonConstant.NOT_UNIQUE
        return CommonConstant.UNIQUE

    @classmethod
    async def check_email_unique_services(cls, query_db: AsyncSession, page_object: UserModel) -> bool:
        """
        校验用户邮箱是否唯一service

        :param query_db: orm对象
        :param page_object: 用户对象
        :return: 校验结果
        """
        user_id = -1 if page_object.user_id is None else page_object.user_id
        user = await UserDao.get_user_by_info(query_db, UserModel(email=page_object.email))
        if user and user.user_id != user_id:
            return CommonConstant.NOT_UNIQUE
        return CommonConstant.UNIQUE

    @classmethod
    async def add_user_services(cls, query_db: AsyncSession, page_object: AddUserModel) -> CrudResponseModel:
        """
        新增用户信息service

        :param query_db: orm对象
        :param page_object: 新增用户对象
        :return: 新增用户校验结果
        """
        add_user = UserModel(**page_object.model_dump(by_alias=True, exclude={'create_time', 'update_time'}))
        if not await cls.check_user_name_unique_services(query_db, page_object):
            raise ServiceException(message=f'新增用户{page_object.user_name}失败，登录账号已存在')
        if page_object.phonenumber and not await cls.check_phonenumber_unique_services(query_db, page_object):
            raise ServiceException(message=f'新增用户{page_object.user_name}失败，手机号码已存在')
        if page_object.email and not await cls.check_email_unique_services(query_db, page_object):
            raise ServiceException(message=f'新增用户{page_object.user_name}失败，邮箱账号已存在')
        try:
            add_result = await UserDao.add_user_dao(query_db, add_user)
            user_id = add_result.user_id
            await IdentitySubjectService.create_for_new_user(
                query_db,
                user_id=user_id,
                create_by=page_object.create_by,
            )
            if page_object.role_ids:
                for role in page_object.role_ids:
                    await UserDao.add_user_role_dao(query_db, UserRoleModel(userId=user_id, roleId=role))
            if page_object.post_ids:
                for post in page_object.post_ids:
                    await UserDao.add_user_post_dao(query_db, UserPostModel(userId=user_id, postId=post))
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='新增成功')
        except Exception as e:
            await query_db.rollback()
            raise e

    @classmethod
    def _deal_edit_user(cls, page_object: EditUserModel, edit_user: dict[str, Any]) -> None:
        """
        处理编辑用户字典

        :param page_object: 编辑用户对象
        :param edit_user: 编辑用户字典
        :return: None
        """
        if page_object.type not in ['status', 'avatar', 'pwd', 'profile']:
            del edit_user['role_ids']
            del edit_user['post_ids']
            edit_user.pop('role', None)
        else:
            del edit_user['type']

    @classmethod
    async def _handle_edit_identity_security_event(
        cls,
        query_db: AsyncSession,
        page_object: EditUserModel,
        current_user: UserInfoModel,
    ) -> None:
        """
        将用户编辑类型映射为同事务OIDC安全事件

        :param query_db: orm对象
        :param page_object: 编辑用户对象
        :param current_user: 编辑前的用户信息
        :return: None
        """
        user_id = page_object.user_id
        if user_id is None:
            raise ServiceException(message='用户不存在')
        # 状态既能从专用按钮修改，也能来自完整编辑表单；两条路径共享同事务保护。
        if 'status' in page_object.model_fields_set and page_object.status != current_user.status:
            await IdentitySecurityEventService.handle_user_event(
                query_db,
                user_id,
                'user_disabled' if page_object.status == '1' else 'user_enabled',
                actor=page_object.update_by,
            )
        if page_object.type == 'status':
            return
        if page_object.type == 'pwd':
            if page_object.password is not None:
                await IdentitySecurityEventService.handle_user_event(
                    query_db,
                    user_id,
                    'password_changed',
                    actor=page_object.update_by,
                )
            return
        if page_object.type in {'avatar', 'profile'}:
            return

        current_roles = {int(value) for value in (current_user.role_ids or '').split(',') if value.isdigit()}
        requested_roles = {int(value) for value in (page_object.role_ids or [])}
        roles_changed = 'role_ids' in page_object.model_fields_set and current_roles != requested_roles
        department_changed = 'dept_id' in page_object.model_fields_set and current_user.dept_id != page_object.dept_id
        if roles_changed or department_changed:
            event = 'role_assignment_changed' if roles_changed else 'department_changed'
            await IdentitySecurityEventService.handle_user_event(
                query_db,
                user_id,
                event,
                actor=page_object.update_by,
            )

    @classmethod
    async def edit_user_services(cls, query_db: AsyncSession, page_object: EditUserModel) -> CrudResponseModel:
        """
        编辑用户信息service

        :param query_db: orm对象
        :param page_object: 编辑用户对象
        :return: 编辑用户校验结果
        """
        # 登录也复用此写服务更新登录时间；只读修改前状态，不加载管理页面的所有选项。
        # 写授权仍由下面的业务编辑/安全事件守卫检查，不能借管理读取要求阻断认证本身。
        previous = await UserDao.get_user_detail_by_id(query_db, page_object.user_id)
        basic = previous.get('user_basic_info')
        user_info = (
            UserInfoModel(
                **CamelCaseUtil.transform_result(basic),
                roleIds=','.join(str(row.role_id) for row in previous.get('user_role_info') or []),
            )
            if basic
            else None
        )
        if user_info and user_info.user_id:
            # 先授权后检查字段，不能用全局唯一性提示探测无权租户的联系方式。
            await cls._check_business_edit_guards(query_db, page_object)
            # 宿主可以规范化业务字段，写入字典必须在守卫后生成，不能继续保存旧原始值。
            edit_user = page_object.model_dump(
                exclude_unset=True,
                exclude={'admin', 'create_time', 'update_time'},
            )
            cls._deal_edit_user(page_object, edit_user)
            if page_object.type not in ['status', 'avatar', 'pwd']:
                unique_contacts = all(
                    [await policy(query_db, page_object.user_id) for policy in cls._business_contact_policies]
                )
                if not await cls.check_user_name_unique_services(query_db, page_object):
                    raise ServiceException(message=f'修改用户{page_object.user_name}失败，登录账号已存在')
                if (
                    unique_contacts
                    and page_object.phonenumber
                    and not await cls.check_phonenumber_unique_services(query_db, page_object)
                ):
                    raise ServiceException(message=f'修改用户{page_object.user_name}失败，手机号码已存在')
                if (
                    unique_contacts
                    and page_object.email
                    and not await cls.check_email_unique_services(query_db, page_object)
                ):
                    raise ServiceException(message=f'修改用户{page_object.user_name}失败，邮箱账号已存在')
            try:
                captured = await cls._capture_business_changes(query_db, page_object.user_id)
                await UserDao.edit_user_dao(query_db, edit_user)
                if page_object.type not in {'status', 'avatar', 'pwd', 'profile'}:
                    await UserDao.delete_user_role_dao(query_db, UserRoleModel(userId=page_object.user_id))
                    await UserDao.delete_user_post_dao(query_db, UserPostModel(userId=page_object.user_id))
                    if page_object.role_ids:
                        for role in page_object.role_ids:
                            await UserDao.add_user_role_dao(
                                query_db, UserRoleModel(userId=page_object.user_id, roleId=role)
                            )
                    if page_object.post_ids:
                        for post in page_object.post_ids:
                            await UserDao.add_user_post_dao(
                                query_db, UserPostModel(userId=page_object.user_id, postId=post)
                            )
                await cls._handle_edit_identity_security_event(query_db, page_object, user_info)
                await cls._finish_business_changes(query_db, captured)
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='更新成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='用户不存在')

    @classmethod
    async def delete_user_services(cls, query_db: AsyncSession, page_object: DeleteUserModel) -> CrudResponseModel:
        """
        删除用户信息service

        :param query_db: orm对象
        :param page_object: 删除用户对象
        :return: 删除用户校验结果
        """
        if page_object.user_ids:
            user_id_list = page_object.user_ids.split(',')
            try:
                await DirectoryMutationPolicy.guard(query_db, 'USER_DELETE', user_id_list)
                for user_id in user_id_list:
                    user_id_dict = {
                        'userId': user_id,
                        'updateBy': page_object.update_by,
                        'updateTime': page_object.update_time,
                    }
                    await UserDao.delete_user_role_dao(query_db, UserRoleModel(**user_id_dict))
                    await UserDao.delete_user_post_dao(query_db, UserPostModel(**user_id_dict))
                    await UserDao.delete_user_dao(query_db, UserModel(**user_id_dict))
                    await IdentitySecurityEventService.handle_user_event(
                        query_db,
                        int(user_id),
                        'user_deleted',
                        actor=page_object.update_by,
                    )
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='删除成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='传入用户id为空')

    @classmethod
    async def user_detail_services(cls, query_db: AsyncSession, user_id: int | str) -> UserDetailModel:
        """
        获取用户详细信息service

        :param query_db: orm对象
        :param user_id: 用户id
        :return: 用户id对应的信息
        """
        if user_id != '':
            await DirectoryReadPolicy.guard(query_db, 'USER', int(user_id))
        posts = await PostService.get_post_list_services(query_db, PostPageQueryModel(), is_page=False)
        roles = await RoleService.get_role_select_option_services(query_db)
        if user_id != '':
            query_user = await UserDao.get_user_detail_by_id(query_db, user_id=user_id)
            roles = cls._include_assigned_roles(roles, query_user.get('user_role_info') or [])
            post_ids = ','.join([str(row.post_id) for row in query_user.get('user_post_info')])
            post_ids_list = [row.post_id for row in query_user.get('user_post_info')]
            role_ids = ','.join([str(row.role_id) for row in query_user.get('user_role_info')])
            role_ids_list = [row.role_id for row in query_user.get('user_role_info')]

            return UserDetailModel(
                **CamelCaseUtil.transform_result(await DirectoryReadPolicy.describe(query_db, 'USER', int(user_id))),
                data=UserInfoModel(
                    **CamelCaseUtil.transform_result(query_user.get('user_basic_info')),
                    postIds=post_ids,
                    roleIds=role_ids,
                    dept=CamelCaseUtil.transform_result(query_user.get('user_dept_info')),
                    role=CamelCaseUtil.transform_result(query_user.get('user_role_info')),
                ),
                postIds=post_ids_list,
                posts=posts,
                roleIds=role_ids_list,
                roles=roles,
            )

        return UserDetailModel(posts=posts, roles=roles)

    @staticmethod
    def _include_assigned_roles(options: list[dict[str, Any]], assigned: list[Any]) -> list[dict[str, Any]]:
        """已有角色即使停用也要回显且禁选，不能因编辑基础资料而静默解除原关联。"""
        known = {int(option['roleId']) for option in options}
        return options + [
            CamelCaseUtil.transform_result(role) for role in assigned if role.role_id != 1 and role.role_id not in known
        ]

    @classmethod
    async def update_user_timezone_services(
        cls, query_db: AsyncSession, user_id: int, user_name: str, time_zone: str
    ) -> CrudResponseModel:
        """
        更新当前账号的显示时区

        :param query_db: 数据库会话
        :param user_id: 当前登录用户ID
        :param user_name: 当前登录用户账号
        :param time_zone: auto或IANA时区名称
        :return: 时区更新结果
        """
        preference = TimezoneUtil.validate_timezone_preference(time_zone)
        try:
            await UserDao.edit_user_dao(query_db, {'user_id': user_id, 'time_zone': preference, 'update_by': user_name})
            await query_db.commit()
        except Exception:
            await query_db.rollback()
            raise
        return CrudResponseModel(is_success=True, message='时区设置已保存')

    @classmethod
    async def user_profile_services(cls, query_db: AsyncSession, user_id: int) -> UserProfileModel:
        """
        获取用户个人详细信息service

        :param query_db: orm对象
        :param user_id: 用户id
        :return: 用户id对应的信息
        """
        query_user = await UserDao.get_user_detail_by_id(query_db, user_id=user_id)
        post_ids = ','.join([str(row.post_id) for row in query_user.get('user_post_info')])
        post_group = ','.join([row.post_name for row in query_user.get('user_post_info')])
        role_ids = ','.join([str(row.role_id) for row in query_user.get('user_role_info')])
        role_group = ','.join([row.role_name for row in query_user.get('user_role_info')])

        return UserProfileModel(
            data=UserInfoModel(
                **CamelCaseUtil.transform_result(query_user.get('user_basic_info')),
                postIds=post_ids,
                roleIds=role_ids,
                dept=CamelCaseUtil.transform_result(query_user.get('user_dept_info')),
                role=CamelCaseUtil.transform_result(query_user.get('user_role_info')),
            ),
            postGroup=post_group,
            roleGroup=role_group,
        )

    @classmethod
    async def reset_user_services(cls, query_db: AsyncSession, page_object: ResetUserModel) -> CrudResponseModel:
        """
        重置用户密码service

        :param query_db: orm对象
        :param page_object: 重置用户对象
        :return: 重置用户校验结果
        """
        reset_user = page_object.model_dump(
            exclude_unset=True,
            exclude={'admin', 'create_time', 'update_time'},
        )
        if page_object.old_password:
            user = (await UserDao.get_user_detail_by_id(query_db, user_id=page_object.user_id)).get('user_basic_info')
            if not PwdUtil.verify_password(page_object.old_password, user.password):
                raise ServiceException(message='修改密码失败，旧密码错误')
            if PwdUtil.verify_password(page_object.password, user.password):
                raise ServiceException(message='新密码不能与旧密码相同')
            del reset_user['old_password']
        if page_object.sms_code and page_object.session_id:
            del reset_user['sms_code']
            del reset_user['session_id']
        try:
            reset_user['password'] = PwdUtil.get_password_hash(page_object.password)
            await UserDao.edit_user_dao(query_db, reset_user)
            await IdentitySecurityEventService.handle_user_event(
                query_db,
                page_object.user_id,
                'password_changed',
                actor=page_object.update_by,
            )
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='重置成功')
        except Exception as e:
            await query_db.rollback()
            raise e

    @classmethod
    def _set_row_sex_value(cls, row: pd.Series) -> None:
        """
        设置行性别值

        :param row: 行数据
        :return: None
        """
        if row['sex'] == '男':
            row['sex'] = '0'
        if row['sex'] == '女':
            row['sex'] = '1'
        if row['sex'] == '未知':
            row['sex'] = '2'

    @classmethod
    def _set_row_status_value(cls, row: pd.Series) -> None:
        """
        设置行状态值

        :param row: 行数据
        :return: None
        """
        if row['status'] == '正常':
            row['status'] = '0'
        if row['status'] == '停用':
            row['status'] = '1'

    @classmethod
    async def batch_import_user_services(
        cls,
        request: Request,
        query_db: AsyncSession,
        file: UploadFile,
        update_support: bool,
        current_user: CurrentUserModel,
        user_data_scope_sql: ColumnElement,
        dept_data_scope_sql: ColumnElement,
    ) -> CrudResponseModel:
        """
        批量导入用户service

        :param request: Request对象
        :param query_db: orm对象
        :param file: 用户导入文件对象
        :param update_support: 用户存在时是否更新
        :param current_user: 当前用户对象
        :param user_data_scope_sql: 用户数据权限sql
        :param dept_data_scope_sql: 部门数据权限sql
        :return: 批量导入用户结果
        """
        header_dict = {
            '部门编号': 'dept_id',
            '登录名称': 'user_name',
            '用户名称': 'nick_name',
            '用户邮箱': 'email',
            '手机号码': 'phonenumber',
            '用户性别': 'sex',
            '帐号状态': 'status',
        }
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))
        await file.close()
        df.rename(columns=header_dict, inplace=True)
        if not set(header_dict.values()).issubset(df.columns):
            raise ServiceException(message='导入模板字段不完整，请下载最新技术用户模板')
        add_error_result = []
        count = 0
        init_password = await ConfigService.query_config_list_from_cache_services(
            request.app.state.redis, 'sys.user.initPassword'
        )
        await cls.validate_password_services(request.app.state.redis, init_password)
        try:
            # 不更新已存在用户时沿用原“跳过并报告”流程；更新模式先核对整批业务映射。
            await DirectoryMutationPolicy.guard(
                query_db, 'USER_IMPORT', df['user_name'].tolist() if update_support else []
            )
            for _index, row in df.iterrows():
                count = count + 1
                cls._set_row_sex_value(row)
                cls._set_row_status_value(row)
                add_user = UserModel(
                    deptId=row['dept_id'],
                    userName=row['user_name'],
                    password=PwdUtil.get_password_hash(init_password),
                    nickName=row['nick_name'],
                    email=row['email'],
                    phonenumber=str(row['phonenumber']),
                    sex=row['sex'],
                    status=row['status'],
                    createBy=current_user.user.user_name,
                    updateBy=current_user.user.user_name,
                )
                user_info = await UserDao.get_user_by_info(query_db, UserModel(userName=row['user_name']))
                if user_info:
                    if update_support:
                        edit_user_model = UserModel(
                            userId=user_info.user_id,
                            deptId=row['dept_id'],
                            userName=row['user_name'],
                            nickName=row['nick_name'],
                            email=row['email'],
                            phonenumber=str(row['phonenumber']),
                            sex=row['sex'],
                            status=row['status'],
                            updateBy=current_user.user.user_name,
                        )
                        edit_user_model.validate_fields()
                        await cls.check_user_allowed_services(edit_user_model)
                        if not current_user.user.admin:
                            await cls.check_user_data_scope_services(
                                query_db, edit_user_model.user_id, user_data_scope_sql
                            )
                            await DeptService.check_dept_data_scope_services(
                                query_db, edit_user_model.dept_id, dept_data_scope_sql
                            )
                        edit_user = edit_user_model.model_dump(
                            exclude_unset=True,
                            exclude={'create_time', 'update_time'},
                        )
                        await UserDao.edit_user_dao(query_db, edit_user)
                        if edit_user_model.status == '1' and user_info.status != '1':
                            await IdentitySecurityEventService.handle_user_event(
                                query_db,
                                user_info.user_id,
                                'user_disabled',
                                actor=current_user.user.user_name,
                            )
                        if edit_user_model.dept_id != user_info.dept_id:
                            await IdentitySecurityEventService.handle_user_event(
                                query_db,
                                user_info.user_id,
                                'department_changed',
                                actor=current_user.user.user_name,
                            )
                    else:
                        add_error_result.append(f'{count}.用户账号{row["user_name"]}已存在')
                else:
                    add_user.validate_fields()
                    if not current_user.user.admin:
                        await DeptService.check_dept_data_scope_services(
                            query_db, add_user.dept_id, dept_data_scope_sql
                        )
                    added_user = await UserDao.add_user_dao(query_db, add_user)
                    await IdentitySubjectService.create_for_new_user(
                        query_db,
                        user_id=added_user.user_id,
                        create_by=current_user.user.user_name,
                    )
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='\n'.join(add_error_result))
        except Exception as e:
            await query_db.rollback()
            raise e

    @staticmethod
    async def get_user_import_template_services() -> bytes:
        """
        获取用户导入模板service

        :return: 用户导入模板excel的二进制数据
        """
        header_list = ['部门编号', '登录名称', '用户名称', '用户邮箱', '手机号码', '用户性别', '帐号状态']
        selector_header_list = ['用户性别', '帐号状态']
        option_list = [{'用户性别': ['男', '女', '未知']}, {'帐号状态': ['正常', '停用']}]
        binary_data = ExcelUtil.get_excel_template(
            header_list=header_list, selector_header_list=selector_header_list, option_list=option_list
        )

        return binary_data

    @staticmethod
    async def export_user_list_services(user_list: list) -> bytes:
        """
        导出用户信息service

        :param user_list: 用户信息列表
        :return: 用户信息对应excel的二进制数据
        """
        # 创建一个映射字典，将英文键映射到中文键
        mapping_dict = {
            'userId': '用户编号',
            'userName': '用户名称',
            'nickName': '用户昵称',
            'deptName': '部门',
            'email': '邮箱地址',
            'phonenumber': '手机号码',
            'sex': '性别',
            'status': '状态',
            'createBy': '创建者',
            'createTime': '创建时间',
            'updateBy': '更新者',
            'updateTime': '更新时间',
            'remark': '备注',
        }

        for item in user_list:
            # 业务人员可以不绑定若依部门；导出仍保留空部门列。
            item['deptName'] = (item.get('dept') or {}).get('deptName')
            if item.get('status') == '0':
                item['status'] = '正常'
            else:
                item['status'] = '停用'
            if item.get('sex') == '0':
                item['sex'] = '男'
            elif item.get('sex') == '1':
                item['sex'] = '女'
            else:
                item['sex'] = '未知'
        binary_data = ExcelUtil.export_list2excel(user_list, mapping_dict)

        return binary_data

    @classmethod
    async def get_user_role_allocated_list_services(
        cls, query_db: AsyncSession, page_object: UserRoleQueryModel
    ) -> UserRoleResponseModel:
        """
        根据用户id获取已分配角色列表

        :param query_db: orm对象
        :param page_object: 用户关联角色对象
        :return: 已分配角色列表
        """
        await DirectoryReadPolicy.guard(query_db, 'USER', page_object.user_id)
        query_user = await UserDao.get_user_detail_by_id(query_db, page_object.user_id)
        post_ids = ','.join([str(row.post_id) for row in query_user.get('user_post_info')])
        role_ids = ','.join([str(row.role_id) for row in query_user.get('user_role_info')])
        user = UserInfoModel(
            **CamelCaseUtil.transform_result(query_user.get('user_basic_info')),
            postIds=post_ids,
            roleIds=role_ids,
            dept=CamelCaseUtil.transform_result(query_user.get('user_dept_info')),
            role=CamelCaseUtil.transform_result(query_user.get('user_role_info')),
        )
        options = cls._include_assigned_roles(
            await RoleService.get_role_select_option_services(query_db),
            query_user.get('user_role_info') or [],
        )
        query_role_list = [SelectedRoleModel(**row) for row in options]
        for model_a in query_role_list:
            for model_b in user.role:
                if model_a.role_id == model_b.role_id:
                    model_a.flag = True
        result = UserRoleResponseModel(roles=query_role_list, user=user)

        return result

    @classmethod
    async def add_user_role_services(
        cls, query_db: AsyncSession, page_object: CrudUserRoleModel, actor: str | None = None
    ) -> CrudResponseModel:
        """
        新增用户关联角色信息service

        :param query_db: orm对象
        :param page_object: 新增用户关联角色对象
        :param actor: 实际执行角色分配的操作者
        :return: 新增用户关联角色校验结果
        """
        if page_object.user_id and page_object.role_ids:
            role_id_list = page_object.role_ids.split(',')
            try:
                requested_role_ids = {int(role_id) for role_id in role_id_list}
                captured = await cls._capture_business_role_changes(query_db, [page_object.user_id])
                cls._check_unique_role_references(role_id_list, requested_role_ids)
                if await cls._current_role_ids(query_db, page_object.user_id) == requested_role_ids:
                    await query_db.commit()
                    return CrudResponseModel(is_success=True, message='分配成功')
                await UserDao.delete_user_role_by_user_and_role_dao(query_db, UserRoleModel(userId=page_object.user_id))
                for role_id in role_id_list:
                    await UserDao.add_user_role_dao(query_db, UserRoleModel(userId=page_object.user_id, roleId=role_id))
                await IdentitySecurityEventService.handle_user_event(
                    query_db,
                    page_object.user_id,
                    'role_assignment_changed',
                    actor=actor,
                )
                await cls._finish_business_changes(query_db, captured)
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='分配成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        elif page_object.user_id and not page_object.role_ids:
            try:
                captured = await cls._capture_business_role_changes(query_db, [page_object.user_id])
                if not await cls._current_role_ids(query_db, page_object.user_id):
                    await query_db.commit()
                    return CrudResponseModel(is_success=True, message='分配成功')
                await UserDao.delete_user_role_by_user_and_role_dao(query_db, UserRoleModel(userId=page_object.user_id))
                await IdentitySecurityEventService.handle_user_event(
                    query_db,
                    page_object.user_id,
                    'role_assignment_changed',
                    actor=actor,
                )
                await cls._finish_business_changes(query_db, captured)
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='分配成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        elif page_object.user_ids and page_object.role_id:
            user_id_list = page_object.user_ids.split(',')
            try:
                captured = await cls._capture_business_role_changes(query_db, user_id_list)
                changed_user_ids: list[int] = []
                for user_id in user_id_list:
                    user_role = await cls.detail_user_role_services(
                        query_db, UserRoleModel(userId=user_id, roleId=page_object.role_id)
                    )
                    if user_role:
                        continue
                    await UserDao.add_user_role_dao(query_db, UserRoleModel(userId=user_id, roleId=page_object.role_id))
                    changed_user_ids.append(int(user_id))
                await cls._handle_role_assignment_changes(query_db, changed_user_ids, actor)
                await cls._finish_business_changes(query_db, captured)
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='新增成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='不满足新增条件')

    @classmethod
    async def delete_user_role_services(
        cls, query_db: AsyncSession, page_object: CrudUserRoleModel, actor: str | None = None
    ) -> CrudResponseModel:
        """
        删除用户关联角色信息service

        :param query_db: orm对象
        :param page_object: 删除用户关联角色对象
        :param actor: 实际执行取消分配的操作者
        :return: 删除用户关联角色校验结果
        """
        if (page_object.user_id and page_object.role_id) or (page_object.user_ids and page_object.role_id):
            if page_object.user_id and page_object.role_id:
                try:
                    captured = await cls._capture_business_role_changes(query_db, [page_object.user_id])
                    existing = await cls.detail_user_role_services(
                        query_db,
                        UserRoleModel(userId=page_object.user_id, roleId=page_object.role_id),
                    )
                    await UserDao.delete_user_role_by_user_and_role_dao(
                        query_db, UserRoleModel(userId=page_object.user_id, roleId=page_object.role_id)
                    )
                    if existing is not None:
                        await IdentitySecurityEventService.handle_user_event(
                            query_db,
                            page_object.user_id,
                            'role_assignment_changed',
                            actor=actor,
                        )
                    await cls._finish_business_changes(query_db, captured)
                    await query_db.commit()
                    return CrudResponseModel(is_success=True, message='删除成功')
                except Exception as e:
                    await query_db.rollback()
                    raise e
            elif page_object.user_ids and page_object.role_id:
                user_id_list = page_object.user_ids.split(',')
                try:
                    captured = await cls._capture_business_role_changes(query_db, user_id_list)
                    changed_user_ids: list[int] = []
                    for user_id in user_id_list:
                        existing = await cls.detail_user_role_services(
                            query_db,
                            UserRoleModel(userId=user_id, roleId=page_object.role_id),
                        )
                        await UserDao.delete_user_role_by_user_and_role_dao(
                            query_db, UserRoleModel(userId=user_id, roleId=page_object.role_id)
                        )
                        if existing is not None:
                            changed_user_ids.append(int(user_id))
                    await cls._handle_role_assignment_changes(query_db, changed_user_ids, actor)
                    await cls._finish_business_changes(query_db, captured)
                    await query_db.commit()
                    return CrudResponseModel(is_success=True, message='删除成功')
                except Exception as e:
                    await query_db.rollback()
                    raise e
            else:
                raise ServiceException(message='不满足删除条件')
        else:
            raise ServiceException(message='传入用户角色关联信息为空')

    @classmethod
    async def detail_user_role_services(cls, query_db: AsyncSession, page_object: UserRoleModel) -> SysUserRole | None:
        """
        获取用户关联角色详细信息service

        :param query_db: orm对象
        :param page_object: 用户关联角色对象
        :return: 用户关联角色详细信息
        """
        user_role = await UserDao.get_user_role_detail(query_db, page_object)

        return user_role
