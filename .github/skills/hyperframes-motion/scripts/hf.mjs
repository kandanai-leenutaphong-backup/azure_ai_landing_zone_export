#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { existsSync, mkdirSync, readFileSync, realpathSync, statSync } from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';
import { fileURLToPath } from 'node:url';
import { parse as parseHTML } from 'parse5';

export const LIBRARY_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const MAX_DURATION_SEC = 8;
export const MAX_TIMESTAMPS = 20;
const DECIMAL = /^\d+(\.\d+)?$/;
export class Refusal extends Error {}

function inside(root, target) {
  const relative = path.relative(root, target);
  return relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative));
}

export function configuration(root, runtime) {
  if (![root, runtime].every(value => typeof value === 'string' && path.isAbsolute(value))) {
    throw new Refusal('--root and --runtime must be explicit absolute directories');
  }
  root = realpathSync(root);
  runtime = realpathSync(runtime);
  if (![root, runtime].every(value => statSync(value).isDirectory() && !inside(LIBRARY_ROOT, value))) {
    throw new Refusal('work and runtime directories must be outside the installed library');
  }
  if (inside(root, runtime) || inside(runtime, root)) {
    throw new Refusal('work and runtime directories must not overlap');
  }
  return { root, runtime };
}

export function containedPath(root, value, label) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9._/-]+$/.test(value) || path.isAbsolute(value)
      || value.split('/').includes('..')) throw new Refusal(`${label} must be a root-relative path without traversal`);
  const resolved = path.resolve(root, value);
  let ancestor = resolved;
  while (!existsSync(ancestor) && path.dirname(ancestor) !== ancestor) ancestor = path.dirname(ancestor);
  if (!inside(root, resolved) || !inside(root, realpathSync(ancestor))) throw new Refusal(`${label} escapes the work root`);
  return resolved;
}

export function parseAtTimestamps(raw, duration) {
  if (typeof raw !== 'string' || !raw || raw.split(',').length > MAX_TIMESTAMPS) {
    throw new Refusal(`--at requires 1-${MAX_TIMESTAMPS} timestamps`);
  }
  let previous = -1;
  return raw.split(',').map(token => {
    const value = Number(token);
    if (!DECIMAL.test(token) || !Number.isFinite(value) || value <= previous || value >= duration) {
      throw new Refusal('--at timestamps must be unsigned, strictly increasing and inside the duration');
    }
    previous = value;
    return String(value);
  }).join(',');
}

export function composition(html, parse = parseHTML) {
  const document = parse(html);
  const elements = [];
  function visit(node) {
    if (node.tagName) elements.push(node);
    for (const child of node.childNodes ?? []) visit(child);
  }
  visit(document);
  const roots = elements.filter(node => node.attrs?.some(attribute => attribute.name === 'data-composition-id'));
  if (roots.length !== 1 || roots[0].parentNode?.tagName !== 'body') throw new Refusal('one composition must be directly beneath body');
  const attributes = Object.fromEntries(roots[0].attrs.map(attribute => [attribute.name, attribute.value]));
  const duration = Number(attributes['data-duration']);
  if (!DECIMAL.test(attributes['data-duration'] ?? '') || duration <= 0 || duration > MAX_DURATION_SEC) {
    throw new Refusal(`data-duration must be positive and at most ${MAX_DURATION_SEC}s`);
  }
  if (attributes['data-start'] !== '0' || !Object.hasOwn(attributes, 'data-no-timeline')) {
    throw new Refusal('root needs data-start="0" and data-no-timeline for finite CSS motion');
  }
  for (const dimension of ['data-width', 'data-height']) {
    if (!/^\d+$/.test(attributes[dimension] ?? '') || Number(attributes[dimension]) <= 0 || Number(attributes[dimension]) > 4096) {
      throw new Refusal('root dimensions must be positive integers at most 4096');
    }
  }
  for (const element of elements) {
    if (['script', 'iframe', 'object', 'embed', 'base'].includes(element.tagName)
        || element.attrs?.some(attribute => attribute.name.startsWith('on'))) {
      throw new Refusal('this runner accepts CSS-only local compositions, not active scripts or frames');
    }
  }
  if (/https?:|\/\/|@import|\binfinite\b|Date\.now|performance\.now/.test(html)) {
    throw new Refusal('remote assets, imports, clocks and infinite animation are outside this contract');
  }
  return { duration, width: Number(attributes['data-width']), height: Number(attributes['data-height']) };
}

