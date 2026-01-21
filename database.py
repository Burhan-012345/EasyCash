import sqlite3
import os
import uuid
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

DATABASE_PATH = 'easycash.db'

def get_db():
    """Create database connection"""
    try:
        db = sqlite3.connect(DATABASE_PATH)
        db.row_factory = sqlite3.Row
        return db
    except sqlite3.Error as e:
        print(f"Database connection error: {e}")
        raise

def table_exists(db, table_name):
    """Check if a table exists in the database"""
    try:
        result = db.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'").fetchone()
        return result is not None
    except:
        return False

def column_exists(db, table_name, column_name):
    """Check if a column exists in a table"""
    try:
        db.execute(f'SELECT {column_name} FROM {table_name} LIMIT 1')
        return True
    except sqlite3.OperationalError:
        return False

def check_constraint_exists(db, table_name):
    """Check if CHECK constraint exists on type column"""
    try:
        cursor = db.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        create_stmt = cursor.fetchone()
        
        if create_stmt and create_stmt[0]:
            sql_statement = create_stmt[0].upper()
            return 'CHECK(TYPE IN' in sql_statement or "CHECK (TYPE IN" in sql_statement
        return False
    except:
        return False

def fix_transactions_table_constraint():
    """Fix the transactions table to allow send/receive types"""
    try:
        db = get_db()
        
        cursor = db.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='transactions'")
        create_stmt = cursor.fetchone()
        
        if create_stmt and create_stmt[0]:
            sql_statement = create_stmt[0]
            if "CHECK(type IN ('deposit', 'withdraw'))" in sql_statement or "CHECK(type IN ('deposit','withdraw'))" in sql_statement:
                print("Found old constraint, fixing transactions table...")
                
                db.execute('''
                    CREATE TABLE transactions_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        phone TEXT NOT NULL,
                        transaction_id TEXT UNIQUE NOT NULL,
                        type TEXT NOT NULL CHECK(type IN ('deposit', 'withdraw', 'send', 'receive')),
                        amount REAL NOT NULL,
                        balance_after REAL NOT NULL,
                        date_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (phone) REFERENCES users (phone)
                    )
                ''')
                
                db.execute('''
                    INSERT INTO transactions_new 
                    (id, phone, transaction_id, type, amount, balance_after, date_time)
                    SELECT id, phone, transaction_id, type, amount, balance_after, date_time
                    FROM transactions
                ''')
                
                db.execute('DROP TABLE transactions')
                db.execute('ALTER TABLE transactions_new RENAME TO transactions')
                
                print("✓ Fixed transactions table constraint")
                
                db.execute('CREATE INDEX IF NOT EXISTS idx_transactions_phone ON transactions(phone)')
                db.execute('CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date_time)')
        
        db.commit()
        db.close()
        return True
        
    except Exception as e:
        print(f"Error fixing transactions constraint: {e}")
        db.rollback()
        db.close()
        return False

