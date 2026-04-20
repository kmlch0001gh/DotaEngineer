-- Staging: raw OpenDota hero stats → cleaned, normalized columns
-- Source: hero_meta_raw (populated by meta_pipeline.py)

WITH source AS (
    SELECT *
    FROM {{ source('raw', 'hero_meta_raw') }}
    WHERE source = 'opendota'
),

cleaned AS (
    SELECT
        hero_id,
        hero_name,
        ingested_at::DATE                                       AS data_date,
        total_matches,
        total_wins,
        CASE
            WHEN total_matches > 0
            THEN ROUND(total_wins / total_matches::FLOAT, 4)
            ELSE NULL
        END                                                     AS overall_win_rate,
        -- Immortal bracket specific columns (8_pick / 8_win in OpenDota naming)
        immortal_matches,
        immortal_wins,
        CASE
            WHEN immortal_matches > 0
            THEN ROUND(immortal_wins / immortal_matches::FLOAT, 4)
            ELSE NULL
        END                                                     AS immortal_win_rate
    FROM source
)

SELECT * FROM cleaned
