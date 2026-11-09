-- 不修改已实测015；日事实归属冻结版本与明确的未知原因，普通补采不得历史更正。
ALTER TABLE orbit_account_spend_day
 ADD COLUMN attribution_version BIGINT NOT NULL DEFAULT 1 COMMENT '首次日事实冻结归属版本，普通迟到补采复制；双人更正另行发布新版本',
 ADD COLUMN attribution_reason VARCHAR(40) NOT NULL DEFAULT 'LEGACY_UNVERIFIED' COMMENT '完整唯一归属COVERED或UNASSIGNED原因；旧记录待核验不伪造证据';
ALTER TABLE orbit_account_spend_day_history
 ADD COLUMN attribution_version BIGINT NOT NULL DEFAULT 1 COMMENT '历史版本冻结归属版本，保留不可变快照',
 ADD COLUMN attribution_reason VARCHAR(40) NOT NULL DEFAULT 'LEGACY_UNVERIFIED' COMMENT '冻结归属依据或UNASSIGNED原因，补采原样复制';