def init_db():
    """Initialize database with schema - handles migration safely"""
    try:
        db = get_db()
        
        print("Initializing database with phone-based authentication...")
        
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE NOT NULL,
                username TEXT,
                pin_hash TEXT NOT NULL,
                balance REAL DEFAULT 0.0,
                upi_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("✓ Created users table with phone as primary identifier")
        
        old_table = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='old_users'").fetchone()
        if not old_table:
            try:
                result = db.execute("PRAGMA table_info(users)").fetchall()
                columns = [col[1] for col in result]
                
                if 'phone' not in columns and 'username' in columns:
                    print("Migrating from old username-based system to phone-based system...")
                    
                    db.execute('ALTER TABLE users RENAME TO old_users')
                    
                    db.execute('''
                        CREATE TABLE users (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            phone TEXT UNIQUE NOT NULL,
                            username TEXT,
                            pin_hash TEXT NOT NULL,
                            balance REAL DEFAULT 0.0,
                            upi_id TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    
                    print("✓ Created new users table structure")
                    print("Note: Old users need manual migration to phone-based system")
                    
            except Exception as e:
                print(f"Migration check error: {e}")
        
        db.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                transaction_id TEXT UNIQUE NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('deposit', 'withdraw', 'send', 'receive')),
                amount REAL NOT NULL,
                balance_after REAL NOT NULL,
                date_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (phone) REFERENCES users (phone)
            )
        ''')
        print("✓ Created transactions table")
        
        if not column_exists(db, 'transactions', 'payment_method'):
            try:
                db.execute('ALTER TABLE transactions ADD COLUMN payment_method TEXT')
                print("✓ Added payment_method column to transactions table")
            except sqlite3.OperationalError as e:
                print(f"Could not add payment_method column: {e}")
        
        if not column_exists(db, 'transactions', 'receiver_identifier'):
            try:
                db.execute('ALTER TABLE transactions ADD COLUMN receiver_identifier TEXT')
                print("✓ Added receiver_identifier column to transactions table")
            except sqlite3.OperationalError as e:
                print(f"Could not add receiver_identifier column: {e}")
        
        if not column_exists(db, 'transactions', 'sender_identifier'):
            try:
                db.execute('ALTER TABLE transactions ADD COLUMN sender_identifier TEXT')
                print("✓ Added sender_identifier column to transactions table")
            except sqlite3.OperationalError as e:
                print(f"Could not add sender_identifier column: {e}")
        
        db.execute('''
            CREATE TABLE IF NOT EXISTS pin_attempts (
                phone TEXT PRIMARY KEY,
                attempts INTEGER DEFAULT 0,
                last_attempt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("✓ Created pin_attempts table")
        
        db.execute('''
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_phone TEXT NOT NULL,
                contact_phone TEXT NOT NULL,
                nickname TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_phone) REFERENCES users (phone),
                FOREIGN KEY (contact_phone) REFERENCES users (phone),
                UNIQUE(user_phone, contact_phone)
            )
        ''')
        print("✓ Created contacts table")
        
        try:
            db.execute('CREATE INDEX IF NOT EXISTS idx_transactions_phone ON transactions(phone)')
            print("✓ Created transactions phone index")
        except:
            pass
        
        try:
            db.execute('CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date_time)')
            print("✓ Created transactions date index")
        except:
            pass
        
        try:
            db.execute('CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone)')
            print("✓ Created users phone index")
        except:
            pass
        
        try:
            db.execute('CREATE INDEX IF NOT EXISTS idx_users_upi ON users(upi_id)')
            print("✓ Created users UPI index")
        except:
            pass
        
        if table_exists(db, 'contacts'):
            try:
                db.execute('CREATE INDEX IF NOT EXISTS idx_contacts_user ON contacts(user_phone)')
                print("✓ Created contacts index")
            except:
                pass
        
        db.commit()
        db.close()
        
        fix_transactions_table_constraint()
        
        print("Database initialized successfully with phone-based authentication!")
        return True
        
    except sqlite3.Error as e:
        print(f"Error initializing database: {e}")
        if 'db' in locals():
            db.rollback()
            db.close()
        raise

def create_user_with_phone(username, phone, pin):
    """Create a new user with phone number"""
    try:
        hashed_pin = generate_password_hash(pin)
        db = get_db()
        
        existing = db.execute('SELECT phone FROM users WHERE phone = ?', (phone,)).fetchone()
        if existing:
            db.close()
            return False
        
        if not username:
            username = f"User_{phone[-4:]}"
        
        upi_id = f"{phone}@easycash"
        
        db.execute('INSERT INTO users (phone, username, pin_hash, balance, upi_id) VALUES (?, ?, ?, ?, ?)',
                   (phone, username, hashed_pin, 0.0, upi_id))
        db.commit()
        db.close()
        return True
        
    except sqlite3.IntegrityError as e:
        print(f"Integrity error creating user: {e}")
        return False
    except Exception as e:
        print(f"Error creating user with phone: {e}")
        return False

def user_exists_by_phone(phone):
    """Check if phone number exists"""
    try:
        db = get_db()
        user = db.execute('SELECT phone FROM users WHERE phone = ?', (phone,)).fetchone()
        db.close()
        return user is not None
    except Exception as e:
        print(f"Error checking phone existence: {e}")
        return False

def verify_user_by_phone(phone, pin):
    """Verify user by phone number"""
    try:
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE phone = ?', (phone,)).fetchone()
        db.close()
        
        if user and check_password_hash(user['pin_hash'], pin):
            return dict(user)
        return None
        
    except Exception as e:
        print(f"Error verifying user by phone: {e}")
        return None

def get_user_by_phone(phone):
    """Get user details by phone"""
    try:
        db = get_db()
        user = db.execute('''
            SELECT 
                id,
                phone,
                username,
                balance,
                upi_id,
                created_at
            FROM users 
            WHERE phone = ?
        ''', (phone,)).fetchone()
        
        db.close()
        
        if user:
            return {
                'id': user['id'],
                'phone': user['phone'],
                'username': user['username'],
                'balance': float(user['balance']) if user['balance'] is not None else 0.0,
                'upi_id': user['upi_id'],
                'created_at': user['created_at']
            }
        return None
    except Exception as e:
        print(f"Error getting user by phone: {e}")
        return None

def get_pin_attempts_by_phone(phone):
    """Get PIN attempt count by phone"""
    try:
        db = get_db()
        
        result = db.execute('SELECT attempts FROM pin_attempts WHERE phone = ?', 
                           (phone,)).fetchone()
        db.close()
        
        if result:
            return int(result['attempts'])
        return 0
    except Exception as e:
        print(f"Error getting PIN attempts by phone: {e}")
        return 0

def add_pin_attempt_by_phone(phone):
    """Record PIN attempt by phone"""
    try:
        db = get_db()
        
        existing = db.execute('SELECT attempts FROM pin_attempts WHERE phone = ?', 
                             (phone,)).fetchone()
        
        if existing:
            db.execute('UPDATE pin_attempts SET attempts = attempts + 1, last_attempt = CURRENT_TIMESTAMP WHERE phone = ?', 
                      (phone,))
        else:
            db.execute('INSERT INTO pin_attempts (phone, attempts) VALUES (?, 1)', 
                      (phone,))
        
        db.commit()
        
        attempts = db.execute('SELECT attempts FROM pin_attempts WHERE phone = ?', 
                             (phone,)).fetchone()
        
        db.close()
        
        if attempts:
            return int(attempts['attempts'])
        return 1
        
    except Exception as e:
        print(f"Error adding PIN attempt by phone: {e}")
        return 1

def reset_pin_attempts_by_phone(phone):
    """Reset PIN attempt counter by phone"""
    try:
        db = get_db()
        db.execute('DELETE FROM pin_attempts WHERE phone = ?', (phone,))
        db.commit()
        db.close()
        return True
    except Exception as e:
        print(f"Error resetting PIN attempts by phone: {e}")
        return False

def update_balance(phone, amount):
    """Update user balance"""
    try:
        db = get_db()
        
        db.execute('UPDATE users SET balance = balance + ? WHERE phone = ?', 
                   (amount, phone))
        db.commit()
        
        new_balance = db.execute('SELECT balance FROM users WHERE phone = ?', 
                                (phone,)).fetchone()
        db.close()
        
        if new_balance:
            return float(new_balance['balance'])
        return 0.0
        
    except Exception as e:
        print(f"Error updating balance: {e}")
        raise

def add_transaction(phone, transaction_type, amount, balance_after, payment_method=None, receiver_identifier=None, sender_identifier=None):
    """Add transaction record"""
    try:
        db = get_db()
        
        transaction_id = str(uuid.uuid4())
        
        valid_types = ['deposit', 'withdraw', 'send', 'receive']
        if transaction_type not in valid_types:
            transaction_type = 'send' if transaction_type.startswith('send') else 'receive' if transaction_type.startswith('receive') else transaction_type
        
        db.execute('''
            INSERT INTO transactions 
            (phone, transaction_id, type, amount, balance_after, 
             payment_method, receiver_identifier, sender_identifier)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (phone, transaction_id, transaction_type, float(amount), float(balance_after), 
              payment_method, receiver_identifier, sender_identifier))
        
        db.commit()
        db.close()
        return transaction_id
        
    except sqlite3.IntegrityError as e:
        if 'CHECK' in str(e):
            print("Constraint error, attempting to fix...")
            fix_transactions_table_constraint()
            return add_transaction(phone, transaction_type, amount, balance_after, 
                                 payment_method, receiver_identifier, sender_identifier)
        else:
            raise
    except Exception as e:
        print(f"Error adding transaction: {e}")
        raise

