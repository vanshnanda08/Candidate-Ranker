# npm dependency review

Audited 2026-11-14. The starting audit identified **six vulnerable packages** (one moderate, five high), covering multiple advisory entries. All were dev/build tooling; the runtime-only audit had zero findings. Fixes used `npm audit fix`, without `--force` or a major-version override, followed by `npm ci` to verify the resulting lockfile. Direct dependency ranges did not change; resolved versions are pinned in package-lock.json.

| Package | Relationship | Original severity | Locked change |
|---|---|---|---|
| baseline-browser-mapping | Transitive dev tooling | moderate | 2.10.40 → 2.11.37 |
| browserslist | Transitive dev tooling | high | 4.28.4 → 4.29.5 |
| nanoid | Transitive dev tooling | high | 3.3.15 → 3.3.20 |
| postcss | Direct devDependency | high | 8.5.16 → 8.5.33 |
| source-map-js | Transitive dev tooling | high | 1.2.1 → 1.2.2 |
| vite | Direct devDependency | high | 8.1.3 → 8.3.8 |

Paths: Browserslist is reached through Autoprefixer; baseline-browser-mapping is under Browserslist; Nano ID and source-map-js are under PostCSS. PostCSS and Vite are direct devDependencies and also serve other build plugins. The browser runtime dependencies are React, React DOM and Recharts; npm's omit-dev audit reports no vulnerable runtime dependency graph.

Final `npm audit` and `npm audit --omit=dev`: **0 vulnerabilities**, after clean install. This is an npm audit result on the checked date, not a guarantee against unknown vulnerabilities or an audit of Python packages. No npm advisories remain to require another change.

Advisory references:
- baseline-browser-mapping: [baseline-browser-mapping process termination on invalid input causes denial of service](https://github.com/advisories/GHSA-w5vr-8v7q-w6rv)
- browserslist: [Browserslist: Unbounded memory growth (no cache eviction) via distinct query results, leading to eventual OOM](https://github.com/advisories/GHSA-c83g-rgw3-j3cx)
- browserslist: [Browserslist: Uncaught crash / prototype write via untrusted browserslist-stats.json custom stats (normalizeStats)](https://github.com/advisories/GHSA-73wf-gq98-2v4g)
- nanoid: [nanoid: non-secure generators can loop indefinitely with negative size](https://github.com/advisories/GHSA-28wg-ghj8-5hjv)
- nanoid: [nanoid: custom generators can loop indefinitely when size is zero](https://github.com/advisories/GHSA-2v37-7h3g-55p8)
- postcss: [PostCSS: incomplete fix of GHSA-6g55-p6wh-862q — attacker-controlled sourceMappingURL reads arbitrary .map files when `from` is unset](https://github.com/advisories/GHSA-fxqj-rqcc-2cmp)
- postcss: [PostCSS: Path Traversal in Previous Source Map Auto-Loading (sourceMappingURL) leads to Arbitrary .map File Disclosure](https://github.com/advisories/GHSA-r28c-9q8g-f849)
- source-map-js: [source-map-js allows event-loop denial of service through indexed source-map section offsets](https://github.com/advisories/GHSA-68fv-2mgg-jv7q)
- vite: [launch-editor: escapeCmdArgs() omits % escaping on Windows](https://github.com/advisories/GHSA-698v-4r3x-3vcv)
- vite: [launch-editor: Editor CLI flag misinterpretation causing arbitrary command execution for some editors](https://github.com/advisories/GHSA-r825-w8mm-5pxw)
- vite: [launch-editor: `fs.existsSync()` existence check can be bypassed on Windows](https://github.com/advisories/GHSA-587h-7wmj-h5pm)
- vite: [Vite: Cross origin script execution through Vite custom middleware](https://github.com/advisories/GHSA-9jrq-w75r-8gcw)
- vite: [Vite: Files outside `server.fs.allow` could be served when project paths match system paths on non-Windows machine](https://github.com/advisories/GHSA-rq7h-c2jc-7f22)

Other compatible lockfile updates include Rolldown/native bindings and browser-compatibility database packages pulled by the fixes. The original 500 kB JavaScript chunk warning still occurs; the release build is approximately 585 kB minified/174 kB gzip. It is a build advisory, not a failed build. Clean install also reports an unapproved optional fsevents install script under npm's script policy; no broad script permission was granted. Build, lint and browser verification determine whether tooling works under that policy.
