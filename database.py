"""Database models and connection management."""
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
import logging
from config import Config

logger = logging.getLogger(__name__)

class Database:
    """Database connection and operations manager."""
    
    def __init__(self):
        self.connection = None
        self.connect()
    
    def connect(self):
        """Establish database connection."""
        try:
            self.connection = psycopg2.connect(
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                database=Config.DB_NAME,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD
            )
            self.connection.autocommit = True
            logger.info("Database connected successfully")
            self.setup_tables()
        except psycopg2.Error as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def setup_tables(self):
        """Create necessary tables if they don't exist."""
        cursor = self.connection.cursor()
        try:
            # Quotes table
            cursor.execute("""
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
                    status VARCHAR(20) DEFAULT 'voting',
                    processed_at TIMESTAMP
                )
            """)
            
            # Votes table to track individual votes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS votes (
                    id SERIAL PRIMARY KEY,
                    quote_id INTEGER REFERENCES quotes(id),
                    user_id BIGINT NOT NULL,
                    vote_type VARCHAR(10) NOT NULL,
                    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(quote_id, user_id)
                )
            """)
            
            # Approved quotes table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS approved_quotes (
                    id SERIAL PRIMARY KEY,
                    quote_id INTEGER REFERENCES quotes(id),
                    content TEXT NOT NULL,
                    author_name VARCHAR(255) NOT NULL,
                    approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    final_score INTEGER DEFAULT 0
                )
            """)
            
            logger.info("Database tables created/verified successfully")
        except psycopg2.Error as e:
            logger.error(f"Failed to setup tables: {e}")
            raise
        finally:
            cursor.close()
    
    def add_quote(self, content, author_id, author_name, message_id=None, channel_id=None):
        """Add a new quote to the database."""
        cursor = self.connection.cursor()
        try:
            cursor.execute("""
                INSERT INTO quotes (content, author_id, author_name, message_id, channel_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (content, author_id, author_name, message_id, channel_id))
            
            quote_id = cursor.fetchone()[0]
            logger.info(f"Quote {quote_id} added successfully")
            return quote_id
        except psycopg2.Error as e:
            logger.error(f"Failed to add quote: {e}")
            raise
        finally:
            cursor.close()
    
    def update_quote_message_info(self, quote_id, message_id, channel_id):
        """Update quote with message and channel IDs."""
        cursor = self.connection.cursor()
        try:
            cursor.execute("""
                UPDATE quotes 
                SET message_id = %s, channel_id = %s 
                WHERE id = %s
            """, (message_id, channel_id, quote_id))
            logger.info(f"Quote {quote_id} message info updated")
        except psycopg2.Error as e:
            logger.error(f"Failed to update quote message info: {e}")
            raise
        finally:
            cursor.close()
    
    def add_vote(self, quote_id, user_id, vote_type):
        """Add or update a vote for a quote."""
        cursor = self.connection.cursor()
        try:
            # First, try to update existing vote
            cursor.execute("""
                INSERT INTO votes (quote_id, user_id, vote_type)
                VALUES (%s, %s, %s)
                ON CONFLICT (quote_id, user_id)
                DO UPDATE SET vote_type = EXCLUDED.vote_type, voted_at = CURRENT_TIMESTAMP
            """, (quote_id, user_id, vote_type))
            
            # Update vote counts in quotes table
            cursor.execute("""
                UPDATE quotes 
                SET upvotes = (
                    SELECT COUNT(*) FROM votes 
                    WHERE quote_id = %s AND vote_type = 'upvote'
                ),
                downvotes = (
                    SELECT COUNT(*) FROM votes 
                    WHERE quote_id = %s AND vote_type = 'downvote'
                )
                WHERE id = %s
            """, (quote_id, quote_id, quote_id))
            
            logger.info(f"Vote added for quote {quote_id} by user {user_id}")
        except psycopg2.Error as e:
            logger.error(f"Failed to add vote: {e}")
            raise
        finally:
            cursor.close()
    
    def get_quote_by_id(self, quote_id):
        """Get a quote by its ID."""
        cursor = self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cursor.execute("SELECT * FROM quotes WHERE id = %s", (quote_id,))
            return cursor.fetchone()
        except psycopg2.Error as e:
            logger.error(f"Failed to get quote: {e}")
            return None
        finally:
            cursor.close()
    
    def get_quotes_ready_for_processing(self):
        """Get quotes that are ready to be processed (older than vote duration)."""
        cursor = self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cutoff_date = datetime.now() - timedelta(days=Config.VOTE_DURATION_DAYS)
            cursor.execute("""
                SELECT * FROM quotes 
                WHERE status = 'voting' AND submitted_at < %s
            """, (cutoff_date,))
            return cursor.fetchall()
        except psycopg2.Error as e:
            logger.error(f"Failed to get quotes ready for processing: {e}")
            return []
        finally:
            cursor.close()
    
    def process_quote(self, quote_id, approved=False):
        """Mark a quote as processed and optionally approve it."""
        cursor = self.connection.cursor()
        try:
            # Update quote status
            status = 'approved' if approved else 'rejected'
            cursor.execute("""
                UPDATE quotes 
                SET status = %s, processed_at = CURRENT_TIMESTAMP 
                WHERE id = %s
            """, (status, quote_id))
            
            # If approved, add to approved_quotes table
            if approved:
                cursor.execute("""
                    INSERT INTO approved_quotes (quote_id, content, author_name, final_score)
                    SELECT id, content, author_name, (upvotes - downvotes)
                    FROM quotes
                    WHERE id = %s
                """, (quote_id,))
            
            logger.info(f"Quote {quote_id} processed as {status}")
        except psycopg2.Error as e:
            logger.error(f"Failed to process quote: {e}")
            raise
        finally:
            cursor.close()
    
    def get_random_approved_quote(self):
        """Get a random approved quote."""
        cursor = self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cursor.execute("""
                SELECT content, author_name, approved_at 
                FROM approved_quotes 
                ORDER BY RANDOM() 
                LIMIT 1
            """)
            return cursor.fetchone()
        except psycopg2.Error as e:
            logger.error(f"Failed to get random quote: {e}")
            return None
        finally:
            cursor.close()
    
    def get_approved_quotes_count(self):
        """Get the count of approved quotes."""
        cursor = self.connection.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM approved_quotes")
            return cursor.fetchone()[0]
        except psycopg2.Error as e:
            logger.error(f"Failed to get approved quotes count: {e}")
            return 0
        finally:
            cursor.close()
    
    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")