def get_transactions(phone, limit=10, offset=0):
    """Get user transactions"""
    try:
        db = get_db()
        
        cursor = db.execute('''
            SELECT 
                id,
                transaction_id,
                phone,
                type,
                amount,
                balance_after,
                datetime(date_time) as date_time,
                payment_method,
                receiver_identifier,
                sender_identifier
            FROM transactions 
            WHERE phone = ? 
            ORDER BY date_time DESC 
            LIMIT ? OFFSET ?
        ''', (phone, limit, offset))
        
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        db.close()
        
        result = []
        for row in rows:
            transaction = {}
            for i, col in enumerate(columns):
                if row[i] is None:
                    transaction[col] = None
                elif col in ['amount', 'balance_after']:
                    transaction[col] = float(row[i])
                else:
                    transaction[col] = row[i]
            result.append(transaction)
        
        return result
        
    except Exception as e:
        print(f"Error getting transactions: {e}")
        return []

def get_user_balance_by_phone(phone):
    """Get only user balance"""
    try:
        db = get_db()
        result = db.execute('SELECT balance FROM users WHERE phone = ?', (phone,)).fetchone()
        db.close()
        
        if result and result['balance'] is not None:
            return float(result['balance'])
        return 0.0
        
    except Exception as e:
        print(f"Error getting user balance: {e}")
        return 0.0

def get_transaction_stats(phone):
    """Get transaction statistics for a user"""
    try:
        db = get_db()
        
        deposits = db.execute('''
            SELECT COALESCE(SUM(amount), 0) as total_deposits 
            FROM transactions 
            WHERE phone = ? AND type = 'deposit'
        ''', (phone,)).fetchone()
        
        withdrawals = db.execute('''
            SELECT COALESCE(SUM(amount), 0) as total_withdrawals 
            FROM transactions 
            WHERE phone = ? AND type = 'withdraw'
        ''', (phone,)).fetchone()
        
        sent = db.execute('''
            SELECT COALESCE(SUM(amount), 0) as total_sent 
            FROM transactions 
            WHERE phone = ? AND type = 'send'
        ''', (phone,)).fetchone()
        
        received = db.execute('''
            SELECT COALESCE(SUM(amount), 0) as total_received 
            FROM transactions 
            WHERE phone = ? AND type = 'receive'
        ''', (phone,)).fetchone()
        
        count = db.execute('''
            SELECT COUNT(*) as count 
            FROM transactions 
            WHERE phone = ?
        ''', (phone,)).fetchone()
        
        latest = db.execute('''
            SELECT MAX(date_time) as latest_date 
            FROM transactions 
            WHERE phone = ?
        ''', (phone,)).fetchone()
        
        db.close()
        
        return {
            'total_deposits': float(deposits['total_deposits']),
            'total_withdrawals': float(withdrawals['total_withdrawals']),
            'total_sent': float(sent['total_sent']),
            'total_received': float(received['total_received']),
            'total_transactions': int(count['count']),
            'net_flow': float(deposits['total_deposits']) - float(withdrawals['total_withdrawals']) - float(sent['total_sent']) + float(received['total_received']),
            'latest_transaction': latest['latest_date'] if latest['latest_date'] else 'No transactions yet'
        }
        
    except Exception as e:
        print(f"Error getting transaction stats: {e}")
        return {
            'total_deposits': 0.0,
            'total_withdrawals': 0.0,
            'total_sent': 0.0,
            'total_received': 0.0,
            'total_transactions': 0,
            'net_flow': 0.0,
            'latest_transaction': 'No transactions yet'
        }

def get_recent_transactions(phone, limit=5):
    """Get recent transactions for dashboard"""
    return get_transactions(phone, limit=limit)

def get_filtered_transactions(phone, transaction_type=None, start_date=None, end_date=None, limit=50):
    """Get filtered transactions"""
    try:
        db = get_db()
        
        query = '''
            SELECT 
                id,
                transaction_id,
                phone,
                type,
                amount,
                balance_after,
                datetime(date_time) as date_time,
                payment_method,
                receiver_identifier,
                sender_identifier
            FROM transactions 
            WHERE phone = ?
        '''
        params = [phone]
        
        if transaction_type and transaction_type != 'all':
            query += ' AND type = ?'
            params.append(transaction_type)
        
        if start_date:
            query += ' AND date(date_time) >= date(?)'
            params.append(start_date)
        
        if end_date:
            query += ' AND date(date_time) <= date(?)'
            params.append(end_date)
        
        query += ' ORDER BY date_time DESC LIMIT ?'
        params.append(limit)
        
        cursor = db.execute(query, params)
        
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        db.close()
        
        result = []
        for row in rows:
            transaction = {}
            for i, col in enumerate(columns):
                if row[i] is None:
                    transaction[col] = None
                elif col in ['amount', 'balance_after']:
                    transaction[col] = float(row[i])
                else:
                    transaction[col] = row[i]
            result.append(transaction)
        
        return result
        
    except Exception as e:
        print(f"Error getting filtered transactions: {e}")
        return []

