import assert from "node:assert/strict";
import test from "node:test";

import { nextStage } from "../src/agent_optimization/scripts/continue_campaign.mjs";

const candidate = changes => ({ version: 3, status: "pending", training_runs: [], evaluations: [], ...changes });
const experiment = version => ({ status: "ready", versions: [version] });

test("only a newly published pending candidate starts training", () => {
  assert.deepEqual(nextStage(experiment(candidate())), { version: 3, action: "tune" });
  assert.equal(nextStage(experiment(candidate({ training_runs: [{status:"completed"}] }))), null);
});

test("completed training advances to evaluation without a repeat", () => {
  assert.deepEqual(nextStage(experiment(candidate({ status: "tuned", training_runs: [{status:"completed"}] }))), { version: 3, action: "evaluate" });
  assert.equal(nextStage(experiment(candidate({ status: "tuned", training_runs: [{status:"completed"},{status:"failed"}] }))), null);
  assert.equal(nextStage(experiment(candidate({ status: "tuned", training_runs: [{status:"completed"}], evaluations: [{status:"completed"}] }))), null);
});

test("in-flight, measured and terminal states are never restarted", () => {
  for (const status of ["tuning", "running", "completed", "failed", "cancelled"]) {
    assert.equal(nextStage(experiment(candidate({status}))), null);
  }
  for (const status of ["completed", "failed", "cancelled"]) {
    assert.equal(nextStage({status,versions:[candidate()]}), null);
  }
  assert.equal(nextStage({status:"running",versions:[candidate({version:2,status:"tuning"}),candidate()]}), null);
});