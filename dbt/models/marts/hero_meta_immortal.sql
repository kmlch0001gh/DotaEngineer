-- Mart: unified hero meta table at immortal bracket
-- Joins OpenDota + Stratz to get win rate, pick rate, ban rate.
-- This is the primary table consumed by the analysis layer.

WITH od AS (
    SELECT *
    FROM {{ ref('stg_hero_meta_opendota') }}
    WHERE data_date = (SELECT MAX(data_date) FROM {{ ref('stg_hero_meta_opendota') }})
),

stratz AS (
    SELECT *
    FROM {{ ref('stg_hero_meta_stratz') }}
    WHERE data_date = (SELECT MAX(data_date) FROM {{ ref('stg_hero_meta_stratz') }})
),

hero_roles AS (
    SELECT *
    FROM {{ ref('stg_heroes') }}
),

joined AS (
    SELECT
        od.hero_id,
        hr.localized_name                                   AS hero_name,
        hr.primary_attr,
        hr.attack_type,
        hr.primary_role,
        hr.roles,
        -- Win rate: prefer Stratz immortal, fallback to OpenDota immortal
        COALESCE(stratz.win_rate, od.immortal_win_rate)     AS immortal_win_rate,
        COALESCE(stratz.pick_rate, NULL)                    AS immortal_pick_rate,
        COALESCE(stratz.ban_rate, NULL)                     AS immortal_ban_rate,
        COALESCE(stratz.match_count, od.immortal_matches)   AS immortal_matches,
        od.overall_win_rate,
        od.total_matches
    FROM od
    LEFT JOIN stratz USING (hero_id)
    LEFT JOIN hero_roles USING (hero_id)
)

SELECT * FROM joined
WHERE hero_id IS NOT NULL
