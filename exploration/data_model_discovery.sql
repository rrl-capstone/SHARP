/* 
   HOW TO RUN :
     Run the whole script with Alt+X. You get three result tabs:
       [1] TABLES   one row per table: column count, partition columns, format, S3 location
       [2] MODEL    one row per column: type, role (key / join / partition), what it
                    joins to, confidence, ready-to-run JOIN SQL and match-check SQL
       [3] MERMAID  ER diagram text -> copy the column, paste at https://mermaid.live
     Click "Fetch all rows" before copying results (DBeaver only fetches 200 rows).

   External tables have no PK/FK constraints, so every join is inferred from names:
     high   : same column name as the key of the table named after it
              drug_exposure.person_id  -> person.person_id
     medium : role-named column pointing at that key, or x_id -> x.id
              condition_concept_id     -> concept.concept_id
     low    : key-like column shared by several tables, none named after it;
              linked to the smallest table that has it
   needs_cast = the two columns have different types; the generated SQL casts both.

   This script only reads metadata. The generated check_sql DOES read data from S3
   (Spectrum bills by bytes scanned); it samples 100k child rows to keep it light.

   Both MODEL and MERMAID repeat the same BASE block; change both if you edit a rule.
   ============================================================================= */
@set schema_1 = ''
@set schema_2 = ''


-- =============================================================================
-- [1] TABLES
-- =============================================================================
SELECT
    t.schemaname                                        AS table_schema,
    t.tablename                                         AS table_name,
    count(c.columnname)                                 AS column_count,
    sum(CASE WHEN c.part_key > 0 THEN 1 ELSE 0 END)     AS partition_columns,
    CASE WHEN t.input_format ILIKE '%parquet%' THEN 'parquet'
         WHEN t.input_format ILIKE '%orc%'     THEN 'orc'
         WHEN t.input_format ILIKE '%avro%'    THEN 'avro'
         WHEN t.input_format ILIKE '%text%'    THEN 'text/csv'
         ELSE t.input_format END                        AS file_format,
    t.location
FROM svv_external_tables t
LEFT JOIN svv_external_columns c
       ON c.schemaname = t.schemaname
      AND c.tablename  = t.tablename
WHERE t.schemaname IN (${schema_1}, ${schema_2})
GROUP BY t.schemaname, t.tablename, t.input_format, t.location
ORDER BY t.schemaname, t.tablename;


