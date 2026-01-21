// static/js/notifications.js
class NotificationManager {
    constructor() {
        this.unreadCount = 0;
        this.checkInterval = 30000; // Check every 30 seconds
        this.selectedNotifications = new Set();
        this.bulkActions = document.getElementById('bulkActions');
        this.init();
    }
    
    async init() {
        // Check for service worker support
        if ('serviceWorker' in navigator && 'PushManager' in window) {
            await this.registerServiceWorker();
            await this.requestNotificationPermission();
            this.startPolling();
        } else {
            console.log('Push notifications not supported');
        }
        
        // Load initial notification count
        await this.updateBadge();
        
        // Initialize event listeners
        this.initEventListeners();
        
        // Check for new notifications on page load
        this.checkForNewNotifications();
    }
    
    async registerServiceWorker() {
        try {
            const registration = await navigator.serviceWorker.register('/service-worker.js');
            console.log('ServiceWorker registered:', registration);
            this.serviceWorker = registration;
        } catch (error) {
            console.error('ServiceWorker registration failed:', error);
        }
    }
    
    async requestNotificationPermission() {
        if (Notification.permission === 'granted') {
            return true;
        } else if (Notification.permission === 'default') {
            const permission = await Notification.requestPermission();
            return permission === 'granted';
        }
        return false;
    }
    
