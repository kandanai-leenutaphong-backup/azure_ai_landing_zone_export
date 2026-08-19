BASELINE_SQL_FUZZY_QUERY = """
WITH ScoredPeople AS (
    SELECT
        id,
        first_name,
        last_name,
        address,
        first_name_score,
        last_name_score,
        address_score,
        (
            SELECT MAX(score)
            FROM (
                VALUES
                    (first_name_score),
                    (last_name_score),
                    (address_score)
            ) AS scores(score)
        ) AS score
    FROM dbo.thai_people
    CROSS APPLY (
        SELECT
            EDIT_DISTANCE_SIMILARITY(
                first_name COLLATE Thai_100_CI_AI,
                CAST(%s AS NVARCHAR(100)) COLLATE Thai_100_CI_AI
            ) AS first_name_score,
            EDIT_DISTANCE_SIMILARITY(
                last_name COLLATE Thai_100_CI_AI,
                CAST(%s AS NVARCHAR(100)) COLLATE Thai_100_CI_AI
            ) AS last_name_score,
            EDIT_DISTANCE_SIMILARITY(
                address COLLATE Thai_100_CI_AI,
                CAST(%s AS NVARCHAR(500)) COLLATE Thai_100_CI_AI
            ) AS address_score
    ) AS similarities
)
SELECT TOP 20
    id,
    first_name,
    last_name,
    address,
    score,
    first_name_score,
    last_name_score,
    address_score
FROM ScoredPeople
WHERE score >= 30
ORDER BY score DESC, id
"""


NATIVE_TOKEN_FUZZY_QUERY = """
WITH QueryTokens AS (
    SELECT DISTINCT token
    FROM OPENJSON(%s)
    WITH (token NVARCHAR(100) '$.token')
),
TokenMatches AS (
    SELECT
        q.token AS query_token,
        candidates.token AS candidate_token,
        EDIT_DISTANCE_SIMILARITY(
            candidates.token COLLATE Thai_100_CI_AI,
            q.token COLLATE Thai_100_CI_AI
        ) AS similarity
    FROM QueryTokens q
    CROSS APPLY (
        SELECT vocabulary.token
        FROM dbo.thai_token_vocabulary vocabulary
        WHERE vocabulary.token_length BETWEEN
            CASE WHEN LEN(q.token) > 1 THEN LEN(q.token) - 1 ELSE 1 END
            AND LEN(q.token) + 1
    ) candidates
),
PersonTokenScores AS (
    SELECT
        t.person_id,
        matches.query_token,
        MAX(matches.similarity) AS token_score
    FROM TokenMatches matches
    JOIN dbo.thai_people_tokens t
        ON t.token = matches.candidate_token
    WHERE matches.similarity >= 50
    GROUP BY t.person_id, matches.query_token
),
RankedPeople AS (
    SELECT
        p.id,
        p.first_name,
        p.last_name,
        p.address,
        CAST(AVG(CAST(scores.token_score AS FLOAT)) AS DECIMAL(5, 1)) AS score
    FROM PersonTokenScores scores
    JOIN dbo.thai_people p ON p.id = scores.person_id
    GROUP BY p.id, p.first_name, p.last_name, p.address
    HAVING COUNT(*) = (SELECT COUNT(*) FROM QueryTokens)
)
SELECT TOP 20
    ranked.id,
    ranked.first_name,
    ranked.last_name,
    ranked.address,
    ranked.score,
    (
        SELECT STRING_AGG(t.token, N' | ')
        FROM dbo.thai_people_tokens t
        WHERE t.person_id = ranked.id
    ) AS tokens
FROM RankedPeople ranked
ORDER BY ranked.score DESC, ranked.id
"""
