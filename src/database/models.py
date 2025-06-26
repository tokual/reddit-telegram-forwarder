"""Database models and management for the Reddit Telegram Bot."""

import aiosqlite
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any


logger = logging.getLogger(__name__)


class Database:
    """Database manager for the bot."""
    
    def __init__(self, db_path: str):
        """Initialize database manager."""
        self.db_path = db_path
        self.db_dir = Path(db_path).parent
        self.db_dir.mkdir(parents=True, exist_ok=True)
    
    async def init_db(self):
        """Initialize database tables."""
        async with aiosqlite.connect(self.db_path) as db:
            # Create posts table for caching Reddit posts
            await db.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY,
                    subreddit TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    author TEXT NOT NULL,
                    created_utc INTEGER NOT NULL,
                    permalink TEXT NOT NULL,
                    media_type TEXT,
                    file_path TEXT,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    admin_id INTEGER,
                    UNIQUE(id)
                )
            """)
            
            # Create forwarder rules table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS forwarder_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER NOT NULL,
                    subreddit TEXT NOT NULL,
                    sort_type TEXT NOT NULL,
                    time_filter TEXT,
                    frequency_hours INTEGER NOT NULL,
                    target_channel TEXT NOT NULL,
                    active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_check TIMESTAMP,
                    UNIQUE(admin_id, subreddit, sort_type, target_channel)
                )
            """)
            
            # Create pending approvals table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS pending_approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT NOT NULL,
                    admin_id INTEGER NOT NULL,
                    rule_id INTEGER NOT NULL,
                    message_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(post_id) REFERENCES posts(id),
                    FOREIGN KEY(rule_id) REFERENCES forwarder_rules(id)
                )
            """)
            
            # Create approved posts table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS approved_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT NOT NULL,
                    admin_id INTEGER NOT NULL,
                    rule_id INTEGER NOT NULL,
                    target_channel TEXT NOT NULL,
                    forwarded_message_id INTEGER,
                    approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(post_id) REFERENCES posts(id),
                    FOREIGN KEY(rule_id) REFERENCES forwarder_rules(id)
                )
            """)
            
            await db.commit()
            logger.info("Database initialized successfully")
    
    async def add_post(self, post_data: Dict[str, Any]) -> bool:
        """Add a post to the database if it doesn't exist."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR IGNORE INTO posts 
                    (id, subreddit, title, url, author, created_utc, permalink, media_type, file_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    post_data['id'],
                    post_data['subreddit'],
                    post_data['title'],
                    post_data['url'],
                    post_data['author'],
                    post_data['created_utc'],
                    post_data['permalink'],
                    post_data.get('media_type'),
                    post_data.get('file_path')
                ))
                await db.commit()
                
                # Check if post was actually inserted (not a duplicate)
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM posts WHERE id = ? AND scraped_at > datetime('now', '-1 minute')",
                    (post_data['id'],)
                )
                count = await cursor.fetchone()
                return count[0] > 0
        except Exception as e:
            logger.error(f"Error adding post to database: {e}")
            return False
    
    async def post_exists(self, post_id: str) -> bool:
        """Check if a post exists in the database."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("SELECT 1 FROM posts WHERE id = ?", (post_id,))
                result = await cursor.fetchone()
                return result is not None
        except Exception as e:
            logger.error(f"Error checking post existence: {e}")
            return False
    
    async def add_forwarder_rule(self, admin_id: int, subreddit: str, sort_type: str, 
                                time_filter: Optional[str], frequency_hours: int, target_channel: str) -> int:
        """Add a new forwarder rule."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    INSERT OR REPLACE INTO forwarder_rules 
                    (admin_id, subreddit, sort_type, time_filter, frequency_hours, target_channel)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (admin_id, subreddit, sort_type, time_filter, frequency_hours, target_channel))
                await db.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding forwarder rule: {e}")
            return 0
    
    async def get_active_rules(self) -> List[Dict[str, Any]]:
        """Get all active forwarder rules."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT * FROM forwarder_rules 
                    WHERE active = 1 
                    ORDER BY created_at
                """)
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting active rules: {e}")
            return []
    
    async def update_rule_last_check(self, rule_id: int):
        """Update the last check timestamp for a rule."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE forwarder_rules 
                    SET last_check = CURRENT_TIMESTAMP 
                    WHERE id = ?
                """, (rule_id,))
                await db.commit()
        except Exception as e:
            logger.error(f"Error updating rule last check: {e}")
    
    async def add_pending_approval(self, post_id: str, admin_id: int, rule_id: int, message_id: int) -> int:
        """Add a pending approval entry."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    INSERT INTO pending_approvals (post_id, admin_id, rule_id, message_id)
                    VALUES (?, ?, ?, ?)
                """, (post_id, admin_id, rule_id, message_id))
                await db.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding pending approval: {e}")
            return 0
    
    async def get_pending_approval(self, message_id: int) -> Optional[Dict[str, Any]]:
        """Get pending approval by message ID."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT pa.*, p.*, fr.target_channel
                    FROM pending_approvals pa
                    JOIN posts p ON pa.post_id = p.id
                    JOIN forwarder_rules fr ON pa.rule_id = fr.id
                    WHERE pa.message_id = ?
                """, (message_id,))
                row = await cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting pending approval: {e}")
            return None
    
    async def approve_post(self, post_id: str, admin_id: int, rule_id: int, target_channel: str, 
                          forwarded_message_id: Optional[int] = None) -> bool:
        """Mark a post as approved and add to approved posts."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Add to approved posts
                await db.execute("""
                    INSERT INTO approved_posts (post_id, admin_id, rule_id, target_channel, forwarded_message_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (post_id, admin_id, rule_id, target_channel, forwarded_message_id))
                
                # Update post status
                await db.execute("""
                    UPDATE posts SET status = 'approved', admin_id = ? WHERE id = ?
                """, (admin_id, post_id))
                
                # Remove from pending approvals
                await db.execute("""
                    DELETE FROM pending_approvals WHERE post_id = ? AND admin_id = ? AND rule_id = ?
                """, (post_id, admin_id, rule_id))
                
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error approving post: {e}")
            return False
    
    async def reject_post(self, post_id: str, admin_id: int, rule_id: int) -> bool:
        """Mark a post as rejected."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Update post status
                await db.execute("""
                    UPDATE posts SET status = 'rejected', admin_id = ? WHERE id = ?
                """, (admin_id, post_id))
                
                # Remove from pending approvals
                await db.execute("""
                    DELETE FROM pending_approvals WHERE post_id = ? AND admin_id = ? AND rule_id = ?
                """, (post_id, admin_id, rule_id))
                
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error rejecting post: {e}")
            return False
    
    async def get_admin_rules(self, admin_id: int) -> List[Dict[str, Any]]:
        """Get all rules for a specific admin."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT * FROM forwarder_rules 
                    WHERE admin_id = ? 
                    ORDER BY created_at DESC
                """, (admin_id,))
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting admin rules: {e}")
            return []
    
    async def delete_rule(self, rule_id: int, admin_id: int) -> bool:
        """Delete a forwarder rule."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    DELETE FROM forwarder_rules 
                    WHERE id = ? AND admin_id = ?
                """, (rule_id, admin_id))
                await db.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting rule: {e}")
            return False
    
    async def get_rule_by_id(self, rule_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific rule by its ID."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT * FROM forwarder_rules WHERE id = ?
                """, (rule_id,))
                row = await cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting rule by ID {rule_id}: {e}")
            return None
