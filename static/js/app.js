// Toast Notification System
function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    if (!toast) {
        // Create toast if it doesn't exist
        const toastElement = document.createElement('div');
        toastElement.id = 'toast';
        toastElement.className = 'toast';
        document.body.appendChild(toastElement);
    }
    
    const toastElement = document.getElementById('toast');
    toastElement.textContent = message;
    toastElement.className = 'toast';
    
    // Add type-specific styling
    const colors = {
        error: 'linear-gradient(135deg, #ea4335, #c62828)',
        success: 'linear-gradient(135deg, #34a853, #2e7d32)',
        warning: 'linear-gradient(135deg, #fbbc04, #f57c00)',
        info: 'linear-gradient(135deg, #3498db, #2980b9)',
        send: 'linear-gradient(135deg, #4285f4, #0d47a1)',
        receive: 'linear-gradient(135deg, #2ecc71, #27ae60)'
    };
    
    toastElement.style.background = colors[type] || colors.info;
    
    toastElement.classList.add('show');
    
    setTimeout(() => {
        toastElement.classList.remove('show');
    }, 3000);
}

// Form Validation Helper
function validateAmount(amount) {
    if (!amount || isNaN(amount) || amount <= 0) {
        showToast('Please enter a valid amount', 'error');
        return false;
    }
    
    if (amount > 50000) {
        showToast('Maximum transaction limit is ₹50,000', 'error');
        return false;
    }
    
    return true;
}

function validateMobile(mobile) {
    const mobileRegex = /^[6-9]\d{9}$/;
    if (!mobileRegex.test(mobile)) {
        showToast('Please enter a valid 10-digit mobile number', 'error');
        return false;
    }
    return true;
}

function validateUPI(upi) {
    const upiRegex = /^[\w\.-]+@[\w\.-]+$/;
    if (!upiRegex.test(upi)) {
        showToast('Please enter a valid UPI ID (e.g., name@bank)', 'error');
        return false;
    }
    return true;
}

// Format Currency
function formatCurrency(amount) {
    return '₹' + parseFloat(amount).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,');
}

// PWA Installation Logic
let deferredPrompt;
let installShown = false;

// Show install button
function showInstallButton() {
    const installContainer = document.getElementById('installContainer');
    if (installContainer && !installShown) {
        installContainer.classList.remove('hidden');
        document.body.classList.add('has-install-banner');
        installShown = true;
        console.log('Install banner shown');
    }
}

// Hide install button
function hideInstallButton() {
    const installContainer = document.getElementById('installContainer');
    if (installContainer) {
        installContainer.classList.add('hidden');
        document.body.classList.remove('has-install-banner');
        console.log('Install banner hidden');
    }
}

// Check if app is already installed
function checkIfInstalled() {
    // Check if running in standalone mode
    if (window.matchMedia('(display-mode: standalone)').matches) {
        console.log('Running in standalone mode');
        hideInstallButton();
        return true;
    }
    
    // Check for other installation indicators
    if (window.navigator.standalone === true) {
        hideInstallButton();
        return true;
    }
    
    return false;
}

// Session Management
let sessionTimer;
function startSessionTimer() {
    // Clear existing timer
    if (sessionTimer) clearTimeout(sessionTimer);
    
    // Set new timer for 14 minutes (warning) and 15 minutes (logout)
    sessionTimer = setTimeout(() => {
        showToast('Session will expire in 1 minute', 'warning');
        
        // Logout after another minute
        setTimeout(() => {
            if (window.location.pathname !== '/' && 
                window.location.pathname !== '/pin-entry' && 
                window.location.pathname !== '/pin-setup') {
                showToast('Session expired. Please login again.', 'warning');
                setTimeout(() => {
                    window.location.href = '/logout';
                }, 2000);
            }
        }, 60 * 1000);
    }, 14 * 60 * 1000); // 14 minutes
}

// Reset timer on user activity
function resetSessionTimer() {
    if (sessionTimer) {
        startSessionTimer();
    }
}

// Input Auto-formatting
function formatAmountInput(input) {
    if (input && input.type === 'number' && input.name === 'amount') {
        const value = input.value;
        if (value.includes('.')) {
            const [whole, decimal] = value.split('.');
            if (decimal && decimal.length > 2) {
                input.value = whole + '.' + decimal.slice(0, 2);
            }
        }
    }
}

