"""Synthetic example evidence tool. Hand-authored shape illustration, never executed in a run."""


def run(ctx):
    rows = ctx.query(
        "SELECT category, count(*) AS events FROM evidence WHERE case_id = :case_id GROUP BY category ORDER BY events DESC",
        {"case_id": ctx.case_id},
        max_rows=50,
    )["rows"]
    return {"categories": [{"category": row[0], "events": row[1]} for row in rows[:10]],
            "distinct_categories": len(rows)}
