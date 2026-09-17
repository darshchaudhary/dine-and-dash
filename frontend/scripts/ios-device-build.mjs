import { spawnSync } from "node:child_process";
import { networkInterfaces } from "node:os";
import { loadEnv } from "vite";
import { resolveDeviceApiUrl } from "./ios-api-url.mjs";

function localAddress() {
  const interfaces = networkInterfaces();
  const preferred = ["en0", "en1"];

  for (const name of [...preferred, ...Object.keys(interfaces)]) {
    const address = interfaces[name]?.find(
      (entry) => entry.family === "IPv4" && !entry.internal,
    );
    if (address) return address.address;
  }

  throw new Error("No Wi-Fi IPv4 address was found. Connect the Mac and iPhone to the same Wi-Fi network first.");
}

function run(command, args, env = process.env) {
  const result = spawnSync(command, args, { env, stdio: "inherit" });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}

const hosted = process.argv.includes("--hosted");
const savedEnv = loadEnv("production", process.cwd(), "VITE_");
const apiUrl = resolveDeviceApiUrl({
  configuredUrl: process.env.VITE_API_URL || savedEnv.VITE_API_URL,
  hosted,
  localAddress,
  port: process.env.API_PORT || "8001",
});
const buildEnvironment = { ...process.env, VITE_API_URL: apiUrl };

console.log(`Building the iPhone app to use the API at ${apiUrl}`);
if (hosted) {
  const response = await fetch(`${apiUrl}/health/ready`, { signal: AbortSignal.timeout(15000) });
  if (!response.ok) throw new Error(`Hosted API is not ready (HTTP ${response.status}). Check the server and PostgreSQL before installing.`);
  const result = await response.json();
  if (result.status !== "ok" || result.database !== "ok") throw new Error("The URL did not return a healthy Dine&Dash API and database.");
} else {
  console.warn("Local demo build: the API still requires your Mac to be awake and reachable. Use ios:release for an independently hosted API.");
}
run("pnpm", ["run", "build"], buildEnvironment);
run("pnpm", ["exec", "cap", "copy", "ios"]);

console.log("\nThe iPhone build is ready. Open Xcode with `pnpm exec cap open ios`, select your iPhone, and press Run.");
