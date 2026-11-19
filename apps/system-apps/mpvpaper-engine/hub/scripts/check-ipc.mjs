import assert from 'node:assert/strict';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import ts from 'typescript';

await mkdir('.sites-runtime', { recursive: true });

// Transpile engine-ipc-client.ts
const ipcClientTs = await readFile('lib/engine-ipc-client.ts', 'utf8');
const transpiled = ts.transpileModule(ipcClientTs, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }
}).outputText;
await writeFile('.sites-runtime/engine-ipc-client-transpiled.mjs', transpiled);

const { EngineIpcClient, ALLOWED_IPC_METHODS } = await import('../.sites-runtime/engine-ipc-client-transpiled.mjs');

console.log('Testing MPVpaper Hub IPC Client...');

// Test 1: Whitelisted methods
assert(ALLOWED_IPC_METHODS.has('engine.status'));
assert(ALLOWED_IPC_METHODS.has('media.optimize'));
assert(ALLOWED_IPC_METHODS.has('hub.v1.download'));
assert(ALLOWED_IPC_METHODS.has('hub.v1.download.start'));
assert(ALLOWED_IPC_METHODS.has('hub.v1.apply'));
assert(!ALLOWED_IPC_METHODS.has('system.shell_exec'));

// Test 2: Mock UNIX Socket Server
const testSocketPath = path.join(os.tmpdir(), `test-hub-ipc-${Date.now()}.sock`);
if (fs.existsSync(testSocketPath)) fs.unlinkSync(testSocketPath);

const server = net.createServer((socket) => {
  socket.on('data', (data) => {
    const line = data.toString('utf-8').trim();
    const req = JSON.parse(line);
    if (req.method === 'engine.status') {
      socket.write(JSON.stringify({ id: req.id, ok: true, result: { service_status: 'running', active_tasks_count: 0 } }) + '\n');
    } else if (req.method === 'media.estimate') {
      socket.write(JSON.stringify({ id: req.id, ok: true, result: { estimate: { estimated_size_mb: 45.2, requires_lossy_confirmation: true } } }) + '\n');
    } else if (req.method === 'media.optimize') {
      if (!req.params.confirmed_lossy) {
        socket.write(JSON.stringify({ id: req.id, ok: false, error: { code: 'confirmation_required', message: 'Confirmation requise' } }) + '\n');
      } else {
        socket.write(JSON.stringify({ id: req.id, ok: true, result: { task_id: 'task-test-123', state: 'queued' } }) + '\n');
      }
    } else if (req.method === 'task.status') {
      socket.write(JSON.stringify({ id: req.id, ok: true, result: { id: req.params.task_id, state: 'running', progress: 0.65 } }) + '\n');
    } else if (req.method === 'task.cancel') {
      socket.write(JSON.stringify({ id: req.id, ok: true, result: { id: req.params.task_id, state: 'cancelled' } }) + '\n');
    } else if (req.method === 'hub.v1.download') {
      setTimeout(() => socket.write(JSON.stringify({ id: req.id, ok: true, result: { downloaded: true } }) + '\n'), 100);
    } else {
      socket.write(JSON.stringify({ id: req.id, ok: false, error: { code: 'unknown_method', message: 'Unknown' } }) + '\n');
    }
  });
});

await new Promise((resolve) => server.listen(testSocketPath, resolve));

try {
  const client = new EngineIpcClient(testSocketPath, 1500);

  // Status
  const status = await client.engineStatus();
  assert.equal(status.service_status, 'running');

  // Estimate
  const est = await client.mediaEstimate({ file_path: '/test.mp4' });
  assert.equal(est.estimate.estimated_size_mb, 45.2);

  // Optimize without confirmation -> should reject
  await assert.rejects(
    () => client.mediaOptimize({ file_path: '/test.mp4', confirmed_lossy: false }),
    (err) => err.code === 'confirmation_required'
  );

  // Optimize with confirmation -> returns task_id
  const opt = await client.mediaOptimize({ file_path: '/test.mp4', confirmed_lossy: true });
  assert.equal(opt.task_id, 'task-test-123');

  // Task Status
  const tStat = await client.taskStatus(opt.task_id);
  assert.equal(tStat.progress, 0.65);

  // Task Cancel
  const tCancel = await client.taskCancel(opt.task_id);
  assert.equal(tCancel.state, 'cancelled');

  // A timed out mutation must not be retried via the HTTP bridge.
  const originalFetch = globalThis.fetch;
  let httpFallbackCalls = 0;
  globalThis.fetch = async () => {
    httpFallbackCalls++;
    throw new Error('unexpected HTTP fallback');
  };
  try {
    const impatientClient = new EngineIpcClient(testSocketPath, 25);
    await assert.rejects(
      () => impatientClient.request('hub.v1.download', { media_url: 'fixture' }),
      (err) => err.code === 'timeout'
    );
    assert.equal(httpFallbackCalls, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }

  // Forbidden method
  await assert.rejects(
    () => client.request('arbitrary.command'),
    (err) => err.code === 'forbidden_method'
  );

  console.log('IPC client tests passed successfully (status, estimate, lossy check, task tracking, cancel).');
} finally {
  server.close();
  if (fs.existsSync(testSocketPath)) fs.unlinkSync(testSocketPath);
}
