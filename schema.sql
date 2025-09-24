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
    author_id VARCHAR(255) NOT NULL,
    author_name VARCHAR(255) NOT NULL,
    channel_id VARCHAR(255) NOT NULL,
    message_id VARCHAR(255) UNIQUE NOT NULL,
    submitted_by_id VARCHAR(255) NOT NULL,
    submitted_by_name VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    vote_message_id VARCHAR(255),
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Votes table - tracks individual user votes to prevent duplicate voting
CREATE TABLE IF NOT EXISTS votes (
    id SERIAL PRIMARY KEY,
    quote_id INTEGER REFERENCES quotes(id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL,
    user_name VARCHAR(255) NOT NULL,
    vote_type VARCHAR(10) NOT NULL CHECK (vote_type IN ('upvote', 'downvote')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(quote_id, user_id)
);

-- Quote bot settings table
CREATE TABLE IF NOT EXISTS quote_bot_settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(255) UNIQUE NOT NULL,
    value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Useful indexes for better performance
CREATE INDEX IF NOT EXISTS idx_quotes_status ON quotes(status);
CREATE INDEX IF NOT EXISTS idx_quotes_submitted_at ON quotes(submitted_at);
CREATE INDEX IF NOT EXISTS idx_votes_quote_id ON votes(quote_id);
CREATE INDEX IF NOT EXISTS idx_votes_user_id ON votes(user_id);
CREATE INDEX IF NOT EXISTS idx_quotes_message_id ON quotes(message_id);
CREATE INDEX IF NOT EXISTS idx_settings_key ON quote_bot_settings(key);