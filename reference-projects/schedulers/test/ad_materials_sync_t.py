# 1. 测试 D0 基础数据计算
# sync_af_cohort_d0("2025-01-10")
from tasks.ad_materials.ad_materials_sync import check_no_img


# 2. 测试日常增量更新（更新过去30天的DN列）
# sync_af_cohort_daily_increment()


# 3. 测试历史回填
# sync_af_cohort_d0("2025-10-28")              # 步骤1：创建D0基准
# sync_af_cohort_daily_increment("2025-10-28") # 步骤2：回填D1~D30
def ad_materials_sync():
    # from tasks.ad_materials.ad_materials_sync import run
    # from utils.common import SyncHourCompleted
    #
    # params: SyncHourCompleted = {
    #     "china_date": "2025-10-28",
    #     "game_platform": "JKT88",
    #     "agent_line": "jykx001",
    #     "ad_platform": "facebook",
    # }
    # run(params)
    from tasks.ad_materials.ad_materials_sync import fill_missing_data

    fill_missing_data("2025-05-23", "2025-11-13")


def run_write_ad_materials():
    from tasks.ad_materials.ad_materials_sync import write_ad_materials
    from conf.log_conf import init
    # from utils.common import set_local_proxy

    # set_local_proxy()

    init("write_ad_materials")
    write_ad_materials(3)


def check_no_material():
    check_no_img()


if __name__ == "__main__":
    # ad_materials_sync()
    # check_no_material()
    run_write_ad_materials()
