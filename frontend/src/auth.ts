import { Capacitor, registerPlugin } from "@capacitor/core";

const vault = registerPlugin<{
  read(): Promise<{ token?: string }>;
  write(options: { token: string }): Promise<void>;
  clear(): Promise<void>;
}>("SessionVault");
export const native = Capacitor.getPlatform() === "ios";
let token: string | undefined;

export async function restoreSession() {
  if (native) token = (await vault.read()).token;
}
export async function storeSession(value?: string) {
  if (native) {
    if (!value) throw new Error("The server did not return an iPhone session.");
    await vault.write({ token: value });
    token = value;
  }
}
export async function clearSession() {
  token = undefined;
  if (native) await vault.clear();
}
export function authHeaders(): Record<string, string> {
  return { "X-DineDash-Client": native ? "native" : "web", ...(native && token ? { Authorization: `Bearer ${token}` } : {}) };
}
