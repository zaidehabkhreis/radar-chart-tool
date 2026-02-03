/**
 * Chatbot Widget JavaScript
 * Handles chat interactions with the Gemini-powered assistant
 */

class ChatBot {
    constructor(userEmail) {
        this.container = document.getElementById('chat-container');
        this.toggleBtn = document.getElementById('chat-toggle-btn');
        this.messagesContainer = document.getElementById('chat-messages');
        this.input = document.getElementById('chat-input');
        this.sendBtn = document.getElementById('chat-send-btn');
        this.suggestionsContainer = document.getElementById('chat-suggestions');

        this.chatHistory = [];
        this.isOpen = false;
        this.isLoading = false;
        // User-specific storage key
        this.userEmail = userEmail || 'anonymous';
        this.storageKey = `chatbot_history_${this.userEmail}`;

        this.loadHistory();
        this.init();
    }

    // Static method to clear chat history for logout
    static clearHistory(userEmail) {
        const key = `chatbot_history_${userEmail}`;
        try {
            localStorage.removeItem(key);
        } catch (e) {
            console.warn('Could not clear chat history:', e);
        }
    }

    loadHistory() {
        try {
            const saved = localStorage.getItem(this.storageKey);
            if (saved) {
                this.chatHistory = JSON.parse(saved);
            }
        } catch (e) {
            console.warn('Could not load chat history:', e);
        }
    }

    saveHistory() {
        try {
            // Keep only last 20 messages to avoid storage limits
            const toSave = this.chatHistory.slice(-20);
            localStorage.setItem(this.storageKey, JSON.stringify(toSave));
        } catch (e) {
            console.warn('Could not save chat history:', e);
        }
    }

    init() {
        // Toggle chat
        this.toggleBtn.addEventListener('click', () => this.toggle());

        // Send message
        this.sendBtn.addEventListener('click', () => this.sendMessage());

        // Enter key to send
        this.input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Suggestion buttons
        this.suggestionsContainer.addEventListener('click', (e) => {
            if (e.target.classList.contains('suggestion-btn')) {
                this.input.value = e.target.textContent;
                this.sendMessage();
            }
        });
    }

    toggle() {
        this.isOpen = !this.isOpen;
        this.container.classList.toggle('active', this.isOpen);
        this.toggleBtn.classList.toggle('active', this.isOpen);

        if (this.isOpen) {
            this.input.focus();
            // Only add content if messages container is empty
            if (this.messagesContainer.children.length === 0) {
                if (this.chatHistory.length === 0) {
                    this.showWelcome();
                } else {
                    // Restore messages from history
                    this.restoreMessages();
                }
            }
        }
    }

    restoreMessages() {
        // Hide suggestions since we have history
        this.suggestionsContainer.style.display = 'none';

        // Restore all messages from history
        this.chatHistory.forEach(msg => {
            this.addMessage(msg.content, msg.role === 'user' ? 'user' : 'assistant', false);
        });
    }

    showWelcome() {
        const welcome = document.createElement('div');
        welcome.className = 'welcome-message';
        welcome.innerHTML = `
            <h4>Hi! I'm your staffing assistant</h4>
            <p>Ask me about employee skills, availability, or help finding the right team for your project.</p>
        `;
        this.messagesContainer.appendChild(welcome);
    }