-- =============================================================================
-- [2] MODEL : table structure + inferred joins, one row per column
-- =============================================================================
WITH
-- ---------------- BASE BLOCK (start) ----------------
cols AS (
    SELECT
        c.schemaname::text                       AS table_schema,
        c.tablename::text                        AS table_name,
        c.columnnum                              AS column_position,
        c.columnname::text                       AS column_name,
        lower(c.columnname::text)                AS lc,
        lower(c.tablename::text)                 AS lt,
        c.external_type::text                    AS data_type,
        CASE WHEN position('<' in lower(c.external_type)) > 0
                  THEN substring(lower(c.external_type) from 1 for position('<' in lower(c.external_type)) - 1)
             WHEN position('(' in lower(c.external_type)) > 0
                  THEN substring(lower(c.external_type) from 1 for position('(' in lower(c.external_type)) - 1)
             ELSE lower(c.external_type) END     AS type_short,
        COALESCE(c.part_key, 0)                  AS part_key,
        CASE WHEN lower(c.external_type) ~ '^(tinyint|smallint|int|integer|bigint|decimal|numeric|double|float|real)'
                  THEN 'number'
             WHEN lower(c.external_type) ~ '^(string|varchar|char)'
                  THEN 'text'
             ELSE 'other' END                    AS type_family
    FROM svv_external_columns c
    WHERE c.schemaname IN (${schema_1}, ${schema_2})
),
ck AS (
    SELECT
        c.*,
        (c.lc ~ '(^id|_id|_key|_code|_cd|_sk|_no|_nbr|_num|_number)$'
         OR c.lc IN ('npi', 'ndc', 'ndc11', 'icd', 'cpt', 'hcpcs'))   AS is_keyish,
        -- person_id -> person, claim_no -> claim, diagnosis_code -> diagnosis
        CASE
            WHEN c.lc ~ '_id$'     THEN substring(c.lc from 1 for length(c.lc) - 3)
            WHEN c.lc ~ '_key$'    THEN substring(c.lc from 1 for length(c.lc) - 4)
            WHEN c.lc ~ '_code$'   THEN substring(c.lc from 1 for length(c.lc) - 5)
            WHEN c.lc ~ '_cd$'     THEN substring(c.lc from 1 for length(c.lc) - 3)
            WHEN c.lc ~ '_sk$'     THEN substring(c.lc from 1 for length(c.lc) - 3)
            WHEN c.lc ~ '_no$'     THEN substring(c.lc from 1 for length(c.lc) - 3)
            WHEN c.lc ~ '_nbr$'    THEN substring(c.lc from 1 for length(c.lc) - 4)
            WHEN c.lc ~ '_num$'    THEN substring(c.lc from 1 for length(c.lc) - 4)
            WHEN c.lc ~ '_number$' THEN substring(c.lc from 1 for length(c.lc) - 7)
            WHEN c.lc IN ('npi', 'ndc', 'ndc11', 'icd', 'cpt', 'hcpcs') THEN c.lc
            ELSE ''
        END                                      AS col_entity,
        -- dim_patients -> patients, ref_ndc -> ndc
        CASE WHEN c.lt ~ '^(dim|fact|fct|stg|tbl|ref|lkp|d|f|t)_'
             THEN substring(c.lt from position('_' in c.lt) + 1)
             ELSE c.lt END                       AS tbl_entity
    FROM cols c
),
ckf AS (
    SELECT
        ck.*,
        ck.col_entity || 's'                     AS f2,
        ck.col_entity || 'es'                    AS f3,
        CASE WHEN ck.col_entity ~ 'y$'
             THEN substring(ck.col_entity from 1 for length(ck.col_entity) - 1) || 'ies'
             ELSE ck.col_entity END              AS f4,
        (ck.is_keyish AND ck.lc <> 'id' AND ck.part_key = 0 AND ck.type_family <> 'other') AS joinable
    FROM ck
),
-- a key column sitting in the table named after it: person.person_id, concept.concept_id
home AS (
    SELECT table_schema, table_name, column_name, lc, type_family
    FROM ckf
    WHERE joinable
      AND tbl_entity IN (col_entity, f2, f3, f4)
),
-- high: drug_exposure.person_id -> person.person_id
exact_home AS (
    SELECT
        ch.table_schema AS from_schema, ch.table_name AS from_table, ch.column_name AS from_column,
        h.table_schema  AS to_schema,   h.table_name  AS to_table,   h.column_name  AS to_column,
        'high'::text                                               AS confidence,
        1                                                          AS conf_rank,
        'same column name; target table is named after it'::text   AS reason,
        ch.type_family                                             AS from_family,
        h.type_family                                              AS to_family
    FROM ckf ch
    JOIN home h
      ON h.lc = ch.lc
     AND (h.table_schema <> ch.table_schema OR h.table_name <> ch.table_name)
    WHERE ch.joinable
      -- same key has a home table in both schemas: link the two only once
      AND NOT (ch.tbl_entity IN (ch.col_entity, ch.f2, ch.f3, ch.f4)
               AND ch.table_schema || '.' || ch.table_name < h.table_schema || '.' || h.table_name)
),
-- medium: condition_concept_id -> concept.concept_id
role_home AS (
    SELECT
        ch.table_schema AS from_schema, ch.table_name AS from_table, ch.column_name AS from_column,
        h.table_schema  AS to_schema,   h.table_name  AS to_table,   h.column_name  AS to_column,
        'medium'::text                                             AS confidence,
        2                                                          AS conf_rank,
        'column ends with _' || h.column_name || '; target table is named after it' AS reason,
        ch.type_family                                             AS from_family,
        h.type_family                                              AS to_family
    FROM ckf ch
    JOIN home h
      ON length(ch.lc) > length(h.lc) + 1
     AND substring(ch.lc from length(ch.lc) - length(h.lc)) = '_' || h.lc
    WHERE ch.part_key = 0
      AND ch.type_family <> 'other'
),
-- medium: orders.customer_id -> customers.id
id_home AS (
    SELECT
        ch.table_schema AS from_schema, ch.table_name AS from_table, ch.column_name AS from_column,
        p.table_schema  AS to_schema,   p.table_name  AS to_table,   p.column_name  AS to_column,
        'medium'::text                                             AS confidence,
        2                                                          AS conf_rank,
        'x_id -> x.id pattern'::text                               AS reason,
        ch.type_family                                             AS from_family,
        p.type_family                                              AS to_family
    FROM ckf ch
    JOIN ckf p
      ON p.lc = 'id'
     AND p.type_family <> 'other'
     AND p.tbl_entity IN (ch.col_entity, ch.f2, ch.f3, ch.f4)
     AND (p.table_schema <> ch.table_schema OR p.table_name <> ch.table_name)
    WHERE ch.joinable
),
-- low: key-like column in 2+ tables, none named after it -> link to the smallest table
tsize AS (
    SELECT table_schema, table_name, count(*) AS ncols
    FROM ckf
    GROUP BY table_schema, table_name
),
shared_cols AS (
    SELECT c.lc, min(t.ncols) AS min_cols
    FROM ckf c
    JOIN tsize t ON t.table_schema = c.table_schema AND t.table_name = c.table_name
    WHERE c.joinable
      AND c.lc NOT IN (SELECT lc FROM home)
    GROUP BY c.lc
    HAVING count(*) >= 2
),
hub AS (
    SELECT c.lc, min(c.table_schema || '.' || c.table_name) AS hub_table
    FROM ckf c
    JOIN tsize t       ON t.table_schema = c.table_schema AND t.table_name = c.table_name
    JOIN shared_cols s ON s.lc = c.lc AND s.min_cols = t.ncols
    GROUP BY c.lc
),
peer AS (
    SELECT
        ch.table_schema AS from_schema, ch.table_name AS from_table, ch.column_name AS from_column,
        p.table_schema  AS to_schema,   p.table_name  AS to_table,   p.column_name  AS to_column,
        'low'::text                                                AS confidence,
        3                                                          AS conf_rank,
        'shared key-like column, no table named after it; linked to smallest table that has it'::text AS reason,
        ch.type_family                                             AS from_family,
        p.type_family                                              AS to_family
    FROM ckf ch
    JOIN hub hb ON hb.lc = ch.lc
    JOIN ckf p  ON p.lc = ch.lc AND p.table_schema || '.' || p.table_name = hb.hub_table
    WHERE ch.joinable
      AND ch.table_schema || '.' || ch.table_name <> hb.hub_table
),
all_rels AS (
    SELECT * FROM exact_home
    UNION ALL
    SELECT * FROM role_home
    UNION ALL
    SELECT * FROM id_home
    UNION ALL
    SELECT * FROM peer
),
-- per column keep the best guess: higher confidence, then same schema, then longest key name
best AS (
    SELECT from_schema, from_table, from_column,
           min(conf_rank * 1000
               + CASE WHEN from_schema = to_schema THEN 0 ELSE 100 END
               + 99 - CASE WHEN length(to_column) > 99 THEN 99 ELSE length(to_column) END) AS best_score
    FROM all_rels
    GROUP BY from_schema, from_table, from_column
),
rels AS (
    SELECT
        r.*,
        (r.from_schema <> r.to_schema)  AS cross_schema,
        (r.from_family <> r.to_family)  AS needs_cast
    FROM all_rels r
    JOIN best b
      ON b.from_schema = r.from_schema
     AND b.from_table  = r.from_table
     AND b.from_column = r.from_column
     AND b.best_score  = r.conf_rank * 1000
                         + CASE WHEN r.from_schema = r.to_schema THEN 0 ELSE 100 END
                         + 99 - CASE WHEN length(r.to_column) > 99 THEN 99 ELSE length(r.to_column) END
)
-- ---------------- BASE BLOCK (end) ----------------
SELECT
    x.table_schema,
    x.table_name,
    x.column_position                                          AS pos,
    x.column_name,
    x.data_type,
    CASE WHEN x.part_key > 0 THEN 'partition'
         WHEN hk.lc IS NOT NULL AND r.from_column IS NOT NULL THEN 'key + join'
         WHEN hk.lc IS NOT NULL THEN 'key'
         WHEN r.from_column IS NOT NULL THEN 'join'
         ELSE '' END                                           AS role,
    r.to_schema || '.' || r.to_table || '.' || r.to_column     AS joins_to,
    r.confidence,
    r.cross_schema,
    r.needs_cast,
    r.reason,
    CASE WHEN r.from_column IS NOT NULL THEN
        'SELECT * FROM ' || quote_ident(x.table_schema) || '.' || quote_ident(x.table_name)
        || ' c LEFT JOIN ' || quote_ident(r.to_schema) || '.' || quote_ident(r.to_table) || ' p ON '
        || CASE WHEN r.needs_cast
                THEN 'CAST(c.' || quote_ident(r.from_column) || ' AS VARCHAR) = CAST(p.'
                     || quote_ident(r.to_column) || ' AS VARCHAR)'
                ELSE 'c.' || quote_ident(r.from_column) || ' = p.' || quote_ident(r.to_column) END
        || ' LIMIT 100'
    END                                                        AS join_sql,
    CASE WHEN r.from_column IS NOT NULL THEN
        'SELECT count(*) AS sample_rows, count(p.k) AS matched, '
        || 'round(100.0 * count(p.k) / nullif(count(*), 0), 1) AS match_pct FROM (SELECT '
        || CASE WHEN r.needs_cast THEN 'CAST(' || quote_ident(r.from_column) || ' AS VARCHAR)'
                ELSE quote_ident(r.from_column) END
        || ' AS k FROM ' || quote_ident(x.table_schema) || '.' || quote_ident(x.table_name)
        || ' WHERE ' || quote_ident(r.from_column) || ' IS NOT NULL LIMIT 100000) c LEFT JOIN (SELECT DISTINCT '
        || CASE WHEN r.needs_cast THEN 'CAST(' || quote_ident(r.to_column) || ' AS VARCHAR)'
                ELSE quote_ident(r.to_column) END
        || ' AS k FROM ' || quote_ident(r.to_schema) || '.' || quote_ident(r.to_table) || ') p ON c.k = p.k'
    END                                                        AS check_sql
