"""
QR Code Service for EasyCash UPI Wallet
Handles QR generation and scanning functionality with Phone-Based Authentication
"""
import qrcode
import qrcode.image.svg
from io import BytesIO
import base64
import re
from flask import Blueprint, request, jsonify, send_file, current_app
from PIL import Image
import sqlite3
from urllib.parse import quote, urlparse, parse_qs, unquote

# Try to import pyzbar, but make it optional
try:
    from pyzbar.pyzbar import decode
    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False
    print("Warning: pyzbar not installed. QR file scanning will not work.")
    print("Install with: pip install pyzbar pillow")

# Create blueprint
qr_bp = Blueprint('qr', __name__, url_prefix='/qr')

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect('easycash.db')
    conn.row_factory = sqlite3.Row
    return conn

def generate_upi_payload(upi_id, phone_number, amount=None):
    """
    Generate UPI payment payload in standard format for phone-based system
    Format: upi://pay?pa=<upi_id>&pn=<phone_number>&cu=INR
    """
    # URL encode parameters
    pa = quote(upi_id)
    pn = quote(phone_number)
    
    # Build UPI URL
    upi_url = f"upi://pay?pa={pa}&pn={pn}&cu=INR"
    
    if amount and amount > 0:
        upi_url += f"&am={amount:.2f}"
    
    return upi_url

def generate_qr_code(upi_payload, size=300):
    """
    Generate QR code image from UPI payload
    Returns base64 encoded image
    """
    try:
        # Create QR code instance
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        
        # Add data
        qr.add_data(upi_payload)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Resize if needed
        if size != 300:
            img = img.resize((size, size), Image.Resampling.LANCZOS)
        
        # Convert to base64
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return f"data:image/png;base64,{img_str}"
        
    except Exception as e:
        print(f"Error generating QR code: {e}")
        return None

