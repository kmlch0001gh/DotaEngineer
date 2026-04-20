-- Mart: hero matchup matrix at immortal bracket
-- hero_id vs enemy_hero_id → win rate advantage
-- Populated from OpenDota /heroes/{id}/matchups for all heroes

WITH source AS (
    SELECT *
    FROM {{ source('raw', 'hero_matchups_raw') }}
    WHERE bracket = 'immortal'
),

hero_names AS (
    SELECT hero_id, localized_name AS hero_name FROM {{ ref('stg_heroes') }}
),

calc AS (
    SELECT
        s.hero_id,
        hn1.hero_name,
        s.enemy_hero_id,
        hn2.hero_name                                               AS enemy_hero_name,
        s.matchup_count,
        s.matchup_wins,
        ROUND(s.matchup_wins / NULLIF(s.matchup_count, 0)::FLOAT, 4)  AS win_rate,
        -- Advantage vs expected 50% baseline
        ROUND(
            s.matchup_wins / NULLIF(s.matchup_count, 0)::FLOAT - 0.5,
            4
        )                                                           AS win_rate_advantage
    FROM source s
    LEFT JOIN hero_names hn1 ON s.hero_id = hn1.hero_id
    LEFT JOIN hero_names hn2 ON s.enemy_hero_id = hn2.hero_id
    WHERE s.matchup_count >= 100
)

SELECT * FROM calc
