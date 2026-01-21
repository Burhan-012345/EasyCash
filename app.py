from flask import Flask, render_template, request, session, redirect, url_for, jsonify, make_response, send_from_directory, flash
from urllib.parse import quote
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
import os
import re
import uuid
from datetime import datetime, timedelta

from database import (
    init_db, create_user_with_phone, verify_user_by_phone, user_exists_by_phone,
    update_balance, add_transaction, get_transactions,
    get_user_by_phone, reset_pin_attempts_by_phone, add_pin_attempt_by_phone,
    get_pin_attempts_by_phone, get_user_balance_by_phone, get_transaction_stats,
    get_filtered_transactions, get_transaction_by_id,
    get_transaction_count, get_recent_transactions,
    send_payment as db_send_payment,
    get_contacts as db_get_contacts,
    add_contact as db_add_contact,
    search_users as db_search_users,
    get_user_by_mobile as db_get_user_by_mobile,
    get_user_by_upi as db_get_user_by_upi,
    get_sent_to_contacts,
    get_person_transaction_history,
    get_all_sent_transactions,
    get_sent_transactions_count,
    add_to_contacts_from_transaction,
    get_received_from_contacts,
    get_all_received_transactions,
    get_received_transactions_count,
    get_all_people_history
)

from database import fix_transactions_table_constraint

# Import QR service
from qr_service import qr_bp

# Import for PDF generation
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch, cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.graphics.shapes import Drawing, Line  # Added Line import here
from reportlab.graphics.charts.piecharts import Pie
import io

# Import Notification Service
from notification_service import notification_service

DATABASE_PATH = 'easycash.db'

# Add this after imports in app.py
def get_base_url():
    """Get the base URL based on the environment"""
    if 'pythonanywhere.com' in request.host:
        return 'https://atm01.pythonanywhere.com'
    else:
        return request.url_root.rstrip('/')

# Helper function to get database connection
def get_db():
    """Get database connection"""
    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row
    return db

# Add this helper function
def get_last_sent_identifier(phone):
    """Get the last identifier (phone/UPI) user sent money to"""
    try:
        db = get_db()
        result = db.execute('''
            SELECT receiver_identifier, payment_method 
            FROM transactions 
            WHERE phone = ? AND type = 'send'
            ORDER BY date_time DESC 
            LIMIT 1
        ''', (phone,)).fetchone()
        db.close()
        
        if result:
            return {
                'identifier': result['receiver_identifier'],
                'method': result['payment_method']
            }
    except Exception as e:
        print(f"Error getting last sent identifier: {e}")
    return None

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=15)
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Add this after app = Flask(__name__)
@app.before_request
def before_request():
    # Log session info for debugging
    if request.endpoint and 'static' not in request.endpoint:
        print(f"\n=== {request.method} {request.path} ===")
        print(f"Session authenticated: {session.get('authenticated')}")
        print(f"Session phone: {session.get('phone')}")
        print(f"Session last_phone: {session.get('last_phone')}")
        print(f"Session keys: {list(session.keys())}")
    
    # Restore last_phone from session if it exists and user is returning to site
    if request.endpoint == 'phone_screen' and session.get('last_phone'):
        # Skip phone screen and go directly to PIN entry
        if user_exists_by_phone(session['last_phone']):
            return redirect(url_for('pin_entry'))

@app.after_request
def after_request(response):
    # Add headers to prevent caching
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['X-Frame-Options'] = 'DENY'
    return response

# Register QR blueprint
app.register_blueprint(qr_bp)

@app.context_processor
def inject_now():
    def get_current_time():
        return datetime.now()
    return {'now': get_current_time}

@app.context_processor
def inject_datetime():
    return {
        'timedelta': timedelta,
        'datetime': datetime
    }

# Initialize database
init_db()
fix_transactions_table_constraint()

# Decorator to require authentication - IMPROVED VERSION
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check both authentication flags
        if 'phone' not in session or not session.get('authenticated', False):
            print("Login required: User not authenticated")
            print(f"Session phone: {session.get('phone')}")
            print(f"Session authenticated: {session.get('authenticated')}")
            return redirect(url_for('phone_screen'))
        
        # Additional validation: ensure user exists in database
        phone = session['phone']
        if not user_exists_by_phone(phone):
            print(f"User {phone} not found in database")
            session.clear()
            return redirect(url_for('phone_screen'))
        
        return f(*args, **kwargs)
    return decorated_function

# Helper function for PDF generation
def generate_transaction_pdf(phone, transactions, filter_type='all', date_range='all'):
    """Generate PDF for transactions"""
    buffer = io.BytesIO()
    
    # Create PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72,
        title=f"EasyCash Statement - {phone}"
    )
    
    # Create styles
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=24,
        spaceAfter=30,
        textColor=colors.HexColor('#2C3E50'),
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=12,
        textColor=colors.HexColor('#34495E')
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6
    )
    
    small_style = ParagraphStyle(
        'CustomSmall',
        parent=styles['Normal'],
        fontSize=8,
        spaceAfter=3,
        textColor=colors.gray
    )
    
    # Content elements
    elements = []
    
    # Title
    elements.append(Paragraph("EasyCash Transaction Statement", title_style))
    
    # User info
    user = get_user_by_phone(phone)
    user_info = f"""
    <b>Phone Number:</b> {phone}<br/>
    <b>Account Holder:</b> {user.get('username', 'User')}<br/>
    <b>Generated On:</b> {datetime.now().strftime('%d %B, %Y at %I:%M %p')}<br/>
    <b>Current Balance:</b> ₹{user['balance']:.2f}<br/>
    <b>Account Created:</b> {user['created_at'][:10]}
    """
    elements.append(Paragraph(user_info, normal_style))
    elements.append(Spacer(1, 20))
    
    # Filter info
    filter_text = f"<b>Filter Applied:</b> {filter_type.title()} transactions"
    if date_range != 'all':
        filter_text += f" | <b>Period:</b> {date_range.title()}"
    elements.append(Paragraph(filter_text, heading_style))
    elements.append(Spacer(1, 10))
    
    # Calculate summary
    total_deposits = sum(t['amount'] for t in transactions if t['type'] == 'deposit')
    total_withdrawals = sum(t['amount'] for t in transactions if t['type'] == 'withdraw')
    total_sent = sum(t['amount'] for t in transactions if t['type'] == 'send')
    total_received = sum(t['amount'] for t in transactions if t['type'] == 'receive')
    net_flow = (total_deposits + total_received) - (total_withdrawals + total_sent)
    
    # Summary table
    summary_data = [
        ['Total Transactions', 'Total Deposits', 'Total Withdrawals', 'Net Flow'],
        [
            str(len(transactions)),
            f'₹{total_deposits:.2f}',
            f'₹{total_withdrawals:.2f}',
            f'₹{net_flow:.2f}' if net_flow >= 0 else f'-₹{abs(net_flow):.2f}'
        ]
    ]
    
    summary_table = Table(summary_data, colWidths=[doc.width/4]*4)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495E')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#ECF0F1')),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, 1), 11),
        ('TOPPADDING', (0, 1), (-1, 1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#BDC3C7'))
    ]))
    
    elements.append(summary_table)
    elements.append(Spacer(1, 20))
    
    # Transactions table
    if transactions:
        # Prepare table data
        table_data = [['Date', 'Time', 'Transaction ID', 'Type', 'Amount (₹)', 'Balance (₹)']]
        
        for t in transactions:
            # Format date and time
            try:
                trans_date = datetime.strptime(t['date_time'], '%Y-%m-%d %H:%M:%S')
                date_str = trans_date.strftime('%d/%m/%Y')
                time_str = trans_date.strftime('%I:%M %p')
            except:
                date_str = t['date_time'][:10]
                time_str = t['date_time'][11:16]
            
            # Shorten transaction ID for display
            trans_id = t['transaction_id'][:8] + '...' if len(t['transaction_id']) > 8 else t['transaction_id']
            
            # Format amount with appropriate sign
            if t['type'] == 'deposit':
                amount_str = f"+₹{t['amount']:.2f}"
                amount_color = 'green'
            elif t['type'] == 'withdraw':
                amount_str = f"-₹{t['amount']:.2f}"
                amount_color = 'red'
            elif t['type'] == 'send':
                amount_str = f"-₹{t['amount']:.2f}"
                amount_color = 'orange'
            elif t['type'] == 'receive':
                amount_str = f"+₹{t['amount']:.2f}"
                amount_color = 'blue'
            else:
                amount_str = f"₹{t['amount']:.2f}"
                amount_color = 'black'
            
            table_data.append([
                date_str,
                time_str,
                trans_id,
                t['type'].title(),
                amount_str,
                f"₹{t['balance_after']:.2f}"
            ])
        
        # Create transactions table
        trans_table = Table(table_data, colWidths=[
            doc.width/6,  # Date
            doc.width/6,  # Time
            doc.width/6,  # ID
            doc.width/6,  # Type
            doc.width/6,  # Amount
            doc.width/6   # Balance
        ])
        
        # Style the table
        trans_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2C3E50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8F9FA')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E0E0E0'))
        ]))
        
        # Color amount column based on type
        for i, row in enumerate(table_data[1:], start=1):
            if table_data[i][3].lower() == 'deposit':
                trans_table.setStyle(TableStyle([
                    ('TEXTCOLOR', (4, i), (4, i), colors.green),
                    ('FONTNAME', (4, i), (4, i), 'Helvetica-Bold')
                ]))
            elif table_data[i][3].lower() == 'withdraw':
                trans_table.setStyle(TableStyle([
                    ('TEXTCOLOR', (4, i), (4, i), colors.red),
                    ('FONTNAME', (4, i), (4, i), 'Helvetica-Bold')
                ]))
            elif table_data[i][3].lower() == 'send':
                trans_table.setStyle(TableStyle([
                    ('TEXTCOLOR', (4, i), (4, i), colors.orange),
                    ('FONTNAME', (4, i), (4, i), 'Helvetica-Bold')
                ]))
            elif table_data[i][3].lower() == 'receive':
                trans_table.setStyle(TableStyle([
                    ('TEXTCOLOR', (4, i), (4, i), colors.blue),
                    ('FONTNAME', (4, i), (4, i), 'Helvetica-Bold')
                ]))
        
        elements.append(trans_table)
    else:
        elements.append(Paragraph("No transactions found for the selected filters.", normal_style))
        elements.append(Spacer(1, 20))
    
    elements.append(Spacer(1, 30))
    
    # Add pie chart if we have transactions
    if transactions and len(transactions) > 0:
        try:
            # Create pie chart for transaction type distribution
            drawing = Drawing(400, 200)
            pie = Pie()
            pie.x = 150
            pie.y = 50
            pie.width = 150
            pie.height = 150
            
            # Calculate values for pie chart
            deposit_count = sum(1 for t in transactions if t['type'] == 'deposit')
            withdraw_count = sum(1 for t in transactions if t['type'] == 'withdraw')
            send_count = sum(1 for t in transactions if t['type'] == 'send')
            receive_count = sum(1 for t in transactions if t['type'] == 'receive')
            
            if deposit_count + withdraw_count + send_count + receive_count > 0:
                pie.data = [deposit_count, withdraw_count, send_count, receive_count]
                pie.labels = [
                    f'Deposits ({deposit_count})',
                    f'Withdrawals ({withdraw_count})',
                    f'Sent ({send_count})',
                    f'Received ({receive_count})'
                ]
                pie.slices.strokeWidth = 1
                pie.slices[0].fillColor = colors.green
                pie.slices[1].fillColor = colors.red
                pie.slices[2].fillColor = colors.orange
                pie.slices[3].fillColor = colors.blue
                
                drawing.add(pie)
                elements.append(drawing)
                elements.append(Spacer(1, 20))
        except:
            pass  # Skip chart if there's an error
    
    # Footer
    footer_text = """
    <para align=center>
    <font size=8 color=gray>
    <b>EasyCash - Digital Wallet System</b><br/>
    This is an electronically generated statement. No signature required.<br/>
    For any queries or discrepancies, please contact support within 7 days.<br/>
    Generated by EasyCash v1.0 | Statement ID: {statement_id}
    </font>
    </para>
    """.format(statement_id=str(uuid.uuid4())[:8].upper())
    
    elements.append(Paragraph(footer_text, small_style))
    
    # Build PDF
    doc.build(elements)
    
    # Get PDF value from buffer
    pdf = buffer.getvalue()
    buffer.close()
    
    return pdf