def parse_upi_qr(qr_data):
    """
    Parse UPI QR code data and extract parameters
    Handles multiple formats including phone-based UPI IDs
    """
    if not qr_data:
        return None
    
    # Clean and decode the data
    qr_data = qr_data.strip()
    
    print(f"DEBUG parse_upi_qr: Raw QR data: {qr_data}")
    
    params = {}
    
    # Check if it's a phone-based UPI ID format: {phone}@easycash
    phone_upi_pattern = r'^(\+91)?[6-9]\d{9}@easycash$'
    if re.match(phone_upi_pattern, qr_data, re.IGNORECASE):
        print(f"DEBUG: Phone-based UPI ID detected: {qr_data}")
        params['pa'] = qr_data
        # Try to extract phone number from UPI ID
        phone_match = re.match(r'^(\+91)?([6-9]\d{9})@easycash$', qr_data, re.IGNORECASE)
        if phone_match:
            phone = phone_match.group(2)  # Get phone without country code
            params['phone'] = phone
        return params
    
    # Check if it's already a simple UPI ID (backward compatibility)
    if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+$', qr_data):
        print(f"DEBUG: Direct UPI ID detected: {qr_data}")
        params['pa'] = qr_data
        # Check if it's a phone-based UPI ID
        phone_match = re.match(r'^(\+91)?([6-9]\d{9})@easycash$', qr_data, re.IGNORECASE)
        if phone_match:
            phone = phone_match.group(2)
            params['phone'] = phone
        return params
    
    # Handle URL-encoded UPI data
    if qr_data.startswith('upi://pay'):
        print(f"DEBUG: UPI URL detected: {qr_data}")
        
        # Extract the query string
        if '?' in qr_data:
            query_string = qr_data.split('?', 1)[1]
            
            # Parse parameters
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    params[key] = unquote(value)
        
        # Check for phone-based UPI ID in pa parameter
        if 'pa' in params:
            phone_match = re.match(r'^(\+91)?([6-9]\d{9})@easycash$', params['pa'], re.IGNORECASE)
            if phone_match:
                phone = phone_match.group(2)
                params['phone'] = phone
    
    # Handle other UPI formats
    elif qr_data.startswith('UPI:'):
        print(f"DEBUG: Alternative UPI format detected: {qr_data}")
        
        # Remove 'UPI:' prefix
        qr_data = qr_data[4:]
        
        if '?' in qr_data:
            # Format: UPI:phone@easycash?pn=Name&am=100
            upi_part, query_part = qr_data.split('?', 1)
            params['pa'] = unquote(upi_part)
            
            # Check for phone number
            phone_match = re.match(r'^(\+91)?([6-9]\d{9})@easycash$', params['pa'], re.IGNORECASE)
            if phone_match:
                phone = phone_match.group(2)
                params['phone'] = phone
            
            # Parse remaining parameters
            for param in query_part.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    params[key] = unquote(value)
        else:
            # Just UPI ID after UPI:
            params['pa'] = unquote(qr_data)
            # Check for phone number
            phone_match = re.match(r'^(\+91)?([6-9]\d{9})@easycash$', params['pa'], re.IGNORECASE)
            if phone_match:
                phone = phone_match.group(2)
                params['phone'] = phone
    
    # Check for plain text that might contain UPI ID
    elif '@easycash' in qr_data.lower():
        print(f"DEBUG: Checking for phone-based UPI ID in text: {qr_data}")
        
        # Try to find phone-based UPI ID pattern in the text
        phone_upi_match = re.search(r'((\+91)?[6-9]\d{9}@easycash)', qr_data, re.IGNORECASE)
        if phone_upi_match:
            params['pa'] = phone_upi_match.group(1)
            print(f"DEBUG: Found phone-based UPI ID in text: {params['pa']}")
            
            # Extract phone number
            phone_match = re.match(r'^(\+91)?([6-9]\d{9})@easycash$', params['pa'], re.IGNORECASE)
            if phone_match:
                phone = phone_match.group(2)
                params['phone'] = phone
    
    # Check for phone number in the text (without @easycash)
    elif re.search(r'(\+91)?[6-9]\d{9}', qr_data):
        print(f"DEBUG: Checking for phone number in text: {qr_data}")
        
        # Try to find phone number pattern in the text
        phone_match = re.search(r'(\+91)?([6-9]\d{9})', qr_data)
        if phone_match:
            phone = phone_match.group(2)
            params['phone'] = phone
            # Create phone-based UPI ID
            params['pa'] = f"{phone}@easycash"
            print(f"DEBUG: Created phone-based UPI ID: {params['pa']}")
    
    print(f"DEBUG: Final parsed params: {params}")
    return params if params else None

def validate_upi_qr_data(qr_data):
    """
    Validate UPI QR code data and check if user exists
    Returns tuple (is_valid, message, user_data)
    """
    if not qr_data:
        return False, "No QR data provided", None
    
    print(f"DEBUG validate_upi_qr_data: Input: {qr_data[:100]}...")
    
    # Parse QR data
    params = parse_upi_qr(qr_data)
    
    if not params:
        print(f"DEBUG: Failed to parse QR data")
        return False, "Invalid QR code format. Could not extract UPI ID or phone number", None
    
    # Check if we have a UPI ID or phone number
    upi_id = params.get('pa')
    phone_number = params.get('phone')
    
    if not upi_id and not phone_number:
        print(f"DEBUG: No UPI ID or phone number found in params: {params}")
        return False, "No UPI ID or phone number found in QR code", None
    
    # If we have phone number but not UPI ID, construct phone-based UPI ID
    if phone_number and not upi_id:
        upi_id = f"{phone_number}@easycash"
        params['pa'] = upi_id
    
    # If we have UPI ID but not phone number, try to extract phone from UPI ID
    elif upi_id and not phone_number:
        phone_match = re.match(r'^(\+91)?([6-9]\d{9})@easycash$', upi_id, re.IGNORECASE)
        if phone_match:
            phone_number = phone_match.group(2)
            params['phone'] = phone_number
    
    user_name = params.get('pn', '')
    
    print(f"DEBUG: Extracted UPI ID: {upi_id}")
    print(f"DEBUG: Extracted phone number: {phone_number}")
    print(f"DEBUG: Extracted name: {user_name}")
    
    # Validate UPI ID format (allow both phone-based and legacy formats)
    phone_upi_pattern = r'^(\+91)?[6-9]\d{9}@easycash$'
    legacy_upi_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+$'
    
    if not re.match(phone_upi_pattern, upi_id, re.IGNORECASE) and not re.match(legacy_upi_pattern, upi_id):
        print(f"DEBUG: Invalid UPI ID format: {upi_id}")
        return False, f"Invalid UPI ID format: {upi_id}", None
    
    # Validate phone number format if present
    if phone_number and not re.match(r'^[6-9]\d{9}$', phone_number):
        print(f"DEBUG: Invalid phone number format: {phone_number}")
        return False, f"Invalid phone number format: {phone_number}", None
    
    # Check if user exists in database (prefer phone-based lookup)
    try:
        conn = get_db_connection()
        
        # Try to find user by phone number first
        user = None
        if phone_number:
            user = conn.execute(
                'SELECT phone, username, upi_id, created_at FROM users WHERE phone = ?',
                (phone_number,)
            ).fetchone()
        
        # If not found by phone, try by UPI ID (for backward compatibility)
        if not user and upi_id:
            user = conn.execute(
                'SELECT phone, username, upi_id, created_at FROM users WHERE upi_id = ?',
                (upi_id.lower(),)
            ).fetchone()
        
        conn.close()
        
        if user:
            user_dict = dict(user)
            print(f"DEBUG: User found with phone: {user_dict['phone']}")
            
            return True, f"Valid user found: {user_dict['phone']}", user_dict
        else:
            print(f"DEBUG: User not found for phone/UPI: {phone_number or upi_id}")
            
            # Prepare user data for response
            user_data = {
                'upi_id': upi_id,
                'phone': phone_number,
                'is_registered': False
            }
            
            # Add name if available
            if user_name:
                user_data['name'] = user_name
            
            return True, "User not found in system", user_data
            
    except Exception as e:
        print(f"DEBUG: Database error: {e}")
        return False, f"Database error: {str(e)}", None