FROM ckf x
LEFT JOIN home hk
       ON hk.table_schema = x.table_schema
      AND hk.table_name   = x.table_name
      AND hk.column_name  = x.column_name
LEFT JOIN rels r
       ON r.from_schema = x.table_schema
      AND r.from_table  = x.table_name
      AND r.from_column = x.column_name
ORDER BY x.table_schema, x.table_name, x.column_position, r.conf_rank;


-- =============================================================================
-- [3] MERMAID ER DIAGRAM : copy the whole column -> https://mermaid.live
-- =============================================================================
WITH
-- ---------------- BASE BLOCK (start) ----------------
cols AS (
    SELECT
        c.schemaname::text                       AS table_schema,
        c.tablename::text                        AS table_name,
        c.columnnum                              AS column_position,
        c.columnname::text                       AS column_name,
        lower(c.columnname::text)                AS lc,
        lower(c.tablename::text)                 AS lt,
        c.external_type::text                    AS data_type,
        CASE WHEN position('<' in lower(c.external_type)) > 0
                  THEN substring(lower(c.external_type) from 1 for position('<' in lower(c.external_type)) - 1)
             WHEN position('(' in lower(c.external_type)) > 0
                  THEN substring(lower(c.external_type) from 1 for position('(' in lower(c.external_type)) - 1)
             ELSE lower(c.external_type) END     AS type_short,
        COALESCE(c.part_key, 0)                  AS part_key,
        CASE WHEN lower(c.external_type) ~ '^(tinyint|smallint|int|integer|bigint|decimal|numeric|double|float|real)'
                  THEN 'number'
             WHEN lower(c.external_type) ~ '^(string|varchar|char)'
                  THEN 'text'
             ELSE 'other' END                    AS type_family
    FROM svv_external_columns c
    WHERE c.schemaname IN (${schema_1}, ${schema_2})
),
ck AS (
    SELECT
        c.*,
        (c.lc ~ '(^id|_id|_key|_code|_cd|_sk|_no|_nbr|_num|_number)$'
         OR c.lc IN ('npi', 'ndc', 'ndc11', 'icd', 'cpt', 'hcpcs'))   AS is_keyish,
        CASE
            WHEN c.lc ~ '_id$'     THEN substring(c.lc from 1 for length(c.lc) - 3)
            WHEN c.lc ~ '_key$'    THEN substring(c.lc from 1 for length(c.lc) - 4)
            WHEN c.lc ~ '_code$'   THEN substring(c.lc from 1 for length(c.lc) - 5)
            WHEN c.lc ~ '_cd$'     THEN substring(c.lc from 1 for length(c.lc) - 3)
            WHEN c.lc ~ '_sk$'     THEN substring(c.lc from 1 for length(c.lc) - 3)
            WHEN c.lc ~ '_no$'     THEN substring(c.lc from 1 for length(c.lc) - 3)
            WHEN c.lc ~ '_nbr$'    THEN substring(c.lc from 1 for length(c.lc) - 4)
            WHEN c.lc ~ '_num$'    THEN substring(c.lc from 1 for length(c.lc) - 4)
            WHEN c.lc ~ '_number$' THEN substring(c.lc from 1 for length(c.lc) - 7)
            WHEN c.lc IN ('npi', 'ndc', 'ndc11', 'icd', 'cpt', 'hcpcs') THEN c.lc
            ELSE ''
        END                                      AS col_entity,
        CASE WHEN c.lt ~ '^(dim|fact|fct|stg|tbl|ref|lkp|d|f|t)_'
             THEN substring(c.lt from position('_' in c.lt) + 1)
             ELSE c.lt END                       AS tbl_entity
    FROM cols c
),
ckf AS (
    SELECT
        ck.*,
        ck.col_entity || 's'                     AS f2,
        ck.col_entity || 'es'                    AS f3,
        CASE WHEN ck.col_entity ~ 'y$'
             THEN substring(ck.col_entity from 1 for length(ck.col_entity) - 1) || 'ies'
             ELSE ck.col_entity END              AS f4,
        (ck.is_keyish AND ck.lc <> 'id' AND ck.part_key = 0 AND ck.type_family <> 'other') AS joinable
    FROM ck
),
home AS (
    SELECT table_schema, table_name, column_name, lc, type_family
    FROM ckf
    WHERE joinable
      AND tbl_entity IN (col_entity, f2, f3, f4)
),
exact_home AS (
    SELECT
        ch.table_schema AS from_schema, ch.table_name AS from_table, ch.column_name AS from_column,
        h.table_schema  AS to_schema,   h.table_name  AS to_table,   h.column_name  AS to_column,
        'high'::text                                               AS confidence,
        1                                                          AS conf_rank,
        'same column name; target table is named after it'::text   AS reason,
        ch.type_family                                             AS from_family,
        h.type_family                                              AS to_family
    FROM ckf ch
    JOIN home h
      ON h.lc = ch.lc
     AND (h.table_schema <> ch.table_schema OR h.table_name <> ch.table_name)
    WHERE ch.joinable
      AND NOT (ch.tbl_entity IN (ch.col_entity, ch.f2, ch.f3, ch.f4)
               AND ch.table_schema || '.' || ch.table_name < h.table_schema || '.' || h.table_name)
),
role_home AS (
    SELECT
        ch.table_schema AS from_schema, ch.table_name AS from_table, ch.column_name AS from_column,
        h.table_schema  AS to_schema,   h.table_name  AS to_table,   h.column_name  AS to_column,
        'medium'::text                                             AS confidence,
        2                                                          AS conf_rank,
        'column ends with _' || h.column_name || '; target table is named after it' AS reason,
        ch.type_family                                             AS from_family,
        h.type_family                                              AS to_family
    FROM ckf ch
    JOIN home h
      ON length(ch.lc) > length(h.lc) + 1
     AND substring(ch.lc from length(ch.lc) - length(h.lc)) = '_' || h.lc
    WHERE ch.part_key = 0
      AND ch.type_family <> 'other'
),
id_home AS (
    SELECT
        ch.table_schema AS from_schema, ch.table_name AS from_table, ch.column_name AS from_column,
        p.table_schema  AS to_schema,   p.table_name  AS to_table,   p.column_name  AS to_column,
        'medium'::text                                             AS confidence,
        2                                                          AS conf_rank,
        'x_id -> x.id pattern'::text                               AS reason,
        ch.type_family                                             AS from_family,
        p.type_family                                              AS to_family
    FROM ckf ch
    JOIN ckf p
      ON p.lc = 'id'
     AND p.type_family <> 'other'
     AND p.tbl_entity IN (ch.col_entity, ch.f2, ch.f3, ch.f4)
     AND (p.table_schema <> ch.table_schema OR p.table_name <> ch.table_name)
    WHERE ch.joinable
),
tsize AS (
    SELECT table_schema, table_name, count(*) AS ncols
    FROM ckf
    GROUP BY table_schema, table_name
),
shared_cols AS (
    SELECT c.lc, min(t.ncols) AS min_cols
    FROM ckf c
    JOIN tsize t ON t.table_schema = c.table_schema AND t.table_name = c.table_name
    WHERE c.joinable
      AND c.lc NOT IN (SELECT lc FROM home)
    GROUP BY c.lc
    HAVING count(*) >= 2
),
hub AS (
    SELECT c.lc, min(c.table_schema || '.' || c.table_name) AS hub_table
    FROM ckf c
    JOIN tsize t       ON t.table_schema = c.table_schema AND t.table_name = c.table_name
    JOIN shared_cols s ON s.lc = c.lc AND s.min_cols = t.ncols
    GROUP BY c.lc
),
peer AS (
    SELECT
        ch.table_schema AS from_schema, ch.table_name AS from_table, ch.column_name AS from_column,
        p.table_schema  AS to_schema,   p.table_name  AS to_table,   p.column_name  AS to_column,
        'low'::text                                                AS confidence,
        3                                                          AS conf_rank,
        'shared key-like column, no table named after it; linked to smallest table that has it'::text AS reason,
        ch.type_family                                             AS from_family,
        p.type_family                                              AS to_family
    FROM ckf ch
    JOIN hub hb ON hb.lc = ch.lc
    JOIN ckf p  ON p.lc = ch.lc AND p.table_schema || '.' || p.table_name = hb.hub_table
    WHERE ch.joinable
      AND ch.table_schema || '.' || ch.table_name <> hb.hub_table
),
all_rels AS (
    SELECT * FROM exact_home
    UNION ALL
    SELECT * FROM role_home
    UNION ALL
    SELECT * FROM id_home
    UNION ALL
    SELECT * FROM peer
),
best AS (
    SELECT from_schema, from_table, from_column,
           min(conf_rank * 1000
               + CASE WHEN from_schema = to_schema THEN 0 ELSE 100 END
               + 99 - CASE WHEN length(to_column) > 99 THEN 99 ELSE length(to_column) END) AS best_score
    FROM all_rels
    GROUP BY from_schema, from_table, from_column
),
rels AS (
    SELECT
        r.*,
        (r.from_schema <> r.to_schema)  AS cross_schema,
        (r.from_family <> r.to_family)  AS needs_cast
    FROM all_rels r
    JOIN best b
      ON b.from_schema = r.from_schema
     AND b.from_table  = r.from_table
     AND b.from_column = r.from_column
     AND b.best_score  = r.conf_rank * 1000
                         + CASE WHEN r.from_schema = r.to_schema THEN 0 ELSE 100 END
                         + 99 - CASE WHEN length(r.to_column) > 99 THEN 99 ELSE length(r.to_column) END
),
-- ---------------- BASE BLOCK (end) ----------------
ent AS (
    SELECT table_schema, table_name,
           translate(table_schema || '__' || table_name, ' .-#', '____') AS ent,
           min(column_position)                                          AS first_pos
    FROM ckf
    GROUP BY table_schema, table_name
),
fk_cols AS (
    SELECT DISTINCT from_schema, from_table, from_column
    FROM rels
),
mrels AS (
    SELECT DISTINCT from_schema, from_table, from_column, to_schema, to_table, confidence
    FROM rels
    -- add  WHERE confidence <> 'low'  here to hide the weakest guesses
),
lines AS (
    SELECT 0 AS sect, ''::text AS ent, 0 AS pos, 'erDiagram'::text AS line
    UNION ALL
    SELECT 0, '', 1, '    %% all keys and joins are inferred from column names'
    UNION ALL
    SELECT 1, e.ent, -1, '    ' || e.ent || ' {'
    FROM ent e
    UNION ALL
    SELECT 1, e.ent, c.column_position,
           '        ' || translate(c.type_short, ' .-#', '____')
           || ' ' || translate(c.column_name, ' .-#', '____')
           || CASE WHEN hk.lc IS NOT NULL AND f.from_column IS NOT NULL THEN ' PK, FK'
                   WHEN hk.lc IS NOT NULL THEN ' PK'
                   WHEN f.from_column IS NOT NULL THEN ' FK'
                   ELSE '' END
           || CASE WHEN c.part_key > 0 THEN ' "partition"' ELSE '' END
    FROM ckf c
    JOIN ent e ON e.table_schema = c.table_schema AND e.table_name = c.table_name
    LEFT JOIN home hk
           ON hk.table_schema = c.table_schema
          AND hk.table_name   = c.table_name
          AND hk.column_name  = c.column_name
    LEFT JOIN fk_cols f
           ON f.from_schema = c.table_schema
          AND f.from_table  = c.table_name
          AND f.from_column = c.column_name
    -- draws key / join / partition columns only (plus the first column so no box is empty);
    -- delete the next line to draw every column
    WHERE hk.lc IS NOT NULL OR f.from_column IS NOT NULL OR c.part_key > 0 OR c.column_position = e.first_pos
    UNION ALL
    SELECT 1, e.ent, 2147483647, '    }'
    FROM ent e
    UNION ALL
    SELECT 2, ce.ent, 0,
           '    ' || pe.ent || ' ||..o{ ' || ce.ent || ' : "' || r.from_column || ' (' || r.confidence || ')"'
    FROM mrels r
    JOIN ent ce ON ce.table_schema = r.from_schema AND ce.table_name = r.from_table
    JOIN ent pe ON pe.table_schema = r.to_schema   AND pe.table_name = r.to_table
)
SELECT line AS mermaid
FROM lines
ORDER BY sect, ent, pos;