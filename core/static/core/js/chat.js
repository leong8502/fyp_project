/**
 * Chat WebSocket Management
 * Handles real-time messaging via WebSocket connections
 */

// Global configuration (set by Django template)
FIND_URL;
FIND_TEXT;
// CSRF Token retrieval
let CSRF_TOKEN;

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Initialize CSRF token
CSRF_TOKEN = getCookie('csrftoken');

// Initialize chat when DOM is ready
document.addEventListener('DOMContentLoaded', function () {
    const contactListEl = document.getElementById('contact-list');
    const messagesAreaEl = document.getElementById('messages-area');
    const chatHeader = document.getElementById('chat-header');
    const chatInputArea = document.getElementById('chat-input-area');
    const messageInput = document.getElementById('message-input');
    const btnSend = document.getElementById('btn-send');
    const btnMoreOptions = document.getElementById('btn-more-options');
    const headerDropdown = document.getElementById('header-dropdown');
    const btnMute = document.getElementById('btn-mute');

    let currentConversationId = null;
    let chatSocket = null;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;

    // --- WebSocket Management ---
    function connectWebSocket(conversationId) {
        // Close existing connection if any
        if (chatSocket) {
            chatSocket.close();
        }

        // Determine WebSocket protocol (ws or wss)
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/chat/${conversationId}/`;

        chatSocket = new WebSocket(wsUrl);

        chatSocket.onopen = function (e) {
            console.log('WebSocket connected');
            reconnectAttempts = 0;
        };

        chatSocket.onmessage = function (e) {
            const data = JSON.parse(e.data);

            if (data.type === 'chat_message') {
                // New message received
                appendMessage(data.message);
                // Refresh conversation list to update last message
                loadConversations();
            } else if (data.type === 'messages_read') {
                // Messages were read by another user
                // Could update UI to show read receipts
            } else if (data.type === 'conversation_updated') {
                // Conversation list needs refresh
                loadConversations();
            }
        };

        chatSocket.onclose = function (e) {
            console.log('WebSocket disconnected', e.code, e.reason);

            // Don't reconnect if it was a clean close or authentication failure
            // Code 1000 = normal closure, 1006 = abnormal closure, 3000-3999 = custom codes
            if (e.code === 1000 || e.code === 3000) {
                console.log('WebSocket closed normally, not reconnecting');
                return;
            }

            // Attempt to reconnect
            if (reconnectAttempts < maxReconnectAttempts && currentConversationId) {
                reconnectAttempts++;
                console.log(`Reconnecting... Attempt ${reconnectAttempts}/${maxReconnectAttempts}`);
                setTimeout(() => {
                    if (currentConversationId) {
                        connectWebSocket(currentConversationId);
                    }
                }, 2000 * reconnectAttempts); // Exponential backoff
            } else {
                console.error('Max reconnection attempts reached or no conversation selected');
            }
        };

        chatSocket.onerror = function (err) {
            console.error('WebSocket error:', err);
        };
    }

    function loadConversations() {
        console.log('Loading conversations...');
        fetch("/api/chat/conversations/")
            .then(response => {
                console.log('Response received:', response.status);
                return response.json();
            })
            .then(data => {
                console.log('Conversations data:', data);
                contactListEl.innerHTML = '';
                if (data.length === 0) {
                    contactListEl.innerHTML = `
                        <div class="sidebar-empty-state">
                            <div class="empty-icon">📭</div>
                            <p>No conversations yet.</p>
                            <a href="${FIND_URL}" class="btn-find">${FIND_TEXT}</a>
                        </div>
                    `;
                    return;
                }

                data.forEach(chat => {
                    const div = document.createElement('div');
                    div.className = `contact-item ${chat.id == currentConversationId ? 'active' : ''}`;
                    div.dataset.id = chat.id;
                    div.dataset.name = chat.name;
                    div.dataset.avatar = chat.avatar;
                    div.dataset.role = chat.role;
                    div.dataset.tagline = chat.tagline;
                    div.dataset.muted = chat.is_muted;

                    div.innerHTML = `
                        <div class="contact-avatar">
                            <img src="${chat.avatar}" alt="${chat.name}">
                        </div>
                        <div class="contact-info">
                            <div class="contact-top">
                                <span class="contact-name">${chat.name}</span>
                                <span class="contact-time">${formatTime(chat.last_message_time)}</span>
                            </div>
                            <div class="contact-bottom">
                                <p class="contact-preview">${chat.last_message || ''}</p>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    ${chat.unread_count > 0 ? `<span class="unread-badge">${chat.unread_count}</span>` : ''}
                                    ${chat.is_muted ? '<i class="mute-icon-large fas fa-bell-slash"></i>' : ''}
                                </div>
                            </div>
                        </div>
                    `;

                    div.addEventListener('click', () => selectConversation(chat.id, chat));
                    contactListEl.appendChild(div);
                });
            })
            .catch(error => {
                console.error('Error loading conversations:', error);
                contactListEl.innerHTML = `
                    <div class="sidebar-empty-state">
                        <div class="empty-icon">⚠️</div>
                        <p>Error loading conversations</p>
                        <button onclick="loadConversations()" class="btn-find">Retry</button>
                    </div>
                `;
            });
    }

    // --- 2. Select Conversation ---
    function selectConversation(id, chatData) {
        currentConversationId = id;

        // Update UI Active State and immediately remove unread badge
        document.querySelectorAll('.contact-item').forEach(item => {
            item.classList.remove('active');
            if (item.dataset.id == id) {
                item.classList.add('active');
                // Immediately remove unread badge from UI
                const unreadBadge = item.querySelector('.unread-badge');
                if (unreadBadge) {
                    unreadBadge.remove();
                }
            }
        });

        // Show Chat Interface
        chatHeader.style.display = 'flex';
        chatInputArea.style.display = 'flex';

        // Update Header
        document.getElementById('header-name').textContent = chatData.name;
        document.getElementById('header-avatar').src = chatData.avatar;
        const taglineEl = document.getElementById('header-tagline');
        if (chatData.tagline) {
            taglineEl.textContent = chatData.tagline;
            taglineEl.style.display = 'block';
        } else {
            taglineEl.textContent = chatData.role || '';
            taglineEl.style.display = chatData.role ? 'block' : 'none';
        }
        updateMuteUI(chatData.is_muted);

        // Load Messages (History)
        loadMessages(id);

        // Connect to WebSocket for real-time updates
        connectWebSocket(id);

        // Update URL for persistence
        const url = new URL(window.location);
        url.searchParams.set('conversation_id', id);
        window.history.pushState({}, '', url);
    }

    // --- Search Functionality ---
    const contactSearchInput = document.getElementById('contact-search');
    contactSearchInput.addEventListener('input', (e) => {
        const term = e.target.value.toLowerCase();
        document.querySelectorAll('.contact-item').forEach(item => {
            const name = (item.dataset.name || '').toLowerCase();

            if (name.includes(term)) {
                item.style.display = 'flex';
            } else {
                item.style.display = 'none';
            }
        });
    });

    // --- Helper: Render Message Content ---
    function renderMessageHTML(msg, isMe) {
        let avatarHtml = '';
        if (!isMe) {
            avatarHtml = `
                <div class="message-avatar">
                    <img src="${msg.sender_avatar}" alt="${msg.sender_name}">
                </div>
            `;
        }

        // Handle message content and attachments
        let messageContent = '';
        if (msg.attachment) {
            const fileName = msg.original_filename || msg.attachment.split('/').pop();
            const downloadAttr = `download="${fileName}"`;

            if (msg.attachment_type === 'image') {
                // Image with download link wrapper
                messageContent = `<div style="position: relative; display: inline-block;"><img src="${msg.attachment}" alt="Image" style="max-width: 300px; max-height: 300px; border-radius: 8px; cursor: pointer; display: block;" onclick="window.open('${msg.attachment}', '_blank')"><a href="/api/chat/download/${msg.id}/" ${downloadAttr} target="_blank" style="position: absolute; bottom: 5px; right: 5px; background: rgba(0,0,0,0.6); color: white; border-radius: 50%; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; text-decoration: none;" title="Download"><i class="fas fa-download"></i></a></div>`;
            } else {
                // File attachment with download attribute
                const fileIcon = msg.attachment_type === 'pdf' ? '<i class="fas fa-file-alt"></i>' : '<i class="fas fa-paperclip"></i>';
                messageContent = `<a href="/api/chat/download/${msg.id}/" target="_blank" ${downloadAttr} style="color: inherit; text-decoration: none; display: flex; align-items: center; gap: 5px; background: rgba(0,0,0,0.05); padding: 5px 10px; border-radius: 5px;"><span style="font-size: 1.2em;">${fileIcon}</span><span style="text-decoration: underline;">${fileName}</span><span style="margin-left:auto;"><i class="fas fa-download"></i></span></a>`;
            }
            if (msg.content) {
                messageContent = `${escapeHtml(msg.content)}<br><br>${messageContent}`;
            }
        } else {
            messageContent = escapeHtml(msg.content);
        }

        return `
            ${avatarHtml}
            <div class="message-content">
                <div class="message-bubble">${messageContent}</div>
                <span class="message-time">${formatTime(msg.created_at)}</span>
            </div>
        `;
    }

    // --- 3. Load Messages ---
    function loadMessages(conversationId) {
        if (!conversationId) return;

        fetch(`/api/chat/messages/${conversationId}/`)
            .then(response => response.json())
            .then(messages => {
                if (messages.error) return;

                messagesAreaEl.innerHTML = '';
                let lastDate = null;

                messages.forEach(msg => {
                    // Add date separator if date changed
                    const msgDate = new Date(msg.created_at);
                    const dateStr = formatDate(msgDate);

                    if (dateStr !== lastDate) {
                        const dateSeparator = document.createElement('div');
                        dateSeparator.className = 'date-separator';
                        dateSeparator.innerHTML = `<span>${dateStr}</span>`;
                        messagesAreaEl.appendChild(dateSeparator);
                        lastDate = dateStr;
                    }

                    const msgDiv = document.createElement('div');
                    msgDiv.className = `message-row ${msg.is_me ? 'sent' : 'received'}`;
                    msgDiv.innerHTML = renderMessageHTML(msg, msg.is_me);
                    messagesAreaEl.appendChild(msgDiv);
                });

                // Scroll to bottom
                messagesAreaEl.scrollTop = messagesAreaEl.scrollHeight;
            });
    }

    // --- 4. Send Message ---
    let selectedFile = null;
    const fileInput = document.getElementById('file-input');
    const btnAttach = document.getElementById('btn-attach');
    const attachmentPreview = document.getElementById('attachment-preview');
    const attachmentName = document.getElementById('attachment-name');
    const removeAttachment = document.getElementById('remove-attachment');

    btnAttach.addEventListener('click', () => {
        fileInput.click();
    });

    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (!file) return;

        // Validate file size (10MB max)
        const maxSize = 10 * 1024 * 1024;
        if (file.size > maxSize) {
            alert('File size exceeds 10MB limit');
            fileInput.value = '';
            return;
        }

        // Validate file type
        const allowedExts = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf', 'doc', 'docx', 'txt', 'zip'];
        const fileExt = file.name.split('.').pop().toLowerCase();
        if (!allowedExts.includes(fileExt)) {
            alert('Unsupported file type. Allowed: images, PDFs, documents');
            fileInput.value = '';
            return;
        }

        selectedFile = file;
        attachmentName.innerHTML = `<i class="fas fa-paperclip"></i> ${file.name} (${formatFileSize(file.size)})`;
        attachmentPreview.style.display = 'block';
    });

    removeAttachment.addEventListener('click', () => {
        selectedFile = null;
        fileInput.value = '';
        attachmentPreview.style.display = 'none';
    });

    function sendMessage() {
        const content = messageInput.value.trim();
        if (!content && !selectedFile) return;
        if (!currentConversationId) return;

        const formData = new FormData();
        if (content) formData.append('content', content);
        if (selectedFile) formData.append('attachment', selectedFile);

        fetch(`/api/chat/send/${currentConversationId}/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': CSRF_TOKEN
            },
            body: formData
        })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    messageInput.value = '';
                    messageInput.style.height = 'auto';
                    selectedFile = null;
                    fileInput.value = '';
                    attachmentPreview.style.display = 'none';
                    // Message will be received via WebSocket
                } else {
                    alert(data.error || 'Error sending message');
                }
            })
            .catch(error => {
                alert('Error sending message');
                console.error(error);
            });
    }

    btnSend.addEventListener('click', sendMessage);

    // Auto-resize textarea
    messageInput.style.overflow = 'hidden';
    messageInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });

    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // --- 5. Mute Toggle ---
    function updateMuteUI(isMuted) {
        const muteStatus = document.getElementById('header-mute-status');
        muteStatus.style.display = isMuted ? 'inline' : 'none';
        btnMute.textContent = isMuted ? 'Unmute Notifications' : 'Mute Notifications';
    }

    btnMute.addEventListener('click', (e) => {
        e.preventDefault();
        if (!currentConversationId) return;

        fetch(`/api/chat/mute/${currentConversationId}/`, {
            method: 'POST',
            headers: { 'X-CSRFToken': CSRF_TOKEN }
        })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    updateMuteUI(data.is_muted);
                    loadConversations(); // Update sidebar icon
                    headerDropdown.classList.remove('show');
                }
            });
    });

    // --- UI Interactions ---
    btnMoreOptions.addEventListener('click', () => {
        headerDropdown.classList.toggle('show');
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (!btnMoreOptions.contains(e.target) && !headerDropdown.contains(e.target)) {
            headerDropdown.classList.remove('show');
        }
    });

    // --- Initial Load ---
    loadConversations();

    // Check for ?conversation_id=X
    const urlParams = new URLSearchParams(window.location.search);
    const urlConvId = urlParams.get('conversation_id');
    if (urlConvId) {
        // Auto-select conversation after list loads
        setTimeout(() => {
            const item = document.querySelector(`.contact-item[data-id="${urlConvId}"]`);
            if (item) item.click();
        }, 500);
    } else {
        // No conversation selected, connect to global user channel for notifications
        connectWebSocket('global');
    }

    // --- Helper: Append Message (for WebSocket) ---
    function appendMessage(msg) {
        // Check if message already exists (avoid duplicates)
        const existingMsg = messagesAreaEl.querySelector(`[data-message-id="${msg.id}"]`);
        if (existingMsg) return;

        // Calculate is_me based on sender_id
        const isMe = msg.sender_id === CURRENT_USER_ID;

        // Determine if we need a date separator
        const msgDate = new Date(msg.created_at);
        const dateStr = formatDate(msgDate);

        // Check the last date separator
        const separators = messagesAreaEl.querySelectorAll('.date-separator span');
        let lastDateInDom = null;
        if (separators.length > 0) {
            lastDateInDom = separators[separators.length - 1].textContent;
        }

        if (dateStr !== lastDateInDom) {
            const dateSeparator = document.createElement('div');
            dateSeparator.className = 'date-separator';
            dateSeparator.innerHTML = `<span>${dateStr}</span>`;
            messagesAreaEl.appendChild(dateSeparator);
        }

        const msgDiv = document.createElement('div');
        msgDiv.className = `message-row ${isMe ? 'sent' : 'received'}`;
        msgDiv.dataset.messageId = msg.id;
        msgDiv.innerHTML = renderMessageHTML(msg, isMe);
        messagesAreaEl.appendChild(msgDiv);

        // Auto scroll to bottom
        messagesAreaEl.scrollTop = messagesAreaEl.scrollHeight;
    }

    // --- Utilities ---
    function formatTime(isoString) {
        const date = new Date(isoString);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    function formatDate(date) {
        const today = new Date();
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);

        // Reset time parts for comparison
        today.setHours(0, 0, 0, 0);
        yesterday.setHours(0, 0, 0, 0);
        const msgDate = new Date(date);
        msgDate.setHours(0, 0, 0, 0);

        if (msgDate.getTime() === today.getTime()) {
            return 'Today';
        } else if (msgDate.getTime() === yesterday.getTime()) {
            return 'Yesterday';
        } else {
            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        }
    }

    function formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    function escapeHtml(text) {
        if (!text) return '';
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Clean up WebSocket on page unload
    window.addEventListener('beforeunload', () => {
        if (chatSocket) {
            chatSocket.close();
        }
    });
});