// Network Status Detection
function updateNetworkStatus() {
    if (!navigator.onLine) {
        showToast('You are offline. Some features may not work.', 'warning');
    }
}

// Prevent auto-submit on PIN setup pages
function disablePinAutoSubmit() {
    const pinSetupForm = document.querySelector('form[data-pin-type="setup"]');
    if (pinSetupForm) {
        console.log('Disabling auto-submit for PIN setup page');
        return true;
    }
    return false;
}

// Send Money Functions
async function validateRecipient(method, identifier) {
    try {
        const response = await fetch('/api/validate-payment', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                method: method,
                identifier: identifier
            })
        });
        
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Validation error:', error);
        showToast('Network error. Please check your connection.', 'error');
        return { valid: false, error: 'Network error' };
    }
}

async function quickSend(amount, recipient, method = 'contact') {
    if (!validateAmount(amount)) return;
    
    if (!confirm(`Send ${formatCurrency(amount)} to ${recipient}?`)) {
        return;
    }
    
    try {
        // Check if PIN input exists on page
        const pinInput = document.querySelector('input[name="pin"]');
        let pin = '';
        
        if (!pinInput) {
            pin = prompt('Enter 6-digit PIN to confirm:');
            if (!pin || pin.length !== 6) {
                showToast('PIN is required (6 digits)', 'error');
                return;
            }
        } else {
            pin = pinInput.value;
        }
        
        const formData = new FormData();
        formData.append('amount', amount);
        formData.append('identifier', recipient);
        formData.append('payment_method', method);
        formData.append('pin', pin);
        
        const response = await fetch('/send-money', {
            method: 'POST',
            body: formData
        });
        
        if (response.redirected) {
            window.location.href = response.url;
        } else {
            const result = await response.text();
            if (response.ok) {
                showToast('Payment sent successfully!', 'success');
                setTimeout(() => {
                    window.location.reload();
                }, 1500);
            } else {
                showToast('Payment failed. Please try again.', 'error');
            }
        }
    } catch (error) {
        console.error('Send error:', error);
        showToast('Payment failed. Please try again.', 'error');
    }
}

