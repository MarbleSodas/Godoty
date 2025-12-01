/**
 * Environment Detection Utility
 *
 * This utility helps determine whether the application is running in:
 * - PyWebView desktop mode (needs bridge communication)
 * - Browser mode (can use HTTP requests)
 */

export enum EnvironmentMode {
  DESKTOP = 'desktop',  // PyWebView desktop application
  BROWSER = 'browser',    // Web browser (development)
  UNKNOWN = 'unknown'    // Unable to determine
}

export class EnvironmentDetector {
  private static _cachedMode: EnvironmentMode | null = null;

  /**
   * Detect the current runtime environment
   */
  static detectEnvironment(): EnvironmentMode {
    if (this._cachedMode) {
      return this._cachedMode;
    }

    // Check if running in PyWebView desktop mode
    if (this.isPyWebViewDesktop()) {
      this._cachedMode = EnvironmentMode.DESKTOP;
      return EnvironmentMode.DESKTOP;
    }

    // Check if running in browser environment
    if (this.isBrowserEnvironment()) {
      this._cachedMode = EnvironmentMode.BROWSER;
      return EnvironmentMode.BROWSER;
    }

    // Unknown environment
    this._cachedMode = EnvironmentMode.UNKNOWN;
    return EnvironmentMode.UNKNOWN;
  }

  /**
   * Check if running in PyWebView desktop mode
   */
  static isPyWebViewDesktop(): boolean {
    const windowAny = window as any;

    // Primary check: pywebview API object
    if (windowAny.pywebview?.api) {
      return true;
    }

    // Secondary check: pywebview object exists (but API might not be ready yet)
    if (windowAny.pywebview) {
      return true;
    }

    // Tertiary check: desktop-specific indicators
    if (windowAny.electronAPI || windowAny.desktop) {
      return true;
    }

    return false;
  }

  /**
   * Check if running in browser environment
   */
  static isBrowserEnvironment(): boolean {
    // Check if we have typical browser APIs
    return !!(typeof window.fetch === 'function' && window.location && !this.isPyWebViewDesktop());
  }

  /**
   * Get the current environment mode
   */
  static getCurrentMode(): EnvironmentMode {
    return this.detectEnvironment();
  }

  /**
   * Check if desktop mode is available
   */
  static isDesktopMode(): boolean {
    return this.getCurrentMode() === EnvironmentMode.DESKTOP;
  }

  /**
   * Check if browser mode is available
   */
  static isBrowserMode(): boolean {
    return this.getCurrentMode() === EnvironmentMode.BROWSER;
  }

  /**
   * Reset cached environment detection (useful for testing)
   */
  static resetCache(): void {
    this._cachedMode = null;
  }

  /**
   * Get environment information for debugging
   */
  static getEnvironmentInfo(): {
    mode: EnvironmentMode;
    isPyWebView: boolean;
    isBrowser: boolean;
    hasPywebviewAPI: boolean;
    userAgent: string;
    location: string;
  } {
    const windowAny = window as any;

    return {
      mode: this.getCurrentMode(),
      isPyWebView: this.isPyWebViewDesktop(),
      isBrowser: this.isBrowserEnvironment(),
      hasPywebviewAPI: !!(windowAny.pywebview?.api),
      userAgent: navigator.userAgent,
      location: window.location.href
    };
  }
}