export function validate(argv, config, { allowRender = false, allowBrowserInstall = false } = {}) {
  const exact = shape => argv.length === shape.length && shape.every((value, index) => value === null || argv[index] === value);
  if (exact(['--version']) || exact(['doctor', '--json'])) return argv;
  if (exact(['browser', 'ensure'])) {
    if (!allowBrowserInstall) throw new Refusal('browser download requires --allow-browser-install');
    return argv;
  }
  const command = argv[0];
  const valid = command === 'lint' && exact(['lint', null, '--json'])
    || command === 'check' && (exact(['check', null, '--json', '--snapshots', '--at-transitions'])
       || exact(['check', null, '--json', '--snapshots', '--at', null]))
    || command === 'render' && exact(['render', null, '--quality', null, '--fps', '30', '--output', null]);
  if (!valid) throw new Refusal('command is not an allowlisted HyperFrames shape');
  if (command === 'render') {
    if (!allowRender) throw new Refusal('render requires --allow-render');
    if (!['draft', 'high'].includes(argv[3])) throw new Refusal('quality must be draft or high');
    containedPath(config.root, argv[7], 'render output');
    if (!argv[7].endsWith('.mp4')) throw new Refusal('render output must end in .mp4');
  }
  let entry = containedPath(config.root, argv[1], 'project');
  if (statSync(entry).isDirectory()) entry = containedPath(config.root, `${argv[1]}/index.html`, 'entry');
  const details = composition(readFileSync(entry, 'utf8'));
  if (command === 'check' && argv[4] === '--at') return [...argv.slice(0, 5), parseAtTimestamps(argv[5], details.duration)];
  return argv;
}

export function runtimeFacts(config) {
  const require = createRequire(path.join(config.runtime, 'package.json'));
  const packagePath = require.resolve('hyperframes/package.json');
  if (!inside(config.runtime, realpathSync(packagePath))) throw new Refusal('HyperFrames must be installed in the supplied runtime');
  const manifest = require(packagePath);
  if (manifest.version !== '0.8.12') throw new Refusal('runtime must use locked HyperFrames 0.8.12');
  const bin = path.resolve(path.dirname(packagePath), typeof manifest.bin === 'string' ? manifest.bin : manifest.bin.hyperframes);
  return { bin, version: manifest.version, ffmpeg: require('@ffmpeg-installer/ffmpeg').path,
           ffprobe: require('@ffprobe-installer/ffprobe').path };
}

export function runAllowed(argv, config, options = {}) {
  const args = validate([...argv], config, options);
  if (Number(process.versions.node.split('.')[0]) < 22) throw new Refusal('HyperFrames needs Node 22+; use the locked runtime Node executable');
  const facts = runtimeFacts(config);
  const home = path.join(config.runtime, '.home');
  const cache = path.join(config.runtime, '.cache');
  for (const directory of [home, cache]) mkdirSync(directory, { recursive: true });
  const env = {
    PATH: `${path.join(LIBRARY_ROOT, 'tools')}${path.delimiter}${process.env.PATH ?? ''}`,
    HOME: home, XDG_CACHE_HOME: cache, XDG_CONFIG_HOME: path.join(home, '.config'),
    HYPERFRAMES_FONT_CACHE_DIR: path.join(cache, 'fonts'), HYPERFRAMES_EXTRACT_CACHE_DIR: path.join(cache, 'extract'),
    HYPERFRAMES_NO_TELEMETRY: '1', DO_NOT_TRACK: '1', HYPERFRAMES_SKIP_SKILLS: '1',
    HYPERFRAMES_RUN_ID: 'harness-hyperframes', HYPERFRAMES_FFMPEG_PATH: facts.ffmpeg,
    HYPERFRAMES_FFPROBE_PATH: facts.ffprobe,
  };
  for (const name of ['SYSTEMROOT', 'WINDIR', 'TMP', 'TEMP', 'TMPDIR', 'LANG']) {
    if (process.env[name]) env[name] = process.env[name];
  }
  const result = spawnSync(process.execPath, [facts.bin, ...args], {
    cwd: config.root, env, encoding: 'utf8', timeout: options.timeoutMs ?? 600000,
    maxBuffer: 32 * 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe'],
  });
  if (result.error) throw result.error;
  return { status: result.status ?? 1, stdout: result.stdout ?? '', stderr: result.stderr ?? '' };
}

if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const separator = process.argv.indexOf('--', 2);
    if (separator < 0) throw new Refusal('use --root ROOT --runtime RUNTIME [approvals] -- <command>');
    const { values } = parseArgs({ args: process.argv.slice(2, separator), options: {
      root: { type: 'string' }, runtime: { type: 'string' },
      'allow-render': { type: 'boolean' }, 'allow-browser-install': { type: 'boolean' },
    }});
    const config = configuration(values.root, values.runtime);
    const result = runAllowed(process.argv.slice(separator + 1), config, {
      allowRender: values['allow-render'], allowBrowserInstall: values['allow-browser-install'],
    });
    process.stdout.write(result.stdout);
    process.stderr.write(result.stderr);
    process.exitCode = result.status;
  } catch (error) {
    process.stderr.write(`hf: ${error instanceof Refusal ? 'refused' : 'error'}: ${error.message}\n`);
    process.exitCode = error instanceof Refusal ? 2 : 1;
  }
}