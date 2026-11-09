// 在 mongosh 中执行：mongosh "$MONGODB_URI" scripts/dev/ensure-ad-account-mongo-indexes.js
// 仅创建广告账户列表当前排序与补充信息查询实际使用的索引；createIndex 可重复执行。

const accountCollection = db.getCollection('fb_ad_accounts');
const usageRecordCollection = db.getCollection('feishu_account_used_record');

accountCollection.createIndex(
  { updated_at: -1, _id: -1 },
  { name: 'idx_fb_ad_accounts_updated_id' },
);
usageRecordCollection.createIndex(
  { account_id: 1 },
  { name: 'idx_feishu_account_used_record_account_id' },
);

printjson({
  fb_ad_accounts: accountCollection.getIndexes(),
  feishu_account_used_record: usageRecordCollection.getIndexes(),
});
