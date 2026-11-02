CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id          serial PRIMARY KEY,
    name        text NOT NULL,
    edition     text NOT NULL,
    sha256      char(64) NOT NULL UNIQUE,
    page_count  int NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

-- One row per section of the Act or per Schedule. Holds the full text so an answer
-- can show the whole provision, not just the chunk that matched.
CREATE TABLE IF NOT EXISTS provisions (
    id            serial PRIMARY KEY,
    document_id   int NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    kind          text NOT NULL CHECK (kind IN ('section', 'schedule')),
    number        text NOT NULL,           -- '24', '80C', 'First Schedule'
    heading       text NOT NULL,
    chapter       text,                    -- 'IV'
    chapter_title text,
    page_start    int NOT NULL,
    page_end      int NOT NULL,
    text          text NOT NULL,
    omitted       boolean NOT NULL DEFAULT false,
    seq           int NOT NULL             -- order in the PDF
);

CREATE INDEX IF NOT EXISTS provisions_number_idx ON provisions (document_id, number);

-- Retrieval unit: a subsection, clause, proviso or explanation, small enough to cite precisely.
CREATE TABLE IF NOT EXISTS chunks (
    id           serial PRIMARY KEY,
    provision_id int NOT NULL REFERENCES provisions(id) ON DELETE CASCADE,
    ref          text NOT NULL,            -- 'Section 24(b)', 'Section 139(1), fourth proviso'
    path         text[] NOT NULL,          -- {'24', 'b'}
    page_start   int NOT NULL,
    page_end     int NOT NULL,
    text         text NOT NULL,
    context      text NOT NULL,            -- section heading prepended for search
    amended_by   text[] NOT NULL DEFAULT '{}',
    embedding    vector(384),
    tsv          tsvector GENERATED ALWAYS AS (to_tsvector('english', context || ' ' || text)) STORED
);

CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_provision_idx ON chunks (provision_id);
