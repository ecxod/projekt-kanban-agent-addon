(function (global) {
  "use strict";

  function extractVersion(value) {
    const match = String(value || "").match(/(?:^|[^0-9])v?(\d+(?:\.\d+)+)(?:[^0-9.]|$)/i);
    return match ? match[1] : "";
  }

  function versionParts(value) {
    const source = extractVersion(value) || String(value || "").trim().replace(/^v/i, "");
    return source
      .split(".")
      .filter(Boolean)
      .map((part) => Number.parseInt(part, 10) || 0);
  }

  function compareVersions(left, right) {
    const a = versionParts(left);
    const b = versionParts(right);
    const length = Math.max(a.length, b.length);
    for (let index = 0; index < length; index += 1) {
      const delta = (a[index] || 0) - (b[index] || 0);
      if (delta !== 0) {
        return delta;
      }
    }
    return 0;
  }

  function getReleaseVersion(release) {
    return extractVersion(release && release.tag_name) || extractVersion(release && release.name);
  }

  function usableAsset(asset) {
    return Boolean(
      asset
      && typeof asset.name === "string"
      && typeof asset.browser_download_url === "string"
      && asset.browser_download_url
    );
  }

  function pickReleaseAsset(release) {
    const version = getReleaseVersion(release);
    if (!version || !release || !Array.isArray(release.assets)) {
      return { asset: null, kind: "missing", version };
    }
    const exactPrefix = `projekt-kanban-agent-${version}`;
    const signedName = `${exactPrefix}-signed.xpi`;
    const unsignedName = `${exactPrefix}.xpi`;
    const signed = release.assets.find((asset) => usableAsset(asset) && asset.name.toLowerCase() === signedName);
    if (signed) {
      return { asset: signed, kind: "signed", version };
    }
    const unsigned = release.assets.find((asset) => usableAsset(asset) && asset.name.toLowerCase() === unsignedName);
    if (unsigned) {
      return { asset: unsigned, kind: "unsigned", version };
    }
    return { asset: null, kind: "missing", version };
  }

  function selectLatestRelease(releases) {
    const candidates = Array.isArray(releases)
      ? releases.filter((release) => release && !release.draft && !release.prerelease)
      : [];
    return candidates.sort((left, right) => {
      const versionDelta = compareVersions(getReleaseVersion(right), getReleaseVersion(left));
      if (versionDelta !== 0) {
        return versionDelta;
      }
      const rightDate = Date.parse(right.published_at || right.created_at || "") || 0;
      const leftDate = Date.parse(left.published_at || left.created_at || "") || 0;
      return rightDate - leftDate;
    })[0] || null;
  }

  global.PKReleaseUtils = Object.freeze({
    compareVersions,
    getReleaseVersion,
    pickReleaseAsset,
    selectLatestRelease
  });
}(globalThis));
