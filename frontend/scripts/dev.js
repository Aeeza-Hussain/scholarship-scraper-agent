import { spawn, execSync } from 'child_process';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const BACKEND_PORT = 8001;
const HEALTH_URL = `http://127.0.0.1:${BACKEND_PORT}/health`;
const ROOT_DIR = path.resolve(__dirname, '../..');
const BACKEND_DIR = path.resolve(ROOT_DIR, 'backend');

// Find the Python executable (prefer workspace venv)
function getPythonExecutable() {
  const candidates = [
    path.join(ROOT_DIR, 'venv', 'Scripts', 'python.exe'),
    path.join(ROOT_DIR, 'venv', 'bin', 'python'),
    path.join(ROOT_DIR, '.venv', 'Scripts', 'python.exe'),
    path.join(ROOT_DIR, '.venv', 'bin', 'python'),
  ];

  if (process.env.VIRTUAL_ENV) {
    candidates.unshift(
      path.join(
        process.env.VIRTUAL_ENV,
        process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'
      )
    );
  }

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  return process.platform === 'win32' ? 'python' : 'python3';
}

// Check if backend is already responding
async function isBackendRunning() {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 1000);
    const res = await fetch(HEALTH_URL, { signal: controller.signal });
    clearTimeout(timeout);
    return res.ok;
  } catch {
    return false;
  }
}

// Wait until backend health endpoint returns ok
async function waitForBackend(maxWaitMs = 20000) {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    if (await isBackendRunning()) {
      return true;
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

let backendProcess = null;

function killBackend() {
  if (backendProcess && !backendProcess.killed) {
    console.log('\n[dev] Shutting down FastAPI backend...');
    try {
      if (process.platform === 'win32') {
        execSync(`taskkill /pid ${backendProcess.pid} /t /f`, { stdio: 'ignore' });
      } else {
        backendProcess.kill('SIGTERM');
      }
    } catch {
      // Process already terminated
    }
    backendProcess = null;
  }
}

async function main() {
  const alreadyRunning = await isBackendRunning();

  if (alreadyRunning) {
    console.log(`\x1b[32m[dev] FastAPI backend is already running on http://127.0.0.1:${BACKEND_PORT}\x1b[0m`);
  } else {
    const pythonExe = getPythonExecutable();
    console.log(`\x1b[36m[dev] 🚀 Starting FastAPI backend on http://127.0.0.1:${BACKEND_PORT}...\x1b[0m`);
    console.log(`\x1b[90m[dev] Using Python: ${pythonExe}\x1b[0m`);

    backendProcess = spawn(pythonExe, ['app.py'], {
      cwd: BACKEND_DIR,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
    });

    backendProcess.stdout.on('data', (chunk) => {
      const text = chunk.toString().trimEnd();
      if (text) console.log(`\x1b[35m[backend]\x1b[0m ${text}`);
    });

    backendProcess.stderr.on('data', (chunk) => {
      const text = chunk.toString().trimEnd();
      if (text) console.error(`\x1b[31m[backend]\x1b[0m ${text}`);
    });

    backendProcess.on('exit', (code) => {
      if (code && code !== 0) {
        console.error(`\x1b[31m[dev] Backend exited with code ${code}\x1b[0m`);
      }
    });

    const isReady = await waitForBackend();
    if (isReady) {
      console.log(`\x1b[32m[dev] ✅ FastAPI backend is ready and connected!\x1b[0m\n`);
    } else {
      console.warn(`\x1b[33m[dev] ⚠️ Backend taking longer than usual to report healthy, continuing with frontend startup...\x1b[0m\n`);
    }
  }

  // Handle cleanup on exit
  process.on('SIGINT', () => {
    killBackend();
    process.exit(0);
  });
  process.on('SIGTERM', () => {
    killBackend();
    process.exit(0);
  });
  process.on('exit', () => {
    killBackend();
  });

  // Start Vite dev server directly via Node.js to avoid Windows EINVAL on batch/.cmd files
  const viteBin = path.resolve(__dirname, '../node_modules/vite/bin/vite.js');
  const viteProcess = fs.existsSync(viteBin)
    ? spawn(process.execPath, [viteBin], {
        cwd: path.resolve(__dirname, '..'),
        stdio: 'inherit',
      })
    : spawn(process.platform === 'win32' ? 'npx.cmd' : 'npx', ['vite'], {
        cwd: path.resolve(__dirname, '..'),
        stdio: 'inherit',
        shell: true,
      });

  viteProcess.on('exit', (code) => {
    killBackend();
    process.exit(code ?? 0);
  });
}

main().catch((err) => {
  console.error('[dev] Error starting development environment:', err);
  killBackend();
  process.exit(1);
});