# Route: Root - Auto-login or phone screen
@app.route('/', methods=['GET', 'POST'])
def phone_screen():
    # Check if we should auto-login from session
    last_phone = session.get('last_phone')
    
    # If user has a stored phone and it exists, redirect to PIN entry immediately
    if last_phone and user_exists_by_phone(last_phone):
        session['temp_phone'] = last_phone
        return redirect(url_for('pin_entry'))
    
    # Handle POST request (form submission)
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        
        # Validate phone number
        if not re.match(r'^[6-9]\d{9}$', phone):
            return render_template('phone_screen.html', error='Please enter a valid 10-digit mobile number starting with 6-9')
        
        session['temp_phone'] = phone
        
        # Store this phone as last used for auto-login
        session['last_phone'] = phone
        
        if user_exists_by_phone(phone):
            return redirect(url_for('pin_entry'))
        else:
            return redirect(url_for('pin_setup'))
    
    # GET request - show phone screen only if no stored phone exists
    return render_template('phone_screen.html')
    
@app.route('/api/phone-lookup', methods=['GET'])
@login_required
def api_phone_lookup():
    """API to lookup phone number for send money validation"""
    phone = request.args.get('phone', '').strip()
    current_phone = session['phone']
    
    if not phone:
        return jsonify({'exists': False, 'error': 'Phone number required'})
    
    # Validate mobile format
    if not re.match(r'^[6-9]\d{9}$', phone):
        return jsonify({'exists': False, 'error': 'Invalid phone number'})
    
    if phone == current_phone:
        return jsonify({
            'exists': False, 
            'error': 'Cannot send to yourself',
            'self_transfer': True
        })
    
    try:
        db = get_db()
        
        # Get user by mobile
        user = db.execute('''
            SELECT 
                username,
                upi_id,
                phone,
                created_at
            FROM users 
            WHERE phone = ?
        ''', (phone,)).fetchone()
        
        db.close()
        
        if user:
            return jsonify({
                'exists': True,
                'username': user['username'],
                'upi_id': user['upi_id'],
                'phone': user['phone'],
                'name': user['username'] or f"User {user['phone'][-4:]}"
            })
        else:
            return jsonify({'exists': False})
            
    except Exception as e:
        print(f"Error looking up phone: {e}")
        return jsonify({'exists': False, 'error': str(e)})

# Route: Direct PIN entry with phone parameter (for bookmarks/deep links)
@app.route('/direct-pin/<phone>')
def direct_pin_entry(phone):
    """Direct PIN entry for returning users with phone in URL"""
    # Validate phone format
    if not re.match(r'^[6-9]\d{9}$', phone):
        return redirect(url_for('phone_screen'))
    
    # Check if user exists
    if not user_exists_by_phone(phone):
        return redirect(url_for('phone_screen'))
    
    # Set session variables
    session['temp_phone'] = phone
    session['last_phone'] = phone
    
    return redirect(url_for('pin_entry'))

# Route: Switch Account (clear stored phone)
@app.route('/switch-account')
def switch_account():
    """Clear stored phone and go to phone screen"""
    session.pop('last_phone', None)
    session.pop('temp_phone', None)
    return redirect(url_for('phone_screen'))

# Route: PIN Setup (New users) - FIXED VERSION
@app.route('/pin-setup', methods=['GET', 'POST'])
def pin_setup():
    phone = session.get('temp_phone')
    if not phone:
        return redirect(url_for('phone_screen'))
    
    if request.method == 'POST':
        pin = request.form.get('pin', '')
        confirm_pin = request.form.get('confirm_pin', '')
        username = request.form.get('username', '').strip() or f"User_{phone[-4:]}"
        
        if len(pin) != 6 or not pin.isdigit():
            return render_template('pin_setup.html', error='PIN must be 6 digits')
        
        if pin != confirm_pin:
            return render_template('pin_setup.html', error='PINs do not match')
        
        # Create user with phone
        if create_user_with_phone(username, phone, pin):
            # CLEAR session completely first
            session.clear()
            
            # Set session variables
            session['phone'] = phone
            session['last_phone'] = phone  # Store for auto-login
            session['authenticated'] = True
            session.permanent = True
            session.modified = True
            
            # Send welcome notification
            notification_service.add_notification(
                phone,
                "Welcome to EasyCash!",
                "Your account has been created successfully. You can now send, receive, and manage money.",
                'success'
            )
            
            return redirect(url_for('dashboard'))
        else:
            return render_template('pin_setup.html', error='Phone number already registered')
    
    return render_template('pin_setup.html', phone=phone)

# Route: PIN Entry (Returning users) - FIXED VERSION
@app.route('/pin-entry', methods=['GET', 'POST'])
def pin_entry():
    # Check multiple sources for phone number
    phone = session.get('temp_phone')
    
    # If no temp phone, check for last phone from auto-login
    if not phone:
        phone = session.get('last_phone')
    
    # If still no phone, check query parameters
    if not phone and request.method == 'GET':
        phone = request.args.get('phone', '').strip()
        if phone and re.match(r'^[6-9]\d{9}$', phone) and user_exists_by_phone(phone):
            session['temp_phone'] = phone
            session['last_phone'] = phone
        else:
            # Phone doesn't exist or invalid, go to phone screen
            return redirect(url_for('phone_screen'))
    
    # Validate phone exists in database
    if not phone or not user_exists_by_phone(phone):
        # Phone doesn't exist, go to phone screen
        session.pop('last_phone', None)
        session.pop('temp_phone', None)
        return redirect(url_for('phone_screen'))
    
    # Check PIN attempts
    attempts = get_pin_attempts_by_phone(phone)
    if attempts >= 5:
        return render_template('pin_entry.html', 
                             phone=phone, 
                             error='Account locked. Too many attempts.')
    
    if request.method == 'POST':
        pin = request.form.get('pin', '')
        
        if len(pin) != 6 or not pin.isdigit():
            add_pin_attempt_by_phone(phone)
            return render_template('pin_entry.html', 
                                 phone=phone, 
                                 error='Invalid PIN format')
        
        user = verify_user_by_phone(phone, pin)
        if user:
            reset_pin_attempts_by_phone(phone)
            
            # CLEAR session completely first
            session.clear()
            
            # Set session variables with explicit session modification
            session['phone'] = phone
            session['last_phone'] = phone  # Store for auto-login
            session['authenticated'] = True
            session.permanent = True
            
            # Force session to save
            session.modified = True
            
            # Send login notification
            notification_service.send_security_notification(
                phone, 
                'login',
                request.remote_addr,
                request.user_agent.string[:50]
            )
            
            # Debug print (remove in production)
            print(f"Session set for phone: {phone}")
            print(f"Session contents: {dict(session)}")
            
            # Redirect to dashboard
            return redirect(url_for('dashboard'))
        else:
            attempts = add_pin_attempt_by_phone(phone)
            remaining = 5 - attempts
            error_msg = f'Incorrect PIN. {remaining} attempts remaining.' if remaining > 0 else 'Account locked.'
            return render_template('pin_entry.html', 
                                 phone=phone, 
                                 error=error_msg)
    
    return render_template('pin_entry.html', phone=phone)

@app.route('/dashboard')
@login_required
def dashboard():
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    # Check if user exists
    if not user:
        session.clear()
        return redirect(url_for('phone_screen'))
    
    recent_transactions = get_recent_transactions(phone, limit=5)
    
    # Get transaction statistics
    stats = get_transaction_stats(phone)
    
    # Get sent to contacts for dashboard
    sent_to_contacts = get_sent_to_contacts(phone, limit=3)
    
    # Get received from contacts
    received_from_contacts = get_received_from_contacts(phone, limit=3)
    
    # Get all people history (combined sent and received)
    all_people = get_all_people_history(phone, limit=6)
    
    # Get unread notification count
    unread_count = notification_service.get_unread_count(phone)
    
    # Debug logging
    print(f"DEBUG - Sent to contacts count: {len(sent_to_contacts)}")
    print(f"DEBUG - Received from contacts count: {len(received_from_contacts)}")
    print(f"DEBUG - Sent to contacts data: {sent_to_contacts}")
    print(f"DEBUG - Received from contacts data: {received_from_contacts}")
    
    return render_template('dashboard.html', 
                         user=user, 
                         transactions=recent_transactions,
                         stats=stats,
                         sent_to_contacts=sent_to_contacts,
                         received_from_contacts=received_from_contacts,
                         all_people=all_people,
                         needs_upi_setup=session.get('needs_upi_setup', False),
                         unread_count=unread_count)
                         
@app.route('/received-history')
@login_required
def received_history():
    """Page showing all people user has received money from"""
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    if not user:
        session.clear()
        return redirect(url_for('phone_screen'))
    
    # Get all received from contacts
    received_from_contacts = get_received_from_contacts(phone, limit=50)
    
    # Get total received count
    total_received = get_received_transactions_count(phone)
    
    # Get unread notification count
    unread_count = notification_service.get_unread_count(phone)
    
    return render_template('received_history.html',
                         user=user,
                         contacts=received_from_contacts,
                         total_received=total_received,
                         unread_count=unread_count)

