import test from "node:test";
import assert from "node:assert/strict";
import { resolveDeviceApiUrl } from "./ios-api-url.mjs";

const offline = () => { throw new Error("No Wi-Fi"); };
test("hosted builds do not depend on a Mac network interface", () => {
  assert.equal(resolveDeviceApiUrl({ configuredUrl: "https://api.example.com/", hosted: true, localAddress: offline }), "https://api.example.com");
});
test("hosted builds require a public HTTPS URL", () => {
  for (const configuredUrl of [undefined, "http://api.example.com", "https://localhost", "https://127.0.0.1", "https://10.1.2.3", "https://192.168.1.5", "https://172.16.0.5", "https://[::1]", "https://user:password@api.example.com", "https://api.example.com?token=secret"]) {
    assert.throws(() => resolveDeviceApiUrl({ configuredUrl, hosted: true, localAddress: offline }));
  }
});
test("local demo builds use the specified address and port", () => {
  assert.equal(resolveDeviceApiUrl({ hosted: false, localAddress: () => "10.1.2.3", port: "8001" }), "http://10.1.2.3:8001");
});