    startPolling() {
        // Check for new notifications periodically
        setInterval(() => {
            this.checkForNewNotifications();
        }, this.checkInterval);
        
        // Also check when page becomes visible
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                this.checkForNewNotifications();
            }
        });
    }
    
    async checkForNewNotifications() {
        try {
            const response = await fetch('/api/notifications?unread_only=true&limit=1');
            const data = await response.json();
            
            if (data.success && data.notifications.length > 0) {
                const latestNotification = data.notifications[0];
                
                // Check if we've already shown this notification
                const lastShownId = localStorage.getItem('lastShownNotificationId');
                if (lastShownId !== latestNotification.id.toString()) {
                    this.showBrowserNotification(latestNotification);
                    localStorage.setItem('lastShownNotificationId', latestNotification.id);
                }
            }
            
            await this.updateBadge();
        } catch (error) {
            console.error('Error checking notifications:', error);
        }
    }
    
    showBrowserNotification(notification) {
        if (Notification.permission === 'granted' && !document.hidden) {
            // Only show if user is not actively on the notifications page
            const isOnNotificationsPage = window.location.pathname.includes('/notifications');
            
            if (!isOnNotificationsPage) {
                const notif = new Notification(notification.title, {
                    body: notification.message,
                    icon: '/static/icon-192.png',
                    tag: 'easycash-notification',
                    badge: '/static/icon-192.png',
                    data: notification
                });
                
                notif.onclick = () => {
                    window.focus();
                    window.location.href = '/notifications';
                    notif.close();
                };
                
                // Play notification sound if enabled
                this.playNotificationSound();
            }
        }
    }
    
    playNotificationSound() {
        // Check if sound is enabled
        const soundEnabled = localStorage.getItem('notificationSound') !== 'false';
        if (!soundEnabled) return;
        
        try {
            const audio = new Audio('/static/sounds/notification.mp3');
            audio.volume = 0.3;
            audio.play().catch(e => console.log('Could not play notification sound:', e));
        } catch (e) {
            console.log('Notification sound not available');
        }
    }
    
    async updateBadge() {
        try {
            const response = await fetch('/api/notifications/count');
            const data = await response.json();
            
            if (data.success) {
                this.unreadCount = data.count;
                this.updateBadgeUI();
            }
        } catch (error) {
            console.error('Error updating badge:', error);
        }
    }
    
    updateBadgeUI() {
        // Update badge in navbar
        const badge = document.getElementById('notification-badge');
        if (badge) {
            if (this.unreadCount > 0) {
                badge.textContent = this.unreadCount > 99 ? '99+' : this.unreadCount.toString();
                badge.style.display = 'flex';
            } else {
                badge.style.display = 'none';
            }
        }
        
        // Update browser tab title if there are unread notifications
        if (this.unreadCount > 0) {
            document.title = `(${this.unreadCount}) EasyCash`;
        } else {
            document.title = 'EasyCash';
        }
        
        // Update statistics if on notifications page
        this.updateStatistics();
    }
    
    async updateStatistics() {
        // Only update if on notifications page
        if (!window.location.pathname.includes('/notifications')) return;
        
        try {
            const response = await fetch('/api/notifications');
            const data = await response.json();
            
            if (data.success) {
                const notifications = data.notifications || [];
                
                // Calculate statistics
                const total = notifications.length;
                const unread = notifications.filter(n => !n.is_read).length;
                const read = notifications.filter(n => n.is_read).length;
                
                // Update stat cards
                this.updateStatCard('total', total);
                this.updateStatCard('unread', unread);
                this.updateStatCard('read', read);
            }
        } catch (error) {
            console.error('Error updating statistics:', error);
        }
    }
    
    updateStatCard(type, count) {
        const statCard = document.querySelector(`.stat-card.${type} .stat-number`);
        if (statCard) {
            statCard.textContent = count;
        }
    }
    
    initEventListeners() {
        // Mark as read buttons
        document.addEventListener('click', (e) => {
            const markReadBtn = e.target.closest('.mark-read-btn');
            if (markReadBtn) {
                const card = markReadBtn.closest('.notification-card');
                const notificationId = card.dataset.id;
                this.markAsRead(notificationId, card);
            }
        });
        
        // Delete buttons
        document.addEventListener('click', (e) => {
            const deleteBtn = e.target.closest('.delete-btn');
            if (deleteBtn) {
                const card = deleteBtn.closest('.notification-card');
                const notificationId = card.dataset.id;
                this.deleteNotification(notificationId, card);
            }
        });
        
        // Filter buttons
        document.addEventListener('click', (e) => {
            const filterBtn = e.target.closest('.filter-btn');
            if (filterBtn) {
                this.filterNotifications(filterBtn.dataset.filter);
            }
        });
        
        // Mark all as read
        const markAllReadBtn = document.getElementById('mark-all-read');
        if (markAllReadBtn) {
            markAllReadBtn.addEventListener('click', () => this.markAllAsRead());
        }
        
        // Delete all read
        const deleteReadBtn = document.getElementById('delete-read');
        if (deleteReadBtn) {
            deleteReadBtn.addEventListener('click', () => this.deleteAllRead());
        }
        
        // Quick action buttons
        document.addEventListener('click', (e) => {
            const quickActionBtn = e.target.closest('.quick-action-btn');
            if (quickActionBtn) {
                this.handleQuickAction(quickActionBtn.dataset.action);
            }
        });
        
        // Checkbox selection
        document.addEventListener('change', (e) => {
            const checkbox = e.target.closest('.notification-select input[type="checkbox"]');
            if (checkbox) {
                this.handleSelection(checkbox);
            }
        });
        
        // Select all checkbox
        const selectAllCheckbox = document.getElementById('selectAllNotifications');
        if (selectAllCheckbox) {
            selectAllCheckbox.addEventListener('change', (e) => {
                this.handleSelectAll(e.target.checked);
            });
        }
        
        // Bulk action buttons
        document.addEventListener('click', (e) => {
            if (e.target.closest('#bulkMarkRead')) {
                this.bulkMarkAsRead();
            } else if (e.target.closest('#bulkDelete')) {
                this.bulkDelete();
            } else if (e.target.closest('#bulkCancel')) {
                this.clearSelection();
            }
        });
    }
    
    async markAsRead(notificationId, card) {
        try {
            const response = await fetch(`/api/notifications/${notificationId}/read`, {
                method: 'POST'
            });
            const data = await response.json();
            
            if (data.success) {
                // Update UI
                card.classList.remove('unread');
                const markReadBtn = card.querySelector('.mark-read-btn');
                if (markReadBtn) markReadBtn.remove();
                
                // Update unread count
                this.unreadCount = data.unread_count || 0;
                this.updateBadgeUI();
                
                // Show success message
                this.showToast('Notification marked as read', 'success');
            }
        } catch (error) {
            console.error('Error marking notification as read:', error);
            this.showToast('Failed to mark as read', 'error');
        }
    }
    
    async deleteNotification(notificationId, card) {
        if (!confirm('Are you sure you want to delete this notification?')) {
            return;
        }
        
        try {
            const response = await fetch(`/api/notifications/${notificationId}`, {
                method: 'DELETE'
            });
            const data = await response.json();
            
            if (data.success) {
                // Remove from UI with animation
                card.style.transition = 'all 0.3s ease';
                card.style.opacity = '0';
                card.style.transform = 'translateX(-100%)';
                
                setTimeout(() => {
                    card.remove();
                    
                    // Update unread count
                    this.unreadCount = data.unread_count || 0;
                    this.updateBadgeUI();
                    
                    // Show success message
                    this.showToast('Notification deleted', 'success');
                    
                    // Check if no notifications left
                    if (document.querySelectorAll('.notification-card').length === 0) {
                        this.showEmptyState();
                    }
                }, 300);
            }
        } catch (error) {
            console.error('Error deleting notification:', error);
            this.showToast('Failed to delete notification', 'error');
        }
    }
    
    filterNotifications(filter) {
        const cards = document.querySelectorAll('.notification-card');
        const filterBtns = document.querySelectorAll('.filter-btn');
        
        // Update active button
        filterBtns.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.filter === filter);
        });
        
        // Show/hide cards based on filter
        cards.forEach(card => {
            switch (filter) {
                case 'all':
                    card.style.display = 'flex';
                    break;
                case 'unread':
                    card.style.display = card.classList.contains('unread') ? 'flex' : 'none';
                    break;
                case 'transaction':
                    const type = card.dataset.type;
                    card.style.display = ['success', 'info'].includes(type) ? 'flex' : 'none';
                    break;
                case 'security':
                    const securityType = card.dataset.type;
                    card.style.display = ['warning', 'danger'].includes(securityType) ? 'flex' : 'none';
                    break;
                default:
                    card.style.display = 'flex';
            }
        });
    }
    
    async markAllAsRead() {
        if (!confirm('Mark all notifications as read?')) {
            return;
        }
        
        try {
            const response = await fetch('/api/notifications/read-all', {
                method: 'POST'
            });
            const data = await response.json();
            
            if (data.success) {
                // Update all cards
                document.querySelectorAll('.notification-card.unread').forEach(card => {
                    card.classList.remove('unread');
                    const markReadBtn = card.querySelector('.mark-read-btn');
                    if (markReadBtn) markReadBtn.remove();
                });
                
                // Update unread count
                this.unreadCount = 0;
                this.updateBadgeUI();
                
                // Show success message
                this.showToast('All notifications marked as read', 'success');
            }
        } catch (error) {
            console.error('Error marking all as read:', error);
            this.showToast('Failed to mark all as read', 'error');
        }
    }
    
    async deleteAllRead() {
        if (!confirm('Delete all read notifications? This action cannot be undone.')) {
            return;
        }
        
        try {
            const response = await fetch('/api/notifications/delete-read', {
                method: 'DELETE'
            });
            const data = await response.json();
            
            if (data.success) {
                // Remove all read cards with animation
                const readCards = document.querySelectorAll('.notification-card:not(.unread)');
                readCards.forEach((card, index) => {
                    setTimeout(() => {
                        card.style.transition = 'all 0.3s ease';
                        card.style.opacity = '0';
                        card.style.transform = 'translateX(-100%)';
                        
                        setTimeout(() => {
                            card.remove();
                            
                            // Check if no notifications left
                            if (document.querySelectorAll('.notification-card').length === 0) {
                                this.showEmptyState();
                            }
                        }, 300);
                    }, index * 50); // Stagger animations
                });
                
                // Show success message
                this.showToast('Read notifications deleted', 'success');
            }
        } catch (error) {
            console.error('Error deleting read notifications:', error);
            this.showToast('Failed to delete read notifications', 'error');
        }
    }
    
    handleQuickAction(action) {
        switch (action) {
            case 'clear':
                this.deleteAllRead();
                break;
            case 'refresh':
                this.refreshNotifications();
                break;
            case 'settings':
                window.location.href = '/profile#notifications';
                break;
        }
    }
    
    async refreshNotifications() {
        try {
            // Show loading state
            const container = document.getElementById('notifications-container');
            const originalContent = container.innerHTML;
            container.innerHTML = `
                <div class="loading-state">
                    <div class="loading-spinner"></div>
                    <p>Loading notifications...</p>
                </div>
            `;
            
            // Reload page after a short delay
            setTimeout(() => {
                window.location.reload();
            }, 500);
            
        } catch (error) {
            console.error('Error refreshing notifications:', error);
            this.showToast('Failed to refresh notifications', 'error');
        }
    }
    
    showEmptyState() {
        const container = document.getElementById('notifications-container');
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">
                    <i class="fas fa-bell-slash"></i>
                </div>
                <h3>No notifications</h3>
                <p>You're all caught up! Check back later for updates.</p>
            </div>
        `;
    }
    
    handleSelection(checkbox) {
        const card = checkbox.closest('.notification-card');
        const notificationId = card.dataset.id;
        
        if (checkbox.checked) {
            this.selectedNotifications.add(notificationId);
        } else {
            this.selectedNotifications.delete(notificationId);
        }
        
        this.updateBulkActions();
    }
    
    handleSelectAll(checked) {
        const checkboxes = document.querySelectorAll('.notification-select input[type="checkbox"]');
        checkboxes.forEach(checkbox => {
            checkbox.checked = checked;
            const card = checkbox.closest('.notification-card');
            const notificationId = card.dataset.id;
            
            if (checked) {
                this.selectedNotifications.add(notificationId);
            } else {
                this.selectedNotifications.delete(notificationId);
            }
        });
        
        this.updateBulkActions();
    }
    
    updateBulkActions() {
        const selectedCount = this.selectedNotifications.size;
        
        if (selectedCount > 0) {
            // Show bulk actions
            this.bulkActions.classList.add('show');
            document.getElementById('selectedCount').textContent = selectedCount;
        } else {
            // Hide bulk actions
            this.bulkActions.classList.remove('show');
        }
    }
    
    clearSelection() {
        this.selectedNotifications.clear();
        const checkboxes = document.querySelectorAll('.notification-select input[type="checkbox"]');
        checkboxes.forEach(checkbox => {
            checkbox.checked = false;
        });
        
        this.updateBulkActions();
        this.showToast('Selection cleared', 'info');
    }
    
    async bulkMarkAsRead() {
        if (this.selectedNotifications.size === 0) return;
        
        try {
            const promises = Array.from(this.selectedNotifications).map(id => 
                fetch(`/api/notifications/${id}/read`, { method: 'POST' })
            );
            
            await Promise.all(promises);
            
            // Update UI
            Array.from(this.selectedNotifications).forEach(id => {
                const card = document.querySelector(`.notification-card[data-id="${id}"]`);
                if (card) {
                    card.classList.remove('unread');
                    const markReadBtn = card.querySelector('.mark-read-btn');
                    if (markReadBtn) markReadBtn.remove();
                }
            });
            
            // Clear selection
            this.clearSelection();
            
            // Update count
            await this.updateBadge();
            
            this.showToast('Selected notifications marked as read', 'success');
            
        } catch (error) {
            console.error('Error bulk marking as read:', error);
            this.showToast('Failed to mark selected as read', 'error');
        }
    }
    
    async bulkDelete() {
        if (this.selectedNotifications.size === 0) return;
        
        if (!confirm(`Delete ${this.selectedNotifications.size} selected notifications? This action cannot be undone.`)) {
            return;
        }
        
        try {
            const promises = Array.from(this.selectedNotifications).map(id => 
                fetch(`/api/notifications/${id}`, { method: 'DELETE' })
            );
            
            await Promise.all(promises);
            
            // Remove from UI with animation
            Array.from(this.selectedNotifications).forEach((id, index) => {
                setTimeout(() => {
                    const card = document.querySelector(`.notification-card[data-id="${id}"]`);
                    if (card) {
                        card.style.transition = 'all 0.3s ease';
                        card.style.opacity = '0';
                        card.style.transform = 'translateX(-100%)';
                        
                        setTimeout(() => {
                            card.remove();
                            
                            // Check if no notifications left
                            if (document.querySelectorAll('.notification-card').length === 0) {
                                this.showEmptyState();
                            }
                        }, 300);
                    }
                }, index * 50); // Stagger animations
            });
            
            // Clear selection
            this.clearSelection();
            
            // Update count
            await this.updateBadge();
            
            this.showToast('Selected notifications deleted', 'success');
            
        } catch (error) {
            console.error('Error bulk deleting:', error);
            this.showToast('Failed to delete selected notifications', 'error');
        }
    }
    
    showToast(message, type = 'info') {
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast-notification ${type}`;
        toast.innerHTML = `
            <i class="fas fa-${this.getToastIcon(type)}"></i>
            <span>${message}</span>
        `;
        
        // Add to page
        document.body.appendChild(toast);
        
        // Show with animation
        setTimeout(() => {
            toast.style.display = 'flex';
        }, 10);
        
        // Hide after 3 seconds
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(-50%) translateY(-20px)';
            
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 3000);
    }
    
    getToastIcon(type) {
        switch (type) {
            case 'success': return 'check-circle';
            case 'error': return 'exclamation-circle';
            case 'warning': return 'exclamation-triangle';
            case 'info': return 'info-circle';
            default: return 'bell';
        }
    }
}