@app.route('/all-people-history')
@login_required
def all_people_history():
    """Page showing all people user has interacted with"""
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    if not user:
        session.clear()
        return redirect(url_for('phone_screen'))
    
    # Get all people history
    all_people = get_all_people_history(phone, limit=50)
    
    # Get unread notification count
    unread_count = notification_service.get_unread_count(phone)
    
    return render_template('all_people_history.html',
                         user=user,
                         people=all_people,
                         total_people=len(all_people),
                         unread_count=unread_count)

@app.route('/api/received-contacts')
@login_required
def api_received_contacts():
    """API to get received from contacts"""
    phone = session['phone']
    
    limit = request.args.get('limit', 10, type=int)
    contacts = get_received_from_contacts(phone, limit)
    
    return jsonify({
        'success': True,
        'contacts': contacts,
        'count': len(contacts)
    })

@app.route('/api/all-people')
@login_required
def api_all_people():
    """API to get all people user has interacted with"""
    phone = session['phone']
    
    limit = request.args.get('limit', 10, type=int)
    people = get_all_people_history(phone, limit)
    
    return jsonify({
        'success': True,
        'people': people,
        'count': len(people)
    })

@app.route('/sent-history')
@login_required
def sent_history():
    """Page showing all people user has sent money to"""
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    if not user:
        session.clear()
        return redirect(url_for('phone_screen'))
    
    # Get all sent to contacts
    sent_to_contacts = get_sent_to_contacts(phone, limit=50)
    
    # Get total sent count
    total_sent = get_sent_transactions_count(phone)
    
    # Get unread notification count
    unread_count = notification_service.get_unread_count(phone)
    
    return render_template('sent_to.html',
                         user=user,
                         contacts=sent_to_contacts,
                         total_sent=total_sent,
                         unread_count=unread_count)

@app.route('/person-history/<path:contact_identifier>')
@login_required
def person_history(contact_identifier):
    """Transaction history with a specific person"""
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    if not user:
        session.clear()
        return redirect(url_for('phone_screen'))
    
    # Get transaction history with this person
    history_data = get_person_transaction_history(phone, contact_identifier)
    
    # Get unread notification count
    unread_count = notification_service.get_unread_count(phone)
    
    return render_template('person_history.html',
                         user=user,
                         contact_info=history_data['contact_info'],
                         transactions=history_data['transactions'],
                         summary=history_data['summary'],
                         unread_count=unread_count)

@app.route('/api/add-to-contacts', methods=['POST'])
@login_required
def api_add_to_contacts():
    """API to add a person from transaction history to contacts"""
    phone = session['phone']
    
    data = request.json
    contact_identifier = data.get('contact_identifier', '').strip()
    nickname = data.get('nickname', '').strip() or None
    
    if not contact_identifier:
        return jsonify({'success': False, 'error': 'Contact identifier required'})
    
    result = add_to_contacts_from_transaction(phone, contact_identifier, nickname)
    
    return jsonify(result)

@app.route('/api/sent-transactions')
@login_required
def api_sent_transactions():
    """API to get sent transactions (for pagination)"""
    phone = session['phone']
    
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    offset = (page - 1) * limit
    
    transactions = get_all_sent_transactions(phone, limit, offset)
    total_count = get_sent_transactions_count(phone)
    
    return jsonify({
        'success': True,
        'transactions': transactions,
        'total': total_count,
        'page': page,
        'total_pages': (total_count + limit - 1) // limit
    })

@app.route('/api/sent-to-contacts')
@login_required
def api_sent_to_contacts():
    """API to get sent to contacts"""
    phone = session['phone']
    
    limit = request.args.get('limit', 10, type=int)
    contacts = get_sent_to_contacts(phone, limit)
    
    return jsonify({
        'success': True,
        'contacts': contacts,
        'count': len(contacts)
    })

