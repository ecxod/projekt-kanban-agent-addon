const assert = require("assert");

require("../addon/options/release-utils.js");
const { compareVersions, pickReleaseAsset, selectLatestRelease } = globalThis.PKReleaseUtils;

const release = {
  tag_name: "v0.1.8.1",
  assets: [
    { name: "projekt-kanban-agent-0.1.7.1-signed.xpi", browser_download_url: "https://example.invalid/old.xpi" },
    { name: "projekt-kanban-agent-0.1.8.1-test.xpi", browser_download_url: "https://example.invalid/test.xpi" },
    { name: "projekt-kanban-agent-0.1.8.1.xpi", browser_download_url: "https://example.invalid/unsigned.xpi" }
  ]
};

let selected = pickReleaseAsset(release);
assert.strictEqual(selected.kind, "unsigned");
assert.strictEqual(selected.asset.name, "projekt-kanban-agent-0.1.8.1.xpi");

release.assets.unshift({
  name: "projekt-kanban-agent-0.1.8.1-signed.xpi",
  browser_download_url: "https://example.invalid/signed.xpi"
});
selected = pickReleaseAsset(release);
assert.strictEqual(selected.kind, "signed");
assert.strictEqual(selected.asset.name, "projekt-kanban-agent-0.1.8.1-signed.xpi");

const latest = selectLatestRelease([
  { tag_name: "v0.1.8.0", published_at: "2026-09-08T10:00:00Z", assets: [] },
  release,
  { tag_name: "v0.1.8.2", prerelease: true, published_at: "2026-09-08T12:00:00Z", assets: [] }
]);
assert.strictEqual(latest.tag_name, "v0.1.8.1");
assert(compareVersions("v0.1.8.1", "0.1.8.0") > 0);

console.log("Release asset selection tests passed.");
