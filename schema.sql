-- Users table
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    pin_hash TEXT NOT NULL,
    balance REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Transactions table
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    type TEXT NOT NULL, -- 'deposit' or 'withdraw'
    amount REAL NOT NULL,
    date_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    balance_after REAL NOT NULL,
    FOREIGN KEY (username) REFERENCES users (username)
);

-- PIN attempts tracking
CREATE TABLE IF NOT EXISTS pin_attempts (
    username TEXT PRIMARY KEY,
    attempts INTEGER DEFAULT 1,
    last_attempt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (username) REFERENCES users (username)
);

-- Add mobile and UPI support to users table
ALTER TABLE users ADD COLUMN mobile TEXT UNIQUE;
ALTER TABLE users ADD COLUMN upi_id TEXT UNIQUE;

-- Create contacts table for saving frequent recipients
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    contact_user_id INTEGER NOT NULL,
    nickname TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (contact_user_id) REFERENCES users (id),
    UNIQUE(user_id, contact_user_id)
);

-- Update transactions table for payment methods
ALTER TABLE transactions ADD COLUMN payment_method TEXT;
ALTER TABLE transactions ADD COLUMN receiver_identifier TEXT;
ALTER TABLE transactions ADD COLUMN sender_identifier TEXT;

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_transactions_username ON transactions(username);
CREATE INDEX IF NOT EXISTS idx_transactions_datetime ON transactions(date_time);