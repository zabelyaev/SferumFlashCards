const maxLaunchParameters = ['WebAppData', 'WebAppPlatform', 'WebAppVersion', 'WebAppDeviceName']

export function isMaxLaunchHash(hash: string): boolean {
  if (!hash.startsWith('#') || hash.startsWith('#/')) return false
  const params = new URLSearchParams(hash.slice(1))
  return maxLaunchParameters.some((key) => params.has(key))
}