@app.route('/api/search-users')
@login_required
def api_search_users():
    search_term = request.args.get('q', '').strip()
    current_phone = session['phone']
    
    if len(search_term) < 2:
        return jsonify({'success': False, 'error': 'Search term too short'})
    
    try:
        db = get_db()
        
        # Search users (excluding current user)
        users = db.execute('''
            SELECT 
                username,
                phone,
                upi_id,
                created_at
            FROM users 
            WHERE (username LIKE ? 
               OR phone LIKE ?
               OR upi_id LIKE ?)
               AND phone != ?
            ORDER BY 
                CASE 
                    WHEN phone LIKE ? THEN 1
                    WHEN upi_id LIKE ? THEN 2
                    WHEN username LIKE ? THEN 3
                    ELSE 4
                END
            LIMIT 10
        ''', (
            f'{search_term}%',
            f'{search_term}%',
            f'{search_term}%',
            current_phone,
            f'{search_term}%',
            f'{search_term}%',
            f'{search_term}%'
        )).fetchall()
        
        db.close()
        
        result = []
        for user in users:
            result.append({
                'username': user['username'],
                'phone': user['phone'],
                'upi_id': user['upi_id'],
                'created_at': user['created_at']
            })
        
        return jsonify({
            'success': True,
            'users': result,
            'count': len(result)
        })
        
    except Exception as e:
        print(f"Error searching users: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/upi-lookup')
@login_required
def api_upi_lookup():
    upi_id = request.args.get('upi_id', '').strip().lower()
    
    if not upi_id:
        return jsonify({'exists': False, 'error': 'UPI ID required'})
    
    if not re.match(r'^[\w\.\d@_-]+@[\w\.-]+$', upi_id):
        return jsonify({'exists': False, 'error': 'Invalid UPI ID format'})

    try:
        db = get_db()
        
        # Get user by UPI ID
        user = db.execute('''
            SELECT 
                username,
                upi_id,
                phone,
                created_at
            FROM users 
            WHERE upi_id = ?
        ''', (upi_id,)).fetchone()
        
        db.close()
        
        if user:
            return jsonify({
                'exists': True,
                'username': user['username'],
                'upi_id': user['upi_id'],
                'phone': user['phone']
            })
        else:
            return jsonify({'exists': False})
            
    except Exception as e:
        print(f"Error looking up UPI ID: {e}")
        return jsonify({'exists': False, 'error': str(e)})

# API: Get User by Mobile Number
@app.route('/api/mobile-lookup')
@login_required
def api_mobile_lookup():
    phone = request.args.get('mobile', '').strip()
    current_phone = session['phone']
    
    if not phone:
        return jsonify({'exists': False, 'error': 'Mobile number required'})
    
    # Validate mobile format
    if not re.match(r'^[6-9]\d{9}$', phone):
        return jsonify({'exists': False, 'error': 'Invalid mobile number'})
    
    if phone == current_phone:
        return jsonify({'exists': False, 'error': 'Cannot send to yourself'})
    
    try:
        db = get_db()
        
        # Get user by mobile
        user = db.execute('''
            SELECT 
                username,
                upi_id,
                phone,
                created_at
            FROM users 
            WHERE phone = ?
        ''', (phone,)).fetchone()
        
        db.close()
        
        if user:
            return jsonify({
                'exists': True,
                'username': user['username'],
                'upi_id': user['upi_id'],
                'phone': user['phone']
            })
        else:
            return jsonify({'exists': False})
            
    except Exception as e:
        print(f"Error looking up mobile: {e}")
        return jsonify({'exists': False, 'error': str(e)})

# API: Validate Payment Method (enhanced)
@app.route('/api/validate-payment', methods=['POST'])
@login_required
def api_validate_payment():
    data = request.json
    payment_method = data.get('method')
    identifier = data.get('identifier', '').strip()
    current_phone = session['phone']
    
    if not identifier:
        return jsonify({'valid': False, 'message': 'Identifier required'})
    
    try:
        db = get_db()
        user_info = None
        
        if payment_method == 'mobile':
            # Validate mobile format
            if re.match(r'^[6-9]\d{9}$', identifier):
                user_info = db.execute('''
                    SELECT username, upi_id, phone 
                    FROM users 
                    WHERE phone = ? AND phone != ?
                ''', (identifier, current_phone)).fetchone()
        
        elif payment_method == 'upi':
            # Validate UPI format
            if re.match(r'^[\w\.-]+@[\w\.-]+$', identifier):
                user_info = db.execute('''
                    SELECT username, upi_id, phone 
                    FROM users 
                    WHERE upi_id = ? AND phone != ?
                ''', (identifier, current_phone)).fetchone()
        
        elif payment_method == 'contact':
            user_info = db.execute('''
                SELECT username, upi_id, phone 
                FROM users 
                WHERE username = ? AND phone != ?
            ''', (identifier, current_phone)).fetchone()
        
        db.close()
        
        if user_info:
            return jsonify({
                'valid': True,
                'user': {
                    'exists': True,
                    'username': user_info['username'],
                    'upi_id': user_info['upi_id'],
                    'phone': user_info['phone']
                }
            })
        elif payment_method == 'bank':
            return jsonify({
                'valid': True,
                'user': {
                    'exists': False,
                    'message': 'Bank transfer will be processed within 24 hours'
                }
            })
        else:
            return jsonify({
                'valid': True,
                'user': {
                    'exists': False,
                    'message': 'Recipient not found in EasyCash'
                }
            })
            
    except Exception as e:
        print(f"Error validating payment: {e}")
        return jsonify({
            'valid': False,
            'message': 'Validation failed'
        })

@app.route('/deposit', methods=['GET', 'POST'])
@login_required
def deposit():
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    # Add this check
    if not user:
        session.clear()
        return redirect(url_for('phone_screen'))
    
    if request.method == 'POST':
        try:
            amount = float(request.form.get('amount', 0))
            pin = request.form.get('pin', '')
            
            # Validate PIN first
            if not pin or len(pin) != 6 or not pin.isdigit():
                return render_template('deposit.html', 
                                     user=user,
                                     error='Invalid PIN format. Please enter 6 digits.')
            
            # Verify PIN
            if not verify_user_by_phone(phone, pin):
                return render_template('deposit.html', 
                                     user=user,
                                     error='Incorrect PIN. Please try again.')
            
            # Validate amount after PIN verification
            if amount <= 0:
                return render_template('deposit.html', 
                                     user=user,
                                     error='Amount must be positive')
            
            if amount > 1000000:  # Limit to 1 million
                return render_template('deposit.html',
                                     user=user,
                                     error='Amount exceeds maximum limit of ₹10,00,000')
            
            # Process deposit only after PIN validation
            new_balance = update_balance(phone, amount)
            transaction_id = add_transaction(phone, 'deposit', amount, new_balance)
            
            # Send deposit notification
            notification_service.send_transaction_notification(
                phone,
                'deposit',
                amount,
                transaction_id
            )
            
            # Update user data
            user = get_user_by_phone(phone)
            
            # Set success message in session
            session['deposit_success'] = {
                'amount': amount,
                'transaction_id': transaction_id,
                'new_balance': new_balance
            }
            
            return redirect(url_for('deposit_success'))
        except ValueError:
            return render_template('deposit.html', 
                                 user=user,
                                 error='Invalid amount')
        except Exception as e:
            return render_template('deposit.html',
                                 user=user,
                                 error=f'Transaction failed: {str(e)}')
    
    return render_template('deposit.html', user=user)
    
# Route: Deposit Receipt
@app.route('/deposit-receipt/<transaction_id>')
@login_required
def deposit_receipt(transaction_id):
    """View deposit receipt"""
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    # Get transaction details
    transaction = get_transaction_by_id(transaction_id)
    
    if not transaction or transaction['phone'] != phone:
        return redirect(url_for('deposit_success'))
    
    # Format transaction date
    try:
        transaction_date = datetime.strptime(transaction['date_time'], '%Y-%m-%d %H:%M:%S')
    except:
        transaction_date = datetime.now()
    
    # Calculate previous balance
    previous_balance = user['balance'] - transaction['amount']
    
    # Generate receipt number
    import random
    receipt_number = f"EC{transaction_date.strftime('%y%m%d')}{random.randint(1000, 9999)}"
    
    return render_template('deposit_receipt.html',
                         user=user,
                         transaction=transaction,
                         transaction_date=transaction_date,
                         previous_balance=previous_balance,
                         receipt_number=receipt_number,
                         current_time=datetime.now())
                         
@app.route('/download-transaction/<transaction_id>')
@login_required
def download_transaction_receipt(transaction_id):
    phone = session['phone']
    
    # Get the specific transaction
    transaction = get_transaction_by_id(transaction_id)
    
    # Check if transaction exists and belongs to user
    if not transaction or transaction['phone'] != phone:
        return "Transaction not found or access denied", 404
    
    # Create a single transaction PDF
    buffer = io.BytesIO()
    
    # Create PDF document with custom styling
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=50,
        bottomMargin=50
    )
    
    # Create styles
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'ReceiptTitle',
        parent=styles['Title'],
        fontSize=22,
        spaceAfter=20,
        textColor=colors.HexColor('#2C3E50'),
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=10,
        textColor=colors.HexColor('#34495E'),
        fontName='Helvetica-Bold'
    )
    
    normal_style = ParagraphStyle(
        'NormalStyle',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=5,
        leading=14
    )
    
    highlight_style = ParagraphStyle(
        'HighlightStyle',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=10,
        textColor=colors.HexColor('#2C3E50'),
        fontName='Helvetica-Bold',
        alignment=TA_CENTER
    )
    
    footer_style = ParagraphStyle(
        'FooterStyle',
        parent=styles['Normal'],
        fontSize=8,
        spaceBefore=20,
        textColor=colors.gray,
        alignment=TA_CENTER
    )
    
    # Content elements
    elements = []
    
    # Title
    elements.append(Paragraph("EasyCash Transaction Receipt", title_style))
    elements.append(Spacer(1, 10))
    
    # Add logo/header line
    header_line = Drawing(400, 2)
    header_line.add(Line(0, 0, 400, 0, strokeColor=colors.HexColor('#3498db'), strokeWidth=2))
    elements.append(header_line)
    elements.append(Spacer(1, 20))
    
    # Get user info
    user = get_user_by_phone(phone)
    
    # Transaction details header
    elements.append(Paragraph("Transaction Details", header_style))
    elements.append(Spacer(1, 10))
    
    # Format transaction date
    try:
        trans_date = datetime.strptime(transaction['date_time'], '%Y-%m-%d %H:%M:%S')
        date_str = trans_date.strftime('%d %B, %Y')
        time_str = trans_date.strftime('%I:%M %p')
    except:
        date_str = transaction['date_time'][:10]
        time_str = transaction['date_time'][11:16]
    
    # Create transaction details table
    trans_type = transaction['type'].title()
    
    # Determine amount format based on transaction type
    amount_display = f"₹{transaction['amount']:.2f}"
    if trans_type.lower() in ['deposit', 'receive']:
        amount_display = f"+₹{transaction['amount']:.2f}"
    elif trans_type.lower() in ['withdraw', 'send']:
        amount_display = f"-₹{transaction['amount']:.2f}"
    
    # Create details table
    details_data = [
        ['Field', 'Value'],
        ['Transaction ID', transaction['transaction_id']],
        ['Date', date_str],
        ['Time', time_str],
        ['Transaction Type', trans_type],
        ['Amount', amount_display],
        ['Balance After', f"₹{transaction['balance_after']:.2f}"],
        ['Account Holder', user.get('username', 'User')],
        ['Phone Number', phone]
    ]
    
    # Add receiver info for send transactions
    if trans_type.lower() == 'send' and 'receiver_identifier' in transaction:
        receiver_info = transaction['receiver_identifier']
        if 'receiver_username' in transaction and transaction['receiver_username']:
            receiver_info = f"{transaction['receiver_username']} ({receiver_info})"
        details_data.append(['Sent To', receiver_info])
    
    # Add payment method if available - FIXED: Check if value exists and is not None
    payment_method = transaction.get('payment_method')
    if payment_method:
        details_data.append(['Payment Method', str(payment_method).title()])
    else:
        # If payment_method exists but is None/empty, show "Not specified"
        details_data.append(['Payment Method', 'Not specified'])
    
    details_table = Table(details_data, colWidths=[doc.width/3, doc.width*2/3])
    details_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495E')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8F9FA')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E0E0E0')),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TEXTCOLOR', (1, 0), (1, 0), colors.whitesmoke)
    ]))
    
    # Color amount cell based on transaction type
    for i, row in enumerate(details_data):
        if row[0] == 'Amount':
            if trans_type.lower() in ['deposit', 'receive']:
                details_table.setStyle(TableStyle([
                    ('TEXTCOLOR', (1, i), (1, i), colors.green),
                    ('FONTNAME', (1, i), (1, i), 'Helvetica-Bold')
                ]))
            elif trans_type.lower() in ['withdraw', 'send']:
                details_table.setStyle(TableStyle([
                    ('TEXTCOLOR', (1, i), (1, i), colors.red),
                    ('FONTNAME', (1, i), (1, i), 'Helvetica-Bold')
                ]))
    
    elements.append(details_table)
    elements.append(Spacer(1, 25))
    
    # Status and verification
    status_text = """
    <para align=center>
    <font size=12 color=darkgreen>
    <b>✓ Transaction Successful</b><br/>
    This receipt serves as proof of your transaction.
    </font>
    </para>
    """
    elements.append(Paragraph(status_text, highlight_style))
    elements.append(Spacer(1, 15))
    
    # Verification info
    verification_info = f"""
    <b>Receipt ID:</b> {str(uuid.uuid4())[:12].upper()}<br/>
    <b>Generated On:</b> {datetime.now().strftime('%d %B, %Y at %I:%M %p')}<br/>
    <b>Document ID:</b> EC-{transaction_id[:8]}
    """
    elements.append(Paragraph(verification_info, normal_style))
    elements.append(Spacer(1, 20))
    
    # Terms and conditions
    terms_text = """
    <para>
    <font size=9>
    <b>Terms & Conditions:</b><br/>
    1. This is an electronically generated receipt. No signature required.<br/>
    2. Keep this receipt for your records and future reference.<br/>
    3. For any discrepancies, contact support within 7 days.<br/>
    4. Transaction ID is proof of successful transaction completion.
    </font>
    </para>
    """
    elements.append(Paragraph(terms_text, normal_style))
    elements.append(Spacer(1, 25))
    
    # Footer
    footer_text = """
    <para align=center>
    <font size=9>
    <b>EasyCash - Secure Digital Wallet</b><br/>
    Thank you for using our services.<br/>
    Visit our website: www.easycash.example.com | Support: support@easycash.example.com
    </font>
    </para>
    """
    elements.append(Paragraph(footer_text, footer_style))
    
    # Build PDF
    doc.build(elements)
    
    # Get PDF value from buffer
    pdf = buffer.getvalue()
    buffer.close()
    
    # Create response
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    
    # Create filename with transaction details
    filename = f"EasyCash_Receipt_{transaction_id}_{date_str.replace(' ', '_')}.pdf"
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response

# Route: Deposit Success
@app.route('/deposit-success')
@login_required
def deposit_success():
    success_data = session.pop('deposit_success', None)
    if not success_data:
        return redirect(url_for('deposit'))
    
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    # Get the actual transaction from database
    transaction = get_transaction_by_id(success_data['transaction_id'])
    
    # Format date for display
    transaction_date = datetime.now()
    if transaction and 'date_time' in transaction:
        try:
            transaction_date = datetime.strptime(transaction['date_time'], '%Y-%m-%d %H:%M:%S')
        except:
            pass
    
    return render_template('deposit_success.html',
                         user=user,
                         transaction=transaction,
                         transaction_date=transaction_date)

# Route: Setup UPI
@app.route('/setup-upi', methods=['GET', 'POST'])
@login_required
def setup_upi():
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    if not user:
        session.clear()
        return redirect(url_for('phone_screen'))
    
    if request.method == 'POST':
        upi_id = request.form.get('upi_id', '').strip().lower()
        
        if not re.match(r'^[\w\.\d@_-]+@[\w\.-]+$', upi_id):
            return render_template('setup_upi.html', 
                                 user=user,
                                 error='Invalid UPI ID format. Use format: username@provider')
        
        try:
            db = get_db()
            existing_user = db.execute('''
                SELECT phone FROM users WHERE upi_id = ? AND phone != ?
            ''', (upi_id, phone)).fetchone()
            
            if existing_user:
                db.close()
                return render_template('setup_upi.html',
                                     user=user,
                                     error='This UPI ID is already taken by another user')
            
            # Update user's UPI ID
            db.execute('UPDATE users SET upi_id = ? WHERE phone = ?', 
                      (upi_id, phone))
            db.commit()
            db.close()
            
            # Update user data
            user = get_user_by_phone(phone)
            session.pop('needs_upi_setup', None)  # Remove the setup flag
            session['upi_setup_success'] = True
            
            # Send notification
            notification_service.add_notification(
                phone,
                "UPI ID Set Successfully",
                f"Your UPI ID {upi_id} is now active. You can receive payments using this ID.",
                'success'
            )
            
            return redirect(url_for('upi_setup_success'))
            
        except Exception as e:
            return render_template('setup_upi.html',
                                 user=user,
                                 error=f'Failed to set UPI ID: {str(e)}')
    
    return render_template('setup_upi.html', user=user)

