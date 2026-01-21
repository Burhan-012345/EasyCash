# notification_service.py
import json
import os
from datetime import datetime
import sqlite3

class NotificationService:
    def __init__(self):
        self.db_path = 'easycash.db'
    
    def add_notification(self, phone, title, message, notification_type='info', data=None):
        """Add a notification to the database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create notifications table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    type TEXT DEFAULT 'info',
                    data TEXT,
                    is_read INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (phone) REFERENCES users(phone)
                )
            ''')
            
            # Insert notification
            data_json = json.dumps(data) if data else None
            cursor.execute('''
                INSERT INTO notifications (phone, title, message, type, data)
                VALUES (?, ?, ?, ?, ?)
            ''', (phone, title, message, notification_type, data_json))
            
            conn.commit()
            notification_id = cursor.lastrowid
            conn.close()
            
            return notification_id
        except Exception as e:
            print(f"Error adding notification: {e}")
            return None
    
    def get_unread_notifications(self, phone, limit=10):
        """Get unread notifications for a user"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 
                    id,
                    title,
                    message,
                    type,
                    data,
                    is_read,
                    created_at
                FROM notifications 
                WHERE phone = ? AND is_read = 0
                ORDER BY created_at DESC
                LIMIT ?
            ''', (phone, limit))
            
            notifications = []
            for row in cursor.fetchall():
                data = json.loads(row['data']) if row['data'] else {}
                notifications.append({
                    'id': row['id'],
                    'title': row['title'],
                    'message': row['message'],
                    'type': row['type'],
                    'data': data,
                    'is_read': bool(row['is_read']),
                    'created_at': row['created_at'],
                    'created_at_formatted': self.format_date(row['created_at'])
                })
            
            conn.close()
            return notifications
        except Exception as e:
            print(f"Error getting notifications: {e}")
            return []
    
    def get_all_notifications(self, phone, limit=20):
        """Get all notifications for a user"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 
                    id,
                    title,
                    message,
                    type,
                    data,
                    is_read,
                    created_at
                FROM notifications 
                WHERE phone = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (phone, limit))
            
            notifications = []
            for row in cursor.fetchall():
                data = json.loads(row['data']) if row['data'] else {}
                notifications.append({
                    'id': row['id'],
                    'title': row['title'],
                    'message': row['message'],
                    'type': row['type'],
                    'data': data,
                    'is_read': bool(row['is_read']),
                    'created_at': row['created_at'],
                    'created_at_formatted': self.format_date(row['created_at'])
                })
            
            conn.close()
            return notifications
        except Exception as e:
            print(f"Error getting all notifications: {e}")
            return []
    
    def mark_as_read(self, notification_id, phone=None):
        """Mark a notification as read"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if phone:
                cursor.execute('''
                    UPDATE notifications 
                    SET is_read = 1 
                    WHERE id = ? AND phone = ?
                ''', (notification_id, phone))
            else:
                cursor.execute('''
                    UPDATE notifications 
                    SET is_read = 1 
                    WHERE id = ?
                ''', (notification_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error marking notification as read: {e}")
            return False
    
    def mark_all_as_read(self, phone):
        """Mark all notifications as read for a user"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE notifications 
                SET is_read = 1 
                WHERE phone = ? AND is_read = 0
            ''', (phone,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error marking all notifications as read: {e}")
            return False
    
    def get_unread_count(self, phone):
        """Get count of unread notifications"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT COUNT(*) as count 
                FROM notifications 
                WHERE phone = ? AND is_read = 0
            ''', (phone,))
            
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else 0
        except Exception as e:
            print(f"Error getting unread count: {e}")
            return 0
    
    def delete_notification(self, notification_id, phone=None):
        """Delete a notification"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if phone:
                cursor.execute('DELETE FROM notifications WHERE id = ? AND phone = ?', 
                             (notification_id, phone))
            else:
                cursor.execute('DELETE FROM notifications WHERE id = ?', (notification_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error deleting notification: {e}")
            return False
    
    def delete_all_read(self, phone):
        """Delete all read notifications for a user"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM notifications WHERE phone = ? AND is_read = 1', 
                         (phone,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error deleting read notifications: {e}")
            return False
    
    def format_date(self, date_string):
        """Format date for display"""
        try:
            if not date_string:
                return "Just now"
            
            # Parse the date
            from datetime import datetime
            date_obj = datetime.strptime(date_string, '%Y-%m-%d %H:%M:%S')
            now = datetime.now()
            
            # Calculate difference
            diff = now - date_obj
            
            if diff.days > 7:
                return date_obj.strftime('%b %d, %Y')
            elif diff.days > 1:
                return f"{diff.days} days ago"
            elif diff.days == 1:
                return "Yesterday"
            elif diff.seconds >= 3600:
                hours = diff.seconds // 3600
                return f"{hours} hour{'s' if hours > 1 else ''} ago"
            elif diff.seconds >= 60:
                minutes = diff.seconds // 60
                return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
            else:
                return "Just now"
        except:
            return date_string
    
    # Helper methods for specific notification types
    
    def send_transaction_notification(self, phone, transaction_type, amount, transaction_id, 
                                      receiver_name=None, sender_name=None):
        """Send notification for a transaction"""
        if transaction_type == 'deposit':
            title = "Deposit Successful"
            message = f"₹{amount:.2f} has been deposited to your account"
            notif_type = 'success'
            data = {
                'transaction_id': transaction_id,
                'amount': amount,
                'type': 'deposit'
            }
        
        elif transaction_type == 'withdraw':
            title = "Withdrawal Requested"
            message = f"Withdrawal of ₹{amount:.2f} has been initiated"
            notif_type = 'info'
            data = {
                'transaction_id': transaction_id,
                'amount': amount,
                'type': 'withdraw'
            }
        
        elif transaction_type == 'send':
            title = "Payment Sent"
            message = f"₹{amount:.2f} sent to {receiver_name or 'contact'}"
            notif_type = 'info'
            data = {
                'transaction_id': transaction_id,
                'amount': amount,
                'type': 'send',
                'receiver_name': receiver_name
            }
        
        elif transaction_type == 'receive':
            title = "Payment Received"
            message = f"₹{amount:.2f} received from {sender_name or 'contact'}"
            notif_type = 'success'
            data = {
                'transaction_id': transaction_id,
                'amount': amount,
                'type': 'receive',
                'sender_name': sender_name
            }
        else:
            return None
        
        return self.add_notification(phone, title, message, notif_type, data)
    
    def send_security_notification(self, phone, event_type, ip_address=None, device=None):
        """Send security-related notifications"""
        notifications = {
            'login': {
                'title': "New Login",
                'message': f"New login detected{'. Device: ' + device if device else ''}",
                'type': 'warning'
            },
            'pin_change': {
                'title': "PIN Changed",
                'message': "Your PIN has been changed successfully",
                'type': 'warning'
            },
            'failed_attempt': {
                'title': "Failed Login Attempt",
                'message': "Multiple failed login attempts detected",
                'type': 'danger'
            },
            'logout': {
                'title': "Logged Out",
                'message': "You have been logged out",
                'type': 'info'
            }
        }
        
        if event_type in notifications:
            data = {
                'event_type': event_type,
                'ip_address': ip_address,
                'device': device,
                'timestamp': datetime.now().isoformat()
            }
            return self.add_notification(
                phone,
                notifications[event_type]['title'],
                notifications[event_type]['message'],
                notifications[event_type]['type'],
                data
            )
        return None

# Create global instance
notification_service = NotificationService()