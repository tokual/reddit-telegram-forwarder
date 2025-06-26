#!/usr/bin/env python3
"""
Database cleanup script for Reddit Telegram Forwarder Bot
Clears posts and approval data for fresh testing.
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config import Config
import aiosqlite


async def clear_database():
    """Clear posts and approval data from the database."""
    try:
        config = Config()
        
        async with aiosqlite.connect(config.database_path) as db:
            # Clear all posts and related data
            await db.execute("DELETE FROM pending_approvals")
            await db.execute("DELETE FROM approved_posts")
            await db.execute("DELETE FROM posts")
            
            # Reset rule last_check times so they will check again immediately
            await db.execute("UPDATE forwarder_rules SET last_check = NULL")
            
            await db.commit()
            
            print("✅ Database cleared successfully!")
            print("   - All posts removed")
            print("   - All pending approvals removed")
            print("   - All approved posts removed")
            print("   - Rule check times reset")
            
        # Clean up temp files
        import os
        import glob
        
        temp_dir = Path(config.temp_files_dir)
        if temp_dir.exists():
            temp_files = list(temp_dir.glob("*"))
            for temp_file in temp_files:
                if temp_file.is_file():
                    os.remove(temp_file)
            
            print(f"   - Cleaned up {len(temp_files)} temp files")
        
        print("\n🚀 Ready for fresh testing!")
        print("   Your rules are still active and will start checking for new posts immediately.")
        
    except Exception as e:
        print(f"❌ Error clearing database: {e}")
        return False
    
    return True


if __name__ == "__main__":
    success = asyncio.run(clear_database())
    sys.exit(0 if success else 1)
