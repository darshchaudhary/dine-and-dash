export function resolveDeviceApiUrl({ configuredUrl, hosted, localAddress, port }) {
  if (hosted && !configuredUrl) {
    throw new Error("Set VITE_API_URL to your hosted HTTPS API in frontend/.env.production.local before building a release.");
  }
  const url = new URL(configuredUrl || `http://${localAddress()}:${port}`);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error("The API URL must be an HTTP(S) base URL without credentials, query parameters, or a fragment.");
  }
  const host = url.hostname.toLowerCase();
  const privateHost = host === "localhost" || host.endsWith(".localhost") || host.endsWith(".local") ||
    host === "[::1]" || host === "[::]" || /^\[(fc|fd|fe80)/.test(host) ||
    /^(0|10|127)\./.test(host) || /^192\.168\./.test(host) || /^169\.254\./.test(host) ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(host);
  if (hosted && (url.protocol !== "https:" || privateHost)) {
    throw new Error("A release needs a public HTTPS API, not localhost or your Mac's Wi-Fi address.");
  }
  return url.toString().replace(/\/$/, "");
}
