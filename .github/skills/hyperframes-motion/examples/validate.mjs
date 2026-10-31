import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { composition, parseAtTimestamps } from '@agentcraft/hyperframes-tools';

const html = readFileSync(new URL('./pulse/index.html', import.meta.url), 'utf8');
const beats = JSON.parse(readFileSync(new URL('./pulse/beat-map.json', import.meta.url), 'utf8'));
const details = composition(html);
assert.equal(details.duration, beats.duration);
const timestamps = parseAtTimestamps(beats.sampleTimes.join(','), details.duration);
for (const beat of beats.beats) {
  assert.ok(beats.sampleTimes.some(time => time > beat.startSec && time < beat.endSec));
}
console.log(JSON.stringify({ ...details, timestamps, nativeExecution: false }));