# Route: UPI Setup Success
@app.route('/upi-setup-success')
@login_required
def upi_setup_success():
    success = session.pop('upi_setup_success', None)
    if not success:
        return redirect(url_for('setup_upi'))
    
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    return render_template('upi_setup_success.html', user=user)

# Route: Withdraw
@app.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw():
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    if request.method == 'POST':
        try:
            amount = float(request.form.get('amount', 0))
            
            if amount <= 0:
                return render_template('withdraw.html', 
                                     user=user, 
                                     error='Amount must be positive')
            
            if amount > user['balance']:
                return render_template('withdraw.html', 
                                     user=user, 
                                     error='Insufficient balance')
            
            if amount > 50000:  # Limit to 50,000 per withdrawal
                return render_template('withdraw.html',
                                     user=user,
                                     error='Amount exceeds maximum limit of ₹50,000 per withdrawal')
            
            new_balance = update_balance(phone, -amount)
            transaction_id = add_transaction(phone, 'withdraw', amount, new_balance)
            
            # Send withdrawal notification
            notification_service.send_transaction_notification(
                phone,
                'withdraw',
                amount,
                transaction_id
            )
            
            # Update user data
            user = get_user_by_phone(phone)
            
            # Set success message in session
            session['withdraw_success'] = {
                'amount': amount,
                'transaction_id': transaction_id,
                'new_balance': new_balance
            }
            
            return redirect(url_for('withdraw_success'))
        except ValueError:
            return render_template('withdraw.html', 
                                 user=user, 
                                 error='Invalid amount')
        except Exception as e:
            return render_template('withdraw.html',
                                 user=user,
                                 error=f'Transaction failed: {str(e)}')
    
    return render_template('withdraw.html', user=user)

# Route: Withdraw Success
@app.route('/withdraw-success')
@login_required
def withdraw_success():
    success_data = session.pop('withdraw_success', None)
    if not success_data:
        return redirect(url_for('withdraw'))
    
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    # Get the actual transaction from database
    transaction = get_transaction_by_id(success_data['transaction_id'])
    
    # Format date for display
    transaction_date = datetime.now()
    if transaction and 'date_time' in transaction:
        try:
            transaction_date = datetime.strptime(transaction['date_time'], '%Y-%m-%d %H:%M:%S')
        except:
            pass
    
    # Calculate arrival date (2 business days from now)
    arrival_date = transaction_date + timedelta(days=2)
    
    return render_template('withdraw_success.html',
                         user=user,
                         transaction=transaction,
                         transaction_date=transaction_date,
                         arrival_date=arrival_date,
                         timedelta=timedelta)  

@app.route('/receipt/<transaction_id>')
@login_required
def view_receipt(transaction_id):
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    # Get transaction details
    transaction = get_transaction_by_id(transaction_id)
    
    if not transaction or transaction['username'] != phone:
        return redirect(url_for('transactions'))
    
    # Format transaction date
    try:
        transaction_date = datetime.strptime(transaction['date_time'], '%Y-%m-%d %H:%M:%S')
    except:
        transaction_date = datetime.now()
    
    current_time = datetime.now()
    
    # Calculate arrival date for withdrawals
    arrival_date = None
    if transaction and transaction.get('type') == 'withdraw':
        arrival_date = current_time + timedelta(days=2)
    
    return render_template('receipt_success.html',
                         user=user,
                         transaction=transaction,
                         transaction_date=transaction_date,
                         current_time=current_time,
                         arrival_date=arrival_date,
                         timedelta=timedelta)

@app.route('/receipt-success')
@login_required
def receipt_success():
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    # Get transaction_id from query parameter
    transaction_id = request.args.get('transaction_id')
    
    if not transaction_id:
        return redirect(url_for('transactions'))
    
    # Get transaction details
    transaction = get_transaction_by_id(transaction_id)
    
    if not transaction or transaction['username'] != phone:
        return redirect(url_for('transactions'))
    
    # Format transaction date
    try:
        transaction_date = datetime.strptime(transaction['date_time'], '%Y-%m-%d %H:%M:%S')
    except:
        transaction_date = datetime.now()
    
    return render_template('receipt_success.html',
                         user=user,
                         transaction=transaction,
                         transaction_date=transaction_date,
                         current_time=datetime.now(),
                         timedelta=timedelta)

# Route: Transactions
@app.route('/transactions')
@login_required
def transactions():
    phone = session['phone']
    user_transactions = get_transactions(phone, limit=50)
    user = get_user_by_phone(phone)
    
    if not user:
        # Handle case where user doesn't exist (shouldn't happen if logged in)
        session.clear()
        return redirect(url_for('phone_screen'))
    
    # Ensure balance is a float with proper fallback
    current_balance = user.get('balance', 0.0) if user else 0.0
    
    # Get unread notification count
    unread_count = notification_service.get_unread_count(phone)
    
    return render_template('transactions.html', 
                         transactions=user_transactions,
                         current_balance=current_balance,
                         unread_count=unread_count)

# Route: Filtered Transactions (AJAX endpoint)
@app.route('/api/transactions/filter', methods=['GET'])
@login_required
def filtered_transactions():
    phone = session['phone']
    filter_type = request.args.get('type', 'all')
    date_range = request.args.get('date_range', 'all')
    
    # Calculate date range
    start_date = None
    end_date = datetime.now()
    
    if date_range == 'today':
        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_range == 'week':
        start_date = datetime.now() - timedelta(days=7)
    elif date_range == 'month':
        start_date = datetime.now() - timedelta(days=30)
    
    # Get filtered transactions
    transactions = get_filtered_transactions(
        phone=phone,  # Fixed: Changed from 'username' to 'phone'
        transaction_type=filter_type if filter_type != 'all' else None,
        start_date=start_date.strftime('%Y-%m-%d') if start_date else None,
        end_date=end_date.strftime('%Y-%m-%d'),
        limit=100
    )
    
    return jsonify({
        'success': True,
        'transactions': transactions,
        'count': len(transactions),
        'filter': filter_type,
        'date_range': date_range
    })

# Route: Profile
@app.route('/profile')
@login_required
def profile():
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    if not user:
        session.clear()
        return redirect(url_for('phone_screen'))
    
    # Get transaction statistics
    stats = get_transaction_stats(phone)
    
    # Get unread notification count
    unread_count = notification_service.get_unread_count(phone)
    
    return render_template('profile.html', 
                         user=user,
                         stats=stats,
                         unread_count=unread_count)

# Route: Download Receipt/PDF
@app.route('/download-receipt')
@login_required
def download_receipt():
    phone = session['phone']
    
    # Get filter parameters
    filter_type = request.args.get('filter', 'all')
    date_range = request.args.get('date_range', 'all')
    
    # Calculate date range
    start_date = None
    end_date = datetime.now()
    
    if date_range == 'today':
        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_range == 'week':
        start_date = datetime.now() - timedelta(days=7)
    elif date_range == 'month':
        start_date = datetime.now() - timedelta(days=30)
    
    # Get filtered transactions
    transactions = get_filtered_transactions(
        phone=phone,  # Fixed: Changed from 'username' to 'phone'
        transaction_type=filter_type if filter_type != 'all' else None,
        start_date=start_date.strftime('%Y-%m-%d') if start_date else None,
        end_date=end_date.strftime('%Y-%m-%d'),
        limit=1000
    )
    
    # Generate PDF
    pdf_content = generate_transaction_pdf(
        phone,
        transactions,
        filter_type,
        date_range
    )
    
    # Create response
    response = make_response(pdf_content)
    response.headers['Content-Type'] = 'application/pdf'
    filename = f"EasyCash_Statement_{phone}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response

# Route: Preview Receipt (HTML version)
@app.route('/receipt-preview')
@login_required
def receipt_preview():
    phone = session['phone']
    
    # Get filter parameters
    filter_type = request.args.get('filter', 'all')
    date_range = request.args.get('date_range', 'all')
    
    # Calculate date range
    start_date = None
    end_date = datetime.now()
    
    if date_range == 'today':
        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_range == 'week':
        start_date = datetime.now() - timedelta(days=7)
    elif date_range == 'month':
        start_date = datetime.now() - timedelta(days=30)
    
    # Get filtered transactions
    transactions = get_filtered_transactions(
        phone=phone,  # Fixed: Changed from 'username' to 'phone'
        transaction_type=filter_type if filter_type != 'all' else None,
        start_date=start_date.strftime('%Y-%m-%d') if start_date else None,
        end_date=end_date.strftime('%Y-%m-%d'),
        limit=1000
    )
    
    # Calculate summary
    total_deposits = sum(t['amount'] for t in transactions if t['type'] == 'deposit')
    total_withdrawals = sum(t['amount'] for t in transactions if t['type'] == 'withdraw')
    total_sent = sum(t['amount'] for t in transactions if t['type'] == 'send')
    total_received = sum(t['amount'] for t in transactions if t['type'] == 'receive')
    net_flow = (total_deposits + total_received) - (total_withdrawals + total_sent)
    
    # Get user info
    user = get_user_by_phone(phone)
    
    return render_template(
        'receipt_download.html',
        phone=phone,
        transactions=transactions,
        filter_type=filter_type,
        date_range=date_range,
        total_transactions=len(transactions),
        total_deposits=total_deposits,
        total_withdrawals=total_withdrawals,
        total_sent=total_sent,
        total_received=total_received,
        net_flow=net_flow,
        current_balance=user['balance'] if user else 0.0,
        generated_date=datetime.now().strftime('%d %B, %Y at %I:%M %p')
    )

@app.route('/logout')
def logout():
    phone = session.get('phone')
    last_phone = session.get('last_phone')
    
    # Send logout notification
    if phone:
        notification_service.send_security_notification(
            phone, 
            'logout',
            request.remote_addr,
            request.user_agent.string[:50]
        )
    
    session.clear()
    
    if last_phone:
        session['last_phone'] = last_phone
        
        session['temp_phone'] = last_phone
        
        return redirect(url_for('pin_entry'))
    
    elif phone:
        session['temp_phone'] = phone
        return redirect(url_for('pin_entry'))
    
    return redirect(url_for('phone_screen'))

# API: Get balance
@app.route('/api/balance')
@login_required
def api_balance():
    phone = session['phone']
    balance = get_user_balance_by_phone(phone)
    return jsonify({
        'success': True,
        'balance': balance
    })

# API: Get transaction statistics
@app.route('/api/stats')
@login_required
def api_stats():
    phone = session['phone']
    stats = get_transaction_stats(phone)
    return jsonify({
        'success': True,
        'stats': stats
    })