def get_transaction_count(phone):
    """Get total number of transactions for a user"""
    try:
        db = get_db()
        result = db.execute('SELECT COUNT(*) as count FROM transactions WHERE phone = ?', 
                           (phone,)).fetchone()
        db.close()
        
        if result:
            return int(result['count'])
        return 0
        
    except Exception as e:
        print(f"Error getting transaction count: {e}")
        return 0

def get_transaction_by_id(transaction_id):
    """Get a specific transaction by ID"""
    try:
        db = get_db()
        
        transaction = db.execute('''
            SELECT 
                id,
                transaction_id,
                phone,
                type,
                amount,
                balance_after,
                datetime(date_time) as date_time,
                payment_method,
                receiver_identifier,
                sender_identifier
            FROM transactions 
            WHERE transaction_id = ?
        ''', (transaction_id,)).fetchone()
        
        db.close()
        
        if transaction:
            trans_dict = {
                'id': transaction['id'],
                'transaction_id': transaction['transaction_id'],
                'phone': transaction['phone'],
                'type': transaction['type'],
                'amount': float(transaction['amount']) if transaction['amount'] is not None else 0.0,
                'balance_after': float(transaction['balance_after']) if transaction['balance_after'] is not None else 0.0,
                'date_time': transaction['date_time'],
                'payment_method': transaction['payment_method'],
                'receiver_identifier': transaction['receiver_identifier'],
                'sender_identifier': transaction['sender_identifier']
            }
            return trans_dict
            
        return None
        
    except Exception as e:
        print(f"Error getting transaction by ID: {e}")
        return None

def get_user_by_mobile(mobile):
    """Get user by mobile number"""
    try:
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE phone = ?', (mobile,)).fetchone()
        db.close()
        
        if user:
            return dict(user)
        return None
    except Exception as e:
        print(f"Error getting user by mobile: {e}")
        return None

def get_user_by_upi(upi_id):
    """Get user by UPI ID"""
    try:
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE upi_id = ?', (upi_id,)).fetchone()
        db.close()
        
        if user:
            return dict(user)
        return None
    except Exception as e:
        print(f"Error getting user by UPI: {e}")
        return None

def get_contacts(phone):
    """Get user's saved contacts"""
    try:
        db = get_db()
        
        contacts = db.execute('''
            SELECT 
                u.phone,
                u.username,
                u.upi_id,
                c.nickname
            FROM contacts c
            JOIN users u ON c.contact_phone = u.phone
            WHERE c.user_phone = ?
            ORDER BY c.created_at DESC
        ''', (phone,)).fetchall()
        
        db.close()
        
        result = []
        for contact in contacts:
            result.append({
                'phone': contact['phone'],
                'username': contact['username'],
                'upi_id': contact['upi_id'],
                'nickname': contact['nickname']
            })
        
        return result
        
    except Exception as e:
        print(f"Error getting contacts: {e}")
        return []

def add_contact(user_phone, contact_phone, nickname=None):
    """Add a user to contacts"""
    try:
        db = get_db()
        
        user = db.execute('SELECT phone FROM users WHERE phone = ?', (user_phone,)).fetchone()
        contact_user = db.execute('SELECT phone FROM users WHERE phone = ?', (contact_phone,)).fetchone()
        
        if not user or not contact_user:
            return False
        
        existing = db.execute('''
            SELECT id FROM contacts 
            WHERE user_phone = ? AND contact_phone = ?
        ''', (user_phone, contact_phone)).fetchone()
        
        if existing:
            return False
        
        db.execute('''
            INSERT INTO contacts (user_phone, contact_phone, nickname)
            VALUES (?, ?, ?)
        ''', (user_phone, contact_phone, nickname))
        
        db.commit()
        db.close()
        return True
        
    except Exception as e:
        print(f"Error adding contact: {e}")
        return False

def remove_contact(user_phone, contact_phone):
    """Remove a user from contacts"""
    try:
        db = get_db()
        
        db.execute('''
            DELETE FROM contacts 
            WHERE user_phone = ? AND contact_phone = ?
        ''', (user_phone, contact_phone))
        
        db.commit()
        db.close()
        return True
        
    except Exception as e:
        print(f"Error removing contact: {e}")
        return False

def send_payment(sender_phone, receiver_identifier, amount, payment_method, description=""):
    """Send payment to another user"""
    try:
        db = get_db()
        
        sender = db.execute('SELECT * FROM users WHERE phone = ?', (sender_phone,)).fetchone()
        if not sender:
            raise Exception("Sender not found")
        
        if float(sender['balance']) < float(amount):
            raise Exception("Insufficient balance")
        
        receiver = None
        
        if payment_method == 'mobile':
            receiver = db.execute('SELECT * FROM users WHERE phone = ?', (receiver_identifier,)).fetchone()
        elif payment_method == 'upi':
            receiver = db.execute('SELECT * FROM users WHERE upi_id = ?', (receiver_identifier,)).fetchone()
        elif payment_method == 'contact':
            receiver = db.execute('SELECT * FROM users WHERE phone = ?', (receiver_identifier,)).fetchone()
        
        db.execute('BEGIN TRANSACTION')
        
        new_sender_balance = float(sender['balance']) - float(amount)
        db.execute('UPDATE users SET balance = ? WHERE phone = ?', 
                   (new_sender_balance, sender_phone))
        
        receiver_phone = None
        
        if receiver and payment_method != 'bank':
            new_receiver_balance = float(receiver['balance']) + float(amount)
            db.execute('UPDATE users SET balance = ? WHERE phone = ?', 
                       (new_receiver_balance, receiver['phone']))
            receiver_phone = receiver['phone']
        
        transaction_id = str(uuid.uuid4())
        
        db.execute('''
            INSERT INTO transactions 
            (phone, transaction_id, type, amount, balance_after, payment_method, receiver_identifier)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            sender_phone,
            transaction_id,
            'send',
            float(amount),
            new_sender_balance,
            payment_method,
            receiver_identifier
        ))
        
        if receiver and payment_method != 'bank':
            receiver_transaction_id = str(uuid.uuid4())
            db.execute('''
                INSERT INTO transactions 
                (phone, transaction_id, type, amount, balance_after, payment_method, sender_identifier)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                receiver['phone'],
                receiver_transaction_id,
                'receive',
                float(amount),
                new_receiver_balance,
                payment_method,
                sender_phone
            ))
        
        db.commit()
        db.close()
        
        return {
            'transaction_id': transaction_id,
            'sender_balance': new_sender_balance,
            'receiver_found': receiver is not None,
            'receiver_phone': receiver_phone
        }
        
    except Exception as e:
        print(f"Error sending payment: {e}")
        db.rollback()
        db.close()
        raise

