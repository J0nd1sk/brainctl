-- Migration 087: bi-temporal validity on memories (interference control)
--
-- created_at / retired_at record *transaction* time: when brainctl learned
-- a memory and when it stopped storing it as active. They say nothing about
-- when the fact itself was true. `memory add --supersedes <id>` used to
-- leave the superseded row fully active, so the stale value kept winning
-- searches (it was older, so it won exact-score ties on the lower id).
--
-- valid_from / valid_to record *valid* time: the interval during which the
-- fact held. NULL valid_from means "since created_at"; NULL valid_to means
-- "still true". A supersede closes the predecessor's interval
-- (valid_to = the successor's write time) and retires it, so the row and
-- the supersedes_id chain stay on disk for audit.
--
-- cmd_search drops any candidate whose valid_to has passed, or that an
-- active memory supersedes, so links written before this migration (or by
-- tools that set supersedes_id without closing the interval) stop
-- intruding too.
--
-- Backfill: rows that an active memory already supersedes get
-- valid_to = the earliest such successor's created_at. Nothing is retired
-- or deleted here.
--
-- Rollback:
--   DROP INDEX IF EXISTS idx_memories_valid_to;
--   DROP INDEX IF EXISTS idx_memories_supersedes;
--   UPDATE memories SET valid_from = NULL, valid_to = NULL;
--   DELETE FROM schema_versions WHERE version = 87;
--
-- IDEMPOTENT (the runner treats "duplicate column name" as already applied;
-- the backfill only touches rows whose valid_to is still NULL).

ALTER TABLE memories ADD COLUMN valid_from TEXT DEFAULT NULL;
ALTER TABLE memories ADD COLUMN valid_to TEXT DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_memories_supersedes
    ON memories(supersedes_id) WHERE supersedes_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_memories_valid_to
    ON memories(valid_to) WHERE valid_to IS NOT NULL;

UPDATE memories
   SET valid_to = (
       SELECT MIN(s.created_at) FROM memories s
        WHERE s.supersedes_id = memories.id AND s.retired_at IS NULL
   )
 WHERE valid_to IS NULL
   AND id IN (
       SELECT supersedes_id FROM memories
        WHERE supersedes_id IS NOT NULL AND retired_at IS NULL
   );
