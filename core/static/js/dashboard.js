document.addEventListener('DOMContentLoaded', function () {
    const trendNode = document.getElementById('admin-trend-months');
    const incomeNode = document.getElementById('admin-income-values');
    const expenseNode = document.getElementById('admin-expense-values');
    const categoryLabelNode = document.getElementById('admin-category-labels');
    const categoryValueNode = document.getElementById('admin-category-values');

    if (!trendNode || !incomeNode || !expenseNode) {
        return;
    }

    const trendMonths = JSON.parse(trendNode.textContent);
    const incomeValues = JSON.parse(incomeNode.textContent);
    const expenseValues = JSON.parse(expenseNode.textContent);
    const categoryLabels = categoryLabelNode ? JSON.parse(categoryLabelNode.textContent) : [];
    const categoryValues = categoryValueNode ? JSON.parse(categoryValueNode.textContent) : [];

    const formatCurrency = function (value) {
        return 'Rs ' + Number(value).toLocaleString('en-IN');
    };

    const trendCtx = document.getElementById('systemFinancialTrendChart');
    if (trendCtx) {
        new Chart(trendCtx, {
            type: 'line',
            data: {
                labels: trendMonths,
                datasets: [
                    {
                        label: 'Income',
                        data: incomeValues,
                        borderColor: '#16a34a',
                        backgroundColor: 'rgba(22, 163, 74, 0.15)',
                        borderWidth: 2.5,
                        tension: 0.35,
                        fill: true,
                        pointRadius: 3
                    },
                    {
                        label: 'Expense',
                        data: expenseValues,
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239, 68, 68, 0.12)',
                        borderWidth: 2.5,
                        tension: 0.35,
                        fill: true,
                        pointRadius: 3
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                return context.dataset.label + ': ' + formatCurrency(context.parsed.y);
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function (value) {
                                return formatCurrency(value);
                            }
                        }
                    }
                }
            }
        });
    }

    const categoryCtx = document.getElementById('categorySpendingChart');
    if (categoryCtx && categoryLabels.length) {
        new Chart(categoryCtx, {
            type: 'pie',
            data: {
                labels: categoryLabels,
                datasets: [
                    {
                        data: categoryValues,
                        backgroundColor: ['#0284c7', '#10b981', '#f59e0b', '#ef4444', '#6366f1', '#14b8a6'],
                        borderColor: '#ffffff',
                        borderWidth: 2
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                return context.label + ': ' + formatCurrency(context.parsed);
                            }
                        }
                    }
                }
            }
        });
    }
});