def get_payment_transactions(phone):
    """Get all payment transactions for a user"""
    try:
        db = get_db()
        
        sent_transactions = db.execute('''
            SELECT 
                transaction_id,
                'sent' as direction,
                type,
                amount,
                balance_after,
                date_time,
                payment_method,
                receiver_identifier
            FROM transactions 
            WHERE phone = ? AND type = 'send'
            ORDER BY date_time DESC
        ''', (phone,)).fetchall()
        
        received_transactions = db.execute('''
            SELECT 
                transaction_id,
                'received' as direction,
                type,
                amount,
                balance_after,
                date_time,
                payment_method,
                sender_identifier
            FROM transactions 
            WHERE phone = ? AND type = 'receive'
            ORDER BY date_time DESC
        ''', (phone,)).fetchall()
        
        db.close()
        
        all_transactions = []
        
        for trans in sent_transactions:
            all_transactions.append({
                'transaction_id': trans['transaction_id'],
                'direction': 'sent',
                'type': trans['type'],
                'amount': float(trans['amount']),
                'balance_after': float(trans['balance_after']),
                'date_time': trans['date_time'],
                'payment_method': trans['payment_method'],
                'receiver_identifier': trans['receiver_identifier']
            })
        
        for trans in received_transactions:
            all_transactions.append({
                'transaction_id': trans['transaction_id'],
                'direction': 'received',
                'type': trans['type'],
                'amount': float(trans['amount']),
                'balance_after': float(trans['balance_after']),
                'date_time': trans['date_time'],
                'payment_method': trans['payment_method'],
                'sender_identifier': trans['sender_identifier']
            })
        
        all_transactions.sort(key=lambda x: x['date_time'], reverse=True)
        
        return all_transactions
        
    except Exception as e:
        print(f"Error getting payment transactions: {e}")
        return []

def search_users(search_term):
    """Search users by username, phone, or UPI ID"""
    try:
        db = get_db()
        
        users = db.execute('''
            SELECT 
                phone,
                username,
                upi_id,
                balance
            FROM users 
            WHERE username LIKE ? 
               OR phone LIKE ?
               OR upi_id LIKE ?
            LIMIT 20
        ''', (f'%{search_term}%', f'%{search_term}%', f'%{search_term}%')).fetchall()
        
        db.close()
        
        result = []
        for user in users:
            result.append({
                'phone': user['phone'],
                'username': user['username'],
                'upi_id': user['upi_id']
            })
        
        return result
        
    except Exception as e:
        print(f"Error searching users: {e}")
        return []

def get_sent_to_contacts(phone, limit=10):
    """Get all people the user has sent money to - FIXED VERSION"""
    try:
        db = get_db()
        
        contacts = db.execute('''
            SELECT 
                u.phone,
                u.username,
                u.upi_id,
                COUNT(t.id) as transaction_count,
                SUM(t.amount) as total_amount,
                MAX(t.date_time) as last_transaction,
                c.nickname,
                t.receiver_identifier
            FROM transactions t
            LEFT JOIN users u ON (
                t.receiver_identifier = u.phone OR 
                t.receiver_identifier = u.upi_id
            )
            LEFT JOIN contacts c ON (
                c.user_phone = ? AND 
                (c.contact_phone = u.phone OR (u.phone IS NULL AND c.contact_phone = t.receiver_identifier))
            )
            WHERE t.phone = ? 
            AND t.type = 'send'
            AND t.receiver_identifier IS NOT NULL
            GROUP BY t.receiver_identifier
            ORDER BY MAX(t.date_time) DESC
            LIMIT ?
        ''', (phone, phone, limit)).fetchall()
        
        db.close()
        
        result = []
        for contact in contacts:
            contact_dict = {
                'phone': contact['phone'],
                'username': contact['username'],
                'upi_id': contact['upi_id'],
                'transaction_count': contact['transaction_count'],
                'total_amount': float(contact['total_amount']) if contact['total_amount'] else 0.0,
                'last_transaction': contact['last_transaction'],
                'nickname': contact['nickname'],
                'identifier': contact['receiver_identifier']
            }
            
            if not contact['phone'] and not contact['username']:
                identifier = contact['receiver_identifier']
                if identifier and len(identifier) == 10 and identifier.isdigit():
                    contact_dict['username'] = f"User {identifier[-4:]}"
                    contact_dict['phone'] = identifier
                elif '@' in str(identifier):
                    contact_dict['username'] = identifier.split('@')[0]
                else:
                    contact_dict['username'] = identifier
            
            result.append(contact_dict)
        
        return result if result else []
        
    except Exception as e:
        print(f"Error getting sent to contacts: {e}")
        return []

def get_received_from_contacts(phone, limit=10):
    """Get all people the user has received money from - FIXED VERSION"""
    try:
        db = get_db()
        
        contacts = db.execute('''
            SELECT 
                u.phone,
                u.username,
                u.upi_id,
                COUNT(t.id) as transaction_count,
                SUM(t.amount) as total_amount,
                MAX(t.date_time) as last_transaction,
                c.nickname,
                t.sender_identifier
            FROM transactions t
            LEFT JOIN users u ON (
                t.sender_identifier = u.phone OR 
                t.sender_identifier = u.upi_id
            )
            LEFT JOIN contacts c ON (
                c.user_phone = ? AND 
                (c.contact_phone = u.phone OR (u.phone IS NULL AND c.contact_phone = t.sender_identifier))
            )
            WHERE t.phone = ? 
            AND t.type = 'receive'
            AND t.sender_identifier IS NOT NULL
            GROUP BY t.sender_identifier
            ORDER BY MAX(t.date_time) DESC
            LIMIT ?
        ''', (phone, phone, limit)).fetchall()
        
        db.close()
        
        result = []
        for contact in contacts:
            contact_dict = {
                'phone': contact['phone'],
                'username': contact['username'],
                'upi_id': contact['upi_id'],
                'transaction_count': contact['transaction_count'],
                'total_amount': float(contact['total_amount']) if contact['total_amount'] else 0.0,
                'last_transaction': contact['last_transaction'],
                'nickname': contact['nickname'],
                'identifier': contact['sender_identifier']
            }
            
            if not contact['phone'] and not contact['username']:
                identifier = contact['sender_identifier']
                if identifier and len(identifier) == 10 and identifier.isdigit():
                    contact_dict['username'] = f"User {identifier[-4:]}"
                    contact_dict['phone'] = identifier
                elif '@' in str(identifier):
                    contact_dict['username'] = identifier.split('@')[0]
                else:
                    contact_dict['username'] = identifier
            
            result.append(contact_dict)
        
        return result if result else []
        
    except Exception as e:
        print(f"Error getting received from contacts: {e}")
        return []

def get_person_transaction_history(user_phone, contact_identifier):
    """Get all transactions between user and a specific person"""
    try:
        db = get_db()
        
        contact_user = None
        if contact_identifier and '@' in contact_identifier:
            contact_user = db.execute('SELECT * FROM users WHERE upi_id = ?', 
                                     (contact_identifier,)).fetchone()
        elif contact_identifier and len(contact_identifier) == 10 and contact_identifier.isdigit():
            contact_user = db.execute('SELECT * FROM users WHERE phone = ?', 
                                     (contact_identifier,)).fetchone()
        
        contact_phone = contact_user['phone'] if contact_user else contact_identifier
        
        sent_by_user = db.execute('''
            SELECT 
                t.transaction_id,
                'sent_by_me' as transaction_type,
                t.type,
                t.amount,
                t.balance_after as my_balance_after,
                NULL as their_balance_after,
                t.date_time,
                t.payment_method,
                t.receiver_identifier,
                'You' as sender_name,
                u2.username as receiver_name,
                u2.phone as receiver_phone
            FROM transactions t
            LEFT JOIN users u2 ON (t.receiver_identifier = u2.phone OR t.receiver_identifier = u2.upi_id)
            WHERE t.phone = ? 
            AND t.type = 'send'
            AND (
                t.receiver_identifier = ?
                OR (t.receiver_identifier = ? AND ? LIKE '%@%')
                OR u2.phone = ?
            )
        ''', (user_phone, contact_identifier, contact_identifier, contact_identifier, contact_phone)).fetchall()
        
        received_by_user = db.execute('''
            SELECT 
                t.transaction_id,
                'received_by_me' as transaction_type,
                t.type,
                t.amount,
                t.balance_after as my_balance_after,
                NULL as their_balance_after,
                t.date_time,
                t.payment_method,
                t.sender_identifier,
                u2.username as sender_name,
                'You' as receiver_name,
                u2.phone as sender_phone
            FROM transactions t
            LEFT JOIN users u2 ON (t.sender_identifier = u2.phone OR t.sender_identifier = u2.upi_id)
            WHERE t.phone = ? 
            AND t.type = 'receive'
            AND (
                t.sender_identifier = ?
                OR (t.sender_identifier = ? AND ? LIKE '%@%')
                OR u2.phone = ?
            )
        ''', (user_phone, contact_identifier, contact_identifier, contact_identifier, contact_phone)).fetchall()
        
        sent_by_contact = db.execute('''
            SELECT 
                t.transaction_id,
                'sent_by_them' as transaction_type,
                t.type,
                t.amount,
                NULL as my_balance_after,
                t.balance_after as their_balance_after,
                t.date_time,
                t.payment_method,
                t.receiver_identifier,
                u2.username as sender_name,
                'You' as receiver_name,
                u2.phone as sender_phone
            FROM transactions t
            LEFT JOIN users u2 ON t.phone = u2.phone
            WHERE t.type = 'send'
            AND t.receiver_identifier = ?
            AND u2.phone = ?
        ''', (user_phone, contact_phone)).fetchall()
        
        received_by_contact = db.execute('''
            SELECT 
                t.transaction_id,
                'received_by_them' as transaction_type,
                t.type,
                t.amount,
                NULL as my_balance_after,
                t.balance_after as their_balance_after,
                t.date_time,
                t.payment_method,
                t.sender_identifier,
                'You' as sender_name,
                u2.username as receiver_name,
                u2.phone as receiver_phone
            FROM transactions t
            LEFT JOIN users u2 ON t.phone = u2.phone
            WHERE t.type = 'receive'
            AND t.sender_identifier = ?
            AND u2.phone = ?
        ''', (user_phone, contact_phone)).fetchall()
        
        db.close()
        
        all_transactions = []
        
        def row_to_dict(row):
            if row:
                d = dict(row)
                d['amount'] = float(d['amount']) if d['amount'] else 0.0
                d['my_balance_after'] = float(d['my_balance_after']) if d['my_balance_after'] else None
                d['their_balance_after'] = float(d['their_balance_after']) if d['their_balance_after'] else None
                return d
            return None
        
        for trans in sent_by_user:
            all_transactions.append(row_to_dict(trans))
        for trans in received_by_user:
            all_transactions.append(row_to_dict(trans))
        for trans in sent_by_contact:
            all_transactions.append(row_to_dict(trans))
        for trans in received_by_contact:
            all_transactions.append(row_to_dict(trans))
        
        all_transactions.sort(key=lambda x: x['date_time'] if x['date_time'] else '', reverse=True)
        
        contact_info = None
        if contact_user:
            contact_info = {
                'phone': contact_user['phone'],
                'username': contact_user['username'],
                'upi_id': contact_user['upi_id'],
                'exists_in_system': True
            }
        else:
            contact_info = {
                'identifier': contact_identifier,
                'exists_in_system': False
            }
        
        total_sent_by_me = sum(t['amount'] for t in all_transactions if t['transaction_type'] == 'sent_by_me')
        total_received_by_me = sum(t['amount'] for t in all_transactions if t['transaction_type'] == 'received_by_me')
        total_sent_by_them = sum(t['amount'] for t in all_transactions if t['transaction_type'] == 'sent_by_them')
        total_received_by_them = sum(t['amount'] for t in all_transactions if t['transaction_type'] == 'received_by_them')
        
        net_balance = total_received_by_me - total_sent_by_me
        
        return {
            'contact_info': contact_info,
            'transactions': all_transactions,
            'summary': {
                'total_transactions': len(all_transactions),
                'total_sent_by_me': float(total_sent_by_me),
                'total_received_by_me': float(total_received_by_me),
                'total_sent_by_them': float(total_sent_by_them),
                'total_received_by_them': float(total_received_by_them),
                'net_balance': float(net_balance),
                'sent_count': len([t for t in all_transactions if t['transaction_type'] in ['sent_by_me', 'sent_by_them']]),
                'received_count': len([t for t in all_transactions if t['transaction_type'] in ['received_by_me', 'received_by_them']])
            }
        }
        
    except Exception as e:
        print(f"Error getting complete person transaction history: {e}")
        import traceback
        traceback.print_exc()
        return {
            'contact_info': {'identifier': contact_identifier, 'exists_in_system': False},
            'transactions': [],
            'summary': {
                'total_transactions': 0,
                'total_sent_by_me': 0.0,
                'total_received_by_me': 0.0,
                'total_sent_by_them': 0.0,
                'total_received_by_them': 0.0,
                'net_balance': 0.0,
                'sent_count': 0,
                'received_count': 0
            }
        }