// Initialize notification manager when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize if user is authenticated (on notifications page)
    if (document.querySelector('.notification-page')) {
        window.notificationManager = new NotificationManager();
        
        // Initialize tooltips
        this.initTooltips();
    }
});

// Tooltip initialization
function initTooltips() {
    const tooltipElements = document.querySelectorAll('[data-tooltip]');
    
    tooltipElements.forEach(element => {
        element.addEventListener('mouseenter', (e) => {
            const tooltip = document.createElement('div');
            tooltip.className = 'tooltip';
            tooltip.textContent = e.target.dataset.tooltip;
            
            // Position tooltip
            const rect = e.target.getBoundingClientRect();
            tooltip.style.position = 'fixed';
            tooltip.style.left = `${rect.left + rect.width / 2}px`;
            tooltip.style.top = `${rect.top - 10}px`;
            tooltip.style.transform = 'translate(-50%, -100%)';
            
            // Style tooltip
            tooltip.style.background = 'var(--dark-surface)';
            tooltip.style.color = 'var(--dark-text)';
            tooltip.style.padding = '8px 12px';
            tooltip.style.borderRadius = '6px';
            tooltip.style.fontSize = '0.85rem';
            tooltip.style.boxShadow = 'var(--shadow-md)';
            tooltip.style.zIndex = '9999';
            tooltip.style.whiteSpace = 'nowrap';
            tooltip.style.border = '1px solid var(--border-color)';
            
            document.body.appendChild(tooltip);
            
            e.target._tooltip = tooltip;
        });
        
        element.addEventListener('mouseleave', (e) => {
            if (e.target._tooltip) {
                e.target._tooltip.remove();
                delete e.target._tooltip;
            }
        });
    });
}