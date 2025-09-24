-- Database schema for Quote Bot
-- This file shows the tables that will be created automatically by the bot
-- You can use this for reference or manual setup if needed

-- Create database (run this manually as superuser)
-- CREATE DATABASE quotebot;
-- CREATE USER quotebot_user WITH PASSWORD 'your_password_here';
-- GRANT ALL PRIVILEGES ON DATABASE quotebot TO quotebot_user;

-- Main quotes table - stores all submitted quotes
CREATE TABLE IF NOT EXISTS quotes (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    author_id BIGINT NOT NULL,
    author_name VARCHAR(255) NOT NULL,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    message_id BIGINT,
    channel_id BIGINT,
    upvotes INTEGER DEFAULT 0,
    downvotes INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',
    processed_at TIMESTAMP
);

-- Votes table - tracks individual user votes to prevent duplicate voting
CREATE TABLE IF NOT EXISTS votes (
    id SERIAL PRIMARY KEY,
    quote_id INTEGER REFERENCES quotes(id),
    user_id BIGINT NOT NULL,
    vote_type VARCHAR(10) NOT NULL,
    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(quote_id, user_id)
);

-- Approved quotes table - stores quotes that passed the voting process
CREATE TABLE IF NOT EXISTS approved_quotes (
    id SERIAL PRIMARY KEY,
    quote_id INTEGER REFERENCES quotes(id),
    content TEXT NOT NULL,
    author_name VARCHAR(255) NOT NULL,
    approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    final_score INTEGER DEFAULT 0
);

-- Useful indexes for better performance
CREATE INDEX IF NOT EXISTS idx_quotes_status ON quotes(status);
CREATE INDEX IF NOT EXISTS idx_quotes_submitted_at ON quotes(submitted_at);
CREATE INDEX IF NOT EXISTS idx_votes_quote_id ON votes(quote_id);
CREATE INDEX IF NOT EXISTS idx_votes_user_id ON votes(user_id);