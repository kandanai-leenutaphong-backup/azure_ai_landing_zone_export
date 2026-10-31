import type { parse } from 'parse5';

export const LIBRARY_ROOT: string;
export const MAX_DURATION_SEC: 8;
export const MAX_TIMESTAMPS: 20;
export class Refusal extends Error {}

export interface Configuration {
  root: string;
  runtime: string;
}

export interface CompositionDetails {
  duration: number;
  width: number;
  height: number;
}

export interface Approvals {
  allowRender?: boolean;
  allowBrowserInstall?: boolean;
}

export interface RunOptions extends Approvals {
  timeoutMs?: number;
}

export interface RuntimeFacts {
  bin: string;
  version: '0.8.12';
  ffmpeg: string;
  ffprobe: string;
}

export interface RunResult {
  status: number;
  stdout: string;
  stderr: string;
}

export function configuration(root: string, runtime: string): Configuration;
export function containedPath(root: string, value: string, label: string): string;
export function parseAtTimestamps(raw: string, duration: number): string;
export function composition(html: string, parser?: typeof parse): CompositionDetails;
export function validate(argv: string[], config: Configuration, options?: Approvals): string[];
export function runtimeFacts(config: Configuration): RuntimeFacts;
export function runAllowed(argv: string[], config: Configuration, options?: RunOptions): RunResult;