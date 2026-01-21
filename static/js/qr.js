/**
 * QR Code Scanning and Processing for EasyCash
 */

class QRScanner {
    constructor() {
        this.scanner = null;
        this.currentCameraId = null;
        this.cameras = [];
        this.currentMethod = 'camera';
        this.scannedData = null;
    }

    async init() {
        try {
            // Check for camera permission
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                this.showError('Camera not supported or permission denied');
                return false;
            }

            // Get available cameras
            await this.getCameras();
            
            // Initialize HTML5 QR Scanner
            this.scanner = new Html5QrcodeScanner(
                "qr-reader",
                {
                    fps: 10,
                    qrbox: { width: 250, height: 250 },
                    rememberLastUsedCamera: true,
                    supportedScanTypes: [Html5QrcodeScanType.SCAN_TYPE_CAMERA]
                },
                false
            );

            // Set up scan callback
            this.scanner.render(this.onScanSuccess.bind(this), this.onScanError.bind(this));
            
            return true;
        } catch (error) {
            console.error('Failed to initialize QR scanner:', error);
            this.showError('Failed to initialize camera. Please check permissions.');
            return false;
        }
    }

    async getCameras() {
        try {
            const devices = await navigator.mediaDevices.enumerateDevices();
            this.cameras = devices.filter(device => device.kind === 'videoinput');
            console.log('Available cameras:', this.cameras);
        } catch (error) {
            console.error('Error getting cameras:', error);
        }
    }

    async switchCamera() {
        if (!this.cameras.length || !this.scanner) return;
        
        try {
            // Get current camera
            const currentState = await this.scanner.getState();
            if (!currentState) return;
            
            // Find next camera
            const currentIndex = this.cameras.findIndex(cam => 
                cam.deviceId === currentState.selectedCameraId
            );
            const nextIndex = (currentIndex + 1) % this.cameras.length;
            const nextCamera = this.cameras[nextIndex];
            
            // Stop current scanner
            await this.stop();
            
            // Restart with new camera
            this.scanner = new Html5QrcodeScanner(
                "qr-reader",
                {
                    fps: 10,
                    qrbox: { width: 250, height: 250 },
                    rememberLastUsedCamera: true
                },
                false
            );
            
            await this.scanner.start(
                { deviceId: { exact: nextCamera.deviceId } },
                { fps: 10 },
                this.onScanSuccess.bind(this),
                this.onScanError.bind(this)
            );
            
            showToast(`Switched to ${nextCamera.label || 'camera'}`, 'info');
        } catch (error) {
            console.error('Error switching camera:', error);
            showToast('Failed to switch camera', 'error');
        }
    }

    onScanSuccess(decodedText, decodedResult) {
        console.log('QR Scan Success:', decodedText);
        
        // Stop scanner after successful scan
        this.stop();
        
        // Process scanned data
        this.processScannedData(decodedText);
    }

    onScanError(error) {
        // Ignore common non-critical errors
        if (error && !error.includes('NotFoundException')) {
            console.warn('QR Scan Error:', error);
        }
    }

    async stop() {
        if (this.scanner) {
            try {
                await this.scanner.clear();
                this.scanner = null;
            } catch (error) {
                console.error('Error stopping scanner:', error);
            }
        }
    }

    async processScannedData(qrData) {
        try {
            showLoading('Validating QR code...');
            
            // Send to server for validation
            const response = await fetch('/qr/validate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ qr_data: qrData })
            });
            
            const result = await response.json();
            
            hideLoading();
            
            if (result.success) {
                this.scannedData = {
                    qrData: qrData,
                    user: result.user,
                    isRegistered: result.is_registered,
                    message: result.message
                };
                
                this.showResults();
            } else {
                this.showError(result.error || 'Invalid QR code');
                // Restart scanner after error
                setTimeout(() => this.init(), 2000);
            }
        } catch (error) {
            hideLoading();
            console.error('Error processing QR data:', error);
            this.showError('Failed to process QR code');
            setTimeout(() => this.init(), 2000);
        }
    }

    showResults() {
        const resultsDiv = document.getElementById('scanResults');
        const resultUpiId = document.getElementById('resultUpiId');
        const resultName = document.getElementById('resultName');
        const resultStatus = document.getElementById('resultStatus');
        
        if (!this.scannedData || !this.scannedData.user) {
            this.showError('Invalid scan data');
            return;
        }
        
        const user = this.scannedData.user;
        
        // Update UI with scanned data
        resultUpiId.textContent = user.upi_id || 'Unknown';
        resultName.textContent = user.username || 'Unknown';
        
        // Set status
        if (this.scannedData.isRegistered) {
            resultStatus.textContent = '✓ Registered EasyCash User';
            resultStatus.className = 'value status success';
        } else {
            resultStatus.textContent = '⚠️ External UPI User';
            resultStatus.className = 'value status warning';
        }
        
        // Update hidden form fields
        document.getElementById('hiddenUpiId').value = user.upi_id;
        document.getElementById('hiddenName').value = user.username;
        document.getElementById('hiddenQrData').value = this.scannedData.qrData;
        
        // Show results section
        resultsDiv.style.display = 'block';
        
        // Scroll to results
        resultsDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        
        // Set up amount input
        this.setupAmountInput();
    }

    setupAmountInput() {
        const amountInput = document.getElementById('qrAmount');
        const quickAmounts = document.querySelectorAll('.quick-amount');
        const proceedBtn = document.getElementById('proceedPaymentBtn');
        
        // Quick amount buttons
        quickAmounts.forEach(button => {
            button.addEventListener('click', () => {
                const amount = button.dataset.amount;
                amountInput.value = amount;
                
                // Update active state
                quickAmounts.forEach(btn => btn.classList.remove('active'));
                button.classList.add('active');
                
                // Enable proceed button if amount is valid
                this.updateProceedButton();
            });
        });
        
        // Amount input listener
        amountInput.addEventListener('input', () => {
            // Clear quick amounts active state
            quickAmounts.forEach(btn => btn.classList.remove('active'));
            
            // Update proceed button
            this.updateProceedButton();
        });
        
        // Proceed button click
        proceedBtn.addEventListener('click', () => {
            this.processPayment();
        });
    }

    updateProceedButton() {
        const amountInput = document.getElementById('qrAmount');
        const proceedBtn = document.getElementById('proceedPaymentBtn');
        const amount = parseFloat(amountInput.value) || 0;
        
        if (amount > 0 && amount <= 50000) {
            proceedBtn.disabled = false;
            proceedBtn.innerHTML = `<i class="fas fa-paper-plane"></i> Send ₹${amount.toFixed(2)}`;
        } else {
            proceedBtn.disabled = true;
            proceedBtn.innerHTML = `<i class="fas fa-paper-plane"></i> Proceed to Payment`;
        }
    }

    async processPayment() {
        const amountInput = document.getElementById('qrAmount');
        const amount = parseFloat(amountInput.value) || 0;
        
        // Validate amount
        if (amount <= 0 || amount > 50000) {
            showToast('Please enter a valid amount (₹1 - ₹50,000)', 'error');
            return;
        }
        
        // Check balance
        try {
            const balanceResponse = await fetch('/api/balance');
            const balanceData = await balanceResponse.json();
            
            if (balanceData.success && amount > balanceData.balance) {
                showToast('Insufficient balance', 'error');
                return;
            }
        } catch (error) {
            console.error('Error checking balance:', error);
        }
        
        // Show PIN prompt
        this.showPinPrompt(amount);
    }

    showPinPrompt(amount) {
        const pin = prompt(`Enter your 6-digit PIN to send ₹${amount.toFixed(2)}:`);
        
        if (!pin || pin.length !== 6 || !/^\d{6}$/.test(pin)) {
            showToast('Invalid PIN. Please try again.', 'error');
            return;
        }
        
        // Submit payment
        this.submitPayment(amount, pin);
    }

    async submitPayment(amount, pin) {
        try {
            showLoading('Processing payment...');
            
            const formData = new FormData(document.getElementById('qrPaymentForm'));
            formData.append('amount', amount);
            formData.append('pin', pin);
            
            const response = await fetch('/send-money-qr', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            hideLoading();
            
            if (result.success) {
                showToast('Payment processed successfully!', 'success');
                setTimeout(() => {
                    window.location.href = result.redirect;
                }, 1500);
            } else {
                showToast(result.error || 'Payment failed', 'error');
            }
        } catch (error) {
            hideLoading();
            console.error('Error submitting payment:', error);
            showToast('Payment failed. Please try again.', 'error');
        }
    }

    showError(message) {
        showToast(message, 'error');
        
        // Update UI if on results page
        const resultStatus = document.getElementById('resultStatus');
        if (resultStatus) {
            resultStatus.textContent = `✗ ${message}`;
            resultStatus.className = 'value status error';
        }
    }
}