def get_all_sent_transactions(phone, limit=50, offset=0):
    """Get all sent transactions with receiver details"""
    try:
        db = get_db()
        
        transactions = db.execute('''
            SELECT 
                t.id,
                t.transaction_id,
                t.type,
                t.amount,
                t.balance_after,
                t.date_time,
                t.payment_method,
                t.receiver_identifier,
                u.username as receiver_username,
                u.phone as receiver_phone,
                u.upi_id as receiver_upi,
                c.nickname as receiver_nickname
            FROM transactions t
            LEFT JOIN users u ON (
                t.receiver_identifier = u.phone OR 
                t.receiver_identifier = u.upi_id
            )
            LEFT JOIN contacts c ON (
                c.user_phone = ? AND 
                (c.contact_phone = u.phone OR (u.phone IS NULL AND c.contact_phone = t.receiver_identifier))
            )
            WHERE t.phone = ? 
            AND t.type = 'send'
            ORDER BY t.date_time DESC
            LIMIT ? OFFSET ?
        ''', (phone, phone, limit, offset)).fetchall()
        
        db.close()
        
        result = []
        for trans in transactions:
            trans_dict = dict(trans)
            trans_dict['amount'] = float(trans_dict['amount'])
            trans_dict['balance_after'] = float(trans_dict['balance_after'])
            
            receiver_display = trans_dict['receiver_identifier']
            if trans_dict['receiver_nickname']:
                receiver_display = trans_dict['receiver_nickname']
            elif trans_dict['receiver_username']:
                receiver_display = trans_dict['receiver_username']
            elif trans_dict['receiver_phone']:
                receiver_display = f"User {trans_dict['receiver_phone'][-4:]}"
            
            trans_dict['receiver_display'] = receiver_display
            result.append(trans_dict)
        
        return result
        
    except Exception as e:
        print(f"Error getting all sent transactions: {e}")
        return []

def get_sent_transactions_count(phone):
    """Get total count of sent transactions"""
    try:
        db = get_db()
        result = db.execute('''
            SELECT COUNT(*) as count 
            FROM transactions 
            WHERE phone = ? AND type = 'send'
        ''', (phone,)).fetchone()
        db.close()
        
        return result['count'] if result else 0
    except Exception as e:
        print(f"Error getting sent transactions count: {e}")
        return 0

def add_to_contacts_from_transaction(user_phone, contact_identifier, nickname=None):
    """Add a contact from transaction history"""
    try:
        db = get_db()
        
        contact_user = None
        if '@' in contact_identifier:
            contact_user = db.execute('SELECT phone FROM users WHERE upi_id = ?', 
                                     (contact_identifier,)).fetchone()
        elif len(contact_identifier) == 10 and contact_identifier.isdigit():
            contact_user = db.execute('SELECT phone FROM users WHERE phone = ?', 
                                     (contact_identifier,)).fetchone()
        
        if not contact_user:
            return {'success': False, 'error': 'User not found'}
        
        contact_phone = contact_user['phone']
        
        existing = db.execute('''
            SELECT id FROM contacts 
            WHERE user_phone = ? AND contact_phone = ?
        ''', (user_phone, contact_phone)).fetchone()
        
        if existing:
            return {'success': False, 'error': 'Already in contacts'}
        
        db.execute('''
            INSERT INTO contacts (user_phone, contact_phone, nickname)
            VALUES (?, ?, ?)
        ''', (user_phone, contact_phone, nickname))
        
        db.commit()
        db.close()
        
        return {'success': True, 'contact_phone': contact_phone}
        
    except Exception as e:
        print(f"Error adding to contacts from transaction: {e}")
        return {'success': False, 'error': str(e)}
        