    async sendMessage() {
        const message = this.input.value.trim();
        if (!message || this.isLoading) return;

        // Remove welcome message if present
        const welcome = this.messagesContainer.querySelector('.welcome-message');
        if (welcome) welcome.remove();

        // Hide suggestions after first message
        this.suggestionsContainer.style.display = 'none';

        // Add user message
        this.addMessage(message, 'user');
        this.chatHistory.push({ role: 'user', content: message });
        this.saveHistory();

        // Clear input
        this.input.value = '';

        // Show typing indicator
        this.showTyping();
        this.isLoading = true;
        this.sendBtn.disabled = true;

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    question: message,
                    history: this.chatHistory.slice(0, -1) // Exclude current message
                }),
            });

            const data = await response.json();

            // Remove typing indicator
            this.hideTyping();

            if (data.error) {
                this.addMessage(data.error, 'assistant error');
            } else {
                this.addMessage(data.answer, 'assistant');
                this.chatHistory.push({ role: 'assistant', content: data.answer });
                this.saveHistory();
            }
        } catch (error) {
            this.hideTyping();
            this.addMessage('Failed to connect to the server. Please try again.', 'assistant error');
        } finally {
            this.isLoading = false;
            this.sendBtn.disabled = false;
            this.input.focus();
        }
    }

    addMessage(content, type, shouldScroll = true) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${type}`;

        // Convert markdown-like formatting to HTML
        let formattedContent = this.formatMessage(content);
        messageDiv.innerHTML = formattedContent;

        this.messagesContainer.appendChild(messageDiv);
        if (shouldScroll) {
            this.scrollToBottom();
        }
    }

    formatMessage(content) {
        // Clean up any weird colon-prefixed names (: Name -> **Name**)
        content = content.replace(/^:\s*(\w+)\s*$/gm, '**$1**');

        // Remove markdown table formatting
        content = content.replace(/^\|[\s\-:]+\|[\s\-:]*\|?.*$/gm, '');
        content = content.replace(/^\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]*)\s*\|?$/gm, (match, col1, col2, col3) => {
            col1 = col1.trim();
            col2 = col2.trim();
            col3 = col3 ? col3.trim() : '';
            if (col1 && col2) {
                return col3 ? `- **${col1}**: ${col2} (${col3})` : `- **${col1}**: ${col2}`;
            }
            return match;
        });

        // Convert **Name** on its own line to employee card
        content = content.replace(/^\*\*([A-Za-z]+(?:\s+[A-Za-z]+)?)\*\*\s*$/gm, '<div class="employee-card"><div class="employee-name">$1</div>');

        // Close employee cards before next employee card or end
        content = content.replace(/(<\/ul>)\s*\n*(<div class="employee-card">)/g, '$1</div>\n$2');

        // Convert **bold** to <strong> (for remaining bold text)
        content = content.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

        // Convert bullet points with special styling for metrics
        content = content.replace(/^[\-\*]\s+(Generative AI|AI and Machine Learning|GCP Skills|Technical Skills|Capacity|Utilization|Justification|[A-Za-z\s]+):?\s*(.+)$/gm, (match, label, value) => {
            label = label.trim();
            value = value.trim();
            if (label === 'Justification') {
                return `<li class="justification"><span class="metric-label">${label}:</span> ${value}</li>`;
            }
            return `<li><span class="metric-label">${label}:</span> <span class="metric-val">${value}</span></li>`;
        });

        // Convert remaining bullet points
        content = content.replace(/^[\-\*]\s+(.+)$/gm, '<li>$1</li>');

        // Wrap consecutive <li> in <ul>
        content = content.replace(/(<li[^>]*>.*<\/li>\n?)+/g, (match) => `<ul class="metrics-list">${match}</ul>`);

        // Convert line breaks
        content = content.replace(/\n/g, '<br>');

        // Clean up
        content = content.replace(/<\/ul><br>/g, '</ul>');
        content = content.replace(/<br><br><br>/g, '<br><br>');
        content = content.replace(/<\/div><br><br>/g, '</div>');
        content = content.replace(/<br><div/g, '<div');
        content = content.replace(/<div class="employee-card"><br>/g, '<div class="employee-card">');

        // Close any unclosed employee cards at the end
        const openCards = (content.match(/<div class="employee-card">/g) || []).length;
        const closedCards = (content.match(/<\/div>\s*(?=<div class="employee-card">|$)/g) || []).length;
        if (openCards > closedCards) {
            content += '</div>'.repeat(openCards - closedCards);
        }

        return content;
    }

    showTyping() {
        const typing = document.createElement('div');
        typing.className = 'typing-indicator';
        typing.id = 'typing-indicator';
        typing.innerHTML = '<span></span><span></span><span></span>';
        this.messagesContainer.appendChild(typing);
        this.scrollToBottom();
    }

    hideTyping() {
        const typing = document.getElementById('typing-indicator');
        if (typing) typing.remove();
    }

    scrollToBottom() {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }
}

// Initialize chatbot when DOM is ready
// The userEmail should be set in a script tag before this file loads
document.addEventListener('DOMContentLoaded', () => {
    const userEmail = window.chatbotUserEmail || 'anonymous';
    window.chatBot = new ChatBot(userEmail);
});
