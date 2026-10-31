import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { after, test } from 'node:test';
import { mkdtempSync, mkdirSync, writeFileSync, symlinkSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { parse } from 'parse5';
import { configuration, containedPath, composition, parseAtTimestamps, validate, Refusal, LIBRARY_ROOT } from '@agentcraft/hyperframes-tools';

const suppliedRuntime = process.env.HYPERFRAMES_TEST_RUNTIME;
const runtime = suppliedRuntime || mkdtempSync(path.join(tmpdir(), 'hf-validator-runtime-'));
after(() => { if (!suppliedRuntime) rmSync(runtime, { recursive: true }); });
const markup = '<!doctype html><html><body><main data-composition-id="fixture" data-start="0" data-width="640" data-height="360" data-duration="2" data-no-timeline></main></body></html>';

test('HTML parser finds only a real directly-owned composition', () => {
  assert.deepEqual(composition(markup, parse), { duration: 2, width: 640, height: 360 });
  for (const invalid of [markup.replace('data-start="0"', ''), markup.replace('data-duration="2"', 'data-duration="9"'),
    markup.replace('data-no-timeline', ''), markup.replace('<main ', '<script>const fake = "<main '),
    markup.replace('</main>', '<img src="https://example.test/image.png"></main>'),
    markup.replace('</main>', '<style>main {animation: move 1s infinite}</style></main>')]) {
    assert.throws(() => composition(invalid, parse), Refusal);
  }
});

test('timestamp grammar, ordering and bounds discriminate', () => {
  assert.equal(parseAtTimestamps('00,0.50,1.9', 2), '0,0.5,1.9');
  for (const invalid of ['', '-1', '+1', '1e0', '0,0', '1,0', '2', '0, 1', '0,', Array(21).fill('0').join(',')]) {
    assert.throws(() => parseAtTimestamps(invalid, 2), Refusal);
  }
});

test('explicit roots, path containment and approvals precede execution', () => {
  const temporary = mkdtempSync(path.join(tmpdir(), 'hf-wrapper-'));
  try {
    const root = path.join(temporary, 'work');
    mkdirSync(root);
    writeFileSync(path.join(root, 'index.html'), markup);
    const config = configuration(root, runtime);
    assert.deepEqual(validate(['lint', 'index.html', '--json'], config), ['lint', 'index.html', '--json']);
    assert.deepEqual(validate(['check', 'index.html', '--json', '--snapshots', '--at', '0.50,1'], config),
      ['check', 'index.html', '--json', '--snapshots', '--at', '0.5,1']);
    const render = ['render', 'index.html', '--quality', 'draft', '--fps', '30', '--output', 'result.mp4'];
    assert.throws(() => validate(render, config), Refusal);
    assert.deepEqual(validate(render, config, { allowRender: true }), render);
    assert.throws(() => validate(['browser', 'ensure'], config), Refusal);
    assert.deepEqual(validate(['browser', 'ensure'], config, { allowBrowserInstall: true }), ['browser', 'ensure']);
    for (const invalid of [['publish'], ['lint', '../outside', '--json'], ['lint', 'index.html', '--json', '--extra']]) {
      assert.throws(() => validate(invalid, config), Refusal);
    }
    symlinkSync(temporary, path.join(root, 'escape'));
    assert.throws(() => containedPath(root, 'escape/file.mp4', 'output'), Refusal);
    assert.throws(() => configuration(LIBRARY_ROOT, runtime), Refusal);
    assert.throws(() => configuration(root, root), Refusal);
  } finally {
    rmSync(temporary, { recursive: true });
  }
});

test('installed CLI symlink refuses unsupported commands before native execution', () => {
  const temporary = mkdtempSync(path.join(tmpdir(), 'hf-cli-'));
  try {
    const root = path.join(temporary, 'work');
    mkdirSync(root);
    const executable = path.join(temporary, 'hyperframes-tools');
    symlinkSync(path.join(LIBRARY_ROOT, 'scripts/hf.mjs'), executable);
    const result = spawnSync(process.execPath, [executable, '--root', root, '--runtime', runtime, '--', 'publish'], {
      encoding: 'utf8', timeout: 5000,
    });
    assert.equal(result.status, 2);
    assert.equal(result.stdout, '');
    assert.match(result.stderr, /refused: command is not an allowlisted HyperFrames shape/);
  } finally {
    rmSync(temporary, { recursive: true });
  }
});