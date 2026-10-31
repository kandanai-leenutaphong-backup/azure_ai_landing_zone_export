import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cpSync, mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';
import { configuration, runtimeFacts, runAllowed, LIBRARY_ROOT } from '@agentcraft/hyperframes-tools';

const { values } = parseArgs({ options: { root: { type: 'string' }, runtime: { type: 'string' } } });
const config = configuration(values.root, values.runtime);
const evidence = path.join(config.root, 'evidence');
mkdirSync(evidence, { recursive: true });
cpSync(path.join(LIBRARY_ROOT, 'examples/pulse'), path.join(config.root, 'pulse'), { recursive: true });
const commands = [];

function run(label, args) {
  const result = runAllowed(args, config, { allowRender: true });
  writeFileSync(path.join(evidence, `${label}.stdout.log`), result.stdout);
  writeFileSync(path.join(evidence, `${label}.stderr.log`), result.stderr);
  assert.equal(result.status, 0, `${label}: ${result.stdout}\n${result.stderr}`);
  commands.push({ label, args, passed: true });
}

run('lint', ['lint', 'pulse', '--json']);
run('check', ['check', 'pulse', '--json', '--snapshots', '--at', '0.25,1,1.75']);
for (const suffix of ['a', 'b']) {
  run(`render-${suffix}`, ['render', 'pulse', '--quality', 'high', '--fps', '30', '--output', `render-${suffix}.mp4`]);
}
const facts = runtimeFacts(config);
const probe = spawnSync(facts.ffprobe, ['-v', 'error', '-show_streams', '-show_format', '-of', 'json', path.join(config.root, 'render-a.mp4')], { encoding: 'utf8' });
assert.equal(probe.status, 0, probe.stderr);
const media = JSON.parse(probe.stdout);
const video = media.streams.find(stream => stream.codec_type === 'video');
assert.equal(video.width, 640);
assert.equal(video.height, 360);
assert.equal(video.r_frame_rate, '30/1');
assert.ok(Math.abs(Number(media.format.duration) - 2) < 0.1);
writeFileSync(path.join(evidence, 'probe.json'), probe.stdout);
const frames = [];
for (const timestamp of ['0.25', '1', '1.75']) {
  const hashes = [];
  for (const suffix of ['a', 'b']) {
    const frame = spawnSync(facts.ffmpeg, ['-v', 'error', '-ss', timestamp, '-i', path.join(config.root, `render-${suffix}.mp4`),
      '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'], { maxBuffer: 4 * 1024 * 1024 });
    assert.equal(frame.status, 0, frame.stderr.toString());
    assert.equal(frame.stdout.length, 640 * 360 * 3);
    assert.ok(new Set(frame.stdout).size > 20, 'decoded frame is blank');
    hashes.push(createHash('sha256').update(frame.stdout).digest('hex'));
  }
  assert.equal(hashes[0], hashes[1], `frame differs across renders at ${timestamp}`);
  frames.push({ timestamp, sha256: hashes[0] });
  const poster = spawnSync(facts.ffmpeg, ['-v', 'error', '-y', '-ss', timestamp, '-i', path.join(config.root, 'render-a.mp4'),
    '-frames:v', '1', path.join(evidence, `frame-${timestamp}.png`)]);
  assert.equal(poster.status, 0, poster.stderr.toString());
}
assert.equal(new Set(frames.map(frame => frame.sha256)).size, frames.length, 'motion did not change between sampled frames');
writeFileSync(path.join(evidence, 'result.json'), JSON.stringify({ passed: true, version: facts.version, commands, frames,
  width: video.width, height: video.height, duration: media.format.duration }, null, 2));
console.log('PASS: actual lint/check, two MP4 renders, dimensions/fps/duration, nonblank moving frames, exact decoded-frame repeatability');