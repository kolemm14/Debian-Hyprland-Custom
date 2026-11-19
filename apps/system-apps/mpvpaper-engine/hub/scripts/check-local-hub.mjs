import assert from 'node:assert/strict';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import ts from 'typescript';

await mkdir('.sites-runtime', { recursive: true });
const localHubTs = await readFile('lib/local-hub.ts', 'utf8');
const transpiled = ts.transpileModule(localHubTs, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }
}).outputText;
await writeFile('.sites-runtime/check-local-hub-transpiled.mjs', transpiled);

const {
  INITIAL_OPTIMIZER_VIDEO,
  INITIAL_OPTIMIZER_IMAGE,
  estimateVideoOptimization,
  estimateImageOptimization,
  DEFAULT_MONITORS,
  DEFAULT_LOCAL_LIBRARY,
  DEFAULT_WEB_PROJECTS,
} = await import('../.sites-runtime/check-local-hub-transpiled.mjs');

// 1. Initial optimizer profile specifications (Section 4 of prompt: 720p & 150MB max, preserve original)
assert.equal(INITIAL_OPTIMIZER_VIDEO.resolution, '720p');
assert.equal(INITIAL_OPTIMIZER_VIDEO.targetMaxMB, 150);
assert.equal(INITIAL_OPTIMIZER_VIDEO.preserveOriginal, true);

assert.equal(INITIAL_OPTIMIZER_IMAGE.resolution, '720p');
assert.equal(INITIAL_OPTIMIZER_IMAGE.targetMaxMB, 150);
assert.equal(INITIAL_OPTIMIZER_IMAGE.preserveOriginal, true);

// 2. Video estimation
const videoEst = estimateVideoOptimization(
  { width: 3840, height: 2160, sizeMB: 400, fps: 60 },
  INITIAL_OPTIMIZER_VIDEO
);
assert.equal(videoEst.originalResolution, '3840x2160');
assert.equal(videoEst.targetResolution, '1280x720');
assert.equal(videoEst.codecOrFormat, 'H264');
assert(videoEst.estimatedSizeMB <= 150, 'Estimated size must be capped at target max MB (150MB)');
assert.equal(videoEst.requiresLossyConfirmation, true);

// 3. Image estimation
const imgEst = estimateImageOptimization(
  { width: 3840, height: 2160, sizeMB: 25 },
  INITIAL_OPTIMIZER_IMAGE
);
assert.equal(imgEst.targetResolution, '1280x720');
assert.equal(imgEst.codecOrFormat, 'WEBP');
assert(imgEst.estimatedSizeMB <= 150);

// 4. Default monitors
assert.equal(DEFAULT_MONITORS.length, 2);
assert(DEFAULT_MONITORS.some(m => m.name === 'eDP-1'));
assert(DEFAULT_MONITORS.some(m => m.name === 'HDMI-A-1'));

// 5. Web projects security sandbox status
assert(DEFAULT_WEB_PROJECTS.length >= 3);
assert(DEFAULT_WEB_PROJECTS.some(p => p.status === 'blocked_policy'));

// 6. Local library
assert(DEFAULT_LOCAL_LIBRARY.length >= 4);
assert(DEFAULT_LOCAL_LIBRARY.some(m => m.type === 'video'));
assert(DEFAULT_LOCAL_LIBRARY.some(m => m.type === 'image'));

console.log('Vérifications Hub local réussies : profil initial 720p/150Mo, estimation manuelle, multi-écrans, bibliothèque et projets web sécurisés.');