// File scanning functionality
class FileQRScanner {
    constructor() {
        this.selectedFile = null;
        this.previewImage = null;
    }

    init() {
        const dropArea = document.getElementById('dropArea');
        const fileInput = document.getElementById('qrFileInput');
        const browseBtn = document.getElementById('browseBtn');
        const scanImageBtn = document.getElementById('scanImageBtn');
        const removeImageBtn = document.getElementById('removeImageBtn');
        const imagePreview = document.getElementById('imagePreview');
        const previewImage = document.getElementById('previewImage');

        // Browse button
        browseBtn.addEventListener('click', () => fileInput.click());

        // File input change
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.handleFileSelect(e.target.files[0]);
            }
        });

        // Drag and drop
        dropArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropArea.style.borderColor = 'var(--primary-color)';
            dropArea.style.background = 'rgba(var(--primary-rgb), 0.1)';
        });

        dropArea.addEventListener('dragleave', () => {
            dropArea.style.borderColor = 'var(--border-color)';
            dropArea.style.background = '';
        });

        dropArea.addEventListener('drop', (e) => {
            e.preventDefault();
            dropArea.style.borderColor = 'var(--border-color)';
            dropArea.style.background = '';
            
            if (e.dataTransfer.files.length > 0) {
                this.handleFileSelect(e.dataTransfer.files[0]);
            }
        });

        // Remove image
        removeImageBtn.addEventListener('click', () => {
            this.clearFile();
            imagePreview.style.display = 'none';
            scanImageBtn.disabled = true;
            fileInput.value = '';
        });

        // Scan button
        scanImageBtn.addEventListener('click', () => this.scanFile());
    }

    handleFileSelect(file) {
        // Validate file type
        const validTypes = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/bmp'];
        if (!validTypes.includes(file.type)) {
            showToast('Please select a valid image file (PNG, JPG, GIF, BMP)', 'error');
            return;
        }

        // Validate file size (max 5MB)
        if (file.size > 5 * 1024 * 1024) {
            showToast('File size must be less than 5MB', 'error');
            return;
        }

        this.selectedFile = file;
        
        // Show preview
        const reader = new FileReader();
        reader.onload = (e) => {
            document.getElementById('previewImage').src = e.target.result;
            document.getElementById('imagePreview').style.display = 'block';
            document.getElementById('scanImageBtn').disabled = false;
        };
        reader.readAsDataURL(file);
    }

    clearFile() {
        this.selectedFile = null;
        document.getElementById('previewImage').src = '';
    }

    async scanFile() {
        if (!this.selectedFile) return;

        try {
            showLoading('Scanning QR code from image...');
            
            const formData = new FormData();
            formData.append('file', this.selectedFile);

            const response = await fetch('/qr/scan/file', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            
            hideLoading();

            if (result.success) {
                // Process the scanned data
                window.qrScanner.scannedData = {
                    qrData: result.qr_data,
                    user: result.user,
                    isRegistered: result.is_registered,
                    message: result.message
                };
                
                window.qrScanner.showResults();
                
                // Switch to results tab
                document.getElementById('tab-camera').click();
            } else {
                showToast(result.error || 'Failed to scan QR code', 'error');
            }
        } catch (error) {
            hideLoading();
            console.error('Error scanning file:', error);
            showToast('Failed to scan QR code', 'error');
        }
    }
}