def get_all_received_transactions(phone, limit=50, offset=0):
    """Get all received transactions with sender details"""
    try:
        db = get_db()
        
        transactions = db.execute('''
            SELECT 
                t.id,
                t.transaction_id,
                t.type,
                t.amount,
                t.balance_after,
                t.date_time,
                t.payment_method,
                t.sender_identifier,
                u.username as sender_username,
                u.phone as sender_phone,
                u.upi_id as sender_upi,
                c.nickname as sender_nickname
            FROM transactions t
            LEFT JOIN users u ON (
                t.sender_identifier = u.phone OR 
                t.sender_identifier = u.upi_id
            )
            LEFT JOIN contacts c ON (
                c.user_phone = ? AND 
                (c.contact_phone = u.phone OR (u.phone IS NULL AND c.contact_phone = t.sender_identifier))
            )
            WHERE t.phone = ? 
            AND t.type = 'receive'
            ORDER BY t.date_time DESC
            LIMIT ? OFFSET ?
        ''', (phone, phone, limit, offset)).fetchall()
        
        db.close()
        
        result = []
        for trans in transactions:
            trans_dict = dict(trans)
            trans_dict['amount'] = float(trans_dict['amount'])
            trans_dict['balance_after'] = float(trans_dict['balance_after'])
            
            sender_display = trans_dict['sender_identifier']
            if trans_dict['sender_nickname']:
                sender_display = trans_dict['sender_nickname']
            elif trans_dict['sender_username']:
                sender_display = trans_dict['sender_username']
            elif trans_dict['sender_phone']:
                sender_display = f"User {trans_dict['sender_phone'][-4:]}"
            
            trans_dict['sender_display'] = sender_display
            result.append(trans_dict)
        
        return result
        
    except Exception as e:
        print(f"Error getting all received transactions: {e}")
        return []

def get_received_transactions_count(phone):
    """Get total count of received transactions"""
    try:
        db = get_db()
        result = db.execute('''
            SELECT COUNT(*) as count 
            FROM transactions 
            WHERE phone = ? AND type = 'receive'
        ''', (phone,)).fetchone()
        db.close()
        
        return result['count'] if result else 0
    except Exception as e:
        print(f"Error getting received transactions count: {e}")
        return 0

def get_all_people_history(phone, limit=10):
    """Get all people user has interacted with (both sent to and received from)"""
    try:
        db = get_db()
        
        people = db.execute('''
            SELECT 
                COALESCE(u.phone, t.identifier) as phone,
                COALESCE(u.username, t.identifier) as username,
                u.upi_id,
                MAX(t.date_time) as last_interaction,
                SUM(CASE WHEN t.direction = 'sent' THEN 1 ELSE 0 END) as sent_count,
                SUM(CASE WHEN t.direction = 'sent' THEN t.amount ELSE 0 END) as total_sent,
                SUM(CASE WHEN t.direction = 'received' THEN 1 ELSE 0 END) as received_count,
                SUM(CASE WHEN t.direction = 'received' THEN t.amount ELSE 0 END) as total_received
            FROM (
                SELECT 
                    receiver_identifier as identifier,
                    date_time,
                    amount,
                    'sent' as direction
                FROM transactions 
                WHERE phone = ? AND type = 'send' AND receiver_identifier IS NOT NULL
                
                UNION ALL
                
                SELECT 
                    sender_identifier as identifier,
                    date_time,
                    amount,
                    'received' as direction
                FROM transactions 
                WHERE phone = ? AND type = 'receive' AND sender_identifier IS NOT NULL
            ) t
            LEFT JOIN users u ON (
                t.identifier = u.phone OR 
                t.identifier = u.upi_id
            )
            GROUP BY COALESCE(u.phone, t.identifier)
            HAVING (sent_count + received_count) > 0
            ORDER BY MAX(t.date_time) DESC
            LIMIT ?
        ''', (phone, phone, limit)).fetchall()
        
        db.close()
        
        result = []
        for person in people:
            total_interactions = person['sent_count'] + person['received_count']
            net_flow = person['total_received'] - person['total_sent']
            
            result.append({
                'phone': person['phone'],
                'username': person['username'],
                'upi_id': person['upi_id'],
                'last_interaction': person['last_interaction'],
                'sent_count': person['sent_count'],
                'total_sent': float(person['total_sent']) if person['total_sent'] else 0.0,
                'received_count': person['received_count'],
                'total_received': float(person['total_received']) if person['total_received'] else 0.0,
                'total_interactions': total_interactions,
                'net_flow': float(net_flow) if net_flow else 0.0,
                'interaction_type': 'both' if person['sent_count'] > 0 and person['received_count'] > 0 else ('sent' if person['sent_count'] > 0 else 'received')
            })
        
        return result if result else []
        
    except Exception as e:
        print(f"Error getting all people history: {e}")
        return []

if __name__ == '__main__':
    print("=" * 50)
    print("EasyCash Database Initialization")
    print("=" * 50)
    
    try:
        print("\nOptions:")
        print("1. Reinitialize database (keep data if possible)")
        print("2. Recreate database (DELETE ALL DATA)")
        print("3. Test connection only")
        
        choice = input("\nEnter choice (1, 2, or 3): ").strip()
        
        if choice == '2':
            print("\n⚠️ WARNING: This will DELETE ALL DATA!")
            confirm = input("Type 'YES' to confirm: ")
            if confirm == 'YES':
                if recreate_database():
                    print("\n✓ Database recreated successfully with phone-based authentication!")
                else:
                    print("\n✗ Failed to recreate database")
            else:
                print("\nOperation cancelled")
                exit()
        elif choice == '1':
            if init_db():
                print("\n✓ Database initialized successfully with phone-based authentication!")
        elif choice == '3':
            print("\nTesting connection only...")
        
        if test_connection():
            print("✓ Database connection test passed!")
        
        print("\n" + "=" * 50)
        print("Ready to run EasyCash with Phone-based Authentication!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        print("\nIf you're having database issues, try:")
        print("1. Delete easycash.db file and restart")
        print("2. Run this file with option 2 to recreate database")
        print("=" * 50)