-- HCS Mains Exam Prep — Supabase Schema Extension
-- Run these SQL commands in Supabase to add Mains support

-- 1. Add exam_mode column to user_profiles
ALTER TABLE user_profiles ADD COLUMN exam_mode text DEFAULT 'prelims';

-- 2. Create mains_answers table for tracking answer writing practice
CREATE TABLE mains_answers (
  id bigserial PRIMARY KEY,
  chat_id text NOT NULL,
  topic text NOT NULL,
  question_text text NOT NULL,
  user_answer text NOT NULL,
  answer_type text NOT NULL,        -- 'short' | 'medium' | 'essay' | 'case_study'
  score_content int,                -- 0–10
  score_structure int,              -- 0–5
  score_examples int,               -- 0–5
  total_score int,
  max_score int DEFAULT 20,
  feedback text,
  missing_points jsonb,
  attempted_at timestamptz DEFAULT NOW()
);

-- 3. Create indexes for efficient queries
CREATE INDEX ON mains_answers(chat_id);
CREATE INDEX ON mains_answers(chat_id, topic);
CREATE INDEX ON mains_answers(chat_id, answer_type);
CREATE INDEX ON mains_answers(attempted_at DESC);

-- 4. Verify table creation
SELECT * FROM mains_answers LIMIT 1;