# API: Quick deposit
@app.route('/api/deposit/quick', methods=['POST'])
@login_required
def api_quick_deposit():
    phone = session['phone']
    
    try:
        amount = float(request.json.get('amount', 0))
        
        if amount <= 0:
            return jsonify({'success': False, 'error': 'Amount must be positive'}), 400
        
        if amount > 1000000:
            return jsonify({'success': False, 'error': 'Amount exceeds limit'}), 400
        
        new_balance = update_balance(phone, amount)
        transaction_id = add_transaction(phone, 'deposit', amount, new_balance)
        
        # Send deposit notification
        notification_service.send_transaction_notification(
            phone,
            'deposit',
            amount,
            transaction_id
        )
        
        return jsonify({
            'success': True,
            'transaction_id': transaction_id,
            'new_balance': new_balance,
            'message': f'Successfully deposited ₹{amount:.2f}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

# API: Quick withdraw
@app.route('/api/withdraw/quick', methods=['POST'])
@login_required
def api_quick_withdraw():
    phone = session['phone']
    
    try:
        amount = float(request.json.get('amount', 0))
        
        if amount <= 0:
            return jsonify({'success': False, 'error': 'Amount must be positive'}), 400
        
        current_balance = get_user_balance_by_phone(phone)
        if amount > current_balance:
            return jsonify({'success': False, 'error': 'Insufficient balance'}), 400
        
        if amount > 50000:
            return jsonify({'success': False, 'error': 'Amount exceeds limit'}), 400
        
        new_balance = update_balance(phone, -amount)
        transaction_id = add_transaction(phone, 'withdraw', amount, new_balance)
        
        # Send withdrawal notification
        notification_service.send_transaction_notification(
            phone,
            'withdraw',
            amount,
            transaction_id
        )
        
        return jsonify({
            'success': True,
            'transaction_id': transaction_id,
            'new_balance': new_balance,
            'message': f'Successfully withdrew ₹{amount:.2f}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/send-money', methods=['GET', 'POST'])
@login_required
def send_money():
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    if not user:
        session.clear()
        return redirect(url_for('phone_screen'))
    
    # Get last sent identifier for suggestion
    last_sent = get_last_sent_identifier(phone)
    last_sent_identifier = None
    last_sent_method = None
    
    if last_sent:
        last_sent_identifier = last_sent['identifier']
        last_sent_method = last_sent['method']
    
    # Handle QR method separately - check for hidden fields
    if request.method == 'POST':
        try:
            # Get form data - handle both regular and QR methods
            payment_method = request.form.get('payment_method')
            
            # For QR method, check for QR-specific fields
            if payment_method == 'qr':
                # QR method might have qr_upi_id or qr_phone
                qr_upi_id = request.form.get('qr_upi_id', '').strip()
                qr_phone = request.form.get('qr_phone', '').strip()
                
                if qr_upi_id:
                    identifier = qr_upi_id
                    payment_method = 'upi'  # Change to UPI for processing
                elif qr_phone:
                    identifier = qr_phone
                    payment_method = 'mobile'  # Change to mobile for processing
                else:
                    # Try to get from regular identifier field
                    identifier = request.form.get('identifier', '').strip()
            else:
                identifier = request.form.get('identifier', '').strip()
            
            amount = float(request.form.get('amount', 0))
            pin = request.form.get('pin', '')
            
            # Debug logging
            print(f"DEBUG: Processing send money request")
            print(f"DEBUG: Payment method: {payment_method}")
            print(f"DEBUG: Identifier: {identifier}")
            print(f"DEBUG: Amount: {amount}")
            print(f"DEBUG: PIN length: {len(pin) if pin else 0}")
            
            # Validate inputs
            if amount <= 0:
                print(f"DEBUG: Invalid amount: {amount}")
                return render_template('send_money.html',
                                     user=user,
                                     error='Amount must be positive',
                                     contacts=db_get_contacts(phone),
                                     last_sent_identifier=last_sent_identifier,
                                     last_sent_method=last_sent_method)
            
            if amount > user['balance']:
                print(f"DEBUG: Insufficient balance. User balance: {user['balance']}, Amount: {amount}")
                return render_template('send_money.html',
                                     user=user,
                                     error='Insufficient balance',
                                     contacts=db_get_contacts(phone),
                                     last_sent_identifier=last_sent_identifier,
                                     last_sent_method=last_sent_method)
            
            # Maximum transaction limit
            if amount > 50000:
                print(f"DEBUG: Amount exceeds limit: {amount}")
                return render_template('send_money.html',
                                     user=user,
                                     error='Maximum transaction limit is ₹50,000',
                                     contacts=db_get_contacts(phone),
                                     last_sent_identifier=last_sent_identifier,
                                     last_sent_method=last_sent_method)
            
            # Validate PIN
            if not pin or len(pin) != 6 or not pin.isdigit():
                print(f"DEBUG: Invalid PIN format: {pin}")
                return render_template('send_money.html',
                                     user=user,
                                     error='Invalid PIN format. Please enter 6 digits.',
                                     contacts=db_get_contacts(phone),
                                     last_sent_identifier=last_sent_identifier,
                                     last_sent_method=last_sent_method)
            
            # Verify PIN
            if not verify_user_by_phone(phone, pin):
                print(f"DEBUG: PIN verification failed for phone: {phone}")
                return render_template('send_money.html',
                                     user=user,
                                     error='Incorrect PIN',
                                     contacts=db_get_contacts(phone),
                                     last_sent_identifier=last_sent_identifier,
                                     last_sent_method=last_sent_method)
            
            # Validate identifier based on payment method
            if payment_method == 'mobile':
                if not re.match(r'^[6-9]\d{9}$', identifier):
                    print(f"DEBUG: Invalid mobile number: {identifier}")
                    return render_template('send_money.html',
                                         user=user,
                                         error='Invalid mobile number',
                                         contacts=db_get_contacts(phone),
                                         last_sent_identifier=last_sent_identifier,
                                         last_sent_method=last_sent_method)
            
            elif payment_method == 'upi':
                if not re.match(r'^[\w\.-]+@[\w\.-]+$', identifier):
                    print(f"DEBUG: Invalid UPI ID format: {identifier}")
                    return render_template('send_money.html',
                                         user=user,
                                         error='Invalid UPI ID format',
                                         contacts=db_get_contacts(phone),
                                         last_sent_identifier=last_sent_identifier,
                                         last_sent_method=last_sent_method)
            
            elif payment_method == 'contact':
                if not identifier or len(identifier) < 3:
                    print(f"DEBUG: Invalid contact identifier: {identifier}")
                    return render_template('send_money.html',
                                         user=user,
                                         error='Invalid contact identifier',
                                         contacts=db_get_contacts(phone),
                                         last_sent_identifier=last_sent_identifier,
                                         last_sent_method=last_sent_method)
            
            # Check if sending to yourself
            current_user_phone = user['phone']
            current_user_upi = user.get('upi_id', '')
            
            if (payment_method == 'mobile' and identifier == current_user_phone) or \
               (payment_method == 'upi' and identifier.lower() == current_user_upi.lower()):
                print(f"DEBUG: User trying to send to themselves")
                return render_template('send_money.html',
                                     user=user,
                                     error='You cannot send money to yourself',
                                     contacts=db_get_contacts(phone),
                                     last_sent_identifier=last_sent_identifier,
                                     last_sent_method=last_sent_method)
            
            print(f"DEBUG: All validations passed. Processing payment...")
            
            # Send payment using database function
            result = db_send_payment(phone, identifier, amount, payment_method)
            
            print(f"DEBUG: Payment result: {result}")
            
            # Send notification for sent payment
            notification_service.send_transaction_notification(
                phone,
                'send',
                amount,
                result['transaction_id'],
                receiver_name=identifier
            )
            
            # Update user data
            user = get_user_by_phone(phone)
            
            # Set success message
            session['send_success'] = {
                'amount': amount,
                'transaction_id': result['transaction_id'],
                'payment_method': payment_method,
                'receiver_identifier': identifier,
                'receiver_found': result.get('receiver_found', False),
                'receiver_username': result.get('receiver_username')
            }
            
            print(f"DEBUG: Redirecting to send_success")
            return redirect(url_for('send_success'))
            
        except ValueError as e:
            print(f"DEBUG: ValueError: {e}")
            return render_template('send_money.html',
                                 user=user,
                                 error='Invalid amount format',
                                 contacts=db_get_contacts(phone),
                                 last_sent_identifier=last_sent_identifier,
                                 last_sent_method=last_sent_method)
        except Exception as e:
            print(f"DEBUG: Exception: {str(e)}")
            import traceback
            traceback.print_exc()
            return render_template('send_money.html',
                                 user=user,
                                 error=f'Transaction failed: {str(e)}',
                                 contacts=db_get_contacts(phone),
                                 last_sent_identifier=last_sent_identifier,
                                 last_sent_method=last_sent_method)
    
    # GET request - show send money page
    contacts = db_get_contacts(phone)
    unread_count = notification_service.get_unread_count(phone)
    
    return render_template('send_money.html',
                         user=user,
                         contacts=contacts,
                         last_sent_identifier=last_sent_identifier,
                         last_sent_method=last_sent_method,
                         unread_count=unread_count)

# Route: Send Success
@app.route('/send-success')
@login_required
def send_success():
    success_data = session.pop('send_success', None)
    if not success_data:
        return redirect(url_for('send_money'))
    
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    # Get transaction details
    transaction = None
    if success_data.get('transaction_id'):
        transaction = get_transaction_by_id(success_data['transaction_id'])
    
    return render_template('send_success.html',
                         user=user,
                         transaction=transaction,
                         success_data=success_data)

# Route: Send Money via QR
@app.route('/send-money-qr', methods=['POST'])
@login_required
def send_money_qr():
    """Handle payment from QR scan"""
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    if not user:
        session.clear()
        return redirect(url_for('phone_screen'))
    
    try:
        # Get QR validated data
        upi_id = request.form.get('upi_id', '').strip()
        receiver_name = request.form.get('receiver_name', '').strip()
        amount = float(request.form.get('amount', 0))
        pin = request.form.get('pin', '')
        qr_data = request.form.get('qr_data', '')
        
        # Validate inputs
        if amount <= 0:
            return jsonify({'success': False, 'error': 'Amount must be positive'}), 400
        
        if amount > user['balance']:
            return jsonify({'success': False, 'error': 'Insufficient balance'}), 400
        
        if amount > 50000:
            return jsonify({'success': False, 'error': 'Maximum transaction limit is ₹50,000'}), 400
        
        # Validate PIN
        if len(pin) != 6 or not pin.isdigit():
            return jsonify({'success': False, 'error': 'Invalid PIN format'}), 400
        
        if not verify_user_by_phone(phone, pin):
            return jsonify({'success': False, 'error': 'Incorrect PIN'}), 400
        
        # Validate UPI ID
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+$', upi_id):
            return jsonify({'success': False, 'error': 'Invalid UPI ID format'}), 400
        
        # Send payment using database function
        result = db_send_payment(phone, upi_id, amount, 'upi')
        
        # Send notification for sent payment
        notification_service.send_transaction_notification(
            phone,
            'send',
            amount,
            result['transaction_id'],
            receiver_name=receiver_name or upi_id
        )
        
        # Update user data
        user = get_user_by_phone(phone)
        
        # Set success message
        session['send_success'] = {
            'amount': amount,
            'transaction_id': result['transaction_id'],
            'payment_method': 'upi',
            'receiver_identifier': upi_id,
            'receiver_found': result.get('receiver_found', False),
            'receiver_username': result.get('receiver_username', receiver_name),
            'via_qr': True,
            'qr_data': qr_data
        }
        
        return jsonify({
            'success': True,
            'redirect': url_for('send_success'),
            'transaction_id': result['transaction_id']
        })
        
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid amount'}), 400
    except Exception as e:
        print(f"Error processing QR payment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Route: Shared Receipt (Public View)
@app.route('/shared/receipt/<transaction_id>')
def view_shared_receipt(transaction_id):
    """Public view of a receipt (no authentication required)"""
    
    # Get transaction details
    transaction = get_transaction_by_id(transaction_id)
    
    if not transaction:
        return render_template('404.html'), 404
    
    # Get sender user info
    sender = get_user_by_phone(transaction['phone'])
    
    if not sender:
        return render_template('404.html'), 404
    
    # Format transaction date
    try:
        transaction_date = datetime.strptime(transaction['date_time'], '%Y-%m-%d %H:%M:%S')
    except:
        transaction_date = datetime.now()
    
    # Create success data structure
    success_data = {
        'amount': transaction['amount'],
        'receiver_identifier': transaction.get('receiver_identifier', 'Unknown'),
        'payment_method': transaction.get('payment_method', 'Unknown'),
        'transaction_id': transaction_id,
        'receiver_found': False  # Default for shared view
    }
    
    return render_template('shared_receipt.html',
                         transaction=transaction,
                         sender=sender,
                         transaction_date=transaction_date,
                         success_data=success_data,
                         base_url=get_base_url())  # Add this

@app.route('/contacts', methods=['GET', 'POST'])
@login_required
def contacts():
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            contact_phone = request.form.get('contact_phone', '').strip()
            nickname = request.form.get('nickname', '').strip()
            
            if not contact_phone:
                flash('Contact phone number is required', 'error')
                return redirect(url_for('contacts'))
            
            if contact_phone == phone:
                flash('Cannot add yourself as contact', 'error')
                return redirect(url_for('contacts'))
            
            # Check if contact exists
            if not user_exists_by_phone(contact_phone):
                flash('User not found. They must be registered with EasyCash.', 'error')
                return redirect(url_for('contacts'))
            
            # Add contact - FIXED: Use db_add_contact instead of add_contact
            if db_add_contact(phone, contact_phone, nickname):
                flash('Contact added successfully!', 'success')
                
                # Send notification
                notification_service.add_notification(
                    phone,
                    "Contact Added",
                    f"{nickname or contact_phone} added to your contacts",
                    'info'
                )
            else:
                flash('Contact already exists or could not be added', 'error')
            
            return redirect(url_for('contacts'))
    
    # GET request - show contacts page
    contacts_list = db_get_contacts(phone)  # FIXED: Changed get_contacts to db_get_contacts
    sent_to_contacts = get_sent_to_contacts(phone, limit=50)
    received_from_contacts = get_received_from_contacts(phone, limit=50)
    all_people = get_all_people_history(phone, limit=50)
    
    # Calculate stats
    sent_to_count = len(sent_to_contacts)
    received_from_count = len(received_from_contacts)
    both_ways_count = sum(1 for person in all_people 
                         if person['sent_count'] > 0 and person['received_count'] > 0)
    
    # Get unread notification count
    unread_count = notification_service.get_unread_count(phone)
    
    return render_template('contacts.html',
                         user=user,
                         contacts=contacts_list,
                         sent_to_contacts=sent_to_contacts,
                         received_from_contacts=received_from_contacts,
                         all_people=all_people,
                         sent_to_count=sent_to_count,
                         received_from_count=received_from_count,
                         both_ways_count=both_ways_count,
                         unread_count=unread_count)
                         
@app.route('/api/contacts/<contact_phone>/nickname', methods=['PUT'])
@login_required
def api_update_contact_nickname(contact_phone):
    """API to update contact nickname"""
    phone = session['phone']
    data = request.json
    nickname = data.get('nickname', '').strip() or None
    
    try:
        db = get_db()
        
        # Update nickname
        if nickname:
            db.execute('''
                UPDATE contacts 
                SET nickname = ? 
                WHERE user_phone = ? AND contact_phone = ?
            ''', (nickname, phone, contact_phone))
        else:
            db.execute('''
                UPDATE contacts 
                SET nickname = NULL 
                WHERE user_phone = ? AND contact_phone = ?
            ''', (phone, contact_phone))
        
        db.commit()
        db.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Error updating contact nickname: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/contacts/<contact_phone>', methods=['DELETE'])
@login_required
def api_delete_contact(contact_phone):
    """API to delete a contact"""
    phone = session['phone']
    
    try:
        db = get_db()
        
        db.execute('''
            DELETE FROM contacts 
            WHERE user_phone = ? AND contact_phone = ?
        ''', (phone, contact_phone))
        
        db.commit()
        db.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Error deleting contact: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/contacts/sync-from-history', methods=['POST'])
@login_required
def api_sync_contacts_from_history():
    """API to sync contacts from transaction history"""
    phone = session['phone']
    
    try:
        db = get_db()
        
        # Get unique people from sent transactions
        sent_contacts = db.execute('''
            SELECT DISTINCT receiver_identifier 
            FROM transactions 
            WHERE phone = ? 
            AND type = 'send' 
            AND receiver_identifier IS NOT NULL
        ''', (phone,)).fetchall()
        
        # Get unique people from received transactions
        received_contacts = db.execute('''
            SELECT DISTINCT sender_identifier 
            FROM transactions 
            WHERE phone = ? 
            AND type = 'receive' 
            AND sender_identifier IS NOT NULL
        ''', (phone,)).fetchall()
        
        added_count = 0
        
        # Process sent contacts
        for contact in sent_contacts:
            contact_identifier = contact['receiver_identifier']
            
            # Try to find user by phone or UPI
            contact_user = None
            if '@' in contact_identifier:
                contact_user = db.execute('SELECT phone FROM users WHERE upi_id = ?', 
                                         (contact_identifier,)).fetchone()
            else:
                contact_user = db.execute('SELECT phone FROM users WHERE phone = ?', 
                                         (contact_identifier,)).fetchone()
            
            if contact_user:
                contact_phone = contact_user['phone']
                
                # Check if already in contacts
                existing = db.execute('''
                    SELECT id FROM contacts 
                    WHERE user_phone = ? AND contact_phone = ?
                ''', (phone, contact_phone)).fetchone()
                
                if not existing:
                    # Add to contacts
                    db.execute('''
                        INSERT INTO contacts (user_phone, contact_phone)
                        VALUES (?, ?)
                    ''', (phone, contact_phone))
                    added_count += 1
        
        # Process received contacts
        for contact in received_contacts:
            contact_identifier = contact['sender_identifier']
            
            # Try to find user by phone or UPI
            contact_user = None
            if '@' in contact_identifier:
                contact_user = db.execute('SELECT phone FROM users WHERE upi_id = ?', 
                                         (contact_identifier,)).fetchone()
            else:
                contact_user = db.execute('SELECT phone FROM users WHERE phone = ?', 
                                         (contact_identifier,)).fetchone()
            
            if contact_user:
                contact_phone = contact_user['phone']
                
                # Check if already in contacts
                existing = db.execute('''
                    SELECT id FROM contacts 
                    WHERE user_phone = ? AND contact_phone = ?
                ''', (phone, contact_phone)).fetchone()
                
                if not existing:
                    # Add to contacts
                    db.execute('''
                        INSERT INTO contacts (user_phone, contact_phone)
                        VALUES (?, ?)
                    ''', (phone, contact_phone))
                    added_count += 1
        
        db.commit()
        db.close()
        
        # Send notification if contacts were added
        if added_count > 0:
            notification_service.add_notification(
                phone,
                "Contacts Synced",
                f"Added {added_count} new contacts from your transaction history",
                'info'
            )
        
        return jsonify({
            'success': True,
            'added_count': added_count,
            'message': f'Added {added_count} new contacts from your transaction history'
        })
        
    except Exception as e:
        print(f"Error syncing contacts from history: {e}")
        return jsonify({'success': False, 'error': str(e)})

# ========== NOTIFICATION ROUTES ==========

@app.route('/notifications')
@login_required
def notifications_page():
    """Notifications page"""
    phone = session['phone']
    user = get_user_by_phone(phone)
    
    if not user:
        session.clear()
        return redirect(url_for('phone_screen'))
    
    # Get all notifications
    all_notifications = notification_service.get_all_notifications(phone, limit=50)
    unread_count = notification_service.get_unread_count(phone)
    
    return render_template('notifications.html',
                         user=user,
                         notifications=all_notifications,
                         unread_count=unread_count)

@app.route('/api/notifications')
@login_required
def api_notifications():
    """API to get notifications"""
    phone = session['phone']
    
    unread_only = request.args.get('unread_only', 'false').lower() == 'true'
    limit = request.args.get('limit', 10, type=int)
    
    if unread_only:
        notifications = notification_service.get_unread_notifications(phone, limit)
    else:
        notifications = notification_service.get_all_notifications(phone, limit)
    
    unread_count = notification_service.get_unread_count(phone)
    
    return jsonify({
        'success': True,
        'notifications': notifications,
        'unread_count': unread_count
    })

@app.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def api_mark_notification_read(notification_id):
    """API to mark a notification as read"""
    phone = session['phone']
    
    success = notification_service.mark_as_read(notification_id, phone)
    
    return jsonify({
        'success': success,
        'unread_count': notification_service.get_unread_count(phone)
    })

@app.route('/api/notifications/read-all', methods=['POST'])
@login_required
def api_mark_all_notifications_read():
    """API to mark all notifications as read"""
    phone = session['phone']
    
    success = notification_service.mark_all_as_read(phone)
    
    return jsonify({
        'success': success,
        'unread_count': 0
    })

@app.route('/api/notifications/<int:notification_id>', methods=['DELETE'])
@login_required
def api_delete_notification(notification_id):
    """API to delete a notification"""
    phone = session['phone']
    
    success = notification_service.delete_notification(notification_id, phone)
    
    return jsonify({
        'success': success,
        'unread_count': notification_service.get_unread_count(phone)
    })

@app.route('/api/notifications/delete-read', methods=['DELETE'])
@login_required
def api_delete_read_notifications():
    """API to delete all read notifications"""
    phone = session['phone']
    
    success = notification_service.delete_all_read(phone)
    
    return jsonify({
        'success': success,
        'unread_count': notification_service.get_unread_count(phone)
    })

@app.route('/api/notifications/count')
@login_required
def api_notification_count():
    """API to get unread notification count"""
    phone = session['phone']
    count = notification_service.get_unread_count(phone)
    
    return jsonify({
        'success': True,
        'count': count
    })

# Route: Service Worker
@app.route('/sw.js')
def sw():
    response = make_response(open('service-worker.js').read())
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@app.route('/service-worker.js')
def service_worker():
    response = make_response(open('service-worker.js').read())
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

# Route: Manifest
@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('.', 'manifest.json')

# Route: Offline page
@app.route('/offline')
def offline():
    return render_template('offline.html')

# Route: Health check
@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'EasyCash API'
    })

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

# Create 404.html template if it doesn't exist
@app.route('/404.html')
def error_404():
    return render_template('404.html')

# Create 500.html template if it doesn't exist
@app.route('/500.html')
def error_500():
    return render_template('500.html')

# Create 403.html template if it doesn't exist
@app.route('/403.html')
def error_403():
    return render_template('403.html')

if __name__ == '__main__':
    # Create templates for error pages if they don't exist
    import os
    templates_dir = 'templates'
    
    if not os.path.exists(templates_dir):
        os.makedirs(templates_dir)
    
    error_pages = {
        '404.html': """<!DOCTYPE html>
<html>
<head>
    <title>404 - Page Not Found</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
        h1 { color: #e74c3c; }
        a { color: #3498db; text-decoration: none; }
    </style>
</head>
<body>
    <h1>404 - Page Not Found</h1>
    <p>The page you are looking for does not exist.</p>
    <a href="/">Go to Home</a>
</body>
</html>""",
        
        '500.html': """<!DOCTYPE html>
<html>
<head>
    <title>500 - Server Error</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
        h1 { color: #e74c3c; }
        a { color: #3498db; text-decoration: none; }
    </style>
</head>
<body>
    <h1>500 - Server Error</h1>
    <p>Something went wrong on our end. Please try again later.</p>
    <a href="/">Go to Home</a>
</body>
</html>""",
        
        '403.html': """<!DOCTYPE html>
<html>
<head>
    <title>403 - Forbidden</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
        h1 { color: #e74c3c; }
        a { color: #3498db; text-decoration: none; }
    </style>
</head>
<body>
    <h1>403 - Forbidden</h1>
    <p>You don't have permission to access this page.</p>
    <a href="/">Go to Home</a>
</body>
</html>"""
    }
    
    for filename, content in error_pages.items():
        filepath = os.path.join(templates_dir, filename)
        if not os.path.exists(filepath):
            with open(filepath, 'w') as f:
                f.write(content)
            print(f"✓ Created {filename}")
    
    # Create notifications.html template if it doesn't exist
    notifications_html = os.path.join(templates_dir, 'notifications.html')
    if not os.path.exists(notifications_html):
        with open(notifications_html, 'w') as f:
            f.write("""{% extends "base.html" %}

{% block title %}Notifications - EasyCash{% endblock %}

{% block content %}
<div class="container">
    <div class="header-section">
        <h1><i class="fas fa-bell"></i> Notifications</h1>
        <div class="header-actions">
            <button id="mark-all-read" class="btn btn-secondary">
                <i class="fas fa-check-double"></i> Mark All Read
            </button>
            <button id="delete-read" class="btn btn-danger">
                <i class="fas fa-trash"></i> Delete Read
            </button>
        </div>
    </div>

    <div class="notification-filters">
        <button class="filter-btn active" data-filter="all">All</button>
        <button class="filter-btn" data-filter="unread">Unread</button>
        <button class="filter-btn" data-filter="transaction">Transactions</button>
        <button class="filter-btn" data-filter="security">Security</button>
    </div>

    <div id="notifications-container">
        {% if notifications %}
            <div class="notifications-list">
                {% for notification in notifications %}
                <div class="notification-card {% if not notification.is_read %}unread{% endif %}" 
                     data-id="{{ notification.id }}" 
                     data-type="{{ notification.type }}">
                    <div class="notification-icon">
                        {% if notification.type == 'success' %}
                            <i class="fas fa-check-circle text-success"></i>
                        {% elif notification.type == 'warning' %}
                            <i class="fas fa-exclamation-triangle text-warning"></i>
                        {% elif notification.type == 'danger' %}
                            <i class="fas fa-exclamation-circle text-danger"></i>
                        {% elif notification.type == 'info' %}
                            <i class="fas fa-info-circle text-info"></i>
                        {% else %}
                            <i class="fas fa-bell"></i>
                        {% endif %}
                    </div>
                    <div class="notification-content">
                        <div class="notification-header">
                            <h4>{{ notification.title }}</h4>
                            <span class="notification-time">{{ notification.created_at_formatted }}</span>
                        </div>
                        <p class="notification-message">{{ notification.message }}</p>
                        
                        {% if notification.data and notification.data.transaction_id %}
                        <div class="notification-actions">
                            <a href="{{ url_for('download_transaction_receipt', transaction_id=notification.data.transaction_id) }}" 
                               class="btn btn-sm btn-outline-primary">
                                <i class="fas fa-receipt"></i> View Receipt
                            </a>
                        </div>
                        {% endif %}
                    </div>
                    <div class="notification-actions">
                        {% if not notification.is_read %}
                        <button class="btn btn-sm btn-outline-success mark-read-btn" 
                                title="Mark as read">
                            <i class="fas fa-check"></i>
                        </button>
                        {% endif %}
                        <button class="btn btn-sm btn-outline-danger delete-btn" 
                                title="Delete">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                </div>
                {% endfor %}
            </div>
        {% else %}
            <div class="empty-state">
                <div class="empty-icon">
                    <i class="fas fa-bell-slash"></i>
                </div>
                <h3>No notifications</h3>
                <p>You're all caught up! Check back later for updates.</p>
            </div>
        {% endif %}
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
$(document).ready(function() {
    // Mark as read
    $('.mark-read-btn').click(function() {
        const card = $(this).closest('.notification-card');
        const notificationId = card.data('id');
        
        $.ajax({
            url: `/api/notifications/${notificationId}/read`,
            method: 'POST',
            success: function(response) {
                if (response.success) {
                    card.removeClass('unread');
                    $(this).remove();
                    updateNotificationCount();
                }
            }
        });
    });
    
    // Delete notification
    $('.delete-btn').click(function() {
        const card = $(this).closest('.notification-card');
        const notificationId = card.data('id');
        
        if (confirm('Delete this notification?')) {
            $.ajax({
                url: `/api/notifications/${notificationId}`,
                method: 'DELETE',
                success: function(response) {
                    if (response.success) {
                        card.fadeOut(300, function() {
                            $(this).remove();
                            updateNotificationCount();
                            
                            // If no notifications left, show empty state
                            if ($('.notification-card').length === 0) {
                                $('#notifications-container').html(`
                                    <div class="empty-state">
                                        <div class="empty-icon">
                                            <i class="fas fa-bell-slash"></i>
                                        </div>
                                        <h3>No notifications</h3>
                                        <p>You're all caught up! Check back later for updates.</p>
                                    </div>
                                `);
                            }
                        });
                    }
                }
            });
        }
    });
    
    // Mark all as read
    $('#mark-all-read').click(function() {
        $.ajax({
            url: '/api/notifications/read-all',
            method: 'POST',
            success: function(response) {
                if (response.success) {
                    $('.notification-card').removeClass('unread');
                    $('.mark-read-btn').remove();
                    updateNotificationCount();
                    showToast('All notifications marked as read', 'success');
                }
            }
        });
    });
    
    // Delete all read
    $('#delete-read').click(function() {
        if (confirm('Delete all read notifications?')) {
            $.ajax({
                url: '/api/notifications/delete-read',
                method: 'DELETE',
                success: function(response) {
                    if (response.success) {
                        $('.notification-card:not(.unread)').fadeOut(300, function() {
                            $(this).remove();
                            updateNotificationCount();
                            
                            // If no notifications left, show empty state
                            if ($('.notification-card').length === 0) {
                                $('#notifications-container').html(`
                                    <div class="empty-state">
                                        <div class="empty-icon">
                                            <i class="fas fa-bell-slash"></i>
                                        </div>
                                        <h3>No notifications</h3>
                                        <p>You're all caught up! Check back later for updates.</p>
                                    </div>
                                `);
                            }
                        });
                        showToast('Read notifications deleted', 'success');
                    }
                }
            });
        }
    });
    
    // Filter notifications
    $('.filter-btn').click(function() {
        const filter = $(this).data('filter');
        
        $('.filter-btn').removeClass('active');
        $(this).addClass('active');
        
        $('.notification-card').hide();
        
        if (filter === 'all') {
            $('.notification-card').show();
        } else if (filter === 'unread') {
            $('.notification-card.unread').show();
        } else if (filter === 'transaction') {
            $('.notification-card').each(function() {
                const data = $(this).data('type');
                if (['success', 'info'].includes(data)) {
                    $(this).show();
                }
            });
        } else if (filter === 'security') {
            $('.notification-card').each(function() {
                const data = $(this).data('type');
                if (['warning', 'danger'].includes(data)) {
                    $(this).show();
                }
            });
        }
    });
    
    function updateNotificationCount() {
        $.ajax({
            url: '/api/notifications/count',
            success: function(response) {
                if (response.success) {
                    // Update badge in navbar if exists
                    const badge = $('#notification-badge');
                    if (badge.length) {
                        if (response.count > 0) {
                            badge.text(response.count).show();
                        } else {
                            badge.hide();
                        }
                    }
                }
            }
        });
    }
});
</script>
{% endblock %}""")
        print(f"✓ Created notifications.html")
    
    # Install required packages: pip install reportlab qrcode pillow
    print("\n" + "=" * 50)
    print("Starting EasyCash Server...")
    print("✓ Database initialized successfully!")
    print("✓ QR service integrated successfully!")
    print("✓ Notification system integrated successfully!")
    print("✓ Auto-login feature enabled!")
    print("✓ Returning users go directly to PIN entry!")
    print(f"✓ Server running at: http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)