// Manual entry functionality
class ManualEntry {
    constructor() {
        this.validator = new QRValidator();
    }

    init() {
        const validateBtn = document.getElementById('validateManualBtn');
        const upiInput = document.getElementById('manualUpiId');
        const nameInput = document.getElementById('manualName');

        validateBtn.addEventListener('click', () => this.validateManualEntry());
        
        // Enter key support
        upiInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.validateManualEntry();
        });
        
        nameInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.validateManualEntry();
        });
    }

    async validateManualEntry() {
        const upiId = document.getElementById('manualUpiId').value.trim();
        const name = document.getElementById('manualName').value.trim();

        if (!upiId) {
            showToast('Please enter a UPI ID', 'error');
            return;
        }

        // Validate UPI format
        if (!/^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+$/.test(upiId)) {
            showToast('Invalid UPI ID format', 'error');
            return;
        }

        try {
            showLoading('Validating UPI ID...');
            
            // Check if UPI exists
            const response = await fetch(`/qr/details/${encodeURIComponent(upiId)}`);
            const result = await response.json();
            
            hideLoading();

            if (result.success) {
                const user = result.user;
                
                // Verify name if provided
                if (name && user.username.toLowerCase() !== name.toLowerCase()) {
                    if (!confirm(`Name doesn't match. Found: ${user.username}. Continue anyway?`)) {
                        return;
                    }
                }

                // Create fake QR data for consistency
                const qrData = `upi://pay?pa=${encodeURIComponent(upiId)}&pn=${encodeURIComponent(user.username || name)}`;
                
                window.qrScanner.scannedData = {
                    qrData: qrData,
                    user: user,
                    isRegistered: true,
                    message: 'Manual entry validated'
                };
                
                window.qrScanner.showResults();
                
                // Switch to results tab
                document.getElementById('tab-camera').click();
            } else {
                // UPI not found in EasyCash
                const proceed = confirm('UPI ID not registered with EasyCash. Continue with external transfer?');
                if (proceed) {
                    const user = {
                        upi_id: upiId,
                        username: name || 'Unknown User',
                        is_registered: false
                    };
                    
                    const qrData = `upi://pay?pa=${encodeURIComponent(upiId)}&pn=${encodeURIComponent(user.username)}`;
                    
                    window.qrScanner.scannedData = {
                        qrData: qrData,
                        user: user,
                        isRegistered: false,
                        message: 'External UPI user'
                    };
                    
                    window.qrScanner.showResults();
                    document.getElementById('tab-camera').click();
                }
            }
        } catch (error) {
            hideLoading();
            console.error('Error validating manual entry:', error);
            showToast('Failed to validate UPI ID', 'error');
        }
    }
}

