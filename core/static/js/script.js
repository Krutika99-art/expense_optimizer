document.addEventListener('DOMContentLoaded', function () {
    const yearNode = document.getElementById('year');
    if (yearNode) {
        yearNode.textContent = '© ' + new Date().getFullYear() + ' Expense Optimizer. All rights reserved.';
    }

    const cards = document.querySelectorAll('.stat-item, .feature-card, .workflow-card, .usecase-card');
    cards.forEach(function (card, index) {
        card.style.opacity = '0';
        card.style.transform = 'translateY(16px)';
        card.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
        setTimeout(function () {
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, 80 * index);
    });
});
