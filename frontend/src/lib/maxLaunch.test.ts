import { describe, expect, it } from 'vitest'
import { isMaxLaunchHash } from './maxLaunch'

describe('MAX launch hash', () => {
  it('recognizes MAX launch parameters in any order', () => {
    expect(isMaxLaunchHash('#WebAppData=user%3D%257B%257D&WebAppPlatform=web')).toBe(true)
    expect(isMaxLaunchHash('#other=value&WebAppPlatform=android')).toBe(true)
    expect(isMaxLaunchHash('#WebAppVersion=1')).toBe(true)
  })

  it('does not replace application routes or unrelated fragments', () => {
    expect(isMaxLaunchHash('#/')).toBe(false)
    expect(isMaxLaunchHash('#/share/WebAppData=example')).toBe(false)
    expect(isMaxLaunchHash('#other=value')).toBe(false)
    expect(isMaxLaunchHash('')).toBe(false)
  })
})