@qr_bp.route('/generate/<phone>', methods=['GET'])
def generate_user_qr(phone):
    """Generate QR code for a user by phone number"""
    try:
        # Validate phone number format
        if not re.match(r'^[6-9]\d{9}$', phone):
            return jsonify({'success': False, 'error': 'Invalid phone number format. Use 10-digit Indian mobile number'}), 400
        
        # Get user data
        conn = get_db_connection()
        user = conn.execute(
            'SELECT phone, username, upi_id FROM users WHERE phone = ?',
            (phone,)
        ).fetchone()
        conn.close()
        
        if not user:
            return jsonify({'success': False, 'error': 'User not found with this phone number'}), 404
        
        if not user['upi_id']:
            return jsonify({'success': False, 'error': 'User has no UPI ID'}), 400
        
        # Get optional parameters
        amount = request.args.get('amount', type=float)
        size = request.args.get('size', default=300, type=int)
        
        # Validate size
        if size < 100 or size > 1000:
            size = 300
        
        # Generate UPI payload
        upi_payload = generate_upi_payload(
            upi_id=user['upi_id'],
            phone_number=user['phone'],
            amount=amount
        )
        
        # Generate QR code
        qr_image = generate_qr_code(upi_payload, size)
        
        if not qr_image:
            return jsonify({'success': False, 'error': 'Failed to generate QR code'}), 500
        
        return jsonify({
            'success': True,
            'qr_image': qr_image,
            'upi_payload': upi_payload,
            'user': {
                'phone': user['phone'],
                'username': user['username'],
                'upi_id': user['upi_id']
            },
            'amount': amount,
            'size': size
        })
        
    except Exception as e:
        print(f"Error generating QR: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@qr_bp.route('/validate', methods=['POST'])
def validate_qr():
    """Validate scanned QR code data"""
    try:
        data = request.get_json()
        qr_data = data.get('qr_data', '').strip()
        
        if not qr_data:
            return jsonify({
                'success': False,
                'error': 'No QR data provided'
            }), 400
        
        print(f"VALIDATE: Received QR data length: {len(qr_data)}")
        
        # Validate QR data
        is_valid, message, user_data = validate_upi_qr_data(qr_data)
        
        if not is_valid:
            return jsonify({
                'success': False,
                'error': message,
                'debug': {
                    'qr_data_sample': qr_data[:100] if len(qr_data) > 100 else qr_data,
                    'length': len(qr_data)
                }
            }), 400
        
        return jsonify({
            'success': True,
            'message': message,
            'user': user_data,
            'is_registered': user_data.get('is_registered', True) if user_data else False,
            'qr_data': qr_data
        })
        
    except Exception as e:
        print(f"Error validating QR: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@qr_bp.route('/scan/file', methods=['POST'])
def scan_qr_from_file():
    """Scan QR code from uploaded image file"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        # Check file type
        allowed_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp'}
        if not any(file.filename.lower().endswith(ext) for ext in allowed_extensions):
            return jsonify({'success': False, 'error': 'Invalid file type. Use PNG, JPG, JPEG, GIF, or BMP'}), 400
        
        # Check if pyzbar is available
        if not PYZBAR_AVAILABLE:
            return jsonify({
                'success': False,
                'error': 'QR scanning requires pyzbar package. Install with: pip install pyzbar pillow'
            }), 500
        
        # Read image file
        image = Image.open(file.stream)
        
        # Decode QR codes
        decoded_objects = decode(image)
        
        if not decoded_objects:
            return jsonify({'success': False, 'error': 'No QR code found in image'}), 400
        
        # Get first QR code data
        qr_data = decoded_objects[0].data.decode('utf-8')
        
        print("=" * 60)
        print("FILE SCAN DEBUG:")
        print(f"File: {file.filename}")
        print(f"QR Data (first 200 chars): {qr_data[:200]}")
        print(f"Full length: {len(qr_data)}")
        print("=" * 60)
        
        # Validate the QR data
        is_valid, message, user_data = validate_upi_qr_data(qr_data)
        
        if not is_valid:
            return jsonify({
                'success': False,
                'error': message,
                'debug': {
                    'raw_qr_data': qr_data[:200],
                    'length': len(qr_data)
                }
            }), 400
        
        return jsonify({
            'success': True,
            'qr_data': qr_data,
            'message': message,
            'user': user_data,
            'is_registered': user_data.get('is_registered', True) if user_data else False,
            'file_name': file.filename
        })
        
    except Exception as e:
        print(f"Error scanning QR from file: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@qr_bp.route('/details/<upi_id>')
def get_upi_details(upi_id):
    """Get user details by UPI ID"""
    try:
        # Decode URL if needed
        upi_id = unquote(upi_id)
        
        conn = get_db_connection()
        user = conn.execute(
            'SELECT phone, username, upi_id, created_at FROM users WHERE upi_id = ?',
            (upi_id,)
        ).fetchone()
        conn.close()
        
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        return jsonify({
            'success': True,
            'user': dict(user)
        })
        
    except Exception as e:
        print(f"Error getting UPI details: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@qr_bp.route('/details/phone/<phone>')
def get_user_by_phone(phone):
    """Get user details by phone number"""
    try:
        # Validate phone number format
        if not re.match(r'^[6-9]\d{9}$', phone):
            return jsonify({'success': False, 'error': 'Invalid phone number format'}), 400
        
        conn = get_db_connection()
        user = conn.execute(
            'SELECT phone, username, upi_id, created_at FROM users WHERE phone = ?',
            (phone,)
        ).fetchone()
        conn.close()
        
        if not user:
            return jsonify({'success': False, 'error': 'User not found with this phone number'}), 404
        
        return jsonify({
            'success': True,
            'user': dict(user)
        })
        
    except Exception as e:
        print(f"Error getting user by phone: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@qr_bp.route('/health')
def qr_health():
    """Check QR service health"""
    return jsonify({
        'status': 'healthy',
        'service': 'QR Service with Phone-Based Auth',
        'pyzbar_available': PYZBAR_AVAILABLE,
        'features': {
            'generate_qr': True,
            'scan_file': PYZBAR_AVAILABLE,
            'validate_qr': True,
            'upi_details': True,
            'phone_based_auth': True
        }
    })

@qr_bp.route('/test-parse', methods=['POST'])
def test_parse():
    """Test endpoint to see what's being parsed from QR"""
    try:
        data = request.get_json()
        qr_data = data.get('qr_data', '').strip()
        
        if not qr_data:
            return jsonify({'success': False, 'error': 'No QR data provided'}), 400
        
        print("=" * 60)
        print("TEST PARSE DEBUG:")
        print(f"QR Data: {qr_data}")
        print(f"Length: {len(qr_data)}")
        
        # Test parsing
        params = parse_upi_qr(qr_data)
        
        print(f"Parsed params: {params}")
        
        # Check if it looks like a phone-based UPI ID
        phone_upi_pattern = r'^(\+91)?[6-9]\d{9}@easycash$'
        is_phone_upi_id = re.match(phone_upi_pattern, qr_data, re.IGNORECASE)
        
        # Check if it looks like a legacy UPI ID
        legacy_upi_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+$'
        is_legacy_upi_id = re.match(legacy_upi_pattern, qr_data)
        
        print(f"Is phone-based UPI ID: {bool(is_phone_upi_id)}")
        print(f"Is legacy UPI ID: {bool(is_legacy_upi_id)}")
        print("=" * 60)
        
        return jsonify({
            'success': True,
            'qr_data': qr_data,
            'length': len(qr_data),
            'parsed_params': params,
            'is_phone_upi_id': bool(is_phone_upi_id),
            'is_legacy_upi_id': bool(is_legacy_upi_id),
            'suggested_upi_id': qr_data if (is_phone_upi_id or is_legacy_upi_id) else None
        })
        
    except Exception as e:
        print(f"Test parse error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@qr_bp.route('/test-phone/<phone>')
def test_phone_qr(phone):
    """Test endpoint to generate QR for phone number"""
    try:
        # Validate phone number format
        if not re.match(r'^[6-9]\d{9}$', phone):
            return jsonify({'success': False, 'error': 'Invalid phone number format'}), 400
        
        # Create phone-based UPI ID
        upi_id = f"{phone}@easycash"
        
        # Generate UPI payload
        upi_payload = generate_upi_payload(
            upi_id=upi_id,
            phone_number=phone,
            amount=100.00  # Test amount
        )
        
        # Generate QR code
        qr_image = generate_qr_code(upi_payload, 300)
        
        if not qr_image:
            return jsonify({'success': False, 'error': 'Failed to generate QR code'}), 500
        
        return jsonify({
            'success': True,
            'phone': phone,
            'upi_id': upi_id,
            'upi_payload': upi_payload,
            'qr_image': qr_image[:100] + "..." if len(qr_image) > 100 else qr_image
        })
        
    except Exception as e:
        print(f"Test phone QR error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@qr_bp.route('/test-page')
def test_page():
    """Simple test page for debugging"""
    return '''
    <html>
    <head><title>QR Test - Phone Based</title></head>
    <body>
        <h1>QR Parser Test - Phone Based Authentication</h1>
        
        <h2>Test Phone Number QR</h2>
        <input type="text" id="phoneInput" placeholder="Enter phone number (10 digits)" pattern="[6-9]\d{9}">
        <button onclick="testPhoneQR()">Generate Test QR</button>
        
        <h2>QR Data Parser</h2>
        <textarea id="qrData" rows="4" cols="50" placeholder="Paste QR data here..."></textarea>
        <br>
        <button onclick="testParse()">Test Parse</button>
        <div id="result"></div>
        
        <script>
        function testPhoneQR() {
            const phone = document.getElementById('phoneInput').value;
            
            if (!/^[6-9]\d{9}$/.test(phone)) {
                alert('Please enter a valid 10-digit Indian mobile number');
                return;
            }
            
            fetch(`/qr/test-phone/${phone}`)
            .then(r => r.json())
            .then(data => {
                document.getElementById('result').innerHTML = 
                    '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
            })
            .catch(err => {
                document.getElementById('result').innerHTML = 'Error: ' + err;
            });
        }
        
        function testParse() {
            const qrData = document.getElementById('qrData').value;
            
            fetch('/qr/test-parse', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({qr_data: qrData})
            })
            .then(r => r.json())
            .then(data => {
                document.getElementById('result').innerHTML = 
                    '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
            })
            .catch(err => {
                document.getElementById('result').innerHTML = 'Error: ' + err;
            });
        }
        </script>
    </body>
    </html>
    '''