// QR Validator utility
class QRValidator {
    validateUPIFormat(upiId) {
        return /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+$/.test(upiId);
    }

    parseUPIQR(qrData) {
        try {
            const url = new URL(qrData);
            if (url.protocol !== 'upi:') return null;
            
            const params = new URLSearchParams(url.search);
            return {
                upiId: params.get('pa'),
                name: params.get('pn'),
                amount: params.get('am'),
                currency: params.get('cu')
            };
        } catch (error) {
            return null;
        }
    }
}

// Global functions
function showLoading(message) {
    const overlay = document.getElementById('loadingOverlay');
    const text = document.getElementById('loadingText');
    
    if (overlay && text) {
        text.textContent = message || 'Processing...';
        overlay.style.display = 'flex';
    }
}

function hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}

function showToast(message, type = 'info') {
    // Use existing toast function if available
    if (typeof window.showToast === 'function') {
        window.showToast(message, type);
        return;
    }
    
    // Fallback toast implementation
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
        <span>${message}</span>
    `;
    
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: var(--dark-surface);
        color: var(--dark-text);
        padding: 12px 24px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        z-index: 9999;
        display: flex;
        align-items: center;
        gap: 10px;
        animation: slideUp 0.3s ease;
        border: 1px solid var(--border-color);
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(-50%) translateY(20px)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Initialize everything
function initQRScanner() {
    // Create global scanner instance
    window.qrScanner = new QRScanner();
    window.fileScanner = new FileQRScanner();
    window.manualEntry = new ManualEntry();
    
    // Initialize camera scanner
    window.qrScanner.init();
    
    // Initialize file scanner
    window.fileScanner.init();
    
    // Initialize manual entry
    window.manualEntry.init();
    
    // Set up camera control buttons
    document.getElementById('stopCameraBtn')?.addEventListener('click', () => {
        window.qrScanner.stop();
        showToast('Camera stopped', 'info');
    });
    
    document.getElementById('switchCameraBtn')?.addEventListener('click', () => {
        window.qrScanner.switchCamera();
    });
}

// Export for use in HTML
window.QRScanner = QRScanner;
window.FileQRScanner = FileQRScanner;
window.ManualEntry = ManualEntry;
window.initQRScanner = initQRScanner;
window.showLoading = showLoading;
window.hideLoading = hideLoading;