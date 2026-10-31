"""Query templates for the PostgreSQL Flexible Server search tab.

PostgreSQL has no built-in Thai collation-aware edit distance function, so the
fuzzy mode relies on the ``pg_trgm`` extension's trigram ``similarity()``
function instead of Azure SQL's ``EDIT_DISTANCE_SIMILARITY``. Scores are on a
0-1 scale (not the 0-100 scale used by the SQL tabs).
"""

POSTGRES_FUZZY_QUERY = """
SELECT
    id,
    first_name,
    last_name,
    address,
    GREATEST(
        similarity(first_name, %s),
        similarity(last_name, %s),
        similarity(address, %s)
    ) AS score
FROM thai_people
WHERE first_name %% %s OR last_name %% %s OR address %% %s
ORDER BY score DESC, id
LIMIT 20
"""

POSTGRES_PREFIX_QUERY = """
SELECT id, first_name, last_name, address
FROM thai_people
WHERE first_name ILIKE %s OR last_name ILIKE %s OR address ILIKE %s
ORDER BY id
LIMIT 20
"""

POSTGRES_BROWSE_QUERY = """
SELECT id, first_name, last_name, address
FROM thai_people
ORDER BY id
LIMIT 20
"""

POSTGRES_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS thai_people (
    id INT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    street TEXT,
    district TEXT,
    province TEXT,
    postal_code TEXT,
    address TEXT NOT NULL
)
"""

POSTGRES_CREATE_TRGM_INDEXES = """
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_thai_people_first_name_trgm
    ON thai_people USING gin (first_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_thai_people_last_name_trgm
    ON thai_people USING gin (last_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_thai_people_address_trgm
    ON thai_people USING gin (address gin_trgm_ops);
"""
