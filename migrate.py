from database import get_db, init_db
import sqlite3

def migrate_database():
    """Migrate database to add payment functionality"""
    try:
        db = get_db()
        
        # Add new columns if they don't exist
        try:
            db.execute('ALTER TABLE users ADD COLUMN mobile TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        try:
            db.execute('ALTER TABLE users ADD COLUMN upi_id TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        try:
            db.execute('ALTER TABLE transactions ADD COLUMN payment_method TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        try:
            db.execute('ALTER TABLE transactions ADD COLUMN receiver_identifier TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        try:
            db.execute('ALTER TABLE transactions ADD COLUMN sender_identifier TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Create contacts table
        db.execute('''
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                contact_user_id INTEGER NOT NULL,
                nickname TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (contact_user_id) REFERENCES users (id),
                UNIQUE(user_id, contact_user_id)
            )
        ''')
        
        # Create indexes
        db.execute('CREATE INDEX IF NOT EXISTS idx_users_mobile ON users(mobile)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_users_upi ON users(upi_id)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_contacts_user ON contacts(user_id)')
        
        db.commit()
        db.close()
        
        print("Database migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"Migration error: {e}")
        return False

if __name__ == '__main__':
    init_db()
    migrate_database()