# EasyCash - ATM-Style Digital Wallet

A Progressive Web App (PWA) that mimics an ATM-style digital wallet with Google Pay-inspired UI/UX.

## Features

### 🎨 UI/UX
- Google Pay-style design with dark mode
- Mobile-first responsive design
- Smooth animations and transitions
- Material Design icons
- Bottom navigation bar
- Toast notifications

### 🔐 Authentication
- Username-based identification
- 6-digit PIN security
- PIN setup for new users
- PIN entry for returning users
- Secure PIN hashing with Werkzeug
- PIN attempt limiting (5 attempts max)

### 💰 ATM Features
- Check balance
- Deposit money
- Withdraw money
- Transaction history
- Quick amount buttons (₹500, ₹1000, ₹2000)

### 📱 PWA Features
- Installable on mobile devices
- Offline support
- Service worker for caching
- App manifest with icons
- Splash screen support

### 🛡️ Security
- Session-based authentication
- 15-minute session timeout
- Input validation
- SQL injection prevention
- Secure password hashing
- Local data storage only

## Installation

1. Clone or download the project
2. Create virtual environment (optional):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate