/** 主数据支持的媒体不等于广告执行能力；未支持的平台不能回退到其他媒体。 */
export function assertAdPublishingPlatform(platform: string) {
  if (!['facebook', 'google', 'tiktok'].includes(platform)) {
    throw new Error('当前平台不支持广告创建或发布');
  }
}
