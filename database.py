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
            # Quotes table with new schema
            cursor.execute("""
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
                )
            """)
            
            # Votes table with new schema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS votes (
                    id SERIAL PRIMARY KEY,
                    quote_id INTEGER REFERENCES quotes(id) ON DELETE CASCADE,
                    user_id VARCHAR(255) NOT NULL,
                    user_name VARCHAR(255) NOT NULL,
                    vote_type VARCHAR(10) NOT NULL CHECK (vote_type IN ('upvote', 'downvote')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(quote_id, user_id)
                )
            """)
            
            # Quote bot settings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS quote_bot_settings (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(255) UNIQUE NOT NULL,
                    value TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Apply schema migrations for backward compatibility
            self._apply_migrations(cursor)
            
            logger.info("Database tables created/verified successfully")
        except psycopg2.Error as e:
            logger.error(f"Failed to setup tables: {e}")
            raise
        finally:
            cursor.close()
    
    def _apply_migrations(self, cursor):
        """Apply database schema migrations for backward compatibility."""
        try:
            # Check if we're dealing with old schema by looking for BIGINT columns
            cursor.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'quotes' AND column_name IN ('author_id', 'message_id', 'channel_id')
            """)
            columns = cursor.fetchall()
            
            # Migration: Convert BIGINT columns to VARCHAR(255) if needed
            for column_name, data_type in columns:
                if data_type.upper() == 'BIGINT':
                    logger.info(f"Migrating column {column_name} from BIGINT to VARCHAR(255)")
                    cursor.execute(f"""
                        ALTER TABLE quotes 
                        ALTER COLUMN {column_name} TYPE VARCHAR(255) USING {column_name}::TEXT
                    """)
            
            # Migration: Add missing columns if they don't exist
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'quotes'
            """)
            existing_columns = {row[0] for row in cursor.fetchall()}
            
            required_columns = {
                'submitted_by_id': 'VARCHAR(255)',
                'submitted_by_name': 'VARCHAR(255)',
                'vote_message_id': 'VARCHAR(255)',
                'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
                'updated_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
            }
            
            for column_name, column_type in required_columns.items():
                if column_name not in existing_columns:
                    logger.info(f"Adding missing column: {column_name}")
                    cursor.execute(f"""
                        ALTER TABLE quotes 
                        ADD COLUMN IF NOT EXISTS {column_name} {column_type}
                    """)
            
            # Migration: Make channel_id and message_id NOT NULL if they were nullable
            # But first populate them with placeholder values for any NULL rows
            cursor.execute("""
                UPDATE quotes 
                SET channel_id = 'unknown', message_id = 'temp_' || id::text 
                WHERE channel_id IS NULL OR message_id IS NULL
            """)
            
            # Now make them NOT NULL
            cursor.execute("ALTER TABLE quotes ALTER COLUMN channel_id SET NOT NULL")
            cursor.execute("ALTER TABLE quotes ALTER COLUMN message_id SET NOT NULL")
            
            # Add UNIQUE constraint on message_id if it doesn't exist
            cursor.execute("""
                DO $$ BEGIN
                    ALTER TABLE quotes ADD CONSTRAINT quotes_message_id_unique UNIQUE (message_id);
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """)
            
            # Migration: Update votes table if needed
            cursor.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'votes' AND column_name = 'user_id'
            """)
            vote_columns = cursor.fetchall()
            
            if vote_columns and vote_columns[0][1].upper() == 'BIGINT':
                logger.info("Migrating votes.user_id from BIGINT to VARCHAR(255)")
                cursor.execute("""
                    ALTER TABLE votes 
                    ALTER COLUMN user_id TYPE VARCHAR(255) USING user_id::TEXT
                """)
            
            # Add user_name column to votes if missing
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'votes' AND column_name = 'user_name'
            """)
            if not cursor.fetchall():
                logger.info("Adding user_name column to votes table")
                cursor.execute("""
                    ALTER TABLE votes 
                    ADD COLUMN IF NOT EXISTS user_name VARCHAR(255) DEFAULT 'unknown'
                """)
                
                # Make it NOT NULL after adding default values
                cursor.execute("ALTER TABLE votes ALTER COLUMN user_name SET NOT NULL")
            
            logger.info("Schema migrations completed successfully")
            
        except psycopg2.Error as e:
            logger.error(f"Migration error (may be expected): {e}")
            # Migrations can fail if schema is already current, which is okay
    
    def add_quote(self, content, author_id, author_name, message_id, channel_id, submitted_by_id=None, submitted_by_name=None):
        """Add a new quote to the database with new schema."""
        cursor = self.connection.cursor()
        try:
            # Use author info as submitter if not provided separately
            if submitted_by_id is None:
                submitted_by_id = str(author_id)
            if submitted_by_name is None:
                submitted_by_name = author_name
            
            cursor.execute("""
                INSERT INTO quotes (
                    content, author_id, author_name, message_id, channel_id,
                    submitted_by_id, submitted_by_name, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
            """, (
                content, str(author_id), author_name, str(message_id), str(channel_id),
                str(submitted_by_id), submitted_by_name
            ))
            
            quote_id = cursor.fetchone()[0]
            logger.info(f"Quote {quote_id} added successfully")
            return quote_id
        except psycopg2.Error as e:
            logger.error(f"Failed to add quote: {e}")
            raise
        finally:
            cursor.close()
    
    def update_quote_message_info(self, quote_id, message_id, channel_id, vote_message_id=None):
        """Update quote with message and channel IDs and set status to voting."""
        cursor = self.connection.cursor()
        try:
            cursor.execute("""
                UPDATE quotes 
                SET message_id = %s, channel_id = %s, vote_message_id = %s, 
                    status = 'voting', updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (str(message_id), str(channel_id), str(vote_message_id) if vote_message_id else None, quote_id))
            logger.info(f"Quote {quote_id} message info updated and status set to voting")
        except psycopg2.Error as e:
            logger.error(f"Failed to update quote message info: {e}")
            raise
        finally:
            cursor.close()
    
    def add_vote(self, quote_id, user_id, user_name, vote_type):
        """Add or update a vote for a quote."""
        cursor = self.connection.cursor()
        try:
            # Validate vote_type
            if vote_type not in ['upvote', 'downvote']:
                raise ValueError(f"Invalid vote_type: {vote_type}. Must be 'upvote' or 'downvote'")
            
            # First, try to update existing vote
            cursor.execute("""
                INSERT INTO votes (quote_id, user_id, user_name, vote_type, created_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (quote_id, user_id)
                DO UPDATE SET vote_type = EXCLUDED.vote_type, created_at = CURRENT_TIMESTAMP
            """, (quote_id, str(user_id), user_name, vote_type))
            
            logger.info(f"Vote added for quote {quote_id} by user {user_id} ({user_name})")
        except psycopg2.Error as e:
            logger.error(f"Failed to add vote: {e}")
            raise
        finally:
            cursor.close()
    
    def get_vote_counts(self, quote_id):
        """Get vote counts for a quote."""
        cursor = self.connection.cursor()
        try:
            cursor.execute("""
                SELECT 
                    COUNT(CASE WHEN vote_type = 'upvote' THEN 1 END) as upvotes,
                    COUNT(CASE WHEN vote_type = 'downvote' THEN 1 END) as downvotes
                FROM votes 
                WHERE quote_id = %s
            """, (quote_id,))
            result = cursor.fetchone()
            return {'upvotes': result[0] or 0, 'downvotes': result[1] or 0}
        except psycopg2.Error as e:
            logger.error(f"Failed to get vote counts: {e}")
            return {'upvotes': 0, 'downvotes': 0}
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
                SELECT q.*, 
                       COUNT(CASE WHEN v.vote_type = 'upvote' THEN 1 END) as upvotes,
                       COUNT(CASE WHEN v.vote_type = 'downvote' THEN 1 END) as downvotes
                FROM quotes q
                LEFT JOIN votes v ON q.id = v.quote_id
                WHERE q.status = 'voting' AND q.submitted_at < %s
                GROUP BY q.id
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
                SET status = %s, updated_at = CURRENT_TIMESTAMP 
                WHERE id = %s
            """, (status, quote_id))
            
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
                SELECT content, author_name, updated_at as approved_at
                FROM quotes 
                WHERE status = 'approved'
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
            cursor.execute("SELECT COUNT(*) FROM quotes WHERE status = 'approved'")
            return cursor.fetchone()[0]
        except psycopg2.Error as e:
            logger.error(f"Failed to get approved quotes count: {e}")
            return 0
        finally:
            cursor.close()
    
    def quote_exists(self, content, author_id):
        """Check if a quote with the same content and author already exists."""
        cursor = self.connection.cursor()
        try:
            cursor.execute("""
                SELECT COUNT(*) FROM quotes 
                WHERE content = %s AND author_id = %s
            """, (content, str(author_id)))
            
            count = cursor.fetchone()[0]
            return count > 0
        except psycopg2.Error as e:
            logger.error(f"Failed to check quote existence: {e}")
            return False
        finally:
            cursor.close()
    
    def get_setting(self, key):
        """Get a setting value by key."""
        cursor = self.connection.cursor()
        try:
            cursor.execute("SELECT value FROM quote_bot_settings WHERE key = %s", (key,))
            result = cursor.fetchone()
            return result[0] if result else None
        except psycopg2.Error as e:
            logger.error(f"Failed to get setting {key}: {e}")
            return None
        finally:
            cursor.close()
    
    def set_setting(self, key, value):
        """Set a setting value."""
        cursor = self.connection.cursor()
        try:
            cursor.execute("""
                INSERT INTO quote_bot_settings (key, value, created_at, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (key)
                DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
            """, (key, value))
            logger.info(f"Setting {key} updated")
        except psycopg2.Error as e:
            logger.error(f"Failed to set setting {key}: {e}")
            raise
        finally:
            cursor.close()
    
    def quote_exists(self, content):
        """Check if a quote with the given content already exists."""
        cursor = self.connection.cursor()
        try:
            cursor.execute("SELECT id FROM quotes WHERE content = %s", (content,))
            result = cursor.fetchone()
            return result is not None
        except psycopg2.Error as e:
            logger.error(f"Failed to check if quote exists: {e}")
            return False
        finally:
            cursor.close()

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")