// Export transactions as CSV
function exportTransactions() {
    const transactions = [];
    document.querySelectorAll('.transaction-card-item').forEach(item => {
        if (item.style.display !== 'none') {
            const type = item.dataset.type;
            const amount = item.dataset.amount;
            const date = item.dataset.date;
            const method = item.dataset.method || '';
            const balance = item.dataset.balance;
            
            transactions.push({
                type: type.charAt(0).toUpperCase() + type.slice(1),
                amount: amount,
                date: date,
                method: method,
                balance: balance
            });
        }
    });
    
    if (transactions.length === 0) {
        showToast('No transactions to export', 'info');
        return;
    }
    
    // Create CSV
    let csv = 'Type,Amount (₹),Date,Payment Method,Balance (₹)\n';
    transactions.forEach(t => {
        const formattedDate = new Date(t.date).toLocaleDateString('en-IN', {
            day: '2-digit',
            month: 'short',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
        
        csv += `${t.type},${t.amount},${formattedDate},${t.method || 'N/A'},${t.balance}\n`;
    });
    
    // Download CSV
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `easycash-transactions-${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    showToast('Transactions exported successfully', 'success');
}

// Copy to clipboard helper
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Copied to clipboard', 'success');
    }).catch(err => {
        console.error('Failed to copy: ', err);
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.opacity = '0';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        
        try {
            const successful = document.execCommand('copy');
            if (successful) {
                showToast('Copied to clipboard', 'success');
            } else {
                showToast('Failed to copy', 'error');
            }
        } catch (err) {
            showToast('Failed to copy', 'error');
        }
        
        document.body.removeChild(textArea);
    });
}

// Refresh balance function
async function refreshBalance() {
    try {
        const response = await fetch('/api/balance');
        const data = await response.json();
        
        if (data.success) {
            const balanceElement = document.querySelector('.balance-amount');
            if (balanceElement) {
                balanceElement.textContent = formatCurrency(data.balance);
            }
            showToast('Balance updated', 'success');
        }
    } catch (error) {
        console.error('Balance refresh error:', error);
        showToast('Failed to update balance', 'error');
    }
}

// Search users function
async function searchUsers(searchTerm) {
    try {
        const response = await fetch(`/api/search-users?q=${encodeURIComponent(searchTerm)}`);
        const data = await response.json();
        
        if (data.success) {
            return data.users;
        }
        return [];
    } catch (error) {
        console.error('Search error:', error);
        return [];
    }
}

// Transaction filtering
function filterTransactions(filterType, dateRange, paymentMethod) {
    const transactionItems = document.querySelectorAll('.transaction-card-item');
    const now = new Date();
    let visibleCount = 0;
    
    transactionItems.forEach(item => {
        let show = true;
        
        // Type filter
        if (filterType !== 'all' && item.dataset.type !== filterType) {
            show = false;
        }
        
        // Payment method filter
        if (show && paymentMethod !== 'all') {
            const itemMethod = item.dataset.method || '';
            if (itemMethod.toLowerCase() !== paymentMethod.toLowerCase()) {
                show = false;
            }
        }
        
        // Date filter
        if (show && dateRange !== 'all') {
            const itemDate = new Date(item.dataset.date);
            let shouldShow = false;
            
            switch (dateRange) {
                case 'today':
                    shouldShow = itemDate.toDateString() === now.toDateString();
                    break;
                case 'week':
                    const weekAgo = new Date(now);
                    weekAgo.setDate(now.getDate() - 7);
                    shouldShow = itemDate >= weekAgo;
                    break;
                case 'month':
                    const monthAgo = new Date(now);
                    monthAgo.setMonth(now.getMonth() - 1);
                    shouldShow = itemDate >= monthAgo;
                    break;
            }
            
            if (!shouldShow) show = false;
        }
        
        item.style.display = show ? '' : 'none';
        if (show) visibleCount++;
    });
    
    return visibleCount;
}

// Download receipt for transaction
function downloadReceipt(transactionId) {
    const url = `/download-transaction/${transactionId}`;
    const iframe = document.createElement('iframe');
    iframe.style.display = 'none';
    iframe.src = url;
    document.body.appendChild(iframe);
    
    setTimeout(() => {
        if (iframe.parentNode) {
            iframe.parentNode.removeChild(iframe);
        }
    }, 5000);
    
    showToast('Downloading receipt...', 'info');
}

// Initialize all functionality
document.addEventListener('DOMContentLoaded', function() {
    console.log('EasyCash app initialized');
    
    // Check if we're on a PIN setup page
    const isPinSetupPage = disablePinAutoSubmit();
    
    // Check if app is already installed
    checkIfInstalled();
    
    // Install button event handlers
    const installBtn = document.getElementById('installBtn');
    const dismissBtn = document.getElementById('dismissInstall');
    
    if (installBtn) {
        installBtn.addEventListener('click', async () => {
            if (deferredPrompt) {
                try {
                    deferredPrompt.prompt();
                    const { outcome } = await deferredPrompt.userChoice;
                    
                    if (outcome === 'accepted') {
                        console.log('User accepted the install prompt');
                        showToast('EasyCash installed successfully!', 'success');
                        hideInstallButton();
                    } else {
                        console.log('User dismissed the install prompt');
                        showToast('Installation cancelled', 'info');
                    }
                    
                    deferredPrompt = null;
                } catch (error) {
                    console.error('Installation error:', error);
                    showToast('Installation failed', 'error');
                }
            } else {
                showToast('Installation not available', 'info');
            }
        });
    }
    
    if (dismissBtn) {
        dismissBtn.addEventListener('click', () => {
            hideInstallButton();
            // Store dismissal in localStorage for 7 days
            localStorage.setItem('easycash_install_dismissed', Date.now().toString());
            console.log('Install banner dismissed');
        });
    }
    
    // Check if user dismissed install recently
    const dismissedTime = localStorage.getItem('easycash_install_dismissed');
    if (dismissedTime) {
        const sevenDays = 7 * 24 * 60 * 60 * 1000;
        const now = Date.now();
        if (now - parseInt(dismissedTime) < sevenDays) {
            hideInstallButton();
        } else {
            localStorage.removeItem('easycash_install_dismissed');
        }
    }
    
    // Quick amount buttons handler
    document.querySelectorAll('.quick-amount').forEach(button => {
        button.addEventListener('click', (e) => {
            const amount = e.target.dataset.amount || 
                          e.target.closest('.quick-amount').dataset.amount;
            const amountInput = document.querySelector('input[name="amount"]');
            if (amountInput) {
                amountInput.value = amount;
                amountInput.focus();
                amountInput.dispatchEvent(new Event('input', { bubbles: true }));
                
                // Add visual feedback
                const buttonEl = e.target.closest('.quick-amount');
                buttonEl.style.transform = 'scale(0.95)';
                setTimeout(() => {
                    buttonEl.style.transform = '';
                }, 150);
            }
        });
    });
    
    // PIN input auto-focus and auto-submit - ONLY for non-PIN setup pages
    if (!isPinSetupPage) {
        const pinInputs = document.querySelectorAll('input[type="password"][maxlength="6"]');
        pinInputs.forEach(input => {
            // Check if we're on a page with PIN confirmation (has both PIN and confirm PIN)
            const hasConfirmPin = document.querySelector('input[name="confirm_pin"]');
            
            if (!hasConfirmPin && input.name === 'pin') {
                // Only auto-submit for single PIN pages (like PIN entry)
                input.addEventListener('input', (e) => {
                    if (e.target.value.length === 6) {
                        // Auto-submit after short delay
                        setTimeout(() => {
                            if (e.target.form && e.target.form.checkValidity()) {
                                showToast('Processing...', 'info');
                                e.target.form.submit();
                            }
                        }, 300);
                    }
                });
            }
        });
    }
    
    // Amount input formatting
    document.addEventListener('input', (e) => {
        if (e.target.type === 'number' && e.target.name === 'amount') {
            formatAmountInput(e.target);
        }
    });
    
    // Session timer for authenticated pages
    if (document.querySelector('.dashboard') || 
        document.querySelector('.transaction-container') ||
        document.querySelector('.profile-container') ||
        document.querySelector('.transactions-container') ||
        document.querySelector('.send-money-container')) {
        
        startSessionTimer();
        
        // Reset timer on user activity
        ['click', 'keypress', 'mousemove', 'scroll', 'touchstart'].forEach(event => {
            document.addEventListener(event, resetSessionTimer, { passive: true });
        });
    }
    
    // Network status
    updateNetworkStatus();
    window.addEventListener('online', () => {
        showToast('You are back online', 'success');
    });
    
    window.addEventListener('offline', () => {
        showToast('You are offline. Some features may not work.', 'warning');
    });
    
    // Prevent form resubmission
    if (window.history.replaceState && window.performance.navigation.type === 1) {
        window.history.replaceState(null, null, window.location.href);
    }
    
    // Show install button after delay if available
    setTimeout(() => {
        if (deferredPrompt && !checkIfInstalled() && !installShown) {
            showInstallButton();
        }
    }, 5000);
    
    // Add loading spinner to buttons during form submission
    document.addEventListener('submit', function(e) {
        const form = e.target;
        const submitButton = form.querySelector('button[type="submit"]');
        
        if (submitButton && !submitButton.disabled) {
            const originalText = submitButton.innerHTML;
            submitButton.disabled = true;
            submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
            
            // Re-enable button if form submission fails
            setTimeout(() => {
                if (submitButton.disabled) {
                    submitButton.disabled = false;
                    submitButton.innerHTML = originalText;
                }
            }, 5000);
        }
    });
    
    // Add global event listeners for common actions
    document.addEventListener('click', function(e) {
        // Refresh balance button
        if (e.target.closest('#refreshBalance')) {
            e.preventDefault();
            refreshBalance();
        }
        
        // Quick 500 withdraw button
        if (e.target.closest('#quick500')) {
            e.preventDefault();
            quickSend(500, '', 'withdraw');
        }
        
        // Export transactions button
        if (e.target.closest('#exportBtn')) {
            e.preventDefault();
            exportTransactions();
        }
        
        // Copy text to clipboard
        if (e.target.closest('[data-copy]') || e.target.hasAttribute('data-copy')) {
            e.preventDefault();
            const textToCopy = e.target.getAttribute('data-copy') || 
                              e.target.closest('[data-copy]').getAttribute('data-copy') ||
                              e.target.textContent;
            copyToClipboard(textToCopy);
        }
        
        // Send back button in transaction list
        if (e.target.closest('.send-back-btn')) {
            e.preventDefault();
            const username = e.target.closest('.send-back-btn').dataset.username;
            const amount = prompt(`Amount to send back to ${username}:`, '100');
            if (amount && !isNaN(amount) && parseFloat(amount) > 0) {
                quickSend(amount, username, 'contact');
            }
        }
        
        // Resend button in transaction list
        if (e.target.closest('.resend-btn')) {
            e.preventDefault();
            const identifier = e.target.closest('.resend-btn').dataset.identifier;
            const method = e.target.closest('.resend-btn').dataset.method;
            const amount = prompt(`Amount to send to ${identifier}:`, '100');
            if (amount && !isNaN(amount) && parseFloat(amount) > 0) {
                quickSend(amount, identifier, method);
            }
        }
    });
    
    // Auto-save form data for send money
    const sendMoneyForm = document.querySelector('#sendMoneyForm');
    if (sendMoneyForm) {
        setupAutoSave('#sendMoneyForm', 'easycash_send_money_draft');
        
        // Validate recipient on identifier input
        const identifierInput = sendMoneyForm.querySelector('input[name="identifier"]');
        if (identifierInput) {
            let validateTimeout;
            identifierInput.addEventListener('input', function() {
                clearTimeout(validateTimeout);
                const identifier = this.value.trim();
                const method = sendMoneyForm.querySelector('input[name="payment_method"]').value;
                
                if (identifier.length >= 3) {
                    validateTimeout = setTimeout(async () => {
                        const result = await validateRecipient(method, identifier);
                        if (result.valid) {
                            showToast('Recipient validated', 'success');
                        } else {
                            showToast(result.error || 'Invalid recipient', 'error');
                        }
                    }, 500);
                }
            });
        }
    }
});

// PWA Event Listeners (must be at top level, not inside DOMContentLoaded)
window.addEventListener('beforeinstallprompt', (e) => {
    // Prevent Chrome 67 and earlier from automatically showing the prompt
    e.preventDefault();
    deferredPrompt = e;
    console.log('beforeinstallprompt event fired');
    
    // Only show if not already installed
    if (!checkIfInstalled()) {
        // Show after a delay
        setTimeout(() => {
            if (deferredPrompt && !installShown) {
                showInstallButton();
            }
        }, 3000);
    }
});

window.addEventListener('appinstalled', (evt) => {
    console.log('EasyCash was installed');
    hideInstallButton();
    deferredPrompt = null;
    
    // Track installation in localStorage
    localStorage.setItem('easycash_installed', 'true');
    localStorage.removeItem('easycash_install_dismissed');
});

// Detect display mode changes
if (window.matchMedia) {
    window.matchMedia('(display-mode: standalone)').addEventListener('change', (evt) => {
        if (evt.matches) {
            console.log('Switched to standalone mode');
            hideInstallButton();
        }
    });
}

// Detect when app is launched from home screen (iOS)
window.addEventListener('load', function() {
    if (window.navigator.standalone) {
        console.log('Launched from home screen (iOS)');
        hideInstallButton();
    }
});

// Error handling for API calls
function handleApiError(error) {
    console.error('API Error:', error);
    showToast('Something went wrong. Please try again.', 'error');
    
    if (error.status === 401) {
        // Unauthorized - redirect to login
        setTimeout(() => {
            window.location.href = '/logout';
        }, 2000);
    }
}

// API helper function
async function apiCall(url, options = {}) {
    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        handleApiError(error);
        throw error;
    }
}

// Debounce function for performance
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Throttle function for performance
function throttle(func, limit) {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// Input validation helper
function validateInput(input, rules) {
    const value = input.value.trim();
    let isValid = true;
    let errorMessage = '';
    
    if (rules.required && !value) {
        isValid = false;
        errorMessage = 'This field is required';
    }
    
    if (rules.minLength && value.length < rules.minLength) {
        isValid = false;
        errorMessage = `Minimum ${rules.minLength} characters required`;
    }
    
    if (rules.maxLength && value.length > rules.maxLength) {
        isValid = false;
        errorMessage = `Maximum ${rules.maxLength} characters allowed`;
    }
    
    if (rules.pattern && !rules.pattern.test(value)) {
        isValid = false;
        errorMessage = rules.errorMessage || 'Invalid format';
    }
    
    if (rules.type === 'email' && value) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(value)) {
            isValid = false;
            errorMessage = 'Please enter a valid email address';
        }
    }
    
    if (rules.type === 'number' && value) {
        if (isNaN(value) || parseFloat(value) < 0) {
            isValid = false;
            errorMessage = 'Please enter a valid number';
        }
    }
    
    if (rules.type === 'mobile' && value) {
        if (!/^[6-9]\d{9}$/.test(value)) {
            isValid = false;
            errorMessage = 'Please enter a valid 10-digit mobile number';
        }
    }
    
    if (rules.type === 'upi' && value) {
        if (!/^[\w\.-]+@[\w\.-]+$/.test(value)) {
            isValid = false;
            errorMessage = 'Please enter a valid UPI ID (e.g., name@bank)';
        }
    }
    
    return { isValid, errorMessage };
}

// Form validation with visual feedback
function setupFormValidation(formSelector, validationRules) {
    const form = document.querySelector(formSelector);
    if (!form) return;
    
    form.addEventListener('submit', function(e) {
        let isValid = true;
        
        Object.keys(validationRules).forEach(fieldName => {
            const input = form.querySelector(`[name="${fieldName}"]`);
            const rules = validationRules[fieldName];
            
            if (input) {
                const validation = validateInput(input, rules);
                
                if (!validation.isValid) {
                    isValid = false;
                    
                    // Show error
                    input.classList.add('error');
                    
                    // Show error message
                    let errorElement = input.nextElementSibling;
                    if (!errorElement || !errorElement.classList.contains('error-message')) {
                        errorElement = document.createElement('div');
                        errorElement.className = 'error-message';
                        input.parentNode.insertBefore(errorElement, input.nextSibling);
                    }
                    errorElement.textContent = validation.errorMessage;
                    errorElement.style.display = 'block';
                } else {
                    // Clear error
                    input.classList.remove('error');
                    
                    // Hide error message
                    const errorElement = input.nextElementSibling;
                    if (errorElement && errorElement.classList.contains('error-message')) {
                        errorElement.style.display = 'none';
                    }
                }
            }
        });
        
        if (!isValid) {
            e.preventDefault();
            showToast('Please fix the errors in the form', 'error');
        }
    });
    
    // Clear errors on input
    Object.keys(validationRules).forEach(fieldName => {
        const input = form.querySelector(`[name="${fieldName}"]`);
        if (input) {
            input.addEventListener('input', function() {
                this.classList.remove('error');
                const errorElement = this.nextElementSibling;
                if (errorElement && errorElement.classList.contains('error-message')) {
                    errorElement.style.display = 'none';
                }
            });
        }
    });
}

// Auto-save form data
function setupAutoSave(formSelector, storageKey) {
    const form = document.querySelector(formSelector);
    if (!form) return;
    
    // Load saved data
    const savedData = localStorage.getItem(storageKey);
    if (savedData) {
        try {
            const data = JSON.parse(savedData);
            Object.keys(data).forEach(fieldName => {
                const input = form.querySelector(`[name="${fieldName}"]`);
                if (input) {
                    input.value = data[fieldName];
                }
            });
        } catch (e) {
            console.error('Error loading saved form data:', e);
        }
    }
    
    // Save on input
    const saveData = debounce(function() {
        const formData = new FormData(form);
        const data = {};
        formData.forEach((value, key) => {
            data[key] = value;
        });
        localStorage.setItem(storageKey, JSON.stringify(data));
    }, 500);
    
    form.addEventListener('input', saveData);
    
    // Clear on successful submit
    form.addEventListener('submit', function() {
        localStorage.removeItem(storageKey);
    });
}

// Initialize common form validations
document.addEventListener('DOMContentLoaded', function() {
    // Login form validation
    setupFormValidation('#loginForm', {
        username: { required: true, minLength: 3 },
        password: { required: true, minLength: 6 }
    });
    
    // Registration form validation
    setupFormValidation('#registerForm', {
        username: { required: true, minLength: 3, maxLength: 50 },
        email: { required: true, type: 'email' },
        password: { required: true, minLength: 8 },
        confirm_password: { required: true }
    });
    
    // Send money form validation
    setupFormValidation('#sendMoneyForm', {
        identifier: { required: true, minLength: 3 },
        amount: { required: true, type: 'number', min: 1 },
        pin: { required: true, minLength: 6, maxLength: 6, pattern: /^\d{6}$/ }
    });
    
    // Setup auto-save for transaction forms
    setupAutoSave('#transactionForm', 'easycash_transaction_draft');
    
    // Check for unsaved changes
    window.addEventListener('beforeunload', function(e) {
        const hasDraft = localStorage.getItem('easycash_send_money_draft') || 
                        localStorage.getItem('easycash_transaction_draft');
        if (hasDraft) {
            e.preventDefault();
            e.returnValue = 'You have unsaved transaction data. Are you sure you want to leave?';
        }
    });
    
    // Add CSS for error styling
    const errorStyles = document.createElement('style');
    errorStyles.textContent = `
        input.error {
            border-color: #e74c3c !important;
            box-shadow: 0 0 0 2px rgba(231, 76, 60, 0.2) !important;
        }
        
        .error-message {
            color: #e74c3c;
            font-size: 12px;
            margin-top: 5px;
            display: none;
        }
        
        .payment-method-selector {
            display: flex;
            gap: 10px;
            margin: 15px 0;
        }
        
        .method-option {
            flex: 1;
            text-align: center;
            padding: 15px 10px;
            background: var(--dark-surface);
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.3s ease;
            border: 2px solid transparent;
        }
        
        .method-option:hover {
            background: var(--dark-surface-light);
            transform: translateY(-2px);
        }
        
        .method-option.active {
            border-color: var(--primary-color);
            background: var(--dark-surface-light);
        }
        
        .method-option i {
            font-size: 24px;
            margin-bottom: 8px;
            display: block;
        }
        
        .method-option.mobile i { color: #34a853; }
        .method-option.upi i { color: #4285f4; }
        .method-option.contact i { color: #ea4335; }
        .method-option.bank i { color: #9b59b6; }
    `;
    document.head.appendChild(errorStyles);
});

// Password strength checker
function checkPasswordStrength(password) {
    let score = 0;
    let feedback = [];
    
    if (password.length >= 8) score += 1;
    else feedback.push('At least 8 characters');
    
    if (/[A-Z]/.test(password)) score += 1;
    else feedback.push('One uppercase letter');
    
    if (/[a-z]/.test(password)) score += 1;
    else feedback.push('One lowercase letter');
    
    if (/[0-9]/.test(password)) score += 1;
    else feedback.push('One number');
    
    if (/[^A-Za-z0-9]/.test(password)) score += 1;
    else feedback.push('One special character');
    
    let strength = 'Weak';
    let color = '#ea4335';
    
    if (score >= 4) {
        strength = 'Strong';
        color = '#34a853';
    } else if (score >= 3) {
        strength = 'Good';
        color = '#fbbc04';
    } else if (score >= 2) {
        strength = 'Fair';
        color = '#f57c00';
    }
    
    return { score, strength, color, feedback };
}

// Initialize password strength indicator
document.addEventListener('DOMContentLoaded', function() {
    const passwordInput = document.querySelector('input[type="password"][name="password"]');
    const confirmPasswordInput = document.querySelector('input[type="password"][name="confirm_password"]');
    
    if (passwordInput) {
        const strengthIndicator = document.createElement('div');
        strengthIndicator.className = 'password-strength';
        strengthIndicator.style.cssText = `
            margin-top: 5px;
            font-size: 12px;
            height: 20px;
            display: flex;
            align-items: center;
        `;
        
        passwordInput.parentNode.insertBefore(strengthIndicator, passwordInput.nextSibling);
        
        passwordInput.addEventListener('input', function() {
            const password = this.value;
            const strength = checkPasswordStrength(password);
            
            strengthIndicator.textContent = `Strength: ${strength.strength}`;
            strengthIndicator.style.color = strength.color;
            
            // Show/hide feedback
            if (password && strength.feedback.length > 0) {
                const feedbackText = strength.feedback.join(', ');
                strengthIndicator.title = `Needs: ${feedbackText}`;
            }
            
            // Validate password match
            if (confirmPasswordInput && confirmPasswordInput.value) {
                if (password !== confirmPasswordInput.value) {
                    confirmPasswordInput.classList.add('error');
                } else {
                    confirmPasswordInput.classList.remove('error');
                }
            }
        });
    }
    
    if (confirmPasswordInput && passwordInput) {
        confirmPasswordInput.addEventListener('input', function() {
            if (this.value !== passwordInput.value) {
                this.classList.add('error');
            } else {
                this.classList.remove('error');
            }
        });
    }
});