-- Per-agent records in Foundry Cosmos (hosted agent v3+).
-- Account cosmos-foundry-wus3jbm3vfsrmekbg > enterprise_memory >
-- 2d09d4a7-6d74-4871-8212-c26918cc8bae-run-state-v1. Private endpoint: VPN plus
-- Cosmos DB Built-in Data Reader. Run each query separately in Data Explorer.
-- Do not ORDER BY metadata fields: they are excluded from the index (sort on agent_step yourself).

-- 1. All agents in one trace. span_id = App Insights dependencies.id (chat.agent).
SELECT c.partition_id, c["object"].metadata.agent_step AS step, c["object"].metadata.agent_id AS agent,
       c["object"].metadata.span_id AS span_id, c["object"].usage.input_tokens AS input_tokens,
       c["object"].usage.output_tokens AS output_tokens
FROM c
WHERE c["object"].metadata.trace_id = "<trace_id>"

-- 2. One agent by span_id.
SELECT c.partition_id, c["object"].metadata AS m FROM c
WHERE c["object"].metadata.span_id = "<span_id>"

-- 3. That agent's input and output: partition_id from query 1 or 2.
SELECT c._ts, c["object"].item_resource.role AS role, c["object"].item_resource.content[0].text AS text
FROM c
WHERE c.partition_id = "<partition_id>" AND IS_DEFINED(c["object"].item_resource)

-- 4. The user-facing turn (hosted response): partition ends with the 18 characters after
--    "caresp_" in chat.turn response_id.
SELECT c._ts, c["object"].item_resource.role AS role, c["object"].item_resource.content[0].text AS text
FROM c
WHERE ENDSWITH(c.partition_id, "/<18 chars>") AND IS_DEFINED(c["object"].item_resource)
