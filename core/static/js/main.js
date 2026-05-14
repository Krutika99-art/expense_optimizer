document.addEventListener('DOMContentLoaded', function () {
    const appShell = document.body;
    const sidebarToggleBtn = document.getElementById('sidebarToggleBtn');
    const sidebarCloseBtn = document.getElementById('sidebarCloseBtn');
    const sidebarBackdrop = document.getElementById('sidebarBackdrop');

    function closeSidebar() {
        appShell.classList.remove('sidebar-open');
    }

    if (sidebarToggleBtn) {
        sidebarToggleBtn.addEventListener('click', function () {
            appShell.classList.toggle('sidebar-open');
        });
    }

    if (sidebarCloseBtn) {
        sidebarCloseBtn.addEventListener('click', closeSidebar);
    }

    if (sidebarBackdrop) {
        sidebarBackdrop.addEventListener('click', closeSidebar);
    }

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            closeSidebar();
        }
    });

    const anchors = document.querySelectorAll('a[href^="#"]');
    anchors.forEach(function (anchor) {
        anchor.addEventListener('click', function (event) {
            const targetId = this.getAttribute('href');
            if (targetId && targetId.length > 1) {
                const target = document.querySelector(targetId);
                if (target) {
                    event.preventDefault();
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }
        });
    });

    const logoutForm = document.querySelector('form[action*="logout"]');
    if (logoutForm) {
        logoutForm.addEventListener('submit', function (event) {
            const confirmed = window.confirm('Are you sure you want to log out?');
            if (!confirmed) {
                event.preventDefault();
            }
        });
    }

    const revealNodes = document.querySelectorAll('[data-reveal]');
    if (revealNodes.length > 0) {
        if ('IntersectionObserver' in window) {
            const observer = new IntersectionObserver(function (entries, io) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('revealed');
                        io.unobserve(entry.target);
                    }
                });
            }, { threshold: 0.2, rootMargin: '0px 0px -30px 0px' });

            revealNodes.forEach(function (node, index) {
                node.style.transitionDelay = Math.min(index * 70, 320) + 'ms';
                observer.observe(node);
            });
        } else {
            revealNodes.forEach(function (node) {
                node.classList.add('revealed');
            });
        }
    }

    const chatbotForm = document.getElementById('chatbotForm');
    const chatbotInput = document.getElementById('chatbotInput');
    const chatbotMessages = document.getElementById('chatbotMessages');
    const chatbotSuggestions = document.getElementById('chatbotSuggestions');

    function getCsrfToken() {
        const tokenInput = chatbotForm ? chatbotForm.querySelector('input[name="csrfmiddlewaretoken"]') : null;
        return tokenInput ? tokenInput.value : '';
    }

    function appendChatMessage(role, text) {
        if (!chatbotMessages) {
            return;
        }

        const message = document.createElement('div');
        message.className = 'chat-message ' + (role === 'user' ? 'user-message' : 'bot-message');

        const avatar = document.createElement('div');
        avatar.className = 'chat-avatar';
        avatar.innerHTML = role === 'user' ? '<i class="bi bi-person"></i>' : '<i class="bi bi-stars"></i>';

        const bubble = document.createElement('div');
        bubble.className = 'chat-bubble';
        bubble.textContent = text;

        message.appendChild(avatar);
        message.appendChild(bubble);
        chatbotMessages.appendChild(message);
        chatbotMessages.scrollTop = chatbotMessages.scrollHeight;
    }

    function setChatbotLoading(isLoading) {
        if (!chatbotForm) {
            return;
        }

        const button = chatbotForm.querySelector('button[type="submit"]');
        if (button) {
            button.disabled = isLoading;
            button.innerHTML = isLoading ? '<span class="spinner-border spinner-border-sm"></span> Thinking' : '<i class="bi bi-send"></i> Send';
        }
    }

    function sendChatbotMessage(messageText) {
        const message = (messageText || '').trim();
        if (!message || !chatbotForm) {
            return;
        }

        appendChatMessage('user', message);
        chatbotInput.value = '';
        setChatbotLoading(true);

        const formData = new FormData();
        formData.append('message', message);

        const replyUrl = chatbotForm.dataset.replyUrl || chatbotForm.action;

        fetch(replyUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken()
            },
            body: formData
        })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Chat request failed');
                }
                return response.json();
            })
            .then(function (data) {
                appendChatMessage('bot', data.reply || 'I could not generate a response right now.');
            })
            .catch(function () {
                appendChatMessage('bot', 'Something went wrong while answering. Please try again.');
            })
            .finally(function () {
                setChatbotLoading(false);
                chatbotInput.focus();
            });
    }

    if (chatbotForm && chatbotInput) {
        chatbotForm.addEventListener('submit', function (event) {
            event.preventDefault();
            sendChatbotMessage(chatbotInput.value);
        });
    }

    if (chatbotSuggestions) {
        chatbotSuggestions.addEventListener('click', function (event) {
            const button = event.target.closest('.chatbot-suggestion');
            if (button) {
                sendChatbotMessage(button.textContent);
            }
        });
    }
});
