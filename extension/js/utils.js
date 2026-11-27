export function validTabUrl(tab) {
  if (!tab || !tab.url || (typeof tab.id === "number" && tab.id < 0)) return false;
  const restricted = ["chrome://", "edge://", "about:", "file://", "moz-extension://", "chrome-extension://"];
  if (restricted.some((prefix) => tab.url.startsWith(prefix))) return false;
  return true;
}
