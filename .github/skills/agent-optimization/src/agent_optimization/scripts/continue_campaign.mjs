import assert from "node:assert/strict";
import { readFileSync, watch } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

export function nextStage(experiment) {
  if (["completed", "cancelled", "failed"].includes(experiment.status)) return null;
  if (experiment.versions.some(version => ["tuning", "running"].includes(version.status))) return null;
  const version = experiment.versions.at(-1);
  if (!version) return null;
  if (version.status === "pending" && !version.training_runs.length && !version.evaluations.length) {
    return { version: version.version, action: "tune" };
  }
  if (version.status === "tuned" && version.training_runs.at(-1)?.status === "completed" && !version.evaluations.length) {
    return { version: version.version, action: "evaluate" };
  }
  return null;
}

export async function continueCampaign(directory, endpoint) {
  const base = new URL(endpoint);
  assert.ok(base.protocol === "http:" && ["127.0.0.1", "localhost", "[::1]"].includes(base.hostname), "Only an explicitly authorized loopback endpoint is supported");
  assert.ok(!base.username && !base.password && !base.search && !base.hash, "Endpoint cannot contain credentials, query or fragment");
  const path = resolve(directory, "experiment.json");
  const attempted = new Set();
  let pending = false;
  let snapshot = "";
  await new Promise((done, reject) => {
    const changes = watch(resolve(directory), (event, name) => { if (name === "experiment.json") void inspect(); });
    changes.on("error", reject);
    async function inspect() {
      try {
        const experiment = JSON.parse(readFileSync(path, "utf8"));
        assert.equal(base.pathname.split("/").filter(Boolean).at(-1), experiment.id, "Endpoint and ledger name different experiments");
        const version = experiment.versions.at(-1);
        const run = version && [...version.training_runs, ...version.evaluations].at(-1);
        const identity = JSON.stringify([experiment.status, version?.version, version?.status, run?.id, run?.status, Math.floor((run?.cases_finished ?? 0) / 512)]);
        if (identity !== snapshot) {
          snapshot = identity;
          console.log(JSON.stringify({ at: new Date().toISOString(), experiment: experiment.id, status: experiment.status,
            version: version?.version, version_status: version?.status, stage: run?.stage, run: run?.id,
            done: run?.cases_finished, total: run?.case_count, macro_f1: run?.metrics?.macro_f1 }));
        }
        if (["completed", "cancelled", "failed"].includes(experiment.status)) {
          changes.close();
          if (experiment.status === "completed") done();
          else reject(new Error(`Campaign ended ${experiment.status}; recorded attempts are preserved`));
          return;
        }
        const step = nextStage(experiment);
        if (!step || pending) return;
        const identityKey = `${step.version}:${step.action}`;
        if (attempted.has(identityKey)) return;
        attempted.add(identityKey);
        pending = true;
        try {
          const response = await fetch(`${base.href.replace(/\/$/, "")}/versions/${step.version}/${step.action}`, {
            method: "POST", signal: AbortSignal.timeout(20000),
          });
          if (!response.ok) {
            const current = JSON.parse(readFileSync(path, "utf8")).versions.find(item => item.version === step.version);
            const runs = step.action === "tune" ? current.training_runs : current.evaluations;
            assert.ok(runs.length > 0, `Stage admission failed: ${response.status}`);
          }
          console.log(JSON.stringify({ at: new Date().toISOString(), advanced: identityKey, source: "saved_stage_state" }));
        } finally {
          pending = false;
        }
        void inspect();
      } catch (error) {
        changes.close();
        reject(error);
      }
    }
    void inspect();
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  assert.equal(process.argv.length, 4, "Usage: node continue_campaign.mjs EXPERIMENT_DIRECTORY AUTHORIZED_LOOPBACK_EXPERIMENT_ENDPOINT");
  await continueCampaign(process.argv[2], process.argv[3]);
}